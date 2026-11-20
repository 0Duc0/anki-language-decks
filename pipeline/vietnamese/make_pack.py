"""Vietnamese content pack: improve.py changes + new_notes.py notes -> dist/vietnamese-update-<date>.json.gz"""
from __future__ import annotations

import pickle
import sys
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(HERE.parent)]
import paths  # noqa: E402
import deck  # noqa: E402
import pack  # noqa: E402

notes = deck.load(paths.deck("vn.anki2"))
changes = pickle.load(open(ROOT / "data/work/vn_changes.pkl", "rb"))
new = pickle.load(open(ROOT / "data/work/vn_new_notes.pkl", "rb"))
updates, fields_changed = [], Counter()
for n in notes:
    ch = changes.get(n.nid) or {}
    if ch:
        fields_changed.update(ch.keys())
        updates.append({"guid": n.guid, "key": [n.fields["Headword (VN)"], n.fields["EntryID"]],
                        "old": {f: n.fields[f] for f in ch}, "new": ch})
new_notes = [{"guid": g, "fields": f, "tags": ["deck-update::2026-11-20", f"source::{reason}"]}
             for g, w, reason, f in new]
out = pack.write(
    ROOT / f"dist/vietnamese-update-{date.today().isoformat()}.json.gz",
    language="vn", title=f"Vietnamese: meanings, example sentences and {len(new_notes):,} new words",
    notetype_prefixes=["Kaikki/Underthesea/FVDP (VN", "Vietnamese Optimized EN"],
    key_fields=["Headword (VN)", "EntryID"], updates=updates, new_notes=new_notes,
    new_note_deck="Language::Vietnamese::Vietnamese Optimized Dictionary::99 Dictionary Reference",
    stats={"fields": dict(fields_changed), "new_by_source": dict(Counter(r for _, _, r, _ in new))},
    sources=["Wiktionary via Kaikki (CC BY-SA)", "FVDP (GPL-2.0-or-later)", "Underthesea UVD (GPL-3.0)",
             "Tatoeba (CC BY 2.0 FR)", "TED2020 via OPUS (CC BY-NC-ND 4.0)", "OpenSubtitles 2018 via OPUS"])
print(out, out.stat().st_size // 1024, "KB", dict(fields_changed), len(new_notes))
