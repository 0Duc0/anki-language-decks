"""Content packs for Japanese and Chinese (example sentences only)."""
from __future__ import annotations

import pickle
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "pipeline"), str(ROOT / "pipeline/vietnamese")]
import pack  # noqa: E402

SOURCES = ["Tatoeba (CC BY 2.0 FR)", "TED2020 via OPUS (CC BY-NC-ND 4.0)", "OpenSubtitles 2018 via OPUS"]


def make(lang: str):
    if lang == "jp":
        sys.path.insert(0, str(ROOT / "pipeline/japanese"))
        import examples as ex
        title, prefixes, keys, deckname = "Japanese: example sentences", ["JMdict (JP", "JP Vocabulary"], ["Headword (JP)", "EntryID"], "japanese"
    else:
        sys.path.insert(0, str(ROOT / "pipeline/chinese"))
        import examples as ex
        title, prefixes, keys, deckname = "Chinese: example sentences", ["CC-CEDICT (ZH", "CC-CEDICT Optimized EN"], ["Simplified", "EntryID"], "chinese"
    notes = ex.load_notes()
    changes = pickle.load(open(ROOT / f"data/work/{lang}_changes.pkl", "rb"))
    updates, fields = [], Counter()
    for nid, guid, f, _s in notes:
        ch = changes.get(nid)
        if ch:
            fields.update(ch.keys())
            updates.append({"guid": guid, "key": [f[k] for k in keys], "old": {k: f[k] for k in ch}, "new": ch})
    out = pack.write(ROOT / f"dist/{deckname}-update-{date.today().isoformat()}.json.gz", language=lang,
                     title=f"{title} for {len(updates):,} words", notetype_prefixes=prefixes, key_fields=keys,
                     updates=updates, new_notes=[], new_note_deck="", stats={"fields": dict(fields)}, sources=SOURCES)
    print(out, out.stat().st_size // 1024, "KB", dict(fields))
    sys.modules.pop("examples", None)


if __name__ == "__main__":
    for lang in sys.argv[1:]:
        make(lang)
