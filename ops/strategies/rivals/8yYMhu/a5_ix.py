#!/usr/bin/env python3
"""8yYMhu a5 (read-only): instruction-level facts from the public-RPC sample (ixs.pkl): per landed buy / failed attempt, the Lighthouse
slot deadline vs the trigger slot, the vSOL band vs the trigger's post-sell curve, BuyV3 args (token amount, max SOL), CU limit/price,
tip relay/amount, durable nonce accounts (pool size, reuse), sells' args. Trigger = last outside sell >= 1 SOL before (att.pkl rule).
Out: DATA/a5.txt"""
import sys, os, pickle, collections, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, rlib as X
I = pickle.load(open(f"{X.D}/ixs.pkl", "rb")); A = {a["sig"]: a for a in pickle.load(open(f"{X.D}/att.pkl", "rb"))}
L = pickle.load(open(f"{X.D}/lots.pkl", "rb")); lot_by_sell = {l["sells"][0][0]: l for l in L}; lot_by_buy = {l["buy_sig"]: l for l in L}
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
buys = [v for v in I.values() if v["pump"] and v["lh"] and v["signer"] == X.W]
P(f"RPC-decoded buy-shaped txs (with Lighthouse + pump ix): {len(buys)}; landed {sum(v['err'] is None for v in buys)}, failed {sum(v['err'] is not None for v in buys)}")
rows = []
for v in buys:
    a = A.get(v["sig"])
    clock = [x for x in v["lh"] if x.get("t") == "clock"]; dat = [x for x in v["lh"] if x.get("t") == "data"]
    dl = clock[0]["value"] if clock else None; dl_op = clock[0]["op"] if clock else None
    lo = hi = None; offs = set()
    if dat:
        for off, val, op in dat[0]["asserts"]:
            offs.add(off)
            if op == 4: lo = val / 1e9
            if op == 5: hi = val / 1e9
    args = v["pump"][0]["args"]; disc = v["pump"][0]["disc"]
    r = dict(sig=v["sig"], ok=v["err"] is None, err=json.dumps(v["err"])[-22:] if v["err"] else "", slot=v["slot"], dl=dl, dl_op=dl_op, lo=lo, hi=hi, offs=tuple(sorted(offs)),
             tok_arg=args[0] if args else None, max_sol=(args[1] / 1e9 if len(args) > 1 else None), disc=disc, cul=v["cul"], cup=v["cup"], ldl=v["ldl"],
             tips=v["tips"], nonce=v["nonce"], fee=v["fee"], seed=v["seed"])
    if a and "trig_slot" in a:
        r.update(trig_slot=a["trig_slot"], trig_vsol=a["trig_vsol_after"], trig_sol=a["trig_sol"], out=a["out"])
    if r["ok"]:
        l = lot_by_buy.get(v["sig"])
        if l: r.update(cost=l["cost"], sol_curve=l["sol_curve"], vsol_before=l["vsol_before"], tok=l["tok"])
    rows.append(r)
R = [r for r in rows if r.get("trig_slot") is not None and r["dl"] is not None]
P(f"with trigger + deadline decoded: {len(R)}")
P("deadline slot - trigger slot: " + str(collections.Counter(r["dl"] - r["trig_slot"] for r in R).most_common(6)))
P("deadline op codes: " + str(collections.Counter(r["dl_op"] for r in R)) + "; landed slot - deadline (landed): " + str(collections.Counter(r["slot"] - r["dl"] for r in R if r["ok"]).most_common(5)) +
  "; (6001 late): " + str(collections.Counter(r["slot"] - r["dl"] for r in R if "6001" in r["err"]).most_common(5)))
P("band asserts: offsets " + str(collections.Counter(r["offs"] for r in R)))
lo = np.array([r["lo"] / r["trig_vsol"] for r in R if r["lo"]]); hi = np.array([r["hi"] / r["trig_vsol"] for r in R if r["hi"]])
P(f"band lo / trigger post-sell vSOL p5/25/50/75/95 = " + "/".join(f"{X.pct(lo,q):.4f}" for q in (5, 25, 50, 75, 95)))
P(f"band hi / trigger post-sell vSOL p5/25/50/75/95 = " + "/".join(f"{X.pct(hi,q):.4f}" for q in (5, 25, 50, 75, 95)))
# hi vs pre-sell vSOL
hp = np.array([(r["hi"] - r["trig_vsol"]) / r["trig_sol"] for r in R if r["hi"] and r["trig_sol"]])
P(f"(hi - post) / trigger sell SOL p10/50/90 = " + "/".join(f"{X.pct(hp,q):.3f}" for q in (10, 50, 90)))
# landed: where did the curve sit vs band
Lr = [r for r in R if r["ok"] and r.get("vsol_before")]
pos = np.array([(r["vsol_before"] - r["lo"]) / (r["hi"] - r["lo"]) for r in Lr])
P(f"landed buys: curve vSOL just before his buy inside the band at position p10/50/90 = " + "/".join(f"{X.pct(pos,q):.2f}" for q in (10, 50, 90)) + " (0 = lo, 1 = hi)")
ms = np.array([r["max_sol"] for r in Lr]); sc = np.array([r["sol_curve"] for r in Lr])
P(f"BuyV3 max SOL p10/50/90 = {X.pct(ms,10):.4f}/{X.med(ms):.4f}/{X.pct(ms,90):.4f}; spent (curve) p10/50/90 {X.pct(sc,10):.4f}/{X.med(sc):.4f}/{X.pct(sc,90):.4f}; max/spent p50 {X.med(ms/sc):.3f}")
# implied target SOL at the trigger price: tokens * price at post-trigger curve
k_tok = []
for r in Lr:
    V = r["trig_vsol"] * 1e9; k = V * (32190000000000000000000000.0 / V) if False else None
P("pump discriminators: " + str(collections.Counter(r["disc"] for r in rows)))
P("CU limit p10/50/90: " + "/".join(f"{X.pct([r['cul'] for r in rows if r['cul']], q):.0f}" for q in (10, 50, 90)) +
  "; CU price p10/50/90: " + "/".join(f"{X.pct([r['cup'] for r in rows if r['cup']], q):.0f}" for q in (10, 50, 90)) +
  "; loaded-data limit: " + str(collections.Counter(r["ldl"] for r in rows).most_common(3)))
P("tips in buy-shaped txs (relay: count, lamports p50): " + ", ".join(f"{k} {len(v)} {int(np.median(v))}" for k, v in sorted(
    collections.defaultdict(list, {**{}}).items())) )
tipc = collections.defaultdict(list)
for r in rows:
    if r["tips"]:
        for acc, lam, rel in r["tips"]: tipc[rel].append(lam)
    else: tipc["(no tip ix)"].append(0)
P("   " + ", ".join(f"{k}: {len(v)} txs, p50 {int(np.median(v))} lamports" for k, v in sorted(tipc.items(), key=lambda kv: -len(kv[1]))))
tl = collections.Counter((r["tips"][0][2] if r["tips"] else "(none)", r["ok"]) for r in rows)
P("   landed vs failed by copy: " + ", ".join(f"{k[0]}/{'ok' if k[1] else 'fail'} {n}" for k, n in sorted(tl.items(), key=lambda kv: -kv[1])))
# nonce pool
na = collections.Counter(r["nonce"] for r in rows if r["nonce"])
P(f"durable nonce accounts in the sample: {len(na)} distinct over {sum(na.values())} buy-shaped txs; top uses {na.most_common(3)}")
# sells
sells = [v for v in I.values() if v["pump"] and not v["lh"] and v["signer"] == X.W and v["err"] is None and any("Sell" in x for x in v["ixn"])]
P(f"RPC-decoded sells: {len(sells)}; args (token amount, min SOL out) min_sol_out==0 share {np.mean([s['pump'][0]['args'][1]==0 for s in sells if len(s['pump'][0]['args'])>1]):.2f}; "
  f"nonce on sells {np.mean([s['nonce'] is not None for s in sells]):.2f}; tips {collections.Counter((s['tips'][0][2] if s['tips'] else '(none)') for s in sells).most_common(6)}")
sn = collections.Counter(s["nonce"] for s in sells if s["nonce"]); P(f"   distinct nonce accounts on sells {len(sn)}; shared with buys {len(set(sn) & set(na))}")
same = 0; tot = 0
for s in sells:
    l = lot_by_sell.get(s["sig"])
    if l and l["buy_sig"] in I and I[l["buy_sig"]]["nonce"]:
        tot += 1; same += I[l["buy_sig"]]["nonce"] == s["nonce"]
P(f"   sell uses the same nonce account as its buy: {same}/{tot}")
pickle.dump(rows, open(f"{X.D}/a5.pkl", "wb"))
open(f"{X.D}/a5.txt", "w").write("\n".join(out) + "\n")
