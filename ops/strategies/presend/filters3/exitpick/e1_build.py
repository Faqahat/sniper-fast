#!/usr/bin/env python3
"""EXITPICK step 1: one row per live pre-send fill (r42..r50) = Stage-A features (arm + fill context, known at fill time),
Stage-B features (hold tape trades the engine could have seen before the 125 ms decision, at feed delays 0/15/30 ms),
and targets (counterfactual P&L at every exit from exit125/cf.json: own lag, resampled lag, followers -20%).
Read-only on inputs. Out: /home/it/sniper-data/filters3/exitpick/rows.json
No look-ahead: Stage-B uses only tape trades after our fill with rx t <= fill_t + 125 ms - delay (our own sell excluded)."""
import json, sys, time, calendar, collections
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filters3/exit125")
import xlib as X
E = "/home/it/sniper-data/filters3/exit125"
O = "/home/it/sniper-data/filters3/exitpick"
RUNS = [42, 43, 44, 45, 46, 47, 48, 49, 50]
KEYS = [f"t{t}" for t in (100, 125, 150, 200, 250, 300, 400, 600, 800, 1000, 1500, 2000)] + [f"s{n}" for n in range(1, 6)]
DEV_CUT = calendar.timegm((2026, 11, 1, 7, 0, 0)) * 10**9      # 11-01 12:00 PKT
FEE = 0.0125

cf = {(r["run"], r["mint"], r["t"]): r for r in json.load(open(f"{E}/cf.json"))}
F = json.load(open(f"{E}/fills.json"))["fills"]
ht = {}
for r in RUNS:
    for l in open(f"{E}/ht_r{r}.jsonl"):
        h = json.loads(l); ht[h["fill"]["sig"]] = h

# arm/fill context: last presend_live_arm for the mint before the fill (file order), the fill record itself
arm_of, fill_of = {}, {}
for r in RUNS:
    last_arm = {}
    for l in open(f"{O}/arm_r{r}.jsonl"):
        o = json.loads(l); e = o["ev"]
        if e == "presend_live_arm": last_arm[o.get("mint") or o["trig"]["mint"]] = o
        elif e == "presend_live_fill":
            fill_of[o["sig"]] = o
            if o["mint"] in last_arm: arm_of[o["sig"]] = last_arm[o["mint"]]

def num(v, d=-1.0):
    try:
        return float(v) if v is not None else d
    except (TypeError, ValueError):
        return d

def stage_a(x, fr, ar, h, P):
    f = {}
    f["rearm"] = 1.0 if x["kind"] == "rearm" else 0.0
    f["spend"] = x["spend"]
    f["hour"] = time.gmtime(x["t"] / 1e9 + 5 * 3600).tm_hour
    tr, fi = P["tr"], P["fi"]
    me = tr[fi]
    f["vsol_fill"] = me["vsol"] / 1e9
    # the dump that filled us
    d = (h or {}).get("dump")
    if d:
        f["dump_sol"] = d["sol"] / 1e9; f["dump_pct"] = d["tok"] / 1e13; f["dump_drop"] = d.get("drop_pct", -1)
        f["dump_ms"] = d.get("ms_before_fill", -1); f["dump_left"] = d.get("pct_after", -1)
        fl = d.get("fl", "")
        f["dump_B"] = 1.0 if "B" in fl else 0.0; f["dump_CS"] = 1.0 if ("C" in fl or "S" in fl) else 0.0
        f["dump_I"] = 1.0 if "I" in fl else 0.0; f["dump_W"] = 1.0 if "W" in fl else 0.0
        f["dump_same_slot"] = 1.0 if d["slot"] == me["slot"] else 0.0
        dk = next((i for i, a in enumerate(tr) if a["sig"] == d["sig"]), None)
    else:
        for k in ("dump_sol", "dump_pct", "dump_drop", "dump_ms", "dump_left", "dump_B", "dump_CS", "dump_I", "dump_W", "dump_same_slot"): f[k] = -1.0
        dk = None
    # buys between the dump and us (we are behind them)
    ahead = [a for a in tr[(dk + 1 if dk is not None else 0):fi] if a["buy"]]
    f["n_ahead"] = len(ahead); f["sol_ahead"] = sum(a["sol"] for a in ahead) / 1e9
    ann = (fr or {}).get("ann") or {}
    f["depth"] = num(ann.get("depth")); f["ob6"] = num(ann.get("ob6"))
    hs = ann.get("holders") or []
    f["n_holders"] = len(hs); f["max_holder"] = max([num(a.get("pct"), 0) for a in hs] or [0]); f["sum_holder"] = sum(num(a.get("pct"), 0) for a in hs)
    f["holder_risk"] = max([num(a.get("risk"), 0) for a in hs] or [0])
    f["grp_pct"] = num(ann.get("grp_pct")); f["ctx85"] = 1.0 if ann.get("ctx85") else 0.0
    f["guard_pct"] = num((ann.get("guard") or {}).get("pct"))
    f["slots_after_trigger"] = num((fr or {}).get("slots_after_trigger")); f["slots_after_send"] = num((fr or {}).get("slots_after_send"))
    f["ms_send_to_rx"] = num((fr or {}).get("ms_send_to_rx"))
    pe, ps = num((fr or {}).get("p_entry_post"), 0), num((fr or {}).get("p_sign"), 0)
    f["entry_vs_sign"] = pe / ps if pe > 0 and ps > 0 else -1.0
    f["client_jito"] = 1.0 if (fr or {}).get("client") == "JitoLabs" else 0.0
    f["client_harm"] = 1.0 if "Harmonic" in str((fr or {}).get("client")) else 0.0
    f["attempt_n"] = num((fr or {}).get("n"))
    # log-only risk flags at landing (owner 11-03 23:00): safe sell timer, group risk, holder clock, ctx85, landing guard
    f["fl_st"] = 1.0 if ann.get("st_block") else 0.0
    risky = sum(num(a.get("pct"), 0) for a in hs if num(a.get("risk"), 0) >= 5 and num(a.get("hz3"), 0) >= 0.3)
    f["fl_grp"] = 1.0 if (ann.get("grp_block") or risky >= 6) else 0.0
    f["fl_clock"] = 1.0 if any(num(a.get("pct"), 0) >= 6 and num(a.get("n"), 0) >= 5 and num(a.get("h3"), 0) >= 0.3 for a in hs) else 0.0
    f["fl_ctx85"] = 1.0 if ann.get("ctx85") else 0.0
    f["fl_guard"] = 1.0 if (ann.get("guard") or {}).get("block") else 0.0
    f["fl_n"] = f["fl_st"] + f["fl_grp"] + f["fl_clock"] + f["fl_ctx85"] + f["fl_guard"]
    if ar:
        tg = ar.get("trig") or {}
        f["whale_pct"] = num(tg.get("pct")); f["age_slots"] = num(tg.get("age_slots")); f["trig_sol"] = num(tg.get("sol"), 0) / 1e9
        f["nb"] = num(ar.get("nb")); f["arm_drop"] = num(ar.get("drop"))
        q = ar.get("quiet") or {}
        f["wh_dumps"] = num(q.get("wh_dumps")); f["wh_fol"] = num(q.get("wh_fol")); f["coh_hold"] = num(q.get("coh_hold")); f["since_last"] = num(q.get("since_last"))
        v2 = ar.get("v2") or {}
        f["maxdd_120s"] = num(v2.get("maxdd_120s")); f["n_120s"] = num(v2.get("n_120s")); f["n_tr_60s"] = num(v2.get("n_tr_60s"))
        f["at_120s_high"] = 1.0 if v2.get("at_120s_high") else 0.0
        a2 = ar.get("ann") or {}
        f["cr_pct"] = num(a2.get("cr_pct")); f["nb50"] = num(a2.get("nb50"))
        cr = ar.get("cr") or {}
        f["cr_n"] = num(cr.get("n")); f["cr_sum"] = num(cr.get("sum"), 0.0)
        f["arm_ms_after_dump"] = num(ar.get("arm_ms_after_dump")); f["gap"] = num(ar.get("gap"))
    else:
        for k in ("whale_pct", "age_slots", "trig_sol", "nb", "arm_drop", "wh_dumps", "wh_fol", "coh_hold", "since_last", "maxdd_120s", "n_120s", "n_tr_60s", "at_120s_high", "cr_pct", "nb50", "cr_n", "cr_sum", "arm_ms_after_dump", "gap"): f[k] = -1.0
    return f

def stage_b(x, P, h, cut_ms):
    """trades after our fill seen by the engine before fill + cut_ms (rx clock); our own sell excluded"""
    tr, fi, si, q = P["tr"], P["fi"], P["si"], P["q"]
    t0 = x["t"]; T = t0 + cut_ms * 1e6
    seen = [a for i, a in enumerate(tr) if i > fi and i != si and a["t"] <= T and not a.get("raw")]
    d = (h or {}).get("dump") or {}
    dw = d.get("w")
    buys = [a for a in seen if a["buy"]]; sells = [a for a in seen if not a["buy"]]
    f = {}
    f["b_n"] = len(seen); f["b_nbuy"] = len(buys); f["b_nsell"] = len(sells)
    f["b_buy_sol"] = sum(a["sol"] for a in buys) / 1e9; f["b_sell_sol"] = sum(a["sol"] for a in sells) / 1e9
    f["b_net_sol"] = f["b_buy_sol"] - f["b_sell_sol"]
    f["b_max_sell"] = max([a["sol"] for a in sells] or [0]) / 1e9; f["b_max_buy"] = max([a["sol"] for a in buys] or [0]) / 1e9
    f["b_nbuyers"] = len({a["w"] for a in buys})
    f["b_big_sell"] = 1.0 if any("B" in a.get("fl", "") for a in sells) else 0.0
    f["b_insider_sell"] = 1.0 if any(("I" in a.get("fl", "") or "C" in a.get("fl", "") or "S" in a.get("fl", "")) for a in sells) else 0.0
    f["b_dumper_sell"] = 1.0 if dw and any(a["w"] == dw for a in sells) else 0.0
    f["b_dumper_buy"] = 1.0 if dw and any(a["w"] == dw for a in buys) else 0.0
    f["b_watched_buy"] = 1.0 if any("W" in a.get("fl", "") for a in buys) else 0.0
    f["b_new_slot"] = 1.0 if any(a["slot"] > tr[fi]["slot"] for a in seen) else 0.0
    f["b_last_age"] = (T - max(a["t"] for a in seen)) / 1e6 if seen else cut_ms
    # the engine's mark: our position value now / spend (after fee), price move vs our fill
    me = tr[fi]
    v0 = X.gross_out(q, me["vsol"], me["vtok"]) * (1 - FEE) / (x["spend"] * 1e9)
    if seen:
        last = max(((i, a) for i, a in enumerate(tr) if i > fi and i != si and a["t"] <= T and not a.get("raw")), key=lambda z: z[0])[1]
        lk = tr.index(last)
        vtok = last["vtok"] - (q if lk > si else 0); vsol = last["vsol"] * last["vtok"] // vtok
        v = X.gross_out(q, vsol, vtok) * (1 - FEE) / (x["spend"] * 1e9)
        f["b_px"] = vsol / vtok / (me["vsol"] / me["vtok"]) - 1.0
    else:
        v = v0; f["b_px"] = 0.0
    f["b_mark"] = v; f["b_mark_d"] = v - v0
    return f

rows = []
miss = collections.Counter()
for x in F:
    c = cf.get((x["run"], x["mint"], x["t"]))
    if not c or "cf" not in c: miss["no cf"] += 1; continue
    P = X.prep(x)
    if not P: miss["no prep"] += 1; continue
    h = ht.get(x["sig"]); fr = fill_of.get(x["sig"]); ar = arm_of.get(x["sig"])
    if not h: miss["no ht"] += 1
    if not fr: miss["no fill rec"] += 1
    if not ar: miss["no arm"] += 1
    row = dict(run=x["run"], t=x["t"], mint=x["mint"], sig=x["sig"], kind=x["kind"], real=c["real"],
               split=("dev" if x["run"] == 42 and x["t"] < DEV_CUT else "val" if x["run"] in (42, 43, 44) else "hold"),
               real_why=c.get("real_why"))
    row["A"] = stage_a(x, fr, ar, h, P)
    row["B"] = {str(dl): stage_b(x, P, h, 125 - dl) for dl in (0, 15, 30)}
    # Stage B at later checkpoints (for a 2-step policy): decision at 400 ms with 15 ms delay
    row["B400"] = stage_b(x, P, h, 400 - 15)
    row["y"] = {k: (c["cf"][k]["pnl"] if c["cf"].get(k) else None) for k in KEYS}
    row["y_rs"] = {k: (c["cf"][k + "_rs"]["pnl"] if c["cf"].get(k + "_rs") else None) for k in KEYS}
    row["y_fc"] = {k: (c["cf"][k + "_fc20"]["pnl"] if c["cf"].get(k + "_fc20") else None) for k in KEYS}
    row["why125"] = (c["cf"].get("t125") or {}).get("why")
    row["dec125"] = (c["cf"].get("t125") or {}).get("dec")
    rows.append(row)
print("rows", len(rows), dict(miss))
print("split", collections.Counter((r["split"], r["run"]) for r in rows))
json.dump(rows, open(f"{O}/rows.json", "w"))
