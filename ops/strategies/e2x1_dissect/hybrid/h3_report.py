#!/usr/bin/env python3
"""hybrid step 3: tables for REPORT.txt (reads sim.pkl)."""
import pickle, collections, time, numpy as np
OUT = "/home/moiz/sniper-data/e2x1_dissect/hybrid"; RP = "/home/moiz/sniper/ops/strategies/e2x1_dissect/hybrid"
Z = pickle.load(open(f"{OUT}/sim.pkl", "rb")); VARS = Z["VARS"]
E = "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb"; G = "Grozoe2Lk9yu7kWPcCMuWEbrnuBYseBExkYAuHPRJUdJ"
W0, W1 = 1793118600, 1793205000
MAIN = ("either", "in", 120, True)    # chosen before looking at results
HRS = {}
for ln in open(f"{OUT}/run_hours.txt"):
    p, a, b = ln.split()
    r = p.split("/")[-1].replace(".jsonl", "")
    name = ("AMS r" + r.split("_r")[-1]) if "ams" in r else ("FRA r" + r.split("_r")[-1])
    HRS[name] = (int(b) - int(a)) / 3.6e12
pk = lambda t: time.strftime("%m-%d %H:%M", time.gmtime(t + 18000))
out = []
def P(s=""): print(s); out.append(s)
def boot(x, n=5000, seed=1):
    x = np.asarray(x)
    if len(x) < 2: return (np.nan, np.nan)
    rng = np.random.default_rng(seed); s = rng.choice(x, (n, len(x))).sum(1)
    return np.percentile(s, 5), np.percentile(s, 95)
L = [x for x in Z["live"] if "res" in x]; SH = [x for x in Z["shadow"] if "res" in x]
def runorder(r): return (r.split()[0], int(r.split("r")[-1]))
RUNS = sorted({x["run"] for x in L}, key=runorder)
def stats(rows, v, base_key):
    aff = [x for x in rows if v in x["hyb"]]
    if not aff: return None
    b = np.array([x[base_key] for x in aff]); h = np.array([x["hyb"][v] for x in aff]); d = h - b
    lo, hi = boot(d); top3 = np.sort(d)[::-1][:3].sum()
    return dict(n=len(aff), base=b.sum(), hyb=h.sum(), d=d.sum(), lo=lo, hi=hi, per=d.mean(), top3=top3, d_list=d, aff=aff,
                flags=collections.Counter(x["res"][v][1] for x in aff), why=collections.Counter(x["res"][v][3] for x in aff))
vn = lambda v: f"{v[0]:<6} {v[1]:<8} max{v[2]:>5}s {'SL-20' if v[3] else 'noSL '}"
for x in L: x["base"] = x["real"]
# ---------------------------------------------------------------- A. all live runs
hours = sum(HRS[r] for r in RUNS); nfill = len(L)
P(f"A. ALL LIVE PRE-SEND FILLS, FRA r23-r28 + AMS r16-r34 (10-25 08:48 -> 10-28 21:20 PKT): {nfill} fills priced on the tape, "
  f"{hours:.1f} engine-hours (fills/engine-day {nfill / hours * 24:.0f}). Real P&L all fills {sum(x['real'] for x in L):+.3f} SOL. MEASURED replay.")
P(f"Skipped fills: {collections.Counter(x.get('skip') for x in Z['live'] if 'res' not in x)}")
P("variant (wallet / entry / max hold / stop)     | n aff | share | real on aff | hybrid | diff   | 90% CI           | per fill | top-3 | runs + / with n | diff/engine-day | exits copy/max/sl | grad/tape_end")
for v in VARS:
    s = stats(L, v, "base")
    if not s: continue
    pr = [sum(d for x, d in zip(s["aff"], s["d_list"]) if x["run"] == r) for r in RUNS]
    nr = [sum(1 for x in s["aff"] if x["run"] == r) for r in RUNS]
    P(f"{vn(v)} {'*' if v == MAIN else ' '}| {s['n']:5d} | {s['n'] / nfill:5.1%} | {s['base']:+8.3f} | {s['hyb']:+7.3f} | {s['d']:+6.3f} | [{s['lo']:+6.3f}, {s['hi']:+6.3f}] | {s['per']:+.4f} | {s['top3']:+.3f} | "
      f"{sum(1 for p, n in zip(pr, nr) if n and p > 0):2d} / {sum(1 for n in nr if n):2d} | {s['d'] / hours * 24:+.3f} | {s['why']['copy']}/{s['why']['max']}/{s['why']['sl']} | {s['flags']['grad']}/{s['flags']['tape_end']}")
P(f"(* = main variant, fixed before results: {vn(MAIN)}; {len(VARS)} variants tested -> expect ~{0.1 * len(VARS):.0f} of {len(VARS)} 90% CIs to exclude 0 by chance; Bonferroni-90% needs ~p<{0.1 / len(VARS):.4f})")
P("")
P("A2. Per run, main variant and the best pooled variant:")
best = max((v for v in VARS if stats(L, v, "base")), key=lambda v: stats(L, v, "base")["d"])
for v in (MAIN, best):
    P(f"  {vn(v)}{'  (best pooled diff, selected AFTER looking)' if v == best else '  (main)'}")
    P("  run      | fills | hours | n aff | real on aff | hybrid | diff   | 90% CI           | per fill | diff/engine-day")
    for r in RUNS:
        rr = [x for x in L if x["run"] == r]; s = stats(rr, v, "base")
        if not s: P(f"  {r:<8} | {len(rr):5d} | {HRS[r]:5.1f} |     0 |"); continue
        P(f"  {r:<8} | {len(rr):5d} | {HRS[r]:5.1f} | {s['n']:5d} | {s['base']:+8.3f} | {s['hyb']:+7.3f} | {s['d']:+6.3f} | [{s['lo']:+6.3f}, {s['hi']:+6.3f}] | {s['per']:+.4f} | {s['d'] / HRS[r] * 24:+.3f}")
P("")
# ---------------------------------------------------------------- B. holders at our fill (live)
P("B. When we filled (live, all runs): was E2x1 / Grozoe in? (MEASURED; E2x1 from recon lots where covered, else tape)")
for W, nm in ((E, "E2x1"), (G, "Grozoe")):
    c = collections.Counter()
    for x in L:
        i = x["info"][W]
        if i["holds"]: c["holding at our fill"] += 1
        elif i["first_after"] and i["first_after"][0] - x["fs"] <= 10: c["first buy <=10 slots after our fill"] += 1
        elif i["first_after"] and (i["first_after"][0] - x["fs"]) * Z["SLOT_MS"] / 1000 <= 60: c["first buy 10 slots-60 s after"] += 1
        elif i["sold_before"]: c["bought+sold before our fill"] += 1
        if i["enter_while"]: c["entered while we still held"] += 1
    P(f"  {nm}: " + ", ".join(f"{k} {v}" for k, v in c.most_common()) + f"  (of {len(L)} fills)")
both = sum(1 for x in L if x["info"][E]["holds"] and x["info"][G]["holds"])
P(f"  both holding: {both}; tape-vs-lots agreement on E2x1 holding (fills inside recon window): "
  f"{sum(1 for x in L if x['info'][E]['src'] == 'lots' and x['info'][E]['holds'] == x['info'][E]['tape_holds'])}/{sum(1 for x in L if x['info'][E]['src'] == 'lots')}")
P("")
# ---------------------------------------------------------------- C. last 24 h live
L24 = [x for x in L if W0 <= x["ft"] <= W1]; R24 = sorted({x["run"] for x in L24}, key=runorder)
h24 = (min(W1, max(x["ft"] for x in L24)) - W0) / 3600
P(f"C. LAST 24 H (10-27 21:30 -> 10-28 21:30 PKT), LIVE pre-send fills: {len(L24)} fills in runs {', '.join(f'{r} ({sum(1 for x in L24 if x['run'] == r)})' for r in R24)}; "
  f"real P&L all {sum(x['real'] for x in L24):+.3f} SOL")
P("variant                                        | n aff | real on aff | hybrid | diff   | 90% CI           | per fill | top-3 | grad/tape_end")
for v in VARS:
    s = stats(L24, v, "base")
    if s: P(f"{vn(v)} {'*' if v == MAIN else ' '}| {s['n']:5d} | {s['base']:+8.3f} | {s['hyb']:+7.3f} | {s['d']:+6.3f} | [{s['lo']:+6.3f}, {s['hi']:+6.3f}] | {s['per']:+.4f} | {s['top3']:+.3f} | {s['flags']['grad']}/{s['flags']['tape_end']}")
P("  per run, main variant:")
for r in R24:
    s = stats([x for x in L24 if x["run"] == r], MAIN, "base")
    if s: P(f"  {r:<8} n aff {s['n']:3d} | real {s['base']:+.3f} | hybrid {s['hyb']:+.3f} | diff {s['d']:+.3f} [{s['lo']:+.3f}, {s['hi']:+.3f}]")
    else: P(f"  {r:<8} n aff 0")
def ex(rows, v, title):
    s = stats(rows, v, "base")
    if not s: return
    z = sorted(zip(s["d_list"], s["aff"]), key=lambda t: -t[0])
    P(f"  {title} — 5 best / 5 worst by hybrid-minus-baseline ({vn(v)}):")
    sel = z[:5] + z[-5:] if len(z) > 10 else z
    for k, (d, x) in enumerate(sel):
        if len(z) > 10 and k == 5: P("   ...")
        hold = [n for n, W in (("E2x1", E), ("Grozoe", G)) if x["info"][W]["holds"]] or [n + "(after)" for n, W in (("E2x1", E), ("Grozoe", G)) if x["info"][W]["enter_while"]]
        P(f"   {pk(x['ft'])} {x['run']:<8} https://gmgn.ai/sol/token/{x['mint']}  base {x['base']:+.4f} -> hybrid {x['hyb'][v]:+.4f} ({d:+.4f}); "
          f"held {x['res'][v][2]:.1f} s, exit={x['res'][v][3]}{' ' + x['res'][v][1] if x['res'][v][1] else ''}; holder {'+'.join(hold)}"
          + (f"; our buy https://solscan.io/tx/{x['buy_sig']}" if x.get("buy_sig") else ""))
ex(L24, MAIN, "LIVE 24 h")
P("")
# ---------------------------------------------------------------- D. 24 h shadow
for x in SH: pass
P(f"D. LAST 24 H, SHADOW pre-send fills (row c = lands 10 ms after the dump; entry state from the engine record, size {np.median([x['sol_in'] for x in SH]) / 1e9:.3f} SOL curve-in), "
  f"{len(SH)} shadow fills priced (skipped {sum(1 for x in Z['shadow'] if 'res' not in x)}); baseline = sell 200 ms after fill (+L); all-fill baseline {sum(x['base'] for x in SH):+.3f} SOL. "
  f"Costs 1.25 % fee each way + 2.9 mSOL/trip. INFERRED (no real tx).")
P(f"  shadow runs: {dict(collections.Counter(x['run'] for x in SH))}; shadow fills that were also live-fired (imit.fired): {sum(1 for x in SH if x.get('fired'))}")
P("variant                                        | n aff | base on aff | hybrid | diff   | 90% CI           | per fill | top-3 | grad/tape_end")
for v in VARS:
    s = stats(SH, v, "base")
    if s: P(f"{vn(v)} {'*' if v == MAIN else ' '}| {s['n']:5d} | {s['base']:+8.3f} | {s['hyb']:+7.3f} | {s['d']:+6.3f} | [{s['lo']:+6.3f}, {s['hi']:+6.3f}] | {s['per']:+.4f} | {s['top3']:+.3f} | {s['flags']['grad']}/{s['flags']['tape_end']}")
for x in SH: x["buy_sig"] = None
ex(SH, MAIN, "SHADOW 24 h")
open(f"{RP}/tables.txt", "w").write("\n".join(out) + "\n")
