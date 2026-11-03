#!/usr/bin/env python3
"""PAPER AUDIT step 1 [MEASURED, read-only]: every pre-send record of a run, split by engine session (run_start), in one pickle.
Shadow (presend_arm / _fill / _exit / _disarm), live (presend_live_arm / _skip / _disarm / _fill / _exit / _sell_land / _close /
_realized / _ata_close, each try = presend_attempt joined with its presend_attempt_land), the regular paper (regular_paper_*),
and the run_start configs. Keys: (session, window id); shadow and live window ids are separate counters.
usage: pa1_extract.py RUN.jsonl OUT.pkl"""
import sys, json, pickle, collections

KEEP_ATT = ("n", "sig", "t", "slot", "deadline", "en_slot", "vsol", "vtok", "p", "lim", "min_out", "spend", "client", "tip", "path")
KEEP_LAND = ("res", "err", "slot", "idx", "a", "first_rx", "fee", "ms_after_x_a", "ms_after_x_first", "ms_after_x_rx", "ms_after_d_a", "ms_after_d_first",
             "n_between", "slots_after_send", "ms_send_to_first_rx", "client", "path")


def extract(fn):
    ses = -1
    X = {"cfg": [], "sh_arm": {}, "sh_fill": {}, "sh_exit": {}, "sh_dis": {}, "sh_skip": [], "lv_arm": {}, "lv_skip": [], "lv_dis": {}, "lv_fill": collections.defaultdict(list),
         "lv_exit": collections.defaultdict(list), "lv_sell": collections.defaultdict(list), "lv_close": collections.defaultdict(list),
         "lv_real": collections.defaultdict(list), "lv_ata_close": [], "lv_late": [], "reg": [], "ptape": collections.defaultdict(list), "status_t": []}
    atts, lands = {}, {}
    cur = {}
    t0 = t1 = None
    for line in open(fn, errors="replace"):
        if '"ev":"presend' not in line and '"ev":"run_start"' not in line and '"ev":"regular_paper' not in line and '"ev": "' not in line: continue
        try: r = json.loads(line)
        except Exception: continue
        e = r.get("ev"); t = r.get("t")
        if isinstance(t, (int, float)) and t > 1e18: t0 = t if t0 is None else min(t0, t); t1 = t if t1 is None else max(t1, t)
        if e == "run_start":
            ses += 1
            X["cfg"].append({"t": r.get("t"), "presend": r.get("presend"), "presend_live": r.get("presend_live"), "regular": r.get("regular"),
                             "regular_paper_ms": r.get("regular_paper_ms"), "spend": r.get("spend"), "tp": r.get("tp"), "sl": r.get("sl"), "hold_slots": r.get("hold_slots"),
                             "guard": r.get("guard"), "obs": r.get("obs")})
            continue
        if ses < 0: ses = 0
        if e == "presend_arm": X["sh_arm"][(ses, r["w"])] = r
        elif e == "presend_fill": X["sh_fill"][(ses, r["w"], r["row"])] = r
        elif e == "presend_exit": X["sh_exit"][(ses, r["w"], r["row"])] = r
        elif e == "presend_disarm": X["sh_dis"][(ses, r["w"])] = r
        elif e == "presend_skip": X["sh_skip"].append(r)
        elif e == "presend_live_arm":
            X["lv_arm"][(ses, r["w"])] = r
            cur[(ses, r["trig"]["mint"] if "trig" in r else r.get("mint"))] = (ses, r["w"])
        elif e == "presend_live_skip": r["ses"] = ses; X["lv_skip"].append(r)
        elif e == "presend_live_disarm": X["lv_dis"][(ses, r["w"])] = r
        elif e in ("presend_live_fill", "presend_live_exit", "presend_live_sell_land", "presend_live_close", "presend_live_realized"):
            k = (ses, r["w"]) if r.get("w") is not None else cur.get((ses, r.get("mint")))
            {"presend_live_fill": X["lv_fill"], "presend_live_exit": X["lv_exit"], "presend_live_sell_land": X["lv_sell"], "presend_live_close": X["lv_close"],
             "presend_live_realized": X["lv_real"]}[e][k].append(r)
        elif e == "presend_live_ata_close": r["ses"] = ses; X["lv_ata_close"].append(r)
        elif e == "presend_live_late_fill": r["ses"] = ses; X["lv_late"].append(r)
        elif e == "presend_attempt":
            if r["sig"] in atts: atts[r["sig"]][1]["copies"] += 1; continue
            a = {x: r.get(x) for x in KEEP_ATT}; a["copies"] = 1
            atts[r["sig"]] = (ses, a, r["w"])
        elif e == "presend_attempt_land":
            old = lands.get(r["sig"])
            if old is None or (old.get("res") == "unseen" and r.get("res") != "unseen"):
                L = {x: r.get(x) for x in KEEP_LAND}
                if r.get("res") == "ok":
                    L["x"] = r.get("x"); L["d"] = r.get("d"); L["between"] = r.get("between"); L["after"] = r.get("after")
                lands[r["sig"]] = L
        elif e == "presend_live_tape":
            X["ptape"][(ses, r["mint"])].append((r["slot"], r["idx"], r["j"], r["t"], r["user"], r["buy"], r["sol"], r["tok"], r["vsol"], r["vtok"]))
        elif e and e.startswith("regular_paper"): r["ses"] = ses; X["reg"].append(r)
    tries = collections.defaultdict(list); nmiss = 0
    for sig, (s_, a, w) in atts.items():
        a = dict(a); a["land"] = lands.get(sig)
        if (s_, w) not in X["lv_arm"]: nmiss += 1
        tries[(s_, w)].append(a)
    for k in tries: tries[k].sort(key=lambda a: (a["t"], a["n"]))
    X["tries"] = dict(tries)
    for k in ("lv_fill", "lv_exit", "lv_sell", "lv_close", "lv_real", "ptape"): X[k] = dict(X[k])
    X["meta"] = {"file": fn, "t0": t0, "t1": t1, "sessions": len(X["cfg"]), "tries": len(atts), "lands": len(lands), "tries_without_arm": nmiss}
    return X


if __name__ == "__main__":
    X = extract(sys.argv[1])
    pickle.dump(X, open(sys.argv[2], "wb"))
    m = X["meta"]
    print(m, "| shadow arms", len(X["sh_arm"]), "fills", len(X["sh_fill"]), "exits", len(X["sh_exit"]), "| live arms", len(X["lv_arm"]), "skips", len(X["lv_skip"]),
          "fills", sum(len(v) for v in X["lv_fill"].values()), "realized", sum(len(v) for v in X["lv_real"].values()), "| regular paper", len(X["reg"]))
