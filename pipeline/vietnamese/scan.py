"""One pass over the Vietnamese–English corpus.

Collects, for every word of the lexicon:
  * frequency (agreed segmentation tokens), split by source
  * the best example candidates (bounded heap per word)
  * for deck words: how often each listed meaning matches the English translation ("evidence")
Writes data/work/vn_scan.pkl.
"""
from __future__ import annotations

import gzip
import heapq
import json
import math
import pickle
import random
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
import paths  # noqa: E402
import deck  # noqa: E402
import english  # noqa: E402
from seg import SYL, Segmenter, norm  # noqa: E402
from wordfreq import zipf_frequency  # noqa: E402

ROOT = HERE.parents[1]
SRC_W = {"Tatoeba": 3.0, "TED2020": 1.0, "OpenSubtitles": 1.0}
KEEP = 24
MIN_IDF = 2.3   # the matched English word occurs in under ~10 % of sentences


def lexicon(notes) -> set[str]:
    V = "/mnt/user-data/uploads/ANKI/Anki Deck Preperation/Vietnamese"
    words = {norm(n.word) for n in notes}
    for line in open(f"{V}/reports/2026-11-15_vietnamese_audit/kaikki-current.jsonl", encoding="utf-8"):
        r = json.loads(line)
        if r.get("lang_code") == "vi" and SYL.fullmatch(norm(r["word"]).replace(" ", "x")) is None:
            pass
        if r.get("lang_code") == "vi":
            w = norm(r["word"])
            if all(SYL.fullmatch(p) for p in w.split()):
                words.add(w)
    for name in ("fvdp_vi_en.jsonl", "uvd_vi_vi.jsonl"):
        for line in open(f"{V}/work/v8_lexicon/{name}", encoding="utf-8"):
            w = norm(json.loads(line)["word"])
            if w and all(SYL.fullmatch(p) for p in w.split()):
                words.add(w)
    return words


_zipf: dict[str, float] = {}


def zipf(s: str) -> float:
    v = _zipf.get(s)
    if v is None:
        v = _zipf[s] = zipf_frequency(s, "vi")
    return v


def base_score(src: str, syl: list[str], text: str) -> float:
    n = len(syl)
    score = SRC_W[src]
    score -= 0.18 * max(0, n - 12) + 0.35 * max(0, 5 - n)
    # simple vocabulary: average syllable frequency
    score += 0.5 * (sum(min(zipf(s), 6.5) for s in syl) / max(1, n) - 4.5)
    # names in the middle of a sentence make poor examples
    caps = sum(1 for w in text.split()[1:] if w[:1].isupper())
    score -= 0.5 * caps
    if text[-1:] in ".!?…":
        score += 0.3
    return score


def main() -> None:
    notes = deck.load(paths.deck("vn.anki2"))
    lex = lexicon(notes)
    print("lexicon", len(lex), file=sys.stderr)
    seg = Segmenter(lex)
    sense_kw = {}
    for n in notes:
        if len(n.items) >= 1:
            sense_kw[norm(n.word)] = [english.heads(it.text) for it in n.items]
    # how rare each English stem is: a match on "left" or "go" says little, on "spear" a lot
    df: Counter = Counter()
    total = 0
    with gzip.open(ROOT / "data/corpus/vi.tsv.gz", "rt", encoding="utf-8") as f:
        for line in f:
            df.update(english.stems(line.rsplit("\t", 1)[1]))
            total += 1
    idf = {w: math.log(total / c) for w, c in df.items()}
    for kws in sense_kw.values():
        for j, kw in enumerate(kws):
            kws[j] = {k: idf.get(k, 12.0) for k in kw}
    freq: Counter = Counter()
    freq_src: dict[str, Counter] = defaultdict(Counter)
    evidence: dict[str, list[float]] = {}
    heaps: dict[str, list] = defaultdict(list)
    rnd = random.Random(7)
    t0 = time.time()
    with gzip.open(ROOT / "data/corpus/vi.tsv.gz", "rt", encoding="utf-8") as f:
        for i, line in enumerate(f):
            src, ref, vi, en = line.rstrip("\n").split("\t")
            toks = seg.tokens(vi)
            if not toks:
                continue
            syl = [s for s, _, _ in seg.syllables(vi)]
            base = base_score(src, syl, vi)
            en_st = english.stems(en)
            seen = set()
            for w, a, b in toks:
                if w in seen:
                    continue
                seen.add(w)
                freq[w] += 1
                freq_src[w][src] += 1
                kws = sense_kw.get(w)
                hits = []
                if kws:
                    weights = [max((v for k, v in kw.items() if k in en_st), default=0.0) for kw in kws]
                    best = max(weights)
                    if best >= MIN_IDF:
                        # only the meaning(s) with the most specific matching word get the credit
                        hits = [j for j, v in enumerate(weights) if v >= best - 0.01]
                        ev = evidence.setdefault(w, [0.0] * len(kws))
                        for j in hits:
                            ev[j] += SRC_W[src] / len(hits)
                # OpenSubtitles lines need a meaning match: alignment there is noisy
                if src == "OpenSubtitles" and kws and not hits:
                    continue
                score = base + (1.2 if hits else 0.0) + rnd.random() * 0.01
                h = heaps[w]
                entry = (score, src, ref, vi, en, a, b, tuple(hits))
                if len(h) < KEEP:
                    heapq.heappush(h, entry)
                elif score > h[0][0]:
                    heapq.heapreplace(h, entry)
            if i % 250000 == 0:
                print(i, round(time.time() - t0), "s", file=sys.stderr)
    out = ROOT / "data/work/vn_scan.pkl"
    with open(out, "wb") as fo:
        pickle.dump({"freq": freq, "freq_src": dict(freq_src), "evidence": evidence,
                     "heaps": dict(heaps), "lexicon": sorted(lex)}, fo)
    print("done", out, len(freq), "words seen", file=sys.stderr)


if __name__ == "__main__":
    main()
