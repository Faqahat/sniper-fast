# GRAD: "buy near graduation, hold through it, sell N slots after migration" (agent grad, 10-28 ~23:30 PKT)

Code is in `/home/moiz/sniper/ops/strategies/e2x1_dissect/grad/` (`g1_decode.py`, `g2_build.py`, `g2b_full.py`, `g3_cov.py`, `g4_sim.py`, `g5_his.py`, `g6_eval.py`, `g7_pool.py`, `g8_cont.py`, `g9_robust.py`, `glib.py`).

Data is in `/home/moiz/sniper-data/e2x1_dissect/grad/` (1.1 GB). Results files there: `cov.log`/`cov.json`, `cont.txt`, `his.txt`, `eval.txt`, `robust.txt`, `pool_open.txt`, `curve_math.txt`.

Times are PKT. M = measured, I = inferred.

## 1. Coverage: are PumpSwap trades recorded? Yes (M)

**How the recorder works**
- It records every transaction that touches a mint created inside its window, PumpSwap ones included (`ops/collect/collect.py`).
- Pool events come from the "Program data" logs. Only the first 12 events of a transaction are kept.

**Reserve-chain test (`g8_cont.py`)**
- Pool base reserves are exact integers that only trades change. So in each pool, the reserve after one recorded event must equal the reserve before the next one; a missing trade shows up as a break.
- Over 2,741 normal SOL graduations (first 2 min after migration) there are 1,770,650 consecutive event pairs and 615 breaks (0.03%).
- In 13% of pools the very first pool trade(s) are missing. These are big bundled first buys inside transactions with more than 12 events.
- Every later event carries the full pool reserves, so the pool state is exact again from the next recorded trade.

**Public RPC check (`g3_cov.py`)**
- I checked 11 graduated tokens (6 E2x1 GRAD tokens and 5 random ones), first 2 min after migration, using getSignaturesForAddress on the pool.
- The recorder holds 8,773 trade transactions for these pools.
- RPC listed 28,652 further successful transactions that we did not record. I sampled 210 of them and none contained a PumpSwap trade; they are bots touching the pool without trading.
- On 3 busy pools, RPC's own listing missed some recorded trades (for example 240 of 445 for FuK9). RPC is the incomplete side there.

**E2x1's sells**
- All 33 of his D0/D1 PumpSwap sells are in the tape.
- The SOL out in each event equals the lots.pkl proceeds to the lamport. lots.pkl came from wallet balance changes, independent of my decoder.

**Decode note (M)**
- The PumpSwap event field `pool_quote_token_reserves` is 17.58 SOL lower than the reserve used for pricing. MigrateV2 sends 67.41 SOL to the pool vault and 17.59 SOL to a second account; pricing uses about 85 SOL.
- I derive the real reserve from each trade's own amounts. Replaying his 33 sells from the previous event's state reproduces his SOL out to within 0.002 SOL.

## 2. E2x1's GRAD lots reproduced (M, `his.txt`)

**Entries**
- Curve vSOL 39–109, token age 4 s to 67 min.
- 11 to 2,817 slots before the curve completed.

**Timing around graduation**
- Curve complete → migration: 0–3 slots (one case 11).
- His sell: migration +42 to +49 slots in 28 of 33 lots, and +6 to +10 in the other 5. This looks like a ~47-slot timer from migration (I).

**P&L**
- My replay matches lots.pkl: D0 +12.04, D1 +17.79.
- The same tokens sold at other times after migration:

| sell at | D0 | D1 |
|---|---|---|
| his actual (~+47 slots) | +12.04 | +17.79 |
| migration +2 slots | +12.86 | +14.19 |
| migration +48 slots | +10.83 | +17.94 |
| migration +100 slots | +9.65 | +20.55 |

- The ~10 s hold after migration added −0.8 (D0) and +3.6 (D1).
- So the profit is the graduation premium: the gap between his curve entry price and the pool-open price.
- The exec report's "≈0 with a 2-slot exit" means 2 slots after his buy, which is before graduation.

**Examples**
- [FuK9BkA4](https://gmgn.ai/sol/token/FuK9BkA4jXTBzj8HQRQT4538gy1BJzPYy9qwiHs2pump): in at vSOL 75, sold at migration +46, +0.703. [buy](https://solscan.io/tx/23dyML3ZgBsQLy8o3ePEdYVY1Ss6wgDXMWcYaMK9dFqQ6hVo3DTSvdNpj3tN3qtCLsCdfDyeukkNtzH4VicUj1xp) / [sell](https://solscan.io/tx/2edW96u7GiEU1iZW6wLyxE5cGFiRAX4RHwXzEhuT91CgrZGZ2sWLtpHJVeuqHFSNSTRJiEEAw1uvMGfyi6GhrnLb)
- [DA4yHG5X](https://gmgn.ai/sol/token/DA4yHG5XdywG7ZSAWffKZet3cH7JQamjEJwRC3vVXN5X): in at vSOL 58, sold at migration +44, +1.625. [sell](https://solscan.io/tx/26sPMTHpzeQwYpwUSgD4X9VS1eWPi2JcKdJ9ps8yciiDtUpPRLWFEHRur1a5fQFYi8ALAbmDx5zXNdzBdp5dCWSL)
- [27F4ADeE](https://gmgn.ai/sol/token/27F4ADeEKDJ7FhdgduVYLknhNLAUVKkM8ZPVCc4Wpump): in at vSOL 91, sold at migration +49, +0.905. [sell](https://solscan.io/tx/4jq6fBL6pan7VuzVgNsi9WtDpujxzsD8sAWDUdjUerAeVcsExXRGUCLdzYQK1mw1pqbSwNzqmKQfvKm7qj4dMKD6)
- [H8WTqu1S](https://gmgn.ai/sol/token/H8WTqu1SeuYrgdQEguGBVQory7uXesVFuPVAZDjnpump): in at vSOL 97, sold at migration +46, +0.431. [sell](https://solscan.io/tx/4daAtVJnJJyRKjb2F4MNQ9m3vd1Ng4Yt5yQLCXfHY62vHBpZ3NP9muUUduNvH13Cb5MMf8wdnnMhq5Y6cW79CzKy)
- [CqeWWnUn](https://gmgn.ai/sol/token/CqeWWnUnQdxWysTDDS8T3DqXLvwNiRPLpV1h1imCpump): in at vSOL 106, sold at migration +47, +0.037. [sell](https://solscan.io/tx/HnhTD8tNq5BDssi56cSxMWaECmWXX3Rgwi8jzbLYjtL5MW6jhAwsvS9csE4NapkEzWP1HSZFPVnEvstkybfuGWT)

**His selection: all D0+D1 lots bought near graduation**

| entry vSOL | lots | token graduated | held through graduation | sold before graduation | did not graduate |
|---|---|---|---|---|---|
| 80–90 | 59 | 51% | 5 | 25 | 29 lots, −6.60 |
| 90–100 | 34 | 71% | 8 | 16 | 10 lots, −2.30 |
| 100–110 | 14 | 93% | 8 | 5 | 1 lot, −0.15 |

- His tokens graduate at about the market rate (64–92% at V=80–105, section 3).
- So he does not pick graduators at entry (I). What differs is his curve exit: he gets out of most non-graduators early. The exec report shows that exit signal belongs to the token, not to his position.

## 3. Strategy universe

Train days were 10-24 to 10-26; test days were 10-27 and 10-28 (to ~20:35). Nothing was chosen on test.

**Setup (M on the tape)**
- **Universe:** every non-mayhem pump.fun token whose curve first crosses V vSOL, including tokens that later fail.
- **Entry:** our buy lands after the live landing-delay distribution, scaled to a 66 ms median (10 quantiles). +5% price guard; pump fees 125 bps.
- **If it graduates:** sell at migration + N slots (plus the landing delay) into the real pool state, with pool fees of about 1.23%.
- **If it does not:** stop-loss of −10%, −20% or none, combined with a timeout of 30 s, 2 min, 10 min or 30 min.
- **Costs:** 2.9 mSOL per round trip; 0.5 mSOL per reverted or late buy.
- **Tape depth:** the first pass only kept curve trades at vSOL ≥ 45. That hid the crashes of failed tokens and inflated results by about +5 to +20 SOL/day, so I redid it with every curve trade.

**Universe**

| V | tokens/day | graduate | crossing trade itself completes the curve (can't enter) | we land after completion | guard revert |
|---|---|---|---|---|---|
| 80 | 726 | 64% | 30% | 11% | 20% |
| 90 | 615 | 75% | 37% | 12% | 11% |
| 100 | 542 | 86% | 44% | 11% | 7% |
| 105 | 505 | 92% | 49% | 12% | 7% |

**Train grid**
- Every (V, size) combination loses on train even with its best exit.
- The best is −1.7 SOL/day: V=105, 0.5 SOL, sell 100 slots after migration, −20% stop, 30 min timeout.
- That rule on the test days:

| day | entries | graduated | P&L graduated | P&L failed | net SOL | per entry | 90% CI |
|---|---|---|---|---|---|---|---|
| 10-27 | 265 | 82% | +11.85 | −5.79 | +6.05 | +0.023 | [+1.6, +10.9] |
| 10-28 | 190 | 78% | +5.20 | −7.52 | −2.32 | −0.012 | [−6.7, +2.7] |

- Test mean +1.9/day, worst day −2.3. The train days were +1.4, −4.3 and −2.2.

**E2x1-like hold (sell 48 slots after migration, no stop, 30 min timeout, 1 SOL), test SOL/day**

| V | all tokens |
|---|---|
| 80 | −41.2 |
| 90 | −12.7 |
| 100 | −3.2 |
| 105 | −5.2 |

- At V=90, the tokens that graduated alone would have made +90.8/day; the failed ones lost −103.5/day.
- Holding pays only on tokens that graduate. Knowing in advance which ones will is the whole edge.

**Selection variant (net buy SOL in the last 10 s ≥ X)**
- Chosen on train: V=105, 1 SOL, X=20, sell 100 slots after migration, −20% stop, 2 min timeout.
- Train +1.2/day; test +4.0 and +4.2/day, about 40 entries/day at roughly +0.10 SOL each.

| day | SOL | entries |
|---|---|---|
| 10-23 (evening only) | +1.1 | 14 |
| 10-24 | +1.9 | 48 |
| 10-25 | +3.4 | 36 |
| 10-26 | −1.7 | 49 |
| 10-27 | +4.0 | 42 |
| 10-28 | +4.2 | 36 |

- Without its 5 best trades: train −0.18, test −0.70.
- **Lower V:** with X=20, V=90/95/100 make −5.0, −2.9 and −0.7/day on train but +8.9 to +9.6/day on test. That points to different market conditions on the test days, not a stable edge.
- **Exit timing:** selling 48 slots after migration gives −0.05/day on train; 5 slots after gives −0.8/day.
- **Stricter flow:** X=30 or 40 gives +1.8 and +2.0/day on train, +5.1 and +5.0/day on test, about 25 entries/day.

**Curve maths (M, `curve_math.txt`)**
- Return from a curve buy at V, sold into the opening pool after fees:

| entry V | 0.5 SOL | 1 SOL | 2 SOL |
|---|---|---|---|
| 90 | +57% | +55% | +50% |
| 100 | +27% | +26% | +23% |
| 105 | +16% | +14% | +12% |

- A 1 SOL buy fills only 0.94–1.10% above spot on the curve.
- Selling into the 85 SOL pool costs another 1.4–1.8% at 1 SOL.
- Size is not the problem near graduation; the losses on tokens that don't graduate are.

## 4. Caveats

**Migration timing is predictable (M)**
- Migration lands 0 slots after curve completion at the median, 2 at the 90th percentile, 32 at most.

**Competition at pool open (M)**
- In the first 5 slots after migration: median 13 buys and 32 SOL bought, no sells.
- Half of all normal graduations are self-bundled: one group creates the token, buys the whole curve, migrates and buys 150–190 SOL in the pool, all in the same slot. We cannot enter these; they are in the "crossing trade completes the curve" share.
- Pool price 48 slots after migration vs open: ×2.5 median over all graduations, but ×1.09 for the tokens our rule enters.

**Modelling limits**
- Our sell landing is modelled at the 66 ms median. The +100-slot exit is not sensitive to it.
- In the sim, our buy does not change who completes the curve (I). Pool reserves at open are fixed, so this matters little.

**Recorder blind spots**
- Tokens near the edges of a recording window were dropped (1,388 rows).
- 48 completions had no recorded migration.
- About 3.5% of curve trades are missed (version 1 transactions, a known gap).

## 5. If anyone still wants to test it (no live run started)

**Paper rule**
1. Non-mayhem token.
2. Trigger: the first curve buy that takes vSOL to ≥105 without completing the curve.
3. Filter: net buy SOL over the last 47 slots ≥ 20.
4. Buy 1 SOL with a +5% guard.
5. If the curve completes, sell everything 100 slots after the migration slot.
6. Otherwise sell on a −20% mark-to-market stop or after 2 min.

**What the paper engine must log**
- Our landing slot and index vs the crossing trade.
- Whether we landed before the curve completed.
- The migration slot.
- Pool reserves at our sell, using the derived reserve, not the event field.
- Our fill vs the replay.

**Expected:** about 0 to +4 SOL/day at 1 SOL (test +4.1, train +1.2, ≈0 without the top 5 trades).