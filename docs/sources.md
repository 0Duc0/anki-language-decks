# Sources and licenses

The update files combine dictionary data that was already in the decks with example sentences from open
parallel corpora. Every example on a card names its source (*Example sources: …* at the end of the examples).

## Example sentences

| Source | What is used | License / terms |
|---|---|---|
| [Tatoeba](https://tatoeba.org) | Vietnamese, Mandarin and Japanese sentences with linked English translations (per-language exports + links) | CC BY 2.0 FR (some sentences CC0). Each sentence is cited with its number. |
| [TED2020](https://opus.nlpl.eu/TED2020/corpus/version/TED2020) via [OPUS](https://opus.nlpl.eu) | Subtitle-aligned TED talk transcripts, en–vi / en–ja / en–zh_cn / en–zh_tw | CC BY-NC-ND 4.0 (TED). Non-commercial use only. |
| [OpenSubtitles 2018](https://opus.nlpl.eu/OpenSubtitles/corpus/version/OpenSubtitles) via OPUS | Aligned film and TV subtitles | Collected from opensubtitles.org; distributed by OPUS for research. Used only when the English side shows the meaning on the card. |

Ranking: Tatoeba before TED2020 before OpenSubtitles; within a source, shorter and more typical sentences
first. Filters drop links, numbers, markup, profanity, very short or very long lines, pairs whose length ratio
looks wrong, subtitles whose two sides do not line up (different number of sentences or dialogue dashes) and
sentences that nearly repeat one already on the card.

Chinese sentences are converted with [OpenCC](https://github.com/BYVoid/OpenCC) so that every example shows
Taiwan-standard traditional and simplified characters. Pinyin comes from the deck's own lexicon. Japanese
sentences are matched with [fugashi](https://github.com/polm/fugashi) + UniDic Lite, so conjugated forms
(食べた, 食べない) count for 食べる. Chinese word boundaries come from [jieba](https://github.com/fxsjy/jieba)
with the deck's words as the dictionary.

## Dictionaries (already in the decks; Vietnamese new words)

| Source | Used for | License |
|---|---|---|
| [Wiktionary](https://en.wiktionary.org) via [Kaikki](https://kaikki.org) | Vietnamese meanings, place names | CC BY-SA 4.0 / GFDL |
| [FVDP](https://www.crosswire.org/sword/modules/ModInfo.jsp?modName=FVDPVietAnh) (Free Vietnamese Dictionary Project) | Vietnamese–English meanings | see the FVDP module notes |
| [Underthesea UVD](https://github.com/undertheseanlp/resources) | Vietnamese–Vietnamese dictionary, phrases | see the Underthesea resources repository |
| [JMdict](https://www.edrdg.org/jmdict/j_jmdict.html) (EDRDG) | Japanese meanings | CC BY-SA 4.0 |
| [CC-CEDICT](https://cc-cedict.org) | Chinese meanings | CC BY-SA 4.0 |

Hand-written English glosses for 1,180 Vietnamese words that only had a Vietnamese definition
(`data/curated/vn_new_glosses_*.tsv`) and the hand-checked meaning order of the 700 most frequent Vietnamese
words with several meanings (`data/curated/vn_review_*.tsv`) were written for this project.

## Use

The update files are for personal study. Because TED2020 is non-commercial and OpenSubtitles is distributed for
research, do not sell or publish decks built from them.
