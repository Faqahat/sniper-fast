#!/usr/bin/env python3
"""FLAT study, IDEA A core (read-only, offline): replay one live pre-send position with a different exit on the real chain tape.
  * the position: our buy's chain row (its post-trade curve state, our tokens q), our live sell(s), the token's later trades
  * the counterfactual (INFERRED): our live sell removed; every other trade after our buy in chain order keeps its size and is
    re-priced with pump's integer math (real/r065/pmath.py) on the counterfactual curve:
      SOL-in buy   : the same SOL into the curve; tokens by the formula that reproduces it on its real pre-state ('n1' =
                     t (n-1) // (v + n - 1), the buy_exact_quote_in form; 'floor' = t n // (v + n))
      exact-token  : the same tokens; cost = v a // (t - a) + 1
      sell         : the same tokens, less any tokens the wallet did not get from its own earlier replayed buys
    nobody changes behaviour; no follower fails ('nolim'); optionally decoded limits (lims={sig: (kind, limit)}) make a buy
    fail when it would get fewer tokens than its min / pay more than its max (then dropped, as real/r065 core.walk)
  * the engine during the hold: TP +10% / SL -20% on every other wallet's trade (dip value = eng_sell_out x (1 - fee rate) /
    spend), checked on trades in slots before the time-exit slot
  * our sell lands: time exit at slot fill + N -> (fill slot + N) x 212 ms + this position's own live time-exit delay;
    trade-triggered (TP / SL / big sell / first other trade K = 0) -> the trigger trade's chain time + D_REACT (median live TP / SL
    reaction, measured on dev); K >= 1 -> max(first trade + D_REACT, (its slot + K) x 212 + the position's time delay)
  * our sell = sell_sol on the state just before its chain position, minus pump's fees at our live sell's fee bps; realized =
    live realized + (sell net SOL replayed - live sell net SOL); every other cost (buy, tips, tx fees, rent) as live."""
import sys
import numpy as np
import flatlib as FL
from flatlib import PM

sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real/r065")
import core as R065          # noqa: E402  fee_rate_ps, eng_sell_out (the engine's own value formula)

SMS = FL.SMS


def buy_form(v0, t0, sol, tok):
    if sol > 1 and t0 * (sol - 1) // (v0 + sol - 1) == tok: return "n1"
    if t0 * sol // (v0 + sol) == tok: return "floor"
    return "exact"


def prep(C, w):
    """the position's tape after our buy (chain order), our live sell; None when not replayable"""
    if not w["filled"] or w.get("k_buy") is None or w.get("k_sell") is None: return None
    c = C.c
    rows = C.mint_rows(w["mint"])
    kb, ks = w["k_buy"], w["k_sell"]
    rb = rows[kb]; rs = rows[ks]
    our_sells = set(int(rows[q]) for q in range(kb + 1, len(rows)) if c["user"][rows[q]] == C.ams and c["buy"][rows[q]] == 0 and q <= ks)
    land = int(c["s"][rb])
    end = land + 40
    tape = []
    for q in range(kb + 1, len(rows)):
        r = int(rows[q])
        s = int(c["s"][r])
        if s > end: break
        if r in our_sells: continue
        buy = bool(c["buy"][r]); sol = int(c["sol"][r]); tok = int(c["tok"][r]); vs = int(c["vsol"][r]); vt = int(c["vtok"][r])
        if buy: v0, t0 = vs - sol, vt + tok
        else: v0, t0 = vs + sol, vt - tok
        tape.append(dict(r=r, s=s, i=int(c["i"][r]), j=int(c["j"][r]), buy=buy, sol=sol, tok=tok, vs=vs, vt=vt, user=int(c["user"][r]),
                         fb=int(c["fbps"][r]), cb=int(c["cbps"][r]), form=buy_form(v0, t0, sol, tok) if buy else None,
                         cc=C.cc(s, int(c["i"][r])), sig=C.sig(r), ours=(int(c["user"][r]) == C.ams)))
    sl_sol = sum(int(c["sol"][rows[q]]) for q in range(kb + 1, ks + 1) if int(rows[q]) in our_sells)
    sfb, scb = int(c["fbps"][rs]), int(c["cbps"][rs])
    net_live = sl_sol - PM.fees(sl_sol, sfb, scb) if len(our_sells) == 1 else \
        sum(int(c["sol"][rows[q]]) - PM.fees(int(c["sol"][rows[q]]), int(c["fbps"][rows[q]]), int(c["cbps"][rows[q]])) for q in range(kb + 1, ks + 1) if int(rows[q]) in our_sells)
    cc_sell = C.cc(int(c["s"][rs]), int(c["i"][rs]))
    P = dict(w=w, land=land, v=int(c["vsol"][rb]), t=int(c["vtok"][rb]), q=int(w["fill"]["tokens"]), spend=int(w["spend"]), fb=int(c["fbps"][rb]), cb=int(c["cbps"][rb]),
             sell_key=(int(c["s"][rs]), int(c["i"][rs])), cc_sell=cc_sell, d_time=cc_sell - (land + 2) * SMS, net_live=net_live, sfb=sfb, scb=scb,
             tape=tape, pnl=w["pnl"], rb=w["rb"], t_sell=(w["sells"][-1]["t"] if w["sells"] else None))
    return P


def walk(P, rule, d_react, lims=None, check=False):
    """rule: dict(N=max hold slots, K=None|0|1|2 (sell K slots after the first other trade), X=None|SOL (sell at once on another
    wallet's sell >= X)). Returns dict(net, pnl, score, a_sell, why, n_applied, first_other, dropped)"""
    v, t = P["v"], P["t"]; q = P["q"]; spend = P["spend"]; land = P["land"]
    N = rule["N"]; K = rule.get("K"); X = rule.get("X")
    a_time = (land + N) * SMS + P["d_time"]           # the time exit's landing (chain ms)
    a_dec = (land + N) * SMS                           # its decision (slot start)
    a_sell = a_time; why = f"time+{N}"
    first = None
    delta = {}
    dropped = 0
    states = []                                        # (cc, v, t) after each applied row
    mism = 0
    blocked = []
    for row in P["tape"]:
        if row["cc"] >= a_sell: break
        if row["ours"] and row["cc"] >= P["cc_sell"]:
            # one of OUR later trades on this token (a later pre-send fill / a reactive buy, or its sell): blocked while we still
            # hold this position in the counterfactual (blocked_position / presend_position) -> not applied; reported as a side effect
            blocked.append(row); continue
        # apply the row on the counterfactual state
        if row["buy"]:
            if row["form"] == "exact":
                a = row["tok"]
                if a >= t: dropped += 1; continue
                n = v * a // (t - a) + 1
                lim = (lims or {}).get(row["sig"])
                if lim and lim[0] == "tok" and n + PM.fees(n, row["fb"], row["cb"]) > lim[1]: dropped += 1; delta[row["user"]] = delta.get(row["user"], 0) + a; continue
                v += n; t -= a
            else:
                n = row["sol"]
                qq = t * (n - 1) // (v + n - 1) if row["form"] == "n1" else t * n // (v + n)
                lim = (lims or {}).get(row["sig"])
                if lim and lim[0] == "quote" and qq < lim[1]: dropped += 1; delta[row["user"]] = delta.get(row["user"], 0) + row["tok"]; continue
                v += n; t -= qq
                delta[row["user"]] = delta.get(row["user"], 0) + row["tok"] - qq
            sold = None
        else:
            qa = row["tok"] - max(delta.get(row["user"], 0), 0)
            if qa <= 0: dropped += 1; continue
            if qa < row["tok"]: delta[row["user"]] = 0
            o = v * qa // (t + qa)
            v -= o; t += qa
            sold = o
        if check and row["cc"] < P["cc_sell"]:
            if (v, t) != (row["vs"], row["vt"]): mism += 1
        states.append((row["cc"], v, t))
        if row["ours"]: continue
        # the engine's checks on this trade (other wallets only), after the live decision moment
        if first is None:
            first = row
            if K is not None and row["cc"] < a_dec:
                a_k = row["cc"] + d_react if K == 0 else max(row["cc"] + d_react, (row["s"] + K) * SMS + P["d_time"])
                a_k = max(a_k, P["cc_sell"])
                if a_k < a_sell:
                    a_sell = a_k; why = f"first+{K}"
                    a_dec = row["cc"] if K == 0 else max(row["cc"], (row["s"] + K) * SMS)
                    if K == 0: continue
        if row["cc"] < a_dec:
            fr = R065.fee_rate_ps(row["fb"], row["cb"])
            val = R065.eng_sell_out(v, t, q) * (1.0 - fr) / spend
            trig = None
            if val >= 1.10: trig = "take-profit"
            elif val <= 0.80: trig = "stop-loss"
            elif X is not None and sold is not None and sold >= X * 1e9: trig = "big-sell"
            if trig:
                a_t = max(row["cc"] + d_react, P["cc_sell"])
                if a_t < a_sell: a_sell = a_t; why = trig; a_dec = row["cc"]
    # our sell on the state just before a_sell
    vv, tt = P["v"], P["t"]
    for cc_, v_, t_ in states:
        if cc_ < a_sell: vv, tt = v_, t_
        else: break
    gross = vv * q // (tt + q)
    net = gross - PM.fees(gross, P["sfb"], P["scb"])
    pnl = P["pnl"] + (net - P["net_live"])
    return dict(net=net, pnl=pnl, score=pnl + P["rb"], a_sell=a_sell, why=why, first_other=first, dropped=dropped, mism=mism, n_states=len(states),
                blocked=blocked)
