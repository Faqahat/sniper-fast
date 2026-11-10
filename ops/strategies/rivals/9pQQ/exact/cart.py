"""numpy CART (binary, weighted gini on quantile-binned features) + rule printing. No sklearn on this box."""
import numpy as np
NB = 64
def binize(X, tr_mask, nb=NB):
    B = np.zeros(X.shape, np.int16); edges = []
    for j in range(X.shape[1]):
        x = X[:, j]; xt = x[tr_mask & ~np.isnan(x)]
        e = np.unique(np.quantile(xt, np.linspace(0, 1, nb)[1:-1])) if len(xt) else np.array([])
        edges.append(e); b = np.searchsorted(e, x, side="right") + 1; b[np.isnan(x)] = 0; B[:, j] = b
    return B, edges
def gini_split(Bm, y, w, rows, feats, min_w):
    best = (0.0, None, None)
    W = w[rows].sum(); P = (w[rows] * y[rows]).sum()
    if W <= 0: return best
    g0 = 2 * P * (W - P) / W
    for f in feats:
        b = Bm[rows, f]
        hw = np.bincount(b, w[rows], NB + 1); hp = np.bincount(b, w[rows] * y[rows], NB + 1)
        cw = np.cumsum(hw)[:-1]; cp = np.cumsum(hp)[:-1]
        rw = W - cw; rp = P - cp
        with np.errstate(divide="ignore", invalid="ignore"):
            g = 2 * cp * (cw - cp) / cw + 2 * rp * (rw - rp) / rw
        g = np.where((cw >= min_w) & (rw >= min_w), g, np.inf)
        k = int(np.argmin(g))
        if g0 - g[k] > best[0]: best = (g0 - g[k], f, k)
    return best
def build(Bm, y, w, rows, depth, min_w, feats):
    W = w[rows].sum(); P = (w[rows] * y[rows]).sum()
    node = {"n": int(len(rows)), "p": float(P / W) if W else 0.0, "npos": int(y[rows].sum())}
    if depth == 0: return node
    gain, f, b = gini_split(Bm, y, w, rows, feats, min_w)
    if f is None: return node
    m = Bm[rows, f] <= b
    node.update(f=int(f), b=int(b), l=build(Bm, y, w, rows[m], depth - 1, min_w, feats), r=build(Bm, y, w, rows[~m], depth - 1, min_w, feats))
    return node
def leaf_ids(t, Bm):
    out = np.full(len(Bm), -1); stack = [(t, np.arange(len(Bm)), "")]; leaves = {}
    while stack:
        n, ix, path = stack.pop()
        if "f" not in n:
            lid = len(leaves); leaves[lid] = (path, n); out[ix] = lid; continue
        m = Bm[ix, n["f"]] <= n["b"]
        stack.append((n["l"], ix[m], path + f"|{n['f']}<={n['b']}")); stack.append((n["r"], ix[~m], path + f"|{n['f']}>{n['b']}"))
    return out, leaves
def thr(edges, f, b):
    e = edges[f]
    if b <= 0: return "NaN"
    return float(e[b - 1]) if b - 1 < len(e) else float("inf")
def fmt_rule(path, names, edges):
    parts = []
    for c in path.strip("|").split("|"):
        if not c: continue
        if "<=" in c: f, b = c.split("<="); op = "<"
        else: f, b = c.split(">"); op = ">="
        f = int(f); b = int(b)
        v = thr(edges, f, b)                     # bin b covers x < e[b-1]  (searchsorted right => x >= e[b-2] and x < e[b-1])
        parts.append(f"{names[f]} {op} {v:.4g}" if b > 0 else f"{names[f]} {'is NaN' if op == '<' else 'not NaN'}")
    return " AND ".join(parts)
