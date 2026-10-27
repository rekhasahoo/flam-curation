# DECISIONS.md

## 1. Sources

| Source | License (verify dataset card) | Records downloaded | Bytes |
|---|---|---:|---:|
| `wikipedia_hi` — Wikipedia Hindi, 20231101.hi | CC BY-SA 3.0 / GFDL; verify | 6,000 | 11,210,546 |
| `fineweb2_hin_Deva` — FineWeb-2 | ODC-By 1.0 + CC ToU; verify | 6,000 | 9,576,894 |
| `fineweb2_hin_Latn` — FineWeb-2 | ODC-By 1.0 + CC ToU; verify | 6,000 | 16,971,692 |

FineWeb-2's `hin_Latn` subset contains Romanized Hindi web text, including substantial noise. Upstream labels are not blindly trusted; a script-and-lexicon language identifier assigns the final labels.

## 2. Funnel and language identification

| Language | Input | After quality | After holdout | After contamination | After exact dedup | Final |
|---|---:|---:|---:|---:|---:|---:|
| `hi` | 12,022 | 11,925 | 11,775 | 11,773 | 11,418 | 11,363 |
| `hi-Latn` | 5,946 | 3,579 | 3,529 | 3,523 | 3,523 | 3,522 |
| `en` | 24 | 0 | 0 | 0 | 0 | 0 |
| `other` | 8 | 0 | 0 | 0 | 0 | 0 |

Final corpus: **14,885 documents** — 11,363 Hindi and 3,522 Romanized Hindi, approximately 3.23:1. The language identifier retained all 12,022 Devanagari-labelled Hindi records and all 5,946 Latin-script Hindi candidates at its stage. The 24 English-labelled and 8 other-language records were rejected.

Language identification is heuristic, not model-based: Devanagari letter share ≥35% gives `hi`; Latin text is classified as `hi-Latn` only when ≥10% of tokens are unambiguous Romanized Hindi function words. Words shared with English are excluded. Known limitations include Marathi, Nepali, and Sanskrit being classified as Hindi, and Hindi stubs containing English bibliographies being falsely rejected.

The quality stage removed 2,207 documents as `adult_content`, plus 231 spam, 15 garbled-encoding, 6 repetitive, 4 boilerplate, and 1 markup-heavy document. Strict adult-content filtering is intentional; its cost is losing legitimate sexual-health and sex-education material. Gender-related uses of “sex” should remain eligible. This policy requires contextual false-positive testing.

## 3. Near-duplicates

Deduplication uses word 3-gram shingles on an aggressive normalized key, 128-permutation MinHash, and 16 bands × 8 rows. Candidates are verified at estimated Jaccard similarity ≥0.80. Documents under eight tokens receive exact deduplication only. First-seen records in sorted file order are retained.

The similarity histogram shows 58 pairs in 0.60–0.65, 46 in 0.65–0.70, 46 in 0.70–0.75, 40 in 0.75–0.80, 20 in 0.80–0.85, 15 in 0.85–0.90, 20 in 0.90–0.95, and 1 in 0.95–1.00.

Three reviewed pairs near the threshold scored 0.781, 0.797, and 0.820. They describe different Indian districts or towns using similar encyclopedia templates. Shared structure alone is insufficient to establish duplicate content, so these are reasonable near-miss examples to retain rather than merge. The chosen threshold is a practical compromise, not a guarantee of semantic equivalence.

The final run removed 355 exact duplicates and 56 near-duplicates.

## 4. Quality-filter decisions

The content policy rejects explicit sexual narratives and pornographic material, while allowing legitimate educational or medical material where possible. The observed 2,207 adult-content drops are a significant source of corpus reduction, particularly in `fineweb2_hin_Latn` (2,130 drops), compared with `fineweb2_hin_Deva` (73) and `wikipedia_hi` (4).

Other deliberate exemptions include short texts (minimum eight non-space characters), poem-like documents (at least four lines, average line under 60 characters), and digit-heavy documents (at least 30% digits), which bypass selected repetition or symbol rules.

Known limitations and debugging observations: repetitive Hindi constructions can trigger false positives; substring-based rules can match words such as Uganda, Scotland, and Sensex incorrectly. A clean sentence wrapped in heavy HTML can be rejected as `markup_heavy`. These cases motivate boundary-aware matching, context-sensitive rules, and manual false-positive review rather than indiscriminately lowering thresholds.

## 5. Evaluation holdout and contamination

The held-out evaluation set contains 200 items: 150 Devanagari Hindi and 50 Romanized Hindi targets. Items are selected deterministically by seeded hash priority from eligible documents and held out before deduplication. The intended evaluation measures language-model perplexity and continuation fluency on clean, in-distribution Indic text, not knowledge or reasoning.

Contamination checks cover exact copies, normalized-key matches, word 5-gram overlap, and cross-script consonant-skeleton overlap. The final manifest reports **4 affected evaluation items and 8 training documents removed for contamination**. The diagnostic shows three affected items with `near_ngram` matches and one with a `cross_script` match. The tables report seven near-ngram and one cross-script training-side removal events.

One rejected near-miss scored 0.404 and compared hotel descriptions for different properties and locations. Similar boilerplate wording is not sufficient evidence of evaluation leakage; the underlying content differs.

Limitations: consonant-skeleton matching is a crude cross-script candidate generator, not a transliterator. Paraphrases and translations can remain undetected.

## 6. Reproducibility

`raw/checksums.txt` records checksums for downloaded source files. `manifest.json` records output statistics, PII detections, evaluation results, and pipeline metadata. Rebuild using the same code revision and raw inputs:

`./run.sh raw out`

The pipeline is designed for deterministic ordering, seeded selection, and reproducible outputs. Tests exercise interruption and restart behavior.

Dataset revisions observed on 27 October 2026:

- `wikimedia/wikipedia`: `b04c8d1ceb2f5cd4588862100d08de323dccfbaa`
- `HuggingFaceFW/fineweb-2`: `af9c13333eb981300149d5ca60a8e9d659b276b9`

Confirm that these exact revisions are pinned in the downloader and recorded in `raw/SOURCES.json`; recording a revision after downloading does not retroactively pin the download. Verify licenses and terms on the dataset cards. Raw checksums identify the actual downloaded bytes and should be checked before rebuilding.

## 7. Scale to 2 TB

The first bottleneck is stage B's global in-memory state: exact-hash indexes, LSH tables, signatures, and sequential deduplication. Stage A also retries whole files instead of smaller chunks.

For object storage, split stage A into approximately 100 MB checkpointed chunks. Use hash-partitioned shuffles for exact deduplication and band-partitioned candidate generation for near-deduplication, followed by deterministic component resolution. Run evaluation contamination checks as joins over evaluation n-grams. Choose canonical documents deterministically rather than relying on processing order.

## 8. Wrap-up

Completed: ingestion, normalization, language identification, quality filtering, evaluation holdout creation, contamination checks, exact and near-deduplication, source checksums, and output inspection.

Remaining work, in priority order:

1. Improve language identification for Hindi documents containing English bibliographies.
2. Evaluate quality filters, especially adult-content false positives and false negatives.
3. Add classifier-based quality scoring.
4. Investigate semantic deduplication with embeddings.
5. Tune thresholds per source and consider chunked stage-A processing for larger corpora.

**Time spent:** Approximately 3 hours of active work across two days (2 hours on the first day and 1 hour on the second day).

The work covered dataset ingestion, language identification, quality filtering, PII redaction, deduplication, evaluation-set construction, contamination checks, reproducibility validation, and documentation.
