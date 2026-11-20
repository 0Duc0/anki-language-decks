"""Japanese: more example sentences for the JMdict deck.

scan()    one pass over the Japanese–English corpus with UniDic (fugashi): a word is found when
          its written form equals consecutive tokens, the last one in dictionary form (食べ → 食べる),
          and no longer dictionary word covers the same place. Best candidates per note are kept.
improve() adds sentences until a word has three (more only for a meaning without one), in the
          deck's existing example layout (sense caption, highlighted word, TTS, translation).
"""
from __future__ import annotations

import gzip
import heapq
import html
import pickle
import random
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))
import paths  # noqa: E402

sys.path[:0] = [str(HERE.parent / "vietnamese"), paths.CARD_REDESIGN]
import english  # noqa: E402
from common import SimpleEx, render_examples  # noqa: E402
from deck import parse_defs, plain  # noqa: E402  (cr-defs parser, same layout in all three decks)
from improve import misaligned, parse_examples  # noqa: E402

DECK = paths.deck("jp.anki2")
SRC_W = {"Tatoeba": 3.0, "TED2020": 1.0, "OpenSubtitles": 1.0}
KEEP = 10
MAX_TOK = 6
TARGET, MAXIMUM = 3, 5
SRC_LABEL = {"Tatoeba": "Tatoeba", "TED2020": "TED2020 via OPUS", "OpenSubtitles": "OpenSubtitles via OPUS"}
KANA = re.compile(r"^[぀-ヿー]+$")


def load_notes():
    from anki.collection import Collection

    col = Collection(DECK)
    try:
        m = col.models.by_name("JMdict (JP - EN)")
        names = [f["name"] for f in m["flds"]]
        out = []
        for nid, guid, flds in col.db.all("select id, guid, flds from notes where mid = ?", m["id"]):
            f = dict(zip(names, flds.split("\x1f")))
            _defs, _rest, items = parse_defs(f["Senses"])
            out.append((nid, guid, f, [it.text for it in items]))
        return out
    finally:
        col.close()


def scan(notes) -> dict:
    import fugashi

    tagger = fugashi.Tagger()
    by_word: dict[str, list[int]] = defaultdict(list)
    heads: dict[int, list[set[str]]] = {}
    for idx, (nid, guid, f, senses) in enumerate(notes):
        w = plain(f["Headword (JP)"])
        if w:
            by_word[w].append(idx)
        heads[idx] = [english.heads(s) for s in senses] or [english.heads(plain(f["Gloss"]))]
    maxlen = max(len(w) for w in by_word)
    heaps: dict[int, list] = defaultdict(list)
    rnd = random.Random(7)
    t0 = time.time()
    with gzip.open(ROOT / "data/corpus/ja.tsv.gz", "rt", encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            src, ref, ja, en = line.rstrip("\n").split("\t")
            if misaligned(ja, en):
                continue
            toks = tagger(ja)
            pos, starts, surf, base = 0, [], [], []
            for t in toks:
                start = ja.find(t.surface, pos)
                if start < 0:
                    start = pos
                starts.append(start)
                pos = start + len(t.surface)
                surf.append(t.surface)
                b = getattr(t.feature, "orthBase", None) or t.surface
                base.append(b if b != "*" else t.surface)
            found = []                                   # (start, end, note index)
            for a in range(len(toks)):
                acc = ""
                for b in range(a, min(a + MAX_TOK, len(toks))):
                    for cand in (acc + surf[b], acc + base[b]):
                        if len(cand) <= maxlen and cand in by_word:
                            end = starts[b] + len(surf[b])
                            found.append((starts[a], end, cand))
                    acc += surf[b]
            if not found:
                continue
            # a word inside a longer dictionary word does not count (先 in 先生, 脚本 in 脚本家 if listed)
            spans = {(s, e) for s, e, _ in found}
            kept = [(s, e, w) for s, e, w in found
                    if not any((s2 <= s and e <= e2) and (s2, e2) != (s, e) for s2, e2 in spans)]
            en_st = english.stems(en)
            n = len(ja)
            base_score = SRC_W[src] - 0.08 * max(0, n - 24) - 0.25 * max(0, 7 - n) + (0.3 if ja[-1:] in "。！？" else 0)
            seen = set()
            for s, e, w in kept:
                for idx in by_word[w]:
                    if idx in seen:
                        continue
                    seen.add(idx)
                    hits = tuple(j for j, h in enumerate(heads[idx]) if h & en_st)
                    if src == "OpenSubtitles" and not hits:
                        continue
                    score = base_score + (1.2 if hits else 0) + rnd.random() * 0.01
                    heap = heaps[idx]
                    entry = (score, src, ref, ja, en, s, e, hits)
                    if len(heap) < KEEP:
                        heapq.heappush(heap, entry)
                    elif score > heap[0][0]:
                        heapq.heapreplace(heap, entry)
            if i % 200000 == 0:
                print(i, round(time.time() - t0), "s", file=sys.stderr)
    return dict(heaps)


def _hl(text: str, a: int, b: int) -> str:
    e = lambda t: html.escape(t, quote=False)  # noqa: E731
    return e(text[:a]) + f'<b class="hl">{e(text[a:b])}</b>' + e(text[b:])


def improve(notes, heaps) -> dict[int, dict[str, str]]:
    changes = {}
    for idx, (nid, guid, f, senses) in enumerate(notes):
        cands = sorted(heaps.get(idx, []), reverse=True)
        if not cands:
            continue
        parsed = parse_examples(f["Examples"]) if f["Examples"] else ([], "")
        if parsed is None:
            continue
        exs, src_line = parsed
        sentences = [e for e in exs if not e.phrase]
        have = {re.sub(r"\W", "", plain(e.text)) for e in exs}
        covered = {e.key for e in sentences if e.key}
        added, sources = [], []
        for score, src, ref, ja, en, a, b, hits in cands:
            if len(sentences) + len(added) >= MAXIMUM:
                break
            k = re.sub(r"\W", "", ja)
            if k in have:
                continue
            key = senses[hits[0]][:70] if hits and len(senses) > 1 else ""
            if len(sentences) + len(added) >= TARGET and (not key or key in covered):
                continue
            added.append(SimpleEx(text=_hl(ja, a, b), translation=html.escape(en, quote=False),
                                  audio=[f"[anki:tts lang=ja_JP]{html.escape(ja, quote=False)}[/anki:tts]"],
                                  key=key, lang="ja"))
            have.add(k)
            covered.add(key)
            sources.append(SRC_LABEL[src] if src != "Tatoeba" else f"Tatoeba · sentence {ref}")
        if not added:
            continue
        final = sentences + added + [e for e in exs if e.phrase]
        body = render_examples(final, [])
        uniq = []
        for s in ([src_line] if src_line else []) + sources:
            if s not in uniq:
                uniq.append(s)
        body += '<p class="ex-src">Example sources: ' + " · ".join(uniq) + "</p>"
        changes[nid] = {"Examples": body}
    return changes


if __name__ == "__main__":
    notes = load_notes()
    if "--improve-only" not in sys.argv:
        heaps = scan(notes)
        pickle.dump(heaps, open(ROOT / "data/work/jp_heaps.pkl", "wb"))
    heaps = pickle.load(open(ROOT / "data/work/jp_heaps.pkl", "rb"))
    changes = improve(notes, heaps)
    pickle.dump(changes, open(ROOT / "data/work/jp_changes.pkl", "wb"))
    had = sum(1 for _, _, f, _ in notes if f["Examples"])
    print("notes with examples before:", had, "| notes improved:", len(changes),
          "| without examples now:", sum(1 for nid, _, f, _ in notes if not f["Examples"] and nid not in changes))
