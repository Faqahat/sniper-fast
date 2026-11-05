#!/usr/bin/env python3
"""Sanity check: the landing model + replay on the 81 live attempts vs realized P&L."""
import json, pickle, collections, numpy as np
RD = "/home/moiz/sniper-data/apex2/realism"
live = json.load(open(f"{RD}/live_tape.json")); S = {r[0]: r for r in pickle.load(open(f"{RD}/sim3/LIVE.pkl", "rb"))}
ev = collections.defaultdict(dict)
for r in ("r10", "r11", "r13", "r14"):
    for l in open(f"/home/moiz/sniper-data/apex2/probes/apex_{r}.jsonl"):
        x = json.loads(l)
        if "id" in x: ev[(r, x["id"])].setdefault(x["ev"], x)
CR_REAL = []; CT_REAL = collections.defaultdict(list); rows = []
for x in live:
    d = ev[(x["run"], x["id"])]; s = S[x["mint"]]
    pnl = d["realized"]["pnl"] / 1e9
    if x["outcome"] == "landed":
        Lg = -(-d["buy_landed"]["buy_sol"] * 10125 // 10000) / 1e9; sn = d["sell_landed"]["sol"] * (1 - 0.0125) / 1e9
        curve = sn - Lg; cost = pnl - curve; CT_REAL[x["run"]].append(-cost)
    else: curve = 0.0; CR_REAL.append(-pnl)
    j, exv, nra = s[5]
    rows.append(dict(run=x["run"], id=x["id"], out=x["outcome"], size=x["size"], pnl=pnl, curve=curve, j=j, act_h2=None if exv is None else exv[0],
                     nra=nra, ev_g=float(s[3][1, 0, 0, 0, 0]), pl=float(s[4][1, 0, 0]), aref=float(s[2][0, 0, 0]), rc=s[1]["rc"]))
print("real landed-trip cost mSOL by run:", {k: round(np.mean(v) * 1e3, 2) for k, v in CT_REAL.items()}, "all", round(np.mean(sum(CT_REAL.values(), [])) * 1e3, 2))
print("real revert cost mSOL mean", round(np.mean(CR_REAL) * 1e3, 3), "n", len(CR_REAL))
CT = np.mean(sum(CT_REAL.values(), [])); CR = np.mean(CR_REAL)
R = rows
for nm, f in (("all", lambda r: True), ("0.05 SOL (r10)", lambda r: r["size"] < 0.1), ("0.2 SOL (r11,r13,r14)", lambda r: r["size"] > 0.1)):
    rr = [r for r in R if f(r)]; nl = sum(r["out"] == "landed" for r in rr)
    real = sum(r["pnl"] for r in rr); real_curve = sum(r["curve"] for r in rr if r["out"] == "landed")
    det = sum(((r["act_h2"] - CT) if (r["nra"] == 0 and r["act_h2"] is not None) else -CR) for r in rr)
    det_curve = sum(r["act_h2"] for r in rr if r["out"] == "landed" and r["act_h2"] is not None)
    model = sum(r["ev_g"] - r["pl"] * CT - (1 - r["pl"]) * CR for r in rr); mpl = sum(r["pl"] for r in rr)
    simA = sum((r["aref"] - CT) if np.isfinite(r["aref"]) else -CR for r in rr)
    print(f"\n[{nm}] attempts {len(rr)} landed {nl} (model expects {mpl:.1f})")
    print(f"  realized P&L            {real*1e3:+8.1f} mSOL  (landed curve P&L {real_curve*1e3:+.1f})")
    print(f"  replay at our ACTUAL clk {det*1e3:+8.1f} mSOL  (landed curve {det_curve*1e3:+.1f}; rule-landed {sum(r['nra']==0 for r in rr)})")
    print(f"  M1 model expectation     {model*1e3:+8.1f} mSOL")
    print(f"  old sim (always pos A)   {simA*1e3:+8.1f} mSOL")
json.dump(dict(rows=R, CT=CT, CR=CR), open(f"{RD}/livecheck.json", "w"))
