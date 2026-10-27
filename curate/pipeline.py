"""Orchestrator.  raw --(stage A, per file, cached)--> shards --(stage B, global, ordered)--> outputs

Stage B passes over the shards in sorted (file, record) order:
  pass 1  choose eval items (deterministic hash priority, per-language quota, eval-internal dedup)
  pass 2  per doc:  eval hold-out -> contamination scan -> exact dedup -> near dedup -> write
Everything is written to <out>/_build and swapped into place at the end, so a killed run can
never leave a half-written final output; rerunning is idempotent.
"""
import csv, gzip, heapq, hashlib, json, os, shutil, time, zlib
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor

from . import ingest, skeleton, stage_a, textnorm
from .config import Config, code_hash
from .minhash import LSH, MinHasher, shingles

STAGES = ["ingest", "normalize", "langid", "quality", "eval_holdout", "contamination", "exact_dedup", "near_dedup"]
LEDGER_COLS = ["id", "source", "lang", "status", "stage", "reason", "dup_of", "sim"]
EVAL_MEASURES = ("Held-out Hindi (Devanagari) and Hinglish passages: measures language-model perplexity / "
                 "continuation fluency on clean, in-distribution Indic text (NOT a knowledge or reasoning benchmark).")


def read_shards(work_dir, metas):
    for m in metas:
        with gzip.open(os.path.join(work_dir, m["shard"]), "rt", encoding="utf-8") as f:
            for line in f:
                yield json.loads(line)


class GzJsonlWriter:
    """Deterministic gzip (mtime=0) jsonl shards of `shard_size` rows."""
    def __init__(self, dirpath, size):
        os.makedirs(dirpath, exist_ok=True)
        self.dir, self.size, self.n, self.part, self.fh, self.files = dirpath, size, 0, 0, None, []

    def write(self, row):
        if self.fh is None or self.n >= self.size:
            self.close()
            p = os.path.join(self.dir, f"part-{self.part:05d}.jsonl.gz"); self.part += 1
            self.fh, self.n = gzip.GzipFile(p, "wb", mtime=0, compresslevel=4), 0
            self.files.append(p)
        self.fh.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")); self.n += 1

    def close(self):
        if self.fh:
            self.fh.close(); self.fh = None


def _sha_file(p):
    return ingest.sha256_file(p)


def _truncate(text, limit):
    if len(text) <= limit:
        return text
    cut = max(text.rfind(c, 0, limit) for c in ("।", ". ", "\n", "? ", "! "))
    return text[:cut + 1].strip() if cut > limit // 2 else text[:limit].rsplit(" ", 1)[0]


# ---------------------------------------------------------------- eval selection
def select_eval(work_dir, metas, cfg, hasher):
    def prio(r):
        return hashlib.sha1(f"{cfg.seed}:{r['id']}".encode()).hexdigest()

    def eligible(lang):
        for r in read_shards(work_dir, metas):
            if r["status"] == "ok" and r["lang"] == lang:
                t = _truncate(r["text"], cfg.eval_max_chars)
                if len(t) >= cfg.eval_min_chars and len(t.split()) >= cfg.eval_min_tokens:
                    yield (prio(r), r["id"], r["source"], r["lang"], t)

    chosen = []
    for lang, n in (("hi", cfg.eval_hi), ("hi-Latn", cfg.eval_latn)):
        lsh, seen, got = LSH(cfg.lsh_bands, cfg.lsh_rows), set(), 0
        for _, did, src, lg, t in heapq.nsmallest(int(n * 1.6) + 5, eligible(lang)):
            key = textnorm.dedup_key(t)
            if key in seen:
                continue
            sig = hasher.signature(list(shingles(key, cfg.shingle_k)))
            if lsh.best(sig)[1] >= cfg.near_threshold:
                continue                                    # eval items must be distinct from each other
            seen.add(key); lsh.add(did, sig); got += 1
            chosen.append({"source_doc_id": did, "source": src, "lang": lg, "text": t})
            if got >= n:
                break
    for i, e in enumerate(chosen):
        e["eval_id"] = f"eval-{i:04d}"
    return chosen


class ContamIndex:
    def __init__(self, items, cfg):
        self.cfg, self.items = cfg, items
        self.raw, self.key = {}, {}
        self.ng, self.ng_n = defaultdict(list), {}
        self.xs, self.xs_n = defaultdict(list), {}
        for i, e in enumerate(items):
            e["raw_sha"] = hashlib.sha1(e["text"].encode()).hexdigest()[:20]
            k = textnorm.dedup_key(e["text"])
            e["key_sha"] = hashlib.sha1(k.encode()).hexdigest()[:20]
            self.raw.setdefault(e["key_sha"], []).append(i)
            grams = self._grams(k.split(), cfg.contam_ngram)
            self.ng_n[i] = len(grams)
            if len(grams) >= cfg.contam_min_ngrams:
                for g in grams:
                    self.ng[g].append(i)
            sk = self._grams(skeleton.skeleton_words(e["text"], e["lang"]), cfg.contam_xscript_ngram)
            self.xs_n[i] = len(sk)
            if len(sk) >= cfg.contam_min_ngrams:
                for g in sk:
                    self.xs[g].append(i)

    @staticmethod
    def _grams(toks, n):
        if len(toks) < n:
            return set()
        return {zlib.crc32(" ".join(toks[i:i + n]).encode()) for i in range(len(toks) - n + 1)}   # 32-bit ids: cheap, deterministic

    def scan(self, doc, key=None):
        """-> list of (eval_idx, method, score) for hits, plus near-misses."""
        cfg, hits, near = self.cfg, {}, []
        for i in self.raw.get(doc["key_sha"], ()):
            hits[i] = ("exact" if self.items[i]["raw_sha"] == doc["raw_sha"] else "normalized", 1.0)
        toks = (key if key is not None else textnorm.dedup_key(doc["text"])).split()
        cnt = Counter(i for g in self._grams(toks, cfg.contam_ngram) for i in self.ng.get(g, ()))
        for i, c in cnt.items():
            s = c / self.ng_n[i]
            if i in hits:
                continue
            if s >= cfg.contam_overlap:
                hits[i] = ("near_ngram", round(s, 3))
            elif s >= cfg.contam_report_min:
                near.append((i, "near_ngram", round(s, 3)))
        # cross-script: only against eval items written in the *other* script
        other = "hi-Latn" if doc["lang"] == "hi" else "hi"
        sk = self._grams(skeleton.skeleton_words(doc["text"], doc["lang"]), cfg.contam_xscript_ngram)
        cx = Counter(i for g in sk for i in self.xs.get(g, ()) if self.items[i]["lang"] == other)
        for i, c in cx.items():
            s = c / self.xs_n[i]
            if i in hits:
                continue
            if s >= cfg.contam_xscript:
                hits[i] = ("cross_script", round(s, 3))
            elif s >= cfg.contam_report_min + 0.1:
                near.append((i, "cross_script", round(s, 3)))
        return [(i, m, s) for i, (m, s) in sorted(hits.items())], near


# ---------------------------------------------------------------- main
def run(raw_dir, out_dir, cfg: Config):
    t0 = time.time()
    work = os.path.join(out_dir, "_work"); build = os.path.join(out_dir, "_build")
    os.makedirs(work, exist_ok=True)
    shutil.rmtree(build, ignore_errors=True); os.makedirs(build)

    files = ingest.list_files(raw_dir)
    if not files:
        raise SystemExit(f"no readable input files in {raw_dir}")
    jobs = [(rel, full, work, cfg) for rel, full in files]
    if cfg.workers > 1:
        with ProcessPoolExecutor(cfg.workers) as ex:
            metas = list(ex.map(stage_a.process_file, jobs))          # map keeps input order
    else:
        metas = [stage_a.process_file(j) for j in jobs]

    hasher = MinHasher(cfg.num_perm, cfg.seed)
    eval_items = select_eval(work, metas, cfg, hasher)
    eval_by_doc = {e["source_doc_id"]: e["eval_id"] for e in eval_items}
    cidx = ContamIndex(eval_items, cfg)

    lsh, exact_seen = LSH(cfg.lsh_bands, cfg.lsh_rows), {}
    contam = defaultdict(list)             # eval idx -> [(train_id, method, score)]
    drop_counts, kept_counts, pii_counts = Counter(), Counter(), Counter()
    reasons = Counter()
    clean = GzJsonlWriter(os.path.join(build, "clean"), cfg.shard_size)
    near_miss_f, contam_near_f = [], []
    crash_at = int(os.environ.get("CURATE_CRASH_AT", "0") or 0)          # test hook: simulate kill -9

    with open(os.path.join(build, "ledger.csv"), "w", newline="", encoding="utf-8") as lf:
        lw = csv.writer(lf); lw.writerow(LEDGER_COLS)

        def ledger(r, status, stage="", reason="", dup_of="", sim=""):
            lw.writerow([r["id"], r["source"], r["lang"], status, stage, reason, dup_of, sim])
            if status == "dropped":
                drop_counts[(r["lang"], stage)] += 1; reasons[(stage, reason)] += 1
            else:
                kept_counts[r["lang"]] += 1

        for n, r in enumerate(read_shards(work, metas)):
            if crash_at and n == crash_at:
                os._exit(137)
            if r["status"] != "ok":
                ledger(r, "dropped", r["stage"], r["reason"]); continue
            for k, v in r.get("pii", {}).items():
                pii_counts[k] += v
            if r["id"] in eval_by_doc:
                ledger(r, "dropped", "eval_holdout", "held_out_for_eval", eval_by_doc[r["id"]]); continue

            key = textnorm.dedup_key(r["text"])             # computed once, shared by contamination + dedup
            hits, near = cidx.scan(r, key)
            for i, m, s in near:
                contam_near_f.append({"eval_id": eval_items[i]["eval_id"], "doc_id": r["id"], "method": m, "score": s})
            if hits:
                for i, m, s in hits:
                    contam[i].append((r["id"], m, s))
                best = hits[0]
                ledger(r, "dropped", "contamination", f"eval_leak:{best[1]}", eval_items[best[0]]["eval_id"], best[2]); continue

            if r["key_sha"] in exact_seen:
                ledger(r, "dropped", "exact_dedup", "exact_duplicate", exact_seen[r["key_sha"]], 1.0); continue
            sig = None
            if len(key.split()) >= cfg.near_min_tokens:
                sig = hasher.signature(list(shingles(key, cfg.shingle_k)))
                for cid, j in lsh.near(sig, cfg.near_report_min):
                    if j < cfg.near_threshold:
                        near_miss_f.append({"a": cid, "b": r["id"], "sim": round(j, 3)})
                cid, j = lsh.best(sig)
                if cid is not None and j >= cfg.near_threshold:
                    ledger(r, "dropped", "near_dedup", "near_duplicate", cid, round(j, 3)); continue
            exact_seen[r["key_sha"]] = r["id"]
            if sig is not None:
                lsh.add(r["id"], sig)
            clean.write({"id": r["id"], "text": r["text"], "lang": r["lang"], "source": r["source"]})
            ledger(r, "kept")
    clean.close()

    with open(os.path.join(build, "eval.jsonl"), "w", encoding="utf-8") as f:
        for e in eval_items:
            f.write(json.dumps({k: e[k] for k in ("eval_id", "lang", "source", "source_doc_id", "text")}, ensure_ascii=False, sort_keys=True) + "\n")
    with open(os.path.join(build, "contamination.jsonl"), "w", encoding="utf-8") as f:
        for i in sorted(contam):
            ids = sorted({t for t, _, _ in contam[i]})
            order = ["exact", "normalized", "near_ngram", "cross_script"]
            method = min((m for _, m, _ in contam[i]), key=order.index)
            f.write(json.dumps({"eval_id": eval_items[i]["eval_id"], "train_ids": ids, "method": method,
                                "details": [{"id": t, "method": m, "score": s} for t, m, s in sorted(contam[i])]},
                               ensure_ascii=False, sort_keys=True) + "\n")
    for name, rows in (("near_miss.jsonl", near_miss_f), ("contam_near_miss.jsonl", contam_near_f)):
        with open(os.path.join(work, name), "w", encoding="utf-8") as f:
            for x in rows:
                f.write(json.dumps(x, sort_keys=True) + "\n")

    manifest = build_manifest(raw_dir, cfg, metas, drop_counts, kept_counts, pii_counts, reasons, eval_items, contam, clean.files)
    with open(os.path.join(build, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True, ensure_ascii=False)

    for name in ("clean", "ledger.csv", "eval.jsonl", "contamination.jsonl", "manifest.json"):
        dst = os.path.join(out_dir, name)
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        elif os.path.exists(dst):
            os.remove(dst)
        os.replace(os.path.join(build, name), dst)
    shutil.rmtree(build, ignore_errors=True)
    open(os.path.join(out_dir, "_SUCCESS"), "w").write(manifest["code_hash"] + "\n")
    return manifest, time.time() - t0


def build_manifest(raw_dir, cfg, metas, drop_counts, kept_counts, pii_counts, reasons, eval_items, contam, clean_files):
    langs = sorted({l for l, _ in drop_counts} | set(kept_counts))
    funnel = {}
    for lang in langs:
        total = kept_counts[lang] + sum(v for (l, _), v in drop_counts.items() if l == lang)
        left, row = total, {"in": total}
        for st in STAGES:
            left -= drop_counts[(lang, st)]
            row[f"after_{st}"] = left
        funnel[lang] = row
    sources_json = os.path.join(raw_dir, "SOURCES.json")
    ingest_totals = Counter()
    for m in metas:
        ingest_totals.update(m["counters"])
    return {
        "code_hash": code_hash(), "config": cfg.to_dict(),
        "sources": json.load(open(sources_json)) if os.path.exists(sources_json) else "no SOURCES.json in raw_dir",
        "inputs": [{"path": m["relpath"], "source": m["source"], "sha256": m["input_sha256"], "bytes": m["bytes"],
                    "records": m["counters"].get("records", 0)} for m in metas],
        "ingest_counters": dict(sorted(ingest_totals.items())),
        "funnel_by_lang": funnel, "kept_by_lang": dict(sorted(kept_counts.items())),
        "drop_reasons": {f"{s}/{r}": v for (s, r), v in sorted(reasons.items())},
        "pii_redactions": dict(sorted(pii_counts.items())),
        "eval": {"n": len(eval_items), "by_lang": dict(Counter(e["lang"] for e in eval_items)),
                 "measures": EVAL_MEASURES, "items_with_leaks": len(contam),
                 "train_docs_removed_for_leaks": len({t for v in contam.values() for t, _, _ in v})},
        "outputs": {os.path.basename(p): _sha_file(p) for p in clean_files},
    }
