#!/usr/bin/env python3
"""GAP step 7 (read-only): the guard-failure bucket. For every REGULAR fire of ours that landed but failed (no fill in the episode),
what would the same tx have made with NO price limit, at its REAL landing position (slot, idx)? Exact curve replay (dv8sim.pnl_exact:
later buys keep their SOL, later sells keep their tokens; validated on 595 live fills to +0.02 mSOL/fill), 0.40 SOL, timer exit
5 / 8 / 12 slots after our landing slot. Split: e = haqq filled on that event (his lot linked) vs x = he had no lot.
Extra tx cost of turning a failed fire into a fill at NOW costs: (1.75 - 0.53) + 1.77 = 2.99 mSOL; CHEAP (haqq recipe): 0.62.
No landing model is involved (real positions) -> no calibration applied. INFERRED (replay), counts MEASURED.
Out: gap/g7_guard.txt"""
import pickle, collections, sys, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
from dv8sim import pnl_exact
OUT = "/home/moiz/sniper-data/haqq_dissect/gap"
SIZE = 0.40


def main():
    Z = pickle.load(open(f"{OUT}/g3_rows.pkl", "rb")); rows = Z["rows"]; eps = Z["eps"]
    for E in eps:
        bk = [rows[i]["bucket"] for i in E["his"]]
        E["cat"] = "f" if "f" in bk else ("e" if (bk and not E["fill"]) else ("d" if E["fill"] else ("x" if E["n_fail"] > 0 else "o")))
    todo = []
    for k, E in enumerate(eps):
        if E["fill"] or E["path"] not in ("reg",) or E["cat"] not in ("e", "x"): continue
        a = [(s, i) for (s, i, kd, code, pth) in E["att"] if kd == "buy_fail" and code == "6042"]
        if not a: continue
        s, i = min(a); todo.append((k, E["mint"], s, i))
    ids, idm = L.ids_map(); ours = set(idm[w] for w in L.WAL.values() if w in idm)
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    mids = np.array(sorted(set(idm[m] for _, m, _, _ in todo if m in idm)), np.uint32)
    sel = np.flatnonzero(np.isin(np.asarray(T["mint"]), mids))
    S = np.asarray(T[sel]); S = S[~np.isin(S["user"], list(ours))]
    o = np.lexsort((S["j"], S["idx"], S["slot"], S["mint"])); S = S[o]
    um, st = np.unique(S["mint"], return_index=True); en = np.append(st[1:], len(S)); span = {int(m): (a, b) for m, a, b in zip(um, st, en)}
    res = []
    for k, mint, s, i in todo:
        mi = idm.get(mint)
        if mi not in span: continue
        a, b = span[mi]; X = S[a:b]
        sl = X["slot"].astype(np.int64); ix = X["idx"].astype(np.int64)
        r = int(np.searchsorted(sl * 10000 + ix, s * 10000 + i, side="right"))
        if r == 0 or r >= len(X): continue
        vs = X["vsol"].astype(np.float64) / 1e9; vt = X["vtok"].astype(np.float64); so = X["sol"].astype(np.float64) / 1e9
        tk = X["tok"].astype(np.float64); bu = X["buy"].astype(bool)
        out = {}
        for H in (5, 8, 12):
            q = int(np.searchsorted(sl, s + H, side="right")) - 1
            q = max(q, r - 1)
            out[H] = pnl_exact(vs, vt, so, tk, bu, r, q, SIZE)
        E = eps[k]
        res.append(dict(day=E["day"], cat=E["cat"], w=E["w"], pnl=out, his=sum(rows[j]["net"] for j in E["his"]), cost=E["pnl"]))
    lines = []
    def P(*x):
        t = " ".join(str(y) for y in x); print(t); lines.append(t)
    P("# Our REGULAR fires that landed and failed the +5 % guard (6042): same tx with NO limit at its real landing position, 0.40 SOL (INFERRED exact replay)")
    P("| day | event | fires | his net on them (MEASURED) | no-limit P&L exit 5 / 8 / 12 slots (curve) | win % (5) | net of extra NOW costs (5) | net of extra CHEAP costs (5) |")
    P("|---|---|---|---|---|---|---|---|")
    J = {}
    for d in sorted(set(x["day"] for x in res)):
        for c in ("e", "x", "all"):
            v = [x for x in res if x["day"] == d and (c == "all" or x["cat"] == c)]
            if not v: continue
            p = {H: sum(x["pnl"][H] for x in v) for H in (5, 8, 12)}
            n = len(v)
            J[f"{d}|{c}"] = dict(n=n, his=sum(x["his"] for x in v), p=p, now=p[5] - n * 0.00299, cheap=p[5] - n * 0.00062)
            P(f"| {d} | {c} | {n} | {sum(x['his'] for x in v):+.2f} | {p[5]:+.3f} / {p[8]:+.3f} / {p[12]:+.3f} | {100 * np.mean([x['pnl'][5] > 0 for x in v]):.0f} | "
              f"{p[5] - n * 0.00299:+.3f} | {p[5] - n * 0.00062:+.3f} |")
    open(f"{OUT}/g7_guard.txt", "w").write("\n".join(lines) + "\n")
    json.dump(J, open(f"{OUT}/g7.json", "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
