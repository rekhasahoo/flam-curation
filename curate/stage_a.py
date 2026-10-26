"""Stage A: per-file, embarrassingly parallel, cached.
read -> normalize -> langid -> quality -> PII. Output: one shard per input file with a record
for EVERY input document (kept docs carry text; dropped docs carry stage/reason/snippet)."""
import gzip, hashlib, json, os
from collections import Counter

from . import ingest, langid, pii, quality, textnorm
from .config import Config

SNIPPET = 400


def _atomic_write_json_gz(path, rows):
    tmp = path + ".tmp"
    with open(tmp, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        for r in rows:
            gz.write((json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    os.replace(tmp, path)


def process_doc(raw_text, cfg: Config):
    """-> dict(status, stage, reason, lang, text, snippet, pii)"""
    text, flags = textnorm.normalize(raw_text)
    if not text:
        return {"status": "dropped", "stage": "normalize", "reason": "empty", "lang": "unk", "snippet": ""}
    lang = langid.detect(text)
    snip = pii.redact(text[:SNIPPET])[0]
    if lang not in cfg.keep_langs:
        return {"status": "dropped", "stage": "langid", "reason": f"lang_{lang}", "lang": lang, "snippet": snip}
    text, reason = quality.check(text, flags, cfg)
    if reason:
        return {"status": "dropped", "stage": "quality", "reason": reason, "lang": lang, "snippet": snip}
    text, counts = pii.redact(text, cfg.aadhaar_strict)
    return {"status": "ok", "lang": lang, "text": text, "pii": dict(counts),
            "raw_sha": hashlib.sha1(raw_text.encode("utf-8", "surrogatepass")).hexdigest()[:20],
            "key_sha": hashlib.sha1(textnorm.dedup_key(text).encode("utf-8")).hexdigest()[:20]}


def process_file(args):
    relpath, full, work_dir, cfg = args
    sig = cfg.stage_a_signature()
    name = hashlib.sha1(relpath.encode()).hexdigest()[:12]
    shard, meta_p = os.path.join(work_dir, f"A-{name}.jsonl.gz"), os.path.join(work_dir, f"A-{name}.meta.json")
    in_sha = ingest.sha256_file(full)
    if os.path.exists(meta_p) and os.path.exists(shard):
        meta = json.load(open(meta_p))
        if meta.get("input_sha256") == in_sha and meta.get("sig") == sig:
            return meta                                              # cached, skip
    source, counters = ingest.source_of(relpath), Counter()

    def rows():
        for idx, text, err in ingest.iter_records(full, cfg.text_field):
            did = ingest.doc_id(relpath, idx)
            counters["records"] += 1
            if err:
                counters[f"skipped_{err}"] += 1
                yield {"id": did, "source": source, "status": "dropped", "stage": "ingest",
                       "reason": err, "lang": "unk", "snippet": ""}
                continue
            r = process_doc(text, cfg)
            r.update(id=did, source=source)
            if r["status"] == "ok":
                for k, v in r["pii"].items():
                    counters[f"pii_{k}"] += v
            yield r
    _atomic_write_json_gz(shard, rows())
    meta = {"relpath": relpath, "source": source, "input_sha256": in_sha, "bytes": os.path.getsize(full),
            "sig": sig, "shard": os.path.basename(shard), "counters": {k: v for k, v in counters.items() if v}}
    tmp = meta_p + ".tmp"
    json.dump(meta, open(tmp, "w"), sort_keys=True)
    os.replace(tmp, meta_p)                                         # meta last => marks shard complete
    return meta
