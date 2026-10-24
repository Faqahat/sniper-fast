#!/usr/bin/env python3
# Owner 10-24 15:40 PKT: "for this run [7] if we had wider tier, how would it have gone?" Run 7's hours (08:04 -> 16:05 PKT),
# near leaders only (the dump slot's leader in near_leaders_5ms, from the epoch's leader schedule), 0.5 SOL (0.75 on the dev's
# tokens), exit no TP / SL -10% / 1.3 s, real costs (+0.0035 SOL per fill over the replay's tx costs, 0.0005 per blocked buy),
# engine limits (one open position: busy 1.6 s after a fill, 0.8 s after a blocked buy; 5 slots between picks on a token).
# A = run 7 as set (others strict); B = wider tier on every token. Compared at 35 / 50 / 75 ms with the live result.
import json, collections
D = "/home/moiz/sniper/ops/overnight/sel"; S = "/home/moiz/sniper/ops/dip/speed/leaders"
EXTRA, FAIL, EX = 0.0035, 0.0005, "tpnone_sl10_1.3s"
TH = json.load(open(f"{D}/IMIT1.json"))["thresholds"]
rows = sorted(json.load(open(f"{D}/run7w_r7.json"))["rows"], key=lambda o: o["t"])
sc = json.load(open(f"{S}/schedule_cur.json")); near = {l.strip() for l in open(f"{S}/close_leaders_5ms.txt") if l.strip()}
def leader(slot):
    i = slot - sc["start"]
    return sc["ids"][sc["slot_leader"][i]] if 0 <= i < len(sc["slot_leader"]) else None
for o in rows: o["near"] = leader(o["s"]) in near
RULES = {"A run 7 as set (others strict)": lambda o: (0.75 if o["dev"] else 0.5) if o["score"] >= (TH["top4"] if o["dev"] else TH["top2"]) else None,
         "B wider tier on every token": lambda o: (0.75 if o["dev"] else 0.5) if o["score"] >= TH["top4"] else None}
def sim(L, rule, only=None):
    busy = -1.0; last = {}; tot = 0.0; n = w = nb = 0; extra = 0.0
    for o in rows:
        if not o["near"]: continue
        size = rule(o)
        if size is None or o["t"] < busy: continue
        if o["m"] in last and o["s"] < last[o["m"]] + 5: continue
        last[o["m"]] = o["s"]
        v = o["ours"].get(f"{L}|{size}")
        if v is None: continue
        wider_only = (not o["dev"]) and o["score"] < TH["top2"]
        if v == "b": tot -= FAIL; nb += 1; busy = o["t"] + 0.8; extra -= FAIL if wider_only else 0; continue
        p = v[EX] - EXTRA; tot += p; n += 1; w += p > 0; busy = o["t"] + 1.6
        if wider_only: extra += p
    return tot, n, w, nb, extra
print(f"run 7 window: {len(rows)} dumps with score >= wider (any token); on near leaders {sum(o['near'] for o in rows)} "
      f"(strict {sum(1 for o in rows if o['near'] and o['score'] >= TH['top2'])}, wider-only {sum(1 for o in rows if o['near'] and o['score'] < TH['top2'])})")
print("LIVE run 7 (chain): 9 fills, 6 won, +0.2366 SOL (18 fires on near leaders)")
for L in sorted({int(k.split('|')[0]) for o in rows for k in o["ours"]}):
    print(f"--- landing {L} ms after the dump")
    for name, rule in RULES.items():
        t, n, w, nb, ex = sim(L, rule)
        print(f"  {name:32s} {t:+.3f} SOL | {n:2d} fills ({w} won) {nb:2d} blocked" + (f" | of it the wider-only picks {ex:+.3f}" if name.startswith("B") else ""))
