#!/usr/bin/env python3
"""ourspeed step 3: tables from sim_rows.pkl. Costs: C = 2.9 mSOL per filled round trip, R = 0.3 mSOL per reverted try.
Calibrated = phi-0 net - gap(S) per attempt, gap(S) = max(0, -4.4 + 28.1 S) mSOL (PAPER_VS_LIVE.md straight-line fit:
~15 mSOL/SOL at 0.35, ~24 at 1.0). Calibration and phi overlap -> never stack them."""
import pickle, sys, numpy as np
O = "/home/moiz/sniper-data/e2x1_dissect/ourspeed"
R = pickle.load(open(f"{O}/sim_rows.pkl", "rb"))
C, RV = 0.0029, 0.0003
gap = lambda S: max(0.0, -4.4 + 28.1 * S) / 1000
BANDS = ("FRESH", "MINUTE", "OLD", "ALL")
out = []
def P(s=""): print(s); out.append(s)

def agg(rows, tag, calib=False):
    n = 0; pf = 0.0; net = [];
    for r in rows:
        v = r.get(tag)
        if v is None: continue
        f, p = v; x = p - C * f - RV * (1 - f)
        if calib: x -= gap(r["S"])
        n += 1; pf += f; net.append(x)
    net = np.array(net)
    if not len(net): return None
    tot = net.sum(); srt = np.sort(net)[::-1]; k = max(1, int(round(0.05 * len(net))))
    top = srt[:k].sum() / tot if tot > 0 else np.nan
    return dict(n=n, fills=pf, rate=pf / n, tot=tot, per_fill=tot / pf if pf else np.nan, top5=top)

def sel(day, band): return [r for r in R if r["day"] == day and (band == "ALL" or r["bot"] == band)]

P("## Validation: his own lots replayed on the counterfactual tape (entry at his buy, exit at his sell), MEASURED")
for day in ("D0", "D1"):
    v = np.array([r["V"] for r in sel(day, "ALL") if "V" in r]); vr = np.array([r["V_real"] for r in sel(day, "ALL") if "V" in r])
    P(f"{day}: lots {len(v)}; sim curve P&L {v.sum():+.3f} vs his real proceeds-cost {vr.sum():+.3f}; median |err| {np.median(np.abs(v - vr)) * 1e3:.2f} mSOL, p90 {np.percentile(np.abs(v - vr), 90) * 1e3:.1f}")

LS = [35, 50, 66, 90]
def table(mode, ex, title):
    P(f"\n### {title}")
    P("| day | band | his actual (lots, SOL) | L ms | fills / rate | raw | raw phi20 | raw phi40 | **calibrated** | cal mSOL/fill | top-5% share (cal) |")
    P("|---|---|---|---|---|---|---|---|---|---|---|")
    for day in ("D1", "D0"):
        for b in BANDS:
            rows = sel(day, b); his = sum(r["his_pnl"] for r in rows)
            for Lm in LS:
                a0 = agg(rows, f"{mode}|{ex}|{Lm}|0.0|fast"); a2 = agg(rows, f"{mode}|{ex}|{Lm}|0.2|fast"); a4 = agg(rows, f"{mode}|{ex}|{Lm}|0.4|fast")
                ac = agg(rows, f"{mode}|{ex}|{Lm}|0.0|fast", calib=True)
                if a0 is None: continue
                g = lambda a: f"{a['tot']:+.2f}" if a else "–"
                P(f"| {day} | {b} | {len(rows)} lots, {his:+.1f} | {Lm} | {a0['fills']:.0f} / {a0['rate']:.0%} | {a0['tot']:+.2f} | {g(a2)} | {g(a4)} | **{ac['tot']:+.2f}** | {ac['per_fill'] * 1e3:+.1f} | {ac['top5']:.0%} |")

for mode, ex, t in (("A", "his", "A. ORACLE-PICKS, exit = his own hold from our entry (SOL/day; D1 and D0 are each exactly 24 h)"),
                    ("A", "band", "A. ORACLE-PICKS, exit = fixed 18 / 34 / 83 s per band"),
                    ("A", "200ms", "A. ORACLE-PICKS, exit = our 200 ms (+ sell landing delay)"),
                    ("A2", "his", "A2. ORACLE-PICKS on the REAL tape (he + sibling still trade, we land behind him), exit = his hold"),
                    ("A2", "band", "A2. ORACLE-PICKS on the REAL tape, exit = fixed 18 / 34 / 83 s"),
                    ("B", "copy", "B. COPY-TRADE, buy L after his buy lands, sell L after his first sell lands"),
                    ("B", "band", "B. COPY-TRADE, exit fixed 18 / 34 / 83 s"),
                    ("B", "200ms", "B. COPY-TRADE, exit 200 ms")):
    table(mode, ex, t)

# phi over the whole hold (harsh variant), 66 ms
P("\n### phi applied to ALL other buy SOL over the whole hold (harsh variant), 66 ms, raw SOL/day")
P("| day | band | A his phi20 | A his phi40 | B copy phi20 | B copy phi40 |")
P("|---|---|---|---|---|---|")
for day in ("D1", "D0"):
    for b in BANDS:
        rows = sel(day, b)
        g = lambda t: agg(rows, t)["tot"]
        P(f"| {day} | {b} | {g('A|his|66|0.2|full'):+.2f} | {g('A|his|66|0.4|full'):+.2f} | {g('B|copy|66|0.2|full'):+.2f} | {g('B|copy|66|0.4|full'):+.2f} |")

# break-even latency (calibrated, phi 0)
P("\n### Break-even landing (calibrated SOL/day = 0), linear interpolation over L = 10..200 ms")
P("| day | band | A his-exit | A band-exit | A 200ms | A2 his-exit | B copy | B band | B 200ms |")
P("|---|---|---|---|---|---|---|---|---|")
GL = [10, 20, 35, 50, 66, 90, 120, 150, 200]
BE = {}
for day in ("D1", "D0"):
    for b in BANDS:
        rows = sel(day, b); cells = []
        for mode, ex in (("A", "his"), ("A", "band"), ("A", "200ms"), ("A2", "his"), ("B", "copy"), ("B", "band"), ("B", "200ms")):
            y = [agg(rows, f"{mode}|{ex}|{Lm}|0.0|fast", calib=True)["tot"] for Lm in GL]
            if y[0] <= 0: c = "<10 (neg at 10)"
            elif all(v > 0 for v in y): c = ">200"
            else:
                k = next(q for q in range(len(y)) if y[q] <= 0); x0, x1, y0, y1 = GL[k - 1], GL[k], y[k - 1], y[k]
                c = f"{x0 + (x1 - x0) * y0 / (y0 - y1):.0f}"
            BE[(day, b, mode, ex)] = (c, y)
            cells.append(c)
        P(f"| {day} | {b} | " + " | ".join(cells) + " |")
P("\nCalibrated SOL/day by L (curve, phi 0):")
for (day, b, mode, ex), (c, y) in BE.items():
    if ex in ("his", "copy"):
        P(f"- {day} {b} {mode}-{ex}: " + ", ".join(f"{Lm}:{v:+.1f}" for Lm, v in zip(GL, y)))
P("\n### SUMMARY: SOL/day by band x L, raw (after 2.9 mSOL trip cost) / calibrated, D1 | D0")
P("| mode | band | 35 ms | 50 ms | 66 ms | 90 ms |")
P("|---|---|---|---|---|---|")
for mode, ex in (("A", "his"), ("A2", "his"), ("B", "copy")):
    for b in BANDS:
        cells = []
        for Lm in LS:
            c = []
            for day in ("D1", "D0"):
                r0 = agg(sel(day, b), f"{mode}|{ex}|{Lm}|0.0|fast"); rc = agg(sel(day, b), f"{mode}|{ex}|{Lm}|0.0|fast", calib=True)
                c.append(f"{r0['tot']:+.1f}/{rc['tot']:+.1f}")
            cells.append(" \\| ".join(c))
        P(f"| {mode}-{ex} | {b} | " + " | ".join(cells) + " |")
open("/home/moiz/sniper-data/e2x1_dissect/ourspeed/o3_tables.md", "w").write("\n".join(out) + "\n")
