"""Regression tests for filter decisions found by reading real data (see DECISIONS.md section 4)."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from curate import quality, textnorm
from curate.config import Config

CFG = Config()


BALANCED = Config(adult_policy="balanced")


def verdict(t, cfg=CFG):
    t2, flags = textnorm.normalize(t)
    return quality.check(t2, flags, cfg)[1]


class TestKeepsLegitimateTails(unittest.TestCase):
    def test_short_wikipedia_stub_with_repeated_function_word(self):
        # 'के' is >30% of this 11-token stub; it was dropped as 'repetitive' before the fix
        self.assertIsNone(verdict("महाभारत के पश्चात के मगध वंश के राजा।\n\nमगधवंश के राजा"))

    def test_list_of_names_with_empty_parentheses(self):
        self.assertIsNone(verdict("यह महिला टेनिस खिलाडियों की सूची है।\n\n" + "\n".join(f"नाम{c} ()" for c in "अबसदफगहजकलमन")))

    def test_proverb_poem_table(self):
        self.assertIsNone(verdict("जैसी करनी वैसी भरनी"))
        self.assertIsNone(verdict("सुबह की किरणें आईं,\nकलियाँ खिल गईं,\nचिड़िया गीत गाईं,\nसुबह की किरणें आईं,\nहवा मुस्काई।"))

    def test_words_that_contain_explicit_substrings(self):
        self.assertIsNone(verdict("अर्जुन ने गांडीव धनुष उठाया और लंडन की यात्रा पर निकल पड़ा, वहाँ उसने बहुत कुछ देखा और सीखा।"))
        self.assertIsNone(verdict("The sex ratio of the district is 940 females per 1000 males, and the literacy rate is 74 percent."))

    def test_chod_is_ambiguous_and_not_flagged(self):
        self.assertIsNone(verdict("Maine woh purana ghar chod diya aur ab nayi jagah par rehta hoon, yahan sab kuch bahut accha hai."))


class TestAdultTiers(unittest.TestCase):
    @staticmethod
    def filler(tag, n=300):
        return " ".join(f"baat{tag}{i}" for i in range(n))                  # non-repetitive Latin text

    def test_long_story_with_sparse_strong_terms_is_dropped(self):
        # ~0.7% density: below the old 1% rule, which let these through
        f = self.filler
        doc = f("a") + " usne lund pakda " + f("b") + " boobs dabaye " + f("c") + " lund chut " + f("d")
        self.assertEqual(verdict(doc), "adult_content")

    def test_innocent_look_alikes_survive(self):
        for w in ("chutkara", "chutki", "chuttiyon", "Achuthanandan", "chute-chute"):
            f = self.filler
            self.assertIsNone(verdict(f("a") + f" {w} " + f("b") + f" {w} " + f("c") + f" {w} " + f("d")), w)

    def test_single_ambiguous_chut_is_kept(self):
        self.assertIsNone(verdict(self.filler("a") + " is offer par 10 percent chut milegi " + self.filler("b")))


class TestDevanagariWordBoundaries(unittest.TestCase):
    """Real false positives from wikipedia_hi: loanwords that merely CONTAIN an explicit-term substring."""
    def test_place_names_calendar_sensex_survive(self):
        doc = ("युगांडा पूर्वी अफ्रीका का देश है। युगांडा की राजधानी कम्पाला है। बुगांडा राजशाही से नाम लिया गया। "
               "स्कॉटलंड का राजा डंकन। ग्रेगोरी कैलंडर के अनुसार वर्ष का दिन। सेंसेक्स में आज भारी गिरावट आई। युगाण्डा में हुए परीक्षण।")
        self.assertIsNone(verdict(doc))

    MUSEUM = ("मुंबई में सेक्स और उससे संबंधित विषयों के बारे में जानकारी बढ़ाने के लिए भारत का पहला सेक्स संग्रहालय है। "
              "इस संग्रहालय में सेक्स के बारे में भारत की प्राचीन परंपराओं को दिखाया गया है।")

    def test_balanced_policy_keeps_sex_education_style_text(self):    # weak terms alone never drop a doc
        self.assertIsNone(verdict(self.MUSEUM, BALANCED))

    def test_strict_policy_removes_it(self):                           # the default: sexual content goes
        self.assertEqual(verdict(self.MUSEUM), "adult_content")

    def test_strict_still_ignores_single_mentions_and_lookalikes(self):
        self.assertIsNone(verdict("The sex ratio in the district improved this year according to the latest census report published by the state."))
        self.assertIsNone(verdict("सेंसेक्स में आज भारी गिरावट आई और निवेशकों ने बाजार से दूरी बनाई, सेंसेक्स 500 अंक नीचे बंद हुआ।"))
        self.assertIsNone(verdict("This article mentions sex once in a long and otherwise harmless paragraph about demographic changes across the country."))

    def test_devanagari_whole_word_matches_still_drop(self):
        self.assertEqual(verdict("वहां तेरे पापा हाथ में लंड लिये तेरी चूत और गांड मारने का मन बना चुके थे"), "adult_content")


class TestSexMeaningGender(unittest.TestCase):
    """'sex' as gender must never count, even many times, under the strict policy."""
    def test_gender_sense_survives_even_when_frequent(self):
        f = TestAdultTiers.filler
        for gender_text in (
            "The sex ratio was 940. Sex ratio improved. The sex-ratio at birth and sex ratio in cities were reported.",
            "Data are disaggregated by sex. Counts by sex and by sex again; also age and sex, and age, sex of respondents.",
            "Same-sex marriage was debated; same sex couples, opposite sex partners and either sex were mentioned.",
            "Sex: Male\nSex: Female\nSex - F\nSex discrimination and sex determination were examined in sex-wise tables.",
            "Both sexes were included; male sex and female sex hormones; sex chromosomes and sex differences were compared.",
        ):
            self.assertIsNone(verdict(f("a", 60) + " " + gender_text + " " + f("b", 60)), gender_text[:30])

    def test_hindi_sex_ratio_survives(self):
        self.assertIsNone(verdict("जिले में सेक्स रेशियो 940 रहा। सेक्स रेशियो में सुधार हुआ और सेक्स रेशियो राज्य औसत से बेहतर रहा। " + TestAdultTiers.filler("a", 60)))

    def test_sexual_sense_still_counts(self):
        f = TestAdultTiers.filler
        self.assertEqual(verdict(f("a", 60) + " they have sex. oral sex, sex life and sex scandal " + f("b", 60)), "adult_content")

    def test_place_names_containing_sex(self):
        f = TestAdultTiers.filler
        self.assertIsNone(verdict(f("a", 60) + " Essex, Sussex, Middlesex and Wessex are English counties; Essex again. " + f("b", 60)))


class TestMediumTier(unittest.TestCase):
    def test_repeated_medium_terms_count_as_strong(self):
        f = TestAdultTiers.filler
        self.assertEqual(verdict(f("a") + " chut " + f("b") + " chut " + f("c") + " chut " + f("d")), "adult_content")

    def test_two_strong_terms_in_a_short_text(self):
        self.assertEqual(verdict("Madhuri bra panty mein ubhari hui badi gaand aur latakte boobs dikhakar apne fans ko pagal kar rahi hai aaj raat"), "adult_content")


class TestDropsJunk(unittest.TestCase):
    def test_romanized_adult_content(self):
        self.assertEqual(verdict("maine apna lund nikala aur usne chut me sex kiya, boobs dabaye aur wo horny ho gayi bahut maja aaya"), "adult_content")

    def test_real_repetition(self):
        self.assertEqual(verdict("buy now cheap watches " * 30), "repetitive")

    def test_boilerplate_footer_even_if_short_lines(self):
        self.assertEqual(verdict("सर्वाधिकार सुरक्षित\nअधिक पढ़ें\nसब्सक्राइब करें\nविज्ञापन"), "boilerplate")


if __name__ == "__main__":
    unittest.main()
