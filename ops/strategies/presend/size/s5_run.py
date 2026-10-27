#!/usr/bin/env python3
"""SIZE study main (read-only, offline): every live fill of AMS r24-r28 (pre-send + regular) replayed on the real chain sequence at
other sizes with REPLAY_065's exact method + revived failed buys (sizelib.py).
  validation : each run at its own live size must give back every trade to the lamport (r24/r25 0.34, r26 0.50, r27 0.35, r28 0.50;
               regular 0.35 / 0.50 / 0.55)
  sizes      : 0.25, 0.35, 0.40, 0.50, 0.65 SOL for every run (pre-send and regular)
  variants   : main (fail_buy revival on) | literal (revival off = REPLAY_065 as it was)
  stress     : 20 % of later buyers (incl. revived ones) dropped at random, N paired draws (same draws at every size)
Writes /home/moiz/sniper-data/presend_size/results.json (per trade, every size) + calib per group. Replay = INFERRED, live = MEASURED."""
import sys, json, pickle, collections, time
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real/r065")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/size")
import numpy as np
import core
import sizelib as SL

OUT = "/home/moiz/sniper-data/presend_size"
GROUPS = [("A", "/home/moiz/sniper-data/replay065", ("r24", "r25"), [f"{OUT}/args_2425.jsonl"]),
          ("B", "/home/moiz/sniper-data/presend_size", ("r26", "r27", "r28"), [])]
SIZES = [250_000_000, 350_000_000, 400_000_000, 500_000_000, 650_000_000]
RENT_BACK = 1_508_820


def calib(D, PS, RG, PO):
    """calib065.main without writing: live costs, live TP/SL trigger rows, MEASURED sell delays"""
    for p in PS:
        st = p.sell_tr
        p.costs = p.buy_fee + p.tip + p.rent + p.sell_fee + p.sell_tips
        p.net_live = st["sol"] - SL.PM.fees(st["sol"], st["fbps"], st["cbps"])
    for p in RG:
        st = p.sell_tr
        p.net_live = st["sol"] - SL.PM.fees(st["sol"], st["fbps"], st["cbps"])
        p.costs = p.net_live - p.spend - p.realized
    dl = collections.defaultdict(list); found = collections.Counter()
    SL.CFG["resurrect"] = False
    for p in PS + RG:
        p.live_dec_row = None; p.live_trig_rx = None
        if p.exit_why in ("take-profit", "stop-loss"):
            W = SL.walk2(D, p.mint, p.pre, p.rows, p.spend, p.ours_buy["fbps"], p.ours_buy["cbps"], (10 ** 15, 0, 0))
            best = None
            for k, v, t, ap in W["states"]:
                row = p.rows[k]
                if not ap or row["kind"] != "trade": continue
                rx = p.tape_rx.get(row["tr"]["sig"])
                if rx is None or rx > p.exit_t: continue
                val = PO.value_ps(v, t, W["q"], row["tr"]["fbps"], row["tr"]["cbps"], p.spend) if p.kind == "ps" else PO.value_reg(v, t, W["q"], row["tr"]["fbps"], row["tr"]["cbps"], p.spend)
                if abs(val - p.exit_value) < 1e-9: best = (k, rx)
            if best:
                p.live_dec_row, p.live_trig_rx = best; found["trig_found"] += 1
                row = p.rows[best[0]]
                dl[p.kind + ":tpsl"].append(D.ck.cc(*p.sell_pos) - D.ck.cc(row["s"], row["i"]))
            else:
                found["trig_missing"] += 1
        elif p.exit_why == "time-limit":
            base = (p.land_slot + (2 if p.kind == "ps" else p.hold)) * core.SMS
            dl[p.kind + ":time"].append(D.ck.cc(*p.sell_pos) - base)
    SL.CFG["resurrect"] = True
    delays = {k: float(np.median(v)) for k, v in dl.items()}
    delays.setdefault("reg:tpsl", delays["ps:tpsl"])
    delays.setdefault("reg:time", delays.get("ps:time", 111.0))
    return delays, dict(found), {k: len(v) for k, v in dl.items()}


def one_group(name, base, runs, extra, draws):
    t0 = time.time()
    core.BASE = base
    D = core.Data()
    for fn in extra:
        for l in open(fn):
            r = json.loads(l)
            if r.get("kind") == "ok" or r["sig"] not in D.args: D.args[r["sig"]] = r
    SL.install()
    import positions as PO
    PS = [p for p in PO.presend_positions(D) if p.run in runs]
    RG, RF = PO.regular_positions(D)
    RG = [p for p in RG if p.run in runs and p.sell_tr is not None and p.realized is not None]
    delays, found, ndl = calib(D, PS, RG, PO)
    nbad = sum(SL.mark_bad(D, p) for p in PS + RG)
    nfb = sum(1 for p in PS + RG for r in p.rows if r["kind"] == "fail_buy")
    nnd = sum(1 for p in PS + RG for r in p.rows if r["kind"] == "fail_buy_nodec")
    print(name, "positions ps", len(PS), "reg", len(RG), "delays", {k: round(v, 1) for k, v in delays.items()}, ndl, found,
          "fail_buy rows", nfb, "unexplained at live (never revived)", nbad, "undecoded", nnd, f"{time.time() - t0:.0f}s", flush=True)
    trades = []
    for idx, p in enumerate(PS + RG):
        T = dict(g=name, idx=idx, run=p.run, kind=p.kind, mint=p.mint, t=p.t, spend_live=p.spend, live=p.realized, costs=p.costs,
                 why_live=p.exit_why, buy_pos=list(p.buy_pos), sell_pos=list(p.sell_pos),
                 n_fb=sum(1 for r in p.rows if r["kind"] == "fail_buy" and (r["s"], r["i"]) < p.sell_pos),
                 n_fb_bad=sum(1 for r in p.rows if r["kind"] == "fail_buy" and r.get("bad") and (r["s"], r["i"]) < p.sell_pos),
                 n_fb_nodec=sum(1 for r in p.rows if r["kind"] == "fail_buy_nodec" and (r["s"], r["i"]) < p.sell_pos))
        rl = SL.replay2(D, p, p.spend, delays)
        T["val"] = rl["pnl"] if rl["filled"] else None
        T["val_why"] = rl.get("why"); T["val_flat"] = rl.get("flat"); T["val_revived"] = rl.get("revived_n"); T["val_buys_in"] = rl.get("buys_in")
        T["sz"] = {}
        for S in SIZES + [p.spend]:
            r = SL.replay2(D, p, S, delays)
            SL.CFG["resurrect"] = False
            r0 = SL.replay2(D, p, S, delays)
            SL.CFG["resurrect"] = True
            T["sz"][str(S)] = dict(filled=r["filled"], pnl=r.get("pnl"), why=r.get("why"), src=r.get("sell_src"), po_n=r.get("priced_out_n"), po_sol=r.get("priced_out_sol"),
                                   sf_n=r.get("sells_failed_n"), rv_n=r.get("revived_n"), rv_sol=r.get("revived_sol"), flat=r.get("flat"), buys_in=r.get("buys_in"),
                                   q=r.get("q"), lit_pnl=r0.get("pnl"), lit_flat=r0.get("flat"), lit_po_n=r0.get("priced_out_n"))
        trades.append(T)
    print(name, "replayed sizes", f"{time.time() - t0:.0f}s", flush=True)
    # stress: 20 % fewer later buyers, paired draws (one rng per draw and position, the same at every size)
    P = PS + RG
    cut = {str(S): np.zeros((draws, len(P))) for S in SIZES + ["live"]}
    for d in range(draws):
        for k, p in enumerate(P):
            for S in SIZES + ["live"]:
                sz = p.spend if S == "live" else S
                r = SL.replay2(D, p, sz, delays, cut=0.2, rng=np.random.default_rng([65, d, k]))
                cut[str(S)][d, k] = r["pnl"] if r["filled"] else 0.0
    print(name, "stress", f"{time.time() - t0:.0f}s", flush=True)
    return dict(delays=delays, found=found, ndl=ndl, nbad=nbad, nfb=nfb, nnd=nnd), trades, {k: v.tolist() for k, v in cut.items()}


if __name__ == "__main__":
    draws = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    only = sys.argv[2].split(",") if len(sys.argv) > 2 else None
    tag = sys.argv[3] if len(sys.argv) > 3 else ""
    res = dict(groups={}, trades=[], cut={})
    for name, base, runs, extra in GROUPS:
        if only and name not in only: continue
        g, tr, cut = one_group(name, base, runs, extra, draws)
        res["groups"][name] = g; res["trades"] += tr; res["cut"][name] = cut
        # quick print: validation + totals
        for run in runs:
            for kind in ("ps", "reg"):
                X = [t for t in tr if t["run"] == run and t["kind"] == kind]
                if not X: continue
                live = sum(t["live"] for t in X) / 1e9; val = sum(t["val"] for t in X if t["val"] is not None) / 1e9
                ex = sum(1 for t in X if t["val"] == t["live"])
                line = f"{run} {kind} n={len(X)} live {live:+.4f} val {val:+.4f} exact {ex}/{len(X)} |"
                for S in SIZES:
                    tot = sum(t["sz"][str(S)]["pnl"] or 0 for t in X if t["sz"][str(S)]["filled"]) / 1e9
                    line += f" {S / 1e9:.2f} {tot:+.4f}"
                print(line, flush=True)
    json.dump(res, open(f"{OUT}/results{tag}.json", "w"), default=float)
    print("wrote results.json")
