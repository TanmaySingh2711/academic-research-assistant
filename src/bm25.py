"""BM25 keyword search: scores chunks by the words they share with the question.

Vector search understands meaning ("how were the models validated" finds "cross validation"),
but it is weak at exact terms: a number like 0.035, a name like LightGBM, or "RTX 3060".
BM25 is the classic search-engine formula for exact words, so the two complement each other.

For a question word w and a chunk c:
    idf(w)    = log(1 + (N - n(w) + 0.5) / (n(w) + 0.5))     rare words count more
    tf part   = f(w, c) * (k1 + 1) / (f(w, c) + k1 * (1 - b + b * len(c) / avg_len))
    score(c)  = sum over the question words of idf(w) * tf part
N = number of chunks, n(w) = chunks that contain w, f(w, c) = how often w is in c.
k1 limits how much repeating a word helps; b corrects for long chunks containing more words.
"""

import math
import re
from collections import Counter

from src.schema import Chunk

K1 = 1.5
B = 0.75

# Common words that say nothing about the topic
STOPWORDS = set(
    "a an and are as at be been but by can could did do does for from had has have how i if in into is it its "
    "of on or our so such than that the their them then there these they this to was we were what when where "
    "which who why will with would you your about after also any more most other over only same some".split()
)

# Words and numbers; a number keeps its decimal point ("0.035") and loses thousands commas ("85,000")
_TOKEN = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)*")


def tokenize(text: str) -> list[str]:
    tokens = []
    for token in _TOKEN.findall(text.lower()):
        token = token.replace(",", "")
        if token in STOPWORDS:
            continue
        # Very small stemming: "levels" -> "level", "studies" -> "study"
        if token.endswith("ies") and len(token) > 4:
            token = token[:-3] + "y"
        elif token.endswith("s") and not token.endswith("ss") and len(token) > 3 and not token[0].isdigit():
            token = token[:-1]
        tokens.append(token)
    return tokens


class BM25:
    """A BM25 index over a list of chunks. Build once, then score many questions."""

    def __init__(self, chunks: list[Chunk]):
        self.docs = [Counter(tokenize(chunk["text"])) for chunk in chunks]
        self.lengths = [sum(doc.values()) for doc in self.docs]
        self.avg_length = sum(self.lengths) / len(self.lengths) if self.lengths else 0.0
        containing: Counter[str] = Counter()
        for doc in self.docs:
            containing.update(doc.keys())
        n = len(self.docs)
        self.idf = {word: math.log(1 + (n - count + 0.5) / (count + 0.5)) for word, count in containing.items()}

    def score(self, question: str, rows: list[int]) -> list[float]:
        """BM25 score of the question for each chunk row in `rows` (same order)."""
        words = set(tokenize(question))
        scores = []
        for row in rows:
            doc, length = self.docs[row], self.lengths[row]
            total = 0.0
            for word in words:
                freq = doc.get(word, 0)
                if freq:
                    norm = 1 - B + B * length / self.avg_length
                    total += self.idf[word] * freq * (K1 + 1) / (freq + K1 * norm)
            scores.append(total)
        return scores
