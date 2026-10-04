# Profitable arbitrage on our pools: patterns (w5h-p1..p15, 2026-10-03 18:46-21:28 UTC)

Scope: 15 live segments, 2.47 h of recording on Cherry. Everything below is aggregate statistics from public transactions we recorded (rivals.jsonl, exec.jsonl, moves.log, txarr/poh, our attempts/outcomes), plus trade sizes for wins of 0.01 SOL or more from getTransaction (1,395 calls). Scripts: `scan.py`, `sizes.py`, `analyze.py`, `extra.py`. These were arb-lab tools run on Cherry and were removed from arbx on 2026-10-04 (arbx is standalone); they are in git history under tools/analysis/patterns/.

## Definitions and caveats (read first)
- **Win** = a successful transaction by another signer that touched at least one watched pool, where the signer's SOL+WSOL went up and no other token balance was left over. "Gain" is the signer's net after fees and tips. "Gross" = gain + fee + tip.
- **Removed from the universe:**
  - 11,314 "wins" that touched no watched pool (217 SOL; pump.fun migrations and similar).
  - 27 one-off position exits through Jupiter by signers with fewer than 20 arb-like txs (155 SOL).
  - 47 non-arb "claims", where the gain was more than 25% of the SOL that moved through the pools (173 SOL; farmnFYo, LPGn4GRU, CoAjARag, FR3kVwdX...).
  - Our own 2 wins.
- **What is left:** **10,644 wins, 67.2 SOL net, 4,314/h, 27.3 SOL/h.** Without these filters the totals are about 6x too high (the seg.py "rivals took" numbers include some of them).
- **Gap age** = time from the last successful tx that touched any of the win's watched pools (the state change that opened the gap) to the win. 97% of values come from first-arrival times at Cherry (txarr.log). PoH times exist for only about 2% of these txs. Shreds arrive in execution order, so the error is a few ms.
  - When only one leg of the arb is on a watched pool, the gap may have opened on the unwatched pool, so the "slow slice" below uses only wins that touched at least 2 watched pools.
- **Not seg.py's "ms after trigger":** that number is measured from the first trigger of a multi-slot episode, so it makes wins look much later than they were. The exp4 claim of "0.92 SOL/h reachable" relied on it.
- **Bot fee and tip totals** come from txs that have an execution record. That is 63% of the arb-like txs seen in shreds, so failed-tx fees are undercounted by about a third.
- **Small samples:** segments p3, p8, p11 and p13 are 1-2 min long. Per-segment rates from them are noisy.
- **Possible real arbs in the claims filter:** it also removed 3 large 8oSD5a9E wins on a USDC route (10 SOL, gain 50-70% of size, probably first arbs of a mispriced new pool). Two were same-slot at under 0.03 ms, so the reachable-slice answer is unchanged.

## Top 10 patterns
1. **Big wins are same-slot backruns.** 552 wins of 0.01 SOL or more (224/h, 24.8 SOL/h). 91% landed in the same slot as the state change that opened the gap.
   - Gap age p50 is 1.6 ms; 48% are under 1 ms, 74% under 20 ms and 94% under 150 ms.
   - For wins of 0.1 SOL or more (94 wins, 38/h, 19.5 SOL/h): 88% same slot, p50 1.8 ms.
   - In 90% of cases the previous state change was another bot's arb, so most big wins are second- or third-round arbs inside the same block.
2. **One bot takes more than half.** MriyaNN8 has 59% of big-win SOL (66% of wins of 0.1 SOL or more). The top 3 bots have 69% (78%) and the top 5 have 74% (83%). The median big win had 28 other bots landing txs on the same pools in its window.
   - MriyaNN8: 194 big wins, 36.1 SOL, gap age p50 0.0 ms, 82% durable nonce, no tip, priority p50 170k lamports, bid about 1% of gross.
   - Its overall net is +38.7 SOL in 2.47 h (about 15.7 SOL/h).
3. **Big wins need size.** Median trade size is 2.3 SOL for wins of 0.01 SOL or more and 10.6 SOL for wins of 0.1 SOL or more.
   - Trades of 8.4 SOL or more: 57 wins, 35.3 SOL (64% of the SOL among wins with a known size).
   - All size bands up to 4.2 SOL together: 310 wins, 9.9 SOL (4.0 SOL/h), median gain 0.015-0.028 SOL, gap age p50 0.9-5.5 ms.
4. **One venue pair, a few tokens.** DLMM<->PumpSwap carries 85% of big-win SOL (52.2 of 61.3 SOL; 375 of 552 wins).
   - Top tokens: 7VertkgF 24.0 SOL, 9dSMwFfP 7.7, XLBLxbY1 6.9, H7TuvDxE 2.9, GAwhcphC 2.7, DvdmEnzt 1.4.
   - The top token is 25-87% of each segment's SOL. 7VertkgF was active in all 15 segments (25.3 SOL); some tokens flare for 2-3 segments (DvdmEnzt, BL1ujbX7).
5. **The path decides how much of the gross the winner keeps.** For gross wins of 0.01 SOL or more (707 wins, 88.6 SOL gross):
   - No-tip winners bid 13% of gross, with gap age p50 0.9 ms.
   - Jito-tipped winners bid 71% of gross (159 wins, 24.95 SOL gross; 15.9 ms, 84% same slot).
   - The Jito auction gives most of the value to the tip. One bundle-only bot paid 39.5 SOL in tips on 39.5 SOL gross.
6. **The slow slice is small.** Gross wins of 0.01 SOL or more with gap age of 150 ms or more, both legs watched: 34 wins in 2.47 h.
   - That is 13.8/h, 1.0 SOL/h gross and 0.6 SOL/h net to the winners. Median size is 2.5 SOL, and MriyaNN8 has 11 of the 34.
   - Restricted to net of 0.01 SOL or more and size up to 4.2 SOL: 9 wins, 0.40 SOL (0.16 SOL/h). At 300 ms or more: 6 wins, 0.29 SOL (0.12 SOL/h).
7. **Small wins (under 0.01 SOL) are numerous but worth little.** 4,090/h market-wide, 2.4 SOL/h, median 36k lamports.
   - 47% are Jito-only: tip p50 9k lamports, 31% of gross, gap age p50 58 ms, only 60% in the same slot. This is our niche, and it is slower.
   - Small wins with gap age of 150 ms or more: 560/h but only 0.094 SOL/h (median 4.6k lamports). 70% are Jito, and 59% are on DAMMv2<->PumpSwap.
8. **Our results fall with size.** 31 wins in 6,167 live attempts (0.5%).
   - Bundle win rate by size: 1.44% under 0.05 SOL, 0.39% at 0.05-0.2, 0.09% at 0.2-1, and 0 of 901 at 1 SOL or more.
   - Where we did win, our share of the market's small wins on those pools is about 1%.
   - Our attempts are spread differently from the market's wins: DLMM<->DAMMv2 got 939 attempts and 0 wins; DAMMv2<->PumpSwap got only 7% of our attempts but holds 37% of market small Jito wins.
9. **Volume does not pay; selectivity does.** Of 965 bots with 20 or more arb txs (2 wash/volume bots that lost 39 SOL in LP fees excluded), 91 are net-positive. The top 10 made +62.5 SOL, and all bots together made +22.8 SOL.
   - Multi-sender sprayers: -11.4 SOL net (2,724 wins/h at a 0.54% win rate).
   - Bundle-only bots break even (gross 42.7 SOL, tips 42.5 SOL).
   - No-tip sprayers are net +25.9 SOL only because of MriyaNN8; without it they are negative.
   - Profitable non-Mriya bots are mid-volume: 8oSD5a9E +11.1 SOL at 651 tx/h, 4BQ6ATUt, Bgokg3ju, DtvmxrTA.
10. **Higher fees do not win more on their own; profitable snipers scale the bid to the gap.**
    - Within the same bot, the top priority-fee bucket wins more than the bottom one in 6 bots and less in 6.
    - The profitable snipers put their largest bids (over 1M lamports) on their best shots: MriyaNN8 49% vs 28-34%; 8oSD5a9E 93% vs 2-14%; 9EwQoN74 94% vs 4-18%.
    - Jito-tipped txs win 36% with tips of 100k-1M lamports, vs about 2% at 100k or less. This is confounded by gap size (bigger gaps get bigger bids), not proof that a bigger tip wins.
    - Crowding: the median big win had 28 other bots landing txs on the same pools in its window (p90 44). Our win rate is 0.9% on pools with 5-20 bots and 0.4% on pools with 150 or more, yet 49% of our attempts went to the 21 pools with 150 or more bots.

## Is any big-win slice reachable at our speed? How big?
**Yes, but it is small.** We act about 15 ms after the trigger and land 100-250 ms after sending. 94% of big wins came within 150 ms of the state change, and 91% were in the same slot.

| Slice of the reachable part (both legs watched) | Wins/h | SOL/h |
|---|---|---|
| Gross 0.01 SOL or more, gap age 150 ms or more | 13.8 | 1.0 gross, 0.6 net to winners |
| Same, net 0.01 SOL or more and size up to 4.2 SOL (our wallet) | 3.6 | 0.16 |
| Same, at 300 ms or more | 2.4 | 0.12 |

What this slice looks like:
- Mostly DLMM<->PumpSwap memecoins: 7VertkgF, 9dSMwFfP, GAwhcphC and similar.
- Median size 2.5 SOL (p25 1.6, p75 7.6). 94% landed in a later slot than the state change.
- Winners paid priority p50 670k lamports (bid about 33% of gross), mostly with no tip.
- Median 15 other bots also landed txs in the window, so these gaps were contested even when old.
- MriyaNN8 again takes about a third of them.

A realistic capture at our speed is 10-30% of this slice, about **0.02-0.1 SOL/h**. The exp4 target of 0.92 SOL/h "reachable" does not hold once the timing is measured from the last state change.

## 5 recommendations (prioritized)
1. **Persistence re-check instead of big sends at the trigger.**
   - Change: never send 1 SOL or more at the trigger (0 wins in 901 attempts; the winners of those gaps had gap age p50 4 ms and 91% were in the same slot). Instead, re-price the pair from the next slot's state (+400-800 ms). Only if the gap is still there, send at a size of 1-4.2 SOL, as a Jito bundle with a tip of about 35-50% of gross, or as a direct send with a priority fee near the slow-slice winners' level (p50 670k lamports).
   - Expected impact: this is the only big-win slice we can reach, about 3-14 opportunities/h and up to 0.16-1.0 SOL/h at market level. Realistically +0.02-0.1 SOL/h. It also frees the 5 bundles/s limiter from the 901 sends that had no chance.
2. **Small sizes and slow venues for the bundle niche.**
   - Change: cap state-trigger bundles at about 0.05-0.2 SOL. Our win rate is 1.44% below 0.05 SOL vs 0.09% at 0.2-1 SOL.
   - Move attempt budget from DLMM<->DAMMv2 (939 attempts, 0 wins) and the 150+-bot pools to DAMMv2<->PumpSwap and DLMM<->PumpSwap memecoin pools. Those hold 59% and 15% of the market's slow (150 ms or more) small wins and 37% and 19% of small Jito wins; we spend 7% of attempts there.
   - Expected impact: 2-3x our win count (about 12/h to 25-35/h). Value stays tiny (under 0.01 SOL/h), because the market's whole slow small-win pool is 0.094 SOL/h.
3. **Bid tiers that match the winners, not a flat 70%.**
   - Change: about 30-35% of gross for small Jito gaps. Small Jito winners pay p50 31% (19-45% by gap-age band). Use 35-50% only on persistent big gaps (rec 1).
   - Why it is safe: we lose on state, not on the auction (4,479 would-fail vs 88 accepted bundles).
   - Expected impact: +35-40% net per small win at the same win count.
4. **A rotating hot-token list.**
   - Change: rank tokens every 10 min by market arb SOL on our pools (from the exec/rivals records we already write). Give the bundle budget and pool discovery to the current top 3-5 tokens and add their new pools automatically. The top token is 25-87% of each segment's SOL; 7VertkgF was worth 25 SOL across all 15 segments, and new tokens flare for 2-3 segments.
   - Expected impact: more attempts where the money is. It mainly multiplies the effect of recs 1 and 2.
5. **No paid direct sends until rec 1 exists.**
   - Change: stop paid direct sends. They produced 0 wins in 239 landed sends. Big wins are 89% same-slot with gap age p50 1.8 ms, so no priority or tip level fixes a 100-250 ms landing delay. Within-bot data also shows that fees do not buy wins by themselves.
   - Expected impact: saves about 0.5-1.1M lamports per segment in failed fees (p12/p14), with no loss of wins.

---
# Data tables (generated by analyze.py / extra.py)
Notes on the tables:
- The crowding table's "market SOL" counts a win on every watched pool it touched, so it double-counts. It also includes the excluded claims. Use its win counts, not its SOL.
- In Q6, "winner size" is known only for wins of 0.01 SOL or more, so in the small bands it reflects only the larger winners.

## Raw analysis output (analyze.py)

Observation: 15 segments, 2.47 h of recording (w5h-p1..p15, 18:46-21:28 UTC).
Excluded: 11314 'wins' not touching any watched pool (217.5 SOL: pump.fun migrations etc.), 27 one-off Jupiter position exits by signers with <20 arb-like txs (154.7 SOL), 47 non-arb 'claims' (gain > 25% of SOL through the pools, or signer mostly so: ['6vUfHdop', 'CoAjARag', 'FR3kVwdX', 'HFiPuqzz', 'LPGn4GRU', 'farmnFYo']; 173.16 SOL), our own 2 wins.
UNIVERSE: 10644 profitable round trips by other bots on our pools, 67.23 SOL net (4314/h, 27.25 SOL/h)
timing source of gap age: {'arrival': 10265, None: 153, 'poh': 226}

## Q1 BIG WINS
| metric | >= 0.01 SOL | >= 0.1 SOL |
|---|---|---|
| wins | 552 | 94 |
| wins per hour | 223.7 | 38.1 |
| SOL total (net to winner) | 61.28 | 47.98 |
| SOL per hour | 24.84 | 19.45 |
| distinct winning bots | 79 | 28 |
| top-1 bot share of SOL | 59% | 66% |
| top-3 share | 69% | 78% |
| top-5 share | 74% | 83% |
| trade size SOL p10/p25/p50/p75/p90 | 0.47 / 0.95 / 2.29 / 5.18 / 10.59 | 2.81 / 4.98 / 10.59 / 15.18 / 23.39 |
| net gain SOL p25/p50/p75/p90 | 0.015 / 0.025 / 0.068 / 0.163 | 0.128 / 0.235 / 0.488 / 0.831 |
| gap age ms (win - last state change on its pools) p10/p25/p50/p75/p90 | 0.0 / 0.0 / 1.6 / 20.4 / 59.3 | 0.0 / 0.0 / 1.8 / 23.5 / 168.7 |
| share landed in the SAME slot as the state change | 91% | 88% |
| share gap age < 1 / 7 / 20 / 50 / 150 / 300 ms | 48% / 61% / 74% / 88% / 94% / 95% | 47% / 57% / 71% / 88% / 89% / 91% |
| previous state change was another bot's arb | 90% | 87% |
| durable nonce share | 45% | 38% |
| priority fee p50 (lamports) | 13,471 | 7,674 |
| tip p50 (lamports) | 0 | 0 |
| share with any tip | 35% | 27% |
| (prio+tip)/gross profit p50 | 1% | 0% |
| (prio+tip)/gross p25/p75/p90 | 0% / 34% / 49% | 0% / 6% / 35% |
| landed arb txs on the same pools in window (copies) p50 | 64 | 80 |
| other bots landing txs in window p50 | 28 | 31 |
| other bots p25/p75/p90 | 18 / 37 / 44 | 20 / 39 / 44 |
| winner's own extra copies p50 | 1 | 1 |

per segment (big wins >= 0.01 SOL / >= 0.1 SOL):
| seg | UTC | min | wins>=0.01 | SOL | /h | wins>=0.1 | SOL | top bot (share) |
|---|---|---|---|---|---|---|---|---|
| w5h-p1 | 18:46-19:06 | 20 | 74 | 6.48 | 19.57 | 17 | 4.73 | MriyaNN8 (49%) |
| w5h-p2 | 19:06-19:11 | 5 | 13 | 3.56 | 40.65 | 2 | 3.31 | MriyaNN8 (89%) |
| w5h-p3 | 19:12-19:14 | 2 | 14 | 1.79 | 46.46 | 3 | 1.47 | MriyaNN8 (81%) |
| w5h-p4 | 19:15-19:35 | 20 | 50 | 2.54 | 7.66 | 6 | 1.19 | MriyaNN8 (64%) |
| w5h-p5 | 19:35-19:41 | 6 | 15 | 0.84 | 8.92 | 4 | 0.60 | MriyaNN8 (54%) |
| w5h-p6 | 19:41-19:50 | 9 | 24 | 2.72 | 18.00 | 3 | 2.17 | MriyaNN8 (57%) |
| w5h-p7 | 19:51-20:11 | 20 | 70 | 14.75 | 44.55 | 12 | 13.10 | MriyaNN8 (74%) |
| w5h-p8 | 20:18-20:19 | 2 | 6 | 0.13 | 4.67 | 0 | 0.00 | 9EwQoN74 (31%) |
| w5h-p9 | 20:20-20:27 | 7 | 26 | 1.76 | 14.35 | 2 | 1.06 | MriyaNN8 (57%) |
| w5h-p10 | 20:28-20:48 | 20 | 54 | 8.94 | 26.98 | 16 | 7.85 | MriyaNN8 (70%) |
| w5h-p11 | 20:48-20:49 | 1 | 10 | 0.67 | 41.78 | 2 | 0.46 | 7dGrdJRY (40%) |
| w5h-p12 | 20:50-20:57 | 7 | 38 | 3.89 | 32.96 | 8 | 2.96 | MriyaNN8 (46%) |
| w5h-p13 | 20:57-20:58 | 1 | 6 | 0.58 | 28.96 | 1 | 0.41 | DsCJ5siu (71%) |
| w5h-p14 | 20:59-21:07 | 8 | 72 | 7.84 | 58.41 | 8 | 5.79 | FUJKrQhx (47%) |
| w5h-p15 | 21:08-21:28 | 20 | 80 | 4.78 | 14.44 | 10 | 2.87 | MriyaNN8 (54%) |

top bots (>= 0.01 SOL wins):
| bot | wins | SOL | median gain | median size | gap age p50 ms | same-slot | nonce | path (tip service) | prio p50 | tip p50 | bid/gross p50 | other bots in window p50 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MriyaNN8 (Mriya) | 194 | 36.09 | 0.027 | 2.62 | 0.0 | 89% | 82% | no tip:178, jito:11 | 169,571 | 0 | 1% | 27 |
| FUJKrQhx | 3 | 3.73 | 0.416 | 4.98 | 0.5 | 67% | 0% | no tip:2, helius:1 | 8,463 | 0 | 0% | 42 |
| DtvmxrTA | 27 | 2.50 | 0.021 | 0.91 | 35.1 | 85% | 100% | jito:10, no tip:9 | 147,089 | 7,480,349 | 24% | 25 |
| 6AGp6zbG | 5 | 1.54 | 0.038 | 2.57 | 11.2 | 100% | 100% | no tip:2, jito:1 | 100,000 | 9,471,670 | 20% | 36 |
| 4BQ6ATUt | 21 | 1.43 | 0.026 | 1.90 | 0.0 | 95% | 0% | unknown-tip:21 | 0 | 1,000,000 | 4% | 29 |
| A9pQ1Qsv | 14 | 1.20 | 0.073 | 4.07 | 17.4 | 100% | 0% | no tip:12, unknown-tip:2 | 0 | 0 | 0% | 34 |
| Bgokg3ju | 24 | 1.14 | 0.023 | 2.85 | 10.6 | 96% | 0% | jito:16, no tip:8 | 0 | 340,000 | 2% | 31 |
| DsCJ5siu | 12 | 1.08 | 0.051 | 5.00 | 15.2 | 100% | 0% | no tip:9, jito:3 | 17,619 | 0 | 0% | 12 |
| CzYQ2kFn | 27 | 1.04 | 0.022 | 1.19 | 15.6 | 85% | 0% | no tip:27 | 11,007 | 0 | 0% | 7 |
| 8oSD5a9E | 22 | 0.89 | 0.018 | 4.22 | 2.4 | 100% | 5% | no tip:13, jito:5 | 25,365,702 | 0 | 70% | 30 |
| 6Ta1LBdn | 6 | 0.84 | 0.185 | 6.72 | 24.2 | 100% | 0% | no tip:6 | 10,196 | 0 | 0% | 43 |
| 3KvsoNxg | 8 | 0.82 | 0.070 | - | 10.1 | 88% | 38% | jito:5, no tip:2 | 0 | 39,850 | 0% | 31 |

size bands (>= 0.01 SOL wins with a fetched size):
| size band SOL | wins | SOL | median gain | gap age p50 ms | share gap >= 150 ms |
|---|---|---|---|---|---|
| 0-0.2 | 6 | 0.12 | 0.021 | 18.0 | 17% |
| 0.2-1 | 113 | 2.13 | 0.015 | 5.5 | 4% |
| 1-2.1 | 99 | 3.59 | 0.023 | 0.9 | 7% |
| 2.1-4.2 | 92 | 4.10 | 0.028 | 1.3 | 4% |
| 4.2-8.4 | 88 | 10.17 | 0.048 | 0.5 | 10% |
| 8.4-+ | 57 | 35.28 | 0.247 | 0.2 | 7% |
(sizes unknown for 97 wins)

venue sets (>= 0.01 SOL): dlmm+pumpswap 52.19 SOL (375 wins); dammv2+dlmm+pumpswap 3.24 SOL (69 wins); dlmm+pumpswap+rayclmm 1.78 SOL (22 wins); dlmm+pumpswap+whirlpool 1.15 SOL (16 wins); pumpswap 0.90 SOL (35 wins); dammv1+dammv2+pumpswap+whirlpool 0.49 SOL (1 wins); pumpswap+rayclmm 0.25 SOL (11 wins); dammv1+dammv2+pumpswap 0.24 SOL (1 wins)

tokens (>= 0.01 SOL): 7VertkgF 23.95 SOL; 9dSMwFfP 7.68 SOL; XLBLxbY1 6.85 SOL; ? 6.64 SOL; H7TuvDxE 2.88 SOL; GAwhcphC 2.73 SOL; DvdmEnzt 1.40 SOL; 2AVjqmGb 1.36 SOL; CbcyNo7m 1.26 SOL; 98kfF7rm 1.24 SOL; BL1ujbX7 1.11 SOL; 9pJWJdpP 0.54 SOL

path (tip service) of big wins: no tip: 358 wins / 44.12 SOL; jito: 104 wins / 7.05 SOL; helius: 21 wins / 6.41 SOL; unknown-tip: 31 wins / 1.86 SOL; nozomi: 10 wins / 1.03 SOL; astralane: 24 wins / 0.73 SOL; nodeone: 3 wins / 0.07 SOL; blockrazor: 1 wins / 0.01 SOL

leader kind (>= 0.01): {'Jito': 346, 'BAM': 200, 'non-Jito': 6}  location: {'far>=30ms': 108, 'EU<30ms': 185, 'near<5ms': 45, 'sameDC<1ms': 141, '?': 73}

### The slow slice: big wins whose gap was older than our reaction (both legs on watched pools)
| slice (>= 0.01 SOL, n_watched >= 2) | wins | per hour | SOL | SOL/h | bots | top bot share | median size | median gain | same-slot | other bots p50 | tip-path mix | leader kinds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gap age 0-20 ms | 360 | 145.9 | 46.82 | 18.98 | 60 | 68% | 2.71 | 0.027 | 100% | 30 | no tip:245, jito:58, unknown-tip:26 | {'Jito': 235, 'BAM': 121, 'non-Jito': 4} |
| gap age 20-50 ms | 65 | 26.3 | 5.54 | 2.24 | 34 | 32% | 2.14 | 0.026 | 98% | 23 | no tip:36, jito:25, nozomi:1 | {'Jito': 33, 'BAM': 31, 'non-Jito': 1} |
| gap age 50-150 ms | 26 | 10.5 | 1.99 | 0.81 | 17 | 69% | 1.07 | 0.019 | 50% | 23 | no tip:15, jito:9, nozomi:1 | {'Jito': 14, 'BAM': 12} |
| gap age 150-300 ms | 5 | 2.0 | 0.69 | 0.28 | 4 | 81% | 1.60 | 0.028 | 20% | 4 | no tip:3, blockrazor:1, astralane:1 | {'BAM': 1, 'Jito': 4} |
| gap age 300-+ ms | 12 | 4.9 | 0.73 | 0.30 | 4 | 74% | 2.54 | 0.046 | 0% | 17 | no tip:8, jito:2, astralane:2 | {'BAM': 4, 'Jito': 8} |
| gap age 150-+ ms | 17 | 6.9 | 1.42 | 0.58 | 8 | 39% | 2.54 | 0.041 | 6% | 15 | no tip:11, astralane:3, jito:2 | {'BAM': 5, 'Jito': 12} |

slow slice (>= 150 ms) detail: n=17; venue sets [('dlmm+pumpswap', 13), ('dlmm+pumpswap+rayclmm', 1), ('dlmm+pumpswap+whirlpool', 1), ('dlmm+pumpfun+pumpswap+rayclmm', 1), ('dammv2+dlmm+pumpswap', 1)]; tokens [('7VertkgF', 0.616), ('?', 0.258), ('JCsKWhEL', 0.161), ('8dBnKHwN', 0.151), ('2AVjqmGb', 0.085), ('98kfF7rm', 0.042), ('9dSMwFfP', 0.041), ('DvNcJZTi', 0.021)]; bots [('MriyaNN8', 9), ('CzYQ2kFn', 2), ('Bgokg3ju', 1), ('9EwQoN74', 1), ('GxDC9e7S', 1), ('R32xAccF', 1), ('DC99qH3j', 1), ('CbX3yk2g', 1)]; prev state change by an arb: 88%; size p25/p50/p75 ['1.60', '2.54', '7.60']; prio p50 670000; tip p50 0; bid/gross p50 33%; per segment {'w5h-p1': 3, 'w5h-p3': 1, 'w5h-p4': 1, 'w5h-p5': 1, 'w5h-p6': 1, 'w5h-p7': 2, 'w5h-p12': 2, 'w5h-p14': 1, 'w5h-p15': 5}

biggest slow-slice wins:
- w5h-p15 CbX3yk2g +0.559 SOL size 12.46 dlmm+pumpswap 7VertkgF gap age 169 ms (prev slot 453052480 -> win slot 453052481, idx 197) no tip tip 0 prio 430068590 leader Jito/sameDC<1ms other bots 1 prev-by-arb True
- w5h-p5 MriyaNN8 +0.161 SOL size 1.79 dlmm+pumpswap JCsKWhEL gap age 2461 ms (prev slot 453030196 -> win slot 453030205, idx 1173) no tip tip 0 prio 88275072 leader BAM/sameDC<1ms other bots 17 prev-by-arb False
- w5h-p1 MriyaNN8 +0.151 SOL size 7.82 dlmm+pumpswap 8dBnKHwN gap age 16123 ms (prev slot 453022447 -> win slot 453022507, idx 584) no tip tip 0 prio 78321603 leader BAM/EU<30ms other bots 15 prev-by-arb True
- w5h-p15 DC99qH3j +0.126 SOL size - dlmm+pumpfun+pumpswap+rayclmm ? gap age 13506 ms (prev slot 453051828 -> win slot 453051878, idx 1001) astralane tip 2500000 prio 670000 leader Jito/far>=30ms other bots 0 prev-by-arb True
- w5h-p15 CzYQ2kFn +0.085 SOL size 1.60 dammv2+dlmm+pumpswap 2AVjqmGb gap age 201 ms (prev slot 453052883 -> win slot 453052883, idx 1412) no tip tip 0 prio 44807 leader Jito/EU<30ms other bots 1 prev-by-arb True
- w5h-p1 MriyaNN8 +0.076 SOL size 7.60 dlmm+pumpswap+rayclmm ? gap age 79495 ms (prev slot 453021948 -> win slot 453022246, idx 802) no tip tip 0 prio 39322015 leader BAM/? other bots 15 prev-by-arb True
- w5h-p3 Bgokg3ju +0.057 SOL size 11.60 dlmm+pumpswap 7VertkgF gap age 305 ms (prev slot 453024419 -> win slot 453024420, idx 71) jito tip 2550000 prio 0 leader Jito/? other bots 35 prev-by-arb True
- w5h-p7 MriyaNN8 +0.046 SOL size 1.01 dlmm+pumpswap+whirlpool ? gap age 4552 ms (prev slot 453034945 -> win slot 453034962, idx 384) no tip tip 0 prio 1553318 leader Jito/sameDC<1ms other bots 18 prev-by-arb True
- w5h-p14 MriyaNN8 +0.041 SOL size 1.80 dlmm+pumpswap 9dSMwFfP gap age 305 ms (prev slot 453048811 -> win slot 453048812, idx 305) no tip tip 0 prio 40757600 leader Jito/EU<30ms other bots 10 prev-by-arb True
- w5h-p12 R32xAccF +0.028 SOL size 4.59 dlmm+pumpswap 98kfF7rm gap age 158 ms (prev slot 453046720 -> win slot 453046721, idx 14) astralane tip 2098500 prio 8433 leader Jito/sameDC<1ms other bots 18 prev-by-arb True
- w5h-p6 MriyaNN8 +0.021 SOL size 0.12 dlmm+pumpswap DvNcJZTi gap age 524 ms (prev slot 453031455 -> win slot 453031457, idx 24) jito tip 10802986 prio 0 leader BAM/far>=30ms other bots 31 prev-by-arb True
- w5h-p15 MriyaNN8 +0.014 SOL size 5.33 dlmm+pumpswap 98kfF7rm gap age 355 ms (prev slot 453051795 -> win slot 453051796, idx 894) no tip tip 0 prio 693443 leader Jito/sameDC<1ms other bots 23 prev-by-arb True

(one-watched-leg big wins, gap age unreliable: n=71, 3.78 SOL; share >= 150 ms 25%)
slow slice >= 150 ms AND size <= 4.2 SOL: 9 wins, 0.400 SOL (0.162 SOL/h, 3.6/h)
slow slice >= 300 ms AND size <= 4.2 SOL: 6 wins, 0.292 SOL (0.118 SOL/h, 2.4/h)

## Q2 SMALL WINS (< 0.01 SOL)
market: 10092 wins (4090/h), 5.951 SOL (2.412 SOL/h), median gain 35661 lamports
Jito-tipped-only: 4760 (47%), 1.181 SOL; tip p25/p50/p75 [1849, 8971, 49053]; tip/gross p50 31%; gap age p50 58.2 ms; same slot 60%
no-tip: 4649 (46%), 3.882 SOL; prio p50 6726; gap age p50 17.7 ms
small wins by venue set: dammv2+pumpswap: 2899; dlmm+pumpswap: 2675; dammv2+dlmm+pumpswap: 1694; pumpswap: 1017; pumpswap+rayclmm: 197; dlmm+pumpswap+rayclmm: 157; pumpswap+raycpmm: 156; dlmm+pumpswap+whirlpool: 119
small Jito wins by venue set: dammv2+pumpswap: 1760; dlmm+pumpswap: 907; dammv2+dlmm+pumpswap: 652; pumpswap: 412; pumpswap+raycpmm: 131; pumpswap+rayclmm: 114
small wins top tokens: ?: 3036; 7VertkgF: 1393; H7TuvDxE: 914; 9dSMwFfP: 687; 2AVjqmGb: 646; CJ7yfNkt: 364; GAwhcphC: 286; CbcyNo7m: 266; 6NwarBvD: 255; 9cRCn9rG: 160
small-win gap age p25/p50/p75/p90: ['4.4', '32.1', '116.8', '359.7']; share >= 150 ms 21%
OURS: 31 wins, -0.02199 SOL net; size p50 0.025 SOL; tip p50 10270; pairs [('Dlmm>Dlmm', 17), ('Dlmm>PumpSwap', 5), ('PumpSwap>Dlmm', 2), ('PumpSwap>DammV2', 2), ('Dlmm>RayCpmm', 2), ('Dlmm>RayAmmV4', 1)]; tokens [('EPjFWdd5', 14), ('6GmAFSYs', 3), ('J9d68or9', 2), ('CJ7yfNkt', 2), ('GAwhcphC', 1), ('H7TuvDxE', 1)]
market small wins on the pools where we won at least once: 4104 (3.509 SOL); our share of wins there: 1%; Jito-tipped among them 34%
our wins per segment: {'w5h-p3': 2, 'w5h-p6': 2, 'w5h-p7': 8, 'w5h-p9': 2, 'w5h-p10': 7, 'w5h-p11': 1, 'w5h-p12': 1, 'w5h-p14': 3, 'w5h-p15': 5}

## Q3 VOLUME vs RESULTS by strategy type (other bots, all segments)
volume/wash-like signers excluded (ok round trips losing more than fees+tips, i.e. LP fees; few wins): 2, their losses -39.01 SOL; e.g. ['AgmLJBMD', 'Gygj9QQb']
| path | volume | bots | arb txs/h | landed | win/landed | wins/h | gross won SOL (gain+fees+tips on wins) | fees+tips spent SOL | net SOL | net SOL/h | profitable bots | median bot net SOL |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| no-tip(TPU/prio) | sprayer(>=1000/h) | 27 | 489,365 | 73% | 0.58% | 2074 | 59.39 | 22.83 | 25.91 | 10.50 | 5 | -0.0249 |
| multi-sender | mid(100-1000/h) | 46 | 16,857 | 46% | 13.20% | 1016 | 18.01 | 10.56 | 10.79 | 4.38 | 9 | -0.0006 |
| single tip-sender | mid(100-1000/h) | 17 | 9,493 | 43% | 2.40% | 98 | 3.50 | 4.52 | 0.93 | 0.38 | 3 | -0.0074 |
| single tip-sender | sprayer(>=1000/h) | 15 | 37,726 | 44% | 2.78% | 463 | 4.20 | 4.62 | 0.26 | 0.10 | 3 | -0.0268 |
| bundle-only | sniper(<100/h) | 16 | 465 | 26% | 69.73% | 83 | 0.13 | 0.12 | -0.04 | -0.02 | 8 | 0.0000 |
| no-tip(TPU/prio) | mid(100-1000/h) | 22 | 7,770 | 51% | 10.22% | 408 | 0.22 | 0.25 | -0.20 | -0.08 | 3 | -0.0001 |
| no-tip(TPU/prio) | sniper(<100/h) | 71 | 1,868 | 24% | 6.22% | 28 | 0.04 | 0.19 | -0.29 | -0.12 | 4 | 0.0000 |
| bundle-only | mid(100-1000/h) | 14 | 4,879 | 59% | 44.78% | 1282 | 42.67 | 42.48 | -0.52 | -0.21 | 5 | 0.0000 |
| single tip-sender | sniper(<100/h) | 81 | 1,660 | 56% | 4.25% | 39 | 0.10 | 2.81 | -0.55 | -0.22 | 9 | 0.0000 |
| bundle-only | sprayer(>=1000/h) | 7 | 63,122 | 68% | 0.36% | 153 | 0.96 | 1.52 | -0.59 | -0.24 | 1 | -0.0357 |
| multi-sender | sniper(<100/h) | 575 | 11,579 | 51% | 2.35% | 138 | 0.38 | 53.01 | -1.48 | -0.60 | 27 | 0.0000 |
| multi-sender | sprayer(>=1000/h) | 74 | 833,875 | 61% | 0.54% | 2724 | 36.47 | 50.52 | -11.38 | -4.61 | 14 | -0.0419 |

bundle-only bots (>= 90% of txs Jito-tipped), top by gross: ESuvjvsQ: 113 tx/h, 55 wins, gross 39.515, tips 39.521, net -0.457; rLsi2DPw: 243 tx/h, 268 wins, gross 2.741, tips 2.613, net 0.167; 66666y3R: 17,065 tx/h, 208 wins, gross 0.399, tips 0.193, net 0.006; Luckywzb: 19,894 tx/h, 75 wins, gross 0.262, tips 0.220, net -0.143; XUrKb2aK: 8,771 tx/h, 87 wins, gross 0.249, tips 0.484, net -0.330; GocsRvL8: 139 tx/h, 173 wins, gross 0.137, tips 0.125, net 0.001

top 15 bots by net (other bots):
| bot | type | arb txs/h | landed | ok | wins | win/landed | gross SOL | fees+tips SOL | failed-tx fees SOL | net SOL | nonce | paths |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MriyaNN8 (Mriya) | no-tip(TPU/prio) / sprayer(>=1000/h) | 1,804 | 52% | 42% | 851 | 36.71% | 45.592 | 7.019 | 1.611 | 38.680 | 95% | no tip:93%, unknown-tip:4%, jito:3% |
| 8oSD5a9E | multi-sender / mid(100-1000/h) | 651 | 51% | 25% | 193 | 23.59% | 13.582 | 2.498 | 0.075 | 11.148 | 8% | nozomi:79%, no tip:16%, jito:6% |
| FUJKrQhx | multi-sender / sprayer(>=1000/h) | 32,907 | 79% | 44% | 31 | 0.05% | 3.797 | 0.767 | 0.413 | 3.039 | 0% | no tip:47%, helius:25%, jito:20% |
| 4BQ6ATUt | single tip-sender / mid(100-1000/h) | 203 | 46% | 100% | 72 | 31.44% | 2.110 | 0.230 | 0.000 | 1.902 | 0% | unknown-tip:100% |
| DtvmxrTA | multi-sender / sprayer(>=1000/h) | 2,053 | 49% | 7% | 118 | 4.77% | 4.082 | 2.769 | 0.957 | 1.865 | 100% | no tip:80%, unknown-tip:12%, astralane:3% |
| Bgokg3ju | multi-sender / mid(100-1000/h) | 236 | 50% | 100% | 122 | 42.07% | 1.816 | 0.280 | 0.000 | 1.536 | 0% | jito:66%, no tip:34% |
| 4DcT8f8V | multi-sender / sprayer(>=1000/h) | 24,331 | 30% | 41% | 14 | 0.08% | 1.775 | 0.362 | 0.086 | 1.415 | 39% | no tip:62%, unknown-tip:13%, nozomi:9% |
| 6AGp6zbG | multi-sender / sprayer(>=1000/h) | 4,359 | 44% | 7% | 302 | 6.45% | 15.532 | 14.079 | 0.147 | 1.400 | 95% | no tip:61%, unknown-tip:24%, jito:5% |
| 9EwQoN74 | single tip-sender / sprayer(>=1000/h) | 1,006 | 62% | 15% | 224 | 14.61% | 3.008 | 2.372 | 0.200 | 0.813 | 86% | no tip:85%, unknown-tip:6%, astralane:3% |
| HL2kH8ya | multi-sender / sprayer(>=1000/h) | 3,395 | 47% | 2% | 74 | 1.89% | 0.908 | 0.149 | 0.063 | 0.734 | 99% | no tip:84%, nextblock:15%, jito:1% |
| 7dGrdJRY | multi-sender / sprayer(>=1000/h) | 5,771 | 45% | 6% | 110 | 1.70% | 1.362 | 1.458 | 0.458 | 0.512 | 99% | no tip:81%, nozomi:12%, unknown-tip:3% |
| 6Ta1LBdn | multi-sender / sprayer(>=1000/h) | 9,865 | 89% | 100% | 26 | 0.12% | 0.866 | 0.343 | 0.000 | 0.510 | 0% | no tip:65%, jito:35% |
| GxDC9e7S | multi-sender / sprayer(>=1000/h) | 4,225 | 52% | 15% | 504 | 9.32% | 0.855 | 0.588 | 0.296 | 0.285 | 86% | no tip:76%, unknown-tip:10%, nozomi:6% |
| Hg4zYYx3 | single tip-sender / mid(100-1000/h) | 640 | 50% | 1% | 9 | 1.15% | 0.294 | 0.041 | 0.032 | 0.252 | 0% | helius:100% |
| EDZQHk2M | single tip-sender / mid(100-1000/h) | 886 | 58% | 0% | 3 | 0.24% | 0.242 | 0.027 | 0.027 | 0.215 | 100% | helius:100% |

biggest losers (net):
- DsCJ5siu multi-sender/sprayer(>=1000/h): 114,041 txs/h, wins 96, gross 1.358, failed fees 0.000, net -1.531 SOL
- Dy1jE82C multi-sender/sprayer(>=1000/h): 157,529 txs/h, wins 242, gross 0.614, failed fees 0.755, net -2.934 SOL
- CzYQ2kFn no-tip(TPU/prio)/sprayer(>=1000/h): 235,153 txs/h, wins 541, gross 2.020, failed fees 0.009, net -3.144 SOL
- VLXFRyxh multi-sender/sprayer(>=1000/h): 13,379 txs/h, wins 16, gross 0.100, failed fees 0.362, net -4.674 SOL
- VLXAMxYR multi-sender/sprayer(>=1000/h): 13,447 txs/h, wins 18, gross 0.177, failed fees 0.338, net -5.017 SOL
- DeFG8i8z no-tip(TPU/prio)/sprayer(>=1000/h): 34,225 txs/h, wins 612, gross 7.561, failed fees 0.022, net -6.124 SOL
bots with >= 20 arb txs: 965; net-positive 91; total net 22.82 SOL; top-10 net 62.53 SOL
exec coverage: arb-like txs seen in shreds that have an execution record: 63% (fees of the rest are not counted)

## Q4 FEES THAT WIN
win rate per landed arb tx by priority fee paid (lamports), by path:
| priority fee | no-tip: landed | win% | jito: landed | win% | other senders: landed | win% |
|---|---|---|---|---|---|---|
| 0 | 17,487 | 10.04% | 241,877 | 3.81% | 14,206 | 2.61% |
| <=1000 | 538,192 | 0.46% | 120,211 | 0.42% | 96,564 | 0.25% |
| <=10000 | 577,639 | 0.46% | 122,550 | 0.23% | 202,657 | 0.12% |
| <=100000 | 341,485 | 0.74% | 6,620 | 1.36% | 106,034 | 0.36% |
| <=1000000 | 67,618 | 1.02% | 1,180 | 0.51% | 33,775 | 0.22% |
| >1000000 | 2,602 | 20.18% | 16 | 12.50% | 2,199 | 0.32% |

win rate of Jito-tipped (no other sender) landed txs by tip:
| tip lamports | landed | wins | win% |
|---|---|---|---|
| 0 | 0 | 0 | 0.00% |
| <=10000 | 310,267 | 6,313 | 2.03% |
| <=100000 | 108,740 | 2,568 | 2.36% |
| <=1000000 | 2,227 | 795 | 35.70% |
| <=10000000 | 70,945 | 336 | 0.47% |
| >10000000 | 275 | 84 | 30.55% |

win rate by leader kind and path:
- Jito: no tip: 7180/999316 = 0.72%; jito: 6553/363500 = 1.80%
- BAM: no tip: 3251/520621 = 0.62%; jito: 3532/127150 = 2.78%
- non-Jito: no tip: 133/21967 = 0.61%; jito: 0/1157 = 0.00%

within-bot (same bot, wins vs losses) — win rate by the bot's own priority-fee bucket (bots with >= 500 landed txs):
| bot | 0 | <=1000 | <=10000 | <=100000 | <=1000000 | >1000000 | tip buckets used (win% by tip bucket) |
|---|---|---|---|---|---|---|---|
| MriyaNN8 | 71.8% (156) | 27.3% (110) | 33.7% (433) | 28.0% (504) | 33.9% (799) | 49.1% (291) | 0:35.0%(2129) <=1000000:47.6%(42) <=10000000:50.0%(80) |
| 8oSD5a9E | 97.9% (48) | - | - | 1.8% (330) | 14.0% (279) | 92.7% (82) | 0:90.4%(125) <=1000000:7.6%(353) <=10000000:9.6%(219) >10000000:15.6%(45) |
| DeFG8i8z | 0.0% (2084) | 0.8% (79259) | 0.0% (3096) | - | - | - | 0:0.7%(83483) <=10000:0.0%(875) <=1000000:0.0%(36) <=10000000:0.0%(45) |
| FUJKrQhx | 0.1% (13468) | 0.0% (8932) | 0.0% (33206) | 0.1% (8541) | 0.0% (118) | - | 0:0.0%(30268) <=10000:0.1%(26670) <=100000:0.2%(2617) <=10000000:0.0%(4681) |
| DtvmxrTA | 63.2% (38) | - | - | 4.1% (1355) | 3.8% (816) | 3.0% (234) | 0:2.4%(1906) <=1000000:8.0%(276) <=10000000:20.2%(193) >10000000:17.6%(68) |
| CzYQ2kFn | - | 0.1% (192189) | 0.1% (170783) | 0.2% (84822) | 0.3% (1443) | - | 0:0.1%(431414) <=10000:0.1%(11735) <=100000:0.1%(5189) <=10000000:0.0%(452) >10000000:0.0%(452) |
| 6AGp6zbG | 90.6% (310) | - | 0.4% (3284) | 0.6% (1024) | 0.0% (38) | - | 0:0.5%(2604) <=100000:90.2%(194) <=1000000:15.6%(493) <=10000000:2.9%(1013) >10000000:2.3%(352) |
| 4DcT8f8V | - | 0.0% (8921) | 0.0% (7431) | 0.2% (1785) | - | - | 0:0.1%(7380) <=10000000:0.0%(4696) >10000000:0.0%(6063) |
| DsCJ5siu | 0.0% (54628) | 0.0% (41225) | 0.0% (104113) | 0.1% (46472) | - | - | 0:0.0%(191810) <=10000:0.0%(36482) <=100000:0.1%(18146) |
| 9EwQoN74 | 5.9% (960) | 3.9% (154) | - | - | 17.6% (279) | 93.5% (108) | 0:14.1%(1232) <=10000000:9.3%(258) |
| 7dGrdJRY | 15.0% (207) | 1.1% (1688) | 0.6% (476) | 1.0% (3437) | 1.2% (606) | 33.3% (51) | 0:1.3%(5161) <=1000000:1.1%(1031) <=10000000:12.0%(225) >10000000:13.3%(30) |
| 3KvsoNxg | 0.2% (13988) | 0.0% (49) | 0.0% (13368) | 0.2% (17295) | 0.0% (87) | - | 0:0.2%(13804) <=10000:0.0%(806) <=100000:0.2%(13170) <=1000000:0.1%(10007) <=10000000:0.1%(1412) >10000000:0.0%(5588) |
| 6Ta1LBdn | - | 0.1% (4875) | 0.1% (8562) | 0.2% (8204) | - | - | 0:0.1%(15714) <=10000:0.0%(2675) <=100000:0.2%(3252) |
| HL2kH8ya | 63.4% (41) | 2.3% (1831) | 0.3% (1461) | 0.2% (517) | 0.0% (67) | - | 0:1.4%(3083) <=100000:4.8%(377) <=1000000:3.0%(399) <=10000000:0.0%(62) |
within-bot: highest-priority bucket wins more often than lowest in 6 bots, less in 6, similar in 2

bid (priority+tip) as share of gross profit, by win size:
| gross band SOL | wins | bid/gross p25 | p50 | p75 | no-tip share | jito share |
|---|---|---|---|---|---|---|
| 0-0.0001 | 5388 | 9% | 17% | 45% | 38% | 61% |
| 0.0001-0.001 | 2678 | 2% | 15% | 69% | 56% | 36% |
| 0.001-0.01 | 1871 | 1% | 12% | 69% | 57% | 23% |
| 0.01-0.1 | 591 | 0% | 9% | 48% | 58% | 24% |
| 0.1-+ | 116 | 0% | 0% | 34% | 72% | 14% |

## Q5 TIME and REGIME
| seg | UTC | min | arb wins/h | SOL/h (all sizes) | big wins/h | top token share of SOL | top token | bots winning | our live attempts | our wins |
|---|---|---|---|---|---|---|---|---|---|---|
| w5h-p1 | 18:46-19:06 | 20 | 3961 | 22.22 | 223 | 34% | 7VertkgF | 121 | 917 | 0 |
| w5h-p2 | 19:06-19:11 | 5 | 2691 | 42.84 | 148 | 85% | XLBLxbY1 | 72 | 187 | 0 |
| w5h-p3 | 19:12-19:14 | 2 | 4234 | 49.50 | 364 | 87% | 9dSMwFfP | 58 | 149 | 2 |
| w5h-p4 | 19:15-19:35 | 20 | 4079 | 10.16 | 151 | 27% | 9dSMwFfP | 125 | 444 | 0 |
| w5h-p5 | 19:35-19:41 | 6 | 3091 | 10.50 | 159 | 58% | 7VertkgF | 73 | 143 | 0 |
| w5h-p6 | 19:41-19:50 | 9 | 2823 | 19.64 | 159 | 52% | 7VertkgF | 73 | 131 | 2 |
| w5h-p7 | 19:51-20:11 | 20 | 3050 | 46.71 | 211 | 51% | 7VertkgF | 120 | 381 | 8 |
| w5h-p8 | 20:18-20:19 | 2 | 6667 | 7.27 | 211 | 29% | GAwhcphC | 52 | 115 | 0 |
| w5h-p9 | 20:20-20:27 | 7 | 5746 | 17.19 | 213 | 54% | BL1ujbX7 | 94 | 1182 | 2 |
| w5h-p10 | 20:28-20:48 | 20 | 5833 | 29.42 | 163 | 54% | 7VertkgF | 128 | 762 | 7 |
| w5h-p11 | 20:48-20:49 | 1 | 8263 | 47.11 | 621 | 52% | 9pJWJdpP | 56 | 81 | 1 |
| w5h-p12 | 20:50-20:57 | 7 | 6521 | 35.80 | 322 | 44% | XLBLxbY1 | 107 | 450 | 1 |
| w5h-p13 | 20:57-20:58 | 1 | 5561 | 30.71 | 298 | 68% | 2AVjqmGb | 41 | 53 | 0 |
| w5h-p14 | 20:59-21:07 | 8 | 6453 | 62.81 | 537 | 53% | 7VertkgF | 126 | 513 | 3 |
| w5h-p15 | 21:08-21:28 | 20 | 3463 | 16.09 | 242 | 25% | 7VertkgF | 126 | 659 | 5 |

token lifetimes (top 12 tokens by SOL, all sizes): SOL per segment
- 7VertkgF9K: total 25.30 SOL, active in 15 segments: p1:2.47, p2:0.28, p3:0.11, p4:0.60, p5:0.58, p6:1.55, p7:7.95, p8:0.02, p9:0.25, p10:5.29, p11:0.00, p12:0.44, p13:0.03, p14:4.43, p15:1.31
- 9dSMwFfPez: total 8.43 SOL, active in 13 segments: p1:2.00, p2:0.08, p3:1.65, p4:0.92, p5:0.15, p6:0.01, p7:0.70, p9:0.00, p10:0.02, p11:0.00, p12:0.00, p14:1.96, p15:0.94
- ?: total 7.21 SOL, active in 15 segments: p1:0.32, p2:0.09, p3:0.08, p4:0.11, p5:0.05, p6:0.07, p7:5.03, p8:0.01, p9:0.02, p10:0.71, p11:0.24, p12:0.02, p13:0.05, p14:0.07, p15:0.33
- XLBLxbY1Mr: total 6.95 SOL, active in 12 segments: p1:0.08, p2:3.21, p3:0.02, p4:0.03, p6:0.83, p7:0.00, p10:0.76, p11:0.00, p12:1.84, p13:0.08, p14:0.00, p15:0.08
- H7TuvDxEKy: total 3.81 SOL, active in 14 segments: p1:0.49, p2:0.05, p3:0.02, p4:0.51, p5:0.02, p6:0.09, p7:0.66, p9:0.25, p10:1.08, p11:0.00, p12:0.17, p13:0.02, p14:0.22, p15:0.24
- GAwhcphCqC: total 2.90 SOL, active in 14 segments: p1:1.38, p2:0.00, p3:0.02, p4:0.66, p5:0.01, p6:0.01, p7:0.67, p8:0.06, p9:0.00, p10:0.00, p11:0.00, p12:0.00, p14:0.02, p15:0.07
- 2AVjqmGbMq: total 1.91 SOL, active in 8 segments: p8:0.04, p9:0.31, p10:0.76, p11:0.04, p12:0.07, p13:0.42, p14:0.10, p15:0.18
- CbcyNo7m1a: total 1.49 SOL, active in 12 segments: p1:0.00, p2:0.00, p3:0.00, p4:0.02, p6:0.00, p7:0.01, p8:0.00, p9:0.00, p10:0.16, p12:0.15, p14:0.45, p15:0.67
- DvdmEnztCm: total 1.40 SOL, active in 2 segments: p14:0.85, p15:0.56
- 98kfF7rmsg: total 1.32 SOL, active in 8 segments: p1:0.00, p4:0.00, p7:0.00, p10:0.01, p12:1.25, p13:0.00, p14:0.04, p15:0.01
- BL1ujbX7DM: total 1.14 SOL, active in 3 segments: p8:0.01, p9:1.13, p12:0.00
- 9pJWJdpPeb: total 0.64 SOL, active in 8 segments: p4:0.00, p5:0.00, p9:0.00, p10:0.00, p11:0.40, p12:0.15, p14:0.02, p15:0.07

crowding: pools binned by number of distinct arb signers that touched them (all night):
| arb bots on pool | pools | market wins | market SOL | wins per pool | our attempts | our wins | our win% |
|---|---|---|---|---|---|---|---|
| 1-5 | 525 | 355 | 0.04 | 0.7 | 91 | 0 | 0.0% |
| 5-20 | 362 | 1540 | 0.79 | 4.3 | 338 | 3 | 0.9% |
| 20-60 | 236 | 4808 | 102.49 | 20.4 | 1156 | 9 | 0.8% |
| 60-150 | 118 | 7266 | 231.27 | 61.6 | 4641 | 27 | 0.6% |
| 150-+ | 21 | 9515 | 169.78 | 453.1 | 6108 | 23 | 0.4% |

## Q6 CONTRAST: our attempts vs the winners of the same gaps
our live attempts: 6167; verdicts {'not-landed': 5903, 'landed-fail': 233, 'WIN': 31}; arms {'tpu': 1129, 'bundle': 5038}; jito verdicts {'would-fail': 4479, 'accepted': 88}
lost attempts with a profitable winner on the same pools within 5 slots: 2988 of 6136
| our size band | lost w/ winner | our size p50 | our expected p50 | our tip p50 | our send ms p50 | winner gain p50 | winner size p50 | winner gap age p50 ms | winner same-slot | winner path mix | winner bid p50 | winner gain / our expected p50 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0-0.1 | 1093 | 0.036 | 115,742 | 47,036 | 14.3 | 68,840 | 4.35 | 16.2 | 83% | no tip:602, jito:429, astralane:36 | 16,134 | 0.66 |
| 0.1-1 | 1200 | 0.289 | 1,453,996 | 988,563 | 14.5 | 545,007 | 0.84 | 6.3 | 89% | no tip:712, jito:354, astralane:60 | 40,078 | 0.46 |
| 1-4.3 | 695 | 2.996 | 23,890,653 | 7,369,256 | 15.6 | 3,560,828 | 3.89 | 4.0 | 91% | no tip:418, jito:174, astralane:45 | 121,000 | 0.29 |

our attempts >= 1 SOL: 1157; with a profitable winner within 5 slots: 695; winner gain >= 50% of our expected: 265; our expected p50 17304384; jito verdicts {'would-fail': 835, None: 321, 'accepted': 1}
winners of our >= 1 SOL attempts: gap age p25/p50/p75 ['0.0', '4.0', '23.0']; same-slot 91%; top winners [('MriyaNN8', 145), ('CzYQ2kFn', 40), ('9EwQoN74', 26), ('8oSD5a9E', 26), ('DtvmxrTA', 25), ('Bgokg3ju', 22)]; path [('no tip', 418), ('jito', 174), ('astralane', 45), ('unknown-tip', 25)]

seg.py 'denied' lists (p4,p6,p7,p10,p12; winner timing vs the opportunity's trigger): n=1242; winner ms p25/p50/p75 ['0.9', '31.7', '95.2']; our first send ms p50 14.7; winner later than our send 62%; winner size p50 0.15 SOL; profit p50 0.00029 SOL; our expected p50 996,020

## Extra checks (extra.py): gross-based big wins, slow slices, our size gradient

```
gross>=0.01: 707 88.61 net 62.07 bid 26.53
no tip 428 gross 51.0 bid share of gross 0.13 gap p50 0.875355 same-slot 0.9 >=150ms 16 1.932
jito 159 gross 24.95 bid share of gross 0.71 gap p50 15.880103 same-slot 0.84 >=150ms 7 0.259
other 120 gross 12.66 bid share of gross 0.19 gap p50 1.828036 same-slot 0.81 >=150ms 11 0.311
gross>=0.01 & gap>=150 & 2 legs: 34 gross 2.502 net 1.497 per h 13.8 1.014
 bots [('MriyaNN8', 11), ('GxDC9e7S', 3), ('CzYQ2kFn', 2), ('8oSD5a9E', 2), ('Bgokg3ju', 1), ('rLsi2DPw', 1)] svc [('no tip', 16), ('jito', 7), ('astralane', 4), ('unknown-tip', 4)] size p50 2.544305076
ESuvjvsQ wins 16 gross 0.0 gap p50 224.706742 same slot 6 vp [('dammv2+pumpswap', 5), ('pumpswap+raycpmm+whirlpool', 4), ('pumpswap+rayammv4', 2)] size None
small jito gap 0 20 1306 529 SOL 0.714 tip p50 13206 tip/gross 0.19 gain p50 38061
small jito gap 20 50 777 315 SOL 0.215 tip p50 20588 tip/gross 0.45 gain p50 16556
small jito gap 50 150 1081 438 SOL 0.118 tip p50 9148 tip/gross 0.37 gain p50 6576
small jito gap 150 300 651 264 SOL 0.044 tip p50 6536 tip/gross 0.38 gain p50 3221
small jito gap 300 1000000000.0 766 310 SOL 0.06 tip p50 3662 tip/gross 0.22 gain p50 3864
small >=150ms 2 legs 1382 560 SOL 0.231 0.094 /h svc [('jito', 966), ('no tip', 375), ('helius', 15)] vp [('dammv2+pumpswap', 822), ('dlmm+pumpswap', 212), ('dammv2+dlmm+pumpswap', 112), ('dammv2+pumpswap+rayclmm', 33)] tok [('?', 801), ('CJ7yfNkt', 43), ('GAwhcphC', 37), ('GTBxUiw6', 34), ('9dSMwFfP', 29)] gain p50 4563 rivals p50 1
our wins sent_ms p50 14.22923 exp p50 20496 tip/exp p50 0.5 profit p50 -4447 kinds Counter({'state': 28, 'decoded': 3}) arms Counter({'bundle': 28, 'tpu': 3})
our bundles size 0 0.05 1463 wins 21 rate 0.0144 exp p50 40175
our bundles size 0.05 0.2 1557 wins 6 rate 0.0039 exp p50 298547
our bundles size 0.2 1 1117 wins 1 rate 0.0009 exp p50 1777246
our bundles size 1 4.3 901 wins 0 rate 0.0 exp p50 19493731
our pairs [('Dlmm>Dlmm', 1542, 17), ('PumpSwap>Dlmm', 1295, 2), ('Dlmm>PumpSwap', 1139, 5), ('DammV2>DammV2', 722, 1), ('Dlmm>DammV2', 472, 0), ('DammV2>Dlmm', 467, 0), ('PumpSwap>DammV2', 268, 2), ('DammV2>PumpSwap', 169, 1), ('Dlmm>RayCpmm', 26, 2), ('Dlmm>RayAmmV4', 23, 1)]
```
