#!/usr/bin/env python3
"""VERIFY v1b: tables from v1_rsim_fwd.py output (G2's r8 definitions re-implemented: per fill NOW cost 2.015 mSOL, failed tries
5,120 lamports, cal = 0.81 x added fill P&L when > 0, ADDED = (base + re) - base on the same draw). Per hour (PKT) and total,
mean over draws and each draw. usage: v1b_report.py RESPKL"""
import sys, pickle, collections, time
import numpy as np

COST = 5120 + 200_000 + 605_000 + 1_200_000 + 5020
FAIL = 5120


def pkt(t): return time.strftime("%m-%d %H:%M", time.gmtime(int(t) + 18000))


def agg(rows, s2b, v="base"):
    """per hour: fills, fill P&L (after per-fill cost) lamports, fees lamports, re fills"""
    H = collections.defaultdict(lambda: np.zeros(4))
    for r in rows:
        if not r[1]: continue
        key = r[0]; slot = key[2]
        bt = s2b(slot); h = (bt + 18000) // 3600 * 3600 - 18000
        a = H[h]
        a[2] += r[4] * FAIL
        if r[3]:
            a[0] += 1; a[1] += r[8][2][v][0] - COST
            if key[0] == "re": a[3] += 1
    return H


def net(dpf, dfee, lvl):
    if lvl == "model": return dpf - dfee
    return (0.81 * dpf if dpf > 0 else dpf) - dfee


if __name__ == "__main__":
    Z = pickle.load(open(sys.argv[1], "rb"))
    sl, bt = Z["smap_slots"]; sl = sl.astype(np.int64); bt = bt.astype(np.int64)
    def s2b(s):
        k = min(max(int(np.searchsorted(sl, s)), 0), len(sl) - 1); return int(bt[k])
    name = Z["cfg"]["name"]; out = Z["out"]; nd = len(out["base"])
    print(f"cfg {name}; T2 {Z['n_t2']}, whale dumps {Z['n_ev']}, re windows {Z['n_re']}; draws {nd}; usable hours: " +
          ", ".join(f"{pkt(h)} cov {v[0]:.3f}" for h, v in sorted(Z["hours"].items())))
    hrs = sorted(Z["hours"])
    variants = [("model", "base"), ("cal", "base"), ("cal", "cut10"), ("cal", "cut20"), ("cal", "wave")]
    res = collections.defaultdict(list)            # (hour or 'ALL', label) -> per draw values
    for d in range(nd):
        for lvl, v in variants:
            Hb = agg(out["base"][d], s2b, v); Hc = agg(out[name][d], s2b, v)
            tot = np.zeros(2)
            for h in hrs:
                b = Hb.get(h, np.zeros(4)); c = Hc.get(h, np.zeros(4))
                dpf = (c[1] - b[1]) / 1e9; dfe = (c[2] - b[2]) / 1e9
                res[(h, f"{lvl}:{v}")].append(net(dpf, dfe, lvl)); tot += [dpf, dfe]
                if lvl == "model" and v == "base":
                    res[(h, "fills_add")].append(c[0] - b[0]); res[(h, "re_fills")].append(c[3]); res[(h, "base_fills")].append(b[0])
                    res[(h, "base_net")].append((b[1] - b[2]) / 1e9); res[(h, "re_pf")].append(None)
            res[("ALL", f"{lvl}:{v}")].append(net(tot[0], tot[1], lvl))
        # re-window fill P&L per fill (model, live exit) and fees
        rr = [r for r in out[name][d] if r[1] and r[0][0] == "re"]
        pf = [r[8][2]["base"][0] - COST for r in rr if r[3]]
        res[("ALL", "re_fill_mean_msol")].append(np.mean(pf) / 1e6 if pf else 0)
        res[("ALL", "re_fills")].append(len(pf)); res[("ALL", "re_win")].append(sum(1 for x in pf if x > 0))
        res[("ALL", "re_fees")].append(sum(r[4] for r in rr) * FAIL / 1e9)
    print("\n| Hour (PKT) | Base fills | Base model net | Re fills | Added fills | ADDED model | x0.81 | 10% fewer fol (cal) | 20% fewer (cal) | Wave exit (cal) |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for h in hrs:
        g = lambda k: np.mean(res[(h, k)])
        print(f"| {pkt(h)} | {g('base_fills'):.0f} | {g('base_net'):+.3f} | {g('re_fills'):.1f} | {g('fills_add'):+.1f} | {g('model:base'):+.3f} | {g('cal:base'):+.3f} | "
              f"{g('cal:cut10'):+.3f} | {g('cal:cut20'):+.3f} | {g('cal:wave'):+.3f} |")
    g = lambda k: np.mean(res[("ALL", k)])
    print(f"| **Total** | | | {g('re_fills'):.1f} | | **{g('model:base'):+.3f}** | {g('cal:base'):+.3f} | {g('cal:cut10'):+.3f} | {g('cal:cut20'):+.3f} | {g('cal:wave'):+.3f} |")
    print("\nper draw (ADDED model / cal / cut10 cal / wave cal): " + "; ".join(
        f"d{d}: {res[('ALL', 'model:base')][d]:+.3f} / {res[('ALL', 'cal:base')][d]:+.3f} / {res[('ALL', 'cal:cut10')][d]:+.3f} / {res[('ALL', 'cal:wave')][d]:+.3f}" for d in range(nd)))
    print(f"re fills {np.mean(res[('ALL','re_fills')]):.1f} (wins {np.mean(res[('ALL','re_win')]):.1f}), re fill P&L mean {np.mean(res[('ALL','re_fill_mean_msol')]):+.2f} mSOL/fill (after 2.015 cost), re-window failed-try fees {np.mean(res[('ALL','re_fees')]):.3f} SOL")
    nh = sum(1 for h in hrs for _ in [0]); span = sum((Z["hours"][h][3] - max(Z["hours"][h][2], 1793131823)) for h in hrs) / 3600
    print(f"fresh usable span ~{span:.2f} h -> ADDED model {g('model:base') / span:+.3f} SOL/h ({24 * g('model:base') / span:+.2f}/day), cal {24 * g('cal:base') / span:+.2f}/day")
