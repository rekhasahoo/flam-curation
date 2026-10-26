# Indic corpus curation (Hindi + Hinglish)

    ./download.sh raw                 # network; writes raw/<source>/*.jsonl.gz + SOURCES.json + checksums
    ./run.sh raw out                  # offline; python3 + numpy (+ pyarrow for .parquet input)
    python scripts/review.py out tables|hist|pairs|drops <reason>|contam|sample   # evidence for DECISIONS.md
    python3 -m unittest discover -s tests -v

Outputs in `out/`: `clean/part-*.jsonl.gz` (id,text,lang,source), `ledger.csv`, `eval.jsonl`,
`contamination.jsonl`, `manifest.json`. `out/_work/` = cache + diagnostics (safe to delete).

Pipeline: read(stream) → normalize → langid → quality → PII → [eval hold-out → contamination scan → exact dedup → near dedup].
Input formats: jsonl/ndjson/json-lines, csv/tsv, txt (blank-line separated docs), parquet; each optionally `.gz`.
Source name = first sub-directory of raw_dir (or file stem). Override the text column with `--text-field`.
Every threshold is a CLI flag (`./run.sh raw out --near-threshold 0.85`); see `curate/config.py`.
