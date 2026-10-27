"""Helpers for writing DECISIONS.md from a finished run.
  python scripts/review.py <out_dir> pairs [--lo 0.70 --hi 0.90 -n 3]   near-dup pairs around the threshold
  python scripts/review.py <out_dir> hist                               histogram of candidate-pair similarity
  python scripts/review.py <out_dir> drops <reason> [-n 10]             sampled dropped docs for a filter reason
  python scripts/review.py <out_dir> adult --raw raw --source wikipedia_hi -n 7   explicit terms behind adult drops, in context\n  python scripts/review.py <out_dir> leaks                               each contamination hit with eval text + matching doc\n  python scripts/review.py <out_dir> contam                             leak summary + rejected near-misses
  python scripts/review.py <out_dir> sample [--rows 1000] -o sample.jsonl   random cleaned sample (seeded)
  python scripts/review.py <out_dir> tables                              markdown funnel/sources/drop-reason tables"""
import argparse, csv, gzip, json, os, random, sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from curate.pipeline import read_shards


def metas(out):
    work = os.path.join(out, "_work")
    ms = [json.load(open(os.path.join(work, f))) for f in sorted(os.listdir(work)) if f.endswith(".meta.json")]
    return work, sorted(ms, key=lambda m: m["relpath"])


def text_index(out, wanted):
    work, ms = metas(out); found = {}
    for r in read_shards(work, ms):
        if r["id"] in wanted:
            found[r["id"]] = r.get("text") or r.get("snippet", "")
    return found


def ledger(out):
    with open(os.path.join(out, "ledger.csv"), encoding="utf-8") as f:
        yield from csv.DictReader(f)


def jl(path):
    return [json.loads(l) for l in open(path, encoding="utf-8")] if os.path.exists(path) else []


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("out"); ap.add_argument("cmd")
    ap.add_argument("arg", nargs="?"); ap.add_argument("-n", type=int, default=3)
    ap.add_argument("--lo", type=float, default=0.70); ap.add_argument("--hi", type=float, default=0.90)
    ap.add_argument("-o", default="sample.jsonl"); ap.add_argument("--rows", type=int, default=1000)
    ap.add_argument("--raw", default="raw"); ap.add_argument("--source", default="")
    a = ap.parse_args()
    if a.cmd == "pairs":
        pairs = [(r["dup_of"], r["id"], float(r["sim"])) for r in ledger(a.out) if r["stage"] == "near_dedup"]
        pairs += [(p["a"], p["b"], p["sim"]) for p in jl(os.path.join(a.out, "_work", "near_miss.jsonl"))]
        pairs = sorted((p for p in pairs if a.lo <= p[2] <= a.hi), key=lambda p: p[2])
        step = max(1, len(pairs) // a.n); pick = pairs[::step][:a.n]
        txt = text_index(a.out, {x for p in pick for x in p[:2]})
        for x, y, s in pick:
            print(f"--- sim={s}\nA[{x}]: {txt[x][:300]}\nB[{y}]: {txt[y][:300]}\n")
    elif a.cmd == "hist":
        sims = [float(r["sim"]) for r in ledger(a.out) if r["stage"] == "near_dedup"]
        sims += [p["sim"] for p in jl(os.path.join(a.out, "_work", "near_miss.jsonl"))]
        c = Counter(int(s * 20) / 20 for s in sims)
        for k in sorted(c):
            print(f"{k:.2f}-{k+0.05:.2f} {'#' * min(80, c[k])} {c[k]}")
    elif a.cmd == "drops":
        ids = [r["id"] for r in ledger(a.out) if r["reason"] == a.arg]
        random.Random(0).shuffle(ids); ids = ids[:max(a.n, 3) * 3]
        txt = text_index(a.out, set(ids))
        print(f"{len(ids)} sampled of reason={a.arg}")
        for i in ids[:max(a.n, 3)]:
            print(f"[{i}] {txt[i][:300]!r}\n")
    elif a.cmd == "contam":
        c = jl(os.path.join(a.out, "contamination.jsonl"))
        print("leaking eval items:", len(c), Counter(x["method"] for x in c))
        miss = sorted(jl(os.path.join(a.out, "_work", "contam_near_miss.jsonl")), key=lambda x: -x["score"])[:a.n]
        ev = {e["eval_id"]: e["text"] for e in jl(os.path.join(a.out, "eval.jsonl"))}
        txt = text_index(a.out, {m["doc_id"] for m in miss})
        for m in miss:
            print(f"--- rejected: {m['method']} score={m['score']}\nEVAL: {ev[m['eval_id']][:250]}\nDOC : {txt[m['doc_id']][:250]}\n")
    elif a.cmd == "adult":                      # which explicit terms triggered adult_content drops, in context
        from curate import ingest, quality, textnorm
        ids = {r["id"] for r in ledger(a.out) if r["reason"] == "adult_content" and (not a.source or r["source"] == a.source)}
        shown = 0
        for rel, full in ingest.list_files(a.raw):
            for idx, text, err in ingest.iter_records(full):
                if text and ingest.doc_id(rel, idx) in ids and shown < max(a.n, 3):
                    t = textnorm.normalize(text)[0]
                    pats = [("S", quality._STRONG_LAT), ("S", quality._STRONG_DEV), ("m", quality._MED_LAT), ("w", quality._WEAK_LAT), ("w", quality._WEAK_DEV)]
                    ms = sorted((m.start(), k, m.group(0)) for k, rx in pats for m in rx.finditer(t))
                    s_n = sum(k == "S" for _, k, _ in ms); m_n = sum(k == "m" for _, k, _ in ms)
                    print(f"--- {rel} #{idx}  strong={s_n} medium={m_n} weak={len(ms) - s_n - m_n} tokens={len(t.split())}  title/start: {t[:70]!r}")
                    for pos, k, w in ms[:3]:
                        print(f"    [{k}] {w!r}: ...{t[max(0, pos - 45):pos + 35]!r}")
                    shown += 1
        print(f"({len(ids)} adult_content drops for source={a.source or 'ALL'})")
    elif a.cmd == "leaks":                      # every contamination hit: is it a real copy or just a shared template?
        ev = {e["eval_id"]: e["text"] for e in jl(os.path.join(a.out, "eval.jsonl"))}
        rows = jl(os.path.join(a.out, "contamination.jsonl"))
        txt = text_index(a.out, {d["id"] for r in rows for d in r["details"]})
        for r in rows:
            print(f"=== {r['eval_id']} ({r['method']})\nEVAL: {ev[r['eval_id']][:160]!r}")
            for d in r["details"][:3]:
                print(f"  -> {d['method']} score={d['score']}  DOC: {txt[d['id']][:160]!r}")
    elif a.cmd == "tables":
        m = json.load(open(os.path.join(a.out, "manifest.json")))
        stages = ["in", "after_ingest", "after_normalize", "after_langid", "after_quality", "after_eval_holdout",
                  "after_contamination", "after_exact_dedup", "after_near_dedup"]
        print("| lang | " + " | ".join(stages) + " |\n|" + "---|" * (len(stages) + 1))
        for lang, row in m["funnel_by_lang"].items():
            print(f"| {lang} | " + " | ".join(str(row[s]) for s in stages) + " |")
        print("\n| source file | records | bytes |\n|---|---|---|")
        for i in m["inputs"]:
            print(f"| {i['path']} | {i['records']} | {i['bytes']} |")
        print("\n| stage/reason | docs |\n|---|---|")
        for k, v in m["drop_reasons"].items():
            print(f"| {k} | {v} |")
        print("\nPII:", m["pii_redactions"], " ingest:", m["ingest_counters"])
    elif a.cmd == "sample":
        rows = []
        for p in sorted(os.listdir(os.path.join(a.out, "clean"))):
            with gzip.open(os.path.join(a.out, "clean", p), "rt", encoding="utf-8") as f:
                rows += [l for l in f]
        random.Random(0).shuffle(rows)
        with open(a.o, "w", encoding="utf-8") as f:
            f.writelines(rows[:a.rows])


if __name__ == "__main__":
    main()
