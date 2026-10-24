#!/usr/bin/env python3
# Fast-exit sweep summary (owner 10-24 ~22:00 PKT): sell after 2-19 slots (0.4-4 s) x stop-loss 5-20% / none, on the last ~19 h
# of recorded dumps the live model would pick (near leaders = Frankfurt list, wider tier, 0.55 SOL, +5% guard), real costs
# (+0.0035 SOL per fill, 0.0005 per blocked buy), engine limits (one position: busy for the hold + 0.3 s; 0.8 s after a block;
# 5 slots between picks on a token). Night = 10-23 19:26 -> 10-24 06:27, day = 10-24 08:04 -> 16:05 PKT.
import json, sys
D = "/home/moiz/sniper/ops/overnight/sel"; S = "/home/moiz/sniper/ops/dip/speed/leaders"; EXTRA, FAIL = 0.0035, 0.0005
sc = json.load(open(f"{S}/schedule_cur.json")); near = {l.strip() for l in open("/home/moiz/sniper/ops/region/near_leaders_fra.txt") if l.strip()}
def lead(s):
    i = s - sc["start"]; return sc["ids"][sc["slot_leader"][i]] if 0 <= i < len(sc["slot_leader"]) else None
W = {w: sorted(json.load(open(f"{D}/dayexit_{w}_fast.json"))["rows"], key=lambda o: o["t"]) for w in ("r3", "r7")}
for rows in W.values():
    for o in rows: o["near"] = lead(o["s"]) in near
CAPS = (2, 3, 4, 5, 6, 9, 19); SLS = ("5", "7p5", "10", "12p5", "15", "20", "none")
def nm(cap, sl): return f"tpnone_sl{sl}_{cap}sl"
def sim(rows, L, ex, cap):
    busy = -1.0; last = {}; tot = 0.0; n = won = 0
    for o in rows:
        if not o["near"] or o["t"] < busy: continue
        if o["m"] in last and o["s"] < last[o["m"]] + 5: continue
        last[o["m"]] = o["s"]
        v = o["ours"].get(f"{L}|0.55")
        if v is None: continue
        if v == "b": tot -= FAIL; busy = o["t"] + 0.8; continue
        p = v[ex] - EXTRA; tot += p; n += 1; won += p > 0; busy = o["t"] + cap * 0.212 + 0.3
    return tot, n, won
for L in (35, 50):
    print(f"\n--- landing {L} ms: SOL over ~19 h (night + day), by sell time and stop-loss")
    print("sell after        " + " ".join(f"{('SL ' + s.replace('p', '.') + '%') if s != 'none' else 'no SL':>9}" for s in SLS))
    best = None
    for cap in CAPS:
        cells = []
        for sl in SLS:
            a = sim(W["r3"], L, nm(cap, sl), cap); b = sim(W["r7"], L, nm(cap, sl), cap); t = a[0] + b[0]
            cells.append(t)
            if best is None or t > best[0]: best = (t, cap, sl, a, b)
        print(f"  {cap:2d} slots ({cap * 0.212:.1f} s) " + " ".join(f"{c:+9.2f}" for c in cells))
    t, cap, sl, a, b = best
    print(f"  best: {cap} slots ({cap * 0.212:.1f} s), SL {sl}: {t:+.2f} SOL ({a[1] + b[1]} fills, {a[2] + b[2]} won) | night {a[0]:+.2f} day {b[0]:+.2f}")
    for cap, sl in ((6, "10"), (19, "20")):
        a = sim(W["r3"], L, nm(cap, sl), cap); b = sim(W["r7"], L, nm(cap, sl), cap)
        print(f"  (live now) {cap} slots SL {sl}: {a[0] + b[0]:+.2f} SOL ({a[1] + b[1]} fills) | night {a[0]:+.2f} day {b[0]:+.2f}")
