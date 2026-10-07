# Stage 0 exit report

> Win-mix correction (2026-10-07, WP-11 review #12): by mint, FT-007 is 31 meme vs 34 common and FT-007 + FT-008 is **73 vs 66** (one "CAKE" win was the cake.xmr meme); the rule still passes.
>
> **Stage 0 CLOSED (owner, 2026-10-07):** the three telemetry items below are waived in writing (PLAN §9, OD-T), as exec coverage was (OD-1). Their fixes are carried into Stage 1.

- **Date:** 2026-10-07, written 02:20–03:10 UTC by Claude for the owner's review. Not committed.
- **Scope:** the canary series the owner set for the exit: **FT-005 + FT-006 + FT-007 + FT-008**, 16 segments, 12.05 h, wallet frz `FRZh63L6…`. FT-004 (the first 1 h canary) is shown in the series table for reference only.
- **Method:** every number below was recomputed from the recorded files, not copied from the FT docs.
  - Money comes from the chain ledger (`ledger.jsonl`), with the `pre_run: true` rows (signatures re-read from the previous segment at boot) excluded.
  - Data: `/home/moiz/arbx-offload/ft00{5,6,7,8}/…` (pulled earlier), plus read-only copies from Cherry in `/home/moiz/arbx-offload/stage0-exit/`.
  - The scripts used are in `/home/moiz/arbx-offload/stage0-exit/scripts/`.

## 1. Verdict

**Stage 0 does not pass as written. It passes on every gate except "Telemetry populated"; exec coverage is waived by the owner (OD-1).**
1. **What fails:** three telemetry items.
   - PoH trigger share 5.9% (target ≥ 90%).
   - Verdict sequence on 99.37% of sends (target 100%): 0.52% lack one outside the result stream's one outage.
   - Complete `blockctx` 0.7% on the one segment checked (target ≥ 95%), a consequence of the exec-coverage shortfall OD-1 waived.
   - The gate's other items hold: leader, state version, blockhash and stage timestamps on 100% of attempts; RTT on ≥ 99.5%.
2. **What passes:** every other PLAN §6 gate, and all 8 of the owner's trade-success criteria.
   - 231 / 231 landings net > 0; the series made +966,055 lamports.
   - Win ratio 2.61%; realised/quoted median 1.000.
   - 73 meme vs 66 common wins over FT-007 + FT-008.
3. **To close Stage 0:** a written owner waiver for those telemetry items (in PLAN §9, like OD-1), or fixes and a re-measure.

## 2. The series

| Test | Build | Hours | Sent | Landed | Win ratio | Net (lamports) | Net/h | Net per win | Tips / gross | Fees / gross | Meme / common wins |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FT-004 (reference) | 374fda1 | 1.01 | 415 | 12 | 2.89% | +37,053 | 36,527 | 3,088 | 48.3% | 31.9% | 1 / 11 |
| FT-005 | 374fda1 | 3.01 | 2,078 | 54 | 2.60% | +222,873 | 74,069 | 4,127 | 52.1% | 26.2% | 15 / 39 |
| FT-006 | 6f6163c | 3.01 | 2,404 | 38 | 1.58% | +232,600 | 77,157 | 6,121 | 23.9% | 34.2% | 9 / 29 |
| FT-007 | 6f6163c | 3.01 | 2,093 | 65 | 3.11% | +235,938 | 78,298 | 3,630 | 29.7% | 40.7% | 30 / 35 |
| FT-008 | b1318ef | 3.01 | 2,282 | 74 | 3.24% | +274,644 | 91,116 | 3,711 | 31.2% | 39.5% | 42 / 32 |
| **Series FT-005…008** | | **12.05** | **8,857** | **231** | **2.61%** | **+966,055** | **80,163** | **4,182** | **36.1%** | **34.8%** | 96 / 135 |
| Meme-rule window FT-007 + 008 | | 6.03 | 4,375 | 139 | 3.18% | +510,582 | 84,708 | 3,673 | 30.5% | 40.1% | **73 / 66** |

- **Hours** are each segment's start (`meta.json` `run.started_ns`) to its stop (`stop.json` `ended_ns`), summed. Boot and drain are included; the gaps between segments are not.
  - The FT docs used about 2.99–3.0 h, so their net/h figures are 0.5–1% higher (FT-008: 91,982 there, 91,116 here).
- **Sent** = attempts with `sent: true` = copies (one copy per attempt). **Landed** = ledger route rows with `ok: true`.
  - Wins/h: FT-005 17.9, FT-006 12.6, FT-007 21.6, FT-008 24.5; series 19.2.
- **Net** = Σ `trade_net` = gross − tip − fee (non-recoverable rent is 0 on every row).
  - Gross per test: 187,905 / 1,029,727 / 555,298 / 797,760 / 937,503; series 3,320,288.
  - Tips: 90,852 / 536,854 / 132,698 / 236,822 / 292,859; series 1,199,233.
  - Fees: 60,000 / 270,000 / 190,000 / 325,000 / 370,000; series 1,155,000.
- **Cross-checks, all equal:**
  - every campaign's net, fees, tips, gross and rent equal its `spend.json` `budget_md_row` (ft004, ft006, ft007, ft008) or its `budget-state.json` entry (ft005 −93,543, ft005b −129,330);
  - the cumulative −1,003,108 equals BUDGET.md.
- **The FT-004 … FT-008 results sections are confirmed** for every per-segment sent / landed / win ratio / net row, the totals, the smallest win, the rent figures, the win mix and the memes' share of net.
  - The only difference is the net/h basis noted above.
  - Not re-checked: the leader-kind land rates, FT-007's size distribution, and FT-008's wins on WP-22-added pools and its refresh timings.

### Every win's token (the mix counts each win by `route.mint` in attempts.jsonl; the common list is FT-008's)
- **FT-007** (30 meme / 35 common):
  - common: USDC 29, MET 2, PUMP 1, CAKE 1, JUP 1, BELIEVE 1;
  - meme: Attention+ 7, ANISOM 3, phubber 3, OTC 2, baton 2, and 1 each of STONK10, YAJUCoin, PAID, memee, CTO, GIGACAT, PLAGUE, SI, swordcat, GYM, UP, FLAME, SPEC.
- **FT-008** (42 meme / 32 common):
  - common: USDC 27, USDT 5;
  - meme: Aiden 3, mamAOCita 3, Attention+ 3, cashrat 3, 2 each of OTC, ANSEM, fone, FLAME, SPLICE, CTO, baton, BP, and 1 each of CATE, HUHCAT, www, XPLX, PAID, phubber, AUTON, SPEC, GRIFFAIN, CYBERLEEK, SLOPCORE, CARDS, SUMMIT, DEXPAD.
- **FT-005** (15 / 39):
  - common: USDC 28, MET 5, JUP 4, USDT 1, BELIEVE 1;
  - meme: Buttcoin 3, STONK 2, and 1 each of Aiden, $RIBBIT, EGO, STONK10, Human, SM, ANSEM, MADE, Cupsey, 67.
- **FT-006** (9 / 29):
  - common: USDC 24, MET 5;
  - meme: GRIFFAIN 2, and 1 each of Cadence, ABU, Buttcoin, ANSEM, ELON, TIPTOE, STONK.
- **Mints checked:** every common win's mint is the canonical one (USDC `EPjFWdd5…`, USDT `Es9vMFrz…`, MET `METvsvVR…`, JUP `JUPyiwrY…`, BELIEVE `BLVxek8Y…`, PUMP `pumpCmXq…`, CAKE `DAemPFNc…`). Every route's hub is WSOL.
- **By net, FT-007 + FT-008:** meme wins made +361,035 of +510,582 (70.7%).

## 3. Gates

### 3a. PLAN §6 "Stage 0 exit" (with the owner's changes)

| Gate | Evidence | Verdict |
|---|---|---|
| **Bundle-only, no failure fees** (24 h → the 12 h series, owner) | **Copies:** 8,857 in 16 segments, every `path` `jito-bundle`: 0 non-bundle copies. **Ledger:** 231 route rows, all `ok: true`, categories only `trade_gross` / `tip` / `fee_win`: 0 failed landings, 0 `fee_fail`. **Outcomes:** finals only `landed_ok` (231) and `not_landed_expired` (8,626); `failed_fees_total_lamports` 0 on all | **Pass** |
| **Money reconciles** (hourly, within 10k, total and liquid basis) | **Windows:** 97 recon windows in 16 segments (start, every ~10 min, stop), all `ok`. Residual 0 and liquid residual 0 in every one; executor diff 0; 0 unexplained, 0 provisional, 0 refused bundles landed, 0 owner transfers. **Chain view:** equity agrees too (ft008-p1: liquid equity +32,887 = the ledger's net) | **Pass** |
| **No prediction pricing** | **Tests:** `decoded_swap_is_a_hint_only`, `a_failed_swaps_prediction_never_prices_the_other_pool` and `s1_a_split_route_is_never_priced_half_updated` pass (engine unit tests, HEAD). **Pending accounts:** decisions.jsonl of **all 16 segments** checked (1,128,152 decisions, 8,857 send decisions = the 8,857 sent attempts). 0 routes priced with a `pending_commit` / `fork_pending` / `parts_skewed` / `resync` / … reason; every send decision's route has reason `best`. The guard fired: 384,994 `pending_commit` route rejections, equal in each of the 16 segments to the status counter `reject_pending_commit`. **`torn_suspect`:** 82 decisions flagged in the series (the `torn_suspect` follow-up lines of decisions.jsonl, equal to commits.jsonl's late lines). Of these, **1 was sent** (ft005b-p2, attempt 183, not landed): 1 / 8,857 = **0.011%** (limit 0.1%) | **Pass** |
| **Rent** | **Held rent:** `rent_recoverable` 2,976,880 in all 102 snapshots (start, every 10 min, stop): it never grows. **Create+close:** 123 landings, rent 184,983,120 locked = 184,983,120 reclaimed in the same transactions; ledger `rent_nonrecoverable` 0 on all 231. **One account:** the snapshots show a constant 1,346,200 non-recoverable in a PumpSwap-owned account `CUiyUSbx…`. By owner and size it is the user-volume accumulator (OD-10 prices its creation at 1,346,200). It is there from FT-005's first snapshot, so it was not created in the series; its origin was not checked | **Pass** |
| **Scenarios** S1–S16 (+S1b, S1b', S4b, S8b) | `cargo test --release --lib scenarios` at HEAD ce86781 (code = 221a2d8): **65 passed, 0 failed, 1 ignored** (`digest_points::cut_the_ft001_p1_tail_fixture`, a fixture cutter). S1 / S1b / S1b' (`s1b_late_member_marks_torn_suspect`), S2–S16, S4b and S8b are all present. HEAD is newer than the canary builds; b1318ef's merge recorded 621 tests passing | **Pass** |
| **Replay** (a 1 h run replays to identical compared fields) | **FT-007 p2** (canary, a full 60 min, 3,635 s of engine time, executor replayed from `exec_init`, 2,831 settlements fed): `arbx replay --compare` **ok, whole**. 74,701 / 74,701 decisions, 78,967 / 78,967 commit groups and 738 / 738 attempts identical; state and decision digests equal at `run_end` and `stop_end`; 0 journal gaps, 0 missing accounts, 0 verdict mismatches. **Also ok:** FT-007 p3 (58.1 min: 71,283 decisions, 73,851 commits, 555 attempts identical, digests equal) and FT-008 p3 (30 min, b1318ef's code: 39,257 decisions, 38,893 commits, 300 attempts identical, digests equal). Earlier, FT-001b (1 h shadow, 374fda1) replayed ok (FT-002 doc; not re-run here). **Binary:** replayed locally with `arbx-185fa02` (`/home/moiz/arbx-offload/targets/wp22-review/release/arbx`, sha256 `de78d077…`, clean); its `src/`, Cargo.toml and Cargo.lock equal b1318ef's, and 6f6163c→b1318ef changes only campaign / config / main / poolrefresh. `same_binary` is false (stripped Cherry binary vs this build) | **Pass** (code-identical build, not the same binary) |
| **Telemetry populated** | **100% of 8,857 attempts:** leader identity and kind, state version `sv`, blockhash age and source, all 9 state-path stage timestamps (`t_update_recv` … `t_enqueued`), `t_first_shred`. **Host → leader RTT:** 99.5–100% per segment (≥ 95%). **Verdict sequence:** 8,801 / 8,857 outcomes (99.37%). Of the 56 without one, 10 belong to the one result-stream outage (ft007-p1, attempts 541–550: sent from 26 s before the "stream ended" event to 10 s after it came back). **46 (0.52%) lack verdicts outside it:** 42 landed bundles, and a 58 s cluster of 4 in ft008-p6 with no down event. **`poh_trigger_pct`:** 519 / 8,833 = **5.9%** of attempts while ≥ 1 PoH-capable feed was alive (summed from the status gauge's per-interval counts; a PoH-capable feed was alive in 98% of status lines; 635 / 8,857 = 7.2% of outcomes carry a trigger PoH position) vs **≥ 90%**. **Complete `blockctx` ≥ 95% within 10 min:** checked on one segment only, ft008-p1 (`arbx-report blockctx --offline` on its exec / slotidx / accounts / leaders): **2 of 280 attempts (0.7%) complete**. 1,185 of 1,680 slot references lack a slot-index line or an exec `idx` for a route writer: the exec-coverage shortfall OD-1 waives. Not measured on the other 15 segments, and `--fill-gaps` (RPC) was not run | **Fail** (PoH share, verdict sequence, blockctx on the segment checked) |
| **Recording** | Final status line of all 16 segments: `recorder.dropped_total` {} (0 in every class: core, replay `accounts` / `journal`, chain, bulk), `io_errors_total` {}, `io_lost_total` {}, `encode_errors_total` {}, `writers_dead_now` []. All three replays were whole: 0 recorder drops, 0 journal gaps, 0 missing account records | **Pass** |
| **Exec coverage (F1)** | **Waived by the owner** (OD-1, 2026-10-06, PLAN §9, commit 349140d): *"We don't have RPC options right now. Haan is all we have as is. We gotta make do for now. Before Stage 1 I'll try to manage another."* **Measured anyway:** `coverage.watched_with_tx_pct` 68.3% mean (median 72.6%) per status interval (60 s window, not the gate's 10 min); sampled unseen share 0.0% | **Waived** (owner, OD-1) |
| **Wallet** (`wallet.jsonl` = `getSignaturesForAddress`) | Public RPC (finalized, 1 call of 1,000 signatures covering slots 452,361,756–454,086,369) against the union of each campaign's `wallet.jsonl`, per campaign window. **Counts:** ft005 12 = 12, ft005b 42 = 42, ft006 38 = 38, ft007 65 = 65, ft008 74 = 74. **0 missing, 0 extra**, 0 chain signatures between the windows. **Fields:** 286 matched records (re-reads included), 0 slot and 0 error mismatches. The 231 are exactly the 231 ledger landings | **Pass** |
| **Provenance** | All 16 segments have `meta.json` with: build (git commit, binary sha256, `git_dirty` false); config (file and normalized sha256, `matches_campaign` true); programs (the route program `8K8uyQDt…` with ELF sha256 = expected `e4f03590…`; the 5 venue programs' hashes recorded); the probe (`probe.json` sha256 `7ae8dd02…`; the file is in all 16 segment directories on Cherry). All 16 have `stop.json` with a reason: 14 `deadline` (exit 0), 2 `control` (exit 10, the owner's stops: the pool refresh in FT-005 and its shortening to 3 h) | **Pass** |
| **Reports** (`arbx-report segment` regenerates, deterministic) | **FT-007 p3** (the pulled core and replay streams, 2.2 GB): run twice, `--offline`, 8.5 and 8.3 min. Outputs are byte-identical: `report.json` sha256 `aeed724e7dc1…`, `report.md` `d944ce63d651…`, `diff -r` empty. Of its 14 sections, 7 are complete; 7 say "incomplete" and name the cause: streams not pulled (exec, slotidx, leaders, feeds, caps), no `--arbx-bin` for `arbx quote`, or no WP-11 arms. **FT-008 p1** (local subset): run twice, identical. **Known bug:** `arbx-report ledger` sums `pre_run` rows (§5) | **Pass** (runs, deterministic); every section's regeneration from a complete segment with `--arbx-bin` was not run |

### 3b. The owner's trade-success criteria (FT-008 "Stage 0 exit")

| Criterion | Evidence | Verdict |
|---|---|---|
| Every landed trade nets > 0 | 231 / 231 (FT-005…008): smallest +84 (ft008-p6), largest +82,773 (ft006-p1); FT-004 12 / 12 | **Pass** |
| Series net ≥ 0 | **+966,055 lamports** (+1,003,108 with FT-004) | **Pass** |
| ≥ 10 wins | **231** | **Pass** |
| Realised vs quoted median within ±10% | Median `trade_net` / `attempts.expected.net` = **1.000** in every test and the series (table below) | **Pass** |
| Win ratio per send ≥ 0.3% (stretch 0.5%) | **2.61%** (231 / 8,857); lowest test 1.58% (FT-006) | **Pass**, stretch met |
| Bundle-only, 0 failed-landing fees | As in 3a | **Pass** |
| Reconciliation ok at every stop | 16 / 16 stop reconciliations `ok`, `final`, residual 0 / 0 | **Pass** |
| Win mix: more meme than common, over FT-007 + FT-008 | **73 meme vs 66 common** (FT-007 30 / 35, FT-008 42 / 32). PUMP and CAKE are counted as common | **Pass** (a 5-win margin) |

**Realised vs quoted (each landed win: ledger `trade_net` / the attempt's `expected.net`)**

| Test | Wins | Median | p10 | p90 | Min | Max | Exactly equal | Within ±10% | Σ realised / Σ quoted |
|---|---|---|---|---|---|---|---|---|---|
| FT-005 | 54 | 1.000 | 1.000 | 1.000 | 0.195 | 1.090 | 50 | 52 | 0.969 |
| FT-006 | 38 | 1.000 | 1.000 | 1.000 | 0.602 | 3.751 | 34 | 35 | 1.376 |
| FT-007 | 65 | 1.000 | 0.985 | 1.000 | 0.093 | 3.041 | 56 | 59 | 0.794 |
| FT-008 | 74 | 1.000 | 0.984 | 1.000 | 0.003 | 1.000 | 61 | 67 | 0.307 |
| **Series** | **231** | **1.000** | 0.993 | 1.000 | 0.003 | 3.751 | **201** | **213** | **0.608** |

- **The median passes, but the aggregate is 0.61 because of one win.**
  - FT-008 p2, token `fone`, size 0.05 SOL: quoted +595,544 (gross 700,544, tip 100,000 at the cap), realised +22,701 (gross 127,701).
  - Without it, the other 230 wins realise 0.949 of their quotes.
- **18 wins fall outside ±10%:** 14 below, 4 above (the largest is FT-006's Cadence at 3.75×).

## 4. Owner decisions during Stage 0

| Date (UTC) | Decision | Where |
|---|---|---|
| 2026-10-05 | Live tests on the frz wallet, with a pre-approved test budget of $3–5 (hard cap 34,000,000 lamports, target ≤ 21,000,000); "never drain it" | PLAN-ADDENDUM I-11 update, BUDGET.md |
| 2026-10-06 08:54 | Trade-success criteria added to the exit (every landing > 0, net ≥ 0, ≥ 10 wins, realised/quoted ±10%, win ratio ≥ 0.3%), and the $500 trigger: net positive over 48 h of canary | PLAN-ADDENDUM "Owner decision (2026-10-06)", commit 5f38309 |
| 2026-10-06 08:55 | **OD-1: the exec-coverage gate (F1) is waived for Stage 0** ("We gotta make do for now"); a second provider before Stage 1 | PLAN §9, commit 349140d |
| 2026-10-06 09:11 | Astralane's deshred feed dropped ("subscriber limit reached", a 429 storm in FT-001 p3) | commit b95a654 |
| 2026-10-06 12:51 | The exit canary FT-005 runs 12 h instead of 24 h; PLAN §6's "24 h live" items are measured over it | commit 06e094c |
| 2026-10-06 ~14:15 | Pool refresh in the middle of FT-005 (ft005-p1 stopped by the owner); FT-005 continues on the fresh list as ft005b | ft005-p1 `stop.json`, commit 02a45ef |
| 2026-10-06 15:41 | FT-005 shortened to 3 h; **Stage 0 closes after FT-007**, criteria over FT-005 + FT-006 + FT-007 (about 9 h) | commit ecc3404, ft005b-p3 `stop.json` |
| 2026-10-06 16:44 | WP-22 started ("test it before closing Stage 0"); **Stage 0 closes after FT-008**, criteria over FT-005…FT-008 (about 12 h) | commit f952cee |
| 2026-10-06 18:04 | Win-mix criterion: more meme / long-tail wins than common-token wins | commit 141b8c7 |
| 2026-10-06 20:17 (FT-006 rule) | **Keep the 0.2 tip shares** (net SOL/h 77,562 ≥ FT-005's 74,600) and **keep the BAM landing fix** (BAM-led land rate 1.77% vs Jito-led 1.47%, target ≥ 70% of Jito's) | FT-006 doc, commit 8075f4d |
| 2026-10-06 23:19 (FT-007 rule) | **Keep the 0.05 SOL size cap and the small rungs** (78,668 ≥ 77,562); PUMP and CAKE listed as common protocol tokens | FT-007 doc, commit 149e5c1 |
| 2026-10-07 00:59 | **The meme rule counts FT-007 + FT-008 only** ("meme rule is for ft007,008"); the other criteria still cover FT-005…FT-008 | commit 347caa0 |
| 2026-10-07 01:30 | FT-010 (tip share 0.1) and FT-011 (size cap back to 0.2 with small rungs): criteria agreed before the runs (Stage 1 tests) | commit 3658a93 |
| 2026-10-07 02:20 (FT-008 rule) | **Keep the automatic pool refresh (WP-22) on for Stage 1** (both pass/fail lists held) | FT-008 doc, commit ce86781 |

## 5. Open items carried into Stage 1

1. **Telemetry gate (blocks the exit unless waived):**
   - **PoH trigger coverage** is 5.9% vs ≥ 90%: only about 1 attempt in 17 has its trigger's PoH position, although 2 PoH-capable feeds report alive.
     - PLAN OD-6 notes that PoH coverage depends on the dead feeds.
     - Astralane's deshred feed was also dropped on 2026-10-06.
   - **Verdict sequence:** 46 sends (0.52%) have no block-engine verdict outside the one outage. 42 of them landed, and 4 form a 58 s cluster in ft008-p6.
     - Find out whether Jito skips results for some bundles, or we drop them.
     - The stream also went quiet about 26 s before its "stream ended" event (ft007-p1), so silent gaps are not detected.
   - **`blockctx` completeness:** 2 / 280 (0.7%) on ft008-p1, offline. It needs exec records with `idx` for the route writers, so it rises with exec coverage (OD-1's second provider).
     - The owner may want to extend OD-1's waiver to this item explicitly.
     - The other 15 segments were not measured.
2. **Exec coverage (OD-1):** waived for Stage 0 only. It needs the second provider or a bigger Haan plan before Stage 1 (discovery WP-14 / X8, the X1 census). Measured about 68% within 60 s.
3. **Toolkit bug:** `arbx-report ledger` (and the segment / campaign money sections built on it) sums the `pre_run` rows. Only the first segment of each campaign is inflated:

   | Segment | Rows added | Lamports added |
   |---|---|---|
   | ft005-p1 | 11 | +34,062 |
   | ft005b-p1 | 8 | +46,345 |
   | ft006-p1 | 16 | +49,689 |
   | ft007-p1 | 9 | +51,440 |
   | ft008-p1 | 11 | +111,648 |

   - Example: ft008-p1 shows 21 transactions / +144,535 instead of 10 / +32,887, in both `arbx-report ledger` and the segment report's R1 Money. R1's own outcomes cross-check shows +32,887.
   - The bot's counters, `spend.json` and `budget-state.json` are correct.
4. **Realised vs quoted outlier:**
   - FT-008 p2's `fone` win realised 3.8% of its quote and paid the 100,000 tip cap on a 0.05 SOL trade.
   - The series aggregate is therefore 0.61 (0.95 without it).
   - The fixed tip was sized on the quote; the realised gross was 18% of it.
   - The FT-004 doc already lists the related Stage 1 levers: the X4 tip share and arbx-exec CPI tips, which pay a share of the realised profit.
5. **Replay with the exact binaries:**
   - The three replays (FT-007 p2, FT-007 p3, FT-008 p3) used a code-identical local build (`arbx-185fa02`), not the stripped Cherry binaries.
   - To close that fully, replay one segment on Cherry with its frozen binary (`runs/ft007/arbx-7b4ea85f` = 6f6163c, `runs/ft008/arbx-d98188a5` = b1318ef) after the latency test (after 04:30 UTC; it is CPU-heavy), or build those commits locally.
6. **Scenarios** were run at HEAD (221a2d8 code), not at each canary build.
7. **$500 trigger:** net positive over 48 h of canary. Stage 0 has 13.1 h (FT-004…FT-008), all net positive.
8. **Win-mix margin:**
   - 73 vs 66 holds with the owner's closed list of common tokens: any token not on it counts as meme.
   - Moving 3 wins from meme to common would flip the result, so extending the list later could change it.
9. **Follow-ups from the FT docs:**
   - **FT-002:** a wider DLMM bin-array buffer, and simulating at the decision's state (7 DLMM simulation errors).
   - **FT-005:** the win ratio fell from 3.2% to 2.0% within 2 h on one list: pools go stale fast. WP-22 now refreshes every segment.
   - **FT-006 / FT-007:**
     - the tip and size decisions are time-separated and indicative;
     - the concurrent arms come with WP-11;
     - fees are now the largest cost (40% of gross in FT-007 / FT-008).
   - **FT-006:** BAM's gain over Jito is partly Jito's rate falling with the lower tips.
   - **FT-008:**
     - new pools from creation events in our own feed;
     - add the CLMM / Whirlpool venues to the refresh;
     - whether idle trimming helped p5 / p6 is not separable.
   - **Plan:** FT-009 (WP-21 CLMM shadow) results, then FT-010 / FT-011.

## Appendix: how the checks were run

- **Scripts** (`/home/moiz/arbx-offload/stage0-exit/scripts/`):
  - `an.py`: per-segment ledger, attempts, copies, outcomes, recon, snapshots, status, meta and stop; reads with the toolkit's own stream readers.
  - `wal.py`: the wallet against the public RPC, 1 request.
  - `decchk.py`: decisions, pending and torn checks.
  - `decpull.sh`, `ft007p2.sh`, `bc.sh`: the pull, check and delete chains.
- **Outputs** (`/home/moiz/arbx-offload/stage0-exit/keep/`): `an.json` (every per-segment number), `decchk.jsonl`, `wal.json`, the replay summaries, the FT-007 p3 segment report, the blockctx summary and the test logs.
- **Torn check:** the late lines (`torn_suspect_decisions`) of `commits.jsonl` in the 13 segments whose status counted `torn_suspect` > 0, crossed with `attempts.jsonl` `decision`; then confirmed from the decisions.jsonl follow-up lines of all 16 segments. Each segment's decisions were pulled, checked and deleted one at a time.
- **Replays:** `arbx-185fa02 replay --run <seg> --compare --out <dir>` on the replay-class files pulled from Cherry for ft007-p2, ft007-p3 and ft008-p3 (rate-limited scp; nothing written to Cherry). The `replay.json` and `replay-diff.json` are kept in `/home/moiz/arbx-offload/stage0-exit/keep/`; the pulled recordings were deleted.
- **Wallet:** `wal.py` makes 1 `getSignaturesForAddress` call (limit 1,000, finalized) to api.mainnet-beta.solana.com, plus 1 more for the slot and error comparison.
- **Tests:**
  - `flock /home/moiz/arbx-offload/build.lock env CARGO_BUILD_JOBS=3 cargo test --release --lib scenarios`;
  - the same with `-- decoded_swap_is_a_hint_only a_failed_swaps_prediction_never_prices_the_other_pool s1_a_split_route_is_never_priced_half_updated`.
