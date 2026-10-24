#!/usr/bin/env python3
# Shadow engine vs the host paper run, same hours: picks matched on (mint, token age at the dump). Reports matched, shadow-only,
# paper-only, and for matched picks the score difference (live features vs batch features). Read-only (the shadow log is
# copied from the server first).   usage: python3 -I compare_shadow.py shadow.jsonl [paper live_trades.jsonl]
import sys, json, time, collections
S = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
P = [json.loads(l) for l in open(sys.argv[2] if len(sys.argv) > 2 else "/home/moiz/sniper/ops/overnight/sel/live_trades.jsonl")]
start = next(r["t"] for r in S if r["ev"] == "run_start") / 1e9
picks = [r for r in S if r["ev"] == "pick"]; dumps = [r for r in S if r["ev"] == "dump"]
t_last = max([r["t"] / 1e9 for r in dumps] or [start])
# the paper's picks of tokens the shadow could follow: created after the shadow started (launch time = pick time - age), up to its last dump
pp = [r for r in P if r["t"] - r["age"] >= start + 2 and r["t"] <= t_last - 30]
sp = {(r["mint"], round(r["age"], 2)): r for r in picks if r["t"] / 1e9 <= t_last - 30}
pk = {(r["m"], round(r["age"], 2)): r for r in pp}
both = sp.keys() & pk.keys()
print(f"shadow running {(t_last - start) / 60:.0f} min ({time.strftime('%H:%M', time.gmtime(start + 18000))}-{time.strftime('%H:%M', time.gmtime(t_last + 18000))} PKT): shadow picks {len(sp)}, paper picks {len(pk)}, matched {len(both)}")
print(f"  shadow only {len(sp.keys() - pk.keys())}, paper only {len(pk.keys() - sp.keys())}")
d = [sp[k]["score"] - pk[k]["score"] for k in both]
if d: print(f"  matched picks: score difference shadow - paper: median {sorted(d)[len(d) // 2]:+.4f}, max |diff| {max(abs(x) for x in d):.4f}")
# for misses, is the dump in the shadow's dump log at all (seen, scored lower) or not seen?
sd = {(r["mint"], round(r["age"], 2)): r for r in dumps}
for k in list(pk.keys() - sp.keys())[:8]:
    r = sd.get(k); print(f"  paper-only {k[0][:8]} age {k[1]}: paper score {pk[k]['score']:.3f} | shadow " + (f"saw it, score {r['score']:.3f} pass {r['pass']}" if r else "never saw this dump (outside envelope or missed)"))
for k in list(sp.keys() - pk.keys())[:5]:
    print(f"  shadow-only {k[0][:8]} age {k[1]}: shadow score {sp[k]['score']:.3f}")
