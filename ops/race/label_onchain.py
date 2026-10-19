#!/usr/bin/env python3
# READ-ONLY. Race labels for on-chain records from onchain.py; prints a per-launch table + summary.
# usage: label_onchain.py <onchain.jsonl> [tag]
import sys, json, statistics as st
sys.path.insert(0, "/root/race")
from race_lib import labels

pros = frozenset(json.load(open("/root/race/pros.json")))
rows = []
for l in open(sys.argv[1]):
    r = json.loads(l)
    b, s = r.get("b") or {}, r.get("s") or {}
    if "csig" not in b or not s or "sig_err" in s:
        continue
    o = labels(b, s, pros)
    o.update(mint=r["mint"], slot=r["slot"], glued=b.get("glued", 0), gsol=(b.get("gsol") or 0) / 1e9, dev=b.get("dev", 0) / 1e9,
             ins="+".join(x for x in b.get("ins") or [] if x.startswith("Buy")) or "none", host=(b.get("uri") or "").split("://")[-1].split("/")[0])
    rows.append(o)
print(f"{'mint':10} {'dev':>5} {'dev ix':14} {'bundle':>7} {'outS':>4} {'outS1':>5} {'out01':>5} {'2s n':>4} {'2s SOL':>6} host")
for o in rows:
    print(f"{o['mint'][:10]} {o['dev']:5.2f} {o['ins'][:14]:14} {o['glued']:2}/{o['gsol']:4.1f} {o['outS_n']:4} {o['outS1_n']:5} {o['out01_n']:5} {o['out2s_n']:4} {o['out2s_sol']:6.2f} {o['host'][:28]}")
n = len(rows)
if n:
    print(f"\nn={n} | S+S1 >=2 outsiders (RACE): {sum(o['out01_n'] >= 2 for o in rows)} ({sum(o['out01_n'] >= 2 for o in rows) / n:.0%}) | >=1 outsider in S: "
          f"{sum(o['outS_n'] >= 1 for o in rows)} | S+S1 >=3: {sum(o['out01_n'] >= 3 for o in rows)} | 2s outside SOL >=1: {sum(o['out2s_sol'] >= 1 for o in rows)} | "
          f"median out01 {st.median(o['out01_n'] for o in rows)} | 4yFAz bought {sum(any(o['outS_his']) for o in rows)}")
