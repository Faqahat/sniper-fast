#!/usr/bin/env python3
"""SIZE_48H step 3 (read-only, offline): the newest 48 h of chain recording (s48/hours48.json, bins >= 95% recorded) replayed
with probe-3 settings (whale >= 6%, k 8, helius-ps 30/s path + global, limit 0.88 x the latest seen price, deadline +1, window
10 slots, exit 2 slots / TP 10% / SL 20%, one position) and the probe-3-calibrated landing (P3 donor windows), at several
sizes. Size changes only what it changes on chain: our buy's tokens on the curve, the price move our buy makes (followers whose
slippage it breaks are dropped; the TP / SL value of our tokens), our sell's impact, and pump's fees (a share of size).
The fill rule does not change with size: the engine's min-out is the buy of `spend` at the 0.88 x price state
(src/presend_live.rs limit_min_out), so a try fills iff the curve price where it executes is <= the limit, at any size.
No 100-fill / 0.1-SOL caps here (see --caps in the report step).
usage: size48.py [--draws 40] [--sizes 0.35,0.5,0.75,1.0] [--cuts 0,0.2,0.3] [--pool P3|P123|P12] [--tag main] [--procs 14]"""
import sys, os, json, pickle, argparse, collections, time
import numpy as np
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s48lib
s48lib.use_tab48()
import rlib, sim, variants, p3check

G = {}

def prepare(tp):
    H = json.load(open(f"{s48lib.S48}/hours48.json"))
    use = {x["t0"]: x for x in H["use"]}
    trig = pickle.load(open(f"{s48lib.S48}/trig_6.pkl", "rb"))
    wins = []
    for d in trig:
        b = use.get(d["bt"] // 600 * 600)
        if b is None: continue
        ws = None
        if d["sells"]:
            k = d["sells"][0]; ws = (int(tp.s[k]), int(tp.i[k]))
        wins.append(dict(mint=d["mint"], slot=d["slot"], idx=d["idx"], j=d["j"], age_slots=d["age_slots"], v2=d["v2"], cashback=d["cashback"],
                         whale=d["whale"], whale_sell=ws, pred=None, quick=0, bt=d["bt"], half=1, pct=d["pct"]))
    armable = [w for w in wins if w["age_slots"] > 0 and w["v2"] and not w["cashback"]]
    return H, wins, armable

def one(job):
    size, cut, seed = job
    cfg = p3check.cfg_p3(G["slot_ms"], size=int(round(size * 1e9)), D=G["D"]); cfg.follower_cut = cut
    rng = np.random.default_rng(seed)
    res = sim.run(G["ck"], G["store"], G["armable"], cfg, G["land"], G["model"], G["view"], rng)
    rows = []
    for r in res:
        if not r["armed"]: continue
        rows.append((r["trig"]["bt"], int(r.get("filled", False)), int(r.get("net", 0)), int(r.get("pnl", 0)), int(r.get("fees", 0)), r.get("exit") or "",
                     r["trig"]["mint"], r.get("fill_S")))
    return size, cut, seed, rows

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--draws", type=int, default=40); ap.add_argument("--sizes", default="0.35,0.5,0.75,1.0"); ap.add_argument("--cuts", default="0,0.2,0.3")
    ap.add_argument("--pool", default="P3"); ap.add_argument("--tag", default="main"); ap.add_argument("--procs", type=int, default=14)
    A = ap.parse_args()
    t0 = time.time()
    tp = s48lib.Tape48()
    D = pickle.load(open(f"{s48lib.S48}/donors123.pkl", "rb")); G["D"] = D
    G["slot_ms"] = json.load(open(f"{s48lib.S48}/p3check.json"))["slot_ms"]
    G["land"] = sim.Landing(D, probes=tuple(["P" + c for c in A.pool[1:]]))
    G["model"] = s48lib.ModelN(D, tp, ("P1", "P2", "P3")); G["view"] = sim.View(); G["ck"] = tp.clock()
    H, wins, armable = prepare(tp)
    G["armable"] = armable
    G["store"] = sim.build_store(tp, variants.spans_for(armable))
    tp.slim()
    print(f"window {rlib.pkt(H['start'])} -> {rlib.pkt(H['end'])} PKT, {H['hours']:.2f} usable hours; triggers {len(wins)}, armable {len(armable)}; "
          f"landing pool {A.pool} ({len(G['land'].L)} donor windows); pace slot {G['slot_ms']:.1f} ms; prep {time.time() - t0:.0f} s", flush=True)
    import gc; gc.collect()
    sizes = [float(x) for x in A.sizes.split(",")]; cuts = [float(x) for x in A.cuts.split(",")]
    jobs = [(s, c, 300 + d) for s in sizes for c in cuts for d in range(A.draws)]
    R = collections.defaultdict(list)
    with Pool(A.procs) as p:
        for size, cut, seed, rows in p.imap_unordered(one, jobs, chunksize=1):
            R[(size, cut)].append((seed, rows))
    pickle.dump(dict(R=dict(R), H=H, pool=A.pool, slot_ms=G["slot_ms"], n_armable=len(armable)), open(f"{s48lib.S48}/size48_{A.tag}.pkl", "wb"))
    for (size, cut), lst in sorted(R.items()):
        nets = [sum(r[2] for r in rows) / 1e9 for s, rows in lst]; fills = [sum(r[1] for r in rows) for s, rows in lst]
        print(f"size {size:.2f} cut {cut:.1f}: net {np.mean(nets):+.3f} SOL [p5 {np.percentile(nets, 5):+.3f}, p95 {np.percentile(nets, 95):+.3f}] fills {np.mean(fills):.0f}")
    print(f"done {time.time() - t0:.0f} s")
