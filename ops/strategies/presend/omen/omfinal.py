import sys
sys.path.insert(0, "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/omen/code")
from omrep import *
DAYS = {D: Day(D, "final") for D in (2, 3, 4, 5, 6)}
TR = [DAYS[D] for D in (2, 3, 4)]; TE = [DAYS[D] for D in (5, 6)]
V = [k for k in DAYS[2].out if k != "base"]
OM = ("a_time", "add")
P = print
P("### Per variant, per day (0.65 SOL, TP 20%; SOL/day scaled to 24 h; INFERRED)")
P("| Variant | Day | arms/day | tries/day | fills/day | OMEN-added fills/day | added fills alone SOL/day | total SOL/day | Δ vs today [90% CI] | Δ −20% followers [CI] | Δ w/o top-5 OMEN fills | sends/s | cap-bound s % |")
P("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for v in ["base"] + V:
    for D, dy in DAYS.items():
        c = counts(dy, v); rs = rate_stats(dy, v)
        tot = boot([dy], lvl_fn(v), n=1)[0]
        if v == "base":
            P(f"| today (6%) | {NAME[D]}{' (test)' if D >= 5 else ''} | {c['arms']:.0f} | {c['tries']:.0f} | {c['fills']:.0f} | – | – | {tot:+.2f} | – | – | – | {rs[0]:.2f} | {100*rs[1]:.1f} |"); continue
        alone = boot([dy], lvl_fn(v, only=("add",)), n=1)[0] if c["arms_add"] > 0 else 0.0
        d0 = boot([dy], delta_fn(v), n=1000); d2 = boot([dy], delta_fn(v, key=K65c), n=1000); dt = boot([dy], delta_fn(v, drop_top=5, only=None), n=1)[0]
        P(f"| {v} | {NAME[D]}{' (test)' if D >= 5 else ''} | {c['arms']:.0f} | {c['tries']:.0f} | {c['fills']:.0f} | {c['fills_add']:.0f} | {alone:+.2f} | {tot:+.2f} | {fmt(*d0)} | {fmt(*d2)} | {dt:+.2f} | {rs[0]:.2f} | {100*rs[1]:.1f} |")
P("\n### Pooled (TRAIN 10-24..10-26, TEST 10-27..10-28)")
P("| Variant | TRAIN Δ raw | TRAIN Δ −20% | **TEST Δ raw** | **TEST Δ −20%** | TEST Δ w/o top-5 | TEST fills/day (today → variant) | TEST added fills/day, their own SOL/day |")
P("|---|---|---|---|---|---|---|---|")
for v in V:
    fb = np.mean([counts(d, "base")["fills"] for d in TE]); fv = np.mean([counts(d, v)["fills"] for d in TE]); fa = np.mean([counts(d, v)["fills_add"] for d in TE])
    al = boot(TE, lvl_fn(v, only=("add",)), n=1)[0]
    P(f"| {v} | {fmt(*boot(TR, delta_fn(v)))} | {fmt(*boot(TR, delta_fn(v, key=K65c)))} | **{fmt(*boot(TE, delta_fn(v)))}** | **{fmt(*boot(TE, delta_fn(v, key=K65c)))}** | {boot(TE, delta_fn(v, drop_top=5), n=1)[0]:+.2f} | {fb:.0f} → {fv:.0f} | {fa:.0f}, {al:+.2f} |")
# per-fill economics of OMEN-added fills vs base fills (TEST)
P("\n### Per fill (TEST pooled, mSOL after 2.015 trip cost, all followers / −20%)")
for v in ["base"] + V:
    for tags in (("b",), ("a_time",), ("add",)):
        g = []; g2 = []
        for dy in TE:
            for d in dy.draws:
                for r in dy.out[v][d]["rows"]:
                    if r.get("filled") and r["tag"] in tags and dy.ok(r): g.append((r["grid"][K65] - TRIP) / 1e6); g2.append((r["grid"][K65c] - TRIP) / 1e6)
        if g: P(f"- {v} {tags[0]}: n/draw-day {len(g)/len(TE)/10:.0f}, mean {np.mean(g):+.1f} / {np.mean(g2):+.1f}, median {np.median(g):+.1f}, win {np.mean(np.array(g)>0)*100:.0f}%")
