"""Write a content pack: the deck changes as one JSON file (gzip), applied by Card Redesign's
"Deck update" button.

Every changed field carries the SHA-1 of its value in the snapshot the change was computed
from. The add-on only writes a field whose current value still has that hash, so anything
the user edited in the meantime is left alone (and reported). New notes carry a fixed GUID,
so applying a pack twice never adds a note twice.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from datetime import date
from pathlib import Path

FORMAT = "anki-language-decks.content-pack"
VERSION = 1
PROTECTED = ("PersonalNotes", "Mnemonic", "Notizen", "UserMnemonic", "Eigene_Merkhilfe")


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def write(path: Path, *, language: str, title: str, notetype_prefixes: list[str], key_fields: list[str],
          updates: list[dict], new_notes: list[dict], new_note_deck: str, stats: dict, sources: list[str]) -> Path:
    """updates: [{"guid", "key": [...], "old": {field: old}, "new": {field: new}}]
    new_notes: [{"guid", "fields": {...}, "tags": [...]}]"""
    out_updates = []
    for u in updates:
        fields = {f: [sha1(u["old"][f]), v] for f, v in u["new"].items() if f not in PROTECTED and v != u["old"][f]}
        if fields:
            out_updates.append({"guid": u["guid"], "key": u["key"], "fields": fields})
    for n in new_notes:
        for f in PROTECTED:
            n["fields"].pop(f, None)
    pack = {
        "format": FORMAT, "version": VERSION, "language": language, "title": title,
        "created": date.today().isoformat(), "notetype_prefixes": notetype_prefixes, "key_fields": key_fields,
        "protected_fields": list(PROTECTED), "new_note_deck": new_note_deck, "sources": sources,
        "stats": dict(stats, updated_notes=len(out_updates), new_notes=len(new_notes)),
        "updates": out_updates, "new_notes": new_notes,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(pack, f, ensure_ascii=False, separators=(",", ":"))
    return path
