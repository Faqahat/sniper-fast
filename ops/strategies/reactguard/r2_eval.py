#!/usr/bin/env python3
"""REACTGUARD step 2: greedy engine-like picks (one open position; busy until our sell lands + 0.3 s after a fill, 0.8 s after
a revert; >= 5 slots between picks on one mint), threshold + exit chosen on DEV only, frozen, then VAL / HOLDOUT once.
Costs (base): 2.9 mSOL per landed round trip (m2v4), 0.154 mSOL per revert (MEASURED: APEX probe 3, cheap lanes, 13 reverts
= 0.002 SOL). Stress: + pen(0.45) = 8.25 mSOL per FILL (ECHO live-vs-sim calibration of m2v4). Size 0.45 SOL.
usage: r2_eval.py > out.txt"""
import sys, json, glob, numpy as np, datetime as dt
sys.path.insert(0, "/home/it/sniper-studies/sniper-m2v4"); import sim as SM
D = "/home/it/sniper-data/reactguard/"; PKT = SM.PKT; SLOT = 0.21207
TRIP = 0.0029; REV = 0.000154; PEN = SM.pen(0.45); S = 0.45
def ts(s): return int(dt.datetime.strptime("2026-" + s, "%Y-%m-%d %H:%M").replace(tzinfo=PKT).timestamp())
RUNS = sorted(r.split("o_")[1][:-4] for r in glob.glob(D + "o_*.npz"))
starts = [int(np.load(D + f"tape_{r}/slots.npy")["bt"].min()) for r in RUNS]
ends = [int(np.load(D + f"tape_{r}/slots.npy")["bt"].max()) for r in RUNS]
W = {"DEV": (0, ts("11-01 12:00")), "VAL": (ts("11-01 12:00"), ts("11-01 19:06")), "HOLD": (ts("11-02 17:50"), 2**31)}
# assignment by token creation time + hours per window
parts = []; HRS = {w: 0.0 for w in W}; DAYH = {}
for j, r in enumerate(RUNS):
    lo = starts[j] + (5 if j else 0); hi = starts[j + 1] + 5 if j + 1 < len(RUNS) else ends[j] + 1
    if j + 1 < len(RUNS) and starts[j + 1] > ends[j]: hi = ends[j] + 1      # gap: run covers to its end
    z = dict(np.load(D + f"o_{r}.npz")); keep = (z["cbt"] >= lo) & (z["cbt"] < hi)
    parts.append({k: v[keep] for k, v in z.items()})
    sb = np.load(D + f"tape_{r}/slots.npy")["bt"].astype(np.int64); sb = sb[(sb >= lo) & (sb < hi)]
    for w, (a, b) in W.items(): HRS[w] += ((sb >= a) & (sb < b)).sum() * SLOT / 3600
    dd = (sb - ts("10-26 00:00")) // 86400 + 26
    for d in np.unique(dd): DAYH[int(d)] = DAYH.get(int(d), 0) + (dd == d).sum() * SLOT / 3600
Z = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
o = np.argsort(Z["clk"], kind="stable"); Z = {k: v[o] for k, v in Z.items()}
bt = Z["bt"].astype(np.int64); WIN = {w: (bt >= a) & (bt < b) for w, (a, b) in W.items()}
DAY = (bt - ts("10-26 00:00")) // 86400 + 26
LS = ["0", "5", "10", "20", "30", "45", "60", "fra"]

def att(L, g, ex, c):
    """per-attempt fill prob F, fill-weighted pnl FP, busy-until clock"""
    if L == "fra": F = Z[f"Lfra|F_{g}"].astype(float); FP = Z[f"Lfra|FP_{g}_{ex}_{c}"].astype(float); tl = Z["Lfra|tl"]; tx = Z["Lfra|tx_T"]
    else:
        F = Z[f"L{L}|{g}"].astype(float); FP = F * Z[f"L{L}|p_{ex}_{c}"]; tl = Z[f"L{L}|tl"]; tx = Z[f"L{L}|tx_{ex}"]
    return F, FP, tl, tx

def greedy(mask, F, tl, tx):
    idx = np.flatnonzero(mask); busy = -1e18; last = {}; pick = []
    clk = Z["clk"]; mt = Z["mint"]; sl = Z["slot"]
    # mints are per-run indices: key by (run-local mint, creation bt)
    cb = Z["cbt"]
    for r in idx.tolist():
        if clk[r] < busy: continue
        m = (int(mt[r]), int(cb[r]))
        if m in last and sl[r] < last[m] + 5: continue
        last[m] = sl[r]; pick.append(r)
        busy = (tx[r] + 0.3 / SLOT) if F[r] >= 0.5 else (tl[r] + 0.8 / SLOT)
    return np.array(pick, np.int64)

def val(F, FP, pen=False):
    return FP - TRIP * F - REV * (1 - F) - (PEN * F if pen else 0)

def stats(pk, F, FP, w, pen=False):
    pk = pk[WIN[w][pk]]; v = val(F[pk], FP[pk], pen); h = HRS[w]
    if not len(pk): return dict(n=0, fills=0, rev=0, revc=0, day=0, no5=0)
    vs = np.sort(v)[::-1]
    return dict(n=len(pk), fills=F[pk].sum(), rev=(1 - F[pk]).sum(), revc=REV * (1 - F[pk]).sum(), day=v.sum() / h * 24,
                no5=vs[5:].sum() / h * 24, per=1e3 * v.mean())

def run_cfg(model, thr, L, g, ex):
    sc = Z[model]; out = {}
    for c in (0, 20):
        F, FP, tl, tx = att(L, g, ex, c)
        pk = greedy(sc >= thr, *att(L, g, ex, 0)[0:1], tl, tx) if False else greedy(sc >= thr, F, tl, tx)
        out[c] = (pk, F, FP)
    return out

print(f"# REACTGUARD eval  hours DEV {HRS['DEV']:.1f}  VAL {HRS['VAL']:.1f}  HOLD {HRS['HOLD']:.1f}; envelope dumps "
      + " ".join(f"{w} {WIN[w].sum()}" for w in W))
print(f"runs: {RUNS}")
QS = [0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.12, 0.2, 0.3, 0.5, 1.0]
LIVE = {"sc3": 0.0101, "sc4": 0.006}
res = {}
for model in ("sc3", "sc4"):
    dv = Z[model][WIN["DEV"]]
    grid = sorted(set([LIVE[model]] + [float(np.quantile(dv, 1 - q)) if q < 1 else -1e9 for q in QS]))
    for L in LS:
        best = None
        for thr in grid:
            for ex in ("T", "S2"):
                F, FP, tl, tx = att(L, "g01", ex, 0); pk = greedy(Z[model] >= thr, F, tl, tx)
                s = stats(pk, F, FP, "DEV")
                if best is None or s["day"] > best[0]: best = (s["day"], thr, ex)
        res[(model, L)] = best
json.dump({f"{m}|{L}": v for (m, L), v in res.items()}, open(D + "frozen_choice.json", "w"), indent=1)

def row(model, thr, L, g, ex, tag):
    cells = {}
    for c in (0, 20):
        F, FP, tl, tx = att(L, g, ex, c); pk = greedy(Z[model] >= thr, F, tl, tx)
        for w in W: cells[(w, c)] = stats(pk, F, FP, w)
        for w in W: cells[(w, "pen")] = stats(pk, F, FP, w, pen=True)
    d, v, h = cells[("DEV", 0)], cells[("VAL", 0)], cells[("HOLD", 0)]
    return (f"| {tag} | {L} | {g} | {ex} | {d['n']}/{d['fills']:.0f}/{d['rev']:.0f} | {h['n']}/{h['fills']:.0f}/{h['rev']:.0f} ({1e3*h['revc']:.1f} mSOL) | "
            f"{d['day']:+.2f} | {v['day']:+.2f} | {h['day']:+.2f} | {v['no5']:+.2f} / {h['no5']:+.2f} | "
            f"{cells[('VAL',20)]['day']:+.2f} / {cells[('HOLD',20)]['day']:+.2f} | {cells[('VAL','pen')]['day']:+.2f} / {cells[('HOLD','pen')]['day']:+.2f} |")

HDR = ("| config | L ms | guard | exit | DEV picks/fills/reverts | HOLD picks/fills/reverts (revert cost) | DEV SOL/day | VAL SOL/day | HOLD SOL/day | "
       "w/o top5 VAL / HOLD | -20% followers VAL / HOLD | +pen stress VAL / HOLD |\n|---|---|---|---|---|---|---|---|---|---|---|---|")
NM = {"sc3": "v3", "sc4": "v4"}
print("\n## A. DEV-chosen (threshold + exit chosen on DEV, guard g01, base costs), frozen -> VAL / HOLD\n" + HDR)
for model in ("sc3", "sc4"):
    for L in LS:
        _, thr, ex = res[(model, L)]
        print(row(model, thr, L, "g01", ex, f"{NM[model]} thr {thr:.4f}"))
print("\n## B. Same frozen choice, other guard rules\n" + HDR)
for model in ("sc3", "sc4"):
    for L in LS:
        _, thr, ex = res[(model, L)]
        for g in ("g05", "gx"): print(row(model, thr, L, g, ex, f"{NM[model]} thr {thr:.4f}"))
print("\n## C. Live thresholds (v3 0.0101, v4 0.006), both exits, g01 (not chosen; informative)\n" + HDR)
for model in ("sc3", "sc4"):
    for ex in ("T", "S2"):
        for L in LS: print(row(model, LIVE[model], L, "g01", ex, f"{NM[model]} live"))
print("\n## D. All envelope dumps (no M2 gate), exit T, g01\n" + HDR)
for L in LS: print(row("sc3", -1e9, L, "g01", "T", "all dumps"))

# per-day rows for the DEV-chosen configs
print("\n## E. Per PKT day SOL/day (DEV-chosen, g01, base costs; DEV to 11-01 12:00, VAL 11-01 12:00-19:06, HOLD 11-02 17:50+; partial days)")
days = sorted(DAYH)
lab = lambda d: (dt.datetime.fromtimestamp(ts("10-26 00:00") + (d - 26) * 86400, PKT)).strftime("%m-%d")
print("| config | L | " + " | ".join(f"{lab(d)} ({DAYH[d]:.1f} h)" for d in days) + " |\n|---|---|" + "---|" * len(days))
for model in ("sc3", "sc4"):
    for L in LS:
        _, thr, ex = res[(model, L)]; F, FP, tl, tx = att(L, "g01", ex, 0); pk = greedy(Z[model] >= thr, F, tl, tx)
        v = val(F[pk], FP[pk]); dd = DAY[pk]
        print(f"| {NM[model]} {ex} thr {thr:.4f} | {L} | " + " | ".join(f"{v[dd == d].sum() / DAYH[d] * 24:+.2f} ({(dd == d).sum()})" for d in days) + " |")

# adverse selection
print("\n## F. Adverse selection: value of a fill RIGHT BEHIND the dump (front, exit T, no costs, mSOL/attempt) split by whether the "
      "guard (g01) fills at L\n| set | L | dumps | guard-fill share | front P&L when guard FILLS | front P&L when guard REVERTS (someone backran) | "
      "actual P&L of our fill (at our position) | unguarded P&L at our position, all dumps |\n|---|---|---|---|---|---|---|---|")
for nm, msk in (("all envelope dumps", np.ones(len(bt), bool)), ("v3 live picks (sc3>=0.0101)", Z["sc3"] >= 0.0101), ("v4 live picks (sc4>=0.006)", Z["sc4"] >= 0.006)):
    for L in LS[:-1]:
        g = Z[f"L{L}|g01"] > 0; pf = Z[f"L{L}|pf_T_0"]; p = Z[f"L{L}|p_T_0"]
        a, b = msk & g, msk & ~g
        print(f"| {nm} | {L} | {msk.sum()} | {g[msk].mean():.2f} | {1e3*pf[a].mean():+.2f} | {1e3*pf[b].mean() if b.any() else float('nan'):+.2f} | "
              f"{1e3*p[a].mean():+.2f} | {1e3*p[msk].mean():+.2f} |")

# G. live-threshold configs (frozen before these data for v3: built 10-25; v4 trained 10-22..10-27 -> its 10-26/27 are in-sample)
print("\n## G. Live thresholds, live exit T, g01: per PKT day SOL/day and per-fill economics (base costs)")
print("| config | L | fills/day HOLD | gross mSOL/fill HOLD | net mSOL/fill HOLD (after trip+reverts) | " + " | ".join(lab(d) for d in days) + " |\n|---|---|---|---|---|" + "---|" * len(days))
for model in ("sc3", "sc4"):
    for L in LS:
        F, FP, tl, tx = att(L, "g01", "T", 0); pk = greedy(Z[model] >= LIVE[model], F, tl, tx)
        v = val(F[pk], FP[pk]); dd = DAY[pk]; h = pk[WIN["HOLD"][pk]]
        fills = F[h].sum(); gross = FP[h].sum() / max(fills, 1e-9); net = val(F[h], FP[h]).sum() / max(fills, 1e-9)
        print(f"| {NM[model]} live T | {L} | {fills / HRS['HOLD'] * 24:.0f} | {1e3*gross:+.1f} | {1e3*net:+.1f} | " + " | ".join(f"{v[dd == d].sum() / DAYH[d] * 24:+.2f}" for d in days) + " |")
