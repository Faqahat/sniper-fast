# Competitors in our lane (2026-10-21)

Read-only study. Who else snipes the launches our rule #2 fires on, how much they really make, what they do differently, and whether our rule #2 (1.5 SOL, sell at the end of S+2) is net positive. All PnL numbers are measured on-chain (public RPC, the wallets' own transactions); model numbers come from the unchanged FILTERS.md landing model. Inferences are marked *(inference)*.

## Summary

- **Who they are.** 682 wallets bought our recorded launches in the create slot or the next one; about 40 trade like us (0.5–3 SOL, many different creators). I measured 24 of them on-chain over the last ~22 h. The closest copies of our setup:
  - **CWiNFA** — 1 SOL flat, one sell ~2 s later, same speed as our model.
  - **BXB7FF** — 1.5 SOL flat, sells ~2 slots after buying: our exact design.
  - **3yrJE1** — rule #2-type launches, 0.5 / 2 / 4 SOL tiers, take-profit or a 4 s time stop.
  - **D24ipY** — always the first outside buyer, sells 60% of the bag at once.
  - **AHwJSn / AMDEmV** — 0.6 SOL bots.
- **How much they make.**
  - The good copies make **+0.1 to +0.45 SOL/h** (+1–5% per trade, about half the trades win, median trade ≈ 0).
  - Copies that pay more or land later are flat or losing (8ptvsh, 9XPMCa, Six5j1, 54YNHF, AqMoKz: −0.1 to +0.07 SOL/h). The slowest one (Anubis, ~100 ms, never first) lost **−28 SOL in 12 h** despite 0.1% fees.
  - **Only conviction bots are in or above the 0.5–2 SOL/h band:** 2mqrin **+0.5 SOL/h** and 8RvtT8 **+1.1 SOL/h** (both with 4yFAz's exact size tiers and ladder, so very likely the same bot family), dKMjeG **+4.5 SOL/h** (1.8 / 5 / 8 SOL tiers, ladder; 21 h of data) and 9qz7cW **~+14 SOL/h** (up to 7 SOL, ladder exits; only its last 6.4 h fetched). They rarely touch rule #2 (0–8 of 93 launches each; dKMjeG bet 8 SOL on 6 of them, +7.2 SOL) and their choice of launch is not reproducible.
- **On our rule #2 launches** (99 trades by the tracked wallets: +7.73 SOL — of which dKMjeG's six 8 SOL bets made +7.2 — mean return +0.41%, median +0.70%, win 52%):
  - The fast snipers made **+6.5% per trade, the same as our model predicts for those launches (+6.1%)**.
  - A sniper that lands one slot late made **−5.9%** where our model says +6.7%.
  - On the launches our model refused, a faster sniper got in first and won (3yrJE1 +1.40 SOL on one of them).
- **What they do differently.**
  1. They land first: the create slot, first or second outside buyer, seen by our feed 18–33 ms after the create.
  2. They pay 0.2–0.7% of size per buy, mostly as a tip inside one durable-nonce transaction sent through 4–8 relays, with tight CU limits (50–80k). A failed copy costs ~5,000 lamports.
  3. The small bots sell within ~2 s. The big earners size up to 2–8 SOL on a few launches and ladder out.
- **What to copy** (details in section 7):
  1. Speed: measure our real landing after Alpenglow on every fire.
  2. The cheap durable-nonce, tip-only send (model: +0.008 SOL/launch, ~+0.5 SOL per 58 launches). Needs the owner's OK.
  3. Keep the S+2 exit. On 76 rule #2 launches with full tapes, S+2–S+4 is the best simple exit; holding ≥2 s, ladders and trailing stops lose on our entries.
  4. 2 SOL only after 1–2.
- **Verdict.** Rule #2 at 1.5 SOL with the S+2 exit is **not proven net positive.**
  - It is flat on 10-21 in our model (+0.004 SOL/launch) and −0.31 SOL on 49 paper launches. After Alpenglow the tracked snipers' own rule #2 trades turned negative too (29 trades, −3.9% per trade, ~1.7 h of data).
  - It is worth roughly **+0.03–0.05 SOL per launch (≈ +0.25–0.4 SOL/h)** only if we land in the create slot within ~30 ms and cut costs.
  - At our older measured landing (median 78 ms) it should lose, like the slot-late sniper.
  - **Run 2 should be a landing-measurement run, not a profit run.**

## 1. How the competitors were found (`discover.py`)

- **Launches:** every launch our engines recorded block by block: the A–C logs (10-20 12:40 → 10-21 10:13), the 1 h dry hour (long windows to S+280), and a read-only copy of the paper loop's recordings (D, E and after, 10-21 09:23 → 15:31). **1,728 launches**, 99 of them rule #2 (lunar largest transfer + glued bundle 3–5 SOL + create ≤150 ms), 251 after Alpenglow (slot ≥ 459,653,000).
- **Candidate buys:** every buy of the mint in the create slot S (after the creator's glued bundle) or S+1, excluding the bundle members, the creator, our wallets (FRZh63…, 2g7rYv…) and 4yFAz. Our feed time for each buy comes from the engines' `RACE obs outs` timelines (989 launches).
- **682 wallets** bought at least once; **41** look like they are in our lane (≥5 buys of 0.5–3 SOL across ≥4 creators), 31 of them on at least one rule #2 launch. Many frequent wallets buy only 0.05–0.15 SOL (volume or copy bots, e.g. DnEMSg on 23 rule #2 launches); those are not in our lane.
- **Fetched:** the 24 wallets with the most lane buys and rule #2 presence. For each: signatures for the last ~22–24 h, then every successful transaction (pump TradeEvents, fees, tips, routes) plus a sample of 40 failed ones. Heavy wallets were capped at the newest 2,000–2,500 transactions (9qz7cW covers only the last 6.4 h).

## 2. The competitors (`comp_trades.py`, `table.py`)

PnL per trade = sells × (1 − pump fee) − buys × (1 + pump fee) − the tx fees and tips of that trade's transactions. Net SOL/h also subtracts failed-tx fees (sampled mean × failed count). Token-account rent is left out (every wallet reclaims it in batch close transactions; checked: the wallet-delta PnL differs from this by exactly the rent). **Only SOL-quote launches are counted;** some wallets also trade non-SOL-quote launches (3yrJE1 80, 9qz7cW 68, AMDEmV 58, 8ptvsh 39, 7cp6zx 39 trades) whose PnL is not decoded.

| wallet | hours | trades/h | net SOL/h | SOL/trade | size med (tiers) | win | median | w/o best 3 | hold med | exit | dslot 0 / +1 | our feed saw it | fill vs post-bundle | buy fee+tip | watched picks (rule #2) | PnL on watched / rule #2 | pre-AG / post-AG per trade |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 9qz7cWBq | 6.4 | 46.4 | **+14.40** | +0.355 | 3.00 (3.0x70, 1.8x69, 1.2x33, 3.6x16) | 50% | +0.003 | +64.9 | 6.0 s | ladder | 49% / 17% (n 235) | 32 ms (n 34) | 1.07x | 0.0131 (0.7%) | 56 (8) | +29.45 / -0.64 | +0.273 (n 168) / +0.462 (n 128) |
| dKMjeGJ4 | 20.8 | 16.2 | **+4.49** | +0.289 | 5.00 (1.8x142, 5.0x113, 8.0x80, 3.0x2) | 49% | -0.015 | +58.6 | 5 s | ladder | 69% / 31% (n 154) | 24 ms (n 22) | 1.21x | 0.0193 (0.7%) | 42 (6) | +7.53 / +7.24 | +0.368 (n 282) / -0.112 (n 55) |
| 8RvtT818 | 21.9 | 7.7 | **+1.12** | +0.146 | 1.91 (1.4x49, 3.0x35, 2.2x30, 1.5x12) | 46% | -0.017 | +14.6 | 4 s | mixed | 74% / 25% (n 69) | 40 ms (n 13) | 1.07x | 0.0250 (1.7%) | 18 (2) | +3.67 / +0.05 | +0.141 (n 152) / +0.184 (n 17) |
| 2mqrindM | 18.4 | 6.7 | **+0.51** | +0.077 | 2.10 (3.0x34, 1.4x23, 2.2x19, 1.2x10) | 48% | -0.007 | +4.8 | 3.0 s | mixed | 78% / 22% (n 55) | 49 ms (n 12) | 1.08x | 0.0250 (1.7%) | 16 (0) | -1.81 / +0.00 | +0.096 (n 111) / -0.093 (n 13) |
| 3yrJE1A8 | 21.9 | 7.0 | **+0.44** | +0.063 | 0.50 (0.5x90, 2.0x49, 4.0x9, 3.0x5) | 48% | -0.011 | +3.0 | 4 s | single | 77% / 23% (n 84) | 21 ms (n 7) | 1.10x | 0.0012 (0.2%) | 25 (11) | +0.21 / +1.74 | +0.057 (n 136) / +0.110 (n 17) |
| D24ipYXu | 22.0 | 9.3 | **+0.38** | +0.044 | 0.99 (1.0x44, 0.5x31, 1.8x18, 0.6x14) | 51% | +0.005 | +5.4 | 6.0 s | ladder | 86% / 14% (n 92) | 27 ms (n 11) | 1.03x | 0.0101 (1.1%) | 20 (1) | +0.79 / +0.07 | +0.050 (n 183) / -0.009 (n 21) |
| CWiNFAEk | 23.9 | 23.3 | **+0.36** | +0.015 | 1.00 (1.0x557) | 38% | -0.016 | +6.3 | 2 s | single | 73% / 26% (n 283) | 33 ms (n 39) | 1.06x | 0.0060 (0.6%) | 92 (16) | +1.21 / +1.04 | +0.012 (n 489) / +0.037 (n 68) |
| 6anjqMeW | 5.4 | 24.5 | **+0.26** | +0.011 | 0.50 (0.5x124, 1.0x9) | 36% | -0.020 | -0.4 | 3 s | mixed | 50% / 25% (n 110) | 71 ms (n 23) | 1.11x | 0.0087 (1.7%) | 20 (5) | -0.02 / +0.10 | +0.003 (n 86) / +0.024 (n 47) |
| 3oN2NBiW | 12.9 | 12.0 | **+0.25** | +0.021 | 0.99 (0.5x65, 1.0x29, 1.5x11, 2.0x9) | 39% | -0.010 | -1.4 | 1 s | mixed | 13% / 1% (n 85) | 65 ms (n 5) | 1.11x | 0.0011 (0.1%) | 21 (2) | +1.02 / -0.10 | +0.019 (n 105) / +0.027 (n 50) |
| AHwJSnFN | 23.7 | 16.9 | **+0.23** | +0.014 | 0.60 (0.6x142, 0.4x95, 0.9x75, 1.2x34) | 47% | -0.004 | +1.1 | 2.0 s | single | 70% / 30% (n 186) | 47 ms (n 34) | 1.02x | 0.0016 (0.4%) | 51 (6) | +2.86 / +0.09 | +0.013 (n 363) / +0.019 (n 39) |
| DRWPSrUb | 21.6 | 3.2 | **+0.23** | +0.072 | 2.00 (2.0x31, 1.9x14, 1.8x5, 1.5x3) | 47% | -0.011 | -1.8 | 7.0 s | mixed | 37% / 22% (n 46) | 39 ms (n 3) | 1.34x | 0.0205 (1.0%) | 17 (4) | -1.47 / +0.33 | +0.071 (n 56) / +0.076 (n 12) |
| AMDEmVoc | 21.5 | 15.9 | **+0.21** | +0.014 | 0.60 (0.6x289, 0.3x26, 0.2x11, 1.0x9) | 32% | -0.017 | +0.8 | 7.0 s | single | 64% / 36% (n 166) | 36 ms (n 17) | 1.03x | 0.0026 (0.4%) | 42 (0) | -0.78 / +0.00 | +0.007 (n 307) / +0.067 (n 35) |
| BXB7FF4m | 22.0 | 8.8 | **+0.13** | +0.016 | 1.50 (1.5x193) | 33% | -0.039 | +1.0 | 1 s | single | 100% / 0% (n 89) | 28 ms (n 12) | 1.04x | 0.0188 (1.3%) | 18 (1) | +0.58 / +0.02 | +0.015 (n 178) / +0.023 (n 15) |
| G9sQPg9E | 21.0 | 14.2 | **+0.12** | +0.010 | 1.00 (1.0x161, 0.5x138) | 37% | -0.018 | +0.4 | 1 s | single | 63% / 36% (n 124) | 36 ms (n 42) | 1.09x | 0.0075 (1.5%) | 39 (3) | -0.85 / -0.48 | +0.012 (n 288) / -0.049 (n 11) |
| 8ptvshQR | 21.9 | 7.9 | **+0.07** | +0.015 | 1.25 (1.2x26, 1.1x25, 1.0x18, 1.4x15) | 34% | -0.045 | -4.4 | 2 s | single | 66% / 34% (n 74) | 36 ms (n 10) | 1.11x | 0.0244 (1.9%) | 25 (5) | -1.85 / -0.26 | +0.016 (n 151) / +0.006 (n 22) |
| 24678QKx | 21.9 | 3.4 | **+0.03** | +0.012 | 0.44 (0.5x24, 0.4x24, 0.2x7, 0.3x7) | 32% | -0.016 | -0.6 | 2 s | single | 67% / 33% (n 55) | 19 ms (n 3) | 1.06x | 0.0051 (1.0%) | 10 (6) | -0.06 / -0.63 | -0.021 (n 21) / +0.025 (n 54) |
| 9XPMCaxt | 21.9 | 2.5 | **+0.03** | +0.025 | 3.00 (3.0x19, 1.0x9, 1.5x9, 4.0x7) | 39% | -0.049 | -1.6 | 2.0 s | ladder | 93% / 7% (n 28) | 26 ms (n 11) | 1.06x | 0.0849 (3.9%) | 14 (4) | +0.11 / -0.24 | +0.012 (n 49) / +0.153 (n 5) |
| 7cp6zxvh | 22.0 | 8.4 | **+0.02** | +0.002 | 0.98 (1.0x37, 0.8x36, 1.2x36, 0.6x32) | 42% | -0.028 | -1.7 | 4.0 s | single | 18% / 48% (n 104) | 136 ms (n 6) | 1.12x | 0.0012 (0.1%) | 30 (12) | +2.07 / -0.79 | -0.024 (n 158) / +0.160 (n 26) |
| Six5j1cv | 21.5 | 4.4 | **-0.02** | -0.001 | 0.89 (0.9x37, 0.7x22, 1.0x18, 0.8x12) | 43% | -0.013 | -0.5 | 0 s | single | 73% / 27% (n 52) | 69 ms (n 16) | 1.03x | 0.0140 (1.5%) | 29 (5) | -0.05 / +0.11 | -0.001 (n 88) / -0.003 (n 7) |
| 54YNHFVt | 21.4 | 3.8 | **-0.06** | -0.008 | 1.60 (1.6x43, 1.4x24, 2.0x4, 2.6x4) | 41% | -0.031 | -2.9 | 1.0 s | single | 88% / 12% (n 33) | 31 ms (n 11) | 1.05x | 0.0139 (0.9%) | 11 (0) | -0.28 / +0.00 | -0.012 (n 80) / +0.122 (n 2) |
| DsGJkPzF | 16.1 | 4.9 | **-0.06** | -0.012 | 0.50 (0.2x17, 0.5x11, 0.6x10, 0.3x8) | 33% | -0.015 | -2.0 | 8 s | single | 70% / 30% (n 43) | 41 ms (n 9) | 1.03x | 0.0023 (0.5%) | 14 (0) | -0.15 / +0.00 | -0.018 (n 58) / +0.003 (n 21) |
| AqMoKz92 | 22.0 | 6.6 | **-0.10** | -0.013 | 1.00 (1.0x128, 2.0x17) | 37% | -0.030 | -3.3 | 1 s | single | 74% / 26% (n 77) | 24 ms (n 9) | 1.06x | 0.0200 (1.7%) | 19 (1) | -1.13 / +0.03 | -0.009 (n 132) / -0.062 (n 13) |
| H9kuqGKN | 6.1 | 13.8 | **-0.91** | -0.075 | 0.71 (0.6x24, 0.7x17, 0.8x9, 1.0x6) | 11% | -0.070 | -9.9 | 1800.0 s | single | 70% / 29% (n 79) | 42 ms (n 12) | 1.02x | 0.0056 (0.9%) | 15 (0) | -0.39 / +0.00 | -0.115 (n 66) / +0.253 (n 8) |
| Anubis51 | 12.4 | 25.8 | **-2.28** | -0.088 | 2.19 (2.2x148, 1.2x86, 1.9x20, 3.4x13) | 27% | -0.146 | -34.1 | 3 s | single | 37% / 41% (n 103) | 102 ms (n 20) | 1.23x | 0.0022 (0.1%) | 34 (1) | -5.61 / +0.05 | -0.088 (n 319) / - |

Column notes: *dslot* = the buy's slot minus the create slot (known only for creates in our logs/recordings); *our feed saw it* = median ms after the create at which our engine's feed saw the wallet's buy (comparable to our own modelled landing of 20–35 ms); *fill* = the wallet's average price ÷ the post-bundle price, on our recorded launches; *watched picks* = trades on launches our engines watched (rule #2 in brackets).

**Who is in the 0.5–2 SOL/h band? Nobody that looks like us.** The wallets that trade our kind of launch with our kind of size and a quick exit make **−0.1 to +0.45 SOL/h** (−1% to +5% per trade); the slow one (Anubis, ~100 ms) lost −2.3 SOL/h. The four at or above 0.5 SOL/h — 2mqrin (+0.5) and 8RvtT8 (+1.1), both with 4yFAz's exact size tiers, dKMjeG (+4.5) and 9qz7cW (~+14) — are conviction bots: size tiers up to 4–8 SOL, ladder exits held for 5–40 s, the 4yFAz profile. They bought 0, 2, 6 and 8 of the 93 rule #2 launches and made their money elsewhere (dKMjeG's 6 rule #2 buys at 8 SOL made +7.2 SOL); their choice of launch is not reproducible from create-time data.

## 3. Deep dives (`deep.py`)

### CWiNFA (CWiNFAEk4M1y…3S2J) — the closest copy of our setup that makes money

- **Results (measured):** 557 trades in 23.9 h (23/h), **+8.6 SOL** (+0.36 SOL/h after 0.09 SOL of failed-tx fees). Mean +1.5% per trade, median −0.016 SOL, win 38%, +6.3 SOL without the best 3 (broad, not one lucky trade).
- **Size:** always exactly **1.00 SOL** (buy-exact-quote 1 SOL including the pump fee).
- **Exit:** one sell, median **2 s (7 slots)** after the buy, spread over 1–24 slots (not a fixed timer). By hold time: < 1 s −2.2 SOL (n 60), 1–4 s **+10.9 SOL** (n 420), > 4 s ≈ 0 (n 77). *(Hold time is chosen by its exit rule, so this split is not causal.)*
- **Landing:** create slot 73%, S+1 26%; first outside buyer on 38% of our watched launches; our feed saw its buy a median **33 ms** after the create (p25 16 ms) — our speed class. Fill 1.06× the post-bundle price.
- **Cost:** priority 0.003 + tip 0.003 = **0.006 SOL a buy (0.6%)**, sells 0.0011. **Durable nonce on every buy** (the same signed tx goes to several relays and only one can land): flashblock 159, nozomi 150, stellium 69, astralane 62, helius 59, jito 34. CU limit 80k, its own program `5DVzy5…`. Only 53 failed txs in 24 h.
- **Selection:** buys 5.8% of the launches our engines watch, but **17% of rule #2 launches** (16 of 93) against 5% of the rest. Prefers bundle 3–5 SOL (14% pick rate), j7tracker (9%), creators with ≥4 earlier launches (16%).
- **On rule #2:** 16 trades, **+1.04 SOL, +6.5% per trade, 56% win.** On the other watched launches: 76 trades, +0.16.
- **Alpenglow:** before 22 trades/h, +0.27 SOL/h; after (13:54–15:35) 41/h, +1.54 SOL/h. But 12:00–13:54 (before AG) was already 45/h, +1.78 SOL/h, so the jump is the US-hours market, not Alpenglow. Create-slot landing fell from 84% (12:00–13:54) to 69% after AG.

### 3yrJE1 (3yrJE1A8…2fjJ) — rule #2-type launches, size tiers, take-profit + 20-slot time stop

- **Results:** 153 SOL-quote trades in 21.9 h (7/h), **+9.6 SOL (+0.44 SOL/h)**, +5.0% per trade, median −0.011, win 48%, +3.0 without the best 3. (Plus 80 non-SOL-quote trades not counted.)
- **Size tiers:** 0.5 SOL (90 trades, +4.5%), **2.0 SOL (49, +4.1%)**, 3–4 SOL (14, +7.0%). It uses **2.0 SOL on rule #2 launches** (median).
- **Exit:** one sell. **73 of 153 first sells land exactly 20 slots (~4 s) after the buy: a time stop.** The early exits (1–4 s) look like take-profits: 27 trades, +18.4 SOL. The time-stop exits lost −8.8 SOL (124 trades).
- **Landing:** create slot 77%; our feed saw it at ~21 ms (n 7); fill 1.10×.
- **Cost:** fee ∝ size: 0.0012 SOL at 0.5 SOL (0.2%), 0.015 at 2 SOL, 0.03–0.04 at 3–4 SOL; durable nonce; landx, helius, bolt, soyas, astralane.
- **Selection:** never buys a launch without a creator bundle (0 of 652); **12% of rule #2** (11 of 90) against 1% of other watched launches; lunar, glued 2–3 txs, dev 2–6 SOL.
- **On rule #2: 11 trades, +1.74 SOL, +8.9% per trade, 64% win.** Three of them were launches our model refused (price >15% over the post-bundle quote when we would land): 3yrJE1 was the first outside buyer there and made +1.40 (3 SOL), +0.08 and +0.01.
- **Alpenglow:** after AG 17 trades, +1.88 SOL (+7.8%), sizes 2 SOL; 12:00–13:54: 30 trades, +0.92 (+2.7%).

### BXB7FF (BXB7FF4m…W8PL) — our exact setup, executed well: barely positive

- **Results:** 193 trades in 22 h (8.8/h), **+3.05 SOL (+0.13 SOL/h)**, +1.1% per trade, median −0.039, win 33%, +1.0 without the best 3.
- **Size 1.50 SOL flat. Exit ≈ ours:** 128 of 193 first sells 2 slots after the buy; mostly one sell (168); 25 trades sold 50% first and laddered (+5.8 SOL; the single sells lost −2.8).
- **Landing better than our model assumes:** create slot on **89 of 89** launches with a known create; first outside buyer on 16 of 18 watched launches; feed 28 ms; fill 1.04×.
- **Cost: tip only** (0.0188 SOL ≈ 1.3%, priority ~0): a failed copy costs ~5,000 lamports. Durable nonce; speedlanding, helius, node1, landx, astralane, nozomi, jito.
- Mostly not our launches (only 1 rule #2): its median curve has 2.65 SOL ahead of it (small or no bundle).
- **Takeaway (inference):** fast landing + 1.5 SOL + an S+2-style exit + ~1.3% cost ≈ +1% per trade. That is the realistic ceiling for our current design without a better exit or lower cost.

### D24ipY (D24ipYXu…CwQ) — first in, sells 60% into the next buyers

- **Results:** 204 trades in 22 h (9.3/h), +9.0 SOL gross, −0.6 failed-tx fees → **+0.38 SOL/h**, +3.0% per trade, median +0.005, win 51%.
- **Sizes** 0.5–3 SOL in many tiers; return rises with size (0.5 −1.2%, 1.0 +2.0%, 1.3 +7.3%, 1.8–2 +3.7%, 3.0 +6.8%; 6 SOL −3.3%).
- **Exit:** sells **~60% of the bag 0–1 slots after its own buy** (171 of 204), into the snipers that land behind it, then ladders the rest over up to 60 s (median hold 6 s).
- **Landing:** first outside buyer on 20 of 20 watched launches; **feed 18–27 ms** (n 8–11); fill 1.03×. Cost 0.010 SOL (1.1%), mostly landx.
- Only 1 rule #2 trade (+0.07); 2 on lunar 3–5 bundles with late creates (+0.88).

### 9qz7cW (9qz7cWBq…MhWpw) — the biggest earner: a 4yFAz-class conviction bot

- **Results (last 6.4 h only, 09:10–15:34):** 297 SOL-quote trades (46/h), **+105 SOL gross, −12.8 SOL of failed-tx fees** (4,783 failed txs × 0.0029) → **+14 SOL/h**.
- **The money is in the big tier:** ≥4 SOL buys (75 trades) made **+94 SOL** (+15.9%); 1.2–3.6 SOL buys made +11 SOL (+2%).
- **Exit:** ladder (first leg ~30% in most trades), median hold 6 s, winners held 16–40+ s. Single sells lost −8.3 SOL.
- **Landing:** create slot +20.5 SOL vs S+1 −5.7 SOL; many later buys too (not only snipes).
- **On rule #2: 8 trades, −0.64 SOL.** On our other watched launches: +30 SOL.
- **Takeaway:** same lesson as 4yFAz — the 0.5–2+ SOL/h results come from sizing up on a few launches the bot "knows" and riding them with a ladder; nothing in our create-time data reproduces that choice.

### 8RvtT8 (8RvtT818…5Yj4) — in the 0.5–2 SOL/h band, and almost certainly 4yFAz's bot

- **Results:** 169 trades in 21.9 h (7.7/h), **+24.6 SOL (+1.12 SOL/h)**, +6.9% per trade, median −0.017, win 46%, +14.6 without the best 3.
- **Same fingerprint as 4yFAz** *(inference)*: size tiers **1.19 / 1.45 / 2.18 / 2.96 / 4.15 SOL** (4yFAz: 1.19 / 1.45 / 2.18 / 2.96 / 6.72), a ~30% first sell, and a **40 s time stop** (39 trades closed at 38–42 s).
- **Size and exit carry the result:** 1.19 SOL tier −2.9%, 1.45 +6.8%, 2.18 +3.9%, 2.96 +7.6%, 4.15 +16.7%. Ladder trades (88) +26.2 SOL, single sells (81) −1.6.
- **Landing:** create slot 51 of 69 with a known create; our feed saw it at a median ~40 ms over all our recordings (n 13; 78 ms on the 10 inside its fetched window) — slower than CWiNFA/BXB7FF; fill 1.07–1.08×. Cost 0.025 SOL (1.7%), tip-heavy.
- **Not our lane by selection:** it bought 18 of 1,597 watched launches (1.1%) and **only 2 of 93 rule #2** (+0.05 SOL). +20.9 of its +24.6 SOL came from launches our engines did not watch.
- **A third sibling: 2mqrin** (2mqrindM…sjwdY) uses the same tiers (1.19 / 1.45 / 2.18 / 2.96 / 4.15 SOL) and a ~30% first leg: **+9.5 SOL in 18.4 h (+0.51 SOL/h)**, +3.6% per trade; ladders +12.7, single sells −3.2; **0 rule #2 trades**, −1.81 SOL on our other watched launches; after AG −1.21 on 13. *Inference:* the 4yFAz tiers are a bot product or one operator running several wallets; none of the three works our rule #2 lane.

### dKMjeG (dKMjeGJ4…2CTK) — the other big conviction bot (known from 10-19), and the only one that bets big on rule #2

- **Results:** 337 trades in 20.8 h (16/h), +97.5 SOL gross, −4.4 SOL failed-tx fees → **+4.5 SOL/h**, +6.6% per trade, median −0.015, win 49%, +58.6 without the best 3.
- **Tiers 1.8 / 5 / 8 SOL**; ladders on 311 of 337 trades; winners held 16–40 s (+119.6 SOL), 8–16 s holds lost −18.7. Lands in the create slot 106 of 154; our feed saw it at ~22–24 ms; fill 1.21×; cost 0.7% (up to 0.25 SOL on its biggest buys).
- **On rule #2: 6 trades at 8 SOL, +7.24 SOL (+20% per trade, 5 of 6 won).** Conviction sizing is what turns these launches into real money; it skipped the other 87.
- **After Alpenglow it lost:** 55 trades, −6.14 SOL (−4.1 SOL/h), median size down to 1.8 SOL; 13–15 h UTC −11.2 SOL. One bad 1.5 h does not prove anything, but it is the only big bot here that turned negative after AG.

### Short notes on the rest

- **AHwJSn** (0.6 SOL tiers 0.4–3.6, +0.23 SOL/h, 1–2 s single sells, 0.4% cost, first outsider on 50 of 51 watched launches, feed 47 ms) and **AMDEmV** (0.6 SOL, +0.21 SOL/h, mostly no-bundle launches, ~7 s time stop, ladders on pops): small, cheap, positive.
- **8ptvsh** (1.25 SOL, 2 s, **1.9% cost**, +0.07 SOL/h after 0.92 SOL of failed-tx fees; −1.85 SOL on our watched launches, −0.26 on rule #2): what we look like with high costs — break-even.
- **7cp6zx** (0.98 SOL, lands **S+1 mostly, feed 136 ms**, single sell ~4 s, 0.1% cost): +0.02 SOL/h; **on rule #2: 12 trades, −0.79 SOL.** Slow landing on our launches loses.
- **9XPMCa** (1–4.5 SOL, half sold at ~1 s, rest at ~2 s, **3.9% cost**): +0.6 SOL in 22 h; rule #2: 4 trades −0.24.
- **Six5j1** (0.9 SOL, sells in the same or next slot, 1.5% cost): −0.13 SOL in 21.5 h. Selling immediately does not pay.
- **Anubis** (Anubis51…HF5w; 2.24 / 1.25 SOL, one sell after ~3 s, **cost only 0.1%** but **slow: never the first outside buyer, rank 3, feed ~102 ms, fill 1.23×**): **−28.2 SOL in 12.4 h (−2.3 SOL/h)**, then it stopped trading. Cheap fees do not rescue a slow sniper.
- **54YNHF** (1.6 SOL, one sell after ~1 s, 0.9% cost + 0.55 SOL failed-tx fees) and **AqMoKz** (1.0 SOL, ~1 s, 1.7% cost): −0.06 and −0.10 SOL/h. Fixed-size quick-exit copies of our design that lose.
- **DRWPSr** (2.0 SOL, ~7 s, Axiom-funded, often S+1, fill 1.34×): +0.23 SOL/h; create slot +20.6% per trade vs S+1 −10.1%.

## 4. Their real results on the launches we fire on (`same_launch.py`)

Launches inside the competitors' fetched window (10-20 ~15:35 → 10-21 15:35): 1,597 watched, **93 rule #2** (71 with our model row).

| launch group | competitor trades (tracked wallets) | their real PnL | mean / median return | win | our model S+2 on the same group |
|---|---|---|---|---|---|
| **rule #2** (93 launches, 45 traded by ≥1 tracked wallet) | 99 | +7.73 SOL | +0.41% / +0.70% | 52% | +3.81 SOL on 71 (+0.054/launch, median −0.011, win 38%) |
| other watched (1,432 launches) | 538 | +23.37 SOL | +0.94% / -2.74% | 41% | −0.60 SOL on 1,185 (≈0/launch) |

- **Rule #2 is the better lane for them too.** Their median return on rule #2 launches is positive (+0.70%), on the other watched launches negative (-2.74%). The fast snipers pick rule #2 launches 3–12× more often than other watched launches (CWiNFA 17% vs 5%, 3yrJE1 12% vs 1%).
- **Speed decides who wins on the same launches.** Per wallet, their real return vs our model's S+2 return on the same rule #2 launches:

| wallet | rule #2 trades | their real return | our model on the same launches | they landed in the create slot | their hold (slots) |
|---|---|---|---|---|---|
| CWiNFA | 14 | +5.3% | +5.9% | 13/14 | 8 |
| 3yrJE1 | 9 | +8.6% | +10.5% | 9/9 | 20 |
| AHwJSn | 6 | +1.9% | +2.1% | 6/6 | 7.5 |
| **4 fast snipers together** (+ D24ipY 1 trade) | **30** | **+6.5%** | **+6.1%** | | |
| **7cp6zx (slow: S+1 8 of 10, feed ~136 ms)** | **10** | **−5.9%** | **+6.7%** | 2/10 | 14 |
| dKMjeG (8 SOL bets, ladder, held ~79 slots) | 4 | +19.8% | +60.5% (at 1.5 SOL, S+2) | 4/4 | 79 |

- dKMjeG's rule #2 launches spiked early: our model's S+2 exit at 1.5 SOL would have made +60% on them, its 8 SOL ladder made +20% (its own size moves the price ~5× more than ours).
- **Measured:** when a sniper lands like our model assumes (create slot, first or second outside buyer), its real result on rule #2 launches matches our model (+6.5% vs +6.1%). A sniper that lands one slot late on the same launches loses about 6% where our model says +6.7%. *Inference:* our model is right **only if we really land in the 20–35 ms class**; at ~80–140 ms (our older live buys) we would be the 7cp6zx row.
- On launches our model REFUSED (price >15% over the post-bundle quote when we land), faster snipers were the first outside buyer and won: GZDe8AQN 3yrJE1 +1.40 SOL (3 SOL, fill 1.08×) and CWiNFA +0.18; 8E4L9kgP 3yrJE1 +0.08; 7BEUZH3E 3yrJE1 +0.01.
- *Inference:* the fast snipers' buys are our exit liquidity. Our S+2 PnL tracks the outside SOL bought in S..S+2 (correlation 0.8 over 77 rule #2 launches): < 0.5 SOL of outside buying → all 25 launches lost (−0.049 each, the fee floor); 2–5 SOL → +0.051; > 5 SOL → +0.369.

## 5. Exit timing on our own model (`tapes.py`, `exit_sim.py`)

The competitors hold longer than we do (CWiNFA ~7 slots, 3yrJE1 20, the ladder bots 30–200). Is our S+2 exit leaving money on the table? I extended our model's replay past S+2 with the full trade tape of each rule #2 launch (S+3..S+15 from the chain; the 1 h dry hour's own recordings run to S+280). The entry is the unchanged model; only the exit changes. Exits that react to the price decide at the end of a slot and fill at the end of the next one. 76 of the 77 rule #2 launches (one tape not fetched); 73 with a complete tape (≤1 reserve-chain break) give the same picture.

| exit (sell everything at the end of …) | A in-sample (19) | B (30) | C–E 10-21 (27) | **held-out B–E (57): total / per launch** | B–E w/o best 3 | same, complete tapes only (54) |
|---|---|---|---|---|---|---|
| S+1 | +2.45 | +1.39 | −0.18 | +1.22 / +0.021 | −0.10 | +1.18 |
| **S+2 (today)** | **+2.52** | +1.83 | +0.12 | **+1.95 / +0.034** | +0.25 | +2.00 |
| S+3 | +2.11 | +1.91 | +0.58 | +2.49 / +0.044 | +0.37 | +2.79 |
| S+4 | +1.61 | +1.83 | +0.85 | +2.67 / +0.047 | +0.28 | +3.00 |
| S+5 | +1.31 | +1.89 | +0.11 | +2.01 / +0.035 | −0.38 | +2.39 |
| S+7 (~1.5 s, CWiNFA-like) | +1.35 | +1.90 | +0.48 | +2.38 / +0.042 | −0.01 | +2.89 |
| S+10 (~2 s) | +0.22 | +1.17 | −1.33 | −0.16 / −0.003 | −2.08 | +0.35 |
| S+14 (~3 s) | +1.84 | +0.81 | −1.48 | −0.68 / −0.012 | −2.70 | −0.54 |

Competitor-style exits on our entries (held-out B–E, 57 launches; A in brackets):

| exit | held-out B–E | A |
|---|---|---|
| hold to S+4 if up at the end of S+1, else S+2 | +2.94 | (+1.97) |
| sell when outside selling ≥ 0.5× buying in a slot, max S+4 / S+7 | +2.19 / +2.05 | (+1.75 / +2.02) |
| take-profit +10%, stop −5%, max S+5 | +2.18 | (+1.53) |
| sell 70% at S+2, rest at S+14 | +1.27 | (+2.36) |
| sell 60% at S+1 (D24ipY-style), rest at S+10 | +0.75 | (+1.60) |
| sell 50% at S+2, rest at S+10 | +0.97 | (+1.41) |
| trailing stop (arm +5%, drop 5%), max S+10 | +0.58 | (+0.94) |
| trailing stop (arm +15%, drop 10%), max S+20 | −0.58 | (+1.10) |

- **The best exit is a short plateau from S+2 to ~S+7 (0.4–1.5 s).** S+3/S+4 add about +0.01 SOL per launch held-out but lose about −0.02 to −0.05 in-sample (A), so the gain is inside the noise. **S+2 is the exit chosen on A, and it holds out (+0.034 per launch).**
- **Holding ≥ ~2 s (S+10+) loses** in A, B and C–E. Ladders, splits and trailing stops all do worse than plain S+2–S+4 out of sample. The competitors' longer holds work for them only after a pop (take-profits); their time-stop exits lose (3yrJE1's 20-slot exits −8.8 SOL, 4yFAz/8RvtT8 40 s exits).
- **No exit lever worth a live change.** A zero-cost paper check of S+3 next to S+2 is reasonable; nothing longer.

## 6. Fees and size on our own model (`exit_sim.py`, S+2 exit)

Same 77 rule #2 launches as FILTERS3 (A in-sample 19; held-out B 31, C–E 27), the unchanged landing model and the S+2 exit; only the cost or size changes. **The model keeps our landing time fixed, so these rows assume a cheaper fee does not land us later — that is the thing a live A/B must check (fees help; do not assume they are free to cut).**

| variant (per filled buy) | A | B | C–E (10-21) | held-out B–E: total / per launch / median | w/o best 3 (B–E) |
|---|---|---|---|---|---|
| **today: prio 0.011 + tip by class (0.001–0.015), refused buy −0.011** | +2.52 | +1.79 | +0.12 | +1.91 / +0.033 / −0.018 | +0.21 |
| prio 0.004 + tip 0.003 (CWiNFA-like) | +2.73 | +2.06 | +0.31 | +2.37 / +0.041 / −0.012 | +0.65 |
| tip only 0.006, failed buy ~0 (durable nonce, tip inside the tx) | +2.75 | +2.10 | +0.35 | +2.45 / +0.042 / −0.010 | +0.73 |
| 1.0 SOL, prio 0.003 + tip 0.003 | +1.86 | +1.39 | +0.20 | +1.59 / +0.027 / −0.009 | +0.41 |
| 2.0 SOL, prio 0.004 + tip 0.003 | +3.55 | +2.70 | +0.42 | +3.12 / +0.054 / −0.014 | +0.90 |
| 3.0 SOL, today's fees | +4.80 | +3.56 | +0.38 | +3.94 / +0.068 / −0.025 | +0.80 |

- **Cost:** cutting the fixed cost from ~0.015 to ~0.006 SOL per trade adds about **+0.008 SOL per launch** (+0.46–0.54 SOL over 58 held-out launches) and roughly halves the "flat loser" (31 of 77 rule #2 trades end between −0.03 and −0.07: that is just the fee floor).
- **Size:** in the model the return per SOL is flat with size (3.6–4.0% per launch at 1.0–3.0 SOL), so a bigger size scales the PnL. But the 10-21 period (C–E) is near zero at every size and its result without the best 3 is negative at every size, so a bigger size mostly scales the variance until the edge is proven. The model also cannot see other snipers reacting to a bigger buy.

## 7. What we can leverage (ranked)

Ranked by expected impact × confidence. "Model" = our FILTERS landing model on the 77 rule #2 launches (held-out = B–E, 58 launches); "real" = the competitors' on-chain results.

1. **Land first — and measure it on every fire after Alpenglow.** Confidence **high** that it decides the sign; medium on how much a change of route buys.
   - Model: first outside buyer +0.089 SOL/launch (50 of 77); one ahead +0.060 (11); ≥2 ahead −0.042 (16, 7 of them refused by the cap). 20 ms slower turns the 10-21 groups negative.
   - Real: the same rule #2 launches gave +6.5% to fast snipers and −5.9% to a slot-late one (7cp6zx). Anubis (feed ~102 ms, never first, 0.1% cost) lost −28 SOL in 12 h. Create slot vs S+1: DRWPSr +20.6% vs −10.1%, 9qz7cW +20.5 vs −5.7 SOL, 8ptvsh +3.9% vs −5.7%, 3yrJE1 +11.0% vs +0.4%, AqMoKz −1.4% vs −5.9%.
   - Our buys in the older live logs were seen at a median 78 ms (Run 1: 57–138 ms). The model needs 20–35 ms.
   - Concrete: log feed-seen ms, slot and block position of our own buy on every fire (Run 2's main output). Every profitable lane bot signs one tx with a **durable nonce** and sends it through 4–8 relays (nozomi, helius, astralane, flashblock, landx, stellium, jito, speedlanding, node1, soyas); only one copy can land and the rest fail for ~5,000 lamports. Our multi-path routing (arbx-lat) is the same idea. **Send-path change → needs the owner's OK.**
2. **Cut the fixed cost per trade from ~0.015 SOL to ~0.006 SOL and make a failed/refused buy nearly free.** Confidence **medium** (it must not cost landing).
   - Model: +0.008 SOL per launch held-out (B–E +1.91 → +2.37 with prio 0.004 + tip 0.003; → +2.45 tip-only with free failures); 10-21 (C–E) +0.12 → +0.31/+0.35; it shrinks the fee floor that 31 of 77 trades end on.
   - Real: the profitable lane bots pay 0.2–0.7% of size per buy (3yrJE1 0.2%, AHwJSn 0.4%, AMDEmV 0.4%, CWiNFA 0.6%); most pay through a tip inside the tx with ~zero priority fee. Across 12 lane wallets, cost share vs net return: correlation −0.39 (weak, confounded).
   - Cheapest piece: the lane bots set tight CU limits per tx (CWiNFA 80k, 3yrJE1 76.5k, AMDEmV 75k, 8ptvsh/9qz7cW ~50–59k; CU used ~50–60k). Our engine sets the priority as a CU price × a CU limit (`--cu-limit`, default 120k; 95k in its tests). A ~65k limit (if our buy uses ~55–60k like theirs) keeps the same priority per CU for ~35–45% less priority fee *(inference: check the CU our real buys consumed)*.
   - Risk: fees help landing (owner's rule) and the model holds landing fixed. Test as a live A/B (alternate runs on the same routes) judged by landing position first, PnL second. Send path → owner's OK.
3. **Keep the fast exit (S+2; S+3 is as good).** Confidence **medium** (76 rule #2 launches with long tapes; noisy).
   - Model (section 5): S+2 +0.034 SOL/launch held-out (the exit chosen in-sample); S+3/S+4 +0.044/+0.047 (but worse in-sample); S+10 −0.003, S+14 −0.012; ladders, splits and trailing stops +0.01 to +0.02 or negative.
   - Real: the lane bots that hold 1–2 s with one sell make +1–2%; the ones making more hold longer *only after a pop* (take-profit / ladder) and lose on their time-stop exits (3yrJE1's 20-slot exits −8.8 SOL; 8RvtT8/4yFAz 40 s exits). Copying their long holds on our entries loses in the model.
   - *Inference:* we profit from the snipers who buy after us in S..S+2, so we must be out while they are still buying.
4. **Size 2 SOL on rule #2 — only after 1 and 2 are in place.** Confidence **low-medium**.
   - Real: 3yrJE1 uses 2 SOL on rule #2 launches (+8.9% per trade on 11); dKMjeG bet 8 SOL on 6 of them (+20% per trade) but skipped the other 87; most tiered bots make most of their money on their bigger tiers (D24ipY, 8RvtT8, 2mqrin, 9qz7cW, 4yFAz lose or break even on their smallest tier); 3yrJE1 is positive on every tier.
   - Model: return per SOL is flat in size (+3.6–4.0%), so 2 SOL makes +0.054 SOL/launch held-out vs +0.041 at 1.5 SOL (both at the cheaper fee). But 10-21 alone is ~0 and negative without the best 3 at every size, so today it mostly scales variance.
5. **No new selection rule.** Confidence **low** that anything here would hold out of sample.
   - The fast snipers concentrate on rule #2 (pick rates 12–17% vs 1–5% elsewhere): it is the right lane.
   - The rule #2 launches they buy are better on our model (+0.104 vs +0.034 SOL/launch), but their buys are our exit liquidity, so this is mechanical and not visible before our buy *(inference)*.
   - Skipping BAM-leader launches (model +0.017/launch on 13, −0.35 if 20 ms slower) is too thin to act on; recheck after Run 2.
6. **Not worth copying:** the conviction bots' selection (2mqrin / 8RvtT8 / dKMjeG / 9qz7cW / 4yFAz bought only 0–8 of 93 rule #2 launches each and made their money elsewhere), and "follow a fast bot's buy" (they land at the same time as we would).

## 8. Is rule #2 at 1.5 SOL with the S+2 exit net positive?

**Short answer: not proven, and not "net positive from every angle".** It is break-even to mildly positive *if* we land like the fast snipers, and negative if we land one slot late. The most recent day (10-21) is flat on our model and slightly negative on paper.

| angle | what the data says | read |
|---|---|---|
| Our model, rule #2, 77 launches (A–E) | +4.43 SOL; per launch A +0.133 (in-sample), B +0.058, C–E (10-21) **+0.004**; median −0.011 to −0.030; win 35–47%; B–E without the best 3 +0.21 | positive on 10-20, flat on 10-21 |
| Paper loop (live engine, 10-21 09:23–15:31) | 49 rule #2 launches **−0.31 SOL** (+20 ms: −1.02); of the 48 I could split: before AG 26 +0.04, after AG 22 −0.44 | flat to negative |
| Landing speed | model: first outside buyer +0.089/launch (50 of 77), ≥2 snipers ahead −0.042 (16; 7 refused); +20 ms turns 10-21 negative | **the deciding factor** |
| Same launches, real snipers | fast snipers +6.5% real vs our model +6.1%; a slot-late sniper −5.9% real vs our model +6.7% | model right only if we are fast |
| Our measured live landing (older logs) | our buys seen at 9–148 ms, median 78 ms (n 18); Run 1 57–138 ms | the slow class, unless the new routes hold after AG |
| Real copies of our design (fixed size, one quick sell, 0.6–2.2 SOL) | positive: CWiNFA +0.36 SOL/h (cost 0.6%), AHwJSn +0.23 (0.4%), BXB7FF +0.13 (1.3%, create slot 100%); flat or negative: 8ptvsh +0.07 (1.9%), 9XPMCa +0.03 (3.9%), Six5j1 −0.02 (1.5%), 54YNHF −0.06 (0.9% + failed-tx fees), AqMoKz −0.10 (1.7%); slow: Anubis −2.3 SOL/h (0.1% cost, ~102 ms) | ≈ break-even on average; the positive ones are cheaper or always first |
| Exit | S+2 to S+4 is the best simple exit on our entries; ladders, trailing stops and ≥ S+10 holds lose (section 5) | keep S+2 (or S+3) |
| Time of day | 5 lane bots (CWiNFA, AHwJSn, AMDEmV, 8ptvsh, 3yrJE1) positive in every 6-h block (+1.5% to +2.9%); 16–17 h and 20 h UTC negative; our model per 3-h block all ≥ 0 except 00–03 h (n 4) | one day only: no gate |
| Leader type | model: Harmonic +0.081 (21), Jito +0.063 (41), BAM +0.017 (13; −0.35 if 20 ms slower) | BAM weakest, n small |
| Alpenglow | **on rule #2 launches the tracked snipers went from +2.2% per trade before AG (70 trades, +8.0 SOL) to −3.9% after (29 trades, −0.27 SOL)**; overall, most lane snipers did as well or better after AG (US hours; 3yrJE1, AMDEmV, AHwJSn up; CWiNFA, BXB7FF about the same), dKMjeG lost −6.1 SOL in 1.5 h; their create-slot share vs 12:00–13:54 fell for most (CWiNFA 84→69%, AHwJSn 82→58%, 3yrJE1 77→64%; BXB7FF and D24ipY unchanged; small n); our paper after AG −0.44 on 22 (create-time gate broken) | unproven for us |

**Conditions under which it is net positive** (model + real snipers agree):

1. **We land in the create slot as the first or second outside buyer, ≤ ~25–30 ms after the create.** Without this nothing else matters.
2. **Fixed cost ≲ 0.006 SOL per trade** and a refused/failed buy costs ~0 (tip inside the tx, durable nonce).
3. **Exit at S+2–S+4.** Do not hold for seconds on these entries.
4. **A busy market.** The model was +0.06 to +0.13 per launch on 10-20 (2–3× the launch rate) and ~0 on 10-21.

Under 1–3 the expected value is about **+0.03 to +0.05 SOL per rule #2 launch, ≈ +0.25–0.4 SOL/h at ~8 launches/h** — the same as the real snipers who do exactly this (+0.1 to +0.45 SOL/h). **0.5–2 SOL/h needs conviction sizing (2–8 SOL) with laddered exits on launches we cannot yet pick (2mqrin, 8RvtT8, 4yFAz, dKMjeG, 9qz7cW).**

**For Run 2 (my read):** run it as a measurement run, not a profit run. The go/no-go numbers are our real feed-seen landing ms and block position after Alpenglow (target: create slot, ≤ 30 ms, first or second outside buyer on ≥ 60% of fires) and the real fill vs the model's price. If landing is in the fast class, the cost cut (lever 2) is the next change; if it is in the 60–140 ms class, rule #2 at 1.5 SOL is expected to lose (the 7cp6zx row).

## How it was measured

- **Read-only.** Public RPC on the host only (publicnode first, api.mainnet-beta when publicnode has no data), at most 3 requests in flight in total, paced with retries. Nothing was sent; nothing on the server was touched; the paper loop's files were copied (`cp`) and only the copies were read. The server was not used.
- **Data** (not committed): `/home/moiz/sniper-data/research/competitors/` — `launches.json`/`cand.json` (discovery), `w/<wallet>.sigs.json` + `w/<wallet>.txs.jsonl` (wallet histories), `tapes/<mint>.tape.json` (rule #2 launch tapes to S+15 or S+30), `paper_c6_copy/` (read-only copy of the paper loop's recordings, log and output), `comp_rows.json`/`comp_summary.json` (per-trade rows and per-wallet results).
- **Scripts** (this folder):
  - `discover.py` — candidate wallets from every block recording + the engines' `RACE obs` feed timelines.
  - `sigs_multi.py`, `txs_multi.py` — signatures, then every successful tx + 40 sampled failed ones (handles the new v1 transactions, whose priority fee sits in `transactionConfig`).
  - `comp_trades.py` — round trips, PnL, fees, routes, landing (create slot from our recordings / DETECT logs), joined with our model rows.
  - `deep.py` — per-wallet deep dive (tiers, exits, landing, fees, selection inside our watched launches, pre/post Alpenglow).
  - `same_launch.py` — competitors' real PnL on rule #2 / watched launches next to our model.
  - `tapes.py`, `exit_sim.py` — rule #2 launch tapes and the exit / fee / size test on our model (entry = `filters.py` `run()` unchanged; `fixed S+2` reproduces the FILTERS p2 exactly: mean |diff| 0.0000 on 77 launches).
  - `table.py` — the competitor table.
- **Run order:** `discover.py` → `sigs_multi.py` → `txs_multi.py` → `comp_trades.py` → `deep.py <prefix>` / `same_launch.py` / `table.py`; `tapes.py` → `exit_sim.py`.
- **Caveats.**
  - One day of data (10-20 15:30 → 10-21 15:35 UTC); post-Alpenglow is only ~1.7 h and overlaps the US-hours market.
  - Only SOL-quote trades are priced; several wallets also trade non-SOL-quote launches (not counted).
  - Fetch caps: 9qz7cW covers only its last 6.4 h (2,500 newest txs); 6anjqM 5.4 h and H9kuqG 6.1 h (low-priority wallets, 600 txs); 3oN2NB 12.9 h, DsGJkP 16.1 h, 2mqrin 18.4 h; Anubis stopped trading after 12.4 h; the others 21–24 h.
  - Failed-tx cost = sampled mean fee × failed count in the span.
  - "dslot" needs the create slot from our own logs, so it covers only the creates our engines saw (about half of each wallet's trades).
  - Hold-time and exit-type splits of the competitors' PnL are not causal (their exit rule decides the hold). The causal exit test is section 5, on our own model.
  - Our model lands us 20–35 ms after the create; our real live buys in the older logs were seen at 9–148 ms (median 78 ms, n 18; Run 1 57–138 ms).
