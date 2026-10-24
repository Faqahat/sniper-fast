#!/usr/bin/env python3
"""verify_dip / vx_compare: per-event comparison of my rebuild (vx_events_*.jsonl.gz) with the claim's ev4_b05 / ev4_b05_slow.
Keys (m, age). Reports event-set differences (and why), PnL agreement for the claim-spec variant 'c', feature agreement.
usage: python3 -I -B vx_compare.py <my events> [claim b05] [claim slow]"""
import sys, os, json, gzip, collections, statistics, time
HERE = os.path.dirname(os.path.abspath(__file__))
MY = sys.argv[1]
CF = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "snap", "ev4_b05.jsonl.gz")
CS = sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, "snap", "ev4_b05_slow.jsonl.gz")
def pkt(t): return time.strftime("%m-%d %H:%M", time.gmtime(t + 18000))
M = {}
for l in gzip.open(MY, "rt"):
    r = json.loads(l); M[(r["m"], r["age"])] = r
C = {}
for l in gzip.open(CF, "rt"):
    r = json.loads(l); C[(r["m"], r["age"])] = r
CSL = {}
for l in gzip.open(CS, "rt"):
    r = json.loads(l); CSL[(r["m"], r["age"])] = r
tmax = max(r["bt"] + r["age"] for r in C.values()); tmin = min(r["bt"] + r["age"] for r in C.values())
print(f"claim events {len(C)} ({pkt(tmin)} -> {pkt(tmax)} PKT); my events {len(M)} (all curve kinds)")
Mk = collections.Counter((r["kind"], r["cf"]) for r in M.values()); print("my events by (curve kind, passes the claim's vsol filter):", dict(Mk))
# restrict mine to the claim's time window and the claim's filter
Mw = {k: r for k, r in M.items() if r["bt"] + r["age"] <= tmax}
both = set(Mw) & set(C); onlyC = set(C) - set(Mw); onlyM = {k for k in set(Mw) - set(C) if Mw[k]["cf"]}
print(f"in the claim's window: matched {len(both)}; only claim {len(onlyC)}; only mine (passing the claim filter) {len(onlyM)}")
print("  matched by my curve kind:", dict(collections.Counter(Mw[k]["kind"] for k in both)))
print("  only-mine by kind:", dict(collections.Counter(Mw[k]["kind"] for k in onlyM)), "by run", dict(collections.Counter(Mw[k]["run"] for k in onlyM)))
print("  only-claim by run:", dict(collections.Counter(C[k]["run"] for k in onlyC)), "mint has other matched events:",
      sum(1 for k in onlyC if any((k[0], a) in Mw for a in [k[1]])), "mint in my data:", sum(1 for k in onlyC if any(kk[0] == k[0] for kk in Mw)))
# PnL agreement
for LAT, src in (("20", C), ("35", C), ("50", CSL), ("75", CSL)):
    ks = [k for k in both if k in src and LAT in src[k]["pnl"] and LAT in Mw[k]["pnl"]]
    d = [Mw[k]["pnl"][LAT]["c"] - 0.0016 - src[k]["pnl"][LAT]["4"] for k in ks]
    ex = sum(1 for x in d if abs(x) < 2e-5)
    ad = sorted(abs(x) for x in d)
    print(f"L{LAT}: matched with pnl {len(ks)}; |diff| < 0.00002 SOL: {ex / len(ks):.1%}; mean diff (mine - claim) {statistics.mean(d):+.5f}; "
          f"p99 |diff| {ad[int(0.99 * len(ad))]:.4f}; max {ad[-1]:.4f}; sum mine {sum(Mw[k]['pnl'][LAT]['c'] - 0.0016 for k in ks):+.2f} claim {sum(src[k]['pnl'][LAT]['4'] for k in ks):+.2f}")
    big = sorted(ks, key=lambda k: -abs(Mw[k]["pnl"][LAT]["c"] - 0.0016 - src[k]["pnl"][LAT]["4"]))[:8]
    for k in big:
        a = Mw[k]; c = src[k]
        print(f"     {k[0][:10]} age {k[1]:6.2f} mine {a['pnl'][LAT]['c'] - 0.0016:+.4f} claim {c['pnl'][LAT]['4']:+.4f} ahead mine {a['ahead'].get(LAT)} claim {c['ahead'].get(LAT)} "
              f"ngap {a['ngap']} kind {a['kind']}")
    na = sum(1 for k in ks if Mw[k]["ahead"][LAT] != src[k]["ahead"][LAT]); print(f"     'ahead' count differs on {na} events ({na / len(ks):.1%})")
# feature agreement on matched events
FK = ["sell", "drop", "vsol", "nb", "ns", "pb", "dd", "b20", "s20", "u20", "dev", "glued", "first_big", "ins"]
XF = ["s_frac", "s_pnl", "s_nb", "s_entry", "s_in_bundle", "n_big", "since_big", "ret5", "ret20", "peak_mult", "b3", "nb3", "sellers20", "uniq_buyers", "ins_sold", "net_flow"]
bad = collections.Counter()
for k in both:
    a, c = Mw[k], C[k]
    for f in FK:
        if a[f] != c[f]: bad[f] += 1
    for f in XF:
        if a["xf"][f] != c["xf"][f]: bad["xf." + f] += 1
    if a["seller"] != c["seller"]: bad["seller"] += 1
print("feature mismatches on matched events:", dict(bad) if bad else "none")
