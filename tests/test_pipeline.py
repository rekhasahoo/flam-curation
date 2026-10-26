"""python3 -m unittest discover -s tests -v"""
import hashlib, json, os, shutil, subprocess, sys, tempfile, unittest, unicodedata
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from curate import langid, pii, textnorm
from curate.config import Config
from curate.pipeline import ContamIndex


class TestNormalize(unittest.TestCase):
    def test_nfd_nukta_and_invisibles_collapse(self):
        a = "क़िला ज़रूर"
        b = unicodedata.normalize("NFD", a).replace(" ", "\u00a0\u200b")
        self.assertEqual(textnorm.normalize(a)[0], textnorm.normalize(b)[0])

    def test_joiner_kept_only_after_virama(self):
        self.assertIn("\u200d", textnorm.normalize("क्\u200dष")[0])
        self.assertNotIn("\u200d", textnorm.normalize("का\u200dम")[0])

    def test_mojibake_repair(self):
        s = "भारत एक देश है".encode("utf-8").decode("latin-1")
        self.assertEqual(textnorm.normalize(s)[0], "भारत एक देश है")

    def test_dedup_key_folds_digits_and_punct(self):
        self.assertEqual(textnorm.dedup_key("साल २०२४, अच्छा।"), textnorm.dedup_key("साल 2024 अच्छा"))


class TestPII(unittest.TestCase):
    def test_redacts(self):
        t, c = pii.redact("फोन +91 98765 43210, ९८७६५४३२१०, mail a@b.in PAN ABCPE1234F")
        self.assertEqual(c, {"phone": 2, "email": 1, "pan": 1})
        self.assertNotIn("98765", t)

    def test_non_pii_survives(self):
        s = "साल 2018 2019 2020 कीमत ₹1,00,000 तारीख 03-04-2021 संख्या 1234567890123 कोड 5123456"
        self.assertEqual(pii.redact(s)[0], s)

    def test_aadhaar(self):
        good = next(p + str(d) for p in ["23456789012"] for d in range(10) if pii.verhoeff_ok(p + str(d)))
        t, c = pii.redact(f"आधार {good[:4]} {good[4:8]} {good[8:]}")
        self.assertEqual(c["aadhaar"], 1)


class TestLangid(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(langid.detect("यह एक अच्छा दिन है, with some English words"), "hi")
        self.assertEqual(langid.detect("Mujhe yeh movie bahut pasand aayi"), "hi-Latn")
        self.assertEqual(langid.detect("The weather is nice and we are going to the park"), "en")
        self.assertEqual(langid.detect("1990 45.3 12"), "other")
        self.assertEqual(langid.detect("जैसी करनी वैसी भरनी"), "hi")


class TestContamination(unittest.TestCase):
    def test_cross_script_and_near(self):
        cfg = Config()
        hi = "मैं घर जा रहा हूँ क्योंकि मुझे फिर काम है और बहुत थकान भी है आज रात को जल्दी सोना है"
        item = {"eval_id": "eval-0000", "lang": "hi", "text": hi}
        idx = ContamIndex([item], cfg)
        doc = lambda t, l: {"text": t, "lang": l, "raw_sha": "x", "key_sha": "y"}
        lat = "main ghar ja raha hoon kyonki mujhe phir kaam hai aur bahut thakan bhi hai aaj raat ko jaldi sona hai"
        hits, _ = idx.scan(doc(lat, "hi-Latn"))
        self.assertEqual([h[1] for h in hits], ["cross_script"])
        hits, _ = idx.scan(doc("पहले कुछ और लिखा था। " + hi + " फिर कुछ और।", "hi"))
        self.assertEqual([h[1] for h in hits], ["near_ngram"])
        hits, _ = idx.scan(doc("आज मौसम अच्छा है और हम सब बाज़ार जा रहे हैं क्योंकि कुछ सामान लेना है", "hi"))
        self.assertEqual(hits, [])


def run_pipe(raw, out, env=None):
    e = dict(os.environ, **(env or {}))
    return subprocess.run([os.path.join(ROOT, "run.sh"), raw, out], env=e, capture_output=True, text=True)


def tree_hash(out):
    h = hashlib.sha256()
    for name in ("clean", "ledger.csv", "eval.jsonl", "contamination.jsonl", "manifest.json"):
        p = os.path.join(out, name)
        files = [os.path.join(p, f) for f in sorted(os.listdir(p))] if os.path.isdir(p) else [p]
        for f in files:
            h.update(os.path.basename(f).encode()); h.update(open(f, "rb").read())
    return h.hexdigest()


class TestEndToEnd(unittest.TestCase):
    def test_deterministic_and_kill_resume(self):
        tmp = tempfile.mkdtemp()
        try:
            raw = os.path.join(tmp, "raw")
            subprocess.check_call([sys.executable, os.path.join(ROOT, "tests", "make_fixture.py"), raw, "300"])
            a, b = os.path.join(tmp, "a"), os.path.join(tmp, "b")
            self.assertEqual(run_pipe(raw, a).returncode, 0)
            killed = run_pipe(raw, b, {"CURATE_CRASH_AT": "150"})     # os._exit(137) mid stage B
            self.assertEqual(killed.returncode, 137)
            self.assertFalse(os.path.exists(os.path.join(b, "ledger.csv")))   # nothing half-published
            self.assertEqual(run_pipe(raw, b).returncode, 0)
            self.assertEqual(tree_hash(a), tree_hash(b))
            ids = [l.split(",")[0] for l in open(os.path.join(a, "ledger.csv"), encoding="utf-8")][1:]
            self.assertEqual(len(ids), len(set(ids)))                          # no duplicated ledger rows
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
