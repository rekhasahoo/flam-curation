"""Quality filters. Returns (text, reason|None). Each rule is conservative on purpose:
short proverbs, poems (many short lines, refrains) and digit-heavy tables are legitimate
tails of the distribution, so length/repetition/ratio rules have explicit exemptions."""
import re, unicodedata
from collections import Counter
from .config import Config

_URL = re.compile(r"(?:https?://|www\.)\S+", re.I)
_WS = re.compile(r"\s+")
_NOT_DIGIT = re.compile(r"\D")
_NOT_SYM = re.compile(r"[^{}\[\]<>=\\|^~`]")
_TEXTCH = re.compile(r"[^\w\u0900-\u0903\u093a-\u094f\u0951-\u0957\u0962\u0963]|[\d_]")   # letters + combining marks
_NOT_EMOJI = re.compile(r"[^\u2190-\u2bff\U0001F000-\U0001FAFF]")
# Explicit adult content, three tiers (calibrated by reading real output; see DECISIONS.md section 4):
#  STRONG = unambiguous terms.
#  MEDIUM = words that are the commonest terms in Hinglish erotica but have innocent uses ('chut' also
#           romanizes छूट = discount/exemption). One or two are ignored; three or more count as STRONG.
#  WEAK   = words common in health / sex-ed / news text ('sex', 'porn'); they never drop a document on
#           their own unless extremely dense (that is spam, not sex-ed).
# Deliberately absent: chod/chhod ("leave"), mutthi ("fist"), ganda ("dirty"), and anything that is only a
# substring of a common word (chutkara = relief, chutki = a pinch).
# Devanagari terms must match WHOLE words (+ a few inflections): a bare substring match flagged
# युगांडा (Uganda: 'गांड'), स्कॉटलंड/कैलंडर (Scotland/calendar: 'लंड') and सेंसेक्स (Sensex: 'सेक्स').
_STRONG_LAT = re.compile(
    r"\b(?:lund|lauda|loda|gand|gaand|gaandu|chudai|chudne|chudwa|chudwana|chudti|chodu|fuddi|bhosda|bhosdi|bhosdike|"
    r"boobs|fuck\w*|pussy|blowjob|handjob|threesome|antarvasna|kamukta)\b", re.I)
_MED_LAT = re.compile(r"\b(?:chut|choot|chuth|muth|randi|raand|nangi|nanga|horny)\b", re.I)
# 'sex' also means gender (sex ratio, same-sex, by sex, "Sex: Male"): those uses are NOT sexual content.
_SEX_AS_GENDER_BEFORE = "".join(f"(?<!{w})" for w in (
    "same ", "same-", "opposite ", "either ", "both ", "male ", "female ", "by ", "age and ", "age, ", "age & ",
    "gender and ", "gender or ", "gender, "))
_SEX_AS_GENDER_AFTER = (r"(?!\s*[-:]?\s*(?:ratios?|wise|determination|discrimination|chromosomes?|bias|gaps?|disaggregated|"
                        r"selective|selection|differences?|specific|stereotypes?|roles?|hormones?|characteristics?|distribution|"
                        r"and\s+age|or\s+age|and\s+gender|or\s+gender|(?:m|f|male|female)\b))")
_WEAK_LAT = re.compile(
    r"\b(?:" + _SEX_AS_GENDER_BEFORE + "sex" + _SEX_AS_GENDER_AFTER + r"|sexy|nipples?|cum|dick|cock|porn|xxx|orgasm|masturbat\w*|erotic)\b", re.I)


def _dev_words(words):
    alt = "|".join(re.escape(unicodedata.normalize("NFC", w)) for w in words)
    return re.compile(rf"(?<![\u0900-\u097f])(?:{alt})(?:ों|ें|ो|े|ू|ी)?(?![\u0900-\u097f])")


_STRONG_DEV = _dev_words(["लंड", "लण्ड", "चूत", "गांड", "गाण्ड", "चुदाई", "रंडी", "भोसड\u093cी", "भोसड\u093cा", "भोसडी",
                          "भोसड\u093cीके", "भोसडीके"])
_WEAK_DEV = re.compile(r"(?<![\u0900-\u097f])(?:सेक्स(?!\s*(?:रेशियो|रेश्यो|रेशो))|पोर्न|बूब्स)(?:ों|ें|ो|े|ू|ी)?(?![\u0900-\u097f])")
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

    ns = _WS.sub("", text)
    n = len(ns)
    if n < cfg.min_chars:
        return text, "too_short"
    digit_heavy = len(_NOT_DIGIT.sub("", ns)) / n >= 0.30      # tables of numbers are legitimate

    if len(_NOT_SYM.sub("", ns)) / n > cfg.max_symbol_ratio and not digit_heavy:
        return text, "markup_heavy"
    if not digit_heavy and len(_TEXTCH.sub("", ns)) / n < cfg.min_text_ratio:
        return text, "low_text_ratio"
    if len(_NOT_EMOJI.sub("", ns)) / n > 0.30:
        return text, "symbol_heavy"

    toks = text.split()
    urls = len(_URL.findall(text))
    if toks and urls / len(toks) > cfg.max_url_token_ratio:
        return text, "url_spam"
    if len(_SPAM.findall(text)) >= 2 or len(_HASHTAG.findall(text)) > max(10, len(toks) * 0.3):
        return text, "spam"
    strong = len(_STRONG_LAT.findall(text)) + len(_STRONG_DEV.findall(text))
    medium = len(_MED_LAT.findall(text))
    weak = len(_WEAK_LAT.findall(text)) + len(_WEAK_DEV.findall(text))
    if medium >= 3:                                   # repeated 'chut'/'horny'... is erotica, a lone one is not
        strong, medium = strong + medium, 0
    adult = strong + medium + weak
    if toks:
        ratio = adult / len(toks)
        if (strong >= cfg.min_adult_strong
                or (strong >= 2 and ratio >= cfg.max_adult_ratio / 2)
                or (strong >= 1 and adult >= cfg.min_adult_hits and ratio >= cfg.max_adult_ratio)
                or (adult >= 5 and ratio >= 0.08)
                # strict policy: sexual content in general goes, not just erotica. Costs: sex-ed, health and
                # news articles that discuss sex are removed too (documented in DECISIONS.md).
                or (cfg.adult_policy == "strict"
                    and (adult >= cfg.strict_min_hits or (strong >= 1 and ratio >= cfg.max_adult_ratio)))):
            return text, "adult_content"
    if not digit_heavy:
        if len(toks) >= 30 and len(set(toks)) / len(toks) < cfg.min_unique_token_ratio:
            return text, "repetitive"
        # Top-token rule looks at content-length tokens only: in a 10-word Hindi stub, 'के' alone can be
        # 30% of the words without the text being repetitive (this dropped legit Wikipedia stubs before).
        long_toks = [t for t in toks if len(t) >= 4]
        if len(long_toks) >= 20 and Counter(long_toks).most_common(1)[0][1] / len(long_toks) > cfg.max_top_token_ratio:
            return text, "repetitive"
        if not poem_like and len(lines) >= 5 and len(set(lines)) / len(lines) < 0.2:
            return text, "repetitive"
    if toks and len(_BADSTART.findall(text)) / len(toks) > cfg.max_bad_start_ratio:
        return text, "garbled_devanagari"
    return text, None
