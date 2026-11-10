#!/usr/bin/env python3
"""MULTIARM step 3: one run's replay context [MEASURED inputs].
  * the live windows (T2 + re-arm) as custom37/c37lib windows on this tape (our trades out, token accounting), and the run's
    measured distributions (c37lib.run_ctx: landing latency L of every real landed try, unseen share, sell landing delay D, close
    delay C, timer lateness tau, slot-backstop lateness, QUIET decision lateness)
  * the clock anchors: A (feed arrival of chain trades), B (our tries' landing seen), and the send-slot offset (off_s - off)
  * the re-arm port's calibration vs the live / observatory records (ma2_validate): arm time and end times (live - port, ms)
  * ATA close: landed slots after our sell's landing (MEASURED), first try after the arm (T2 +51 ms, re-arm +4 ms)
  * the evaluation span: from the engine start to the tape end - 2 min (T2 triggers and re-arm checks inside it)
usage: ma3_ctx.py X.pkl TAB VAL.json OUT.pkl"""
import sys, json, pickle, collections
import numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/custom37")
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/multiarm")
import c37lib as L
import ma_lib as M


def tape_rows(tape, mint, s0, lo=3, hi=160):
    t = tape.trades(mint)
    if t is None: return []
    t = t[(t["slot"] >= s0 - lo) & (t["slot"] <= s0 + hi)]
    ids = tape.ids
    return [(int(x["slot"]), int(x["idx"]), int(x["j"]), int(x["buy"]), int(x["sol"]), int(x["tok"]), int(x["vsol"]), int(x["vtok"]), ids[int(x["user"])]) for x in t]


def prep_live(tape, W):
    rows = tape_rows(tape, W["mint"], W["trig"]["slot"])
    if not rows: return None
    P = L.prep_window(W, rows, tape.cc)
    if P is None: return None
    P.cc = tape.cc
    def pos_of(c, maxi=tape.maxi):
        s = int(c // L.SMS); m = maxi.get(s, 400) + 1.0
        return s, int(min(m - 1, max(0, (c - s * L.SMS) / L.SMS * m)))
    P.pos_of = pos_of
    P.rx_map = {(r[0], r[1], r[2]): r[3] / 1e6 for r in W.get("ptape", []) if r[4] not in L.OURS}
    return P


def ata_clear_samples(X):
    """live re-arm windows armed after an "ata_open" wait: arm time - our last sell landing on the token (ms)"""
    sells = collections.defaultdict(list)
    for W in X["wins"]:
        c = W["close"]
        if c and c.get("sell_land") and len(c["sell_land"]) > 2: sells[W["mint"]].append(c["sell_land"][2] / 1e6)
    out = []
    for W in X["wins"]:
        if W["kind"] != "rearm" or W["rearm"].get("deferred") != "ata_open": continue
        a = W["rearm"]["arm_t"] / 1e6
        prev = [x for x in sells[W["mint"]] if x < a]
        if prev and a - max(prev) < 10_000: out.append(a - max(prev))
    return out


def main(xp, tab, valp, outp):
    X = pickle.load(open(xp, "rb")); tape = M.Tape(tab); val = json.load(open(valp))
    A = M.Anchor(tape, X["trade_obs"]); B = M.Anchor(tape, X["land_obs"])
    s_end = tape.s_hi - 600                      # 2 min before the tape end: windows + exits inside the tape
    t_start = X["cfg"]["t"] / 1e6
    t_end = tape.cc(s_end, 0) + A(s_end)
    wins = []
    for W in X["wins"]:
        if W["trig"]["slot"] > s_end or W["trig"]["slot"] < tape.s_lo + 10: continue
        P = prep_live(tape, W)
        if P is None: continue
        wins.append(P)
    R = L.run_ctx(X["meta"]["run"], wins, tape.cc)
    lc = X["cfg"]["presend_live"]
    for P in wins: P.live_exit_slots = lc.get("exit_slots") or 2; P.live_exit_ms = lc.get("exit_ms") or 10 ** 9
    q = []
    for P in wins:
        d = P.dis; lq = L.live_qstop(P)
        if d and d["why"] == "quiet" and lq and P.W["kind"] == "t2": q.append(d["t"] / 1e6 - (P.off_s + (P.s0 + lq[0]) * L.SMS))
    R.b_q = float(np.median(q)) if q else 12.0
    # send-slot offset vs the landing anchor, landing anchor vs B(slot) (MEASURED on windows with own tries)
    offs_rel = [P.off_s - P.off for P in wins if not P.off_est]
    own_vs_B = [P.off - B(P.s0) for P in wins if not P.off_est]
    first = collections.defaultdict(list)
    for P in wins:
        if not P.tries: continue
        t_arm = P.W["rearm"]["arm_t"] / 1e6 if P.W["kind"] == "rearm" else P.t_trig
        first[P.W["kind"]].append(P.tries[0]["t"] - t_arm)
    # ATA close: landed slot - our sell's landing slot
    sells = collections.defaultdict(list)
    for W in X["wins"]:
        if W["close"] and W["close"].get("sell_land"): sells[W["mint"]].append(W["close"]["sell_land"][0])
    dsl = []
    for r in X["atas"]:
        if r.get("ev") == "presend_live_ata_close" and r.get("ok") and r.get("slot"):
            prev = [s for s in sells.get(r["mint"], []) if s <= r["slot"]]
            if prev: dsl.append(r["slot"] - max(prev))
    # ATA clear (MEASURED): our token account counts as open until the engine has read it empty, closed it and polled the close
    # (pslive.rs ATA flow): live re-arm windows that waited on "ata_open" armed this long after our sell's landing. Runs without live
    # re-arm use the saved r38 sample (ata_clear.json)
    acl = ata_clear_samples(X)
    if len(acl) >= 10: json.dump({"run": X["meta"]["run"], "ms": acl}, open("/home/it/sniper-data/insider/ata_clear_" + X["meta"]["run"] + ".json", "w"))
    else:
        try: acl = json.load(open("/home/it/sniper-data/multiarm/ata_clear.json"))["ms"]
        except FileNotFoundError: acl = [2320.0]
    # port calibration (live - port): arm time, ends by reason
    end_dt = {k: v[1] for k, v in (val.get("ends_dt_ms") or {}).items()}
    cal = {"arm_dt": (val.get("arm_dt_ms") or [0, 13.5])[1], "end_dt": end_dt, "first_t2": float(np.median(first["t2"])) if first["t2"] else 51.1,
           "first_re": float(np.median(first["rearm"])) if first.get("rearm") else 4.0, "offs_rel": float(np.median(offs_rel)), "own_vs_B": float(np.median(own_vs_B)),
           "ata_dslots": dsl or [3], "ata_clear_ms": acl, "iv": 26.5, "t_start": t_start, "t_end": t_end, "s_end": s_end}
    Rd = {k: getattr(R, k) for k in ("L", "p_unseen", "D", "C", "tau", "b_exp", "b_back", "b_ws", "first", "b_q")}
    Rd["k_eff"] = None
    ctx = {"run": X["meta"]["run"], "tab": tab, "cfg": X["cfg"], "cal": cal, "R": Rd, "xp": xp,
           "live_keys": [(P.W["kind"], P.W["w"]) for P in wins]}
    pickle.dump(ctx, open(outp, "wb"))
    print({k: (v if not isinstance(v, list) else (len(v), float(np.median(v)))) for k, v in cal.items()})
    print({k: (float(np.median(v)) if isinstance(v, np.ndarray) else v) for k, v in Rd.items()}, "windows", len(wins), collections.Counter(P.W["kind"] for P in wins))


if __name__ == "__main__":
    main(*sys.argv[1:5])
