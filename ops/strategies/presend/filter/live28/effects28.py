#!/usr/bin/env python3
"""LIVE28 step 4: what QUIET gave up (+) or saved (-) in run 28, from the replay streams (INFERRED; live numbers MEASURED).
  given up by the skip rule = C - A0, by the stop rule = D - A0, by QUIET = B - A0 (interaction = the rest); per window
  deltas sum to these exactly (a window armed in one stream only counts its whole net). Fills booked as live books them
  (-5,020 lamports token-account close fee).
  Ranges: (a) model draws with the windows fixed; (b) bootstrap over windows (stratified: the skipped, the stopped, the
  132 other live windows resampled within their group, each picked window with a random draw), 5th-95th percentile.
  Calibrated rows (INFERRED): every winning fill's P&L x f_win (live wins / replay wins on the armed live windows), losses and
  fees as modeled (the replay matched live losses: see calib28.py).
usage: effects28.py POOL [TAG] [--fwin X]"""
import sys, os, pickle, collections, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib28 as L

RENT = 5020
NB = 10000


def adj_net(r, fwin=1.0, floss=1.0):
    """window net as live books it; fwin scales a winning fill's P&L, floss a losing fill's"""
    if not r["armed"]: return 0.0
    if not r["filled"]: return -float(r["fees"])
    p = r["pnl"] - RENT
    p *= fwin if p > 0 else floss
    return p - float(r["fees"])


def floss_of(Z, drop=()):
    M = Z["meta"]; lv = {x["key"]: x for x in M["live"]}
    ll = sum((x["live"]["pnl"] + x["live"]["rb"]) for k, x in lv.items() if k not in drop and x["live"]["filled"] and x["live"]["pnl"] + x["live"]["rb"] <= 0)
    rl = np.mean([sum(r["pnl"] - RENT for k, r in by.items() if k not in drop and r["filled"] and r["pnl"] - RENT <= 0) for _, by in Z["out"]["cal"]])
    return ll / rl


def fwin_of(Z, drop=()):
    M = Z["meta"]; lv = {x["key"]: x for x in M["live"]}
    lw = sum((x["live"]["pnl"] + x["live"]["rb"]) for k, x in lv.items() if k not in drop and x["live"]["filled"] and x["live"]["pnl"] + x["live"]["rb"] > 0)
    rw = np.mean([sum(r["pnl"] - RENT for k, r in by.items() if k not in drop and r["filled"] and r["pnl"] - RENT > 0) for _, by in Z["out"]["cal"]])
    return lw / rw


def deltas(Z, s1, s0, fwin=1.0, hybrid=True, floss=1.0):
    """per draw: {key: net_s1 - net_s0} over the union of keys (lamports). hybrid: a LIVE window that the counterfactual blocks
    (armed in s0, not armed in s1) loses its MEASURED live net, not the model's (the replay knows what that window really did)"""
    a = Z["out"][s1]; b = Z["out"][s0]
    lv = {x["key"]: x["live"]["net"] for x in Z["meta"]["live"]}
    out = []
    for (sa, A), (sb, B) in zip(a, b):
        assert sa == sb
        keys = set(A) | set(B); d = {}
        for k in keys:
            x1 = adj_net(A[k], fwin, floss) if k in A else 0.0
            if hybrid and k in lv and k in B and B[k]["armed"] and not (k in A and A[k]["armed"]):
                x0 = float(lv[k])
            else:
                x0 = adj_net(B[k], fwin, floss) if k in B else 0.0
            d[k] = x1 - x0
        out.append(d)
    return out


def boot(D, groups, rng, nb=NB):
    """stratified bootstrap over windows: groups = list of key lists; each picked key gets a random draw"""
    nd = len(D)
    tot = np.zeros(nb)
    for g in groups:
        if not g: continue
        M = np.array([[D[d].get(k, 0.0) for d in range(nd)] for k in g])          # keys x draws
        ki = rng.integers(len(g), size=(nb, len(g))); di = rng.integers(nd, size=(nb, len(g)))
        tot += M[ki, di].sum(axis=1)
    return tot / 1e9


def show(name, D, keys, groups, rng):
    v = np.array([sum(d.get(k, 0.0) for k in keys) for d in D]) / 1e9
    b = boot(D, groups, rng)
    return dict(name=name, mean=float(v.mean()), m5=float(np.percentile(v, 5)), m95=float(np.percentile(v, 95)), b5=float(np.percentile(b, 5)),
                b95=float(np.percentile(b, 95)), p_pos=float((b > 0).mean()))


def fmt(r):
    return (f"| {r['name']} | **{r['mean']:+.4f}** | {r['m5']:+.4f} to {r['m95']:+.4f} | {r['b5']:+.4f} to {r['b95']:+.4f} | {r['p_pos'] * 100:.0f}% |")


if __name__ == "__main__":
    pool = sys.argv[1]; tag = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "main"
    Z = pickle.load(open(f"{L.DATA}/replay28_{pool}_{tag}.pkl", "rb"))
    M = Z["meta"]; lv = {x["key"]: x for x in M["live"]}
    top = max(lv, key=lambda k: lv[k]["live"]["net"])
    fw_all = fwin_of(Z); fw_notop = fwin_of(Z, drop=(top,)); fl_all = floss_of(Z)
    SK = [x["key"] for x in M["skip"]]
    ST = [k for k, x in lv.items() if x["d_stop"] is not None]
    OT = [k for k, x in lv.items() if x["d_stop"] is None]
    sk_ph = {x["key"]: x["phase"] for x in M["skip"]}
    live_net = sum(x["live"]["net"] for x in lv.values()) / 1e9
    res = {}
    print(f"pool {pool} tag {tag}: {M['draws']} draws; cut {M['cut']} lag {M['lag']}; f_win all {fw_all:.2f}, without the top live winner "
          f"(w{top[1]}) {fw_notop:.2f}; live net {live_net:+.4f}; skipped {len(SK)}, stopped {len(ST)}, other live {len(OT)}")
    print(f"f_loss (live losers / replay losers, all windows) {fl_all:.2f}")
    for lab, fw, fl in (("model", 1.0, 1.0), ("cal_notop", fw_notop, 1.0), ("cal_all", fw_all, 1.0), ("cal_both", fw_all, fl_all)):
        rng = np.random.default_rng(42)
        Dsk = deltas(Z, "C", "A0", fw, floss=fl); Dst = deltas(Z, "D", "A0", fw, floss=fl); Dto = deltas(Z, "B", "A0", fw, floss=fl)
        rows = [
            show(f"Skip rule: the {len(SK)} skipped triggers' own P&L (armed, stop rule on)", Dsk, SK, [SK], rng),
            show(f"Skip rule: knock-on on the {len(ST) + len(OT)} live windows", Dsk, ST + OT, [ST, OT], rng),
            show("**Skip rule, total (C - A0)**", Dsk, SK + ST + OT, [SK, ST, OT], rng),
            show(f"Stop rule: the {len(ST)} stopped windows after their stop", Dst, ST, [ST], rng),
            show(f"Stop rule: knock-on on the other {len(OT)} windows", Dst, OT, [OT], rng),
            show("**Stop rule, total (D - A0)**", Dst, ST + OT, [ST, OT], rng),
            show("**QUIET total, no QUIET vs live (B - A0)**", Dto, SK + ST + OT, [SK, ST, OT], rng),
        ]
        for _, name in L.PERIODS:
            sk = [k for k in SK if sk_ph[k] == name]; st = [k for k in ST if lv[k]["phase"] == name]; ot = [k for k in OT if lv[k]["phase"] == name]
            rows.append(show(f"  QUIET total, {name} (skipped {len(sk)}, stopped {len(st)})", Dto, sk + st + ot, [sk, st, ot], rng))
            rows.append(show(f"    skip rule, {name}", Dsk, sk + st + ot, [sk, st, ot], rng))
            rows.append(show(f"    stop rule, {name}", Dst, st + ot, [st, ot], rng))
        inter = np.array([sum(d.values()) for d in Dto]) - np.array([sum(d.values()) for d in Dsk]) - np.array([sum(d.values()) for d in Dst])
        res[lab] = dict(fwin=fw, floss=fl, rows=rows, interaction=float(inter.mean() / 1e9))
        print(f"\n[{lab}] f_win {fw:.2f} f_loss {fl:.2f}  (given up = counterfactual - live; negative = QUIET saved)")
        print("| Item | Given up (mean) | Model draws 5-95% | Bootstrap over windows 5-95% | Bootstrap > 0 |")
        print("|---|---|---|---|---|")
        for r in rows: print(fmt(r))
        print(f"interaction (B - A0) - (C - A0) - (D - A0): {inter.mean() / 1e9:+.4f}")
    # counts per stream: fills, armed, blocked
    cnt = {}
    for s in ("A0", "B", "C", "D"):
        dr = Z["out"][s]
        cnt[s] = dict(armed=float(np.mean([sum(r["armed"] for r in by.values()) for _, by in dr])),
                      fills=float(np.mean([sum(r["filled"] for r in by.values()) for _, by in dr])),
                      skips=dict(collections.Counter(r["why"] for _, by in dr for r in by.values() if not r["armed"])))
    print("\nstreams:", json.dumps(cnt))
    json.dump(dict(pool=pool, tag=tag, res=res, cnt=cnt, fw_all=fw_all, fw_notop=fw_notop, fl_all=fl_all, top=list(top), live_net=live_net),
              open(f"{L.DATA}/effects28_{pool}_{tag}.json", "w"), indent=1)
