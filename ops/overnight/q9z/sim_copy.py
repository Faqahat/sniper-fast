#!/usr/bin/env python3
# READ-ONLY, offline paper replay (no money): can WE copy 9qz7cW? Exact pump.fun curve replay (core/rp.py) on the replay
# window = R2 launches with our engine's arrival timeline (obs), SOL-quoted, not mayhem. Our mechanics: land at 45 or 75 ms
# in our feed (block-order placement with failed-tx anchors, rp.place_bo2), 0.5 SOL, 1% price guard (fail -> -0.005 SOL
# unless the price before our buy is within 1% of the price right after the dev's bundle), sell everything at the end of
# the next slot (rp "slot" leg), fill penalty 1.5%.
#  (a) ORACLE: its snipe attempts (first attempt in the create slot or the next), filled or failed.
#  (a') same picks with its own trades removed from the path (if it were not there) - sensitivity only.
#  (b) WALK-FORWARD deployer list from its snipe attempts: a launch is traded if its creator had >= K earlier launches
#      sniped by it (R1 + R2 history before the launch); quality gate: drop a creator once OUR simulated guarded fills on
#      it number >= 3 and average < 0.
#  (c) its LATER buys (first buy >= 2 slots after the create, R1 + R2, no timeline needed): we buy 0.5 SOL right after
#      the first trade of the slot AFTER its buy (we see its tx, then land one slot later), exits: end of next slot,
#      hold 5 s, hold 20 s, and its own ladder shape (30% at +15 slots, then 17% of the rest every 10 slots, rest at 20 s).
# -> sim_copy.json + printed table (total SOL, fills / attempts, first half / second half by time)
import sys, os, json, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__)); W = "9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw"
A = json.load(open("/home/moiz/sniper/ops/overnight/core/attempts_q9z.json"))
PL = json.load(open(os.path.join(HERE, "perlaunch_q9z.json")))
L = rp.load_launches(); O = rp.load_obs()
cre = lambda c: c.get("creator") or c.get("user")
mayhem = lambda c: "InitializeMayhemState" in (c.get("ixn") or [])
# ---- (b) walk-forward list membership for every R2 launch with a timeline
ev = sorted((c["bt"], m) for m, c in L.items() if c.get("bt"))
snip = collections.Counter(); keepK = {1: {}, 2: {}}
for bt, m in ev:
    c = L[m]
    if c["run"] == "R2" and m in O and not mayhem(c):
        for K in keepK: keepK[K][m] = snip[cre(c)] >= K
    a = A.get(m, {}).get("9qz7cW")
    if a and a[1] <= 1: snip[cre(c)] += 1
cand_b = {m for K in keepK for m, v in keepK[K].items() if v}
cand_a = {m for m, v in A.items() if v["9qz7cW"][1] <= 1 and m in L and L[m]["run"] == "R2" and m in O and not mayhem(L[m])}
cand_c = {m for m, r in PL.items() if r["beh"] == "later" and r.get("buy_slot") and r["quote"] == "SOL" and not r["may"]}
print(f"(a) its snipe attempts in the replay window: {len(cand_a)} | (b) list candidates K=1: {sum(keepK[1].values())}, K=2: {sum(keepK[2].values())} | (c) later buys (filled): {len(cand_c)}", flush=True)
EOS = [rp.R("eos1", [(1.0, ("slot", 1))], 5)]
EXC = [rp.R("eos1", [(1.0, ("slot", 1))], 5), rp.R("hold5s", [(1.0, ("t", 5))], 6), rp.R("hold20s", [(1.0, ("t", 20))], 21)]
jobs = collections.defaultdict(set)
for m in cand_a | cand_b: jobs[("R2", rp.bucket(m))].add(m)
for m in cand_c: jobs[(L[m]["run"], rp.bucket(m))].add(m)
def guarded(tr, c, st, outs, fa, Lm, me=None):
    ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]
    path = [t for t in tr if t["user"] != me] if me else tr
    if me:
        st = rp.structure(path, c)
        if st["g_end"] < 1: return None
    ib, n_ahead = rp.place_bo2(path, c, st, outs, Lm, [x for x in fa if not (me and x[2] == me)])
    if ib < 1: return None
    ok = (path[ib - 1]["vsol"] / path[ib - 1]["vtok"]) / p_b <= 1.01
    o = rp.sim(path, c, st, ib, 0.5, EOS, fill_pen=0.015)
    if not o: return None
    return dict(ng=o["eos1"]["pnl"], g=o["eos1"]["pnl"] if ok else -0.005, fill=ok, ahead=n_ahead)
def work(job):
    run, b = job; ms = jobs[job]
    tra = rp.read_bucket(run, b, ms); fa = rp.read_failed(run, b, ms) if run == "R2" else {}
    out = {}
    for m in ms:
        tr = tra.get(m); c = L[m]
        if not tr or min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        r = dict(bt=c["bt"], run=run, creator=cre(c))
        if m in O and run == "R2":
            for Lm in (45, 75):
                r[f"a{Lm}"] = guarded(tr, c, st, O[m]["outs"], fa.get(m, []), Lm)
                r[f"x{Lm}"] = guarded(tr, c, st, O[m]["outs"], fa.get(m, []), Lm, me=W)
        if m in cand_c:
            p = PL[m]; k = next((i for i, t in enumerate(tr) if t["sig"] == p["buy_sig"]), None)
            if k is not None:
                j = next((i for i, t in enumerate(tr) if t["s"] > tr[k]["s"]), None)
                if j is not None:
                    j = min(j + 1, len(tr))                          # right after the first trade of the next slot
                    o = rp.sim(tr, c, st, j, 0.5, EXC, fill_pen=0.015)
                    dg = rp.sim_dg(tr, c, st, j, 0.5, 0.3, 15, [], 10, 0.17, 20)
                    if o: r["c"] = dict(eos1=o["eos1"]["pnl"], hold5s=o["hold5s"]["pnl"], hold20s=o["hold20s"]["pnl"], ladder=dg[0], its=p["sol_result"], its_buy=p["buy_sol"])
        out[m] = r
    return out
if __name__ == "__main__":
    res = {}
    with Pool(12) as p:
        for o in p.imap_unordered(work, sorted(jobs)): res.update(o)
    json.dump(dict(res=res, keepK={K: [m for m, v in d.items() if v] for K, d in keepK.items()}), open(os.path.join(HERE, "sim_copy.json"), "w"))
    def halves(v):
        if not v: return "n 0"
        v = sorted(v); t0, t1 = v[0][0], v[-1][0]; mid = t0 + (t1 - t0) / 2
        tot = sum(x for _, x in v); a = sum(x for t, x in v if t < mid)
        return f"{tot:+7.2f} SOL ({a:+.2f} / {tot - a:+.2f})"
    print("\n(a) ORACLE: its snipe attempts at OUR landing, 0.5 SOL, sell end of next slot")
    for Lm in (45, 75):
        v = [(res[m]["bt"], res[m][f"a{Lm}"]) for m in cand_a if m in res and res[m].get(f"a{Lm}")]
        print(f"   L{Lm}: guard {halves([(t, x['g']) for t, x in v])} fills {sum(1 for _, x in v if x['fill'])}/{len(v)} | no guard {halves([(t, x['ng']) for t, x in v])} | outside buys ahead of us med {statistics.median([x['ahead'] for _, x in v]) if v else None}")
        v = [(res[m]["bt"], res[m][f"x{Lm}"]) for m in cand_a if m in res and res[m].get(f"x{Lm}")]
        print(f"   L{Lm} (its own trades removed): guard {halves([(t, x['g']) for t, x in v])} fills {sum(1 for _, x in v if x['fill'])}/{len(v)} | no guard {halves([(t, x['ng']) for t, x in v])}")
    print("\n(b) WALK-FORWARD creator list from its snipes (+ quality gate: drop after >= 3 of our fills averaging < 0)")
    for K in (1, 2):
        for Lm in (45, 75):
            ms = sorted((res[m]["bt"], m) for m in keepK[K] if keepK[K][m] and m in res and res[m].get(f"a{Lm}"))
            fills = collections.defaultdict(list); v = []; skipped = 0
            for bt, m in ms:
                cr = res[m]["creator"]; f = fills[cr]
                if len(f) >= 3 and statistics.mean(f) < 0: skipped += 1; continue
                x = res[m][f"a{Lm}"]; v.append((bt, x["g"]))
                if x["fill"]: f.append(x["g"])
            print(f"   K={K} L{Lm}: {halves(v)} fills {sum(1 for _, x in v if x != -0.005)}/{len(v)} (gate skipped {skipped}) | without gate: {halves([(bt, res[m][f'a{Lm}']['g']) for bt, m in ms])}")
            # same list, its own trades removed from the path (if it were not there): conservative
            ms2 = sorted((res[m]["bt"], m) for m in keepK[K] if keepK[K][m] and m in res and res[m].get(f"x{Lm}"))
            fills = collections.defaultdict(list); v2 = []
            for bt, m in ms2:
                f = fills[res[m]["creator"]]
                if len(f) >= 3 and statistics.mean(f) < 0: continue
                x = res[m][f"x{Lm}"]; v2.append((bt, x["g"]))
                if x["fill"]: f.append(x["g"])
            print(f"   K={K} L{Lm} (its own trades removed): {halves(v2)} fills {sum(1 for _, x in v2 if x != -0.005)}/{len(v2)}")
    print("\n(c) its LATER buys copied one slot later, 0.5 SOL (R1 + R2)")
    v = [(res[m]["bt"], res[m]["c"]) for m in cand_c if m in res and res[m].get("c")]
    for ex in ("eos1", "hold5s", "hold20s", "ladder"):
        print(f"   exit {ex:8}: {halves([(t, x[ex]) for t, x in v])} n {len(v)} win {sum(1 for _, x in v if x[ex] > 0) / max(1, len(v)):.0%} | without its best 5 tokens: {sum(sorted(x[ex] for _, x in v)[:-5]):+.2f}")
    for run in ("R1", "R2"):
        vv = [(res[m]["bt"], res[m]["c"]) for m in cand_c if m in res and res[m].get("c") and res[m]["run"] == run]
        print(f"   {run}: eos1 {halves([(t, x['eos1']) for t, x in vv])} | ladder {halves([(t, x['ladder']) for t, x in vv])} | its own result on these {sum(x['its'] for _, x in vv):+.2f} SOL (its size med {statistics.median([x['its_buy'] for _, x in vv]) if vv else 0:.2f})")
