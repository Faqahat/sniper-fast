#!/usr/bin/env python3
# READ-ONLY, offline follow-up tests for Q7 (same mechanics as q6.py: rp.sim, size 0.5, fill_pen 1.5%, slip, fast-sniper removal).
# (A) FiFawH-style exits at OUR snipe landing (L45/L75 + 1% guard) on its picks (oracle) and on random launches:
#     t3 = all at ~3 s | half@1.15x, rest @8 s, stop 0.95 | trail (arm 1.1x, -15%), stop 0.93, cap 10 s | half@1.1x rest@5 s
# (B) Momentum-confirmed LATER entry on any launch (generic): decide at t_d = 1 / 2 s if the non-insider buy flow seen
#     before t_d is strong; land after every trade up to t_d + 0.4 s; 0.5% send cost; exits ~2 / 5 / 10 s.
import sys, json, collections, math
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/fifaw/copy")
import q6, rp
from multiprocessing import Pool
SETS = q6.SETS
EXA = [rp.R("t3", [(1.0, ("t", 3.0))], 4), rp.R("half115_t8", [(0.5, ("x", 1.15)), (1.0, ("t", 8.0)), (1.0, ("sl", 0.95))], 9),
       rp.R("trail", [(1.0, ("dd", 1.1, 0.15)), (1.0, ("sl", 0.93)), (1.0, ("t", 10.0))], 11), rp.R("half110_t5", [(0.5, ("x", 1.10)), (1.0, ("t", 5.0))], 6),
       rp.R("t5", [(1.0, ("t", 5.0))], 6)]
EXB = [rp.R("t2", [(1.0, ("t", 2.0))], 3), rp.R("t5", [(1.0, ("t", 5.0))], 6), rp.R("t10", [(1.0, ("t", 10.0))], 11)]
CONDS = {"k>=5&net>=2": (5, 2.0), "k>=10&net>=5": (10, 5.0), "k>=20&net>=10": (20, 10.0)}
def flow(tr, c, st, td):
    S = c["slot"]; b = set(); bs = 0; ss = 0
    for t in tr:
        if (t["s"] - S) * q6.SLOT >= td: break
        if t["user"] in st["insiders"]: continue
        if t["buy"]: b.add(t["user"]); bs += t["sol"]
        else: ss += t["sol"]
    return len(b), (bs - ss) / 1e9
def work(job):
    run, b, ms = job; q6.init(); tra = q6.read(run, b, ms); fa = rp.read_failed(run, b, ms) if run == "R2" else {}; out = {}
    for m, tr in tra.items():
        c = dict(q6.L[m]); c["mint"] = m
        if "InitializeMayhemState" in (c.get("ixn") or []): continue
        st = rp.structure(tr, c); p_b = q6.ref_price(tr, st)
        if not p_b: continue
        r = dict(run=c["run"], A={}, B={})
        for mode in ("L45", "L75"):
            idx = q6.place(mode, tr, c, st, fa.get(m, []))
            if idx is None: continue
            pr = (tr[idx - 1]["vsol"] / tr[idx - 1]["vtok"]) if idx > 0 and tr[idx - 1]["vtok"] else 30e9 / 1.073e15
            if pr / p_b > 1.01: r["A"][mode] = None; continue
            res = {}
            for vn, rm in (("v1", None), ("v3", q6.FAST)):
                p = q6.strip(tr, idx, rm)
                o = rp.sim(p, c, st, idx, q6.B, EXA, fee_buy_pct=0.02, fill_pen=0.015, slip=q6.SL) if p else None
                if o: res[vn] = {k: v["pnl"] for k, v in o.items()}
            if res: r["A"][mode] = res
        for td in (1.0, 2.0):
            k, net = flow(tr, c, st, td)
            k_land = math.floor((td + 0.4) / q6.SLOT); idx = next((i for i, t in enumerate(tr) if t["s"] - c["slot"] > k_land), len(tr)); idx = max(idx, st["g_end"])
            res = dict(k=k, net=round(net, 3))
            for vn, rm in (("v1", None), ("v3", q6.FAST)):
                p = q6.strip(tr, idx, rm)
                o = rp.sim(p, c, st, idx, q6.B, EXB, fee_buy_pct=0.005, fill_pen=0.015, slip=q6.SL) if p and idx <= len(p) else None
                if o: res[vn] = {kk: v["pnl"] for kk, v in o.items()}
            r["B"][str(td)] = res
        out[m] = r
    return out
if __name__ == "__main__":
    mints = set(SETS["(a) oracle: its attempts"]) | set(SETS["(z) random control launches"]) | set(SETS["(a') oracle: its filled buys"])
    byb = collections.defaultdict(set)
    for m in mints:
        if m in q6.L: byb[(q6.L[m]["run"], rp.bucket(m))].add(m)
    RES = {}
    with Pool(8) as p:
        for o in p.imap_unordered(work, [(r, b, ms) for (r, b), ms in byb.items()]): RES.update(o)
    json.dump(RES, open("q7_tests.json", "w"))
    lines = []
    for sn in ("(a) oracle: its attempts", "(z) random control launches"):
        for mode in ("L45", "L75"):
            for vn in ("v1", "v3"):
                agg = collections.defaultdict(lambda: {"R1": 0.0, "R2": 0.0}); nf = collections.Counter(); nfail = collections.Counter()
                for m in SETS[sn]:
                    r = RES.get(m)
                    if not r or mode not in r["A"]: continue
                    if r["A"][mode] is None: nfail[r["run"]] += 1; continue
                    if vn not in r["A"][mode]: continue
                    nf[r["run"]] += 1
                    for e, v in r["A"][mode][vn].items(): agg[e][r["run"]] += v
                lines.append(f"(A) {sn[:24]} {mode} {vn} fills R1 {nf['R1']} R2 {nf['R2']} (guard fails {nfail['R1']}/{nfail['R2']}, -0.005 each not included): " +
                             " | ".join(f"{e} {v['R1'] + v['R2']:+.2f} ({v['R1']:+.2f}/{v['R2']:+.2f})" for e, v in agg.items()))
    for sn in ("(z) random control launches", "(a) oracle: its attempts"):
        for td in ("1.0", "2.0"):
            for cn, (kk, nn) in CONDS.items():
                for vn in ("v1", "v3"):
                    agg = collections.defaultdict(lambda: {"R1": 0.0, "R2": 0.0}); n = collections.Counter()
                    for m in SETS[sn]:
                        r = RES.get(m)
                        if not r or td not in r["B"]: continue
                        b = r["B"][td]
                        if b["k"] < kk or b["net"] < nn or vn not in b: continue
                        n[r["run"]] += 1
                        for e, v in b[vn].items(): agg[e][r["run"]] += v
                    lines.append(f"(B) {sn[:24]} t_d={td} {cn:14} {vn} n R1 {n['R1']} R2 {n['R2']}: " + " | ".join(f"{e} {v['R1'] + v['R2']:+.2f} ({v['R1']:+.2f}/{v['R2']:+.2f}) mean {(v['R1'] + v['R2']) / max(1, n['R1'] + n['R2']):+.3f}" for e, v in agg.items()))
    open("q7_tests.txt", "w").write("\n".join(lines)); print("\n".join(lines))
