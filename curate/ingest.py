"""Streaming readers. Every reader yields (index, text|None, error|None); index is the
0-based record position in the file, so document ids are stable and independent of filtering.
Malformed records are yielded as errors (never raised) so the caller can count and ledger them."""
import csv, gzip, hashlib, io, json, os, sys

EXTS = (".jsonl", ".ndjson", ".json", ".csv", ".tsv", ".txt", ".parquet")
TEXT_KEYS = ("text", "content", "body", "document", "raw_content", "sentence", "paragraph", "article", "review", "comment", "tweet", "post")
SKIP_NAMES = {"SOURCES.json", "SOURCES.md", "MANIFEST.json", "checksums.txt"}
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def list_files(raw_dir):
    out = []
    for root, dirs, files in os.walk(raw_dir):
        dirs[:] = sorted(d for d in dirs if not d.startswith((".", "_")))
        for f in sorted(files):
            base = f[:-3] if f.endswith(".gz") else f
            if f.startswith(".") or f in SKIP_NAMES or not base.lower().endswith(EXTS):
                continue
            full = os.path.join(root, f)
            out.append((os.path.relpath(full, raw_dir).replace(os.sep, "/"), full))
    return sorted(out)


def source_of(relpath):
    parts = relpath.split("/")
    return parts[0] if len(parts) > 1 else parts[0].split(".")[0]


def doc_id(relpath, idx):
    return hashlib.sha1(f"{relpath}\x00{idx}".encode()).hexdigest()[:16]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _open(path):
    return gzip.open(path, "rb") if path.endswith(".gz") else open(path, "rb")


def _pick_text(obj, forced):
    if isinstance(obj, str):
        return obj, None
    if not isinstance(obj, dict):
        return None, "not_a_record"
    if forced:
        v = obj.get(forced)
        return (v, None) if isinstance(v, str) else (None, "no_text_field")
    for k in TEXT_KEYS:
        if isinstance(obj.get(k), str):
            return obj[k], None
    strs = [v for v in obj.values() if isinstance(v, str)]
    if strs:
        return max(strs, key=len), None
    return None, "no_text_field"


def _decode(b):
    try:
        return b.decode("utf-8-sig"), None
    except UnicodeDecodeError:
        return None, "bad_encoding"


def _iter_jsonl(path, forced):
    with _open(path) as fh:
        idx = 0
        for line in fh:
            if not line.strip():
                continue
            s, err = _decode(line)
            if err:
                yield idx, None, err
            else:
                try:
                    text, err = _pick_text(json.loads(s), forced)
                    yield idx, text, err
                except (json.JSONDecodeError, RecursionError):
                    yield idx, None, "malformed_json"
            idx += 1


def _iter_csv(path, forced):
    delim = "\t" if ".tsv" in path else ","
    with _open(path) as fh:
        txt = io.TextIOWrapper(fh, encoding="utf-8-sig", errors="strict", newline="")
        rd = csv.DictReader(txt, delimiter=delim)
        idx = 0
        while True:
            try:
                row = next(rd)
            except StopIteration:
                return
            except csv.Error:
                yield idx, None, "malformed_csv"; idx += 1; continue
            except UnicodeDecodeError:
                yield idx, None, "bad_encoding"; return
            text, err = _pick_text(row, forced)
            yield idx, text, err
            idx += 1


def _iter_txt(path, forced):
    """Blank-line separated blocks = documents."""
    with _open(path) as fh:
        idx, buf = 0, []
        for line in fh:
            s, err = _decode(line)
            if err:
                buf = None if buf is None else buf
                yield idx, None, err; idx += 1; continue
            if s.strip() == "":
                if buf:
                    yield idx, "\n".join(buf), None; idx += 1
                buf = []
            else:
                buf.append(s.rstrip("\r\n"))
        if buf:
            yield idx, "\n".join(buf), None


def _iter_parquet(path, forced):
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(path)
    names = pf.schema_arrow.names
    col = forced if forced in names else next((k for k in TEXT_KEYS if k in names), None)
    if col is None:
        col = next((f.name for f in pf.schema_arrow if str(f.type) in ("string", "large_string")), None)
    idx = 0
    for batch in pf.iter_batches(batch_size=1000, columns=[col] if col else None):
        for v in batch.column(0).to_pylist() if col else []:
            yield idx, (v if isinstance(v, str) else None), (None if isinstance(v, str) else "no_text_field")
            idx += 1


def iter_records(path, forced=""):
    base = path[:-3] if path.endswith(".gz") else path
    ext = os.path.splitext(base.lower())[1]
    if ext in (".jsonl", ".ndjson", ".json"):
        return _iter_jsonl(path, forced)
    if ext in (".csv", ".tsv"):
        return _iter_csv(path, forced)
    if ext == ".parquet":
        return _iter_parquet(path, forced)
    return _iter_txt(path, forced)
