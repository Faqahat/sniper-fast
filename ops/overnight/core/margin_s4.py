# how much time margin do S4 fills have? For each guarded fill at L ms: arrival (our clock) of the first outside trade that
# lands right after our position. If it arrives long after our landing, small timing errors cannot put it ahead of us.
import sys, json, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
exec(open("/home/moiz/sniper/ops/overnight/core/ana_rate_wf.py").read().split("for name, f in")[0])
S3 = {r["mint"] for r in rows if (lambda a, n: a >= 2 and (n == 0 or a / n >= 0.10))(*state[r["mint"]])}
O = rp.load_obs()
byb = collections.defaultdict(set)
for m in S3: byb[rp.bucket(m)].add(m)
G = 0.01; out = collections.defaultdict(list)
for b, ms in byb.items():
    tra = rp.read_bucket("R2", b, ms); fa = rp.read_failed("R2", b, ms)
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9: continue
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; outs = O[m]["outs"]
        # matched arrival for every outside trade
        S = c["slot"]; used = set(); arr = {}
        cand = [(k, t) for k, t in enumerate(tr) if k >= st["g_end"] and t["s"] - S <= 6 and t["user"] not in st["insiders"]]
        for a, sol, isbuy, w6 in sorted(outs):
            for k, t in cand:
                if k in used or t["buy"] != isbuy or not t["user"].startswith(w6): continue
                if isbuy and sol > 0 and abs(t["sol"] / 1e9 - sol) > max(0.02, 0.15 * sol): continue
                used.add(k); arr[k] = a; break
        for Lm in (45, 60, 75):
            ib, _ = rp.place_bo2(tr, c, st, outs, Lm, fa.get(m, []))
            if ib < 1 or (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b > 1 + G: continue
            pnl = rp.flip(tr, ib, rp.place_ms(tr, c, st, outs, 500, ib), 0.5)
            nxt = next(((k, t) for k, t in cand if k >= ib), None)
            if nxt is None: margin = None
            else:
                k, t = nxt
                margin = arr.get(k)   # arrival of the next outside trade (None = our engine never saw it)
                moves = (t["vsol"] / t["vtok"]) / p_b > 1 + G if t["buy"] else False
            out[Lm].append((margin, pnl, nxt is not None and nxt[1]["s"] - S))
for Lm, v in out.items():
    seen = [x for x in v if x[0] is not None]
    lab = lambda a: "no later trade" if a is None else ("<+10 ms" if a - Lm < 10 else "+10-25" if a - Lm < 25 else "+25-50" if a - Lm < 50 else "+50-100" if a - Lm < 100 else "+100 ms+")
    g = collections.defaultdict(list)
    for a, p, ds in v: g[lab(a)].append(p)
    print(f"L{Lm}: {len(v)} guarded fills; next outside trade arrives after our landing by: " + " | ".join(f"{k}: n {len(x)} pnl {sum(x):+.2f}" for k, x in sorted(g.items())))
