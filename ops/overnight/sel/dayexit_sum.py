#!/usr/bin/env python3
# Exit retune with the CURRENT setup (owner 10-24 18:05: "what about hold time and tp"): near leaders (Frankfurt list, epoch
# 1066), wider tier, 0.55 SOL, guard +5%, real costs (+0.0035 per fill, 0.0005 per block), engine limits (one position: busy
# for the hold + 0.3 s after a fill, 0.8 s after a block; 5 slots between picks on a token). All 192 exits, night + run-7 day.
import json, collections, sys
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import live_exits as LE
D = "/home/moiz/sniper/ops/overnight/sel"; S = "/home/moiz/sniper/ops/dip/speed/leaders"; EXTRA, FAIL = 0.0035, 0.0005
sc = json.load(open(f"{S}/schedule_cur.json")); near = {l.strip() for l in open("/home/moiz/sniper/ops/region/near_leaders_fra.txt") if l.strip()}
def lead(s):
    i = s - sc["start"]; return sc["ids"][sc["slot_leader"][i]] if 0 <= i < len(sc["slot_leader"]) else None
import os
SZ = os.environ.get("DAY_SIZE", "0.55"); TAG = os.environ.get("DAY_TAG", "")
W = {w: sorted(json.load(open(f"{D}/dayexit_{w}{TAG}.json"))["rows"], key=lambda o: o["t"]) for w in ("r3", "r7")}
for rows in W.values():
    for o in rows: o["near"] = lead(o["s"]) in near
CAP = {e[0]: e[3] for e in LE.EXITS}
def sim(rows, L, ex):
    busy = -1.0; last = {}; tot = 0.0; n = won = 0
    for o in rows:
        if not o["near"] or o["t"] < busy: continue
        if o["m"] in last and o["s"] < last[o["m"]] + 5: continue
        last[o["m"]] = o["s"]
        v = o["ours"].get(f"{L}|{SZ}")
        if v is None: continue
        if v == "b": tot -= FAIL; busy = o["t"] + 0.8; continue
        p = v[ex] - EXTRA; tot += p; n += 1; won += p > 0; busy = o["t"] + CAP[ex] * 0.212 + 0.3
    return tot, n, won
for L in (35, 50):
    res = {}
    for nm, *_ in LE.EXITS:
        a = sim(W["r3"], L, nm); b = sim(W["r7"], L, nm); res[nm] = (a[0] + b[0], a[1] + b[1], a[2] + b[2], a[0], b[0])
    top = sorted(res, key=lambda k: -res[k][0])
    print(f"--- landing {L} ms: current exit (no TP / SL -10% / 1.3 s) {res['tpnone_sl10_1.3s'][0]:+.3f} SOL, rank {top.index('tpnone_sl10_1.3s') + 1}/192")
    for k in top[:10]:
        t, n, w, ni, da = res[k]
        print(f"   {LE.label(k):34s} {t:+.3f} SOL | {n:3d} fills ({w} won) | night {ni:+.3f}  day {da:+.3f}")
    for k in ("tp5_sl10_1.3s", "tp10_sl10_1.3s", "tpnone_slnone_1.3s", "tpnone_sl10_2s", "tpnone_sl10_4s", "tpnone_sl10_6s"):
        if k in res: t, n, w, ni, da = res[k]; print(f"   (ref) {LE.label(k):28s} {t:+.3f} SOL | night {ni:+.3f}  day {da:+.3f}")
