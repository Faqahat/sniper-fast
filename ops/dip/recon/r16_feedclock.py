#!/usr/bin/env python3
# r16: the engine's own feed clock (rx time of every trade it logged around our buys, "tape" records) for each fire:
# do the tape records cover every trade on the token between the dump and our landing? If yes, real-time what-ifs are possible
# (land X ms earlier on the feed clock = in front of every trade the feed showed in those X ms).
import sys, os, json, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib as R, rsim as S
P = json.load(open(f"{R.WORK}/pertrade.json"))
TPS = {tag: S.Tapes(tag) for tag in ("NEW", "OLD")}
# tape records + timing per fire (by mint and order)
tape = collections.defaultdict(list); timing = {}
for srv, rn, base in R.RUN_FILES:
    for l in open(f"{R.LIVE}/{base}.jsonl"):
        if '"tape"' in l[:60]:
            o = json.loads(l)
            if o.get("ev") == "tape": tape[(srv, o["mint"])].append(o)
F = json.load(open(f"{R.WORK}/fires.json"))
fr = {(r["srv"], r["mint"], r["dump_slot"]): r for r in F["rows"]}
cov = collections.Counter(); out = []
for o in P:
    r = fr[(o["srv"], o["mint"], o["dump_slot"])]
    tm = r.get("timing") or {}
    TP = TPS[o["tape"]]; t, j0 = TP.find(o["mint"], o["dump_slot"], o["dump_idx"], o.get("sell")); tp = TP.token(t)
    key_us = o["land_slot"] * 100000 + o["land_idx"]
    between = [x for x in range(j0 + 1, tp["n"]) if tp["SI"][x] < key_us and not tp["ours"][x]]
    tk = {(z["slot"], z["idx"]): z for z in tape[(o["srv"], o["mint"])] if z["t"] / 1e9 >= r["t_dump_rx"] - 1 and z["t"] / 1e9 <= r["t_dump_rx"] + 30}
    have = [x for x in between if (int(tp["s"][x]), int(tp["i"][x])) in tk]
    cov[("all covered" if len(have) == len(between) else ("none ahead" if not between else "partial"))] += 1
    # our own buy rx on the feed (fills: in the tape as our wallet; fails: timing.buy_first_rx)
    rx_us = tm.get("buy_first_rx")
    out.append(dict(srv=o["srv"], run=o["run"], mint=o["mint"], n_between=len(between), n_have=len(have), rx_us=rx_us, t_dump_rx=r["t_dump_rx"],
                    dump_first_rx=tm.get("dump_first_rx"), fire_to_seen=tm.get("fire_to_seen_ms")))
print("tape coverage of the trades between the dump and our landing:", dict(cov))
nb = np.array([x["n_between"] for x in out]); nh = np.array([x["n_have"] for x in out])
print(f"trades between dump and us: total {nb.sum()}, logged by the engine with a feed time {nh.sum()} ({100 * nh.sum() / max(1, nb.sum()):.0f}%)")
print("fires with our own buy rx time:", sum(1 for x in out if x["rx_us"]))
