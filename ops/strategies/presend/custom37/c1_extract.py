#!/usr/bin/env python3
"""CUSTOM37 step 1 [MEASURED, read-only]: every live pre-send window of the chosen runs, with its REAL tries.
Per run (split by run_start = engine session): presend_live_arm / _disarm / _skip, every presend_attempt joined with its
presend_attempt_land (send time, send slot, deadline, signing curve state, limit, min_out, landing slot/idx/coordinate, result),
fills, exits, sell landings, closes, realized P&L, the position tape (presend_live_tape) and the shadow presend_arm rows.
Out: /home/it/sniper-data/custom37/win_<run>.pkl  {"meta", "wins", "skips", "cfg"}
Usage: c1_extract.py [run ...]   (default: all in RUNS)"""
import json, sys, pickle, collections
OUT = "/home/it/sniper-data/custom37"
RUNS = {
    "r37": ("AMS", f"{OUT}/runs/dip_ams_r37.jsonl"),
    "r36": ("AMS", "/home/it/sniper-data/runs/ams/runs/dip_ams_r36.jsonl"),
    "r35": ("AMS", "/home/it/sniper-data/runs/ams/runs/dip_ams_r35.jsonl"),
    "r34": ("AMS", "/home/it/sniper-data/runs/ams/runs/dip_ams_r34.jsonl"),
    "f28": ("FRA", "/home/it/sniper-data/runs/fra/runs/dip_r28.jsonl"),
    "f27": ("FRA", "/home/it/sniper-data/runs/fra/runs/dip_r27.jsonl"),
    "f26": ("FRA", "/home/it/sniper-data/runs/fra/runs/dip_r26.jsonl"),
    # k=4 runs (extra robustness set)
    "r26": ("AMS", "/home/it/sniper-data/runs/ams/runs/dip_ams_r26.jsonl"),
    "r25": ("AMS", "/home/it/sniper-data/runs/ams/runs/dip_ams_r25.jsonl"),
    "r24": ("AMS", "/home/it/sniper-data/runs/ams/runs/dip_ams_r24.jsonl"),
    "f24": ("FRA", "/home/it/sniper-data/runs/fra/runs/dip_r24.jsonl"),
    "f23": ("FRA", "/home/it/sniper-data/runs/fra/runs/dip_r23.jsonl"),
}
KEEP_ATT = ("n", "sig", "t", "slot", "deadline", "en_slot", "vsol", "vtok", "p", "lim", "min_out", "spend", "pos", "client", "leader", "tip")
KEEP_LAND = ("res", "err", "slot", "idx", "a", "first_rx", "fee", "ms_send_to_first_rx", "slots_after_send")


def extract(run):
    reg, fn = RUNS[run]
    ses = -1; cfgs = []; wins = {}; skips = []; sh_arms = []; atts = {}; lands = {}
    pos_tape = collections.defaultdict(list); t0 = t1 = None; cur = {}   # (ses, mint) -> window key
    for line in open(fn):
        if '"ev":"presend' not in line and '"ev":"run_start"' not in line and '"ev": "run_start"' not in line: continue
        try: r = json.loads(line)
        except Exception: continue
        e = r.get("ev"); t = r.get("t")
        if isinstance(t, (int, float)) and t > 1e18: t0 = t if t0 is None else min(t0, t); t1 = t if t1 is None else max(t1, t)
        if e == "run_start":
            ses += 1; cfgs.append({"t": r.get("t"), "presend_live": r.get("presend_live"), "presend": r.get("presend")}); continue
        if ses < 0: ses = 0
        if e == "presend_live_arm":
            k = (ses, r["w"])
            wins[k] = {"run": run, "reg": reg, "ses": ses, "w": r["w"], "mint": r["trig"]["mint"], "trig": r["trig"], "en_slot": r["en_slot"],
                       "k": r.get("k"), "spend": r.get("spend"), "drop": r.get("drop"), "lim0": r.get("lim0"), "quiet": r.get("quiet"),
                       "v2": r.get("v2"), "dis": None, "tries": [], "fills": [], "exit": None, "sells": [], "close": None, "real": [], "late": []}
            cur[(ses, r["trig"]["mint"])] = k
        elif e == "presend_live_skip":
            skips.append({"ses": ses, "why": r["why"], "trig": r["trig"], "quiet": r.get("quiet"), "v2": r.get("v2")})
        elif e == "presend_live_disarm":
            k = (ses, r["w"])
            if k in wins: wins[k]["dis"] = {x: r.get(x) for x in ("why", "slot", "t", "attempts", "filled", "armed_ms", "quiet", "quiet_stop")}
        elif e == "presend_attempt":
            # a byte-identical resend (same state, deadline and blockhash) has the SAME signature: one tx; keep the first send, count copies
            if r["sig"] in atts: atts[r["sig"]][1]["copies"] += 1; continue
            a = {x: r.get(x) for x in KEEP_ATT}; a["copies"] = 1
            atts[r["sig"]] = (ses, a, r["w"])
        elif e == "presend_attempt_land":
            old = lands.get(r["sig"])
            if old is None or (old.get("res") == "unseen" and r.get("res") != "unseen"): lands[r["sig"]] = {x: r.get(x) for x in KEEP_LAND}
        elif e in ("presend_live_fill", "presend_live_exit", "presend_live_sell_land", "presend_live_close", "presend_live_realized", "presend_live_late_fill"):
            k = (ses, r["w"]) if r.get("w") is not None else cur.get((ses, r.get("mint")))
            W = wins.get(k)
            if W is None: continue
            if e == "presend_live_fill": W["fills"].append({x: r.get(x) for x in ("sig", "n", "slot", "idx", "t", "tokens", "sol_in", "fee", "tip", "client", "lim", "min_out", "p_sign",
                                                                                  "p_entry_pre", "p_entry_post", "ms_send_to_rx", "window_open", "after_exit", "slots_after_trigger")})
            elif e == "presend_live_exit": W["exit"] = W["exit"] or {x: r.get(x) for x in ("why", "slot", "t", "value", "slots_held", "pid", "round")}
            elif e == "presend_live_sell_land": W["sells"].append({x: r.get(x) for x in ("slot", "idx", "t", "sol", "fee", "pid", "round", "sig")})
            elif e == "presend_live_close": W["close"] = {x: r.get(x) for x in ("land", "sell_land", "sell_lands", "sol_in_curve", "sol_out_curve", "tokens", "exit_why", "exit_slot",
                                                                                 "held_s", "tips", "fee", "rounds", "merged", "late", "result", "buys", "sell_sigs", "curve_pnl", "pid")}
            elif e == "presend_live_realized": W["real"].append({x: r.get(x) for x in ("pnl", "buy_delta", "buy_fee", "buys_found", "sells_found", "src", "pid")})
            else: W["late"].append(r)
        elif e == "presend_live_tape":
            pos_tape[(ses, r["mint"])].append((r["slot"], r["idx"], r["j"], r["t"], r["user"], r["buy"], r["sol"], r["tok"], r["vsol"], r["vtok"]))
        elif e == "presend_arm":
            sh_arms.append({x: r.get(x) for x in ("mint", "sig", "slot", "idx", "j", "t", "a", "age_slots", "wallet", "pct", "bal", "sol", "tok", "vsol", "vtok", "quiet", "v2", "rows")} | {"ses": ses})
    # attach tries to windows
    nmiss = 0
    for sig, (ses_, a, w) in atts.items():
        W = wins.get((ses_, w))
        if W is None: nmiss += 1; continue
        L = lands.get(sig)
        a = dict(a); a["land"] = L
        W["tries"].append(a)
    for W in wins.values():
        W["tries"].sort(key=lambda a: (a["t"], a["n"]))
        W["ptape"] = pos_tape.get((W["ses"], W["mint"]), [])
    meta = {"run": run, "reg": reg, "file": fn, "t0": t0, "t1": t1, "sessions": len(cfgs), "wins": len(wins), "skips": len(skips), "tries": len(atts),
            "landed_records": len(lands), "tries_without_window": nmiss}
    return {"meta": meta, "cfg": cfgs, "wins": sorted(wins.values(), key=lambda W: W["trig"]["t"]), "skips": skips, "sh_arms": sh_arms}


if __name__ == "__main__":
    for run in (sys.argv[1:] or list(RUNS)):
        X = extract(run)
        pickle.dump(X, open(f"{OUT}/win_{run}.pkl", "wb"))
        W = X["wins"]
        nf = sum(1 for w in W if w["fills"]); rp = sum(sum(x["pnl"] or 0 for x in w["real"]) for w in W) / 1e9
        print(run, X["meta"], "filled windows", nf, "realized", round(rp, 4), flush=True)
