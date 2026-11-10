#!/usr/bin/env python3
"""VERIFY step 2: one chained simulation r37 -> r46 of the frozen QUIET3 (A, B) and TAIL (G1, G3, G4) rules on the joined live
positions from v_extract.py, alone and combined, scored on DEV / VAL / HOLDOUT (per run) with realized P&L. Also SIZE15 / WIDE5
pooled from v_ten.py. Writes VERIFY.json. All features come from the frozen scorers' own functions (see v_extract.py)."""
import json, collections, datetime, os
D = "/home/it/sniper-data/filters3/verify"
OUT = "/home/it/sniper/ops/strategies/presend/filters3/verify/VERIFY.json"
TS_AT_TRIGGER = os.environ.get("TS_AT_TRIGGER") == "1"  # sensitivity: G1/G4 decided at the trigger time instead of the filled attempt signing
if TS_AT_TRIGGER: OUT = "/home/it/sniper-data/filters3/verify/VERIFY_ts_at_trigger.json"
RUNS = [f"r{r}" for r in range(37, 47)]
HOLD = ["r43", "r44", "r45", "r46"]
SPLIT = 1793516400000000000
ATT0, ATT1 = 1793588400000000000, 1793590800000000000  # 11-02 08:00 -> 08:40 PKT
H24 = 24 * 3600 * 10**9
CR_MAX, FRESH_MIN = -0.10, 35.0
BRK_N, BRK_L, BRK_W, BRK_P = 2, 0.20, 10 * 60e9, 30 * 60e9
pkt = lambda ns: (datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=ns / 1e9, hours=5)).strftime("%m-%d %H:%M")

X = {r: json.load(open(f"{D}/x_{r}.json")) for r in RUNS}
P = []
for r in RUNS:
    for i, p in enumerate(X[r]["rows"]):
        p["id"] = f"{r}:{i}"; P.append(p)
P.sort(key=lambda p: (RUNS.index(p["run"]), p["t"]))
for p in P:
    p["slice"] = "VAL" if (p["run"] == "r42" and p["t"] >= SPLIT) else ("DEV" if p["run"] <= "r42" else "HOLD")
    p["attack"] = ATT0 <= p["t"] < ATT1
    if TS_AT_TRIGGER and "q_t0" in p: p["ts"] = min(p["ts"], p["q_t0"])

hours = {}
for r in RUNS:
    t0, t1 = X[r]["t0"], X[r]["t1"]
    if r == "r42": hours["r42a"] = (SPLIT - t0) / 3.6e12; hours["r42b"] = (t1 - SPLIT) / 3.6e12
    else: hours[r] = (t1 - t0) / 3.6e12
H = {"DEV": sum(hours[r] for r in ["r37", "r38", "r39", "r40", "r41", "r42a"]), "VAL": hours["r42b"], "HOLD": sum(hours[r] for r in HOLD)}
H.update({r: hours[r] for r in HOLD}); H["VAL_ex_attack"] = H["VAL"] - (ATT1 - ATT0) / 3.6e12

def sim(rules, b_hist="kept", g1_ledger="kept"):
    """rules: subset of A B G1 G3 G4. b_hist / g1_ledger: 'kept' = only positions this rule set lets through feed the history
    (what an engine would see); 'all' = every live position feeds it (TAIL's frozen G1 does this). Breaker: kept trades, per run."""
    blk = {}
    bh = collections.defaultdict(list)   # creator -> [(known, followed)]
    led = collections.defaultdict(list)  # creator -> [(known, pnl)]
    brk = {"run": None, "ev": [], "until": 0}
    for p in P:
        if brk["run"] != p["run"]: brk = {"run": p["run"], "ev": [], "until": 0}
        f = set()
        if "A" in rules and p.get("A"): f.add("A")
        cq = p.get("creator_q")
        if "B" in rules and cq and "q_t0" in p:
            prev = sorted([h for h in bh[cq] if h[0] < p["q_t0"] and h[0] >= p["q_t0"] - H24])[-3:]
            if prev and all(not h[1] for h in prev): f.add("B")
        ct = p.get("creator_tl")
        if "G1" in rules and ct:
            if sum(v for t, v in led[ct] if t <= p["ts"]) <= CR_MAX: f.add("G1")
        if "G3" in rules and p["has_holders"] and (p.get("sum_fresh") or 0) >= FRESH_MIN: f.add("G3")
        if "G4" in rules and not f:
            bad = [t for t, v in brk["ev"] if p["ts"] - BRK_W <= t <= p["ts"] and v <= -BRK_L]
            if len(bad) >= BRK_N: brk["until"] = max(brk["until"], max(bad) + BRK_P)
            if p["ts"] < brk["until"]: f.add("G4")
        blk[p["id"]] = f
        kept = not f
        if kept and "G4" in rules: brk["ev"].append((p["known_tl"], p["pnl"]))
        if (kept or b_hist == "all") and cq and "q_known" in p: bh[cq].append((p["q_known"], p["followed"]))
        if (kept or g1_ledger == "all") and ct: led[ct].append((p["known_tl"], p["pnl"]))
    return blk

def norm(p):
    """size-normalised P&L (r43 traded 0.15 / 0.35 SOL): scale to the r44+ size (T2 0.55, re-arm 0.65)"""
    tgt = 0.65 if p["kind"] == "rearm" else 0.55
    return p["pnl"] * (tgt / p["spend"]) if p["spend"] > 0 else p["pnl"]

def score(ps, blocked, hrs, key=lambda p: p["pnl"]):
    if not ps: return {"n": 0}
    v = [key(p) for p in ps]; b = [key(p) for p in ps if blocked(p)]; k = [key(p) for p in ps if not blocked(p)]
    s = sorted(b); top5 = sorted(v, reverse=True)[:5]
    vs = sorted(v, reverse=True); ks = sorted(k, reverse=True)
    wr = lambda x: round(sum(1 for y in x if y > 0) / len(x), 3) if x else None
    saves = -sum(b)
    return {"n": len(v), "hours": round(hrs, 2), "base": round(sum(v), 3), "base_day": round(sum(v) / hrs * 24, 2), "base_win": wr(v),
            "blocked": len(b), "winners_lost": [sum(1 for x in b if x > 0), round(sum(x for x in b if x > 0), 3)],
            "losers_saved": [sum(1 for x in b if x <= 0), round(-sum(x for x in b if x <= 0), 3)],
            "saves": round(saves, 3), "saves_day": round(saves / hrs * 24, 2),
            "saves_wo_its_5_best": round(-sum(s[5:]), 3),
            "saves_wo_top5_trades": round(saves - (-sum(x for x in b if x in top5)), 3),
            "after": round(sum(k), 3), "after_day": round(sum(k) / hrs * 24, 2), "after_win": wr(k),
            "base_wo_top5": round(sum(vs[5:]), 3), "after_wo_top5": round(sum(ks[5:]), 3)}

SLICES = {"DEV": lambda p: p["slice"] == "DEV", "VAL": lambda p: p["slice"] == "VAL",
          "VAL_ex_attack": lambda p: p["slice"] == "VAL" and not p["attack"], "HOLD": lambda p: p["slice"] == "HOLD"}
for r in HOLD: SLICES[r] = (lambda rr: (lambda p: p["run"] == rr))(r)

CONF = {"QUIET3": (("A", "B"), "kept", "kept"), "Q3_A": (("A",), "kept", "kept"), "Q3_B": (("B",), "kept", "kept"),
        "REC_frozen": (("G1", "G3", "G4"), "kept", "all"), "REC_kept_ledger": (("G1", "G3", "G4"), "kept", "kept"),
        "G1_frozen": (("G1",), "kept", "all"), "G1_kept_ledger": (("G1",), "kept", "kept"), "G3": (("G3",), "kept", "kept"),
        "G4": (("G4",), "kept", "kept"),
        "COMBINED_seq": (("A", "B", "G1", "G3", "G4"), "kept", "kept"),
        "COMBINED_seq_g1all": (("A", "B", "G1", "G3", "G4"), "kept", "all")}
BLK = {name: sim(*c) for name, c in CONF.items()}
BLK["COMBINED_union"] = {pid: BLK["QUIET3"][pid] | BLK["REC_frozen"][pid] for pid in BLK["QUIET3"]}

res = {"hours": {k: round(v, 2) for k, v in H.items()}, "rules": {}}
for name, bl in BLK.items():
    res["rules"][name] = {}
    for sn, sf in SLICES.items():
        ps = [p for p in P if sf(p)]
        res["rules"][name][sn] = score(ps, lambda p: bool(bl[p["id"]]), H[sn])
    hp = [p for p in P if p["slice"] == "HOLD"]
    res["rules"][name]["HOLD_size_normalised"] = score(hp, lambda p: bool(bl[p["id"]]), H["HOLD"], key=norm)
    res["rules"][name]["HOLD_ex_r43"] = score([p for p in hp if p["run"] != "r43"], lambda p: bool(bl[p["id"]]), H["HOLD"] - H["r43"])

# overlap QUIET3 vs REC on each slice
res["overlap"] = {}
for sn in ["DEV", "VAL", "HOLD"]:
    ps = [p for p in P if SLICES[sn](p)]
    q = {p["id"] for p in ps if BLK["QUIET3"][p["id"]]}; t = {p["id"] for p in ps if BLK["REC_frozen"][p["id"]]}
    qb = {p["id"] for p in ps if "B" in BLK["QUIET3"][p["id"]]}; g1 = {p["id"] for p in ps if "G1" in BLK["REC_frozen"][p["id"]]}
    pn = {p["id"]: p["pnl"] for p in ps}
    res["overlap"][sn] = {"quiet3": len(q), "rec": len(t), "both": len(q & t), "both_sol": round(-sum(pn[i] for i in q & t), 3),
                          "quiet3_B_and_G1": len(qb & g1), "sum_of_separate_saves": round(-sum(pn[i] for i in q) - sum(pn[i] for i in t), 3),
                          "union_saves": round(-sum(pn[i] for i in q | t), 3)}

# list of holdout blocks of the combined set
res["holdout_blocks_combined"] = [{"run": p["run"], "pkt": pkt(p["t"]), "kind": p["kind"], "mint": p["mint"], "pnl": round(p["pnl"], 4),
                                   "rules": sorted(BLK["COMBINED_seq"][p["id"]]), "followed": p.get("followed")}
                                  for p in P if p["slice"] == "HOLD" and BLK["COMBINED_seq"][p["id"]]]

# sanity: realized totals per run
res["sanity"] = {r: {"raw_realized_sol": round(X[r]["raw_realized_sol"], 4), "raw_n": X[r]["raw_realized_n"], "tail_n": X[r]["tail_n"],
                     "tail_sum": round(X[r]["tail_sum"], 4), "q3_n": X[r]["q3_n"], "q3_sum": round(X[r]["q3_sum"], 4),
                     "unmatched_q3": X[r]["unmatched_q3"], "unmatched_tail": X[r]["unmatched_tail"], "pnl_mismatch": X[r]["pnl_mismatch"]}
                 for r in RUNS}
sp = collections.Counter((p["run"], p["kind"], round(p["spend"], 2)) for p in P if p["slice"] == "HOLD")
res["sanity"]["holdout_spend_counts"] = {f"{a} {b} {c}": n for (a, b, c), n in sorted(sp.items())}
res["sanity"]["rule_on_false_holdout"] = collections.Counter(p["run"] for p in P if p["slice"] == "HOLD" and p.get("rule_on") is False)

# TEN levers
T = {}
for tag in ["r37", "r38", "r39", "r40", "r41", "r42a", "r42b", "r43", "r44", "r45", "r46"]:
    T[tag] = json.load(open(f"{D}/ten_{tag}.json"))
TS = {"DEV": ["r37", "r38", "r39", "r40", "r41", "r42a"], "VAL": ["r42b"], "HOLD": HOLD}
for r in HOLD: TS[r] = [r]
keyrun = {"r42a": "r42", "r42b": "r42"}
pid_by = {}
for p in P: pid_by[(p["run"], p["w"], p["mint"])] = p["id"]
def lev(vals, hrs):
    s = sorted(vals, reverse=True)
    return {"n": len(vals), "sol": round(sum(vals), 3), "day": round(sum(vals) / hrs * 24, 2), "wo_top5": round(sum(s[5:]), 3),
            "wo_top5_day": round(sum(s[5:]) / hrs * 24, 2)}
res["ten"] = {}
for sn, tags in TS.items():
    hrs = sum(T[t]["hrs"] for t in tags)
    o = {"hours": round(hrs, 2), "WIDE5": lev([x for t in tags for x in T[t]["wide"]], hrs), "WIDE5raw": lev([x for t in tags for x in T[t]["wide_raw"]], hrs)}
    for b in ["b3", "b0", "b9", "b3d20"]:
        o[f"SIZE15_{b}"] = lev([x[b] for t in tags for x in T[t]["size"]], hrs)
    # SIZE15 on top of the combined filters: only trades the combined set keeps
    kept = []; nmiss = 0
    for t in tags:
        for x in T[t]["size"]:
            pid = pid_by.get((keyrun.get(t, t), x["k"][1], x["mint"]))
            if pid is None: nmiss += 1; kept.append(x["b3"]); continue
            if not BLK["COMBINED_seq"][pid]: kept.append(x["b3"])
    o["SIZE15_b3_on_combined_kept"] = lev(kept, hrs); o["SIZE15_join_missing"] = nmiss
    o["live_size_per_run"] = {t: T[t]["live_size"] for t in tags}
    res["ten"][sn] = o
json.dump(res, open(OUT, "w"), indent=1)
# compact print
for name in BLK:
    row = res["rules"][name]
    print(f"{name:20s}" + " | ".join(f"{sn} {row[sn].get('blocked', 0):3d} {row[sn].get('saves', 0):+.3f} ({row[sn].get('saves_day', 0):+.2f}/d) w/o5 {row[sn].get('saves_wo_its_5_best', 0):+.3f}" for sn in ["DEV", "VAL", "VAL_ex_attack", "HOLD"]))
for name in BLK:
    print(f"{name:20s} HOLD per run " + " ".join(f"{r} {res['rules'][name][r].get('blocked', 0)}/{res['rules'][name][r].get('saves', 0):+.3f}" for r in HOLD)
          + f" | norm {res['rules'][name]['HOLD_size_normalised']['saves']:+.3f} w/o5 {res['rules'][name]['HOLD_size_normalised']['saves_wo_its_5_best']:+.3f}")
print(json.dumps(res["overlap"])); print(json.dumps(res["sanity"]))
for sn in ["DEV", "VAL", "HOLD"]: print(sn, json.dumps(res["ten"][sn]))
