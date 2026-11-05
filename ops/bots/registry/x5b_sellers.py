#!/usr/bin/env python3
"""BOTREG step 5b [MEASURED]: SELLS-INTO-US class on our live positions. Rules were fixed before this script read any r55
outcome; DEV = r37-r54 first, r55 printed once (flag R55=1).
Per position (flatsig run extracts, P&L = engine presend_live_realized): was a wallet that the registry listed as a seller
AT THAT HOUR (backtest/sellers.npz, built from chain data before the hour) holding >= 0.5% when our buy landed (chain)?
Also the S4 bait pattern per position, and the 'rival dip bot' check for 4ggJqUDD.
usage: x5b_sellers.py [R55=1 env to include r55]"""
import sys, os, json, pickle, glob, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C, reg as R

FS = "/home/moiz/sniper-data/flatsig/runs"
DEV = [f"r{i}" for i in range(37, 55)]
RUNS = DEV + (["r55"] if os.environ.get("R55") else [])
OUT = []
def say(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); OUT.append(s)

chain = {}
for p in sorted(glob.glob(f"{C.DATA}/hourly/*.ours.pkl")):
    for x in pickle.load(open(p, "rb")): chain[(x["mint"], x["slot"], x["w"])] = x
Sz = np.load(f"{C.DATA}/backtest/sellers.npz")
sl = collections.defaultdict(set)
for t, u, s in zip(Sz["t"], Sz["u"], Sz["s"]): sl[int(t)].add(int(u))
reg = pickle.load(open(f"{C.DATA}/backtest/registry_state.pkl", "rb"))
first_flag = {u: r["first_flag"] for u, r in reg.S.items()}
OURW = {1: None, 2: None}
rows = []
for run in RUNS:
    x = pickle.load(open(f"{FS}/ex_{run}.pkl", "rb"))
    me = x.get("me")
    for p in x["pos"]:
        t = p["t0"] / 1e9; h = C.hour_of(t)
        m64 = C.pk64(p["mint"])
        cp = None
        for w in C.OURS64:
            cp = chain.get((m64, p["buy_slot"], w)) or cp
        listed = sl.get(h, set())
        held = [u for u, pct in (cp["holders"] if cp else []) if u in listed]
        sold = [u for u, sol, pct in (cp["sellers"] if cp else []) if u in listed and sol >= 0.05]
        whale_listed = p.get("whale") and C.pk64(p["whale"]) in listed
        rows.append({"run": run, "per": "r55" if run == "r55" else "DEV", "t": t, "pnl": p["pnl"], "kind": p["kind"], "chain": cp is not None,
                     "held": bool(held), "sold": bool(sold), "whale_listed": bool(whale_listed), "bait": bool(cp and R.bait_event(cp)),
                     "bait_loss": bool(cp and R.bait_event(cp) and cp["pnl"] < 0)})

def tab(rs, name):
    if not rs: return
    a = np.array([r["pnl"] for r in rs])
    say(f"    {name:52s} n {len(rs):5d}  P&L {a.sum():+8.3f} SOL  mean {a.mean() * 1000:+6.1f} mSOL  losers {np.mean(a < 0):.0%}")

for per in ("DEV", "r55"):
    rs = [r for r in rows if r["per"] == per]
    if not rs: continue
    hrs = (max(r["t"] for r in rs) - min(r["t"] for r in rs)) / 3600
    say(f"\n{per}: {len(rs)} positions ({sum(r['chain'] for r in rs)} matched to the recorded chain), {hrs:.0f} h")
    cr = [r for r in rs if r["chain"]]
    tab(cr, "all chain-matched")
    tab([r for r in cr if r["held"]], "a listed seller HELD >= 0.5% when our buy landed")
    tab([r for r in cr if not r["held"]], "no listed seller held")
    sv = np.sort([-r["pnl"] for r in cr if r["held"]])[::-1]
    blk = collections.defaultdict(float)
    for r in cr:
        if r["held"]: blk[r["run"]] -= r["pnl"]
    say(f"    => skip-if-held: saved {sv.sum():+.3f} SOL ({sv.sum() / max(hrs, 1) * 24:+.2f}/day), w/o top 5 {sv.sum() - sv[:5].sum():+.3f}; "
        f"runs with saved > 0: {sum(v > 0 for v in blk.values())}/{len(blk)}")
    tab([r for r in cr if r["whale_listed"]], "the trigger whale was a listed seller")
    tab([r for r in cr if r["held"] or r["whale_listed"]], "held OR trigger whale listed (skip candidate)")
    tab([r for r in cr if r["sold"]], "(after the fact) a listed seller sold into our hold")
    tab([r for r in cr if r["bait"]], "S4 bait pattern (whale+helpers, quiet old token, >=2 sold in)")
    for k in ("T2", "rearm"):
        tab([r for r in cr if r["kind"] == k and (r["held"] or r["whale_listed"])], f"  {k}: held OR whale listed")
# how many seller wallets
ends = {}
for run in RUNS:
    x = pickle.load(open(f"{FS}/ex_{run}.pkl", "rb"))
    ends[run] = max(p["t0"] for p in x["pos"]) / 1e9 if x["pos"] else 0
t54 = max(v for k, v in ends.items() if k != "r55")
say(f"\nSELLER WALLETS (any rule, ever flagged, causal): {len(reg.S)}; flagged by the end of r54: "
    f"{sum(1 for v in first_flag.values() if v <= t54)}; by rule: "
    + str(collections.Counter(r['rule'].split('+')[0] for r in reg.S.values())))
open(f"{C.DATA}/eval_sellers{'_r55' if os.environ.get('R55') else ''}.txt", "w").write("\n".join(OUT) + "\n")
