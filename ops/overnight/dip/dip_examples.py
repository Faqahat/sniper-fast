#!/usr/bin/env python3
# A few model-selected dip trades (top 5%, model trained on the other run, entry 35 ms, exit 4 slots) with on-chain links:
# the big sell, the trade we land right behind, the trade our sell lands in front of; prices vs the post-sell price; PnL.
import sys, os, json, gzip, random, collections
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry"); os.environ["RP_REPAIR"] = "1"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/dip")
import dipbuy4 as D
SMS = D.SMS
S = json.load(open("/home/moiz/sniper/ops/overnight/dip/sel_x_35_8_R1toR2.json")) + json.load(open("/home/moiz/sniper/ops/overnight/dip/sel_x_35_8_R2toR1.json"))
sel = [r for r in S if r["score"] >= r["thr5"]]
E4 = {}
for l in gzip.open("/home/moiz/sniper/ops/overnight/dip/ev4_b05.jsonl.gz", "rt"):
    r = json.loads(l); E4[(r["m"], r["age"])] = r
sel = [r for r in sel if (r["m"], r["age"]) in E4 and "35" in E4[(r["m"], r["age"])]["pnl"]]
rnd = random.Random(5); rnd.shuffle(sel)
wins = [r for r in sel if E4[(r["m"], r["age"])]["pnl"]["35"]["4"] > 0][:4]; losses = [r for r in sel if E4[(r["m"], r["age"])]["pnl"]["35"]["4"] <= 0][:2]
out = []
for r in wins + losses:
    m = r["m"]; c = D.L[m]; key = (c["run"], D.rp.bucket(m))
    tr = D.rp.read_bucket(c["run"], D.rp.bucket(m), {m})[m]
    k = next(k for k, t in enumerate(tr) if (not t["buy"]) and not t.get("syn") and t["sol"] >= 1e9 and round((t["s"] - c["slot"]) * SMS / 1000, 2) == r["age"])
    t = tr[k]; a0 = D.arr(t); ke = k + 1
    while ke < len(tr) and D.arr(tr[ke]) < a0 + 35: ke += 1
    s_in = tr[ke - 1]["s"]; ks = ke
    while ks < len(tr) and not (tr[ks]["s"] >= s_in + 4 and (tr[ks]["s"] > s_in + 4 or (tr[ks]["i"] / max(D.SS.get(tr[ks]["s"], 400), tr[ks]["i"] + 1)) * SMS >= 75)): ks += 1
    p_after = t["vsol"] / t["vtok"]
    out.append(dict(name=c.get("name"), mint=m, created=c["bt"], age=r["age"], sell_sig=t["sig"], sell_sol=round(t["sol"] / 1e9, 3), seller=t["user"],
                    ahead=ke - k - 1, after_sig=tr[ke - 1]["sig"], entry_px=round((tr[ke - 1]["vsol"] / tr[ke - 1]["vtok"]) / p_after, 4),
                    exit_before_sig=tr[ks]["sig"] if ks < len(tr) else None, exit_px=round((tr[ks - 1]["vsol"] / tr[ks - 1]["vtok"]) / p_after, 4),
                    buyers_between=sum(1 for x in tr[ke:ks] if x["buy"]), pnl=E4[(m, r["age"])]["pnl"]["35"]["4"]))
json.dump(out, open("/home/moiz/sniper/ops/overnight/dip/dip_examples.json", "w"))
import time
for o in out: print(time.strftime("%m-%d %H:%M", time.gmtime(o["created"] + 18000)), o["name"], "age", o["age"], "sell", o["sell_sol"], "| ahead", o["ahead"], "entry", o["entry_px"], "| exit", o["exit_px"], "buyers", o["buyers_between"], "| pnl", o["pnl"])
