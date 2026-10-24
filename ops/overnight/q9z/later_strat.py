#!/usr/bin/env python3
# READ-ONLY, offline paper replay (no money): LATER-ENTRY strategies built from 9qz7cW's later buys, scored the owner's way
# (2026-10-23): profit must come from generic flow, not from landing ahead of pro bots.
#  Our fill: decision at the trigger trade (slot s); our normal low-fee tx lands 300 ms or 500 ms later, so EVERY trade in
#  slots <= s+1 (300 ms) or <= s+2 (500 ms) is ahead of us. Costs: pump fees per side (from the events) + 0.0001 SOL per
#  tx; variant with a 1% worse fill. Size 0.5 SOL.
#  Robustness: (1) buys after our entry by the 380 FAST SNIPER wallets (fast_snipers.json, 9qz7cW included) removed;
#  (2) buys after our entry by the 10 wallets that most often buy after us (computed per strategy) removed; (3) both;
#  (4) slippage-aware: follower buys that their own decoded limit would reject after our insert are dropped
#  (rp.sim slip=, core/slip_args.jsonl + its own limits slip_q9z.jsonl); with / without.
#  L1 FOLLOW: buy after its later buys (decision = its buy tx).
#  L2 GENERIC TRIGGER (no wallet dependency): first trade 5-300 s after the create where price >= 1.10x the post-bundle
#     price, the last 10 s had net SOL inflow >= 3 SOL from >= 8 buys, curve vsol 38-65 SOL (thresholds = its own later-
#     entry medians / ranges, NOT tuned on outcomes). One entry per launch. All SOL-quoted, non-mayhem launches R1 + R2.
#  Exits: eos1 (end of next slot), hold 5 s, hold 20 s, its ladder shape (30% at 3.2 s, then 10% every 2.1 s to 17.9 s),
#  ladder with a 0.9x stop.
# -> later_strat.json + later_strat.txt
import sys, os, json, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__)); W = "9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw"
FS = set(json.load(open(os.path.join(HERE, "fast_snipers.json"))))
PL = json.load(open(os.path.join(HERE, "perlaunch_q9z.json")))
L = rp.load_launches()
SLIP = {}
for f in ("/home/moiz/sniper/ops/overnight/core/slip_args.jsonl", os.path.join(HERE, "slip_q9z.jsonl")):
    if os.path.exists(f):
        for l in open(f):
            try: r = json.loads(l)
            except Exception: continue
            if r.get("kind") in ("sol", "tok"): SLIP[r["sig"]] = (r["kind"], r["a1"], r["a2"])
B = 0.5; FEE_PCT = 0.0001 / B; SELL_FEE = 0.0001
LAD = [(0.3, ("t", 3.2))] + [(0.1, ("t", round(3.2 + 2.1 * k, 1))) for k in range(1, 8)]
EXITS = [rp.R("eos1", [(1.0, ("slot", 1))], 5), rp.R("hold5s", [(1.0, ("t", 5))], 6), rp.R("hold20s", [(1.0, ("t", 20))], 21),
         rp.R("ladder", LAD, 19), rp.R("ladder_stop0.9", LAD + [(1.0, ("sl", 0.9))], 19)]
mayhem = lambda c: "InitializeMayhemState" in (c.get("ixn") or [])
def entry_after(tr, s_dec, lag_slots):
    """index of the first trade AFTER every trade in slots <= s_dec + lag_slots (we are before tr[idx])"""
    return next((i for i, t in enumerate(tr) if t["s"] > s_dec + lag_slots), None)
def trigger(tr, st, S):
    """L2: first trade index meeting the generic momentum trigger"""
    ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; j0 = 0
    for k in range(st["g_end"], len(tr)):
        t = tr[k]; age = (t["s"] - S) * 0.212
        if age < 5: continue
        if age > 300: return None
        if not (38e9 <= t["vsol"] <= 65e9) or (t["vsol"] / t["vtok"]) / p_b < 1.10: continue
        while tr[j0]["s"] < t["s"] - 47: j0 += 1
        win = tr[j0:k + 1]
        nb = sum(1 for x in win if x["buy"]); flow = sum((x["sol"] if x["buy"] else -x["sol"]) for x in win)
        if nb >= 8 and flow >= 3e9: return k
    return None
def score(tr, c, st, idx, drop=None, slip=None, pen=0.0):
    o = rp.sim(tr, c, st, idx, B, EXITS, fee_buy_pct=FEE_PCT, sell_fee_sol=SELL_FEE, fill_pen=pen, drop_after=drop, slip=slip)
    return {k: v["pnl"] for k, v in o.items()} if o else None
def after_buyers(tr, idx, S_end):
    return {t["user"] for t in tr[idx:] if t["buy"] and t["s"] <= S_end}
jobs = collections.defaultdict(set)
for m, c in L.items():
    if c.get("bt") and not mayhem(c): jobs[(c["run"], rp.bucket(m))].add(m)
def work(job, top10=frozenset()):
    run, b = job; tra = rp.read_bucket(run, b, jobs[job]); out = {}
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        S = c["slot"]; rec = {}
        cand = {}
        p = PL.get(m)
        if p and p["beh"] == "later" and p.get("buy_sig"):
            k = next((i for i, t in enumerate(tr) if t["sig"] == p["buy_sig"]), None)
            if k is not None: cand["L1"] = tr[k]["s"]
        k2 = trigger(tr, st, S)
        if k2 is not None: cand["L2"] = tr[k2]["s"]
        for strat, s_dec in cand.items():
            for lag, lab in ((1, "300ms"), (2, "500ms")):
                idx = entry_after(tr, s_dec, lag)
                if idx is None or idx >= len(tr): continue
                end_slot = tr[idx - 1]["s"] + 95                 # ~20 s window for after-us buyers
                if top10: r = dict(t10=score(tr, c, st, idx, drop=top10), fs_t10=score(tr, c, st, idx, drop=FS | top10))
                else: r = dict(base=score(tr, c, st, idx), pen1=score(tr, c, st, idx, pen=0.01), fs=score(tr, c, st, idx, drop=FS),
                               slip=score(tr, c, st, idx, slip=SLIP), fs_slip=score(tr, c, st, idx, drop=FS, slip=SLIP),
                               after=sorted(after_buyers(tr, idx, end_slot)), age_s=round((s_dec - S) * 0.212, 1))
                rec[f"{strat}_{lab}"] = r
        if rec: out[m] = dict(bt=c["bt"], run=run, its_later=bool(p and p["beh"] == "later"), r=rec)
    return out
def run_all(top10=frozenset()):
    res = {}
    with Pool(12) as pool:
        for o in pool.starmap(work, [(j, top10) for j in sorted(jobs)]): res.update(o)
    return res
if __name__ == "__main__":
    res = run_all()
    # top-10 most frequent after-us buyers per strategy family (L1 / L2), at 300 ms
    top = {}
    for strat in ("L1", "L2"):
        cnt = collections.Counter()
        for v in res.values():
            r = v["r"].get(f"{strat}_300ms")
            if r and r.get("after"): cnt.update(r["after"])
        top[strat] = [w for w, _ in cnt.most_common(10)]
    t10 = frozenset(top["L1"]) | frozenset(top["L2"])
    res2 = run_all(t10)
    for m, v in res2.items():
        for k, r in v["r"].items():
            if m in res and k in res[m]["r"]: res[m]["r"][k]["t10"] = r["t10"]; res[m]["r"][k]["fs_t10"] = r["fs_t10"]
    json.dump(dict(top10=top, res=res), open(os.path.join(HERE, "later_strat.json"), "w"))
    lines = []
    def P(x): print(x, flush=True); lines.append(x)
    P(f"fast sniper wallets removed after our entry: {len(FS)} | top-10 after-us buyers: L1 {[w[:6] for w in top['L1']]} | L2 {[w[:6] for w in top['L2']]} | slip limits known: {len(SLIP)}")
    for strat in ("L1", "L2"):
        for lab in ("300ms", "500ms"):
            key = f"{strat}_{lab}"
            rows = [(v["bt"], v["run"], v["r"][key]) for v in res.values() if key in v["r"] and v["r"][key]["base"]]
            if not rows: continue
            P(f"\n== {key}: n {len(rows)} entries (R1 {sum(1 for _, r, _ in rows if r == 'R1')}, R2 {sum(1 for _, r, _ in rows if r == 'R2')}); age at decision med {statistics.median([x['age_s'] for _, _, x in rows]):.0f} s")
            if strat == "L2": P(f"   of which also its later picks: {sum(1 for m, v in res.items() if key in v['r'] and v['its_later'])}")
            for ex in ("eos1", "hold5s", "hold20s", "ladder", "ladder_stop0.9"):
                cells = []
                for var in ("base", "pen1", "fs", "t10", "fs_t10", "slip", "fs_slip"):
                    v = [(bt, x[var][ex]) for bt, _, x in rows if x.get(var) and x[var].get(ex) is not None]
                    if not v: cells.append(f"{var} -"); continue
                    v.sort(); mid = v[0][0] + (v[-1][0] - v[0][0]) / 2
                    tot = sum(y for _, y in v); a = sum(y for t, y in v if t < mid)
                    cells.append(f"{var} {tot:+.2f} ({a:+.1f}/{tot - a:+.1f})")
                P(f"   {ex:15} " + " | ".join(cells))
            for run_ in ("R1", "R2"):
                v = [x["fs_t10"]["ladder"] for _, r, x in rows if r == run_ and x.get("fs_t10")]
                w = [x["base"]["ladder"] for _, r, x in rows if r == run_]
                P(f"   {run_}: ladder base {sum(w):+.2f} (n {len(w)}, win {sum(1 for y in w if y > 0) / max(1, len(w)):.0%}) | ladder with fast snipers + top-10 removed {sum(v):+.2f}")
    open(os.path.join(HERE, "later_strat.txt"), "w").write("\n".join(lines) + "\n")
