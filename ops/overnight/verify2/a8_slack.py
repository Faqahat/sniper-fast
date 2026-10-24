#!/usr/bin/env python3
"""verify2 / a8: how much price move do follower buyers tolerate? Slack of each decoded limit (slip_args.jsonl) at its own fill:
sol-kind: tokens_out/min_tokens - 1 ; tok-kind: max_sol/(cost incl. fees) - 1. By slot offset from the create (picks' launches
and all launches). Used to bound the effect of the ~70% of follower buys (2-8 s after us) whose limits were never fetched."""
import sys, os, json, gzip, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v2core as V
SLIP, kinds = V.load_slip()
# slot offsets: use launches.jsonl slots + the picks' extracted trades (for picks) ; for other mints use phase-less approach: only picks
P = V.load_picks(); L = V.load_launches(P); X = V.load_x1()
rows = []
for m in P:
    M = V.Mint(m, L[m], X.get(m, []), repair=False)
    for t in M.trades:
        lim = SLIP.get(t["sig"])
        if not lim or not t["buy"] or lim.get("kind") not in ("sol", "tok") or lim.get("tok") != t["tok"]: continue
        fr = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
        if lim["kind"] == "sol": slack = t["tok"] / lim["a2"] - 1 if lim["a2"] else 9.9
        else: slack = lim["a2"] / (t["sol"] * (1 + fr)) - 1
        rows.append((t["s"] - M.S, slack, t["sol"] / 1e9))
def q(v, p): v = sorted(v); return v[min(len(v) - 1, int(p * len(v)))]
by = collections.defaultdict(list)
for d, s, sol in rows: by["0-1" if d <= 1 else ("2-5" if d <= 5 else ("6-10" if d <= 10 else "11+"))].append(s)
print("decoded follower limits on the 238 picks:", len(rows))
for k in ("0-1", "2-5", "6-10", "11+"):
    v = by[k]
    if not v: continue
    print(f"  slots after create {k:5s}: n {len(v):4d} | slack p10 {q(v, .1):.3f} p25 {q(v, .25):.3f} p50 {q(v, .5):.3f} | share with slack < 1.5% {sum(1 for x in v if x < .015) / len(v):.2f}, < 3% {sum(1 for x in v if x < .03) / len(v):.2f}, < 5% {sum(1 for x in v if x < .05) / len(v):.2f}")
json.dump(dict(rows=rows), open(os.path.join(V.WORK, "a8_slack.json"), "w"))
