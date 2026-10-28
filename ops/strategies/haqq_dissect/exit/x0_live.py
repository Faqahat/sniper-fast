#!/usr/bin/env python3
"""EXIT step 0 (read-only): every OUR live position (regular fills + pre-send fills) from the run records, with the exit decision
(why, slot, local rx time) and every sell landing (slot, idx, rx time, SOL). Runs: AMS r9-r33, FRA r1-r26 (dv8/runs.py).
Regular: fire -> buy_land -> exit -> sell_land -> close.   Pre-send: presend_live_fill -> presend_live_exit -> presend_live_sell_land
-> presend_live_close (buys list = every attempt that landed into the position).
Out: /home/moiz/sniper-data/haqq_dissect/exit/ours_pos.pkl  [dict(kind, run, srv, mint, buys=[(slot, idx, t_rx, sol_in, tokens|None)],
     exit=(why, slot, t, value), sells=[(slot, idx, t_rx, sol)], hold_cfg, tp, sl, spend, curve_pnl)]"""
import json, pickle, sys, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
from runs import run_files
OUT = "/home/moiz/sniper-data/haqq_dissect/exit"


def tsec(t): return t / 1e9 if t and t > 1e15 else t


def main():
    P = []
    for run, f in run_files().items():
        srv = run[:3]; cfg = {}
        reg = {}; reg_exit = {}; reg_sell = collections.defaultdict(list); fires = {}
        ps_fill = {}; ps_exit = {}; ps_sell = collections.defaultdict(list); ps_close = []
        for l in open(f):
            try: d = json.loads(l)
            except Exception: continue
            e = d.get("ev")
            if e == "run_start":
                ps = d.get("presend") if isinstance(d.get("presend"), dict) else {}
                cfg = dict(hold=d.get("hold_slots"), tp=d.get("tp"), sl=d.get("sl"), spend=d.get("spend"), ps_exit=ps.get("exit_slots"), ps_tp=ps.get("tp"), ps_sl=ps.get("sl"))
            elif e == "fire": fires[d["buy_sig"]] = d
            elif e == "close" and d.get("result") not in ("buy_failed", None) and d.get("land"):
                reg[d["mint"] + ":" + str(d["land"][0])] = d
            elif e == "exit": reg_exit[d["mint"]] = reg_exit.get(d["mint"], []) + [d]
            elif e == "sell_land": reg_sell[d["mint"]].append(d)
            elif e == "presend_live_exit": ps_exit[(d["mint"], d.get("pid"))] = d
            elif e == "presend_live_sell_land": ps_sell[(d["mint"], d.get("pid"))].append(d)
            elif e == "presend_live_close": ps_close.append(d)
        for k, c in reg.items():
            m = c["mint"]; ls = c["land"][0]
            ex = [x for x in reg_exit.get(m, []) if ls <= x["slot"] <= ls + 200]
            ex = ex[0] if ex else None
            sl_ = [x for x in reg_sell.get(m, []) if ls <= x["slot"] <= ls + 400]
            P.append(dict(kind="reg", run=run, srv=srv, mint=m, result=c.get("result"), buys=[(c["land"][0], c["land"][1], c["land"][2], None, None)],
                          exit=(ex["why"], ex["slot"], ex["t"], ex.get("value")) if ex else (c.get("exit_why"), c.get("exit_slot"), None, c.get("exit_value")),
                          sells=[(x["slot"], x["idx"], x["t"], x["sol"]) for x in sl_], hold=cfg.get("hold"), tp=cfg.get("tp"), sl=cfg.get("sl"),
                          spend=(cfg.get("spend") or 0) / 1e9, curve_pnl=c.get("curve_pnl"), dump_sig=c.get("dump_sig"), dump_slot=c.get("dump_slot"),
                          dump_idx=c.get("dump_idx"), held_s=c.get("held_s")))
        for c in ps_close:
            key = (c["mint"], c.get("pid")); ex = ps_exit.get(key)
            buys = [(b["slot"], b["idx"], b.get("t"), b.get("sol_in"), b.get("tokens")) for b in (c.get("buys") or [])]
            if not buys and c.get("land"): buys = [(c["land"][0], c["land"][1], c["land"][2], c.get("sol_in_curve"), c.get("tokens"))]
            sells = [(x["slot"], x["idx"], x["t"], x["sol"]) for x in ps_sell.get(key, [])]
            if not sells and c.get("sell_lands"): sells = [tuple(s) for s in c["sell_lands"]]
            P.append(dict(kind="ps", run=run, srv=srv, mint=c["mint"], result=c.get("result"), buys=buys,
                          exit=(ex["why"], ex["slot"], ex["t"], ex.get("value")) if ex else (c.get("exit_why"), c.get("exit_slot"), None, c.get("exit_value")),
                          sells=sells, hold=cfg.get("ps_exit"), tp=cfg.get("ps_tp"), sl=cfg.get("ps_sl"), spend=(c.get("spend") or 0) / 1e9,
                          curve_pnl=c.get("curve_pnl"), merged=c.get("merged"), late=c.get("late"), held_s=c.get("held_s")))
        print(run, "reg", len(reg), "ps", len(ps_close), flush=True)
    pickle.dump(P, open(f"{OUT}/ours_pos.pkl", "wb"))
    c = collections.Counter((p["kind"], p["exit"][0]) for p in P); print(len(P), dict(c))


if __name__ == "__main__":
    main()
