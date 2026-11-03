#!/usr/bin/env python3
"""QUIET4 step 1 [MEASURED, read-only]: every r37 pre-send trigger that reached the QUIET / age gates, in the custom37 window format
(so ops/strategies/presend/custom37/c37lib.py can replay it), plus the skipped triggers as VIRTUAL windows (no tries, no outcome).
  armed   = presend_live_arm (real tries joined with presend_attempt_land, fill, exit, sells, close, realized)
  quiet   = presend_live_skip why=quiet       (the QUIET arm rule skipped it)
  young   = presend_live_skip why=young_age   (age 1 slot, the --presend-live-min-age-slots 2 skip)
  blocked = presend_live_skip why=blocked_armed (a window was armed on the mint; arms only if that window is skipped)
Every row keeps the engine's own arm-time signals: quiet{since_last, coh_hold, fb_n, wh_fol, wh_dumps, q, all4} and v2{...}.
Value of an armed window (SOL) = presend_live_realized - 5120 lamports x landed failed tries (6042 / deadline / ata_exists / 6005).
Out: /home/moiz/sniper-data/presend_quiet4/win_r37.pkl  (custom37 format + "kind", "blocker")"""
import json, pickle, collections, sys
OUT = "/home/moiz/sniper-data/presend_quiet4"
FN = f"{OUT}/runs/dip_ams_r37.jsonl"
KEEP_ATT = ("n", "sig", "t", "slot", "deadline", "en_slot", "vsol", "vtok", "p", "lim", "min_out", "spend", "pos", "client", "leader", "tip")
KEEP_LAND = ("res", "err", "slot", "idx", "a", "first_rx", "fee", "ms_send_to_first_rx", "slots_after_send")
FAIL = 5120


def main():
    ses = -1; cfgs = []; wins = {}; virt = []; atts = {}; lands = {}; pos_tape = collections.defaultdict(list); cur = {}
    armed_on = {}   # (ses, mint) -> window key armed now (for the blocker of blocked_armed skips)
    t0 = t1 = None
    for line in open(FN):
        if '"ev":"presend' not in line and '"ev":"run_start"' not in line: continue
        try: r = json.loads(line)
        except Exception: continue
        e = r.get("ev"); t = r.get("t")
        if isinstance(t, (int, float)) and t > 1e18: t0 = t if t0 is None else min(t0, t); t1 = t if t1 is None else max(t1, t)
        if e == "run_start":
            ses += 1; cfgs.append({"t": r.get("t"), "presend_live": r.get("presend_live"), "presend": r.get("presend")}); continue
        if ses < 0: ses = 0
        if e == "presend_live_arm":
            k = (ses, r["w"])
            wins[k] = {"run": "r37", "reg": "AMS", "ses": ses, "w": r["w"], "kind": "armed", "mint": r["trig"]["mint"], "trig": r["trig"], "en_slot": r["en_slot"],
                       "k": r.get("k"), "spend": r.get("spend"), "drop": r.get("drop"), "lim0": r.get("lim0"), "quiet": r.get("quiet"),
                       "v2": r.get("v2"), "dis": None, "tries": [], "fills": [], "exit": None, "sells": [], "close": None, "real": [], "late": []}
            cur[(ses, r["trig"]["mint"])] = k; armed_on[(ses, r["trig"]["mint"])] = k
        elif e == "presend_live_skip":
            why = r["why"]
            if why in ("quiet", "young_age", "blocked_armed"):
                kind = {"quiet": "quiet", "young_age": "young", "blocked_armed": "blocked"}[why]
                tg = r["trig"]
                virt.append({"run": "r37", "reg": "AMS", "ses": ses, "w": None, "kind": kind, "mint": tg["mint"], "trig": tg,
                             "en_slot": None, "k": 8, "spend": 696000000, "drop": 0.12, "lim0": None, "quiet": r.get("quiet"), "v2": r.get("v2"),
                             "dis": None, "tries": [], "fills": [], "exit": None, "sells": [], "close": None, "real": [], "late": [],
                             "blocker": armed_on.get((ses, tg["mint"])) if kind == "blocked" else None})
        elif e == "presend_live_disarm":
            k = (ses, r["w"])
            if k in wins: wins[k]["dis"] = {x: r.get(x) for x in ("why", "slot", "t", "attempts", "filled", "armed_ms", "quiet", "quiet_stop")}
        elif e == "presend_attempt":
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
        # a window stays "armed on its mint" until its disarm (the blocked_armed skips name it as their blocker)
        if e == "presend_live_disarm":
            k = (ses, r["w"]); m = wins.get(k, {}).get("mint")
            if m and armed_on.get((ses, m)) == k: armed_on.pop((ses, m), None)
    nmiss = 0
    for sig, (ses_, a, w) in atts.items():
        W = wins.get((ses_, w))
        if W is None: nmiss += 1; continue
        L = lands.get(sig); a = dict(a); a["land"] = L
        W["tries"].append(a)
    for W in wins.values():
        W["tries"].sort(key=lambda a: (a["t"], a["n"]))
        W["ptape"] = pos_tape.get((W["ses"], W["mint"]), [])
        W["n_fail"] = sum(1 for a in W["tries"] if a["land"] and a["land"].get("res") not in (None, "unseen", "ok"))
        W["pnl_real"] = sum((x["pnl"] or 0) for x in W["real"]) / 1e9 if W["real"] else None
        W["v"] = (W["pnl_real"] or 0.0) - W["n_fail"] * FAIL / 1e9
    # virtual windows: unique negative ids, the custom37 en_slot rule (trigger a + live_ms 50 + 10 slots x 212 ms)
    for n, V in enumerate(virt):
        V["w"] = -(n + 1); V["ptape"] = []; V["n_fail"] = 0; V["pnl_real"] = None; V["v"] = None
        V["en_slot"] = int((V["trig"]["a"] + 50.0 + 10 * 212.0) // 212.0)
    allw = sorted(list(wins.values()) + virt, key=lambda W: W["trig"]["t"])
    meta = {"run": "r37", "file": FN, "t0": t0, "t1": t1, "sessions": len(cfgs), "armed": len(wins), "virtual": collections.Counter(V["kind"] for V in virt),
            "tries": len(atts), "tries_without_window": nmiss}
    X = {"meta": meta, "cfg": cfgs, "wins": allw, "skips": [], "sh_arms": []}
    pickle.dump(X, open(f"{OUT}/win_r37.pkl", "wb"))
    A = [W for W in allw if W["kind"] == "armed"]
    print(meta)
    print("armed", len(A), "fills", sum(1 for W in A if W["fills"]), "realized %+.4f" % sum(W["pnl_real"] or 0 for W in A),
          "failed landed tries", sum(W["n_fail"] for W in A), "fees %.4f" % (sum(W["n_fail"] for W in A) * FAIL / 1e9), "value %+.4f" % sum(W["v"] for W in A))
    print("blocked with a known blocker:", sum(1 for V in virt if V["kind"] == "blocked" and V["blocker"] is not None), "of", sum(1 for V in virt if V["kind"] == "blocked"))


if __name__ == "__main__":
    main()
