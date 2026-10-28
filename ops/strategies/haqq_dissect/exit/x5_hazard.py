#!/usr/bin/env python3
"""EXIT step 5 (read-only): what makes haqq sell a lot - a discrete-time hazard on his non-DEAD lots (MEASURED).
Grid: every 100 ms from his buy (chain clock) until his exit (the sell that closed the lot; lots whose exit is inside the
300-slot path). At grid time t the state is built only from outside trades landed at or before t (what he could have seen):
  ret     = the lot's sell value / cost on the real tape (va)                     max_ret = highest ret so far
  slots   = current slot - his buy slot (from the chain clock at t)
  b300 / s300 = outside buy / sell SOL landed in (t-300 ms, t]                     bmax300 = biggest outside buy in it
  new_hi  = a new max ret was set in (t-300, t]
Label: his exit lands in (t, t+150 ms]. Hazard = labelled steps / steps (per 150 ms). Tables by state bins, per day.
Out: haqq_dissect/exit/x5.txt, hazard.npz"""
import pickle, sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
import xlib as X
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)


def build():
    Z = pickle.load(open(f"{X.OUT}/haqq.pkl", "rb")); LOTS = Z["lots"]; POS = Z["pos"]
    A = np.load(f"{X.OUT}/paths.npz")
    off = A["off"]; ex = A["lot_exit"]; dcc = A["dcc"]; dsl = A["dsl"]; bu = A["buy"]; so = A["sol"]; va = A["va"]
    cols = collections.defaultdict(list)
    for i, L in enumerate(LOTS):
        if L["t"] == "DEAD" or L["close_cc"] is None: continue
        a, b = off[i], off[i + 1]; n = b - a; e = ex[i]
        if e <= 0 or e >= n: continue
        xt = L["close_cc"] - L["cc"]
        g = np.arange(100.0, xt, 100.0)
        if not len(g): continue
        dc = dcc[a:b].astype(np.float64)
        kk = np.searchsorted(dc, g, side="right") - 1                          # last outside row at or before t
        v = va[a:b].astype(np.float64)
        ret = np.where(kk >= 0, v[np.maximum(kk, 0)] - 1, np.nan)
        cm = np.maximum.accumulate(np.where(np.isfinite(v), v, -1))
        mret = np.where(kk >= 0, cm[np.maximum(kk, 0)] - 1, np.nan)
        cb = np.concatenate([[0], np.cumsum(np.where(bu[a:b], so[a:b], 0))]); cs = np.concatenate([[0], np.cumsum(np.where(~bu[a:b], so[a:b], 0))])
        k3 = np.searchsorted(dc, g - 300, side="right") - 1
        b300 = cb[kk + 1] - cb[k3 + 1]; s300 = cs[kk + 1] - cs[k3 + 1]
        # biggest buy in window, new high in window
        bmax = np.zeros(len(g)); nh = np.zeros(len(g), bool)
        bb = np.where(bu[a:b], so[a:b], 0.0)
        for q in np.flatnonzero(kk > k3):
            bmax[q] = bb[k3[q] + 1:kk[q] + 1].max()
            prev = cm[k3[q]] if k3[q] >= 0 else -1
            nh[q] = cm[kk[q]] > prev + 1e-9
        sl = np.searchsorted(dc, g, side="right")
        slots = np.floor((L["cc"] + g) / X.SMS).astype(np.int64) - L["slot"]          # current slot since his buy (chain clock)
        lab = (xt > g) & (xt <= g + 150)
        cols["lot"].append(np.full(len(g), i)); cols["t"].append(g); cols["ret"].append(ret); cols["mret"].append(mret)
        cols["b300"].append(b300); cols["s300"].append(s300); cols["bmax"].append(bmax); cols["nh"].append(nh); cols["slots"].append(slots)
        cols["lab"].append(lab); cols["day"].append(np.full(len(g), L["day"])); cols["add"].append(np.full(len(g), L["add"]))
    H = {k: np.concatenate(v) for k, v in cols.items()}
    np.savez(f"{X.OUT}/hazard.npz", **H)
    return H


def tab(H, m_all, name, groups):
    P(f"\n### {name}")
    P("| state | steps | exits in next 150 ms | hazard % | lift vs all |"); P("|---|---|---|---|---|")
    base = H["lab"][m_all].mean()
    for gname, m in groups:
        mm = m_all & m
        if mm.sum() < 200: continue
        h = H["lab"][mm].mean()
        P(f"| {gname} | {mm.sum():,} | {H['lab'][mm].sum():,} | {100 * h:.2f} | {h / base:.2f} |")


def main():
    H = build()
    P("# haqq's exit hazard (non-DEAD lots, exit inside 300 slots), MEASURED on the tape 10-22 03:07 -> 10-28 01:12 PKT")
    P(f"grid steps {len(H['lab']):,}, lots {len(np.unique(H['lot'])):,}, exits labelled {H['lab'].sum():,}")
    allm = np.ones(len(H["lab"]), bool)
    r = H["ret"]; s = H["slots"]
    tab(H, allm, "by slots since his buy", [(f"{a}-{b - 1}", (s >= a) & (s < b)) for a, b in ((0, 2), (2, 3), (3, 5), (5, 8), (8, 10), (10, 15), (15, 20), (20, 30), (30, 50), (50, 300))])
    tab(H, allm & (s >= 2), "by lot return now (slots >= 2)", [(f"{a:+.0%}..{b:+.0%}", (r >= a) & (r < b)) for a, b in ((-1, -.2), (-.2, -.1), (-.1, -.05), (-.05, -.02), (-.02, .02), (.02, .05), (.05, .1), (.1, .2), (.2, .4), (.4, 9))])
    tab(H, allm & (s >= 2), "by outside buy SOL in the last 300 ms (slots >= 2)", [(f"{a}-{b}", (H["b300"] >= a) & (H["b300"] < b)) for a, b in ((0, 1e-9), (1e-9, .1), (.1, .3), (.3, .7), (.7, 1.5), (1.5, 3), (3, 1e9))])
    tab(H, allm & (s >= 2), "by outside sell SOL in the last 300 ms (slots >= 2)", [(f"{a}-{b}", (H["s300"] >= a) & (H["s300"] < b)) for a, b in ((0, 1e-9), (1e-9, .1), (.1, .3), (.3, .7), (.7, 1.5), (1.5, 3), (3, 1e9))])
    tab(H, allm & (s >= 2), "new high of the lot's return in the last 300 ms (slots >= 2)", [("new high", H["nh"]), ("no new high", ~H["nh"])])
    dd = H["mret"] - H["ret"]
    tab(H, allm & (s >= 2) & (H["mret"] >= 0.05), "give-back from the best return (best >= +5%, slots >= 2)", [(f"{a:.0%}-{b:.0%}", (dd >= a) & (dd < b)) for a, b in ((0, .01), (.01, .03), (.03, .06), (.06, .1), (.1, .2), (.2, 9))])
    # 2-D: slots x return
    P("\n### hazard % per 150 ms: slots since buy (rows) x lot return now (cols)")
    rb = ((-1, -.1), (-.1, -.03), (-.03, .03), (.03, .1), (.1, .25), (.25, 9))
    P("| slots | " + " | ".join(f"{a:+.0%}..{b:+.0%}" for a, b in rb) + " |"); P("|---|" + "---|" * len(rb))
    for a, b in ((2, 5), (5, 10), (10, 15), (15, 25), (25, 40), (40, 300)):
        cells = []
        for x, y in rb:
            m = (s >= a) & (s < b) & (r >= x) & (r < y)
            cells.append(f"{100 * H['lab'][m].mean():.1f} ({m.sum() // 1000}k)" if m.sum() >= 300 else "-")
        P(f"| {a}-{b - 1} | " + " | ".join(cells) + " |")
    P("\n### hazard % per 150 ms: outside buy SOL in last 300 ms (rows) x lot return now (cols), slots >= 2")
    P("| buy SOL | " + " | ".join(f"{a:+.0%}..{b:+.0%}" for a, b in rb) + " |"); P("|---|" + "---|" * len(rb))
    for a, b in ((0, 1e-9), (1e-9, .3), (.3, 1), (1, 3), (3, 1e9)):
        cells = []
        for x, y in rb:
            m = (s >= 2) & (H["b300"] >= a) & (H["b300"] < b) & (r >= x) & (r < y)
            cells.append(f"{100 * H['lab'][m].mean():.1f} ({m.sum() // 1000}k)" if m.sum() >= 300 else "-")
        P(f"| {a:g}-{b:g} | " + " | ".join(cells) + " |")
    P("\n### per day: hazard with buy SOL >= 0.3 in last 300 ms & ret >= +3% vs base (slots >= 2)")
    for d in range(7):
        m = (H["day"] == d) & (s >= 2)
        if m.sum() < 1000: continue
        mm = m & (H["b300"] >= 0.3) & (r >= 0.03)
        P(f"- D{d}: base {100 * H['lab'][m].mean():.2f}%, trigger {100 * H['lab'][mm].mean():.2f}% (n {mm.sum():,}), lift {H['lab'][mm].mean() / H['lab'][m].mean():.2f}")
    P("\n### ADD lots vs first lots (slots >= 2): hazard by return")
    for nm, m0 in (("first lots", ~H["add"]), ("ADD lots", H["add"])):
        tab(H, m0 & (s >= 2), nm, [(f"{a:+.0%}..{b:+.0%}", (r >= a) & (r < b)) for a, b in ((-1, -.1), (-.1, -.03), (-.03, .03), (.03, .1), (.1, .25), (.25, 9))])
    open(f"{X.OUT}/x5.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
