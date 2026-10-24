#!/usr/bin/env python3
# Follower buys of the CURRENT picks (out-of-fold top 5% from dipcv.py SEL_OUT: spacing 5, 2-slot exit, entries 35/50/75/100 ms):
# every successful buy from the trigger up to 6 slots after it (covers our landing slot plus a 2- or 4-slot hold) whose real
# slippage limit is not decoded yet -> {mint: [sig, ...]} for core/slip_fetch.py. Closes the coverage gap the checker found
# (only ~35% of these followers had a real limit). Local data only.
# usage: python3 -I follower_sigs2.py sel_oof_slow.jsonl sel_oof_real.jsonl -> dip/follower_sigs2.json
import sys, os, json, collections
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry"); os.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/dip")
import dipbuy4 as D
done = set()
for l in open("/home/moiz/sniper/ops/overnight/core/slip_args.jsonl"):
    try: done.add(json.loads(l)["sig"])
    except Exception: pass
bym = collections.defaultdict(set)
for f in sys.argv[1:]:
    for l in open(f):
        r = json.loads(l); bym[r["m"]].add(r["age"])
byb = collections.defaultdict(set)
for m in bym: byb[(D.L[m]["run"], D.rp.bucket(m))].add(m)
out = collections.defaultdict(list); n_ev = 0; n_all = 0
for key in sorted(byb):
    run, b = key
    for m, tr in D.rp.read_bucket(run, b, byb[key]).items():
        S0 = D.L[m]["slot"]
        for k, t in enumerate(tr):
            if t["buy"] or t["sol"] < D.MIN_SELL or round((t["s"] - S0) * D.SMS / 1000, 2) not in bym[m]: continue
            n_ev += 1
            for x in tr[k + 1:]:
                if x["s"] > t["s"] + int(os.environ.get("WIN", "6")): break
                if x["buy"]:
                    n_all += 1
                    if x["sig"] not in done and x["sig"] not in out[m]: out[m].append(x["sig"])
json.dump(out, open(os.environ.get("FOL_OUT", "/home/moiz/sniper/ops/overnight/sel/follower_sigs_sel.json"), "w"))
print("pick events", n_ev, "follower buys in window", n_all, "to fetch", sum(len(v) for v in out.values()))
