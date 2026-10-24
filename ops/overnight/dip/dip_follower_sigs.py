#!/usr/bin/env python3
# Follower buys of model-selected dips (top 5%, both directions, entry 35 ms): every successful buy in the 8 slots after our
# modelled entry -> {mint: [sig, ...]} for core/slip_fetch.py (decodes each buy's real slippage limit). Skips sigs already fetched.
import sys, os, json, gzip, collections
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry"); os.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/dip")
import dipbuy4 as D
done = set()
for l in open("/home/moiz/sniper/ops/overnight/core/slip_args.jsonl"):
    try: done.add(json.loads(l)["sig"])
    except Exception: pass
S = json.load(open("/home/moiz/sniper/ops/overnight/dip/sel_x_35_8_R1toR2.json")) + json.load(open("/home/moiz/sniper/ops/overnight/dip/sel_x_35_8_R2toR1.json"))
sel = [r for r in S if r["score"] >= r["thr5"]]
bym = collections.defaultdict(list)
for r in sel: bym[r["m"]].append(r["age"])
byb = collections.defaultdict(set)
for m in bym: byb[(D.L[m]["run"], D.rp.bucket(m))].add(m)
out = collections.defaultdict(list); n_ev = 0
for key in sorted(byb):
    run, b = key
    for m, tr in D.rp.read_bucket(run, b, byb[key]).items():
        S0 = D.L[m]["slot"]
        for age in bym[m]:
            k = next((k for k, t in enumerate(tr) if (not t["buy"]) and t["sol"] >= 1e9 and round((t["s"] - S0) * D.SMS / 1000, 2) == age), None)
            if k is None: continue
            n_ev += 1; a0 = D.arr(tr[k]); ke = k + 1
            while ke < len(tr) and D.arr(tr[ke]) < a0 + 35: ke += 1
            s_in = tr[ke - 1]["s"] if ke - 1 >= 0 else tr[k]["s"]
            for t in tr[ke:]:
                if t["s"] > s_in + 8: break
                if t["buy"] and t["sig"] not in done and t["sig"] not in out[m]: out[m].append(t["sig"])
json.dump(out, open("/home/moiz/sniper/ops/overnight/dip/dip_follower_sigs.json", "w"))
print("events", n_ev, "launches", len(out), "follower buy sigs to fetch", sum(len(v) for v in out.values()))
