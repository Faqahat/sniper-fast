#!/usr/bin/env python3
# Rank wallets from census parts: who is consistently profitable, and how do they enter / hold?
import json, gzip, glob, collections, statistics, sys
CORE = "/home/moiz/sniper/ops/overnight/core"
W = json.load(open(f"{CORE}/gf_wallets.json"))
SNIPER = {u for u, v in W.items() if v[1] >= 5 and v[1] >= 0.5 * v[0]}
PRO6 = ("9Sh2fd", "DGmspi", "D24ipY", "dKMjeG", "CWiNFA", "9qz7cW", "FiFawH", "AHwJSn", "4yFAz")
A = collections.defaultdict(list)
for f in glob.glob("/home/moiz/sniper/ops/overnight/census/parts/*.jsonl.gz"):
    for l in gzip.open(f, "rt"):
        r = json.loads(l); A[r[0]].append(r)
print("wallets", len(A))
# r: [u, m, run, bt, fb_s, fb_k, fb_sol, spent, got, mark, cost, pnl, nb, ns, ls_s, done, open]
rows = []
for u, v in A.items():
    if len(v) < 30: continue
    v.sort(key=lambda r: r[3])
    pn = [r[11] for r in v]; tot = sum(pn)
    h = len(v) // 2; t1 = sum(pn[:h]); t2 = sum(pn[h:])
    q = [sum(pn[i * len(v) // 4:(i + 1) * len(v) // 4]) for i in range(4)]
    spent = [r[7] for r in v]; R = [r[11] / r[7] for r in v if r[7] > 0]
    fb = [r[4] for r in v]; hold = [(r[14] - r[4]) for r in v if r[14] is not None]
    rows.append(dict(u=u, n=len(v), tot=tot, t1=t1, t2=t2, q=q, qpos=sum(1 for x in q if x > 0), win=sum(1 for x in pn if x > 0) / len(v),
                     medR=statistics.median(R) if R else 0, meanR=sum(pn) / max(sum(spent), 1e-9), size=statistics.median(spent),
                     fb_med=statistics.median(fb), fb0=sum(1 for x in fb if x == 0) / len(fb), fb_le2=sum(1 for x in fb if x <= 2) / len(fb),
                     hold_med=statistics.median(hold) if hold else None, open=sum(r[16] for r in v) / len(v), r1=sum(1 for r in v if r[2] == "R1"),
                     top5=sum(sorted(pn)[-5:]), sniper=u in SNIPER, pro=u.startswith(PRO6)))
rows.sort(key=lambda r: -r["tot"])
json.dump(rows, open("/home/moiz/sniper/ops/overnight/census/wallets.json", "w"))
def show(title, rs, k=40):
    print(f"\n{title} ({len(rs)})")
    print("  wallet    n    total   1st-half 2nd-half q+  win  medR   size  entry(slots) med/%s0/%<=2  hold_med  open  w/o top5  tag")
    for r in rs[:k]:
        print(f"  {r['u'][:8]} {r['n']:4d} {r['tot']:+8.2f} {r['t1']:+8.2f} {r['t2']:+8.2f} {r['qpos']}/4 {r['win']:4.0%} {r['medR']:+.3f} {r['size']:6.2f}  {r['fb_med']:5.0f} {r['fb0']:4.0%} {r['fb_le2']:4.0%}  {str(r['hold_med']):>6}  {r['open']:4.0%} {r['tot'] - r['top5']:+8.2f}  {'PRO' if r['pro'] else ('snp' if r['sniper'] else '')}")
cons = [r for r in rows if r["tot"] > 0 and r["t1"] > 0 and r["t2"] > 0 and r["qpos"] >= 3]
show("Consistent winners: total>0, both halves>0, >=3 of 4 quarters>0, n>=30", cons)
late = [r for r in cons if r["fb_le2"] < 0.5]
show("...of which LATE entrants (most first buys > 2 slots after the create)", late)
show("All wallets n>=30 by total (top)", rows, 25)
print("\nCounts: n>=30 wallets", len(rows), "| total>0", sum(1 for r in rows if r["tot"] > 0), "| consistent", len(cons), "| consistent late", len(late))
