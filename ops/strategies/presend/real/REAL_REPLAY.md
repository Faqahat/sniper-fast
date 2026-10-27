# Pre-send REAL replay (agent, 10-25 PKT)

Owner OK 10-25 ~18:45 PKT. Read-only, offline, $0. Nothing sent, no server touched, no engine file changed, nothing committed.
MEASURED = probe records, the chain recording, or a replay run on them. INFERRED = my reading or a model step. Times PKT.
Section 0 (the pre-registration) was written 10-25 ~19:10 PKT, before any replay result. It is at the end, unchanged.
Results written 10-25 ~20:40 PKT.

## Verdict
- **Pre-registered answer: NO version is proven worth a live test.** My rule needed a passing calibration, and it
  missed 2 of its 3 marks:
  - P&L per probe is off by -0.016 SOL (probe 1) and +0.016 SOL (probe 2). The mark was +-0.01.
  - GvtdnDT8 comes out as a fill (p 0.86); live missed it. The other 3 misses come out right.
  - So, as pre-registered, the variant numbers below are "not reliable", even though all 27 variants pass their own rules.
- **Plain reading:**
  - The replay counts only fills we can really get, and it reproduces the two probes **together**:
    fills 33.2 vs 33, net -0.025 vs -0.026 SOL (MEASURED vs replay). The per-probe misses go in opposite directions.
  - On **76 unseen hours**, every pre-registered version is positive in both halves and beats random arming.
    **V0 = probe 2's own settings: +4.3 SOL/day** (halves +4.9 / +3.7; every day +3.3 to +5.0; random arming -0.8 at p95).
  - **Doubt 1, the big one: the edge is the buyers who come after us.** Drop 20% of later buys at random: V0 +1.0/day.
    Drop 30%: V0 -0.7/day. So the result stands or falls on the bot cohort (as V2_OPTIONS found).
  - **Doubt 2: live has only seen weak hours.** Both probes fell in hours the replay also calls weak (replay of those
    hours: probe 1 -0.023 SOL, probe 2 -0.002). 3 h and 33 fills in all, about 0 per fill live.
    In the replay, 87% of clock hours and 94% of 4-hour blocks are positive for V0.
- **My read (INFERRED, outside the pre-registered rule): one more probe-2 run of ~4 h is worth it, as a test of this
  replay, not as income.** It is the cheapest way to settle doubt 2, and the pass / fail below also settles doubt 1.
  Owner's call.
  - **Settings: probe 2 exactly as run** (flags only): whale >= 6%, 0.35 SOL, `--presend-live-k 8`, helius-ps 30/s
    (path, global, [[send]]), limit 0.88, deadline +1, window 10 slots, exit 2 slots / TP 10% / SL 20%, one position.
    - Optional one-flag change `--presend-live-k 6` (EXPLORATORY, added after the pre-registered runs): same 30/s, but no
      slot without tries each second. Replay +4.8 vs +4.3 SOL/day, fewer failed tries.
  - **Run >= 4 h**, in normal hours (avoid 21-24 PKT, the replay's weakest band). Caps: 100 fills, fee budget 0.1 SOL.
  - **Expected (replay, INFERRED):** +0.18 SOL/h, 24 fills/h, failed-try fees 0.027 SOL/h (so the 0.1 SOL budget stops it
    after ~3.7 h). 4-hour blocks: 94% positive, p10 +0.25 SOL. Worst clock hour -0.14 SOL.
  - **Pass / fail (set now):** afterwards, replay the same hours with this code.
    - Pass: live P&L per fill (chain) >= +0.004 SOL on >= 80 fills, and live net inside the replay's 90% band for those hours.
    - Fail: live P&L per fill <= +0.001 SOL. Then the follower assumption is wrong for us: stop pre-send T2.
    - In between: not decided; run another ~4 h.
  - Only after a pass: size 0.55 (V0 +6.7/day) and a 2nd path at 45/s (V2 k16: +5.5/day at 0.35, +9.0 at 0.55).
    Any new path needs the owner's OK.
- **What does NOT help** (replay, unseen hours, vs V0 +4.30):
  - V1, keep trying 1-2 slots after the whale sells: +4.22 / +4.23.
  - V3, bursts timed on the whale's past sell delay: +3.6 to +4.8 (no gain at the same cap).
  - V4, only repeat quick-dumpers: +3.3 to +4.2. Better per fill (+0.010 to +0.012), but it arms 2.5x fewer windows
    and gets ~1.6x fewer fills.
  - 32 tries/slot, or a 60/s cap: more failed tries, no more fills than 45/s. At 60/s the paths' 1-second budgets empty
    and leave a slot with no tries: the same thing that cost probe 2 its two AEgTuy8L windows.

## 1. Calibration on the two live probes (marks pre-registered in 0.1)

### 1.1 Final run (400 draws per probe; replay = mean, 90% range in brackets)
| | Probe 1 live | Probe 1 replay | Probe 2 live | Probe 2 replay |
|---|---|---|---|---|
| Windows | 118 | same 118 | 71 | same 71 |
| Fills | 20 | 21.7 (18-25) | 13 | 11.5 (9-14) |
| **Mark 1: fill / no fill agreement (>= 90%)** | - | **92.7% PASS** | - | **94.4% PASS** |
| **Mark 2: net SOL (within +-0.01 of live)** | -0.0075 | **-0.0231 FAIL** (-0.122 to +0.094) | -0.0181 | **-0.0022 FAIL** (-0.061 to +0.047) |
| Fills P&L / failed-try fees, SOL | +0.0119 / 0.0194 | -0.0042 / 0.0188 | -0.0010 / 0.0171 | +0.0153 / 0.0175 |
| Tries sent / landed | 3,808 / 3,808 | 3,711 / 3,700 | 3,376 / 3,360 | 3,435 / 3,429 |
| Tries refused by the rate caps | 83 | 79 | 807 | 791 |
| Deadline failures | 366 | 354 | 256 | 332 |
| Fill lands after its crossing trade, ms p25/50/75 | 24 / 44 / 54 | 12 / 27 / 46 | 13 / 26 / 43 | 7 / 17 / 32 |
| Where live sits in the replay's spread | - | 62nd percentile | - | 29th percentile |

- Live probe 2 sent 3,429 tries, but 53 were exact copies of an earlier try (same blockhash, limit and deadline give the
  same signature), so 3,376 distinct txs.
- **Both probes together:** replay -0.0253 SOL (-0.145 to +0.096) vs live -0.0256; fills 33.2 vs 33. MEASURED vs replay.
- Same hours through the variant pipeline (detected triggers, the engine's own skip rules, 40 draws): probe 1's hour
  -0.050 SOL (live -0.0075), probe 2's two hours +0.028 (live -0.018). A typical 2-hour block of the unseen hours gives
  +0.37 SOL with V0. So the probe hours were weak in the replay too.
- **Mark 3: 3 of 4 PASS.** p(fill): 2uYDtKbW 0.09, 7Y436FBv 0.20, 2yrbEtsu 0.07, **GvtdnDT8 0.86 (FAIL).**
  - GvtdnDT8: the live engine saw that trigger a slot late. Its first try (sent 51 ms after the engine saw the trigger)
    landed ~590 ms after the trigger: after the whale's crash (+496 ms) and after the 2.9 SOL bounce buy (+533 ms).
  - Of 85 live windows whose trigger sat early in its slot, this is the only one the engine saw a slot late. The replay
    cannot know that, so it mostly fills there.
- **Why mark 2 fails:** one window's result swings -48 to +37 mSOL, and which window fills depends on that window's real
  landing speed (a race, below). With 13-20 fills, a probe's total is one draw with a 0.03-0.07 SOL spread.
  The +-0.01 mark was too tight for that. The two probes' errors cancel almost exactly.
- **Caution, MEASURED:** replay fills land closer behind the crossing trade than live fills (median 27 vs 44 ms and
  17 vs 26 ms; live has only 33 fills). Landing every try 15 ms later does not move this gap and changes the unseen-hour
  results by <= 0.3 SOL/day, so the gap is about how live tries bunch up, not their average delay.

### 1.2 The race that decides a window (MEASURED)
- A try fills only if it was sent BEFORE the engine saw the crash (so its limit is still 0.88 x the pre-crash price) and
  lands AFTER the crash, before the bounce, inside its slot deadline.
- Example, probe 1 w28 (8Ab9gVcr): live tries landed 34-90 ms after sending, all before a 3-sell cascade, and the next try
  had already seen it (limit lowered): no fill. A normal, slower window fills there. Replay p 0.92.
- So the replay is right on average, not window by window.

### 1.3 Runs (pre-registration: report both)
- **First run** (16 draws): agreement 91.1% / 93.9%; net error -0.053 / +0.027 SOL; GvtdnDT8 p 0.94.
- **Fixed after it** (model and bugs, never the data):
  1. The engine's view of the chain, fitted on the 7,184 live signing prices (each try's limit shows which trades the
     engine had seen). Later trades are seen sooner than the chain clock says (same slot ~25 ms), at a per-window speed.
     The replay's limits now match live for 92-95% of tries.
  2. The engine's slot (+1 deadline, window end) from that same view (75% exact, 99% within one slot). Before, a donor
     window's slot sequence ended windows ~1.7 slots early.
  3. Bugs: a whale sell after the stored tape was read as immediate; our FRA bot's trades had been dropped from the tape
     (they are real buys); the probe's pace slot (214.1 / 211.7 ms).
- **Final run**: the table above. Try counts, refused tries and failed-try fees now match live.
- Checks of the parts on their own (MEASURED, before any landing model):
  - the replay detector gives every live trigger (265 of 265, 183 of 183, same holding %);
  - every one of 7,168 landed live tries gets its real chain result back from the tape at its real landing spot
    (ok / 6042 / deadline / ata_exists: 100%);
  - every live fill's realized P&L comes back within 3 lamports at its real entry and sell spots (33 of 33).

### 1.4 Landing by leader client (MEASURED, 7,184 landed live tries)
| Leader client | Tries | Send -> land, ms p25 / p50 / p75 (incl. the trigger's view delay) | Land in the send slot / next / later |
|---|---|---|---|
| AgaveBam | 2,422 | 74 / 112 / 160 | 33% / 62% / 5% |
| JitoLabs | 1,488 | 59 / 112 / 178 | 42% / 51% / 6% |
| HarmonicAgave | 1,442 | 72 / 109 / 146 | 50% / 48% / 2% |
| Firedancer | 932 | -63 / 15 / 100 | 40% / 56% / 5% |
| HarmonicFiredancer | 642 | 62 / 94 / 123 | 45% / 53% / 2% |
- Firedancer leaders put our tries early in their blocks. The others differ little. The replay does not split by client:
  it lays whole live windows (with their real leader mix) onto each window.

## 2. Variants on unseen hours (rules pre-registered in 0.2)
- 76.2 test hours, 10-22 03:40 -> 10-25 18:00 PKT (both probes, warm-ups, the newest tail and 15 low-coverage bins out).
  Half 1 = 10-22 03:40 -> 10-23 22:20; half 2 = the rest (38 h each).
- 14,906 T2 triggers (whale >= 6%); 9,240 can arm (5,650 were create-slot triggers). One stream, one position.
- 4 draws per variant; null = 20 runs of random arming at the variant's own rate per 10 min, on tokens the engine
  would follow (seen from their create, standard SOL curve, not mayhem, not in their create slot).
- SOL/day is net of every cost. P&L / fill is after the fill's own costs (pump fees, buy fee + tip, sell fee + tips),
  before failed tries.

### 2.1 All pre-registered variants at 0.35 SOL (all pass both rules)
| Variant | SOL/day | Half 1 | Half 2 | Fills/day | Failed tries / fill | P&L / fill | Null p95 | Pass |
|---|---|---|---|---|---|---|---|---|
| V0 | +4.30 | +4.88 | +3.72 | 586 | 0.0011 | +0.0085 | -0.81 | yes |
| V1a | +4.22 | +4.82 | +3.63 | 595 | 0.0011 | +0.0082 | -0.81 | yes |
| V1b | +4.23 | +4.72 | +3.74 | 598 | 0.0012 | +0.0082 | -0.81 | yes |
| V2_k16_c30 | +4.22 | +4.81 | +3.64 | 584 | 0.0012 | +0.0084 | -0.89 | yes |
| V2_k16_c45 | +5.46 | +6.30 | +4.62 | 695 | 0.0015 | +0.0094 | -1.42 | yes |
| V2_k16_c60 | +4.62 | +5.08 | +4.16 | 632 | 0.0021 | +0.0094 | -1.62 | yes |
| V2_k32_c30 | +3.84 | +4.28 | +3.41 | 582 | 0.0012 | +0.0078 | -0.88 | yes |
| V2_k32_c45 | +5.36 | +6.30 | +4.43 | 694 | 0.0015 | +0.0093 | -1.48 | yes |
| V2_k32_c60 | +3.92 | +4.52 | +3.32 | 612 | 0.0023 | +0.0087 | -1.88 | yes |
| V2_k4_c30 | +4.18 | +5.03 | +3.33 | 598 | 0.0007 | +0.0077 | -0.62 | yes |
| V2_k4_c45 | +4.27 | +5.07 | +3.49 | 602 | 0.0007 | +0.0078 | -0.67 | yes |
| V2_k4_c60 | +4.27 | +5.07 | +3.49 | 602 | 0.0007 | +0.0078 | -0.67 | yes |
| V2_k8_c30 | +4.30 | +4.88 | +3.72 | 586 | 0.0011 | +0.0085 | -0.81 | yes |
| V2_k8_c45 | +5.18 | +5.96 | +4.40 | 677 | 0.0012 | +0.0088 | -1.20 | yes |
| V2_k8_c60 | +5.14 | +5.90 | +4.37 | 678 | 0.0012 | +0.0088 | -1.09 | yes |
| V3a_c30 | +4.17 | +4.97 | +3.37 | 579 | 0.0009 | +0.0081 | -0.81 | yes |
| V3a_c60 | +4.78 | +5.80 | +3.77 | 622 | 0.0012 | +0.0089 | -1.09 | yes |
| V3b_c30 | +3.63 | +4.06 | +3.20 | 383 | 0.0005 | +0.0099 | -0.38 | yes |
| V3b_c60 | +3.69 | +4.31 | +3.07 | 397 | 0.0007 | +0.0100 | -0.52 | yes |
| V4a_k16_c30 | +3.43 | +3.90 | +2.97 | 374 | 0.0007 | +0.0099 | -0.37 | yes |
| V4a_k16_c60 | +4.15 | +4.62 | +3.68 | 409 | 0.0012 | +0.0113 | -0.75 | yes |
| V4a_k32_c30 | +3.46 | +3.99 | +2.93 | 375 | 0.0007 | +0.0099 | -0.29 | yes |
| V4a_k32_c60 | +3.59 | +4.09 | +3.08 | 390 | 0.0013 | +0.0105 | -0.82 | yes |
| V4b_k16_c30 | +3.31 | +3.43 | +3.19 | 327 | 0.0006 | +0.0108 | -0.34 | yes |
| V4b_k16_c60 | +3.75 | +3.89 | +3.60 | 353 | 0.0011 | +0.0117 | -0.43 | yes |
| V4b_k32_c30 | +3.26 | +3.27 | +3.25 | 328 | 0.0006 | +0.0106 | -0.29 | yes |
| V4b_k32_c60 | +3.45 | +3.45 | +3.44 | 340 | 0.0012 | +0.0114 | -0.52 | yes |
- Names: k = tries per slot; c30 = one path at 30/s (as probe 2); c45 / c60 = a second path, global 45 or 60/s (needs owner OK). V2_k8_c30 is V0. V3a/b: bursts of 32/slot in the whale's predicted sell slots (b: only whales with a history). V4a/b: only whales with >= 1 / >= 2 earlier quick dumps of >= 12%.

- Per PKT day (SOL/day; hours in the day in brackets):

| Variant | 10-22 (18 h) | 10-23 (22 h) | 10-24 (23 h) | 10-25 (14 h) |
|---|---|---|---|---|
| V0 | +4.40 | +4.97 | +3.27 | +4.84 |
| V2_k16_c30 | +4.69 | +4.58 | +3.33 | +4.53 |
| V2_k16_c45 | +5.80 | +6.34 | +3.78 | +6.40 |
| V2_k4_c30 | +4.78 | +4.76 | +2.76 | +4.83 |
| V2_k8_c45 | +5.60 | +5.98 | +3.28 | +6.51 |
| V3b_c30 | +3.73 | +3.89 | +3.17 | +3.84 |
| V4b_k16_c60 | +3.93 | +3.44 | +3.34 | +4.67 |
- V0 by 3-hour PKT band (SOL/day rate): 00-03 +7.0, 03-06 +6.2, 06-09 +4.8, 09-12 +3.7, 12-15 +3.1, 15-18 +4.0, 18-21 +4.5, 21-24 +0.3.
- V0 by clock hour: 87% positive, worst -0.14 SOL, best +0.84 SOL; mean +0.18 SOL/h.
- Exploratory (added after the pre-registered runs, so NOT part of the pass / fail):
  - `X_k6_c30` = V0 with k 6: +4.81 (halves +5.57 / +4.05; days +5.1 / +5.6 / +3.1 / +6.0); null p95 -0.85; fee/fill 0.0009.
  - `X_k8_g25` = V0 with the global cap at 25/s: +4.27.
  - At 0.55 SOL, k 6: +7.87.

### 2.2 Size (V5; every variant passed at 0.35)
| Variant | 0.35 SOL | 0.55 SOL | 0.75 SOL |
|---|---|---|---|
| V0 | +4.30 | +6.68 | +8.42 |
| V2_k4_c30 | +4.18 | +6.58 | +8.14 |
| V2_k16_c30 | +4.22 | +6.44 | +7.98 |
| V2_k8_c45 | +5.18 | +8.42 | +11.32 |
| V2_k16_c45 | +5.46 | +8.95 | +11.60 |
| V3b_c30 | +3.63 | +5.36 | +7.00 |
| V4b_k16_c60 | +3.75 | +6.01 | +7.59 |
- Both halves stay positive at every size. A bigger size also makes the follower risk (2.3) bigger.

### 2.3 Stress tests (SOL/day; halves in brackets)
| Variant | Main | Tries land 15 ms later | Pessimistic landing (no interpolation) | 20% of later buys dropped | 30% dropped |
|---|---|---|---|---|---|
| V0 | +4.30 | +4.26 | +4.30 | +1.02 (+1.28 / +0.76) | **-0.73** |
| V2_k4_c30 | +4.18 | +3.87 | +3.68 | +0.93 | - |
| V2_k16_c30 | +4.22 | +3.92 | +3.83 | +0.72 | - |
| V2_k8_c45 | +5.18 | +5.21 | +5.36 | +1.50 | **-0.65** |
| V2_k16_c45 | +5.46 | +5.35 | +5.07 | +1.32 | **-0.77** |
| V2_k32_c60 | +3.92 | +3.96 | +3.62 | +0.24 (+0.68 / **-0.20**) | - |
| V4b_k16_c60 | +3.75 | +3.81 | +3.60 | +1.59 | +0.28 (+0.76 / **-0.19**) |
- Our own bots' trades (FRA / AMS wallets, 478 in the whole tape) removed: V0 +4.31 (vs +4.43 in that run). No self-help.
- In probe 1, replay fills in windows where live did NOT fill earn about the same as in shared windows (-0.03% vs
  +0.26% of size per fill), so that hour looks weak, not distorted by our own live buys.

### 2.4 Where the dense pre-sender economics bite (MEASURED replay)
- Failed-try cost per fill: k 4: 0.0007; k 8: 0.0011-0.0012; k 16: 0.0012-0.0021; k 32: 0.0012-0.0023 SOL.
- P&L per fill only rises from +0.0077 (k 4) to +0.0094 (k 16). Fills land closer behind the crash (median 26 ms at
  k 4, 16 at k 8, 12 at k 16, 10 at k 32), but the bounce still comes first in many windows.
- Our caps hold real density to ~6 per slot (30/s) or ~10-12 (45-60/s). At 60/s the paths' 1-second budgets empty and
  leave slots with no tries, so 60/s fills fewer than 45/s while paying more (k 32: 612 vs 694 fills/day).
- The dense bots' 26-85 tries per slot would cost ~0.006-0.015 SOL per fill (INSTANT_BOTS.md estimate, INFERRED)
  against our ~+0.009 per fill: at 25/slot about break-even, above it a loss.

## 3. Earlier pre-send claims this contradicts or confirms (quoted)
1. V2_OPTIONS.md, probe-2 pass mark: "Fills >= 20% of armed windows (model 24%...)". Live was **18%** (13 / 71); this
   replay gives 16% on those windows and 23% on the unseen hours. The probe-2 hours were weak, not the model.
2. V2_OPTIONS.md size sweep "+5-12 SOL/day" (the task calls it suspect): **the landing model does not kill it**.
   With only real-landing fills: 0.35 SOL +4.2 to +5.5, 0.55 +6.4 to +9.0, 0.75 +8.0 to +11.6 per day. But it rests on
   the later buyers: 20% fewer of them leaves +0.2 to +1.6 at 0.35, 30% fewer is negative.
3. V2_OPTIONS.md: "8 attempts per slot land ~13 ms earlier: median 16 vs 29 ms". Replay agrees (16 vs 26 ms), but live
   fills landed later behind the crossing than the replay's (1.1). Absolute timing may be optimistic; SOL/day barely moves.
4. ops/dip/vm1/VERIFY.md: "Any landing distribution replay over-predicts our real fires by +5.3 mSOL per fire". **Not
   seen for pre-send:** the two probes together differ by +0.3 mSOL in total (~0.0 per fill, 1 sd ~2 mSOL per fill).
   Caveat: at live fills the tape already holds the market's reaction to our real buy, so this check is partly circular.
5. instant/INSTANT_BOTS.md: "this density on T2 windows costs more than T2 earns" (25-60 tries/slot). Holds at 60/slot;
   about break-even at 25/slot against this replay's +0.009 per-fill edge. At our caps density is cheap (<= 0.0023/fill).
6. The task's probe-2 reading ("in all 4 the whale's own sell was the crash ... only ~6 tries/slot went out"):
   confirmed and explained. helius-ps's 1-second budget (30) is used up ~0.8 s into a window at 8/slot, so no try goes
   out for ~1 slot each second. 2uYDtKbW and 7Y436FBv crashed in such a gap (replay p 0.09 / 0.20).
7. Small: 68 of 110 tries the engine logged as "unseen" did land on chain (all failed, so fees paid). The engine's
   failed-try fee counter misses them (~0.0003 SOL in probe 2).

## 4. How the replay works (short)
- **Tape:** my own decode of the 4 raw recordings: 13.1 M successful pump.fun trades, 153 k creates, per token in chain
  order. Our probes' own fills and sells removed (the replay puts its own buy in); everything else as recorded.
- **Tries:** the engine's pace (k per slot, 212 ms slot) and its three rate limits in its own order (path bucket,
  global bucket, then the path's 1-second budget), shared by all armed windows. A refused try is lost, never queued.
- **Landing ("donor"):** each window takes one of the 115 full-length live windows whose trigger sat at a similar point
  of its slot, and lays that window's send -> land delays onto its own chain events (never itself or its token in
  calibration). This keeps leader batches, slow slots and the ~0.5% of tries that never land.
- **Engine view:** each window gets its donor's view speed (fitted on the live signing prices). It sets each try's limit
  (0.88 x the latest price seen), the whale-sell stop (+30 ms), when our fill is seen, and the engine's slot.
- **Fill:** price at the try's landing spot <= its limit, slot <= its deadline, one fill per window, one position at a
  time (every try pauses while a position is open; token blocked until sell + 300 ms).
- **Exit:** TP +10% / SL -20% on the first later trade that crosses before the engine reaches entry slot + 2, else the
  time exit; the sell lands after a delay drawn from the 33 live sells.
- **Costs (MEASURED on chain):** failed try 5,120 lamports; fill: buy fee 5,120 + tip 200,000, sell fee 605,000 +
  tips 1,200,000 (2.01 mSOL per fill); pump fees (1.25% each way) in the curve math; ATA rent comes back.
- **Followers:** the recorded tape; a later buyer whose slippage our buy breaks is dropped (the 711 measured slippage
  settings). In the 33 live fills no follower was dropped. Stress: 20% / 30% of later buys dropped at random.
- **Not modelled:** a second path's own landing (assumed like helius-ps); competitors reacting to us; the reactive bot
  sharing the one position (it rarely fires on AMS).

## 5. Files
- Code (`ops/strategies/presend/real/`): `decode.py` + `build.py` (tape), `rlib.py` (clock, detector), `probes.py` +
  `donors.py` (live tries, view speed), `sim.py` (the replay), `calib.py`, `hours.py`, `variants.py`, `vreport.py`,
  `mktables.py`, `probehours.py`, `run_after.sh`.
- Data (`/home/moiz/sniper-data/presend_real/`): `tab/` (merged tape), `donors.pkl`, `view_cdf.json`, `hours.json`,
  `calib_final.txt/json` (+ `_corr_final`, `_lag15`, and the earlier `smoke*` runs), `variants_<tag>_raw.pkl/.json/.log`
  for tags main, explo, explo055, size055, size075, corr, cut20, cut30, lag15, smoke_noours.
- Re-run: `python3 calib.py --draws 400 --tag final`; `python3 variants.py --draws 4 --nulls 20 --tag main`;
  `python3 vreport.py main`. New hours: re-run `decode.py`, `build.py`, `hours.py` first.


## 0. Pre-registration (fixed before any result)

### 0.1 Calibration on the two live probes (window by window)
- Unit = one live armed window. Probe 1 (AMS run 16): 118 windows. Probe 2 (AMS run 17): 71 windows.
- The replay re-runs each window from the recorded chain tape, with MODELED tries (never the real ones).
  The landing draws are random, so each window runs 400 draws. p = share of draws that fill.
- **Mark 1, fill / no-fill agreement:** the mean, over windows, of P(replay outcome = live outcome) must be >= 90%,
  in EACH probe. Also shown (not a mark): the majority rule (p >= 0.5 vs live).
- **Mark 2, P&L:** the replay's mean net P&L per probe must be within +-0.01 SOL of live, in EACH probe.
  - Live net = chain-realized P&L of the fills (presend_live_realized) + the fees of failed tries (chain).
  - Replay net = the same items, modeled.
- **Mark 3:** the 4 probe-2 misses (2uYDtKbW, 7Y436FBv, GvtdnDT8, 2yrbEtsu) each come out with p < 0.5.
- If a mark fails: find why, fix the MODEL (never the data), re-run, and report both runs.
- Diagnostics (not marks): the replay with the REAL tries (tests the tape, fill rule, exits and costs on their own);
  try outcomes (ok / 6042 / deadline / dropped); tries refused by the rate caps.

### 0.2 Variant test on unseen hours
- Hours: every recorded hour except the probe hours (probe 1 08:38-10:28, probe 2 15:20-17:40 PKT on 10-25),
  minus recording holes. Split into two halves by time, equal hours each.
- SOL/day = net P&L (every cost in) / hours x 24. One stream, one position at a time.
- **A variant passes only if BOTH hold (main landing model):**
  1. net SOL/day > 0 in BOTH halves;
  2. it beats the null: its net SOL/day over all test hours is above the 95th percentile of 20 null runs.
     Null = the same variant, but windows armed at random times on random tradeable tokens (traded in the last 10
     slots, curve < 100 SOL), at the same number of windows per hour; same window length, same tries; no whale, so
     no whale-sell disarm.
- "Worth a small live test" needs a passing variant AND a passing calibration. If calibration fails, I say the
  variant numbers are not reliable.
- Shown, not marks: a pessimistic landing (tries fully correlated), per-day results, fills/day, failed-try cost per fill.
- Variants (settings fixed now):
  - **V0** = probe 2: whale >= 6%, 0.35 SOL, k 8/slot, limit 0.88 x latest price, deadline +1 slot, window 10 slots,
    disarm 30 ms after the whale's first sell, one path with caps 30/s (path, global, path config), exit 2 slots /
    TP +10% / SL -20%, one position, create-slot triggers skipped.
  - **V1** = V0, but the whale-sell disarm waits 1 slot (V1a, 212 ms) or 2 slots (V1b, 424 ms) instead of 30 ms.
  - **V2** = V0 with k = 4 / 8 / 16 / 32, at the live 30/s caps, and with a second path (total 45/s and 60/s;
    "needs owner OK", as any new path does).
  - **V3** = whale-timed tries: if the whale had >= 1 earlier window (strictly before this trigger) where it sold
    within the window, the predicted sell slot = the median of its earlier trigger -> first-sell delays (slots).
    Tries go out at k 32 in slots [pred - 1, pred + 1] and k 2 in the other slots. Whales with no history: as V0
    (V3a) or not armed (V3b). Caps: 30/s and 60/s.
  - **V4** = repeat-whale only: arm only if, in earlier windows (strictly before this trigger), the whale's first sell
    came within the window AND that sell dropped the price >= 12% at least once (V4a) or twice (V4b). Dense tries:
    k 16 and 32, caps 30/s and 60/s.
  - **V5** = sizes 0.35 / 0.55 / 0.75 SOL, only for variants that pass at 0.35.
