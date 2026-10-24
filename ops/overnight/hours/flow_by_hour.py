#!/usr/bin/env python3
# READ-ONLY market regime check: ordinary ("generic") buying per launch by PKT hour, R1 (phaseA) + R2 (phaseA_dry).
# Per standard SOL-curve launch (no mayhem / odd reserves): after the dev's glued bundle, in the next 8 s:
#   gen_sol = buy SOL by wallets that are not insiders, not the 321 snipers, not the 9 pros; gen_n = such buyers;
#   m8 = price 8 s after the bundle / post-bundle price; mx = max price in those 8 s / post-bundle price.
# -> hours/flow_by_hour.json + a table. usage: python3 -I flow_by_hour.py
import sys, os, json, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry")
import rp
from multiprocessing import Pool
CORE = "/home/moiz/sniper/ops/overnight/core"
L = rp.load_launches(); W = json.load(open(f"{CORE}/gf_wallets.json"))
SNIPER = {u for u, v in W.items() if v[1] >= 5 and v[1] >= 0.5 * v[0]}
PRO = set()
for p in ("9Sh2fd", "DGmspi", "D24ipY", "dKMjeG", "CWiNFA", "9qz7cW", "FiFawH", "AHwJSn", "4yFAz"):
    c = [u for u in W if u.startswith(p)]
    if c: PRO.add(max(c, key=lambda u: W[u][0]))
NS = int(8000 / rp.SLOT_MS) + 1
byb = collections.defaultdict(set)
for m, c in L.items(): byb[(c["run"], rp.bucket(m))].add(m)
def work(key):
    run, b = key; out = []
    tra = rp.read_bucket(run, b, byb[key])
    for m, tr in tra.items():
        if not tr or min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]
        if c.get("mayhem"): continue
        st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; pb = ge["vsol"] / ge["vtok"]; S = c["slot"]
        w = [t for t in tr[st["g_end"]:] if t["s"] <= S + NS]
        gen = [t for t in w if t["buy"] and not t.get("syn") and t["user"] not in st["insiders"] and t["user"] not in SNIPER and t["user"] not in PRO]
        snp = [t for t in w if t["buy"] and (t["user"] in SNIPER or t["user"] in PRO)]
        last = w[-1] if w else ge
        mx = max([t["vsol"] / t["vtok"] for t in w] + [pb]) / pb
        out.append(dict(m=m, run=run, bt=c["bt"], gen_sol=round(sum(t["sol"] for t in gen) / 1e9, 4), gen_n=len({t["user"] for t in gen}),
                        snp_sol=round(sum(t["sol"] for t in snp) / 1e9, 4), m8=round((last["vsol"] / last["vtok"]) / pb, 4), mx=round(mx, 4),
                        dev=round(sum(t["sol"] for t in tr[:st["g_end"]] if t["buy"]) / 1e9, 3), glued=len(st["glued"])))
    return out
if __name__ == "__main__":
    res = []
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb), chunksize=4): res += o
    json.dump(res, open("/home/moiz/sniper/ops/overnight/hours/flow_by_hour.json", "w"))
    H = collections.defaultdict(list)
    for r in res: H[(r["run"], int(((r["bt"] + 5 * 3600) % 86400) // 3600))].append(r)
    print(f"{len(res)} standard launches. Per PKT hour: launches | mean generic buy SOL in 8 s | share with >=1 SOL generic | share >=3 generic buyers | share m8>=1.3 | mean m8")
    for run in ("R1", "R2"):
        for h in range(24):
            v = H.get((run, h))
            if not v or len(v) < 30: continue
            print(f"  {run} {h:02d}h {len(v):5d} | {statistics.mean(x['gen_sol'] for x in v):6.3f} | {sum(1 for x in v if x['gen_sol'] >= 1)/len(v):5.1%} | "
                  f"{sum(1 for x in v if x['gen_n'] >= 3)/len(v):5.1%} | {sum(1 for x in v if x['m8'] >= 1.3)/len(v):5.1%} | {statistics.mean(x['m8'] for x in v):.3f}")
