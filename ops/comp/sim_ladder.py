# READ-ONLY offline. Replays the ENGINE's --exit-ladder (src/bin/snipe_engine.rs exit_ladder) slot by slot on the
# rule-#2 tapes, with our buy inserted at several landing positions, all costs included:
#   pump fee per side (from events), buy landing fee (priority + tips), per-sell-leg fee, own price impact on every leg,
#   entry cap (--slip-bps: min_tokens_out vs the decision-time quote at the post-bundle curve -> revert, pay fail cost).
# usage: SNIPER_ROOT=/home/moiz/sniper-data python3 sim_ladder.py [tapes] [out.json]
import sys, os, json, math, itertools, statistics as st
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import order_launch, bundle_set, post_bundle_state, pre_state, load

ROOT = os.environ.get("SNIPER_ROOT", "/root")
TAPES = sys.argv[1] if len(sys.argv) > 1 else ROOT + "/comp/tapes_r2.jsonl"
OUT = sys.argv[2] if len(sys.argv) > 2 else ROOT + "/comp/sim_ladder.json"
SLOT_S = 0.217          # MEASURED slot time (PoH clock, 10-19)
SELL_LEG_FEE = 0.0005   # sell CU price ~5M x 95k CU + base fee
FAIL_COST = 0.0105      # a reverted (cap) buy that lands on a non-bundle path pays the priority fee
SCEN = ("d8", "d25", "d100", "d200", "s1")
SIZES = (1.0, 1.5, 2.0)
BUYFEES = (0.006, 0.025)
SLIPS = (0.10, 0.15, 0.20, 9.0)
GRID = list(itertools.product((0.0, 0.3, 0.5),          # derisk
                              (0.0, 0.15, 0.25),        # ladder frac
                              (1.2, 1.3, 1.5, 9.0),     # ride mult (9 = never ride)
                              (0.80, 0.85, 0.90),       # trail frac
                              (0.0, 0.80, 0.90),        # cut r
                              (0.5, 1, 2, 4, 8, 15, 20)))  # exit cap seconds


def ladder(path, q, entry, fee_rate, p):
    """path: list of (V,T) at end of each slot from the buy-landing slot. Returns (proceeds SOL, legs, hold slots)."""
    derisk, lfrac, ride, trail, cut, cap_s = p
    cap = max(1, math.ceil(cap_s / SLOT_S))
    n = len(path)
    rem = q; peak = 1.0; riding = False; first = True; last_sell = 0
    exV = exT = 0.0; proc = 0.0; legs = 0; s = 0; hold = 0

    def sell(qty, at):
        nonlocal exV, exT, proc, legs, rem, hold
        at = min(at, n - 1)
        V, T = path[at][0] - exV, path[at][1] + exT
        so = V * qty / (T + qty)
        proc += so * (1 - fee_rate) / 1e9
        exV += so; exT += qty; rem -= qty; legs += 1; hold = at
    while rem > 1 and s < n - 1:
        V, T = path[s][0] - exV, path[s][1] + exT
        r = (V / T) / entry
        peak = max(peak, r)
        if not riding and r >= ride: riding = True
        qty = 0; fin = False
        if first:
            first = False; qty = rem * derisk
        elif r <= cut: qty = rem; fin = True
        elif riding and r <= peak * trail: qty = rem; fin = True
        elif s >= cap: qty = rem; fin = True
        elif not riding and 1.0 <= r < ride and s - last_sell >= 4: qty = rem * lfrac
        if qty > 1:
            sell(qty, s + 1)          # lands next slot
            last_sell = s; s += 2     # engine waits for the leg to land before the next read
            if fin: break
        else:
            s += 1
    if rem > 1: sell(rem, min(s, n - 1))
    return proc, legs, hold


def prep(r):
    ev, fb = order_launch(r)
    if len(ev) < 3: return None
    S = r["slot"]; bw = bundle_set(r)
    fr = [(e["fbps"] + e["cbps"]) / 1e4 for e in ev if e["fbps"] is not None]
    fee_rate = sorted(fr)[len(fr) // 2] if fr else 0.0125
    last = S + 300
    gv, gt = post_bundle_state(r)

    def idx_before_d(D):
        k = 0
        while k < len(ev) and ev[k]["slot"] == S and ev[k]["d"] is not None and ev[k]["d"] < D: k += 1
        return k
    k_s1 = 0
    while k_s1 < len(ev) and ev[k_s1]["slot"] == S: k_s1 += 1
    sc = {"d8": (idx_before_d(8), S), "d25": (idx_before_d(25), S), "d100": (idx_before_d(100), S), "d200": (idx_before_d(200), S), "s1": (k_s1, S + 1)}
    return dict(mint=r["mint"], bt=r["bt"], S=S, ev=ev, fee_rate=fee_rate, last=last, gv=gv, gt=gt, sc=sc)


def entry_path(L, k0, eslot, xs):
    ev = L["ev"]
    V, T = pre_state(ev[k0]) if k0 < len(ev) else (ev[-1]["vsol"], ev[-1]["vtok"])
    x = xs * 1e9; q = T * x / (V + x); V += x; T -= q
    carried = {}
    for e in ev[k0:]:
        if e["buy"]:
            dt = T * e["sol"] / (V + e["sol"]); V += e["sol"]; T -= dt
        else:
            so = V * e["tok"] / (T + e["tok"]); V -= so; T += e["tok"]
        carried[e["slot"]] = (V, T)
    path = []; cur = None
    V0s, T0s = pre_state(ev[k0]) if k0 < len(ev) else (ev[-1]["vsol"], ev[-1]["vtok"])
    cur = (V0s + x, T0s - q)
    for s in range(eslot, L["last"] + 1):
        if s in carried: cur = carried[s]
        path.append(cur)
    return q, path


def work(r):
    L = prep(r)
    if L is None: return None
    out = dict(mint=L["mint"], bt=L["bt"], res={})
    for sc, (k0, eslot) in L["sc"].items():
        for x in SIZES:
            xs = x / (1 + L["fee_rate"])
            q, path = entry_path(L, k0, eslot, xs)
            q_dec = L["gt"] * xs * 1e9 / (L["gv"] + xs * 1e9)       # decision-time quote at the post-bundle curve
            short = 1 - q / q_dec                                   # how much worse than quoted (fraction of tokens)
            entry = x * 1e9 / q                                     # lamports per token incl. pump fee (engine: spend/amount)
            pn = []; hd = []
            for p in GRID:
                proc, legs, hold = ladder(path, q, entry, L["fee_rate"], p)
                pn.append(proc - x - legs * SELL_LEG_FEE); hd.append(hold)
            out["res"][(sc, x)] = (short, pn, hd)
    return out


def main():
    import numpy as np
    rows = list(load(TAPES))
    with Pool(max(1, os.cpu_count() - 2)) as pool:
        R = [o for o in pool.map(work, rows, chunksize=4) if o]
    R.sort(key=lambda o: o["bt"])
    n = len(R)
    fold = np.array([min(2, i * 3 // n) for i in range(n)])
    print(f"launches {n}; folds by time {[int((fold == f).sum()) for f in range(3)]}")
    G = len(GRID); iref = GRID.index((0.0, 0.0, 9.0, 0.8, 0.0, 0.5))
    summary = {}
    for sc in SCEN:
        for x in SIZES:
            SH = np.array([o["res"][(sc, x)][0] for o in R])
            PN = np.array([o["res"][(sc, x)][1] for o in R])        # n x G
            HD = np.array([o["res"][(sc, x)][2] for o in R]) * SLOT_S
            for bf in BUYFEES:
                for slip in SLIPS:
                    ok = SH <= slip
                    V = np.where(ok[:, None], PN - bf, -FAIL_COST)
                    mean = V.mean(0); med = np.median(V, 0)
                    srt = np.sort(V, 0); ex3 = srt[:-3].mean(0)
                    win = (V > 0).mean(0)
                    fm = np.stack([V[fold == f].mean(0) for f in range(3)])
                    worst = fm.min(0)
                    hold = np.array([np.median(HD[ok, g]) if ok.any() else 0 for g in range(G)])
                    order = list(np.argsort(-worst)[:8]) + [iref]
                    summary[f"{sc}|{x}|{bf}|{slip}"] = dict(traded=float(ok.mean()), short_q=[float(a) for a in np.quantile(SH, [0, .25, .5, .75, 1])],
                        rows=[dict(p=GRID[g], mean=float(mean[g]), med=float(med[g]), ex3=float(ex3[g]), win=float(win[g]), worst_fold=float(worst[g]),
                                   folds=[float(a) for a in fm[:, g]], hold_med_s=float(hold[g])) for g in order])
    json.dump(summary, open(OUT, "w"))
    for sc in SCEN:
        for x in (1.5,):
            for bf in BUYFEES:
                for slip in (0.15, 9.0):
                    s = summary[f"{sc}|{x}|{bf}|{slip}"]
                    print(f"\n[{sc} size {x} buyfee {bf} cap {'off' if slip > 5 else slip}] traded {s['traded']:.2f} short q {['%.2f' % a for a in s['short_q']]}")
                    print("   derisk lad ride trail cut  cap |  mean    med   ex3  win  worstF  folds                   hold_s")
                    for d in s["rows"][:4] + s["rows"][-1:]:
                        p = d["p"]
                        print(f"   {p[0]:4} {p[1]:4} {p[2]:4} {p[3]:4} {p[4]:4} {p[5]:4} | {d['mean']:+.4f} {d['med']:+.4f} {d['ex3']:+.4f} {d['win']:.2f} {d['worst_fold']:+.4f}"
                              f" [{', '.join('%+.3f' % f for f in d['folds'])}] {d['hold_med_s']:.1f}")


if __name__ == "__main__":
    main()
