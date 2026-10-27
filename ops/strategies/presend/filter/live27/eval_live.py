#!/usr/bin/env python3
"""QUIET live evaluation of a dip20 run (MEASURED from the engine records; paper rows labelled as such).
usage: eval_live.py <run>.jsonl"""
import sys, json, collections, datetime as dt
PKT = dt.timezone(dt.timedelta(hours=5))
def hm(ns): return dt.datetime.fromtimestamp(ns / 1e9, PKT).strftime("%H:%M:%S")
F = sys.argv[1]
arm, dis, real, fill, ata = {}, {}, {}, {}, collections.defaultdict(list)
skips = []; att_fail = collections.Counter(); att_keys = None
shadow_arm = {}; shadow_exit = collections.defaultdict(dict)
for line in open(F, errors="ignore"):
    if '"presend' not in line: continue
    d = json.loads(line); ev = d.get("ev")
    if ev == "presend_live_arm": arm[d["w"]] = d
    elif ev == "presend_live_disarm": dis[d["w"]] = d
    elif ev == "presend_live_realized": real[d["w"]] = d
    elif ev == "presend_live_fill": fill[d["w"]] = d
    elif ev == "presend_live_ata_close": ata[d["mint"]].append(d)
    elif ev == "presend_live_skip": skips.append(d)
    elif ev == "presend_attempt_land":
        if att_keys is None: att_keys = sorted(d.keys())
        w = d.get("w"); err = d.get("err")
        if w is not None and err and d.get("res") != "unseen": att_fail[w] += d.get("fee") or 5120
    elif ev == "presend_arm": shadow_arm[d.get("sig")] = d
    elif ev == "presend_exit":
        shadow_exit[(d.get("mint"), d.get("row"))] = d
print("attempt_land keys:", att_keys)
used = set()
def win_net(w):
    r = real.get(w); f = fill.get(w)
    pnl = (r or {}).get("pnl", 0) if f else 0
    rb = 0
    if f:
        for q, z in enumerate(ata.get(f["mint"], [])):
            if (f["mint"], q) in used: continue
            if z.get("slot", 0) >= f["slot"]: rb = z.get("delta", 0); used.add((f["mint"], q)); break
    return pnl, rb, att_fail.get(w, 0)
rows = []
for w, a in sorted(arm.items()):
    q = a.get("quiet") or {}; t = a["trig"]["t"]
    pnl, rb, fee = win_net(w)
    d = dis.get(w, {})
    rows.append(dict(w=w, t=t, mint=a["trig"]["mint"], all4=q.get("all4"), rule_on=q.get("rule_on"), filled=bool(fill.get(w)),
                     pnl=pnl, rb=rb, fee=fee, net=pnl + rb - fee, stop=d.get("quiet_stop", False)))
def summ(name, R):
    n = len(R); nf = sum(r["filled"] for r in R); s = sum(r["net"] for r in R) / 1e9
    wins = sum(1 for r in R if r["filled"] and r["pnl"] + r["rb"] > 0)
    print(f"  {name:48s} windows {n:4d} fills {nf:3d} wins {wins:3d} | trades {sum(r['pnl'] for r in R)/1e9:+.4f} rent {sum(r['rb'] for r in R)/1e9:+.4f} fees {-sum(r['fee'] for r in R)/1e9:+.4f} -> net {s:+.4f} SOL")
tot = sum(r["net"] for r in rows) / 1e9
on_t = min((r["t"] for r in rows if r["rule_on"]), default=None)
print(f"live pre-send windows {len(rows)}; skip rule ON from {hm(on_t) if on_t else '-'} PKT; total net {tot:+.4f} SOL (fee only of attempts with a landed error)")
W = [r for r in rows if not r["rule_on"]]; O = [r for r in rows if r["rule_on"]]
print("WARM-UP (skip rule off, stop rule on):"); summ("all armed windows", W)
summ("would-skip (all 4 signals held) [MEASURED]", [r for r in W if r["all4"]])
summ("kept by the rule", [r for r in W if not r["all4"]])
print("SKIP RULE ON:"); summ("all armed windows", O)
print("STOP RULE (both phases):"); summ("windows stopped quiet", [r for r in rows if r["stop"]])
for r in [r for r in W if r["all4"] and r["filled"]]:
    print(f"    would-skip fill {hm(r['t'])} {r['mint'][:8]} net {r['net']/1e9:+.4f}")
qs = [s for s in skips if s.get("quiet_skip")]
print(f"SKIPPED by the rule: {len(qs)} triggers (no live data; paper rows below are the engine's shadow, NOT a forecast)")
by = collections.Counter(s.get("why") for s in skips); print("  all live skip reasons:", dict(by))
