#!/usr/bin/env python3
"""REARM step 7 (read-only): export EVERY decision of the re-arm rule in the test replay to decisions.jsonl (one JSON per line),
from the decision logs of r4_days.py --log (draw 0, seed 9100; reproducible: r1_tapes.py -> r3_events.py -> r3b_holders.py ->
r4_days.py DAY --cfgs C --draws 1 --tag T --log). All INFERRED (replay) except the tape facts (paid dump, next whale dump: MEASURED).
Every record: day, cfg, win (window id), mint, kind, slot, idx, trigger (the paid dump: slot, idx, seller, r2), reason.
Per re window, in order:
  arm | arm_wait (token blocked by our own position / token account, waits) | skip (never armed, with the reason)
  buy_try   one per attempt the engine sends (rate-capped / paused attempts are not sent and not listed): send time t (ms), engine
            slot, the price it had seen (sign_px) and its limit (lim_px = 0.88 x sign_px), where it lands (slot, fractional tx
            index), the curve price there before it (land_px), result = reason: 6042 (price above the limit: fails, pays 5,120
            lamports) | deadline (lands after its slot deadline: fails, pays) | drop (never lands) | cand (price at/below the limit:
            the first one fills, later ones fail at the token-account create, pay)
  fill      slot / index, entry price, tokens, SOL to the curve (0.40 SOL spend incl. pump's fee); on_next_dump = the fill is in the
            slot of the token's next whale dump (or the one after)
  sell      exit reason (tp / sl / time), sell slot, SOL out after pump's fee, P&L (NOW costs 2.015 mSOL/fill): model, cal (0.81 x
            if > 0), cons (0.46 x if > 0), addc (-1.49 mSOL); S2 costs (0.510 mSOL/fill); the wave exit; -10 / -20 % followers
  disarm    why: expired (window's last slot) | whale_sold (30 ms after the engine sees the next whale dump or, H=2, the trade after
            which no wallet holds >= 6 %) | filled | quiet (QUIET stop 6:2) | superseded (a T2 trigger took the token)
Plus the knock-on on today's pre-send (res rows, base vs this config, same draw): kind t2_changed = a T2 window whose outcome the
re-arm changed (it lost / gained / changed its fill), with both P&Ls (model, NOW) and the reason.
Prices are curve prices in lamports per raw token unit (x 1e-3 = SOL per token). t = the replay's chain clock in ms.
usage: r7_export.py TAG DAY:CFG[,DAY:CFG..] [--out decisions.jsonl] [--append]"""
import sys, json, pickle, argparse
OUT = "/home/moiz/sniper-data/haqq_dissect/rearm"
COST = 2_015_140; COST_S2 = 510_140


def r6(x): return None if x is None else float(f"{x:.6g}")


def ms(x): return None if x is None else round(float(x), 1)


def arm_reason(cfg):
    x, g, a, k, h = cfg.split(":")
    r = "whale_dump" + ("" if x == "any" else f"_paid_r2>={x}") + f"_age<={a}s"
    return r + ("_6pct_holder_left" if h != "0" else "")


def lv(g):
    return dict(pnl_model_sol=r6(g / 1e9), pnl_cal_sol=r6((0.81 * g if g > 0 else g) / 1e9), pnl_cons_sol=r6((0.46 * g if g > 0 else g) / 1e9),
                pnl_addc_sol=r6((g - 1_490_000) / 1e9))


ap = argparse.ArgumentParser(); ap.add_argument("tag"); ap.add_argument("plan"); ap.add_argument("--out", default="decisions.jsonl"); ap.add_argument("--append", action="store_true")
A = ap.parse_args()
n = 0; kinds = {}
with open(f"{OUT}/{A.out}", "a" if A.append else "w") as fo:
    def W(r):
        global n
        fo.write(json.dumps(r, separators=(",", ":")) + "\n"); n += 1; kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    for item in A.plan.split(","):
        day, cfg = item.split(":", 1); day = int(day)
        logs = pickle.load(open(f"{OUT}/log_D{day}_{A.tag}.pkl", "rb"))[cfg]
        EV = pickle.load(open(f"{OUT}/ev_D{day}.pkl", "rb"))["EV"]
        evk = {(e["mint"], e["slot"], e["idx"]): e for e in EV}
        for wi, (trig, lg, res) in enumerate(logs):
            src = trig["src"]; e = evk.get((trig["mint"], src[0], src[1]), {})
            nx = e.get("nxt")
            tg = dict(dump_slot=src[0], dump_idx=src[1], dump_seller=src[2], dump_r2_sol=r6(trig["r2"]), dump_age_s=r6(e.get("age_s")),
                      next_whale_dump=list(nx) if nx else None)
            base = dict(day=day, cfg=cfg, win=f"D{day}-{wi}", mint=trig["mint"])
            for x in lg or []:
                ev = x["ev"]
                if ev == "arm":
                    W(dict(base, kind="arm", slot=trig["slot"], idx=0, trigger=tg, t=ms(x["t"]), px=r6(x["psign0"]), win_first_slot=trig["slot"], win_last_slot=trig["en"],
                           stop_at=list(trig["whale_sell"]) if trig.get("whale_sell") else None, k=trig["k"], reason=arm_reason(cfg)))
                elif ev == "arm_wait":
                    W(dict(base, kind="arm_wait", slot=trig["slot"], idx=0, trigger=tg, t=ms(x["t"]), until=ms(x["until"]), reason="own_position_or_token_account"))
                elif ev == "skip":
                    W(dict(base, kind="skip", slot=trig["slot"], idx=0, trigger=tg, t=ms(x["t"]), reason=x["why"]))
                elif ev == "try":
                    W(dict(base, kind="buy_try", slot=x.get("S"), idx=r6(x.get("I")), n=x["n"], t=ms(x["t"]), engine_slot=x["E"], sign_px=r6(x["psign"]), lim_px=r6(x["lim"]),
                           land_px=r6(x.get("p_land")), sol=0.40, reason=x["res"]))
                elif ev == "disarm":
                    if res.get("filled"):
                        ex = res["ex"]; b = ex["base"]
                        g = b["gross"] - COST
                        onx = bool(nx and nx[0] <= res["fill_S"] <= nx[0] + 1 and nx[0] <= trig["en"])
                        W(dict(base, kind="fill", slot=res["fill_S"], idx=r6(res["fill_I"]), trigger=tg, entry_px=r6(res["p_pre"]), lim_px=r6(res["lim"]), sign_px=r6(res["psign"]),
                               tokens=b["tokens"], sol_to_curve=b["x_in"] / 1e9, sol=0.40, path=res["path"], on_next_dump=onx, reason="price_at_or_below_limit"))
                        W(dict(base, kind="sell", slot=b["sell_S"], idx=None, trigger=tg, reason=b["why"], sol_out=b["out"] / 1e9, **lv(g),
                               pnl_model_s2_sol=r6((b["gross"] - COST_S2) / 1e9), pnl_model_wave_sol=r6((ex["wave"]["gross"] - COST) / 1e9), wave_exit=ex["wave"]["why"],
                               pnl_model_wave_s2_sol=r6((ex["wave"]["gross"] - COST_S2) / 1e9),
                               pnl_model_fol10_sol=r6((ex["cut10"]["gross"] - COST) / 1e9), pnl_model_fol20_sol=r6((ex["cut20"]["gross"] - COST) / 1e9),
                               costs_sol=COST / 1e9, failed_tries=res["nfail"], failed_try_fees_sol=res["nfail"] * 5120 / 1e9))
                    W(dict(base, kind="disarm", slot=None, idx=None, trigger=tg, t=ms(x["t"]), reason=x["why"], failed_tries=res.get("nfail"),
                           failed_try_fees_sol=(res.get("nfail") or 0) * 5120 / 1e9))
        # knock-on on today's T2 windows (base vs this config, same draw)
        fn = f"{OUT}/res_D{day}_{A.tag}.pkl"
        Z = pickle.load(open(fn, "rb"))["out"]
        bmap = {r[0]: r for r in Z["base"][0] if r[0][0] == "t2"}
        for r in Z[cfg][0]:
            if r[0][0] != "t2": continue
            b = bmap.get(r[0])
            if b is None: continue
            gb = (b[8][2]["base"][0] - COST) if b[3] else None; gc = (r[8][2]["base"][0] - COST) if r[3] else None
            fb = b[4] * 5120; fc = r[4] * 5120
            if gb == gc and fb == fc: continue
            W(dict(day=day, cfg=cfg, win=f"D{day}-t2-{r[0][2]}-{r[0][3]}", mint=r[0][1], kind="t2_changed", slot=r[0][2], idx=r[0][3], trigger="t2_whale_buy",
                   base_filled=bool(b[3]), now_filled=bool(r[3]), base_pnl_model_sol=r6(gb / 1e9) if gb is not None else None,
                   now_pnl_model_sol=r6(gc / 1e9) if gc is not None else None, base_fees_sol=fb / 1e9, now_fees_sol=fc / 1e9,
                   delta_model_sol=r6(((gc or 0) - fc - (gb or 0) + fb) / 1e9), reason=f"base:{b[2]} -> now:{r[2]}"))
print(f"wrote {OUT}/{A.out}: {n:,} decisions {kinds}")
