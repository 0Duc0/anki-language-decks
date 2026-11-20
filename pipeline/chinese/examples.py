"""Chinese: more example sentences for the CC-CEDICT deck.

scan()    one pass over the Chinese–English corpus (Tatoeba, TED2020 zh-cn/zh-tw, OpenSubtitles
          zh-cn/zh-tw). Sentences are segmented with jieba using the deck's own words as dictionary,
          so a word only counts where it is a word (高兴 in 很高兴, not 兴 inside 高兴).
improve() appends sentences (traditional on top, simplified below, English, pinyin on request, TTS)
          with Card Redesign's own renderer, until a word has three. Existing examples stay as they are.
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

CR = paths.CARD_REDESIGN
sys.path[:0] = [str(HERE.parent), str(HERE.parent / "vietnamese"), CR]
import english  # noqa: E402
from cn import _Ex, _ex_html  # noqa: E402  (Card Redesign's Chinese example renderer)
from deck import parse_defs, plain  # noqa: E402
from html_tree import parse  # noqa: E402
from improve import misaligned  # noqa: E402
from zh_lex import Lexicon  # noqa: E402

DECK = paths.deck("cn_raw.anki2")
SRC_W = {"Tatoeba": 3.0, "TED2020": 1.0, "OpenSubtitles": 1.0}
KEEP = 8
TARGET = 3
SRC_LABEL = {"TED2020": "TED2020 via OPUS (CC BY-NC-ND 4.0)", "OpenSubtitles": "OpenSubtitles 2018 via OPUS"}


def load_notes():
    from anki.collection import Collection

    col = Collection(DECK)
    try:
        m = col.models.by_name("CC-CEDICT (ZH - EN)")
        names = [f["name"] for f in m["flds"]]
        out = []
        for nid, guid, flds in col.db.all("select id, guid, flds from notes where mid = ?", m["id"]):
            f = dict(zip(names, flds.split("\x1f")))
            _d, _r, items = parse_defs(f["Senses"])
            out.append((nid, guid, f, [it.text for it in items]))
        return out
    finally:
        col.close()


def char_t2s() -> dict[int, str]:
    """Character-level traditional -> simplified table (OpenCC), only to find words; display keeps the original."""
    import opencc

    cc = opencc.OpenCC("t2s")
    table = {}
    for cp in range(0x4E00, 0xA000):
        ch = chr(cp)
        s = cc.convert(ch)
        if s != ch and len(s) == 1:
            table[cp] = s
    return table


def scan(notes) -> dict:
    import jieba

    jieba.setLogLevel(60)
    words: dict[str, list[int]] = defaultdict(list)
    heads = {}
    userdict = ROOT / "data/work/cn_userdict.txt"
    with open(userdict, "w", encoding="utf-8") as f:
        for idx, (nid, guid, fl, senses) in enumerate(notes):
            s = plain(fl["Simplified"])
            if s and " " not in s:
                words[s].append(idx)
                rank = fl.get("FrequencyCount", "") or "3"
                f.write(f"{s} {max(3, int(re.sub(r'[^0-9]', '', rank) or 3))}\n")
            heads[idx] = [english.heads(x) for x in senses]
    jieba.load_userdict(str(userdict))
    t2s = char_t2s()
    heaps: dict[int, list] = defaultdict(list)
    rnd = random.Random(11)
    t0 = time.time()
    with gzip.open(ROOT / "data/corpus/zh.tsv.gz", "rt", encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            src, ref, zh, en = line.rstrip("\n").split("\t")
            if misaligned(zh, en):
                continue
            simp = zh.translate(t2s)
            toks = jieba.lcut(simp, HMM=False)
            en_st = english.stems(en)
            n = len(re.sub(r"\W", "", zh))
            base = SRC_W[src] - 0.1 * max(0, n - 20) - 0.3 * max(0, 6 - n) + (0.3 if zh[-1:] in "。！？" else 0)
            seen = set()
            for tok in toks:
                for idx in words.get(tok, ()):
                    if idx in seen:
                        continue
                    seen.add(idx)
                    hits = tuple(j for j, h in enumerate(heads[idx]) if h & en_st)
                    if src == "OpenSubtitles" and not hits:
                        continue
                    score = base + (1.2 if hits else 0) + rnd.random() * 0.01
                    heap = heaps[idx]
                    entry = (score, src, ref, zh, en, hits)
                    if len(heap) < KEEP:
                        heapq.heappush(heap, entry)
                    elif score > heap[0][0]:
                        heapq.heapreplace(heap, entry)
            if i % 500000 == 0:
                print(i, round(time.time() - t0), "s", file=sys.stderr, flush=True)
    return dict(heaps)


HEAD = re.compile(r'^<details class="cr-v1 cr-ex" data-multi="([01])"( open(?:="")?)?><summary>Examples \((\d+)\)</summary>(.*)</details>$', re.S)


CJK_GAP = re.compile(r"(?<=[\u4e00-\u9fff\u3400-\u4dbf])\s+(?=[\u4e00-\u9fff\u3400-\u4dbf])")


def scripts(zh: str, src: str, ref: str, conv) -> tuple[str, str]:
    """(simplified, traditional) of a corpus sentence. The corpus' own script is kept as it is;
    the other one comes from OpenCC (Taiwan standard for traditional)."""
    zh = CJK_GAP.sub("，", zh.strip())               # subtitle lines mark clause breaks with a space
    t2s, s2tw = conv
    simp = t2s.convert(zh)
    traditional_source = ref.startswith("zh_tw") or (src == "Tatoeba" and simp != zh)
    trad = zh if traditional_source else s2tw.convert(zh)
    return simp, trad


def improve(notes, heaps) -> dict[int, dict[str, str]]:
    import opencc

    conv = (opencc.OpenCC("t2s"), opencc.OpenCC("s2tw"))
    lx = Lexicon()
    for _nid, _g, f, _s in notes:
        lx.add(f["Simplified"], f["Traditional"], f["Pinyin"])
    changes = {}
    for idx, (nid, guid, f, senses) in enumerate(notes):
        cands = sorted(heaps.get(idx, []), reverse=True)
        if not cands:
            continue
        old = f["Examples"]
        if old:
            m = HEAD.match(old)
            if not m:
                continue                      # unknown shape: leave the note alone
            multi, opened, body = m.group(1), m.group(2) or "", m.group(4)
            blocks = [c.outer_html() for c in parse(body).children if c.tag == "div"]
        else:
            multi, opened, blocks = "0", ' open=""', []
        texts = {re.sub(r"\W", "", plain(b)) for b in blocks}
        sentences = sum(1 for b in blocks if 'class="ex ex-phrase"' not in b)
        simp, trad = plain(f["Simplified"]), plain(f["Traditional"])
        new_blocks, sources = [], []
        for score, src, ref, zh, en, hits in cands:
            if sentences + len(new_blocks) >= TARGET:
                break
            s_text, t_text = scripts(zh, src, ref, conv)
            if any(re.sub(r"\W", "", s_text) in t for t in texts):
                continue
            tts = s_text.replace(simp, f" {simp} ", 1) if simp in s_text else s_text
            esc = lambda t: html.escape(t, quote=False)  # noqa: E731
            if s_text == t_text:
                ex = _Ex(both=esc(s_text))
            else:
                ex = _Ex(simp=esc(s_text), trad=esc(t_text))
            ex.translation = esc(en)
            ex.reading = esc(lx.pinyin(s_text))
            ex.audio = [f"[anki:tts lang=zh_CN]{esc(' '.join(tts.split()))}[/anki:tts]"]
            new_blocks.append(_ex_html(ex, simp, trad, lx))
            texts.add(re.sub(r"\W", "", s_text))
            sources.append(f"Tatoeba · sentence {ref}" if src == "Tatoeba" else SRC_LABEL[src])
        if not new_blocks:
            continue
        first_phrase = next((i for i, b in enumerate(blocks) if 'class="ex ex-phrase"' in b), len(blocks))
        allb = blocks[:first_phrase] + new_blocks + blocks[first_phrase:]
        ch = {"Examples": f'<details class="cr-v1 cr-ex" data-multi="{multi}"{opened}>'
                          f"<summary>Examples ({len(allb)})</summary>" + "".join(allb) + "</details>"}
        src_html = f["ExampleSources"]
        items = re.findall(r"<li>(.*?)</li>", src_html, re.S) if src_html else []
        for s in sources:
            if s not in items:
                items.append(s)
        ch["ExampleSources"] = '<div class="cr-v1 cr-src"><ul>' + "".join(f"<li>{s}</li>" for s in items) + "</ul></div>"
        changes[nid] = ch
    return changes


if __name__ == "__main__":
    notes = load_notes()
    if "--improve-only" not in sys.argv:
        heaps = scan(notes)
        pickle.dump(heaps, open(ROOT / "data/work/cn_heaps.pkl", "wb"))
    heaps = pickle.load(open(ROOT / "data/work/cn_heaps.pkl", "rb"))
    changes = improve(notes, heaps)
    pickle.dump(changes, open(ROOT / "data/work/cn_changes.pkl", "wb"))
    print("notes with examples before:", sum(1 for _, _, f, _ in notes if f["Examples"]),
          "| notes improved:", len(changes),
          "| without examples now:", sum(1 for nid, _, f, _ in notes if not f["Examples"] and nid not in changes))
