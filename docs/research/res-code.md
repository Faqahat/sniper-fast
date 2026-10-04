# Architecture and the uncommitted code that is running live

## Scope and state at review time

The live state changed while I worked. The **local `src/` now builds the deployed binary byte for byte**: `sha256(target/release/arb-lab) = sha256(/root/arb-lab/arb-lab-w) = bbad56d6…`. That binary was deployed at 20:54:47 UTC after `src/venues/cp.rs` was edited at 20:53 (PumpSwap virtual reserve read as signed `i128`). Timeline, from `w5h.supervisor.log`, file mtimes and hashes:

| seg | binary | ran | result |
|---|---|---|---|
| p11 | 20:27 build | 81 s, stopped with SIGINT | 81 sent, 1 win (profit −1,494,010) |
| p12 "hybrid" | 40ad9a55 (20:49) | 448 s | 450 sent, 75 landed, 1 win, failed fees 497,170 |
| p13 | bbad56d6 | 96 s | 53 sent, 0 landed |
| p14 | bbad56d6 | live since 20:59:10 | — |

The p14 config differs from the snapshot `arb-w.toml` (p11): `confirm_trigger_ms=60`, `tpu_cu_price_micro=60000`, `tpu_max_expected=0`, `tpu_min_expected=1.5M`. Enabled paths are jito-bundle, shyft, haan, tpu-direct, plus helius, astralane and nozomi with a 1M-lamport tip. The p12/p14 configs and the p12 small files are in `work/code/`. Nothing was written anywhere else, and no script was run on Cherry.

## 1. Live decision path (file:line)

1. **Feeds.** `feeds/mod.rs:83` `start`: UDP/multicast shreds go through `shred::Assembler` (:100-111); gRPC entries and deshred go through `grpc::feed_once` (grpc.rs:272) and then `forward` (:154). The pool state stream comes from `start_state` (:209) and `accounts_once` (grpc.rs:361), at processed commitment, and also emits slots (grpc.rs:404). In p12 these feeds delivered 0 messages: raiden, corvus, getblock, constantk-prism and erpc (erpc also had connect timeouts). So `archive_feed="erpc"` produced a 13-byte `entries.zst`.
2. **Engine.** One thread, `engine.rs:309` `run`.
   - `on_tx` (:406) → `process` (:426) → `decode_swaps` (:531) → `on_trigger` (:596): slippage-bound skip at :613, then prediction, then `best_cycle` (:773: size ladder plus ternary search, fee = 5000 + 40k·cu + min_tip, min_tip = 0 at main.rs:579).
   - `on_account` (:863) → `on_confirm` (:189) and `state_trigger` (:203).
   - Both lead to `after_opportunity` (:660) → `route_in` (:741), with size clamped to `[live] max_size_sol`.
3. **Exec.** `exec.rs:538` `send` takes the first free nonce, then `copies` (:421) picks arm, tip, priority fee and per-copy `min_profit`. `build` (:333) emits [AdvanceNonce, CU limit, CU price, ATA create, nexus route (build.rs:205), tip]. The program checks only the **WSOL** gain against `min_profit` (build.rs:9).
4. **Send.** Optional sim gate (:616-660), then `Paths::fire` (send/mod.rs:678) → `Path::send/deliver` (:398/:414): jito gRPC, JSON-RPC, raw bytes, or QUIC to 2 leaders (tpu.rs:146).
5. **Settle.** After `fire` returns: sleep `settle_s` (:675), `getSignatureStatuses` (:681), `getTransaction`, Jito verdict, nonce read (:697), then `on_settled` (:715) does accounting and frees the nonce (:739-741). The stop check is `wants_send` (:315). Supervisor `run-w.sh:24-32` sums `failed_fees_lamports` from each segment's last status line.

## 2. Knobs in `arb-w.toml` (p11) vs. code

| knob | what the code does | verdict |
|---|---|---|
| `confirm_trigger_ms=0` "act only once the pool update names the trigger" | 0 means act on the **prediction at once** (config.rs:358-362, engine.rs:650) | comment is the opposite (p8–p11, p13) |
| `tpu_max_expected_lamports=1` "no cap" | `expected > 1` means everything is `tpu_hopeless`, so **bundle only** (exec.rs:442-446). 0 means no cap | wrong. p7–p10 were 100% bundle (381/115/1182/762 attempts) |
| `tip_share=0.7` "half of the gross edge" | 0.7×(expected−5000), clamped to [1000, 1e8] (send/mod.rs:372, exec.rs:509) | stale comment |
| `pair_lock_ms=400` "per 1.5 s" | lock only while the attempt is open and under 400 ms (exec.rs:434) | stale comment |
| `settle_s=1` "landings within 1-2 slots" | nonce freed about 1 s after `fire` returns | contradicted by data, see §3 |
| `margin_lamports` "on-chain min_profit = fees+tip+this" | on chain: bundle = tip+fee+prio+1; others with gross_floor = tip+1 (exec.rs:517-518). Margin is used only off chain (:512, :619) | stale comment |
| `gross_floor` | non-bundle copies only | accurate, but in p11 inert |
| `sim_gate`, `compete_*`, `tpu_cu_price_micro`, `tpu_skip_mints` | TPU arm only | **inert in p7–p11** because of `tpu_max=1` |
| `spec_cu_price_micro` "flat bid on every copy" | used only inside `bid_tiers` (exec.rs:457) | inert; comment wrong |
| `bid_*`, `race_mix`, `rotate_paths`, `test_all_paths`, `[gate]`, `[canary]`, `bundle_size_variants=[]` | off or empty | inert. `bundle_size_variants` comment ("quarter-size copy") is stale |
| `max_priority_lamports=30000` | cap at :460, but the TPU arm's `tpu_cu_price_micro` overrides it afterwards (:465) | cap bypassed. In p14 (60k µL) the largest seen cu_limit, 1.747M, would pay 104,820 lamports |
| `max_new_token_accounts=25` "rent ~0.0025 SOL, refundable" | counter is per run (resets each segment). Rent seen on chain is 1,488,440 or 1,513,840 lamports. Nothing closes the accounts | comment off; exposure is 25 accounts per segment |
| `skip_failing_signers=false`, `budget_caps_sol` | statistics only, written to files | fine |
| header "engine does not send yet"; `[gate]` "keep it" | live mode; gate disabled | stale |

No key in p11 or p14 is unknown to the config structs. But serde has no `deny_unknown_fields`, so a mistyped knob would silently fall back to its default.

## 3. Bugs and money risks on the live path

**A. The sim gate is bypassed whenever the RPC is behind (exec.rs:646-650).** On the first check, `sim.slot < trigger slot` means "send on our quote" and the loop exits (`break`). So the re-checks at +30/+60 ms never run in exactly the case they were added for. An RPC error also sends the trade (:633). Note that `replaceRecentBlockhash:true` (rpc.rs:240) means the gate never checks the nonce.

| | TPU attempts | bypassed as stale (at check 0) | outcome | failed fees from bypassed / segment total |
|---|---|---|---|---|
| p6 | 57 | 55 | 54 failed, 1 win | 712,897 / 755,198 |
| p12 | 87 | 84 (83 were 1 slot behind) | **74 of 74 landed TPU copies failed**; gate blocked 0 | 490,579 / 497,170 |

The live p14 config re-enables the TPU arm for expected profit ≥ 1.5M with this gate.

**B. `settle_s=1` frees nonces before late landings show up.** I counted nonce values that were consumed on chain with no landing recorded. Only our wallet is the nonce authority, and no value ever reverted (0 of 92 value groups in p12).
- p12: **11** such values. Every one belonged to a group that sent a TPU copy; 10 had no settle error.
- p1–p10: at most 1 per segment (p1 and p2), both after `statuses` RPC errors (exec.rs:690 fails open).
- p12 also had 7 bundles rejected with "Blockhash not found", meaning they were built on an already-consumed nonce.
- In p1–p6 plus w500-p1, 9 of 110 TPU landings were first seen more than 1 s after sending.

These landings never enter `spent` (the failed-fee budget), `landed`, `new_atas` or `held`. The TPU copies that were recorded all failed, so these were likely failed fees too (inference).

**C. The budget stop counts only fees of landed failed transactions.**
- `spent` comes from exec.rs:761, summed by run-w.sh:28.
- Rent for new token accounts is paid in SOL outside the WSOL-based `min_profit`, so a "win" that creates an account loses about 1.49–1.51M lamports.
- Attempts in flight at shutdown are never settled (main.rs:588-605; nothing drains them). p8 had 7 and p9 had 6 attempts with no outcome.

**D. `profit_lamports` mixes rent with trading P&L (exec.rs:764-771).**
- p1–p10 status profit is −16,201,607. Of that, 16,383,000 is rent in 10 token accounts plus one other account (2,860,040 in p6, inferred to be PumpSwap's volume accumulator).
- Trading P&L excluding rent is +181,393; minus 2,497,246 of failed fees that is **−2,315,853**.
- p11 and p12 add about −1.49M and −1.51M, consistent with one more account each (inference).
- Budget spent through p13: 2,994,416 lamports (≈ $0.36).

**E. A late trigger confirmation is lost.** When the 60 ms deadline passes, the opportunity is dropped (engine.rs:230). `state_trigger` then skips it because the opportunity still exists (engine.rs:209). Timeouts vs. releases: p1 557 vs 150; p6 89 vs 31; p12 75 vs 99.

**F. The exec RPC (sims, gate, statuses, nonce reads) is invisible.** `Rpc::only` creates fresh `Stats` (rpc.rs:69-72), and only the engine's RPC is printed (main.rs:586). The engine RPC in p12 showed Haan rate-limited 297 times and Shyft timing out at 3 s 130 times.

**G. Smaller issues.**
- `watch` entries leak for sim-gated attempts, because `fired.copies` is empty.
- Jito "would-fail" caused by a stale nonce counts toward the token cool-down.
- `meta.json` has no build hash. The binary was replaced at 20:27, 20:49 and 20:54 with about 2,000 lines uncommitted.

**Keystore** (wallet.rs:93-128, run-w.sh). The passphrase comes over a pipe; plaintext and passphrase are zeroed; `PR_SET_DUMPABLE=0` and no core dumps. The passphrase lives in the supervisor bash process for 5 h, readable by root only. The derived key is not zeroed on the wrong-passphrase path. Low risk.

**DAMM v2.** The leg encoder matches the `IX_*` layout. 662 of 758 trigger predictions matched `sqrt_price` exactly. I did not run the tests, because `cargo` would write to disk. Local time is used for the dynamic fee instead of the chain clock (minor; inference).

## CLAIMS
- [high] C1: At review time the local src builds exactly the deployed binary (sha256 bbad56d6… for both target/release/arb-lab and /root/arb-lab/arb-lab-w, deployed 20:54:47 UTC). Segment 11 was stopped with SIGINT after 81 s; p12 ran build 40ad9a55; p14 is live since 20:59:10 with a config that differs from the snapshot arb-w.toml.
  EVID: sha256sum on both machines; ls --time-style=full-iso on Cherry; runs/w5h.supervisor.log segment 11-14 lines; stat of src/venues/cp.rs (20:53:36) and target/release/arb-lab (20:54:11)
  VERDICT: confirmed — Checked independently. Local target/release/arb-lab and Cherry's /root/arb-lab/arb-lab-w both hash to sha256 bbad56d6…4d03. Cherry's file mtime is 23:54:47 +0300 (20:54:47 UTC). Local binary mtime is 20:54:11, later than the newest source file (src/venues/cp.rs, 20:53:36). The supervisor log shows p11 exit 0 after 81 s, p12 448 s (450/75/1/497,170), p13 96 s (53/0) and p14 starting at 20:59:10. Three details could not be checked: 'build 40ad9a55' (that binary has been overwritten) and 'SIGINT' (main.rs:507-508 exits 0 on ctrl_c or SIGTERM alike). The claim is now out of date: p14 ended at 21:07:36 after 506 s with sent 513, landed 66, wins 3, failed fees 1,117,914. p15 has been live since 21:07:46. Its arb-w-p15.toml differs from p14 in confirm_trigger_ms (0), tpu_max_expected_lamports (1, so bundle only) and the budget.
- [high] C2: tpu_max_expected_lamports=1 (commented 'no cap') sends every trade to the bundle-only arm, which made sim_gate, compete_*, gross_floor and tpu_cu_price_micro inert in p7–p11; p7–p10 attempts were 100% bundle (381/115/1182/762).
  EVID: exec.rs:442-446 (tpu_hopeless when expected > tpu_max), exec.rs:427 (expected<=0 skipped); work/code/arms.py over runs/w5h-p*/attempts.jsonl path_arm; config diffs p6→p7 show only tpu_max 0→1
  VERDICT: confirmed — exec.rs:442-446: with bundle_mix=true, any expected profit above 1 lamport is tpu_hopeless, so the attempt goes to the bundle arm, and exec.rs:427 skips expected<=0. Gate (:616), compete and tpu_price (:463-480) apply only when the arm is not bundle, and gross_floor (:517-518) only to non-bundle copies. From attempts.jsonl path_arm: p7 381, p8 115, p9 1182 and p10 762 attempts, all bundle. diff of arb-w-p6.toml and arb-w-p7.toml shows only tpu_max 0→1 plus the budget line. Inference: the operator set tpu_max=1 again in p13 and p15, right after the TPU-on segments p12 and p14. So it reads as a deliberate bundle-only switch with a stale comment, not a misunderstanding.
- [high] C3: The sim gate sends a TPU trade unchecked when the RPC simulation slot is behind the trigger slot, already at check 0. In p6, 55 of 57 TPU attempts were bypassed (712,897 of 755,198 lamports of failed fees). In p12, 84 of 87 were bypassed, the gate blocked 0, and all 74 landed TPU copies failed (490,579 of 497,170 lamports of failed fees came from bypassed attempts).
  EVID: exec.rs:631-653 (stale branch at 646-650 breaks with fail=None; RPC error at 633 also sends); 'gate: attempt N sim stale' lines in runs/w5h-p6.out and w5h-p12.out joined to outcomes.jsonl (work/code/p12)
  VERDICT: partly — The mechanism is right (exec.rs:633 and 646-650). The stale branch is reached only after a check has already failed or come back thin, so every bypassed trade is one the simulation said would fail. p12 is exact: 87 TPU attempts, 84 stale at check 0 (83 one slot behind), 74 of 74 landed TPU copies failed, 0 sim_gated, and 490,579 of 497,170 lamports of failed fees came from bypassed attempts. p6 is undercounted: one stale line in w5h-p6.out is spliced into an 'rpc failure' line (attempt 50). The corrected p6 figures are 56 of 57 TPU attempts bypassed (55 failed, 1 win) and 720,198 of 755,198 lamports from bypassed attempts. The one non-stale attempt (84) failed for 35,000. p14 (from the Cherry .out) had 85 stale lines, 0 gated and 85 TPU attempts: 63 landed, 0 won.
- [high] C4: With settle_s=1, nonces are released before late landings appear: in p12, 11 nonce values were consumed on chain with no landing recorded, all in groups that sent a TPU copy (10 with no settle error), and 7 bundles were rejected with 'Blockhash not found'. In p1–p10, only p1 and p2 had such a case, each after a statuses RPC error. These landings never reach failed_fees_lamports (the budget).
  EVID: exec.rs:675 (sleep settle), 681-691 (statuses; error fails open), 697 and 739-741 (nonce read and release); work/code/missed.py over attempts.jsonl nonce {account,value} sequences and outcomes.jsonl; 0 value reversions in p12
  VERDICT: confirmed — My own nonce-group pass (work/verify-code/nonce2.py) found 0 value reversions. p12 has 11 values consumed with no recorded landing, all in groups with a sent TPU copy and 10 with no settle error. In p1–p10 there is 1 in p1 and 1 in p2, both after statuses errors. p12 has 7 Jito 'Blockhash not found' rejections. I also checked on chain, using public mainnet RPC getSignaturesForAddress on the 20 nonce accounts and getTransaction (read-only). Of 291 nonce transactions since 18:46, 261 match recorded landings. The other 30 are our own TPU copies that landed and failed and were never recorded: p1 1, p2 1, p12 11, p14 17. They cost 426,475 lamports, none of it in failed_fees_lamports (p12 77,288; p14 327,592). Nuance: settle_s was 3 in p1–p9 and only 1 from p10 on, so the 'p1–p10' comparison mixes two settle values.
- [high] C5: profit_lamports counts rent for new token accounts as loss: p1–p10 status profit −16,201,607 lamports = 16,383,000 of rent (10 token accounts at 1,488,440 or 1,513,840, plus one other account) + 181,393 trading gain. Net of 2,497,246 failed fees, trading P&L is −2,315,853. Rent is neither covered by the on-chain min_profit nor counted in the budget.
  EVID: exec.rs:764-771 (SOL+WSOL balance delta), build.rs:9 (min_profit is on the WSOL quote account), exec.rs:761 (spent = failed fees only); per-win (round_trip_on_chain − fee − tip) − profit_lamports in runs/w5h-p*/outcomes.jsonl; status.jsonl new_token_accounts sums to 10
  VERDICT: confirmed — Recomputed (round_trip_on_chain − fee − tip − profit_lamports) for each win in outcomes.jsonl (work/verify-code/rent.py). p1–p10 status profit is −16,201,607 and the residuals sum to exactly 16,383,000. Ten wins created a token account. Nine of them have a residual of exactly 1,488,440 or 1,513,840. The tenth (p6 attempt 69) has 2,860,040, which covers its own token account plus one more account of about 1.35–1.37M (an inference). Trade P&L is +181,393, and after 2,497,246 of failed fees it is −2,315,853. Adding the 21,595 of unrecorded p1/p2 fees gives −2,337,448. p11, p12 and p14 carry 1,513,840, 1,513,840 and 1,488,440 of rent. The code citations hold: build.rs:9 (WSOL-only min_profit) and exec.rs:761 and :764-771.
- [medium] C6: The failed-fee budget is fail-open in three ways: statuses RPC errors drop the landing (p1 5, p2 1, p5 1, p8 2, p10 4, p12 1 errors), attempts in flight at shutdown are never settled (p8 7, p9 6 attempts without an outcome), and run-w.sh sums only failed_fees_lamports.
  EVID: exec.rs:690; main.rs:588-605 (no drain, rt.shutdown_timeout 2 s); run-w.sh:24-31; settle_error counts and attempts-without-outcome in runs/*/outcomes.jsonl
  VERDICT: partly — The mechanisms are right: exec.rs:690 fails open, main.rs:588-605 has no drain, and run-w.sh:24-30 sums only failed_fees. The statuses error counts are exact (p1 5, p2 1, p5 1, p8 2, p10 4, p12 1). The examples overstate the impact, though. Checked on chain, statuses errors dropped a real landing only in p1 (7,301) and p2 (14,294). The p8 (7) and p9 (6) in-flight attempts were bundle-only and consumed no nonce afterwards, so they cost 0. The real shutdown leak is p14: 7 in flight (4 TPU), and 5 nonce accounts advanced after p14 ended with no recorded landing. Attempts 506, 508, 510 and 512 landed and failed after shutdown, costing 74,844. Also missed: p5 and p10 each had 1 attempt with no outcome.
- [medium] C7: With confirm_trigger_ms=60, most decoded opportunities time out and are never retried, because state_trigger skips any transaction that already has an open opportunity: confirm_timeout vs confirm_released was p1 557/150, p6 89/31, p12 75/99.
  EVID: engine.rs:230-233 (expire), engine.rs:209 (state trigger skip), engine.rs:650-654; status.jsonl counts
  VERDICT: partly — The no-retry mechanism is real (engine.rs:232 expires, and :209 skips because opps still holds the trigger for outcome_watch_ms=2000). The counts are right: p1 557/150, p6 89/31, p12 75/99. The p12 rate is 43%, not 44%. But opportunities.jsonl trigger_landed_slot shows that nearly all timed-out triggers never landed within 2 s, so they are phantoms the gate correctly dropped. Decoded opportunities whose trigger never landed: p1 554 (of 557 timeouts), p6 89/89, p7 51/51, p12 69/75, p14 250/292. Late confirmations actually lost: p1 3, p6 0, p7 0, p12 6, p14 42. They are not 44–79% of opportunities.
- [low] C8: tpu_cu_price_micro overrides the max_priority_lamports cap on the TPU arm. In p14 (60000 µL/CU) the largest cu_limit seen, 1,747,000, would pay 104,820 lamports against a 30,000 cap (p99 cu_limit 278,000 → 16,680).
  EVID: exec.rs:460 (cap applied) then exec.rs:465 (cu_price = tpu_price); cu_limit distribution over 4,861 attempts in w5h-p1..p10 and p12 attempts.jsonl
  VERDICT: confirmed — exec.rs:460 applies the cap, then :465 sets cu_price = tpu_price, and the compete bid (:476) also ends in .max(tpu_price). Over 4,861 attempts (p1–p10 and p12): max cu_limit 1,747,000, p99 278,000, p50 184,000. At 60k µL/CU that is 104,820 and 16,680 lamports. In practice p14's 85 TPU attempts peaked at a priority fee of 18,120 lamports (max cu_limit 302,005), so none breached the 30,000 cap. Low impact, as stated.
- [medium] C9: Statistics of the money-path RPC (sim gate, statuses, nonce reads) are never reported: Rpc::only builds a fresh Stats and main prints only the engine RPC, which in p12 showed Haan rate-limited 297 times and Shyft timing out at 3 s 130 times.
  EVID: rpc.rs:69-72; exec.rs:242; main.rs:586-599; 'rpc failure' lines in runs/w5h-p12.out
  VERDICT: confirmed — rpc.rs:69-72: Rpc::only builds stats with Default. exec.rs:242 creates the exec RPC from [exec] rpc = ["haan","shyft"]. main.rs:586-599 prints only eng.rpc_handle(), the engine's raced RPC. The p12 'rpc final' lines on Cherry read 'haan … errors 297' with 297 x rate limited, and 'shyft … errors 130' with 130 x no answer in 3 s. Inference: these are the same providers the gate, statuses and nonce reads use, so the invisible exec RPC probably suffered the same errors.

## MISSED (verifier)
- On chain the budget undercount is real and larger than shown. Public-RPC history for the 20 nonce accounts has 30 of our TPU transactions that landed and failed but were never recorded: p1 1, p2 1, p12 11, p14 17. They total 426,475 lamports. p14 alone is 327,592, 29% on top of its recorded 1,117,914. The true failed fees through p14 are 4,538,805, not the 4,112,330 the supervisor uses (work/verify-code/chain.py, match.py, fees.py).
- p14 finished after the review and played out the predicted risk. The gate was bypassed as stale 85 times in 85 TPU attempts (0 gated), with 63 TPU landings and 0 TPU wins. Recorded failed fees were 1,117,914 plus 327,592 unrecorded. Five nonces were consumed after shutdown. p15 is now live bundle-only (tpu_max=1, confirm_trigger_ms=0), so the 'now' advice for p14 is already overtaken.
- The TPU arm loses even when the gate works. In p1–p5 the gate blocked many trades (40 of 50 in p5), yet there were still 40 failed TPU landings and only 2 TPU wins (p3). Over all TPU segments the arm has won 3 times (p3 2, p6 1) against more than 230 failed landings. A gate fix alone does not justify turning TPU back on.
- settle_s was 3 in p1–p9 and 1 only from p10 (arb-w-pN.toml). With 3 s, TPU landings were missed only after statuses RPC errors, so the data supports a longer settle. Durable-nonce transactions never expire, though: a copy can land whenever the nonce value is still current, so no settle value closes the hole. Only invalidating the nonce or reconciling on chain does.
- Most confirm timeouts are phantom triggers that never landed within 2 s (for example p6 89 of 89, p7 51 of 51). Lost late confirmations are only p1 3, p6 0, p12 6, p14 42.
- Exposure no stop rule covers: max_new_token_accounts=25 resets every segment. Over 15 segments that allows about 375 accounts × about 1.5M, roughly 0.56 SOL of rent, 14 times the 40M failed-fee budget. Through p14 the wallet outflow is about 25.2M lamports (~$3.00), of which about 20.9M is rent locked in token accounts.
## REC ISSUES (verifier)
- R1 (turn off TPU until the gate's stale branch is fixed): turning TPU off is well supported, but p14 has ended and p15 is already bundle-only, so the advice is stale. Making a gate fix the condition for re-enabling is unsupported: with a gate that blocked (p1–p5) TPU still produced 40 failed landings and 2 wins. Since 83 of 84 checks are one slot behind, 'block when stale' means the TPU arm is effectively always off. Keep TPU off until a separate test shows it has positive expected value.
- R2 (settle_s ≥3 or lease until the nonce read shows an advance): this is incomplete and partly unsound. A durable-nonce transaction stays valid until the nonce advances, so seeing 'not advanced' proves nothing about a copy still in a leader's queue, and an open-ended lease starves the nonces. Better: after settle, advance the nonce yourself (5,000 lamports) or reconcile on chain. Scan getSignaturesForAddress on the nonce accounts or the wallet, charge every unrecorded landing to spent, and have the supervisor budget on the wallet's SOL+WSOL balance delta rather than self-reported counters.
- R4 (drain at shutdown, charge in_flight × worst): the cited evidence (p8 7, p9 6) was bundle-only and cost 0 on chain. The supporting case is p14: 4 in-flight TPU copies landed after shutdown for 74,844 lamports. Draining for settle_s still misses copies that land later. Add a post-segment on-chain reconciliation.
- R7 (let a late confirmation fall through to state_trigger): little support. Nearly all timeouts are triggers that never landed. Only 0–6 per segment were late (42 in p14), and at more than 60 ms those gaps were probably already taken (inference). Low value; do not prioritise it.
- R3 (job that closes empty token accounts): this is a live write against the wallet. Closing accounts the bot will soon reuse means paying rent again, and Token-2022 accounts with withheld fees need a harvest before they can close. Run it between segments only, against the bot's held set, never during a live segment. The supervisor stop on rent plus losing wins is sound and should also cap token accounts across the campaign, not per segment.
- R5/R6 (deny_unknown_fields, priority cap, commit): each is a code change plus rebuild and redeploy into a live 5-hour campaign; the binary has already been swapped 3 times with no provenance. Batch them between campaigns. deny_unknown_fields turns any stale key into a start failure, which the supervisor counts as an early end (it stops after 7 in 15 min).
## RECS
- [now] Turn the TPU arm off in p14 (set tpu_min_expected_lamports very high, or tpu_max_expected_lamports=1 = bundle only) until the sim gate's stale branch at exec.rs:646-650 waits for the RPC slot (continue the re-checks) and treats 'still stale' or 'RPC error' as a block instead of a send. — 85+ TPU landings across p6 and p12 bypassed the gate and failed; 0 of 74 TPU landings won in p12.
- [now] With any TPU or paid copy enabled, set settle_s to 3 or more, or keep the nonce leased until a nonce-account read shows whether it advanced. On a statuses error, retry and charge the attempt's worst-case fee to `spent`. — In p12, 11 consumed nonces had no recorded landing; their fees and P&L are missing from the budget.
- [next] Split rent out of profit_lamports (report trade P&L, rent locked and new accounts separately), make the supervisor stop on (failed fees + rent + losing wins), and add a job that closes empty token accounts. — Reported −16.2M lamports in p1–p10 is mostly refundable rent; the real P&L (−2.3M) and the rent outflow are both invisible to the budget.
- [next] Drain open attempts (wait settle_s and settle them) before writing the final status at shutdown, and have run-w.sh charge in_flight × worst fee. — Attempts in flight when a segment stops are never accounted (p8 7, p9 6).
- [next] Fix the stale config comments (confirm_trigger_ms, tpu_max_expected_lamports, tip_share, pair_lock_ms, margin_lamports, spec_cu_price_micro, bundle_size_variants, max_new_token_accounts, gate and header text), add #[serde(deny_unknown_fields)], and log at start which arm each knob applies to. — Several live decisions (p7–p11 bundle-only, confirm off) contradicted the comments that describe them.
- [next] Print the exec RPC statistics, cap TPU priority at max_priority_lamports after the tpu_cu_price override, and stamp git hash plus a dirty-diff hash into meta.json; commit the uncommitted ~2,000 lines and the 3 untracked files that are running live. — Observability and provenance: the binary was swapped 3 times in 30 minutes with no record of which code a segment ran.
- [later] Let a late trigger confirmation fall through to state_trigger (or keep confirm_wait entries until outcome_watch_ms) instead of dropping the opportunity. — 44–79% of decoded opportunities timed out at 60 ms with no retry.
## OPEN Q
- Was tpu_max_expected_lamports=1 in p7–p11 an intended bundle-only test, or a mistaken 'no cap'?
- Did the 11 unrecorded p12 landings fail (paying fees)? This could be checked read-only with getSignaturesForAddress on the nonce accounts, which I did not do to avoid RPC load.
- Why do failed TPU landings show an on-chain round trip of about −1.3× to −2× the prediction (p12 median −1.29)? Stale pool state, or lost races? 49 of 57 TPU trades in p6 came from single-pool state triggers. This needs the exec and rival analysis of another dimension.
- Do the Haan sender and Shyft rebroadcast durable-nonce transactions after our settle window (Shyft is sent with maxRetries 0)?
- DAMM v2 quote math was reviewed by reading only (cargo test not run under the no-write rule); 96 of 758 predictions mismatched. Is that because of ordering, or because the fee uses local time instead of the chain clock?
- What was edited in exec.rs/config.rs at 20:48 versus the 20:27 build that p10/p11 ran? There is no copy of that source.