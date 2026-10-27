#!/usr/bin/env python3
# e14: the transferable half of the learned exit as a SIMPLE engine rule, chosen on TRAIN only (maximin over 6 cells as e10).
# CUT(X, kmin, cap): keep today's timer (sell at tick `cap`), but at the start of each slot k >= kmin before that, SELL EARLY if no
# outside buy has landed for >= X ms (block clock; the engine sees this on its own trade feed). Never holds longer than today.
# Then: TEST (M2 / IMIT1, landing rows, CIs), our real live fills, the +crowd stress.
# -> /home/moiz/sniper-data/exits/e14_cut.txt/.json
import sys, os, json, time, itertools
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import e_eval as V, exit_lib as E, e05_report as R5

CELLS = [("10-24 09:45", "10-24 15:00"), ("10-24 15:00", "10-24 21:00"), ("10-24 21:00", "10-25 01:00")]


def cut_rule(d, X, kmin, cap):
    F = d.ft; I = d.TFI; K = d.K
    stale = F[:, :, I["stall_ms"]] >= X
    ks = np.arange(1, K + 1)[None, :]
    sell = (stale & (ks >= kmin)) | (ks >= cap)
    return d.tick_policy(sell.argmax(1) + 1)


if __name__ == "__main__":
    T0 = time.time()
    lines = []
    def L(s=""): lines.append(s); print(s, flush=True)
    d = V.Data(); D = d.D
    per = [(E.pk(a), E.pk(b)) for a, b in CELLS]
    def cells(pol):
        val, tdec, knd = pol; pnl = d.pnl(val, 0); out = []
        for w in ("M2", "IMIT1"):
            for p in per:
                e = d.engine(d.picks(w), pnl, tdec, knd, lmode="meas", R=16, period=p); out.append(V.fmt_day(e["pnl"], p))
        return np.array(out)
    base = cells(d.tick_policy(np.full(len(d.s_in), 4)))
    grid = list(itertools.product((100, 150, 192, 250, 300, 424, 636), (1, 2, 3), (4, 5)))
    res = {str(g): (cells(cut_rule(d, *g)) - base).tolist() for g in grid}
    order = sorted(grid, key=lambda g: (-min(res[str(g)]), -sum(res[str(g)])))
    L(f"CUT(X ms stale, kmin, cap) on TRAIN, worst-cell gain over c4 (SOL/day), cells M2 x 3 periods, IMIT1 x 3 periods; c4 cells {np.round(base, 2).tolist()}")
    for g in order[:12]:
        r = res[str(g)]; L(f"  {str(g):18s} worst {min(r):+.2f} sum {sum(r):+.2f} {np.round(r, 2).tolist()}")
    best = order[0]
    L(f"\nCHOSEN on TRAIN: CUT{best}")
    # ---- TEST, landing rows, CIs
    PER = {"train": (V.W0, V.SPLIT), "test": (V.SPLIT, V.W1)}
    pols = {"TODAY_c4": d.tick_policy(np.full(len(d.s_in), 4)), f"CUT{best}": cut_rule(d, *best)}
    for w in ("M2", "IMIT1"):
        rows = {}
        for nm, (val, tdec, knd) in pols.items():
            pnl = d.pnl(val, 0); s = f"  {w:5s} {nm:18s}"
            for pn in ("train", "test"):
                for lm in (("meas", "35", "50", "75") if pn == "test" else ("meas",)):
                    e = d.engine(d.picks(w), pnl, tdec, knd, lmode=lm, R=24, period=PER[pn], return_rows=(lm == "meas"))
                    s += f" {pn} {lm} {V.fmt_day(e['pnl'], PER[pn]):+6.2f} |"
                    if lm == "meas": rows[(nm, pn)] = e["rows"]
            L(s)
        nm = f"CUT{best}"
        for pn in ("train", "test"):
            bt = R5.block_sums(d, rows[("TODAY_c4", pn)], PER[pn], 24); bx = R5.block_sums(d, rows[(nm, pn)], PER[pn], 24)
            df = bx - bt; lo, hi = R5.boot_ci(df); sc = 24 / V.hours(PER[pn])
            ids, e4 = R5.per_dump_expect(d, d.pnl(pols["TODAY_c4"][0], 0), d.picks(w), PER[pn]); _, ex = R5.per_dump_expect(d, d.pnl(pols[nm][0], 0), d.picks(w), PER[pn])
            dd = ex - e4; lo2, hi2 = R5.boot_ci(dd, stat=np.mean)
            L(f"     {w} {pn}: diff {df.sum() * sc:+.2f} SOL/day [{lo * sc:+.2f}, {hi * sc:+.2f}] | per dump {1000 * dd.mean():+.2f} mSOL [{1000 * lo2:+.2f}, {1000 * hi2:+.2f}]")
    # ---- live fills
    dl = V.Data(paths=f"{E.DATA}/paths/paths_live.npz")
    idx = [x for x in json.load(open(f"{E.DATA}/paths/live_index.json")) if x["st"] == 0]
    te = np.array([x["t"] for x in idx]) >= V.SPLIT
    p4 = dl.pnl(dl.tick_policy(np.full(len(dl.s_in), 4))[0], 0); pc = dl.pnl(cut_rule(dl, *best)[0], 0)
    rng = np.random.default_rng(4); s = "  live fills (exact landing) diff vs c4:"
    for pn, m in (("train hours", ~te), ("test hours", te)):
        df = pc[m] - p4[m]; bs = [df[rng.integers(0, m.sum(), m.sum())].sum() for _ in range(3000)]
        s += f" | {pn} n {m.sum()} {df.sum():+.3f} SOL [{np.percentile(bs, 5):+.3f}, {np.percentile(bs, 95):+.3f}]"
    L(s)
    # ---- +crowd stress
    dc = V.Data(paths=f"{E.DATA}/paths/paths2_crowd.npz")
    for w in ("M2", "IMIT1"):
        a = dc.engine(dc.picks(w), dc.pnl(dc.tick_policy(np.full(len(dc.s_in), 4))[0], 0), *dc.tick_policy(np.full(len(dc.s_in), 4))[1:], lmode="meas", R=24, period=PER["test"])
        vb, tb, kb = cut_rule(dc, *best)
        b = dc.engine(dc.picks(w), dc.pnl(vb, 0), tb, kb, lmode="meas", R=24, period=PER["test"])
        L(f"  +crowd stress TEST {w}: c4 {V.fmt_day(a['pnl'], PER['test']):+.2f} vs CUT {V.fmt_day(b['pnl'], PER['test']):+.2f} SOL/day")
    json.dump(dict(res=res, best=list(best)), open(f"{E.DATA}/e14_cut.json", "w"))
    open(f"{E.DATA}/e14_cut.txt", "w").write("\n".join(lines) + "\n")
    print(f"done {time.time() - T0:.0f} s")
