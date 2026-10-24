# Haiku pattern search on trading data + bot playbook (10-24, ~20:40 PKT)

Read-only study, nothing traded. MEASURED = counted from chain data; INFERRED = reading.
Scripts: ops/strategies/patterns/p0–p8. Results: /home/moiz/sniper-data/strategies/patterns/ (final.txt / final.json =
survivors with the R1 check, registry.json = all 428 rules with results, bots_verified.json, playbook_bait.json,
stories_R2/R3.jsonl, llm/ = prompts, answers and the spend ledger).

## The question
Owner, 10-24 ~20:10 PKT: can Haiku find new patterns we could act on, profitably, by reading the trading history of
tokens? And can we profit from the habits of other bots?

## Short answer
1. **Reacting to other people's trades: no new winner at our speed (MEASURED).**
   - Haiku proposed 228 + 129 + 40 rules: dump bounces, momentum after big buys, near-graduation runs, copying or
     front-running specific bots, buying after quiet spells.
   - On the train day every "react to someone else" category lost 1–1.5% per trade.
   - Only 6 of 242 such rules were positive. The best was the bounce after one serial creator fully exits, which is already
     our dip bot's territory and tiny (+0.7 to +4 SOL a day).
2. **What works is being the first buyer on a quiet token** (the earlier "F7 bait"). Haiku refined it and found one new
   variant.
   - **Refined quiet-token bait:** token at least 32 s old, no trade for 8 s, curve ≤40 SOL, buy 0.75–3 SOL. Sell at +8%,
     at −6%, after 25 s, or into a responder's buy. About 90 trades an hour, one position at a time (MEASURED replay):

     | Day | Profit | Trades | Per trade | Wins |
     |---|---|---|---|---|
     | R2 (train) | +82 SOL | 2,072 | +0.040 | 53% |
     | R3 (test) | +101 SOL | 2,193 | +0.046 | 57% |
     | R1 (extra check) | +44 SOL | 1,427 | +0.031 | 50% |

   - **New: young-token bait.** Token 6–25 s old that paused 2 s, curve ≤45 SOL, buy 0.9–2 SOL. Sell at +8% / −8% or
     after 13 s. A bot buys within 1 slot 67–69% of the time on every day, about 1.5 SOL of follower buying (MEASURED):

     | Day | Per trade | Wins | Trades | Profit |
     |---|---|---|---|---|
     | R2 | +0.054 | 61% | 607 | +32 SOL |
     | R3 | +0.038 | 61% | 768 | +29 SOL |
     | R1 | +0.073 | 67% | 428 | +31 SOL |

3. **Bait size matters.**

   | Bait size | Some bot buys within 1 slot (R2 / R3) | Follower buying |
   |---|---|---|
   | 0.35–0.75 SOL | 41% / 41% | ~0.5 SOL |
   | 0.75–1.2 SOL | 61% / 61% | ~0.9 SOL |
   | 1.2–2.1 SOL | 60% / 64% | ~1.3 SOL |

   - At 0.35–0.75 SOL the best rules make only +0.008 to +0.014 SOL a trade on all three days (about +4 to +13 SOL a day).
   - The 0.5–1.0 SOL bait on 4–25 s old tokens, selling into bot B345's buy, made +11.7 / +11.6 / +11.4 SOL on
     R2 / R3 / R1 (+0.016 to +0.031 a trade).
4. **Joining someone else's bait 35–50 ms later loses** (−0.004 to −0.009 SOL a trade, MEASURED). Only the first buyer
   gets the followers.

## How it was tested
- **Days:**
  - Train: R2, 10-22 20:43 → 10-23 18:28 PKT. Haiku saw only this day's tapes and results.
  - Test: R3, 10-23 19:26 → 10-24 19:23 PKT. Never shown to Haiku.
  - Extra check: R1, 10-22 03:12 → 18:56 PKT, used only at the end.
- **Tape stories:** 1,829 per day, picked from these groups: dumps, quiet spells, big buys, creator sells, near
  graduation, a random sample.
  - Each story covers price, curve, buys and sells, new wallets, and every trade ≥0.5 SOL or by an ID'd bot.
  - Trades are tagged creator / insider / new wallet / family F1–F10 / stable bot ID B1–B500.
  - Each story carries the token's label.
  - The family and bot lists come from the train day only, so there is no look-ahead.
- **Haiku rounds:** 92 + 30 + 12 batch requests. Train results were fed back from round 2 on; round 3 was steered toward
  non-bait ideas and capped-size bait filters.
- **Rules:** each rule is JSON (trigger conditions, race or not, exit). They are compiled and replayed automatically.
- **Replay settings:**
  - pump fee 1.25% each side + 0.0035 SOL per round trip + 0.0005 per failed buy;
  - +5% guard;
  - landing 35 / 50 ms after the trigger for races, next slot otherwise;
  - one position at a time;
  - follower slippage limits enforced.
- **Engine check:** the replay reproduces known results — dip trigger without the selector −3%/SOL, F7 bait +3.5–3.8%/SOL,
  momentum at our speed −2.4%/SOL.
- **Bait honesty rule:** "be the trigger" counts only at uncontested moments (quiet ≥10 slots, ≥30 slots old). Early-launch
  "baits" (≤3–10 slots old, +1,274 SOL on paper) were thrown out as launch-sniping races.
- **Luck check:** 97.7% of train-positive rules stayed positive on the test day, against 4.3% of train-negative ones. That
  persistence is almost entirely the one bait effect.

## Bot playbook (MEASURED; hit = how often the bot acts after the trigger while it is active)

**Followers of baits (our potential exit liquidity):**

| Bot | Wallet | Family | Reaction | Hit R2 / R3 | Timing | Size |
|---|---|---|---|---|---|---|
| B301 | 9pQQc1xy | F9 | buys within 1 slot after a 0.75–3 SOL quiet-token buy | 16.0% / 15.4% | 55% same slot, ~111 tx after | 0.47–0.69 |
| B1 | ssssswdk | F8 | same | 9.2% / 10.7% | ~120 tx after | 0.22 |
| B10, B11 | EprLoV21, EJX629cp | F9, one "1,105,000-fee" operator | same | 3–4% each | ~70–78 tx after | 0.296 |
| B9, B3, B4, B5 | 2Dd3TRSd, sssssDdM, omegoMAe, GKd5EMzR | F9 | same | 2–6% each | | |

B301 also follows ≥1 SOL buys by F7-family wallets: 15% / 20% (lift 6–8).

**Dip and dump reactors:**

| Bot | Wallet | Family | Reaction | Hit R2 / R3 | Lift | Timing | Size |
|---|---|---|---|---|---|---|---|
| B2 | haqqiUUX | F2 | buys within 2 slots after a creator or insider sell ≥0.9 SOL | 13.2% / 13.6% | ~9 | ~98 tx after | 0.27 |
| B12 | HkQ7hMjy | F2 | same | 3.9% / 4.7% | 9 | 84% same slot, ~82 tx after | 0.5 |
| B343 | AUih1Qc6 | bot | buys within 1 slot after a ≥5 SOL dump of −20% or worse | 3.7% / 2.4% | 23–32 | ~178 tx after | 0.49 |

**Early-launch actors:**

| Bot | Wallet | Reaction | Hit R2 / R3 | Lift | Timing | Size |
|---|---|---|---|---|---|---|
| B335 | CWiNFAEk | buys within 2 slots after ≥0.9 SOL buys on tokens ≤3 slots old | 6.3% / 8.9% | ~50 | ~71 tx after | ~1 SOL |
| B402 | dKMjeGJ4 | buys within 1 slot after ≥1.5 SOL buys at age ≤2 slots | 3.4% / 2.9% | ~50 | ~52 tx after | ~3.6 SOL |
| B486 | Anubis51 | flips ~2 SOL about 12 slots after early buys | 3.2% / 3.5% | 5–8 | | ~2 SOL |

B402 also sells about 1.2 SOL within roughly 8 slots of early activity.

**Serial dev:** B435 = bwamJzzt dumps in a ladder. The dip bounce after it fully exits is mildly positive (+0.009 to
+0.020 a trade), which is our dip bot's ground.

**Can we profit from them?**
- **Be the trigger:** yes. B301, B1 and the F9 crowd are the bait responders; profit depends on bait size (above).
- **Front-run:** no.
  - B2: −0.014 a trade.
  - B343: −0.008.
  - B301: about 0, and negative on R1.
  - B335 and B402 react at ~50–71 tx, faster than our ~65.
- **Avoid:** small gains only. Skipping tokens where an ID'd bot holds lifted the 0.75–1.2 SOL bait from +0.028 to +0.040
  a trade on the train day, but it halves the count.
- **Haiku's bot descriptions are too neat.** Of 401 behaviors described, none had a measured hit above ~35%. Only 2 cleared
  a 10% hit with ≥5× lift on R2, and both held on R3. Bots are selective, not mechanical.

## What this means
1. Stop looking for "react to X at 35–50 ms" ideas: this search found none that pay.
2. The bait effect is real and stable across three days, but only for the first buyer, and the edge shrinks fast below
   0.75 SOL.
3. **Owner decision:** a small live probe — 30 baits from a fresh wallet, young-token or quiet-token.
   - Measure: does a bot buy within 1 slot (61–69% expected at 0.75–2 SOL)?
   - Typical worst case: about −1.5 SOL.
   - It needs the owner's explicit OK: it conflicts with the "race pools only" rule and can't be paper-tested.
4. **Free first step:** watch other people's baits live to confirm the responder rates still hold today.

## API spend
- This task: $0.432 of the $40 cap (round 1 $0.274, round 2 $0.081, round 3 $0.069, test call $0.007).
- Ledger total for both studies: $0.762.
- Launch-labeling batch: $4.67.
