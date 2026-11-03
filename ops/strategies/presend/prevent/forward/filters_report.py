#!/usr/bin/env python3
"""HOURLY FILTERS TABLE for a live dip run (owner 10-30 ~08:55 PKT: "include the filters report: how they did, what they blocked, won,
lost ... along with the log-only filters"). Read-only on a local copy of the run's records (.jsonl).

LIVE filters (they changed what the engine did), scored on the shadow's paper (row c: every T2 trigger, the standard 0.88x limit, the
shadow's own fills; P&L scaled to the live size; PAPER ESTIMATE, as filter_savings.py):
  quiet / create_slot / young_age / lone_whale   a skipped T2 trigger -> the shadow's window on the same trigger
  deeper limit (dip28 --presend-live-deep-drop)  a live T2 window whose attempts used the deeper drop and that never filled live, while
                                                 the shadow's window on its trigger filled (the fill the deeper limit refused); its live
                                                 fills that still came ("deep" fills, bought >= 15% down) are counted apart. T2 only
                                                 (re-arm windows have no shadow); a refusal can also be a fill the 0.88x limit would
                                                 have missed, so this is an estimate
LOG-ONLY rules on the run's real fills (realized P&L; "blocked" = the fills the rule would have stopped):
  bad creator (gcr), safe sell timer (st_block), ctx85 (moot when the deeper limit is live), holder clock approx (h3 >= 0.3, n >= 5)
usage: filters_report.py RUN.jsonl [--seed gcr_seed.json]"""
import sys, json, collections, os

path = sys.argv[1]
seed_p = sys.argv[sys.argv.index("--seed") + 1] if "--seed" in sys.argv else "/home/moiz/sniper-data/prevent/forward/gcr_seed.json"
led = collections.defaultdict(lambda: [0, 0.0])
if os.path.exists(seed_p):
    for c, d in json.load(open(seed_p)).items(): led[c] = [d["n"], d["sum"]]

sh_w, sh_exit, sh_size = {}, {}, {}           # shadow: trigger sig -> shadow w; w -> row c P&L (SOL); w -> row c size (SOL)
skips = []                                     # (why, trigger sig)
live_arm_sig, kind, arm_ann, gcr_flag = {}, {}, {}, {}
deep_w, fills, fill_ann, real = set(), set(), {}, {}
live_size = None
for line in open(path, errors="replace"):
    if '"ev":"presend_' not in line: continue
    d = json.loads(line); e = d["ev"]
    if e == "presend_arm": sh_w[d["sig"]] = d.get("w")
    elif e == "presend_exit" and d.get("row") == "c": sh_exit[d["w"]] = d.get("net_cheap", d.get("pnl", 0.0))
    elif e == "presend_fill" and d.get("row", "c") == "c" and "entry" in d: sh_size.setdefault(d.get("w"), d["entry"].get("sol_in", 0) / 1e9)
    elif e == "presend_live_skip":
        if d.get("kind") == "rearm" or "trig" not in d: continue
        skips.append((d.get("why") or "?", d["trig"]["sig"]))
    elif e == "presend_live_arm":
        mint = d.get("mint") or (d.get("trig") or {}).get("mint"); k = (d.get("w"), mint)
        kind[k] = d.get("kind", "t2")
        if kind[k] == "t2":
            live_arm_sig[d["w"]] = d["trig"]["sig"]
            if live_size is None: live_size = d.get("spend", 0) / 1e9 or None
        a = d.get("ann")
        if a is not None:
            arm_ann[k] = a
            c = a.get("creator"); n, s = led[c] if c else (0, 0.0)
            gcr_flag[k] = bool(c and a.get("cr_pct", 0) >= 3 and n >= 2 and s <= -0.05)
    elif e == "presend_attempt" and d.get("drop") is not None and d.get("kind") != "rearm":
        if d["drop"] > 0.125: deep_w.add(d["w"])
    elif e == "presend_live_fill":
        fills.add(d["w"]); fill_ann.setdefault((d["w"], d["mint"]), (d.get("ann") or {}, d.get("deep")))
    elif e == "presend_live_realized":
        k = (d["w"], d["mint"]); real[k] = d["pnl"] / 1e9
        a = arm_ann.get(k)
        if a and a.get("creator") and a.get("cr_pct", 0) >= 3: led[a["creator"]][0] += 1; led[a["creator"]][1] += real[k]

def paper(w):
    p = sh_exit.get(w)
    if p is None: return None
    return p * ((live_size / sh_size[w]) if live_size and sh_size.get(w) else 1.0)

rows = []   # (name, kind, blocked, win_n, win_sol, lose_n, lose_sol, note)
agg = collections.defaultdict(list)
for why, sig in skips:
    w = sh_w.get(sig); v = paper(w) if w is not None else None
    agg[why].append(v)
for why in ("quiet", "create_slot", "young_age", "lone_whale"):
    vs = agg.get(why, []); f = [x for x in vs if x is not None]
    rows.append((why.replace("young_age", "age-1 skip").replace("lone_whale", "10-sec skip").replace("create_slot", "create-slot skip").replace("quiet", "QUIET"),
                 "LIVE", len(vs), sum(1 for x in f if x > 0), sum(x for x in f if x > 0), sum(1 for x in f if x <= 0), sum(x for x in f if x <= 0), "paper; blocked = triggers skipped, W/L = the ones that would have filled"))
if deep_w:
    blocked = [w for w in deep_w if w not in fills]
    vs = [paper(sh_w.get(live_arm_sig.get(w))) for w in blocked if live_arm_sig.get(w) in sh_w]
    f = [x for x in vs if x is not None]
    deep_fills = [k for k, (a, dp) in fill_ann.items() if dp]
    rows.append(("deeper limit", "LIVE", len(blocked), sum(1 for x in f if x > 0), sum(x for x in f if x > 0), sum(1 for x in f if x <= 0), sum(x for x in f if x <= 0),
                 f"paper estimate, T2; {len(deep_w)} windows ran deep, {len(deep_fills)} still filled deeper (real P&L {sum(real.get(k, 0) for k in deep_fills):+.3f})"))
def logrule(name, keys, note):
    v = [real[k] for k in keys if k in real]
    rows.append((name, "LOG", len(v), sum(1 for x in v if x > 0), sum(x for x in v if x > 0), sum(1 for x in v if x <= 0), sum(x for x in v if x <= 0), note))
logrule("bad creator", [k for k in real if gcr_flag.get(k)], "real fills")
logrule("safe sell timer", [k for k, (a, dp) in fill_ann.items() if a.get("st_block")], "real fills (needs the safe on-chain check to be real)")
if not deep_w: logrule("ctx85 (deeper limit, log)", [k for k, (a, dp) in fill_ann.items() if a.get("ctx85")], "real fills")
# GROUP RISK (owner 10-30 ~23:55 PKT "prepare it for the next run"): several 2-6% holders that each look like the safe sell timer's
# risky holder (>= 5 holds at risk, hz3 >= 0.3) add up to >= 6% at landing; constants fixed BEFORE scoring (the safe timer's own)
def group_risk(a):
    if "grp_block" in a: return bool(a["grp_block"])            # dip30 logs the rule itself (12 holders)
    return sum(h.get("pct", 0) for h in a.get("holders", []) if (h.get("risk") or 0) >= 5 and (h.get("hz3") or 0) >= 0.3) >= 6.0
logrule("group risk (new)", [k for k, (a, dp) in fill_ann.items() if group_risk(a)], "real fills; risky holders of any size summed >= 6%")
logrule("holder clock (approx)", [k for k, (a, dp) in fill_ann.items() if any(h.get("pct", 0) >= 6 and h.get("n", 0) >= 5 and (h.get("h3") or 0) >= 0.3 for h in a.get("holders", []))], "real fills")

print(f"FILTERS {os.path.basename(path)}: {len(real)} positions realized {sum(real.values()):+.3f} SOL")
print(f"{'filter':26s} {'type':4s} {'blocked':>7s} | {'would win':>16s} | {'would lose':>16s} | {'net saved':>9s}")
for name, ty, n, wn, ws, ln, ls, note in rows:
    print(f"{name:26s} {ty:4s} {n:7d} | {wn:4d} {ws:+10.3f} | {ln:4d} {ls:+10.3f} | {-(ws + ls):+9.3f}   ({note})")

# UNIQUE TOTALS (owner 10-31: "account for overlap ... add a Total (both log and live)"): the rows above sum one trigger / one fill
# once per rule that caught it; these count each LIVE trigger sig once (a skipped trigger and a deeper-limit window on the same trigger are
# one) and each real fill (w, mint) once (any LOG rule, the landing guard of dip30+ included), and ALL = both (the sets are disjoint: a
# skipped trigger never became a fill). Existing lines above are unchanged.
def _tot(vals):
    w = [x for x in vals if x > 0]; l = [x for x in vals if x <= 0]
    return len(vals), len(w), sum(w), len(l), sum(l)
_lv = {}                                            # trigger key -> paper value (None = the shadow window never filled)
def _put(key, v):
    if _lv.get(key) is None: _lv[key] = v
    else: _lv.setdefault(key, v)
for why, sig in skips:
    if why not in ("quiet", "create_slot", "young_age", "lone_whale"): continue
    w = sh_w.get(sig); _put(sig, paper(w) if w is not None else None)
if deep_w:
    for w in deep_w:
        if w in fills: continue
        sig = live_arm_sig.get(w); key = sig if sig is not None else ("w", w)
        _put(key, paper(sh_w[sig]) if sig in sh_w else None)
_lg = set()
for k, (a, dp) in fill_ann.items():
    if k not in real: continue
    if a.get("st_block") or group_risk(a) or any(h.get("pct", 0) >= 6 and h.get("n", 0) >= 5 and (h.get("h3") or 0) >= 0.3 for h in a.get("holders", [])) \
       or (not deep_w and a.get("ctx85")) or (a.get("guard") or {}).get("block"):
        _lg.add(k)
_lg |= {k for k in real if gcr_flag.get(k)}
LIVE_U = _tot([x for x in _lv.values() if x is not None]); LIVE_U = (len(_lv),) + LIVE_U[1:]
LOG_U = _tot([real[k] for k in _lg])
ALL_U = tuple(a + b for a, b in zip(LIVE_U, LOG_U))
def _line(name, t):
    n, wn, ws, ln, ls = t
    print(f"{name:28s} blocked {n:5d} | win {wn:4d} {ws:+10.3f} | lose {ln:4d} {ls:+10.3f} | net saved {-(ws + ls):+9.3f}")
_line("LIVE total (unique triggers)", LIVE_U)
_line("LOG total (unique fills)", LOG_U)
_line("ALL total", ALL_U)
