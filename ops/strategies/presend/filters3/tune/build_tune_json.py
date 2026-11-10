#!/usr/bin/env python3
"""TUNE: collect the results into tune.json (verdicts + numbers + sha256 of the scripts)."""
import json, hashlib, glob, os
D = "/home/it/sniper-data/filters3/tune"; H = "/home/it/sniper/ops/strategies/presend/filters3/tune"
sha = {os.path.basename(p): hashlib.sha256(open(p, "rb").read()).hexdigest() for p in sorted(glob.glob(f"{H}/*.py"))}
t1 = json.load(open(f"{D}/t1_reconcile.json")); t4 = json.load(open(f"{D}/t4_live.json")); t5 = json.load(open(f"{D}/t5_creator.json")); t9 = json.load(open(f"{D}/t9_combo.json"))
t3 = json.load(open(f"{D}/t3_scan.json"))
out = {
 "program": "FILTERS-3 FILTER-TUNE (11-03 PKT)",
 "periods": {"DEV": "r37..r41 + r42 to 11-01 12:00 PKT (log rules: only runs that log their inputs)", "VAL": "r42 11-01 12:00 -> end",
             "VALx": "VAL without the attack span", "ATTACK": "11-02 08:28:24-08:36:55 PKT (first/last template trade +-60 s): 15 trades -2.238; template = fresh (<=1 hold) holders >= 35% at landing: 9 trades -2.026",
             "HOLD": "r43..r46 (opened by the verifier; final check only, nothing fitted on it)"},
 "reconcile_r42": t1,
 "live_skips_paper_ESTIMATE": {k: v["all"] for k, v in t4.items()},
 "live_release_subgroups_passing": {k: [s for s, d in v.get("sub", {}).items() if d.get("RELEASE_PASS")] for k, v in t4.items()},
 "log_rules_base": {k: v["base"] for k, v in t3.items() if k != "GR_grid"},
 "log_rules_refinements_passing": {k: [c for c, d in v["ref"].items() if d.get("PASS")] for k, v in t3.items() if k != "GR_grid"},
 "holder_grid_pass": sum(1 for g in t3["GR_grid"] if g["PASS"]),
 "creator_ledger": {k: t5[k] for k in ("gcr_logged", "carry cr>=0 n>=2 sum<=-0.05 win all", "carry cr>=0 n>=1 sum<=-0.1 win all", "carry cr>=3 n>=2 sum<=-0.05 win all",
                                         "run   cr>=3 n>=2 sum<=-0.05 win all", "QUIET3-B (last<=3 in 24h all not followed)", "B or carry cr>=0 n>=2 sum<=-0.05")},
 "next_build_sim": t9,
 "verdicts": {
  "create-slot skip (LIVE)": "KEEP. Paper +6.55 DEV / +5.70 VAL / +2.01 HOLD, w/o top 5 positive everywhere; no subgroup is safe to release (every pct/sol/whale-history/creator bin loses on paper in VAL or HOLD).",
  "QUIET skip (LIVE)": "KEEP as is. Paper +1.53 DEV / +0.09 VAL / +0.15 HOLD; no subgroup of the skipped set is positive in all periods (busy-looking ones n_120s>15 / nb50>8 win in VAL, lose in DEV and HOLD).",
  "age-1 skip (LIVE)": "KEEP (no value either way). r42's -1.15 is 5 paper winners (without them +0.03); DEV +0.86, VAL -0.61, HOLD +0.17; precision ~0.5 = coin flip. Not r42-only: r41 -0.46, r39 -0.10; r37/r38/r40 positive.",
  "lone whale (LIVE)": "KEEP (tiny): +0.22 DEV / +0.03 VAL / +0.13 HOLD.",
  "bad creator ledger (LOG)": "IMPROVE -> LIVE G1': carry the ledger across runs (state file), drop the creator-holds->=3% condition, kept positions only, check at ARM (T2 + re-arm): skip when the creator has >= 2 earlier kept positions with realized sum <= -0.05 SOL. DEV +0.87 (48 blocked, p0.62, w/o5 +0.05), VALx +1.70 (75, p0.69, w/o5 +0.94), HOLD +0.54 (52, p0.69, w/o5 +0.10). Run-only (dashboard) DEV -0.18. Precision is below the dashboard rule only in VAL (0.69 vs 0.80).",
  "group risk (LOG)": "LOG-ONLY. Real but weak signal: flagged trades are 10-20 mSOL worse than average in every period (DEV -3.1 vs +16.1, VALx -16.6 vs +3.9, HOLD -10.5 vs 0.0), so as a block ~0 in good markets (DEV +0.25, w/o5 -0.69), + in weak ones (VALx +1.19, HOLD +0.32, w/o5 -0.15). No refinement (60+ one-at-a-time ANDs, 324-combo holder grid, regime gate) passes. Landing-time feature: not enforceable as is (the signing-time form = landing guard fails).",
  "safe sell timer (LOG)": "DISMISS (subset of group risk: every safe flag is also a group flag in DEV; DEV -0.21, w/o5 -1.03).",
  "holder clock (LOG)": "DISMISS (DEV -0.22, HOLD +0.01, lift 0 in HOLD; duplicate of group risk).",
  "landing guard (LOG)": "DISMISS (DEV -1.52, flagged trades BETTER than average in DEV: +28 vs +14 mSOL).",
  "ctx85 (LOG)": "DISMISS. r42 +2.26 = +2.03 from 7 attack trades; ex-attack DEV -0.59, VALx +0.81 (w/o5 +0.19), HOLD +0.06; G3 catches the same attack trades at ~0 cost on normal days.",
  "LOG total (dashboard)": "r42 +2.293 = attack 7 trades +2.033 + the other 291 fills +0.260 (w/o top 5 -0.73)."
 },
 "scripts_sha256": sha,
}
json.dump(out, open(f"{H}/tune.json", "w"), indent=1)
print("wrote", f"{H}/tune.json", os.path.getsize(f"{H}/tune.json"))
