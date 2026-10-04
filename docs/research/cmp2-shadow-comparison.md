# cmp2: old bot (arb-lab-w) vs arbx e2b8fa5 (WP-00/01), shadow, Cherry, 2026-10-04

The main window is 13:22:00–13:50:00 UTC. The chain-truth and policy work used 13:21:46–13:50:00, which holds 937 old-bot opportunities instead of 933. Old-bot status counts are deltas over the window. arbx counts are whole-run totals over a span of nearly the same length.

## 1. Bottom line

- **arbx priced nothing, so this run cannot compare the two bots' decisions.**
  - arbx's three Haan gRPC streams (state, haan-deshred, haan-grpc) got HTTP 503 on all 172 reconnects each, from 13:21:58 to 13:49:58.
  - The old bot held the same three streams, on the same endpoint and token, with 0 errors.
  - arbx's store never moved past its boot snapshot: store_updates was 4,372 and slot was 0 in all 168 status lines.
  - With `decoded_sends = false`, arbx had no other way to price. It found 0 opportunities; the old bot found 933 (659 from pool state, 274 from decoded transactions).
- **On the inputs arbx did receive, the two bots matched.** Both saw the same 4,820 decoded-trigger arrivals, and 4,782 of them match to the nanosecond.
- **Neither bot builds an executor in shadow mode** (`exec_on = sim.enabled || canary || live`). No WP-00 send gate ran in either bot. Every policy figure below is an offline replay on the old bot's records.
- **The WP-00 policy is better, at a cost near zero.**
  - The old live config would have acted on at most 730 decisions. arbx's rules remove 418 of them (57%).
  - The removed decisions quote 38.0 SOL, of which 35.10 SOL is phantom.
  - The removed decisions we could have won add up to at most 0.077 SOL quoted. That is about 0.02 SOL realized (inference).
- **Robustness is worse.**
  - arbx ran blind for 28 minutes without a warning and stopped normally at its deadline, exit code 0.
  - It wrote about 3,430 false signer misses into the signer-stats file that the next run reads.
  - Its first boot crashed.
- **Neither bot showed a winnable edge.**
  - Clean opportunities quoted only 4.43 of the 104.6 SOL. Rivals took 3.74 SOL of that within 80 ms of our decision.
  - arbx would have kept decisions quoting 1.51 SOL. Only 0.002 SOL of that was taken late enough for us to win it.

**Cause of the 503s: unproven.**
- "One stream per key" is ruled out: the old bot held three streams on one HAAN_X_TOKEN.
- Two explanations fit: a per-key or per-IP quota that the old bot had already used up, or Haan refusing only new connections.
- PLAN-ADDENDUM I-2 also logged 503s with one bot running alone.

## 2. Pipelines side by side

| Stage | Old (arb-w.toml in shadow) | arbx (Stage 0) |
|---|---|---|
| Working feeds | dz-leader, dz-retransmit-eu, astralane, haan-deshred, haan-grpc, state | dz-leader, dz-retransmit-eu, astralane |
| Transactions/s on dz-leader / dz-retransmit-eu / astralane | 1,092.6 / 1,970.1 / 957.6 | 1,091.6 / 1,969.9 / 1,058.6 (DAMM v2 added to astralane) |
| First feed on decoded triggers (same three, in order) | 52.8 / 46.7 / 0.5% | 52.8 / 46.7 / 0.6% |
| Decoded triggers | 4,861 (3,075 priced) | 4,868 (3,098 hints) |
| Skipped as will-fail / unquotable / signer skip | 1,127 / 640 / setting off | 759 / 639 / 350 |
| Store updates | +86,218 | 0 |
| Opportunities | 933 | 0 |
| Transactions dropped as alt_unknown | about 610 | 5,001 |
| Time from receipt to decision, p50 / p99 | 164 / 1,437 µs | 87 / 2,169 µs (no pricing) |
| State decision after the trigger's first shred | p50 14.3 ms, p90 23.2 ms | none |
| Recorder | off | 736 MB |
| Provenance | no build or config hashes | complete, matches the repo |

Five other feeds were dead in both bots: constantk-prism, erpc, raiden, corvus and getblock.

- **Trigger signatures do not compare cleanly.**
  - 2,370 signatures are in both files, 697 only in the old bot's and 725 only in arbx's.
  - arbx's will-fail and unquotable skips priced against a snapshot that grew up to 28 minutes stale.
  - Up to 350 of the 697 old-only signatures are arbx signer skips.
  - So the split mixes stale state with policy.
- **Losing Haan's transaction feeds cost arbx no decoded trigger.**
  - Haan was never the first feed on a decoded trigger, and was first on only 3 of 654 state triggers.
  - arbx received all 930 transactions that triggered old-bot opportunities.
- **Why some arbx recorder files are empty:**
  - slots.log is empty because the Jito-entries feeds were dead in both bots.
  - exec.jsonl is empty because it is written only from haan-grpc (grpc.rs:355).
- **alt_unknown (likely cause, not proven).**
  - A single failed lookup-table fetch marks that table missing for the rest of the run (engine.rs:595). Every later transaction using it is dropped.
  - arbx started with an empty cache. In its first minute (13:22) it got 501 Haan 429s, and 305 calls failed on both providers.
  - The comparison is confounded: the old bot's Haan feeds can refill tables it had marked missing.

## 3. Chain truth

The basis is the old bot's 937 opportunities, quoting 104.6 SOL. I checked them with getSignatureStatuses (4,004 signatures), getTransaction, getBlock and arbx's rivals.jsonl.

| Class | Opps | SOL quoted | Meaning |
|---|---|---|---|
| Phantom trigger | 198 | 65.09 | The decoded trigger failed on chain (Custom 6001 ×96, 6003 ×46, 3012 ×37, …). All 76 other decoded triggers succeeded. |
| Poisoned prediction | 62 | 33.76 | The other pool was priced against a failed swap's prediction less than 1.5 s old. |
| Likely poisoned | 22 | 1.34 | Doubtful: opp 838 (1.50 s old) is 1.315 SOL of it, and 14 had takers. |
| Clean | 655 | 4.43 | The trigger landed and the state was real. |

- **Phantom triggers.**
  - They include 104 of the 133 decoded opportunities quoting 1M lamports or more.
  - Across all decoded triggers, 26.5% failed on chain.
  - The old live setting `confirm_trigger_ms = 60` would have dropped these opportunities too. They are in the shadow file because `finish_opp` records opportunities even when nothing is sent.
- **Poisoning.**
  - `leg()` reads `preds`. A failed trigger's prediction stays until another trigger overwrites it, or until housekeeping removes it after 1.5 s.
  - Example: on Gf7sXM (PumpSwap USDC/SOL), three failed swaps produced 10 quotes of 0.59 to 3.88 SOL. One of them, A3uAHtQA (463,420 USDC, Custom 3012), produced all six 3.88 SOL quotes.
  - arbx's hint path returns before `preds.insert`, so this class cannot occur in arbx.
  - Once the confirm gate removes phantom triggers, poisoning is the largest pricing error left.
- **Size-ladder edge.** 57 opportunities sized at 8.4 SOL carry 98.13 SOL of the quotes, and 49 of them are phantom or poisoned.
- **Clean does not mean correctly priced.**
  - Over 110 takers, realized gross divided by our quote: p25 0.54, p50 0.98, p75 1.00.
  - At quotes of 10M lamports and above, 2.584 SOL was quoted and 1.424 SOL realized.
  - Opp 811 quoted 0.96 SOL. The taker, 7dGrdJRY, made 0.029 SOL on a 41.3 SOL trade.
- **Untaken clean opportunities** (219, 0.61 SOL). In all 9 checked, rivals touched both pools within 2 s, and every one of those trades made zero profit or failed. Inference: the gap was not there.
- **Speed.**
  - Takers appeared p50 23.8 ms after our state decision; 132 of 435 appeared before it.
  - Our bundles earlier landed at p50 79 ms, so I count a taker as beatable only if it came 80 ms or more after our decision. Only 105 clean opportunities (0.080 SOL) had such a taker.
  - Those late takers realized 26% of our quote.
- **Winners** (114 successful takers, 1.045 SOL net):
  - MriyaNN8: 24 wins, 0.407 SOL.
  - 8oSD5a9E: 8 wins, 0.137 SOL. Its biggest win (0.334 SOL gross) was in the same Jito bundle as the opener's own transaction. Inference: private order flow, which no latency can beat.
  - A recorded taker does not prove the gap was real: 11 phantom-trigger opportunities have one.

**Would-send: old live config vs arbx rules** (offline, using the quote as the expected profit)

| Rule (exec.rs order) | Decisions | SOL quoted | What the chain shows |
|---|---|---|---|
| Old live: 937 − 198 dropped by the confirm gate − 9 over the account cap | ≤730 | | |
| − No predictions (hint only) | 84 | 35.10 | Phantom; at least 3 small ones were real |
| − Crowded pool and expected ≥ 100k | 173 | 1.84 | 124 taken within 80 ms; 13 late (0.018) |
| − No new token accounts | 145 | 0.50 | 70 taken within 80 ms; 29 late (0.045) |
| − ≥1M throttle | 16 | 0.56 | 10 taken within 80 ms; 2 late (0.014) |
| **arbx keeps** | **312** | **1.51** | 122 taken within 80 ms (1.29), 132 untaken, 58 late (0.002) |

- **What removes the phantoms is the empty `preds` table, not `decoded_sends = false`.** That switch adds nothing over the old confirm gate: the 76 decoded triggers that landed simply move to the state path.
- **Bundle-only removes the old TPU arm.** That arm had at most 68 attempts and about 1.77M lamports of worst-case fees.
- **Neither side of the table is exact.**
  - The old figure of 730 leaves out pair_lock, the nonce settle, sim_gate and the Jito 5/s limit.
  - arbx would also price state triggers that the old bot skipped while a prediction was pending. So 312 is not an upper bound.
  - Neither is the Stage-0 funnel's 293 (8.55 SOL), which probably also keeps poisoned state opportunities (inference).
- **Tip floor.** arbx's minimum tip is 1,000 lamports against the old bot's 0. That removes 23 opportunities.

## 4. Robustness and resources

- **There is no state-health gate.**
  - Nothing checks whether state is fresh, and SendGate has no reason for stale state.
  - A reconnect never takes a new snapshot (feeds/mod.rs:208-235).
  - The engine's slot comes only from the state stream, so it stayed at 0.
- **The signer stats were polluted.**
  - A pending trigger becomes a miss after 5 s unless a state update credits it (engine.rs:440, 976).
  - Result: about 3,430 misses and 0 successes, saved to /root/arbx/runs/signer-stats.json (sha256 5f2942e6… at boot).
  - skip_failing_signers could not be measured at all.
- **Boot crash.**
  - In failover mode a Haan 429 is not retried (rpc.rs:94/114), and a Shyft body error returns at once (rpc.rs:84).
  - One chunk failing on both providers aborts the boot (main.rs:795-802).
  - The crash came at the tail of the old bot's lookup-table fetch burst. That Haan's part was a 429 is inferred.
  - One of 2 boots failed, which is too few to give a failure rate. Exec::new has the same weakness.
- **The bots share one RPC quota.**
  - Haan 429 bursts hit both bots in the same minutes: 698 for arbx and 597 for the old bot.
  - Calls that failed on both providers: 360 for arbx and 228 for the old bot.
- **The engine stalls at each 10 s housekeeping**, by up to 54.8 ms in arbx and 63.2 ms in the old bot. The likely cost is the 2.2 MB `save_signer_stats` write (inference).
- **The three working feeds never reconnected.**
- **Resources.**
  - Neither run recorded CPU or RSS.
  - From the code, the lookup-table cache reaches about 153 MB and is never evicted.
  - Shutdown took about 2.6 s with 4,378 events still queued. stop.json says 16.6 ms because `requested_ns` is stamped late.
- **Recorder volume.**
  - 736 MB in 28 minutes: rivals 603 MB (88% of it `why = venues`) and txarr 130 MB.
  - alts.jsonl is missing from the copy (about 145 MB, estimated).
  - A healthy run projects to about 66 GB/day raw, or 17 GB/day at zstd-3.
  - Nothing compresses the files until WP-02, so a campaign fills the disk in about 1.6 days.

## 5. What this run cannot tell us, and the next run

**What this run cannot tell us:**
- arbx's own pricing;
- the send gates running inside an executor;
- whether skip_failing_signers helps;
- which state triggers arbx would add;
- whether bundles land.

**Bugs both bots share until WP-04/WP-16:**
- overpricing at the size-ladder edge;
- quotes of 10M+ lamports realizing only 55%;
- quoted gaps that were never there;
- torn reads;
- deviations in the venue maths.

**What the next run should do:**
1. Give arbx its own Haan token, or stagger the two boots.
2. Refuse to start until the first state update arrives.
3. Restore the signer-stats file and give each bot its own copy per run.
4. Turn on the old bot's recorder.
5. Build Exec in both bots through `sim.enabled`, after confirming that sim mode sends nothing.

**What the next run should measure:**
- arbx's state-path opportunities against the old bot's, including the ones the old bot suppressed;
- realization at the 4.2 SOL cap, by band;
- the lead from our decision to the taker;
- prediction accuracy;
- alt_unknown with a preloaded lookup-table cache;
- RSS, CPU and the housekeeping stalls.

## 6. Fixes before a live canary

**P0**
1. **State-health gate.**
   - Stop with reason `state_unavailable` if no state update arrives within N s.
   - Force shadow while the stream is down or its last update is more than about 2 s old.
   - Take a new snapshot after each reconnect.
   - Add `state_connected`, `last_update_age_ms` and `reconnects` to status, and log a WARNING.
2. **Haan.** Give arbx a token that no other consumer uses, and ask Haan for its connection limits.
3. **Signer stats.**
   - Count misses only while state is healthy.
   - Restore the boot file (sha256 5f2942e6…).
   - Write a copy per segment instead of editing the shared file.
4. **RPC at boot and in Exec::new.** Retry each chunk on both providers with backoff. Treat 429 and body errors as retryable.
5. **Lookup tables.**
   - One failed fetch must not mark a table missing for the whole run.
   - Cap concurrent fetches.
   - Preload the previous segment's alts.jsonl.
6. **Pricing limits.** Keep the 4.2 SOL size cap and the ≥1M throttle until WP-04 validates pricing.

**P1**
7. Put the post-segment `zstd --rm -3` back into run-w.sh, and sample the `why = venues` rows in rivals.jsonl.
8. Move `save_signer_stats` and the recorder flushes off the engine thread.
9. Remove the dead feeds.
10. Report Shyft 429s separately from timeouts.

**P2**
11. Take the slot from the shred feeds while state is down.
12. Stamp `requested_ns` at the deadline.
13. Build for x86-64-v3.
14. Run chrony.

## Addendum (main session, after the workflow)

**Haan 503: the first process to open the streams wins (strong evidence, cause not confirmed with Haan).**

| Run | Order | Result (status.jsonl `slot` / `store_updates`) |
|---|---|---|
| cmp1, 13:01:41, both bots started together | old bot's state came up after about 60 s | arbx: slot 0, store_updates 4,370 in all 7 status lines (never connected) |
| haan-probe-1, about 13:17, arbx alone | - | arbx: state worked from the first status line (slot 453,267,599, updates growing) |
| cmp2, old bot 13:19:45, arbx 13:21:46 | old bot first | old bot: 0 Haan errors; arbx: 503 on all three streams for 28 min |

Every run fits a per-token (or per-IP) limit that one bot's three Haan streams (state, haan-deshred, haan-grpc) already use up. A live consequence (inference): a segment restart that overlaps a lingering previous process could start blind, and nothing would stop it (no state-health gate). Ask Haan for the concurrent-stream limit, and for a second token for arbx.

**Side effect of the comparison on the live arb-lab files.** My shadow copy of the old config (`/root/arb-lab/arb-w-cmp-shadow.toml`) kept `out_dir = /root/arb-lab/runs` and `signer_stats_file = runs/signer-stats.json`. So cmp1-old and cmp2-old updated the live arb-lab signer-stats file (last write 13:50:42 UTC).
- cmp2-old's updates were healthy, because its state stream worked.
- cmp1-old's state stream was down for its first ~60 s. At most about 146 triggers in that minute became false misses.
- The live bot runs `skip_failing_signers = false`, so this does not change its trading. It matters only if the file is copied to a bot that sets the flag to true, as arbx does.
- No exact pre-test copy exists. The newest backup is the 2026-10-03 21:41 snapshot.
- arbx's own copy, `/root/arbx/runs/signer-stats.json`, holds about 3,430 false misses from cmp2. The restore was not done: the permission check stopped the remote write, so it waits for the owner.
