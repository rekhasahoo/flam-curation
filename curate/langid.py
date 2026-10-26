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


def _script_counts(text: str):
    deva = latin = other = 0
    for ch in text:
        o = ord(ch)
        if 0x0900 <= o <= 0x097F:
            if 0x0966 <= o <= 0x096F or o in (0x0964, 0x0965):   # digits, danda
                continue
            deva += 1
        elif ch.isalpha():
            if o < 0x250:
                latin += 1
            else:
                other += 1
    return deva, latin, other


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
