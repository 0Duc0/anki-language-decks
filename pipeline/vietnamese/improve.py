"""Vietnamese deck update: meaning order + gloss, example sentences, front-side hints.

Reads the clean deck export, the corpus scan (scan.py) and the curated files in data/curated/,
and returns the new field values per note. Nothing is written to any collection here.

Rules
-----
* Meanings: the 700 most frequent multi-sense words follow the hand-made order in
  data/curated/vn_review_*.tsv. Other words: rare, archaic, slang or purely technical
  meanings move behind the others; a meaning moves to the front only with clear corpus evidence.
* Gloss (the prompt of the Meaning → Vietnamese card): hand-written for reviewed words; for
  automatically reordered words it follows the new first meaning when it still matched the old one.
* Examples: an existing sentence stays unless the word is not really in it (e.g. thương in
  "thương mại"); dictionary examples always stay. New sentences come from Tatoeba, TED2020 and
  OpenSubtitles (the last only when the English matches a listed meaning) until a word has
  three sentences; Underthesea usage phrases fill in for words without any sentence.
* Hints: rebuilt from the first sentence that contains the word as a word.
"""
from __future__ import annotations

import html
import json
import pickle
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))
import corpora  # noqa: E402
import paths  # noqa: E402

CR = paths.CARD_REDESIGN
sys.path[:0] = [str(HERE), str(HERE.parent), CR]
import deck  # noqa: E402
import english  # noqa: E402
from common import MARK, SimpleEx, meanings_section, render_examples  # noqa: E402
from html_tree import parse  # noqa: E402
from seg import SYL, Segmenter, norm  # noqa: E402

V = "/mnt/user-data/uploads/ANKI/Anki Deck Preperation/Vietnamese"
DEMOTE = {"Archaic", "Obsolete", "Dated", "Historical", "Rare", "Morpheme", "Slang", "Vulgar", "Euphemistic",
          "Proscribed", "Nonstandard", "Misspelling", "Romanization"}
TECH_ONLY_PENALTY = 1          # a meaning whose only labels are subject fields (Mathematics, Computing …)
SUBJECTS = {"Sciences", "Natural sciences", "Physical sciences", "Human sciences", "Mathematics", "Computing",
            "Engineering", "Medicine", "Biology", "Physics", "Chemistry", "Anatomy", "Arithmetic", "Geometry",
            "Linguistics", "Grammar", "Law", "Botany", "Zoology", "Military", "Government", "Business",
            "Finance", "Religion", "Christianity", "Buddhism", "Catholicism", "Protestantism", "Board games",
            "Card games", "Games", "Hobbies", "Lifestyle", "Media", "Publishing", "Communications", "Journalism"}
TARGET_SENTENCES = 3
MAX_SENTENCES = 5
KEY_CHARS = 70
SRC_LABEL = {"TED2020": "TED2020 via OPUS", "OpenSubtitles": "OpenSubtitles via OPUS"}


# --------------------------------------------------------------------------- inputs

def load_reviews() -> tuple[dict[int, tuple[list[int] | None, str | None]], dict[str, tuple]]:
    by_rank: dict[int, tuple] = {}
    for p in sorted((ROOT / "data/curated").glob("vn_review_[0-9]*.tsv")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            i, order, gloss = line.split("\t")
            by_rank[int(i)] = ([int(x) for x in order.split(",")] if order != "=" else None,
                               gloss if gloss != "=" else None)
    by_word = {}
    for line in (ROOT / "data/curated/vn_review_extra.tsv").read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        w, order, gloss = line.split("\t")
        by_word[w] = ([int(x) for x in order.split(",")], gloss)
    return by_rank, by_word


def dictionary_examples() -> dict[str, set[str]]:
    """Example texts the dictionaries themselves attach to a headword: never dropped."""
    out: dict[str, set[str]] = defaultdict(set)
    for line in open(f"{V}/reports/2026-11-15_vietnamese_audit/kaikki-current.jsonl", encoding="utf-8"):
        r = json.loads(line)
        if r.get("lang_code") != "vi":
            continue
        for s in r.get("senses", []):
            for e in s.get("examples", []):
                if e.get("text"):
                    out[norm(r["word"])].add(_key(e["text"]))
    for name in ("fvdp_vi_en.jsonl", "uvd_vi_vi.jsonl"):
        for line in open(f"{V}/work/v8_lexicon/{name}", encoding="utf-8"):
            r = json.loads(line)
            for s in r.get("senses", []):
                for e in s.get("examples", []):
                    for chunk in (e.get("text") or "").split("~"):
                        if chunk.strip():
                            out[norm(r["word"])].add(_key(chunk))
    try:
        cur = json.load(open(f"{V}/work/v8_examples/curated_examples.json", encoding="utf-8"))
        for item in (cur if isinstance(cur, list) else cur.get("examples", [])):
            if isinstance(item, dict) and item.get("example_vi"):
                out[norm(item.get("word", ""))].add(_key(item["example_vi"]))
    except Exception:
        pass
    return out


def uvd_phrases() -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for line in open(f"{V}/work/v8_lexicon/uvd_vi_vi.jsonl", encoding="utf-8"):
        r = json.loads(line)
        for s in r.get("senses", []):
            for e in s.get("examples", []):
                for chunk in (e.get("text") or "").split("~"):
                    chunk = " ".join(chunk.split()).strip(" ,;")
                    if chunk and '"' not in chunk and len(chunk) <= 60:
                        out[norm(r["word"])].append(chunk)
    return out


def _key(text: str) -> str:
    return re.sub(r"\W+", "", deck.plain(text).lower())


# --------------------------------------------------------------------------- meanings

def render_defs(items: list[deck.Item]) -> str:
    groups: list[tuple[str, list[str]]] = []
    index: dict[str, int] = {}
    for it in items:                       # one section per word class, in order of first appearance
        if it.pos not in index:
            index[it.pos] = len(groups)
            groups.append((it.pos, []))
        groups[index[it.pos]][1].append(it.html)
    labels = {g[0] for g in groups}
    return (f'<div class="{MARK} cr-defs" data-readings="{len(groups)}" data-pinyins="{len(labels)}">'
            + "".join(meanings_section(lbl, its, fold_rest=False) for lbl, its in groups) + "</div>")


def auto_order(items: list[deck.Item], ev: list[float]) -> list[int]:
    def demoted(it: deck.Item) -> int:
        if set(it.labels) & DEMOTE:
            return 2
        if it.labels and set(it.labels) <= SUBJECTS:
            return TECH_ONLY_PENALTY
        return 0
    order = sorted(range(len(items)), key=lambda j: (demoted(items[j]), j))
    # strong corpus evidence may move a plain meaning to the very front
    first = order[0]
    best = max(range(len(items)), key=lambda j: (ev[j], -j)) if ev else first
    if (ev and best != first and demoted(items[best]) == 0 and ev[best] >= 10
            and ev[best] >= 2.5 * max(ev[first], 1) and len(items[best].text) <= 45):
        order.remove(best)
        order.insert(0, best)
    return order


REFERENCE = re.compile(
    r"^(Traditional tone placement spelling|Alternative (?:form|spelling|letter-case form)|Obsolete (?:form|spelling)|"
    r"Nonstandard (?:form|spelling)|Eye dialect spelling|Misspelling|Abbreviation|Synonym|Initialism|Dialectal form|"
    r"Pronunciation spelling) of (.+?)\.?$", re.I)
QUOTED = re.compile(r"[“\"]([^”\"]+)[”\"]")


def reference_gloss(gloss: str, glosses: dict[str, str]) -> str | None:
    """"synonym of thiên văn học (“astronomy”)" -> "astronomy"; spelling variants take the main word's gloss.
    The prompt of the Meaning → Vietnamese card must be English, not a Vietnamese near-answer."""
    m = REFERENCE.match(gloss)
    if not m:
        return None
    kind, target = m.group(1).lower(), m.group(2)
    q = QUOTED.search(target)
    meaning = q.group(1).strip() if q else None
    if meaning is None:
        main = glosses.get(re.sub(r"\s*\(.*$", "", target).strip(" ."))
        if main is None or REFERENCE.match(main):
            return None
        meaning = main
    variant = "spelling" in kind or "form" in kind
    return f"{meaning} (spelling variant)" if variant else meaning


VN_LABEL = re.compile(r"^\((?:[a-zđàáảãạâầấẩẫậăằắẳẵặèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ ]+)\)\s*")


def decapitalised(gloss: str, f: dict) -> str | None:
    """"Remedy" -> "remedy" and "(sinh học) Epithelium" -> "epithelium" when the meanings come from
    FVDP only (it capitalises every entry and starts some with a Vietnamese subject label)."""
    if not gloss or "Wiktionary" in f.get("Sources", "") or "Proper" in f.get("PartOfSpeech", ""):
        return None
    stripped = VN_LABEL.sub("", gloss)
    if not stripped:
        return None
    first = stripped.split()[0]
    if stripped != gloss and not (first[:1].isupper() and first[1:].islower()):
        return stripped
    if first[:1].isupper() and first[1:].islower() and first.lower() not in ("i",):
        return first.lower() + stripped[len(first):]
    return stripped if stripped != gloss else None


def compact(text: str) -> str:
    t = re.split(r"\s*[;|]\s*", text, maxsplit=1)[0].strip()
    t = re.sub(r"\s*›.*$", "", t)
    return t.rstrip(".")


# --------------------------------------------------------------------------- examples

def parse_examples(h: str):
    m = re.match(r'(<details class="cr-v1 cr-ex" data-multi="[01]"( open="")?>.*</details>)'
                 r'(<p class="ex-src">Example sources: (.*)</p>)?$', h, re.S)
    if not m:
        return None
    root = parse(m.group(1)).find(tag="details")
    exs = []
    for div in root.children:
        if div.tag != "div":
            continue
        ex = SimpleEx(text="", phrase="ex-phrase" in div.classes)
        for c in div.children:
            if c.tag is None:
                continue
            if "ex-k" in c.classes:
                ex.key = c.text_content()
            elif "ex-row" in c.classes:
                for cc in c.children:
                    if cc.tag and "ex-main" in cc.classes:
                        ex.text, ex.lang = cc.inner_html(), cc.attrs.get("lang", "")
                    elif cc.tag and "ex-a" in cc.classes:
                        ex.audio = cc.inner_html().split(" ")
            elif "ex-sub" in c.classes:
                ex.translation = c.find(tag="span").inner_html()
            elif "ex-n" in c.classes:
                ex.notes.append(c.inner_html())
        exs.append(ex)
    return exs, (m.group(4) or "")


def near_duplicate(text: str, others: list[str]) -> bool:
    """"Tôi chưa bao giờ thực sự …" vs "Tôi chưa bao giờ thật sự …": one is enough."""
    a = set(SYL.findall(norm(text)))
    for o in others:
        b = set(SYL.findall(norm(o)))
        if a and b and len(a & b) / len(a | b) >= 0.75:
            return True
    return False


def misaligned(target: str, en: str) -> bool:
    """Subtitle pairs that join two lines on one side ("Ready. - We'll go") are often misaligned."""
    if (" - " in en) != (" - " in target):
        return True
    ends = lambda t: len(re.findall(r"[.!?。！？]+", t.strip(" .!?。！？")))  # noqa: E731
    return abs(ends(target) - ends(en)) > 0


def highlight(text: str, a: int, b: int) -> str:
    return html.escape(text[:a], quote=False) + f'<b class="hl">{html.escape(text[a:b], quote=False)}</b>' \
        + html.escape(text[b:], quote=False)


def token_span(seg: Segmenter, text: str, word: str) -> tuple[int, int] | None:
    w = norm(word)
    for tok, a, b in seg.tokens(text):
        if tok == w:
            return a, b
    return None


@dataclass
class Result:
    changes: dict[str, str] = field(default_factory=dict)
    dropped: list[str] = field(default_factory=list)
    added: int = 0
    reordered: str = ""            # "manual" | "auto" | ""


def improve_note(n: deck.VNote, ctx) -> Result:
    res = Result()
    w = norm(n.word)
    f = n.fields
    # ---- meanings
    order = None
    gloss = None
    if n.items:
        manual = ctx.manual.get(n.nid) or ctx.by_word.get(n.word)
        if manual:
            order, gloss = manual
            res.reordered = "manual" if order else ""
        if not manual:
            ev = [] if w in ctx.ambiguous else (ctx.evidence.get(w) or [])
            if len(ev) != len(n.items):
                ev = [0.0] * len(n.items)
            order = auto_order(n.items, ev)
            res.reordered = "auto" if order != list(range(len(n.items))) else ""
        if order:
            order = [j for j in order if 0 <= j < len(n.items)]
            order += [j for j in range(len(n.items)) if j not in order]
            new_items = [n.items[j] for j in order]
            defs = render_defs(new_items)
            if defs != n.defs_html:
                res.changes["DictionaryEntry"] = defs + n.dict_rest
            first_old, first_new = n.items[0], new_items[0]
            if gloss is None and first_new is not first_old:
                old_gloss = deck.plain(f["Gloss"])
                if old_gloss and old_gloss.lower() in first_old.text.lower():
                    gloss = compact(first_new.text)
            if first_new.pos != first_old.pos and deck.plain(f["PartOfSpeech"]).lower() == first_old.pos.lower():
                res.changes["PartOfSpeech"] = html.escape(first_new.pos, quote=False)
    if gloss is None:
        gloss = reference_gloss(deck.plain(f["Gloss"]), ctx.glosses)
    if gloss is None:
        gloss = decapitalised(deck.plain(f["Gloss"]), f)
    if gloss and html.escape(gloss, quote=False) != f["Gloss"]:
        res.changes["Gloss"] = html.escape(gloss, quote=False)
    gloss_now = deck.plain(res.changes.get("Gloss", f["Gloss"]))
    sense_texts = [it.text for it in n.items]

    # ---- examples
    parsed = parse_examples(f["Examples"]) if f["Examples"] else ([], "")
    if parsed is None:
        return res
    exs, src_line = parsed
    protected = ctx.dict_examples.get(w, set())
    kept: list[SimpleEx] = []
    for ex in exs:
        raw = html.unescape(re.sub(r"<[^>]+>", "", ex.text))
        if not ex.phrase and _key(raw) not in protected:
            span = token_span(ctx.seg, raw, n.word)
            if span is None and re.search(r"(?<![\w])" + re.escape(n.word) + r"(?![\w])", raw, re.I):
                res.dropped.append(raw)                 # the word only occurs inside a longer word
                continue
            hl = re.search(r'<b class="hl">', ex.text)
            if span is not None and hl is not None:
                start = len(html.unescape(re.sub(r"<[^>]+>", "", ex.text[:hl.start()])))
                if start != span[0]:                   # highlight sat inside another word: move it
                    ex.text = highlight(raw, *span)
        kept.append(ex)
    sentences = [e for e in kept if not e.phrase]
    have = {_key(deck.plain(e.text)) for e in kept}
    new_sources: list[str] = []
    cands = sorted(ctx.heaps.get(w, []), reverse=True)
    covered = {e.key for e in sentences if e.key}
    added: list[SimpleEx] = []
    final_texts = [html.unescape(re.sub(r"<[^>]+>", "", e.text)) for e in kept]
    meaning_heads = english.heads(gloss_now) | {h for t in sense_texts for h in english.heads(t)}
    for score, src, ref, vi, en, a, b, hits in cands:
        if len(sentences) + len(added) >= MAX_SENTENCES:
            break
        if _key(vi) in have or misaligned(vi, en) or near_duplicate(vi, final_texts):
            continue
        if src == "OpenSubtitles" and not (meaning_heads & english.stems(en)):
            continue                           # subtitles only when the English shows the meaning
        key = ""
        if w in ctx.ambiguous:                 # two notes share this spelling: the scan's sense numbers
            hits = ()                          # may belong to the other one
        if hits and len(n.items) > 1:
            first_hit = min(hits, key=lambda j: order.index(j) if order else j)
            key = compact(sense_texts[first_hit])[:KEY_CHARS]
        enough = len(sentences) + len(added) >= TARGET_SENTENCES
        if enough and (not key or key in covered):
            continue                           # past three sentences only for a meaning not yet shown
        ex = SimpleEx(text=highlight(vi, a, b), translation=html.escape(en, quote=False), key=key, lang="vi")
        added.append(ex)
        final_texts.append(vi)
        have.add(_key(vi))
        covered.add(key)
        new_sources.append(f"Tatoeba · sentence {ref}" if src == "Tatoeba" else SRC_LABEL[src])
    if not sentences and not added and not kept:
        for chunk in ctx.uvd.get(w, []):
            span = token_span(ctx.seg, chunk, n.word)
            if span and len(chunk.split()) > len(w.split()) and _key(chunk) not in have:
                added.append(SimpleEx(text=highlight(chunk, *span), phrase=True, lang="vi"))
                have.add(_key(chunk))
                new_sources.append("Underthesea")
                if len(added) >= 2:
                    break
    res.added = len(added)
    final = [e for e in kept if not e.phrase] + added + [e for e in kept if e.phrase]
    final.sort(key=lambda e: e.phrase)
    if res.added or res.dropped:
        body = render_examples(final, [])
        uniq = []
        if src_line and res.dropped:
            src_line = prune_source_line(src_line, res.dropped, ctx.tatoeba)
        for s in ([src_line] if src_line else []) + new_sources:
            if s and s not in uniq:
                uniq.append(s)
        if body and uniq:
            body += '<p class="ex-src">Example sources: ' + " · ".join(uniq) + "</p>"
        if body != f["Examples"]:
            res.changes["Examples"] = body

    # ---- hints on the card fronts
    first_sentence = next((e for e in final if not e.phrase and e.translation), None)
    if res.dropped or (not f["ContextHint"] and first_sentence is not None):
        ctx_hint, prod_hint = "", ""
        if first_sentence is not None:
            text = deck.plain(first_sentence.text)
            span = token_span(ctx.seg, text, n.word)
            if span and len(text) <= 150:
                ctx_hint = f'<p class="clue" lang="vi">{html.escape(text, quote=False)}</p>'
                en = deck.plain(first_sentence.translation)
                leaks = re.search(r"(?<![\w])" + re.escape(n.word) + r"(?![\w])", gloss_now + " " + en, re.I)
                cue = english.keywords(gloss_now) & english.stems(en)
                if not leaks and cue and len(text.split()) > len(w.split()):
                    a, b = span
                    prod_hint = ('<p class="clue" lang="vi">' + html.escape(text[:a], quote=False)
                                 + '<span class="gap">_____</span>' + html.escape(text[b:], quote=False) + "</p>")
        if ctx_hint != f["ContextHint"]:
            res.changes["ContextHint"] = ctx_hint
        if prod_hint != f["ProductionHint"] and (prod_hint or res.dropped):
            res.changes["ProductionHint"] = prod_hint
    return res


@dataclass
class Context:
    seg: Segmenter
    heaps: dict
    evidence: dict
    manual: dict
    by_word: dict
    dict_examples: dict
    uvd: dict
    ambiguous: set
    glosses: dict
    tatoeba: dict = field(default_factory=dict)      # Tatoeba sentence id -> Vietnamese text


def build_context(notes) -> Context:
    scan = pickle.load(open(ROOT / "data/work/vn_scan.pkl", "rb"))
    by_rank, by_word = load_reviews()
    freq = scan["freq"]
    ranked = sorted([n for n in notes if len(n.items) >= 2], key=lambda n: -freq[norm(n.word)])[:700]
    manual = {ranked[i].nid: v for i, v in by_rank.items()}
    seen, ambiguous = set(), set()
    for n in notes:
        k = norm(n.word)
        (ambiguous if k in seen else seen).add(k)
    return Context(Segmenter(scan["lexicon"]), scan["heaps"], scan["evidence"], manual, by_word,
                   dictionary_examples(), uvd_phrases(), ambiguous,
                   {n.word: deck.plain(n.fields["Gloss"]) for n in notes}, tatoeba_sentences())


def tatoeba_sentences() -> dict:
    return {ref: vi for src, ref, vi, _en in corpora.read("vi") if src == "Tatoeba"}


_TATOEBA_SOURCE = re.compile(r'(?:<a [^>]*>)?Tatoeba · sentence (\d+)(?:</a>)?')


def prune_source_line(src_line: str, dropped: list[str], tatoeba: dict) -> str:
    """Remove "Tatoeba · sentence N" from the source line when that sentence was dropped."""
    gone = {_key(d) for d in dropped}
    def keep(m):
        return "" if _key(tatoeba.get(m.group(1), "")) in gone else m.group(0)
    pruned = _TATOEBA_SOURCE.sub(keep, src_line)
    return re.sub(r"(?:\s*·\s*){2,}", " · ", pruned).strip(" ·")


def run(path: str = paths.deck("vn.anki2")):
    notes = deck.load(path)
    ctx = build_context(notes)
    results = {n.nid: improve_note(n, ctx) for n in notes}
    return notes, results


if __name__ == "__main__":
    from collections import Counter
    notes, results = run()
    c = Counter()
    for r in results.values():
        for k in r.changes:
            c[k] += 1
        c["reordered_" + (r.reordered or "none")] += 1
        c["examples_added"] += r.added
        c["notes_with_new_examples"] += bool(r.added)
        c["examples_dropped"] += len(r.dropped)
    print(dict(c))
    pickle.dump({n.nid: results[n.nid].changes for n in notes}, open(ROOT / "data/work/vn_changes.pkl", "wb"))
