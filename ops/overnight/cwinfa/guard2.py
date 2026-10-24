#!/usr/bin/env python3
# READ-ONLY, offline: CWiNFA's failed buys inside the collector windows, placed exactly by block position (slot, index):
# the curve state right before each failed tx -> price vs the post-bundle price and tokens 1 SOL would buy vs its min-out.
import os, sys, json, statistics, collections
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["RP_PHASEA_R2"] = os.path.join(HERE, "phaseA_snap")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
W = "CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J"
L = rp.load_launches(); LED = {r["sig"]: r for r in json.load(open(os.path.join(HERE, "ledger_CWiNFA.json")))["txs"] if not r.get("missing")}
C = json.load(open(os.path.join(HERE, "coll_cw.json")))
rows = []
byb = collections.defaultdict(set)
for m, v in C.items():
    if m in L and any(x[0] == "X" for x in v.get("rows", [])): byb[(v["run"], rp.bucket(m))].add(m)
for key, mm in byb.items():
    tra = rp.read_bucket(key[0], key[1], mm)
    for m, tr in tra.items():
        c = L[m]; st = rp.structure(tr, c); g = st["g_end"]
        if g < 1: continue
        ge = tr[g - 1]; p_b = ge["vsol"] / ge["vtok"]; fr = (tr[0]["fbps"] + tr[0]["cbps"]) / 1e4
        for x in C[m]["rows"]:
            if x[0] != "X" or x[12] != 1: continue
            r = LED.get(x[5])
            if not r or not r.get("router") or r["router"].get("tag") != 2: continue
            prev = [t for t in tr if (t["s"], t["i"]) < (x[2], x[3])]
            pre = prev[-1] if prev else ge
            X = int(1e9 / (1 + fr)); exp_tok = pre["vtok"] * X // (pre["vsol"] + X)
            ahead = len({t["sig"] for t in tr[g:len(prev)] if t["buy"] and t["user"] not in st["insiders"]}) if len(prev) >= g else 0
            rows.append(dict(m=m, sig=x[5], ds=x[2] - c["slot"], err=r["errname"], mult=(pre["vsol"] / pre["vtok"]) / p_b, tok_vs_min=exp_tok / r["router"]["min_out"], ahead=ahead,
                             cw_filled=bool(C[m].get("buy"))))
json.dump(rows, open(os.path.join(HERE, "guard_fails.json"), "w"))
q = lambda xs, p: sorted(xs)[int(p * (len(xs) - 1))]
print(f"failed buys placed by block position: {len(rows)} (errors {dict(collections.Counter(r['err'] for r in rows))})")
xs = [r["mult"] for r in rows]; ys = [r["tok_vs_min"] for r in rows]
print(f"  price right before the failed buy vs post-bundle price: p10 {q(xs, .1):.3f} median {statistics.median(xs):.3f} p90 {q(xs, .9):.3f}")
print(f"  tokens 1 SOL would buy there / its min-out: median {statistics.median(ys):.3f} (share < 1.0: {sum(y < 1 for y in ys) / len(ys):.0%})")
print(f"  slot delta of failed buys: {dict(collections.Counter(r['ds'] for r in rows))}; outside buys ahead median {statistics.median(r['ahead'] for r in rows)}")
print(f"  launch later filled by another CWiNFA tx: {sum(r['cw_filled'] for r in rows)}")
