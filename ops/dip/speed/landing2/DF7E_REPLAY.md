# DF7eRXHn strategy replayed at OUR execution (0.5 SOL)

Study 10-25, ~23:10 → 10-26 PKT. Read-only: local recordings only. No RPC, no transactions, no server touched.
Competitor forensics: [WALLET_DF7eRX.md](WALLET_DF7eRX.md).

- **Window:** run_20261023_1426 + run_20261024_1425 = **10-23 19:26 → 10-25 19:45 PKT, 48.3 h**. Halves split at 10-24 19:35. His life inside it: 10-24 15:52 → 10-25 19:07.
- **Labels:** MEASURED = counted on chain or replayed on the real tape. INFERRED = my reading or a model.
- **"mSOL per fire"** counts every buy we send that lands, filled or reverted.
- **"Pre-cost"** means after pump fees (1.25% per side, about 12.5 mSOL per 0.5 SOL round trip) and before tx costs.

## Verdict

**At our speed and 0.5 SOL: not positive. Every version of his strategy that we could actually run loses money.**

| Version (max 1 open, our landing, +5% guard, 20% follower cut) | SOL/day, our costs 3.8 mSOL | SOL/day, his costs 1.65 mSOL | mSOL per fire, pre-cost | Fills/day |
|---|---|---|---|---|
| **His trigger classes as rules** (dump, young dump, wake-up, big-buy) | **−303** (−420 corrected) | −259 (−375) | −8.3 | 18,900 |
| **His selection as explicit rules** (SEL-A, about his trade rate) | **−68** (−93) | −59 (−85) | −7.2 | 3,700 |
| **Copy him** (buy right after his own landed buy) | **−34** (−55) | −28 (−48) | −3.8 | 2,900 |
| Null: random entries at the same rate | −312 | −271 | −11.9 | 17,300 |

- **No trigger class is positive at our speed, even before tx costs** (MEASURED replay): dump −13.8, young dump −6.0, wake-up −4.2, big-buy −5.4 mSOL per fire.
- **The rules beat random entries,** but not by enough to cover pump fees and tx costs.
- **Faster landing does not fix it.**
  - 25–35 ms faster: the rules go from −8.3 to −7.6 mSOL per fire, pre-cost.
  - Copying him at 35 ms faster reaches +0.7 pre-cost, which is still −22 SOL/day after costs.
- **His real edge is his choice of trades, and we cannot rebuild that choice from chain data.**
  - He trades only about 1.4% of the eligible events.
  - My best explicit rule finds a group of events where he takes 12%. That rule still loses for us, in every period, at every speed.
- **Replay calibration** (section 4):
  - The curve math reproduces his real P&L exactly.
  - My exit rule reproduces his exits.
  - The full replay at his speed over-predicts his real result by 1.4–2.1×, about +2 to +6 mSOL per fire. That matches our known replay optimism (~+5 mSOL per fire), so the corrected rows are the honest ones.

## 1. His behaviour as rules (causal: only data up to the trigger)

| Piece | Rule | Source |
|---|---|---|
| Dump (D) | Sell ≥ 1 SOL that drops the price ≥ 6%, token > 10 s old | His take rate is 4× higher above 1 SOL / 6% (MEASURED, 27 h). His 0.3–1 SOL dumps made 0.0 |
| Young dump (YD) | The same, token ≤ 10 s old | Same |
| Wake-up (WU) | Buy of 0.5–4 SOL after ≥ 10 slots without a trade, token > 10 s old | Forensics thresholds |
| Big-buy follow (BB) | Buy of 1–8 SOL, 1–9 slots after the previous trade, token > 10 s old | His take rate is highest at 1–8 SOL and 3–10 slot gaps |
| Envelope | Real SOL in the curve ≤ 50; normal SOL curve whose creation is in the recording | His edge is gone above 25–50 SOL |
| Entry guard | Our +5% vs the post-trigger price (a revert costs 0.6 mSOL). His −18% as a reference row | Our 61 h guard sweep |
| Exit (main) | Hold at least 9 slots. Then sell on the first trade by others that leaves the price ≥ 10% below the peak since entry, or after 5 quiet slots; at most 1,500 slots. Our sell lands after our own landing delay | Fit on his own entries, section 4 |
| Re-entry | Allowed once the previous position on that token is closed; never 2 positions on 1 token | He re-enters on 45% of buys |
| Max open | 1 and 3 (he averages 2.6) | |

**His exit is not a simple timer** (MEASURED on 4,069 of his positions):
- At slot 10 he sells ~30% of positions, whatever the price did.
- His later exits depend on the price path.
  - Replaying his entries with a random hold drawn from his own hold times makes +5.1 SOL. His real exits made +22.6.
  - The trail rule above makes +23.1, so it is the main exit.

## 2. Main replay: his trigger classes as rules (0.5 SOL, our landing, +5% guard)

Median landing 53 ms, 23% in the next block: our 371 live landings, r10+.

| Max open | Cost row | Cut 20%: SOL/day raw (corrected) | Cut 35%: raw (corrected) | Fills/day | Fill | Win |
|---|---|---|---|---|---|---|
| 1 | our 3.8 | −303 (−420) | −339 (−409) | 18,944 | 86% | 21% |
| 1 | his 1.65 | −259 (−375) | −294 (−364) | | | 23% |
| 3 | our 3.8 | −660 (−916) | −733 (−887) | 41,656 | 86% | 20% |
| 3 | his 1.65 | −562 (−818) | −635 (−789) | | | 22% |

Corrected = raw − 5.3 mSOL per fire (cut 20%) or − 3.2 (cut 35%): the VM1 live calibration.

**By trigger class** (max 1, cut 20%):

| Class | Fires/day | Fill | Our 3.8: raw (corr) | His 1.65: raw (corr) | mSOL/fire pre-cost |
|---|---|---|---|---|---|
| D dump | 8,110 | 94% | −157 (−200) | −138 (−181) | −13.8 |
| YD young dump | 3,624 | 81% | −49 (−68) | −42 (−61) | −6.0 |
| WU wake-up | 5,889 | 83% | −50 (−81) | −38 (−70) | −4.2 |
| BB big-buy | 4,378 | 80% | −48 (−71) | −40 (−63) | −5.4 |

With max 3 open, the per-fire numbers are the same: −13.8 / −6.7 / −4.3 / −4.8.

**Halves** (max 1, cut 20%, raw SOL/day):

| Half | Our 3.8 | His 1.65 |
|---|---|---|
| 10-23 19:26 → 10-24 19:35 | −309 | −263 |
| 10-24 19:35 → 10-25 19:45 | −297 | −254 |

**Speed, guard, exit and null** (max 1, cut 20%, raw):

| Row | Our 3.8 SOL/day | His 1.65 SOL/day | mSOL/fire pre-cost | Fill | Win |
|---|---|---|---|---|---|
| Our landing (53 ms) | −303 | −259 | −8.3 | 86% | 21% |
| 25 ms faster | −294 | −248 | −7.7 | 89% | 23% |
| 35 ms faster | −295 | −248 | −7.6 | 91% | 24% |
| His guard −18% (reference only) | −309 | −262 | −9.2 | 98% | 21% |
| Exit: fixed 10 slots | −330 | −277 | −7.3 | 86% | 22% |
| Exit: his hold-time draw | −44 (1,434 fills/day) | −40 | −18.6 | 86% | 23% |
| **NULL: random entries, same rate** | −312 | −271 | −11.9 | 97% | 17% |

With max 3 open the picture is the same: 25 / 35 ms faster gives −7.8 / −7.7 pre-cost, and the null gives −11.7.

## 3. His selection as explicit rules, and copying him

- He takes only **1.4%** of the broad events (dumps ≥ 0.3 SOL / 3%, buys ≥ 0.5 SOL; MEASURED).
- I fit a small tree on the first half of his life (10-24 15:52 → 10-25 05:29) and tested it on the second half.
  - In both halves, the top 10% of events by the tree hold 40% of his triggers. So his choice is stable but only weakly explained by chain data.
- **SEL-A** = a dump with the price drop > 9.5%, > 19 trades in the last 150 slots, and the last 5 slots' net flow > −4.7 SOL. He takes 12% of these.
- **SEL-B** = SEL-A plus the leaves where he takes ≥ 3.5%.

**SEL-A** (0.5 SOL, +5% guard, cut 20%, raw SOL/day with corrected in brackets):

| Period | Landing | Max 1: our 3.8 | Max 1: his 1.65 | Pre-cost mSOL/fire | Max 3: our 3.8 |
|---|---|---|---|---|---|
| Before his life (unseen, he is absent) | ours | −83 (−111) | −73 | −8.1 | −99 |
| His 1st half (fit) | ours | −83 (−113) | −73 | −7.7 | −106 |
| His 2nd half (test) | ours | −34 (−51) | −28 | −4.4 | −38 |
| His 2nd half (test) | 35 ms faster | −28 | −22 | −1.5 | −29 |
| **All 48 h** | ours | **−68 (−93)** | **−59 (−85)** | −7.2 | −82 |
| All 48 h | 25 / 35 ms faster | −65 / −64 | −55 / −55 | −5.9 / −5.6 | −80 / −80 |
| All 48 h | NULL, same rate | −90 | −79 | −12.6 | −117 |

- SEL-B is worse: −218 SOL/day at max 1, −9.4 mSOL per fire pre-cost. Its null is −247.

**Copy him** (trigger = his landed buy on our feed; 0.5 SOL, no position limit, cut 20%):

| Landing | Our 3.8: raw (corr) | His 1.65: raw (corr) | Pre-cost mSOL/fire | Fills/day | Win |
|---|---|---|---|---|---|
| Ours | −34 (−55) | −28 (−48) | −3.8 | 2,905 | 25% |
| 25 ms faster | −26 (−46) | −18 (−39) | −0.8 | 3,168 | 30% |
| 35 ms faster | −22 (−42) | −14 (−34) | +0.7 | 3,276 | 32% |

Both halves are negative at every speed.

**His exact trigger events: not a strategy (look-ahead).**
- Replaying the 4,951 events he reacted to gives +40 SOL/day raw at our speed (+16.7 mSOL per fire pre-cost).
- But 22% of those fills land in a slot BEFORE his buy and make +41 mSOL per fire. His buy and his siblings' buys then push the price up after us.
  - The "trigger" (the biggest trade in the 3 slots before him) is often not what he reacted to.
  - Only knowing that he will buy picks these events.
- Where we land after him, it is −3.4 mSOL per fire.

## 4. Calibration on his own trades

All on the tape with his own trades removed, at 0.3 SOL.

| Check | Replay | His real (chain) | |
|---|---|---|---|
| C1. Curve math at his ACTUAL buy and sell positions (4,307 trades) | +22.61 SOL | +22.58 SOL | Exact (median error 0.00 mSOL) |
| C2. His entries, my main exit (trail) | +23.06 | +22.6 | Exit reproduced |
| C2. His entries, fixed 10 slots / fixed 30 / his hold-time draw | +30.7 / +23.0 / +5.1 | +22.6 | His exits are path-dependent, not a timer |
| **C3. His trigger events at his speed** (H2H: ours −16 ms), his −18% guard, his costs, no cut | **+53.9** (11.8 mSOL/fill, fill 93%) | **+25.2** (5.8 mSOL/fill, fill 79%) | **Over-predicts 2.1×** |
| C3. The same with his measured delays (median 60 ms; mis-attributed triggers make these look slow) | +35.4 (8.0/fill, fill 90%) | +25.2 | Over-predicts 1.4× |
| C4. My class rules at his speed and costs, max 13 / max 3 | −413 / −344 (−7.3 mSOL/fill) | +25.2 | The rules do NOT reproduce him |

- **Replay optimism:** +2.1 to +5.9 mSOL per fire at 0.3 SOL (MEASURED here). That matches the VM1 live calibration of +5.3, so the corrected rows are the honest ones.
  - The over-prediction comes from entry fills: 90–93% in the replay against his real 79%. His real guard varies per buy, from 3% to 26%.
- **C4 is the key result.** Even at his speed, his costs and with no follower cut, the trigger-class rules lose −7.3 mSOL per fill where he makes +5.8.
  - His profit sits in which events he picks, not in the trigger types.

## Method and limits

- **Scripts:** `ops/dip/speed/landing2/df7e/replay/`.
  - `r0_decode.py`: decodes the 34 newer raw files with the VM1 decoder.
  - `rlib.py`: data and features.
  - `r1_market.py`: market rates vs his take rate.
  - `r2_calib.py`: C1, C2, his delays and his holds.
  - `sim2.py`: event-driven simulator with a position limit.
  - `r3_replay.py`: the main jobs.
  - `r4_report.py`: the main tables.
  - `r5_select.py`: the selection tree.
  - `r6_sel_replay.py` and `r7_report.py`: SEL and copy.
- **Data:** `/home/moiz/sniper-data/df7e_replay/` (trades table 7.58 M trades, `runs/`, logs `r3.log`, `r4.txt`, `r7.txt`).
- **Simulator:** the VM1 model (`ops/dip/vm1/core.py`).
  - Block clock and spill into the next block.
  - Entry on the reserves just before our position, so bots ahead of us, including him, are priced in.
  - Our buy stays in the curve at the exit.
  - Each config is the mean of 5 Monte-Carlo landing draws (3 for calibration).
  - The 5 seeds differ by < 3%.
- **Limits:**
  - Graduations are exited at the last curve price; his PumpSwap exits are not modelled.
  - Tokens created before 10-23 19:26 are excluded.
  - The H2H speed shift (−16 ms) is from 58 shared dumps.
  - The his-landing rows are an approximation (INFERRED).
  - The bias correction was measured on our dump fires; for buy triggers it is applied as is (INFERRED).
