#!/usr/bin/env python3
"""MULTIARM step 2 [check of the port]: the Python re-arm rule R0 (ma_lib) on the recorder tape vs what the engine decided.
  r38 (live dip26 re-arm): every live re-arm candidate record (presend_live_skip kind rearm: age / untradeable / no_holder / blocked_*,
      presend_live_rearm_defer, presend_live_arm kind rearm) matched by the dump's signature to the port's candidates; the live
      windows' ends (disarm why / time) vs the port's natural end (windows not filled / superseded).
  r37 (observatory R0 shadow, log-only): rearm_cand verdicts and rearm_window ends vs the port.
Also: the clock anchors (feed-arrival A, landing B) and their spread.
usage: ma2_validate.py X.pkl TAB OUT.json"""
import sys, json, pickle, hashlib, collections, statistics
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/multiarm")
import ma_lib as M


def sigh(sig): return int.from_bytes(hashlib.blake2b(sig.encode(), digest_size=8).digest(), "little")


def start_slot(tape, A, t_ms):
    lo, hi = tape.s_lo, tape.s_hi
    while lo < hi:
        m = (lo + hi) // 2
        if tape.cc(m, 0) + A(m) < t_ms: lo = m + 1
        else: hi = m
    return lo


def main(xp, tab, outp):
    X = pickle.load(open(xp, "rb")); tape = M.Tape(tab)
    A = M.Anchor(tape, X["trade_obs"]); B = M.Anchor(tape, X["land_obs"])
    out = {"run": X["meta"]["run"]}
    # anchor spread: leave-one-in residuals of the trade observations vs A
    res = [t - tape.cc(s, i) - A(s) for s, i, t in X["trade_obs"][::20] if tape.s_lo <= s <= tape.s_hi]
    resB = [t - tape.cc(s, i) - B(s) for s, i, t in X["land_obs"][::10] if tape.s_lo <= s <= tape.s_hi]
    out["anchor_resid_ms"] = {"A_p10_p50_p90": [float(np.percentile(res, q)) for q in (10, 50, 90)], "B_p10_p50_p90": [float(np.percentile(resB, q)) for q in (10, 50, 90)],
                              "B_minus_A_median": float(np.median([B(s) - A(s) for s, i, t in X["land_obs"][::50] if tape.s_lo <= s <= tape.s_hi]))}
    t_start = X["cfg"]["t"] / 1e6
    s0 = start_slot(tape, A, t_start)
    out["start_slot"] = s0
    R0 = M.Rule("R0")
    # every token created after the start
    mints = [m for m, c in tape.creates.items() if c["slot"] >= s0]
    port = {}   # sigh -> candidate
    for m in mints:
        tl = tape.tok(m)
        for c in M.candidates(tape, tl, R0, A, s0):
            k = c["k"]
            c["mint"] = m; c["slot"] = int(tl.s[k]); c["idx"] = int(tl.i[k])
            port[(m, int(tl.s[k]), int(tl.i[k]))] = c
    out["port_candidates"] = collections.Counter(str(c["skip"]) for c in port.values())
    # live records (r38) or observatory candidates (r37)
    live = {}
    for r in X["skips"]:
        if r.get("kind") != "rearm": continue
        d = r["dump"]; live[(r["mint"], d["slot"], d["idx"])] = {"why": r["why"], "rec": r}
    for r in X["defers"]:
        d = r["dump"]; live.setdefault((r["mint"], d["slot"], d["idx"]), {"why": "deferred", "rec": r})
    for W in X["wins"]:
        if W["kind"] != "rearm": continue
        tg = W["trig"]; live[(W["mint"], tg["slot"], tg["idx"])] = {"why": "window", "W": W}
    for r in X["obs_cand"]:
        d = r["dump"]; key = (r["mint"], d["slot"], d["idx"])
        if key not in live: live[key] = {"why": "obs_" + r.get("verdict", "?"), "rec": r, "obs": True}
    # agreement table
    tab_ = collections.Counter(); miss = collections.Counter(); exm = collections.defaultdict(list)
    t_lo = min((tape.cc(k[1], k[2]) + A(k[1]) for k in live), default=0)
    for key, L in list(live.items()):
        if key[1] > tape.s_hi - 60 or key[1] < s0: live.pop(key); continue
    for key, L in live.items():
        c = port.get(key)
        lw = L["why"]
        pw = "missing" if c is None else (c["skip"] or "window")
        tab_[(lw, pw)] += 1
        if len(exm[(lw, pw)]) < 3: exm[(lw, pw)].append(key)
    for key, c in port.items():
        if key in live: continue
        tc = tape.cc(key[1], key[2]) + A(key[1])
        if tc < t_lo or tc > X["meta"]["t1"] / 1e6: continue
        miss[c["skip"] or "window"] += 1
        if len(exm[("not_in_live", c["skip"] or "window")]) < 3: exm[("not_in_live", c["skip"] or "window")].append(key)
    out["agree"] = {f"{a} | port {b}": n for (a, b), n in sorted(tab_.items(), key=lambda x: -x[1])}
    out["port_only"] = dict(miss)
    out["examples"] = {f"{a} | {b}": [list(map(str, k)) for k in v] for (a, b), v in exm.items()}
    # window ends: live (not filled / superseded) vs the port's natural end from the live arm
    ends = []
    s_last = tape.s_hi - 60
    for W in X["wins"]:
        if W["kind"] != "rearm" or not W["dis"] or W["en_slot"] > s_last: continue
        why = W["dis"]["why"]
        tl = tape.tok(W["mint"]); re = W["rearm"]
        arm_slot = re.get("arm_slot") or re.get("check_slot")
        t_arm = re["arm_t"] / 1e6
        k_from = None
        if re.get("deferred"):
            k_from = next((k for k in range(tl.n) if tl.c[k] + A(int(tl.s[k])) >= t_arm), tl.n)
        pt, pw, pk = M.natural_end(tape, tl, R0, A, t_arm, arm_slot, W["en_slot"], k_from)
        ends.append({"w": W["w"], "live_why": why, "port_why": pw, "dt_ms": (W["dis"]["t"] / 1e6 - pt) if W["dis"].get("t") else None, "filled": bool(W["fills"])})
    for r in X["obs_win"]:
        e = r.get("end") or {}
        if not e.get("why") or r["en_slot"] > s_last or r["arm"]["slot"] < tape.s_lo: continue
        tl = tape.tok(r["mint"])
        pt, pw, pk = M.natural_end(tape, tl, R0, A, r["arm"]["t"] / 1e6, r["arm"]["slot"], r["en_slot"])
        ends.append({"w": "obs", "live_why": "obs_" + e["why"], "port_why": pw, "dt_ms": e["t"] / 1e6 - pt if e.get("t") else None, "filled": False})
    agg = collections.Counter((e["live_why"], e["port_why"]) for e in ends)
    out["ends_agree"] = {f"{a} | port {b}": n for (a, b), n in sorted(agg.items(), key=lambda x: -x[1])}
    dts = collections.defaultdict(list)
    for e in ends:
        if e["dt_ms"] is not None and e["live_why"].replace("obs_", "") == e["port_why"]: dts[e["port_why"]].append(e["dt_ms"])
    out["ends_dt_ms"] = {k: [round(float(np.percentile(v, q)), 1) for q in (10, 50, 90)] + [len(v)] for k, v in dts.items()}
    # arm time: live arm - (check slot start + A)
    da = []
    for W in X["wins"]:
        if W["kind"] != "rearm" or W["rearm"].get("deferred") or W["en_slot"] > s_last: continue
        cs = W["rearm"]["check_slot"]
        da.append(W["rearm"]["arm_t"] / 1e6 - (tape.slot_start_cc(cs) + A(cs)))
    for r in X["obs_win"]:
        cs = r["arm"]["slot"]
        if tape.s_lo <= cs <= tape.s_hi: da.append(r["arm"]["t"] / 1e6 - (tape.slot_start_cc(cs) + A(cs)))
    if da: out["arm_dt_ms"] = [round(float(np.percentile(da, q)), 1) for q in (10, 50, 90)] + [len(da)]
    json.dump(out, open(outp, "w"), indent=1, default=str)
    print(json.dumps(out, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
