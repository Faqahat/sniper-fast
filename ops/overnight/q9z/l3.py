#!/usr/bin/env python3
# READ-ONLY, offline paper replay: L3 = the generic momentum trigger restricted to what 9qz7cW's later picks look like AT
# DECISION TIME (no look-ahead): age >= 15 s (<= 300 s), price >= 1.30x the post-bundle price, curve vsol 38-65 SOL, last 10 s
# net inflow >= 3 SOL from >= 8 buys, deployer with >= 20 prior launches (known at create). Thresholds come from its picks
# vs skips (later_dive.txt), so this is in-sample for the feature choice: judge by halves and by R1 vs R2.
# Same fill / costs / robustness variants as later_strat.py. -> l3.txt
import sys, os, json, collections, statistics, gzip
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/q9z"); sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import later_strat as LS
import rp
from multiprocessing import Pool
TB = {}
for l in gzip.open("/home/moiz/sniper-data/collect/paper/table_dump.jsonl.gz", "rt"):
    r = json.loads(l)
    try: TB[r["mint"]] = float(r.get("cr_prior_n"))
    except (TypeError, ValueError): TB[r["mint"]] = None
def trig3(tr, st, S, m):
    if (TB.get(m) or 0) < 20: return None
    ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; j0 = 0
    for k in range(st["g_end"], len(tr)):
        t = tr[k]; age = (t["s"] - S) * 0.212
        if age < 15: continue
        if age > 300: return None
        if not (38e9 <= t["vsol"] <= 65e9) or (t["vsol"] / t["vtok"]) / p_b < 1.30: continue
        while tr[j0]["s"] < t["s"] - 47: j0 += 1
        win = tr[j0:k + 1]
        if sum(1 for x in win if x["buy"]) >= 8 and sum((x["sol"] if x["buy"] else -x["sol"]) for x in win) >= 3e9: return k
    return None
def work(job):
    run, b = job; tra = rp.read_bucket(run, b, LS.jobs[job]); out = {}
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = LS.L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        k = trig3(tr, st, c["slot"], m)
        if k is None: continue
        rec = {}
        for lag, lab in ((1, "300ms"), (2, "500ms")):
            idx = LS.entry_after(tr, tr[k]["s"], lag)
            if idx is None or idx >= len(tr): continue
            rec[lab] = dict(base=LS.score(tr, c, st, idx), pen1=LS.score(tr, c, st, idx, pen=0.01), fs=LS.score(tr, c, st, idx, drop=LS.FS),
                            slip=LS.score(tr, c, st, idx, slip=LS.SLIP), fs_slip=LS.score(tr, c, st, idx, drop=LS.FS, slip=LS.SLIP),
                            after=sorted(LS.after_buyers(tr, idx, tr[idx - 1]["s"] + 95)))
        p = LS.PL.get(m)
        out[m] = dict(bt=c["bt"], run=run, its=bool(p and p["beh"] == "later"), r=rec)
    return out
if __name__ == "__main__":
    res = {}
    with Pool(12) as pool:
        for o in pool.imap_unordered(work, sorted(LS.jobs)): res.update(o)
    lines = []
    def P(x): print(x, flush=True); lines.append(x)
    cnt = collections.Counter()
    for v in res.values():
        r = v["r"].get("300ms")
        if r: cnt.update(r["after"])
    top = frozenset(w for w, _ in cnt.most_common(10))
    P(f"L3 entries: {len(res)} (its later picks among them: {sum(1 for v in res.values() if v['its'])}); top-10 after-us buyers {[w[:6] for w in top]}")
    for lab in ("300ms", "500ms"):
        rows = [(v["bt"], v["run"], v["r"][lab]) for v in res.values() if lab in v["r"] and v["r"][lab]["base"]]
        P(f"\n== L3_{lab}: n {len(rows)} (R1 {sum(1 for _, r, _ in rows if r == 'R1')}, R2 {sum(1 for _, r, _ in rows if r == 'R2')})")
        for ex in ("eos1", "hold5s", "hold20s", "ladder", "ladder_stop0.9"):
            cells = []
            for var in ("base", "pen1", "fs", "slip", "fs_slip"):
                v = sorted((bt, x[var][ex]) for bt, _, x in rows if x.get(var) and x[var].get(ex) is not None)
                if not v: continue
                mid = v[0][0] + (v[-1][0] - v[0][0]) / 2; tot = sum(y for _, y in v); a = sum(y for t, y in v if t < mid)
                cells.append(f"{var} {tot:+.2f} ({a:+.1f}/{tot - a:+.1f})")
            P(f"   {ex:15} " + " | ".join(cells))
        for run_ in ("R1", "R2"):
            w = [x["base"]["ladder"] for _, r, x in rows if r == run_]
            P(f"   {run_}: ladder base {sum(w):+.2f} (n {len(w)}, win {sum(1 for y in w if y > 0) / max(1, len(w)):.0%})")
    open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "l3.txt"), "w").write("\n".join(lines) + "\n")
