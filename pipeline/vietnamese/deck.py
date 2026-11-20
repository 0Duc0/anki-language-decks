"""Read the Vietnamese notes and their meanings (the cr-v1 "DictionaryEntry" layout)."""
from __future__ import annotations

import html
import re
import sys
import unicodedata
from dataclasses import dataclass, field

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import paths  # noqa: E402

CR = paths.CARD_REDESIGN
if CR not in sys.path:
    sys.path.insert(0, CR)
from html_tree import parse  # noqa: E402

TAG = re.compile(r"<[^>]+>")
MODEL_PREFIX = "Kaikki/Underthesea/FVDP (VN"


def plain(h: str) -> str:
    return unicodedata.normalize("NFC", " ".join(html.unescape(TAG.sub(" ", h or "")).split()))


@dataclass
class Item:
    pos: str            # word class label shown on the card ("Noun", "Verb", "")
    html: str           # inner html of the meaning (usage labels included)
    text: str           # plain text without usage labels
    labels: list[str]   # usage labels ("Archaic", "Southern Vietnam" …)
    order: int          # position on the card today


@dataclass
class VNote:
    nid: int
    guid: str
    fields: dict[str, str]
    word: str
    items: list[Item] = field(default_factory=list)
    defs_html: str = ""     # the cr-defs block
    dict_rest: str = ""     # everything after it (the "Full dictionary entry" fold)


def parse_defs(entry: str) -> tuple[str, str, list[Item]]:
    """Split DictionaryEntry into (cr-defs html, rest, items)."""
    m = re.match(r'(<div class="cr-v1 cr-defs".*?</div>)(?=<details class="cr-dict"|$)', entry, re.S)
    if not m:
        return "", entry, []
    defs, rest = m.group(1), entry[m.end():]
    items: list[Item] = []
    root = parse(defs)
    for sec in root.find_all(tag="section"):
        label_node = sec.find("r-py")
        pos = label_node.text_content().strip() if label_node is not None else ""
        lis = [li for ol in sec.find_all(tag="ol") if "m-main" in ol.classes for li in ol.find_all(tag="li")]
        gs = [g for g in sec.find_all(tag="span") if "g" in g.classes]
        for node in lis + gs:
            inner = node.inner_html()
            labels = [u.text_content().strip() for u in node.find_all(tag="span") if "usage" in u.classes]
            text = plain(re.sub(r'<span class="usage">.*?</span>', " ", inner))
            items.append(Item(pos, inner, text, labels, len(items)))
    return defs, rest, items


def load(path: str) -> list[VNote]:
    from anki.collection import Collection

    col = Collection(path)
    try:
        model = next(m for m in col.models.all() if m["name"].startswith(MODEL_PREFIX))
        names = [f["name"] for f in model["flds"]]
        out = []
        for nid, guid, flds in col.db.all("select id, guid, flds from notes where mid = ?", model["id"]):
            f = dict(zip(names, flds.split("\x1f")))
            defs, rest, items = parse_defs(f["DictionaryEntry"])
            out.append(VNote(nid, guid, f, plain(f["Headword (VN)"]), items, defs, rest))
        return out
    finally:
        col.close()
