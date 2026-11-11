# dip46 B1 LOG shadow (LOG ONLY)

Build dip46 = dip45 (fleet log + whale-sold log) + a log-only shadow of the learned arm rule **B1** (owner-approved "B1 LOG PLAN v1"):
per token-slot the frozen **B0** score (push-l5/opt2 `FROZEN.md`, FINAL-train decoder + regressor), the fleet-SIGNATURE gate of the dip45
detector, a paper 8-slot window, and whether our live (or dry) windows were on the same token. Audit: `~/sniper-studies/push4-audit/REPORT.md`
(B1 by wallet list is dead; B1 by signature is GO for this shadow only; B0 alone NO-GO). Code `src/bin/snipe_engine/ps46_b1.rs` (inside the
`fleet-log` thread), tests `dip46_b1_tests.rs`, offline `ops/fleet45/b1_lib.py`, `b1_export.py`, `b1_fixture.py`, `b1_report.py`.

**Nothing is sent, armed, skipped, sized or changed; the engine reads nothing back.** Off (the default) = the dip45 build byte for byte.

## Flags (need `--presend-live`; work with `--presend-live-dry`)
| Flag | Default | Meaning |
|---|---|---|
| `--presend-live-b1-log on\|off` | off | the shadow; **needs `--presend-live-fleet-log on`** (its gate is the fleet signature detector) |
| `--presend-live-b1-model FILE` | built-in | the frozen B0 json; refused unless its sha256 is the frozen one `7158769d53d270f9fdd1c9949da3fd52aa9fd61aac2efedfea5c51d5244aa690` |

FRA dry run addition: `--presend-live-fleet-log on --presend-live-b1-log on` (optionally `--presend-live-b1-model /root/dip/dip46_b1_model.json`).
The run scripts' `--presend-live-*` whitelist must get `--presend-live-b1-log` (and `--presend-live-b1-model`), as for the dip45 flags.

## What it does
1. **Features (causal).** Every executed pump trade (all tokens) and create feeds a per-token state. When the executed feed's slot clock
   moves past a slot in which a token traded, the query (token, S = that slot + 1) is scored on trades **strictly before S**: the 25
   features of push-l5 `snap2.py` / push4 `p4_snap.py` (age, vsol, last trade, last-5-slot buy / sell max %, trades, 100-slot activity,
   buyers, buy / sell SOL, run-up, drawdown, holders top1 / top3 / >= 2,4,6 %, creator balance, earlier dumps). Tokens off the standard
   curve (< 90% of their trades with k within 3%) are not scored (the tape's rule).
2. **Score.** Decoder (HGB classifier, 25 features) probability; when >= 0.2 the regressor (HGB, lite + decoder score) = the expected
   window value in SOL (`b0_score`). Exact sklearn tree walk and summation order (floats stored as bit patterns).
3. **Rules.** `b0_pass` = decoder >= 0.2 and value >= 2 mSOL (frozen B0). `b1_pass` = decoder >= 0.2 and value >= 0 **and a fleet-signature
   try on the token in slots S-2..S-1** (dip45 flags `n2 > 0`; the audit's strict gate). One 8-slot window [S, S+7] per token at a time,
   separately per rule (push-l5 `make_windows`); a window opened by either rule is one record (`opens.b0` / `opens.b1`).
4. **Paper outcome** (push-l5 outcomes + push2-d `sim_one`, followers x1): the first dump in the window (run of sells in one slot,
   >= 3% / >= 0.3 SOL, drop >= 10%) fills at position i1 + 26 behind it (next slot past the slot's last pump index + 20), 0.8 SOL,
   exit at the start of slot entry + 3. Later-buy SOL / distinct buyers in [entry, entry + 3 slots).
5. **Live overlap.** Our live / dry `presend_live_arm` [arm slot, en_slot] or `presend_live_fill` on the token inside [S, S+7] =
   `overlap: "same"`, else `"new"` (offline, `--fills` adds the AMS live run's arms / fills).

## Records `"ev": "presend_live_b1"`
| stage | when | fields |
|---|---|---|
| config | start | model_src, model_sha, frozen_sha, feat_schema, features, reg_features, rule {dec_min, b0_thr, b1_thr, window, size_sol, dp, hold, drop, cost_slot_sol} |
| window | a window settled (fill: entry + 4 slots; none: S + 8; run end: `complete: false` if early) | mint, slot (= S), idx / last (the last trade before S), end_slot, kind (t2 / rearm / other = push-l5 cls_of on bb5 / bs5), dec_score, b0_score, b0_pass, b1_pass, opens {b0, b1}, gate_on2, gate_on8, gate_pre8, gate {n0..n8, pre8, signers8, first_slot, last_slot, gap}, live_armed, live_filled, overlap, fill, dump {slot, i0, i1, drop, sol, spct}, entry [slot, idx], exit_slot, dslot_fill, paper_sol, later_buy_sol_3, later_buyers, eval {exec_slot, slot_clock, t}, late_trades, f (the 25 features), model_sha (16 hex), feat_hash (16 hex of sha256 over f as f64 LE) |

Status line part `| B1 LOG: queries Q (dec>=0.2 D, b0 x, b1 y) windows b1 W (new N, fills F, paper +p) b0 W0 (fills, paper) open O late L`;
run_end `fleet.b1 {...}` (trades, creates, late, queries, passes, windows, fills, paper by rule, B1 new, max eval lag).

T2-like and re-arm-like windows are reported separately (`kind`): the audit's live data had fleet+T2 -21 mSOL/fill, fleet+re-arm +117.

## Parity (test `dip46_parity_with_the_offline_scorer`)
`testdata/dip46_b1_parity.json.zst` (`b1_fixture.py`): the real trades of 50 tokens of the push4-audit NEW tape (30 where the decoder passes
often, 20 random), 6,391 token-slot queries with the reference features (`b1_lib.features_at`, equal to the audit's `snap_all.parquet` on
all 6,391 rows), sklearn's own decoder / regressor predictions, and each query's 8-slot window outcome. The engine replays the trades tx by
tx and must match every row: features (relative 1e-9), scores (1e-9), dump / entry / paper / later-buy (1e-9). `b1_export.py` checks the
JSON scorer against sklearn on 20,000 audit rows (difference 0). Live: `b1_report.py` re-scores every logged window's `f` (parity line).

## Offline report
`python3 ops/fleet45/b1_report.py --engine dip_fra_rNN.jsonl [--fills dip_ams_rMM.jsonl] [--rule b1|b0]` prints the FILTERS-style rows
(ALL / same / NEW / NEW by kind / gate split; windows, would-fills, won / lost, net raw AND calibrated, cal mSOL per fill, per day,
later-buy median and shares), per day PKT with the NEW calibrated per-fill bootstrap 5% bound, the parity check, and the frozen lines:

- **>= 3 days and >= 1,200 would-fills**;
- **NEW would-fills >= +6 mSOL/fill CALIBRATED** (`~/sniper-data/gatecheck/calib.pkl` by kind / paper bucket; other = mean of T2 and
  re-arm) **with bootstrap lower bound > 0 on >= 3 of 4 days**;
- **later-buy median >= 1.4** (kill < 1.0);
- **zero parity mismatch**.
Net = value - 0.055 mSOL per armed slot (frozen). Not priced (audit section 3): the real catch rate (~48% of >= 10% dumps), own-fill
calibration on B's own windows, follower reaction to our size; only a small live A/B measures those.
