#!/usr/bin/env python3
# "Could we copy them at OUR place in line?" (read-only paper replay, exact bonding-curve math).
# For every snipe of a leader wallet: put OUR 0.494 SOL buy into the curve right after the leader's first buy plus D more
# trades (D = 0..3 = reaction delay, other copiers / snipers landing first), then sell:
#   mirror  : right after the leader's FIRST sell + 1 trade (we see its sell, our sell lands just behind it)
#   hold Ns : at the first trade more than N slots after our buy (slot ~212 ms)
# and also a PRE-EMPTIVE copy (same token choice, no reaction needed): our buy behind the first K outside trades after the
# glued bundle (K = 1, 2, 3 ~ our 60-75 ms landing), sold with the same exits.
# Pump fees per side from the events; fixed cost per round trip COST (ours ~0.015 SOL). Curve completed before the exit
# -> trade dropped (AMM price unknown). Failed (err) trades are not replayed.
# usage: python3 -I w6_follow.py <w2 out dir> <phaseA R1> <phaseA R2> <launches R1> <launches R2> <out json> [procs]
import sys, os, json, gzip, glob, zlib, collections, statistics
from multiprocessing import Pool
OUTD, PA1, PA2, LF1, LF2, OUTJ = sys.argv[1:7]; PROCS = int(sys.argv[7]) if len(sys.argv) > 7 else 8
X = 493827160; COSTS = (0.015, 0.005); HOLDS = (5, 10, 15, 25, 50); GRAD = 114_000_000_000
R = json.load(open(os.path.join(OUTD, "wallets_all.json"))); PP = json.load(gzip.open(os.path.join(OUTD, "pairs_cands.json.gz"), "rt"))
FOCUS = ["9Sh2fdqMQcec7W9LzzfvkYphrdyR3S8aUBsKdv9xNYa1", "DGmspiBs2ePJ7WgN1pyX5RJDpzhyxYrBN1P4bXNC1NR3", "D24ipYXuDt6PXEPV6rZqfWb35WJaTJW3gDoXwt7yJCwQ"]
LEAD = [w for w, s in R.items() if s.get("pass")] + [w for w in FOCUS if w in R]
L = {}
for run, lf in (("R1", LF1), ("R2", LF2)):
    for l in open(lf):
        try: c = json.loads(l)
        except Exception: continue
        L.setdefault(c["mint"], c)
jobs = collections.defaultdict(list)       # (run, bucket) -> [(leader, mint)]
for w in LEAD:
    for p in PP.get(w, []):
        run, m = p[0], p[7]
        jobs[(run, zlib.crc32(m.encode()) % 256)].append((w, m))

def sim(tr, k0, S, fb, cb, exits):
    """our buy placed right after trades[k0-1]; exits: {name: ('h', slots) | ('idx', k)} -> gross return or None (graduated)"""
    st = tr[k0 - 1]; V, T = st[18], st[19]
    if not T: return {}
    q = T * X // (V + X); V += X; T -= q; cost = X * (1 + (fb + cb) / 1e4)
    val = lambda V, T: (V * q // (T + q)) * (1 - (fb + cb) / 1e4) / cost - 1
    s0 = tr[k0 - 1][2]; res = {}; open_ = dict(exits)
    for k in range(k0, len(tr)):
        t = tr[k]
        for nm, e in list(open_.items()):
            if (e[0] == "h" and t[2] - s0 > e[1]) or (e[0] == "idx" and k > e[1]): res[nm] = val(V, T); del open_[nm]
        if not open_: break
        if t[18] >= GRAD:
            for nm in open_: res[nm] = None
            return res
        if t[15] == 1: dd = T * t[16] // (V + t[16]); V += t[16]; T -= dd
        else: so = V * t[17] // (T + t[17]); V -= so; T += t[17]
    for nm in open_: res[nm] = val(V, T)      # never triggered inside the window: valued at the last state
    return res

def work(key):
    run, b = key; pa = PA1 if run == "R1" else PA2
    want = {m for _, m in jobs[key]}; rows = collections.defaultdict(list)
    for f in glob.glob(os.path.join(pa, f"b{b:03d}", "*.jsonl.gz")):
        try:
            for line in gzip.open(f, "rt"):
                if not line.startswith('["T"'): continue
                r = json.loads(line)
                if r[1] in want and not r[12]: rows[r[1]].append(r)
        except (EOFError, OSError, zlib.error): pass
    out = []
    for w, m in jobs[key]:
        c = L.get(m)
        if not c or m not in rows: continue
        seen = set(); tr = []
        for r in sorted(rows[m], key=lambda r: (r[2], r[3], r[13])):
            if (r[5], r[13]) in seen: continue
            seen.add((r[5], r[13])); tr.append(r)
        S = c["slot"]; ci = c.get("idx"); cs = c.get("sig"); creator = c.get("creator") or c.get("user")
        g = []; prev = ci; gi = 0
        for k, t in enumerate(tr):
            if t[5] == cs: gi = k + 1; continue
            if ci is None: break
            if t[2] == S and t[3] in (prev, prev + 1) and t[15] == 1: g.append(t); prev = t[3]; gi = k + 1
            elif t[2] == S and t[3] > prev + 1: break
            elif t[2] > S: break
        bus = {t[14] for t in g} | {creator, c.get("user")}
        kl = next((k for k, t in enumerate(tr) if t[14] == w and t[15] == 1), None)
        if kl is None: continue
        ks = next((k for k in range(kl + 1, len(tr)) if tr[k][14] == w and tr[k][15] == 0), None)
        fb, cb = (tr[0][22] or 95), (tr[0][23] or 30)
        rec = dict(w=w, m=m, run=run)
        # reactive follow: behind the leader + D trades
        for D in (0, 1, 2, 3):
            k0 = kl + 1 + D
            if k0 >= len(tr): continue
            ex = {f"h{h}": ("h", h) for h in HOLDS}
            if ks is not None and ks + 1 >= k0: ex["mirror"] = ("idx", ks + 1)
            for nm, v in sim(tr, k0, S, fb, cb, ex).items(): rec[f"F{D}_{nm}"] = v
        # pre-emptive copy at our place in line: behind the first K outside trades after the bundle
        for K in (1, 2, 3):
            k0 = gi; seen_o = 0
            while k0 < len(tr) and seen_o < K:
                if tr[k0][14] not in bus: seen_o += 1
                k0 += 1
            if k0 >= len(tr) or k0 == 0: continue
            ex = {f"h{h}": ("h", h) for h in HOLDS}
            if ks is not None and ks + 1 >= k0: ex["mirror"] = ("idx", ks + 1)
            for nm, v in sim(tr, k0, S, fb, cb, ex).items(): rec[f"P{K}_{nm}"] = v
        out.append(rec)
    return out

if __name__ == "__main__":
    allr = []
    with Pool(PROCS) as p:
        for rs in p.imap_unordered(work, list(jobs)): allr.extend(rs)
    by = collections.defaultdict(list)
    for r in allr: by[r["w"]].append(r)
    summ = {}
    cols = [f"F{D}_{e}" for D in (0, 1, 2, 3) for e in ["mirror"] + [f"h{h}" for h in HOLDS]] + [f"P{K}_{e}" for K in (1, 2, 3) for e in ["mirror"] + [f"h{h}" for h in HOLDS]]
    for w, rs in by.items():
        s = {}
        for c in cols:
            for cost in COSTS:
                for run in ("all", "R1", "R2"):
                    v = [r[c] - cost / 0.5 for r in rs if r.get(c) is not None and (run == "all" or r["run"] == run)]
                    if v: s[f"{c}|{cost}|{run}"] = [len(v), round(statistics.mean(v), 4), round(statistics.median(v), 4), round(sum(x > 0 for x in v) / len(v), 3), round(0.5 * sum(v), 3)]
        summ[w] = s
    json.dump(dict(summary=summ, n_trades=len(allr)), open(OUTJ, "w"), separators=(",", ":"))
    print("replayed", len(allr), "leader snipes")
    for w in sorted(summ, key=lambda w: -R[w]["all"]["pnl"]):
        s = summ[w]
        def g(c, cost=0.015, run="all"):
            x = s.get(f"{c}|{cost}|{run}"); return f"{x[1]:+.3f}/{x[4]:+.2f}({x[0]})" if x else "-"
        print(f"{w[:8]} like_us={R[w].get('like_us')} | follow D1 mirror {g('F1_mirror')} R1 {g('F1_mirror', run='R1')} R2 {g('F1_mirror', run='R2')} | D1 h15 {g('F1_h15')} | D2 mirror {g('F2_mirror')} | pre K1 mirror {g('P1_mirror')} K2 {g('P2_mirror')} K2 h15 {g('P2_h15')} | D0 mirror@1% {g('F0_mirror', 0.005)}")
