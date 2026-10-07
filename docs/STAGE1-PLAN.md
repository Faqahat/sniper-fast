# arbx Stage 1 plan: raising the win ratio

**Date:** 2026-10-05, revised after an adversarial review (`docs/reviews/STAGE1-PLAN-review.md`; "Fn" = its findings). Nothing was built, signed or sent. Sources in brackets, key in the appendix; "(est.)" marks my estimates; USD at $145/SOL [FT].

> **What to expect** (estimates)
> - **Win ratio = wins ÷ bundles sent.** Old bot 0.29–0.56%; after Stage 0 about 0.35–0.9%. **Stage 1 target: about 0.5–2%, with wins per day no lower than in Stage 0;** stretch 3%, only if the send-delay test (X2) or the conflict filter delivers.
> - **Money stays small:** about 0–0.002 SOL/h net ($0–7 a day). Gaps our speed can reach earn rivals about 0.031–0.035 SOL/h gross; without new token accounts we reach about 0.001 SOL/h of it.
> - **What moves the ratio most:** create+close (up to ×1.4, the best evidence; also most of the money), the send-delay test X2 (×0.8–3, direction unknown) and a smaller-size arm (×1–2, unproven); skipping trades already lost adds about ×1.2.
> - **What you will see:** Solscan shows about 100% "succeeded" from day one of Stage 0, because failing bundles never land: that is not more winning. Telegram's daily line, "win ratio = wins ÷ bundles sent", comes with wins, sends and net SOL from chain data.
> - **Needs the $500 stage:** arbx-exec (0.35–1 SOL rent), on-chain sizing (WP-17), tips paid inside our program (X7). **Needs a second Haan token or provider:** discovery (WP-14, X8). **Needs paid capacity or your waiver:** exec coverage for the Stage-0 exit and the census X1 (OD-1).
> - **When:** about 4–6 weeks to the Stage-1 decision memo.

## 1. What "win ratio" means

| Form | Definition | Old bot |
|---|---|---|
| A. Explorer success | succeeded ÷ landed wallet transactions | 24 of 1,010 [W §2]; 33 of 1,000 [S §2] |
| B. **Wins per bundle sent** (headline) | wins ÷ bundles sent (`t_sent > 0`, `ok`) [M §6.2] | 0.29–0.56% (§2) |
| C. Per clean opportunity | wins ÷ decisions clearing min_profit on real state | never measured |
| D. Absolute | wins per day; net SOL from the chain ledger | 6.3 wins/h [W]; +0.00005 SOL/h before rent [R §1] |

- **B rises whenever we send less,** so a gain counts only if wins per day hold.
- **A is ≈100% from Stage 0 by construction:** failing bundles never land, and a landed one clears its on-chain min_profit [R05]. "Succeeded" is not "profitable": all 22 old landed bundles succeeded [D §1], yet 12 of W's 23 wins lost SOL to rent [W §3].
- **On Solscan** a win shows native SOL down (fee, tip) and WSOL up by more; the sum is the profit, and from Stage 0 a negative sum is a defect. FT-003's account creations show "succeeded" but are not wins; WP-19 tests via unprotected services show "failed" by design.
- **Telegram** (WP-20, in progress) must label the daily ratio "win ratio = wins ÷ bundles sent", count only live bundles sent (no would-sends, no attempt-counter fallback as in the lane code), and always show wins, sends and net SOL from WP-07's chain ledger.
- `getSignaturesForAddress` sees landed transactions only: never a land rate from it [D §4.13], only a wallet-completeness check [PL §6].

## 2. Baselines, Stage 0, limits

**Old bot B: 0.29–0.56%:** 22 of 7,538 [D §1], 23 of 7,643 [W §1, R §3.4], 28 of 5,038 in w5h, the size bands' window [P]. Windows hours apart differ ×2, so only concurrent control arms attribute a change.

**Stage 0 raises B about ×1.1–1.6 (est.), to 0.35–0.9%,** not the earlier ×2.3. Skipping crowded ≥100k bundles (0 of 1,896 landed) [deploy/arbx-stage0.toml] and ≥1M bundles (0 of 1,869) [R §1] costs no wins. But the removed decisions held 44 gaps taken late enough to win, against 58 kept [C §3] (about ×1.3), and 12 of 23 old bundle wins created a token account [W §3, D §4.5] (×1.1 without those mints, up to ×1.6 with create+close).

**Limits.** At today's speed (bundles land ~79 ms after sending [RS §5]) we reach only gaps a rival took ≥80 ms after our decision: 105 clean opportunities quoting 0.080 SOL per 28 min [C §3, S §4]. Rivals netted about 0.013 SOL/h there after tips (a lower bound), about 0.031–0.035 SOL/h gross ($4.5–5/h) [F5]; Stage-0 rules without new accounts reach about 0.001 SOL/h [C §3]. One 28-minute window, old pool set. Order-flow backruns (41% of big-win SOL) stay out of reach [RS §1].

| Measure | Old bot | After Stage 0 (est.) | Stage 1 target (est.) | Ceiling |
|---|---|---|---|---|
| B | 0.29–0.56% | 0.35–0.9% | 0.5–2%, stretch 3% | 19% (58 of 312 kept would-sends late-taken) [C §3] |
| C | not measured | measure | measure | 16% by count (105/655), 1.8% by value (0.080/4.43 SOL) [C §3] |
| Wins per day | ≈150 [W] | measure | ≥ Stage 0 | — |
| Net | +0.00005 SOL/h before rent | 0–0.002 SOL/h [R §1] | ≥0 over 48 h; 0–0.002 SOL/h | rivals' gross ≈0.031–0.035 SOL/h |

Real money waits for Stage 2 (Track A ≈0.05 SOL/h; ~40% chance neither track breaks even) [R §1].

## 3. Stage 1 levers

### 3.1 By effect on B

| Lever | B (est.) | Wins, money (est.) | Test vs a control; build ($0 unless noted) |
|---|---|---|---|
| Create+close (WP-06), live after your rule change | ×1.0–1.4, best evidence | wins ×1.5–2.1; most money | arm vs held-only; X6 ≥99% fit |
| Send delay X2 (WP-11), live | ×0.8–3, sign unknown | follow B | 4 arms × ≥400, confirmed on landings; 2 d |
| Size cap 0.05 SOL vs bankroll (WP-11 arm), live | ×1–2, unproven | smaller wins | ≈1,300–3,700 per arm (est.) |
| Conflict filter 1a, skip-only, live after checks | ≈×1.2 at best | wins must hold; net 0 | replay, flag-only, skip arm; 1–2 d |
| Tip share X4, 0.35 vs 0.7, live | ×0.8–1.1 | +120% per win | ≥1,000 per arm |
| Multi-region Jito X10 (WP-18), live | ×1.0–1.1 | small | ≥400 per arm; 1.5–2 d |
| Protected senders X11 (WP-19), after revert test | ×1.0–1.05 | small [S §4] | ≥400 per arm; 2–3 d; ≤0.00075 SOL per service |
| BAM X5: Stage-0 effect, action if it fails | ×1.0–1.4 | parity ≈+41% wins [W §6, RS §4] | ≈85 landings |
| Seed refresh; long tail (X1, WP-14/X8) | unknown | out of reach at frz's size; WP-14 only records [PL WP-14] | X1 5–7 d; OD-1, second Haan token |
| Speculative verifier 1b: not Stage 1 | — | — | X9 p99 ≤3 ms, ≥99.5% replay agreement; within Stage 2B's 20–30 d [R §4] |

### 3.2 Notes

**The verifier lever, split** [F1].
- **1a, conflict filter:** skip our send if a transaction seen in shreds writes one of our route's pools after our decision's state. The closer was in our shreds before our send in 506 of 807 old direct-arm failures [W §4] and 115 of 147 big gaps [RS §5], populations Stage 0 largely removes; a perfect filter would drop ≈17% of arbx's cmp2 sends (≈×1.2) [F1] and earn nothing, since those misses were free.
  - **Offline first** on FT-001/FT-005 replay (needs the WP-09 fix), judged by R4 closers in block order, not "any writer": user swaps often leave the gap open, and failed transactions close nothing (26.5% of decoded triggers failed [C §3]). Falsified if it catches <20% of losing sends or skips >10% of wins.
  - **Then flag-only** on live sends (`would_skip` recorded, nothing skipped); a skip arm starts only if the 95% upper bound on flagged wins is ≤10% (0 of ≥30, 1 of ≥46, 2 of ≥61).
- **1b, speculative verifier:** simulating those not-yet-committed transactions in a local Solana runtime is R §3.2 item 5 ("Track B only"), beyond PL's WP-13 ("never on the hot path in Stage 1"). It needs every account they touch, their programs and lookup tables, plus X9 p99 ≤3 ms and ≥99.5% replay agreement [R §3.2]. A scope change for your approval, started only if 1a shows value.
- **Safety:** skipping is not front-running. We only decline to send our own transaction; shred-seen transactions are already ordered in the leader's block. The bot never copies, reorders or places anything ahead of a user, and a bundle holds only our transaction [PL §2 invariant 1]. Invariant 3 gains one line: a shred hint may veto a send, never create, resize or reorder one.

**X2.** If Jito simulates before the trigger's state reaches it, added delay converts would-fails (adopt the best delay); if would-fail falls as delay is removed, speed matters [PL WP-11]. Accepted is not landed (146 against 17 [M §6.2]), so landings must confirm a gain.

**Size arm** [F18]. Bundles under 0.05 SOL won 1.44% (21 of 1,463) against 0.09% at 0.2–1 SOL [P item 8], but those were small gaps, and failed direct round trips ran p50 −150 bps: gaps closed, not shrank [D §4.2]. A randomized cap tests it live and free; FT-005 and all other arms run at the bankroll cap.

**Create+close** [F4]. frz holds only WSOL and USDC token accounts [RPC], so under go-live item 2, "no new token accounts while trading" [A], it can trade only USDC routes and FT-003's mints. USDC routes carried 6 of the 23 old bundle wins (20% of net); the 12 account-creating wins carried 71% (115,671 of 163,187 lamports before rent; my sums over W §3), at about 4 new mints an hour [W §3]. B: ≈×1.4, the step from Stage 0's ×1.1 to ×1.6, if new-mint trades keep W's share of wins (12 of 23) while adding 145 decisions to arbx's 312; flat by cmp2's late-taken counts (29 of 145 against 58 of 312) [C §3]. WP-06 builds it as one rent-neutral transaction; a failing close fails the bundle, free [PL WP-06]. Gates: X6, your amendment of item 2, and a recorded refusal reason measuring the rule's cost. FT-003 becomes required.

**BAM** [F13]. BAM leaders got 3 of 23 wins on a 38.1% slot share [W §6]. WP-05 (committed) dropped the durable nonce, one untested explanation [R §3.6]; X5 checks it in the Stage-0 baseline. If X5 fails: route BAM slots through X10's leader-nearest region or WP-19's services; if neither helps, rank BAM slots last in the Jito queue, where the 5/s limit dropped 13% of attempts [A WP-18].

### 3.3 By money at frz's bankroll

frz's cap is ≈0.32 SOL a trade (85% of 0.414 SOL liquid, minus 0.03), ≈0.19 SOL without wrapping more [A, FT]. All 23 old bundle wins were 0.0026–0.234 SOL [W §1], so the cap removes almost nothing we won. Ranked (est.):
1. **Create+close:** ≈+0.00003 SOL/h on the old record ($0.11/day) [W §3]; ceiling ≈0.005–0.013 SOL/h (the rule removed 57% of late-taken value [C §3]; we keep 30–65% of gross after tip and fees [F5]).
2. **X4 at 0.35:** ≈+0.00005 SOL/h ($0.19/day). Tips took 58% of the old wins' gross and fees 17%; at 0.35, W's net goes 163,187 → 358,341 lamports (my sums over W §2–3).
3. **X2, the size arm, X5, X10, X11:** in proportion to extra wins, on ≈0.00005 SOL/h. The conflict filter: 0. The slow slice and WP-17: out of reach before $500 (median trade 2.5 SOL [P]).

## 4. How each lever is judged

- **Every lever runs against a concurrent, randomized control arm** (WP-11 assigns by hash) at one size regime; no before-and-after.
- **Tests, not point estimates,** with the rule written in the FT entry before the run [FT].
- **Toolkit fixes first** (WP-10 follow-up; the X2 rule goes into PL WP-11):
  - **X2 direction bug:** `r10_experiments.py` tests "decreasing" over delay *added*, but PL WP-11 and R §5 go when would-fail falls per 10 ms *removed*; M §6.4 R10 says only "falls". Fix both: a two-sided trend test with the slope's 95% interval; ≥400 sends per arm, bands balanced [PL WP-11]. **Done (WP-11, 2026-10-07):** `r10_experiments.py`'s X2 is two-sided with the slope's interval (`go_speed`, `go_delay`); MEASUREMENT §6.4 R10 says so.
  - **X4:** we lost on state, not in the auction (0 lost-auction verdicts in 3,858 [RC C1]). Adopt 0.35 unless its arm shows lost-auction verdicts or fewer wins per send (one-sided p < 0.05, ≥1,000 per arm); a 20% land-rate test needs ≈27,600 per arm [F7].
  - **X5:** a one-sided test of the BAM/Jito landing ratio against 0.5 at ≈85 landings (80% power) [F7]; r10's 200 attempts give ≈2 landings.
  - **X10, X11:** acceptance, verdict mix, send→ack time; landing criteria see ≈4 landings per arm.

**What concludes, and when** (est., at 300–700 sends/h; cmp2 suggests ≤670/h [C §3]; FT-005 measures it). Live arms cost about nothing, so time, not the $5, is the limit.

| Question | Sample | Live time |
|---|---|---|
| X2 | 1,600 sends | 2–5 h |
| X4, X10, X11 | 800–2,000 sends | 1–7 h each |
| Filter flag-only gate | ≥30 wins | 5–27 h |
| B ×2 vs control (0.6% → 1.2%) | ≈3,100 per arm | 9–20 h |
| B ×1.5 vs control (0.6% → 0.9%) | ≈10,200 per arm | 29–68 h |
| X5 | ≈85 landings | 14–77 h |
| Smaller B effects; any net SOL/h effect; X4/X10 landing effects | — | not in Stage 1 |

B tests: one-sided, α 0.05, 80% power (two-sided: +27%).

## 5. Sequencing and calendar

**Status:** WP-05 committed (6760f10); WP-16 and WP-09 being fixed on lanes (WP-09's review: "do not merge as is"; `pools.json` breaks the toolkit's blockctx); WP-07 and WP-20 in progress; WP-06 next.

1. **Finish Stage 0:** WP-16/WP-09 fixes, WP-07, WP-20, WP-06 (3 d); toolkit fixes (§4). $0.
2. **Seed refresh** with pooldisco; you confirm the list (OD-4). $0.
3. **Field tests** [FT], the first spending: FT-001 soak, FT-002 dry run, FT-003 wallet prep, FT-004 first live hour, FT-005 24 h at the bankroll cap (canary count above 100, or live under the floor). ≤15.3M lamports; go-live gate [A].
4. **Stage-0 exit** [PL §6]: ≥99% exec coverage on every venue needs OD-1 capacity or your written waiver.
5. **Offline on FT records:** filter 1a, X3, X6 (WP-12, 3 d), X5, R12. $0; needs the WP-09 fix.
6. **Builds:** WP-11 (2 d; X2, size, X4, margin and filter arms), 1a (1–2 d), WP-18 (1.5–2 d), WP-19 (2–3 d); WP-13 offline alongside (8–12 d; needs WP-06 [PL §3.1]). $0.
7. **Live arms:** create+close, X2, filter (flag-only, then skip), size, X4, X10; then WP-19 step 4. ≈$0, each run under its own WP-07 floor.
8. **WP-19 step 3** from frz, the only planned Stage-1 spend: ≥30 built-to-fail routes per service; keys and your approval; outside the gate windows (§6). ≤2.25M.
9. **If bought:** WP-14 with X8 (second Haan token or provider); X1 census, 5–7 d (OD-1).
10. **After $500:** you deploy arbx-exec (0.35–1 SOL rent) → WP-15 → WP-17 SHADOW (needs X3's go), sized only after ≥300 exact landed routes per kind [DESIGN §6.6]; X7; X12.
11. **Exit:** memo with go/no-go per experiment; kill if X1 <0.2 SOL/h and X2 and X3 both fail [PL §6].

**pooldisco** ranks tokens by gaps, gap life and competing bots; the seed list dates from 2026-10-03, and tokens flare for 2–3 segments [P item 4]. On Cherry it runs only as a compiled binary (build artifacts only [FT]) and only while arbx and arb-lab are stopped [A I-3]: its gRPC mode takes a Haan stream, granted to the first process only.

**Calendar (est.): about 4–6 weeks.** Stage 0 needs 1–2 more weeks: WP-06 (3 d), WP-07 (3.5 d) [PL §3.1], lane fixes, reviews, FT-001 to FT-005 with a 24 h canary. Stage-1 builds take 10–14 engineer-days in sequence, with WP-14 if bought [PL §3.1, A]; the arms need several days of sending, X1 5–7 days. R's "about two weeks" [R §4] assumed Stage 0 done and the old bot's 2,090 sends/h.

## 6. Budget, stops and your decisions

**Starting equity ≈576,000,000 lamports, total-equity basis:** native 222,956,693 + WSOL 191,524,924 + rent 2,976,880 + 22.97 USDC (≈158M) [RPC slot 453,433,470; M §4.42]. BUDGET.md's ≈414M omits USDC and rent; a floor typed from it would sit ≈0.16 SOL too low.
- WP-07 computes each floor in-process from its own start snapshot minus **that test's allotment**; the hourly cap (OD-11, 0.02 SOL) is looser.
- Stops use the ledger's cumulative change, which excludes USDC revaluation; a 5% SOL move shifts the USDC by ≈0.0075 SOL, 22% of the cap [F6].
- Held accounts lock 1,488,440 (SPL) or 1,513,840 (Token-2022) lamports each, recoverable [RPC]; 40 lock ≈0.06 SOL, 14% of liquid equity.

**Allotments (lamports):** FT-003 fees ≤300,000 (est., ≈5,000 per transaction); FT-004 ≤5,000,000; FT-005 ≤10,000,000; WP-19 step 3 (three services) ≤2,250,000; each Stage-1 live run 1,000,000 as a protective floor (expected ≈0). Total 17,550,000 plus 1M per run (target ≤21M; cap 34M). WP-19 step 3 is not X12, and runs outside the Stage-0-exit window (24 h, "0 non-bundle copies") and the $500 window (48 h, "0 non-bundle sends") [PL §6, A].

**X12 does not fit the $5:** the full race costs ≈0.4 SOL [FT], so the cap buys ~100 rounds against ~400 needed per arm [S §5]. It runs only from a test wallet you top up (≈0.2 SOL [S §5]; hard stop 0.15 SOL [A]) and may not finish under that stop (S: 0.056–0.38 SOL).

**Your decisions** (cost; "outside" = outside the $5):
1. Allow rent-neutral create+close while trading (0), before its arm.
2. Held-set size N for FT-003 (≈0.0015 SOL each, recoverable).
3. Confirm the seed list (OD-4); keep the USDC at a fixed mark or move it out (0), before FT-004.
4. Exec coverage: OD-1 capacity (outside: paid) or a written waiver, for the Stage-0 exit.
5. A second Haan token or provider (outside: paid), for WP-14.
6. WP-19 keys and the step-3 test (≤0.00075 SOL per service; outside: NextBlock $249+/month, Astralane VIP [A]).
7. The X12 test wallet (outside: ≈0.2 SOL).
8. The speculative verifier 1b, after 1a.
9. Your monthly fixed cost C, which sets X1's break-even [R §6].
10. $500 and the arbx-exec deploy (outside: 0.35–1 SOL, back only if the program is closed), after 48 h live [A].

## 7. Not supported by evidence

- No live arbx run exists; arbx figures come from cmp2's offline replay of one 28-minute window [C §3].
- Unmeasured: arbx's send rate, the filter's false-skip rate, X2's direction, why BAM under-lands, whether smaller sizes win more.
- Unverified: Jito and BAM atomicity (from R05 and old-bot data); a per-region Jito limit; senders' revert protection [A]; whether simulating others' transactions fits 3 ms [F1].

## Appendix: sources and glossary

**Sources:** PL `docs/PLAN.md`; A `docs/PLAN-ADDENDUM.md`; M `docs/MEASUREMENT.md`; FT `docs/field-tests/`. In `docs/research/`: R `redesign-final.md`, W `wallet-synthesis.md`, C `cmp2-shadow-comparison.md`, RS `rival-synthesis.md`, P `PATTERNS.md`, S `sol-trade-sdk-audit.md`, D `docs-review-synthesis.md`, RC `res-compete.md`. R05 `docs/reviews/WP-05-review.md`; DESIGN `program/arbx-sizing/DESIGN.md`; RPC: the review's public-RPC reads; F1–F20: the review.

**Glossary.** *Bundle:* our transaction sent via Jito; it lands whole or not at all, so a miss is free. *Would-fail:* Jito's simulation rejects it. *Shred:* a piece of a block in flight. *BAM:* a Jito block-building variant (≈38% of slots). *Closer (R4):* the first transaction, in block order, after which our gap no longer pays.

## Inputs from the GLiCiNEn rival dossier (2026-10-06, docs/research/rival-GLiCiNEn.md)
- **X4 tip share:** add a 0.15–0.20 arm for gaps under ~50k lamports gross. GLiCiNEn lands about 1,360 arbitrages an hour paying about 15% of gross. At 15%, FT-004's 12 wins would have kept about 62,700 more lamports, if they still landed.
- **Size arm:** go well below 0.05 SOL. Its median trade is 0.00065 SOL against our median send of 0.056 SOL.
- **Coverage:**
  - 79% of its 438 pools in 218 trades are outside our list;
  - 58% of its routes have 3–4 legs, and 17% start and end in USDC;
  - it uses venues we lack (Whirlpool, Raydium CLMM, Tessera V).

  Discovery (WP-14), multi-leg and USDC routes, and new venues are the levers.
- **BAM (X5):** our BAM-targeted sends landed 2 of 170 (1.2%) against 10 of 245 (4.1%) on Jito leaders. Its plain bundles land on BAM in proportion to BAM's slots. Investigate our BAM submission path.
- **Direct competitors on our current gaps** are others: En3NPq8o, GgGap6ti, rLsi2DPw and MriyaNN8 moved first after our FT-004 triggers 22, 18, 14 and 8 times, against GLiCiNEn's 3.
