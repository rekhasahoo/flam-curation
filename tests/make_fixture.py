"""Synthetic messy raw data for smoke tests: python tests/make_fixture.py <raw_dir> [n]"""
import gzip, json, os, random, sys

HI = """भारत एक विशाल देश है जहाँ अनेक भाषाएँ बोली जाती हैं।
गंगा नदी हिमालय से निकलकर बंगाल की खाड़ी में मिलती है।
आज सुबह मौसम बहुत सुहावना था और हम सब पार्क में टहलने गए।
किसान खेतों में धान की रोपाई कर रहे हैं क्योंकि मानसून आ चुका है।
दिल्ली में हर साल लाखों पर्यटक लाल किला देखने आते हैं।
विद्यालय में बच्चों को पढ़ाई के साथ खेलकूद भी सिखाया जाता है।
इस वर्ष की परीक्षा में छात्रों ने बहुत अच्छे अंक प्राप्त किए।
हमारे गाँव में एक पुराना मंदिर है जिसकी देखभाल सब मिलकर करते हैं।
मुंबई की लोकल ट्रेन शहर की जीवन रेखा मानी जाती है।
कंप्यूटर और इंटरनेट ने हमारे काम करने का तरीका पूरी तरह बदल दिया है।
सरकार ने ग्रामीण क्षेत्रों में नई सड़कें बनाने की योजना शुरू की है।
रात को आसमान में चाँद और तारे बहुत सुंदर दिखाई देते हैं।
क्रिकेट भारत में सबसे लोकप्रिय खेल है और लोग इसे बड़े शौक से देखते हैं।
माँ ने रसोई में स्वादिष्ट हलवा बनाया और पूरे परिवार ने साथ बैठकर खाया।
पुस्तकालय में बैठकर पढ़ना मुझे बहुत शांति देता है।
विज्ञान की प्रगति से चिकित्सा के क्षेत्र में अनेक नई खोजें हुई हैं।
बारिश के बाद सड़कों पर पानी भर गया और यातायात रुक गया।
राजस्थान के रेगिस्तान में ऊँट की सवारी पर्यटकों को बहुत पसंद आती है।
नदी के किनारे बैठकर पक्षियों का गाना सुनना एक अलग ही अनुभव है।
त्योहारों के समय बाज़ार में बहुत भीड़ और रौनक रहती है।""".split("\n")
HL = """Mujhe yeh movie bahut pasand aayi, acting kaafi achhi thi aur story bhi mast hai.
Kal main apne dost ke ghar gaya tha, wahan sab log mil kar khana kha rahe the.
Aaj ka din bahut thaka dene wala tha, ab ghar jaake bas so jaunga.
Tum kab aa rahe ho yaar, hum sab tumhara intezaar kar rahe hain.
Yeh phone ki battery bahut jaldi khatam ho jati hai, kuch karna padega.
Mere paas abhi time nahi hai, lekin kal pakka baat karte hain.
Bhai ye wala restaurant sabse best hai, khana bhi sasta aur swadisht hota hai.
Agar tum mehnat karoge toh zarur kamyab hoge, bas himmat mat haarna.
Hamare college mein kal ek bada function hai aur sabko wahan aana hai.
Kya tumne woh naya gaana suna, mujhe toh bahut zyada pasand aaya.
Is saal barish bahut kam hui hai isliye kisan log pareshan hain.
Mujhe samajh nahi aa raha ki yeh kaam kaise karna chahiye.""".split("\n")
EN = ["The quick brown fox jumps over the lazy dog and then runs away from the farm.",
      "This is a long English paragraph that should be dropped because it is neither Hindi nor Hinglish at all."]
PROVERBS = ["जैसी करनी वैसी भरनी", "अब पछताए होत क्या जब चिड़िया चुग गई खेत", "नाच न जाने आँगन टेढ़ा",
            "एक और एक ग्यारह", "बूँद बूँद से घड़ा भरता है"]
POEM = "सुबह की किरणें आईं,\nकलियाँ खिल गईं,\nचिड़िया गीत गाईं,\nसुबह की किरणें आईं,\nहवा मुस्काई।"
TABLE = "1990 45.3 12\n1991 47.8 14\n1992 49.1 15\n1993 52.0 19"
NBSP, ZWSP = "\u00a0", "\u200b"


def main(raw, n=1200, seed=7):
    rnd = random.Random(seed)
    os.makedirs(os.path.join(raw, "wiki"), exist_ok=True); os.makedirs(os.path.join(raw, "web"), exist_ok=True)
    bag_hi = sorted({w.strip("।,") for l in HI for w in l.split()})
    bag_hl = sorted({w.strip(".,").lower() for l in HL for w in l.split()})
    sent = lambda bag, k: " ".join(rnd.sample(bag, k))
    docs_hi = [(sent(bag_hi, 12) + "। ") * 1 + sent(bag_hi, 10) + "। " + sent(bag_hi, 11) + "।" for _ in range(n)]
    docs_hl = [sent(bag_hl, 12) + ". " + sent(bag_hl, 10) + ". " + sent(bag_hl, 9) for _ in range(n // 4)]
    web = [{"text": t, "url": f"http://x/{i}"} for i, t in enumerate(docs_hl)]
    wiki = [{"text": t} for t in docs_hi]
    # ---- messy variants
    for i in range(0, 60):
        b = docs_hi[i]
        wiki.append({"text": b})                                               # exact dup
        wiki.append({"text": b.replace(" ", NBSP + ZWSP, 2) + "\u200d"})        # invisible chars
        wiki.append({"text": b + " " + HI[i % len(HI)]})                       # near dup (extra sentence)
    import unicodedata
    for i in range(60, 100):                                                   # NFD variant (nukta letters)
        wiki.append({"text": unicodedata.normalize("NFD", docs_hi[i])})
    # cross-script copies of Devanagari docs into Hinglish source (romanized by hand-ish: reuse HL as proxy)
    web += [{"text": "Mujhe yeh movie bahut pasand aayi, acting kaafi achhi thi aur story bhi mast hai."}] * 3
    wiki += [{"text": "<div class='x'><p>" + HI[1] + "</p><script>var a=1;</script></div>"},
             {"text": HI[2].encode("utf-8").decode("latin-1") + HI[3].encode("utf-8").decode("latin-1")},
             {"text": "संपर्क करें 9876543210 या ईमेल rashmi.k@example.co.in पैन ABCPE1234F " + HI[4]},
             {"text": "आधार संख्या 2345 6789 0124 और साल 2018 2019 2020 कीमत ₹1,00,000 " + HI[5]},
             {"text": "सर्वाधिकार सुरक्षित\nअधिक पढ़ें\nसब्सक्राइब करें\nविज्ञापन"},
             {"text": "casino betting porn xxx casino " * 20},
             {"text": "   "}, {"text": ""}, {"notext": 1}, {"text": 12345},
             {"text": POEM}, {"text": TABLE}] + [{"text": p} for p in PROVERBS] + [{"text": p} for p in PROVERBS]  # proverbs twice => exact dup
    web += [{"text": e} for e in EN]
    with gzip.open(os.path.join(raw, "wiki", "part0.jsonl.gz"), "wt", encoding="utf-8") as f:
        for r in wiki[: len(wiki) // 2]:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.write("{this is not json\n"); f.write('{"text": "अधूरा\n')
    with open(os.path.join(raw, "wiki", "part1.jsonl"), "w", encoding="utf-8") as f:
        for r in wiki[len(wiki) // 2:]:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.write("\n"); f.write("[1,2,3]\n")
    with open(os.path.join(raw, "web", "hinglish.jsonl"), "w", encoding="utf-8") as f:
        for r in web:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(raw, "web", "bad_bytes.jsonl"), "wb") as f:
        f.write(b'{"text": "ok \xff\xfe broken bytes"}\n')
    json.dump([{"name": "synthetic", "url": "n/a", "license": "CC0", "downloaded": "2026-10-27"}],
              open(os.path.join(raw, "SOURCES.json"), "w"))


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 1200)
