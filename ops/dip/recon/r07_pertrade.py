#!/usr/bin/env python3
# r07: TRADE BY TRADE reconciliation of every live fire (FRA runs 10-15, AMS runs 9-14) with the replay ("paper").
# For each fire: the dump's row in the recording's tape; our real landing (slot, idx) from the recording (r02/r04);
#   - the replay at 0..150 ms (block-position clock) with OUR OWN trades removed from the tape (the counterfactual tape),
#   - the replay at our EXACT landing position (same tape, our trades removed),
#   - the live outcome from the chain (recording tx records) and the engine's REALIZED lines.
# Fills: the gap (live - replay at our position) is split into
#   (a) entry  = model tokens vs live tokens at the same position,
#   (b) exit   = the replay's sell (slot s_in + cap, 75 ms into the slot, SL sells the next slot) vs our real sell position,
#   (c) tape/followers = model value at our real sell position vs the SOL our sell really got (slack-dropped followers etc.),
#   (d) costs  = FIX 0.0051 vs our real tx fees + tips (+ rent),
#   (e) rest.
# -> WORK/pertrade.json + printed tables. All numbers MEASURED (chain / recording) or replay outputs.
import sys, os, json, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib as R, rsim as S

FIX = 0.0051; FAIL = 0.0005
LATS = (0, 10, 20, 35, 50, 75, 100, 150)


def paper_exit(cfg):
    """the exit the paper used for a run's setting (dd12_livecal / dd20 mapping)"""
    h, sl = cfg["hold_slots"], cfg["sl"]
    if h == 19: return 19, 0.20
    if h == 6: return 6, 0.10
    if h == 5: return 4, None          # Stage-A A/B plan: hold 5 ~ c4, no SL (SL 0.5 never mattered in the replay)
    return h, sl


def live_exit(cfg):
    """what the engine actually does: time-limit sell lands in slot s_in + hold - 1 (MEASURED: 55+26+15 of 105 time-limit
    exits), stop-loss sell lands in the trigger slot (or the next)"""
    return cfg["hold_slots"] - 1, (cfg["sl"] if cfg["sl"] < 0.5 else None)


if __name__ == "__main__":
    F = json.load(open(f"{R.WORK}/fires.json")); rows = F["rows"]
    cfgs = {(r["srv"], r["run"]): r["cfg"] for r in F["runs"]}
    TPS = {tag: S.Tapes(tag) for tag in ("NEW", "OLD")}
    out = []
    for r in rows:
        cfg = cfgs[(r["srv"], r["run"])]
        size = r["spend"] / 1e9
        dr = r.get("dump_rec") or {}
        hit = None
        for tag in ("NEW", "OLD"):
            t, j0 = TPS[tag].find(r["mint"], r["dump_slot"], r["dump_idx_live"], dr.get("sell"))
            if j0 is not None: hit = (tag, t, j0); break
        o = dict(srv=r["srv"], run=r["run"], mint=r["mint"], t_fire=r["t_fire"], size=size, dev=r["dev"], client=r["client"], leader=r["leader"],
                 dump_slot=r["dump_slot"], dump_idx=r["dump_idx_live"], land_slot=r["land_slot"], land_idx=r["land_idx"], L_meas=r.get("L_meas"),
                 slots_after=r.get("slots_after"), live_fill=r["live_result"] == "sold", live_err=str(r.get("land_err")) if r.get("land_err") else None,
                 score=dr.get("score"), m2=dr.get("m2"), drop=dr.get("drop_pct"), age=dr.get("age"), sell=dr.get("sell"))
        if hit is None:
            o["tape"] = None; out.append(o); continue
        tag, t, j0 = hit; TP = TPS[tag]; tp = TP.token(t)
        o["tape"] = tag
        cap_p, sl_p = paper_exit(cfg); cap_l, sl_l = live_exit(cfg)
        o["exit_paper"] = [cap_p, sl_p]; o["exit_live_cfg"] = [cap_l, sl_l]
        # our real trades on this token after the dump (from the tape): buy (fills) and sell
        ours_after = [(int(tp["s"][x]), int(tp["i"][x]), int(tp["buy"][x]), float(tp["sol"][x]), float(tp["tokn"][x]))
                      for x in range(j0 + 1, min(tp["n"], j0 + 4000)) if tp["ours"][x]]
        o["ours_in_tape"] = ours_after[:4]
        # ---- replay at fixed latencies, our trades removed
        lat = {}
        for L in LATS:
            res = S.run_path(tp, j0, size, L=L)
            if res["st"] != 0:
                lat[L] = dict(st=res["st"], ratio=res["ratio"], pnl=(-FAIL if res["st"] == 1 else 0.0), ahead=res["ahead"])
            else:
                v, so, why = S.exits(res, cap_p, sl=sl_p)
                lat[L] = dict(st=0, ratio=res["ratio"], pnl=v - size - FIX, gross=v - size, so=so, why=why, ahead=res["ahead"], dropped=res["dropped"])
        o["lat"] = lat
        # ---- replay at our exact landing position
        res = S.run_path(tp, j0, size, at=(r["land_slot"], r["land_idx"]))
        o["x_st"] = res["st"]; o["x_ratio"] = res["ratio"]; o["x_ahead"] = res["ahead"]; o["x_ahead_buys"] = res["ahead_buys"]
        # live guard (exact): tokens our buy would get at that position vs the engine's min_out
        if res["st"] == 0:
            o["x_q"] = res["q"]; o["x_dropped"] = res["dropped"]
            v, so, why = S.exits(res, cap_p, sl=sl_p)
            o["x_paper"] = dict(pnl=v - size - FIX, gross=v - size, so=so, why=why)
            v2, so2, why2 = S.exits(res, cap_l, sell_idx=27, sl=sl_l, sl_lag_slots=0)
            o["x_livecfg"] = dict(pnl=v2 - size - FIX, gross=v2 - size, so=so2, why=why2)
        o["min_out"] = r.get("min_out")
        # ---- live outcome (chain)
        o["land_fee"] = r.get("land_fee"); o["land_tips"] = r.get("land_tips"); o["land_delta"] = r.get("land_delta")
        if o["live_fill"]:
            sells = [s for s in r["sells"] if not s.get("missing")]
            oks = [s for s in sells if not s.get("err")]
            o["n_sells"] = len(sells); o["n_sells_ok"] = len(oks)
            o["live_tok"] = r.get("land_tok"); o["live_sol_in"] = r.get("land_sol")
            o["chain_pnl"] = (r.get("land_delta") or 0) / 1e9 + sum((s.get("delta") or 0) for s in sells) / 1e9
            o["realized"] = r.get("realized")
            if oks:
                s = oks[-1]
                o["sell_slot"] = s["slot"]; o["sell_idx"] = s["idx"]; o["sell_tok"] = s["tok"]; o["sell_sol_gross"] = s["sol"] / 1e9
                fb = (s.get("fee_bps") or 0) / 1e4
                o["sell_fee_bps"] = s.get("fee_bps")
                o["sell_received"] = s["sol"] / 1e9 * (1 - fb)   # SOL out after pump fees (fee_bps = protocol + creator)
                o["sell_txcost"] = sum((x.get("fee") or 0) + (x.get("tips") or 0) for x in sells) / 1e9
                o["buy_txcost"] = ((r.get("land_fee") or 0) + (r.get("land_tips") or 0)) / 1e9
                o["exit_off_live"] = s["slot"] - r["land_slot"]
            o["exit_why_live"] = r.get("exit_why")
            if res["st"] == 0 and oks:
                key_live = o["sell_slot"] * 100000 + o["sell_idx"]
                qL = float(o["live_tok"]); qM = res["q"]
                E0 = o["x_paper"]["pnl"]
                key_paper = (res["s_in"] + o["x_paper"]["so"]) * 100000 + 142
                E1 = S.value_at_q(res, key_paper, qL) - size - FIX
                E2 = S.value_at_q(res, key_live, qL) - size - FIX
                E3 = o["sell_received"] - size - FIX
                E4 = o["chain_pnl"]
                o["decomp"] = dict(model=E0, entry=E1 - E0, exit=E2 - E1, tape=E3 - E2, costs=E4 - E3, live=E4,
                                   q_model=qM, q_live=qL, key_paper=key_paper, key_live=key_live)
        else:
            o["chain_pnl"] = (r.get("land_delta") or 0) / 1e9
        out.append(o)
    json.dump(out, open(f"{R.WORK}/pertrade.json", "w"), default=float)
    # ------------------------------------------------------------------ summaries
    have = [o for o in out if o.get("tape")]
    print(f"fires {len(out)}, on a recorded tape {len(have)}")
    fills = [o for o in have if o["live_fill"]]; fails = [o for o in have if not o["live_fill"]]
    # guard agreement at the exact position
    c = collections.Counter((o["live_fill"], o["x_st"]) for o in have)
    print("guard at our exact position: (live filled?, replay status 0 fill / 1 guard fail / 2 graduated):", dict(c))
    # P&L totals
    def tot(rows, f): return sum(f(o) for o in rows)
    print(f"LIVE chain P&L: fills {tot(fills, lambda o: o['chain_pnl']):+.4f} ({len(fills)}), failed buys {tot(fails, lambda o: o['chain_pnl']):+.4f} ({len(fails)})")
    print(f"  REALIZED lines (fills): {tot([o for o in fills if o.get('realized') is not None], lambda o: o['realized']):+.4f}")
    for L in LATS:
        p = tot(have, lambda o: o["lat"][L]["pnl"]); nf = sum(1 for o in have if o["lat"][L]["st"] == 0)
        print(f"  replay at {L:3d} ms on the SAME fires: {p:+.4f} SOL, fills {nf}/{len(have)}")
    xp = tot(have, lambda o: o["x_paper"]["pnl"] if o["x_st"] == 0 else (-FAIL if o["x_st"] == 1 else 0))
    xl = tot(have, lambda o: o["x_livecfg"]["pnl"] if o["x_st"] == 0 else (-FAIL if o["x_st"] == 1 else 0))
    print(f"  replay at OUR EXACT landing: paper exit {xp:+.4f}, live-like exit {xl:+.4f}, fills {sum(1 for o in have if o['x_st'] == 0)}")
    dd = [o["decomp"] for o in fills if o.get("decomp")]
    if dd:
        print(f"fills decomposed: {len(dd)}")
        for k in ("model", "entry", "exit", "tape", "costs", "live"):
            print(f"   {k:6s} {sum(d[k] for d in dd):+.4f}")
