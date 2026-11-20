"""Highlight a cited excerpt on a PDF page (the yellow marks in the source drawer).

The excerpt is split into lines and sentences; each part is searched on the page in runs of 10 words. A run
that is not found (across a column break, or a table header whose first cell is worded differently) is
searched again in runs of 6, then 4. Every word of a part is covered: the last run ends on the part's last
word, so a sentence's tail is never left unhighlighted.
"""
from __future__ import annotations

import re

COLOR = (1, 0.85, 0.2)
MIN_WORDS = 3


def runs(words: list[str], size: int) -> list[list[str]]:
    """Consecutive runs of `size` words covering every word; the last run ends on the last word (it may
    overlap the run before it by a few words, and is never shorter than MIN_WORDS)."""
    if len(words) <= size:
        return [words]
    out = [words[i:i + size] for i in range(0, len(words) - size + 1, size)]
    covered = (len(words) - size) // size * size + size
    if covered < len(words):
        out.append(words[min(covered, len(words) - MIN_WORDS):])
    return out


SIZES = (10, 6, 4)


def highlight(page, q: str) -> int:
    """Add highlight annotations for excerpt `q` on a fitz page. Returns how many were added."""
    def mark(words: list[str], sizes: tuple[int, ...]) -> int:
        n = 0
        for run in runs(words, sizes[0]):
            hits = page.search_for(" ".join(run))
            for rect in hits:
                annot = page.add_highlight_annot(rect)
                annot.set_colors(stroke=COLOR)
                annot.update()
            n += len(hits)
            if not hits and len(sizes) > 1 and len(run) > MIN_WORDS:
                n += mark(run, sizes[1:])     # e.g. a table header whose first cell is worded differently
        return n

    added = 0
    for part in re.split(r"\n|(?<=[.;:])\s+", q or ""):
        words = part.replace(" | ", " ").split()
        if len(words) >= MIN_WORDS:
            added += mark(words, SIZES)
    return added
