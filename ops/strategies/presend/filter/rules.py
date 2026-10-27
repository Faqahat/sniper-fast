#!/usr/bin/env python3
"""PRESEND FILTER: the candidate rules, FROZEN at 10-27 07:54 PKT from the dev search (AMS r24 + r25 only), before any validation
outcome was looked at. Each candidate = (name, kind, arm(w) or None, send(w, k) or None). sim.py evaluates them."""
import numpy as np
import sim


def oth_since(w, k):
    """other wallets' trades (not the whale, not us) after the trigger, on what the engine had seen when it signed try k"""
    rows = sim.known_rows(w, k)
    if rows is None: return 0
    kt = w["X"]["k_trig"]; wh = w["X"]["whale"]
    r = rows[kt + 1:]
    return int(((r[:, 3] != wh) & ~np.isin(r[:, 3], list(sim._cache["ours"]))).sum())


def score4(w):
    """'bot attention' points (signals picked on chain-wide TUNING events, a3_chain.py / x4_score.py): quiet trigger slot, no cohort bot
    holding, < 2 follower bots ever traded it, the whale's earlier dumps drew < 2.24 buyers (or none known)"""
    return (int(w.get("since_last", 0) >= 1) + int(w.get("coh_hold", 0) == 0) + int(w.get("fb_n", 0) < 2) + int(w.get("wh_dump_fol", -1) < 2.24))


def ok(w): return w.get("chain_ok", False)


CANDIDATES = [
    ("C1 send tries only after >= 2 other trades since the trigger", "DURING", None, lambda w, k: oth_since(w, k) >= 2),
    ("C2 skip if the last trade before the trigger is > 5 slots old", "ARM", lambda w: not (ok(w) and w["since_last"] > 5), None),
    ("C3 skip if no trade in the 50 slots before the trigger", "ARM", lambda w: not (ok(w) and w["n_tr_50"] < 1), None),
    ("C5 stop the window at trigger + 6 slots if < 2 other trades since the trigger", "DURING", None,
     lambda w, k: not (w["X"]["tries"][k][0] >= w["trig_slot"] + 6 and oth_since(w, k) < 2)),
    ("C8 skip if no cohort / follower bot ever traded the token", "ARM", lambda w: not (ok(w) and w["coh_n"] == 0 and w["fb_n"] == 0), None),
    ("C10 skip if attention score >= 3 and whale buy < 3 SOL", "ARM", lambda w: not (ok(w) and score4(w) >= 3 and w["whale_sol"] < 3), None),
    ("C11 skip if attention score == 4", "ARM", lambda w: not (ok(w) and score4(w) == 4), None),
]


# ---------------------------------------------------------------------------------------------------------------------------
# ADDED 10-27 ~08:05 PKT, AFTER the first validation look (v1_validate.py). Not part of the frozen set above.
#   C5a  : C5 with M = 1 (stop at trigger + 6 if NO other trade since the trigger); it was already in the dev search (x2_during [23])
#   QUIET: C11 with the whale's dump history limited to the last 24 h (what an engine would keep in memory) + C5.
#          C11's four signals and thresholds come from the chain-wide TUNING events (a3_chain.py), frozen before validation;
#          the 24 h window and the union with C5 were chosen after seeing validation => its validation numbers are optimistic.
_WDF = {}


def wh_dump_fol_24h(w, hours=24):
    """the whale's earlier dumps (sell >= 0.3 SOL that dropped the price >= 8%, curve < 100 SOL), closed (slot + 2) before the trigger
    slot and in the last `hours` h: mean count of distinct other wallets buying in the dump's slot (after it) and the next 2 slots; -1 = none"""
    key = (w["run"], w["seg"], w["w"], hours)
    if key in _WDF: return _WDF[key]
    if "du" not in _WDF:
        import json, collections
        from chainlib import B
        E = np.load(f"{B}/events.npz"); I = json.load(open(f"{B}/ids.json"))
        du = collections.defaultdict(list)
        for k in range(len(E["du_w"])): du[I["w"][int(E["du_w"][k])]].append((int(E["du_s"][k]), int(E["du_bt"][k]), int(E["du_nf"][k])))
        _WDF["du"] = du
    tb = w["t"] / 1e9
    x = [nf for s, bt, nf in _WDF["du"].get(w["whale"], []) if s + 2 < w["trig_slot"] and bt >= tb - hours * 3600]
    v = float(np.mean(x)) if x else -1.0
    _WDF[key] = v
    return v


def quiet_arm(w):
    """True = arm. Skip when ALL four quiet signals hold at the trigger"""
    if not ok(w): return True
    q = (w["since_last"] >= 1) and (w["coh_hold"] == 0) and (w["fb_n"] < 2) and (wh_dump_fol_24h(w) < 2.24)
    return not q


def c5_send(w, k, N=6, M=2):
    return not (w["X"]["tries"][k][0] >= w["trig_slot"] + N and oth_since(w, k) < M)


POSTHOC = [
    ("C5a stop the window at trigger + 6 slots if NO other trade since the trigger", "DURING", None, lambda w, k: c5_send(w, k, 6, 1)),
    ("C11-24h skip if all 4 quiet signals (whale dump history: last 24 h)", "ARM", quiet_arm, None),
    ("QUIET = C11-24h + C5", "ARM+DURING", quiet_arm, c5_send),
]
