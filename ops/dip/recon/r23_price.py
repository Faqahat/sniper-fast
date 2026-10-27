#!/usr/bin/env python3
# r23: PRICE OF SPEED with the corrected model, on the 309 dumps we really fired on (10-24 16:59 -> 10-25 07:50 PKT;
# 27.6 server-hours = 13.8 h of both servers). Two settings: (1) as the runs were set; (2) today's exit for every fire
# (sell slot +4 ~0.85 s, no SL, 0.35 SOL, nonce-era costs 0.0031/fill, 0.000505/failed buy).
# Landing: block-position clock fixed 0..75 ms; our measured landing; real-time "X ms faster" on our own feed clock (r17 logic).
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
                if o.get("ev") == "tape": tape[(srv, o["mint"])][(o["slot"], o["idx"])] = o["t"] / 1e6
    cost = {}; fcost = {}
    for k in runs:
        fl = [o for o in P if (o["srv"], o["run"]) == k and o["live_fill"] and o.get("buy_txcost") is not None]
        fa = [o for o in P if (o["srv"], o["run"]) == k and not o["live_fill"]]
        cost[k] = float(np.mean([o["buy_txcost"] + o["sell_txcost"] for o in fl])) if fl else 0.0031
        fcost[k] = float(np.mean([-o["chain_pnl"] for o in fa])) if fa else 0.000505
    MODES = [("fixed 0 ms", ("L", 0.0)), ("fixed 10 ms", ("L", 10.0)), ("fixed 20 ms", ("L", 20.0)), ("fixed 35 ms", ("L", 35.0)),
             ("fixed 50 ms", ("L", 50.0)), ("fixed 75 ms", ("L", 75.0)), ("MEASURED (our real landing)", ("x", 0)),
             ("real time: 5 ms faster", ("rt", 5)), ("real time: 10 ms faster", ("rt", 10)), ("real time: 20 ms faster", ("rt", 20)),
             ("real time: 30 ms faster", ("rt", 30)), ("real time: 50 ms faster", ("rt", 50)), ("in front of every rival", ("front", 0))]
    tot = {m: [0.0, 0.0, 0, 0] for m, _ in MODES}
    for o in P:
        k = (o["srv"], o["run"]); cfg = runs[k]["cfg"]; sl = cfg["sl"] if cfg["sl"] < 0.5 else None
        r = fr[(o["srv"], o["mint"], o["dump_slot"])]; tm = r["timing"]
        TP = TPS[o["tape"]]; t, j0 = TP.find(o["mint"], o["dump_slot"], o["dump_idx"], o.get("sell")); tp = TP.token(t)
        key_us = o["land_slot"] * 100000 + o["land_idx"]
        btw = [x for x in range(j0 + 1, tp["n"]) if tp["SI"][x] < key_us and not tp["ours"][x]]
        rx = [tape[(o["srv"], o["mint"])].get((int(tp["s"][x]), int(tp["i"][x]))) for x in btw]
        own = tape[(o["srv"], o["mint"])].get((o["land_slot"], o["land_idx"]))
        if o["live_fill"] and own: rx_us = own
        else:
            lag = ((tm.get("dump_exec_rx") or 0) - (tm.get("dump_first_rx") or 0)) / 1e6 if tm.get("dump_first_rx") else 1.3
            rx_us = tm["buy_first_rx"] / 1e6 + max(0.0, lag)
            last = max([v for v in rx if v is not None], default=None)
            if last is not None: rx_us = max(rx_us, last + 0.001)
        for m, (kind, X) in MODES:
            if kind == "L": res = S.run_path(tp, j0, o["size"], L=X); res2 = S.run_path(tp, j0, 0.35, L=X)
            else:
                if kind == "x": at = (o["land_slot"], o["land_idx"])
                elif kind == "front": at = (int(tp["s"][btw[0]]), int(tp["i"][btw[0]])) if btw else (o["land_slot"], o["land_idx"])
                else:
                    at = (o["land_slot"], o["land_idx"])
                    for n, x in enumerate(btw):
                        if rx[n] is not None and rx[n] >= rx_us - X: at = (int(tp["s"][x]), int(tp["i"][x])); break
                res = S.run_path(tp, j0, o["size"], at=at); res2 = S.run_path(tp, j0, 0.35, at=at)
            a = outcome(res, cfg["hold_slots"], sl, cost[k], fcost[k]); b = outcome(res2, 5, None, 0.0031, 0.000505)
            tot[m][0] += a["pnl"]; tot[m][1] += b["pnl"]; tot[m][2] += a["st"] == 0; tot[m][3] += b["st"] == 0
    live = sum(o["chain_pnl"] for o in P)
    scale = 24.0 / 13.8
    print(f"PRICE OF SPEED, corrected model, the 309 live fires (13.8 h of both servers). LIVE {live:+.3f} SOL ({live * scale:+.2f} SOL/day)")
    print(f"{'landing':32s} | {'as the runs were set':>30s} | {'today exit (+4 slots, no SL, 0.35)':>36s}")
    out = {}
    for m, _ in MODES:
        a, b, fa, fb = tot[m]
        print(f"{m:32s} | {a:+7.3f} SOL {a * scale:+6.2f}/day {fa:3d} fills | {b:+7.3f} SOL {b * scale:+6.2f}/day {fb:3d} fills")
        out[m] = dict(asrun=a, asrun_day=a * scale, today=b, today_day=b * scale, fills_asrun=fa, fills_today=fb)
    json.dump(dict(out=out, live=live, scale=scale), open(f"{R.WORK}/price.json", "w"), indent=1)
