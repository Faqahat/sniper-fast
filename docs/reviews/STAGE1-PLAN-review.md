# Review: docs/STAGE1-PLAN.md (Stage 1 plan: raising the win ratio)

**Date:** 2026-10-05. **Reviewer:** adversarial review, read-only. This file is the only file written, and nothing was committed. No transaction was built, signed or sent, and no `.env`, key or keystore was read.

**Plan reviewed:** `docs/STAGE1-PLAN.md` (untracked, 186 lines, last written 01:26:23 UTC). "Lnn" means a line of that file.

**Checked against:**
- `docs/PLAN.md`: §1-§3, WP-05/06/07, WP-11 to WP-15, §6 and §9.
- `docs/PLAN-ADDENDUM.md`: WP-16 to WP-20, I-3, the go-live gate and the frz update.
- `docs/MEASUREMENT.md`: §4.40, §4.42, §6.2 and §6.4.
- `docs/research/`: W, C, RS, R, S, P, D and RC.
- Reviews: `docs/reviews/WP-05-review.md`, plus the lane reviews `WP-09-review.md` and `WP-16-review.md`.
- Field tests: `docs/field-tests/README.md`, `BUDGET.md` and `FT-000`.
- Code and config: `deploy/arbx-stage0.toml`; in `tools/arbx-report`, `r10_experiments.py`, `r11_census.py` and `stats.py`; `tools/pooldisco/src/main.rs`; `program/arbx-sizing/DESIGN.md`.

**Independent checks:**
- **Public RPC**, read-only, api.mainnet-beta.solana.com, slots 453,433,462 to 453,433,587:
  - frz's SOL and token accounts;
  - the PumpSwap volume accumulator, whose address I derived locally;
  - the current rent-exempt minimums.
- **The cmp2 band analysis, re-run read-only** on the scratch data that survives from the original session (`scratchpad/sts-audit/work/lanes/band.py` over `scratchpad/cmp2/work`), plus one extra script for the ≥80 ms band (`scratchpad/s1review/band80.py`).
- **Every sample size and power figure, recomputed** (`scratchpad/s1review/stats_check.py`).

## Verdict

**The caveats are honest, the numbers are optimistic, and the plan is not yet an actionable schedule.**
- **Honest.** It says that B (wins per bundle sent) rises mainly because we stop sending losers, which already cost nothing. It says absolute profit cannot rise much in Stage 1, and it lists what is unmeasured.
- **Optimistic.** Three of the figures behind "about tenfold" fail against their own sources:
  - the ×2.3 from the Stage-0 rules (F2);
  - the 0.013 SOL/h ceiling, which is a net figure presented as gross (F5);
  - the lever count toward ≥3% (F3).
  
  The #1 lever cannot change a single send in Stage 1 under PLAN WP-13 (F1).
- **Not yet actionable.**
  - The lever with the best evidence, rent-neutral create+close, is missing from both the ranking and the schedule (F4).
  - The equity floor would be computed on the wrong basis (F6).
  - Several steps depend on purchases, owner exceptions or blocked work packages that the plan treats as free or done (F9, F10).

**A promise the evidence supports.** After the fixes:
- B of about 0.5-2% (est.), with wins per day no lower than in Stage 0;
- a stretch target of 3% only if X2 or a live conflict filter delivers;
- net of about 0-0.002 SOL/h, which is about $0-7 a day at $145/SOL;
- money beyond that waits for Stage 2.

The plan does not drift into front-running (F1, "Safety").

## Corrected numbers

| Plan says (where) | Correct figure | Evidence |
|---|---|---|
| The old bot won 0.29-0.30% of bundles sent (L15, L125) | **0.29-0.56% across windows**: 22/7,538 (DOC3 window), 23/7,643 (W window), 28/5,038 (w5h, the same window as the 1.44% size band) | D §1; R §3.4 (7,643 ≈ R's 2,090/h × W's 3.66 h, so the W window; that is my inference, since R does not name the window); P raw output (`our bundles size …` lines) |
| Stage-0 rules give B ×2.3 "if wins hold" (L53, L58, L184) | **×1.1-1.6 (est.)**; about ×1.3 by C's own late-taken counts | C §3 table: 44 late-taken decisions removed against 58 kept; D §4.5: 12 of 23 bundle wins created token accounts |
| B after Stage 0: 0.7-1.5% (L15, L58) | **About 0.35-0.9% (est.)** | follows from the row above |
| "≥3% … about 10× the old bot" (L16) | 5-10× the old bot; **×3.3-8.6** beyond the corrected Stage 0 | rows above |
| "Rivals realized about 0.013 SOL/h … before tips" (L17, L120, L128) | 0.012-0.014 SOL/h is the rivals' **net, after their tips and fees**, and a lower bound (20 of 65 takers). **Gross is about 0.031-0.035 SOL/h** (about $4.5-5/h). Under Stage-0 rules without new token accounts it is **about 0.001 SOL/h** | Re-run band analysis: ≥80 ms band, per 28 min, net 0.0058 and gross 0.0144 SOL. The fetched takers hold 88% of the band's quoted value. C §3's arbx-kept late decisions quote 0.002 SOL |
| A held token account locks about 2.04M (L177) | **1,488,440** (SPL, 165 B); **1,513,840** (Token-2022, 170 B) | `getMinimumBalanceForRentExemption`; frz's own WSOL and USDC accounts hold 1,488,440 each |
| X4 "+35-40% per win" (L80, L128) | **About +120% per win** on the W window's 23 wins (net 163,187 → 358,341), which is only about +0.00005 SOL/h | W §2-§3: tips were 58% of gross and fees 17% |
| X2 "400 per arm per band (PL)" (L162) | PL asks for ≥ 400 **per arm**, with bands balanced. The plan's trend test needs about 200-245 per arm at 90% power when would-fail is about 85% | PL WP-11; stats_check.py |
| X5 "30 landings (proposed)" (L164) | **About 85 landings** for 80% power to separate the old BAM ratio (0.24) from the 0.5 threshold. 30 landings give 36% power | stats_check.py |
| C ceiling "≈19% by count, ≈0.1% by value" (L126) | Those figures describe arbx's kept would-sends (58/312; 0.002/1.51 SOL). Over all clean opportunities: **16% by count (105/655), 1.8% by quoted value (0.080/4.43)** | C §3, S §4 |
| Starting equity ≈ 414,000,000 (BUDGET.md; FT README) | **About 576,000,000 on WP-07's total-equity basis**: add USDC 22.967379 at the mid (about 158M at $145/SOL) and 2,976,880 of recoverable rent | RPC, slot 453,433,470; M §4.42 |
| "22 of 22 landed bundles were profitable (D §1)" (L30) | 22 of 22 **succeeded**. They were profitable only before rent: 12 of the W window's 23 bundle wins showed a SOL **loss** on the explorer | D §1, D §4.5, W §3 |
| Step 1 "commit WP-05" (L139) | **Already committed**: 6760f10 at 01:26:49, 26 s after the plan was last written | `git log` |

## Numbers that check out

- **Old-bot baselines:**
  - 22/7,538 and 0.29% (D §1); 23 wins (W §1) of 7,643 (R §3.4);
  - 6.3 wins/h (23 in 3.66 h); +0.00005 SOL/h for the bundle arm excluding rent (R §1);
  - 24/1,010 and 33/1,000 (W §2, S §2);
  - 6,359/7,529 would-fail (D §4.1).
- **The cmp2 funnel:** 418 of ≤730 removed, 312 kept, 84 decisions quoting 35.10 SOL, 124/173 taken within 80 ms, ≤0.077 SOL removed that we could have won, and 98.85 of 104.6 SOL phantom or poisoned (C §1, §3). Also 0/1,896 crowded bundles ≥100k landed (`deploy/arbx-stage0.toml`).
- **Who closed the gap:** 506/807 = 62.7% (W §4; a population of landed **direct-arm** failures, see F1); 115/147 (RS §5).
- **Size and crowding:** 21/1,463 = 1.44%, 0.39%, 0.09% and 0/901 (P item 8 and raw output); 0.9%, 0.4% and 49% (P item 10; see F16).
- **Timing and landing:**
  - 15.3, 14.9 and 79 ms; 48/22/26% (RS §1, §5);
  - 3/23 wins on BAM against a 38.1% slot share; 18/23 exact (W);
  - BAM parity would add about 41% more wins.
- **Engine and toolkit facts:**
  - 603/3,779 = 16% uncoded errors (RC C1); 525/553 = 95% (RC C6, "partly");
  - 46,589 comparisons with 0 mismatches; 41 and 28 more pools (A; lane WP-16 review).
- **Market figures:**
  - 58.8% (R §3.6); 31% (P item 7); 3.74 of 4.43 SOL; 18 of 23;
  - 0.12-0.16 SOL/h (P); 13% (A WP-18); 1.3% (RS §4); 11.5 SOL/h and 41% (RS §1);
  - 132 opportunities quoting 2.27 SOL; 75 quoting 1.07 SOL; 0.02 SOL/h; 105 quoting 0.080 SOL (S §4; re-run);
  - 218/220 (RS §5); Track A ≈0.05 SOL/h (0.01-0.15) and a 40% chance (R §1).
- **Budget arithmetic:** 5M + 10M + 2.25M = 17.25M, within the 21M target and the 34M hard cap.
- **RPC facts:**
  - frz holds 22.967379 USDC;
  - the accumulator `CUiyUSbx4YkWDZ3gAapjSJ4WbxfAJLfEGF5JnmwapMLt` exists with 1,346,200 lamports, owner pAMM, 137 bytes. I derived it locally as the PDA of ["user_volume_accumulator", frz].
- **Config and toolkit:**
  - `[canary]` is count = 100, every_ms = 5000, size_sol = 0.01;
  - the X2 direction bug is real (F8);
  - X5's minimum is 200 attempts; R11 is a placeholder.
- **Statistics:**
  - 1% against 2% needs 1,826 per arm (one-sided α = 0.05, 80% power; 2,318 two-sided);
  - a 20% relative drop at 1% needs 27,570 per arm (35,001 two-sided);
  - 15 wins in 1,500 sends has a Wilson interval of 0.61-1.64%, so "±0.5 points" is fair.

## Findings

Severity is Major (would mislead the owner, or blocks the plan), Medium (must fix before the runs) or Minor.

### F1. Major: the #1 lever cannot raise B in Stage 1, and it is a scope change presented as WP-13

**Location:** L76, L89-92, L142, L147.

**Problem:**
1. **It is labelled "(WP-13, X9)", but WP-13 does not do this.**
   - PLAN WP-13 runs "our exact signed transaction on a given account state". Its modes are `offline`, `shadow` ("live, beside sends … **no gating**") and `gate` ("Stage 2A, persistent candidates only"), and "it is **never on the hot path in Stage 1**".
   - Executing other people's transactions seen in shreds is R §3.2 item 5, "Speculative state (**Track B only**)". R allows it only if X9 p99 ≤ 3 ms **and** replay shows at least 99.5% agreement between speculative and committed state.
   - The plan lists only the X9 gate and never says this extends WP-13 and the stage plan.
2. **As scheduled, it gates nothing.** Step 4 runs "WP-13 shadow". So its ×1.5-2.5 cannot count toward a Stage-1 target.
3. **Feasibility and effort are not accounted for.** Simulating a rival's transaction needs:
   - every account it touches, many of them outside our watched set, so they would have to be fetched by RPC, which cannot fit in 3 ms;
   - its program (for example MriyaNN8's 507 KB AN225ykG);
   - its lookup tables resolved (cmp2's arbx dropped 5,001 transactions as `alt_unknown`);
   - shred order and failure handling.

   The 8-12 d is WP-13's estimate for committed state only. R budgets speculative state inside Stage 2B (20-30 d).
4. **The evidence for the effect size comes from populations Stage 0 already removes.**
   - W's 506/807 counts landed **direct-arm** failures.
   - RS's 115/147 counts big gaps, which are now skipped (crowded pools, ≥100k) or throttled (≥1M).
   - In cmp2, 132 of 435 clean takers (30%) appeared before our decision. Applied to the 180 taken decisions among arbx's 312 kept, a perfect pre-send filter removes about 54 sends (17%), so **B ≈ ×1.2 (est.)**. That is near the plan's own 20% falsifier.
5. **It has no money effect** (the plan says "none"). It raises B only by not sending misses that are already free. That is the clearest case of B rising without profit.
6. **It starts first.** The plan starts 8-12 engineer-days now, before the free conflict analysis (step 2) that could falsify it.

**Safety.**
- Skipping is not front-running. Transactions seen in shreds are already sequenced in the leader's block, so they are not even pending.
- I found no text in the plan that orders anything ahead of a user transaction. Order-flow backruns (L117) are only mentioned as out of reach.
- PLAN invariant 3 ("price only committed … state") and R's "decoder guesses never become state" still need an explicit amendment: **hints may veto a send, never create, resize or reorder one.**

**Fix:** split the lever in two.
- **1a. Conflict filter.** A skip-only engine rule driven by decoded shreds, about 1-2 d.
  - Falsify it offline in step 2 using R4 **closers** in block order, not "any route writer", which also counts user swaps that leave the gap open.
  - Promote it to live by a written gate that includes the "> 10% of wins skipped" falsifier.
- **1b. Speculative verifier.** An owner-approved scope change to WP-13 and R §3.2.5, with both of R's gates and a real effort estimate. Start it only if 1a's analysis shows value.

Rank by the post-Stage-0 estimate.

### F2. Major: the Stage-0 B estimate contradicts its own source, and the baseline leaves out a window

**Location:** L15, L53, L56, L58, L184.

**Problem: the ×2.3 assumes the removed decisions held no wins.**
- ×2.3 is 730/312.
- **C's own table contradicts it.** The removed rows hold 44 decisions taken late enough to win (≥80 ms): 13 crowded, 29 no-new-account and 2 at ≥1M. The kept set holds 58. By that proxy the kept set holds 57% of the winnable decisions against 43% of all decisions, which gives **×1.3**.
- **By the old bot's actual wins:**
  - removing crowded ≥100k bundles (0/1,896 landed) and ≥1M bundles (0/1,869) costs nothing;
  - but **12 of the 23 bundle wins in the W window created a token account** (D §4.5).
  
  So the no-new-account rule removes about half of the old bot's winning trade types: ×1.1 if the held set misses those mints, up to ×1.6 if create+close covers them.
- **§8 reads the evidence backwards.** It says "only C's ≤0.077 SOL bound supports" the assumption. That bound is by value, while B is a count: by count, the bound shows 44 winnable decisions removed.

**Problem: "B nearer 1.44%" for small sizes is confounded.**
- The <0.05 SOL band held small **gaps**: expected p50 40k lamports, against 19.5M in the 1-4.3 SOL band (P raw output).
- Capping a contested large gap at 0.01 SOL does not make it uncontested. The plan's own counter-evidence applies: failed round trips ran p50 −150 bps (D §4.2).

**Problem: the baseline.** In the window the size bands come from (w5h), the old bot won 28 of 5,038 bundles, 0.56%.

**Fix:**
- State the old bot's B as 0.29-0.56% and name the windows.
- Replace ×2.3 with ×1.1-1.6, and say the result depends on held-set and create+close coverage (F4).
- Make "smaller sizes win more" a hypothesis that a test settles (F18), not a Stage-0 effect.

### F3. Major: the ≥3% target is not reachable with the levers that can act in Stage 1

**Location:** L16, L74-85, L122-128.

**Problem: what the target needs.** From 0.35-0.9%, reaching ≥3% needs a ×3.3-8.6 gain within Stage 1.

**What cannot act live in Stage 1:**
- **#1** is shadow-only (F1).
- **#3 has no Stage-1 action.** The nonce change is WP-05, which is Stage 0 and already committed. X5 only measures (F13).
- **#4's on-chain part needs all of:**
  - $500;
  - an arbx-exec deploy;
  - "SHADOW until ≥300 landed routes per kind" (DESIGN §6.6, where sized mode is labelled Stage 2). That takes weeks per kind at about 1% landing.
- **#6's WP-14 only records in Stage 1** (PL WP-14).
- **#9 and #10** only measure, or wait for $500.

**What can act live:**
- X2's best delay (×0.8-3, sign unknown);
- X4 (×0.8-1.1);
- X10 and X11 (each about ×1.1 at most);
- the seed refresh;
- create+close (F4).

So the target rests almost entirely on X2 coming out at its upper end. The "wins/h ≥ 1.3× Stage 0" target (L127) has no source.

**Fix:**
- State the target as a range with odds: for example, "B 0.5-2% (est.), stretch 3% if X2 or a live conflict filter delivers".
- Keep "wins per day not lower than Stage 0" as a joint condition.
- Give the source of 1.3×, or drop it.

### F4. Major: missing lever: rent-neutral create+close (and held-set coverage)

**Location:** L55, L87; the sequence (L136-145) has no step for it.

**Evidence:**
- 12 of the 23 bundle wins in the W window created token accounts, on 12 distinct mints in 2.99 h (W §3; D §4.5).
- In cmp2, the no-new-account rule removed 29 late-taken decisions quoting 0.045 SOL. That is 57% of all late-taken value in the window (0.079 SOL; C §3), so it is the same block that sets the ceiling in F5.
- frz holds only a WSOL and a USDC token account (RPC, slot 453,433,470). Under the go-live rule "No new token accounts while trading" (A, gate item 2), it can trade only USDC routes and whatever FT-003 pre-creates.
- Old wins hit about 4 new mints per hour, so a static top-N set will miss most of them (inference).
- WP-06 already builds create+close. A failing close fails the whole bundle, which costs nothing.

**Fix:**
- Add "enable WP-06 create+close in live" as an explicit early Stage-1 step:
  - its gate is X6 (≥99% of transactions fit in 1,232 bytes) and an owner decision amending the go-live rule for rent-neutral transactions;
  - record refusals for lack of a held account as a decision reason, so the cost of the rule is measured.
- Rank it first by both B and net (est.).
- FT-003 is required, not "if needed".

### F5. Major: the headline money ceiling is net presented as gross, and Stage-0 rules exclude most of it

**Location:** L17, L120, L128.

**Evidence:** re-running the cmp2 band analysis on the surviving data.
- The ≥80 ms band holds 105 opportunities and 65 distinct takers.
- Only 20 takers were fetched, but they hold 88% of the band's quoted value.
- Their net take (after their own tips and fees) was 0.0058 SOL per 28 min. That is S §4's "0.006", and S printed the column as a lower bound for the other bands.
- Their gross take was 0.0144 SOL, which is C's "26% of our quote".

**Problem:**
- **The 0.013 SOL/h is the rivals' net, not "gross before tips".**
  - Gross is 0.031 SOL/h for the fetched takers, or about 0.035 SOL/h scaled by quote. That is about $4.5-5/h at $145/SOL, if we took all of it.
  - After our own tip (0.7 or 0.35) and fees, we would keep about 30-65% of that.
- **Under Stage-0 rules the kept late decisions quoted only 0.002 SOL per 28 min**, about 0.001 SOL/h gross. The rest sat behind the no-new-account rule (F4) or the crowded-pool skip.
- The whole figure comes from one 28-minute window and the old bot's pool set.

**Fix:**
- Replace the figure with "rivals' gross ≈0.03 SOL/h in one 28-min window; under Stage-0 rules without create+close ≈0.001 SOL/h".
- Give both in USD.

### F6. Major: the equity floor's basis, and USDC price risk

**Location:** L132, L179; FT README "Wallet and budget"; BUDGET.md "Starting wallet".

**Evidence:**
- BUDGET.md's start, ≈414,000,000, is native SOL plus WSOL only.
- WP-07 and M §4.42 say stops and budgets use **total** equity: liquid SOL, plus other tokens at the pool mid, plus recoverable rent.
- RPC (slots 453,433,462-470) shows:
  - native 222,956,693;
  - WSOL 191,524,924;
  - USDC 22.967379;
  - 1,488,440 of rent in each of the two token accounts.
- So total equity at the start is about 414.48M + 2.98M + about 158M of USDC (at $145/SOL; about 192M at $119.7), **≈576M**.

**Problem:**
- **A floor typed in as 414M minus the remaining budget would sit about 0.16 SOL (≈4.8× the hard cap) too low**, so it would trip far too late.
- **USDC valued at the mid moves with SOL.**
  - A 5% rise in SOL lowers equity by about 0.0075 SOL, 22% of the cap, with no trading at all.
  - A fall in SOL hides real losses.
- The plan flags the USDC, but not the rent and not the price movement.

**Fix:**
- WP-07 computes the floor in-process from its own total-equity snapshot at campaign start, minus the remaining budget. Nobody types it in from BUDGET.md.
- Make the stop metric independent of the SOL price. Two ways:
  - the cumulative ledger categories since the start, which exclude `inventory_reval` by definition;
  - or USDC held at a fixed mark from the start of the campaign.
- Restate BUDGET.md's start on the same basis. Or the owner moves the USDC out of frz.

### F7. Medium: experiments that cannot conclude as designed

**Location:** L159-166, L170-171; the X10 and X11 rows (L82-83).

**X4.**
- The plan is right that a 20% relative drop in landing at 1% needs about 27,600 per arm. That is 55,000+ sends in the under-100k scope: days to weeks at an unknown arbx send rate. cmp2 suggests ≤ 670/h, and the canary's pacing allows ≤ 720/h.
- The proposed "2,000 per arm for net" gives about 20 wins per arm. With the old wins' spread (coefficient of variation 1.9), each arm's mean net per win has a 95% interval of about ±85%.
- No decision rule is attached.
- `r10_experiments.x4` decides "go" on point estimates, with no test.
- **Fix:** decide X4 on the mechanism: the share of Jito "lost-auction" verdicts per arm. It was 0 of 3,858 in RC C1, and the old-bot data show we lose on state, not on the auction. Add a non-inferiority bound, or adopt 0.35 with a guardrail.

**X10 (WP-18) and X11 (WP-19 step 4).** Their landing criteria ("≥ 20% relative" at 400 per arm) mean about 4 landings per arm, so they are equally unreachable. **Fix:** use acceptance, the verdict mix and send-to-acknowledgement time instead.

**X5.** 30 landings give 36% power. About 85 landings, roughly 8,500 sends at 1%, are needed for 80%. r10's go is a point ratio.

**Before and after.** The old bot's B moved from 0.56% to 0.30% between windows a few hours apart. So comparing Stage 0 with Stage 1 cannot attribute a gain. **Fix:** judge each lever against a concurrent randomized control arm. WP-11 already assigns arms by hash.

**Durations.**
- State that the 1,826-per-arm figure is one-sided.
- Give expected durations once FT-005 has measured arbx's real send rate.

### F8. Medium: X2's minimum is cited wrongly, and the tool fix covers only half of the problem

**Location:** L96, L162, L170.

**Verified.** `r10_experiments.x2` calls `cochran_armitage(…, "decreasing")`. That means "the proportion falls as the score rises" (stats.py:173-174). Its go is a slope ≤ −0.05 per 10 ms of delay **added**. PL WP-11 and R §5 go when would-fail falls per 10 ms **removed**. The plan's claim is correct.

**But:**
- **The root cause is the specification.** MEASUREMENT §6.4 R10 says only "go if it falls ≥ 5 points per 10 ms". Fix the specification as well.
- **The new decision rule must be written down before the run** (FT protocol). "Falling as delay is added means adopt the best delay" is a new rule; write it into PL WP-11.
- **The minimum is mis-cited.** PL says "at least 400 attempts per arm", with bands balanced, not 400 per band.
- **The 540 needs its basis stated.** It matches a pairwise test of 0 ms against 20 ms at p ≈ 0.5, two-sided. The trend test the tool runs needs about 200-245 per arm.
- **X2 measures would-fail, not landing,** and "accepted" is not "landed" (R §3.4: 146 accepted, 17 landed). An X2 gain in B needs landings to confirm it.

### F9. Medium: sequencing: steps that are blocked, unpaid for or already done

**Location:** L136-153.

1. **WP-05 is already committed** (6760f10).
2. **WP-09 is "Do not merge as is"** (lane review):
   - `pools.json` breaks the toolkit's `blockctx`;
   - go-live item 3's replay cannot pass with WP-05's executor running in shadow.
   
   Step 2's conflict analysis and X1 both depend on R4 and `blockctx`.
3. **WP-14 (step 4) needs another Haan stream.** I-3 and the C addendum: one bot's three streams exhaust the token. So it needs a second token or provider (OD-1, R §6), which is an owner purchase, not "$0".
4. **pooldisco runs on Cherry,** with defaults `--env /root/arbx/deploy/.env` and `--out /root/arbx/runs/discovery`.
   - The owner rule (FT README, 2026-10-05) uploads only the arbx binary, its config and its data: "anything that must run on Cherry … becomes a subcommand". pooldisco needs an exception or a subcommand.
   - Only `--mode grpc` takes a Haan stream. The default `rpc` mode streams from RMR_RPC_URL and only needs HAAN_X_TOKEN to exist, so it need not stop arbx. FT-000 is running now.
5. **The Stage-0 exit is a different gate from go-live.** PL §6 requires ≥99% exec coverage on every venue "with no escape clause": OD-1 capacity (paid) or an owner waiver. Step 1 cites only the go-live gate. X1's coverage depends on the same capacity.
6. **WP-17 "then sized" will not happen in Stage 1.** It needs X3's go (A WP-17) and ≥300 landed routes per kind in SHADOW (DESIGN §6.6).
7. **WP-13 "starts now"** although PL §3.1 lists WP-06 as a dependency (F1).
8. **create+close has no step** (F4).
9. **There is no calendar.** By PL's efforts, the rest of Stage 0 is WP-16 and WP-09 fixes, WP-06 (3 d), WP-07 (3.5 d) and FT-001 to FT-005, including a 24 h canary. Then come the Stage-1 builds (about 11 d sequential, plus WP-13 in parallel) and X1's 5-7-day census. That puts the end of Stage 1 about **4-6 weeks** out (est.), against R's "about two weeks". The owner should get this date.

### F10. Medium: budget: scope and enforcement

**Location:** L84, L110, L143-144, L176.

1. **"WP-19 step 3 (= X12 arm C)" is not one test.**
   - X12 runs "from a dedicated test wallet" with an owner top-up (S §5; A).
   - S's arm C is "a self-transfer built to fail". WP-19 step 3 sends "routes built to fail our profit check".
   - **Fix:** choose. Either the route test runs from frz and is not X12, or arm C runs from the test wallet and sits outside frz's budget.
2. **Built-to-fail and protected-service sends from frz conflict with two gates** if they fall inside their windows:
   - the $500 gate's "0 non-bundle sends";
   - the Stage-0 exit's "0 non-bundle copies and 0 failed-landing fees".
3. **The allotments are not enforced.**
   - The floor allows the whole remaining budget (34M at first).
   - The hourly cap (OD-11) is 20M: 4× FT-004's 5M allotment and 2× FT-005's 10M. [canary] `max_spend_lamports` (3M) counts only failed landings, which a bundle cannot produce.
   - **Fix:** set each test's floor from its own allotment.
4. **A full X12 may not finish.** The plan says about 0.4 SOL in full (FT) and also a 0.15 SOL hard stop (A). S §5 expects 0.056-0.38 SOL. Say that the full run may not fit under its stop.
5. **Costs outside the $5 budget are not flagged:**
   - the second Haan token or provider (WP-14);
   - OD-1 capacity (Stage-0 exit, X1);
   - paid sender access for WP-19: NextBlock at $249+/month, and Astralane's VIP tier for revert protection;
   - arbx-exec rent of 0.35-1 SOL, locked while the program exists.
6. **FT-003's transaction fees** (about 5k lamports per transaction) have no allotment. This is small.

### F11. Medium: the ranking by net SOL/h uses relative gains on a base near zero, and ignores the bankroll

**Location:** L79, L81, L87, L105, L108.

**Problem:**
- **X4 ranks first by net, but the absolute gain is tiny.** It is a per-win percentage on a bundle arm that earned +0.00005 SOL/h. Even at the corrected +120% per win, that is about +0.00005 SOL/h ($0.007/h).
- **X5 ranks second but has no Stage-1 action** (F13).
- **#6's "0.02-0.1 SOL/h (P)" does not hold up:**
  - it is P's capture estimate, which RS §2 P6 marks "unsupported";
  - the slow slice's median trade is 2.5 SOL, while frz's bankroll cap is min(4.2, 0.85 × 0.414 − 0.03) ≈ 0.32 SOL, or about 0.19 SOL of WSOL without wrapping;
  - WP-14 does not trade in Stage 1.
- **#4's "+0-0.05 SOL/h at ≤4.2 SOL"** assumes the cap that comes after $500.

**Fix:** rank by absolute SOL/h at the Stage-1 bankroll, in SOL and USD.

### F12. Medium: what the owner will actually see on the explorer and in Telegram

**Location:** L14, L23-33, L124.

1. **"Profitable" should be "succeeded".** In the old bot, 12 of the W window's 23 bundle wins showed a SOL loss on the explorer: about 1.49-1.51M of rent each, against 9k-228k of gross. 16 of 31 w5h wins had wallet profit ≤ 0 (RS §2 P8). Stage 0 fixes this. Say so: "from Stage 0 every landed trade should show a positive SOL change on Solscan; one that does not is a defect".
2. **A ≈ 100% holds for Jito bundles** (R05: "a landed bundle cannot lose"). But the explorer also lists other transactions:
   - FT-003's account creations, wraps and transfers, all marked successful, none of them wins;
   - any WP-19 step-3 or X11 transaction that lands through an unprotected service, which shows as **failed** by design.
3. **The plan never mentions Telegram.** WP-20's daily summary reports a "win ratio per send". That is what the owner will read as the win ratio.
   - Pin it to B's definition: copies with `t_sent > 0` and `ok`, live sends only, with shadow and dry-run would-sends excluded.
   - Show wins per day and net SOL in the same message.
4. **"Never use getSignaturesForAddress" goes too far.** It is exactly the explorer's landed-only view (A). D §4.13's rule is "never compute a land rate from it", and the Stage-0 exit uses it to check wallet completeness.
5. **B is still the right headline, with one warning.** A is ≈100% by construction, and the owner's Telegram shows B. But B is gameable by sending less (F1), so tell the owner plainly: "Solscan will show about 100% from the first Stage-0 day; that is not more winning. Watch the Telegram daily ratio together with wins per day and SOL per day."

### F13. Medium: #3 (BAM) has no Stage-1 action

**Location:** L78, L97.

**Problem:**
- The change that may fix BAM's receipt of our bundles is WP-05's switch to a recent blockhash. That is Stage 0 and already committed.
- X5 only measures, so any BAM gain lands in the Stage-0 baseline.
- If X5 still fails, nothing is planned beyond "investigate" (R §5).

**Fix:** list it as a Stage-0 effect to verify. Add a concrete Stage-1 follow-up for the case where X5 fails, such as per-leader routing through X10 or X11.

### F14. Minor: the rent per held account is out of date

**Location:** L177; also A's "about 0.002 SOL each" (go-live gate item 2).

**Problem:** the rent-exempt minimum is now 1,488,440 lamports for SPL (165 B) and 1,513,840 for Token-2022 (170 B). frz's own accounts hold exactly 1,488,440. M §4.42's 2,039,280 is an older golden-example value.

**Fix:**
- Correct the figure.
- State the size of the held set N and its effect on liquidity. At N = 40, about 0.06 SOL (14% of frz) leaves the bankroll.

### F15. Minor: the C ceiling is attributed to the wrong population

**Location:** L126-127.

**Problem:**
- The ceiling figures describe arbx's kept would-sends. Over all clean opportunities it is 16% by count and 1.8% by quoted value.
- The target "C ×1.5-2" rests on #6, which does not trade in Stage 1.

### F16. Minor: weak evidence stated as fact

**Location:** L40, L91.

**Problem:**
- **"0.9% on pools with 5-20 bots"** is 3 wins in 338 pool-attempts, with a 95% interval of about 0.2-2.6%. The crowding table also counts each attempt once per pool.
- **The 62.7%** counts landed direct-arm failures. It is a different population from the bundles in Stage 1.

**Fix:** state the sample size or the population next to each figure.

### F17. Minor: internal inconsistencies

1. **Wins per hour.** The summary says the target "counts only if wins/h and net SOL/h hold" (L16), but the table asks for "≥1.3× Stage 0" (L127).
2. **Order.** "Free analyses, then free live arms, then the $5 tests" (L18), but step 1 spends first.
3. **Column mix-up.** #6's "C ×1.5-2" sits in the B column.
4. **Missing step.** WP-19 step 4 (the landing A/B) is not in the sequence.
5. **Missing condition.** Step 6's "WP-17 … then sized" omits the X3 condition (A WP-17).

### F18. Minor: the size regime makes FT-005's baseline incomparable

**Location:** L56, L63, L70.

**Problem:**
- FT-005 on the shipped canary trades at 0.01 SOL.
- The live arms trade at the bankroll cap, about 0.19-0.32 SOL.
- Because of the size gradient, B at one size is not a baseline for B at the other.

**Fix:**
- Fix one size regime for the baseline and the arms.
- Better, randomize the size cap as a WP-11 arm (for example 0.05 SOL against the bankroll). That is a free live test of the size hypothesis, which the plan currently leaves to offline X3 and to WP-17 after $500.

### F19. Minor: clarity for a non-engineer owner

**Location:** whole document.

**Problem:**
- **Jargon.** Terms appear without explanation: landed_ok, t_sent, torn_suspect, fork_priced, rung, R4, Wilson CI, CPI, SVM, shred, BAM, "×" multipliers.
- **Citation tags in every line.** Fourteen source tags make most lines hard to read.
- **No USD figures, and no calendar.**
- **Owner decisions are scattered.** They include:
  - keys;
  - the seed list;
  - the create+close rule;
  - the USDC;
  - a second Haan token;
  - OD-1;
  - the X12 wallet;
  - the $500;
  - the arbx-exec deploy.

**Fix:**
- Open with a five-line plain box: what you will see, what we expect, what it costs, and when.
- Add a list of decisions with their costs.
- Add a glossary.
- Move the citations to an appendix.

### F20. Minor: missing owner inputs

**Problem:**
- X1's go threshold, max(0.5 SOL/h, B/0.15), needs the owner's monthly fixed cost C (R §6). This break-even B is a SOL/h figure, not the plan's win ratio B.
- arbx-exec's rent comes back only if the program is closed.

**Fix:** add both items to the decision list.

## The nine checks, answered

1. **Numbers:** see the two tables above. The mismatches are in F2, F5, F7, F8, F14 and F15.
2. **Definitions of "win ratio":** A is right for the explorer once "profitable" becomes "succeeded" and non-trade transactions are separated. B matches WP-20's Telegram "win ratio per send" but must be pinned to it (F12).
3. **Targets:** optimistic. "About tenfold" relies on ×2.3 (really ×1.1-1.6), a confounded size effect and a shadow-only lever (F2, F3). The profit limits are stated, but the ceiling is mislabelled and has no USD figure (F5, F11).
4. **Lever ranking:**
   - #1 is a scope change beyond WP-13 and R's stage plan; it can only skip, so it is safe, but it cannot act in Stage 1 (F1);
   - #3 has no action (F13);
   - create+close is missing (F4);
   - the net ranking is relative (F11).
   
   There is no drift into front-running.
5. **Statistics:** X2 is well powered at PL's 400 per arm. X4, X5, X10 and X11 cannot conclude on their landing criteria, and before-and-after comparisons are confounded (F7, F8).
6. **Budget:** the arithmetic fits the 0.034 SOL cap with room to spare.
   - The floor's basis is wrong, with USDC, rent and price exposure (F6).
   - The allotments are not enforced, and the X12 wallet conflicts with the frz budget (F10).
   - Several costs fall outside the budget without being flagged (F10).
7. **Tool bugs:** both confirmed (X2 direction, F8; the 100-attempt canary in `deploy/arbx-stage0.toml` [canary]). The X4 and X5 go rules are point estimates too (F7).
8. **Sequencing:** see F9.
9. **Clarity:** see F19.

## Not verified

- **Jito and BAM bundle atomicity** is taken from R05 and the old-bot data, not from Jito's own documentation.
- **P's raw tables** could not be re-run, because arb-lab's scripts were removed from arbx. The figures come from PATTERNS.md as recorded.
- **The cmp2 re-run** relies on the earlier session's scratch files (`txinfo.json` holds 131 fetched transactions).
- **Infeasibility of simulating third-party transactions within 3 ms** is an inference from the account-set argument in F1, not a measurement.
- **WP-20 has no code yet** (lane-wp-20 has no `alerts.rs`), so the Telegram definition is checked only against the addendum.

## Disposition (2026-10-05, plan revised)

`docs/STAGE1-PLAN.md` was rewritten against every finding: 3,200 words (`wc -w`), opening with a "What to expect" box for the owner. Nothing was built, signed or sent; no `.env`, key or keystore was read. **Fixed** means changed as the review asks; **Fixed, differently** means addressed another way, with the reason; **Follow-up** means the change belongs in a file outside this commit.

| # | Severity | Disposition | Plan section |
|---|---|---|---|
| Numbers | — | **Fixed**: all thirteen rows of "Corrected numbers" applied (B 0.29–0.56% with windows named; Stage 0 ×1.1–1.6 to 0.35–0.9%; target 0.5–2%, stretch 3%; 0.013 SOL/h relabelled rivals' net, gross 0.031–0.035, ≈0.001 reachable without new accounts, with USD; rent 1,488,440 / 1,513,840; X4 +120% per win, +0.00005 SOL/h; X2 ≥400 per arm; X5 ≈85 landings; C ceiling 16% / 1.8%; equity ≈576M; "succeeded"; WP-05 committed) | box, §1–§3, §6 |
| F1 | Major | **Fixed**: split into 1a, a skip-only conflict filter (offline replay judged by R4 closers, then flag-only on live sends, then a skip arm behind a written gate with the >10%-of-wins falsifier as a 95% bound), and 1b, the speculative verifier as an owner-approved Track B scope change (X9 p99 ≤ 3 ms, ≥ 99.5% replay agreement, within Stage 2B's 20–30 d), started only if 1a shows value. Effect ≈×1.2 at best, net 0. Safety stated: skipping is not front-running, nothing is ordered ahead of a user; invariant-3 amendment proposed (a hint may veto a send, never create, resize or reorder one). WP-13 now follows WP-06 | §3.1, §3.2, §5 |
| F2 | Major | **Fixed**: three windows named; ×1.1–1.6 from both proxies (44 vs 58 late-taken; 12 of 23 wins created accounts); "smaller sizes win more" is a hypothesis tested by a live arm; the backwards reading in old §8 removed | §2, §3.2 |
| F3 | Major | **Fixed**: target 0.5–2% with wins per day ≥ Stage 0 as a joint condition; stretch 3% only if X2 or the filter delivers; the unsourced 1.3× dropped; the lever table says what acts live. Odds are not quantified; the stretch conditions are stated instead | box, §2, §3.1 |
| F4 | Major | **Fixed**: create+close is first by B and by money, gated on your amendment of go-live item 2, X6 and a recorded refusal reason; FT-003 required. Added: USDC routes carried 6 of 23 old wins (20% of net), the 12 account-creating wins 71% (my sums over W §3). B is given as ×1.0–1.4 because the two proxies disagree, and the plan says it is the same step as Stage 0's ×1.1 → ×1.6, so it is not counted twice | box, §3, §6 |
| F5 | Major | **Fixed**: rivals' net ≈0.013 SOL/h (lower bound), gross ≈0.031–0.035 SOL/h ($4.5–5/h), ≈0.001 SOL/h reachable without new accounts; one 28-minute window, old pool set | box, §2 |
| F6 | Major | **Fixed** in the plan: equity ≈576M with its parts; floors computed in-process by WP-07 from its own snapshot minus the test's allotment; a price-free stop (cumulative ledger change); the USDC is an owner decision. **Follow-up:** restate BUDGET.md's start on the same basis | §6 |
| F7 | Medium | **Fixed**: a concurrent randomized control arm for every lever; tests instead of point estimates; X4 decided on the lost-auction mechanism with a one-sided guardrail; X5 a one-sided test at ≈85 landings; X10/X11 on acceptance, verdict mix and ack time; a table of samples and live hours at 300–700 sends/h (est.; FT-005 measures the rate); one-sidedness stated; what cannot conclude in Stage 1 listed | §4 |
| F8 | Medium | **Fixed**: the direction fix is assigned to a WP-10 follow-up (r10 and M §6.4 R10: two-sided trend test with the slope's interval) and the decision rule to PL WP-11 before the run; ≥400 per arm, bands balanced; landings confirm a gain; the 540 dropped. **Follow-up:** those three edits | §3.2, §4 |
| F9 | Medium | **Fixed**, all nine items: current status (WP-09's "do not merge as is" blocks the offline work); WP-14 needs a second Haan token or provider; pooldisco only as a compiled binary and only while arbx and arb-lab are stopped (I-3), which the owner's build-artifact rule allows without an exception or subcommand; Stage-0 exit needs OD-1 or a written waiver; WP-17 sized only after $500, X3's go and ≥300 exact landed routes per kind; WP-13 after WP-06; a create+close step; a calendar of ≈4–6 weeks with its basis | §5 |
| F10 | Medium | **Fixed**: WP-19 step 3 runs from frz as a route test, not X12, outside the Stage-0-exit and $500 windows; X12 only from a dedicated wallet you top up (a pilot inside the $5 was rejected: the cap buys ~100 rounds against ~400 per arm), and it may not finish under its 0.15 SOL stop; per-test WP-07 floors enforce the allotments; FT-003 fees have an allotment; costs outside the $5 are flagged in the decision list | §6 |
| F11 | Medium | **Fixed**: a separate ranking by absolute SOL/h and USD at frz's 0.19–0.32 SOL cap; all 23 old bundle wins (0.0026–0.234 SOL) fit under it; the slow slice (median 2.5 SOL) and WP-17 are out of reach before $500 | §3.3 |
| F12 | Medium | **Fixed**: "succeeded" is not "profitable"; how a win reads on Solscan (native SOL falls by fee and tip, WSOL rises by more, the sum is the profit, per M §4.42's golden rows, refining the review's "positive SOL change"); wallet-prep and test transactions explained; Telegram pinned to "win ratio = wins ÷ bundles sent" with wins, sends and net SOL from the chain ledger and no attempt-counter fallback; the getSignaturesForAddress rule narrowed to "never a land rate" | box, §1 |
| F13 | Medium | **Fixed**: BAM is a Stage-0 effect that X5 verifies; if X5 fails, route BAM slots through X10's nearest region or WP-19's services, else rank them last in the Jito queue | §3.1, §3.2 |
| F14 | Minor | **Fixed**: 1,488,440 / 1,513,840; a held set of 40 locks ≈0.06 SOL (14% of liquid). **Follow-up:** the addendum's "about 0.002 SOL each" (go-live item 2) | §6 |
| F15 | Minor | **Fixed**: the C ceiling is over all clean opportunities; the 19% is labelled as kept would-sends; no C multiplier target | §2 |
| F16 | Minor | **Fixed**: the 3-of-338 crowding figure is no longer used; 506 of 807 is labelled as old direct-arm failures, a population Stage 0 largely removes | §3.2 |
| F17 | Minor | **Fixed**, all five: wins per day "≥ Stage 0"; spending order stated; C has its own row; WP-19 step 4 is in step 7; WP-17 needs X3's go | §2, §5 |
| F18 | Minor | **Fixed**: one size regime (FT-005 and all arms at the bankroll cap) and a randomized size-cap arm (0.05 SOL vs the bankroll cap) in WP-11 | §3.1, §3.2 |
| F19 | Minor | **Fixed, differently in part**: the box, a decision list with costs, a calendar, USD figures and a glossary were added. Citations stay as short inline tags, since every number must carry its source, with the key moved to an appendix | box, §6, appendix |
| F20 | Minor | **Fixed**: your monthly fixed cost C for X1's break-even, and arbx-exec rent returned only if the program is closed, are in the decision list | §6 |

**Checked while revising, beyond the review:**
- "146 accepted vs 17 landed" is in M §6.2 rule 5 and D, not R §3.4; the plan cites M §6.2.
- lane-wp-20 now holds uncommitted alert code: `daily_alert` prints wins ÷ sends, with sends falling back from `exec.sent_total` to `exec.attempts_total` (`src/alerts/summary.rs`). The "no code yet" note above is out of date.
- pooldisco's default `rpc` mode uses `RMR_RPC_URL` websockets and up to 12 getTransaction/s, while `deploy/arbx-stage0.toml` has its RMR endpoints disabled. "Only while stopped" is the owner's conservative rule, not a measured conflict; the plan cites I-3 for the gRPC mode only.
- Old-win sums over W §3: net before rent 163,187; account-creating wins 115,671 (71%); USDC-route wins 32,666 (20%); 12 distinct new mints in 2.99 h (≈4/h); at a 0.35 tip share, net 358,341 (+120%).
- Sample sizes recomputed (one-sided, 80% power): 0.6% → 1.2% needs ≈3,060 per arm, 0.6% → 0.9% ≈10,230. A false-skip rate ≤10% (one-sided 95% bound) needs 0 flagged wins in ≥29, 1 in ≥46 or 2 in ≥61.
- Stage-1 build days: 9.5–12 without WP-14, 11.5–14 with it; the plan says 10–14.

**Follow-ups outside this commit:** the X2 direction fix in `r10_experiments.py` and M §6.4 R10 (WP-10 follow-up) and its decision rule in PL WP-11; the PL invariant-3 amendment; BUDGET.md's start restated (≈576M, total basis); go-live item 2's rent figure and the owner's create+close decision; WP-20's ratio label and denominator (lane-wp-20).
