"""New Vietnamese notes for words the deck is missing.

Which words
-----------
* in FVDP (English glosses) and seen at least 3 times in the corpus,
* in Underthesea only (Vietnamese definitions) and seen at least 10 times, with an English gloss
  written by hand in data/curated/vn_new_glosses_*.tsv (rows marked "-" are left out),
* place, country and other proper names from Wiktionary that are seen at least 3 times
  (personal names, brands and Hán/Nôm characters are left out).

The fields are built exactly like the existing notes: the v8 dictionary builder (content.py)
writes the raw dictionary sections, Card Redesign's Vietnamese cleaner turns them into the
cr-v1 layout, and improve.py adds example sentences and hints.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import pickle
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))
import paths  # noqa: E402

sys.path[:0] = [str(HERE), str(HERE / "v8"), paths.CARD_REDESIGN]
import content as c  # noqa: E402  (v8 dictionary builder)
import deck  # noqa: E402
import improve  # noqa: E402
import vn as cr_vn  # noqa: E402  (Card Redesign cleaner)
from seg import norm  # noqa: E402
from wordfreq import zipf_frequency  # noqa: E402

V = "/mnt/user-data/uploads/ANKI/Anki Deck Preperation/Vietnamese"
PLACE = re.compile(r"\b(country|continent|city|capital|province|planet|island|region|river|ocean|sea|mountain|"
                   r"holiday|festival|language|earth|ethnic|empire|dynasty|state|kingdom|republic|desert|lake|"
                   r"peninsula|archipelago|district|prefecture|county|moon|sun|star|galaxy|middle east|west|east)\b", re.I)
PERSON = re.compile(r"\b(given name|surname|male name|female name|nickname|company|brand|website|trademark)\b", re.I)
# canonical (v8) field name -> name in the user's collection (renamed 2026-11-19)
LIVE = {"Vietnamese": "Headword (VN)", "English": "Gloss", "Tier": "FrequencyBand", "Frequency": "FrequencyInfo",
        "PartOfSpeech": "PartOfSpeech", "ExampleVietnamese": "Examples", "ExampleEnglish": "ExampleTranslations",
        "ExampleSource": "ExampleSources", "DetailsHTML": "DictionaryEntry", "HumanAudioPrimaryHTML": "Audio",
        "HumanAudioAlternativesHTML": "AudioAlternatives", "SourcesHTML": "Sources", "OriginalGUID": "EntryID",
        "RecognitionHintHTML": "ProductionHint", "Notizen": "PersonalNotes",
        "RecognitionAlternativesHTML": "ContextHint"}


def stable_guid(word: str) -> str:
    """The same word always gets the same note id, so applying a pack twice never duplicates a note."""
    return base64.b85encode(hashlib.sha1(f"vn-new:{word}".encode()).digest()[:8]).decode()


def manual_glosses() -> dict[str, tuple[str, str]]:
    rows = {}
    for line in (ROOT / "data/work/uvd_only_to_gloss.tsv").read_text(encoding="utf-8").splitlines():
        i, w, *_ = line.split("\t")
        rows[i] = w
    out = {}
    for p in sorted((ROOT / "data/curated").glob("vn_new_glosses_*.tsv")):
        for line in p.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) >= 3 and parts[1] != "-":
                out[rows[parts[0]]] = (parts[1], parts[2])
    return out


def frequency_info(word: str) -> str:
    z = zipf_frequency(word, "vi")
    if z <= 0:
        return "Dictionary reference · no reliable frequency estimate"
    return f"Dictionary reference · Zipf estimate {z:.2f}" + (" · phrase estimate" if " " in word else "")


def candidates(freq, existing: set[str], manual: dict) -> list[tuple[str, str]]:
    """[(word, reason)] in a stable order."""
    kk: dict[str, list] = {}
    for line in open(f"{V}/reports/2026-11-15_vietnamese_audit/kaikki-current.jsonl", encoding="utf-8"):
        r = json.loads(line)
        if r.get("lang_code") == "vi":
            kk.setdefault(norm(r["word"]), []).append(r)
    fv = {norm(json.loads(line)["word"]) for line in open(f"{V}/work/v8_lexicon/fvdp_vi_en.jsonl", encoding="utf-8")}
    out = []
    for w in sorted(set(freq) | set(manual)):
        if w in existing or len(w) < 2 or not all(c.LATIN_WORD.fullmatch(p) for p in w.split()):
            continue
        entries = kk.get(w, [])
        poss = {e.get("pos") for e in entries}
        if w in manual:
            out.append((w, "manual"))
        elif w in fv and freq.get(w, 0) >= 3:
            out.append((w, "fvdp"))
        elif "name" in poss and freq.get(w, 0) >= 3:
            glosses = " ".join(g for e in entries for s in e.get("senses", []) for g in s.get("glosses", []))
            if PLACE.search(glosses) and not PERSON.search(glosses):
                out.append((w, "place"))
    return out


def build(notes: list[deck.VNote]):
    scan = pickle.load(open(ROOT / "data/work/vn_scan.pkl", "rb"))
    manual = manual_glosses()
    existing = {norm(n.word) for n in notes}
    words = c.load_kaikki(f"{V}/reports/2026-11-15_vietnamese_audit/kaikki-current.jsonl")
    c.add_supplement(words, f"{V}/work/v8_lexicon/fvdp_vi_en.jsonl", "FVDP", False)
    c.add_supplement(words, f"{V}/work/v8_lexicon/uvd_vi_vi.jsonl", "UVD", True)
    lower = {norm(k): k for k in words}
    out = []
    for w, reason in candidates(scan["freq"], existing, manual):
        key = lower.get(w)
        if key is None:
            continue
        item = words[key]
        if reason == "manual":
            gloss, pos = manual[w]
            item.en.insert(0, c.Sense(gloss, pos, (), "Curated"))
        gloss_text, primary = c.pick_primary(item, "", False)
        if reason == "manual":
            gloss_text = manual[w][0]
        if not gloss_text:
            continue
        ref = improve.REFERENCE.match(gloss_text)
        if ref:                                    # "alternative letter-case form of Trái Đất" -> "Earth"
            q = improve.QUOTED.search(ref.group(2))
            target = words.get(re.sub(r"\s*\(.*$", "", ref.group(2)).strip(" ."))
            alt = q.group(1) if q else (c.pick_primary(target, "", False)[0] if target else "")
            if not alt or improve.REFERENCE.match(alt):
                continue
            gloss_text = alt
        if reason == "place":                      # "West Germany (a former country in …)" -> "West Germany"
            gloss_text = re.sub(r"\s*\(.*$", "", gloss_text).strip() or gloss_text
        details, _en, _vi = c.dictionary_html(key, item, words, None, primary, [])
        raw = {k: "" for k in LIVE}
        raw.update({"Vietnamese": html.escape(key, quote=False), "English": html.escape(gloss_text, quote=False),
                    "Tier": "Reference", "Frequency": frequency_info(key),
                    "PartOfSpeech": html.escape(primary.pos, quote=False) if primary and primary.pos != "Dictionary entry" else "",
                    "DetailsHTML": details, "SourcesHTML": _sources(key, item, reason)})
        res = cr_vn.clean_note(raw)
        if res.unrecognised:
            continue
        raw.update(res.changes)
        fields = {LIVE[k]: v for k, v in raw.items()}
        out.append((stable_guid(key), key, reason, fields))
    return out


def _sources(word, item, reason) -> str:
    s = []
    if any(x.source == "Kaikki" for x in item.en) or item.related:
        s.append(c.link("Wiktionary / Kaikki", c.wiktionary(word)))
    if any(x.source == "FVDP" for x in item.en):
        s.append(c.link("FVDP", c.LINKS["FVDP"]))
    if item.vi:
        s.append(c.link("Underthesea", c.LINKS["UVD"]))
    if reason == "manual":
        s.append("English gloss written for this deck")
    return " · ".join(s)


def with_examples(new, ctx):
    """Run the normal improvement step (examples, hints) on the new notes."""
    done = []
    for i, (guid, word, reason, fields) in enumerate(new):
        n = deck.VNote(-1 - i, guid, fields, word)
        defs, rest, items = deck.parse_defs(fields["DictionaryEntry"])
        n.items, n.defs_html, n.dict_rest = items, defs, rest
        r = improve.improve_note(n, ctx)
        fields = dict(fields, **r.changes)
        done.append((guid, word, reason, fields))
    return done


if __name__ == "__main__":
    from collections import Counter
    notes = deck.load(paths.deck("vn.anki2"))
    new = build(notes)
    ctx = improve.build_context(notes)
    new = with_examples(new, ctx)
    print(Counter(r for _, _, r, _ in new), "with examples:", sum(1 for *_, f in new if f["Examples"]))
    pickle.dump(new, open(ROOT / "data/work/vn_new_notes.pkl", "wb"))
