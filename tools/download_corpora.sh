#!/bin/sh
# Download the raw corpora into ./corpora (not committed). Run from the repository root.
set -eu
mkdir -p corpora && cd corpora
T=https://downloads.tatoeba.org/exports
for l in vie cmn jpn eng; do curl -sSfLO $T/per_language/$l/${l}_sentences.tsv.bz2; done
curl -sSfLO $T/links.tar.bz2
curl -sSfLO $T/per_language/cmn/cmn_sentences_with_audio.tsv.bz2 || true
O=https://object.pouta.csc.fi
curl -sSfL -o ted_en-vi.zip $O/OPUS-TED2020/v1/moses/en-vi.txt.zip
curl -sSfL -o ted_en-ja.zip $O/OPUS-TED2020/v1/moses/en-ja.txt.zip
curl -sSfL -o ted_en-zh_cn.zip $O/OPUS-TED2020/v1/moses/en-zh_cn.txt.zip
curl -sSfL -o ted_en-zh_tw.zip $O/OPUS-TED2020/v1/moses/en-zh_tw.txt.zip
curl -sSfL -o os_en-vi.zip $O/OPUS-OpenSubtitles/v2018/moses/en-vi.txt.zip
curl -sSfL -o os_en-ja.zip $O/OPUS-OpenSubtitles/v2018/moses/en-ja.txt.zip
curl -sSfL -o os_en-zh_cn.zip $O/OPUS-OpenSubtitles/v2018/moses/en-zh_cn.txt.zip
curl -sSfL -o os_en-zh_tw.zip $O/OPUS-OpenSubtitles/v2018/moses/en-zh_tw.txt.zip
echo done
