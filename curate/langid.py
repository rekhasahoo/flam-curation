"""Script + lexicon language ID. No model, no network, fully deterministic.

Labels: hi (Devanagari, incl. English-mixed), hi-Latn (romanized Hindi / Hinglish), en, other.
We never use source-provided labels. Known limitation: Marathi/Nepali/Sanskrit are Devanagari
too and land in 'hi'; see DECISIONS.md.
"""
import re

# Romanized-Hindi function words that are NOT common English words
# (deliberately excluded: main, par, tab, me, to, do, he, ho, is, the, kar, so).
HI_LATN = set("""hai hain nahi nahin nhi kya ke ki ka ko mein se aur bhi toh tha thi thhe hum tum mera meri
mere tera teri uska uski yeh ye woh wo vo kaise kyun kyu kyunki accha acha achha bahut bohot bahot kuch kuchh
karna karte karta karti raha rahi rahe abhi lekin magar agar jab kab kahan kaun wala wali wale hota hoti hote
hoga hogi gaya gayi gaye liye ek koi apna apne apni aap aapko tumhe mujhe humare hamare yaar bhai dost matlab
pata samajh chahiye sakta sakti sakte zyada jyada thoda bilkul sirf phir fir kaam log ghar paisa hoon hu hun
unhe unka unki iska iski isliye jaise waise aisa aisi aise kaisa kitna kitne bas jaldi sabse sab""".split())

EN_STOP = set("""the of and to in is are was were that it for with this on be as by at from have has had you not
but they we his her an or will would can could their there what which who when where how all if""".split())

_WORD = re.compile(r"[a-z']+")


_DEVA = re.compile(r"[^\u0900-\u0963\u0970-\u097f]")      # keeps Devanagari incl. matras, drops digits/danda
_LATIN = re.compile(r"[^A-Za-z\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u024f]")
_LETTER_ONLY = re.compile(r"[\W\d_]")


def _script_counts(text: str):
    deva_chars = _DEVA.sub("", text)
    deva = len(deva_chars)
    latin = len(_LATIN.sub("", text))
    all_letters = len(_LETTER_ONLY.sub("", text))
    deva_letters = len(_LETTER_ONLY.sub("", deva_chars))
    return deva, latin, max(0, all_letters - latin - deva_letters)


def detect(text: str) -> str:
    deva, latin, other = _script_counts(text)
    total = deva + latin + other
    if total < 3:
        return "other"                     # no linguistic signal (numbers, symbols)
    if deva >= 0.35 * total and deva >= other:
        return "hi"
    if latin >= 0.5 * total:
        toks = _WORD.findall(text.lower())
        if len(toks) < 2:
            return "other"
        hin = sum(t in HI_LATN for t in toks)
        en = sum(t in EN_STOP for t in toks)
        if hin >= 1 and hin / len(toks) >= 0.10 and hin >= 0.5 * en:
            return "hi-Latn"
        if en >= 1 and en / len(toks) >= 0.12:
            return "en"
        return "other"
    return "other"
