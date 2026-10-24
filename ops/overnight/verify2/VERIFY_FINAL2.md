# FINAL-2 replay: independent check (verify2)

2026-10-23, times in PKT (UTC+5). Read-only and offline: nothing was sent and no server was touched.

- **What was checked:** the claim in `BECOME_THEM.md` §2 and `report/FINAL2_STRATEGY.html`. Strategy: FINAL-2 live picks, a 0.5 SOL buy landing at 75 ms (or 45 ms), a 0.5% guard, an 8 s hold, today's costs.
- **How:** my own extractor reads the raw collector chunks. My own replay does the placement, guard and curve math. Nothing in `core/` was imported.

**MEASURED** = computed from the chain tape or the engine's own logs. **INFERRED** = a model or assumption.

## Verdict

**The arithmetic is right, but the result is overstated, and the corrected result is not proven.** The claim does not hold at the size stated.

**Arithmetic (MEASURED).** I re-ran the claim's own method on my own data:
- On every pick that fills in both replays, the PnL matches exactly (88 at 75 ms, 125 at 45 ms; no difference above 0.005 SOL).
- The totals are within 0.03 to 0.13 SOL of the claim.

**Three replay bugs push the result up (MEASURED).** Each favours us:

1. **Some trades we can't beat are placed after us. This is the biggest error (−0.61 SOL at 75 ms).**
   - In its first ~3 ms the engine counts every buy as part of the dev's "bundle", so those buys never appear in its arrival list (`outs`).
   - The engine's own decide line counts them (`old_bundle_n` minus `bundle_n`). 25 picks have such buys.
   - On chain they are not in the creator's back-to-back bundle, so the replay calls them "unseen" and puts them behind us.
   - In reality they reached the engine within ~1.5 ms of the create, so they land ahead of any buy of ours.
   - Effect: 6 fills at 75 ms (10 at 45 ms) turn into guard fails. Examples:
     - Pointless Coin: 31.5 SOL of bundle buys at block positions 68–70, absorbed by 1.4 ms. Replay +0.214, really a fail (price 2.9× the guard).
     - The PHP Hero: a 4.94 SOL sniper absorbed at 1.1 ms. Replay +0.489, really a fail.
2. **Some buys the engine saw before our landing are missed (−0.10 at 75 ms, −0.12 at 45 ms).**
   - For fixed-token buys, the engine logs a SOL estimate that ignores the bundle, so it is too low by more than 15%.
   - The claim's 15% match tolerance then rejects them, and the replay treats them as unseen.
   - Example: Cuck Coding. AHwJSn's 0.395 SOL buy was seen at 38.4 ms but logged as 0.328, and the replay puts us ahead of it.
   - 4 fills at 75 ms (9 at 45 ms) should be guard fails.
3. **Gaps in the data (−0.11).**
   - From 01:33 to 01:43 PKT the collector lost about 11% of slots, mostly single slots; a normal hour loses about 0.3%. This happened before its 01:57 crash.
   - Separately, some recorded transactions are missing trade events. Two examples: a second buy inside a create transaction, and multi-wallet sells.
   - The claim's replay never re-syncs to the curve, so missing sells overstate later prices.
   - The worst case is Misanthropic, a top-5 winner. Inside its hold, 4 gaps hide about 4.0 SOL of net selling. +0.509 becomes +0.413, and that is still unreliable.

**Corrected totals (MEASURED, my replay, the claim's 235 picks).** Table A gives every row.
- 75 ms: **+1.64 / +1.04 / +0.53** for slippage / pros removed / all snipers removed (claim +2.46 / +1.72 / +1.30).
- 45 ms: **+3.40 / +2.03 / +1.27** (claim +4.24 / +2.70 / +1.97).

**Why even the corrected numbers are weak:**
- **The 5 best trades carry the whole result.** At 75 ms the best 5 fills make +3.67. Without them the total is −2.03: the other 77 fills lose −1.26, and the 153 failed buys cost −0.77. Median fill −0.019, 39% win.
- **The first half of the window lost:** −0.23 in the first half, +1.88 in the second (75 ms).
- **Bootstrap odds** that the 75 ms total is above zero: 0.78 / 0.68 / 0.59 for the three variants. 90% ranges: [−1.5, +5.1], [−2.0, +4.4], [−2.4, +3.9].
- **Slippage limits are missing for most followers** (MEASURED).
  - Only 25% of follower buys (32% of their SOL) inside the 8 s holds have a decoded limit.
  - The fetch list `slip_sigs_10.json` stops 10 slots (~2 s) after our buy.
  - Every other follower is assumed to buy anyway.
  - INFERRED: giving them limits drawn from the measured distribution costs another 0.2–0.55 SOL at 75 ms.
- **Landing time matters a lot.** One fixed landing time is assumed. Moving it ±10 ms swings the total (75 ms, slippage variant): 60 ms +0.80, 65 ms +1.34, 75 ms +1.64, 85 ms +1.10. Spread evenly over 65–85 ms it averages +1.47 (pros removed: +0.85).
- **Costs.**
  - At Run 2's actual fee level (about 0.0235 per buy, 0.0105 per failed buy) the corrected 75 ms result is **−0.31**.
  - Sells are costed at 0.0005. At 0.01 per sell the slippage variant drops to +0.86.

**Bottom line (INFERRED).**
- **75 ms with today's assumed costs:** the honest estimate is about +1.0 to +1.6 SOL over 8.3 h overnight. That is 0.6 to 1.0 SOL less than claimed, rests on 3–5 trades, and has roughly a 1-in-4 to 1-in-3 chance of being ≤ 0.
- **45 ms:** about 2× better (bootstrap odds above zero 0.89 / 0.77 / 0.67), with the same caveats.
- **Not enough to justify risking money at 75 ms.** A capped test would mostly measure luck in the tail.

## Table A: claimed vs mine

0.5 SOL, 8 s hold, today's costs (2% buy overhead, −0.005 per failed buy, 0.0005 per sell); 235 picks, SOL over 23:36–08:06 PKT. "Slip" applies the decoded follower slippage limits. "Pros removed" also deletes the 9 pro wallets' buys after our entry. "Snipers removed" deletes all 321 fast-sniper wallets' buys and, like the claim, skips the slippage check.

| Variant | 75 ms slip | 75 pros removed | 75 snipers removed | 45 ms slip | 45 pros removed | 45 snipers removed |
|---|---|---|---|---|---|---|
| **Claim** (`final2_picks_v3_become_B0.5_tu.json`) | +2.46 (92 fills) | +1.72 | +1.30 | +4.24 (134) | +2.70 | +1.97 |
| Mine, claim's method (raw tape, claim-style placement) | +2.36 (88) | +1.64 | +1.23 | +4.11 (125) | +2.62 | +1.94 |
| + tape repaired | +2.25 (88) | +1.55 | +1.15 | +4.00 (125) | +2.54 | +1.86 |
| **+ absorbed buys put ahead of us (corrected)** | **+1.64 (82)** | **+1.04** | **+0.53** | **+3.40 (115)** | **+2.03** | **+1.27** |
| Corrected, snipers removed *with* slippage | | | +0.38 | | | +1.09 |
| Corrected + imputed follower limits (INFERRED, 3 draws) | +1.10 … +1.45 | +0.65 … +0.93 | +0.07 … +0.31 (with slippage) | +2.67 … +3.03 | +1.51 … +1.83 | +0.67 … +0.96 |
| Corrected at CW-style costs (1.2%, 0.003) | +2.27 | +1.67 (HTML: +2.38) | +1.16 | +4.10 | +2.73 (HTML: +3.44) | +1.97 |

- **Claim's method vs claim:** the gap (≤0.13) comes entirely from bug 2, and the 4 (75 ms) or 9 (45 ms) differing picks are listed by `a4_diff.py`.
- **All 238 picks:** adding the 3 picks the claim's data snapshot missed (07:59–08:06 PKT, a data cutoff, not chosen by outcome) changes the corrected numbers by −0.03.
- **30 ms, corrected:** +5.27 / +2.97 / +1.75 (claim +6.91 / +4.44 / +3.22).

## 1. Reproduction (task 1)

**Data (MEASURED):**
- `x1_extract.py` decodes TradeEvents and CreateEvents directly from 104 raw chunks.
- It found 576,647 transactions on the 238 picks, including failed ones.
- All 238 creates are standard SOL curves: 30 SOL / 1.073e15 virtual reserves, no mayhem, SOL quote (222 Token-2022, 16 legacy SPL).

**Replay (`v2core.py`, `v3_replay.py`):**
- Placement uses the engine's own `outs` timeline.
- Each `outs` entry is matched to a transaction by fee-payer prefix: buys within the amount tolerance first, then failed transactions, then any buy by that payer.
- Our buy goes after the last transaction seen before L. Every transaction earlier in block order is ahead of us too.
- The rest of the mechanics:
  - the guard compares against the chain's post-bundle price;
  - fees use the event's fee + creator-fee bps;
  - we receive 1.5% fewer tokens;
  - the sell is the curve state just before the first trade in slot ≥ buy slot + 38 (8.06 s at 212 ms per slot).
- **Slot time (MEASURED):** 211.9 ms from block times across the window, so the claim's 212 ms is right.
- **Per pick:** `work/v3_res.json` has every pick, for both tapes and all placement modes and variants.

## 2. Look-ahead and leakage audit (task 2)

**(a) Were picks decided before the outcome? Yes; no leak found (MEASURED).**
- The pick list is exactly the scorer's `final_pick` records from 23:36 to 08:06 PKT (238). The 25 later picks were left out, which is fine.
- **Scoring delay (`t_scored − t`) for picks:** median 35 ms, p90 54 ms, p99 66 s.
  - The 3 slow ones are GyfFMV, CZ5qic and AtmnBV (66–171 s). They are the backlog from the scorer restart at 00:18 PKT.
  - Their features could include up to ~3 min of later creates. They are worth −0.04 SOL in total, so they do not inflate anything.
- **Features are causal:**
  - create and bundle facts come from the engine at decision time (median 1.7 ms after the create);
  - history uses launches settled ≥10 min earlier, in closed chunks;
  - the `outs` timeline is used only for placement, never for picking.
- **Models:** frozen 10-22 23:25 PKT, trained on R1's first 80%, before the window opened.
- **Mid-window config change:**
  - The guards (payer must be the creator; no-bundle launches need ≥1 SOL dev buy) were added at 00:18 PKT. That was 3 minutes after the VumboDepot rug (00:15), which is one of the window's own picks.
  - This is not look-ahead for later launches, because the rule was then applied going forward.
  - The 52 launches it vetoed would have lost −0.58 at 75 ms and −0.83 at 45 ms (`a9_guards.py`).
  - So the window mixes two configs, and the guard looks useful.
- **Live timing (INFERRED):** "75 ms" assumes the pick is ready at bundle close. The current sidecar answered in 35 ms (median) in log-tail mode. The doc's own plan (§4.2) says scoring must move inside the engine first.

**(b) Is the placement at 75 ms honest? No; see bugs 1 and 2 (MEASURED).**
- The block-order rule itself is applied correctly (`place_bo2`).
- The 24-entry cap on `outs` was reached before L on 2 picks, neither of them a fill.
- Every match before 100 ms lands in slot S or S+1.
- Hand checks:
  - Cuck Coding: AHwJSn seen at 38.4 ms, placed behind us by the claim.
  - Pointless Coin and The PHP Hero: absorbed bundle or sniper buys, placed behind us by the claim.
  - The 3 winners in §3.
- **Knife-edge fills:** at 75 ms, 9 fills sit less than 10 ms ahead of a transaction the engine saw. Together they are worth +0.69, mostly WarHound, which lands 7 ms ahead of a burst of 10 sniper buys seen at 82.3 ms.

**(c) Is the guard reference known at decision time? Yes, mostly (MEASURED).**
- The engine closes the glued bundle at a median of 1.7 ms.
- For 230 of 238 picks, its post-bundle price matches the chain within 0.2%. For 6 picks the engine's price is +0.2–0.3% higher (a slightly looser live guard).
- The two big mismatches are explained:
  - Flying Tesla: the chain events miss a second buy inside the create transaction. The engine counted it, and the repaired tape agrees with the engine.
  - CZ5qic: unknown bundle legs.
- 3 picks with unknown or open bundle legs would never be asked live. Removing them changes the total by +0.04.
- The open problem is the transactions absorbed outside the glued bundle (bug 1).

**(d) Is the 8 s sell timed from our buy? Yes (MEASURED).**
- The claim's `sim` starts the clock at our buy's slot (the slot of the trade we land after) and sells before the first trade at or after 8 s. My replay reproduces this exactly.
- Hold sensitivity, corrected 75 ms slippage variant: 5 s +1.27, 6 s +1.81, 7 s +1.75, 8 s +1.64, 9 s +2.12, 10 s +1.82. So 8 s is not a cherry-picked spike at 75 ms.
- At 45 ms, 8–9 s are local peaks: 7 s +2.29, 8 s +3.40, 9 s +3.89, 10 s +3.10.
- The exit was still chosen on this same window.

**(e) Do the "removed wallets" variants keep sells and a consistent curve? Yes (MEASURED).**
- Only buys after our entry are dropped. Sells are kept, even sells of tokens the removed wallet no longer bought, which is conservative.
- The curve is recomputed from our entry using each kept trade's SOL or tokens.
- Followers dropped for slippage also keep their later sells (conservative).
- The claim's "all snipers removed" variant skips the slippage check. With slippage it is 0.15 lower.

## 3. Fat tails at 75 ms (task 3)

Corrected replay, slippage variant. PnL in SOL. In brackets: the claim's number for the same pick.

**Top 10 winners**

| # | PnL (pros removed / snipers removed) [claim] | Token | Created (PKT) | We land after | Last trade before our sell |
|---|---|---|---|---|---|
| 1 | +1.239 (+1.215 / +1.172) [+1.239] | [JUSTICE FOR BAKED_SOL](https://gmgn.ai/sol/token/3NmDDmd8iDCjE4Pv1s6ScPBEcVMkJZHAezVoGydcQS8H) | 10-23 02:56:13 | [vf9QgMRt](https://solscan.io/tx/vf9QgMRtnj3YWEZyaiLFjJiLNcnetA1SoUU8N22NXBRvfG9EXGyYq7Jp5Rq1LB9zTQqHTfmffzpeiZPrkc1mZxC) | [2zyonPgK](https://solscan.io/tx/2zyonPgKHB4VdDeeF6wX3D75jZWUiBEHCzX6SXWxo5HNpdL32SrHJ7i16nSFYfNz6B4c5ci8LAYSn2LVc3UcCFdW) |
| 2 | +0.823 (+0.823 / +0.779) [+0.823] | [Movember](https://gmgn.ai/sol/token/cBDfDSweaHmLuwTqCobZb5AL4b7MWFuzhNmXfpumove) | 10-23 03:44:55 | [3bSM1Sjc](https://solscan.io/tx/3bSM1SjcnkjawmafuGHrfBF4Q2ynXx4HjV9nFki458E2eXZpYvWSo6HutF1tAP3GQNcV5rC1ka2vtq8Xm5gdaq7X) | [rzTX1kJB](https://solscan.io/tx/rzTX1kJBJnNjZf2xgAwDh9cpamTA6DQUQwLYXtunkungbtKSP4qDWyHdB5iBbYavBPY2RTYoEkPsu9svUazbWAb) |
| 3 | +0.689 (+0.689 / +0.718) [+0.689] | [WarHound](https://gmgn.ai/sol/token/3nJzJCM29ETk73nq36oNZir5z3hd7nEtFM3uo2LHpump) | 10-23 04:56:57 | [2U68FVsK](https://solscan.io/tx/2U68FVsKSjSsk8E2E4NLWh4j3sCWghkU7BRyQKiCe3mXCpZCbLCGLF5QMYKpQHQALxgW265zPW3AQknz9JJeTTYK) | [CSnJVcxC](https://solscan.io/tx/CSnJVcxCTWWzhZaztbQXBtjEg45GnfbJYKpxJ5f5ZSsjdpzyk7g6Hnuc9eDH4TFiwu25AXd9h3Dcs3o35AjRhBc) |
| 4 | +0.503 (+0.486 / +0.468) [+0.503] | [BurnPad](https://gmgn.ai/sol/token/GkQ3M6znWrTRhDcQ8Eg3QAPBqXmEKz5AwPj1QPJEpump) | 10-23 06:29:55 | [3BHPXHzW](https://solscan.io/tx/3BHPXHzWLeMBB1PjEbP2BaZejrNxuGKdc13LDZKR5S78WNaw9y2oo22ik9T3u8UioA532igpFuaeqztbHSzZHxNo) | [2EcVkXw4](https://solscan.io/tx/2EcVkXw4Lckgi7486R7kxBsmpcownudvsifUzctMt4D532TCrTvT8RtAm8kk5yktmiLx71ccMsmH3YSb9R9d5DoH) |
| 5 | +0.413 (+0.275 / +0.246) [+0.509] | [Misanthropic](https://gmgn.ai/sol/token/Hc5sxDEhdvjZfyZT54UJPvcs1oBsY1k3JWEz78z2pump) **data gap** | 10-23 01:39:22 | [pG1Q5cXQ](https://solscan.io/tx/pG1Q5cXQEPzpbEyiFWuNyhpcyKR5bKhe1FvUx71U4t6EvjbcEah5DZsiR5FAMHyzBoi96BuaXsfzLojKLAhTLeG) | [jsJmZM7c](https://solscan.io/tx/jsJmZM7cXBDywNS9QmFfzRqS3RQm6uDRMxXNpEP5hecoPqe1Ykt81JitZd2cYzUvsbbVox7yjgDU2NbbJyxMegq) |
| 6 | +0.409 (+0.390 / +0.371) [+0.409] | [McDoge](https://gmgn.ai/sol/token/6G34XizYUYwnE1XNPXAV1n7udhTzqZkbmxbJ222hpump) | 10-23 07:02:34 | [65YujFw5](https://solscan.io/tx/65YujFw5Ssw4HJmxyGKX21kpQbCh9Wk9XKPRGc6RNj675D6ENGAUEUeuCGdqJgDjbPZGZQNzpaTRXNX9i2EY2yrF) | [4gDkurrQ](https://solscan.io/tx/4gDkurrQdH4a2yFRC62ZWCkx1JJyufJq2phey2JqypZnXfdzWF7f3Br3LAPyK5a6oK1yikqDNv45yav6Xi4fS5YE) |
| 7 | +0.399 (+0.362 / +0.358) [+0.399] | [stablecoin](https://gmgn.ai/sol/token/8Zg51MAP6LVF2giKXKEL5eBmx9Syy7rWvdr28jiSpump) | 10-23 06:18:04 | [3WugAeUn](https://solscan.io/tx/3WugAeUnjE5BfN7miS6jBqk3ZKJB14sj2Um5Xud3jJe5EktgmmdkFzganUKoiYN3d8Efiy7B42gsa2f2o2oWrnUT) | [4JGK5w2w](https://solscan.io/tx/4JGK5w2wTSrbRzaeRt5eVu3xkwVae4MEaG4aBtMNYwBDKsYDgSbNmqzuaey1VqtfXtewU3EmDcRmh3HRTa79PTo9) |
| 8 | +0.217 (+0.205 / +0.204) [+0.217] | [FOMO](https://gmgn.ai/sol/token/FNAyTiNhRTjbzq2G72z3uUVZd2UPHxeHPZoCuiMvpump) | 10-23 02:48:41 | [3S3kyNic](https://solscan.io/tx/3S3kyNicifYCAgrXbJK63SWpq7j5RXRr7oh4v7zkqEGFb2D12htSbg1XjnkzxB8cTSwWkiFgwK8HpF3URR1QkHjX) | [396ZcYjk](https://solscan.io/tx/396ZcYjk2VLaqqGroxQkQbqzX4EJS8eFuQieQcCQW3Z6gyKZLaH4Q7yZVbWk7VsATkA3uPPCzo7KxpSHRMYpc91g) |
| 9 | +0.153 (+0.153 / +0.152) [+0.153] | [Book of Pain](https://gmgn.ai/sol/token/gUvfc8XHpqyvpHAg277a4nzwoMVQFGPb6u6Uajzpump) | 10-23 02:29:29 | [4bNvkfc6](https://solscan.io/tx/4bNvkfc6UurCTtjH4fE1qauaG7XB4G5vXJiKTJwp8SAfK3GGJwRGxdDpmLEpYT1mZV9QgX71VkAXPVz6EY4ytKgQ) | [P1X3tVSA](https://solscan.io/tx/P1X3tVSAn39fc9pTWC7EXxPYHrvYxc8zxspqpSqYzMJqpUMRPwFd4ivYUC5GnXVcXhZsnH5iNgm3HG4dWzb4rWV) |
| 10 | +0.122 (+0.122 / +0.118) [+0.122] | [The McRib Indicator](https://gmgn.ai/sol/token/4iuDx8zqzwn9GhmiRQMTUgFeGFmQACu8ZKh5DWtnpump) | 10-23 00:29:07 | [2SYXpJLH](https://solscan.io/tx/2SYXpJLH4Ya9Nj8YdWxtn9JzhP6k9TLsHPKX6JHr7kz2jWozcimWAUt4qrurVgajyJ6p3yAyALu77U2WmpfiNwn) | [63trgwgK](https://solscan.io/tx/63trgwgK4Cfmy1FNohKws8mFngdZhhbXgo4pPApt1s1GqPV39HBQa8pX7cqijaZSNcrZR3qsrnc7UzHS5LjWbEgy) |

**Top 10 losers**

| # | PnL (pros removed / snipers removed) [claim] | Token | Created (PKT) | We land after | Last trade before our sell |
|---|---|---|---|---|---|
| 1 | −0.238 (−0.238 / −0.240) [−0.238] | [Debitcat](https://gmgn.ai/sol/token/9L4qHWECBW8q1uJMU9nt8y9XQ6vTwpU9ExyCbf9Mpump) | 10-23 03:32:34 | [4KpbEHwc](https://solscan.io/tx/4KpbEHwcywuEFcF64Qg28qH4ABu2HQVwLoJzBWs2DYcfTpkfggpKcdNc4yuDxp7MDmGgP4XqLCYaA52ZnkEUDBWa) | [36zXEg5r](https://solscan.io/tx/36zXEg5rVKXPHyynZ6YJuXApbxGjRAg7V1SCR9CaKQp9hmrC7kpEX4Ac6b27NCD1zD8cneQXGGxgefxswoQcSe4f) |
| 2 | −0.226 (−0.226 / −0.225) [−0.200] | [justice](https://gmgn.ai/sol/token/4zYnAQBGnbTjZQYDBMNadYMd4fLyLMxpmxQLVoNhpump) (missing 1.93 SOL sell restored) | 10-23 03:06:16 | [4e2Kw6AF](https://solscan.io/tx/4e2Kw6AFmt99DhJCve5G9PHKtdxvNPAi4DdPbf6s7TT6CpBBK4iXsUd7X1kDJXcbNAjxsUvjbMwz21BBPzBPyb3k) | [41heCtaQ](https://solscan.io/tx/41heCtaQsPCEr1m73hrsRM8MWoaFxCEYj2cWw73zXuPabTs8zZaAr3p4YHHU7YgNu6AAFSdCrYgJNUE1PEDkxSxB) |
| 3 | −0.222 (−0.236 / −0.236) [−0.222] | [Daily.fun](https://gmgn.ai/sol/token/Cb4qegLfHV5GiuKD3WH8epcsHj7j9E7CivnzStwdayLi) | 10-23 00:49:50 | [3Cdim2NV](https://solscan.io/tx/3Cdim2NVfFTSKvbN7kpGaXHZe16ZFeyu1rLMBJRHFxJcbaZerbzJ5bT8rN42PEPwaHVjnLGVQdJcYiEX44prt8e1) | [4fNQM4Hg](https://solscan.io/tx/4fNQM4HgZaonetG344RiRHFAvbzyn2WtRQH4B87r6dFARmeBm2SsigupK6TvrwRbp3njHBtF24rvAkerr5etujFC) |
| 4 | −0.196 (−0.196 / −0.188) [−0.196] | [ElePHPant](https://gmgn.ai/sol/token/5x8AedJP2fGXU5zVcUgfnGwB8Uv25CifZsNp9bL4pump) | 10-23 01:59:37 | [29yMCaaT](https://solscan.io/tx/29yMCaaTnN8GAnPg2eU7x1oFzdcNb6uUDVNLXyjcxsizvJHqHM3HibZGtTMFP3hdB2LjpESd49pDtcjm46rMVg3L) | [2ZmB78zA](https://solscan.io/tx/2ZmB78zAq3za5uq6RLJZ519vYj2HfLuehRiEjrfwU6aKFveBpcFdNL2WQtYaGZMVxR9Rmrw4Y3v5yQxdN8YUsUEg) |
| 5 | −0.168 (−0.168 / −0.208) [−0.167] | [nut](https://gmgn.ai/sol/token/8PKnXinba1JUPbP7qScB4Px4FYNDf29Sd6nFgyWrpump) | 10-22 23:56:07 | [5Co1oEVd](https://solscan.io/tx/5Co1oEVdLmkuf9AcpKpWKannvtsmm7LRFwrftzVPSwZqeRVV8hwmVP8WUuRvBmZijjR1YAW26N7brLrB75k2CXUH) | [4rN3tMnq](https://solscan.io/tx/4rN3tMnqR8iddDsGCSE9rafkMNBtC9xigN3ibiVG3tJCSvJVnmevoCVADkhSpoAMFNsHqn1vWM9uLr6MtQJVHzkc) |
| 6 | −0.158 (−0.158 / −0.158) [−0.158] | [Cookie Tung Tung](https://gmgn.ai/sol/token/BTMV2VgqM6vVN95Uf67j3EVqQW8jvNkkhRrf3ioDpump) | 10-23 01:04:34 | [xsu7hRdS](https://solscan.io/tx/xsu7hRdSe45N3eYZJSnoYfh9Tg1uuuXCXVoEdnyGtK8TSng8oUu2Rg2SGEzDV76r5Le4yGcMq4x8W2M49bzCx2D) | [9Ysg9tm8](https://solscan.io/tx/9Ysg9tm83vwuh4o4S56sCMAgEQmWRPuWLk8ME32JKXmRYXZVK6ovdNkB9HcV8qayiKbcqiytXcwRUvUtXV6VB2y) |
| 7 | −0.137 (−0.137 / −0.149) [−0.137] | [Zoinbase](https://gmgn.ai/sol/token/ChVfnh4tArX4S9nVoECtqBk57uRxVWAPYePFZqfhpump) | 10-23 03:42:56 | [4hzavsA1](https://solscan.io/tx/4hzavsA1UEz1sFWLiWvos6sfbgrCyYokZRQ9Zb9iLwQXSfsDjrygCGw78AqtdRAWKtZhtLbqwaSQqLKNDF6cQunU) | [37iwo9Qa](https://solscan.io/tx/37iwo9QaYEZomnobGu55c1j91cKUB1M1mhmL5eDRzvfsyamgFr81XE73j2W4oQt3Tg8KcCDE7VZwEdmePq5mh9wn) |
| 8 | −0.130 (−0.130 / −0.135) [−0.130] | [Marscoin](https://gmgn.ai/sol/token/8n2QY7ErQKZiuHiGQYqoNSjHhFvxZCgMiWwz59UVpump) | 10-23 04:06:07 | [3DVhCKEJ](https://solscan.io/tx/3DVhCKEJTmsD1UK7ZhaHGCG6ui83Zvhn4wKkwpVofhPsvEZ4piHS5mib1c859f7FqGzBuuGVv1DtQnMUraAKXoZX) | [5chhHcL7](https://solscan.io/tx/5chhHcL73jX8X7sCmwgeUVb5RKPu38KTPLrwxbfBHBSnvCpRDyGFPhMnZTaQwfmTM4u6X9abnqz25s99bMEXW9G2) |
| 9 | −0.130 (−0.130 / −0.131) [−0.130] | [Singularity](https://gmgn.ai/sol/token/HG544ooM7bX5QgwUG7NTeVx2oyBPHY7FvYG3AQ6kpump) | 10-23 01:05:45 | [5JiMfjK5](https://solscan.io/tx/5JiMfjK5uUY3JJ6K8tZmuJ2LArNYkfSoyPTpMX3N5w2Jh7XTQ3oJNTDzVq9DPP1yn2WaxXacKvSjcSarK4PyPqfv) | [4uHnWse2](https://solscan.io/tx/4uHnWse2B78yDJftbEc5d9akgumB4Jbz9nXdcq2m1iSNgXom66a35RwKp3n9nhqaPvybiLGdGmjSCP1MqVmP9nxT) |
| 10 | −0.121 (−0.121 / −0.121) [−0.121] | [grimacecoin](https://gmgn.ai/sol/token/Bh1fxMWPcMzFWeAYFaqKw2TjYSyWkyzmSq71XwPkpump) | 10-23 01:50:02 | [4EBgNfZ2](https://solscan.io/tx/4EBgNfZ2aoX7bYhWQghC8Dw3fx2rfatn8neA8cXAVf1iXN6VHmnmo1dKstuH6rmbZpt3sw1FQcy3GDqoRzcHt5wY) | [2NaH26Fd](https://solscan.io/tx/2NaH26FdnhiD61iXoiWPGbgSMT45T6acS1WYG5fn4dCj1cWydcXP7UfCRDkCaSJfiELmLFNBu6SjcNtFpwYiST7s) |

**Three winners checked by hand against the raw chunk lines** (`a10_handcheck.py` re-decodes the gz lines without using x1; MEASURED). For each, the price really rises after our modelled buy, and the curve state at ~8 s supports the modelled sell.

1. **JUSTICE FOR BAKED_SOL** (+1.239):
   - The dev buys 2.963 SOL with no bundle.
   - The engine's first `outs` entry is at 139 ms, so we are first at 75 ms.
   - At slot +13 (2.8 s), 4 wallets buy about 2.3–2.7 SOL each at back-to-back block positions. Ordinary buyers follow.
   - The dev sells 7.86 SOL at slot +28, then the price recovers.
   - Between slots +36 and +45 the price stays at 3.5–4.2× our entry. Our sell at slot +38 gets 3.69×.
   - The same 4 wallets dump at slot +46 (9.75 s), down to ~2.9×.
   - This is real, and robust to ±1 s of sell timing.
2. **Movember** (+0.823):
   - A 3-transaction glued bundle carries 7 buys; the engine's first `outs` entry is at 125 ms.
   - The price climbs steadily to 2.6–2.8× by slots +33 to +38, and stays 2.5–3.0× through slot +46.
   - This is real and robust.
3. **WarHound** (+0.689):
   - The price path is real: 1.31× at slot +1, about 2.4–2.5× at slots +33 to +38.
   - **But the fill is knife-edge.** A burst of 10 sniper buys was seen at 82.3 ms (DDR9eT 6 SOL; dKMjeG, 9Sh2fd and 4yFAz, whose buys failed on chain). Our 75 ms landing is only 7 ms before it.
   - At 83 ms this fill becomes a guard fail (price 1.6× the guard).

**Also checked:** NUB (+2.12 at 45 ms, a guard fail at 75 ms). It is +1.78 even with dKMjeG's 11.85 SOL buy (seen at 57 ms) removed.

## 4. Other flaws (task 4)

- **Picks left out (MEASURED):** 3 picks (07:59–08:06) are missing from the claim because its data copy ends at about 07:57. This is not a choice made on outcome, and adding them changes the totals by −0.03.
- **Token types (MEASURED):** no mayhem or non-SOL picks.
- **Graduation (MEASURED):** none during any hold.
- **Collector damage (MEASURED):**
  - 01:33–01:43 PKT has about 11% missing slots. 3 picks fall inside: Hc5sxDEh, 9LbTJ1vN and 3Pht7EQC.
  - Without them the corrected 75 ms slippage variant is +1.24.
  - The collector also crashed at 01:57 (truncated chunk), but the restart overlapped and lost no slots.
- **Follower slippage coverage (MEASURED):**
  - The limits that exist agree with the chain: 711 of 711 successful buys satisfy their own decoded limit.
  - But they cover only about 2 s of each 8 s hold, and only 110 of the 238 picks.
  - The doc's "every follower's real slippage limit is applied" is not true.
- **Concentration (MEASURED):** 106 different creators. The two biggest creators (22 picks each) net about zero. The profit comes from one-off creators.
- **Unchecked assumptions (INFERRED):**
  - the 1.5% fill penalty (at 3% the corrected 75 ms slippage variant is +0.98);
  - the 75 ms landing time (Run 2 measured it on n=2 buys);
  - the 0.0005 sell cost;
  - today's assumed costs (2% / 0.005), which Run 2 did not achieve.

## Files (`ops/overnight/verify2/`; run each with `python3 -I`)

Run order: `x1_extract.py` → a1, a2, a3 → a6 → v3 → a4, a5 → v4 → a7, a8 → v5 → v6, v7, v8 → a9a → `x1_extract.py work/a9_guard_vetoed.json x9` → a9 → a10.

| File | What it does |
|---|---|
| `x1_extract.py` | Raw chunks → `work/x1_txs.json.gz` (own decoder: trade and create events, token balances, curve SOL changes, slot coverage). With a mint list and tag it extracts other launches (`x9`). |
| `a1_picks.py` | Pick list vs scorer records; scoring delays; guard config check |
| `a2_integrity.py` | Create and curve checks, curve continuity, bundle as seen by the engine vs the chain, post-bundle price, chunk gaps |
| `a3_reconcile.py` | Transactions whose trade events don't explain the curve's token-balance change |
| `a6_engine_lines.py` | The engine's own decide/obs lines for the picks (`old_bundle_n` = absorbed buys) |
| `v2core.py` | My replay library: tape repair, `outs` matching, placement (with absorbed buys), guard, curve replay, variants |
| `v3_replay.py` | All picks × raw/repaired tape × placement modes × variants → `work/v3_res.json` |
| `a4_diff.py`, `a5_optpess.py` | Per-pick diff vs the claim; what sits between the optimistic and pessimistic placements |
| `v4_sens.py` | Corrected totals, hold times, costs, fill penalty, halves, by hour, top-10 tails (`work/v4_sens.json`) |
| `v5_slipimpute.py`, `a7_slipcov.py`, `a8_slack.py` | Slippage-limit coverage, how much price move followers tolerate, imputed limits |
| `v6_jitter.py`, `v7_boot.py`, `v8_final.py` | Landing-time sensitivity, bootstrap, final table incl. CW-style costs |
| `a9a_vetoed_list.py`, `a9_guards.py` | The launches vetoed after the guards were added (53 listed, 52 with data) and what they would have made |
| `a10_handcheck.py` | Hand check of one fill against the raw lines: `python3 -I a10_handcheck.py <mint prefix> [L]` |
