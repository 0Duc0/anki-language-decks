"""Parallel sentence corpora: Tatoeba, OPUS TED2020 and OPUS OpenSubtitles 2018.

`build(lang)` writes data/corpus/<lang>.tsv.gz with one cleaned, de-duplicated pair per line:
    source <TAB> reference <TAB> sentence <TAB> english
Sources are ranked later (Tatoeba > TED2020 > OpenSubtitles); this module only cleans.
"""
from __future__ import annotations

import bz2
import gzip
import io
import re
import sys
import tarfile
import unicodedata
import zipfile
from pathlib import Path

RAW = Path(__file__).resolve().parents[1] / "corpora"          # downloads (not committed)
OUT = Path(__file__).resolve().parents[1] / "data" / "corpus"

TATOEBA = {"vi": "vie", "zh": "cmn", "ja": "jpn"}
OPUS = {"vi": ["vi"], "zh": ["zh_cn", "zh_tw"], "ja": ["ja"]}

# Lines that are never good learner examples
BAD = re.compile(r"https?://|www\.|@|\.com\b|[<>{}\[\]\\|#*_=~^]|\d{4,}|^[-–—.\s]*$")
EN_BLOCK = set("""fuck fucking fucked fucker motherfucker shit shitty bitch bitches bastard cunt dick dicks cock
 pussy whore slut asshole nigger nigga faggot fag retard rape raped raping rapist porn horny blowjob tits boobs
 cum suck sucks sucking sex sexy sexual naked jerk damn goddamn hell crap piss pissed bloody bullshit ass""".split())
EN_WORD = re.compile(r"[a-z']+")
LEN = {"vi": (3, 22), "zh": (4, 28), "ja": (5, 32)}       # syllables (vi) / characters (zh, ja)


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", " ".join(s.split()))


def size(lang: str, text: str) -> int:
    return len(text.split()) if lang == "vi" else len(re.sub(r"[\s\W\d]", "", text))


def clean_pair(lang: str, text: str, en: str) -> tuple[str, str] | None:
    text, en = nfc(text).strip(" -–—\"'"), nfc(en).strip(" -–—\"'")
    if not text or not en or BAD.search(text) or BAD.search(en):
        return None
    lo, hi = LEN[lang]
    n = size(lang, text)
    if not lo <= n <= hi:
        return None
    words = EN_WORD.findall(en.lower())
    if not 2 <= len(words) <= 30 or EN_BLOCK & set(words):
        return None
    if en.isupper() or text.isupper():
        return None
    if lang == "vi":
        # must be Vietnamese (Latin with diacritics), English must not just repeat the sentence
        if not re.search(r"[À-ỹđĐ]", text) or text.lower() == en.lower():
            return None
        if re.search(r"[぀-ヿ一-鿿]", text):
            return None
    elif lang == "zh":
        if not re.search(r"[一-鿿]", text) or re.search(r"[぀-ヿ]", text):
            return None
        if re.search(r"[A-Za-z]{3,}", text):
            return None
    elif lang == "ja":
        if not re.search(r"[぀-ヿ]", text) or re.search(r"[A-Za-z]{3,}", text):
            return None
    # length ratio between the two sides catches many misalignments
    ratio = len(en) / max(1, len(text))
    if lang == "vi" and not 0.45 <= ratio <= 2.2:
        return None
    if lang in ("zh", "ja") and not 0.9 <= ratio <= 9:
        return None
    return text, en


def tatoeba(lang: str):
    code = TATOEBA[lang]
    texts = {}
    with bz2.open(RAW / f"{code}_sentences.tsv.bz2", "rt", encoding="utf-8") as f:
        for line in f:
            sid, _, text = line.rstrip("\n").split("\t", 2)
            texts[int(sid)] = text
    eng = {}
    with bz2.open(RAW / "eng_sentences.tsv.bz2", "rt", encoding="utf-8") as f:
        for line in f:
            sid, _, text = line.rstrip("\n").split("\t", 2)
            eng[int(sid)] = text
    best: dict[int, str] = {}
    with tarfile.open(RAW / "links.tar.bz2") as tar:
        member = next(m for m in tar.getmembers() if m.name.endswith(".csv"))
        for line in io.TextIOWrapper(tar.extractfile(member), encoding="utf-8"):
            a, b = line.split("\t")
            a, b = int(a), int(b)
            if a in texts and b in eng:
                cur = best.get(a)
                if cur is None or len(eng[b]) < len(cur):      # shortest direct English translation
                    best[a] = eng[b]
    for sid, en in best.items():
        yield "Tatoeba", str(sid), texts[sid], en


def opus(lang: str, corpus: str):
    for code in OPUS[lang]:
        zpath = RAW / (f"ted_en-{code}.zip" if corpus == "TED2020" else f"os_en-{code}.zip")
        name = "TED2020" if corpus == "TED2020" else "OpenSubtitles"
        with zipfile.ZipFile(zpath) as z:
            en_name = next(n for n in z.namelist() if n.endswith(".en"))
            tg_name = next(n for n in z.namelist() if n.endswith("." + code))
            with z.open(en_name) as fe, z.open(tg_name) as ft:
                for i, (e, t) in enumerate(zip(io.TextIOWrapper(fe, encoding="utf-8", errors="replace"),
                                               io.TextIOWrapper(ft, encoding="utf-8", errors="replace"))):
                    yield name, f"{code}:{i}", t.strip(), e.strip()


def build(lang: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{lang}.tsv.gz"
    seen: set[int] = set()
    counts: dict[str, int] = {}
    with gzip.open(path, "wt", encoding="utf-8") as out:
        for gen in (tatoeba(lang), opus(lang, "TED2020"), opus(lang, "OpenSubtitles")):
            for src, ref, text, en in gen:
                pair = clean_pair(lang, text, en)
                if pair is None:
                    continue
                key = hash(re.sub(r"\W", "", pair[0].lower()))
                if key in seen:
                    continue
                seen.add(key)
                counts[src] = counts.get(src, 0) + 1
                out.write(f"{src}\t{ref}\t{pair[0]}\t{pair[1]}\n")
    print(lang, counts, file=sys.stderr)
    return path


def read(lang: str):
    with gzip.open(OUT / f"{lang}.tsv.gz", "rt", encoding="utf-8") as f:
        for line in f:
            src, ref, text, en = line.rstrip("\n").split("\t")
            yield src, ref, text, en


if __name__ == "__main__":
    for lang in sys.argv[1:]:
        build(lang)
