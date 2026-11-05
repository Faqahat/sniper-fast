#!/usr/bin/env python3
"""TAIL t9: creator ledger from the SHADOW (every T2 trigger, traded or not): creator (from the live arm / skip record of the same
trigger: ann.creator) -> paper row c net, known 15 s after the trigger. Feature at signing: the creator's past paper sum / count /
worst, and the live ledger (realized P&L of our past positions on the creator's other mints)."""
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/tail")
import t8_robust as R
import t6_breaker as B
S = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/f3_tail"
cre = {}
for r in (39, 40, 41, 42):
    for l in open(f"{S}/r{r}live.jsonl"):
        if '"ann"' not in l or ('presend_live_arm' not in l and 'presend_live_skip' not in l): continue
        d = json.loads(l); tr = d.get("trig") or {}
        c = (d.get("ann") or {}).get("creator")
        if c and tr.get("mint"): cre[(tr["mint"], tr["slot"])] = c
ev = []
for r in (39, 40, 41, 42):
    arm = {}
    for l in open(f"{S}/shadow_r{r}.jsonl"):
        d = json.loads(l)
        if d["e"] == "a": arm[d["w"]] = d
        elif d["w"] in arm and d.get("net") is not None:
            a = arm[d["w"]]; c = cre.get((a["mint"], a["slot"]))
            if c: ev.append((a["t"] + 15e9, c[:8], a["mint"], d["net"]))
ev.sort()
print("shadow trades with creator", len(ev), "creators", len({e[1] for e in ev}))
j = 0; led = collections.defaultdict(list)
for r in R.rows:
    F = r["F"]; ts = F["_ts"]
    while j < len(ev) and ev[j][0] <= ts: led[ev[j][1]].append(ev[j]); j += 1
    c = (F.get("creator") or "")[:8]
    x = [e for e in led.get(c, []) if e[2] != r["mint"]]
    F["crp_sum"] = sum(e[3] for e in x); F["crp_n"] = len({e[2] for e in x}); F["crp_mean"] = F["crp_sum"] / len(x) if x else 0.0
for k, x in (("crp_sum", -0.05), ("crp_sum", -0.1), ("crp_sum", -0.2), ("crp_sum", -0.3)):
    R.rep(f"{k}<={x}", lambda F, r, k=k, x=x: F.get(k, 0) <= x)
for n in (2, 3, 5):
    for m in (-0.01, -0.02):
        R.rep(f"crp_n>={n} & crp_mean<={m}", lambda F, r, n=n, m=m: F.get("crp_n", 0) >= n and F.get("crp_mean", 0) <= m)
R.rep("live cr<=-0.1 OR crp_sum<=-0.2", lambda F, r: F["led_cr_pnl"] <= -0.1 or F.get("crp_sum", 0) <= -0.2)
