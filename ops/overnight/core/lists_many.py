# guarded flip (1%, hold ~1 s, fail 0.005, 0.5 SOL) with deployer lists copied from each profitable sniper (walk-forward:
# >= 2 attempts and >= 10% of the deployer's launches before each launch). R2 = real place in line (75 ms and 45 ms);
# R1 = old data with the block-position proxy (pessimistic at 60-75 ms).
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
L = rp.load_launches(); O = rp.load_obs()
AT = json.load(open("attempts_top8.json")); A0 = json.load(open("attempts.json")); AH = json.load(open("attempts_ahw.json"))
for m, v in AH.items(): AT.setdefault(m, {}).update(v)
for m, v in A0.items():
    for w in ("9Sh2fd", "DGmspi"):
        if w in v: AT.setdefault(m, {})[w] = v[w]
WAL = ["9Sh2fd", "DGmspi", "AHwJSn", "haqqiU", "dKMjeG", "A21wCG", "3yrJE1", "FeCAXC", "CWiNFA", "6Kj5Ch", "5g8bvi"]
ev = []
for m, c in L.items():
    if not c.get("bt"): continue
    ev.append((c["bt"], c["user"], ""))
    for w in AT.get(m, {}): ev.append((c["bt"], c["user"], w))
ev.sort()
na = collections.defaultdict(collections.Counter); nl = collections.Counter(); j = 0; mem = collections.defaultdict(set)
for bt, m in sorted((c["bt"], m) for m, c in L.items() if c.get("bt")):
    while j < len(ev) and ev[j][0] < bt:
        _, d, w = ev[j]
        if w == "": nl[d] += 1
        else: na[w][d] += 1
        j += 1
    d = L[m]["user"]
    for w in WAL:
        a = na[w][d]
        if a >= 2 and (nl[d] == 0 or a / nl[d] >= 0.10): mem[m].add(w)
todo = [m for m in mem if "InitializeMayhemState" not in (L[m].get("ixn") or [])]
byb = collections.defaultdict(set)
for m in todo: byb[(L[m]["run"], rp.bucket(m))].add(m)
EX = [rp.R("hold1s", [(1.0, ("t", 1))], 2)]
def work(key):
    run, b = key; tra = rp.read_bucket(run, b, byb[key]); fa = rp.read_failed(run, b, byb[key]) if run == "R2" else {}; out = {}
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; r = {}
        for Lm in (45, 75):
            if run == "R2":
                if m not in O: continue
                ib, _ = rp.place_bo2(tr, c, st, O[m]["outs"], Lm, fa.get(m, []))
            else: ib, _ = rp.place_proxy(tr, c, st, Lm)
            if ib < 1: continue
            if (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b > 1.01: r[Lm] = -0.005
            else:
                o = rp.sim(tr, c, st, ib, 0.5, EX, fill_pen=0.015); r[Lm] = o["hold1s"]["pnl"] if o else None
        out[m] = r
    return out
if __name__ == "__main__":
    res = {}
    with Pool(14) as p:
        for o in p.imap_unordered(work, sorted(byb)): res.update(o)
    print(f"{'list source':10} | R2 real 45 ms | R2 real 75 ms | R1 old 45 ms | R1 old 75 ms   (total SOL, fills/attempts)")
    for w in WAL:
        cells = []
        for run in ("R2", "R1"):
            for Lm in (45, 75):
                v = [res[m][Lm] for m in res if w in mem[m] and L[m]["run"] == run and res[m].get(Lm) is not None]
                cells.append(f"{sum(v):+6.2f} ({sum(1 for x in v if x != -0.005)}/{len(v)})")
        print(f"{w:10} | " + " | ".join(cells))
    json.dump({m: sorted(v) for m, v in mem.items()}, open("lists_many.json", "w"))
    out = {}
    for w in WAL:
        out[w] = {}
        for run in ("R2", "R1"):
            for Lm in (45, 75):
                v = [res[m][Lm] for m in res if w in mem[m] and L[m]["run"] == run and res[m].get(Lm) is not None]
                out[w][f"{run}_{Lm}"] = dict(tot=sum(v), fills=sum(1 for x in v if x != -0.005), n=len(v))
    json.dump(out, open("/home/moiz/sniper/ops/overnight/report/lists_many.json", "w"))
