#!/usr/bin/env python3
# A few real HkQ7hMjy dip trades (R2) with signatures: the big sell, its buy right after, its sell; real PnL.
import sys, os, json, gzip, glob, collections, random
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry"); os.environ["RP_REPAIR"] = "0"
import rp
U = "HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ"
ms = set()
for f in glob.glob("/home/moiz/sniper/ops/overnight/census/parts/R2_*.jsonl.gz"):
    for l in gzip.open(f, "rt"):
        if l[2:10] == "HkQ7hMjy": ms.add(json.loads(l)[1])
L = rp.load_launches(); rnd = random.Random(3)
pick = sorted(ms); rnd.shuffle(pick); out = []
byb = collections.defaultdict(set)
for m in pick[:300]: byb[rp.bucket(m)].add(m)
for b in sorted(byb):
    tra = rp.read_bucket("R2", b, byb[b])
    for m, tr in tra.items():
        for k, t in enumerate(tr):
            if t["user"] != U or not t["buy"] or k == 0: continue
            p = tr[k - 1]
            if p["buy"] or p["sol"] < 1e9 or p["s"] != t["s"]: continue
            ks = next((j for j in range(k + 1, len(tr)) if tr[j]["user"] == U), None)
            if ks is None or tr[ks]["buy"]: continue
            fr = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
            out.append(dict(name=L[m].get("name"), mint=m, created_pkt=rp.__dict__.get("x") or "", bt=L[m]["bt"], age_s=round((t["s"] - L[m]["slot"]) * 0.212, 1),
                            sell_sig=p["sig"], seller=p["user"], sell_sol=round(p["sol"] / 1e9, 3), buy_sig=t["sig"], buy_sol=round(t["sol"] / 1e9, 3),
                            exit_sig=tr[ks]["sig"], exit_sol=round(tr[ks]["sol"] / 1e9, 3), hold_slots=tr[ks]["s"] - t["s"],
                            pnl=round(tr[ks]["sol"] * (1 - fr) / 1e9 - t["sol"] * (1 + fr) / 1e9, 4)))
            break
json.dump(out, open("/home/moiz/sniper/ops/overnight/census/hk_examples.json", "w"))
import time
for r in sorted(out, key=lambda r: -r["pnl"])[:4] + sorted(out, key=lambda r: r["pnl"])[:2]:
    print(time.strftime("%m-%d %H:%M", time.gmtime(r["bt"] + 18000)), r["name"], r["age_s"], "s | sell", r["sell_sol"], r["seller"][:8], "| buy", r["buy_sol"], "| exit", r["exit_sol"], "after", r["hold_slots"], "slots | pnl", r["pnl"])
print(len(out), "examples")
