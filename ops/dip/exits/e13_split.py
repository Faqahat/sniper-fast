#!/usr/bin/env python3
# e13: which half of the learned exit carries the out-of-sample gain? "Cut only" = min(learned tick, 4): sell earlier than today when
# the model says so, never hold longer. "Hold only" = max(learned tick, 4): hold longer when the model says so, never sell earlier.
# Engine SOL/day (measured landing) TRAIN / TEST with the paired 90% CI vs c4, and our real live fills.
import sys, os, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e_eval as V, exit_lib as E, e_apply as AP, e05_report as R5

if __name__ == "__main__":
    lines = []
    def L(s=""): lines.append(s); print(s, flush=True)
    d = V.Data(); D = d.D
    ks = np.load(f"{E.DATA}/e04b_ENS3_ksell.npy")
    tree = np.load(f"{E.DATA}/e09_h1248_direct_d3_ksell.npy")
    P = {"TODAY_c4": np.full(len(ks), 4), "LEARN_ENS3": ks, "cut only (min(learned,4))": np.minimum(ks, 4), "hold only (max(learned,4))": np.maximum(ks, 4),
         "TREE cut only": np.minimum(tree, 4), "TREE hold only": np.maximum(tree, 4)}
    PER = {"train": (V.W0, V.SPLIT), "test": (V.SPLIT, V.W1)}
    L("Learned exit split into its two halves (engine SOL/day, measured landing; TEST diff vs c4 with 90% CI from 30-min blocks)")
    for w in ("M2", "IMIT1"):
        rows = {}
        for nm, k in P.items():
            val, tdec, knd = d.tick_policy(k); pnl = d.pnl(val, 0); r = {}
            for pn, per in PER.items():
                e = d.engine(d.picks(w), pnl, tdec, knd, lmode="meas", R=24, period=per, return_rows=True)
                r[pn] = V.fmt_day(e["pnl"], per); rows[(nm, pn)] = e["rows"]
            s = f"  {w:5s} {nm:28s} TRAIN {r['train']:+6.2f} | TEST {r['test']:+6.2f}"
            if nm != "TODAY_c4":
                for pn in ("train", "test"):
                    bt = R5.block_sums(d, rows[("TODAY_c4", pn)], PER[pn], 24); bx = R5.block_sums(d, rows[(nm, pn)], PER[pn], 24)
                    df = bx - bt; lo, hi = R5.boot_ci(df); sc = 24 / V.hours(PER[pn])
                    s += f" | {pn} diff {df.sum() * sc:+5.2f} [{lo * sc:+5.2f}, {hi * sc:+5.2f}]"
            L(s)
    # live fills
    dl = V.Data(paths=f"{E.DATA}/paths/paths_live.npz")
    idx = [x for x in json.load(open(f"{E.DATA}/paths/live_index.json")) if x["st"] == 0]
    te = np.array([x["t"] for x in idx]) >= V.SPLIT
    kl, _ = AP.apply_saved(dl, f"{E.DATA}/e04b_ENS3_model.pkl"); kt = AP.apply_tree(dl, f"{E.DATA}/e09_h1248_direct_d3.pkl")
    p4 = dl.pnl(dl.tick_policy(np.full(len(kl), 4))[0], 0)
    L("\nour real live fills (exact landing): diff vs c4, SOL (train hours n 66 | test hours n 62)")
    rng = np.random.default_rng(2)
    for nm, k in (("LEARN_ENS3", kl), ("cut only", np.minimum(kl, 4)), ("hold only", np.maximum(kl, 4)), ("TREE", kt), ("TREE cut only", np.minimum(kt, 4)), ("TREE hold only", np.maximum(kt, 4))):
        p = dl.pnl(dl.tick_policy(k)[0], 0); s = f"  {nm:16s}"
        for pn, m in (("train", ~te), ("test", te)):
            df = p[m] - p4[m]; bs = [df[rng.integers(0, m.sum(), m.sum())].sum() for _ in range(3000)]
            s += f" | {pn} {df.sum():+.3f} [{np.percentile(bs, 5):+.3f}, {np.percentile(bs, 95):+.3f}]"
        L(s)
    open(f"{E.DATA}/e13_split.txt", "w").write("\n".join(lines) + "\n")
