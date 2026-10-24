# Profitable pump.fun snipers at a place in line like ours

Read-only study, 2026-10-23. Windows: **R1** 10-21 22:07 → 10-22 13:00 UTC (launches) and **R2** 10-22 15:43 → 10-23 00:35 UTC, about 24 h together. No trades were sent and nothing on the server was changed.

## TL;DR

- **Being first is where the money is (MEASURED).** Across every sniper (4,718 wallets, about 40k snipes), buys with 0 outside buys ahead made +305 SOL (ROI +3.2%). With 1–3 ahead they made −110 SOL (−1.3%), with 4–10 ahead −208 SOL (−3.4%), and with 11 or more ahead −97 SOL (−6.1%). At our arrival time (50–100 ms in our feed, R2 from 17:10 UTC) the total is −3 SOL. Without its 10 best trades it is −37 SOL.
- **{{NPASS}} wallets pass the screen** (all MEASURED): 15 or more snipes, profit in both runs (or both halves of one run), profit without their best 2 tokens, and not the creator or the bundle. Of these, {{NLIKE}} land like us (create slot or next, 1+ outside buys ahead), {{NLATER}} land later than us, and {{NFIRST}} are first in line.
- **Most passes could be luck (MEASURED).** I resampled each wallet's own trades with its edge removed. About 28 of the 385 screened wallets would pass by chance anyway, so only about 12 of the {{NPASS}} are more than luck. The column P(mean≤0) ranks how confident each one is.
- **Copy tests on paper, at our place and our cost of 0.015 SOL per round trip:**
  - Following a wallet's buys after we see them loses for 29 of the 40. For dKMjeGJ4 it is −10.6% per trade.
  - Buying the same tokens at our usual place (behind 1 outside trade) and selling when they sell:
    - Positive in both runs for 6Kj5ChEZ (+9.1% / +9.1%, n=104 / 39). Also positive for mwamTohZ, AuTncroT, FZQwaUPe and 2uoELAUQ, but with n under 20 per run.
    - Only +0.7–1.4% in R1 for 3yrJE1A8, FeCAXCyH and 5g8bviwg; most of their gain was in R2. 3yrJE1A8 with a 3 s hold was +6% in both runs.
  - Their choice is **not a plain dev list**. They buy only some of a dev's launches, and buying every launch of those devs loses out of sample.
- **What looks copyable (INFERRED):**
  - **Fill only if first or near-first.** The wallet sets slippage or a guard so the buy fails instead of filling late. AHwJSnFN has 382 fills, 99.5% with no outside buy ahead, against 1,079 failed attempts. It still made +10.8 SOL, including on fills that arrived 100–250 ms after the create.
  - **Choose launches by dev reputation and timing.** Their picks are early in a dev's run, with a bigger glued bundle and more create-slot buyers. For 3 of the 4 leaders checked, picks also come after a longer pause since the dev's last launch (median 6–12 min, against 4–6 min for the launches they skip).
  - **Exit fast.** One sell 1–9 s after the buy.
- **AKbot wallets in these windows:** 9Sh2fd −1.33 SOL, DGmspi −0.75 SOL, D24ipY −8.59 SOL. AKbot's 1% fees are billed outside these txs and are not included, so the true numbers are lower. This fits: D24ipY loses, and the other two made their earlier profit on a few big days.

## How it was measured

**Data:** every pump.fun curve trade on every new launch (phase-A rows). Only SOL-quoted launches are used, meaning the first trade starts at 30 SOL / 1.073e15 virtual reserves and vsol never goes above 200 SOL. That leaves 14,776 launches in R1 and 12,972 in R2. Failed txs (err) are not replayed but their fee is counted.

**Snipe:** a wallet's first curve buy on a launch, landed at most 5 slots after the create (one slot is about 212 ms). The creator, the glued bundle (buy txs right after the create in the create slot) and the creator's own Jito bundle (from enrich jito_create) are excluded. The pump.fun mayhem agent BwWK17… is excluded.

**PnL per token** (MEASURED, two independent ways):
1. **From trade events.** Buys cost sol plus the protocol fee plus the creator fee. Sells return sol minus both fees. Add the tx fee and tips of the wallet's txs, plus the fees of its failed txs. Tokens still held at the end are valued by selling them into the last curve state.
2. **From exact SOL deltas** (the per-account lamport change of every collected tx of the wallet on that mint). This also catches in-tx bot/router fees, ATA rent and post-graduation AMM sells.

**Which source is used:**
- **SOL deltas** for wallets whose two sources agree within 5% of the buy plus 0.01 SOL. That is 394 of the 425 wallets.
- **Trade events plus the native-SOL extras** where the wallet trades through WSOL.
- **Trade events only** where a wallet's own address shows no SOL change (relayed).
- **Check against an independent full ledger:** DGmspi's R1 snipe tokens come to +0.971 SOL here and +0.971 SOL in ops/snipers/ledger.

**Place in line:**
- **Slot delta.**
- **Outside buys ahead:** distinct buy txs after the glued bundle that came before the wallet's first buy, not counting the creator or bundle.
- **Arrival ms:** when our shadow engine saw the wallet's tx, counted from the create. This is only for R2 launches from 17:10 UTC, and the engine's log covers the first ~1 s.
- **Reference points in our feed:** create-slot buys arrive at a median of 43 ms (p10–p90 18–113 ms). Next-slot buys arrive at a median of 161 ms. Ours land at about 60–75 ms.

**Screen:**
- 15 or more snipes, and not insider-like: 25% or more of its early buys in creator or bundle roles, or 50% or more on 3 devs or fewer.
- Profit above 0 in R1 and in R2. A wallet with fewer than 6 snipes in a run is judged on the two halves of its bigger run instead.
- Profit above 0 without its best 2 tokens.

**Luck test (`w5_null.py`):** removes each wallet's mean, resamples its trades within each run-half, and re-applies the screen. **Copy tests (`w6_follow.py`):** exact curve replay of a 0.494 SOL buy placed at our place in line, with pump fees on each side and a fixed 0.015 SOL cost. Trades where the curve completes before the exit are dropped.

## Ranked table (all {{NPASS}} passing wallets, ranked by PnL)

**Columns:**
- **class:** *first* means the median number of outside buys ahead is 0. *like-us* means create slot or next slot with 1 or more ahead. *later* means a median of 2 or more slots after the create.
- **R1·R2:** SOL / number of tokens in each run.
- **ex-top2:** PnL without the best 2 tokens.
- **P(mean≤0):** bootstrap. Smaller is more confident.
- **slot/ahead/ms:** medians.
- **behind:** PnL on the wallet's tokens where 1 or more outside buys were ahead.
- **hold·sells:** median seconds from first buy to last sell, and median number of sells.

| # | wallet | class | tokens | PnL SOL | R1 · R2 | ex-top2 | ROI | P(mean≤0) | slot/ahead/ms | behind | size | hold·sells | fee+tip |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
{{TABLE}}

## Like us ({{NLIKE}}): create slot or next, behind 1+ outside buys

These are the ones to study first. For most of them, the tokens where 1 or more outside buys were ahead are still profitable (see the "behind" column):
- FeCAXCyH: +7.7 SOL on 24 tokens with 1–3 ahead.
- 3yrJE1A8: +4.3 SOL on 91.
- mwamTohZ: +2.7 SOL on 16.
- CWNAJ1ZT: +1.8 SOL on 26.
- 5g8bviwg: profit at every place in line.

The exception is CWiNFAEk. It made +7.0 SOL when first and −1.1 SOL when behind 1–3, so it depends on being first. HVE8996r, H6obhoSN and 8fN6NyEP are about break-even: hundreds of 0.08–0.35 SOL snipes for under +0.6 SOL in total.

{{LIKE}}

## Later than us ({{NLATER}}): 2+ slots after the create

They profit without being first, but they mostly choose AFTER seeing about 0.5–1 s of price action:
- Their entry is at ×1.3–1.6 of the post-bundle price for 2maW7x2X, retAumPG, 4Yy3xBZn, 5XU7ApZv and 5FEM1HQj.
- HnFPB3iA and G3gKCu8X buy right after mega-bundles (55–70 SOL glued) and sell after graduation on the AMM.

Their "same tokens at our place" numbers (+25..+60% per trade) use information we would not have at 74 ms. They are an upper bound, not a copy result. Reactive following of them is about 0 to +10% per trade on small samples.

{{LATER}}

## First in line ({{NFIRST}})

They profit by being first, which does not fit our landing. Two exceptions are worth noting:
- **dKMjeGJ4** also made +13.2 SOL on 169 tokens with 1–3 ahead. That is with its size (1.8–4.2 SOL) and its fee of about 1.1%. Our replay of its tokens at our place still loses.
- **AHwJSnFN** fills almost only when it is first. When it is not, the attempt fails (custom program error 100; INFERRED as an on-chain "abort unless first" guard).

{{FIRST}}

## Focus wallets (AKbot users)

{{FOCUS}}

- **Sanity check (MEASURED):** for DGmspi's R1 snipe tokens my number is +0.971 SOL, the same as the independent ledger in ops/snipers/ledger. For all its trading in R1 (not only snipes), the ledger shows trading +5.78, bot fees −0.70 and failed fees −0.20.
- **Missing fees (MEASURED that they are missing; size INFERRED):** AKbot's 1% buy and 1% sell fees are billed in separate txs that are not in this data, so subtract about 2% of volume. That is about 2.2 SOL for 9Sh2fd, 2.1 for DGmspi and 4.6 for D24ipY.
- **Ledger history** (10-17 → 10-22, earlier study): 9Sh2fd made +14–15 SOL and DGmspi +17–20 SOL, mostly from a few fat-tail days. D24ipY lost about 19 SOL. **In these two windows:**
  - 9Sh2fd and DGmspi are flat to negative on snipes.
  - D24ipY loses (−8.6 SOL on 159 snipes, ROI −3.7%), the same direction as its ledger.
  - The two windows only partly overlap the ledger; R2 runs past its 20:15 UTC end.

## Copy tests in detail (paper, our place, 0.5 SOL, 0.015 SOL cost per round trip)

1. **Reactive follow** (buy right after the leader's buy plus 1 trade, sell right after its first sell plus 1 trade): negative for 29 of the 40 wallets.
   - dKMjeGJ4: −10.6% per trade (−26 SOL on 492).
   - AHwJSnFN: −6.1%. CWiNFAEk: −9.2%.
   - Positive but small: 6Kj5ChEZ +2.5% (n=143), FeCAXCyH +2.2% (54), mwamTohZ +2.7% (21), 4Yy3xBZn +1.4% (82).
   - Positive on fewer than 40 trades: retAumPG +10%, 9iCGPgiZ +13%, 5FEM1HQj +10%, FZQwaUPe, G2fPBRFR, EQcoyTSP and 7nkYRv8x.
2. **Same tokens, pre-emptively at our place** (behind 1 outside trade, sell after the leader's first sell):
   - **Positive in both runs:** 6Kj5ChEZ +9.1% / +9.1% (n=104 / 39), mwamTohZ +17% / +17% (14 / 7), AuTncroT +12% / +11% (7 / 8), 2uoELAUQ +7.7% / +3.4% (19 / 10), FZQwaUPe +11% / +14% (7 / 11).
   - Wallets that land 3–5 slots late (2maW7x2X, retAumPG, 4Yy3xBZn, 5XU7ApZv, 5FEM1HQj, 4mjnzWwd, 9iCGPgiZ) also look strongly positive here. That is look-ahead: they choose after the first second of price action.
   - **Positive in both runs with a 3 s hold behind 2 trades:** 3yrJE1A8 +5.9% / +6.4% (119 / 39), CWNAJ1ZT +2.4% / +6.4%.
   - **Mostly R2 only:** FeCAXCyH +1.4% / +26% (23 / 31), 5g8bviwg +0.7% / +17% (52 / 51).
   - **Negative:** dKMjeGJ4, AHwJSnFN, CWiNFAEk, 54YNHFVt, HVE8996r, H6obhoSN, HkQ7hMjy and DiqYk5RD. Their edge is being first, or their own size, fee or exit.
3. **Is it just a dev list? No (MEASURED).**
   - **They buy only some of a dev's launches.** 6Kj5ChEZ bought 25 of the 118 R1 launches of its main dev bwamJz… and 16 of its 189 R2 launches.
   - **Buying all of those devs' launches loses at our place.** Taking every launch, in the other run, by the devs a leader bought, behind 1 trade with a 3 s hold, gives −0.6% to −5.6% per trade. This holds for 6Kj5ChEZ, 3yrJE1A8, FeCAXCyH, 5g8bviwg, the union of the like-us leaders, dKMjeGJ4, AHwJSnFN and CWiNFAEk.
   - **A generic list barely helps.** Devs that were positive in one run give only +2–3% per trade in the other run, behind 1 trade. The median trade is −5.5%, so it is tail-driven. Behind 2–3 trades it is about 0.
4. **What separates their picks from the same devs' other launches (MEASURED, descriptive):**
   - A longer pause since the dev's previous launch: median 358 / 741 / 512 / 228 s against 263 / 360 / 215 / 234 s for 6Kj5ChEZ / 3yrJE1A8 / FeCAXCyH / 5g8bviwg.
   - Earlier in the dev's run: launch number 3–10 against 14–26.
   - More create-slot outside buyers: 2–2.5 against 1.
   - A bigger glued bundle: 4.2–5.0 against 3.0–3.5 SOL.
   - More creates inside a Jito bundle: 22–24% against 10%.

## Files

**Deliverables:**
- **This report.**
- **wallets.json:** per-wallet stats for the passing wallets and the 3 focus wallets. Covers PnL by run, half, place and ms, landing, size, exits, selection, top devs, null-test numbers, copy tests, and example token and tx links.

**Scripts** (all `python3 -I`, read-only, in this folder):

| Script | What it does |
|---|---|
| w1_pairs.py | Pass 1: per (wallet, token) PnL pieces and landing |
| w3_sd.py | Exact SOL deltas from the raw txs |
| w2_wallets.py | Per-wallet stats and the screen |
| w5_null.py | Luck test |
| w6_follow.py | Copy replays |
| w4_devlist.py | Dev-list out-of-sample test |
| w7_leaderdevs.py | Leaders' dev lists, out of sample |
| w8_picks.py | Picks against the same devs' other launches |
| w10_global.py | Every sniper by place and ms |
| w9_report.py | Builds this file |

**Intermediate data:** /home/moiz/sniper-data/work/wallets/. R1/ and R2/ hold pass 1, sd_R*.jsonl.gz the SOL deltas, and out5/ holds wallets_all.json (all 414 wallets with 15+ snipes), null.json and follow.json. The text outputs are global.txt, devlist.txt, leaderdevs.txt and picks.txt.

**To rerun:**
- Pass 1 for each run: `w1_pairs.py <phaseA> <run dir> <work>/R1`.
- `w2_wallets.py <work> <work>/out0`.
- `w3_sd.py <work>/out0/cands.json` for each run.
- `w2_wallets.py <work> <work>/out5 sd_R1.jsonl.gz,sd_R2.jsonl.gz`.
- Then `w5_null.py`, `w6_follow.py` and `w9_report.py`.

**Caveats:**
- **Windows:** about 24 h in total, and R2 ends at 00:35.
- **Graduated tokens:** these are valued at the last curve price only when no AMM sale is seen. That is flagged as `unres`, and only 2maW7x2X's top token is affected (+11.3 SOL unrealised).
- **ATA rent:** rent of token accounts that are not closed counts as a cost in the SOL-delta numbers, about 0.002 SOL per token.
- **Hidden fees:** bot fees billed outside the trade txs (AKbot) are not visible.
