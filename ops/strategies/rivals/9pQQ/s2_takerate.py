#!/usr/bin/env python3
"""9pQQ selection: take rate (share of decision moments it reacted to) by feature bucket, and the forward price change of taken vs
skipped moments in the same bucket (fwd100 = curve price 100 slots (~21 s) later vs right after the event; no costs; its own
trades included in the path).  Also token-level coverage.  Read-only.  usage: s2_takerate.py"""
import numpy as np, collections, json
import tlib9 as L

Z = {}
for r in L.RUNS:
    z = np.load(f"{L.OUT}/uni_{r}.npz"); Z[r] = {k: z[k] for k in z.files}
A = {k: np.concatenate([Z[r][k] for r in L.RUNS]) for k in Z[L.RUNS[0]]}
y = A["y"] == 1
print("events", len(y), "taken", int(y.sum()), "rate %.3f%%" % (100 * y.mean()))
BK = {
    "side": [0], "size": [0.05, 0.2, 0.5, 1, 2, 5], "age": [10, 50, 150, 450, 1500, 5000, 20000], "vsol": [32, 35, 40, 50, 60, 70, 80],
    "may": [0.5], "flow10": [-5, -2, -0.5, 0.5, 2, 5, 10], "flow75": [-5, -1, 1, 5, 10, 20], "nbuy10": [1, 3, 6, 10, 20],
    "ntr150": [5, 20, 50, 100, 200], "dp10": [-0.2, -0.1, -0.03, 0.03, 0.1, 0.2], "dp75": [-0.3, -0.1, 0, 0.1, 0.3, 0.6],
    "dd450": [-0.5, -0.3, -0.2, -0.1, -0.03, -0.0001], "ntr_sofar": [10, 50, 200, 1000, 3000], "trader_cnt": [10, 100, 1000, 10000],
    "dev_sold": [0.5], "k_done": [1, 2, 4, 8], "since_sell": [5, 25, 100, 400, 1500], "hour": [3, 6, 9, 12, 15, 18, 21],
}
res = {}
for f, ed in BK.items():
    v = A[f]; b = np.digitize(np.nan_to_num(v, nan=-1e18), ed)
    nanm = np.isnan(v)
    print(f"\n--- {f}")
    rows = []
    for k in range(len(ed) + 1):
        m = (b == k) & ~nanm
        if m.sum() < 1000: continue
        lab = f"<{ed[k]}" if k < len(ed) else f">={ed[-1]}"
        tk = m & y; sk = m & ~y
        fw_t = np.nanmean(np.clip(A["fwd100"][tk], -1, 3)) if tk.sum() else np.nan
        fw_s = np.nanmean(np.clip(A["fwd100"][sk], -1, 3))
        net = np.nanmean(A["trip_net"][tk]) * 1000 if tk.sum() else np.nan
        print(f"  {lab:>9s} events {m.sum():8d} taken {tk.sum():6d} rate {100 * tk.sum() / m.sum():6.3f}%  fwd100 taken {fw_t:+.3f} skipped {fw_s:+.3f}  its net mSOL/trip {net:+.1f}")
        rows.append(dict(b=lab, n=int(m.sum()), taken=int(tk.sum()), rate=float(tk.sum() / m.sum()), fwd_t=float(fw_t), fwd_s=float(fw_s), net=float(net)))
    if nanm.sum() >= 1000:
        m = nanm; tk = m & y
        print(f"  {'NaN':>9s} events {m.sum():8d} taken {tk.sum():6d} rate {100 * tk.sum() / m.sum():6.3f}%")
    res[f] = rows
json.dump(res, open("/home/it/sniper/ops/strategies/rivals/9pQQ/takerate.json", "w"), indent=1)
# token level: launched tokens (non-mayhem / mayhem) touched or not, by how many outside trades they got
print("\n--- token level")
for r in L.RUNS:
    z = Z[r]; la = L.launches(r)
    may = {m: v["may"] for m, v in la.items()}
    t = L.load_tape(r)
    cnt = np.bincount(z["m"], minlength=len(t.mints)); tk = np.bincount(z["m"], weights=z["y"].astype(float), minlength=len(t.mints))
    mm = np.array([may.get(m, None) for m in t.mints], dtype=object)
    for lab, sel in (("non-mayhem", mm == False), ("mayhem", mm == True)):
        out = []
        for lo, hi in ((1, 10), (10, 50), (50, 200), (200, 1000), (1000, 10 ** 9)):
            s = sel & (cnt >= lo) & (cnt < hi)
            out.append(f"[{lo},{hi if hi < 1e9 else 'inf'}) {s.sum()} tok, touched {np.mean(tk[s] > 0) * 100 if s.sum() else 0:.1f}%")
        print(r, lab, " | ".join(out))
