#!/usr/bin/env python3
"""REPLAY_065: the live positions of AMS runs 24-25 (pre-send fills and regular M2 dip fills), joined with the chain tape, and
their replay at any size (core.py). Everything taken from the live records / chain is MEASURED; replay outputs are INFERRED."""
import math, collections
import numpy as np
import core, pmath as PM

SMS = core.SMS
WALLET = "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"


def ptime(t_ns):
    import time
    return time.strftime("%m-%d %H:%M:%S", time.gmtime(t_ns / 1e9 + 18000))


class P:
    def __init__(self, **kw): self.__dict__.update(kw)


def _round(sp):
    """a slippage (percent) that a bot would type: a multiple of 0.5 %, the 1 - 1/(1 + k%) form, or exactly 0"""
    if sp is None: return False
    if abs(sp) < 1e-6: return True
    if abs(sp * 2 - round(sp * 2)) < 0.006: return True
    k = (1.0 / (1.0 - sp / 100.0) - 1.0) * 100.0 if sp < 100 else None
    return k is not None and abs(k * 2 - round(k * 2)) < 0.006


def _implied(row, v0, t0):
    """the slippage (percent) this follower's decoded limit implies if it was quoted on the curve state (v0, t0)"""
    tr = row["tr"]; c = row["cls"]
    if c["kind"] == "quote" and c["lim"]:
        n = tr["sol"]
        q = t0 * (n - 1) // (v0 + n - 1) if row.get("form", "n1") != "floor" else t0 * n // (v0 + n)
        return (1 - c["lim"] / q) * 100 if q > 0 else None
    if c["kind"] == "tok" and c["lim"]:
        a = tr["tok"]
        if a >= t0: return None
        cst = PM.cost_exact_tok(v0, t0, a); cst += PM.fees(cst, tr["fbps"], tr["cbps"])
        return (c["lim"] / cst - 1) * 100
    return None


def _rows_and_forms(D, mint, buy_pos, end_slot, our_sigs):
    pre, ob, rows = core.prepare(D, mint, buy_pos, None, end_slot, our_sigs)
    T = D.tape[mint]["trades"]
    kb = next((q for q, t in enumerate(T) if ob is not None and t["sig"] == ob["sig"]), None)
    pos_of = {(t["sig"], t["j"]): q for q, t in enumerate(T)}
    # each recorded buy's own formula at its real pre-state (MEASURED), used again on the replayed state; then which curve state
    # its limit was quoted on (MEASURED from the decoded numbers): the state where its implied slippage is a round number.
    #   quoted on a state at or after OUR buy (incl. a CPI that computes its limit at execution: 0 % at its own pre-state)
    #     -> "requote": the limit moves with our buy, our size cannot break it;
    #   quoted on a state before our buy (typically the crash itself: it was in flight with us) -> "fixed": our bigger buy eats
    #     more of its slippage;  no round match -> "unclear" (treated as fixed; the sensitivity treats later-slot ones as requote)
    last = ob if ob is not None else pre
    for r in rows:
        if r["kind"] != "trade": continue
        tr = r["tr"]
        if last is not None and tr["buy"]: r["form"] = core.tok_formula(tr, last["vsol"], last["vtok"])
        r["ref"] = None
        if tr["buy"] and r["cls"]["kind"] in ("quote", "tok") and kb is not None:
            kf = pos_of.get((tr["sig"], tr["j"]))
            hits = []
            if kf is not None:
                for q in range(max(kb - 4, 0), kf):
                    sp = _implied(r, T[q]["vsol"], T[q]["vtok"])
                    if _round(sp): hits.append(q - kb)          # < 0: before our buy; 0: right after our buy; > 0: later
            r["ref"] = ("after" if hits and max(hits) >= 0 else "before" if hits else "unclear")
            r["ref_hits"] = hits
        r["requote"] = r.get("ref") == "after"
        last = tr
    return pre, ob, rows


def presend_positions(D):
    out = []
    for run, X in D.live.items():
        segs = {s["seg"]: s for s in X["segs"]}
        for (seg, w), W in X["ps"].items():
            if not W["fills"]: continue
            f = W["fills"][0]; mint = f["mint"]
            att = X["att"].get(f["sig"])
            ex = W["exits"][0]; sl = W["sells"][0]; cl = W["close"]; rz = W["realized"]
            buy_pos = (f["slot"], f["idx"])
            end_slot = max(sl["slot"], f["slot"] + 4) + 1
            our_sigs = {f["sig"], sl["sig"]}
            pre, ob, rows = _rows_and_forms(D, mint, buy_pos, end_slot, our_sigs)
            # the attempt's signing fee rate: the latest trade the engine had seen (att pos) -> its fee bps
            fr_sign = None
            if att:
                ps_ = att["pos"]
                tsig = next((t for t in D.tape[mint]["trades"] if (t["s"], t["i"], t["j"]) == tuple(ps_)), None)
                if tsig is not None: fr_sign = core.fee_rate_ps(tsig["fbps"], tsig["cbps"])
            sell_tr = next((t for t in D.tape[mint]["trades"] if t["sig"] == sl["sig"]), None)
            ac = next((a for a in X.get("ata_close", []) if a["seg"] == seg and a["mint"] == mint and a.get("slot", 0) >= sl["slot"]), None)
            tips_sell = sum(s[2] for s in cl["sell_sigs"] if s[1])
            out.append(P(kind="ps", run=run, seg=seg, w=w, mint=mint, t=f["t"], buy_pos=buy_pos, buy_sig=f["sig"], spend=segs[seg]["ps_spend"],
                         tokens=f["tokens"], n_live=f["sol_in"], buy_fee=f["fee"], tip=f["tip"], rent=-rz["buy_delta"] - segs[seg]["ps_spend"] - f["fee"] - f["tip"],
                         realized=rz["pnl"], buy_delta=rz["buy_delta"], exit_why=ex["why"], exit_slot=ex["slot"], exit_value=ex["value"], exit_t=ex["t"],
                         sell_pos=(sl["slot"], sl["idx"]), sell_sig=sl["sig"], sell_gross=sl["sol"], sell_fee=sl["fee"], sell_tips=tips_sell,
                         ata_delta=(ac or {}).get("delta"), att=att, fr_sign=fr_sign, pre=pre, ours_buy=ob, sell_tr=sell_tr, rows=rows, end_slot=end_slot,
                         trig=W["arm"]["trig"], land_slot=f["slot"], tape_rx={r["sig"]: r["t"] for r in X["tape"].get((seg, mint), [])}))
    return out


def regular_positions(D):
    out = []; failed = []
    for run, X in D.live.items():
        segs = {s["seg"]: s for s in X["segs"]}
        real = collections.defaultdict(list)
        for seg, m, p in X["log_reg_real"]: real[(seg, m)].append(p)
        used_sell = collections.Counter()
        for f in X["fires"]:
            seg, mint = f["seg"], f["mint"]
            nz = f.get("nonce") or {}
            cands = {f.get("buy_sig")} | {p.get("sig") for p in nz.get("per_path") or []} | {p.get("sig") for p in nz.get("variants") or []}
            cands.discard(None)
            bl = [b for k, b in X["buy_land"].items() if k[0] == seg and k[1] == mint and k[2] in cands]
            dump = next((t for t in D.tape[mint]["trades"] if t["sig"] == f.get("dump_sig")), None)
            g = segs[seg]
            if not bl:
                # a failed buy: its chain position and error (our failed tx in the recording)
                fl = [x for x in D.tape[mint]["fails"] if x[2] in cands]
                failed.append(P(kind="reg_fail", run=run, seg=seg, mint=mint, t=f.get("t_fire") or f.get("t"), fire=f, dump=dump, fails=fl, spend=f.get("spend"),
                                guard=g["guard"], min_out=f.get("min_out")))
                continue
            b = bl[0]
            buy_pos = (b["slot"], b["idx"])
            sells = X["reg_sell"].get((seg, mint), [])
            k = used_sell[(seg, mint)]; used_sell[(seg, mint)] += 1
            sl = sells[k] if k < len(sells) else None
            ex = (X["reg_exit"].get((seg, mint)) or [None] * (k + 1))[k]
            rz = real[(seg, mint)].pop(0) if real[(seg, mint)] else None
            hold = g["hold"]
            end_slot = max(sl["slot"] if sl else 0, b["slot"] + hold + 1) + 1
            buy_tx = next((t for t in D.tape[mint]["trades"] if t["sig"] == b["sig"]), None)
            sell_tx = next((t for t in D.tape[mint]["trades"] if sl and t["sig"] == sl["sig"]), None)
            our_sigs = {b["sig"]} | ({sl["sig"]} if sl else set())
            pre, ob, rows = _rows_and_forms(D, mint, buy_pos, end_slot, our_sigs)
            out.append(P(kind="reg", run=run, seg=seg, mint=mint, t=b["t"], fire=f, buy_pos=buy_pos, buy_sig=b["sig"], spend=f["spend"], tokens=b["tokens"], n_live=b["sol"],
                         realized=int(round(rz * 1e9)) if rz is not None else None, exit_why=(ex or {}).get("why"), exit_slot=(ex or {}).get("slot"), exit_t=(ex or {}).get("t"), exit_value=(ex or {}).get("value"),
                         sell_pos=(sl["slot"], sl["idx"]) if sl else None, sell_sig=(sl or {}).get("sig"), sell_gross=(sl or {}).get("sol"), sell_fee=(sl or {}).get("fee"),
                         dump=dump, guard=g["guard"], hold=hold, min_out=f.get("min_out"), pre=pre, ours_buy=ob, buy_tx=buy_tx, sell_tr=sell_tx, rows=rows,
                         end_slot=end_slot, land_slot=b["slot"], tape_rx={r["sig"]: r["t"] for r in X["reg_tape"].get((seg, mint), [])}))
    return out, failed


# ---------------------------------------------------------------------------------------------------------------------------
def value_ps(v, t, q, fb, cb, spend):
    fr = core.fee_rate_ps(fb, cb)
    return core.eng_sell_out(v, t, q) * (1.0 - fr) / spend


def value_reg(v, t, q, fb, cb, spend):
    fr = max(fb + cb, 1) / 1e4
    so = core.eng_sell_out(v, t, q) * (1.0 - fr) / 1e9
    return (so - 0.0008) / (spend / 1e9 + 0.0008)


def checked(p, row, last_chk):
    """did the engine run its TP / SL check on this trade before its time exit? (MEASURED rule on the live exits)
    live time-limit exit: every trade it received before that decision (its own receive times, the position's tape records);
    live TP / SL exit: the trades up to its trigger, and later ones in slots <= the last slot before the time limit"""
    rx = p.tape_rx.get(row["tr"]["sig"]) if row["kind"] == "trade" else None
    if p.exit_why == "time-limit":
        # a trade received in the last ~2 ms before the time exit was still queued when the exit fired (MEASURED: HZi3fcn6,
        # r24: three sells of slot entry + 2 received 0.7-1.1 ms before it, one of them below the stop-loss, not acted on)
        if row["s"] <= last_chk: return True
        if rx is not None: return rx < p.exit_t - 2_000_000
        return False
    if rx is not None and getattr(p, "live_trig_rx", None) is not None and rx <= p.live_trig_rx: return True
    return row["s"] <= last_chk


def replay(D, p, size, delays, cut=0.0, rng=None, cpi_free=False, force_live_exit=False, nolim=False, fmode="refined"):
    """one position at `size` lamports. delays: MEASURED median sell delays (ms of chain clock) by exit kind.
    Returns a dict (INFERRED unless size == live size, where it must reproduce the chain)."""
    ob = p.ours_buy
    fb, cb = ob["fbps"], ob["cbps"]
    pre = p.pre
    r = dict(size=size)
    # --- our buy limit at this size (the engine's formula) and pump's buy
    n = PM.net_of_budget(size, fb, cb)
    q = pre["vtok"] * (n - 1) // (pre["vsol"] + n - 1)
    if p.kind == "ps":
        a = p.att
        mo = core.limit_min_out(a["vsol"], a["vtok"], size, p.fr_sign, 0.12)
    else:
        d = p.dump
        mo = core.guard_min_out(d["vsol"], d["vtok"], size, d["fbps"], d["cbps"], p.guard)
    r.update(n=n, q=q, min_out=mo, filled=(mo is not None and q >= mo))
    if not r["filled"]:
        return r
    # --- the later trades on the replayed state (all of them up to end_slot), states after each row
    W = core.walk(D, p.mint, pre, p.rows, size, fb, cb, (10 ** 15, 0, 0), rng=rng, cut=cut, cpi_free=cpi_free, nolim=nolim, fmode=fmode, buy_slot=p.buy_pos[0])
    st = {k: (v, t, ap) for k, v, t, ap in W["states"]}
    # --- the exit decision
    spend = size
    land = p.land_slot
    if p.kind == "ps":
        last_chk = land + 1; tp, sl_ = 0.10, 0.20
    else:
        last_chk = land + p.hold - 2; tp, sl_ = None, 0.50
    dec = None
    for k, row in enumerate(p.rows):
        if k not in st: continue
        if not checked(p, row, last_chk): continue
        v, t, ap = st[k]
        if not ap: continue
        if row["kind"] == "trade":
            tfb, tcb = row["tr"]["fbps"], row["tr"]["cbps"]
        else:
            tfb, tcb = 95, 30
        if p.kind == "ps":
            val = value_ps(v, t, q, tfb, tcb, spend)
            if val >= 1.0 + tp: dec = ("take-profit", k, val); break
            if val <= 1.0 - sl_: dec = ("stop-loss", k, val); break
        else:
            val = value_reg(v, t, q, tfb, tcb, spend)
            if val <= 1.0 - sl_: dec = ("stop-loss", k, val); break
    why = dec[0] if dec else "time-limit"
    r["why"] = why
    r["dec_row"] = dec[1] if dec else None
    # --- where our sell lands
    live_dec_row = getattr(p, "live_dec_row", "unset")
    same = (why == p.exit_why) and (why == "time-limit" or (dec and dec[1] == live_dec_row))
    if force_live_exit or same:
        sp = p.sell_pos; r["sell_src"] = "live"
    elif dec:
        rw = p.rows[dec[1]]
        a = D.ck.cc(rw["s"], rw["i"]) + delays[p.kind + ":tpsl"]
        sp = D.ck.inv(a); sp = (sp[0], sp[1]); r["sell_src"] = "model_tpsl"
    else:
        a = (land + (2 if p.kind == "ps" else p.hold)) * SMS + delays[p.kind + ":time"]
        sp = D.ck.inv(a); sp = (sp[0], sp[1]); r["sell_src"] = "model_time"
    r["sell_pos"] = sp
    # the state just before our sell: every replayed row strictly before the sell position
    v, t = W["v_after"], W["t_after"]
    for k, row in enumerate(p.rows):
        if (row["s"], row["i"]) >= (sp[0], sp[1]): break
        if k in st: v, t = st[k][0], st[k][1]
    gross = PM.sell_sol(v, t, q)
    sfb, scb = (p.sell_tr["fbps"], p.sell_tr["cbps"]) if p.sell_tr else (fb, cb)
    net = gross - PM.fees(gross, sfb, scb)
    r.update(gross=gross, net=net, dropped=len([x for x in W["dropped"] if x[1] == "slip"]), dropped_all=W["dropped"], resurrected=len(W["resurrected"]))
    # realized as the engine books it: sell SOL after pump's fees - spend - every per-tx cost of the live trade (fees, tips,
    # rent: the same at any size; for pre-send they are read from the records, for regular buys they are the live total)
    r["pnl"] = net - size - p.costs
    return r
