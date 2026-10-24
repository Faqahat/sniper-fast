#!/usr/bin/env python3
# Guard (slippage tolerance) retest with the CURRENT setup (owner 10-24 18:00): near leaders only (Frankfurt list, epoch 1066
# schedule), wider tier, 0.55 SOL, exit no TP / SL -10% / 1.3 s, real costs (+0.0035 SOL per fill, 0.0005 per blocked buy), engine
# limits (one position: busy 1.6 s after a fill, 0.8 s after a block; 5 slots between picks on a token). Windows: 10-23 19:26 ->
# 10-24 06:27 (night) and 10-24 08:04 -> 16:05 (run 7's hours). Each pick's entry price ratio comes from dayguard.py.
import json, collections
D = "/home/moiz/sniper/ops/overnight/sel"; S = "/home/moiz/sniper/ops/dip/speed/leaders"; EX = "tpnone_sl10_1.3s"; EXTRA, FAIL = 0.0035, 0.0005
sc = json.load(open(f"{S}/schedule_cur.json")); near = {l.strip() for l in open("/home/moiz/sniper/ops/region/near_leaders_fra.txt") if l.strip()}
def lead(s):
    i = s - sc["start"]; return sc["ids"][sc["slot_leader"][i]] if 0 <= i < len(sc["slot_leader"]) else None
W = {w: json.load(open(f"{D}/dayguard_{w}.json")) for w in ("r3", "r7")}
for w in W.values():
    for o in w["rows"]: o["near"] = lead(o["s"]) in near
GUARDS = (1.05, 1.075, 1.10, 1.15, 1.20)
def sim(rows, L, g):
    busy = -1.0; last = {}; tot = 0.0; n = nb = won = 0; prem = []
    for o in sorted(rows, key=lambda o: o["t"]):
        if not o["near"] or o["t"] < busy: continue
        if o["m"] in last and o["s"] < last[o["m"]] + 5: continue
        last[o["m"]] = o["s"]
        v = o["ours"].get(f"{L}|0.55")
        if not isinstance(v, dict): continue
        if v["ratio"] > g: tot -= FAIL; nb += 1; busy = o["t"] + 0.8; continue
        p = v[EX] - EXTRA; tot += p; n += 1; won += p > 0; busy = o["t"] + 1.6; prem.append(v["ratio"])
    return tot, n, won, nb
for L in (35, 50):
    print(f"--- landing {L} ms after the dump (near leaders, wider tier, 0.55 SOL, sell at 1.3 s)")
    for g in GUARDS:
        parts = [sim(W[w]["rows"], L, g) for w in ("r3", "r7")]
        t = sum(p[0] for p in parts); n = sum(p[1] for p in parts); won = sum(p[2] for p in parts); nb = sum(p[3] for p in parts)
        print(f"  guard +{100 * (g - 1):4.1f}%: {t:+.3f} SOL | {n:3d} fills ({won} won) {nb:3d} blocked | night {parts[0][0]:+.3f}, day {parts[1][0]:+.3f} | per fill {t / max(1, n):+.4f}")
# the extra fills a wider guard adds: entry premium bucket -> their P&L
print("\nfills by how much above the post-dump price we would enter (each pick on its own, 35 ms):")
B = collections.defaultdict(list)
for w in W.values():
    for o in w["rows"]:
        v = o["ours"].get("35|0.55")
        if o["near"] and isinstance(v, dict):
            r = v["ratio"]; k = "<=5%" if r <= 1.05 else "5-7.5%" if r <= 1.075 else "7.5-10%" if r <= 1.10 else "10-15%" if r <= 1.15 else "15-20%" if r <= 1.20 else ">20%"
            B[k].append(v[EX] - EXTRA)
for k in ("<=5%", "5-7.5%", "7.5-10%", "10-15%", "15-20%", ">20%"):
    v = B.get(k, [])
    if v: print(f"  {k:8s}: {len(v):3d} picks, {sum(v):+.3f} SOL, {sum(1 for x in v if x > 0)} won, per pick {sum(v) / len(v):+.4f}")
