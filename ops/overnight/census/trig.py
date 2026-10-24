#!/usr/bin/env python3
# What happens right before a target wallet's first buy on each launch? -> trigger candidates and entry context.
# usage: python3 -I trig.py <wallet prefix> [max_mints]
import sys, os, json, gzip, glob, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry"); os.environ["RP_REPAIR"] = "0"
import rp
from multiprocessing import Pool
WP = sys.argv[1]; MAXM = int(sys.argv[2]) if len(sys.argv) > 2 else 100000
rows = []
for f in glob.glob("/home/moiz/sniper/ops/overnight/census/parts/*.jsonl.gz"):
    for l in gzip.open(f, "rt"):
        if l[2:2 + len(WP)] == WP: rows.append(json.loads(l))
U = rows[0][0]; P = {r[1]: r for r in rows}
print(U, "positions", len(rows))
L = rp.load_launches()
byb = collections.defaultdict(set)
for m in list(P)[:MAXM]: byb[(L[m]["run"], rp.bucket(m))].add(m)
def work(key):
    run, b = key; out = []
    tra = rp.read_bucket(run, b, byb[key])
    for m, tr in tra.items():
        c = L[m]; S = c["slot"]; st = rp.structure(tr, c)
        k0 = next((k for k, t in enumerate(tr) if t["user"] == U and t["buy"]), None)
        if k0 is None or st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; pb = ge["vsol"] / ge["vtok"]
        pre = tr[k0 - 1] if k0 > 0 else None
        p_entry = (pre["vsol"] / pre["vtok"]) if pre else pb
        before = [t for t in tr[max(0, k0 - 12):k0]]
        s0 = tr[k0]["s"]
        win3 = [t for t in tr[:k0] if s0 - t["s"] <= 3 and t["user"] != U]
        mine = [t for t in tr if t["user"] == U]
        out.append(dict(m=m, run=run, ds=s0 - S, k0=k0, nb_before=sum(1 for t in tr[:k0] if t["buy"]), ns_before=sum(1 for t in tr[:k0] if not t["buy"]),
                        px_vs_bundle=round(p_entry / pb, 3), mc=round(p_entry * 1e6, 2), vsol=round((pre or ge)["vsol"] / 1e9, 2),
                        trig=[(t["user"][:8], "B" if t["buy"] else "S", round(t["sol"] / 1e9, 3), s0 - t["s"]) for t in win3[-6:]],
                        last=(before[-1]["user"][:8], "B" if before[-1]["buy"] else "S", round(before[-1]["sol"] / 1e9, 3), s0 - before[-1]["s"]) if before else None,
                        seq=[(t["s"] - S, "B" if t["buy"] else "S", round(t["sol"] / 1e9, 3)) for t in mine][:8],
                        pnl=P[m][11], spent=P[m][7], hold=(P[m][14] - P[m][4]) if P[m][14] is not None else None,
                        sells_between=sum(1 for t in tr[k0:] if (not t["buy"]) and t["user"] != U and t["s"] <= (mine[-1]["s"] if mine else s0))))
    return out
if __name__ == "__main__":
    res = []
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb)): res += o
    json.dump(res, open(f"/home/moiz/sniper/ops/overnight/census/trig_{WP}.json", "w"))
    print("positions with tape", len(res))
    cnt = collections.Counter(); cntw = collections.Counter(); pnlw = collections.defaultdict(float)
    for r in res:
        ws = {x[0] for x in r["trig"] if x[1] == "B"}
        for w in ws: cnt[w] += 1; pnlw[w] += r["pnl"]
    print("most frequent buyers within 3 slots before its first buy (wallet: count, its pnl on those):")
    print("  ", [(w, n, round(pnlw[w], 2)) for w, n in cnt.most_common(15)])
    lastb = collections.Counter((r["last"][0], r["last"][1]) for r in res if r["last"])
    print("most frequent IMMEDIATELY preceding trade:", lastb.most_common(10))
    def band(title, key, edges):
        o = []
        for lo, hi in zip(edges[:-1], edges[1:]):
            x = [r for r in res if key(r) is not None and lo <= key(r) < hi]
            if x: o.append(f"[{lo},{hi}) n{len(x)} {sum(r['pnl'] for r in x):+.1f} w{sum(1 for r in x if r['pnl'] > 0) / len(x):.0%}")
        print(f"  {title}: " + " | ".join(o))
    band("entry price / post-bundle", lambda r: r["px_vs_bundle"], [0, 0.9, 1.0, 1.1, 1.3, 1.6, 2, 3, 5, 100])
    band("vsol at entry", lambda r: r["vsol"], [0, 31, 33, 36, 40, 50, 60, 80, 120])
    band("buys before it", lambda r: r["nb_before"], [0, 2, 4, 7, 12, 20, 40, 100, 10 ** 6])
    band("sells before it", lambda r: r["ns_before"], [0, 1, 2, 4, 8, 16, 10 ** 6])
    band("last trade before it was a BUY of SOL", lambda r: r["last"][2] if r["last"] and r["last"][1] == "B" else None, [0, 0.1, 0.5, 1, 2, 5, 100])
    band("last trade before it was a SELL of SOL", lambda r: r["last"][2] if r["last"] and r["last"][1] == "S" else None, [0, 0.1, 0.5, 1, 2, 5, 100])
    band("slots since last trade", lambda r: r["last"][3] if r["last"] else None, [0, 1, 2, 3, 5, 10, 30, 10 ** 6])
    for r in sorted(res, key=lambda r: r["m"])[:12]:
        print("   ", r["m"][:8], r["run"], "ds", r["ds"], "px", r["px_vs_bundle"], "vsol", r["vsol"], "nb/ns before", r["nb_before"], r["ns_before"], "last", r["last"], "| seq", r["seq"], "pnl", round(r["pnl"], 3))
