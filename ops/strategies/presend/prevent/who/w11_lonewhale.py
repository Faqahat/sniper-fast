#!/usr/bin/env python3
"""WHO step 11 (coordinator question): T2 windows where the whale's buy is the ONLY buy in the last 50 slots (STATE's passing rule):
is there a wallet identity behind those whales? [MEASURED from the tapes; P&L @0.696]"""
import pickle, json, bisect, collections
import numpy as np
D = "/home/it/sniper-data/prevent/who"
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
W = pickle.load(open(f"{D}/windows.pkl", "rb")); F = pickle.load(open(f"{D}/feats.pkl", "rb")); M = pickle.load(open(f"{D}/mints.pkl", "rb"))
X = pickle.load(open(f"{D}/rules.pkl", "rb")); c1 = {(m["mint"], round(m["t"], 3)): m["C1"] for m in X["meta"]}
bots = json.load(open(f"{D}/bots.json"))
import re
coh = {c if isinstance(c, str) else c.get("wallet") for c in json.load(open("/home/it/sniper-data/overnight/sel/cohort_train.json"))}
cand = set(re.findall(r"gmgn\.ai/sol/address/([1-9A-HJ-NP-Za-km-z]{32,44})", open("/home/it/sniper/ops/snipers/CANDIDATES.md").read()))
botset = coh | cand | set(bots["rivals"].values())
rows = []
for w, f in zip(W, F):
    if w["mode"] != "live" or w["kind"] != "t2" or "hold" not in f: continue
    T = M.get(w["mint"]) or []
    ks = [(r[0], r[1]) for r in T]
    k = bisect.bisect_left(ks, (w["trig_slot"], w["trig_idx"]))
    prev = [r for r in T[:k] if r[0] >= w["trig_slot"] - 50 and r[8] not in OURS]
    nb = sum(1 for r in prev if r[3]); ntr = len(prev)
    last = T[k - 1][0] if k > 0 else None
    gap = (w["trig_slot"] - last) if last is not None else None
    lone = nb == 0
    sc = w["pnl"] * 0.696 / (w["spend"] / 1e9) if w.get("filled") else None
    rows.append(dict(run=w["run"], mint=w["mint"], whale=w["wallet"], lone=lone, gap=gap, age=w["age"], filled=bool(w.get("filled")), pnl=sc,
                     fee=(w.get("fee_fail") or 0) / 1e9, creator=f.get("creator"), cr_pct=f.get("creator_pct", 0), bot=w["wallet"] in botset,
                     c1=c1.get((w["mint"], round(w["t_arm"], 3))), whale_is_prev_holder=f.get("trig_sold_before", 0) > 0.05,
                     vsol=None))
L = [r for r in rows if r["lone"]]; O = [r for r in rows if not r["lone"]]
fl = lambda R: [r for r in R if r["filled"]]
print(f"live T2 windows {len(rows)}; lone-whale (no other buy in the 50 slots before the trigger) {len(L)} ({len(L) / len(rows) * 100:.1f}%)")
for nm, R in (("lone", L), ("other", O)):
    F_ = fl(R)
    print(f"  {nm:5s} fills {len(F_):4d} pnl@.696 {sum(r['pnl'] for r in F_):+7.2f} mean {np.mean([r['pnl'] for r in F_]) * 1000 if F_ else 0:+6.1f} mSOL  big-loss {np.mean([r['pnl'] < -0.05 for r in F_]) * 100 if F_ else 0:4.1f}%  "
          f"fees {sum(r['fee'] for r in R):.3f}  age median {np.median([r['age'] for r in R]):.0f} slots  whale in bot lists {np.mean([r['bot'] for r in R]) * 100:.0f}%  "
          f"whale dumps24h median {np.median([r['c1'] for r in R if r['c1'] is not None]):.0f}  creator holds>=3% {np.mean([r['cr_pct'] >= 3 for r in R]) * 100:.0f}%  whale had sold this token before {np.mean([r['whale_is_prev_holder'] for r in R]) * 100:.0f}%")
cw = collections.Counter(r["whale"] for r in L)
print(f"  lone windows: {len(cw)} distinct whales; top 10 whales = {sum(v for _, v in cw.most_common(10)) / len(L) * 100:.0f}% of lone windows")
print("  top lone whales: wallet  lone-windows  lone-fills pnl | same whale in non-lone windows: fills pnl | bot | dumps24h median")
for u, n in cw.most_common(12):
    a = [r for r in L if r["whale"] == u]; b = [r for r in O if r["whale"] == u]
    print(f"   {u[:8]} {n:4d} {len(fl(a)):4d} {sum(r['pnl'] for r in fl(a)):+6.3f} | {len(fl(b)):4d} {sum(r['pnl'] for r in fl(b)):+6.3f} | {u in botset} | {np.median([r['c1'] or 0 for r in a]):.0f}")
cc = collections.Counter(r["creator"] for r in L)
print(f"  lone windows: {len(cc)} distinct creators; top creators: " + ", ".join(f"{(c or '?')[:8]} {v}" for c, v in cc.most_common(6)))
# gap/age split
for lo, hi in ((0, 149), (150, 1499), (1500, 10 ** 9)):
    R = [r for r in fl(L) if lo <= r["age"] <= hi]
    print(f"  lone fills with token age {lo}-{hi} slots: {len(R)} pnl {sum(r['pnl'] for r in R):+.3f}")
json.dump({"n_lone": len(L), "n": len(rows), "top_whales": cw.most_common(20)}, open(f"{D}/lonewhale.json", "w"), indent=1)
FL = fl(L)
cf = collections.Counter(r["whale"] for r in FL)
print(f"  lone FILLS: {len(FL)} fills, {len(cf)} distinct whales; most fills by one whale = {cf.most_common(1)}; whales with >=2 lone fills: {sum(1 for v in cf.values() if v >= 2)}")
crf = collections.Counter(r["creator"] for r in FL)
print("  lone fills by creator (top): " + ", ".join(f"{(c or '?')[:8]} {v} ({sum(r['pnl'] for r in FL if r['creator'] == c):+.3f})" for c, v in crf.most_common(5)))
print(f"  lone fills whale in bot lists: {sum(r['bot'] for r in FL)} ({sum(r['pnl'] for r in FL if r['bot']):+.3f}) vs not {sum(not r['bot'] for r in FL)} ({sum(r['pnl'] for r in FL if not r['bot']):+.3f})")
