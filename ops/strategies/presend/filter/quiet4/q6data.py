"""QUIET4: one table of every pre-send trigger of the 25 runs that the QUIET arm rule / the min-age skip can decide, with its signals and
its value under each stop rule (and at -20% followers where a replay exists). Used by q6_score.py.
  earlier 24 runs (pick set): live ARMED windows = REAL outcomes (realized x 0.696 / live size - 5120 lamports x landed failed tries;
      the size scaling is INFERRED, as QUIET3); the old QUIET's skips = CENSORED (no outcome; a rule that would arm them scores 0 there).
      Stop N:M = quiet3's stopgain on the measured per-slot "other trades" counts (a fill at slot offset >= N is blocked when fewer than M
      others traded through slot N-1; an unfilled window saves its tries after slot N); in the old QUIET-on runs (live stop 6:2) a looser
      stop than 6:2 is CENSORED (kept at the live outcome).
  r37 (test set): ARMED = live value at stop 5:2 (exact), other stops by the paired try-level replay; QUIET- / age-1- / blocked-skipped
      = VIRTUAL (phantom-try model, calibrated on live; INFERRED)."""
import json, pickle, datetime, collections
import numpy as np

D4 = "/home/it/sniper-data/presend_quiet4"
SIZE = 0.696; FAIL = 5120e-9
STOPS = [(3, 2), (4, 2), (5, 2), (6, 2), (7, 2), (8, 2), (4, 3), (5, 3), (6, 3), (7, 3), (8, 3)]
CUR = dict(F=4.0, k=4, fb=False, H=24, S=(5, 2), A=2, v2=None)
R37_H = (1793305231 - 1793241075) / 3600          # r37 session start -> tape end (h)


def pkt_hour(t_ns): return (datetime.datetime.fromtimestamp(t_ns / 1e9, datetime.UTC) + datetime.timedelta(hours=5)).hour


def stopgain(r, S):
    """quiet3's stop gain of N:M against no stop (SOL, at 0.696)"""
    if S is None: return 0.0
    N, M = S; o = r["oth"]
    if o[min(N - 1, 12)] >= M: return 0.0
    if r["isfill"]:
        fo = r["fill_off"] if r["fill_off"] is not None else 0
        return -r["v"] if fo >= N else 0.0
    end = r["end"]
    if end <= N or end <= 0: return 0.0
    return r["fee"] * (end - N) / end


def stops_it(r, S):
    """does stop S stop this window (by its slot N), on the measured counts"""
    if S is None: return False
    N, M = S
    return r["oth"][min(N - 1, 12)] < M


def build():
    J = json.load(open(f"{D4}/windows24.json")); F = json.load(open(f"{D4}/feats.json"))
    X = pickle.load(open(f"{D4}/win_r37.pkl", "rb")); V = pickle.load(open(f"{D4}/values_r37.pkl", "rb"))
    try: CT = json.load(open(f"{D4}/cut_train.json"))
    except Exception: CT = {}
    rows = []; hours = {}
    for k, m in J["meta"].items(): hours[k] = m["hours"]
    hours["r37AMS"] = R37_H
    for x, c in zip(J["windows"], F["w24"]):
        if not c.get("ok"): continue
        key = x["run"] + x["reg"]; m = J["meta"][key]; q = x.get("q") or {}
        if "since_last" in q: since, coh, fb, wf24 = q["since_last"], q["coh_hold"], q["fb_n"], q["wh_fol"]
        else: since, coh, fb, wf24 = c["since_last"], c["coh_hold"], c["fb_n"], c["wf24"]
        v2 = x.get("v2") or {}
        pnl = x["pnl"]; filled = pnl is not None
        r = dict(src="e", key=key, reg=x["reg"], kind="armed", t=x["t"], age=x["age"], since=since, coh=coh, fb=fb, wf24=wf24, wf12=c["wf12"], wf6=c["wf6"],
                 v2skip=bool(v2["skip"]) if "skip" in v2 else bool(c["v2skip"]), oth=c["oth"], isfill=filled, win=filled and pnl > 0, fill_off=x["fill_off"],
                 end=(x.get("dis_slot") or x["slot"]) - x["slot"], fee=x["n_fail"] * FAIL, live_stop=tuple(int(a) for a in m["stop"].split(":")) if m.get("stop") else None,
                 mint=x["mint"], slot=x["slot"], size=x["size"])
        r["v"] = (pnl or 0.0) * SIZE / x["size"] - r["fee"]
        cd = CT.get(key, {}).get(f"{x['mint']}:{x['slot']}")
        r["cutd"] = cd * SIZE / x["size"] if cd is not None else None
        rows.append(r)
    for x, c in zip(J["skips"], F["s24"]):
        if not c.get("ok") or x["why"] != "quiet": continue
        key = x["run"] + x["reg"]; q = x.get("q") or {}; v2 = x.get("v2") or {}
        rows.append(dict(src="e", key=key, reg=x["reg"], kind="cens", t=x["t"], age=x["age"], since=q["since_last"], coh=q["coh_hold"], fb=q["fb_n"], wf24=q["wh_fol"],
                         wf12=c["wf12"], wf6=c["wf6"], v2skip=bool(v2["skip"]) if "skip" in v2 else bool(c["v2skip"]), oth=c["oth"], isfill=False, win=False,
                         fill_off=None, end=0, fee=0.0, live_stop=(6, 2), v=0.0, cutd=None, mint=x["mint"], slot=x["slot"]))
    # r37
    for W in X["wins"]:
        k = f"{W['ses']}:{W['w']}"; c = F["r37"].get(k)
        if not c or not c.get("ok"): continue
        vals = V["armed"].get(k) if W["kind"] == "armed" else V["virt"].get(k)
        if vals is None: continue
        q = W["quiet"]; v2 = W.get("v2") or {}
        r = dict(src="r37", key="r37AMS", reg="AMS", kind=W["kind"], t=W["trig"]["t"], age=W["trig"]["age_slots"], since=q["since_last"], coh=q["coh_hold"], fb=c["fb_n"],
                 wf24=q["wh_fol"], wf12=c["wf12"], wf6=c["wf6"], v2skip=bool(v2.get("skip")), oth=c["oth"], vals=vals, wkey=k, mint=W["mint"], slot=W["trig"]["slot"],
                 blocker=(f"{W['blocker'][0]}:{W['blocker'][1]}" if W.get("blocker") else None))
        if W["kind"] == "armed":
            r["v"] = W["v"]; r["isfill"] = bool(W["fills"]); r["win"] = r["isfill"] and (W["pnl_real"] or 0) > 0
            r["fill_off"] = W["fills"][0].get("slots_after_trigger") if W["fills"] else None
            r["end"] = ((W["dis"] or {}).get("slot") or W["trig"]["slot"]) - W["trig"]["slot"]; r["fee"] = W["n_fail"] * FAIL; r["live_stop"] = (5, 2)
        else:
            r["v"] = None; r["isfill"] = False; r["win"] = False
        rows.append(r)
    for r in rows:
        r["hour"] = pkt_hour(r["t"]); r["night"] = not (8 <= r["hour"] < 20)
    return rows, hours


def values(rows, stop_replay=True):
    """per row: value under each stop at 0% and -20% followers (None = unknown), and the censoring flag per stop.
    stop_replay: the 6 earlier runs with replay pickles take the stop from the paired replay (stop_train.pkl, q5c) instead of the
    stopgain shortcut (which disagrees with the replay on r37)."""
    try: STR = pickle.load(open(f"{D4}/stop_train.pkl", "rb")) if stop_replay else {}
    except Exception: STR = {}
    for r in rows:
        r["val"] = {}; r["valc"] = {}; r["cens"] = {}; r["stop_src"] = "approx"
        rep = STR.get(r["key"], {}).get(f"{r['mint']}:{r['slot']}") if r["src"] == "e" and r["kind"] == "armed" else None
        if rep is not None:
            sc = SIZE / r["size"]; r["stop_src"] = "replay"
            for S in STOPS:
                r["val"][S] = r["v"] + rep[(S, 0.0)] * sc
                r["valc"][S] = (r["v"] + rep[(S, 0.2)] * sc) if r["cutd"] is not None else None
                r["cens"][S] = False
            continue
        for S in STOPS:
            if r["src"] == "e":
                if r["kind"] == "cens": r["val"][S] = 0.0; r["valc"][S] = None; r["cens"][S] = True; continue
                ls = r["live_stop"]
                if ls is not None and stops_it(r, ls) and not (stops_it(r, S) and S[0] <= ls[0]):
                    r["val"][S] = r["v"]; r["cens"][S] = True       # the live stop cut it; a looser S: unknown after -> kept at live (CENSORED)
                else:
                    r["val"][S] = r["v"] + stopgain(r, S) - stopgain(r, ls); r["cens"][S] = False
                if r["cutd"] is None: r["valc"][S] = None
                else:
                    blocked = r["isfill"] and not r["cens"][S] and stops_it(r, S) and (r["fill_off"] or 0) >= S[0]
                    r["valc"][S] = r["val"][S] + (0.0 if blocked or not r["isfill"] else r["cutd"])
            else:
                if r["kind"] == "armed":
                    base = r["vals"][((5, 2), 0.0)][0]
                    r["val"][S] = r["v"] + r["vals"][(S, 0.0)][0] - base
                    r["valc"][S] = r["v"] + r["vals"][(S, 0.2)][0] - base
                else:
                    r["val"][S] = r["vals"][(S, 0.0)][0]; r["valc"][S] = r["vals"][(S, 0.2)][0]
                r["cens"][S] = False
    return rows
