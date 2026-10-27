"""Script-independent 'consonant skeleton' used to catch a Devanagari eval item that appears in
training in Latin script (or vice-versa). Vowels/matras/virama are dropped on both sides and
consonants are folded into coarse classes, so  है/hai -> h,  मैं/main -> mn,  घर/ghar -> gr.
Deliberately crude: it is a *candidate generator* with a high overlap threshold, not a transliterator."""
import re
from functools import lru_cache

_DEV = {}
for chars, cls in [("कखक़ख़", "k"), ("गघग़", "g"), ("चछ", "c"), ("जझज़", "j"), ("टठतथ", "t"), ("डढदध", "d"),
                   ("णन", "n"), ("पफफ़", "p"), ("बभ", "b"), ("म", "m"), ("य", "y"), ("रड़ढ़ऱ", "r"),
                   ("लळ", "l"), ("व", "v"), ("शषस", "s"), ("ह", "h"), ("ंँ", "n")]:
    for ch in chars:
        _DEV[ch] = cls
_DIGRAPH = [("chh", "c"), ("kh", "k"), ("gh", "g"), ("ch", "c"), ("jh", "j"), ("th", "t"), ("dh", "d"),
            ("bh", "b"), ("ph", "p"), ("sh", "s"), ("ng", "n")]
_LAT = {"f": "p", "w": "v", "z": "j", "q": "k", "c": "k", "x": "ks"}
_VOWELS = set("aeiou")


def _collapse(s):
    return re.sub(r"(.)\1+", r"\1", s)


@lru_cache(maxsize=500_000)
def deva_word(w: str) -> str:
    return _collapse("".join(_DEV.get(c, "") for c in w))


@lru_cache(maxsize=500_000)
def latin_word(w: str) -> str:
    w = w.lower()
    for a, b in _DIGRAPH:
        w = w.replace(a, b.upper())              # protect digraph results from later single-letter maps
    out = []
    for c in w:
        if c.isupper():
            out.append(c.lower())
        elif c in _VOWELS or not c.isalpha():
            continue
        else:
            out.append(_LAT.get(c, c))
    return _collapse("".join(out))


def skeleton_words(text: str, lang: str):
    toks = re.findall(r"[\u0900-\u097f]+|[A-Za-z]+", text)
    f = deva_word if lang == "hi" else latin_word
    return [s for s in (f(t) if (t[0] >= "\u0900") == (lang == "hi") else "" for t in toks) if s]
