#!/usr/bin/env python3
# Generic strategy screen (local only): dataset PREFIX (events + exit grid at 60/75 ms from selexit3.py), a universe filter, and
# an imitation label (profitable-bot cohort buys right after the trigger). GBDT trained on TRAIN hours (< 10-23 06:00 PKT, fit
# first 80%, tiers set on the last 20%), exit chosen on TRAIN, judged on TEST at 60 ms (and 75 ms). Spacing 5 slots per token.
# usage: python3 -I sel_strat.py PREFIX NAME AGE_MIN AGE_MAX LABEL(coh1|coh2|win)
import sys, json, gzip, time, calendar
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import gbdt_np as G
PRE, NAME, AMIN, AMAX, LAB = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
EV = [json.loads(l) for l in gzip.open(f"{PRE}_events.jsonl.gz", "rt")]; XG = np.load(f"{PRE}_exits.npy", mmap_mode="r")
GRID = [tuple(g) for g in json.load(open(f"{PRE}_exits_grid.json"))["grid"]]
keep = np.array([AMIN <= r["age"] <= AMAX for r in EV]); EV = [r for r, k in zip(EV, keep) if k]; XG = np.asarray(XG[keep])
FE = ["age", "sell", "drop_pct", "vsol", "pb", "dd", "nb", "ns", "b20", "s20", "u20", "dev", "glued", "first_big", "ins", "s_frac", "s_pnl", "s_nb", "s_entry",
      "n_big", "since_big", "ret5", "ret20", "peak_mult", "b3", "nb3", "sellers20", "uniq_buyers", "ins_sold", "net_flow", "slotpos", "prev_sell_ms", "n_tr", "vmax",
      "since_buy", "coh_n", "coh_20", "coh_seller", "coh_sol", "coh_held"]
def fv(r, k):
    x = r["xf"]; t = r["tok"]
    if k == "drop_pct": return (1 - r["drop"]) * 100
    if k in ("first_big", "ins"): return float(r[k])
    if k in x: return x[k]
    if k == "prev_sell_ms": return r["prev_sell_ms"] if r["prev_sell_ms"] >= 0 else 1e9
    if k in ("n_tr", "vmax", "since_buy"): return t[k] if t[k] is not None and t[k] >= 0 else 1e9
    return r[k]
X = np.array([[fv(r, k) for k in FE] for r in EV], float); T = np.array([r["bt"] + r["age"] for r in EV])
SPLIT = calendar.timegm(time.strptime("2026-10-23 06:00", "%Y-%m-%d %H:%M")) - 18000; TR = T < SPLIT; TE = ~TR
HTR = (T[TR].max() - T[TR].min()) / 3600; HTE = (T[TE].max() - T[TE].min()) / 3600
FILL = np.array([[r["px"].get(L, 9) <= 1.02 for L in ("60", "75")] for r in EV])
def pnl(j, e): return np.where(FILL[:, j], np.nan_to_num(XG[:, j, e]), -0.0002)
e_ref = GRID.index(("T", 0.08, 0.05, 6, 1))
y = {"coh1": np.array([r["lab_coh"] >= 1 for r in EV]), "coh2": np.array([r["lab_coh"] >= 2 for r in EV]),
     "win": (pnl(0, e_ref) > 0) & FILL[:, 0]}[LAB].astype(float)
cut = np.quantile(T[TR], 0.8); FIT = TR & (T < cut); VA = TR & (T >= cut)
Bm = G.binize(X, FIT); trees, f = G.fit(Bm, y, FIT, VA, rounds=400, lr=0.05, depth=3)
acc = np.zeros(len(FE))
for t in trees: G.imp(t, acc)
M = np.array([r["m"] for r in EV]); AG = np.array([r["age"] for r in EV])
def spaced(mask):
    idx = np.where(mask)[0]; idx = idx[np.lexsort((AG[idx], M[idx]))]; out = np.zeros(len(EV), bool); last = {}
    for i in idx:
        if M[i] in last and AG[i] - last[M[i]] < 1.06: continue
        last[M[i]] = AG[i]; out[i] = True
    return out
print(f"\n##### {NAME}: {len(EV)} triggers (TRAIN {TR.sum()} / {HTR:.1f} h, TEST {TE.sum()} / {HTE:.1f} h), label {LAB} rate {y.mean():.1%}, "
      f"AUC val {G.auc(y[VA], f[VA]):.3f} TEST {G.auc(y[TE], f[TE]):.3f} | top features " + ", ".join(f"{FE[j]} {acc[j] / acc.sum():.0%}" for j in np.argsort(-acc)[:6]))
base = spaced(np.ones(len(EV), bool))
print(f"  every trigger, quick exit: TEST 60 ms {pnl(0, e_ref)[base & TE].sum():+.2f} SOL")
for q in (0.01, 0.02, 0.04, 0.08, 0.15):
    thr = np.quantile(f[VA], 1 - q); pick = spaced(f >= thr)
    tot = [pnl(0, e)[pick & TR].sum() + pnl(1, e)[pick & TR].sum() for e in range(len(GRID))]; e = int(np.argmax(tot))
    seg = []
    for j, L in ((0, "60"), (1, "75")):
        p = pnl(j, e); fl = pick & TE & FILL[:, j]
        seg.append(f"{L} ms {p[pick & TE].sum():+6.2f} ({p[pick & TE].sum() / HTE:+.2f}/h, fills {int(fl.sum())}, win {((p[fl] > 0).mean() if fl.any() else 0):.0%})")
    g = GRID[e]; en = (f"hold {g[1]} slots" if g[0] == "H" else f"TP{g[1]:g}/SL{g[2]:g}/{g[3]}sl/mh{g[4]}")
    print(f"  top {q:4.0%}: TEST {int((pick & TE).sum()):5d} picks ({(pick & TE).sum() / HTE:5.1f}/h) exit {en:22s} | " + " | ".join(seg) + f" | TRAIN 60 ms {pnl(0, e)[pick & TR].sum() / HTR:+.2f}/h")
