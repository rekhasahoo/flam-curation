"""PII redaction: email, PAN, Aadhaar, Indian phone numbers.

Matching runs on a digit-folded view (Devanagari digits -> ASCII, 1:1 so offsets line up)
and replaces spans in the original text. Priority email > PAN > Aadhaar > phone, no overlaps.
Precision matters as much as recall: years, prices (1,00,000), dates and plain 10-digit-looking
ids must survive, so Aadhaar needs a Verhoeff checksum or a keyword, and phones need a valid
mobile prefix [6-9] and exact digit counts.
"""
import re
from collections import Counter
from .textnorm import DEVA_DIGITS

_D = [[0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],[3,4,0,1,2,8,9,5,6,7],[4,0,1,2,3,9,5,6,7,8],
      [5,9,8,7,6,0,4,3,2,1],[6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],[8,7,6,5,9,3,2,1,0,4],[9,8,7,6,5,4,3,2,1,0]]
_P = [[0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,3,7,9,6,1,4,2],[8,9,1,6,0,4,3,5,2,7],
      [9,4,5,3,1,2,6,8,7,0],[4,2,8,6,5,7,3,9,0,1],[2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8]]


def verhoeff_ok(num: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


EMAIL = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}(?![\w-])")
PAN = re.compile(r"(?<![A-Za-z0-9])[A-Z]{3}[ABCFGHLJPT][A-Z]\d{4}[A-Z](?![A-Za-z0-9])", re.I)
AADHAAR_G = re.compile(r"(?<!\d)(?<!\d[ -])[2-9]\d{3}([ -])\d{4}\1\d{4}(?!\d)(?![ -]\d)")
AADHAAR_P = re.compile(r"(?<!\d)[2-9]\d{11}(?!\d)")
_AADHAAR_KW = re.compile(r"aadhaar|aadhar|adhaar|uidai|\buid\b|आधार", re.I)
_SEP = r"[ .-]?"
PHONE = re.compile(
    r"(?<![\d])(?:(?:\+|00)[ ]?91[ .-]?|91[ .-]?|0)?"
    r"(?:[6-9]\d{9}|[6-9]\d{4}[ .-]\d{5}|[6-9]\d{2}[ .-]\d{3}[ .-]\d{4}|[6-9]\d{3}[ .-]\d{3}[ .-]\d{3})(?![\d])")
LANDLINE = re.compile(r"(?<![\d])0\d{2,4}[ -]\d{6,8}(?![\d])")


def _looks_like_years(g: str) -> bool:
    parts = re.split(r"[ -]", g)
    return all(1900 <= int(p) <= 2100 for p in parts)


def redact(text: str, aadhaar_strict: bool = False):
    view = text.translate(DEVA_DIGITS)
    claimed, spans = [], []

    def free(a, b):
        return all(b <= x or a >= y for x, y in claimed)

    def add(a, b, tag):
        if free(a, b):
            claimed.append((a, b)); spans.append((a, b, tag))

    for m in EMAIL.finditer(view):
        add(m.start(), m.end(), "<EMAIL>")
    for m in PAN.finditer(view):
        add(m.start(), m.end(), "<PAN>")

    def kw_near(a):
        return bool(_AADHAAR_KW.search(view[max(0, a - 20):a]))
    for m in AADHAAR_G.finditer(view):
        digits = re.sub(r"\D", "", m.group(0))
        if verhoeff_ok(digits):
            ok = True
        elif _looks_like_years(m.group(0)):
            ok = False                       # '2018 2019 2020' is a year list, never an Aadhaar
        else:
            ok = kw_near(m.start()) or not aadhaar_strict
        if ok:
            add(m.start(), m.end(), "<AADHAAR>")
    for m in AADHAAR_P.finditer(view):
        if verhoeff_ok(m.group(0)) or kw_near(m.start()):
            add(m.start(), m.end(), "<AADHAAR>")
    for rx in (PHONE, LANDLINE):
        for m in rx.finditer(view):
            add(m.start(), m.end(), "<PHONE>")

    if not spans:
        return text, Counter()
    spans.sort()
    out, last, counts = [], 0, Counter()
    for a, b, tag in spans:
        out.append(text[last:a]); out.append(tag); last = b
        counts[tag.strip("<>").lower()] += 1
    out.append(text[last:])
    return "".join(out), counts
