# DECISIONS.md

> **Status: template.** Design decisions below are real (they describe the code). Every `«RUN: …»`
> is a number or example that must come from *your* run on the downloaded data. Command in brackets.
> Delete this box and every unfilled `«RUN»` before submitting; do not invent numbers.

## 1. Sources  `[./run.sh raw out; python scripts/review.py out tables]`
| source | license (verify on card) | docs | bytes |
|---|---|---|---|
| wikipedia_hi (`wikimedia/wikipedia` 20231101.hi) | CC BY-SA 3.0 / GFDL | «RUN» | «RUN» |
| fineweb2_hin_Deva (`HuggingFaceFW/fineweb-2`) | ODC-By 1.0 + CC ToU | «RUN» | «RUN» |
| fineweb2_hin_Latn (same dataset) | ODC-By 1.0 + CC ToU | «RUN» | «RUN» |
- Hinglish: FineWeb-2's `hin_Latn` subset is romanized-Hindi web text. Its source labels are not trusted; my own langid decides (see §2). «RUN: how many of its docs I label hi-Latn vs en/other»
- Download dates are in `raw/SOURCES.json` and `manifest.json`.

## 2. Funnel  `[python scripts/review.py out tables]`
«RUN: paste the per-language funnel table (in → ingest → normalize → langid → quality → eval_holdout → contamination → exact_dedup → near_dedup).»
- Skipped at ingest (malformed JSON / bad bytes / no text field): «RUN: from `ingest_counters`».
- Langid is script + lexicon based (no model): Devanagari share ≥ 0.35 of letters → `hi`; Latin → `hi-Latn` only if ≥ 10% of tokens are unambiguous romanized-Hindi function words (words that are also English, like *main, par, to, me*, are excluded). Known limit: Marathi/Nepali/Sanskrit are Devanagari and land in `hi`. Docs with no letters (pure number tables) get `other` and are dropped at the langid stage by design (no linguistic signal); I judged them useless for an LM corpus rather than "unusual but legitimate".

## 3. Near-duplicates  `[python scripts/review.py out hist; … pairs --lo 0.7 --hi 0.9 -n 3]`
- Method: word 3-gram shingles on the aggressive dedup key → 128-perm MinHash → 16 bands × 8 rows (S-curve midpoint ≈ 0.71) → candidates verified by estimated Jaccard ≥ **0.80**. Docs with < 8 tokens are exact-dedup only (templated one-liners would otherwise collide). First-seen in sorted file order is kept, so `dup_of` always points at a kept doc.
- How 0.80 was chosen: «RUN: describe the histogram from `hist` and what you read at 0.70/0.75/0.80/0.85; adjust `--near-threshold` if your reading differs. Default 0.80 is a starting point, not a conclusion.»
- Three pairs near the threshold and my call: «RUN: paste three from `pairs`, state keep/drop and why (e.g. same article + one appended paragraph → distinct content or true near-dup?).»

## 4. Filters: false positives  `[python scripts/review.py out drops <reason> -n 10]`
Deliberate exemptions: short texts (min 8 non-space chars, so proverbs survive), poem-like docs (≥4 lines, avg line < 60 chars) skip the line-repeat/boilerplate-strip rules, digit-heavy docs (≥30% digits) skip repetition/symbol rules.
Known cost I already saw on the synthetic fixture: a clean sentence wrapped in heavy HTML is dropped as `markup_heavy` (tag chars > 20%) rather than salvaged.
«RUN: three real docs that were wrongly dropped, with reason + the rule/threshold you'd change; or an argument that you found none after sampling N per reason.»

## 5. Contamination  `[python scripts/review.py out contam]`
- Eval set: «RUN: n» items (150 Devanagari + 50 Hinglish target), chosen by `sha1(seed:id)` priority from docs that passed all stage-A filters, 80–600 chars, ≥ 15 tokens, distinct from each other. Held out **before** dedup, so they never enter training. Measures: language-model perplexity / continuation fluency on clean in-distribution Hindi and Hinglish (not knowledge or reasoning).
- Checks against every other doc: (1) exact raw copy; (2) equal after normalization key; (3) word-5-gram overlap ≥ 50% of the eval item's n-grams (catches copies inside longer docs); (4) cross-script: Devanagari ↔ Latin compared on a vowel-less consonant skeleton (है/hai → h, घर/ghar → gr), 4-gram overlap ≥ 60%.
- Result: «RUN: items affected, train docs removed, split by method (`contamination.jsonl`).»
- A rejected candidate: «RUN: top item from `contam` near-misses, its score, why it is a different text.»
- Limits: skeleton matching is a crude candidate generator, not a transliterator; paraphrases/translations are not detected.

## 6. Reproducibility
- `manifest.json` holds sha256 of every raw file, all thresholds, a hash of the code, and the sha256 of each output shard. `raw/SOURCES.json` + `raw/checksums.txt` come from `download.sh`.
- Rebuild = same git commit + same raw files (check checksums) + `./run.sh raw out`. No randomness except seeded hashes; no Python `hash()`; gzip mtime = 0; processing order = sorted path, record index. Test: `tests/test_pipeline.py` kills a run mid-way (exit 137), reruns, and asserts byte-identical output to an uninterrupted run and no duplicated ledger ids.
- Stage-A shards are cached by (input sha256, config+code signature), so editing a filter automatically recomputes. Final outputs are built in `_build/` and swapped in last.
- Upstream datasets are moving targets: pin the HF revision (commit hash) in `download.py` before the final run. «RUN/TODO»

## 7. Scale (2 TB on object storage)
First thing to break is stage B's single process holding global state: the exact-hash dict, the LSH tables + 128×uint32 signatures per kept doc (~0.5 KB/doc → hundreds of GB for ~10⁹ docs), and its strictly sequential order (which is what makes dedup deterministic). Stage A also treats a file as the unit of retry, so one 50 GB shard that dies loses everything. Fix: chunk A by ~100 MB with per-chunk checkpoints on S3; do exact dedup by hash-partitioned shuffle (key → shard, keep min id); run LSH by band-partitioned shuffle + connected components (union-find) instead of an in-memory index; run contamination as a join of eval n-grams against the corpus. Determinism is kept by choosing canonical docs as min(doc id) per component rather than "first seen".

## 8. Wrap-up
Not done, in priority order: «RUN/EDIT — e.g. 1. classifier-based quality scoring; 2. real Marathi/Nepali split in langid; 3. semantic dedup with embeddings; 4. per-source threshold tuning; 5. chunked stage A».
Time spent: «RUN: honest hours».
