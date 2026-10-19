# Crude near-floor check using checkpoint states only (entry at state(d), no latency -> optimistic). Paper.
import sys, json, statistics, collections, bisect
sys.path.insert(0, "/root/strat")
from sim import buy, sell
CK = [69, 139, 277, 416, 554, 831, 1109]
K = 30e9 * 1073e12
def pnl(v_in, v_out, X, shift):
    vt_in = K / v_in; a = X * 1e9 / 1.0125
    q = vt_in * a / (v_in + a)
    if shift:
        Vs = v_out + a; Vt = K / Vs
    else:
        Vs = v_out; Vt = K / v_out
    return (sell(Vs, Vt, q, 0.0125) / 1e9 - X - 0.00061) / X
res = collections.defaultdict(list)
MH = {}
for l in open("/root/nob/ds.jsonl"):
    y = json.loads(l); MH[y["mint"]] = 1 if y.get("mayhem") else 0
for l in open("/root/strat/pipe.jsonl"):
    x = json.loads(l)
    if x.get("stage", 0) < 3 or x.get("nonsol") or not x.get("cks"): continue
    okd = []
    for d, n in x["act"]: okd += [d] * n
    ck = {c[0]: c[1] for c in x["cks"]}
    for i, d in enumerate(CK):
        v = ck.get(d)
        if not v or v >= 36e9: continue
        n15 = bisect.bisect_right(okd, d) - bisect.bisect_right(okd, d - 69)
        for j in range(i + 1, len(CK)):
            d2 = CK[j]; v2 = ck.get(d2)
            if v2 is None:
                # no txs since -> unchanged? only if no activity
                if bisect.bisect_right(okd, d2) == bisect.bisect_right(okd, d): v2 = v
                else: continue
            mh = 1 if (x.get("mayhem") or MH.get(x["mint"])) else 0
            for nb, lo, hi in [("n15<5", 0, 5), ("n15 5-20", 5, 20), ("n15>=20", 20, 9999)]:
                if lo <= n15 < hi:
                    res[(d, d2, "mh%d %s" % (mh, nb))].append((pnl(v, v2, 1.0, False), pnl(v, v2, 1.0, True)))
for k in sorted(res):
    v = res[k]
    a = [p[0] for p in v]; b = [p[1] for p in v]
    if len(v) < 20: continue
    sa = sorted(a)
    print("entry %4.0fs exit %4.0fs %-9s n=%4d double mean %+.1f%% med %+.1f%% ex3 %+.1f%% | shift mean %+.1f%%" % (k[0] * 0.2165, k[1] * 0.2165, k[2], len(v), 100 * sum(a) / len(a), 100 * statistics.median(a), 100 * sum(sa[:-3]) / (len(sa) - 3), 100 * sum(b) / len(b)))
