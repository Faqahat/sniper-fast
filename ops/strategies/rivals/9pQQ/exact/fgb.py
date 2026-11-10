"""Flattened GBDT evaluator (all trees at once, level by level) for the gbdt_np nested-dict trees."""
import numpy as np
class Flat:
    def __init__(self, m):
        self.names = m["names"]; self.edges = m["edges"]; self.F0 = m["F0"]; self.lr = m["lr"]
        T = m["trees"]; nodes = []
        for t in T:
            arr = []
            def add(n):
                k = len(arr); arr.append(None)
                if "w" in n: arr[k] = (-1, 0, k, k, n["w"])
                else:
                    l = add(n["l"]); r = add(n["r"]); arr[k] = (n["f"], n["b"], l, r, 0.0)
                return k
            add(t); nodes.append(arr)
        N = max(len(a) for a in nodes); nt = len(nodes)
        self.f = np.full((nt, N), -1, np.int32); self.b = np.zeros((nt, N), np.int32); self.l = np.zeros((nt, N), np.int32)
        self.r = np.zeros((nt, N), np.int32); self.v = np.zeros((nt, N))
        for i, a in enumerate(nodes):
            for k, (f, b, l, r, v) in enumerate(a): self.f[i, k] = f; self.b[i, k] = b; self.l[i, k] = l; self.r[i, k] = r; self.v[i, k] = v
        self.depth = 0
        def dep(n): return 0 if "w" in n else 1 + max(dep(n["l"]), dep(n["r"]))
        self.depth = max(dep(t) for t in T)
    def bin_col(self, j, x):
        b = np.searchsorted(self.edges[j], x, side="right") + 1; b[np.isnan(x)] = 0; return b.astype(np.int16)
    def bin(self, X):
        return np.stack([self.bin_col(j, X[:, j]) for j in range(X.shape[1])], 1)
    def margin(self, B):
        n = len(B); nt = self.f.shape[0]; cur = np.zeros((n, nt), np.int32); ti = np.arange(nt)[None, :]
        for _ in range(self.depth):
            f = self.f[ti, cur]; leaf = f < 0
            fb = B[np.arange(n)[:, None], np.maximum(f, 0)]
            go = fb <= self.b[ti, cur]
            nxt = np.where(go, self.l[ti, cur], self.r[ti, cur])
            cur = np.where(leaf, cur, nxt)
        return self.F0 + self.lr * self.v[ti, cur].sum(1)
