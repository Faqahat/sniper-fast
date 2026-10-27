#!/usr/bin/env python3
# r17: REAL-TIME speed what-ifs on the 309 live fires, using the engine's own feed clock (rx time of every trade on the token
# between the dump and our landing: 1041 of 1041 logged). "X ms faster" = our buy lands in front of every trade on the token
# that our feed showed in the last X ms before our own buy (same feed, same clock: MEASURED order, replayed outcome).
# The corrected model (r13) values each case. Also: feed-time of our landing vs the first rival buy.
import sys, os, json, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib as R, rsim as S
from r13_corrected import outcome

if __name__ == "__main__":
    P = json.load(open(f"{R.WORK}/pertrade.json")); F = json.load(open(f"{R.WORK}/fires.json"))
    runs = {(r["srv"], r["run"]): r for r in F["runs"]}; fr = {(r["srv"], r["mint"], r["dump_slot"]): r for r in F["rows"]}
    TPS = {tag: S.Tapes(tag) for tag in ("NEW", "OLD")}
    tape = collections.defaultdict(dict)
    for srv, rn, base in R.RUN_FILES:
        for l in open(f"{R.LIVE}/{base}.jsonl"):
            if '"tape"' in l[:60]:
                o = json.loads(l)
                if o.get("ev") == "tape": tape[(srv, o["mint"])][(o["slot"], o["idx"])] = o["t"]
    cost = {}; fcost = {}
    for k in runs:
        fl = [o for o in P if (o["srv"], o["run"]) == k and o["live_fill"] and o.get("buy_txcost") is not None]
        fa = [o for o in P if (o["srv"], o["run"]) == k and not o["live_fill"]]
        cost[k] = float(np.mean([o["buy_txcost"] + o["sell_txcost"] for o in fl])) if fl else 0.0031
        fcost[k] = float(np.mean([-o["chain_pnl"] for o in fa])) if fa else 0.000505
    XS = (0, 2, 5, 10, 15, 20, 30, 40, 50, 75, 100, 10 ** 6)
    tot = collections.defaultdict(float); fills = collections.Counter(); per = []
    feed_us = []; feed_first = []; n_ahead = []; mono_bad = 0
    for o in P:
        k = (o["srv"], o["run"]); cfg = runs[k]["cfg"]; sl = cfg["sl"] if cfg["sl"] < 0.5 else None
        r = fr[(o["srv"], o["mint"], o["dump_slot"])]; tm = r["timing"]
        # one clock = the EXECUTED feed (the tape records' rx time): dump = dump_exec_rx; our buy = its tape time (fills) or
        # first-feed sighting + this fire's executed-feed lag, never before the last trade that landed ahead of us (fails)
        t0 = (tm.get("dump_exec_rx") or r["t_dump_rx"] * 1e9) / 1e6          # ms
        TP = TPS[o["tape"]]; t, j0 = TP.find(o["mint"], o["dump_slot"], o["dump_idx"], o.get("sell")); tp = TP.token(t)
        key_us = o["land_slot"] * 100000 + o["land_idx"]
        btw = [x for x in range(j0 + 1, tp["n"]) if tp["SI"][x] < key_us and not tp["ours"][x]]
        rx = [tape[(o["srv"], o["mint"])].get((int(tp["s"][x]), int(tp["i"][x]))) for x in btw]
        rx = [v / 1e6 if v else None for v in rx]
        own = tape[(o["srv"], o["mint"])].get((o["land_slot"], o["land_idx"]))
        if o["live_fill"] and own: rx_us = own / 1e6
        else:
            lag = ((tm.get("dump_exec_rx") or 0) - (tm.get("dump_first_rx") or 0)) / 1e6 if tm.get("dump_first_rx") else 1.3
            rx_us = tm["buy_first_rx"] / 1e6 + max(0.0, lag)
            last = max([v for v in rx if v is not None], default=None)
            if last is not None: rx_us = max(rx_us, last + 0.001)
        prev = -1e18
        for v in rx:
            if v is not None and v < prev - 0.001: mono_bad += 1
            if v is not None: prev = v
        feed_us.append(rx_us - t0); n_ahead.append(len(btw))
        fb = [rx[n] for n, x in enumerate(btw) if tp["buy"][x] and rx[n] is not None]
        feed_first.append((fb[0] - t0) if fb else None)
        row = dict(srv=o["srv"], run=o["run"], mint=o["mint"], feed_ms=rx_us - t0, ahead=len(btw), live=o["chain_pnl"], v={})
        for X in XS:
            thr = rx_us - X
            pos = None
            for n, x in enumerate(btw):
                if rx[n] is not None and rx[n] >= thr:
                    pos = (int(tp["s"][x]), int(tp["i"][x])); break
            if X == 0: pos = None
            if X >= 10 ** 6: pos = None if not btw else (int(tp["s"][btw[0]]), int(tp["i"][btw[0]]))
            at = pos if pos is not None else (o["land_slot"], o["land_idx"])
            oc = outcome(S.run_path(tp, j0, o["size"], at=at), cfg["hold_slots"], sl, cost[k], fcost[k])
            tot[X] += oc["pnl"]; fills[X] += oc["st"] == 0; row["v"][X] = oc["pnl"]
        per.append(row)
    print(f"feed order check: {mono_bad} trades out of chain order on the feed clock")
    fu = np.array(feed_us); ff = np.array([x for x in feed_first if x is not None])
    print(f"our buy seen on our feed after the dump (ms): p25 {np.percentile(fu, 25):.0f} median {np.median(fu):.0f} p75 {np.percentile(fu, 75):.0f} p90 {np.percentile(fu, 90):.0f}")
    print(f"first rival buy seen after the dump, fires where one landed before us ({len(ff)} of {len(fu)}): p25 {np.percentile(ff, 25):.0f} median {np.median(ff):.0f} p75 {np.percentile(ff, 75):.0f}")
    print(f"trades on the token between the dump and us: median {np.median(n_ahead):.0f}, mean {np.mean(n_ahead):.1f}, zero for {np.mean(np.array(n_ahead) == 0) * 100:.0f}% of fires")
    live = sum(o["chain_pnl"] for o in P)
    print(f"\nREAL-TIME what-if on the same 309 fires (corrected model; live = {live:+.3f}):")
    for X in XS:
        nm = "in front of everyone (right after the dump)" if X >= 10 ** 6 else f"{X} ms faster on our feed clock"
        print(f"   {nm:46s} {tot[X]:+7.3f} SOL  fills {fills[X]}/{len(P)}")
    json.dump(dict(tot={str(k): v for k, v in tot.items()}, fills={str(k): v for k, v in fills.items()}, per=per,
                   feed_us=feed_us, feed_first=feed_first), open(f"{R.WORK}/realtime.json", "w"))
