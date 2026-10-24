#!/usr/bin/env python3
# READ-ONLY, offline replay engine. Re-runs an exit rule on the wallet's REAL entry (same buy SOL / tokens / slot) over the
# token's market path. Other traders' intents are kept (buys = fixed SOL in, sells = fixed tokens in) and re-priced on the
# simulated curve, so our different sells move the later prices consistently (constant-product pump.fun curve, K fixed).
# Costs: real all-in buy cost (incl. 1% AKbot); each sell nets curve SOL x (1 - 1.25% pump fee) x (1 - 1% AKbot) - 0.00042 SOL
# (priority + tip, measured), + 0.00204 SOL rent back on the clearing sell.
# Rule triggers are evaluated after every market trade ("price event"), AKbot order: drawdown, follow-dev, take-profit, stop
# loss; lightning sell and timeout are time based. A triggered sell executes right after the triggering trade (same slot),
# which is what the wallets achieve on chain (measured: most reactions land in the same slot).
import sys, os, json, math, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

SELL_OVERHEAD = 0.00042; RENT = 0.00204; SLOT_S = 0.2125   # measured slot time (283 slots = 60 s)

def path_for(a):
    """market path rows for an aligned token (collector) or a fetched one (cache/paths)."""
    if a.get("src") == "fetched":
        return json.load(open(os.path.join(EXITS, "cache", "paths", a["mint"] + ".json")))["rows"]
    tr, _ = trades_of(a["mint"]); return tr

def simulate(rt, W, tr, dev, rule, actual=False, latency_events=0):
    """rt: round-trip record; W: wallet; tr: market path; dev: set of dev wallets; rule: dict. Returns dict(pnl, sells=[...], forced)."""
    own = {l["sig"] for l in rt["legs"]}
    kb = next(k for k, t in enumerate(tr) if t["sig"] == rt["legs"][0]["sig"] and t["user"] == W)
    b = tr[kb]
    vs, vt = b["vsol"], b["vtok"]                    # state right after our real buy
    pos = float(b["tok"]); pos0 = pos
    entry = b["sol"] / b["tok"]                      # exec price of the buy (curve SOL / tokens)
    s0, bt0 = b["s"], b["bt"]
    sells = []; proceeds = 0.0
    hold = collections.defaultdict(float); bought = collections.defaultdict(float)
    for t in tr[:kb]:
        if t["buy"]: hold[t["user"]] += t["tok"]; bought[t["user"]] += t["tok"]
        else: hold[t["user"]] = max(0.0, hold[t["user"]] - t["tok"])
    st = dict(peak=vs / vt, phase=0, tp_ref=None, dd_ref=None, dd_on=False, light=False, done=False, rep_ref=None, last_rep_slot=None)
    actual_sells = {l["sig"]: l for l in rt["legs"] if l["side"] == "sell"}
    def sell(frac, why, slot, tok=None):
        nonlocal vs, vt, pos, proceeds
        if pos <= 0: return
        q = pos * frac if tok is None else min(pos, tok)
        minsell = rule.get("min_sell_sol", 0.0)
        if tok is None and minsell and (pos - q) * (vs / vt) / 1e9 < minsell: q = pos       # remainder below minimum -> clear
        out = curve_sell_out(q, vs, vt)
        vs -= out; vt += q; pos -= q
        net = out / 1e9 * (1 - 0.0125) * (1 - 0.01) - SELL_OVERHEAD + (RENT if pos <= 1 else 0)
        proceeds += net; sells.append(dict(slot=slot, dslot=slot - s0, frac=q / (q + pos), mult=(out / q) / entry if q else None, sol=out / 1e9, net=net, why=why))
        if pos <= 1: pos = 0.0; st["done"] = True
    pending = []                                      # (events left, frac, why) for latency > 0
    for k in range(kb + 1, len(tr)):
        if st["done"]: break
        t = tr[k]
        # time-based triggers happen before this event if its slot is past the deadline
        if not actual:
            L = rule.get("lightning")
            if L and not st["light"] and t["s"] >= s0 + L["delay"]:
                st["light"] = True; sell(L["frac"], "lightning", t["s"])
            T = rule.get("timeout_s")
            t_ref = st["last_tp_slot"] if (rule.get("timeout_from") == "last_tp" and st.get("last_tp_slot")) else s0
            if T and not st["done"] and t["s"] - t_ref >= T / SLOT_S:
                sell(1.0, "timeout", t["s"])
            if st["done"]: break
        if t["user"] == W:
            if actual and t["sig"] in actual_sells and not t["buy"]:
                sell(None, "actual", t["s"], tok=t["tok"])
            continue
        # apply the other trader's intent to the simulated curve
        u = t["user"]
        if t["buy"]:
            out = curve_buy_out(t["sol"], vs, vt); vs += t["sol"]; vt -= out
            hold[u] += t["tok"]; bought[u] += t["tok"]
        else:
            dh = sum(hold[d] for d in dev); db = sum(bought[d] for d in dev)
            gout = curve_sell_out(t["tok"], vs, vt); vs -= gout; vt += t["tok"]
            if u in dev and not actual:
                frac_dev = t["tok"] / dh if dh > 0 else 1.0
                cum = 1 - (dh - t["tok"]) / db if db > 0 else 1.0
                F = rule.get("follow_dev")
                if F and pos > 0:
                    if cum >= F.get("clear_at", 2.0) or frac_dev >= F.get("clear_on_frac", 2.0): pending.append([latency_events, 1.0, "dev-clear"])
                    elif F.get("mirror"): pending.append([latency_events, min(1.0, frac_dev * F.get("mirror", 1.0)), "dev-mirror"])
            hold[u] = max(0.0, hold[u] - t["tok"])
        if actual or pos <= 0: continue
        p = vs / vt; m = p / entry
        # pending reactions
        for pe in pending: pe[0] -= 1
        for pe in [pe for pe in pending if pe[0] < 0]:
            pending.remove(pe); sell(pe[1], pe[2], t["s"])
            if st["done"]: break
        if st["done"]: break
        # drawdown (AKbot: activation gain from entry, drawdown from running reference, sell % of remaining, repeatable)
        D = rule.get("drawdown")
        if D:
            if not st["dd_on"] and m >= 1 + D["act"]: st["dd_on"] = True; st["dd_ref"] = p; st["dd_peak"] = p
            if st["dd_on"]:
                if p > st["dd_peak"]: st["dd_peak"] = p; st["dd_ref"] = p      # only a NEW peak moves the reference (AKbot doc)
                if p <= st["dd_ref"] * (1 - D["dd"]):
                    sell(D["frac"], "drawdown", t["s"]); st["dd_ref"] = p       # reference resets to the trigger price
                    if st["done"]: break
                    continue
        # take-profit ladder: cumulative gains from entry; highest reached phase only; sell % of remaining
        TP = rule.get("tp")
        if TP:
            reached = st["phase"]
            while reached < len(TP) and m >= 1 + TP[reached][0]: reached += 1
            if reached > st["phase"]:
                st["phase"] = reached; sell(TP[reached - 1][1], f"tp{reached}", t["s"]); st["rep_ref"] = p; st["last_tp_slot"] = t["s"]
                if st["done"]: break
                continue
            R = rule.get("tp_repeat")                 # after the last phase: every +step (price) sell frac of remaining
            if R and st["phase"] == len(TP) and st["rep_ref"] and p >= st["rep_ref"] * (1 + R["step"]):
                sell(R["frac"], "tp-repeat", t["s"]); st["rep_ref"] = p
                if st["done"]: break
                continue
        SL = rule.get("stop_loss")
        if SL is not None and m <= 1 - SL:
            sell(1.0, "stop", t["s"])
            if st["done"]: break
        TR = rule.get("trail_clear")                  # clear everything on a drawdown from the peak (after activation)
        st["peak"] = max(st["peak"], p)
        if TR and st["peak"] / entry >= 1 + TR["act"] and p <= st["peak"] * (1 - TR["dd"]):
            sell(1.0, "trail", t["s"])
            if st["done"]: break
    forced = False
    if pos > 1:
        forced = True; sell(1.0, "end-of-path", tr[-1]["s"])
    return dict(pnl=proceeds - rt["cost"], proceeds=proceeds, sells=sells, forced=forced)
