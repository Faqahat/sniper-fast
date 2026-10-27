#!/usr/bin/env python3
# BAIT-FLIP pass 1 (read-only, offline). Owner strategy: hold a position -> SELL + BUY in the same bundle (fake dump) ->
# dip bots buy the "dump" -> sell into them. Find every real instance in R1-R3 (same wallet sells then buys the same mint
# in the same slot, tx-index gap <= 2 or same tx) plus plain-sell controls, and record what outside traders do next.
# -> /home/moiz/sniper-data/strategies/baitflip/{run}_bNNN.jsonl.gz, one JSON dict per event
import os, json, gzip, glob, zlib, collections, sys
from multiprocessing import Pool
D = "/home/moiz/sniper-data/collect"
OUT = "/home/moiz/sniper-data/strategies/baitflip"
RUNS = {"R1": ["phaseA"], "R2": ["phaseA_fwd"], "R3": ["phaseA_r3", "/home/moiz/sniper-data/strategies/phaseA_r3tail"]}
GRADV = 113e9
WIN = [0, 1, 2, 4, 8, 16]          # slots after the event slot (0 = rest of the event slot)
MINSOL = 0.2e9
CTRL_EVERY = 1                      # keep every plain sell >= MINSOL as control

def read(run, b):
    out = collections.defaultdict(list); seen = set()
    for d in RUNS[run]:
        d = d if d.startswith("/") else f"{D}/{d}"
        for f in glob.glob(f"{d}/b{b:03d}/*.jsonl.gz"):
            try:
                for line in gzip.open(f, "rt"):
                    if line[2] != "T": continue
                    r = json.loads(line)
                    if r[12]: continue
                    k = (r[5], r[13])
                    if k in seen: continue
                    seen.add(k)
                    # s, i, j, sig, payer, fee, tips, user, buy, sol, tok, vsol, vtok
                    tips = r[11] if isinstance(r[11], (int, float)) else 0
                    out[r[1]].append((r[2], r[3], r[13], r[5], r[6], r[7] or 0, tips, r[14], r[15] == 1, r[16], r[17], r[18], r[19]))
            except (EOFError, OSError, zlib.error, ValueError): pass
    for m in out: out[m].sort(key=lambda t: (t[0], t[1], t[2]))
    return out

def pre(t):
    return (t[11] - t[9], t[12] + t[10]) if t[8] else (t[11] + t[9], t[12] - t[10])

def px(v, k): return v / k if k else 0

def outcome(tr, k_end, slot, excl):
    """what others do after trade index k_end (exclusive), excluding wallets in excl"""
    n = len(tr); res = {}
    p_ref = px(tr[k_end][11], tr[k_end][12])
    k = k_end + 1
    for w in WIN:
        smax = slot + w
        nb = ns = 0; bsol = ssol = 0; ws = set(); pmax = p_ref; plast = p_ref
        kk = k_end + 1
        while kk < n and tr[kk][0] <= smax:
            t = tr[kk]
            if t[11] >= GRADV: break
            if t[7] not in excl:
                if t[8]: nb += 1; bsol += t[9]; ws.add(t[7])
                else: ns += 1; ssol += t[9]
            p = px(t[11], t[12]); plast = p; pmax = max(pmax, p)
            kk += 1
        res[w] = (nb, round(bsol / 1e9, 4), len(ws), ns, round(ssol / 1e9, 4), round(plast / p_ref, 5) if p_ref else 0, round(pmax / p_ref, 5) if p_ref else 0)
    # first outside buy in event slot right after: index gap
    return res

def scan(job):
    run, b = job
    tr_all = read(run, b)
    rows = []
    for m, tr in tr_all.items():
        if len(tr) < 5: continue
        if any(t[11] < 25e9 or t[11] > 200e9 or not t[12] for t in tr[:50]): continue
        s0 = tr[0][0]; n = len(tr)
        for k, t in enumerate(tr):
            if t[8] or t[9] < MINSOL or t[11] >= GRADV: continue
            u = t[7]
            # same wallet buy after this sell in the same or next slot (filter tight bundles later via ds/di)
            flip = None
            for kk in range(k + 1, min(n, k + 400)):
                q = tr[kk]
                if q[0] > t[0] + 1: break
                if q[7] == u and q[8]: flip = kk; break
            pv, pt = pre(t); p0 = px(pv, pt)
            p1 = px(t[11], t[12])
            row = {"run": run, "m": m, "u": u, "s": t[0], "i": t[1], "age": t[0] - s0, "sell": round(t[9] / 1e9, 4),
                   "vsol": round(pv / 1e9, 2), "drop": round(p1 / p0 - 1, 5) if p0 else 0, "fee": t[5], "tip": t[6],
                   "ntr": k, "quiet": t[0] - tr[k - 1][0] if k else -1}
            # did u hold tokens before? net tokens of u before k
            if flip is not None:
                q = tr[flip]
                row.update(kind="flip", ds=q[0] - t[0], buy=round(q[9] / 1e9, 4), di=q[1] - t[1], same_tx=q[3] == t[3],
                           between=sum(1 for z in tr[k + 1:flip] if z[7] != u), bfee=q[5], btip=q[6],
                           net_after=round(px(q[11], q[12]) / p0 - 1, 5) if p0 else 0)
                kend = flip
            else:
                # control: plain sell, u does not buy back this mint within 2 slots
                if any(z[7] == u and z[8] for z in tr[k + 1:k + 40] if z[0] <= t[0] + 2): continue
                row.update(kind="ctrl")
                kend = k
            row["out"] = outcome(tr, kend, t[0], {u})
            # u's next sell after the event (realized exit of the flipper / seller)
            nx = next((z for z in tr[kend + 1:] if z[7] == u and not z[8]), None)
            if nx:
                row["nx_gap"] = nx[0] - t[0]; row["nx_px"] = round(px(*pre(nx)) / p0, 5) if p0 else 0; row["nx_sol"] = round(nx[9] / 1e9, 4)
            rows.append(row)
    os.makedirs(OUT, exist_ok=True)
    with gzip.open(f"{OUT}/{run}_b{b:03d}.jsonl.gz", "wt") as f:
        for r in rows: f.write(json.dumps(r) + "\n")
    return run, b, sum(1 for r in rows if r["kind"] == "flip"), len(rows)

if __name__ == "__main__":
    jobs = [(r, b) for r in RUNS for b in range(256)]
    tot = collections.Counter()
    with Pool(12) as p:
        for i, (run, b, nf, nr) in enumerate(p.imap_unordered(scan, jobs)):
            tot[run + "_flip"] += nf; tot[run + "_all"] += nr
            if i % 64 == 0: print(i, dict(tot), flush=True)
    print("DONE", dict(tot), flush=True)
