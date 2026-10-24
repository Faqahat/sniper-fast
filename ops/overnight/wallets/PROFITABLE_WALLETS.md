# Profitable pump.fun snipers at a place in line like ours

Read-only study, 2026-10-23. Windows: **R1** 10-21 22:07 → 10-22 13:00 UTC (launches) and **R2** 10-22 15:43 → 10-23 00:35 UTC, about 24 h together. No trades were sent and nothing on the server was changed.

## TL;DR

- **Being first is where the money is (MEASURED).** Across every sniper (4,718 wallets, about 40k snipes), buys with 0 outside buys ahead made +305 SOL (ROI +3.2%). With 1–3 ahead they made −110 SOL (−1.3%), with 4–10 ahead −208 SOL (−3.4%), and with 11 or more ahead −97 SOL (−6.1%). At our arrival time (50–100 ms in our feed, R2 from 17:10 UTC) the total is −3 SOL. Without its 10 best trades it is −37 SOL.
- **40 wallets pass the screen** (all MEASURED): 15 or more snipes, profit in both runs (or both halves of one run), profit without their best 2 tokens, and not the creator or the bundle. Of these, 16 land like us (create slot or next, 1+ outside buys ahead), 16 land later than us, and 8 are first in line.
- **Most passes could be luck (MEASURED).** I resampled each wallet's own trades with its edge removed. About 28 of the 385 screened wallets would pass by chance anyway, so only about 12 of the 40 are more than luck. The column P(mean≤0) ranks how confident each one is.
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

## Ranked table (all 40 passing wallets, ranked by PnL)

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
| 1 | [dKMjeG…2CTK](https://gmgn.ai/sol/address/dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK) | first | 492 | +45.39 | +7.19/245 · +38.20/247 | +28.69 | +2.9% | 0.033 | 0 / 0 / 44 | +13.24 | 1.78 | 4s·2 | 1.09% |
| 2 | [2maW7x…3Zfb](https://gmgn.ai/sol/address/2maW7x2X4shMK3bNc3bGNvRpweindJXzujgdszgp3Zfb) | later | 83 | +17.82 | +0.67/38 · +17.14/45 | +3.98 | +10.5% | 0.017 | 4 / 8 / 810 | +17.82 | 1.98 | 1s·1 | 0.10% |
| 3 | [FeCAXC…djSD](https://gmgn.ai/sol/address/FeCAXCyHwrg3QPkyVrJY2VA1qRQGzjHKhEiteRkqdjSD) | like-us | 54 | +12.84 | +1.99/23 · +10.85/31 | +5.87 | +11.8% | 0.007 | 0 / 1 / 40 | +8.63 | 1.93 | 2.5s·1 | 1.56% |
| 4 | [A21wCG…HNVn](https://gmgn.ai/sol/address/A21wCG8HK3fQSFrb7YS8xwtn5Rn1ujDeMfpKF9TPHNVn) | later | 287 | +11.24 | +6.17/160 · +5.07/127 | +6.51 | +4.9% | 0.017 | 2 / 1 / 350 | +7.87 | 0.77 | 87s·1 | 0.05% |
| 5 | [AHwJSn…paN2](https://gmgn.ai/sol/address/AHwJSnFNUiAU9FfT5ewW2osqMo938WtL7KhfsJyfpaN2) | first | 382 | +10.78 | +6.25/197 · +4.52/185 | +5.55 | +3.8% | 0.013 | 0 / 0 / 44 | +0.09 | 0.59 | 2s·1 | 0.38% |
| 6 | [retAum…Bard](https://gmgn.ai/sol/address/retAumPGyn3U2jjpgRtMLkJR6YnYugSWQiMo9sdBard) | later | 28 | +9.00 | +3.70/13 · +5.29/15 | +2.85 | +32.1% | 0.033 | 3 / 13 / – | +9.00 | 0.99 | 120s·1 | 0.11% |
| 7 | [2uoELA…qmdE](https://gmgn.ai/sol/address/2uoELAUQCQ4Amkdui8piryp2nAf9woYJtJc5Hr64qmdE) | first | 29 | +8.51 | +5.59/19 · +2.93/10 | +2.60 | +15.6% | 0.023 | 0 / 0 / 81 | +4.22 | 1.86 | 274s·1 | 0.15% |
| 8 | [EP51o5…KPYE](https://gmgn.ai/sol/address/EP51o5QPpbAJbTqbHiK5PFjLwpgemmcn4kZPHQJXKPYE) | first | 19 | +8.51 | +6.19/15 · +2.32/4 | +2.22 | +11.0% | 0.02 | 0 / 0 / 124 | +0.00 | 3.46 | 58s·3 | 3.82% |
| 9 | [haqqiU…QgWq](https://gmgn.ai/sol/address/haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq) | later | 538 | +8.00 | +5.63/313 · +2.37/225 | +5.63 | +2.2% | 0.017 | 4 / 5 / 690 | +7.65 | 0.25 | 13s·2 | 0.12% |
| 10 | [6Kj5Ch…RVRp](https://gmgn.ai/sol/address/6Kj5ChEZnyNjgATjjSvp8AveJRa9Nerjir2c4Nh2RVRp) | later | 144 | +7.29 | +3.65/104 · +3.64/40 | +3.46 | +10.1% | 0.003 | 2 / 4 / 577 | +8.05 | 0.49 | 9s·1 | 0.41% |
| 11 | [3yrJE1…2fjJ](https://gmgn.ai/sol/address/3yrJE1A8dgSuy5NLimG5GSYxA6wMkvnAYLD9Y4xR2fjJ) | like-us | 158 | +7.07 | +6.95/119 · +0.12/39 | +4.60 | +3.9% | 0.037 | 0 / 1 / 50 | +3.55 | 0.49 | 4s·1 | 0.24% |
| 12 | [A9X9Ag…zkdV](https://gmgn.ai/sol/address/A9X9AgTwXACgp9UbdjhUPyq15rFPdDBzkD3NHu6YzkdV) | first | 37 | +6.28 | +3.62/27 · +2.67/10 | +0.99 | +5.1% | 0.15 | 0 / 0 / 31 | -0.74 | 2.96 | 1s·1 | 1.01% |
| 13 | [HnFPB3…HXNH](https://gmgn.ai/sol/address/HnFPB3iAAb1dtsBfzcomHibua1Cw8Qx5b5wt5ttrHXNH) | later | 26 | +5.81 | +2.38/18 · +3.43/8 | +2.51 | +59.1% | 0.02 | 2 / 4 / – | +6.21 | 0.24 | 89s·0 | 0.23% |
| 14 | [5g8bvi…pUX3](https://gmgn.ai/sol/address/5g8bviwgHv6gKzCerSjQbFoYxfHnWawNLLn99HDjpUX3) | like-us | 103 | +5.66 | +0.84/52 · +4.82/51 | +2.33 | +7.4% | 0.01 | 1 / 1 / 108 | +5.18 | 0.55 | 2s·1 | 0.10% |
| 15 | [CWiNFA…3S2J](https://gmgn.ai/sol/address/CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J) | like-us | 466 | +5.42 | +4.04/273 · +1.37/193 | +3.51 | +1.2% | 0.023 | 0 / 1 / 49 | -1.47 | 0.99 | 1s·1 | 0.61% |
| 16 | [FYHggF…CyUh](https://gmgn.ai/sol/address/FYHggFuZLTrd6PAZa9SKmDoiRELGzggP3etrQaPwCyUh) | like-us | 17 | +5.39 | +2.95/4 · +2.44/13 | +0.15 | +63.5% | 0.043 | 1 / 3 / 209 | +5.39 | 0.49 | 52s·2 | 0.41% |
| 17 | [6fg6aU…M3Pt](https://gmgn.ai/sol/address/6fg6aUUQ3ZcYnLa2BcddTk6JdERCs2ZpRdNKLrMEM3Pt) | first | 37 | +4.80 | +0.36/18 · +4.44/19 | +1.90 | +5.8% | 0.023 | 0 / 0 / 27 | -0.02 | 2.17 | 7s·3 | 2.77% |
| 18 | [8jsPAC…D2Eg](https://gmgn.ai/sol/address/8jsPACiiC3x7d8gWN9yUUcvjqhJDpnEcV5BP8wPdD2Eg) | like-us | 50 | +3.56 | +0.24/27 · +3.32/23 | +1.87 | +6.6% | 0.017 | 0 / 1 / 77 | +2.15 | 0.92 | 1s·1 | 0.12% |
| 19 | [mwamTo…u6HG](https://gmgn.ai/sol/address/mwamTohZTS8VVDXhJBwEFzmWbbaax5sSYY8e8Vxu6HG) | like-us | 21 | +3.56 | +2.78/14 · +0.77/7 | +2.37 | +15.4% | 0.003 | 1 / 2 / 64 | +3.68 | 1.09 | 5s·1 | 0.10% |
| 20 | [4Yy3xB…5AeY](https://gmgn.ai/sol/address/4Yy3xBZnJfhkmFAcV6hgdjWgkkc9oCoWEtcUiXNq5AeY) | later | 82 | +3.42 | +2.13/35 · +1.29/47 | +0.10 | +8.8% | 0.13 | 2 / 7 / 284 | +3.42 | 0.45 | 7s·1 | 0.24% |
| 21 | [54YNHF…Vd43](https://gmgn.ai/sol/address/54YNHFVt3VwxMpmfiqMmYCFTJkSyCNDX7sx9RcRGVd43) | first | 66 | +3.13 | +0.93/29 · +2.19/37 | +0.08 | +2.9% | 0.123 | 0 / 0 / 52 | +1.44 | 1.58 | 1s·1 | 0.92% |
| 22 | [5XU7Ap…bX3j](https://gmgn.ai/sol/address/5XU7ApZvC9deBCNLPKyR2FgQZPXH8LLBkYXhCnJNbX3j) | later | 25 | +3.02 | +0.62/13 · +2.40/12 | +1.59 | +9.7% | 0.003 | 4 / 6 / 251 | +3.03 | 0.99 | 1s·1 | 0.19% |
| 23 | [CWNAJ1…aVjp](https://gmgn.ai/sol/address/CWNAJ1ZTPxWpKH3CTGpZPAtFpTzsVuuXabCw16RbaVjp) | like-us | 46 | +3.01 | +1.97/28 · +1.05/18 | +1.58 | +6.6% | 0.023 | 0 / 1 / 82 | +2.02 | 0.99 | 3s·2 | 3.83% |
| 24 | [CBKgS8…Wo2s](https://gmgn.ai/sol/address/CBKgS8Nj714YomoPPxhVLUWos7vSrWnuL2cVKnJqWo2s) | like-us | 38 | +2.86 | +0.61/27 · +2.25/11 | +0.36 | +9.2% | 0.07 | 1 / 1.5 / 165 | +3.18 | 0.50 | 1s·1 | 0.22% |
| 25 | [AuTncr…ZnU6](https://gmgn.ai/sol/address/AuTncroT18PVNMzLBGpveiiyFs3faYJdVfewuCYEZnU6) | like-us | 15 | +2.81 | +2.53/7 · +0.28/8 | +0.50 | +8.3% | 0.013 | 0 / 1 / 48 | +2.14 | 1.33 | 1s·1 | 0.11% |
| 26 | [HkQ7hM…NExQ](https://gmgn.ai/sol/address/HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ) | later | 83 | +2.17 | +0.89/50 · +1.28/33 | +1.40 | +4.2% | 0.01 | 4 / 5 / 563 | +2.04 | 0.50 | 5.5s·1 | 0.23% |
| 27 | [4mjnzW…Ls8y](https://gmgn.ai/sol/address/4mjnzWwdtFRVT9hJu8NiJvwK25mXbR4XZcKQ3Qm1Ls8y) | later | 53 | +1.61 | +0.37/17 · +1.23/36 | +0.74 | +6.1% | 0.03 | 2 / 3 / 457 | +1.61 | 0.49 | 4s·1 | 0.02% |
| 28 | [9iCGPg…iPXm](https://gmgn.ai/sol/address/9iCGPgiZrzQayYSzM5W4Uc99zgdf86QZXu91uZ4DiPXm) | later | 19 | +1.34 | +0.01/10 · +1.32/9 | +0.43 | +19.1% | 0.027 | 4 / 11 / – | +1.34 | 0.25 | 31s·1 | 0.24% |
| 29 | [E8s9ti…8MBp](https://gmgn.ai/sol/address/E8s9tiRtxzRKVrwbVEfjYn4c9fdhfhvG5aUnEah88MBp) | like-us | 120 | +0.91 | +0.04/64 · +0.87/56 | +0.54 | +3.9% | 0.043 | 0 / 1 / 91 | +0.47 | 0.20 | 30s·1 | 0.04% |
| 30 | [FZQwaU…kTnp](https://gmgn.ai/sol/address/FZQwaUPe9bvNDVH6byfF15t4RPnbcx66JvNk9dUrkTnp) | like-us | 18 | +0.69 | +0.12/7 · +0.57/11 | +0.16 | +20.3% | 0.0 | 0 / 0.5 / 107 | +0.44 | 0.10 | 58s·1 | 2.54% |
| 31 | [HVE899…PGDJ](https://gmgn.ai/sol/address/HVE8996rtqG8N2sCNaTJZdLBbKW2SrSg2uXjJtNqPGDJ) | like-us | 626 | +0.58 | +0.39/359 · +0.18/267 | +0.34 | +0.9% | 0.137 | 0.5 / 1 / 71 | +0.03 | 0.09 | 88s·1 | 0.13% |
| 32 | [8fN6Ny…EPXs](https://gmgn.ai/sol/address/8fN6NyEPbFziSybqSoFK8y3iSZhkHsKsoFiKB9rREPXs) | like-us | 211 | +0.57 | +0.08/49 · +0.49/162 | +0.02 | +0.8% | 0.237 | 1 / 1 / 199 | +0.10 | 0.35 | 31s·1 | 0.35% |
| 33 | [G2fPBR…dxfP](https://gmgn.ai/sol/address/G2fPBRFRwqrSeJnTmrgBEeEtZpHbaXvnrHdppaWrdxfP) | later | 34 | +0.49 | +0.49/34 · +0.00/0 | +0.24 | +11.1% | 0.05 | 2 / 5 / – | +0.45 | 0.15 | 8s·1 | 0.18% |
| 34 | [Six5j1…qdwf](https://gmgn.ai/sol/address/Six5j1cvdsZgh7vSgvYXD3FG69MPh7dae2qkjwTqdwf) | like-us | 26 | +0.43 | +0.28/8 · +0.15/18 | +0.11 | +1.5% | 0.117 | 0 / 0.5 / 30 | -0.04 | 1.26 | 0s·1 | 2.57% |
| 35 | [DiqYk5…c3j4](https://gmgn.ai/sol/address/DiqYk5RDxWgqDjnhcsefUyc3DY12T9vbhvjWQMLhc3j4) | later | 106 | +0.43 | +0.12/71 · +0.32/35 | +0.10 | +1.6% | 0.217 | 3 / 6 / 400 | +0.41 | 0.25 | 2s·1 | 0.17% |
| 36 | [G3gKCu…34uQ](https://gmgn.ai/sol/address/G3gKCu8XkjXK3zT1CEzFCsBjbuVwXa9pkjmTH5TK34uQ) | later | 26 | +0.41 | +0.02/13 · +0.39/13 | +0.14 | +39.0% | 0.053 | 3 / 5 / 429 | +0.41 | 0.03 | 81s·0.5 | 0.61% |
| 37 | [5FEM1H…ku2W](https://gmgn.ai/sol/address/5FEM1HQjVivAhvqULk1pmwa9UVwwD23JuK3nsbT5ku2W) | later | 39 | +0.34 | +0.30/21 · +0.04/18 | +0.11 | +9.7% | 0.09 | 5 / 16 / – | +0.34 | 0.09 | 5s·1 | 0.60% |
| 38 | [H6obho…1HtG](https://gmgn.ai/sol/address/H6obhoSNUbQhLNUoYFCBiKS4CMRC1qQYoBsms7y81HtG) | like-us | 583 | +0.24 | +0.01/342 · +0.23/241 | +0.02 | +0.5% | 0.3 | 1 / 2 / 71 | +0.01 | 0.08 | 90s·1 | 0.14% |
| 39 | [EQcoyT…XJMy](https://gmgn.ai/sol/address/EQcoyTSPfbPj9nCuNByUQPTF16eC85S2KhmLpY7hXJMy) | first | 15 | +0.13 | -0.03/3 · +0.16/12 | +0.03 | +8.4% | 0.02 | 0 / 0 / 39 | +0.06 | 0.10 | 61s·1 | 1.54% |
| 40 | [7nkYRv…nZTi](https://gmgn.ai/sol/address/7nkYRv8xScp9gjVKNNWN5XDbYsn79iWigiZYgCS8nZTi) | later | 24 | +0.08 | +0.05/13 · +0.03/11 | +0.02 | +12.6% | 0.067 | 2 / 6 / 316 | +0.08 | 0.03 | 3s·1 | 0.30% |

## Like us (16): create slot or next, behind 1+ outside buys

These are the ones to study first. For most of them, the tokens where 1 or more outside buys were ahead are still profitable (see the "behind" column):
- FeCAXCyH: +7.7 SOL on 24 tokens with 1–3 ahead.
- 3yrJE1A8: +4.3 SOL on 91.
- mwamTohZ: +2.7 SOL on 16.
- CWNAJ1ZT: +1.8 SOL on 26.
- 5g8bviwg: profit at every place in line.

The exception is CWiNFAEk. It made +7.0 SOL when first and −1.1 SOL when behind 1–3, so it depends on being first. HVE8996r, H6obhoSN and 8fN6NyEP are about break-even: hundreds of 0.08–0.35 SOL snipes for under +0.6 SOL in total.

**[FeCAXC…djSD](https://gmgn.ai/sol/address/FeCAXCyHwrg3QPkyVrJY2VA1qRQGzjHKhEiteRkqdjSD)** — like-us, 54 snipes, **+12.84 SOL** (R1 +1.99 / R2 +10.85), without best 2 +5.87, ROI +11.8%, win 50%, median token -0.006 SOL, bootstrap P(mean≤0) 0.007, in CANDIDATES.md #17
- Landing (MEASURED): median slot +0 (66% in the create slot), outside buys ahead median 1 (p25–p75 0–2), arrival in our feed median 40 ms (n=16), entry price ×1.11 of the post-bundle price, fee+tip 1.56% of the buy, tips [['astralane', 176], ['nozomi', 138], ['none', 53]]
- PnL by place: 0 ahead: 23 tok +4.21 · 1-3 ahead: 24 tok +7.69 · 4-10 ahead: 6 tok +0.47 · 11+ ahead: 1 tok +0.48
- PnL by arrival ms (R2 17:10+): <25ms: 3 tok +0.51 · 25-50: 7 tok +3.28 · 50-100: 3 tok -1.03 · 100-250: 2 tok +0.31 · >=250: 1 tok +0.73
- Size 1.93 SOL (tiers 1.93, 0.99, 1.98); hold median 2.5 s (p25–p75 1–6), sells median 1.0, sold everything 100%; failed attempts on unfilled launches 0
- Picks (MEASURED): serial devs (96% of picks; dev's launches in run med 37); dev buy med 4.93 SOL; bundled 77% (glued med 4.98 SOL); X link 100% / site 83%; top dev share 20% of 23 devs; busiest UTC hours 22,16,23
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: +15.6%/trade, +4.21 SOL (R1 +1.4%, R2 +26.2%); behind 2: +9.4%; behind 2 + hold 3 s: +15.2%; reactive follow (buy after its buy +1 trade, sell after its sell): +2.2%/trade
- Example: [PUMPVENGERS](https://gmgn.ai/sol/token/64kh5pnoerper6yuZDr1RiJnjcuuJYUh11R94pekpump) +4.10 ([buy tx](https://solscan.io/tx/4M3pHHFLzZCgDv8CVaBp4bECqiEJoForxVJ4D4Ck9Fd279AJJKgFfcsTCuW7JT4QvaaLeSwPyku1h6ZZBmjKTgN)); [FitGirl](https://gmgn.ai/sol/token/6qU8XcAwsosAd8Q43m65NqhDjhhE5TZ3E5hrhsNbpump) +2.87 ([buy tx](https://solscan.io/tx/5hD5hJSo9wHZRxALdnLmDTxxG59aHu9pCNeeerGZnFDj99Y6QVo27FPjZU9TsKzxWAorZzAUjgGFBUMYBKRdxf6z))

**[3yrJE1…2fjJ](https://gmgn.ai/sol/address/3yrJE1A8dgSuy5NLimG5GSYxA6wMkvnAYLD9Y4xR2fjJ)** — like-us, 158 snipes, **+7.07 SOL** (R1 +6.95 / R2 +0.12), without best 2 +4.60, ROI +3.9%, win 51%, median token +0.000 SOL, bootstrap P(mean≤0) 0.037, in CANDIDATES.md #54
- Landing (MEASURED): median slot +0 (69% in the create slot), outside buys ahead median 1 (p25–p75 0–2), arrival in our feed median 50 ms (n=21), entry price ×1.05 of the post-bundle price, fee+tip 0.24% of the buy, tips [['astralane', 198], ['bolt', 100], ['helius', 62]]
- PnL by place: 0 ahead: 60 tok +3.53 · 1-3 ahead: 91 tok +4.30 · 4-10 ahead: 7 tok -0.76
- PnL by arrival ms (R2 17:10+): <25ms: 3 tok +0.92 · 25-50: 8 tok -1.12 · 50-100: 5 tok +1.75 · 100-250: 5 tok +0.63
- Size 0.49 SOL (tiers 0.49, 1.98, 3.95); hold median 4.0 s (p25–p75 4–4), sells median 1.0, sold everything 100%; failed attempts on unfilled launches 0
- Picks (MEASURED): serial devs (97% of picks; dev's launches in run med 20); dev buy med 3.50 SOL; bundled 91% (glued med 4.20 SOL); X link 100% / site 68%; top dev share 12% of 41 devs; busiest UTC hours 23,11,4
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: +1.8%/trade, +1.44 SOL (R1 +0.8%, R2 +4.9%); behind 2: -2.8%; behind 2 + hold 3 s: +6.0%; reactive follow (buy after its buy +1 trade, sell after its sell): -6.0%/trade
- Example: [Cyberinu](https://gmgn.ai/sol/token/Cbe8iKoofePaBLiuvxk51csJ1XC62p6hsp8ywZJtpump) +1.35 ([buy tx](https://solscan.io/tx/3R4Nzp7smATesWny7wDzjUgm3Cbxf4dqAfrk7wNUL4yfiMybszFqMAJZjwQt9xTRmLXGtUBqKrRGtaxDyCdzk3hm)); [ANTI-DOOMER](https://gmgn.ai/sol/token/MipsGqAwKMMCsxKViVGyjMvDNtVQsxCVWzCTL2rnhDa) +1.12 ([buy tx](https://solscan.io/tx/3ojLL7FMmBuMDgM7hot1EKED6wYRETnizRg8Aqi1QRgmUEd7i9hmsRx1t6rmZjg4ngRN1qKYEoyPiegKBgq7AwT4))

**[5g8bvi…pUX3](https://gmgn.ai/sol/address/5g8bviwgHv6gKzCerSjQbFoYxfHnWawNLLn99HDjpUX3)** — like-us, 103 snipes, **+5.66 SOL** (R1 +0.84 / R2 +4.82), without best 2 +2.33, ROI +7.4%, win 39%, median token -0.015 SOL, bootstrap P(mean≤0) 0.01
- Landing (MEASURED): median slot +1 (40% in the create slot), outside buys ahead median 1 (p25–p75 1–4), arrival in our feed median 108 ms (n=31), entry price ×1.05 of the post-bundle price, fee+tip 0.10% of the buy, tips [['helius', 344], ['none', 244], ['0slot', 88]]
- PnL by place: 0 ahead: 20 tok +0.48 · 1-3 ahead: 55 tok +1.14 · 4-10 ahead: 21 tok +1.49 · 11+ ahead: 7 tok +2.54
- PnL by arrival ms (R2 17:10+): <25ms: 1 tok +0.58 · 25-50: 9 tok +0.55 · 50-100: 2 tok +0.29 · 100-250: 17 tok +0.61 · >=250: 2 tok -0.19
- Size 0.55 SOL (tiers 0.48, 0.69, 0.68); hold median 2 s (p25–p75 2–4), sells median 1, sold everything 100%; failed attempts on unfilled launches 25
- Picks (MEASURED): serial devs (84% of picks; dev's launches in run med 15); dev buy med 5.00 SOL; bundled 70% (glued med 4.49 SOL); X link 93% / site 75%; top dev share 12% of 60 devs; busiest UTC hours 22,23,16
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: +8.8%/trade, +4.56 SOL (R1 +0.7%, R2 +17.2%); behind 2: +2.1%; behind 2 + hold 3 s: +4.5%; reactive follow (buy after its buy +1 trade, sell after its sell): -3.6%/trade
- Example: [PUMPVENGERS](https://gmgn.ai/sol/token/64kh5pnoerper6yuZDr1RiJnjcuuJYUh11R94pekpump) +1.84 ([buy tx](https://solscan.io/tx/4LsVdwqvDXmDPt7yAK5QGpACr6MHa8xAQPhQiwGntWzqM779fvH5tgWGyAbNxt4768zhj6FieGdFxfLGYo9WK9i3)); [cybercurrency](https://gmgn.ai/sol/token/CzDuFrKNEkhN2LJkxijJ5SHFwSaRT4FqPMmDnYPdpump) +1.49 ([buy tx](https://solscan.io/tx/4LKTAaCtvEg99ZA8m7mMjDEM7ZW9AyoiaErnK4H6f9SBR9tD7dP9xxw5ofpRzvDyxTFuuC82TgAF1SdFMpCAAxfW))

**[CWiNFA…3S2J](https://gmgn.ai/sol/address/CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J)** — like-us, 466 snipes, **+5.42 SOL** (R1 +4.04 / R2 +1.37), without best 2 +3.51, ROI +1.2%, win 36%, median token -0.020 SOL, bootstrap P(mean≤0) 0.023, in CANDIDATES.md #44
- Landing (MEASURED): median slot +0 (68% in the create slot), outside buys ahead median 1 (p25–p75 0–1), arrival in our feed median 49 ms (n=163), entry price ×1.01 of the post-bundle price, fee+tip 0.61% of the buy, tips [['astralane', 280], ['helius', 212], ['none', 155]]
- PnL by place: 0 ahead: 226 tok +6.95 · 1-3 ahead: 227 tok -1.14 · 4-10 ahead: 13 tok -0.32
- PnL by arrival ms (R2 17:10+): <25ms: 28 tok -0.31 · 25-50: 54 tok +0.55 · 50-100: 33 tok -0.24 · 100-250: 45 tok +1.33 · >=250: 3 tok -0.18
- Size 0.99 SOL (tiers 0.99); hold median 1.0 s (p25–p75 1–3), sells median 1.0, sold everything 100%; failed attempts on unfilled launches 22
- Picks (MEASURED): serial devs (90% of picks; dev's launches in run med 16); dev buy med 3.00 SOL; bundled 70% (glued med 3.04 SOL); X link 92% / site 61%; top dev share 6% of 104 devs; busiest UTC hours 22,18,23
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: -4.2%/trade, -9.89 SOL (R1 -4.2%, R2 -4.3%); behind 2: -7.4%; behind 2 + hold 3 s: -6.8%; reactive follow (buy after its buy +1 trade, sell after its sell): -9.2%/trade
- Example: [Cyberinu](https://gmgn.ai/sol/token/Cbe8iKoofePaBLiuvxk51csJ1XC62p6hsp8ywZJtpump) +0.97 ([buy tx](https://solscan.io/tx/36nBhjduLkBuEBwmvJiJoCao97wNV8JprrbxL1FJrFPsGcMbdZKMahZAfANpCGtHJ8N1bvDwQHjGiQDikfSHkEHw)); [Currency Inu](https://gmgn.ai/sol/token/jakXaYpoees4RWyAKRCHn5DQ542SK9Hry3mWaXppump) +0.95 ([buy tx](https://solscan.io/tx/oRo7pQs154fBADUnZpCxH661nCYHaahvgy7nyWHJG6U4egsocFYjjdAFYtvJsQ4KC3uGv9hTvgwnNojxHJzWu39))

**[FYHggF…CyUh](https://gmgn.ai/sol/address/FYHggFuZLTrd6PAZa9SKmDoiRELGzggP3etrQaPwCyUh)** — like-us, 17 snipes, **+5.39 SOL** (R1 +2.95 / R2 +2.44), without best 2 +0.15, ROI +63.5%, win 52%, median token +0.003 SOL, bootstrap P(mean≤0) 0.043
- Landing (MEASURED): median slot +1 (5% in the create slot), outside buys ahead median 3 (p25–p75 2–5), arrival in our feed median 209 ms (n=8), entry price ×1.23 of the post-bundle price, fee+tip 0.41% of the buy, tips [['none', 202], ['nozomi', 74]]
- PnL by place: 1-3 ahead: 10 tok +4.59 · 4-10 ahead: 6 tok +1.16 · 11+ ahead: 1 tok -0.35
- PnL by arrival ms (R2 17:10+): 100-250: 5 tok +1.56 · >=250: 3 tok -0.08
- Size 0.49 SOL (tiers 0.49); hold median 52 s (p25–p75 12–90), sells median 2, sold everything 82%; failed attempts on unfilled launches 1
- Picks (MEASURED): mostly one-off devs (88%); dev buy med 0.45 SOL; bundled 76% (glued med 4.31 SOL); X link 82% / site 52%; 23% graduated; top dev share 5% of 17 devs; busiest UTC hours 22,16,0
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: +14.9%/trade, +1.11 SOL (R1 -20.8%, R2 +23.8%); behind 2: +11.9%; behind 2 + hold 3 s: +31.6%; reactive follow (buy after its buy +1 trade, sell after its sell): -7.2%/trade
- Example: [Caillou](https://gmgn.ai/sol/token/B37wSqqYtPfiUTpWZMYiUYyG7BCULMcJZFzboSHrpump) +3.43 ([buy tx](https://solscan.io/tx/jUN8F7cqwtMgUSm4BZFa1fXaLB9xUCeLVfNXhDrMQ2qVkT2rugCdTUZSVLrWoyvy9KWRBHPfNH3yY7x6jdADc66)); [Go Incognito](https://gmgn.ai/sol/token/6g6PeQJsP28mxttPv55HMRY99Qz7MHw7uuhuJmptpump) +1.82 ([buy tx](https://solscan.io/tx/3Xifja3DfGxbCM5DTQGhcWEiLk1puoQ7PXE2rN4J1ySe6pRWTYWpbVEQMry9kkz8Ej3FNGHAi6YrjtWpk851f35e))

**[8jsPAC…D2Eg](https://gmgn.ai/sol/address/8jsPACiiC3x7d8gWN9yUUcvjqhJDpnEcV5BP8wPdD2Eg)** — like-us, 50 snipes, **+3.56 SOL** (R1 +0.24 / R2 +3.32), without best 2 +1.87, ROI +6.6%, win 44%, median token -0.002 SOL, bootstrap P(mean≤0) 0.017
- Landing (MEASURED): median slot +0 (62% in the create slot), outside buys ahead median 1 (p25–p75 0–3), arrival in our feed median 77 ms (n=16), entry price ×1.06 of the post-bundle price, fee+tip 0.12% of the buy, tips [['none', 275], ['astralane', 112], ['speedlanding', 106]]
- PnL by place: 0 ahead: 18 tok +1.44 · 1-3 ahead: 21 tok -0.46 · 4-10 ahead: 10 tok +2.24 · 11+ ahead: 1 tok +0.37
- PnL by arrival ms (R2 17:10+): <25ms: 4 tok -0.06 · 25-50: 2 tok +0.69 · 50-100: 4 tok +0.91 · 100-250: 5 tok +0.15 · >=250: 1 tok +0.87
- Size 0.92 SOL (tiers 0.49, 1.48, 0.45); hold median 1.0 s (p25–p75 1–3), sells median 1.0, sold everything 100%; failed attempts on unfilled launches 21
- Picks (MEASURED): serial devs (56% of picks; dev's launches in run med 4); dev buy med 3.00 SOL; bundled 98% (glued med 4.06 SOL); X link 92% / site 68%; top dev share 8% of 36 devs; busiest UTC hours 22,4,11
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: +1.7%/trade, +0.41 SOL (R1 -5.3%, R2 +9.9%); behind 2: +0.2%; behind 2 + hold 3 s: +1.0%; reactive follow (buy after its buy +1 trade, sell after its sell): -5.5%/trade
- Example: [CLASH](https://gmgn.ai/sol/token/mkRiA5yhi4Ddi5voqrNw5SKCfczMUFn9uECBgAypump) +0.87 ([buy tx](https://solscan.io/tx/3eTxpjNUGKRfBvXomqTVeyXBDAc1AA1AGPMMPKKstSbfpx9iBgg4Trq6YXVkY8MBjKCeN6cRo88vkXpaqxT8p3Xf)); [Cornlana](https://gmgn.ai/sol/token/34uXxDMG2Tmq3yyriaoFMWmKgrkyETGKicwKAjfBpump) +0.82 ([buy tx](https://solscan.io/tx/jxQzR1AJPZCEBTdguTC3vPvevJoZppBupoQ2Fhhn7T8hJZQt6TogehyphxLELf2LVU51QBijfjFm9ZEyH6ep5p7))

**[mwamTo…u6HG](https://gmgn.ai/sol/address/mwamTohZTS8VVDXhJBwEFzmWbbaax5sSYY8e8Vxu6HG)** — like-us, 21 snipes, **+3.56 SOL** (R1 +2.78 / R2 +0.77), without best 2 +2.37, ROI +15.4%, win 71%, median token +0.130 SOL, bootstrap P(mean≤0) 0.003
- Landing (MEASURED): median slot +1 (42% in the create slot), outside buys ahead median 2 (p25–p75 1–3), arrival in our feed median 64 ms (n=6), entry price ×1.11 of the post-bundle price, fee+tip 0.10% of the buy, tips [['none', 2226]]
- PnL by place: 0 ahead: 1 tok -0.12 · 1-3 ahead: 16 tok +2.67 · 4-10 ahead: 3 tok +0.69 · 11+ ahead: 1 tok +0.32
- PnL by arrival ms (R2 17:10+): 25-50: 3 tok +0.22 · 50-100: 1 tok -0.06 · 100-250: 1 tok +0.17 · >=250: 1 tok -0.12
- Size 1.09 SOL (tiers 1.09); hold median 5 s (p25–p75 2–7), sells median 1, sold everything 100%; failed attempts on unfilled launches 6
- Picks (MEASURED): serial devs (85% of picks; dev's launches in run med 6); dev buy med 3.00 SOL; bundled 100% (glued med 3.39 SOL); X link 100% / site 57%; top dev share 33% of 6 devs; busiest UTC hours 3,11,1
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: +17.1%/trade, +1.80 SOL (R1 +17.2%, R2 +16.9%); behind 2: +11.9%; behind 2 + hold 3 s: +6.0%; reactive follow (buy after its buy +1 trade, sell after its sell): +2.7%/trade
- Example: [The Last Coin](https://gmgn.ai/sol/token/BEL9R5Y1rgYRbvTChB8JAftAmjccAs3wRJXk3r4kpump) +0.59 ([buy tx](https://solscan.io/tx/51Gx2p96BB4av8v2HXJxkWaFFkdJ2NVjeTsS5XN3xHG4goVrZjR39RK6AvR6ePiHqchkibx6565STezNgqon4D4V)); [MoneroTesla](https://gmgn.ai/sol/token/29VZ85KXBHgKXU8umkssQR1uWCeyM9AZR5cBQiYNpump) +0.59 ([buy tx](https://solscan.io/tx/3BoL2ZtiipmJeRavw16sVcshZhbU1qofb8rkNSVWPZanzTvLeMNHZBmaogqwnwtEBHhsmDmb4QDg6bHq8wCdHFVY))

**[CWNAJ1…aVjp](https://gmgn.ai/sol/address/CWNAJ1ZTPxWpKH3CTGpZPAtFpTzsVuuXabCw16RbaVjp)** — like-us, 46 snipes, **+3.01 SOL** (R1 +1.97 / R2 +1.05), without best 2 +1.58, ROI +6.6%, win 50%, median token +0.001 SOL, bootstrap P(mean≤0) 0.023, in CANDIDATES.md #28
- Landing (MEASURED): median slot +0 (80% in the create slot), outside buys ahead median 1 (p25–p75 0–2), arrival in our feed median 82 ms (n=7), entry price ×1.09 of the post-bundle price, fee+tip 3.83% of the buy, tips [['helius', 82], ['none', 33], ['nozomi', 11]]
- PnL by place: 0 ahead: 18 tok +1.05 · 1-3 ahead: 26 tok +1.83 · 4-10 ahead: 2 tok +0.18
- PnL by arrival ms (R2 17:10+): 25-50: 3 tok +0.49 · 50-100: 3 tok +0.41 · 100-250: 1 tok -0.10
- Size 0.99 SOL (tiers 0.99); hold median 3.0 s (p25–p75 3–3), sells median 2.0, sold everything 100%; failed attempts on unfilled launches 7
- Picks (MEASURED): serial devs (97% of picks; dev's launches in run med 21.5); dev buy med 3.00 SOL; bundled 100% (glued med 3.92 SOL); X link 100% / site 69%; top dev share 10% of 19 devs; busiest UTC hours 16,23,3
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: +2.8%/trade, +0.64 SOL (R1 -1.3%, R2 +9.0%); behind 2: -1.3%; behind 2 + hold 3 s: +4.0%; reactive follow (buy after its buy +1 trade, sell after its sell): -4.5%/trade
- Example: [Schrödinger's Peng](https://gmgn.ai/sol/token/8k5qM579hj58U9jC217M5ojgxmhmMs17VgsjTZxMpump) +0.72 ([buy tx](https://solscan.io/tx/2qbTqoecqjAAQBSHGAyKxJRZ9aVQU3axg7Rd35nKM9jsWyonDgsACaqCq4XeBFAi2VGUESwqmmHJ7gZumupvFHgK)); [The COGE](https://gmgn.ai/sol/token/AQveU9hHeFeEGPbuzC5xM6CjD5VEL3KhMoHnbo9Lpump) +0.72 ([buy tx](https://solscan.io/tx/4yHcqsa7qBdEtWF3PLiDbNfwbeRtPbE2q8vutqGBimYjPHRKsVcSWnq7LiU7sYQwuSGPGbiLMDYiUGnMytmYhjMi))

**[CBKgS8…Wo2s](https://gmgn.ai/sol/address/CBKgS8Nj714YomoPPxhVLUWos7vSrWnuL2cVKnJqWo2s)** — like-us, 38 snipes, **+2.86 SOL** (R1 +0.61 / R2 +2.25), without best 2 +0.36, ROI +9.2%, win 39%, median token -0.011 SOL, bootstrap P(mean≤0) 0.07
- Landing (MEASURED): median slot +1 (47% in the create slot), outside buys ahead median 1.5 (p25–p75 0–3), arrival in our feed median 165 ms (n=6), entry price ×1.05 of the post-bundle price, fee+tip 0.22% of the buy, tips [['none', 411], ['speedlanding', 173], ['astralane', 171]]
- PnL by place: 0 ahead: 10 tok -0.28 · 1-3 ahead: 20 tok +0.10 · 4-10 ahead: 8 tok +3.09
- PnL by arrival ms (R2 17:10+): 50-100: 1 tok -0.11 · 100-250: 4 tok -0.05 · >=250: 1 tok +0.03
- Size 0.50 SOL (tiers 0.5, 0.47, 0.53); hold median 1.0 s (p25–p75 1–2), sells median 1.0, sold everything 100%; failed attempts on unfilled launches 46
- Picks (MEASURED): serial devs (86% of picks; dev's launches in run med 33); dev buy med 1.00 SOL; bundled 92% (glued med 2.20 SOL); X link 92% / site 47%; top dev share 36% of 17 devs; busiest UTC hours 0,16,3
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: +4.2%/trade, +0.80 SOL (R1 -0.8%, R2 +16.5%); behind 2: +0.8%; behind 2 + hold 3 s: +0.7%; reactive follow (buy after its buy +1 trade, sell after its sell): -6.5%/trade
- Example: [Veyron](https://gmgn.ai/sol/token/26saaJyLHcNUEbgYHBaxtd6oxumd83kxdAvUYb8Dpump) +1.49 ([buy tx](https://solscan.io/tx/5yvE1A5obifVR3CVJayToHhDL4XqxKeYmF9nbJK4zM9jdAoZPzzhj1hetR5LccKZz4oEVm7fVPV7aWQXx5bjzzfd)); [cyberattack](https://gmgn.ai/sol/token/HeZAZRLXP2R61WyW6dkcNU5bLHQCBShSrXtdvD1zpump) +1.02 ([buy tx](https://solscan.io/tx/4Skhj4WxBTSWSFbwMbyZvrdgNrT21im6mZoSAKBLg2TeUqd51Y8RupVHvQ148DhiU4wjrH6Q4zBdvDcxv9CvRT52))

**[AuTncr…ZnU6](https://gmgn.ai/sol/address/AuTncroT18PVNMzLBGpveiiyFs3faYJdVfewuCYEZnU6)** — like-us, 15 snipes, **+2.81 SOL** (R1 +2.53 / R2 +0.28), without best 2 +0.50, ROI +8.3%, win 46%, median token -0.016 SOL, bootstrap P(mean≤0) 0.013
- Landing (MEASURED): median slot +0 (66% in the create slot), outside buys ahead median 1 (p25–p75 0–4), arrival in our feed median 48 ms (n=3), entry price ×1.01 of the post-bundle price, fee+tip 0.11% of the buy, tips [['jito', 273], ['none', 59]]
- PnL by place: 0 ahead: 7 tok +0.67 · 1-3 ahead: 4 tok +0.04 · 4-10 ahead: 3 tok +1.96 · 11+ ahead: 1 tok +0.14
- PnL by arrival ms (R2 17:10+): 25-50: 2 tok -0.04 · 50-100: 1 tok -0.04
- Size 1.33 SOL (tiers 1.33, 1.23, 0.1); hold median 1 s (p25–p75 1–2), sells median 1, sold everything 100%; failed attempts on unfilled launches 1
- Picks (MEASURED): serial devs (66% of picks; dev's launches in run med 9); dev buy med 3.00 SOL; bundled 60% (glued med 2.50 SOL); X link 93% / site 66%; top dev share 6% of 15 devs; busiest UTC hours 22,2,18
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: +11.7%/trade, +0.88 SOL (R1 +12.4%, R2 +11.0%); behind 2: +10.9%; behind 2 + hold 3 s: +16.1%; reactive follow (buy after its buy +1 trade, sell after its sell): -2.5%/trade
- Example: [cybercurrency](https://gmgn.ai/sol/token/CMo7GfUhSGXuEfnY7qAzv8hhsV2M2P8GpWqmWikhpump) +1.78 ([buy tx](https://solscan.io/tx/47CMyxAnwbepdVTuxaSVGjmuBpjNpFdjTJG6QJoutQ34kxqRJtwXyuin6kJ15K1pvHRQPTL4idPZLpr2MbbWiBxx)); [CVE-2026-110264](https://gmgn.ai/sol/token/AuKNMG2ZQmXH9ZkPydSMrNcgfAxTdUFG8WQUYCZ7pump) +0.53 ([buy tx](https://solscan.io/tx/5HwoCEfqSXVFM3xagt1dZiCjQRaX5tv6baHEDvrWDxuTLxJQQNaVT5vp3x4bJMRsR9BFjs1o9sZv55Su8V6DX762))

**[E8s9ti…8MBp](https://gmgn.ai/sol/address/E8s9tiRtxzRKVrwbVEfjYn4c9fdhfhvG5aUnEah88MBp)** — like-us, 120 snipes, **+0.91 SOL** (R1 +0.04 / R2 +0.87), without best 2 +0.54, ROI +3.9%, win 40%, median token -0.004 SOL, bootstrap P(mean≤0) 0.043
- Landing (MEASURED): median slot +0 (56% in the create slot), outside buys ahead median 1 (p25–p75 0–2), arrival in our feed median 91 ms (n=43), entry price ×1.02 of the post-bundle price, fee+tip 0.04% of the buy, tips [['jito', 242], ['helius', 242]]
- PnL by place: 0 ahead: 44 tok +0.44 · 1-3 ahead: 72 tok +0.48 · 4-10 ahead: 4 tok -0.00
- PnL by arrival ms (R2 17:10+): <25ms: 7 tok -0.05 · 25-50: 11 tok +0.65 · 50-100: 6 tok +0.30 · 100-250: 18 tok -0.03 · >=250: 1 tok +0.00
- Size 0.20 SOL (tiers 0.2, 0.1); hold median 30.0 s (p25–p75 8–30), sells median 1.0, sold everything 100%; failed attempts on unfilled launches 22
- Picks (MEASURED): mostly one-off devs (67%); dev buy med 0.95 SOL; bundled 34% (glued med 0.00 SOL); X link 81% / site 70%; top dev share 8% of 95 devs; busiest UTC hours 23,21,22
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: +0.7%/trade, +0.45 SOL (R1 -3.4%, R2 +5.4%); behind 2: -0.7%; behind 2 + hold 3 s: +1.3%; reactive follow (buy after its buy +1 trade, sell after its sell): -1.7%/trade
- Example: [Deadnet](https://gmgn.ai/sol/token/BTe46C7q91ApUefUJUR7QJ4fViTW3ib8vHv4oijnpump) +0.22 ([buy tx](https://solscan.io/tx/2oCauhVRdWn6fyzaxgUsjFWSTBWpabWmZgEdqmm43SVCQ71NeGP33cWf9iq8HTDDqgLsix7zUjjyzLXPov51Adyc)); [Null Order](https://gmgn.ai/sol/token/6vMYP7ZB3Y1oS48FjCXfRoKvQTeTHosRgfaDtUmypump) +0.15 ([buy tx](https://solscan.io/tx/26WPR6RsXYXS1EH67r4WBNMSpA8wVYQ3KiqVF8fjhqSd5x3QmY87msVf9VSCtK6Tz4rAh8vUxHSSrkcmiFNjqyq1))

**[FZQwaU…kTnp](https://gmgn.ai/sol/address/FZQwaUPe9bvNDVH6byfF15t4RPnbcx66JvNk9dUrkTnp)** — like-us, 18 snipes, **+0.69 SOL** (R1 +0.12 / R2 +0.57), without best 2 +0.16, ROI +20.3%, win 72%, median token +0.013 SOL, bootstrap P(mean≤0) 0.0
- Landing (MEASURED): median slot +0 (55% in the create slot), outside buys ahead median 0.5 (p25–p75 0–1), arrival in our feed median 107 ms (n=9), entry price ×1.00 of the post-bundle price, fee+tip 2.54% of the buy, tips [['none', 19], ['helius', 9], ['astralane', 5]]
- PnL by place: 0 ahead: 9 tok +0.26 · 1-3 ahead: 9 tok +0.44
- PnL by arrival ms (R2 17:10+): 25-50: 3 tok +0.43 · 100-250: 5 tok +0.00 · >=250: 1 tok +0.02
- Size 0.10 SOL (tiers 0.1, 0.49); hold median 58.0 s (p25–p75 1–60), sells median 1.0, sold everything 100%; failed attempts on unfilled launches 5
- Picks (MEASURED): mostly one-off devs (61%); dev buy med 0.99 SOL; bundled 11% (glued med 0.00 SOL); X link 61% / site 66%; top dev share 5% of 18 devs; busiest UTC hours 12,17,16
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: +13.0%/trade, +1.17 SOL (R1 +11.5%, R2 +14.0%); behind 2: +8.2%; behind 2 + hold 3 s: +5.5%; reactive follow (buy after its buy +1 trade, sell after its sell): +7.7%/trade
- Example: [Drappy](https://gmgn.ai/sol/token/3PtJ8Xjnu1kAj8ZiHvwk7mzXC67W2NdE6iAX5aAgpump) +0.44 ([buy tx](https://solscan.io/tx/5zV7ao9vg3AwyprF7JBfiMYVohY4pMB8iGHhReHnR99L1xxvdn7RnNSHfaVNRq75PgiN1GuUjD1HQ2JEViU3KjTp)); [DEALT](https://gmgn.ai/sol/token/8KzcqGZ7LtVU5PwuAATixSEh8nc2hv8oJQ7JkpVFpump) +0.10 ([buy tx](https://solscan.io/tx/4T4FUJajC44N6AfZLFYPDvjacQiGBEhCV6W2VpULHFjM73QXtZemY6ZU5RKDxXAomjewqTJKPFzPefYbkFKSLGAQ))

**[HVE899…PGDJ](https://gmgn.ai/sol/address/HVE8996rtqG8N2sCNaTJZdLBbKW2SrSg2uXjJtNqPGDJ)** — like-us, 626 snipes, **+0.58 SOL** (R1 +0.39 / R2 +0.18), without best 2 +0.34, ROI +0.9%, win 43%, median token -0.003 SOL, bootstrap P(mean≤0) 0.137
- Landing (MEASURED): median slot +0.5 (50% in the create slot), outside buys ahead median 1 (p25–p75 0–2), arrival in our feed median 71 ms (n=227), entry price ×1.01 of the post-bundle price, fee+tip 0.13% of the buy, tips [['flashblock', 1536], ['none', 266], ['0slot', 195]]
- PnL by place: 0 ahead: 185 tok +0.55 · 1-3 ahead: 376 tok +0.09 · 4-10 ahead: 63 tok -0.09 · 11+ ahead: 2 tok +0.03
- PnL by arrival ms (R2 17:10+): <25ms: 5 tok -0.04 · 25-50: 69 tok +0.01 · 50-100: 68 tok +0.17 · 100-250: 74 tok -0.05 · >=250: 11 tok +0.09
- Size 0.09 SOL (tiers 0.09, 0.1, 0.08); hold median 88.0 s (p25–p75 88–88), sells median 1.0, sold everything 100%; failed attempts on unfilled launches 269
- Picks (MEASURED): serial devs (81% of picks; dev's launches in run med 25); dev buy med 1.44 SOL; bundled 20% (glued med 0.00 SOL); X link 63% / site 33%; top dev share 12% of 161 devs; busiest UTC hours 23,4,22
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: -2.1%/trade, -6.60 SOL (R1 -2.0%, R2 -2.3%); behind 2: -3.0%; behind 2 + hold 3 s: -2.3%; reactive follow (buy after its buy +1 trade, sell after its sell): -3.8%/trade
- Example: [Mark Clowney](https://gmgn.ai/sol/token/G1sGVGv3wrkekU8drdPAVgtisdHUTFVVRUZn3oc4pump) +0.14 ([buy tx](https://solscan.io/tx/3mB9GUxYisxuYPejNsmh3RKn8LZhENTdocyUFx38QvPz9LLjDWGMdzxJ973t4hqJ6sXT8m5Q5anHLACrEL1yLxGo)); [a16z frontier](https://gmgn.ai/sol/token/JA6RD4fTAgNakHKnAU2rxPs4hVtcmxdpG5ULs9Xipump) +0.10 ([buy tx](https://solscan.io/tx/2sxhgz2brcTPXnAuPrF4uSAH3N23hbjRuewX4kpZfDSpEFsVTwnZSt4GvBcRAFUFHiHnMFHTw4duMJZjDYCnZTNu))

**[8fN6Ny…EPXs](https://gmgn.ai/sol/address/8fN6NyEPbFziSybqSoFK8y3iSZhkHsKsoFiKB9rREPXs)** — like-us, 211 snipes, **+0.57 SOL** (R1 +0.08 / R2 +0.49), without best 2 +0.02, ROI +0.8%, win 33%, median token -0.010 SOL, bootstrap P(mean≤0) 0.237
- Landing (MEASURED): median slot +1 (0% in the create slot), outside buys ahead median 1 (p25–p75 0–2), arrival in our feed median 199 ms (n=124), entry price ×1.01 of the post-bundle price, fee+tip 0.35% of the buy, tips [['none', 285], ['helius', 186]]
- PnL by place: 0 ahead: 85 tok +0.47 · 1-3 ahead: 103 tok +0.29 · 4-10 ahead: 23 tok -0.19
- PnL by arrival ms (R2 17:10+): 50-100: 14 tok +0.09 · 100-250: 75 tok +0.05 · >=250: 35 tok +0.20
- Size 0.35 SOL (tiers 0.35, 0.2); hold median 31 s (p25–p75 31–32), sells median 1, sold everything 100%; failed attempts on unfilled launches 3
- Picks (MEASURED): mostly one-off devs (95%); dev buy med 0.86 SOL; bundled 21% (glued med 0.00 SOL); X link 73% / site 57%; top dev share 0% of 211 devs; busiest UTC hours 17,12,22
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: -1.5%/trade, -1.60 SOL (R1 -1.5%, R2 -1.5%); behind 2: -3.4%; behind 2 + hold 3 s: -1.7%; reactive follow (buy after its buy +1 trade, sell after its sell): -5.1%/trade
- Example: [Shill Pills Dot Fu](https://gmgn.ai/sol/token/FifukBKyNFeRCp3nA42H5kBThfk6wRUoDLRo2C4Ypump) +0.34 ([buy tx](https://solscan.io/tx/3Lw2GwU4yjXJ2qwrRq6YpvviU3ikfprtGzX4UTAKSehyaAi2nmkgQP5W8FaD81W71hMrK8ChpHWQCZbB29hr22U9)); [offchaincat](https://gmgn.ai/sol/token/Fz7uaMW9uuNmo4DEZnhqKiKrQFhjm172h9EctFxopump) +0.21 ([buy tx](https://solscan.io/tx/ds251zTHgMymjrhgSu37iXPmQEr1gnJdK6BKzSCLqL2iX3dPvfVzufHUTQda2NtcpbFegt9edhQfDdjEfy72YhK))

**[Six5j1…qdwf](https://gmgn.ai/sol/address/Six5j1cvdsZgh7vSgvYXD3FG69MPh7dae2qkjwTqdwf)** — like-us, 26 snipes, **+0.43 SOL** (R1 +0.28 / R2 +0.15), without best 2 +0.11, ROI +1.5%, win 46%, median token -0.009 SOL, bootstrap P(mean≤0) 0.117
- Landing (MEASURED): median slot +0 (88% in the create slot), outside buys ahead median 0.5 (p25–p75 0–1), arrival in our feed median 30 ms (n=12), entry price ×1.01 of the post-bundle price, fee+tip 2.57% of the buy, tips [['flashblock', 19], ['jito', 13], ['blockrazor', 7]]
- PnL by place: 0 ahead: 13 tok +0.57 · 1-3 ahead: 11 tok -0.00 · 4-10 ahead: 2 tok -0.04
- PnL by arrival ms (R2 17:10+): <25ms: 4 tok +0.30 · 25-50: 4 tok +0.11 · 50-100: 4 tok -0.14
- Size 1.26 SOL (tiers 0.72, 1.24, 1.33); hold median 0.0 s (p25–p75 0–1), sells median 1.0, sold everything 100%; failed attempts on unfilled launches 27
- Picks (MEASURED): serial devs (57% of picks; dev's launches in run med 3.5); dev buy med 2.98 SOL; bundled 73% (glued med 3.05 SOL); X link 96% / site 53%; top dev share 7% of 23 devs; busiest UTC hours 23,15,0
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: -2.4%/trade, -0.31 SOL (R1 +3.5%, R2 -5.0%); behind 2: -6.3%; behind 2 + hold 3 s: -8.9%; reactive follow (buy after its buy +1 trade, sell after its sell): -8.6%/trade
- Example: [FLIPPER 2](https://gmgn.ai/sol/token/Aki48SXAxdTaCe4PhwHG2aS3RrCuMuDYJivQdDX5pump) +0.20 ([buy tx](https://solscan.io/tx/2CcfnA76oHEdBcDHrjX81vXWKqzcGFKr9NEmvmx2XYCqPAk9UntUkYVep76jz7eBAG6A7fV5j8VgD2BVwGCy97NB)); [The PHP Dog](https://gmgn.ai/sol/token/BD7fRJZiM2cnH7m77DVZ6MzbCDmNaQsCF4tuLJyDpump) +0.12 ([buy tx](https://solscan.io/tx/2UJ8AECgNZaTT3EEE2cP5b61VNSmv52LBBqvF5iPYDRAmgLqPxkeXWv18p1Zk1iDJP7WLvWK5L1P3WB62ktcEdtG))

**[H6obho…1HtG](https://gmgn.ai/sol/address/H6obhoSNUbQhLNUoYFCBiKS4CMRC1qQYoBsms7y81HtG)** — like-us, 583 snipes, **+0.24 SOL** (R1 +0.01 / R2 +0.23), without best 2 +0.02, ROI +0.5%, win 40%, median token -0.002 SOL, bootstrap P(mean≤0) 0.3
- Landing (MEASURED): median slot +1 (44% in the create slot), outside buys ahead median 2 (p25–p75 1–3), arrival in our feed median 71 ms (n=210), entry price ×1.01 of the post-bundle price, fee+tip 0.14% of the buy, tips [['flashblock', 1630], ['none', 259], ['helius', 184]]
- PnL by place: 0 ahead: 74 tok +0.23 · 1-3 ahead: 402 tok +0.11 · 4-10 ahead: 102 tok -0.08 · 11+ ahead: 5 tok -0.02
- PnL by arrival ms (R2 17:10+): <25ms: 6 tok -0.04 · 25-50: 57 tok -0.04 · 50-100: 72 tok +0.24 · 100-250: 53 tok -0.02 · >=250: 22 tok +0.03
- Size 0.08 SOL (tiers 0.08, 0.07, 0.16); hold median 90.0 s (p25–p75 90–90), sells median 1, sold everything 99%; failed attempts on unfilled launches 235
- Picks (MEASURED): serial devs (72% of picks; dev's launches in run med 21); dev buy med 1.28 SOL; bundled 11% (glued med 0.00 SOL); X link 58% / site 32%; top dev share 13% of 206 devs; busiest UTC hours 23,22,0
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: -2.6%/trade, -7.71 SOL (R1 -3.0%, R2 -2.1%); behind 2: -3.5%; behind 2 + hold 3 s: -2.8%; reactive follow (buy after its buy +1 trade, sell after its sell): -4.2%/trade
- Example: [Mark Clowney](https://gmgn.ai/sol/token/G1sGVGv3wrkekU8drdPAVgtisdHUTFVVRUZn3oc4pump) +0.12 ([buy tx](https://solscan.io/tx/2UTCKLgzycFSyNRBMHJbojzdnBTifZLoHXBNLdN1z6B1FMu4Kkfb5EdSSTgQvXBM91Nbrk1oHzy54r3bUnDxQ2ox)); [The Blue Bitcoin](https://gmgn.ai/sol/token/9QFNfQa3LrSeAqfdFeysiSH25Ua1xhrv22UKCpFEpump) +0.11 ([buy tx](https://solscan.io/tx/2Hu5jNNysTShGtkGnk6utKMDu8QbJ1N4reeHkc7DkkLe5VSCHLGphf95KTSfVezEJ2wk1vzusjzQZbnUtsVNUe4P))

## Later than us (16): 2+ slots after the create

They profit without being first, but they mostly choose AFTER seeing about 0.5–1 s of price action:
- Their entry is at ×1.3–1.6 of the post-bundle price for 2maW7x2X, retAumPG, 4Yy3xBZn, 5XU7ApZv and 5FEM1HQj.
- HnFPB3iA and G3gKCu8X buy right after mega-bundles (55–70 SOL glued) and sell after graduation on the AMM.

Their "same tokens at our place" numbers (+25..+60% per trade) use information we would not have at 74 ms. They are an upper bound, not a copy result. Reactive following of them is about 0 to +10% per trade on small samples.

**[2maW7x…3Zfb](https://gmgn.ai/sol/address/2maW7x2X4shMK3bNc3bGNvRpweindJXzujgdszgp3Zfb)** — later, 83 snipes, **+17.82 SOL** (R1 +0.67 / R2 +17.14), without best 2 +3.98, ROI +10.5%, win 42%, median token -0.023 SOL, bootstrap P(mean≤0) 0.017
- Includes +14.31 SOL of tokens still held at the end; 1 of them graduated while held (AMM price unknown, valued at the last curve price). Without those: +6.51 SOL
- Landing (MEASURED): median slot +4 (0% in the create slot), outside buys ahead median 8 (p25–p75 5–10), arrival in our feed median 810 ms (n=4), entry price ×1.34 of the post-bundle price, fee+tip 0.10% of the buy, tips [['nozomi', 187], ['helius', 62], ['landx', 15]]
- PnL by place: 1-3 ahead: 10 tok +1.14 · 4-10 ahead: 54 tok +15.27 · 11+ ahead: 19 tok +1.41
- PnL by arrival ms (R2 17:10+): >=250: 4 tok +0.19
- Size 1.98 SOL (tiers 1.98, 2.96, 0.99); hold median 1.0 s (p25–p75 0–1), sells median 1, sold everything 98%; failed attempts on unfilled launches 6
- Picks (MEASURED): serial devs (53% of picks; dev's launches in run med 3); dev buy med 4.00 SOL; bundled 56% (glued med 4.20 SOL); X link 96% / site 77%; top dev share 10% of 63 devs; busiest UTC hours 23,22,17
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: +34.2%/trade, +14.03 SOL (R1 +29.1%, R2 +38.6%); behind 2: +24.6%; behind 2 + hold 3 s: +32.3%; reactive follow (buy after its buy +1 trade, sell after its sell): -6.9%/trade
- Example: [Aura Final Boss](https://gmgn.ai/sol/token/3HqYs4E5UiotUcEstJneSzWC7nL6L2w25jn5L7Pyz1v5) +11.31 ([buy tx](https://solscan.io/tx/ftvNKz8LTbb2CeQ6PcHnb38EkFaYiQ3kj8ycx78vsDwDFnDUgKS8nECn5hvwxBsrbTaSGXmTDhr8CPFA6gSFDR4)); [PSYOPERA](https://gmgn.ai/sol/token/GoLciU2ch1RwBf4sL6oEb6kVa3rZHPhGqBgHimuXpump) +2.53 ([buy tx](https://solscan.io/tx/2KUJq7F3BsibtPGBfT5K5E1Nzdu1mWkbxEARwLNjM5PNcrrGmo5HUncR55eyLZ1fqaHu55KTK6exHGPX74HdfFEq))

**[A21wCG…HNVn](https://gmgn.ai/sol/address/A21wCG8HK3fQSFrb7YS8xwtn5Rn1ujDeMfpKF9TPHNVn)** — later, 287 snipes, **+11.24 SOL** (R1 +6.17 / R2 +5.07), without best 2 +6.51, ROI +4.9%, win 26%, median token -0.027 SOL, bootstrap P(mean≤0) 0.017
- Landing (MEASURED): median slot +2 (0% in the create slot), outside buys ahead median 1 (p25–p75 0–3), arrival in our feed median 350 ms (n=97), entry price ×1.02 of the post-bundle price, fee+tip 0.05% of the buy, tips [['nozomi', 290], ['astralane', 132], ['0slot', 111]]
- PnL by place: 0 ahead: 89 tok +3.49 · 1-3 ahead: 152 tok +4.96 · 4-10 ahead: 46 tok +2.90
- PnL by arrival ms (R2 17:10+): 100-250: 11 tok -0.61 · >=250: 86 tok +3.17
- Size 0.77 SOL (tiers 0.6, 0.3, 0.59); hold median 87 s (p25–p75 14–361), sells median 1, sold everything 100%; failed attempts on unfilled launches 659
- Picks (MEASURED): mostly one-off devs (74%); dev buy med 0.98 SOL; bundled 16% (glued med 0.00 SOL); X link 100% / site 73%; top dev share 2% of 251 devs; busiest UTC hours 22,23,0
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: -0.3%/trade, -0.40 SOL (R1 +0.9%, R2 -1.7%); behind 2: -2.4%; behind 2 + hold 3 s: +2.7%; reactive follow (buy after its buy +1 trade, sell after its sell): -5.4%/trade
- Example: [Null Order](https://gmgn.ai/sol/token/6vMYP7ZB3Y1oS48FjCXfRoKvQTeTHosRgfaDtUmypump) +2.36 ([buy tx](https://solscan.io/tx/5N6cJPfLRQbdMrez7PhCMymyxmczEZKfv6S92B1fAPJyznKvPQ2yqaJXe1J4gXitSeJFSuXVvGQKDeVr9R4VY2VJ)); [Marathon Fusion](https://gmgn.ai/sol/token/E2FkKbPHiJ9NdGDN1YRpB8nsFzSGgxkTD3PGXuUtpump) +2.36 ([buy tx](https://solscan.io/tx/4JKeKFPgSeY6zXbQfdjJdKf6ewX6bXTEWq56UniTyZqGV3WB5eMKT55yQKxWRLAWdo6ZuC4wZU6SWjzwAagU3rgh))

**[retAum…Bard](https://gmgn.ai/sol/address/retAumPGyn3U2jjpgRtMLkJR6YnYugSWQiMo9sdBard)** — later, 28 snipes, **+9.00 SOL** (R1 +3.70 / R2 +5.29), without best 2 +2.85, ROI +32.1%, win 46%, median token -0.085 SOL, bootstrap P(mean≤0) 0.033
- Landing (MEASURED): median slot +3 (0% in the create slot), outside buys ahead median 13 (p25–p75 8–15), arrival in our feed median None ms (n=0), entry price ×1.59 of the post-bundle price, fee+tip 0.11% of the buy, tips [['helius', 557]]
- PnL by place: 1-3 ahead: 1 tok +0.40 · 4-10 ahead: 12 tok -0.50 · 11+ ahead: 15 tok +9.09
- PnL by arrival ms (R2 17:10+): no engine timeline overlap
- Size 0.99 SOL (tiers 0.99); hold median 120 s (p25–p75 67–180), sells median 1.0, sold everything 92%; failed attempts on unfilled launches 1
- Picks (MEASURED): mostly one-off devs (96%); dev buy med 0.86 SOL; bundled 60% (glued med 2.10 SOL); X link 92% / site 92%; top dev share 3% of 28 devs; busiest UTC hours 23,17,20
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: +57.5%/trade, +7.76 SOL (R1 +52.8%, R2 +61.8%); behind 2: +43.9%; behind 2 + hold 3 s: +42.0%; reactive follow (buy after its buy +1 trade, sell after its sell): +10.4%/trade
- Example: [Go Incognito](https://gmgn.ai/sol/token/6g6PeQJsP28mxttPv55HMRY99Qz7MHw7uuhuJmptpump) +3.08 ([buy tx](https://solscan.io/tx/553avqF8mbS3EdCQVSQXmKAwerv9HKx4hQ5mTRn8RNpMxx3t1xaTZoDPwZuxjgDr16q5KpeNS2Yn3xVdzpAZF8Jh)); [Caillou](https://gmgn.ai/sol/token/B37wSqqYtPfiUTpWZMYiUYyG7BCULMcJZFzboSHrpump) +3.07 ([buy tx](https://solscan.io/tx/519NzBTMVm18JmzFqsinz9hCpycw7w62i6WwUpn32gYoYKJJ1ZYRgQWVz6kRZqzvxAQsWoLxFbWKbo8mcSJ3VKtH))

**[haqqiU…QgWq](https://gmgn.ai/sol/address/haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq)** — later, 538 snipes, **+8.00 SOL** (R1 +5.63 / R2 +2.37), without best 2 +5.63, ROI +2.2%, win 36%, median token -0.010 SOL, bootstrap P(mean≤0) 0.017
- Includes +2.52 SOL of tokens still held at the end; 1 of them graduated while held (AMM price unknown, valued at the last curve price). Without those: +6.65 SOL
- Landing (MEASURED): median slot +4 (0% in the create slot), outside buys ahead median 5 (p25–p75 3–8), arrival in our feed median 690 ms (n=35), entry price ×1.03 of the post-bundle price, fee+tip 0.12% of the buy, tips [['helius', 10057], ['none', 3848], ['0slot', 676]]
- PnL by place: 0 ahead: 13 tok +0.35 · 1-3 ahead: 161 tok +2.03 · 4-10 ahead: 282 tok +4.55 · 11+ ahead: 82 tok +1.08
- PnL by arrival ms (R2 17:10+): 50-100: 1 tok +0.02 · 100-250: 2 tok -0.06 · >=250: 32 tok -0.03
- Size 0.25 SOL (tiers 0.25, 0.27, 0.01); hold median 13.0 s (p25–p75 6–37), sells median 2.0, sold everything 99%; failed attempts on unfilled launches 14
- Picks (MEASURED): serial devs (72% of picks; dev's launches in run med 11); dev buy med 3.00 SOL; bundled 71% (glued med 3.75 SOL); X link 94% / site 64%; top dev share 6% of 245 devs; busiest UTC hours 23,16,17
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: -1.3%/trade, -3.42 SOL (R1 -2.3%, R2 +0.2%); behind 2: -3.5%; behind 2 + hold 3 s: -2.7%; reactive follow (buy after its buy +1 trade, sell after its sell): -3.8%/trade
- Example: [Aura Final Boss](https://gmgn.ai/sol/token/3HqYs4E5UiotUcEstJneSzWC7nL6L2w25jn5L7Pyz1v5) +1.34 ([buy tx](https://solscan.io/tx/4dhQRgATyuRZd3oJ9h7bkqqWin3z1Dqmfxi2kbxMRAsPJHchDNhDecywMnXjjeDQPjcbhjPeJeKQQhmSG9W9XsKV)); [Dogewifhat](https://gmgn.ai/sol/token/CqKTxE1yXCvJCBgHeNA9GMsdRA1CYLusbEtkRcuVpump) +1.02 ([buy tx](https://solscan.io/tx/55DewH14u9zDXYXMxamg3kQrUkRSerYMVVW3QPab3T5pFiU26mVDKhFLTNBQUPrqL8iabD7VB52GG4oVirUj3AUF))

**[6Kj5Ch…RVRp](https://gmgn.ai/sol/address/6Kj5ChEZnyNjgATjjSvp8AveJRa9Nerjir2c4Nh2RVRp)** — later, 144 snipes, **+7.29 SOL** (R1 +3.65 / R2 +3.64), without best 2 +3.46, ROI +10.1%, win 43%, median token -0.012 SOL, bootstrap P(mean≤0) 0.003
- Includes +3.17 SOL of tokens still held at the end; 1 of them graduated while held (AMM price unknown, valued at the last curve price). Without those: +4.62 SOL
- Landing (MEASURED): median slot +2 (0% in the create slot), outside buys ahead median 4 (p25–p75 2–6), arrival in our feed median 577 ms (n=2), entry price ×1.08 of the post-bundle price, fee+tip 0.41% of the buy, tips [['helius', 144], ['nozomi', 83], ['astralane', 53]]
- PnL by place: 0 ahead: 6 tok -0.76 · 1-3 ahead: 55 tok +5.68 · 4-10 ahead: 75 tok +2.14 · 11+ ahead: 8 tok +0.23
- PnL by arrival ms (R2 17:10+): >=250: 2 tok -0.21
- Size 0.49 SOL (tiers 0.49); hold median 9 s (p25–p75 8–9), sells median 1.0, sold everything 99%; failed attempts on unfilled launches 0
- Picks (MEASURED): serial devs (90% of picks; dev's launches in run med 37); dev buy med 4.94 SOL; bundled 63% (glued med 3.46 SOL); X link 99% / site 93%; top dev share 28% of 49 devs; busiest UTC hours 22,23,10
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: +9.1%/trade, +6.50 SOL (R1 +9.1%, R2 +9.1%); behind 2: +5.5%; behind 2 + hold 3 s: +4.8%; reactive follow (buy after its buy +1 trade, sell after its sell): +2.5%/trade
- Example: [Aura Final Boss](https://gmgn.ai/sol/token/3HqYs4E5UiotUcEstJneSzWC7nL6L2w25jn5L7Pyz1v5) +2.67 ([buy tx](https://solscan.io/tx/2wPk8LNBMevXHYTCLdc4DanNBVGWjWJ8mjmdispMN7egjVFJKr3PjAy2th8fqbJzufSxoZmBJSp4ehr9tV44kzyH)); [PUMPVENGERS](https://gmgn.ai/sol/token/9eXneWi85Q3csudKv8VwNQ3vW2gTYdzjAc5Tz1CBw79U) +1.16 ([buy tx](https://solscan.io/tx/3aY8oS1Q1P69aWSakBSUaawBs4VgCEVb3G3oNDpotv1qvtWWF9TVU1L3rc6zjwAHc351HLLpWVnYafF2sUpH72kJ))

**[HnFPB3…HXNH](https://gmgn.ai/sol/address/HnFPB3iAAb1dtsBfzcomHibua1Cw8Qx5b5wt5ttrHXNH)** — later, 26 snipes, **+5.81 SOL** (R1 +2.38 / R2 +3.43), without best 2 +2.51, ROI +59.1%, win 46%, median token -0.061 SOL, bootstrap P(mean≤0) 0.02
- Landing (MEASURED): median slot +2 (0% in the create slot), outside buys ahead median 4 (p25–p75 3–7), arrival in our feed median None ms (n=0), entry price ×1.04 of the post-bundle price, fee+tip 0.23% of the buy, tips [['helius', 1088], ['jito', 136]]
- PnL by place: 0 ahead: 1 tok -0.41 · 1-3 ahead: 9 tok +2.36 · 4-10 ahead: 14 tok +4.05 · 11+ ahead: 2 tok -0.19
- PnL by arrival ms (R2 17:10+): no engine timeline overlap
- Size 0.24 SOL (tiers 0.19, 0.46, 0.24); hold median 89.0 s (p25–p75 54–222), sells median 0.0, sold everything 42%; failed attempts on unfilled launches 1
- Picks (MEASURED): mostly one-off devs (96%); dev buy med 0.29 SOL; bundled 92% (glued med 62.25 SOL); X link 100% / site 92%; 61% graduated; top dev share 3% of 26 devs; busiest UTC hours 8,6,16
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: -55.8%/trade, -3.07 SOL (R1 -60.8%, R2 -42.6%); behind 2: -58.5%; behind 2 + hold 3 s: +28.9%; reactive follow (buy after its buy +1 trade, sell after its sell): -70.5%/trade
- Example: [LastCall](https://gmgn.ai/sol/token/Bnq4KRE1i1gcvFjqPaPNtkFs2ZojsPGEoAaPTkvGpump) +1.66 ([buy tx](https://solscan.io/tx/3WiVuCAKhGFZk3o2hsz6biz7w4Qv1Q4NXk2gHtXc8fM1wBE25PBZaX2r235nxYzry58z5oB4fV26sPsk5Vn8CVbQ)); [onboard](https://gmgn.ai/sol/token/91ZVg32ZXX8qW9jKvAzMrQkJXNhatuZZfULHwi2Cpump) +1.64 ([buy tx](https://solscan.io/tx/4VGENwxESxcN3XvHE1rLzyp9kFnTauWAGbzYC5BafJQKJ2fVjR4Zhe8hzXV3sBLnaZeLZzKsdBXbJTCJCJAzP1H9))

**[4Yy3xB…5AeY](https://gmgn.ai/sol/address/4Yy3xBZnJfhkmFAcV6hgdjWgkkc9oCoWEtcUiXNq5AeY)** — later, 82 snipes, **+3.42 SOL** (R1 +2.13 / R2 +1.29), without best 2 +0.10, ROI +8.8%, win 37%, median token -0.015 SOL, bootstrap P(mean≤0) 0.13
- Landing (MEASURED): median slot +2 (8% in the create slot), outside buys ahead median 7 (p25–p75 5–10), arrival in our feed median 284 ms (n=23), entry price ×1.31 of the post-bundle price, fee+tip 0.24% of the buy, tips [['falcon', 587], ['0slot', 226], ['bolt', 47]]
- PnL by place: 1-3 ahead: 2 tok +0.02 · 4-10 ahead: 64 tok +3.67 · 11+ ahead: 16 tok -0.28
- PnL by arrival ms (R2 17:10+): 50-100: 2 tok -0.01 · 100-250: 9 tok -0.22 · >=250: 12 tok +0.04
- Size 0.45 SOL (tiers 0.6, 0.37, 0.31); hold median 7.0 s (p25–p75 2–16), sells median 1.0, sold everything 100%; failed attempts on unfilled launches 1
- Picks (MEASURED): mostly one-off devs (87%); dev buy med 0.99 SOL; bundled 50% (glued med 0.07 SOL); X link 92% / site 80%; top dev share 2% of 81 devs; busiest UTC hours 23,21,22
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: +30.5%/trade, +12.49 SOL (R1 +34.4%, R2 +27.6%); behind 2: +21.4%; behind 2 + hold 3 s: +24.6%; reactive follow (buy after its buy +1 trade, sell after its sell): +1.4%/trade
- Example: [yAI](https://gmgn.ai/sol/token/DoRDRa4mbjmgTpXhBentiR3HEZt17C5r5FYtyWVzpump) +2.40 ([buy tx](https://solscan.io/tx/2kNdJPz4MZbQgozzyRpTfXP2iK1EqLxdxSngPHxhHSEnSR3ik7jVpNU6qTuTQ5ncCS6XQtPPUgPnxQzRs2KGhUj3)); [cyberattack](https://gmgn.ai/sol/token/HeZAZRLXP2R61WyW6dkcNU5bLHQCBShSrXtdvD1zpump) +0.92 ([buy tx](https://solscan.io/tx/3HNTJ91nwZyfEkvg4b15Ln5QGwrXJH3XhWSydAcPCTCq1BK7R5eEtQYbW1TRHW7Ub2WxnFq4yah5MEgMrtbZN6aN))

**[5XU7Ap…bX3j](https://gmgn.ai/sol/address/5XU7ApZvC9deBCNLPKyR2FgQZPXH8LLBkYXhCnJNbX3j)** — later, 25 snipes, **+3.02 SOL** (R1 +0.62 / R2 +2.40), without best 2 +1.59, ROI +9.7%, win 60%, median token +0.027 SOL, bootstrap P(mean≤0) 0.003
- Landing (MEASURED): median slot +4 (4% in the create slot), outside buys ahead median 6 (p25–p75 5–9), arrival in our feed median 251 ms (n=2), entry price ×1.30 of the post-bundle price, fee+tip 0.19% of the buy, tips [['none', 176], ['astralane', 76], ['speedlanding', 51]]
- PnL by place: 0 ahead: 1 tok -0.01 · 1-3 ahead: 3 tok -0.23 · 4-10 ahead: 17 tok +1.85 · 11+ ahead: 4 tok +1.41
- PnL by arrival ms (R2 17:10+): 25-50: 1 tok -0.01 · >=250: 1 tok +0.63
- Size 0.99 SOL (tiers 1.19, 0.57, 0.62); hold median 1 s (p25–p75 1–2), sells median 1, sold everything 100%; failed attempts on unfilled launches 0
- Picks (MEASURED): mostly one-off devs (52%); dev buy med 1.85 SOL; bundled 56% (glued med 2.00 SOL); X link 100% / site 80%; top dev share 12% of 22 devs; busiest UTC hours 19,5,23
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: +29.7%/trade, +3.71 SOL (R1 +31.5%, R2 +27.7%); behind 2: +22.3%; behind 2 + hold 3 s: +27.8%; reactive follow (buy after its buy +1 trade, sell after its sell): -4.9%/trade
- Example: [O DOT](https://gmgn.ai/sol/token/DoLPaV8VqtSxtoHprtRxsSuWjWTUvYsgF1Fcbgshpump) +0.77 ([buy tx](https://solscan.io/tx/5t4vFmpdbyWynF38RtMMp3ALYHkqr8V1sYJ6fUoPd8Z2TaDoC77FvTz7ernh6ykcFCHbtDH9pcXsajHCcqjcDQJh)); [Aura Final Boss](https://gmgn.ai/sol/token/3HqYs4E5UiotUcEstJneSzWC7nL6L2w25jn5L7Pyz1v5) +0.67 ([buy tx](https://solscan.io/tx/JEWsLFn1xuUafbw93HJWTyBrdC7P2K77GS8v2xT6GNdSrvSgQNf9Avd7vcoMyxw4bBsqgQDe296xUBEd5ba1jfx))

**[HkQ7hM…NExQ](https://gmgn.ai/sol/address/HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ)** — later, 83 snipes, **+2.17 SOL** (R1 +0.89 / R2 +1.28), without best 2 +1.40, ROI +4.2%, win 50%, median token +0.000 SOL, bootstrap P(mean≤0) 0.01
- Landing (MEASURED): median slot +4 (4% in the create slot), outside buys ahead median 5 (p25–p75 3–8), arrival in our feed median 563 ms (n=5), entry price ×1.03 of the post-bundle price, fee+tip 0.23% of the buy, tips [['nozomi', 1179], ['helius', 1065], ['none', 883]]
- PnL by place: 0 ahead: 1 tok +0.15 · 1-3 ahead: 26 tok +0.59 · 4-10 ahead: 41 tok +0.32 · 11+ ahead: 15 tok +1.13
- PnL by arrival ms (R2 17:10+): 100-250: 1 tok +0.02 · >=250: 4 tok -0.05
- Size 0.50 SOL (tiers 0.5, 0.51, 0.47); hold median 5.5 s (p25–p75 2–13), sells median 1, sold everything 98%; failed attempts on unfilled launches 68
- Picks (MEASURED): serial devs (56% of picks; dev's launches in run med 3); dev buy med 1.98 SOL; bundled 60% (glued med 1.98 SOL); X link 88% / site 73%; top dev share 7% of 72 devs; busiest UTC hours 22,23,11
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: -8.1%/trade, -3.32 SOL (R1 -12.9%, R2 -0.6%); behind 2: -11.7%; behind 2 + hold 3 s: -8.5%; reactive follow (buy after its buy +1 trade, sell after its sell): -2.9%/trade
- Example: [AI Slop Apocalypse](https://gmgn.ai/sol/token/6WY58skMK4sN4fUibXPW5UTKxAHgSZdF3DbP2KWSpump) +0.47 ([buy tx](https://solscan.io/tx/4Yvuy4L9WANa1iFAFjG4TacJ5EtDdh6kj5bueAwy6BBrZHWE24k9xUXhi4dJzFhMDw76AGqReUqFWMqNiqN16acJ)); [Vaccine Coin](https://gmgn.ai/sol/token/ngyUmBQThKnbgRPFYJNDkKunCPoxzvMgeYbjfm1pump) +0.30 ([buy tx](https://solscan.io/tx/5E3koMYeo4JqeofKYVKPVsMAQMkxL1VPVft617UfpHb7BMApnyYoG6FZ14LgJ2AjFPTkXaq66rvsyaZ2oXYRYPfV))

**[4mjnzW…Ls8y](https://gmgn.ai/sol/address/4mjnzWwdtFRVT9hJu8NiJvwK25mXbR4XZcKQ3Qm1Ls8y)** — later, 53 snipes, **+1.61 SOL** (R1 +0.37 / R2 +1.23), without best 2 +0.74, ROI +6.1%, win 28%, median token -0.012 SOL, bootstrap P(mean≤0) 0.03
- Landing (MEASURED): median slot +2 (0% in the create slot), outside buys ahead median 3 (p25–p75 1–4), arrival in our feed median 457 ms (n=20), entry price ×1.10 of the post-bundle price, fee+tip 0.02% of the buy, tips [['helius', 112]]
- PnL by place: 1-3 ahead: 35 tok -0.31 · 4-10 ahead: 16 tok +1.43 · 11+ ahead: 2 tok +0.48
- PnL by arrival ms (R2 17:10+): 100-250: 2 tok -0.04 · >=250: 18 tok +0.39
- Size 0.49 SOL (tiers 0.49); hold median 4 s (p25–p75 3–4), sells median 1, sold everything 100%; failed attempts on unfilled launches 4
- Picks (MEASURED): mostly one-off devs (96%); dev buy med 1.01 SOL; bundled 1% (glued med 0.00 SOL); X link 88% / site 81%; top dev share 1% of 53 devs; busiest UTC hours 18,17,19
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: +18.3%/trade, +4.86 SOL (R1 +26.4%, R2 +14.5%); behind 2: +12.4%; behind 2 + hold 3 s: +16.3%; reactive follow (buy after its buy +1 trade, sell after its sell): -1.5%/trade
- Example: [FORTELL](https://gmgn.ai/sol/token/fortt5Z2vR3vqPW4b82ZxhkNYxnm2V6KZusYRU6Mewd) +0.46 ([buy tx](https://solscan.io/tx/4SQJezH6p3NQWekLrwMA99vGDoKQYmRNdhk68cevNi82pyLcoYJR5yzPdYDXAEjx8MrLQyKteLRqNLiuMizy1Fat)); [Veyron](https://gmgn.ai/sol/token/26saaJyLHcNUEbgYHBaxtd6oxumd83kxdAvUYb8Dpump) +0.41 ([buy tx](https://solscan.io/tx/aKDQYznzRAUCKbxYVErPC94N24vSEZmoRYHkijVjyogkLAL87Wihvz2RsA3Ckd5viZAAWrK1BqwQMnwrNUK3r5o))

**[9iCGPg…iPXm](https://gmgn.ai/sol/address/9iCGPgiZrzQayYSzM5W4Uc99zgdf86QZXu91uZ4DiPXm)** — later, 19 snipes, **+1.34 SOL** (R1 +0.01 / R2 +1.32), without best 2 +0.43, ROI +19.1%, win 57%, median token +0.017 SOL, bootstrap P(mean≤0) 0.027
- Landing (MEASURED): median slot +4 (0% in the create slot), outside buys ahead median 11 (p25–p75 7–12), arrival in our feed median None ms (n=0), entry price ×1.18 of the post-bundle price, fee+tip 0.24% of the buy, tips [['helius', 58], ['none', 58]]
- PnL by place: 1-3 ahead: 1 tok -0.05 · 4-10 ahead: 8 tok +0.67 · 11+ ahead: 10 tok +0.71
- PnL by arrival ms (R2 17:10+): no engine timeline overlap
- Size 0.25 SOL (tiers 0.25, 0.49); hold median 31 s (p25–p75 31–31), sells median 1, sold everything 100%; failed attempts on unfilled launches 0
- Picks (MEASURED): serial devs (73% of picks; dev's launches in run med 4); dev buy med 2.00 SOL; bundled 100% (glued med 2.84 SOL); X link 100% / site 78%; top dev share 47% of 6 devs; busiest UTC hours 18,11,10
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: +18.3%/trade, +1.74 SOL (R1 +5.8%, R2 +32.3%); behind 2: +15.0%; behind 2 + hold 3 s: +9.8%; reactive follow (buy after its buy +1 trade, sell after its sell): +12.7%/trade
- Example: [Schrödinger's Peng](https://gmgn.ai/sol/token/FFkfn49uMgXiZNJyUXVAaE1nwPWqDU7oNkNjyybqpump) +0.54 ([buy tx](https://solscan.io/tx/3AsSnUismkLS3mWMc38scTguM88wd9r9cKXpMbkbEf2utN9iPifRiabrJAyiau4ew8mEX2hDpvrt3U8F5fpCX6h3)); [Justice For Alan A](https://gmgn.ai/sol/token/8GCHiDqSBEGGWLgCFTuints6KBCuDXbosFh2yWFkpump) +0.37 ([buy tx](https://solscan.io/tx/24xhmVuAQeZdqWtPttH2QqrsywzztDW5HBuwYsV2vNEgzkm4L3djsbawYfAfFqck4RP67A4fnDE8pt7uXY2RaRah))

**[G2fPBR…dxfP](https://gmgn.ai/sol/address/G2fPBRFRwqrSeJnTmrgBEeEtZpHbaXvnrHdppaWrdxfP)** — later, 34 snipes, **+0.49 SOL** (R1 +0.49 / R2 +0.00), without best 2 +0.24, ROI +11.1%, win 55%, median token +0.003 SOL, bootstrap P(mean≤0) 0.05
- Landing (MEASURED): median slot +2 (20% in the create slot), outside buys ahead median 5 (p25–p75 1–7), arrival in our feed median None ms (n=0), entry price ×1.05 of the post-bundle price, fee+tip 0.18% of the buy, tips [['helius', 93], ['none', 10]]
- PnL by place: 0 ahead: 3 tok +0.04 · 1-3 ahead: 13 tok +0.25 · 4-10 ahead: 17 tok +0.25 · 11+ ahead: 1 tok -0.06
- PnL by arrival ms (R2 17:10+): no engine timeline overlap
- Size 0.15 SOL (tiers 0.15, 0.1); hold median 8.0 s (p25–p75 6–9), sells median 1.0, sold everything 100%; failed attempts on unfilled launches 0
- Picks (MEASURED): serial devs (61% of picks; dev's launches in run med 22); dev buy med 2.96 SOL; bundled 100% (glued med 5.24 SOL); X link 100% / site 67%; top dev share 17% of 19 devs; busiest UTC hours 1,10,3
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: +9.8%/trade, +1.66 SOL (R1 +9.8%, R2 +0.0%); behind 2: +8.3%; behind 2 + hold 3 s: +6.2%; reactive follow (buy after its buy +1 trade, sell after its sell): +5.0%/trade
- Example: [Aura Final Boss](https://gmgn.ai/sol/token/GpeEUB1CwTX1Tue9h4FeuTK1VjGviQ1SoVDzsDZYRVxw) +0.13 ([buy tx](https://solscan.io/tx/3rWn57aiG72d642iJvxBP5uWEYDJNxKz2eYTbmToBDtn3SkFF9VHyTpBoYFjKyuqRe6bwXVUs1XGksSpF3xV31zq)); [Act III: The Birth](https://gmgn.ai/sol/token/3VbnKKRF8en6xMb56xdCVREWREcUoG44k26Krg46A9LR) +0.11 ([buy tx](https://solscan.io/tx/26nifDJ2izciGMZAi2ULF1TdSB3jmbbiSexyHjAENm7cHfHE9eBZJ5KG4Wbyunpo1upnP54HcCdgSWMFE1ktq1JQ))

**[DiqYk5…c3j4](https://gmgn.ai/sol/address/DiqYk5RDxWgqDjnhcsefUyc3DY12T9vbhvjWQMLhc3j4)** — later, 106 snipes, **+0.43 SOL** (R1 +0.12 / R2 +0.32), without best 2 +0.10, ROI +1.6%, win 37%, median token -0.008 SOL, bootstrap P(mean≤0) 0.217
- Landing (MEASURED): median slot +3 (0% in the create slot), outside buys ahead median 6 (p25–p75 4–9), arrival in our feed median 400 ms (n=4), entry price ×1.01 of the post-bundle price, fee+tip 0.17% of the buy, tips [['helius', 1070], ['speedlanding', 316], ['none', 201]]
- PnL by place: 0 ahead: 2 tok +0.03 · 1-3 ahead: 19 tok -0.03 · 4-10 ahead: 69 tok +0.35 · 11+ ahead: 16 tok +0.10
- PnL by arrival ms (R2 17:10+): >=250: 4 tok +0.17
- Size 0.25 SOL (tiers 0.25); hold median 2.0 s (p25–p75 1–3), sells median 1.0, sold everything 100%; failed attempts on unfilled launches 9
- Picks (MEASURED): serial devs (94% of picks; dev's launches in run med 13); dev buy med 4.00 SOL; bundled 65% (glued med 2.58 SOL); X link 98% / site 56%; top dev share 10% of 45 devs; busiest UTC hours 11,12,23
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: -6.1%/trade, -3.21 SOL (R1 -7.8%, R2 -2.6%); behind 2: -8.8%; behind 2 + hold 3 s: -7.1%; reactive follow (buy after its buy +1 trade, sell after its sell): -3.7%/trade
- Example: [The Zalgo](https://gmgn.ai/sol/token/CvUyHHMCPYB98RHeUxFvbRaik6qwUAi82MGW4JzC1QZE) +0.18 ([buy tx](https://solscan.io/tx/3t1s1XMNW7pTQDSMVtUa9LM7Wq7NdGxkNnL2TszQqJ6bqBWVZaUjXTq592bEMZu9535QnspjPnGkZPsNmofVNJne)); [cybercurrency](https://gmgn.ai/sol/token/HpGj8dq8UPVNBLprgNae3koUjZchh1LaXPTbAdKq9pSi) +0.15 ([buy tx](https://solscan.io/tx/4DvB8SnSEjdkMLkJeEkUaU6rV9HWXAiL4FshiusWcCsX1Fjn99TPTo9LydQjhqiEbvyZN7YdigDKcGKDjkzRnDGF))

**[G3gKCu…34uQ](https://gmgn.ai/sol/address/G3gKCu8XkjXK3zT1CEzFCsBjbuVwXa9pkjmTH5TK34uQ)** — later, 26 snipes, **+0.41 SOL** (R1 +0.02 / R2 +0.39), without best 2 +0.14, ROI +39.0%, win 50%, median token +0.001 SOL, bootstrap P(mean≤0) 0.053
- Landing (MEASURED): median slot +3 (0% in the create slot), outside buys ahead median 5 (p25–p75 2–8), arrival in our feed median 429 ms (n=2), entry price ×1.05 of the post-bundle price, fee+tip 0.61% of the buy, tips [['helius', 124], ['none', 46]]
- PnL by place: 1-3 ahead: 8 tok +0.02 · 4-10 ahead: 14 tok +0.01 · 11+ ahead: 4 tok +0.37
- PnL by arrival ms (R2 17:10+): >=250: 2 tok +0.11
- Size 0.03 SOL (tiers 0.03, 0.06, 0.02); hold median 81 s (p25–p75 62–299), sells median 0.5, sold everything 46%; failed attempts on unfilled launches 0
- Picks (MEASURED): mostly one-off devs (100%); dev buy med 0.24 SOL; bundled 100% (glued med 56.04 SOL); X link 76% / site 73%; 53% graduated; top dev share 3% of 26 devs; busiest UTC hours 16,7,12
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: -22.8%/trade, -1.48 SOL (R1 -81.2%, R2 +3.2%); behind 2: -25.2%; behind 2 + hold 3 s: +2.7%; reactive follow (buy after its buy +1 trade, sell after its sell): -32.4%/trade
- Example: [Kimchi Trading Age](https://gmgn.ai/sol/token/CQ4FfF2qkzDTuK23hpKHAgSWYAkRkmaU3yqFvjBhpump) +0.15 ([buy tx](https://solscan.io/tx/3JDmaiAdPwqXULDSVhfCktPZkcSRQhMVST269tKk8KzSyy3yqGiCts6uo4bnF4WWREiCsd2e4tyTsAPpgMbCmnBU)); [Solana Smash Bros](https://gmgn.ai/sol/token/8d3LbpJBEwcUhA5Xn2s1FUNNo2qLdzw3CQJsgtJqpump) +0.13 ([buy tx](https://solscan.io/tx/5UCYNDxqBCoYks87eCpwwEnXRxNkqaTJpzMb7MuomXnnUaJXXFp7Z9kLKXWHRxNqZZcW15b6fQoMVxFFPiyETFNq))

**[5FEM1H…ku2W](https://gmgn.ai/sol/address/5FEM1HQjVivAhvqULk1pmwa9UVwwD23JuK3nsbT5ku2W)** — later, 39 snipes, **+0.34 SOL** (R1 +0.30 / R2 +0.04), without best 2 +0.11, ROI +9.7%, win 41%, median token -0.004 SOL, bootstrap P(mean≤0) 0.09
- Landing (MEASURED): median slot +5 (0% in the create slot), outside buys ahead median 16 (p25–p75 14–19), arrival in our feed median None ms (n=0), entry price ×1.49 of the post-bundle price, fee+tip 0.60% of the buy, tips [['helius', 524], ['none', 316], ['jito', 113]]
- PnL by place: 4-10 ahead: 2 tok -0.06 · 11+ ahead: 37 tok +0.41
- PnL by arrival ms (R2 17:10+): no engine timeline overlap
- Size 0.09 SOL (tiers 0.1, 0.09, 0.11); hold median 5 s (p25–p75 3–13), sells median 1, sold everything 97%; failed attempts on unfilled launches 1
- Picks (MEASURED): serial devs (51% of picks; dev's launches in run med 3); dev buy med 2.96 SOL; bundled 66% (glued med 2.96 SOL); X link 97% / site 82%; top dev share 5% of 37 devs; busiest UTC hours 10,4,17
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: +56.8%/trade, +11.08 SOL (R1 +51.5%, R2 +63.0%); behind 2: +48.5%; behind 2 + hold 3 s: +42.5%; reactive follow (buy after its buy +1 trade, sell after its sell): +9.9%/trade
- Example: [phppad](https://gmgn.ai/sol/token/2y2BxuYLqmAb2BzWJoEhpyXFJcPDrV3CW4BMNiyWpump) +0.12 ([buy tx](https://solscan.io/tx/J6znh4y46jZwKyCraAcP2kYvMghCLf13JFHHKVeeB37rDCMFHRaA785FGcnrCfavNC6gZEhvQ3JomWgYbGPpwrx)); [yAI](https://gmgn.ai/sol/token/DoRDRa4mbjmgTpXhBentiR3HEZt17C5r5FYtyWVzpump) +0.12 ([buy tx](https://solscan.io/tx/2Y9Njb27zRzC9UqQc3wdZjR3qqWscj4tFGFaDqx1oYbEoQiEyozP8cYRMYiB9A7vQKJyGTpahtY1J95tDQkCswi9))

**[7nkYRv…nZTi](https://gmgn.ai/sol/address/7nkYRv8xScp9gjVKNNWN5XDbYsn79iWigiZYgCS8nZTi)** — later, 24 snipes, **+0.08 SOL** (R1 +0.05 / R2 +0.03), without best 2 +0.02, ROI +12.6%, win 41%, median token -0.001 SOL, bootstrap P(mean≤0) 0.067
- Landing (MEASURED): median slot +2 (0% in the create slot), outside buys ahead median 6 (p25–p75 4–8), arrival in our feed median 316 ms (n=7), entry price ×1.08 of the post-bundle price, fee+tip 0.30% of the buy, tips [['none', 441]]
- PnL by place: 1-3 ahead: 1 tok +0.02 · 4-10 ahead: 21 tok +0.07 · 11+ ahead: 2 tok -0.01
- PnL by arrival ms (R2 17:10+): 100-250: 2 tok +0.00 · >=250: 5 tok +0.04
- Size 0.03 SOL (tiers 0.03, 0.01); hold median 3.0 s (p25–p75 1–9), sells median 1.0, sold everything 100%; failed attempts on unfilled launches 2
- Picks (MEASURED): mostly one-off devs (54%); dev buy med 1.49 SOL; bundled 95% (glued med 6.12 SOL); X link 100% / site 45%; top dev share 12% of 22 devs; busiest UTC hours 1,21,6
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: +9.8%/trade, +1.18 SOL (R1 +5.8%, R2 +14.7%); behind 2: +8.3%; behind 2 + hold 3 s: -0.4%; reactive follow (buy after its buy +1 trade, sell after its sell): +4.3%/trade
- Example: [Aura Final Boss](https://gmgn.ai/sol/token/7coKdSfV6X1s936CoGtY38SDV1xK6LBgs1CSFzRkpump) +0.04 ([buy tx](https://solscan.io/tx/bxeXFG8GH9X1jjvn4x7tztWLeZoLjM8hRxCHAVxe4Hiy9NNmTJzJyFqiJAX2y5rxoyxGF53i4Xndyudzu543Ver)); [PHP3SHELL](https://gmgn.ai/sol/token/5rGn8w96mKJ7rhdnwzMjmMVGbswApcxH8aBBiobZpump) +0.02 ([buy tx](https://solscan.io/tx/3XbzgJ3KPpRyKpoEpBfBkaqeryk1o9szUfnsvk81F8ZusL7F1BxsT38NuvTtSscyd5BxG7dWmkY4buVN5vMJfqsw))

## First in line (8)

They profit by being first, which does not fit our landing. Two exceptions are worth noting:
- **dKMjeGJ4** also made +13.2 SOL on 169 tokens with 1–3 ahead. That is with its size (1.8–4.2 SOL) and its fee of about 1.1%. Our replay of its tokens at our place still loses.
- **AHwJSnFN** fills almost only when it is first. When it is not, the attempt fails (custom program error 100; INFERRED as an on-chain "abort unless first" guard).

**[dKMjeG…2CTK](https://gmgn.ai/sol/address/dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK)** — first, 492 snipes, **+45.39 SOL** (R1 +7.19 / R2 +38.20), without best 2 +28.69, ROI +2.9%, win 36%, median token -0.059 SOL, bootstrap P(mean≤0) 0.033, in CANDIDATES.md #45
- Landing (MEASURED): median slot +0 (64% in the create slot), outside buys ahead median 0 (p25–p75 0–1), arrival in our feed median 44 ms (n=181), entry price ×1.00 of the post-bundle price, fee+tip 1.09% of the buy, tips [['none', 1100], ['astralane', 606], ['jito', 465]]
- PnL by place: 0 ahead: 321 tok +36.28 · 1-3 ahead: 169 tok +13.20 · 4-10 ahead: 2 tok +0.05
- PnL by arrival ms (R2 17:10+): <25ms: 53 tok +24.96 · 25-50: 42 tok +6.77 · 50-100: 30 tok +3.25 · 100-250: 54 tok -8.54 · >=250: 2 tok -0.64
- Size 1.78 SOL (tiers 1.78, 3.56, 4.15); hold median 4.0 s (p25–p75 2–7), sells median 2.0, sold everything 99%; failed attempts on unfilled launches 189
- Picks (MEASURED): mostly one-off devs (64%); dev buy med 1.47 SOL; bundled 64% (glued med 2.82 SOL); X link 87% / site 70%; top dev share 4% of 389 devs; busiest UTC hours 23,22,16
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: -2.9%/trade, -7.16 SOL (R1 -4.0%, R2 -1.8%); behind 2: -8.3%; behind 2 + hold 3 s: -5.5%; reactive follow (buy after its buy +1 trade, sell after its sell): -10.6%/trade
- Example: [O DOT](https://gmgn.ai/sol/token/DoLPaV8VqtSxtoHprtRxsSuWjWTUvYsgF1Fcbgshpump) +8.50 ([buy tx](https://solscan.io/tx/2z77UGomh9QCv4jdjpZSFTAPq6dFMh2PSmUsrWPoihqxdMZH5JDz1f8KM64MrmFfccvUuAckd7gX3xVZe1trxXST)); [PATCHED](https://gmgn.ai/sol/token/2GEPkAjmz1gSMYxXYuLMxPviXZxRvWRHRAtfZJMWpump) +8.20 ([buy tx](https://solscan.io/tx/njAnZBmE5niKfPi1JTRdhjYc7HfyZgUvegkLPSvTLK379vnFoKWRRr5gTX9T7WorRJntpEC9TmQAP1Hjc7Loscp))

**[AHwJSn…paN2](https://gmgn.ai/sol/address/AHwJSnFNUiAU9FfT5ewW2osqMo938WtL7KhfsJyfpaN2)** — first, 382 snipes, **+10.78 SOL** (R1 +6.25 / R2 +4.52), without best 2 +5.55, ROI +3.8%, win 39%, median token -0.008 SOL, bootstrap P(mean≤0) 0.013, in CANDIDATES.md #56
- Landing (MEASURED): median slot +0 (64% in the create slot), outside buys ahead median 0 (p25–p75 0–0), arrival in our feed median 44 ms (n=140), entry price ×1.00 of the post-bundle price, fee+tip 0.38% of the buy, tips [['helius', 374], ['nozomi', 141], ['jito', 105]]
- PnL by place: 0 ahead: 380 tok +10.70 · 1-3 ahead: 2 tok +0.09
- PnL by arrival ms (R2 17:10+): <25ms: 21 tok +0.60 · 25-50: 54 tok -1.25 · 50-100: 16 tok +0.77 · 100-250: 45 tok +1.57 · >=250: 4 tok +0.97
- Size 0.59 SOL (tiers 0.59, 0.4, 0.89); hold median 2.0 s (p25–p75 1–2), sells median 1.0, sold everything 100%; failed attempts on unfilled launches 1079
- Picks (MEASURED): serial devs (83% of picks; dev's launches in run med 31); dev buy med 3.00 SOL; bundled 81% (glued med 3.35 SOL); X link 97% / site 73%; top dev share 12% of 144 devs; busiest UTC hours 22,23,16
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: -5.3%/trade, -10.15 SOL (R1 -3.7%, R2 -7.0%); behind 2: -6.0%; behind 2 + hold 3 s: -3.6%; reactive follow (buy after its buy +1 trade, sell after its sell): -6.2%/trade
- Example: [cybercurrency](https://gmgn.ai/sol/token/CzDuFrKNEkhN2LJkxijJ5SHFwSaRT4FqPMmDnYPdpump) +3.72 ([buy tx](https://solscan.io/tx/2uGSx8PAGFhNjeF9HAW7MXRgcSymJSwDVem5MGR2qBEJo51GZV9wJTJrerUzmqDBrrtqhJEwv6QVyJt2szfKPvgn)); [PUMPVENGERS](https://gmgn.ai/sol/token/EXjfLwy1YETWwP69hS1s8gCux1gpmGLkf9bPXN37pump) +1.51 ([buy tx](https://solscan.io/tx/2DjMNPSJjVaJw1hDJLiwXQtA84ePyLvy5PL9y4nTpGLQG8exzHnuoKVZZKLriLzituzeBsgJYNBvyruxDiHHc5tj))

**[2uoELA…qmdE](https://gmgn.ai/sol/address/2uoELAUQCQ4Amkdui8piryp2nAf9woYJtJc5Hr64qmdE)** — first, 29 snipes, **+8.51 SOL** (R1 +5.59 / R2 +2.93), without best 2 +2.60, ROI +15.6%, win 34%, median token -0.087 SOL, bootstrap P(mean≤0) 0.023
- Landing (MEASURED): median slot +0 (72% in the create slot), outside buys ahead median 0 (p25–p75 0–1), arrival in our feed median 81 ms (n=9), entry price ×1.00 of the post-bundle price, fee+tip 0.15% of the buy, tips [['helius', 84], ['none', 71]]
- PnL by place: 0 ahead: 16 tok +4.45 · 1-3 ahead: 11 tok +1.31 · 4-10 ahead: 2 tok +2.91
- PnL by arrival ms (R2 17:10+): 25-50: 4 tok +3.34 · 50-100: 1 tok +0.04 · 100-250: 3 tok -0.21 · >=250: 1 tok -0.08
- Size 1.86 SOL (tiers 1.88, 1.86, 1.83); hold median 274 s (p25–p75 272–333), sells median 1, sold everything 100%; failed attempts on unfilled launches 67
- Picks (MEASURED): mostly one-off devs (65%); dev buy med 0.49 SOL; bundled 13% (glued med 0.00 SOL); X link 48% / site 37%; top dev share 10% of 26 devs; busiest UTC hours 1,10,4
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: +6.2%/trade, +0.90 SOL (R1 +7.7%, R2 +3.4%); behind 2: +2.7%; behind 2 + hold 3 s: +1.7%; reactive follow (buy after its buy +1 trade, sell after its sell): -1.5%/trade
- Example: [guld](https://gmgn.ai/sol/token/AkSZuXdmCYfJh4uJZNi5mYxYx47K8E77MgmCwEAqpump) +3.07 ([buy tx](https://solscan.io/tx/51SGqhYk4TtY8CmULwgCXTaxHaQRTpPV2A6LaNRVafHB3UmCqEUevvqsEMHUCtLwn6KNrguF8TfqsidNaztA5QXu)); [404coin](https://gmgn.ai/sol/token/5QXjDZmp43Zr6WYcxb1ExgqtFsDn4S866i5PYPSJpump) +2.85 ([buy tx](https://solscan.io/tx/4ioiDQCPkqLU97MiLouyG8ikdKT2rpaBX5NhN92SvfLrvHEGbbTVNinvgXHc3cjxhBJDMeQzKhR9BvHfx4UBCY6N))

**[EP51o5…KPYE](https://gmgn.ai/sol/address/EP51o5QPpbAJbTqbHiK5PFjLwpgemmcn4kZPHQJXKPYE)** — first, 19 snipes, **+8.51 SOL** (R1 +6.19 / R2 +2.32), without best 2 +2.22, ROI +11.0%, win 47%, median token -0.063 SOL, bootstrap P(mean≤0) 0.02
- Landing (MEASURED): median slot +0 (68% in the create slot), outside buys ahead median 0 (p25–p75 0–0), arrival in our feed median 124 ms (n=3), entry price ×1.00 of the post-bundle price, fee+tip 3.82% of the buy, tips [['astralane', 89], ['landx', 39], ['0slot', 10]]
- PnL by place: 0 ahead: 19 tok +8.65
- PnL by arrival ms (R2 17:10+): <25ms: 1 tok +3.73 · 100-250: 2 tok -0.93
- Size 3.46 SOL (tiers 3.46, 4.94, 3.95); hold median 58 s (p25–p75 7–106), sells median 3, sold everything 100%; failed attempts on unfilled launches 45
- Picks (MEASURED): serial devs (78% of picks; dev's launches in run med 8); dev buy med 2.00 SOL; bundled 42% (glued med 0.00 SOL); X link 100% / site 31%; top dev share 31% of 10 devs; busiest UTC hours 22,9,10
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: -7.0%/trade, -0.67 SOL (R1 -7.5%, R2 -5.0%); behind 2: -11.4%; behind 2 + hold 3 s: -3.2%; reactive follow (buy after its buy +1 trade, sell after its sell): -11.4%/trade
- Example: [Vice Coin](https://gmgn.ai/sol/token/Gav7NgEG2kpQpYKT2mWy25HX7rxsbdG8jJfKsTCUpump) +3.73 ([buy tx](https://solscan.io/tx/4p1SLo6S6uAAyjJeGPtgH7MdwWWm9xiubhPbYH59zXZsmSyWdmDbBN6DcBEYfkfQPZTggocBzzxHeHYofM4YhM66)); [rektoff.xyz](https://gmgn.ai/sol/token/7GwgGCWu34gCz8YUXSN5oQVxz3jMj6k5qCGGcuRUpump) +2.55 ([buy tx](https://solscan.io/tx/mcuY9gkDGbXMMuCgoT2D5yPp4Xmza4VhTMw4A6fjqacAL5S4mTBiJmhU6hwuTNH2CQT3tYvfWQ4VCHhgPGqJkJX))

**[A9X9Ag…zkdV](https://gmgn.ai/sol/address/A9X9AgTwXACgp9UbdjhUPyq15rFPdDBzkD3NHu6YzkdV)** — first, 37 snipes, **+6.28 SOL** (R1 +3.62 / R2 +2.67), without best 2 +0.99, ROI +5.1%, win 56%, median token +0.164 SOL, bootstrap P(mean≤0) 0.15
- Landing (MEASURED): median slot +0 (89% in the create slot), outside buys ahead median 0 (p25–p75 0–0), arrival in our feed median 31 ms (n=6), entry price ×1.00 of the post-bundle price, fee+tip 1.01% of the buy, tips [['none', 116], ['other', 28], ['stellium', 5]]
- PnL by place: 0 ahead: 35 tok +8.96 · 1-3 ahead: 2 tok -0.74
- PnL by arrival ms (R2 17:10+): <25ms: 2 tok -0.73 · 25-50: 2 tok +0.34 · 50-100: 1 tok -0.12 · 100-250: 1 tok +0.49
- Size 2.96 SOL (tiers 1.78, 2.96, 5.73); hold median 1 s (p25–p75 1–3), sells median 1, sold everything 100%; failed attempts on unfilled launches 32
- Picks (MEASURED): serial devs (94% of picks; dev's launches in run med 23); dev buy med 3.00 SOL; bundled 97% (glued med 4.20 SOL); X link 97% / site 59%; top dev share 43% of 5 devs; busiest UTC hours 3,4,2
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: -9.5%/trade, -1.76 SOL (R1 -11.2%, R2 -5.0%); behind 2: -13.2%; behind 2 + hold 3 s: -11.5%; reactive follow (buy after its buy +1 trade, sell after its sell): -13.6%/trade
- Example: [cybercurrency](https://gmgn.ai/sol/token/CMo7GfUhSGXuEfnY7qAzv8hhsV2M2P8GpWqmWikhpump) +2.98 ([buy tx](https://solscan.io/tx/35bShtL7rPNhu5aQsNUYiJ6Rx4JEZFhp8bW9DUoM3NzR816mRukAPLR9GTkMBz5DamcxDyB2Xaf3i4f9TDVgvNNY)); [Agent-5](https://gmgn.ai/sol/token/H5v2UAQcijtD4k3g5adPcbsxQkPJ93CPcZSewa5spump) +2.31 ([buy tx](https://solscan.io/tx/d8W4xuFBZtiPm9yEpaetgmtJVgvX8eARpUuxiquDd4tNJ88rKSQCJvwsBsxbWjZqKmorsRdBTuaom8porbyYotb))

**[6fg6aU…M3Pt](https://gmgn.ai/sol/address/6fg6aUUQ3ZcYnLa2BcddTk6JdERCs2ZpRdNKLrMEM3Pt)** — first, 37 snipes, **+4.80 SOL** (R1 +0.36 / R2 +4.44), without best 2 +1.90, ROI +5.8%, win 59%, median token +0.040 SOL, bootstrap P(mean≤0) 0.023
- Landing (MEASURED): median slot +0 (73% in the create slot), outside buys ahead median 0 (p25–p75 0–0), arrival in our feed median 27 ms (n=13), entry price ×1.00 of the post-bundle price, fee+tip 2.77% of the buy, tips [['astralane', 118], ['landx', 68], ['0slot', 23]]
- PnL by place: 0 ahead: 31 tok +5.04 · 1-3 ahead: 6 tok -0.02
- PnL by arrival ms (R2 17:10+): <25ms: 6 tok +1.13 · 25-50: 4 tok +0.06 · 100-250: 3 tok +0.60
- Size 2.17 SOL (tiers 2.17, 2.96, 2.44); hold median 7 s (p25–p75 3–12), sells median 3, sold everything 100%; failed attempts on unfilled launches 64
- Picks (MEASURED): serial devs (94% of picks; dev's launches in run med 20); dev buy med 2.96 SOL; bundled 70% (glued med 3.75 SOL); X link 91% / site 64%; top dev share 18% of 15 devs; busiest UTC hours 3,1,20
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: +1.5%/trade, +0.28 SOL (R1 -1.6%, R2 +4.5%); behind 2: -5.1%; behind 2 + hold 3 s: +0.6%; reactive follow (buy after its buy +1 trade, sell after its sell): -5.8%/trade
- Example: [X67 Inc.](https://gmgn.ai/sol/token/DQuhqy5wX3fwezxuJJ47RG17N9pdnZbABfHGEZk1pump) +1.91 ([buy tx](https://solscan.io/tx/3yP2EJNng2yrCF1RvHRgKAak3AQkiRiPinLBpHAgLyr6XSpmd93TiECNxhbMH2o6PVfcLGojhnWnfGBbUBVP9PDK)); [catdog](https://gmgn.ai/sol/token/CRMGiMh1qQ9Mw69S2XtUSDeYvgYg9PGwC1wTytavpump) +0.99 ([buy tx](https://solscan.io/tx/5s4mc72ow2XCj7z6P3pPSW65yfoYcqKJfSLWxYZFpnfYaBnEpoPD3EUwsdyhan3SiuZLSArGqdiiQ9uZb67fACWh))

**[54YNHF…Vd43](https://gmgn.ai/sol/address/54YNHFVt3VwxMpmfiqMmYCFTJkSyCNDX7sx9RcRGVd43)** — first, 66 snipes, **+3.13 SOL** (R1 +0.93 / R2 +2.19), without best 2 +0.08, ROI +2.9%, win 36%, median token -0.032 SOL, bootstrap P(mean≤0) 0.123, in CANDIDATES.md #14
- Landing (MEASURED): median slot +0 (69% in the create slot), outside buys ahead median 0 (p25–p75 0–1), arrival in our feed median 52 ms (n=27), entry price ×1.00 of the post-bundle price, fee+tip 0.92% of the buy, tips [['helius', 40], ['astralane', 29], ['none', 22]]
- PnL by place: 0 ahead: 43 tok +1.98 · 1-3 ahead: 22 tok +1.17 · 4-10 ahead: 1 tok +0.26
- PnL by arrival ms (R2 17:10+): <25ms: 8 tok +0.73 · 25-50: 4 tok +1.06 · 50-100: 5 tok +0.21 · 100-250: 10 tok +0.09
- Size 1.58 SOL (tiers 1.58, 1.48, 1.98); hold median 1.0 s (p25–p75 0–1), sells median 1.0, sold everything 100%; failed attempts on unfilled launches 24
- Picks (MEASURED): mostly one-off devs (87%); dev buy med 0.99 SOL; bundled 48% (glued med 0.00 SOL); X link 92% / site 84%; top dev share 3% of 64 devs; busiest UTC hours 22,2,21
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: -3.0%/trade, -0.99 SOL (R1 -4.7%, R2 -1.7%); behind 2: -6.1%; behind 2 + hold 3 s: -6.2%; reactive follow (buy after its buy +1 trade, sell after its sell): -8.9%/trade
- Example: [Particle Quant](https://gmgn.ai/sol/token/D9aBM9VghfLVHjY4sA8P4LsRZDkQDiQtVuhFPtyUpump) +1.78 ([buy tx](https://solscan.io/tx/3DRxraixHVnUxWF6EirbTGaL6vzFosGFyfmm16shygTTAsNqKVa48F7qk9CxQXQqLL7uf9sSVs8jPdV9KwxjZ1a8)); [Zilk Pill](https://gmgn.ai/sol/token/3KppnhX8einBVyZwTFGR6gFbDGaEwvniqPeudDB4pump) +1.27 ([buy tx](https://solscan.io/tx/5DLbhU3Q4suwDqT8sHnAb6sLYGT8xifBmKACsd7TbCN3vNLnusC7PmSBvW4V2dCtHHdQ3t8zPmrUo5ug6GXcjg91))

**[EQcoyT…XJMy](https://gmgn.ai/sol/address/EQcoyTSPfbPj9nCuNByUQPTF16eC85S2KhmLpY7hXJMy)** — first, 15 snipes, **+0.13 SOL** (R1 -0.03 / R2 +0.16), without best 2 +0.03, ROI +8.4%, win 46%, median token -0.002 SOL, bootstrap P(mean≤0) 0.02
- Landing (MEASURED): median slot +0 (93% in the create slot), outside buys ahead median 0 (p25–p75 0–1), arrival in our feed median 39 ms (n=11), entry price ×1.00 of the post-bundle price, fee+tip 1.54% of the buy, tips [['none', 15], ['nozomi', 6], ['astralane', 5]]
- PnL by place: 0 ahead: 8 tok +0.07 · 1-3 ahead: 7 tok +0.06
- PnL by arrival ms (R2 17:10+): <25ms: 1 tok +0.02 · 25-50: 6 tok +0.10 · 50-100: 2 tok +0.01 · 100-250: 2 tok +0.03
- Size 0.10 SOL (tiers 0.1); hold median 61 s (p25–p75 10–61), sells median 1, sold everything 100%; failed attempts on unfilled launches 3
- Picks (MEASURED): mostly one-off devs (86%); dev buy med 0.99 SOL; bundled 13% (glued med 0.00 SOL); X link 73% / site 80%; top dev share 6% of 15 devs; busiest UTC hours 17,21,12
- Copy test at OUR place (paper, 0.5 SOL, 0.015 SOL cost): same tokens behind 1 outside trade, sell after its first sell: +10.8%/trade, +0.81 SOL (R1 -6.0%, R2 +15.0%); behind 2: +9.2%; behind 2 + hold 3 s: +5.6%; reactive follow (buy after its buy +1 trade, sell after its sell): +8.7%/trade
- Example: [Zilk Pill](https://gmgn.ai/sol/token/3KppnhX8einBVyZwTFGR6gFbDGaEwvniqPeudDB4pump) +0.07 ([buy tx](https://solscan.io/tx/3Wj2hbV423x56u1dPvWJuo4yRGvcNeRwgWDfaEi9w8f8NBfYTWT9U1z5b5qcyLtNTQhkxkmvArgwMXoYLjs7oxse)); [Dispatch](https://gmgn.ai/sol/token/3N6gEuYWREH5qWnfYd6jNsd2duvQNkKG8bvvVdxFpump) +0.03 ([buy tx](https://solscan.io/tx/3iZb4gSGTPDFrAe26L7HWAtex9rkNNdr5qRRGJ3etvjxN9TuZTMUgkYXSRSnxL5a1gJ5Y8xizvpCV8fhe8JvJrQF))

## Focus wallets (AKbot users)

- [9Sh2fd…NYa1](https://gmgn.ai/sol/address/9Sh2fdqMQcec7W9LzzfvkYphrdyR3S8aUBsKdv9xNYa1): 41 snipes, **-1.33 SOL** (R1 +3.11/5, R2 -4.45/36), without best 2 -4.66, ROI -1.2%, failed-attempt fees 0.385 SOL, landing slot +0 / ahead 0 / 40 ms, size 2.96 SOL, hold 7 s, sells 3
- [DGmspi…1NR3](https://gmgn.ai/sol/address/DGmspiBs2ePJ7WgN1pyX5RJDpzhyxYrBN1P4bXNC1NR3): 50 snipes, **-0.75 SOL** (R1 +0.82/29, R2 -1.57/21), without best 2 -4.43, ROI -0.7%, failed-attempt fees 0.295 SOL, landing slot +0 / ahead 0 / 49 ms, size 1.63 SOL, hold 18.0 s, sells 2.0
- [D24ipY…JCwQ](https://gmgn.ai/sol/address/D24ipYXuDt6PXEPV6rZqfWb35WJaTJW3gDoXwt7yJCwQ): 159 snipes, **-8.59 SOL** (R1 -1.15/113, R2 -7.44/46), without best 2 -11.01, ROI -3.7%, failed-attempt fees 0.481 SOL, landing slot +0 / ahead 0 / 45 ms, size 0.98 SOL, hold 13 s, sells 2

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
