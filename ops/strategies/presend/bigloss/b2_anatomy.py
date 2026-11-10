#!/usr/bin/env python3
"""BIGLOSS b2: anatomy of every big loss (<= -0.04 SOL) r37-r55 + contrast with wins of the same kind.
Labels use what happened inside our hold (outcome, NOT features)."""
import sys, json, collections
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/bigloss")
from blib import *

BOTS = {"DL7cmioG", "4ggJqUDD", "8PgC4ngp", "sssssDdM", "EMKY7r6U", "9pQQc1xy", "6Z91Dgiz", "FfW5e8gK"}
P = load()
rows = []
for d in P:
    s, b = hold_sellers(d)
    sell_tot = sum(s.values()); buy_tot = sum(b.values())
    main, msol = (max(s.items(), key=lambda kv: kv[1]) if s else (None, 0.0))
    a = d.get("arm") or {}
    cr = ((a.get("ann") or {}).get("creator") or "")[:8]
    wh = whale_of(d)
    hs = sign_holders(d)
    hmap = {h["w"]: h for h in (hs or [])}
    ta = tok_age_fill(d)
    arm_h = {x["w"][:8] for x in (a.get("holders") or [])}
    role = "none"
    if msol >= 0.5:
        if main == wh: role = "whale_resell" if d["kind"] == "t2" else "dumper_resell"
        elif main == cr: role = "creator"
        elif main in arm_h: role = "rearm_holder6"
        elif main in hmap:
            h = hmap[main]
            if ta is not None and h["age"] is not None and h["age"] >= ta - 1: role = "launch_slot_holder"
            elif h["n"] is not None and h["n"] <= 1: role = "fresh_holder"
            else: role = "bot_holder"
        else: role = "unlisted"  # held < ~2% at landing, or tokens moved in (transfer-fed), or bought after our landing
    rows.append({"run": d["run"], "rk": d["rk"], "set": d["set"], "t": d["t"], "mint": d["mint"], "kind": d["kind"], "pnl": d["pnl"],
                 "sol_in": d["fill"].get("sol_in", 0) / 1e9, "role": role, "main": main, "msol": msol, "known_bot": main in BOTS,
                 "sell_tot": sell_tot, "buy_tot": buy_tot, "n_sellers1": sum(1 for v in s.values() if v >= 1),
                 "age": ta, "depth": (d["fill"].get("ann") or {}).get("depth"), "hour": hour_pkt(d["t"]),
                 "client": d["fill"].get("client"), "has_h": hs is not None, "exit": (d.get("close") or {}).get("exit_why")})
json.dump(rows, open(f"{D}/anatomy_rows.json", "w"))
big = [r for r in rows if r["pnl"] <= BIG]
print("positions", len(rows), "big losses", len(big), "sum %.3f" % sum(r["pnl"] for r in big),
      "| all losses %.3f | wins %.3f" % (sum(r["pnl"] for r in rows if r["pnl"] <= 0), sum(r["pnl"] for r in rows if r["pnl"] > 0)))
print("\n== big losses by split/kind")
for st in ("DEV", "VAL", "HOLD"):
    for k in ("t2", "rearm"):
        b = [r for r in big if r["set"] == st and r["kind"] == k]; a_ = [r for r in rows if r["set"] == st and r["kind"] == k]
        print(f"{st:5} {k:6} big {len(b):4} {sum(r['pnl'] for r in b):8.3f} | all n {len(a_):5} net {sum(r['pnl'] for r in a_):8.3f}")
print("\n== big losses by main in-hold seller role (sell>=0.5 SOL)")
c = collections.defaultdict(list)
for r in big: c[(r["kind"], r["role"])].append(r)
for k, v in sorted(c.items(), key=lambda kv: sum(r["pnl"] for r in kv[1])):
    print(f"{k[0]:6} {k[1]:20} n {len(v):4} {sum(r['pnl'] for r in v):8.3f}  known-bot {sum(1 for r in v if r['known_bot'])}  per set " +
          " ".join(f"{s}:{sum(1 for r in v if r['set']==s)}/{sum(r['pnl'] for r in v if r['set']==s):.2f}" for s in ("DEV", "VAL", "HOLD")))
print("\n== same role among WINS (pnl>0) -- how often the same seller type sells into winners")
cw = collections.defaultdict(list)
for r in rows:
    if r["pnl"] > 0: cw[(r["kind"], r["role"])].append(r)
for k, v in sorted(cw.items(), key=lambda kv: -len(kv[1])):
    print(f"{k[0]:6} {k[1]:20} wins n {len(v):4} {sum(r['pnl'] for r in v):8.3f}")
print("\n== top main sellers in big losses (8-char) and their record across ALL positions where they sold >=0.5 into our hold")
cnt = collections.Counter(r["main"] for r in big if r["main"] and r["msol"] >= 0.5)
for w, n in cnt.most_common(25):
    allp = [r for r in rows if r["main"] == w and r["msol"] >= 0.5]
    print(f"{w} big {n:3} | as main seller: n {len(allp):3} W {sum(1 for r in allp if r['pnl']>0):3} net {sum(r['pnl'] for r in allp):7.3f} runs {sorted(set(r['run'] for r in allp))}")
print("\n== big losses by hour PKT")
for h in range(24):
    b = [r for r in big if r["hour"] == h]; a_ = [r for r in rows if r["hour"] == h]
    if a_: print(f"{h:02d} big {len(b):3} {sum(r['pnl'] for r in b):7.3f} | all {len(a_):4} net {sum(r['pnl'] for r in a_):7.3f}")
print("\n== by token age at fill (slots)")
for lo, hi in ((0, 5), (5, 15), (15, 40), (40, 100), (100, 300), (300, 10 ** 9)):
    b = [r for r in big if r["age"] is not None and lo <= r["age"] < hi]; a_ = [r for r in rows if r["age"] is not None and lo <= r["age"] < hi]
    print(f"{lo}-{hi} big {len(b):3} {sum(r['pnl'] for r in b):7.3f} | all {len(a_):4} net {sum(r['pnl'] for r in a_):7.3f} rate {len(b)/max(1,len(a_)):.3f}")
print("\n== by leader client")
for cl in sorted(set(r["client"] for r in rows), key=str):
    b = [r for r in big if r["client"] == cl]; a_ = [r for r in rows if r["client"] == cl]
    print(f"{str(cl):16} big {len(b):3} {sum(r['pnl'] for r in b):7.3f} | all {len(a_):4} net {sum(r['pnl'] for r in a_):7.3f} rate {len(b)/max(1,len(a_)):.3f}")
print("\n== by dip depth at landing")
for lo, hi in ((0, .14), (.14, .18), (.18, .25), (.25, .35), (.35, 1)):
    b = [r for r in big if r["depth"] is not None and lo <= r["depth"] < hi]; a_ = [r for r in rows if r["depth"] is not None and lo <= r["depth"] < hi]
    print(f"{lo}-{hi} big {len(b):3} {sum(r['pnl'] for r in b):7.3f} | all {len(a_):4} net {sum(r['pnl'] for r in a_):7.3f} rate {len(b)/max(1,len(a_)):.3f}")
print("\n== exit reason of big losses", collections.Counter(r["exit"] for r in big))
print("== per run big losses: " + " ".join(f"{k}:{sum(1 for r in big if r['rk']==k)}/{sum(r['pnl'] for r in big if r['rk']==k):.2f}" for k in sorted(set(r['rk'] for r in rows), key=lambda s: (int(s[1:3]), s))))
