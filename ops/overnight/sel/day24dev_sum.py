#!/usr/bin/env python3
# Owner 10-24 06:50 PKT: "bwam creates multiple tokens, most get filtered out. what if we had considered all his tokens?"
# Every dump on the dev's tokens over the last 24 h (day24dev.py), at 0.75 SOL, exit no TP / SL -10% / 1.3 s, real costs
# (+0.0035 SOL per fill over the replay's tx costs, 0.0005 per blocked buy): (1) by how the model scored it, each dump on its own;
# (2) the whole day with the engine's limits (one open position, 5 slots between picks on a token), other tokens strict at 0.35
# (day24_<win>.json): run 5 as set vs + every in-envelope dump of the dev vs + every dump of the dev.
import json, collections
D = "/home/moiz/sniper/ops/overnight/sel"; EXTRA, FAIL = 0.0035, 0.0005; EX = "tpnone_sl10_1.3s"
TH = json.load(open(f"{D}/IMIT1.json"))["thresholds"]
dev = sorted([o for w in ("r2", "r3") for o in json.load(open(f"{D}/day24dev_{w}.json"))["rows"]], key=lambda o: o["t"])
oth = [o for w in ("r2", "r3") for o in json.load(open(f"{D}/day24_{w}.json"))["rows"] if not o["dev"] and o["score"] >= TH["top2"]]
def bucket(o):
    if not o["env"]: return "outside the watch envelope"
    return ("strict" if o["score"] >= TH["top2"] else "wider" if o["score"] >= TH["top4"] else "top8" if o["score"] >= TH["top8"] else "below top8")
LATS = sorted({int(k.split("|")[0]) for o in dev for k in o["ours"]})
print(f"the dev's tokens, last 24 h: {len(dev)} dumps (>= 1 SOL sells after the launch, age 1-1800 s) on {len({o['m'] for o in dev})} tokens")
print("\n(1) each dump on its own, 0.75 SOL, no TP / 1.3 s  [P&L SOL (fills / blocked)]")
B = ["strict", "wider", "top8", "below top8", "outside the watch envelope"]
for L in LATS:
    row = []
    for b in B:
        v = [o["ours"].get(f"{L}|0.75") for o in dev if bucket(o) == b]
        f = [x[EX] - EXTRA for x in v if isinstance(x, dict)]; nb = sum(1 for x in v if x == "b")
        row.append(f"{b} {sum(f) - FAIL * nb:+.2f} ({len(f)}/{nb})")
    print(f"  {L:>3} ms: " + " | ".join(row))
print("  dumps per bucket: " + " | ".join(f"{b} {sum(1 for o in dev if bucket(o) == b)}" for b in B))
def sim(L, dev_ok):
    ev = sorted([("o", o) for o in oth] + [("d", o) for o in dev if dev_ok(o)], key=lambda x: x[1]["t"])
    busy = -1.0; last = {}; tot = 0.0; n = nb = 0; dpart = 0.0
    for kind, o in ev:
        if o["t"] < busy: continue
        if o["m"] in last and o["s"] < last[o["m"]] + 5: continue
        last[o["m"]] = o["s"]
        v = o["ours"].get(f"{L}|{0.75 if kind == 'd' else 0.35}")
        if v is None: continue
        if v == "b": tot -= FAIL; nb += 1; busy = o["t"] + 0.8; continue
        p = v[EX] - EXTRA; tot += p; n += 1; busy = o["t"] + 1.6
        if kind == "d": dpart += p
    return tot, n, nb, dpart
print("\n(2) the whole day (engine limits; other tokens strict at 0.35)  [SOL (fills / blocked), of it the dev's tokens]")
RULES = {"run 5 as set (dev: wider and up)": lambda o: o["env"] and o["score"] >= TH["top4"],
         "+ every in-envelope dump of the dev": lambda o: o["env"],
         "+ every dump of the dev": lambda o: True}
for L in LATS:
    print(f"  {L:>3} ms: " + " | ".join(f"{k} {t:+.2f} ({n}/{nb}; dev {dp:+.2f})" for k, (t, n, nb, dp) in ((k, sim(L, r)) for k, r in RULES.items())))
