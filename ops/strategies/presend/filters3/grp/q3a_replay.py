#!/usr/bin/env python3
"""QUIET3-A alone (frozen 11-03: T2 arm with v2.n_120s <= 15 AND quiet.wh_dumps <= 3, QUIET's rule on) on a run's real fills.
A blocked T2 window saves its realized P&L (+ one failed try ignored). Read-only. usage: q3a_replay.py RUN.jsonl [...]"""
import sys, json, collections
for fn in sys.argv[1:]:
    arm, real = {}, collections.Counter(); t0 = t1 = None
    for l in open(fn, errors="replace"):
        if '"ev":"presend_live_arm"' in l:
            d = json.loads(l)
            if d.get("kind", "t2") != "t2": continue
            v, q = d.get("v2") or {}, d.get("quiet") or {}
            n, wd = v.get("n_120s"), q.get("wh_dumps")
            arm[d["w"]] = None if n is None or wd is None else (n <= 15 and wd <= 3 and q.get("rule_on") is not False)
            t = (d.get("trig") or {}).get("t"); t0 = t if t0 is None else min(t0, t); t1 = t if t1 is None else max(t1, t)
        elif '"ev":"presend_live_realized"' in l:
            d = json.loads(l)
            if d.get("kind", "t2") == "t2": real[d["w"]] += d["pnl"] / 1e9
    v = [p for w, p in real.items() if arm.get(w)]
    na = sum(1 for w in real if arm.get(w) is None)
    h = (t1 - t0) / 3.6e12 if t0 and t1 else 0
    s = sorted(v)
    print(f"{fn.split('/')[-1].split('.')[0]}: T2 trades {len(real)} {sum(real.values()):+.3f} | QUIET3-A blocks {len(v)} (winners {sum(x > 0 for x in v)} {sum(x for x in v if x > 0):+.3f}, "
          f"losers {sum(x <= 0 for x in v)} {sum(x for x in v if x <= 0):+.3f}) -> saves {-sum(v):+.3f}{f' = {-sum(v) / h * 24:+.2f}/day' if h > 1 else ''} | w/o its top 5 saves {-sum(s[5:]):+.3f} | no v2 data {na}")
