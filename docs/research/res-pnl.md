# Money: what the campaign actually made and lost

## Money: what w5h p1-p10 (and w500-p1) made and lost

**Sources.** The snapshot files are `status.jsonl` (last line), `attempts.jsonl`, `outcomes.jsonl`, `copies.jsonl` and `*.out`. I also checked on-chain data read-only through the public Solana RPC. That covered the wallet's 206 signatures since funding, every one of those transactions, its token accounts and the rent-exempt minimums. Raw responses are saved in `work/pnl/chain_*.json*`. I made two light read-only SSH calls to Cherry for configs, supervisor lines and status. Scripts are in `SNAP/work/pnl/` (`seg_pnl.py`, `wins.py`, `ledger.py`, `match.py`, `recon2.py`, `walk.py`, `final_table.py`).

### 1. Per segment (lamports)
| seg | sent | landed | wins | landed-failed | failed fees (rec + unrecorded) | win fees | tips | gross round trip on wins | new ATAs | rent | profit_lamports | trading net ex-rent |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| w500-p1 | 289 | 13 | 0 | 13 | 77,668 + 14,442 | 0 | 0 | 0 | 0 | 0 | 0 | -92,110 |
| p1 | 917 | 14 | 0 | 14 | 91,278 + 7,301 | 0 | 0 | 0 | 0 | 0 | 0 | -98,579 |
| p2 | 187 | 4 | 0 | 4 | 1,318,650 + 14,294 | 0 | 0 | 0 | 0 | 0 | 0 | -1,332,944 |
| p3 | 149 | 6 | 2 | 4 | 37,853 | 16,369 | 0 | 12,735 | 1 | 1,488,440 | -1,492,074 | -41,487 |
| p4 | 444 | 10 | 0 | 10 | 139,043 | 0 | 0 | 0 | 0 | 0 | 0 | -139,043 |
| p5 | 143 | 10 | 0 | 10 | 155,224 | 0 | 0 | 0 | 0 | 0 | 0 | -155,224 |
| p6 | 131 | 58 | 2 | 56 | 755,198 | 12,301 | 10,248 | 43,340 | 2 | 3,027,680 + 1,346,200 (pump) | -4,353,089 | -734,407 |
| p7 | 381 | 8 | 8 | 0 | 0 | 40,000 | 139,080 | 266,685 | 2 | 3,002,280 | -2,914,675 | +87,605 |
| p8 | 115 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| p9 | 1,182 | 2 | 2 | 0 | 0 | 10,000 | 104,362 | 159,088 | 1 | 1,513,840 | -1,469,114 | +44,726 |
| p10 | 762 | 7 | 7 | 0 | 0 | 35,000 | 84,054 | 150,959 | 4 | 6,004,560 | -5,972,655 | +31,905 |
| **p1-p10** | 4,411 | 119 | 21 | 98 | 2,497,246 + 21,595 | 113,670 | 337,744 | 632,807 | 10 | 15,036,800 + 1,346,200 | -16,201,607 | **-2,337,448** |

**Cross-checks.**
- Status and outcomes agree exactly for every segment: sent = attempts rows, and landed, wins, fees, tips and profit match.
- Some attempts never got an outcome row because they were still in flight when the segment stopped: p5 1, p8 7, p9 6, p10 1.
- The chain shows none of those landed. It shows exactly 4 landed failures that were never recorded:
  - p1#2 (7,301) and p2#8 (14,294): the "statuses: shyft ... rate limited / no answer" settle errors.
  - w500 #30 (7,661): also a statuses rate-limit error.
  - w500 #88 (6,781): landed 41 slots after its trigger, after the 8 s settle window. A durable-nonce transaction stays valid, so it can land late.

### 2. How profit_lamports is computed (src/exec.rs:756-792)
For a landed transaction, `profit` is the wallet's lamport change (post minus pre) plus the change in its WSOL token amount. It is added to `c.profit` only when `err` is null, so wins only.

That figure therefore already includes the fee (base + priority), the tip transfer, and the rent of any account the transaction created. For a landed failure, only the fee goes to `c.spent` (failed_fees). `tips_lamports` and `fees_lamports` in the status line are bookkeeping and are already inside the profit figure, so do not subtract them again.

**Why segments with wins are negative.** For each win I computed `residual = profit - (round_trip_on_chain - fee - tip)`:
- It is exactly 0 on the 11 wins that created no account.
- It is exactly -1,488,440 on 4 wins (165-byte SPL token account).
- It is exactly -1,513,840 on 5 wins (170-byte Token-2022 account with immutableOwner).
- It is -2,860,040 on p6#69: 1,513,840 for the account plus 1,346,200 for a 137-byte account owned by the pump AMM program (`BKPfj2Ht…`). That is almost certainly PumpSwap's `user_volume_accumulator`, which `build.rs:149-155` passes on buy legs. This is an inference.

The public RPC confirms the current rent-exempt minimums: 165 bytes = 1,488,440 and 170 bytes = 1,513,840, which is below the config comment's "~0.0025 SOL".

The total rent is 16,383,000 against a profit_lamports sum of -16,201,607. **The trades themselves made +181,393 net**: gross 632,807, minus tips 337,744 (53%), minus win fees 113,670.

All 11 non-WSOL token accounts hold 0 tokens on chain (slot 453,046,640): the 10 from p1-p10 plus 9pJW…, created in p11. Closing them returns the rent. Whether the pump account can be closed is unverified.

**Quote accuracy.**
- On the 21 wins, 14 matched the predicted round trip to within ±2 lamports. Chain total 632,807 vs predicted 706,900 (89.5%). The worst misses were p6#110 (-44,560), p3#96 (-12,735) and p7#350 (-11,496).
- Two wins lost money even before rent:
  - p3#96 (-7,652): `gross_floor` let a 710-lamport round trip land against an 8,362 fee.
  - p7#350 (-4,447): the bundle's on-chain floor was tip + 1. That floor is fixed in p9/p10, where 0 bundle copies have a floor below tip + 5,000.
- All 96 landed failures that have logs reverted on the profit check (0x4e580002) with a negative on-chain round trip, except one 0x1794 venue error in p6. Only the fee was lost. Example: p6's 55 failures predicted +1.494 SOL in total and came in at -1.308 SOL (phantom gaps).

### 3. failed_fees = 0 in p7-p10 is real
From p7, `tpu_max_expected_lamports = 1`, which makes every trade with positive expected profit "TPU-hopeless". All 2,440 attempts in p7-p10 were therefore bundle-arm, with cu_price 0 and only jito-bundle copies or resends. Jito drops a bundle whose transaction fails, so a failure costs nothing.

The chain shows zero failed wallet transactions between 19:50:49 and 20:48:15 UTC; only the 17 wins appear.

What failed_fees does not count:
- rent;
- net-negative wins (those sit in profit);
- landings missed by a statuses error or after the settle window.

Priority fees and compete bids do count, but only when the transaction lands: inside profit on a win, inside failed_fees on a failure. The p2 compete bid did land: attempt 0 used a cu_price of 5,000,000, paid a 1,305,030 fee on a 1.94 SOL trade and reverted. That one fee is 99% of p2's recorded failed fees and 52% of all w5h failure fees. The code comment at exec.rs:474 refers to this p2 trade, next to the cap that now prevents it.

**p6.** 54 of its 56 landed failures were TPU trades that the sim gate sent on our own quote after finding its check stale ("sim stale … sent on our quote", 55 such lines in `w5h-p6.out`). Those 54 cost 712,897 in fees. All 57 TPU attempts in p6 landed, and 1 won.

### 4. True net P&L
The wallet's liquid balance (SOL + WSOL account) was 4,327,670,090 at the w5h start and 4,308,949,642 after p10. That is **-18,720,448 lamports = -0.01872 SOL ≈ -$2.23**, which equals recorded -18,698,853 minus the 21,595 unrecorded. It breaks down as:

| component | lamports | USD |
|---|---|---|
| gross trading profit on 21 wins | +632,807 | +$0.075 |
| tips (all Jito bundle wins) | -337,744 | -$0.040 |
| fees on wins (105,000 base + 8,670 priority) | -113,670 | -$0.014 |
| fees on 98 landed failures (490,000 base + 2,028,841 priority) | -2,518,841 | -$0.300 |
| **true trading result** | **-2,337,448** | **-$0.28** |
| pump AMM account rent (recovery uncertain) | -1,346,200 | -$0.16 |
| rent locked in 10 token accounts (balances 0, closable) | -15,036,800 | -$1.79 |

By era:
- **TPU era p1-p6:** -2,501,684 ex-rent. p2's compete bid and p6's stale-gate bypass account for 2,067,351 of it.
- **Bundle-only era p7-p10:** +164,236 ex-rent (+87,605 / 0 / +44,726 / +31,905). That is about $0.02 over about 57 minutes, on 18 bundle wins netting about 9.3k each after a tip of about 57% of gross.

The reported profit_lamports for p7-p10 (-10,356,444) is 100% rent: 10,520,680 for 7 new accounts.

Separately, w500-p1 lost 92,110 in failed fees, and creating nonce accounts cost 50,000 in fees. The 20 nonce accounts lock 21,132,800 of rent (10 created before w500, 10 during it), which is recoverable.

**Postscript, outside my scope (read live at 21:00 UTC, not reconciled on chain).** The campaign had moved on to segment 14, using a changed "hybrid" arb-w.toml (TPU arm back on for expected ≥ 1.5M, Helius 1M tip) and a binary rebuilt at 20:54:47 UTC.
- p11: 1 win, -1,494,010 (new token account).
- p12: 75 landed, 1 win, failed fees 497,170, profit -1,508,910.
- p13: nothing landed.
- p14 so far: 3 failures, 50,642.

## CLAIMS
- [high] C1: profit_lamports counts wins only and equals the wallet lamport change plus the WSOL token change, so it already includes the fee, the tip and the rent of any account the transaction created. A landed failure adds only its fee, to failed_fees (spent).
  EVID: src/exec.rs:761-792 (c.spent += fee if err; c.profit += profit only when err is None; profit = postBalances-preBalances of payer + WSOL uiTokenAmount delta)
  VERDICT: confirmed — src/exec.rs:756-792. profit = payer postBalances-preBalances plus the WSOL uiTokenAmount delta (lines 769-773). It is added to c.profit only when err is None and tx is non-null (786-790). A landed failure adds only meta.fee to c.spent (763). One edge case is missing from the claim: if getTransaction returned null for a landed signature, c.spent += o.worst (the worst-case fee). No outcome row in w500/p1-p10 hit that case (no landed row has fee 0 or null). The per-win residuals in C2 are exactly 0 or exactly a rent amount, so the recorded tips and fees also match the chain.
- [high] C2: The negative profits on winning segments are account rent, not trading losses. For each win, profit - (round_trip_on_chain - fee - tip) is exactly 0 (11 wins), -1,488,440 (4 wins, 165-byte accounts), -1,513,840 (5 wins, 170-byte Token-2022 accounts), or -2,860,040 (p6#69, which also created a 1,346,200-lamport pump AMM account). Rent totals 16,383,000 against a profit sum of -16,201,607, so trading on wins netted +181,393.
  EVID: work/pnl/wins.py and ledger.py over runs/w5h-p*/outcomes.jsonl + attempts.jsonl; rent minimums from getMinimumBalanceForRentExemption(165)=1,488,440 and (170)=1,513,840 (public RPC); getAccountInfo BKPfj2Ht… owner pAMMBay6…, space 137, 1,346,200 lamports (work/pnl/chain_uva.json)
  VERDICT: confirmed — Recomputed in work/verify-pnl/wins2.py from outcomes.jsonl. Residuals: 11 x 0, 4 x -1,488,440 (p3#72, p7#308, p10#2, p10#617), 5 x -1,513,840 (p6#110, p7#62, p9#976, p10#464, p10#665), and p6#69 -2,860,040. Sums: rent -16,383,000, profit -16,201,607, rt-fee-tip +181,393. The chain agrees: those 11 win transactions are the only w5h p1-p10 transactions that created accounts. In p6#69 the created accounts were SJCBBcgs (1,513,840) and BKPfj2HtknArpzzksCTUfpT2KRge2p4CzDe4JcKKp9HS (1,346,200). A fresh getAccountInfo returns owner pAMMBay6..., space 137. The account is seeded by the payer only (build.rs:149, user_volume_accumulator), so it is a one-time cost per wallet that may not be refundable (that part is inference).
- [high] C3: All 11 non-WSOL token accounts of wallet 2g7rYv7y hold 0 tokens; their only extension is immutableOwner. Closing them recovers the rent: 15,036,800 lamports for the 10 created in p1-p10, or 16,550,640 including the p11 account for 9pJW….
  EVID: getTokenAccountsByOwner (both token programs, jsonParsed) at slot 453,046,640: work/pnl/chain_tokens_*.json
  VERDICT: confirmed — At slot 453,046,640 the 11 accounts hold 0 tokens: 4 SPL x 1,488,440 and 7 Token-2022 x 1,513,840 (immutableOwner only). Totals are 16,550,640, or 15,036,800 without 9pJW. Two caveats. (1) The 15,036,800 includes the USDC account CtRRHdJg (1,488,440), which the analyst's own recommendation says to keep, so the closable one-off rent for p1-p10 is 13,548,360. (2) The figure is already stale. My public-RPC getTokenAccountsByOwner at slot ~453,052,716 shows 13 zero-balance non-WSOL accounts locking 19,552,920, because p12 and p14 each added one (FUoXrksR and BniWiG9M; work/verify-pnl/now_*.json).
- [high] C4: failed_fees = 0 for p7-p10 is real. Every attempt was bundle-arm (tpu_max_expected_lamports = 1, cu_price 0, only jito-bundle copies), and the chain shows no failed wallet transaction between 19:50:49 and 20:48:15 UTC, only the 17 recorded wins.
  EVID: work/pnl/arms.py (path_arm/fee_arm counts per segment); arb-w-p7.toml diff; work/pnl/recon2.py over chain_txs.jsonl (p7 8 ok/0 err, p9 2/0, p10 7/0)
  VERDICT: confirmed — All 2,440 attempts in p7-p10 (381+115+1182+762) have path_arm=bundle, fee_arm=bundle-no-priority and cu_price 0. Their only copies are jito-bundle, both in attempts.jsonl and copies.jsonl. arb-w-p7..p10.toml set tpu_max_expected_lamports = 1, which feeds tpu_hopeless at exec.rs:442. My own chain walk (work/verify-pnl/chainwalk2.py, non-overlapping supervisor windows) gives p7 8 ok/0 err, p8 0/0, p9 2/0 and p10 7/0, which is exactly the 17 recorded wins.
- [high] C5: On-chain reconciliation: the wallet's SOL + WSOL went from 4,327,670,090 at the w5h start to 4,308,949,642 after p10, a change of -18,720,448 lamports (-0.0187 SOL, about -$2.23). That equals the recorded -18,698,853 minus 21,595 of failed fees the bot never recorded (p1#2 and p2#8, both statuses-RPC errors).
  EVID: work/pnl/walk.py and match.py over chain_sigs.json/chain_txs.jsonl vs outcomes.jsonl; outcomes settle_error fields for those attempts
  VERDICT: confirmed — Delta reproduced: -18,720,448 = -16,201,607 - 2,497,246 - 21,595. The analyst's absolute levels count the WSOL ATA's own rent (payer + WSOL account lamports). On a payer + WSOL token-amount basis the levels are 4,326,181,650 -> 4,307,461,202, lower by 1,488,440, with the same delta. Unrecorded landings verified by matching chain signatures to attempts copies: p1#2 tpu-direct 7,301 ('rate limited'), p2#8 shyft 14,294 ('no answer in 3 s'), w500#30 7,661 (rate limited), w500#88 6,781 (no settle error; w500 meta settle_s = 8, so the '8 s window' is right for w500). Lamport continuity holds across all 206 transactions when ordered by slot and transactionIndex, so no wallet transaction is missing from the analyst's list.
- [high] C6: The true trading result for p1-p10 is -2,337,448 lamports (about -$0.28): +632,807 gross on wins, -337,744 tips, -113,670 win fees, -2,518,841 fees on 98 landed failures. Bundle-only p7-p10 netted +164,236 ex-rent; TPU-era p1-p6 lost 2,501,684.
  EVID: work/pnl/final_table.py
  VERDICT: confirmed — Arithmetic reproduced: 632,807 - 337,744 - 113,670 - 2,518,841 = -2,337,448. Per segment: p7 +87,605, p9 +44,726, p10 +31,905 (sum +164,236). p1-p6 total -2,501,684. One label in the report is wrong. It says p2's compete bid and p6's stale-gate bypass 'account for 2,067,351', but 2,067,351 is the whole p2 net (1,332,944) plus the whole p6 net (734,407). The compete bid (1,305,030) plus the 54 stale-gate failures (712,897) come to 2,017,927.
- [medium] C7: p2's loss is one compete bid: attempt 0 (1.94 SOL PumpSwap>DLMM trade, cu_price 5,000,000) paid a 1,305,030 fee and reverted. That is 99% of p2's recorded failed fees and 52% of all w5h failure fees.
  EVID: runs/w5h-p2/attempts.jsonl + outcomes.jsonl attempt 0 (fee_lamports 1,305,030, priority_fee_lamports 1,300,040); exec.rs:474 comment
  VERDICT: confirmed — p2 attempt 0: PumpSwap->Dlmm, size 1,938,467,936, cu_price 5,000,000, priority 1,300,040, landed via tpu-direct, fee 1,305,030, 0x4e580002, round trip on chain -79,837,800 against +63,330,308 predicted. That is 98.97% of p2's recorded 1,318,650 and 51.8% of 2,518,841. Context the analyst left out: arb-w-p2.toml already had max_priority_lamports = 100000, but the compete arm in that binary did not apply it. The cap_abs at exec.rs:473-476 was added later.
- [medium] C8: 54 of p6's 56 landed failures were TPU trades sent after the sim gate judged its check stale. They cost 712,897 lamports in fees; all 57 p6 TPU attempts landed and only 1 won.
  EVID: grep 'sim stale' runs/w5h-p6.out (55 attempts) cross-joined with w5h-p6/outcomes.jsonl failures
  VERDICT: confirmed — Cross-join of w5h-p6.out with attempts and outcomes. 54 TPU landed failures were 'sim stale' attempts, costing 712,897 in fees. 2 non-stale TPU failures cost 42,301. All 57 TPU attempts landed and 1 won (p6#110, also stale). Small correction: w5h-p6.out has 56 'sim stale' lines covering 55 unique attempts, not 55 lines. The fail-open is exec.rs:646-650.
- [medium] C9: Quotes on wins are mostly exact: 14 of 21 wins came within ±2 lamports of the predicted round trip, and the chain total was 632,807 against 706,900 predicted. All 96 landed failures with logs had a negative on-chain round trip (profit-check reverts), so they lost only the fee.
  EVID: outcomes.jsonl round_trip_on_chain vs round_trip_predicted (work/pnl inline script); failure code tally
  VERDICT: partly — Wins: 14 of 21 within ±2 lamports. Chain total 632,807 against 706,900 predicted (89.5%). Worst misses p6#110 -44,560, p3#96 -12,735, p7#350 -11,496. p3#96 had min_profit 1 (gross_floor). p7#350 had min_profit 12,050 = tip 12,049 + 1. All p8-p10 bundle copies have a floor of at least tip + 5,000 (the analyst says p9/p10, but p8 is fixed too). Failures: of the 96 recorded landed failures, 95 have round-trip data, all negative with 0x4e580002. The 96th is 0x1794 with no round trip. So the count is 95, not 96, and '98' in the report includes 2 chain-only failures that have no logs in outcomes. p6's 55 failures: predicted +1,494,276,709, chain -1,308,301,662 (confirmed).
- [medium] C10: The campaign moved on after the task brief. At 21:00 UTC segment 14 was running a modified hybrid arb-w.toml (TPU arm back on) and a binary rebuilt at 20:54:47 UTC. p12 then paid 497,170 in failed fees for 1 win.
  EVID: read-only SSH: runs/w5h.supervisor.log segment 11-14 lines, ls -l arb-lab-w, diff arb-w-p11.toml arb-w.toml, runs/w5h-p11..p14/status.jsonl last line
  VERDICT: partly — Read-only SSH, supervisor tail. p11 ran 20:48:15-20:49:36 (81 s, 1 win, -1,494,010). p12 ran 20:49:46-20:57:14 (75 landed, 1 win, failed fees 497,170, profit -1,508,910). p13 ran 96 s with nothing landed. p14 ran 20:59:10-21:07:36. p15 is running now with budget left 35,887,670. arb-lab-w mtime 23:54:47 +0300 = 20:54:47 UTC, confirmed. Corrections: (1) p12 started before the rebuild, so it ran the 20:27 binary. (2) Its hybrid differed from p14's: tpu_min 50,000, tpu_max 1,000,000, compete_mult 0, Helius disabled. 'TPU arm for expected >= 1.5M, Helius 1M tip' describes p14. (3) p12's real failed fees were higher than recorded. Chain shows 85 landed failures, 11 of them unrecorded (77,288 lamports), so the true total is about 574,458. (4) 'p14 so far: 3 failures, 50,642' is stale. p14 ended with 66 landed, 3 wins (all bundle) and 1,117,914 recorded failed fees, plus 17 chain-only failures (329,271) the bot never saw.

## MISSED (verifier)
- MOST IMPORTANT: since p10, [live] settle_s = 1 (arb-w-p10..p15.toml; p12/p14 meta.json show 'settle_s: 1'; p1-p9 used 3). exec.rs:675-690 checks getSignatureStatuses once, settle_s after sending. TPU copies that land later than that are recorded as 'not landed' with no error. Matching public-RPC getSignaturesForAddress against outcomes: p12 has 11 chain-only landed failures (77,288 lamports, landing 4-18 slots after the trigger), and p14 has 17 (329,271, which is 29% on top of the recorded 1,117,914). The bot's failed_fees and run-w.sh's 'budget left' therefore under-count by about 406,559 lamports now. They will keep under-counting as long as the TPU arm is on. The analyst blamed only statuses-RPC errors and the 8 s w500 window, and missed this 1 s window.
- The hybrid TPU arm's post-brief record is worse than the analyst's postscript shows. In p12+p14, all 137 recorded TPU-arm landings plus 28 chain-only ones failed (0 TPU wins). About 2.02M lamports of failure fees went on chain (497,170 + 77,288 + 1,117,914 + 329,271). All 4 wins in those segments were bundle-arm. Across w5h the TPU arm has 3 wins (p3#72, p3#96, p6#110) against about 263 landed failures.
- The current wallet state is not stated. At slot ~453,052,716 there are 13 zero-balance token accounts (19,552,920), the pump account (1,346,200), and 20 nonce accounts (21,132,800). Liquid SOL+WSOL is 4,300,972,767, which is -48,027,233 (-0.048 SOL, about -$5.72) since the 4,349,000,000 funding. Counting every account balance, the all-in loss is about -4,506,873 (about -$0.54), so most of the 'loss' is recoverable lock-up. Liquid fell another ~6.49M after p10 ended (p11-p15 so far).
- The trade decision never prices rent. creates_ata only adds compute units (exec.rs:340-341, 438) and counts against a per-process cap (max_new_token_accounts, reset each segment). So trades with 12k-120k lamports of gross were allowed to move ~1.5M lamports into new accounts. 10 of 21 p1-p10 wins did this. No minimum expected profit applies to account-creating trades.
- `held` (the set of mints with existing token accounts) is read only at startup (exec.rs:255-263) and decides whether to include CreateIdempotent (exec.rs:340). Closing accounts while a segment runs would make trades in those mints omit the account creation and fail. In the current TPU-on config, those failures land and are paid. The analyst's close-account suggestion does not mention this.
- Smaller errors: 2,067,351 is the whole p2+p6 net, not 'compete bid + stale gate' (that is 2,017,927). p6.out has 56 'sim stale' lines covering 55 attempts. 95, not 96, failures have round-trip logs. The 15,036,800 'closable' figure includes the USDC account the analyst says to keep (13,548,360 without it). Status 'sent' counts sim-gated attempts that were never transmitted (e.g. hundreds of p1/p4 TPU attempts end in 'sim_gated'), so sent=4,411 overstates real sends.
## REC ISSUES (verifier)
- Rec 4 (settle-accounting gaps): the diagnosis is incomplete and the numbers are out of date. The dominant cause now is the 1 s settle window, which missed 28 landed failures (406,559 lamports) in p12/p14, against 4 (36,037) before. The fix should poll statuses until the nonce lease ends, or check the nonce value against the leased value, and should not shorten settle_s while the TPU arm is on. Reconciling against the wallet's on-chain signature list after each segment would catch the rest.
- Rec 3 (close the zero-balance accounts) is risky as written for a live bot. `held` is cached at startup, so closing accounts during a segment makes later trades in those mints fail, and those failures are paid while TPU copies are on. Accounts should be closed only between segments, with the bot stopped. The figure should leave out the USDC account (13.55M, not 15.04M, for p1-p10; it is now 19.55M for 13 accounts in total). An in-transaction CloseAccount is unverified: if any dust remains, or the extra instruction pushes the transaction over the size limit (copies already reach 1,091 bytes against 1,232), the whole trade reverts. That is a paid failure on the TPU arm, so it needs testing before going live.
- Rec 1 (judge on trade_net): sound as a reporting change, but liquid change should not be dropped. The 1,346,200 pump account is probably not refundable, and unclosed accounts are real capital loss. trade_net also needs chain-only landed failures added, or it overstates results (it is wrong by 16-29% in the hybrid segments).
- Rec 2 (bundle-only): the direction is right and p12/p14 make it stronger. The weak point is the positive case. Bundle-only made +164,236 ex-rent over 17 wins in about 57 minutes (about $0.02), and p7#62 alone gave +53,843 (33%). The data show that the TPU arm loses money far more firmly than they show that bundle-only makes money. Also, the campaign is running a TPU-on config right now (p15). Whether to change that is the operator's decision; this read-only analysis must not act on it.
- Rec 6 (tip_share) has no evidence behind it about how the tip affects winning. At 0.5 (p7) the bot won 8 of 381 attempts; at 0.7 (p9-p10) it won 9 of 1,944. The comparison is confounded by time and pools. Lowering the tip could lose Jito auctions, so this should be an A/B experiment rather than a tuning fix. The tip is actually 0.7 x (predicted gross - 5,000) (p9#976: 78,079; p10#2: 10,637), not 0.7 x gross.
- Rec 5 (budget): it should also cover the 1 s settle under-count, which today hides landed failures inside the very failed-fee budget that run-w.sh enforces. That gap is as important as leaving rent and net-negative wins out of the budget.
## RECS
- [now] Report rent separately from trading profit: add rent_lamports (lamports moved into accounts the transaction created) and trade_net to outcomes and status, and judge segments on trade_net. — profit_lamports for p7-p10 reads -10.36M, but all of it is rent (10.52M) and the trades themselves made +164k. The headline number gives the opposite verdict on the only profitable configuration.
- [now] Do not keep re-enabling the TPU arm. The data supports only bundle-only (tpu_max_expected_lamports = 1). — TPU era p1-p6 lost 2.50M ex-rent; p12's hybrid config lost 497k in failed fees for 1 win. Bundle-only p7-p10 had zero failure cost and a positive net.
- [next] Have the owner decide whether to close the zero-balance token accounts for one-off mints (keep the USDC one, which is traded repeatedly), or add a CloseAccount for newly created mid-token accounts at the end of the trade transaction. This is an operator action outside this read-only analysis. — 15.04M lamports (16.55M with p11) is locked in accounts that hold 0 tokens. max_new_token_accounts = 25 applies per segment, not per campaign, so the lock-up can keep growing.
- [next] Fix the settle-accounting gaps: retry getSignatureStatuses on error; compare the nonce value after settle with the leased value to detect a late landing; recheck attempts still in flight at shutdown. — 4 landed failures (36,037 lamports, 21,595 of them in w5h) were never recorded: 3 from statuses rate-limit or no-answer errors and 1 that landed after the 8 s settle window. 15 attempts were still unsettled at shutdown.
- [next] Count rent and net-negative wins in the run-w.sh budget, or add a campaign-wide cap on new token accounts. — The 40M failed-fee budget only counts failed landings, but 16.4M left the liquid wallet as rent and 2 wins landed at a net loss, all invisible to the budget.
- [later] Revisit tip_share (0.5 at p7, 0.7 from p8). Bundle tips took about 57% of bundle-win gross. — 337,744 of 596,034 bundle gross went to tips; the 18 bundle wins netted only about 9.3k lamports each.
## OPEN Q
- Can the PumpSwap user_volume_accumulator (BKPfj2Ht…, 1,346,200 lamports, owner pAMMBay6…, created by p6#69) be closed to recover its rent, and is it really that PDA? I did not derive the PDA.
- p11-p14 were not reconciled on chain. Their numbers come from the live status and supervisor lines read at 21:00 UTC, and p14 was still running.
- The local src matched the binary built at 20:27 (used by p10-p11), but the binary was rebuilt at 20:54:47 UTC for p12+. Does the uncommitted src still match what is deployed?
- Is the bundle-only net of +164,236 lamports over about 57 minutes (18 wins, about $0.02) a stable edge or noise? The sample is too small to say.
- Should the USDC and other repeatedly traded accounts be kept open, trading rent lock-up for avoiding re-creation? That depends on how often each mint recurs.