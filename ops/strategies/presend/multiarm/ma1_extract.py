#!/usr/bin/env python3
"""MULTIARM step 1 [MEASURED, read-only]: every live pre-send window of one engine run (the LAST session), T2 AND dip26 re-arm
("kind":"rearm"), with its REAL tries (presend_attempt + presend_attempt_land), fill, exit, sells, close, realized P&L; every T2 /
re-arm skip and re-arm defer record; plus the clock observations the replay needs:
  trade_obs  (slot, idx, feed t ms) of chain trades the engine saw (T2 triggers, re-arm dumps, reactive "dump" records,
             presend_live_tape, observatory rearm_cand / rearm_tape / backrun_sell)  -> the feed-arrival anchor A(slot)
  land_obs   (slot, idx, first_rx ms) of every landed try                             -> the landing anchor B(slot)
Window dicts follow custom37/c1_extract.py (so custom37/c37lib.prep_window reads them); re-arm windows get "kind": "rearm", a
trig built from their dump (wallet = the seller) and a "rearm" part (arm time / slot, check slot, deferral, holders).
usage: ma1_extract.py RUN.jsonl OUT.pkl [--obs OBS.jsonl ...] [--name r38]"""
import sys, json, pickle, collections

KEEP_ATT = ("n", "sig", "t", "slot", "deadline", "en_slot", "vsol", "vtok", "p", "lim", "min_out", "spend", "pos", "client", "leader", "tip", "path", "kind")
KEEP_LAND = ("res", "err", "slot", "idx", "a", "first_rx", "fee", "ms_send_to_first_rx", "slots_after_send", "path")


def a_of(s, i):
    size = max(400, i + 1)
    return s * 212.0 + (i / size) * 212.0


def trig_of_dump(mint, d):
    return {"sig": d["sig"], "slot": d["slot"], "idx": d["idx"], "j": d.get("j", 0), "t": d["t"], "a": a_of(d["slot"], d["idx"]), "wallet": d["seller"], "bal": 0,
            "vsol": d["vsol"], "vtok": d["vtok"], "age_slots": d.get("age_slots"), "mint": mint, "sol": d["sol"], "tok": d["tok"], "pct": d.get("pct")}


def extract(fn, name, obs=()):
    # pass 1: the last session's first line
    starts = []
    with open(fn, errors="replace") as f:
        for n, line in enumerate(f):
            if '"ev":"run_start"' in line: starts.append(n)
    last = starts[-1] if starts else 0
    cfg = None; wins = {}; skips = []; defers = []; atts = {}; lands = {}; ptape = collections.defaultdict(list)
    trade_obs = []; t0 = t1 = None; cur = {}; atas = []; run_end = None
    with open(fn, errors="replace") as f:
        for n, line in enumerate(f):
            if n < last: continue
            if '"ev":"presend' not in line and '"ev":"run_' not in line and '"ev":"dump"' not in line: continue
            try: r = json.loads(line)
            except Exception: continue
            e = r.get("ev"); t = r.get("t"); kind = r.get("kind") or "t2"
            if isinstance(t, (int, float)) and t > 1e18: t0 = t if t0 is None else min(t0, t); t1 = t if t1 is None else max(t1, t)
            if e == "run_start":
                cfg = {"t": r.get("t"), "presend_live": r.get("presend_live"), "presend": r.get("presend"), "wallet": r.get("wallet"), "allow_holder": r.get("allow_holder")}
                continue
            if e == "run_end": run_end = {"t": r.get("t"), "stop_why": r.get("stop_why")}; continue
            if e == "dump":
                if r.get("slot") is not None and r.get("idx") is not None and r.get("t"): trade_obs.append((r["slot"], r["idx"], r["t"] / 1e6))
                continue
            if e == "presend_live_arm":
                k = r["w"]
                if kind == "rearm":
                    d = r["dump"]; tg = trig_of_dump(r["mint"], d)
                    W = {"run": name, "reg": "AMS", "ses": 0, "w": k, "kind": "rearm", "mint": r["mint"], "trig": tg, "en_slot": r["en_slot"], "k": r.get("k"),
                         "spend": r.get("spend"), "drop": r.get("drop"), "lim0": r.get("lim0"), "quiet": {"stop": "6:2"}, "v2": None,
                         "rearm": {"arm_t": d["t"] + (r.get("arm_ms_after_dump") or 0.0) * 1e6, "arm_slot": r.get("arm_slot"), "check_slot": r.get("check_slot"), "deferred_ms": r.get("deferred_ms"),
                                   "deferred": r.get("deferred"), "holders": r.get("holders"), "holders_arm": r.get("holders_arm"), "arm_ms_after_dump": r.get("arm_ms_after_dump"),
                                   "gap": r.get("gap")}}
                    trade_obs.append((d["slot"], d["idx"], d["t"] / 1e6))
                else:
                    tg = r["trig"]
                    W = {"run": name, "reg": "AMS", "ses": 0, "w": k, "kind": "t2", "mint": tg["mint"], "trig": tg, "en_slot": r["en_slot"], "k": r.get("k"),
                         "spend": r.get("spend"), "drop": r.get("drop"), "lim0": r.get("lim0"), "quiet": r.get("quiet"), "v2": r.get("v2"), "arm_t": tg["t"] + 50e6}
                    trade_obs.append((tg["slot"], tg["idx"], tg["t"] / 1e6))
                W.update({"dis": None, "tries": [], "fills": [], "exit": None, "sells": [], "close": None, "real": [], "late": []})
                wins[k] = W; cur[W["mint"]] = k
            elif e == "presend_live_skip":
                r = dict(r); r["kind"] = kind
                skips.append(r)
                d = r.get("dump") or r.get("trig")
                if d and d.get("slot") is not None and d.get("idx") is not None and d.get("t"): trade_obs.append((d["slot"], d["idx"], d["t"] / 1e6))
            elif e == "presend_live_rearm_defer":
                defers.append(r)
            elif e == "presend_live_disarm":
                if r["w"] in wins: wins[r["w"]]["dis"] = {x: r.get(x) for x in ("why", "slot", "t", "attempts", "filled", "armed_ms", "quiet", "quiet_stop", "rearm")}
            elif e == "presend_attempt":
                if r["sig"] in atts: atts[r["sig"]][0]["copies"] += 1; continue
                a = {x: r.get(x) for x in KEEP_ATT}; a["copies"] = 1
                atts[r["sig"]] = (a, r["w"])
            elif e == "presend_attempt_land":
                old = lands.get(r["sig"])
                if old is None or (old.get("res") == "unseen" and r.get("res") != "unseen"): lands[r["sig"]] = {x: r.get(x) for x in KEEP_LAND}
            elif e in ("presend_live_fill", "presend_live_exit", "presend_live_sell_land", "presend_live_close", "presend_live_realized", "presend_live_late_fill"):
                k = r.get("w") if r.get("w") is not None else cur.get(r.get("mint"))
                W = wins.get(k)
                if W is None: continue
                if e == "presend_live_fill": W["fills"].append({x: r.get(x) for x in ("sig", "n", "slot", "idx", "t", "tokens", "sol_in", "fee", "tip", "client", "lim", "min_out", "p_sign",
                                                                                      "p_entry_pre", "p_entry_post", "ms_send_to_rx", "window_open", "after_exit", "slots_after_trigger", "path")})
                elif e == "presend_live_exit": W["exit"] = W["exit"] or {x: r.get(x) for x in ("why", "slot", "t", "value", "slots_held", "pid", "round")}
                elif e == "presend_live_sell_land": W["sells"].append({x: r.get(x) for x in ("slot", "idx", "t", "sol", "fee", "pid", "round", "sig")})
                elif e == "presend_live_close": W["close"] = {x: r.get(x) for x in ("land", "sell_land", "sell_lands", "sol_in_curve", "sol_out_curve", "tokens", "exit_why", "exit_slot",
                                                                                     "held_s", "tips", "fee", "rounds", "merged", "late", "result", "buys", "sell_sigs", "curve_pnl", "pid", "kind")}
                elif e == "presend_live_realized": W["real"].append({x: r.get(x) for x in ("pnl", "buy_delta", "buy_fee", "buys_found", "sells_found", "src", "pid", "kind")})
                else: W["late"].append(r)
            elif e == "presend_live_tape":
                ptape[r["mint"]].append((r["slot"], r["idx"], r["j"], r["t"], r["user"], r["buy"], r["sol"], r["tok"], r["vsol"], r["vtok"]))
                trade_obs.append((r["slot"], r["idx"], r["t"] / 1e6))
            elif e in ("presend_live_ata", "presend_live_ata_close"):
                atas.append(r)
    nmiss = 0
    for sig, (a, w) in atts.items():
        W = wins.get(w)
        if W is None: nmiss += 1; continue
        a = dict(a); a["land"] = lands.get(sig)
        W["tries"].append(a)
    land_obs = []
    for W in wins.values():
        W["tries"].sort(key=lambda a: (a["t"], a["n"]))
        W["ptape"] = ptape.get(W["mint"], [])
        for a in W["tries"]:
            L = a["land"] or {}
            if L.get("res") not in (None, "unseen") and L.get("slot") is not None and L.get("idx") is not None and L.get("first_rx"):
                land_obs.append((L["slot"], L["idx"], L["first_rx"] / 1e6))
    # observatory: candidates / windows (R0 log-only shadow) and more trade clock observations
    ocand, owin = [], []
    for p in obs:
        with open(p, errors="replace") as f:
            for line in f:
                if '"ev":"rearm_cand"' in line:
                    r = json.loads(line); ocand.append(r); d = r["dump"]; trade_obs.append((d["slot"], d["idx"], d["t"] / 1e6))
                elif '"ev":"rearm_window"' in line:
                    r = json.loads(line)
                    for k in ("rows",): r.pop(k, None)
                    owin.append(r)
                elif '"ev":"rearm_tape"' in line or '"ev":"hold_tape"' in line:
                    r = json.loads(line)
                    for x in r.get("trades") or []:
                        if x.get("slot") is not None and x.get("idx") is not None and x.get("t"): trade_obs.append((x["slot"], x["idx"], x["t"] / 1e6))
                elif '"ev":"backrun_sell"' in line:
                    r = json.loads(line)
                    if r.get("slot") is not None and r.get("idx") is not None and r.get("t"): trade_obs.append((r["slot"], r["idx"], r["t"] / 1e6))
    meta = {"run": name, "file": fn, "t0": t0, "t1": t1, "run_end": run_end, "wins": len(wins), "skips": len(skips), "tries": len(atts), "lands": len(lands),
            "tries_without_window": nmiss, "trade_obs": len(trade_obs), "land_obs": len(land_obs), "obs_cand": len(ocand), "obs_win": len(owin)}
    return {"meta": meta, "cfg": cfg, "wins": sorted(wins.values(), key=lambda W: W["trig"]["t"]), "skips": skips, "defers": defers, "atas": atas,
            "trade_obs": sorted(set(trade_obs)), "land_obs": sorted(set(land_obs)), "obs_cand": ocand, "obs_win": owin}


if __name__ == "__main__":
    a = sys.argv[1:]
    obs = []; name = "run"
    if "--name" in a: k = a.index("--name"); name = a[k + 1]; del a[k:k + 2]
    if "--obs" in a: k = a.index("--obs"); obs = a[k + 1:]; a = a[:k]
    X = extract(a[0], name, obs)
    pickle.dump(X, open(a[1], "wb"))
    W = X["wins"]
    by = collections.Counter(w["kind"] for w in W); nf = collections.Counter(w["kind"] for w in W if w["fills"])
    rp = collections.defaultdict(float)
    for w in W: rp[w["kind"]] += sum(x["pnl"] or 0 for x in w["real"]) / 1e9
    print(X["meta"]); print("windows", dict(by), "filled", dict(nf), "realized", {k: round(v, 4) for k, v in rp.items()})
