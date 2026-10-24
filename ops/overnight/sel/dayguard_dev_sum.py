#!/usr/bin/env python3
# Dev-only wider guard (owner 10-24 18:50 PKT, red failed buys): same replay rows and rules as dayguard_sum.py (near leaders,
# wider tier, 0.55 SOL, no TP / SL -10% / 1.3 s, real costs, engine limits), but the guard is split: non-dev tokens keep +5%,
# dev-list tokens get G. Plus the entry-premium buckets for dev vs non-dev picks.
import json, collections
D = "/home/moiz/sniper/ops/overnight/sel"; S = "/home/moiz/sniper/ops/dip/speed/leaders"; EX = "tpnone_sl10_1.3s"; EXTRA, FAIL = 0.0035, 0.0005
sc = json.load(open(f"{S}/schedule_cur.json")); near = {l.strip() for l in open("/home/moiz/sniper/ops/region/near_leaders_fra.txt") if l.strip()}
def lead(s):
    i = s - sc["start"]; return sc["ids"][sc["slot_leader"][i]] if 0 <= i < len(sc["slot_leader"]) else None
W = {w: json.load(open(f"{D}/dayguard_{w}.json")) for w in ("r3", "r7")}
for w in W.values():
    for o in w["rows"]: o["near"] = lead(o["s"]) in near
def sim(rows, L, gdev, gnon=1.05):
    busy = -1.0; last = {}; out = collections.Counter()
    for o in sorted(rows, key=lambda o: o["t"]):
        if not o["near"] or o["t"] < busy: continue
        if o["m"] in last and o["s"] < last[o["m"]] + 5: continue
        last[o["m"]] = o["s"]
        v = o["ours"].get(f"{L}|0.55")
        if not isinstance(v, dict): continue
        k = "dev" if o["dev"] else "non"; g = gdev if o["dev"] else gnon
        if v["ratio"] > g: out[k + "_sol"] -= FAIL; out[k + "_blk"] += 1; busy = o["t"] + 0.8; continue
        p = v[EX] - EXTRA; out[k + "_sol"] += p; out[k + "_n"] += 1; out[k + "_won"] += p > 0; busy = o["t"] + 1.6
    return out
for L in (35, 50):
    print(f"--- landing {L} ms (non-dev guard stays +5%)")
    for g in (1.05, 1.075, 1.10, 1.15, 1.20):
        a = sim(W["r3"]["rows"], L, g); b = sim(W["r7"]["rows"], L, g); t = a + b
        print(f"  dev guard +{100 * (g - 1):4.1f}%: dev {t['dev_sol']:+.3f} SOL ({t['dev_n']} fills, {t['dev_won']} won, {t['dev_blk']} blocked)"
              f" | non-dev {t['non_sol']:+.3f} | total {t['dev_sol'] + t['non_sol']:+.3f}")
print("\nentry above the post-dump price, each pick on its own (35 ms):")
for dev in (True, False):
    B = collections.defaultdict(list)
    for w in W.values():
        for o in w["rows"]:
            v = o["ours"].get("35|0.55")
            if o["near"] and o["dev"] == dev and isinstance(v, dict):
                r = v["ratio"]; k = "<=5%" if r <= 1.05 else "5-10%" if r <= 1.10 else "10-20%" if r <= 1.20 else ">20%"
                B[k].append(v[EX] - EXTRA)
    print(" ", "dev-list" if dev else "other   ", " | ".join(f"{k}: {len(B[k])} picks {sum(B[k]):+.3f}" for k in ("<=5%", "5-10%", "10-20%", ">20%") if B.get(k)))
