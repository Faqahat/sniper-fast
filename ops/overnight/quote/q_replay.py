#!/usr/bin/env python3
# S4 on NON-SOL-quoted curves (PUMP / USDC / other quotes) — read-only replay. Each curve is rescaled so its initial
# virtual quote reserves equal 30 SOL (the SOL curve's), so a "0.5 SOL" buy has the same relative size and price impact;
# PnL is reported in SOL-equivalent minus a 0.5% round-trip swap cost (SOL -> quote -> SOL). Same S4 rules: deployer list
# (walk-forward), 1% guard vs the post-bundle price, block-order placement (wallet-prefix matching), sell at end of next slot.
import sys, os, json, gzip, glob, zlib, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
D = "/home/moiz/sniper-data/collect"; PQ = {"R1": "phaseQ", "R2": "phaseQ_fwd"}
L = rp.load_launches(); O = rp.load_obs(); A = json.load(open("/home/moiz/sniper/ops/overnight/core/attempts.json"))
DC = "/home/moiz/sniper/ops/snipers/devcheck"
ev = []
for w in ("9Sh2fd", "DGmspi"):
    for f in (f"devs_{w}.json", f"att_{w}.json"):
        p = os.path.join(DC, f)
        if os.path.exists(p):
            for m, v in json.load(open(p)).items():
                if v.get("signer") and v.get("bt") and m not in L: ev.append((v["bt"], v["signer"], 1))
for m, c in L.items():
    if not c.get("bt"): continue
    ev.append((c["bt"], c["user"], 0))
    if "9Sh2fd" in A.get(m, {}) or "DGmspi" in A.get(m, {}): ev.append((c["bt"], c["user"], 1))
ev.sort(); na = collections.Counter(); nl = collections.Counter(); j = 0; s3 = {}
for bt, m in sorted((c["bt"], m) for m, c in L.items() if c.get("bt")):
    while j < len(ev) and ev[j][0] < bt:
        _, d, a = ev[j]; (na if a else nl)[d] += 1; j += 1
    d = L[m]["user"]; s3[m] = na[d] >= 2 and (nl[d] == 0 or na[d] / nl[d] >= 0.10)
def read_q(run, b, mints):
    out = collections.defaultdict(list); seen = set()
    for f in glob.glob(os.path.join(D, PQ[run], f"b{b:03d}", "*.jsonl.gz")):
        try:
            for line in gzip.open(f, "rt"):
                r = json.loads(line)
                if r[0] not in mints or (r[4], r[5]) in seen: continue
                seen.add((r[4], r[5]))
                out[r[0]].append(dict(s=r[1], i=r[2], j=r[5], bt=r[3], sig=r[4], user=r[6], buy=r[7] == 1, tok=r[8], vtok=r[9], qm=r[10], q=r[11], vq=r[12], fbps=r[14] or 95, cbps=r[15] or 30))
        except (EOFError, OSError, zlib.error): pass
    for m in out: out[m].sort(key=lambda t: (t["s"], t["i"], t["j"]))
    return out
def place_q(tr, c, st, outs, land_ms, failed, max_slots=6):
    """block-order placement for quote curves: outs matched by wallet prefix only (amounts are not in SOL)"""
    S = c["slot"]
    succ = [(t["s"], t["i"], k, t) for k, t in enumerate(tr) if k >= st["g_end"] and t["s"] - S <= max_slots and t["user"] not in st["insiders"]]
    fl = [(s, i, None, u) for s, i, u in failed if s - S <= max_slots and u not in st["insiders"]]
    used_s, used_f, seen = set(), set(), {}
    for a, sol, isbuy, w6 in sorted(outs):
        hit = None
        for s, i, k, t in succ:
            if k in used_s or not t["user"].startswith(w6): continue
            used_s.add(k); hit = (s, i); break
        if hit is None:
            for s, i, _, u in fl:
                if (s, i) in used_f or not u.startswith(w6): continue
                used_f.add((s, i)); hit = (s, i); break
        if hit is not None: seen[hit] = min(a, seen.get(hit, a))
    anchors = sorted(seen.items()); last = st["g_end"] - 1
    for s, i, k, t in succ:
        a = seen.get((s, i))
        if a is None:
            later = [ms for (ss, ii), ms in anchors if (ss, ii) > (s, i)]
            a = min(later) if later else None
            if a is None or a >= land_ms: continue
        elif a >= land_ms: continue
        last = max(last, k)
    return max(last + 1, st["g_end"])
todo = [m for m, c in L.items() if s3.get(m) and c.get("bt") and "InitializeMayhemState" not in (c.get("ixn") or [])]
byb = collections.defaultdict(set)
for m in todo: byb[(L[m]["run"], rp.bucket(m))].add(m)
EX = [rp.R("eos1", [(1.0, ("slot", 1))], 5)]
def work(key):
    run, b = key; tq = read_q(run, b, byb[key]); fa = rp.read_failed(run, b, byb[key]); out = []
    for m, tr in tq.items():
        if len(tr) < 2: continue
        first = tr[0]; vq0 = first["vq"] - first["q"] if first["buy"] else first["vq"] + first["q"]
        if vq0 <= 0: continue
        f = 30e9 / vq0
        path = [dict(t, sol=int(t["q"] * f), vsol=int(t["vq"] * f)) for t in tr]
        if any(t["vsol"] <= 0 or t["vtok"] <= 0 for t in path): continue
        c = L[m]; st = rp.structure(path, c)
        if st["g_end"] < 1: continue
        ge = path[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; r = dict(m=m, run=run, bt=c["bt"], qm=first["qm"], res={})
        for Lm in (45, 75):
            if run == "R2":
                if m not in O: continue
                ib = place_q(path, c, st, O[m]["outs"], Lm, fa.get(m, []))
            else: ib, _ = rp.place_proxy(path, c, st, Lm)
            if ib < 1: continue
            if (path[ib - 1]["vsol"] / path[ib - 1]["vtok"]) / p_b > 1.01: r["res"][Lm] = -0.005; continue
            o = rp.sim(path, c, st, ib, 0.5, EX, fill_pen=0.015)
            if o: r["res"][Lm] = o["eos1"]["pnl"] - 0.005 * 0.5 * 2 / 2 * 1.0 - 0.0025   # 0.5% round-trip swap cost on 0.5 SOL
        if r["res"]: out.append(r)
    return out
if __name__ == "__main__":
    res = []
    with Pool(14) as p:
        for o in p.imap_unordered(work, sorted(byb)): res += o
    json.dump(res, open("q_s4.json", "w"))
    print(f"S4 picks on NON-SOL curves: {len(res)} launches with data")
    QN = {"pumpCmXqMfrsAkQ5r49WcJnRayYRqmXz6ae8H7H9Dfn": "PUMP", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC"}
    for run in ("R1", "R2"):
        for Lm in (45, 75):
            v = [r for r in res if r["run"] == run and Lm in r["res"]]
            by = collections.defaultdict(list)
            for r in v: by[QN.get(r["qm"], "other")].append(r["res"][Lm])
            cells = " | ".join(f"{k}: {sum(x):+.2f} ({sum(1 for y in x if y != -0.005)}/{len(x)})" for k, x in sorted(by.items()))
            print(f"   {run} L{Lm}: total {sum(r['res'][Lm] for r in v):+.2f} SOL-eq, fills {sum(1 for r in v if r['res'][Lm] != -0.005)}/{len(v)}  [{cells}]")
