#!/usr/bin/env python3
import sys, pickle, collections
import numpy as np
sys.path.insert(0, "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/rearm2/code")
import rep
from rep import Day, boot, fmt, NAME, TRAIN, TEST
DAYS = {D: Day(D) for D in range(2, 8)}
VARS = [k for k in DAYS[2].out if k != "base"]
S65 = 650_000_000
P = print


def delta_fn(v, size=S65, tp=0.2, cut=0.0, ff=5000, drop_top=0):
    def f(dy, d):
        a = dy.per_hour(v, d, size, tp, cut, ff, drop_top=drop_top); b = dy.per_hour("base", d, size, tp, cut, ff)
        return {h: a.get(h, 0) - b.get(h, 0) for h in set(a) | set(b)}
    return f


def lvl_fn(v, size=S65, tp=0.2, cut=0.0, ff=5000, only=None):
    return lambda dy, d: dy.per_hour(v, d, size, tp, cut, ff, only=only)


# ---------------- TRAIN choice
P("## TRAIN: re-arm minus base, SOL/day, 0.65 SOL TP 20% [90% CI]")
P("| Variant | " + " | ".join(NAME[D] for D in TRAIN) + " | TRAIN pooled | TRAIN pooled, 20% fewer followers |")
P("|---|---|---|---|---|---|")
score = {}
for v in VARS:
    cells = [fmt(*boot([DAYS[D]], delta_fn(v))) for D in TRAIN]
    pooled = boot([DAYS[D] for D in TRAIN], delta_fn(v)); c20 = boot([DAYS[D] for D in TRAIN], delta_fn(v, cut=0.2))
    score[v] = c20[0]
    P(f"| {v} | " + " | ".join(cells) + f" | {fmt(*pooled)} | {fmt(*c20)} |")
best = max(score, key=score.get)
P(f"\nTRAIN-best (by pooled Δ at 20% fewer followers): {best}\n")
pickle.dump(best, open(f"{rep.W}/train_best.pkl", "wb"))


def mean_d(dy, f):
    return float(np.mean([f(dy, d) for d in dy.draws]))


def rate_stats(dy, v):
    a = []; p99 = []; capb = []; refs = []
    for d in dy.draws:
        s = dy.out[v][d]["sent"]; r = dy.out[v][d]["refused"]
        tot = sum(s.values()); rf = sum(r.values())
        secs = set(s) | set(r)
        a.append(tot / (dy.hours * 3600)); p99.append(np.percentile(list(s.values()), 99) if s else 0)
        capb.append(sum(1 for x in secs if r.get(x, 0) > 0) / max(len(secs), 1)); refs.append(rf / max(tot + rf, 1))
    return np.mean(a), np.mean(p99), np.mean(capb), np.mean(refs)


def counts(dy, v, d):
    rows = dy.out[v][d]["rows"]
    ok = lambda r: dy.hour_of(r["bt"]) in dy.hrs
    return dict(arm_re=sum(1 for r in rows if r["kind"] == "re" and r["armed"] and ok(r)), fills=sum(1 for r in rows if r.get("filled") and ok(r)),
                fills_re=sum(1 for r in rows if r.get("filled") and r["kind"] == "re" and ok(r)), arm=sum(1 for r in rows if r["armed"] and ok(r)))


def day_table(v, days, title):
    P(f"\n## {title}: {v} (0.65 SOL, TP 20%; SOL/day scaled to 24 h; Δ = re-arm run minus base run, paired draws) ")
    P("| Day | hours | base SOL/day | extra re windows/day | extra fills/day | re-arm fills alone SOL/day | Δ total [90% CI] | Δ 20% fewer followers [CI] | Δ 40% fewer [CI] | Δ without top-5 re fills | Δ fail cost 0.3 mSOL/try | sends/s avg (base→re) | p99 sends/s | cap-bound s % | refused % |")
    P("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for D in days:
        dy = DAYS[D]; k = 24 / dy.hours
        base = boot([dy], lvl_fn("base"))[0]
        cr = [counts(dy, v, d) for d in dy.draws]; cb = [counts(dy, "base", d) for d in dy.draws]
        xw = np.mean([c["arm_re"] for c in cr]) * k; xf = (np.mean([c["fills"] for c in cr]) - np.mean([c["fills"] for c in cb])) * k
        alone = boot([dy], lvl_fn(v, only="re"))[0]
        d0 = boot([dy], delta_fn(v)); d2 = boot([dy], delta_fn(v, cut=0.2)); d4 = boot([dy], delta_fn(v, cut=0.4))
        dt = boot([dy], delta_fn(v, drop_top=5))[0]; dff = boot([dy], delta_fn(v, ff=300_000))[0]
        rb = rate_stats(dy, "base"); rr = rate_stats(dy, v)
        P(f"| {NAME[D]} | {dy.hours:.1f} | {base:+.2f} | {xw:.0f} | {xf:+.0f} | {alone:+.2f} | {fmt(*d0)} | {fmt(*d2)} | {fmt(*d4)} | {dt:+.2f} | {dff:+.2f} | {rb[0]:.2f}→{rr[0]:.2f} | {rb[1]:.0f}→{rr[1]:.0f} | {100*rb[2]:.1f}→{100*rr[2]:.1f} | {100*rb[3]:.1f}→{100*rr[3]:.1f} |")
    for lab, ds in (("TRAIN pooled", TRAIN), ("**TEST pooled**", TEST)):
        dd = [DAYS[D] for D in ds]
        P(f"| {lab} | {sum(x.hours for x in dd):.1f} | {boot(dd, lvl_fn('base'))[0]:+.2f} | | | {boot(dd, lvl_fn(v, only='re'))[0]:+.2f} | **{fmt(*boot(dd, delta_fn(v)))}** | **{fmt(*boot(dd, delta_fn(v, cut=0.2)))}** | {fmt(*boot(dd, delta_fn(v, cut=0.4)))} | {boot(dd, delta_fn(v, drop_top=5))[0]:+.2f} | {boot(dd, delta_fn(v, ff=300_000))[0]:+.2f} | | | | |")


for v in VARS: day_table(v, list(TRAIN) + list(TEST), "Per day")


def fills_of(days, v, kind):
    out = []
    for D in days:
        dy = DAYS[D]
        for d in dy.draws:
            for r in dy.out[v][d]["rows"]:
                if r.get("filled") and r["kind"] == kind and dy.hour_of(r["bt"]) in dy.hrs: out.append((D, d, r))
    return out


def ss_table(v, days, label):
    P(f"\n## Second seller, {label}: {v} re-arm fills vs base T2 fills (per draw averages; mSOL per fill = gross − 2.9 trip cost)")
    P("| Fill kind | fills/day | another big sell lands inside our hold % | big holder sells within fill+2 slots % | whale dump (≥ 6% supply) inside hold % | per fill, big sell in hold: yes / no (0.65) | per fill, holder sold ≤ 2 slots: yes / no (0.65) | same at 1.0 SOL (yes / no, ≤ 2 slots) |")
    P("|---|---|---|---|---|---|---|---|")
    hrs = sum(DAYS[D].hours for D in days); nd = len(DAYS[days[0]].draws)
    for kind, vv in (("re", v), ("t2", "base")):
        F = fills_of(days, vv, kind)
        if not F: continue
        n = len(F) / nd / hrs * 24
        ih = np.mean([r["flags"]["in_hold"] for _, _, r in F]); tw = np.mean([r["flags"]["two"] for _, _, r in F]); wh = np.mean([r["flags"]["whale_in_hold"] for _, _, r in F])
        def pf(key, val, size=S65):
            x = [(r["grid"][(size, 0.2, 0.0)] - rep.TRIP) / 1e6 for _, _, r in F if r["flags"][key] == val]
            return f"{np.mean(x):+.1f} (n/draw {len(x)/nd:.0f})" if x else "–"
        P(f"| {kind} | {n:.0f} | {100*ih:.0f} | {100*tw:.0f} | {100*wh:.0f} | {pf('in_hold', True)} / {pf('in_hold', False)} | {pf('two', True)} / {pf('two', False)} | {pf('two', True, 1_000_000_000)} / {pf('two', False, 1_000_000_000)} |")


SIZES = (400_000_000, 450_000_000, 650_000_000, 850_000_000, 1_000_000_000)


def size_table(v, days, label, tp=0.2):
    dd = [DAYS[D] for D in days]; hrs = sum(x.hours for x in dd); nd = len(dd[0].draws)
    P(f"\n## Size, {label}, {v}, TP {int(tp*100)}% (SOL/day; corrected = raw − live-fill size gap per fill: " + ", ".join(f"{s/1e9:.2f}→{rep.gap_msol(s/1e9):.1f}" for s in SIZES) + " mSOL)")
    P("| Size | fills/day | fill rate (fills / armed windows) | raw SOL/day [90% CI] | corrected SOL/day | per fill mSOL raw / corr | 20% fewer followers (raw) | without top-5 fills | second-seller fills (holder sold ≤ 2 slots) per fill mSOL | re-arm Δ raw / corrected / 20% fewer |")
    P("|---|---|---|---|---|---|---|---|---|---|")
    allf = [(D, d, r) for D in days for d in DAYS[D].draws for r in DAYS[D].out[v][d]["rows"] if r.get("filled") and DAYS[D].hour_of(r["bt"]) in DAYS[D].hrs]
    arm = sum(1 for D in days for d in DAYS[D].draws for r in DAYS[D].out[v][d]["rows"] if r["armed"] and DAYS[D].hour_of(r["bt"]) in DAYS[D].hrs)
    fpd = len(allf) / nd / hrs * 24
    for s in SIZES:
        raw = boot(dd, lvl_fn(v, s, tp)); c20 = boot(dd, lvl_fn(v, s, tp, 0.2))[0]
        corr = raw[0] - fpd * rep.gap_msol(s / 1e9) / 1e3
        # without the 5 best fills per day per draw
        top = 0.0
        for D in days:
            for d in DAYS[D].draws:
                g = sorted((r["grid"][(s, tp, 0.0)] for r in DAYS[D].out[v][d]["rows"] if r.get("filled") and DAYS[D].hour_of(r["bt"]) in DAYS[D].hrs), reverse=True)[:5]
                top += sum(x - rep.TRIP for x in g) / 1e9
        wo = raw[0] - top / nd / hrs * 24
        ssx = [(r["grid"][(s, tp, 0.0)] - rep.TRIP) / 1e6 for _, _, r in allf if r["flags"]["two"]]
        pf = raw[0] / fpd * 1e3
        rd = ""
        if v != "base":
            dr = boot(dd, delta_fn(v, s, tp)); d2 = boot(dd, delta_fn(v, s, tp, 0.2))
            xf = (len(allf) - sum(1 for D in days for d in DAYS[D].draws for r in DAYS[D].out["base"][d]["rows"] if r.get("filled") and DAYS[D].hour_of(r["bt"]) in DAYS[D].hrs)) / nd / hrs * 24
            rd = f"{fmt(*dr)} / {dr[0] - xf * rep.gap_msol(s / 1e9) / 1e3:+.2f} / {fmt(*d2)}"
        P(f"| {s/1e9:.2f} | {fpd:.0f} | {len(allf)/max(arm,1):.3f} | {fmt(*raw)} | {corr:+.2f} | {pf:+.1f} / {pf - rep.gap_msol(s/1e9):+.1f} | {c20:+.2f} | {wo:+.2f} | {np.mean(ssx):+.1f} (n/day {len(ssx)/nd/hrs*24:.0f}) | {rd} |")


best = pickle.load(open(f"{rep.W}/train_best.pkl", "rb"))
for v in sorted({"R0", best}):
    ss_table(v, list(TRAIN), "TRAIN"); ss_table(v, list(TEST), "TEST")
for v in ["base"] + sorted({"R0", best}):
    size_table(v, list(TEST), "TEST")
size_table("R0", list(TEST), "TEST", tp=0.1)
for D in TEST: size_table("base", [D], f"TEST day {NAME[D]}"); size_table("R0", [D], f"TEST day {NAME[D]}")
