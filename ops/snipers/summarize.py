#!/usr/bin/env python3
# READ-ONLY, offline: one row per candidate sniper from wallet_hist.py's hist.json (buys only; sells/profit ignored on purpose)
import sys, os, json, statistics, collections, datetime
H = json.load(open(sys.argv[1])); OUT = sys.argv[2]
OUR_RATIO = (0.017, 0.031)        # our fee / buy: 1.5 SOL Run 1 ~1.7%, 0.5 SOL Run 2 ~3.0%
rows = []
for w, x in H.items():
    ALL = x["buys"]
    B = [b for b in ALL if b["sol"] > 0]             # SOL-quoted pump.fun buys only (we trade those); others are other-quote curves
    nonsol = len(ALL) - len(B)
    if not B: rows.append(dict(w=w, n=0, nonsol=nonsol, why=["no SOL-quoted buys (only other-quote tokens)"])); continue
    n = len(B); t = [b["bt"] for b in B if b.get("bt")]
    span_h = (max(t) - min(t)) / 3600 if len(t) > 1 else 0
    d0 = sum(1 for b in B if b["delta"] == 0); d2 = sum(1 for b in B if b["delta"] is not None and b["delta"] <= 2)
    sn = [b for b in B if b["delta"] is not None and b["delta"] <= 2] or B
    ratio = [b["fee"] / b["sol"] for b in sn if b["sol"] > 0]
    cre = collections.Counter(b["creator"] for b in B)
    chk = [b for b in B if "insider" in b]; ins = sum(1 for b in chk if b["insider"]); jb = sum(1 for b in chk if b.get("jito_bundle"))
    tipsrv = collections.Counter(tp[0] for b in sn for tp in b["tips"])
    rows.append(dict(w=w, n=n, nonsol=nonsol, span_h=span_h, d0=d0, d2=d2, snipe=d2 / n, sol=statistics.median(b["sol"] for b in sn), fee=statistics.median(b["fee"] for b in sn),
                     ratio=statistics.median(ratio) if ratio else 0, r_lo=(sorted(ratio)[len(ratio) // 4] if ratio else 0), r_hi=(sorted(ratio)[3 * len(ratio) // 4] if ratio else 0),
                     in_curve=statistics.median(b["in_curve"] for b in sn), creators=len(cre), top_cre=cre.most_common(1)[0][1] / n, chk=len(chk), ins=ins, jb=jb,
                     tips=",".join(f"{k}" for k, _ in tipsrv.most_common(2)) or "-", seen=len(x["seen_in"]),
                     seen_pos=",".join(str(s["pos"]) for s in x["seen_in"])))
def verdict(r):
    why = []
    if r["n"] < 5: why.append("few buys seen")
    if r["snipe"] < 0.5: why.append(f"not mainly sniping ({r['snipe']:.0%} within 2 slots)")
    if r["ins"] > 0: why.append(f"INSIDER: {r['ins']}/{r['chk']} create-slot buys in the dev's Jito bundle")
    if r["top_cre"] > 0.3 and r["n"] >= 5: why.append(f"same dev {r['top_cre']:.0%} of buys")
    if r["creators"] < 5 and r["n"] >= 5: why.append(f"only {r['creators']} devs")
    return why
for r in rows:
    if r["n"]: r["why"] = verdict(r)
def sim(r):            # closeness to us: fee/buy ratio, then size
    lo, hi = OUR_RATIO; rr = r["ratio"]
    d = 0 if lo <= rr <= hi else min(abs(rr - lo), abs(rr - hi)) / 0.01
    return d + abs((r["sol"] - 1.0)) * 0.3
rows.sort(key=lambda r: (bool(r["why"]), sim(r) if r["n"] else 99))
json.dump(rows, open(OUT, "w"), indent=1)
print(f"{'wallet':45} {'SOL buys':>8} {'other-quote':>11} {'hrs':>5} {'≤2 slots':>8} {'@create':>7} {'med SOL':>7} {'med fee':>8} {'fee/buy':>14} {'SOL before':>10} {'devs':>5} {'top dev':>7} {'jito/ins':>8} {'tips via':>16} {'in our 43 (pos)':>16}  verdict")
for r in rows:
    if not r["n"]: print(f"{r['w']:45} {0:>8} {r['nonsol']:>11}  " + "; ".join(r["why"])); continue
    print(f"{r['w']:45} {r['n']:>8} {r['nonsol']:>11} {r['span_h']:5.1f} {r['snipe']:8.0%} {r['d0']:>7} {r['sol']:7.2f} {r['fee']:8.4f} {r['ratio']*100:5.2f}% ({r['r_lo']*100:.1f}-{r['r_hi']*100:.1f}) {r['in_curve']:10.1f} "
          f"{r['creators']:>5} {r['top_cre']:7.0%} {r['jb']:>3}/{r['ins']:<3}  {r['tips'][:16]:>16} {r['seen']:>3} ({r['seen_pos'][:10]})  {'OK' if not r['why'] else '; '.join(r['why'])}")
