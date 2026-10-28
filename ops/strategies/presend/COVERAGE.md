# Pre-send coverage audit — FRA run 28 (dip22)

Run 28 started 10-28 14:31:56 PKT. This audit covers the run up to ~19:47 PKT (5.26 h) and was read-only.
Inputs:
- the run's records (`/root/prod/runs/dip_r28.jsonl`, presend_* / dump / attempt lines only);
- the FRA recorder chunks, read from the container copies in `/home/moiz/sniper-data/collect/run_20261027_1410` and `run_20261028_1405`, decoded with `real/decode.py`;
- the engine source (`src/presend.rs`, `src/bin/snipe_engine/dipmode.rs`, `src/bin/snipe_engine/pslive.rs`).

Scripts and outputs: `/tmp/claude-1000/-home-moiz/b89fe85a-.../scratchpad/ps_cov/` (replay.py, replay2.py, cmp.py, skips.py).

## Bottom line
- **The engine misses almost no triggers.** It saw every token created during the run, and its triggers match an offline replay of the same rules exactly (MEASURED).
- **Most skips are deliberate, and on the run's own shadow they would have lost money.** These are the create-slot and QUIET skips (MEASURED).
- **The real silent loss is inside armed windows.** In 55 armed windows the shadow filled and live did not. One cause: the helius-ps path is capped at 20 attempts/s, so a window gets about 4 tries per slot, not 8 (MEASURED).

## 1. DGW974 (created 19:41:32 PKT): no bug
- The run uses `whale_pct 6.0`, as `run_start` → `presend.whale_pct` and `presend_live.whale_pct` show. The status line also says "T2 whale >= 6%".
- The engine saw the create: the dip side logged 28 `dump` events for this mint, with age counted from the create (MEASURED).
- From the recorder tape, each wallet's holding at its first ≥ 3% buy (MEASURED):

| Wallet | Slot after create | Holding |
|---|---|---|
| 7QDpv9Xc | +1 | 4.995% |
| BLw4fXAc | +14 | 5.132% |
| DAYAW4fD | +354 | 5.993% |

- All are below 6%, so no trigger was correct.

## 2. Coverage of the run (MEASURED, 14:31:56 → ~19:44 PKT)
- **Creates:**
  - Recorder: 7,458 non-mayhem creates between run start and slot 462510793.
  - Shadow: `tokens 7464` at that slot.
  - So the engine followed every create (+6: creates the recorder lacks).
- **Triggers:**
  - The offline T2 detector (presend.rs rules, 6%, mayhem / launch-filter / insider rules) found 767 triggers on run-created tokens.
  - The live `presend_arm` records for the same span are also 767, with the same (mint, sig, j), both ways.
  - So 0 triggers were missed and 0 were extra.
- **Live parity:** the shadow and the live detector agree: "parity matched 796 live-only 0 shadow-only 0".
- **Blind spot (tokens created before the start):**
  - 10 triggers in 5.26 h (1.9/h) hit tokens created before 14:31. The engine has no history for them.
  - They came 1–8 h after the start, not only in the warm-up.
  - At the live yardstick (+0.0012 SOL net per armed window) they are worth ≈ +0.05 SOL/day (INFERRED).

## 3. Live skips (796 triggers: 356 armed, 440 skipped)
The shadow outcome per skip comes from the run's own presend_arm, presend_exit and presend_disarm records (MEASURED; gross and net-cheap are similar). The live yardstick: realized +0.489 minus failed-attempt fees 0.053 = **+0.435 SOL / 5.26 h ≈ +2.0 SOL/day** over 356 armed windows and 76 fills.

| Skip | n | Shadow fills (row a) | Shadow P&L, row a / row c (SOL, 5.26 h) |
|---|---|---|---|
| armed (for reference) | 356 | 122 | +3.03 / +1.90 |
| create_slot | 300 | 56 | **−0.77 / −0.08** |
| quiet | 82 | 13 | **−0.22 / −0.14** |
| blocked_armed | 33 | 0 (the shadow blocks them too: one window per token) | 0 |
| no_launch_accounts | 19 | 8 | +0.04 / +0.06 |
| blocked_position, blocked_ata_open | 6 | 1 | −0.08 / −0.01 |

**create_slot** (`pslive.rs` trigger(): `age_slots == 0 && !cfg.create_slot`):
- A create-slot trigger can only come from the create's *signer* when the create names a different creator (launchpads). Every other create-slot buyer is an insider (ht 2) and never triggers.
- `--presend-live-create-slot` is off by design. SHADOW.md shows these triggers at −3/day over 4 replay days, and V2_OPTIONS.md (d) agrees.
- Run 28 confirms it: −0.77 SOL on row a, i.e. arming them would have cost ~−3.5 SOL/day in shadow terms.

**quiet** (dip20 QUIET skip, all four signals): it saved money on this run too.

**blocked_armed** is a second whale on a token whose window is already armed. The study does the same (one window per token), so nothing is lost relative to the study.

## 4. "no-history mints 8264/8300" and "gaps"
At slot 462510793 the engine's count was 7,880. The recorder breaks this down as:
- **Mayhem launches created during the run: 1,944.** `Shadow::create` drops mayhem, so every later trade counts as no-history. This is by design (MEASURED).
- **Tokens created before the start: 1,831.** 1,773 of them were created 10-27 19:10 → 10-28 14:31; the other 58 are older (MEASURED).
- **Remaining ~4,100: old tokens traded only in version-1 transactions** (INFERRED).
  - The recorder does not capture v1 txs: getTransaction says "Transaction version (1) is not supported" unless asked for v1.
  - Checked on public RPC: 4 of the 31 no_history skips whose mint never appears in the recorder are v1 txs, mostly through the FLASHX8D router. One token was created ~12 days earlier.
  - The engine pushes ~3.5% more trades than the recorder holds: 619,031 vs 597,486. That count may include duplicate deliveries.
- **Creates missed during the run: ≈ 0** (section 2).
- **`presend_skip no_history` (213):** 164 mayhem, 18 pre-run tokens, 31 old v1-only tokens.
- **Gaps (1,783):**
  - A gap is a trade whose pre-state ≠ the last post-state the engine saw.
  - The recorder tape shows *more* gaps on the same tokens (2,013 over a slightly shorter span), so they are not engine feed losses.
  - Part comes from the 337 "late" drops (deliveries > 2 slots late).
  - The rest is INFERRED to be trades neither source decodes (e.g. v1 txs).
  - Impact: none on triggers (the exact 767/767 parity). Prices come from each trade's own post-state.

## 5. Inside armed windows: the actual loss
Of the 356 live arms, row a of the shadow filled 122 and live filled 76:

| Group | n | Shadow P&L, row a (SOL) |
|---|---|---|
| Both filled | 67 | +1.55 (live realized on these: +0.61) |
| Shadow filled, live did not | 55 | +1.48 |
| Live filled, shadow did not | 9 | (live realized −0.12) |

Why the 55 were missed, from each attempt's landing slot and index against the shadow's crossing trade (MEASURED):

| Reason | n | Shadow P&L, row a (SOL) |
|---|---|---|
| Our attempts landed only *before* the crossing trade in that slot | 16 | +0.46 |
| Landed after the crossing, but 6042 (price already back up) | 9 | +0.68 |
| No attempt sent for that slot | 14 | +0.34 |
| Sent, but none landed in that slot (deadline / unseen) | 16 | +0.02 |

"No attempt sent for that slot" (14) has three causes:
- 5 were stopped early by QUIET (6:2) while the shadow later filled; their shadow P&L is about 0.
- 9 are whale_sold or expired windows where the attempts had stopped before the fill slot.
- The sender also refused **7,213 attempts as `rate_path_config`**. The helius-ps path's own `[[send]]` max_per_sec budget is 20/s: no second in the run had more than 20 attempts.
  - So with 8/slot pacing (37/s), about 40% of due attempts were dropped, and a window really gets ~4–6 tries per slot.

## Table

| Cause | Triggers or fills lost per hour | Est. SOL/day lost | Fix idea (not built) | Risk |
|---|---|---|---|---|
| Creates missed by the feed | 0 (7,464 vs 7,458; triggers 767/767) | 0 | none needed | the parity is recorder vs engine on the same box; an RPC spot-check would make it independent |
| Pre-run tokens (no history) | 1.9 triggers/h | ~+0.05 (INFERRED, live yardstick) | preload balances for the last ~24 h of creates from the recorder at start (QUIET already preloads `current_run`) | preload time; wrong balances if the recorder has gaps |
| Old tokens traded in v1 txs (~4,100 mints) | unknown, likely ~0 (old tokens rarely hit the < 100 SOL whale rule) | ~0 | none for the engine; **the recorder should capture v1 txs** (replays undercount ~3.5% of trades) | replay-vs-live mismatches until fixed |
| create_slot skip | 57 triggers/h | **saves** ~3.5 (row a) / 0.4 (row c) shadow | keep it off | none |
| QUIET skip | 15.6 triggers/h | **saves** ~1.0 / 0.6 shadow | keep | none |
| blocked_armed / blocked_position / ATA | 7.4 triggers/h | 0 (the study blocks them too) | none | — |
| no_launch_accounts | 3.6 triggers/h | +0.1 (live yardstick) – +0.2 (shadow row a) | build the buy accounts from the CreateEvent instead of `detect_launch` (CPI / launchpad creates) | non-standard launch layouts → failed attempts |
| Rate cap on helius-ps (20/s) | 40% of attempts; 14 shadow fills had no attempt in their slot (2.7/h) | up to ~+0.6 (INFERRED: 14 × shadow P&L × the 39% live/shadow ratio on common fills) | raise the path's `[[send]]` max_per_sec to ≥ 40, or add a second path for pre-send attempts | **send-path change: owner OK needed**; more failed-attempt fees (~+0.05 SOL/day at 5,120 lamports each) |
| Landing timing (in-slot before or after the crossing) | 25 shadow fills / 5.26 h (4.8/h) | the shadow says +1.1 SOL / 5.26 h; real value unknown | speed and placement work (out of scope here) | the shadow's row a assumes 0 ms landing, which is optimistic |
