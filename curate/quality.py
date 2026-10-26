"""Quality filters. Returns (text, reason|None). Each rule is conservative on purpose:
short proverbs, poems (many short lines, refrains) and digit-heavy tables are legitimate
tails of the distribution, so length/repetition/ratio rules have explicit exemptions."""
import re, unicodedata
from .config import Config

_URL = re.compile(r"(?:https?://|www\.)\S+", re.I)
_SYMS = set("{}[]<>=\\|^~`")
_HASHTAG = re.compile(r"#\w+")
_BOILER = re.compile(
    r"cookie|privacy policy|terms (?:of use|and conditions)|all rights reserved|©|copyright|click here|"
    r"read more|subscribe|follow us|sign in|log ?in|share on|advertisement|powered by|"
    r"सर्वाधिकार सुरक्षित|अधिक पढ़ें|और पढ़ें|यह भी पढ़ें|ये भी पढ़ें|सब्सक्राइब|फॉलो करें|लॉग ?इन|विज्ञापन|कुकी|गोपनीयता नीति|शेयर करें",
    re.I)
_SPAM = re.compile(r"casino|viagra|slot gacor|togel|judi online|porn|xxx|escort|call girl|betting|बेटिंग|सट्टा|कैसीनो", re.I)
_BADSTART = re.compile(r"(?:^|\s)[\u093e-\u094d\u0901-\u0903\u0962\u0963]")


def check(text: str, flags: dict, cfg: Config):
    if flags.get("markup_ratio", 0) > cfg.max_tag_ratio:
        return text, "markup_heavy"
    if text.count("\ufffd") >= 3 or text.count("\ufffd") / max(1, len(text)) > 0.005:
        return text, "garbled_encoding"
    # leftover mojibake that repair_mojibake could not fix
    if len(re.findall("\u00e0\u00a4|\u00e0\u00a5|Ã.|â€", text)) >= 3:
        return text, "garbled_encoding"

    lines = [l for l in text.split("\n") if l.strip()]
    avg_line = sum(len(l) for l in lines) / max(1, len(lines))
    poem_like = len(lines) >= 4 and avg_line < 60          # keep refrains / short lines

    # boilerplate: a doc that is mostly boilerplate lines is dropped (poems included: a footer of
    # four short lines is not a poem); otherwise short boilerplate lines are stripped, except in poems
    if lines:
        bad = [l for l in lines if len(l) < 120 and _BOILER.search(l)]
        if len(bad) / len(lines) > cfg.max_boilerplate_line_ratio:
            return text, "boilerplate"
        if bad and not poem_like:
            badset = set(bad)
            text = "\n".join(l for l in text.split("\n") if l not in badset).strip()
            lines = [l for l in text.split("\n") if l.strip()]

    nonspace = [c for c in text if not c.isspace()]
    if len(nonspace) < cfg.min_chars:
        return text, "too_short"
    n = len(nonspace)
    digits = sum(c.isdigit() for c in nonspace)
    digit_heavy = digits / n >= 0.30                        # tables of numbers are legitimate

    if sum(c in _SYMS for c in nonspace) / n > cfg.max_symbol_ratio and not digit_heavy:
        return text, "markup_heavy"
    letters = sum(unicodedata.category(c)[0] in "LM" for c in nonspace)
    if not digit_heavy and letters / n < cfg.min_text_ratio:
        return text, "low_text_ratio"
    if sum(unicodedata.category(c) in ("So", "Sk") for c in nonspace) / n > 0.30:
        return text, "symbol_heavy"

    toks = text.split()
    urls = len(_URL.findall(text))
    if toks and urls / len(toks) > cfg.max_url_token_ratio:
        return text, "url_spam"
    if len(_SPAM.findall(text)) >= 2 or len(_HASHTAG.findall(text)) > max(10, len(toks) * 0.3):
        return text, "spam"
    if not digit_heavy:
        if len(toks) >= 30 and len(set(toks)) / len(toks) < cfg.min_unique_token_ratio:
            return text, "repetitive"
        if len(toks) >= 10:
            top = max(toks.count(t) for t in set(toks))
            if top / len(toks) > cfg.max_top_token_ratio:
                return text, "repetitive"
        if not poem_like and len(lines) >= 5 and len(set(lines)) / len(lines) < 0.2:
            return text, "repetitive"
    if toks and len(_BADSTART.findall(text)) / len(toks) > cfg.max_bad_start_ratio:
        return text, "garbled_devanagari"
    return text, None
