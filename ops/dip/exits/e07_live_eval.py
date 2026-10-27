#!/usr/bin/env python3
# e07: exits on our REAL live buys at their exact chain landing (e06 paths_live), 0.35 SOL, corrected replay, FIX 0.0045.
# No landing model, no engine (the fires are what the engine really did). Per fill P&L by exit, TRAIN-hours vs TEST-hours fires,
# crowded vs quiet, with a paired bootstrap vs today's exit.
# usage: nice python3 -I e07_live_eval.py [learned model pkl tags, comma] -> /home/moiz/sniper-data/exits/e07_live.txt
import sys, os, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e_eval as V, exit_lib as E, e03_baselines as B, e_apply as AP, e08_rules as R8, e10_select as R10

if __name__ == "__main__":
    tags = [x for x in (sys.argv[1].split(",") if len(sys.argv) > 1 else []) if x]
    d = V.Data(paths=f"{E.DATA}/paths/paths_live.npz")
    idx = json.load(open(f"{E.DATA}/paths/live_index.json"))
    fills = [x for x in idx if x["st"] == 0]
    assert len(fills) == len(d.t_did)
    tfire = np.array([x["t"] for x in fills]); srv = np.array([x["srv"] for x in fills])
    P = {"TODAY_c4": d.tick_policy(np.full(len(d.s_in), 4)), "RUN10-14_c5_sl10": d.tpsl(5, sl=0.10), "paper_c6_sl10": d.tpsl(6, sl=0.10),
         "STALL2_k2_c30": B.stall_policy(d, 2, 2, 0.0, 30), "TPSL_c4_tp40_sl10": d.tpsl(4, tp=0.40, sl=0.10),
         "TPSL_c4_tp20_sl20": d.tpsl(4, tp=0.20, sl=0.20), "haqq_check": B.haqq_check(d), "cap2": d.tick_policy(np.full(len(d.s_in), 2)),
         "CROWDHOLD_1_4_2_2_0_30": R8.crowdhold(d, 1, 4, 2, 2, 0.0, 30), "CROWDHOLD_2_3_3_2_.5_12": R8.crowdhold(d, 2, 3, 3, 2, 0.5, 12),
         "HOLD_IF_BUY03_k2_c30": R10.buying_rule(d, 424, 0.3, 2, None, 30),
         "TREE_direct_d3": d.tick_policy(AP.apply_tree(d, f"{E.DATA}/e09_h1248_direct_d3.pkl")),
         "TREE_distill_d3": d.tick_policy(AP.apply_tree(d, f"{E.DATA}/e09_h1248_distill_d3.pkl"))}
    for tg in tags:
        pkl = next(p for p in (f"{E.DATA}/e04_{tg}_model.pkl", f"{E.DATA}/e04b_{tg}_model.pkl", f"{E.DATA}/{tg}_model.pkl") if os.path.exists(p))
        ks, _ = AP.apply_saved(d, pkl)
        P[f"LEARN_{tg}"] = d.tick_policy(ks)
    P["ORACLE"] = B.oracle(d)
    crowd = d.tg_n3[d.t_did]
    lines = []
    def L(s=""): lines.append(s); print(s)
    L(f"EXITS ON OUR REAL LIVE BUYS at their exact chain position (309 fires, {len(fills)} replay fills; 0.35 SOL; FIX {E.FIX}; sell landing MEASURED)")
    L("fires in TRAIN hours (before 10-25 01:00 PKT) vs TEST hours (01:00 -> 07:50). SOL total over the fills | mSOL per fill")
    per = {"train": tfire < V.SPLIT, "test": tfire >= V.SPLIT}
    p4 = d.pnl(P["TODAY_c4"][0], 0)
    rng = np.random.default_rng(3)
    for nm, (val, tdec, kind) in P.items():
        p = d.pnl(val, 0); s = f"{nm:22s}"
        for pn, m in per.items():
            dd = p[m] - p4[m]
            bs = [dd[rng.integers(0, m.sum(), m.sum())].sum() for _ in range(3000)]
            s += f" | {pn} n {m.sum():3d}: {p[m].sum():+6.3f} ({1000 * p[m].mean():+5.1f}/fill) diff vs c4 {dd.sum():+6.3f} [{np.percentile(bs, 5):+.3f}, {np.percentile(bs, 95):+.3f}]"
        for sn, f in (("quiet0-1", crowd <= 1), ("2", crowd == 2), ("crowd3+", crowd >= 3)):
            s += f" | {sn} {1000 * p[f].mean():+5.1f}"
        hold = ((tdec - d.a_in) / E.SMS).mean()
        L(s + f" | hold {hold:4.1f} slots")
    L(f"\ncrowd counts (fills): quiet0-1 {(crowd <= 1).sum()}, 2: {(crowd == 2).sum()}, crowd3+ {(crowd >= 3).sum()}; servers FRA {(srv == 'FRA').sum()} AMS {(srv == 'AMS').sum()}")
    open(f"{E.DATA}/e07_live.txt", "w").write("\n".join(lines) + "\n")
