"""Tiny English helpers: content-word stems used to check that a translation matches a meaning."""
from __future__ import annotations

import re

STOP = set("""a an the to of in on at by for with from and or but as is are was were be been being am do does did
have has had it its this that these those there here he she i we you they me him her us them my your his our their
so very can could will would shall should may might must one ones someone something somebody sth sb oneself
about into out up down off over under than then also just only too more most much many some any all each every
etc e g eg ie i.e usually especially generally used use who what which when where how why whom whose if
""".split())
WORD = re.compile(r"[a-z]+")
PAREN = re.compile(r"\([^)]*\)")


def stem(w: str) -> str:
    for suf, rep in (("ies", "y"), ("ied", "y"), ("ying", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", ""),
                     ("ly", "")):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)] + rep
    return w


def keywords(text: str, drop_parens: bool = True) -> set[str]:
    t = PAREN.sub(" ", text.lower()) if drop_parens else text.lower()
    return {stem(w) for w in WORD.findall(t) if w not in STOP and len(w) > 1}


def stems(sentence: str) -> set[str]:
    return {stem(w) for w in WORD.findall(sentence.lower()) if w not in STOP}


def heads(text: str) -> set[str]:
    """Head words of a meaning: "long-handled spear" -> {spear}; "to love tenderly" -> {love};
    "trade; commerce; business" -> {trade, commerce, business}. Matching on heads keeps
    "for a long time" from counting as evidence for "long-handled spear"."""
    out: set[str] = set()
    for chunk in re.split(r"[;,/]| or ", PAREN.sub(" ", text.lower())):
        words = [w for w in WORD.findall(chunk.replace("-", " "))]
        if not words:
            continue
        if words[0] == "to" and len(words) > 1:          # verb: "to love non-romantically"
            content = [w for w in words[1:] if w not in STOP]
            if content:
                out.add(stem(content[0]))
            continue
        content = [w for w in words if w not in STOP]
        if content:
            out.add(stem(content[-1]))                    # noun phrase / adjective: last word
    return out
