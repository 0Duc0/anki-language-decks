# Update file format

An update file is gzip-compressed JSON (`*.json.gz`). The Card Redesign add-on reads it
(*Tools › Card redesign… › Deck update*); `pipeline/pack.py` writes it.

```jsonc
{
  "format": "anki-language-decks.content-pack",
  "version": 1,
  "language": "vi",                        // vi | ja | zh
  "title": "Vietnamese: meanings, example sentences and 2,882 new words",
  "created": "2026-11-20",
  "notetype_prefixes": ["Kaikki/Underthesea/FVDP"],   // which note type the update is for
  "key_fields": ["Vietnamese"],             // fallback match when a GUID is not found
  "protected_fields": ["PersonalNotes", "Notizen", "Mnemonic", "UserMnemonic", "Eigene_Merkhilfe"],
  "updates": [
    {"guid": "…", "key": ["thương"],
     "fields": {"Gloss": ["<sha1 of the old value>", "<new value>"], "Examples": ["…", "…"]}}
  ],
  "new_notes": [
    {"guid": "…", "fields": {"Vietnamese": "xảy ra", "Gloss": "to happen; to occur", "…": "…"}, "tags": ["…"]}
  ],
  "new_note_deck": "Language::Vietnamese::Vietnamese Optimized Dictionary::99 Dictionary Reference",
  "stats": {"updated_notes": 22221, "new_notes": 2882, "fields": {"Examples": 19051, "…": 0}},
  "sources": ["Tatoeba (CC BY 2.0 FR)", "…"]
}
```

Rules the add-on enforces:

- A field is written only when the SHA-1 of its current value equals the first element (the value the update
  was made from). Otherwise the user's version is kept and counted as *left as you edited them*.
- Protected fields are never written, even if an update lists them.
- Only fields are written: no scheduling, tags, decks or card types change.
- New notes keep the GUID from the file. A note with that GUID already present is skipped, so an update can be
  applied any number of times.
- Every write is recorded first in `user_files/update-undo-<language>-<time>.json` (old value, new value, added
  note ids). Undo restores a field only while it still holds the update's value and removes added notes only
  while they have no reviews.
