#!/usr/bin/env python3
"""VERIFY step 3: add hashes, mechanics notes, look-ahead audit, TEN sensitivity and verdicts to VERIFY.json (numbers from v_sim.py)."""
import json
V = "/home/it/sniper/ops/strategies/presend/filters3/verify/VERIFY.json"
D = "/home/it/sniper-data/filters3/verify"
r = json.load(open(V))
ts = json.load(open(f"{D}/VERIFY_ts_at_trigger.json"))
R = r["rules"]
def line(n):
    x = R[n]; return {s: {"blocked": x[s]["blocked"], "saves": x[s]["saves"], "saves_day": x[s]["saves_day"], "saves_wo_its_5_best": x[s]["saves_wo_its_5_best"]}
                      for s in ["DEV", "VAL", "VAL_ex_attack", "HOLD", "HOLD_ex_r43", "HOLD_size_normalised"]}
r["hashes"] = {"quiet3/quiet3_score.py": "34b2e63276eb553c3515ba59a319faf0cddc083425887f565a11e635dc22cf49 (matches FROZEN)",
               "tail/tail_score.py": "aed9092969af7570230a57aac9c09d69289ead6672f0c7bcff61a08518f244de (matches FROZEN)",
               "tail/tfeat.py": "cdbc7d2557c8067c8e9f113cc227995c7486e3e4f98b789dd14e28f69cd8c66c (NOT imported by tail_score.py; hashed anyway)",
               "tail/tlib.py": "78a693a0d880e3c494f60dbc7008b9673e32676b53f07b7c558b8b25397f09b3 (NOT imported by tail_score.py; hashed anyway)",
               "ten/score.py": "8bde9ac1ab3856453d55dbd5c46479e53da875a68fd0e0dbe7782944e6440b43 (matches prefix 8bde9ac1ab3856453d55)",
               "creator_seed_r37_r42.json": "6c574cb13666892bc3fb763d246c7c1ad5b5f7d746ff459ba5cdccbef225b6b2 (matches FROZEN)",
               "copies": "verify/frozen_copies/ (SHA256SUMS.txt); all runs used the copies"}
r["mechanics_changes"] = ["quiet3: the FROZEN holdout command '--list --warm r42 r43 r44 r45 r46' scores NOTHING (the --warm parser swallows every following file). "
                          "Run instead as '--list r43 r44 r45 r46 --warm r42' (argument order only, no code change). Without --warm: holdout saves +0.811.",
                          "tail: run exactly as FROZEN (seed chain r43->r46). No change.", "ten: run exactly as FROZEN per run. No change.",
                          "v_extract.py / v_ten.py call the frozen copies' own functions (import / runpy) to get per-trade rows for pooling, w/o-top-5 and the combined set."]
r["frozen_scorer_outputs_holdout"] = {
    "QUIET3": {"r43": [16, 0.007], "r44": [35, 0.852], "r45": [14, 0.086], "r46": [1, -0.012], "total": [66, 0.933], "no_warm_total": [64, 0.811]},
    "REC": {"r43": [4, -0.004], "r44": [32, 0.422], "r45": [8, 0.008], "r46": [2, 0.008], "total": [46, 0.434]},
    "note": "[blocked, SOL saved]; my chained simulation reproduces these exactly, and reproduces the agents' DEV/VAL numbers exactly (QUIET3 +2.260/+3.173, REC +0.842/+3.923)"}
r["lookahead_audit"] = {
    "QUIET3_A": "clean. v2.n_120s (pq::V2Ring, trades before the trigger) and quiet.wh_dumps (DumpBook::whale, dumps closed s+2 < s0) are both computed at the arm (presend_quiet.rs 430-506, 209-395). A is inactive while quiet.rule_on is false (r46: 5 T2 trades).",
    "QUIET3_B": "clean. History = own KEPT positions with known = max(buy+3 s, last sell landing) < trigger t; label from presend_live_tape up to our last sell landing; blocked positions never enter. Carrying history across runs needs a new state file (engine has none today).",
    "TAIL_G1": ["MINOR LEAK: the ledger adds the realized P&L of EVERY position, including ones G1 itself (or another filter) blocked; an engine has no realized P&L for a skipped trade. Alone: holdout +0.433 frozen vs +0.425 kept-only (DEV +0.842 vs +0.908). Combined with QUIET3 it matters: union +0.951 vs honest sequential +0.773 on holdout.",
                "TIMING: decided at the filled attempt's SIGNING time while FROZEN says check at arm; at trigger time holdout REC drops +0.433 -> +0.394 (G1 +0.333 -> +0.295); DEV/VAL unchanged. Fine if the engine checks at each signing.",
                "the holdout seed holds every r37..r42 position (same issue as above, small)."],
    "TAIL_G3": "holders = list at OUR LANDING + post-signing sells added back; post-signing BUYERS are not removed. Checked with holder age (slots since first buy, at landing) vs fill slot - signing slot: of 45 G3 fires r39..r46, 2 include a post-signing fresh buyer, 1 would not fire at signing (pnl -0.005). Negligible. Hold count n is also read at landing (tiny).",
    "TAIL_G4": "clean (realized losses known at sell landing + 4 s; only kept trades feed it). Never tripped on holdout.",
    "SIZE15": "feature clean (v2.n_tr_60s at arm). Money is a replay ESTIMATE; beta (follower price-out) is inferred from an old study, not measured.",
    "WIDE5": "selection clean (pct/age at the trigger). Money ESTIMATE: calibration gap uses the SAME run's live-vs-shadow gap over the whole run (in-sample; r46 gap +54.9 mSOL from 7 pairs turns raw -0.066 into +0.043). QUIET / lone-whale skips not applied to wide windows."}
r["ts_at_trigger_sensitivity"] = {n: {s: ts["rules"][n][s]["saves"] for s in ["DEV", "VAL", "HOLD"]} for n in ["REC_frozen", "G1_frozen", "COMBINED_seq"]}
r["ten_sensitivity_text"] = open(f"{D}/ten_sensitivity.txt").read()
r["distortions"] = ["holdout = 14.23 h of live trading (r43 8.46 h, r44 4.81 h, r45 0.76 h, r46 0.20 h), 430 trades; per-day numbers use these hours",
                    "r43 traded at 0.15 (T2) / 0.35 (re-arm) SOL: its P&L and saves are ~1/4..1/2 scale; size-normalised rows (r43 scaled to 0.55/0.65) and ex-r43 rows given",
                    "r46: QUIET rule_on false (warm-up) on its 5 T2 trades -> rule A cannot act; r46 is 14 trades",
                    "r44 carries almost everything (QUIET3 +0.852 of +0.933; REC +0.422 of +0.433); r45 is 0.76 h",
                    "holdout is the newer market (follower bots gone since 11-02); no bait attack in it, so G3/G4 (attack guards) are untested"]
r["verdicts"] = {
    "QUIET3 (A+B)": {"DEV": 2.260, "VAL": 3.173, "HOLD": 0.933, "HOLD_day": 1.57, "HOLD_wo_5_best_saves": 0.338, "verdict": "PASS (by the bar; thin: r44 = 91% of it, r43 ~0, r46 -0.01)"},
    "  QUIET3 A alone": {"DEV": 1.802, "VAL": 2.253, "HOLD": 0.444, "HOLD_wo_5_best_saves": -0.137, "verdict": "WEAK (fails w/o top 5 on HOLD and on VAL ex-attack)"},
    "  QUIET3 B alone": {"DEV": 0.681, "VAL": 0.771, "HOLD": 0.568, "HOLD_wo_5_best_saves": 0.153, "verdict": "PASS on holdout (but DEV w/o 5 best -0.170)"},
    "REC (G1|G3|G4)": {"DEV": 0.842, "VAL": 3.923, "HOLD": 0.433, "HOLD_day": 0.73, "HOLD_wo_5_best_saves": 0.122, "verdict": "PASS by the bar but WEAK in substance (all from r44; minor G1 ledger leak; at arm time +0.394 / w/o5 +0.084)"},
    "  G1 creator": {"DEV": 0.613, "VAL": 1.844, "HOLD": 0.333, "HOLD_wo_5_best_saves": 0.072, "verdict": "PASS marginal (DEV w/o 5 best -0.159)"},
    "  G3 fresh": {"DEV": 0.229, "VAL": 2.079, "HOLD": 0.099, "HOLD_wo_5_best_saves": 0.0, "verdict": "WEAK (5 blocks; no attack in holdout)"},
    "  G4 breaker": {"DEV": 0.0, "VAL": 1.540, "HOLD": 0.0, "verdict": "UNTESTED (never trips on holdout)"},
    "SIZE15": {"DEV_day": 1.24, "VAL_day": 0.45, "HOLD_day": -0.04, "HOLD_wo_top5_day": -0.42, "HOLD_beta9_day": -1.00, "verdict": "FAIL (all three bar items fail; ESTIMATE)"},
    "WIDE5": {"DEV_day": 0.82, "VAL_day": 0.50, "HOLD_day": 0.35, "HOLD_wo_top5_day": -0.35, "HOLD_raw_day": -0.16, "verdict": "FAIL (w/o top 5 < 0; ESTIMATE)"},
    "COMBINED QUIET3+REC (sequential, kept-only histories)": {"DEV": R["COMBINED_seq"]["DEV"]["saves"], "VAL": R["COMBINED_seq"]["VAL"]["saves"], "HOLD": R["COMBINED_seq"]["HOLD"]["saves"],
        "HOLD_day": R["COMBINED_seq"]["HOLD"]["saves_day"], "HOLD_wo_5_best_saves": R["COMBINED_seq"]["HOLD"]["saves_wo_its_5_best"],
        "HOLD_live_before_after": [R["COMBINED_seq"]["HOLD"]["base"], R["COMBINED_seq"]["HOLD"]["after"]], "verdict": "positive on all three; HOLD w/o 5 best only +0.18"}}
r["summary_lines"] = {n: line(n) for n in ["QUIET3", "Q3_A", "Q3_B", "REC_frozen", "G1_frozen", "G3", "G4", "COMBINED_seq", "COMBINED_union"]}
json.dump(r, open(V, "w"), indent=1)
print("ok")
