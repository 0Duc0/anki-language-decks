"""Dictionary-based Vietnamese word segmentation (syllable level).

A word "occurs" in a sentence only where forward AND backward longest matching both
produce it as one token. That keeps `thương` out of `thương mại`, and `học` out of `học sinh`.
"""
from __future__ import annotations

import re
import unicodedata

SYL = re.compile(r"[0-9A-Za-zÀ-ỹđĐ]+(?:[-’'][0-9A-Za-zÀ-ỹđĐ]+)*")


def norm(text: str) -> str:
    return unicodedata.normalize("NFC", text).lower()


class Segmenter:
    def __init__(self, words, max_len: int = 6):
        self.words: set[tuple[str, ...]] = set()
        self.max_len = 1
        for w in words:
            t = tuple(SYL.findall(norm(w)))
            if 1 <= len(t) <= max_len:
                self.words.add(t)
                self.max_len = max(self.max_len, len(t))

    def syllables(self, text: str) -> list[tuple[str, int, int]]:
        """[(syllable, start, end)] with character offsets into `text`."""
        return [(m.group(0).lower(), m.start(), m.end()) for m in SYL.finditer(unicodedata.normalize("NFC", text))]

    def _forward(self, syl: list[str]) -> list[tuple[int, int]]:
        out, i, n = [], 0, len(syl)
        while i < n:
            for k in range(min(self.max_len, n - i), 0, -1):
                if k == 1 or tuple(syl[i:i + k]) in self.words:
                    out.append((i, i + k))
                    i += k
                    break
        return out

    def _backward(self, syl: list[str]) -> list[tuple[int, int]]:
        out, j = [], len(syl)
        while j > 0:
            for k in range(min(self.max_len, j), 0, -1):
                if k == 1 or tuple(syl[j - k:j]) in self.words:
                    out.append((j - k, j))
                    j -= k
                    break
        return out[::-1]

    def tokens(self, text: str) -> list[tuple[str, int, int]]:
        """Agreed tokens: [(word, char_start, char_end)] found identically by both directions."""
        syls = self.syllables(text)
        s = [x[0] for x in syls]
        both = set(self._forward(s)) & set(self._backward(s))
        out = []
        for a, b in sorted(both):
            out.append((" ".join(s[a:b]), syls[a][1], syls[b - 1][2]))
        return out
