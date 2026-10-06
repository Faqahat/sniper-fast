# Rival dossier: 26b966Mh, how it finds and picks pools

**Date:** 2026-10-06. **Subject:** wallet `26b966MheUKjyRTes8vLbpH1qV6pVY7cNzAiyZuyrB9W`. Read-only; nothing was signed or sent.

**Sources.** The window is its last 1,000 transactions, 05:45–15:52 UTC (10.1 h).
- **[W]** `getSignaturesForAddress` on the wallet, with block positions.
- **[B]** the same on its PumpSwap user-volume-accumulator PDA `9BNbq3Es…`, which every buy writes (18/18 decoded buys, 0/55 sells): 5,000 buys back to 10-02 10:47.
- **[T]** its token accounts' signatures for 140 tokens, explaining 745 window transactions.
- **[R]** ≈330 decoded transactions; **[P]** pool signatures before its trades; **[RPC]** its balances.
- **[M]** pump.fun's migration account `39azUYFW…`: 1,000 signatures, 40 decoded.
- **[DS]** DexScreener; its `pairCreatedAt` matched the on-chain pool creation in 14/14 checks. **[J]** Jito's bundle explorer.

*Inference* marks what is not measured directly. Cost: 662 public-RPC requests (54 of them 429 retries), ≈175 DexScreener and 12 Jito lookups. Working files (28 MB) are in `/home/moiz/arbx-offload/rival-26b9/`.

## 1. Bottom line

- **Not an arbitrageur.** Every decoded swap transaction is one PumpSwap buy or one sell, so the token never nets to zero. It is a directional, reactive trader: it buys ≈1.3% of a pool's SOL reserve right after someone else's large sell, and sells ≈1% into later buys (mean reversion is the *inferred* intent).
- **One kind of pool.** All 114 pools it traded are canonical pump.fun-migrated PumpSwap/WSOL pools (creator = pump.fun's `pool-authority` PDA, index 0) [R].
- **Discovery is event-driven; trading is not early.** It creates its token account p50 79 s after a migration, for a sixth to a third of migrations. It then never buys within 30 minutes (first buy p50 79.5 min after the pool's creation) and keeps trading a token for p50 18 h.
- **For arbx:** 63% of its tokens have a single SOL pool, so there is nothing to arbitrage on them. What carries over is the mechanism: hot-add pairs from creation events. None of its activity is in pools under 30 minutes old; 11% is under 2 h and 72% under 24 h.

## 2. Arbitrage or directional?

**Window mix** [W, B, T, R]. ≈904 of the 1,000 transactions are its own: 424 PumpSwap buys (384 succeeded; all 40 failures are `ExceededSlippage`, 6004), ≈390 sells and ≈90 token-account creations (`createIdempotent`, no swap). The other ≈96 are others' pump.fun `DistributeFeeToHolders` cranks, which pay it as a holder (0–1.53M lamports each; 26 failed), and one OTC offer. The sell, ATA and crank counts extrapolate a sample of 12 of the 149 unexplained successes.

| Measure | Value | Src |
|---|---|---|
| Token net per swap tx | Never zero: each tx is one buy or one sell | R |
| Closed round trips (18 tokens bought and flat in the window) | 33 buys of 19.60 SOL, 33 sells of 20.18 SOL. Net **+0.50 SOL** after fees, tips and ATA rent: +2.6% of the SOL put in, +0.015 SOL per buy | R |
| Win rate | 11 of 18 tokens; per token −0.24 to +0.28 SOL | R |
| Holding (first buy → last sell) | 0.8–360 min, p50 76 min on closed tokens. Open positions run for days (§4) | R, T |
| Cash (SOL + WSOL) | 544.9 → 573.4 SOL, 05:56–16:00; includes inventory changes, so not P&L | R |
| Per hour (*inference*) | ≈0.6 SOL/h: 38 successful buys/h × 0.015 | |
| Cost per trade | Priority fee 1.2M µlamports/CU on a 150–160k CU limit (63% of txs), plus a tip of 300k lamports (71%) or 1M (18%) | R |
| Capital | 38.69 SOL native and 534.94 WSOL. 16,857 token accounts (16,743 empty) lock 32.1 SOL of rent | RPC |

The first look's "1.7 swaps per transaction", "8 bonding-curve swaps" and 935/1,000 success rate do not hold for its own transactions. *Inference:* PumpSwap's self-CPI event and others' cranks were counted. Its pump.fun accumulator PDA `F9HM5qT7…` has no signatures.

## 3. Route shape and triggers

| Item | Finding | Src |
|---|---|---|
| Legs | One top-level PumpSwap swap per tx, quoted in WSOL. No program of its own, no second pool, no curve trades | R |
| Buy trigger | 21 of 23 first buys follow another wallet's sell of ≥0.5 SOL, in the same slot (17) or the previous one. The sell: p50 2.98 SOL (IQR 2.47–4.27), 7.7% of the pool's SOL (IQR 4.5–22%). Sellers: 15 wallets in 16 cases, mostly retail via terminals (*inference*; `FLASHX8D…` in 7) | P, R |
| Repeat buys, sells | 5 of 7 repeat buys follow a same-slot sell of 1.0–3.9 SOL. 7 of 11 sells follow another wallet's buy of 0.08–1.98 SOL within one slot (2 unknown) | P, R |
| Position | p50 126 txs after the nearest earlier pool tx in the same slot (p10 5, min 2): fast, not an idx+1 backrun. One `getBlock` (1,025 txs) confirmed the indices: sell at 157, its buy at 206 | P |
| Size | First buy p50 1.27% of the post-sell SOL reserve (IQR 1.09–2.46%); 0.18–1.35 SOL (p10–p90). Repeat buys and sells: 1.0–1.5% | R |
| Sender | Tips: Astralane 79%, Jito 20%, Helius Sender once. Jito's explorer shows 3 of 6 Astralane-tipped txs as one-tx bundles: no trigger inside | R, J |

No schedule apart from the 30-minute embargo (§4), and no new-pool trigger: it never trades a second pool.

## 4. Pool selection

### 4.1 The funnel

| Stage | Measure | Src |
|---|---|---|
| Universe: pump.fun migrations | ≈59/h. `39azUYFW…` had 1,000 signatures in 10.1 h, 68% successful; 35 of 40 decoded successes are migrations | M |
| Watch list: its token account (ATA) | 10 of 30 sampled migrations got one, always made by itself 4–284 s after the migration. Wallet side: ≈9 creations/h, against ≈20/h implied by 10/30 (CI 17–53%) | M, W |
| ATA lag after pool creation | p10 9 s, p50 79 s, p90 529 s (n = 140, DS). On-chain, n = 24: 4 s – 22 min, p50 129 s | DS, P |
| What it skips | Instant bonders (curve completed within seconds of launch): 11 of the 30 sampled migrations, none with an ATA, and 2 of its own 88 tokens. The 10 with ATAs bonded in 0.3–58 min (p50 14.6) and now show 2.4× the 24-h volume of the rest | M, DS |
| First buy | Never within 30 min. After the pool's creation: min 30.4, p10 34.6, p25 42.7, **p50 79.5**, p75 239, p90 490 min, max 23.6 h (n = 112). 8 of the 10 sampled ATAs were bought later | B, T, DS |
| Token age at first buy | p10 41, p50 110, p90 831 min (n = 61) | DS |
| Pool at first buy | SOL reserve p50 32.9 (IQR 7.7–77.1), against 67.4 at migration. Price p50 0.28× the migration price (IQR 0.03–1.24×). Pool txs in the minute before: p50 15 (IQR 5–136) | R, P |
| Lifetime of interest | First buy → last trade: p50 18 h (IQR 6.9–25.3, p90 60 h) for the 57 tokens it stopped; 55 were still active at the window end | T |

### 4.2 Activity by pool age

Its 312 window buys on identified tokens (81% of the 384 successful buys) [B, T, DS]:

| Pool age at the buy | <30 min | 30–60 min | 1–2 h | 2–6 h | 6–24 h | 1–3 d |
|---|---|---|---|---|---|---|
| Share of buys | 0% | 6.7% | 4.5% | 17.0% | 43.3% | 28.5% |

Now the traded pools hold p50 33 SOL (IQR 9–72), with 24-h volume p50 $245k (IQR $91k–631k) [DS].

### 4.3 Overlap with our discovery

- **Coverage:** 20 of its 141 pools are in `cov/pools.json` (14%; 18.8% of its window txs). pooldisco's 14:57 `candidates-tradeable.csv` has 16 of its pools, covering 14 of its 112 traded tokens.
- **Why pooldisco misses them** (112 traded tokens):

| Class | Tokens | Its txs |
|---|---|---|
| One SOL pool (PumpSwap only): no cross-pool gap, excluded by design (`st.pools.len() < 2`) | 63% | 55% |
| Second SOL pool below 0.3 SOL (`MIN_DEPTH`) | 11% | 12% |
| Two SOL pools of ≥0.3 SOL, but not a candidate: no gap in its run, or created later | 13% | 17% |
| In pooldisco's candidates | 12.5% | 16% |

- **Second pools** [DS]: 51 of the 140 tokens have one, first appearing p50 12 min after migration (IQR 5.8–34). Pools: DLMM/SOL 66, DAMM v2/SOL 31, plus USDC/USDT ones; liquidity p50 $97 (p75 $1.3k, p90 $16k).

## 5. Inferred discovery mechanism (*inference*)

1. **Source:** a listener on pump.fun migrations (`MigrateV2`, which runs PumpSwap `create_pool`), the only source of its 114 pools.
2. **First filter, within seconds to minutes:** it mostly skips instant bonders and dead pools, and pre-creates the ATA for the rest, so a later buy needs no account creation (150–160k CU). One of its 16,857 token accounts dates from 07-26, 9 s after that pool's creation.
3. **Trigger:** after a 30-minute embargo, a sell of ≈8% of the SOL reserve → it buys ≈1.3% in the same or next slot; buys by others → it sells ≈1%.
4. **Exit:** it drops a pool when trading dies (p50 18 h).

No volume scan, no copied wallet.

## 6. What arbx can learn

1. **Hot-add pairs from creation events (top recommendation).**
   - **Detect** these instructions in the shred feed: pump.fun `MigrateV2` (discriminator `bbcb121fceedfe29`), PumpSwap `create_pool` (`e992d18ecf6840bc`), and DLMM and DAMM v2 pool initialisations.
   - **Pair by mint without a lookup.** A pump mint's canonical PumpSwap pool is `PDA(["pool", 0u16, PDA(["pool-authority", mint], pump.fun), mint, WSOL], PumpSwap)`. This matched 114/114 of its pools.
   - **Add a pair** once a mint has two pools on our venues with ≥0.3 SOL each: snapshot the new accounts with one `getMultipleAccounts` (`pools::boot` at runtime), add them to the state-stream watch list and WP-04's consistency sets, and price only after the first committed update.
   - **Evict** after ≈24 h without a swap (its lifetime p50 18 h, p90 60 h).
   - This is the coverage-breadth proposal's creation decoder, narrowed to one cheap case; WP-14's discovery connection can carry it.
2. **Use its filters as priors.** Deprioritise instant bonders, and rank by pool activity (its first buys saw p50 15 txs/min). Its 30-minute embargo is a risk rule for directional trades; arbitrage does not need it.
3. **Value (*inference*; measure before building).**
   - **By pool age:** its activity on pools under 1 h old is 6.7%, under 6 h 28%, under 24 h 72%. An hourly refresh would reach ≈93% of it and hot-add 100%; a daily one misses most of these pools' active life.
   - **Events:** a third of its txs are on tokens with a second SOL pool of ≥0.3 SOL, and ≈87% of its buys follow a large sell (≈33/h). That gives ≈11 such sells per hour on two-pool tokens.
   - **Profit:** an 8%-of-reserve sell moves PumpSwap ≈15%, leaving ≈12% against an untouched second pool after fees. pooldisco's estimator (depth × g²/4) gives ≈0.004 SOL per event at 1 SOL depth and ≈0.025 at 7 SOL: ≈0.04–0.3 SOL/h gross, before tips and rivals.
   - **Measure first:** a day of creation events and big PumpSwap trades from the discovery connection, joined with second-pool depth.
4. **It is a rival on the PumpSwap side of those gaps** (*inference*): it lands p50 126 txs after the sell, in the same slot, and takes ≈1.3% of the reserve, so a slower arbx backrun finds a smaller gap.
5. **Do not copy its strategy.** It carries inventory risk (7 of 18 round trips lost, down to −0.24 SOL), which our atomic design avoids.

## 7. Limits

- **Sampling:** the token search favours tokens with many trades; 255 window txs stay unidentified.
- **P&L** comes from 18 closed tokens only; the cash trend mixes in inventory.
- **Triggers** rest on 25 first buys, 7 repeat buys and 11 sells; the large sells it ignores were not counted.
- **DS values** (liquidity, volume, second pools) are from ≈16:20 UTC, not trade time.
