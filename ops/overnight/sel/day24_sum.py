#!/usr/bin/env python3
# Summary of day24.py (owner 10-24 06:30 PKT: the last 24 h replayed with the run-5 settings). Rules, in time order over both
# windows, with the engine's limits: one open position (busy 1.6 s after a filled buy, 0.8 s after a blocked one), 5 slots
# between picks on a token. Costs: the replay's P&L has the pump fees + 0.0016 SOL of tx costs; our real round trip costs
# ~0.0035 SOL more (tips 0.0022, priorities, the sell tip) -> charged per fill; a blocked buy costs 0.0005.
# usage: python3 -I day24_sum.py
import json, collections, datetime as dt
D = "/home/moiz/sniper/ops/overnight/sel"; EXTRA = 0.0035; FAIL = 0.0005
TH = json.load(open(f"{D}/IMIT1.json"))["thresholds"]
W = [json.load(open(f"{D}/day24_{w}.json")) for w in ("r2", "r3")]
rows = sorted([o for w in W for o in w["rows"]], key=lambda o: o["t"])
hours = sum((w["t1"] - w["t0"]) / 3600 for w in W)
PKT = dt.timezone(dt.timedelta(hours=5))
RULES = {
    "runs 1-4 (strict 0.35, TP +5%)": lambda o: (0.35, "tp5_sl10_1.3s") if o["score"] >= TH["top2"] else None,
    "no TP, sell 1.3 s (strict 0.35)": lambda o: (0.35, "tpnone_sl10_1.3s") if o["score"] >= TH["top2"] else None,
    "run 5 = no TP + dev tier 0.75": lambda o: ((0.75, "tpnone_sl10_1.3s") if o["dev"] and o["score"] >= TH["top4"] else
                                               (0.35, "tpnone_sl10_1.3s") if o["score"] >= TH["top2"] else None),
    # owner 10-24 06:40: "and with 1 sol size" -> the dev tier at 1 SOL; and every trade at 1 SOL
    "run 5, dev tier at 1 SOL": lambda o: ((1.0, "tpnone_sl10_1.3s") if o["dev"] and o["score"] >= TH["top4"] else
                                          (0.35, "tpnone_sl10_1.3s") if o["score"] >= TH["top2"] else None),
    "run 5, everything at 1 SOL": lambda o: ((1.0, "tpnone_sl10_1.3s") if (o["dev"] and o["score"] >= TH["top4"]) or o["score"] >= TH["top2"] else None),
    # owner 10-24 06:50: "also replay assuming we sell after 2.5 s no tp" (2.5 s = 12 slots of 212 ms; the position is busy 2.8 s)
    "run 5 but sell at 2.5 s": lambda o: ((0.75, "tpnone_sl10_2.5s") if o["dev"] and o["score"] >= TH["top4"] else
                                         (0.35, "tpnone_sl10_2.5s") if o["score"] >= TH["top2"] else None),
    "run 5 but 2.5 s, no stop-loss": lambda o: ((0.75, "tpnone_slnone_2.5s") if o["dev"] and o["score"] >= TH["top4"] else
                                               (0.35, "tpnone_slnone_2.5s") if o["score"] >= TH["top2"] else None),
}
def sim(rule, L, sel=lambda o: True):
    busy_until = -1.0; last_pick = {}; tot = 0.0; fills = wins = blocked = 0; per = collections.Counter(); dev_part = 0.0
    for o in rows:
        if not sel(o): continue
        r = rule(o)
        if r is None: continue
        size, ex = r
        if o["t"] < busy_until: continue
        if o["m"] in last_pick and o["s"] < last_pick[o["m"]] + 5: continue
        last_pick[o["m"]] = o["s"]
        v = o["ours"].get(f"{L}|{size}")
        if v is None: continue
        if v == "b": tot -= FAIL; blocked += 1; busy_until = o["t"] + 0.8; continue
        p = v[ex] - EXTRA; tot += p; fills += 1; wins += p > 0; busy_until = o["t"] + (2.8 if "2.5s" in ex else 1.6)
        per["day (06:30-18:33)" if o["t"] < W[0]["t1"] + 1 else "night (19:26-06:27)"] += p
        if o["dev"]: dev_part += p
    return tot, fills, wins, blocked, per, dev_part
print(f"last 24 h replay: {len(rows)} candidate dumps over {hours:.1f} h recorded (10-23 06:30 -> 10-24 06:27 PKT; 18:33-19:26 not recorded)")
print(f"candidates on this dev's tokens: {sum(1 for o in rows if o['dev'])}; costs: real tips/fees per fill, 0.0005 per blocked buy\n")
for L in sorted({int(k.split("|")[0]) for o in rows for k in o["ours"]}):
    print(f"--- landing {L} ms after the dump")
    for name, rule in RULES.items():
        tot, f, w, b, per, devp = sim(rule, L)
        print(f"  {name:34s} {tot:+8.3f} SOL | {f:3d} fills ({w} won) {b:3d} blocked | " + " | ".join(f"{k} {v:+.3f}" for k, v in per.items())
              + (f" | of it this dev {devp:+.3f}" if "dev" in name else ""))
