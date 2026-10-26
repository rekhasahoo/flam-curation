"""MinHash + banded LSH, numpy-vectorised, deterministic (no Python hash(), seeded params)."""
import hashlib, zlib
import numpy as np

_P = (1 << 61) - 1


class MinHasher:
    def __init__(self, num_perm: int, seed: int):
        def par(tag, i, mod):
            return int.from_bytes(hashlib.blake2b(f"{tag}:{seed}:{i}".encode(), digest_size=8).digest(), "big") % mod
        self.a = np.array([par("a", i, (1 << 31) - 1) + 1 for i in range(num_perm)], dtype=np.uint64)
        self.b = np.array([par("b", i, 1 << 32) for i in range(num_perm)], dtype=np.uint64)

    def signature(self, shingles):
        x = np.fromiter((zlib.crc32(s.encode("utf-8")) for s in shingles), dtype=np.uint64, count=len(shingles))
        h = (x[:, None] * self.a[None, :] + self.b[None, :]) % np.uint64(_P) & np.uint64(0xFFFFFFFF)
        return h.min(axis=0).astype(np.uint32)


def shingles(key: str, k: int):
    toks = key.split()
    if len(toks) <= k:
        return {" ".join(toks)} if toks else set()
    return {" ".join(toks[i:i + k]) for i in range(len(toks) - k + 1)}


def est_jaccard(s1, s2) -> float:
    return float((s1 == s2).mean())


class LSH:
    """Insert only *kept* docs, so every dup_of points at a kept document."""
    def __init__(self, bands, rows):
        self.bands, self.rows = bands, rows
        self.tables = [dict() for _ in range(bands)]
        self.sigs, self.ids = [], []

    def _keys(self, sig):
        return [sig[i * self.rows:(i + 1) * self.rows].tobytes() for i in range(self.bands)]

    def query(self, sig):
        cands = set()
        for t, k in zip(self.tables, self._keys(sig)):
            cands.update(t.get(k, ()))
        return sorted(cands)               # sorted => deterministic tie-breaks

    def best(self, sig):
        best, bj = None, 0.0
        for c in self.query(sig):
            j = est_jaccard(sig, self.sigs[c])
            if j > bj:
                best, bj = c, j
        return (self.ids[best] if best is not None else None), bj

    def near(self, sig, lo):
        return [(self.ids[c], est_jaccard(sig, self.sigs[c])) for c in self.query(sig)
                if est_jaccard(sig, self.sigs[c]) >= lo]

    def add(self, doc_id, sig):
        n = len(self.sigs)
        self.sigs.append(sig); self.ids.append(doc_id)
        for t, k in zip(self.tables, self._keys(sig)):
            t.setdefault(k, []).append(n)
