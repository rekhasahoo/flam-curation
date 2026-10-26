"""Download raw public data. Needs network + `pip install datasets`. run.sh never calls this.

Rows are written exactly as served (all fields, no cleaning) to raw/<source>/*.jsonl.gz.
Edit N_* via env vars. LICENSES BELOW ARE WHAT THE DATASET CARDS STATED WHEN THIS WAS WRITTEN;
re-check each card before submitting and fix SOURCES.json if anything differs."""
import datetime, gzip, json, os, sys

OUT = sys.argv[1] if len(sys.argv) > 1 else "raw"
N_WIKI = int(os.environ.get("N_WIKI", 6000))
N_DEVA = int(os.environ.get("N_FINEWEB_HIN_DEVA", 6000))
N_LATN = int(os.environ.get("N_FINEWEB_HIN_LATN", 3000))

SOURCES = [
    dict(name="wikipedia_hi", hf="wikimedia/wikipedia", config="20231101.hi", split="train", n=N_WIKI,
         url="https://huggingface.co/datasets/wikimedia/wikipedia", license="CC BY-SA 3.0 / GFDL (Wikipedia text)"),
    dict(name="fineweb2_hin_Deva", hf="HuggingFaceFW/fineweb-2", config="hin_Deva", split="train", n=N_DEVA,
         url="https://huggingface.co/datasets/HuggingFaceFW/fineweb-2", license="ODC-By 1.0 (+ Common Crawl terms of use)"),
    dict(name="fineweb2_hin_Latn", hf="HuggingFaceFW/fineweb-2", config="hin_Latn", split="train", n=N_LATN,
         url="https://huggingface.co/datasets/HuggingFaceFW/fineweb-2", license="ODC-By 1.0 (+ Common Crawl terms of use)"),
]


def main():
    from datasets import load_dataset
    today = datetime.date.today().isoformat()
    meta = []
    for s in SOURCES:
        d = os.path.join(OUT, s["name"]); os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "part-00000.jsonl.gz")
        ds = load_dataset(s["hf"], s["config"], split=s["split"], streaming=True)
        n = 0
        with gzip.open(path, "wt", encoding="utf-8") as f:
            for row in ds:
                f.write(json.dumps(row, ensure_ascii=False) + "\n"); n += 1
                if n >= s["n"]:
                    break
        meta.append({"name": s["name"], "url": s["url"], "hf_dataset": s["hf"], "config": s["config"],
                     "license": s["license"], "downloaded": today, "documents": n,
                     "file": os.path.relpath(path, OUT), "bytes": os.path.getsize(path),
                     "note": "first N rows of the streamed split, rows unmodified"})
        print(s["name"], n, "rows", file=sys.stderr)
    json.dump(meta, open(os.path.join(OUT, "SOURCES.json"), "w"), indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
