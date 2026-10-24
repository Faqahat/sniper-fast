#!/usr/bin/env python3
# Selection study, step 3 (local only): one config, hour by hour (PKT), same hours side by side with the three wallets.
# Per hour: all dumps and tokens with a dump; THEIR picks (dumps each wallet bought right after, and tokens); OUR picks (config,
# spacing: no new pick on a token within 5 slots of our last pick on it); overlap; our fills (guard passes), wins, P&L at
# 35 / 50 / 75 ms; and tokens: how many of OUR tokens ended net positive for us. Exit H slots.
# usage: python3 -I sel_hourly.py CONFIG_JSON [FROM 'MM-DD HH:MM' PKT]
import json, gzip, sys, os, time, calendar, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
H = os.environ.get("H", "4")
cfg = json.loads(sys.argv[1]); FROM = calendar.timegm(time.strptime("2026-" + (sys.argv[2] if len(sys.argv) > 2 else "10-23 06:00"), "%Y-%m-%d %H:%M")) - 18000
EV = [json.loads(l) for l in gzip.open("/home/moiz/sniper/ops/overnight/sel/sel_events.jsonl.gz", "rt")]
def fv(r, k):
    x = r["xf"]; t = r["tok"]
    if k == "drop_pct": return (1 - r["drop"]) * 100
    if k in ("first_big", "ins"): return float(r[k])
    if k in x: return x[k]
    if k == "prev_sell_ms": return r["prev_sell_ms"] if r["prev_sell_ms"] >= 0 else 1e9
    if k in ("n_tr", "vmax", "since_buy"): return t[k] if t[k] is not None and t[k] >= 0 else 1e9
    return r[k]
RULES = cfg if cfg and isinstance(cfg[0][0], list) else [cfg]          # one AND-config, or an OR-list of them
def ok1(r, c): return all((fv(r, k) >= v) if op == ">=" else (fv(r, k) <= v) for k, op, v in c)
def ok(r): return any(ok1(r, c) for c in RULES)
def g(r, L):
    if str(L) not in r["pnl"]: return None
    return (r["pnl"][str(L)][H], True) if r["px"][str(L)] <= 1.02 else (-0.0002, False)
EV.sort(key=lambda r: (r["m"], r["age"])); _pm = None; _b = []
for r in EV:                     # the three wallets' earlier dip buys on the token (same definition as sel_cover.py)
    if r["m"] != _pm: _pm = r["m"]; _b = []
    t0 = r["age"] * 1000.0; past = [b for b in _b if b < t0]
    r["tgt_n"] = len(past); r["tgt_since"] = (t0 - max(past)) / 1000.0 if past else 1e9
    for w, d in r["lab"].items(): _b.append(t0 + d)
EV = [r for r in EV if r["bt"] + r["age"] >= FROM]
EV.sort(key=lambda r: (r["m"], r["age"]))
last = {}; ours = set()
for i, r in enumerate(EV):
    if not ok(r): continue
    if r["m"] in last and r["age"] - last[r["m"]] < 5 * 0.212: continue
    last[r["m"]] = r["age"]; ours.add(i)
hr = lambda r: time.strftime("%m-%d %H", time.gmtime(r["bt"] + r["age"] + 18000))
A = collections.defaultdict(lambda: collections.defaultdict(float)); TOK = collections.defaultdict(lambda: collections.defaultdict(set)); TP = collections.defaultdict(float)
for i, r in enumerate(EV):
    h = hr(r); a = A[h]; a["dumps"] += 1; TOK[h]["all"].add(r["m"])
    for w in ("HkQ7hMjy", "DYXDDrZC", "haqqiUUX"):
        if w in r["lab"]: a[w] += 1; TOK[h][w].add(r["m"])
    if r["lab"]: a["their"] += 1; TOK[h]["their"].add(r["m"])
    if i in ours:
        a["ours"] += 1; TOK[h]["ours"].add(r["m"])
        if r["lab"]: a["both"] += 1
        for L in (35, 50, 75):
            x = g(r, L)
            if x is None: continue
            a[f"p{L}"] += x[0]
            if x[1]: a[f"f{L}"] += 1; a[f"w{L}"] += x[0] > 0
        x = g(r, 35)
        if x and x[1]: TP[r["m"]] += x[0]            # tokens where at least one of our buys filled
for c in RULES: print("rule: " + " AND ".join(f"{k} {op} {v:.4g}" for k, op, v in c))
print(f"exit {H} slots | from {sys.argv[2] if len(sys.argv) > 2 else '10-23 06:00'} PKT")
print("hour PKT  | dumps  tokens | THEIR dumps (HkQ7/DYX/haq)  % of dumps  tokens | OUR picks  % of dumps  tokens | ours they also bought | "
      "35 ms fills win P&L | 50 ms P&L | 75 ms P&L")
tot = collections.defaultdict(float)
for h in sorted(A):
    a = A[h]; t = TOK[h]
    for k, v in a.items(): tot[k] += v
    for k in ("all", "their", "ours"): tot["tok_" + k] += len(t[k])
    print(f"{h}     | {a['dumps']:5.0f} {len(t['all']):6d}  | {a['their']:5.0f} ({a['HkQ7hMjy']:.0f}/{a['DYXDDrZC']:.0f}/{a['haqqiUUX']:.0f}) {a['their'] / a['dumps']:8.1%} {len(t['their']):6d} | "
          f"{a['ours']:5.0f} {a['ours'] / a['dumps']:8.1%} {len(t['ours']):6d} | {a['both'] / max(a['ours'], 1):10.0%}           | "
          f"{a['f35']:4.0f} {a['w35'] / max(a['f35'], 1):4.0%} {a['p35']:+6.2f} | {a['p50']:+6.2f} | {a['p75']:+6.2f}")
nh = len(A)
print(f"TOTAL {nh} h | {tot['dumps']:.0f} dumps ({tot['dumps'] / nh:.0f}/h) | THEIR {tot['their']:.0f} ({tot['their'] / nh:.1f}/h, {tot['their'] / tot['dumps']:.1%}) | "
      f"OUR {tot['ours']:.0f} ({tot['ours'] / nh:.1f}/h, {tot['ours'] / tot['dumps']:.1%}) | ours they also bought {tot['both'] / max(tot['ours'], 1):.0%} | "
      f"35 ms: fills {tot['f35']:.0f} win {tot['w35'] / max(tot['f35'], 1):.0%} P&L {tot['p35']:+.2f} | 50 ms: win {tot['w50'] / max(tot['f50'], 1):.0%} P&L {tot['p50']:+.2f} | "
      f"75 ms: win {tot['w75'] / max(tot['f75'], 1):.0%} P&L {tot['p75']:+.2f}")
pos = sum(1 for v in TP.values() if v > 0)
print(f"tokens per hour: all {tot['tok_all'] / nh:.0f} | theirs {tot['tok_their'] / nh:.1f} | ours {tot['tok_ours'] / nh:.1f} | "
      f"tokens where we got filled at 35 ms: {len(TP)}, net positive {pos} ({pos / max(len(TP), 1):.0%})")
