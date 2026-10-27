"""All tunable knobs in one place. Every value ends up in manifest.json."""
from dataclasses import dataclass, asdict
import hashlib, json, pathlib


@dataclass(frozen=True)
class Config:
    seed: int = 20260101
    keep_langs: tuple = ("hi", "hi-Latn")
    text_field: str = ""            # force a JSON/CSV/parquet column; "" = auto-detect

    # --- quality filters (stage A) ---
    min_chars: int = 8               # visible chars; proverbs are ~15-40
    max_symbol_ratio: float = 0.10   # {}[]<>=\|^~` share of non-space chars
    max_tag_ratio: float = 0.20      # share of chars inside HTML tags -> drop, below -> strip
    max_url_token_ratio: float = 0.30
    min_unique_token_ratio: float = 0.15   # only for docs with >= 30 tokens
    max_top_token_ratio: float = 0.30      # only for docs with >= 10 tokens
    max_boilerplate_line_ratio: float = 0.50
    max_bad_start_ratio: float = 0.20      # words starting with a dependent vowel sign
    min_text_ratio: float = 0.30           # letters / non-space chars (digit-heavy docs exempt)
    max_adult_ratio: float = 0.01          # explicit-term hits / tokens (and >= min_adult_hits)
    min_adult_hits: int = 3
    adult_policy: str = "strict"            # strict: remove sexual content generally; balanced: only explicit/erotic text
    strict_min_hits: int = 3               # strict: this many hits of ANY tier drops a doc (sex-ed, gossip, spam)
    min_adult_strong: int = 3              # this many unambiguous explicit terms => drop, any doc length
    aadhaar_strict: bool = False     # True: 12 digits need Verhoeff checksum or a keyword

    # --- near-dup (MinHash + LSH) ---
    near_threshold: float = 0.80     # est. Jaccard on word shingles; tune with scripts/review.py pairs
    shingle_k: int = 3
    num_perm: int = 128
    lsh_bands: int = 16              # 16 bands x 8 rows -> S-curve midpoint ~0.71
    lsh_rows: int = 8
    near_min_tokens: int = 8         # shorter docs are exact-dedup only
    near_report_min: float = 0.60    # log pairs in [0.60, threshold) to _work/near_miss.jsonl

    # --- eval set + contamination ---
    eval_hi: int = 150
    eval_latn: int = 50
    eval_min_chars: int = 250        # short stubs ('X is a district of Y') make poor eval items
    eval_min_tokens: int = 25
    eval_max_chars: int = 600
    contam_ngram: int = 5            # word n-gram size
    contam_overlap: float = 0.50     # share of an eval item's n-grams found in a train doc
    contam_xscript: float = 0.60     # same, on consonant skeletons (cross-script)
    contam_xscript_ngram: int = 4
    contam_min_ngrams: int = 3
    contam_report_min: float = 0.30  # near misses logged for DECISIONS.md

    shard_size: int = 5000
    workers: int = 1

    def to_dict(self):
        return asdict(self)

    def stage_a_signature(self) -> str:
        """Cache key for per-file shards: stage-A knobs + hash of all code."""
        keys = ["keep_langs", "text_field", "min_chars", "max_symbol_ratio", "max_tag_ratio",
                "max_url_token_ratio", "min_unique_token_ratio", "max_top_token_ratio",
                "max_boilerplate_line_ratio", "max_bad_start_ratio", "min_text_ratio", "aadhaar_strict",
                "max_adult_ratio", "min_adult_hits", "min_adult_strong", "adult_policy", "strict_min_hits"]
        d = {k: getattr(self, k) for k in keys}
        return hashlib.sha256((json.dumps(d, sort_keys=True) + code_hash()).encode()).hexdigest()[:16]


def code_hash() -> str:
    h = hashlib.sha256()
    for p in sorted(pathlib.Path(__file__).parent.glob("*.py")):
        h.update(p.name.encode()); h.update(p.read_bytes())
    return h.hexdigest()[:16]
