# Head-to-head race forensics on our dip fires (runs 1-5) — independent agent report, 10-24 ~08:00 PKT

(Saved verbatim from the agent's final message; scripts and data in ./work/ — 260 MB.)

## Summary
1. **69 fires, 24 filled (35%)**; all 69 buys landed on chain (40 in the dump slot S, 28 in S+1, 1 in S+2). 44 failures = +5% guard (6042), 1 = a "phantom" dump (we saw it in shreds but that leader's whole 4-slot window was skipped; the S+1 deadline (6001) correctly rejected our buy).
2. **We lose inside the block, not by a slot.** 27 of 44 losses landed in the dump's own block behind 1-4 faster buyers; 9 missed the block while others pushed the price past +5% inside it; 8 lost in S+1.
3. **How close the losses were** (our feed clock, ±2 ms): 12/44 needed ≤2 ms, 24/44 ≤20 ms, 27/44 ≤30 ms. ~15 were our slow tail (our tx took 80-340 ms).
4. **Who wins:** first buyers after a dump land a median 25.5 ms after it; we land 33-45 ms after it when in the same block. HkQ7hMjy is ahead of us in 19/28 shared blocks, 5w8xtjc6 in 7/8, each by ~11 block positions (≈4 ms). haqqiUUX and DYXDDrZC are level with us.
5. **Not fees, tips, relays or copies (MEASURED):** winners pay LESS priority than us (median 1.64M µL/CU vs our 5M); in 33/44 losses the tx that crossed our guard paid less per CU than we did; 17/44 had no tip; winners use the same relays (no tip 34%, Helius 27%, Nozomi 12%); top racers send ~1 tx per dump. HkQ7's tx is built like ours (Nozomi 1M tip, cup ~1.7M, creates its token account, same L2TE program) → its edge is before the relay (INFERRED).
6. **Where our time goes (MEASURED):** our processing ~3.1 ms median (executed-feed wait 1.5 ms, max 13.5; decision 1.2 ms; all path writes done within 0.33 ms). After sending, ~30-35 ms even to leaders 0.13 ms away; every single path probed lands in 32-53 ms (median, same slot). Going from 2 to 5 paths did not lower the 31-38 ms floor.
7. **Jito leaders are our worst case:** our send latency there median 91 ms (n=16) vs 33-37 ms on Harmonic/Firedancer; fill 25% vs 39% elsewhere; 8 of the 15 slow-tail losses on Jito leaders. Competitors land on the same leaders in 20/33 ms (p25/median), mostly with Helius-tipped txs; our Jito route had no Helius in runs 2-4.
8. **Priority fee matters in only two places (MEASURED):** at the start of the S+1 block (higher fee first in 79-83% of pairs, n=2025) and among near-simultaneous arrivals on BAM (84-90%) and Harmonic (76-81%) leaders — not on Jito (50%). There our 5M is beaten by a cluster at 14-15M and 18-64M bidders.
9. **Leader distance:** fill 32% near, 22% for 2-30 ms leaders, 59% far (those fills land in S+1). HkQ7 attempted none of the 11 far-leader dumps we fired on.
10. **Time of day is flat:** over 151k dumps, the price crosses +5% inside the dump block in 5-12% of dumps every hour. Our fires only cover 02-07 PKT.
11. **Wider guard is not a fix:** +7.5% → 51% fills, +10% → 66%, but the extra fills replay at −0.6% to −4.5% net vs +1.0% for our actual fills (crude replay, INFERRED).

**Ranked changes**
1. **Fix Jito-leader routing:** add Helius Sender in its default routing mode (not swqos-only) to the Jito route, and test a Jito block-engine bundle path with a Jito tip; verify with forced probes. Expected: Jito fill 25% → ~39% (≈ +3 fills per 20 Jito fires).
2. **Fire on the first shred-level view** (compute the post-dump curve ourselves) and trim decision time: −1.5 to −3 ms median, no 6-13 ms tails (12 photo-finish losses; HkQ7's margin ~4 ms).
3. **Leader-aware fee:** ~15-30M µL/CU on BAM / Harmonic / Firedancer leaders; keep or lower on Jito. Expected ~3-6 more fills per 69; cost +0.001-0.0025 SOL per attempt incl. failures.
4. **Drop tipped paths that rarely win:** in probe head-to-heads vs competitors staked-rpc won 22%, bolt 42%, landx 46% vs Nozomi 70%, Helius 75% (small n). Tips cost 0.063 SOL over 24 fills ≈ 17% of runs 1-4 net (+0.34 SOL).
5. **Don't fire when the current leader is unknown / delinquent** (the phantom case).

**Not mattering:** tip size, copies, durable nonce (not visible in this data; a custom nonce-style dedupe appears in only 1.6% of buys), CU limit / account creation, number of paths, time of day, our CPU / write time.

**Biggest caveat:** for dumps in the last slot of a leader window (16 of 68) the fire record's "leader" may be the next leader → leader analyses mostly use window positions 0-2.

---

## 0. Data and method
- Chain data: run_20261023_1426/txs raw chunks incl. failed txs. For every dump our engine logged in runs 1-5 (6,930 dumps), all txs on that mint from slot S−2 to S+8 (589k txs, work/ext/); same for the dumps behind probes A-E (work/extp/).
- Price crossing: the curve replayed tx by tx from the dump's post-trade reserves; the crossing = the first tx after which our real min_out (tokens at the post-dump state ÷ 1.05, verified on all fires) would fail.
- Arrival times from our own feed: competitors from `tape` rows (executed feed), ours from `buy_first_rx` (first feed); executed-feed times lag the first feed by a median 1.5 ms (corrected). Treat ms comparisons as ±2 ms.
- Probes: probeD/E forced one path each (FRZ wallet, 0.02 SOL, n=8-18 per path); probeA-C multi-path.
- Coverage: runs 1-5 span 10-24 02:15-07:08 PKT (run 5 = local copy, 3 fires, no .realized yet); probes 10-24 01:59-05:07 PKT.

## 1. Fire outcomes (MEASURED)
| outcome | n |
|---|---|
| FILL in dump slot S | 13 |
| FILL in S+1 | 11 |
| LOST in S (landed behind the crossing) | 27 |
| LOST in S+1, price crossed inside S | 9 |
| LOST in S+1, crossed in S+1 before us | 8 |
| Phantom dump (slots 460605996-999 skipped; buy landed S+2, rejected by the deadline 6001) | 1 |
- All 69 buys included on chain: 24 ok, 44 × 6042, 1 × 6001.
- Dump position in its block vs our landing in S: first quarter 15/20, second 16/22, third 10/18, last quarter 0/8 (5 of those 8 still filled in S+1).
- Fill by leader client: HarmonicAgave 5/8, HarmonicFiredancer 4/9, AgaveBam 8/21, JitoLabs 5/20, Firedancer 1/7, FireBAM 1/2, Rakurai 0/1.

## 2. How far behind (MEASURED; need = our arrival − the crossing tx's arrival, our feed clock)
| earlier by | ≤2 ms | ≤5 | ≤10 | ≤15 | ≤20 | ≤30 | ≤50 | ≤100 |
|---|---|---|---|---|---|---|---|---|
| losses flipping to fills (of 44) | 12 | 15 | 15 | 20 | 24 | 27 | 29 | 40 |
- Upper bound (competitors keep their positions): e.g. 20 ms faster → fills 24/68 → 48/68.
- Same-block winners (buys before the crossing, in S): p10 4.3 / p25 17.4 / median 34.9 ms after the dump (n=135). Our same-block fills: p10 33.3 / median 36.5 / p75 44.9 ms (n=13). First buyer after a dump: in S 84%; arrival p25 12.7, median 25.5 ms.
- Head-to-head in shared blocks: HkQ7hMjy ahead 19/28 (+11 positions), 5w8xtjc6 7/8 (+12), 2KtcBCfh 6/6, haqqiUUX 16/37 (level), DYXDDrZC 11/27 (level). Blocks fill at ~0.36 ms per tx position → 11 positions ≈ 4 ms.
- On BAM / Harmonic leaders reactive buys arrive in a burst ~34-42 ms after the dump; of trades within ±1 ms of ours, 35 landed ahead and 35 behind; 17 of the 35 ahead paid a lower fee → sub-ms arrival order decides more than the fee.

## 3. What separates the winners (universe: 6,928 dumps, 4,587 with buy attempts in S..S+1)
| feature | winners (176 buys before the crossing) | us |
|---|---|---|
| CU price (µL/CU), median | 1.64M (p90 14.9M) | 5M |
| priority fee, median | 120k lamports | 500k lamports |
| tipped | 66% (median tip 0.2M) | 2.0-4.0M per fill (1M per relay) |
| relay of landed tx | no tip 60, Helius 48, Nozomi 21, Astralane 13, Jito 8, Speedlanding 5, 0slot 4 | Nozomi + Helius/bolt/landx/astralane |
| CU limit, median | 75k | 100k |
| creates token account in the same tx | 77% | 100% |
- The tx that crossed our guard in each of our 44 losses: 17 no tip, 12 Helius, 6 Nozomi; median CU price 1.70M; only 11/44 paid more per CU than us; 27/44 crossing wallets sent exactly one tx; HkQ7 was the crossing tx 8 times.
- Fast reactive wallets (in S = share of first attempts in the dump's block; Δidx = median block positions after the dump): HkQ7hMjy 92% / 84 / 1.11 tx per dump (Nozomi 1M tip, cup 1.67M, 78k CU, creates ATA, L2TE); 5w8xtjc6 95% / 96 / 1.00 (Nozomi/Jito 1M, cup 2.5M, L2TE); uone2Yn3 94% / 105; 7PedQZmc 74% / 77; **us 57% / 142**.
- Pre-positioned spam bots (CVPz447t, 3mK48y1P, 2HEEWXVw, 5k2Ckkiu, A9KKBdLy) are as active before dumps as after (e.g. 2322 pre vs 1257 post): not faster, always there.
- Copies: 14.8% of wallet-dump pairs have > 1 tx; top racers 1.0-1.2 per dump; multi-copy senders are mostly spam (3-6 copies failing 6042) or custom-dedupe bots.
- Nonce: the system durable-nonce instruction is not visible in this data (the system program does not log instruction names); a custom "ValidateNonce" dedupe appears in 255 of 16,397 successful buys (1.6%), none from top racers.
- Priority ordering (share of pairs where the higher fee lands first): start of S+1 (first 60 txs) 79% (83% if fee ratio ≥ 2; n=2025); inside S, all pairs 60% (n=27,676); near-simultaneous (≤ 15 positions apart): FireBAM 90% (29), AgaveBam 84% (198), HarmonicFiredancer 81% (31), HarmonicAgave 76% (45), Firedancer 65% (31), JitoLabs 50% (121).
- Leader distance (RTT from Frankfurt): near < 2 ms 31 fires, fill 32%, in S 20/31; EU 2-30 ms 18 fires, 22%, 16/18; far ≥ 30 ms 17 fires, 59% (mostly S+1), 4/17. HkQ7: 8 near, 17 EU, 0 far attempts; we had 11 far.
- Time of day (151k dumps ≥ 1 SOL on tokens ≤ 10 min old, 10-22 20:43 → 10-24 06:27 PKT): crossing +5% inside the dump block 5.2-11.9% every hour; first outside buyer in the dump block 28-38%; buyers before the crossing 1.2-1.9 → no meaningful pattern (work/hourly_all.txt).

## 4. Our send paths
- Inside our box (n=56-69): reaction (first feed → fire) median 3.1 ms, p90 6.9, max 14.8; executed-feed lag median 1.5, p90 5.7, max 13.5 (alone enough to lose 4fCN5RT8 and FH4ZtYnz, which needed 14.4 and 16.2 ms); decision 1.2 ms (checks_logs 0.34, prepare 0.17); last path written ≤ 0.33 ms after fire.
- Forced single-path probes (same-slot median ms after the dump / same-slot / share of reactive competitors beaten): bolt 31.9 / 11/18 / 42%; landx-fra3 34.5 / 9/10 / 46%; staked-rpc 35.8 / 7/8 / 22%; nozomi 36.1 / 14/18 / 70%; helius 43.3 / 13/18 / 75%; astralane 45.4 / 9/10 / 64%; haan 50.3 / 9/10 / 40%; tpu-direct 51.8 / 6/10 / 55%; helius-swqos 53.2 / 5/8 / 67%.
- Live send latency by leader client (fire → our feed sees our tx, median): JitoLabs 91 ms (p25 57, p75 122; in S 11/16); HarmonicAgave 35.7 (5/8); HarmonicFiredancer 37.0 (4/6); Firedancer 32.6 (3/5); AgaveBam 95.5 (mix: 31-42 near, 96-184 far; 10/18).
- Jito leaders: probes show tails on every path (bolt up to 1116 ms, Helius 61-140, tpu-direct 135-204). Competitors on the same Jito leaders land p25 20 / median 33 ms, mostly via Helius-tipped txs. On HEL1US, Helius-tipped txs were the earliest and most frequent same-block landers (15 of 28, earliest at position 9).
- More paths did not help: on non-Jito near/EU leaders typical send latency stayed 31-38 ms with 2, 3 or 4 paths.
- INFERRED: on Jito leaders our relays' route into the validator is slow (possibly a relayer hold on plain-TPU packets). Not verifiable with local data — test it.

## 5. Failure modes and costs (MEASURED)
- 44 × 6042: 27 behind in the same block, 9 missed the block, 8 behind in S+1. 1 phantom dump (skipped leader window; that leader's client field was empty). No dropped txs, no CU or account errors.
- Failed buys cost 0.0223 SOL in fees. Tips 0.0628 SOL over 24 fills (2.0-4.0M lamports each). Runs 1-4 net realized +0.338 SOL.
- Wider guard (filling at our real positions): +7.5% → 35/68 fills, +10% → 45/68, +15% → 53/68; replayed net per extra fill (TP +5% / SL −10% / 6 slots, crude, INFERRED): premium 5-7.5% (n=11) −2.9%; 7.5-10% (10) −2.3%; 10-15% (8) −0.6%; > 15% (15) −4.5%; our actual fills (24) +1.0%.

## 6. Ranked changes (expected effect / evidence)
1. Jito-leader routing: add Helius Sender (default mode) to route:jito (runs 2-4 had bolt + astralane + nozomi + staked-rpc); test a direct Jito block-engine bundle path with a Jito tip via forced probes on Jito leaders. Expected Jito fill 25% → toward 39%. Evidence §4, 8/15 slow-tail losses.
2. Remove the executed-feed wait: decide on the first decoded shred (post-dump curve from tracked state); trim the ~1.2 ms decision. Expected −1.5 to −3 ms median, no 6-13 ms tails. Evidence: 12 losses within 2 ms; HkQ7 / 5w8xtjc6 lead by ~4 ms.
3. Leader-aware fee: ~15-30M µL/CU on BAM / Harmonic / Firedancer leaders (consider ~85k CU limit; we use 57-83k); same or lower on Jito. Expected ~3-6 fills per 69; cost +0.001-0.0025 SOL per attempt incl. failures. Evidence §3 ordering table.
4. Trim paths that rarely win (staked-rpc, bolt, landx) where Nozomi / Helius cover the leader: −1-2M lamports of tips per fill with no latency loss (small-n evidence).
5. Skip fires when the current leader is unknown / delinquent (phantom case).
The remaining ~15-25 ms gap to the fastest bots is in the path from our server to the leader; closing it would need infrastructure local data cannot evaluate (e.g. staked QUIC from a validator identity, regional senders) — INFERRED.

## 7. Checked and found not to matter
Tip size (winners' median tip 0.2M; 17/44 crossing txs had none); priority fee in general (winners pay less than us), except at the start of S+1 and near-simultaneous arrivals on BAM / Harmonic; copies (racers ~1 tx per dump); nonce (system durable nonce not observable here; custom dedupe 1.6% of buys, not top racers); CU limit, ATA creation, our multi-instruction tx; number of send paths (2 → 5); our CPU / write time; time of day; a wider guard as a way to add profit.

## 8. Caveats
- Leader = the fire record's leader; when S is the last slot of a leader window (S%4==3) it may be the next leader (e.g. Biiv46yB lists a Singapore leader but landed in S in 40 ms) → leader analyses use window positions 0-2.
- Failed competitor copies show no tips (everything reverts) → their relays are unknown.
- Probe / fire samples are small (8-20 per cell).
- `land_ms_poh` is not milliseconds (same-slot pairs show 0.3-4 while feed timestamps differ by 13-143 ms); do not use it as latency.

## Files (./work/)
fires_h2h.json, fires_cat.json (per-fire race + category); universe.json (6,928 dump races); probes.json; wallets_top.json; hourly_all.txt; scripts extract.py, race.py, fires_analysis.py, fires_stats.py, universe.py, hourly.py, lib.py.
