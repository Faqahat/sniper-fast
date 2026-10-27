#!/usr/bin/env python3
"""PRESEND FILTER: evaluate a rule on the measured windows (score.py's pre-registered rule).
A rule = (arm, send):
  arm(w)          -> False skips the whole window (w: the window row of windows.json + 'X' = its tapes.pkl entry)
  send(w, k)      -> False drops try k of the window (k = index into X['tries']); it may use the token's trades up to that try's
                     'pos' (the latest trade the engine had seen when it signed it) and nothing later
Per window: fees kept = the fees of the tries sent; the fill is kept only if its own try is sent.
Counterfactual cost when a DURING rule drops a fill: the window would have kept sending until its end (live stopped at the fill):
charged as (window end slot - fill slot) x k tries x the run's mean failed fee per try (INFERRED, small)."""
import json, pickle, collections
import numpy as np

B = "/home/moiz/sniper-data/presend_filter"
_cache = {}


def load(runs=None, size=None):
    if "W" not in _cache:
        W = json.load(open(f"{B}/windows.json"))
        T = pickle.load(open(f"{B}/tapes.pkl", "rb"))
        _cache["ours"] = set(x for x in T["ours"] if x is not None)
        for w in W:
            w["X"] = T["out"][(w["run"], w["seg"], w["w"])]
            w["key"] = (w["run"], w["seg"], w["w"])
        # per run: mean failed fee per try, tries per slot
        per = collections.defaultdict(lambda: [0, 0])
        for w in W:
            per[w["run"]][0] += w["fail_fee"]; per[w["run"]][1] += w["n_att"]
        _cache["fee_per_try"] = {r: a / max(b, 1) for r, (a, b) in per.items()}
        _cache["W"] = W
    W = _cache["W"]
    if runs: W = [w for w in W if w["run"] in runs]
    return W


def known_rows(w, k):
    """the token's tape rows the engine had seen when it signed try k (chain order, up to and including the try's pos)"""
    X = w["X"]; tape = X["tape"]
    if tape is None: return None
    pos = X["tries"][k][7]
    key = tape[:, 0] * (1 << 24) + tape[:, 1] * 64 + tape[:, 2]
    n = int(np.searchsorted(key, pos[0] * (1 << 24) + pos[1] * 64 + pos[2], side="right"))
    return tape[:n]


def evaluate(W, arm=None, send=None, net_key="net", k_per_slot=None):
    """returns per-run and total dicts (SOL)"""
    out = collections.defaultdict(lambda: collections.defaultdict(float))
    fee_rate = _cache["fee_per_try"]
    for w in W:
        r = out[w["run"]]; tot = out["ALL"]
        v_net = (w.get(net_key) or 0) if w["filled"] else 0
        before = v_net - w["fail_fee"]
        if arm is not None and not arm(w):
            after = 0; fill_kept = False; fee_kept = 0
        else:
            tries = w["X"]["tries"]
            if send is None:
                fee_kept = w["fail_fee"]; fill_kept = w["filled"]
            else:
                fee_kept = 0; fill_kept = False; fill_seen = False
                for k, t in enumerate(tries):
                    ok = send(w, k)
                    if ok: fee_kept += t[3]
                    if t[4]:
                        fill_seen = True; fill_kept = ok
                if w["filled"] and not fill_seen: fill_kept = True
                if w["filled"] and not fill_kept:
                    kk = k_per_slot or (8 if w["run"] == "ams:r19" else 4)
                    fee_kept += max(w["en_slot"] - w["fill_slot"], 0) * kk * fee_rate[w["run"]]
            after = (v_net if fill_kept else 0) - fee_kept
        for d in (r, tot):
            d["before"] += before / 1e9; d["after"] += after / 1e9; d["windows"] += 1
            if arm is not None and not arm(w): d["windows_skipped"] += 1
            if w["filled"]:
                d["fills"] += 1
                if fill_kept: d["fills_kept"] += 1
                else:
                    if v_net > 0: d["win_rm"] += 1; d["win_rm_sol"] += v_net / 1e9
                    else: d["lose_rm"] += 1; d["lose_rm_sol"] += v_net / 1e9
                    if w.get("y_nb") == 0: d["notrade_rm"] += 1
                if w.get("y_nb") == 0: d["notrade"] += 1
            d["fees_saved"] += (w["fail_fee"] - (fee_kept if not (arm is not None and not arm(w)) else 0)) / 1e9 if True else 0
    for d in out.values(): d["gain"] = d["after"] - d["before"]
    return {k: dict(v) for k, v in out.items()}


def fmt(res, runs=None):
    s = []
    for k in (runs or [k for k in res if k != "ALL"]) + ["ALL"]:
        if k not in res: continue
        d = res[k]
        s.append(f"{k:8s} {d['before']:+.3f} -> {d['after']:+.3f} ({d['gain']:+.3f}) fills {int(d.get('fills_kept', 0))}/{int(d.get('fills', 0))} "
                 f"win_rm {int(d.get('win_rm', 0))} ({d.get('win_rm_sol', 0):+.3f}) lose_rm {int(d.get('lose_rm', 0))} ({d.get('lose_rm_sol', 0):+.3f}) "
                 f"notrade_rm {int(d.get('notrade_rm', 0))}/{int(d.get('notrade', 0))} skipped {int(d.get('windows_skipped', 0))}")
    return "\n".join(s)
