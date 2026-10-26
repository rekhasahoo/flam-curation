"""Unicode normalization and the dedup key.

Why this matters for Devanagari: the same visible string can be encoded several ways
(precomposed nukta letters vs base+U+093C, stray ZWJ/ZWNJ, zero-width spaces, NBSP,
Devanagari vs ASCII digits). If we don't collapse these, dedup and contamination checks
silently miss copies.
"""
import html, re, unicodedata

VIRAMA = "\u094d"
ZWJ, ZWNJ = "\u200d", "\u200c"
DEVA_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

_INVISIBLE = re.compile(
    "[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f\u00ad\u200b\u200e\u200f"
    "\u202a-\u202e\u2060-\u2064\u2066-\u206f\ufeff\u180e\u061c\ufff9-\ufffb]")
_HSPACE = re.compile(r"[^\S\n]+")            # any whitespace except newline (incl. NBSP, thin space)
_TAG = re.compile(r"<(?:/?[A-Za-z][^<>]{0,300}|!--.*?--|!DOCTYPE[^>]*)>", re.S)
_ENTITY = re.compile(r"&(?:#\d+|#x[0-9a-fA-F]+|[A-Za-z]{2,8});")
_MOJI = re.compile("(?:\u00e0\u00a4|\u00e0\u00a5|Ã.|â€)")  # UTF-8 Devanagari/quotes read as latin-1/cp1252


def _fix_joiners(s: str) -> str:
    """ZWJ/ZWNJ are meaningful only right after a virama (half-forms, conjunct control)."""
    if ZWJ not in s and ZWNJ not in s:
        return s
    out, prev = [], ""
    for ch in s:
        if ch in (ZWJ, ZWNJ) and prev != VIRAMA:
            continue
        out.append(ch)
        prev = ch
    return "".join(out)


def repair_mojibake(s: str):
    """Undo 'UTF-8 decoded as cp1252/latin-1'. Only accept if it yields Devanagari/cleaner text."""
    if len(_MOJI.findall(s)) < 3:
        return s, False
    for enc in ("cp1252", "latin-1"):
        try:
            fixed = s.encode(enc).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if len(_MOJI.findall(fixed)) < len(_MOJI.findall(s)):
            return fixed, True
    return s, False


def normalize(raw: str):
    """-> (text, flags). flags: markup_ratio, mojibake_fixed."""
    flags = {"mojibake_fixed": False, "markup_ratio": 0.0}
    s, flags["mojibake_fixed"] = repair_mojibake(raw)
    s = unicodedata.normalize("NFC", s)
    # markup: measure first, strip tags/entities after (quality stage drops heavy-markup docs)
    if "<" in s or "&" in s:
        tag_chars = sum(len(m.group(0)) for m in _TAG.finditer(s))
        flags["markup_ratio"] = tag_chars / max(1, len(s))
        s = _TAG.sub(" ", s)
        s = html.unescape(s) if _ENTITY.search(s) else s
        s = unicodedata.normalize("NFC", s)
    s = _INVISIBLE.sub("", s)
    s = _fix_joiners(s)
    s = s.replace("\r\n", "\n").replace("\r", "\n").replace("\u2028", "\n").replace("\u2029", "\n")
    s = _HSPACE.sub(" ", s)
    s = re.sub(r" ?\n ?", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s, flags


def dedup_key(text: str) -> str:
    """Aggressive comparison form: things that *read* the same compare the same.
    casefold, drop joiners, fold Devanagari digits, punctuation/symbols -> space, collapse spaces."""
    s = unicodedata.normalize("NFKC", text).casefold()
    s = s.replace(ZWJ, "").replace(ZWNJ, "").translate(DEVA_DIGITS)
    s = "".join(" " if unicodedata.category(c)[0] in "PSZC" else c for c in s)
    return " ".join(s.split())
