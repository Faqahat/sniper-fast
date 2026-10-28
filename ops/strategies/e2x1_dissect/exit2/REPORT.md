# E2X1 — EXIT DECISION (agent "exit2", 10-28 PKT)

Question: can E2x1's exit timing be decoded from on-chain data (price/flow/wallet identity), so that a rule reproduces the ~2/3 of his
P&L that the ourspeed agent attributes to HIS EXIT? **Verdict: NO — fails the pass bar by a wide margin.** The best on-chain rule
recovers 5–26 % of the gap between a fixed hold and his real exit (bar: ≥ 70 %), and fires within ±1 slot of his real sell in 22 % of trips.

Code: this folder (e1–e6). Data: /home/moiz/sniper-data/e2x1_dissect/exit2/ (610 MB; e3.txt, e4_66.txt, e5.txt, e6.md are the raw outputs quoted here).
Times PKT. SOL figures pre tx-costs unless stated.

## Data (MEASURED)
- Tape: all pump.fun trades on his 4,990 mints, 10-22 03:07 → 10-28 18:41 (haqqml fresh tape; 3.31 M rows).
- Trips: 7,747 (7,626 closed, 121 open/graduated-to-PumpSwap). **Every closed trip is ONE buy (+228 adds) and ONE sell: 0 of 7,626 trips has a partial sell.** "Partial-exit lots" do not exist on the curve; the only split exits are graduated tokens sold later on PumpSwap (outside the tape).
- Candidates: every outside trade while a trip is open, 911,372 events; label y1 = he sells in this slot or the next (27,597 positives, 3.0 %).
- Split: TRAIN = trips entered before 10-27 18:41 (6,419 trips; last 15 % by time = validation), TEST = 10-27 18:41 → 10-28 18:41 (1,328 trips, 1,300 closed).
- Sim: curve maths as ourspeed/o2 (constant product, our SOL stays in the curve, fee in/out). Validation: sim at his real sell = +46.31 SOL vs his tape proceeds +46.89 on the 1,300 test trips (1.2 % diff from the 21-draw sell-delay averaging). Our-entry mode = counterfactual tape without E2x1+Grozoe, buy lands d after the trigger (ourspeed delay shape rescaled to median 66 ms), +5 % guard, sell lands d′ after the rule fires; phi = fast-follower haircut.

## 1. Exit anatomy (MEASURED, 7,626 closed trips)
| | share |
|---|---|
| last outside trade before his sell is ≤ 1 slot before it | 91.2 % (same slot 74.9 %, previous slot 16.3 %) |
| … and it is a SELL | 70.8 % |
| … and it is a BUY | 20.4 % |
| no outside trade within 1 slot (timer-like) | 8.8 % |
| twin Grozoe sells within ±2 slots | 44 % of trips (72 % of trips where Grozoe was in) |
| same slot: Grozoe lower index / E2x1 lower index | 1,638 / 1,684 — **50/50, nobody leads** |

So he reacts to a trade, mostly a sell, within one slot — like his entries. The twin reacts to the same signal at the same time (same slot, random order); it is not a copier chain.

What an exit event looks like vs other open moments (medians; P(exit) base rate 3.0 %):

| feature | at exit | other | P(exit) top decile | bottom decile |
|---|---|---|---|---|
| event SOL / curve vSOL | 0.96 % | 0.33 % | 8.3 % | 1.2 % |
| event token share of supply | 0.63 % | 0.18 % | 9.0 % | 1.1 % |
| seller sold 100 % of its holding | yes | no | 5.4 % | 1.8 % |
| seller holder rank | 24 | none | 1.8 % (low rank) | 8.4 % (top holders) |
| SOL out in last 1 s | 1.17 | 0.26 | 7.7 % | 2.1 % |
| consecutive outside sells | 1 | 0 | 6.8 % | 2.2 % |
| price vs entry | 1.03 | 1.11 | 1.6 % | 7.1 % |
| drawdown from peak | 0.86 | 0.92 | 3.1 % | 6.6 % |
| slots since entry | 85 | 130 | 2.2 % | 3.2 % (time is NOT the key) |

## 2. Identity rule vs price/flow rule (TEST events, MEASURED)
P(he sells within ≤ 1 slot | event) and the share of his exits that event type accounts for:

| event type | n | P(exit) | share of his exits |
|---|---|---|---|
| **Grozoe (twin) sells before him** | 248 | **91.9 %** | 4.6 % |
| top-3 holder sells | 5,252 | 13.3 % | 14.1 % |
| price ≤ 0.8× entry (any trade) | 10,541 | 10.8 % | 23.0 % |
| creator sells | 575 | 8.0 % | 0.9 % |
| trigger wallet (the trade he bought on) sells | 1,178 | 6.8 % | 1.6 % |
| any outside sell ≥ 0.3 SOL | 29,341 | 6.8 % | 40.4 % |
| drawdown ≥ 20 % | 30,892 | 6.5 % | 40.7 % |
| a follower (bought after him) sells | 27,799 | 5.4 % | 30.2 % |
| any outside sell | 64,068 | 5.2 % | 66.9 % |
| a copier wallet sells | 573 | 3.3 % | 0.4 % |
| a co-reactor bot (select's 102 lift wallets) sells | 8,390 | 3.9 % | 6.6 % |
| first outside sell after entry | 1,280 | 4.8 % | 1.3 % |

- The only near-deterministic identity signal is the twin, and it precedes him in only 19 % of test trips (in the other 25 % of co-exits he is first by index — unusable). Trigger wallet, creator, copiers, cohort bots: no.
- Price/flow: exits sit on big sells by big holders into a weakening tape, but every such rule has P(exit) ≤ 13 % — the same picture fires 7–20 times per trip before he acts.

## 3. Models (TRAIN days 1–5 → TEST day 6)
- GBDT (depth 4, 441 rounds, 75 causal features): event AUC fit 0.908 / val 0.835 / **TEST 0.862**. Top features: event impact, SOL out last 1 s, event token share, seller's activity (mints on tape), slots since last sell, consecutive sells, SOL in last 1 s.
- Precision on TEST: top 1 % of events → 77 % precision but 23 % recall; top 10 % → 20 % precision, 59 % recall.
- Depth-4 single tree (test AUC 0.756), readable rule list: `impact < −0.7 % AND ≥ 9 consecutive outside sells AND > 5.9 SOL out in 1 s` → P(exit) 97 % (leaf 6, 193 test events); `impact ≥ −0.7 % AND token share ≤ 1.65 % AND > 8.5 SOL out in 1 s AND > 5 consecutive sells` → 75 % (leaf 11, 351 events); `impact < −0.7 %, ≤ 8 sells run, ≥ 2 slots since last sell, token share > 2.3 %` → 53 %. Together these cover 11 % of his exits.

**Firing (first event per trip with p ≥ thr; thr chosen on validation), TEST, 1,300 trips:**

| rule | fires | within ±1 slot of his sell (all trips) | fires earlier | later |
|---|---|---|---|---|
| GBDT p ≥ 0.225 (best on val) | 60 % | **22.2 %** | 38 % | 0 % (never fires: 40 %) |
| GBDT p ≥ 0.117 | 82 % | 16.5 % | 66 % | — |
| GBDT p ≥ 0.069 | 92 % | 12.7 % | 80 % | — |
| tree high-lift leaves | 7 % | 5.5 % | 1.5 % | — |
| twin sells before him | 19 % | 17.5 % | 1.5 % | — |
| top-3 holder sells | 74 % | 8.0 % | 66 % | — |
| drawdown ≥ 20 % | 56 % | 10.1 % | 46 % | — |
| any outside sell | 96 % | 4.8 % | 92 % | — |
| hold ≥ 34 s | 50 % | 2.6 % | 47 % | — |

A rule either fires too early (the same picture happens many times per trip) or not at all. No threshold gets past 22 %.

## 4. Simulated P&L of his TEST trips (1,300, SOL pre tx-costs; FIXED = 18 / 34 / 83 s by FRESH / MINUTE / OLD)
"X|FIXED" = exit at the rule's fire or at the fixed band, whichever first (the plain rule with a 1800 s fallback loses −50…−110 SOL from the 40 % of trips where it never fires, so it is not shown). Gap-recovery = (X − FIXED) / (HIS − FIXED).

| exit | his entry (real tape) | gap rec. | our 66 ms entry, phi 0 | gap rec. | our 66 ms entry, phi 0.2 | gap rec. |
|---|---|---|---|---|---|---|
| **HIS real exit** | **+46.31** | 100 % | **+22.29** | 100 % | **+9.63** | 100 % |
| FIXED band | +11.01 | 0 | +3.98 | 0 | −9.43 | 0 |
| 200 ms (ours) | +2.43 | −24 % | −2.83 | −37 % | −6.91 | +13 % |
| GBDT p≥0.225 \| FIXED | +12.73 | 4.9 % | +5.67 | 9.2 % | −6.81 | 13.8 % |
| GBDT p≥0.117 \| FIXED | +13.18 | 6.2 % | +6.29 | 12.6 % | −4.45 | **26.1 %** |
| GBDT p≥0.53 \| FIXED | +13.31 | 6.5 % | +6.07 | 11.4 % | −7.18 | 11.8 % |
| twin sells \| FIXED | +14.09 | 8.7 % | +6.51 | 13.8 % | −6.85 | 13.6 % |
| top-3 holder sells ≥ 1 % \| FIXED | +8.23 | −7.9 % | +2.21 | −9.6 % | −8.41 | 5.4 % |
| first outside sell \| FIXED | +0.73 | −29 % | −4.55 | −47 % | −9.42 | 0 % |
| tree leaves \| FIXED | +12.57 | 4.4 % | — | — | — | — |

By bot (his entry): HIS +7.1 / +13.4 / +25.8 (FRESH / MINUTE / OLD); FIXED −2.2 / +4.9 / +8.3; best rule −0.5 / +4.7 / +9.0. The rule adds ~+1–2 SOL/day over the fixed band; his real exit adds +35.

Where the 35.3 SOL gap (his entry) sits, by his hold length: 0–25 slots +6.7 (239 trips: he sells fast where the band holds into losses), 25–100 slots +10.3, 100–300 +2.9, 300–1500 +11.3, > 1500 +4.1. 590 of 1,300 trips: his exit is worse than the band (−56 SOL), the other 710 make +91. The top 5 % of trips are 110 % of the gap (fat tail, as in recon). The gap is NOT one regime a rule could isolate.

**Pass bar (≥ 70 % recovery): FAILED — 5–14 % (26 % only in the phi 0.2 variant, where everything is near zero).**

## 5. What this means (INFERRED)
- His sell lands ~50 ms after a trade like his buy does, and 70 % of the time that trade is a sell by a large holder. But the identical picture appears 7–20 times per trip without him acting; the one he acts on is not separable by price, flow, holder, age, curve level, or wallet identity. The visible on-chain event is the *timing trigger*, not the *decision*.
- Only the twin's sell is deterministic (92 %), and it is simultaneous (50/50 index order), so both are driven by the same unseen signal — plausibly an off-chain feed or a per-token private score shared by the pair, the same conclusion select reached for his entries.
- Because exits are one full sell, his edge is "when", not "how much". A copy-exit (sell when E2x1/Grozoe sells, visible in shreds) keeps most of it: our-entry + HIS exit = +22.3 (phi 0) / +9.6 (phi 0.2) SOL on the test day vs −2.8 / −6.9 for our 200 ms exit — consistent with the ourspeed agent's finding, so that remains the only actionable route, with the usual copy-trade caveats (he sells 1 slot before us; fill rate on his trigger 0.91).
- Our own exit (200 ms) on his picks ≈ 0: the money is in the hold, not the pick.

## 6. Examples (TEST day; links: GMGN token, solscan buy/sell; P&L SOL; from e6.md)
Rule fired exactly on his sell (±0–1 slot), the event he reacted to:
1. [The Pump Files](https://gmgn.ai/sol/token/B9kb2ujfDHxMzd8N6L7PaYBicdE7b8MMDPSmdXxGpump) 10-28 11:25 OLD 1.0 SOL, hold 1,627 slots — fire +0 slots: **Grozoe sells 1.08 SOL** (holder rank 14), p=0.73; his real +0.091, FIXED +0.148. [buy](https://solscan.io/tx/4jzX5EhExgkQrNcT12R2ahmHRGCqQt2zCbu33qhLqw8HATFJ821hant3p5bG3tzfS4Kf9MpwrM7QdY6bkhfCdag4) [sell](https://solscan.io/tx/4nLUiqJZ44M4rMZbuWHUUzsmsT3ki1biEtwdsu47RYicBji1GqD8Gry3SuDjEEEbDA4n1G8UN1oK5LApGzW8Htcb)
2. [Super Investor](https://gmgn.ai/sol/token/Gf7fVVY848uz5MkYFiveoWzJhkaEhzsMkrvDSenwpump) 10-28 11:12 OLD 0.33 SOL, hold 220 slots — fire +0: SELL 1.04 SOL (2.8 % of curve) by a holder-rank-5 wallet that bought after him; his −0.075, FIXED −0.065. [buy](https://solscan.io/tx/2fLqMkkRfciFCNuAmiqyoGrLGfuoATuU28AUm4qzLy4nqYJWi4oCFDEm8o8Ujj3rhPuBHovBDRUsRgtdtLVx7Q8V) [sell](https://solscan.io/tx/2HMP9EJqH2NZNrBkXJma2qDc9tVhq41V4HvMCEx5dk1MbH9S5waP1ssxK465vqVnjVxo44twxsvCiKqDSdAtNsVM)
3. [45UhEf…](https://gmgn.ai/sol/token/45UhEfHw93pcfCxzWsmsLB7tqQpqHk9WosMdcTX3STtM) 10-27 22:03 FRESH 0.32 SOL, hold 5 slots — fire +0: BUY 2.96 SOL (5.1 %) by AbNUHfB9 (717 mints on tape, a bot) — he sells INTO a bot's buy; his +0.081, FIXED −0.125. [buy](https://solscan.io/tx/5MDYu9C9DnmjbVPt7DqeHYPZtsd9hbqGrsmMsq2PF8EhCSWMD3a5ioEBB2urnhN6suGNz7ZXXTjzv1gvj8GwM3Eu) [sell](https://solscan.io/tx/3b1LESkbbC4fXwbKV89RKayqmrkxBZzKxxRYaii1LYNJVJ2Ko16x37Mda5KTrhPTv4YfkJNaeyo4oSoqJM2BvZec)
4. [9Q9gtW…](https://gmgn.ai/sol/token/9Q9gtWCeud4eRuwpsvZEJhYPmheXKBSrNEjA55Hnpump) 10-27 22:06 MINUTE 0.55 SOL, hold 19 slots — fire +0: BUY 1.96 SOL (3.0 %) by a follower bot; his +0.434, FIXED +0.215. [buy](https://solscan.io/tx/2Vmz9Rk9f3ArnvBwABtRSzQA8VcVpYDhHZR1pA4STd671U1DfojYCu1RxCVS2Aajedr5Jv9979L3EUCAX424Kmo6) [sell](https://solscan.io/tx/3wuXaxJXgfnvGCQCY5XDij3AnfFdNvRCFcb9JFRhjBgofaEJe3NpT4LysTqREoTFysCXC9aKKeyNLBeuKj7iv75r)
5. [Tanisha Fund](https://gmgn.ai/sol/token/4V1DnNrqZ5gy3NPQM1qn6Bvu5VmBczFBY1eGjoGrpump) 10-28 05:38 OLD 1.0 SOL, hold 235 slots — fire +0: **Grozoe sells 0.98 SOL** same slot; his −0.035, FIXED −0.169. [buy](https://solscan.io/tx/2MjY8PXuqHg8uRWR5G422BptiZsFX9LQUpNcwJMP2D2eCNj2JpoaR9793sCXyUZsDQznGDH1yfsHwC1G2PM5tuJX) [sell](https://solscan.io/tx/5w8TUerFccP8pzy1XhKeciwBEiALVptynZqKBtFTzLhSoWXhr4qiPhX1sCiuhpZLrnEyB1kabJwJFFC1eQfUes7t)

Rule fires far too early (the same picture occurred long before he sold) — where his hold made the most:
6. [9xe8DX…](https://gmgn.ai/sol/token/9xe8DXZ5AkqJwYy34P2yKw34yVSGGepSAHQLWdJFpump) 10-27 21:52 OLD 0.66 SOL, hold 8,450 slots (30 min): his +2.52, FIXED +0.57, rule never fires. [buy](https://solscan.io/tx/366LsXscfczCSxRZF2P3Zw25FksnkQJ36xPELiqEwceCCzyMZMV9odBRKrauX5eD47GbLfWGeKfivWRJyr9ELVh2) [sell](https://solscan.io/tx/5zmkc9BbJ6dcH8rnwWgTwHaCRmg1EwYXQ9WDqgcrbQmCNZ1VyoTAE3A4r5bdCMj8bMm1jgWJ7DfmUvGFnVfdEMCx)
7. [Vibe Trading](https://gmgn.ai/sol/token/FixpvmWbF2AkdMD65jbgdky9G1Zkoq7SLySyGucipump) 10-28 09:30 OLD 1.0 SOL, hold 10,793 slots: his +1.48, FIXED −0.09; rule fired 5,490 slots early on a 3.3 SOL buy. [buy](https://solscan.io/tx/2kLkWPwnvScZr8nG1NjZhst3K5dH6ZqQqk7wbdaW7PtfzGetxoxnM3cgLk8MUR5a6ooGZosXiojsCMq28VuBtUMb) [sell](https://solscan.io/tx/4XshW3JX1GrVrfWxUuhkGusj4uUVgbytGJhfgcHbaLmN43ft5kQLn2KKQoXr3yX2mhrVSkPUpktKa43EUaNqyxCp)
8. [CqeWWn…](https://gmgn.ai/sol/token/CqeWWnUnQdxWysTDDS8T3DqXLvwNiRPLpV1h1imCpump) 10-27 22:06 OLD 1.0 SOL, hold 986 slots: his +1.09, FIXED +0.03; rule fired 299 slots early on a 3.0 SOL sell by holder rank 11 (dd 0.68) — he sat through that dump and sold later. [buy](https://solscan.io/tx/bBsNSzjdtQ7iuNyGcGSamKsN7UnySTBt1uxUtQj2e8UgVSreKUNnNnr5Ux6bj1pQZpc2qERK459Jnd1KkrVs5oT) [sell](https://solscan.io/tx/27mMENdQPis4w7QFLDcx49NTQg1opz44G5ujFZsj7pVo56LD7L5bGNdv5RJG9c5QNByQx7M5fmhLT2HfutX3cCny)
9. [Thinking Guy](https://gmgn.ai/sol/token/FfR4XdDPVrRmq7SFhkaH4srv54uFnNW2wfi83eNPpump) 10-28 03:52 FRESH 0.29 SOL, hold 41 slots: creator (holder rank 1) dumped 8.0 SOL (19 % of curve) 31 slots before his sell, price 0.68× entry — he did NOT sell on the creator dump, waited, and still closed +0.112 (FIXED +0.037). [buy](https://solscan.io/tx/3vjzFLvFNb64zda1yLeS8NsRUMnBp8ddphUBm9fRfajHf6sdarLntpbRgxEaym8HoPd1meGFszn34XzgCoX6GKqw) [sell](https://solscan.io/tx/4mdeZD4DE9EoyNYx4x82Vy4PcX156crxtSJrVNwm5cuABnoARUzBnr4WqYFowfZohDDu1S7Jfc3Wnr5dZZAvB2Za)
10. [Director](https://gmgn.ai/sol/token/HtViB821kxdid8qsEfvdrUUKMC7Mek5R4Yvq7CChn5SG) 10-28 07:12 OLD 0.89 SOL, hold 82 slots: fire −1 slot on a 9.9 SOL buy (18 % of curve) by a 97-mint bot — he sells into the pump; his +0.94, FIXED +0.05, rule +0.62. [buy](https://solscan.io/tx/3prVxeR1FP6i1b2C8bCgP9gQYWj2sdWTKBr9J1PwJz8herM1ZqbRkKKZ28A2366Pv2SMahdV34SF1NmT7NAtkTML) [sell](https://solscan.io/tx/4xQ46o2L9y9qHz9QZBhFFfeUGfKqtPMeHR5WYR9oygfPVQJ3mAiybZYTrTjRSwrLvyrmHi3iJ7yWCbN1KukMcna)

## Limits
- Rules fire only on trade events (8.8 % of his sells have no trade within 1 slot); a pure timer was tested as a feature (hazard flat in time) and as fixed holds.
- Twin-based exits in the sim: "SIBSELL" = Grozoe's sell event when it precedes his by index (19 % of trips); the simultaneous half is not usable as a signal.
- The our-entry mode uses the last outside trade before his buy as trigger (recon's exact size-equation trigger only exists for D0/D1); fill rate 0.91.
- Test = one day (1,300 trips); the gap is fat-tailed (top 5 % of trips = 110 % of it), so per-rule recoveries have wide error bars, but none is anywhere near 70 %.
