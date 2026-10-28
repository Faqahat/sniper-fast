import numpy as np, pickle
def cols(rows):
    ks = rows[0].keys(); return {k: np.array([r[k] for r in rows]) for k in ks}
def tab(title, key, X, extra=()):
    """key: array of labels; prints n, first-buys, pnl, mean ret, win, + medians of extra cols"""
    print(f"-- {title}")
    labs = list(dict.fromkeys(sorted(set(key.tolist()), key=lambda z: str(z))))
    hdr = f"{'grp':>22} {'n':>6} {'pnl':>8} {'mret%':>7} {'win%':>5} {'solm':>5}" + "".join(f" {e[:9]:>9}" for e in extra)
    print(hdr)
    for l in labs:
        m = key == l
        if m.sum() == 0: continue
        s = f"{str(l):>22} {m.sum():6d} {X['lot_pnl'][m].sum():8.2f} {100*X['ret'][m].mean():7.2f} {100*(X['ret'][m]>0).mean():5.0f} {np.median(X['sol'][m]):5.2f}"
        s += "".join(f" {np.median(X[e][m]):9.3f}" for e in extra)
        print(s)
def bucket(x, edges):
    i = np.searchsorted(edges, x, side="right")
    labs = [f"<{edges[0]}"] + [f"{edges[k]}..{edges[k+1]}" for k in range(len(edges) - 1)] + [f">={edges[-1]}"]
    return np.array([f"{k:02d} {labs[k]}" for k in i])
