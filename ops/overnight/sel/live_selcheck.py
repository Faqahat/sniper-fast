#!/usr/bin/env python3
# Is the selection good on the LIVE hours (new collector run since 19:26 PKT)? Every >=1 SOL dump in that run, same builder and
# replay as everything else, main exit TP +8% / SL -5% / 1.3 s with the 2% guard: buy EVERY dump vs only the watch filter vs the
# three wallets' own picks vs OUR picks (frozen IMIT1 strict / wider tiers). Local only.
import os, sys, json, collections
os.environ.update(RP_PHASEA_R2="phaseA_selfwd", RP_PHASEA_R3="phaseA_r3", SELL_LAT="75", SLIPIMP="1", DIP_REAL_SLIP="1", SEL_SLIP="1", DIP_LATS="35,50,75",
                  DIP_B="0.5", DIP_HS="4", DIP_BUSY="0", DIP_HLAG="0", DIP_MAX_AGE="1800", DIP_COHORT_FILE="/home/moiz/sniper/ops/overnight/sel/cohort_train.json")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import numpy as np
import selexit2 as X
import gbdt_np as G
from multiprocessing import Pool
M = json.load(open("/home/moiz/sniper/ops/overnight/sel/IMIT1.json")); FE = M["features"]
r3 = {m for m, c in X.L.items() if c["run"] == "R3"}
byb = collections.defaultdict(set)
for m in r3: byb[("R3", X.rp.bucket(m))].add(m)
X.byb = byb
def work(key): return X.work(key)[0]
if __name__ == "__main__":
    rows = []
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb), chunksize=4): rows += o
    def fv(r, k):
        x = r["xf"]; t = r["tok"]
        if k == "drop_pct": return (1 - r["drop"]) * 100
        if k in ("first_big", "ins"): return float(r[k])
        if k in x: return x[k]
        if k == "prev_sell_ms": return r["prev_sell_ms"] if r["prev_sell_ms"] >= 0 else 1e9
        if k in ("n_tr", "vmax", "since_buy"): return t[k] if t[k] is not None and t[k] >= 0 else 1e9
        return r[k]
    rows.sort(key=lambda r: (r["m"], r["age"])); pm = None; past = []
    for r in rows:
        if r["m"] != pm: pm = r["m"]; past = []
        t0 = r["age"] * 1000.0; b = [x for x in past if x < t0]
        r["tgt_n"] = len(b); r["tgt_since"] = (t0 - max(b)) / 1000.0 if b else 1e9
        for w, d in r["lab"].items(): past.append(t0 + d)
    XX = np.array([[fv(r, k) for k in FE] for r in rows], float)
    env = np.ones(len(rows), bool)
    for k, op, v in M["envelope"]:
        j = FE.index(k); env &= (XX[:, j] >= v) if op == ">=" else (XX[:, j] <= v)
    B = np.zeros(XX.shape, np.int16)
    for j, e in enumerate(M["edges"]):
        b = np.searchsorted(np.array(e), XX[:, j], side="right") + 1; b[np.isnan(XX[:, j])] = 0; B[:, j] = b
    f = np.full(len(rows), M["F0"])
    for t in M["trees"]: f += M["lr"] * G.pred(t, B)
    gi = [tuple(g) for g in X.GRID].index(("T", 0.08, 0.05, 6, 1))
    def spaced(mask):
        keep = np.zeros(len(rows), bool); last = {}
        for i in np.where(mask)[0]:
            r = rows[i]
            if r["m"] in last and r["age"] - last[r["m"]] < 5 * 0.212: continue
            last[r["m"]] = r["age"]; keep[i] = True
        return keep
    T = np.array([X.L[r["m"]]["bt"] + r["age"] for r in rows]); hrs = (T.max() - T.min()) / 3600
    sets = [("buy EVERY dump", spaced(np.ones(len(rows), bool))), ("only the watch filter", spaced(env)),
            ("the 3 wallets' own picks", np.array([bool(r["lab"]) for r in rows])),
            ("OUR wider tier (top 4%)", spaced(env & (f >= M["thresholds"]["top4"]))), ("OUR strict tier (top 2%)", spaced(env & (f >= M["thresholds"]["top2"])))]
    print(f"live hours: {hrs:.1f} h, {len(rows)} dumps on {len(r3)} tokens; exit TP +8% / SL -5% / 1.3 s, 2% guard")
    for nm, m in sets:
        seg = []
        for L in ("35", "75"):
            v = [rows[i] for i in np.where(m)[0] if L in rows[i]["px"]]
            fills = [r["xg"][L][gi] for r in v if r["px"][L] <= 1.02]; sk = len(v) - len(fills)
            seg.append(f"{L} ms: {len(fills):5d} fills, win {sum(1 for p in fills if p > 0) / max(len(fills), 1):4.0%}, P&L {sum(fills) - 0.0002 * sk:+8.2f}")
        print(f"  {nm:28s} {int(m.sum()):6d} picks ({m.sum() / hrs:6.1f}/h) | " + " | ".join(seg))
