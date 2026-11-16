"""Cut a stream of text into sentences, so each one can be spoken as soon as it is ready."""
import re

# A full stop after one of these does not end the sentence.
ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc",
    "e.g", "i.e", "inc", "ltd", "approx", "u.s", "u.k", "a.m", "p.m",
}

# Sentence punctuation, optional closing quote or bracket, then white space.
# "3.14" never matches because no white space follows the dot.
_END = re.compile(r"([.!?]+[\"')\]]*)\s+")


def _ends_with_abbreviation(text: str) -> bool:
    if not text.endswith(".") or text.endswith(".."):
        return False
    last_word = text.split()[-1].rstrip(".")
    if last_word.lower() in ABBREVIATIONS:
        return True
    # A single capital letter is an initial, as in "J. K. Rowling". "I" is a word.
    return len(last_word) == 1 and last_word.isupper() and last_word != "I"


class SentenceSplitter:
    """Feed it chunks of text. It hands back whole sentences as they complete."""

    def __init__(self) -> None:
        self.buffer = ""

    def feed(self, text: str) -> list[str]:
        self.buffer += text
        sentences = []
        search_from = 0
        while match := _END.search(self.buffer, search_from):
            candidate = self.buffer[: match.end(1)]
            if _ends_with_abbreviation(candidate):
                search_from = match.end()
                continue
            sentences.append(candidate.strip())
            self.buffer = self.buffer[match.end():]
            search_from = 0
        return sentences

    def flush(self) -> list[str]:
        """Call at the end of the stream to get text that had no ending punctuation."""
        rest = self.buffer.strip()
        self.buffer = ""
        return [rest] if rest else []
