#!/usr/bin/env python3
"""TEN agent (FILTERS-3) extractor: one run's presend.jsonl -> one compact JSON (read-only on the input).
usage: extract.py RUN.presend.jsonl OUT.json
Keeps: run_start/run_end/live_stop; every live window (kind:w) with arm, disarm, fill, close, realized, failed-try fees, tape;
live T2 skips (+ re-arm skip counts and compact re-arm skips); shadow T2 windows (arm, row a/b/c fill+exit, disarm, skips);
wide shadow windows (r41+)."""
import sys, json, re, collections

src, out = sys.argv[1], sys.argv[2]
R = {"run_start": None, "run_end_t": None, "stop": None, "first_t": None, "last_t": None,
     "live": {}, "t2_skips": [], "rearm_skips": collections.Counter(), "rearm_skip_rows": [],
     "shadow": {}, "shadow_skips": [], "wide": {}, "defer": 0}
re_t = re.compile(r'"t":(\d{19})')
fee_re = re.compile(r'"fee":(\d+)')

def L(kind, w):
    k = f"{kind}:{w}"
    if k not in R["live"]:
        R["live"][k] = {"kind": kind, "w": w, "fail_fee": 0, "fail_n": 0, "att": 0, "tape": [], "pnl": None, "real": []}
    return R["live"][k]

def S(store, w):
    if w not in store: store[w] = {"rows": {}}
    return store[w]

TRIM_TRIG = ("age_slots", "pct", "sol", "vsol", "vtok", "slot", "t", "sig", "wallet", "mint", "idx", "tok")
for line in open(src, errors="replace"):
    if '"ev":"' not in line: continue
    if '"ev":"presend_attempt"' in line:
        continue
    if '"ev":"presend_attempt_land"' in line:
        # failed try = landed with err; count fee; key kind:w
        d = json.loads(line)
        lv = L(d.get("kind", "t2"), d.get("w"))
        lv["att"] += 1
        if d.get("err"):
            lv["fail_fee"] += d.get("fee", 0) or 0; lv["fail_n"] += 1
        continue
    d = json.loads(line); e = d.get("ev")
    t = d.get("t")
    if isinstance(t, int) and t > 10**18:
        R["first_t"] = t if R["first_t"] is None else min(R["first_t"], t)
        R["last_t"] = t if R["last_t"] is None else max(R["last_t"], t)
    if e == "run_start":
        if R["run_start"] is None: R["run_start"] = {k: d.get(k) for k in ("t", "presend", "presend_live", "spend", "limits")}
    elif e == "run_end": R["run_end_t"] = t
    elif e == "presend_live_stop": R["stop"] = d
    elif e == "presend_live_arm":
        kind = d.get("kind", "t2"); lv = L(kind, d["w"])
        lv["arm"] = {k: d.get(k) for k in ("ann", "nb", "quiet", "quiet_skip", "spend", "v2", "holders", "gap", "arm_slot", "arm_ms_after_dump", "deferred_ms", "en_slot", "lim0")}
        tr = d.get("trig") or d.get("dump") or {}
        lv["arm"]["trig"] = {k: tr.get(k) for k in TRIM_TRIG + ("drop_pct", "seller")}
        lv["mint"] = d.get("mint") or tr.get("mint")
    elif e == "presend_live_disarm":
        lv = L(d.get("kind", "t2"), d["w"])
        lv["disarm"] = {k: d.get(k) for k in ("why", "filled", "attempts", "armed_ms", "quiet_stop", "t", "slot", "trig_slot", "rearm")}
        q = d.get("quiet")
        if q: lv["disarm"]["others"] = q.get("others")
    elif e == "presend_live_fill":
        lv = L(d.get("kind", "t2"), d["w"])
        a = d.get("ann") or {}
        lv.setdefault("fills", []).append({k: d.get(k) for k in ("t", "slot", "idx", "sol_in", "spend", "tokens", "p_entry_pre", "p_entry_post", "p_sign", "lim", "slots_after_trigger", "slots_after_send", "ms_send_to_rx", "path", "client", "tip", "after_exit", "deep", "n", "min_out", "fee")}
                                    | {"ann": {k: a.get(k) for k in ("depth", "grp_block", "grp_pct", "guard", "holders", "ob6", "st_block", "ctx85")}})
        lv["mint"] = d.get("mint")
    elif e == "presend_live_close":
        lv = L(d.get("kind", "t2"), d["w"])
        lv.setdefault("close", []).append({k: d.get(k) for k in ("held_s", "curve_pnl", "sol_in_curve", "sol_out_curve", "exit_why", "tips", "fee", "result", "rounds", "merged", "late", "sell_land", "spend", "land")})
    elif e == "presend_live_realized":
        lv = L(d.get("kind", "t2"), d["w"])
        lv["real"].append(d.get("pnl", 0)); lv["pnl"] = sum(lv["real"])
        lv["mint"] = d.get("mint") or lv.get("mint")
    elif e == "presend_live_tape":
        # tape has no w; attach by mint later
        R.setdefault("tapes", collections.defaultdict(list))[d["mint"]].append({k: d.get(k) for k in ("t", "slot", "idx", "buy", "sol", "tok", "user", "vsol", "vtok", "sig")})
    elif e == "presend_live_skip":
        if d.get("kind") == "rearm" or "trig" not in d:
            R["rearm_skips"][d.get("why") or "?"] += 1
            dm = d.get("dump") or {}
            R["rearm_skip_rows"].append({"why": d.get("why"), "mint": d.get("mint"), "t": dm.get("t"), "slot": dm.get("slot"),
                                         "age": dm.get("age_slots"), "pct": dm.get("pct"), "sol": dm.get("sol"), "vsol": dm.get("vsol"),
                                         "hold": [[h.get("pct"), h.get("w")] for h in (d.get("holders") or [])], "sig": dm.get("sig"), "seller": dm.get("seller"), "check_slot": d.get("check_slot"), "en_slot": d.get("en_slot")})
        else:
            tr = d["trig"]
            R["t2_skips"].append({"why": d.get("why"), "sig": tr.get("sig"), "t": tr.get("t"), "pct": tr.get("pct"), "age": tr.get("age_slots"),
                                  "mint": tr.get("mint"), "quiet": d.get("quiet"), "nb": d.get("nb"), "v2": d.get("v2"), "ann": d.get("ann")})
    elif e == "presend_live_rearm_defer": R["defer"] += 1
    elif e in ("presend_arm", "presend_wide_arm"):
        st = S(R["shadow"] if e == "presend_arm" else R["wide"], d["w"])
        st["arm"] = {k: d.get(k) for k in ("sig", "t", "slot", "pct", "age_slots", "age_s", "sol", "vsol", "vtok", "mint", "wallet", "quiet", "v2", "idx")}
    elif e in ("presend_fill", "presend_wide_fill"):
        st = S(R["shadow"] if e == "presend_fill" else R["wide"], d["w"])
        en = d.get("entry") or {}
        st["rows"].setdefault(d.get("row", "c"), {})["fill"] = {"sol_in": en.get("sol_in"), "tokens": en.get("tokens"), "p_avg": en.get("p_avg"),
            "drop_pct": d.get("drop_pct"), "sat": d.get("slots_after_trigger"), "n_ahead": d.get("n_ahead"), "siw": d.get("seller_is_whale"),
            "d_ms": d.get("d_ms"), "s_in": d.get("s_in"), "dump_sol": (d.get("m") or {}).get("sol"), "dump_user": (d.get("m") or {}).get("user"),
            "vsol": en.get("vsol"), "t": (d.get("m") or {}).get("t")}
    elif e in ("presend_exit", "presend_wide_exit"):
        st = S(R["shadow"] if e == "presend_exit" else R["wide"], d["w"])
        st["rows"].setdefault(d.get("row", "c"), {})["exit"] = {k: d.get(k) for k in ("net_cheap", "pnl", "why", "pmin", "hold_slots", "grad")}
    elif e in ("presend_disarm", "presend_wide_disarm"):
        st = S(R["shadow"] if e == "presend_disarm" else R["wide"], d["w"])
        st["disarm"] = {"why": d.get("why"), "others": (d.get("quiet_stop") or {}).get("others"), "qstop": (d.get("quiet_stop") or {}).get("stop")}
    elif e == "presend_skip":
        R["shadow_skips"].append({k: d.get(k) for k in ("why", "pct", "sig", "t", "mint")})

# attach tapes to live windows by mint (a mint can have >1 window; keep tape rows within [fill slot-2, fill slot+40])
tapes = R.pop("tapes", {})
for lv in R["live"].values():
    m = lv.get("mint"); f = (lv.get("fills") or [None])[0]
    if not m or not f: continue
    s0 = f["slot"]
    lv["tape"] = [x for x in tapes.get(m, []) if x["slot"] is not None and s0 - 2 <= x["slot"] <= s0 + 40]
R["rearm_skips"] = dict(R["rearm_skips"])
json.dump(R, open(out, "w"))
print(src, "live", len(R["live"]), "shadow", len(R["shadow"]), "wide", len(R["wide"]), "t2skips", len(R["t2_skips"]))
