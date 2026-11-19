"""Text preparation for RSVP reading: tokens, the optimal recognition point and timing.

Pure Python, no Qt, so it is easy to test and reuse.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SENTENCE_END = ".!?…"
PAUSE_END = ",;:"
DASHES = {"-", "–", "—", "‒", "―"}
CLOSERS = "\"'”’)»]}"


@dataclass
class Token:
    word: str
    sentence_end: bool = False
    pause: bool = False
    paragraph_end: bool = False


def tokenize(text: str) -> list[Token]:
    """Split text into display tokens.

    Joins words hyphenated across line breaks, glues stand-alone dashes and
    punctuation to the previous word and marks sentence, clause and paragraph ends.
    """
    text = text.replace("­", "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(\w)-\n[ \t]*(\w)", r"\1\2", text)
    tokens: list[Token] = []
    for paragraph in re.split(r"\n\s*\n", text):
        words = paragraph.split()
        for w in words:
            if w in DASHES and tokens:
                tokens[-1].word += " " + ("–" if w == "-" else w)
                tokens[-1].pause = True
                continue
            if len(w) > 1 and not re.search(r"\w", w) and tokens:  # "...", "!?" on their own
                tokens[-1].word += w
                continue
            tokens.append(Token(w))
        if tokens and words:
            tokens[-1].paragraph_end = True
    for t in tokens:
        core = t.word.rstrip(CLOSERS)
        if core:
            t.sentence_end = core[-1] in SENTENCE_END
            t.pause = t.pause or core[-1] in PAUSE_END
    return tokens


def orp_index(word: str) -> int:
    """Index of the optimal recognition point: slightly left of the middle.

    Leading and trailing punctuation is ignored when measuring the word.
    """
    start = 0
    while start < len(word) and not word[start].isalnum():
        start += 1
    if start == len(word):
        return len(word) // 2
    end = len(word)
    while end > start and not word[end - 1].isalnum():
        end -= 1
    n = end - start
    offset = 0 if n <= 1 else 1 if n <= 5 else 2 if n <= 9 else 3 if n <= 13 else 4
    return start + offset


def split_word(word: str) -> tuple[str, str, str]:
    i = orp_index(word)
    return word[:i], word[i : i + 1], word[i + 1 :]


def delay_factor(t: Token) -> float:
    """How long a token stays on screen relative to the base word time."""
    n = len(t.word)
    m = 1.0
    if n > 7:
        m += min(0.06 * (n - 7), 0.7)
    if any(c.isdigit() for c in t.word):
        m += 0.3
    if t.sentence_end:
        m += 1.1
    elif t.pause:
        m += 0.5
    if t.paragraph_end:
        m += 0.9
    return m


def word_ms(t: Token, wpm: int) -> float:
    return 60000.0 / wpm * delay_factor(t)


def remaining_seconds(tokens: list[Token], start: int, wpm: int) -> float:
    return sum(word_ms(t, wpm) for t in tokens[start:]) / 1000.0


def sentence_start(tokens: list[Token], i: int) -> int:
    j = i
    while j > 0 and not tokens[j - 1].sentence_end:
        j -= 1
    return j


def previous_sentence(tokens: list[Token], i: int) -> int:
    """Start of the current sentence, or of the previous one when already at a start."""
    j = sentence_start(tokens, i)
    if i - j <= 1 and j > 0:
        j = sentence_start(tokens, j - 1)
    return j


def next_sentence(tokens: list[Token], i: int) -> int:
    j = i
    while j < len(tokens) - 1 and not tokens[j].sentence_end:
        j += 1
    return min(len(tokens) - 1, j + 1)
