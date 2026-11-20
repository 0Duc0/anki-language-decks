"""Meaning grouping, provenance and contextual prompts for Vietnamese v8."""

import html
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote


POS = {
    "adj": "Adjective", "adv": "Adverb", "aux": "Auxiliary", "classifier": "Classifier",
    "conj": "Conjunction", "det": "Determiner", "intj": "Interjection",
    "name": "Proper name", "noun": "Noun", "num": "Numeral", "prep": "Preposition",
    "pron": "Pronoun", "verb": "Verb", "phrase": "Phrase", "proverb": "Proverb",
    "particle": "Particle", "prefix": "Prefix", "suffix": "Suffix", "affix": "Affix",
    "combining_form": "Combining form", "romanization": "Hán–Việt reading",
    "syllable": "Syllable", "character": "Character",
}
DISPLAY_ORDER = ("Noun", "Verb", "Adjective", "Adverb", "Pronoun", "Preposition")
NEW_POS = {
    "Adjective", "Adverb", "Auxiliary", "Classifier", "Conjunction", "Determiner",
    "Interjection", "Noun", "Numeral", "Preposition", "Pronoun", "Verb", "Phrase",
    "Proverb", "Particle", "Dictionary entry",
}
RARE = {
    "archaic", "dated", "historical", "obsolete", "rare", "uncommon", "misspelling",
    "romanization", "spelling variant", "alternative spelling", "proscribed",
}
VARIANT = {"alternative", "alt-of", "form-of", "pronunciation-spelling", "misspelling"}
TAG_NAMES = {
    "Southern": "Southern Vietnam", "South": "Southern Vietnam",
    "Northern": "Northern Vietnam", "North": "Northern Vietnam",
    "Central": "Central Vietnam", "Hà-Nội": "Hà Nội", "Hà-Tĩnh": "Hà Tĩnh",
    "Nghệ-An": "Nghệ An", "Hồ-Chí-Minh-City": "Hồ Chí Minh City",
    "Saigon": "Sài Gòn", "alt-of": "Variant", "form-of": "Word form",
    "in-compounds": "In compounds", "idiomatic": "Idiom",
    "figuratively": "Figurative", "literally": "Literal",
}
STOP = set((
    "a an the to in of at and on is it for with by as or be was are have he she i we you"
    " they when that this so his her do does can will their was were its our your its had"
    " someone something usually used one not all out up off about being some there than"
).split())
TAG = re.compile(r"<[^>]*>")
LATIN_WORD = re.compile(r"[\wÀ-ỹ]+(?:[-’'][\wÀ-ỹ]+)*(?: [\wÀ-ỹ]+(?:[-’'][\wÀ-ỹ]+)*)*\Z")
SENSE_SPLIT = re.compile(r"\s*[;|]\s*")
LEGACY_POS = re.compile(r"^\s*(?:noun|verb|adjective|adverb|pronoun|particle|interjection)\s*:\s*", re.I)
LINKS = {
    "Kaikki": "https://kaikki.org/dictionary/Vietnamese/index.html",
    "FVDP": "https://www2.crosswire.org/sword/modules/ModInfo.jsp?modName=FVDPVietAnh",
    "UVD": "https://github.com/undertheseanlp/resources/tree/master/resources/DI_Vietnamese-UVD",
    "Curated": "",
}


def plain(text):
    if not text:
        return ""
    return unicodedata.normalize("NFC", " ".join(html.unescape(TAG.sub(" ", str(text))).split()))


def h(text):
    return html.escape(str(text), quote=True)


def key(text):
    return plain(text).casefold()


def wiktionary(word):
    return "https://en.wiktionary.org/wiki/" + quote(word.replace(" ", "_"), safe="") + "#Vietnamese"


def link(label, url):
    if url.startswith("https://"):
        return f'<a href="{h(url)}">{h(label)}</a>'
    return h(label)


def tokens(text):
    return {word for word in re.findall(r"[a-z]{2,}", key(text)) if word not in STOP}


def word_pattern(word):
    return re.compile(r"(?<![\w-])" + re.escape(word) + r"(?![\w-])", re.IGNORECASE)


def eligible_headword(word):
    if not LATIN_WORD.fullmatch(word) or not 0 < len(word.split()) <= 12:
        return False
    return all(
        unicodedata.name(c, "").startswith("LATIN") or c in " -’'"
        for c in word
    )


def gloss_key(text):
    return re.sub(r"\W+", " ", key(text).removeprefix("to ")).strip()


def compact(gloss):
    text = LEGACY_POS.sub("", SENSE_SPLIT.split(plain(gloss), 1)[0]).strip()
    return text.rstrip(".")


def pos_name(value):
    value = plain(value)
    return POS.get(value.casefold(), value.capitalize() or "Dictionary entry")


@dataclass(frozen=True)
class Example:
    vi: str
    en: str
    source: str
    url: str = ""
    aligned: bool = False


@dataclass
class Sense:
    gloss: str
    pos: str
    labels: tuple
    source: str
    examples: tuple = ()
    rare: bool = False
    variant: bool = False


@dataclass
class Word:
    en: list = field(default_factory=list)
    vi: list = field(default_factory=list)
    ipa: dict = field(default_factory=dict)
    related: dict = field(default_factory=dict)
    audio_pages: dict = field(default_factory=dict)
    legacy: str = ""


def usable_gloss(value):
    value = plain(value)
    return bool(value and value not in {"—", "-", "?", "[]"} and "□□□" not in value)


def labels_for(raw, *groups):
    labels = []
    for tag in [*raw, *(tag for group in groups for tag in group)]:
        if tag in {"Vietnam", "no-gloss"}:
            continue
        value = TAG_NAMES.get(tag, tag.replace("-", " ").capitalize())
        if value not in labels:
            labels.append(value)
    return tuple(labels)


def load_kaikki(path):
    words = defaultdict(Word)
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            word = plain(row.get("word"))
            if row.get("lang_code") != "vi" or not word:
                continue
            item = words[word]
            part = pos_name(row.get("pos"))
            for raw in row.get("senses", []):
                glossary = [plain(value) for value in raw.get("glosses", []) if usable_gloss(value)]
                if not glossary:
                    continue
                tags = set(raw.get("tags", []))
                examples = []
                for sample in raw.get("examples", []):
                    if sample.get("type") == "quotation":
                        continue
                    vi = plain(sample.get("text"))
                    en = plain(sample.get("english") or sample.get("translation"))
                    if vi and len(vi) <= 280:
                        examples.append(Example(vi, en, "Wiktionary", wiktionary(word), True))
                item.en.append(Sense(" › ".join(glossary), part,
                                     labels_for(raw.get("raw_tags", []), raw.get("tags", []), raw.get("topics", [])),
                                     "Kaikki", tuple(examples), bool(tags & RARE)
                                     or part == "Hán–Việt reading", bool(tags & VARIANT)))
            for sound in row.get("sounds", []):
                if sound.get("ipa"):
                    dialect = " · ".join(labels_for([], sound.get("tags", []))) or "IPA"
                    item.ipa[(dialect, sound["ipa"])] = None
                if sound.get("audio"):
                    filename = sound["audio"].replace(" ", "_")
                    page = "https://commons.wikimedia.org/wiki/File:" + quote(filename, safe="()")
                    dialect = " · ".join(labels_for([], sound.get("tags", []))) or "Wiktionary"
                    item.audio_pages[page] = dialect
            for collection in [row, *row.get("senses", [])]:
                for rel, label in (("proverbs", "Proverb"), ("idioms", "Idiom"),
                                   ("derived", "Compound or derivative"), ("related", "Related expression")):
                    for entry in collection.get(rel, []):
                        expression = plain(entry.get("word"))
                        if expression and expression != word:
                            item.related.setdefault(expression, label)
    return words


def add_supplement(words, path, source, vietnamese):
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            word = plain(row["word"])
            if not word:
                continue
            destination = words[word].vi if vietnamese else words[word].en
            for item in row["senses"]:
                if not usable_gloss(item.get("gloss")):
                    continue
                tags = [str(tag) for tag in item.get("tags", [])]
                examples = [
                    Example(vi, plain(example.get("translation")), source, LINKS[source], True)
                    for example in item.get("examples", [])
                    if (vi := plain(example.get("text"))) and len(vi) <= 280
                ]
                destination.append(Sense(plain(item["gloss"]), pos_name(item.get("pos")),
                                         labels_for([], tags), source, tuple(examples),
                                         bool(set(tags) & RARE), bool(set(tags) & VARIANT)))


def distinct_senses(senses):
    seen = set()
    for sense in senses:
        signature = (gloss_key(sense.gloss), sense.pos, sense.labels)
        if signature not in seen:
            seen.add(signature)
            yield sense


def pick_primary(item, previous, learned):
    old_gloss = compact(previous)
    old_key = gloss_key(old_gloss)
    senses = [sense for sense in item.en if not sense.rare and not sense.variant]
    if not senses:
        senses = item.en
    if learned and old_gloss and len(old_gloss) <= 105 and "□□□" not in old_gloss:
        old_words = tokens(old_gloss)
        match = max(senses, default=None, key=lambda sense: (
            gloss_key(compact(sense.gloss)) == old_key,
            len(old_words & tokens(sense.gloss)),
            sense.source == "Kaikki",
        ))
        if match and (old_words & tokens(match.gloss) or old_key == gloss_key(compact(match.gloss))):
            return old_gloss, match
        if previous and not LEGACY_POS.match(plain(previous)):
            return old_gloss, None
    if senses:
        best = next((sense for sense in senses if gloss_key(compact(sense.gloss)) == old_key), senses[0])
        return compact(best.gloss), best
    return old_gloss, None


def example_for(word, gloss, primary, previous, generated):
    pattern = word_pattern(word)
    if generated and generated.source == "Curated for this deck" and generated.en and pattern.search(generated.vi):
        return generated, True
    samples = (*primary.examples,) if primary else ()
    options = [
        (example, True) for example in samples
        if example.en and len(example.vi) < 180 and len(example.en) < 240 and pattern.search(example.vi)
    ]
    cue_words = tokens(gloss)
    for example in (generated, previous):
        if not example or not example.vi or not example.en:
            continue
        if not pattern.search(example.vi) or "Cong sông" in example.vi:
            continue
        # A loose sentence alignment is enough for the back. A production
        # prompt additionally needs matching English meaning evidence.
        options.append((example, bool(cue_words & tokens(example.en)) or example.aligned))
    if not options:
        if generated and generated.vi:
            return generated, False
        return (previous, False) if previous and previous.vi else (None, False)
    return max(options, key=lambda pair: (
        pair[1], len(pair[0].vi.split()) >= 3, len(cue_words & tokens(pair[0].en)),
        pair[0].source != "Tatoeba", -abs(len(pair[0].vi.split()) - 6),
    ))


def production_hint(word, example, aligned):
    if not example or not aligned or not example.en or len(example.vi) > 150:
        return ""
    pattern = word_pattern(word)
    if not pattern.search(example.vi):
        return ""
    if pattern.search(example.en) or len(example.vi.split()) <= len(word.split()):
        return ""
    parts = pattern.split(example.vi)
    if len(parts) != 2 or not "".join(parts).strip(" .,;:!?—–-'’"):
        return ""
    return '<p class="clue" lang="vi">' + '<span class="gap">_____</span>'.join(map(h, parts)) + "</p>"


def sense_html(sense, word, preferred_example):
    tags = "".join(f'<span class="usage">{h(label)}</span>' for label in sense.labels)
    author = {"Kaikki": "Wiktionary", "FVDP": "FVDP", "UVD": "Underthesea",
              "Curated": "Curated for this deck"}[sense.source]
    origin = wiktionary(word) if sense.source == "Kaikki" else LINKS[sense.source]
    out = f'<li><div class="definition">{tags}{h(sense.gloss)}</div><span class="origin">{link(author, origin)}</span>'
    seen = set()
    if preferred_example:
        seen.add(key(preferred_example.vi))
    for example in sense.examples:
        if key(example.vi) in seen:
            continue
        seen.add(key(example.vi))
        if len(seen) > 4:
            break
        translation = f'<div class="translation">{h(example.en)}</div>' if example.en else ""
        out += f'<div class="sense-example"><span lang="vi">{h(example.vi)}</span>{translation}</div>'
    return out + "</li>"


def sense_groups(senses, word, example, primary):
    groups = defaultdict(list)
    for sense in distinct_senses(senses):
        groups[sense.pos].append(sense)
    pos_order = sorted(groups, key=lambda pos: (
        0 if primary and pos == primary.pos else 1,
        DISPLAY_ORDER.index(pos) if pos in DISPLAY_ORDER else len(DISPLAY_ORDER), pos,
    ))
    html_groups = []
    for part in pos_order:
        sorted_group = sorted(groups[part], key=lambda sense: (
            sense is not primary, sense.rare, sense.variant, sense.source != "Kaikki",
        ))
        values = "".join(sense_html(sense, word, example) for sense in sorted_group)
        html_groups.append(f'<h3 class="word-class">{h(part)}</h3><ol class="senses">{values}</ol>')
    return "".join(html_groups)


def section(title, body):
    return f'<details class="disclosure"><summary>{h(title)}</summary>{body}</details>' if body else ""


def dictionary_html(word, item, words, example, primary, related_override):
    current = [s for s in item.en if not s.rare and not s.variant]
    uncommon = [s for s in item.en if s.rare or s.variant]
    main = sense_groups(current, word, example, primary)
    other = sense_groups(uncommon, word, example, None)
    vi = sense_groups(item.vi, word, example, None)
    parts = [
        section("English meanings", main),
        section("Variants, historical & specialized readings", other),
        section("Vietnamese definitions & usage", vi),
    ]
    if item.ipa:
        ipa = "".join(f'<li><b>{h(region)}</b> {h(value)}</li>' for region, value in item.ipa)
        parts.append(section("Regional IPA", f'<ul class="side-list">{ipa}</ul>'))
    relations = dict(item.related)
    for expression, label in related_override:
        relations.setdefault(expression, label)
    grouped = defaultdict(list)
    for expression, label in relations.items():
        if expression == word:
            continue
        other_word = words.get(expression)
        english = ""
        if other_word:
            english = next((compact(s.gloss) for s in other_word.en if not s.rare and not s.variant), "")
            if any(s.pos == "Proverb" for s in other_word.en):
                label = "Proverb"
            elif any("Figurative" in s.labels or "Idiom" in s.labels for s in other_word.en):
                label = "Idiom or figurative expression"
        label = {"derived": "Compound or derivative", "related": "Related expression"}.get(label, label)
        grouped[label].append((expression, english))
    relation_rows = []
    for label, items in sorted(grouped.items(), key=lambda kv: ("Proverb" not in kv[0], kv[0])):
        values = "".join(
            f'<li><span lang="vi">{link(expression, wiktionary(expression))}</span>'
            + (f'<span class="translation"> — {h(english)}</span>' if english else "") + "</li>"
            for expression, english in items
        )
        relation_rows.append(f'<h3 class="word-class">{h(label)}</h3><ul class="side-list">{values}</ul>')
    parts.append(section("Compounds, idioms & proverbs", "".join(relation_rows)))
    english_count = sum(len(list(distinct_senses(group))) for group in (current, uncommon))
    vietnamese_count = len(list(distinct_senses(item.vi)))
    return "".join(parts), english_count, vietnamese_count
