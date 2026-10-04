# Why segments end early (and segment 7 ran long)

## Bottom line
- **The bot did not stop any segment itself.** Every early end was the operator: the Claude session driving the campaign, transcript `~/.claude/projects/-home-moiz-arbed/39acbea7-….jsonl`. It sent SIGINT to the segment process, either to load a new config or binary or to stop fees bleeding away. That covers w5h p2, p3, p5, p6, p8, p9, plus p11, p12 and p13, which ended while I was analysing, and also w500-p1. SIGINT sets the stop flag (main.rs:505-510). The engine loop then leaves at engine.rs:313, prints the final lines and exits 0. The signal handler writes no log line, so the logs never show the reason.
- **p7 did not overrun.** Its engine stopped on time (1202.0 s). The operator had frozen the supervisor with `kill -STOP` and resumed it 25 minutes later. There is no shutdown or settle bug.
- **The fee budget does what its name says: it counts failed fees only.** The bot (exec.rs:319) and run-w.sh agree on this. All real costs fall outside it, so it does not bound losses.

## 1. How a segment can end (code)
`Engine::run` exits only when the stop flag is set or the deadline passes (engine.rs:313), or when the channel disconnects. A disconnect cannot happen because `run()` holds `tx`. Only the SIGINT/SIGTERM task sets the stop flag (main.rs:508). The failed-fee cap (exec.rs:319) and the token-account cap (exec.rs:435) only stop *sending*; the segment keeps running. Errors before the loop exit with code 1. So exit 0 before the deadline means a signal.

Every final status line I checked (w500-p1 and w5h p1-p10, status.jsonl) has `stopped: null`. None has `live_skip_new_token_account_cap`. The most new token accounts in one segment was 4 (p10), against a cap of 25. No `.out` file contains a panic, and every `.out` ends with `done:`.

| seg | engine s (meta→done, run.log) | end trigger (operator transcript, UTC) | class |
|---|---|---|---|
| w500-p1 | 235 | 18:45:13 `touch runs/w500.stop && pkill -INT …arb-w-p1.toml`. Restarted as w5h with 20 nonce accounts (w500 logged 291 `send_no_free_nonce`) | operator abort |
| p1 | 1202.4 | deadline | natural |
| p2 | 325.7 | 19:11:50 `mv -f arb-lab-w.new arb-lab-w && pkill -INT …p2`. Next config adds `gross_floor` (SEG3). p2 paid one failed fee of 1,305,030 lamports | operator restart |
| p3 | 148.6 | 19:13:41 command: `compete_max_share` 0.25→0.10, plus a build with an absolute priority cap ("seg 2: one 1.94 SOL trade paid 1.3M") and pkill p3 | operator safety fix |
| p4 | 1202.4 | deadline | natural |
| p5 | 350.1 | 19:41:02 `kill -INT 1607651`: "Deploying them with the lower fee cap, then restarting segment 5" (`max_priority` 100k→30k) | operator safety fix |
| p6 | 554.5 | 19:50:36 `kill -INT`: "ending it now to stop the fee bleed" (56 landed-and-failed, 755,198 lamports) | manual safety stop |
| p7 | 1202.0 | deadline. The supervisor logged exit 410 s late (§3) | natural |
| p8 | 112.6 | 20:19:56 `bundle_size_variants = []` + `kill -INT` | operator restart |
| p9 | 450.5 | 20:27:47 new build + `settle_s` 3→1 + `kill -INT` | operator restart |
| p10 | 1202.5 | deadline | natural |
| p11 | 68.0 | 20:49:35 `kill -INT` after the 20:49:18 deploy and the "hybrid" send config | operator restart |
| p12 | 435.2 | 20:57:12 `tpu_max_expected_lamports` 1000000→1, `confirm_trigger_ms` 60→0, `kill -INT` (497,170 failed fees) | manual revert |
| p13 | 82.6 | 20:58:58 "tuned" send config + `kill -INT` | operator restart |

Each kill comes 1-3 s before the segment's `done:` line (for example 19:41:02 → 19:41:04.6 and 20:57:12 → 20:57:14.6). The sshd journal on Cherry independently shows a login 0-3 s before every early end. There is no such login before the p1, p4 or p10 ends.

**Classification:** no bot safety stops, no configuration limits, no bugs or crashes. All are manual interrupts:
- p3, p5, p6 and p12 were for safety: fee bleed or the priority cap.
- The rest switched to a new hypothesis or a new build.

**Lost live time** (gaps between one segment's `done` and the next segment's `meta.started_ns`; trading starts within about 0-2 s of meta, per attempts.jsonl; p7 took 10.5 s):
- From 18:46:03 to the end of p13 (20:59:00): 7,977 s of wall clock, 7,337 s with the engine running, **640 s idle (8.0%)**. Of the idle time:
  - **424.1 s** is the SIGSTOP pause between p7 and p8.
  - **215.7 s** is 12 restarts: 10-14 s of boot each, plus the supervisor's `sleep 10` after each of the 9 early ends.
- Within p1-p10 alone: 581 s idle of 7,332 s.
- Early ends do not shorten the campaign, because it is time-boxed by `END`. The real cost is thin samples: p8 112 s, p11 68 s, p13 83 s.

## 2/3. Why p7 took 1622 s
- p7's meta.json was written at 19:50:58.75. Its run.log `done:` is at 20:11:00.78, so the engine ran 1202.0 s.
- On Cherry, every p7 file, including the `.zst` big files, has mtime 23:11:00.78 local (20:11:00.78 UTC). Nothing was written after `done`.
- sar for 20:10-20:20 UTC shows the host at its idlest of the evening: user 4.41%, system 2.53%.
- The transcript shows `kill -STOP 1558445` at 19:52:32, described as "Freeze supervisor so segment 8 waits". `ps` at 20:09:45 shows run-w.sh (pid 1558445) in state `T`.
- At 20:17:50 the operator ran `kill -CONT 1558445`. Bash reaped the finished p7 at 20:17:51 and computed dur = 1622.

So the p7 process sat as a zombie for about 410 s. Side effects:
- The operator's wait loop `until ! kill -0 1623060` could never finish, because `kill -0` succeeds on a zombie. The operator killed that loop at 20:15:57.
- The operator thought p7 ended at 20:10:49 (supervisor start + 20 min). It actually traded until 20:11:00. That explains the "landings" the user saw at 20:09.
- `END` is fixed, so the pause came out of campaign time.

The full-length segments show how long the binary itself takes: p1 1214 s, p4 1212 s, p10 1215 s. That is about 10-14 s of boot plus 1200 s plus about 2 s to finish.

## 4. Budget audit
**Consistency.** run-w.sh adds up the last-line `failed_fees_lamports` of each segment. The bot's `spent` (exec.rs:761) only grows by the fee of a landed transaction that failed, or by `worst` when the transaction can't be fetched. Both sides count the same thing:
- 40,000,000 − 2,497,246 (p1-p6) = 37,502,754.
- After p12's 497,170 it is now 37,005,584. This matches the supervisor log.

**Why it stalled.** From p7 on, everything went as Jito bundles. Bundles that fail never land, so failed fees were 0 in p7-p11, and the budget could not move.

**Costs outside the budget, so far:**
- Σ`profit_lamports` for p1-p13 is −19,204,527. Including failed fees, the wallet change the bot accounts for is about −22.2M lamports (−0.0222 SOL ≈ −$2.64).
- For p1-p10 (outcomes.jsonl), the 21 wins break down as:
  - −16,383,000 for token-account creation, on 10 wins. This equals `new_token_accounts` = 10.
  - +181,393 of trading net (round trip − fee − tip).
  - 2 wins lost money even before rent (−7,652 and −4,447). `gross_floor` lets a win lose its fee plus priority fee.
- I checked p7 attempt 62 on chain (public RPC): a system `createAccount` of 1,513,840 lamports for a Token-2022 account, paid by the wallet. That rent comes back only if the account is closed. seg.py itself labels this figure "profit(incl rent)".

**Can losses grow without limit?** Yes, in total; each single trade is bounded.
- **No loss stop anywhere.** Neither the bot nor the supervisor has a P&L limit or a wallet-balance floor.
- **The token-account cap resets every segment.** `max_new_token_accounts = 25` applies per segment and run-w.sh does not carry it over. That is up to about 37.8M lamports of rent per segment (25 × 1.51M), none of it charged to the budget.
- **Attempts still in flight are dropped when a segment stops,** so they are never counted: p8 had 7, p9 had 6, p5 and p10 had 1 each.
- **`settle_s = 1` checks only once.** Since p10 the bot calls `statuses` once, 1 s after firing (exec.rs:675-681). A transaction that lands later, or that the RPC hasn't seen yet, is recorded as not landed, so its fee or loss is never counted. This matters again now that direct sends are back (p12).
- **Late landings go unrecorded.** A durable-nonce transaction stays valid until its nonce advances, so one sent in a killed segment can land later without being recorded anywhere (an inference; not measured).
- **A bad status file counts as zero.** The supervisor's `except Exception: pass` turns a missing or corrupt last status line into 0 spent.

## Other supervisor hazards
- **The "records only" fallback is broken.** `arb-w.toml` has `mode = "live"`. Running without `--live` fails the check at main.rs:487 and exits 1 at once. Each failure is counted as an early end, so after 7 of them the supervisor logs "too many early ends: stop".
- **The early-end counter also counts the operator's own kills.** At 20:59:00 it stood at "3 in 15 min". Seven deliberate restarts within 15 minutes would end the whole campaign, and restarting needs the passphrase typed again.
- **The early-end diagnostic is noise.** `grep -iE 'panic|error'` matches "(N, 0 errors)" in the send summaries. All 9 early-end lines in the log show only that.
- **The binary changes during the campaign.** There were 15 `mv -f arb-lab-w.new arb-lab-w` deploys between 18:48 and 20:54 UTC. The latest, at 20:54:47, happened while p12 was running. meta.json has no build id, so the local source no longer pins any one segment's binary.
- **The passphrase stays in memory.** It sits in the background bash process for 5 h, including while frozen. Bash is not hardened the way the binary is (wallet.rs:122-127), and several sessions log in to Cherry as root. Passing it with the `printf` builtin through a pipe does keep it out of argv and the environment.
- **Disk is fine.** 131G free against a 25G limit. `alts.jsonl` (107-115 MB per segment) is never compressed.
- **The zstd overlap is harmless.** Compression of a finished segment overlaps the next segment's boot at nice 10, without ionice. sar %nice was ≤0.5% for 20:10-20:20 UTC, which is negligible (an inference). seg.py falls back to `.zst`, leaving only a tiny exists-then-open race.
- **The base config's own cap is never used.** `arb-w.toml`'s `max_failed_fees_lamports = 25000000 # EXP: $3` is overwritten by sed for every segment.

## CLAIMS
- [high] C1: Every early segment end (w5h p2,p3,p5,p6,p8,p9 and later p11,p12,p13; plus w500-p1) was an operator SIGINT. No bot stop condition fired: the final status has stopped=null in every segment, at most 4 new token accounts vs a cap of 25, no panics, and every .out ends with 'done:'.
  EVID: Operator transcript ~/.claude/projects/-home-moiz-arbed/39acbea7-6d22-44f3-a5ba-3fe790ea68b1.jsonl: pkill/kill -INT at 18:45:13, 19:11:50, 19:13:41, 19:41:02, 19:50:36, 20:19:56, 20:27:47, 20:49:35, 20:57:12, 20:58:58; SNAP/root/runs/*/status.jsonl last lines; exit paths at src/engine.rs:313 and src/main.rs:505-510
  VERDICT: confirmed — Every early end has a kill in the operator transcript (my ev.py/ev2.py over 39acbea7-....jsonl): 18:45:13 (w500), 19:11:50 (p2), 19:13:41 (p3; the pkill ran after a local cargo build+test+scp, so about 60 s after the tool-call time), 19:41:02 kill -INT 1607651 (p5), 19:50:36 (p6, pid 1613626), 20:19:56 (p8), 20:27:47 (p9), 20:49:35 (p11), 20:57:12 (p12), 20:58:58 (p13). All tool results returned without error. Code: Engine::run breaks only on the stop flag, the deadline or a channel disconnect (engine.rs:313). Only the ctrl_c/SIGTERM task sets the flag (main.rs:505-510). run() holds tx, so the channel cannot disconnect. The final status.jsonl line equals the 'exec final' line in run.log for w500-p1 and p1-p10, with stopped=null in every one. max new_token_accounts is 4 (p10), against a cap of 25 in every arb-w-pN.toml. No .out contains 'panic', and all end with 'done:'. Over ssh, p11 and p13 also end with done: and stopped=null. One addition: p14 was also SIGINTed, at 21:07:33 after 506 s.
- [high] C2: Segment 7's 1622 s is not a bot overrun. Its engine ran 1202.0 s and printed done at 20:11:00.78 UTC. The supervisor (pid 1558445) was SIGSTOPped at 19:52:32 and SIGCONTed at 20:17:50, so p7 stayed a zombie for about 410 s.
  EVID: SNAP/root/runs/w5h-p7/meta.json started_ns vs run.log last line; transcript tool calls 'kill -STOP 1558445' (19:52:32) and 'kill -CONT 1558445' (20:17:50); ps at 20:09:45 shows state T; Cherry file mtimes all 23:11:00.78 local; sar 23:10-23:20 local: user 4.41%, system 2.53%
  VERDICT: confirmed — p7 meta.started_ns is 19:50:58.758 and its run.log 'done:' is 20:11:00.780, so the engine ran 1202.0 s. The transcript shows 'kill -STOP 1558445' at 19:52:32, with ps showing state T. At 20:09:45 ps shows 1558445 in T and 1623060 in Rl. At 20:15:57 ps shows 1623060 as Z <defunct>. 'kill -CONT 1558445' ran at 20:17:50, and the supervisor logged the exit at 20:17:51. Zombie time is 20:17:51 − 20:11:00.78 = 410.2 s. I did not re-check the sar or mtime claims on Cherry.
- [medium] C3: Through p13, 640 s of 7,977 s of campaign wall time (8.0%) had no engine running: 424.1 s from the p7→p8 SIGSTOP pause and 215.7 s from 12 restarts (boot 10-14 s each, plus a 10 s supervisor backoff after each of 9 early ends).
  EVID: work/stops/timeline.py over SNAP meta.json/run.log for p1-p10 plus p11-p13 meta/run.log read over ssh; supervisor log times
  VERDICT: confirmed — Recomputed from meta.started_ns and run.log 'done' for p1-p10, and from p11/p13 meta and run.log read over ssh: wall 7,977.0 s (18:46:03 → p13 done), engine 7,337.0 s, idle 640.0 s (8.02%). Within p1-p10, idle is 581.1 s of 7,332.4. Two small errors in the split: the 424.1 s 'SIGSTOP pause' includes about 14 s of normal p8 boot (the pause itself is 410.2 s), and only 8 of the 10 s backoffs fall inside the window, because p13's backoff comes after 20:59:00. The total is unaffected.
- [high] C4: The bot and the supervisor both count only failed fees, consistently: 40,000,000 − 2,497,246 = 37,502,754, now 37,005,584 after p12's 497,170. Bundle-only mode (p7-p11) produced 0 failed fees, so the budget froze while Σprofit_lamports over p1-p13 reached −19,204,527.
  EVID: run-w.sh spent calc; src/exec.rs:319 (cap check) and :761 (spent only for landed-failed); supervisor log lines; status.jsonl last lines
  VERDICT: partly — The arithmetic is right. p1-p6 failed fees sum to 2,497,246, so 40,000,000 − 2,497,246 = 37,502,754, and after p12's 497,170 the remainder is 37,005,584, which matches the supervisor's seg-14 line. p7-p11 failed fees are 0. Σprofit over p1-p13 is −19,204,527 (p11 −1,494,010 and p13 0 via ssh; p12 −1,508,910 from big/w5h-p12/status.jsonl). The two sides do agree with each other, but both undercount against the chain. getSignaturesForAddress for the wallet (public RPC, 327 sigs since 18:15) shows 33 landed-and-FAILED transactions (error 0x4E580002) that outcomes.jsonl records as not landed. In w5h their fees total about 426,475 lamports: p1 7,301, p2 14,294, p12 77,288 (11 txs), and p14 about 327,592 (17 txs; one fee estimated from worst_fee). So the recorded p12 failed fees are about 13.5% short and p14's about 22.7% short. The figure is also stale: p14 added 1,117,914, and the budget now shows 35,887,670 (supervisor line for seg 15).
- [high] C5: The negative profit_lamports is mostly token-account creation. In p1-p10, 10 wins carry 16,383,000 lamports of account creation (equal to new_token_accounts = 10). The wins' trading net (round trip − fee − tip) was +181,393. On chain, p7 attempt 62 shows a system createAccount of 1,513,840 lamports for a Token-2022 account.
  EVID: SNAP/root/runs/w5h-p{3,6,7,9,10}/outcomes.jsonl (round_trip_on_chain, fee_lamports, tip_paid_lamports, profit_lamports); public RPC getTransaction for sig kw1frUAY54… saved in work/stops/tx62.json
  VERDICT: partly — The decomposition reproduces exactly: 21 wins in p1-p10, Σround_trip 632,807 − fees 113,670 − tips 337,744 = +181,393 trading net, and residual −16,383,000 on the 10 creates_token_account wins. However, the 16,383,000 is not all token-account rent. Token accounts cost 4×1,488,440 (SPL) + 6×1,513,840 (Token-2022) = 15,036,800. p6 attempt 69's residual is 2,860,040, and on chain (getTransaction 2wqUDpE6…) that transaction also created a 137-byte account owned by the PumpSwap program (pAMMBay…) for 1,346,200. That account is neither a token account nor counted by new_token_accounts or the 25-account cap. The p7 #62 createAccount of 1,513,840 (Token-2022, space 170) is confirmed from work/stops/tx62.json. The two pre-rent losing wins (−7,652 for p3 #96 and −4,447 for p7 #350) are confirmed.
- [high] C6: Real losses are not bounded by the budget: there is no P&L or wallet-balance stop. max_new_token_accounts=25 resets every segment (up to about 37.8M lamports of rent per segment). In-flight attempts are dropped when a segment stops (p8: 7, p9: 6). Since p10, settle_s=1 checks statuses only once, so later landings are never counted.
  EVID: src/exec.rs:435, :611, :675-681, :761, :788; arb-w-p10.toml settle_s=1 and max_new_token_accounts=25; in_flight in final status lines
  VERDICT: confirmed — The code supports it. I found no P&L or balance stop in the run path (the only getBalance is main.rs:231, outside run()). new_atas starts at 0 per process (exec.rs:283). The cap check is at exec.rs:435. A single getSignatureStatuses call follows sleep(settle) (exec.rs:674-681). The loop exits without draining Settled events, and rt.shutdown_timeout(2 s) kills the settle tasks. The chain also confirms it, which the analyst did not measure. In p12, 11 failed transactions landed 3-18 slots after the trigger and were recorded as not landed. In p14, 13 more were missed at settle, and the 4 attempts still in flight at the 21:07:33 SIGINT (#506-512, 74,844 lamports) landed and were never counted. One mechanism correction: the status check was always a single check. p10 only cut its delay from 3 s to 1 s, and with 3 s, p6 had 58 landings with 0 missed. The pre-p10 misses (p1 #2, p2 #8, w500 #30) came from RPC 'rate limited' or 'no answer' errors at settle. The analyst's in-flight examples (p8: 7, p9: 6) cost nothing on chain, because those segments were bundle-only.
- [medium] C7: The supervisor's 'records only' fallback cannot work. arb-w.toml has mode="live", and running without --live fails at main.rs:487 with exit 1. Budget exhaustion would therefore become a crash loop that stops after 7 early ends.
  EVID: SNAP/root/arb-w.toml line 3; src/main.rs:487; run-w.sh live="" branch and crash counter
  VERDICT: confirmed — arb-w.toml line 3 is mode = "live". main.rs:487 runs `if live != (cfg.mode == "live") { bail! }` and main() returns Result, so the process exits 1 immediately. In run-w.sh, live="" when left < 1,000,000, and dur < mins*60−30 then counts as an early end. 'recent > 6' within 900 s stops the loop. Each iteration takes about 10-11 s (instant exit plus sleep 10), so it stops after the 7th try within about 75 s.
- [medium] C8: The early-end diagnostic in the supervisor log is pure noise: grep 'panic|error' matches '(N, 0 errors)' keep-alive summaries. The crash counter counts deliberate operator kills (3 in 15 min at 20:59:00), and 7 would end the campaign.
  EVID: SNAP/root/runs/w5h.supervisor.log 'ended early' lines; Cherry runs/w5h.supervisor.log tail ('segment 13 ended early (3 in 15 min)')
  VERDICT: confirmed — All 9 'ended early' lines in w5h.supervisor.log, plus the p13 and p14 lines over ssh, show only 'send final … (N, 0 errors)'. tail -2 always picks those two final send lines, which hides real error lines that do exist in the .out files (for example, w5h-p3.out has repeated 'erpc: connect … transport error'). The counter is 'recent > 6' within 900 s, so 7 early ends within 15 min stop the campaign. It read '3 in 15 min' at 20:59:00 and again at 21:07:36.
- [medium] C9: The live binary was hot-swapped about 15 times during the campaign (mv -f arb-lab-w.new arb-lab-w), most recently at 20:54:47 UTC while p12 was running. meta.json records no build id, so per-segment results cannot be tied to a code version.
  EVID: Transcript tool calls (18:48:13 … 20:54:45); Cherry 'ls -la arb-lab-w' mtime 23:54:47 local; meta.json keys in SNAP/root/runs/w5h-p7/meta.json
  VERDICT: confirmed — I count 15 successful 'mv -f arb-lab-w.new arb-lab-w' in the transcript between 18:48:13 and 20:54:45, all with is_error false. Cherry's arb-lab-w mtime is 23:54:47 local = 20:54:47 UTC, while p12 was running. meta.json keys have no build id. One nuance: the binary each segment ran can be inferred from deploy times versus process start (p7 ← 19:50:29, p8/p9 ← 20:11:17, p10/p11 ← 20:27:47, p12 ← 20:49:18, p13+ ← 20:54:45). Its source cannot be recovered, because src/ is uncommitted and was edited continuously.

## MISSED (verifier)
- The analyst never checked the chain, and the failed-fee budget is measurably undercounted. Reconciling the wallet's on-chain signatures (public RPC getSignaturesForAddress, 327 sigs) against outcomes.jsonl finds 33 landed-and-failed transactions recorded as 'not landed'. Fees: about 426k lamports in w5h (p1 7,301, p2 14,294, p12 77,288, p14 ~327.6k) and 14,442 in w500. Causes: the single status check at +1 s (settle_s=1) misses landings 3-18 slots after the trigger; RPC rate-limit or no-answer errors at settle; and the SIGINT drops attempts still in flight. Files: work/verify-stops/sigs1.json and missed_fees.json.
- The report is stale on the current state. p14 ran 506 s, was SIGINTed at 21:07:33, and charged 1,117,914 recorded failed fees, with 66 landed and 3 wins. The budget is moving again (35,887,670 left at the start of seg 15), and the early-end counter read '3 in 15 min' again. Direct sends are back on, and those are the segments where the undercount happens.
- The 16,383,000 'token-account creation' figure includes 1,346,200 for a 137-byte account owned by the PumpSwap program (p6 attempt 69, tx 2wqUDpE6…). It is not a token account, it is invisible to new_token_accounts and the 25-account cap, and it is not recovered by closing token accounts. True token-account rent for the 10 accounts is 15,036,800.
- The in-flight examples point at the wrong segments. p8 (7 in flight) and p9 (6) were bundle-only, and nothing from them landed on chain. The real loss from dropping in-flight attempts is in direct-send segments: p14's 4 in-flight attempts landed as failures right after the kill, costing 74,844 lamports that were never counted.
- Code-version caveat for every code citation: the local target/release/arb-lab was built at 20:54:11 UTC (exec.rs and config.rs edited 20:48:28) and is the same size as Cherry's arb-lab-w (60,051,248 bytes). The code the analyst read is therefore the binary that p13 onward ran, not what p1-p12 ran. The task premise of a binary built at 20:27 is also stale.
- A minor point: during live p12 (20:54:45) the operator ran `arb-lab-w simcheck --config arb-w.toml` and RPC-scanning python on the trading host. Other operator activity on the live box went beyond the kills and deploys the analyst listed.
## REC ISSUES (verifier)
- The loss stop as written ('track Σprofit − Σfailed_fees and/or wallet balance') gives the bot's counters as an acceptable primary source. Those counters miss about 13-23% of failed fees in direct-send segments, so a counter-based stop fires late. The wallet SOL+WSOL balance from chain should be the primary check. It also has to be enforced inside a segment by the bot, not only between 20-minute segments by the supervisor.
- Re-checking statuses at +1 s and +10 s helps, but durable-nonce transactions never expire until the nonce advances. The bot frees the nonce lease at settle, so a late landing can invalidate the next attempt on the same nonce and still go unrecorded. The reconciler (wallet signatures vs outcomes) should be required and should run every segment, not be optional. Alternatively, keep the nonce leased until the nonce value is seen to change.
- Closing the new token accounts is safe only while no segment is running. The bot loads its 'held' mints at startup and does not build a create instruction for them. Closing an account mid-campaign would make the next trade on that mint fail and pay a failed fee. The ~18M figure also overstates what closing recovers: the 1,346,200-lamport PumpSwap account is not a token account.
- 'Restarts cost only about 18 s each' averages two cases. After an early end a restart costs about 20-23 s (10-13 s boot plus the 10 s backoff); after a natural end it costs about 10-13 s.
- The pause and restart-file recommendation is sound, but it should also cover the operator's non-atomic config edits. The python open('arb-w.toml','w').write(...) rewrites race the supervisor's sed copy at segment start. Staging the config and renaming it into place would close that race.
## RECS
- [now] Give the supervisor explicit 'pause' and 'restart-now' controls (e.g. runs/<name>.pause and runs/<name>.next files checked between segments, with the supervisor sending the SIGINT itself and logging 'operator restart'). Stop using kill -STOP on run-w.sh, and keep operator restarts out of the crash counter. — The SIGSTOP pause cost 424 s, left p7 as a zombie and confused the operator about whether the bot was live. Operator kills already put the counter at 3/7.
- [now] Add a real loss stop. The supervisor should track Σ(profit_lamports) − Σ(failed_fees) (with rent shown separately) and/or read the wallet SOL+WSOL balance at each segment start and stop below a floor. It should also pass a cumulative remaining-ATA allowance to each segment the way it passes the fee budget. — The 40M budget only sees failed fees. It has been frozen since p7 while profit fell by 19.2M, and the 25-account cap resets every segment.
- [next] Make the bot log why it stopped (SIGINT, SIGTERM, deadline, cap) in run.log and status.jsonl, and write the binary's build hash and the config hash to meta.json. — Every early end looks identical in the logs today. With 15 hot-swaps, results can't be tied to a code version.
- [next] Fix the 'records only' branch: run the no-budget case with a shadow config (mode != live), or stop with a clear message. Also replace grep 'panic|error' with checks of rc and the new stop reason. — Today budget exhaustion becomes a 7× crash loop, and the early-end diagnostic always prints '0 errors' lines.
- [next] With settle_s=1, re-check statuses later (e.g. at +1 s and +10 s) before marking an attempt 'not landed'. On shutdown, wait a bounded time for in-flight settles to finish, and add an offline reconciler that compares the wallet's on-chain signatures with outcomes.jsonl. — Late landings and abandoned in-flight attempts are never counted, which matters again now that direct sends are back on (p12 failed fees 497,170).
- [later] Set a minimum segment length before judging a hypothesis, or log the operator's reason for each kill. — p8 (112 s), p11 (68 s) and p13 (83 s) are too short to support conclusions; the restarts themselves cost only about 18 s each.
- [later] When the campaign ends, close the 12 new token accounts once they are empty (a write action, for the owner to decide). — About 18M lamports of the reported 'loss' is rent sitting in those accounts.
## OPEN Q
- Did any durable-nonce transaction from a stopped segment land after that segment ended? Its fee or P&L would be missing from every status.jsonl. Answering this needs the wallet's on-chain signature list compared against all outcomes.jsonl signatures.
- p6 attempt 69 shows 2,860,040 lamports beyond trade P&L, while the other 9 such wins show 1.49-1.51M. Were two accounts created in that transaction, or is there another cost?
- Do the simcheck runs started during live segments share the Haan RPC quota with the live bot? Every segment logs hundreds of 'rate limited' failures, and the settle-time statuses check depends on that RPC.
- Was the base config's max_failed_fees_lamports = 25000000 ('EXP: $3 for tonight experiments') meant to cap w5h? run-w.sh overrides it every segment with the budget left (37.0-37.5M).