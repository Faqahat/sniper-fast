#!/usr/bin/env python3
# Trigger transactions of dip events: for each event (mint, age, seller prefix) find the big sell that triggered it in the
# collected trade rows -> its signature, signer, slot, index. Inputs: out-of-fold picks from dipcv.py (SEL_OUT) and/or an
# event file (a random share of all events, for the population baseline). Local data only; no RPC.
# usage: python3 -I trig_sigs.py OUT.jsonl sel_oof_slow.jsonl [sel_oof_real.jsonl] [--all ev_busy5_slow.jsonl.gz 0.1]
import sys, os, json, gzip, random, collections
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry"); os.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/dip")
import dipbuy4 as D
out_path = sys.argv[1]; args = sys.argv[2:]
EV = []
while args:
    a = args.pop(0)
    if a == "--all":
        f = args.pop(0); share = float(args.pop(0)); rnd = random.Random(5)
        for l in gzip.open(f, "rt"):
            r = json.loads(l)
            if rnd.random() < share: EV.append(dict(m=r["m"], run=r["run"], bt=r["bt"], age=r["age"], seller=r["seller"], sell=r["sell"], src="all",
                                                    pnl={L: v.get("2") for L, v in r["pnl"].items()}, px=r.get("px", {})))
    else:
        for l in open(a):
            r = json.loads(l); r["src"] = "oof_L" + r["LAT"]; EV.append(r)
print("events", len(EV), collections.Counter(e["src"] for e in EV), flush=True)
byb = collections.defaultdict(set)
for e in EV: byb[(e["run"], D.rp.bucket(e["m"]))].add(e["m"])
bym = collections.defaultdict(list)
for e in EV: bym[e["m"]].append(e)
n_ok = 0
with open(out_path, "w") as fo:
    for key in sorted(byb):
        run, b = key
        for m, tr in D.rp.read_bucket(run, b, byb[key]).items():
            S0 = D.L[m]["slot"]
            for e in bym[m]:
                k = next((k for k, t in enumerate(tr) if (not t["buy"]) and t["sol"] >= D.MIN_SELL and t["user"].startswith(e["seller"])
                          and round((t["s"] - S0) * D.SMS / 1000, 2) == e["age"]), None)
                if k is None: e["sig"] = None
                else:
                    t = tr[k]; n_ok += 1
                    e.update(sig=t["sig"], user=t["user"], payer=t["payer"], s=t["s"], i=t["i"], sol=t["sol"], dslot=t["s"] - S0,
                             tips=t.get("tips"), fee=t.get("fee"), slotpos=round(t["i"] / max(D.SS.get(t["s"], 400), t["i"] + 1), 3))
                    a0 = D.arr(t); fol = []
                    for x in tr[k + 1:k + 13]:          # who traded right after the trigger (same or next slot): proxy delay in ms
                        if x["s"] > t["s"] + 1: break
                        fol.append([x["user"][:8], int(x["buy"]), round(x["sol"] / 1e9, 3), round(D.arr(x) - a0, 1), x["s"] - t["s"], x["sig"]])
                    e["fol"] = fol
                fo.write(json.dumps(e) + "\n")
print("matched", n_ok, "of", len(EV))
