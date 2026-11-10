#!/usr/bin/env python3
"""TEN FROZEN scorer (FILTERS-3, 11-03 PKT). Read-only. usage: score.py RUN.presend.jsonl [--from-ns T0] [--to-ns T1]
Prints, for one run (optionally a time slice by record t), the live money and two ADD-MONEY levers, all as ESTIMATES:

  BASE     live realized (presend_live_realized, all kinds) = the run's real money; n, SOL, SOL/day, win, w/o top 5.
  WIDE5    a 5% whale threshold = the wide shadow's (presend_wide_*) windows holding 5.0 <= pct < 6.0 at arm with age_slots >= 2,
           row c net_cheap scaled to the live T2 size (spend of the first live T2 arm / row c sol_in), CALIBRATED by the run's own
           main shadow vs live gap (mean over live T2 windows whose trigger the shadow filled of live realized (0 if no live fill) minus
           scaled paper; wide_report.py method), minus every wide fill whose mint has a live window (T2 or re-arm) armed within 12 slots
           of the wide fill slot (one window per token: conservative, the live window keeps the token). QUIET / lone-whale cannot be
           applied offline (stated).
  SIZE15   T2 positions whose live arm record has v2.n_tr_60s >= 15 bought at 1.5x the live spend: own-tape curve replay (constant
           product from the live tape rows' post-trade vsol/vtok; others' later buys = fixed SOL, sells = fixed tokens; our sell at its
           live landing (slot, idx); 1.25% fee each way; the position's own fixed costs). Follower price-out: each later buy by others is
           dropped with prob BETA x 2 x (extra curve SOL) / pre-buy vsol (deterministic sha256 draw). Printed: delta vs live at BETA 3
           (the frozen point), BETA 0, BETA 9, and BETA 3 with 20% of later buys dropped at both sizes. Multi-round positions: linear.
Records used: run_start/run_end t, presend_live_arm/_fill/_close/_realized/_tape, presend_arm, presend_fill/_exit (row c),
presend_wide_arm/_fill/_exit (row c). Nothing else."""
import sys, json, hashlib, collections

ME = "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"
FEE = 0.0125
path = sys.argv[1]
t0 = int(sys.argv[sys.argv.index("--from-ns") + 1]) if "--from-ns" in sys.argv else None
t1 = int(sys.argv[sys.argv.index("--to-ns") + 1]) if "--to-ns" in sys.argv else None
def inside(t): return t is not None and (t0 is None or t >= t0) and (t1 is None or t < t1)

first_t = last_t = None
live_arm = {}           # (kind, w) -> dict(mint, slot, sig, spend, n60, t)
fills, closes, real, tapes = {}, {}, collections.defaultdict(int), collections.defaultdict(list)
sh_w, sh_exit, sh_size = {}, {}, {}
wa, wf, wx = {}, {}, {}
live_size = None
for line in open(path, errors="replace"):
    if '"ev":"' not in line or '"ev":"presend_attempt' in line: continue
    d = json.loads(line); e = d.get("ev"); t = d.get("t")
    if isinstance(t, int) and t > 10**18 and inside(t):
        first_t = t if first_t is None else min(first_t, t); last_t = t if last_t is None else max(last_t, t)
    k = (d.get("kind", "t2"), d.get("w"))
    if e == "presend_live_arm":
        tr = d.get("trig") or d.get("dump") or {}
        live_arm[k] = {"mint": d.get("mint") or tr.get("mint"), "slot": d.get("arm_slot") or tr.get("slot"), "sig": tr.get("sig"),
                       "spend": d.get("spend"), "n60": (d.get("v2") or {}).get("n_tr_60s"), "t": tr.get("t")}
        if k[0] == "t2" and live_size is None: live_size = (d.get("spend") or 0) / 1e9 or None
    elif e == "presend_live_fill": fills.setdefault(k, d)
    elif e == "presend_live_close": closes.setdefault(k, d)
    elif e == "presend_live_realized": real[k] += d.get("pnl", 0)
    elif e == "presend_live_tape": tapes[d["mint"]].append(d)
    elif e == "presend_arm": sh_w[d["sig"]] = d.get("w")
    elif e == "presend_exit" and d.get("row") == "c": sh_exit[d["w"]] = d.get("net_cheap", d.get("pnl", 0.0))
    elif e == "presend_fill" and d.get("row") == "c" and "entry" in d: sh_size.setdefault(d["w"], d["entry"].get("sol_in", 0) / 1e9)
    elif e == "presend_wide_arm": wa[d["w"]] = d
    elif e == "presend_wide_fill" and d.get("row") == "c": wf.setdefault(d["w"], d)
    elif e == "presend_wide_exit" and d.get("row") == "c": wx[d["w"]] = d.get("net_cheap", d.get("pnl", 0.0))
hrs = (last_t - first_t) / 3.6e12 if first_t else 0.0

def t_of(k):
    f = fills.get(k); return f.get("t") if f else (live_arm.get(k) or {}).get("t")

def summ(v, label):
    if not v: print(f"{label:8s} n    0"); return
    s = sorted(v, reverse=True)
    print(f"{label:8s} n {len(v):4d} | {sum(v):+8.3f} SOL | {sum(v) / hrs * 24:+6.2f} SOL/day | win {sum(1 for x in v if x > 0) / len(v):4.0%} | w/o top 5 {sum(s[5:]):+8.3f} SOL = {sum(s[5:]) / hrs * 24:+6.2f}/day")

print(f"TEN score {path}  hours {hrs:.2f}  live T2 size {live_size}")
# BASE
base_keys = [k for k in real if inside(t_of(k))]
summ([real[k] / 1e9 for k in base_keys], "BASE")

# WIDE5
def scale(p, size): return p * ((live_size / size) if live_size and size else 1.0)
pairs = []
for k, a in live_arm.items():
    if k[0] != "t2" or not inside(a.get("t")): continue
    w = sh_w.get(a["sig"])
    if w is None or w not in sh_exit: continue
    pairs.append((scale(sh_exit[w], sh_size.get(w)), real.get(k, 0) / 1e9))
gap = sum(r - p for p, r in pairs) / len(pairs) if pairs else 0.0
lw = collections.defaultdict(list)
for k, a in live_arm.items():
    if a.get("slot"): lw[a["mint"]].append(a["slot"])
wv, wraw, nconf = [], [], 0
for w, a in wa.items():
    if not inside(a.get("t")) or not (5.0 <= a.get("pct", 0) < 6.0) or a.get("age_slots", 0) < 2 or w not in wx: continue
    f = wf.get(w) or {}
    p = scale(wx[w], (f.get("entry") or {}).get("sol_in", 0) / 1e9)
    if any(abs(s - (f.get("s_in") or 0)) <= 12 for s in lw.get(a["mint"], [])): nconf += 1; continue
    wraw.append(p); wv.append(p + gap)
print(f"WIDE5 calibration: {len(pairs)} pairs, gap {gap * 1000:+.2f} mSOL/window; {nconf} wide fills dropped (live window on the token)")
summ(wraw, "WIDE5raw")
summ(wv, "WIDE5")

# SIZE15
def h(s): return int(hashlib.sha256(s.encode()).hexdigest()[:8], 16) / 0xffffffff
def replay(k, m_size, beta, drop):
    f, c = fills.get(k), closes.get(k)
    if not f or not c or (c.get("rounds") or 1) > 1 or not c.get("sell_land"): return None
    tp = sorted((x for x in tapes.get(f["mint"], []) if f["slot"] - 2 <= x["slot"] <= f["slot"] + 40), key=lambda x: (x["slot"], x.get("idx") or 0))
    me = [x for x in tp if x.get("user") == ME and x.get("buy") and x["slot"] == f["slot"] and x.get("idx") == f.get("idx")]
    if not me: return None
    m = me[0]; v0 = m["vsol"] - m["sol"]; tk0 = m["vtok"] + m["tok"]; K = v0 * tk0
    spend = (f.get("spend") or live_arm[k]["spend"]) / 1e9 * m_size
    x_in = spend * 1e9 / (1 + FEE); v = v0 + x_in; tt = K / v; mytok = tk0 - tt
    p_out = max(0.0, beta * 2 * (x_in - m["sol"]) / v0)
    sl = c["sell_land"]
    for x in tp:
        key = (x["slot"], x.get("idx") or 0)
        if key <= (m["slot"], m.get("idx") or 0): continue
        if key >= (sl[0], sl[1]): break
        if x.get("user") == ME: continue
        if x.get("buy"):
            if drop and h(f"7:{x['sig']}") < drop: continue
            if p_out and h(f"po:{x['sig']}") < p_out: continue
            v += x["sol"]; tt = K / v
        else:
            tt += x["tok"]; v = K / tt
    out = v - K / (tt + mytok)
    pnl_live = real[k] / 1e9
    fixed = (c.get("curve_pnl") or 0) / 1e9 - FEE * ((c.get("sol_in_curve") or 0) + (c.get("sol_out_curve") or 0)) / 1e9 - pnl_live
    return (out - x_in) / 1e9 - FEE * (x_in + out) / 1e9 - fixed

sel = [k for k in base_keys if k[0] == "t2" and ((live_arm.get(k) or {}).get("n60") or -1) >= 15]
res = collections.defaultdict(float); nrep = 0
for k in sel:
    pl = real[k] / 1e9
    r3 = replay(k, 1.5, 3.0, 0.0)
    if r3 is None:
        for b in ("b3", "b0", "b9", "b3d20"): res[b] += pl * 0.5
        continue
    nrep += 1
    res["b3"] += r3 - pl; res["b0"] += replay(k, 1.5, 0.0, 0.0) - pl; res["b9"] += replay(k, 1.5, 9.0, 0.0) - pl
    res["b3d20"] += replay(k, 1.5, 3.0, 0.2) - replay(k, 1.0, 0.0, 0.2)
print(f"SIZE15   trades n60>=15: {len(sel)} (replayed {nrep}); their live money {sum(real[k] for k in sel) / 1e9:+.3f} SOL")
for b, lab in (("b3", "beta 3 (frozen)"), ("b0", "beta 0"), ("b9", "beta 9"), ("b3d20", "beta 3, -20% buys")):
    print(f"SIZE15   delta {lab:18s} {res[b]:+8.3f} SOL = {res[b] / hrs * 24:+6.2f}/day")
