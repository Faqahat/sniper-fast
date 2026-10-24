# CWiNFA: full dissection (2026-10-23, read-only, times in PKT = UTC+5)

Wallet [CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J](https://gmgn.ai/sol/address/CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J) ([Solscan](https://solscan.io/account/CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J)). The page with its last 15 snipes is [CWiNFA_snipes.html](CWiNFA_snipes.html).

Nothing was sent, traded or changed on any server. Each claim is labelled **MEASURED** (read from chain or our data) or **INFERRED** (my reading of it).

## Verdict

**What it is.** A private, self-built pump.fun sniper, not a commercial bot.
- Every trade goes through its own router, which nobody else used in the last 61 h. The router's upgrade key also owns the wallet's lookup table. There is no bot fee (**MEASURED**). "Self-built" is **INFERRED** from these facts.
- The recipe never changes (**MEASURED**):
  - buy exactly 1 SOL;
  - pay 0.6% to land: 0.003 SOL priority fee plus a 0.003 SOL tip to one of about 10 services, signed with durable nonces;
  - loose buy guard: the buy fails only above about 1.37× the post-bundle price;
  - one sell with no price guard.

**Exits (MEASURED).**
- Normally about 1.5 s after the buy.
- In the same slot when the dev or bundle sells.
- An urgent take-profit at about 1.3–1.5× its entry.

**Profit (MEASURED).**
- **+14.93 SOL after every cost**, 10-20 18:19 → 10-23 07:26 PKT (61.1 h). That is about **+5.9 SOL/day** on 1,312 round trips.
- Win rate 37.7%. +13.2 SOL without its best two tokens.

**Edge (MEASURED).**
- Being first in line: +7.31 SOL with no outside buy ahead, −2.27 with one or more ahead.
- Take-profit sells: +17.6 SOL.
- Selection: its picks rise more than comparable launches over 2–10 s, even with every fast bot removed.

**For us, under the owner's generic-flow rule:**
- The quick-sell copy, of its picks or its deployer list, is **rejected: it depends on CWiNFA and the fast sniper wallets**.
- A 10 s hold on its list makes money on generic flow in the newer run only. **Unproven**; paper candidate.

## 1. Infrastructure / bot identity

**Router (MEASURED).**
- Program [5DVzy5EpG2xVxrwwuyZPDe9EpraUnGh7ZgYABwizzNVu](https://solscan.io/account/5DVzy5EpG2xVxrwwuyZPDe9EpraUnGh7ZgYABwizzNVu):
  - upgradeable; program data at [AccV4tBc…w2aH](https://solscan.io/account/AccV4tBcWRMPzbKJpDd8JbcN5JwK1YngF9mMYWqUw2aH);
  - upgrade authority [A5GQaNc37XMKPhn1hbzc12cvBaXj7Uk1qNmMeS9pRfAz](https://solscan.io/account/A5GQaNc37XMKPhn1hbzc12cvBaXj7Uk1qNmMeS9pRfAz).
- Router traffic in the window: 2,710 signatures. CWiNFA's own ledger has 2,708 router txs, and all 60 sampled router txs were paid by CWiNFA.
- Lookup table [B73XBTEm…xAgv](https://solscan.io/account/B73XBTEmKwFGR7uu8s3NtHKiQoYPsF2rYHJB87NwxAgv) (86 addresses) has the same authority, A5GQ.
- A5GQ wrote program buffers on 10-08 15:56–15:58 PKT (router deploy or upgrade, **INFERRED**).
- No fee transfer to any bot wallet, inside the trades or separately.

**Buys: 1,312 landed (MEASURED).**
1. **Durable nonce:** `advanceNonce` on one of **30 nonce accounts**, all with the wallet as authority (e.g. [HeFPFRBK…](https://solscan.io/account/HeFPFRBKPohPsekcqcw89q1sKUcBbdJFnmn7yikvTWQc), [AAW6kUA6…](https://solscan.io/account/AAW6kUA679zmCbh3HQXBkoGCmEtG8QC6nnBRmqyG8DEX)). 100% of buys and sells use a nonce.
2. **Compute budget:**
   - v0 copies (873 of the 1,312 landed buys) use the lookup table and three compute-budget instructions: 80,000 CU at 37.44 M µ-lamports, i.e. 0.0030002 SOL total fee.
   - v1 copies (439) pay the identical fee, set in the transaction header.
3. **Router instruction:** `0x02` | amount in = 1,000,000,000 lamports | min tokens out | 8-byte seed (the first 8 characters of the mint).
   - Inside: `createAccountWithSeed` + `InitializeAccount3` (Token-2022) + pump.fun `BuyExactQuoteInV3`.
   - Every buy spends exactly 1.000 SOL. Median 58,803 CU.
4. **Tip:** exactly one 0.003 SOL transfer per landed tx.

| Landing service | Landed buys |
|---|---|
| Nozomi | 319 (24%) |
| Astralane | 261 (20%) |
| Flashblock | 243 (19%) |
| Helius | 240 (18%) |
| Stellium | 95 (7%) |
| Jito | 85 (6%) |
| NextBlock | 10 |
| bloXroute | 5 |
| 2 unlabelled accounts, [tKq5esiQ…](https://solscan.io/account/tKq5esiQyvgRyfFa4JEz4uAUmppKyKB1PiQD9JhyGJY) (31) and [D1Mc6j9x…](https://solscan.io/account/D1Mc6j9xQWgR1o1Z7yU5nVVXFQiAYx7FG9AW1aVfwrUM) (23) | 54 (same 0.003 / 0.0011 / 0.0015 amounts, so almost surely tip accounts, **INFERRED**) |

- Examples: [v0 buy](https://solscan.io/tx/55Mo653YQyMEdtYz17ghxNW3nTthTrRt5o2nLmKaYz84Twv9UunkmNLnL2muvyUGg4d1SfXJpVM3dFut4Smasimf), [v1 buy](https://solscan.io/tx/3ZsRDQasFqFMndKx6AB9c8Q9Nx2NgApouULwt3ueUQd9qgficK9pwCS6HwyQTmNLvxNxchvE9sCVRMi7yAREvESr).

**Copies per buy (INFERRED).**
- MEASURED facts: one tip per tx; landed buys spread over about 10 services and both tx versions; never two buys on one token; no failed duplicate buy copies.
- So it most likely signs one copy per service, all bound to the same nonce, and the first to land cancels the rest.
- Losing copies never appear on chain, so the number of copies cannot be measured.

**Sells (MEASURED).**
- Router instruction `0x03` | all tokens | **min SOL out = 1 lamport (no guard)** | an unidentified 32-byte value | 3 flag bytes, calling pump.fun `SellV3`.
- Normal sell: 75,000 CU at 27,000 µ-lamports, fee 0.000007 SOL plus a 0.0011 SOL tip (1,091 sells). Example: [normal sell](https://solscan.io/tx/5Z6XZPZKKKCGDik3ZM5fF8zqo37uJA2wyMx5XgKT4hBwGpsL33mf4sPFr7uDwoqTzicMrw1cYCLk6ZE69u8Uc7MT).
- Urgent sell: 0.000545 SOL fee plus a 0.0015 SOL tip (221 sells). Examples: [after a dev sell](https://solscan.io/tx/48bcuaCSjf2oWCb448JeQwpjVoj4CRkKL37bKSvZqiPWPcdDdmKRkcGqQHbmkqTMsQTSSGjHvF2H5xUAsd2ys2Ny), [take-profit](https://solscan.io/tx/4XiXFaYxtWRweJKhZNw5KYST7DUpHQtDPB1ahjrCjzMHa6UC22vCK2BT8Ln9yNDCcxABmsUbNFizxPhFpkuVcVr7).

**Price guard (MEASURED).**
- Min tokens out ≈ 0.726 × the tokens 1 SOL would buy at the post-bundle price (p5 0.63, p95 0.76).
- All 27 failed buys we can place in our blocks hit `BuySlippageBelowMinTokensOut`. The price just before them was ≥1.375× the post-bundle price (p10), median 1.48×.
- Filled buys met a median 1.016× (p90 1.21×).
- So the guard is not tight. It fills late rather than failing: 63 of 1,385 buy attempts (4.5%) failed on slippage. Example: [failed buy](https://solscan.io/tx/4GRbVusUQUFhzZvAUDjsPjGxjWzqGBPTUGRZUMk572xrz66eUvxDSR6XJRPv1Z6TsgVo8XxNqsZc9W2vWM68WBmA).

**Other transactions (MEASURED).**
- 321 batch account-close txs reclaim the 0.00203928 SOL rent per buy, +2.68 SOL in total ([example](https://solscan.io/tx/41ACprXhkRp8k8oDwVaj7Pyw89PgkamWNPUtnWoXRPADoJQkJPYQj7aAB74EnJT1fs7ZFHm4xQdrvTBhH84BBzn9)).
- 125 nonce-only txs, never next to a buy ([example](https://solscan.io/tx/x1QVnntw2NmuiNUuDxcZyaDLKbm11UPZvGFJof6aJWNgMtLB4r3jD43F6xh8thFfk4PHTXoY3hPPjpUkkrBJd4Y)). They come in bursts: 10-20 23:00 to 10-21 00:00 (45), 10-22 12:00 (10), 10-23 00:00–02:00 (70). This looks like re-advancing all nonces on restart (**INFERRED**), not a guard.

**Compared with 9Sh2fd's AKbot (MEASURED for both).**

| | CWiNFA | 9Sh2fd (AKbot) |
|---|---|---|
| Bot fee | none | 1% per trade, paid separately |
| Landing | 0.003 SOL priority + 0.003 SOL tip, about 10 services | 0.0025–0.005 SOL priority + LandX-only tip (~2%) |
| Tx format | v0 + lookup table and v1 copies; own router for every trade | v1; calls pump.fun directly |
| Size | always 1 SOL | 1.78 / 2.96 SOL |
| Exits | one sell | 2–11 sells |

Both use durable nonces and seed-based token accounts, a common fast-bot toolkit (**INFERRED**).

## 2. Profit (ground truth)

**Ledger (MEASURED).**
- All 3,225 txs the owner's RPC holds: slots 459,244,317 → 460,272,360, 0 missing.
- 1,312 buys, 1,312 sells, 73 failed buys, 11 failed sells, 354 account-close txs, 125 nonce-only, 32 stablecoin txs, 6 dust txs in.

**Two methods agree (MEASURED).**
- **Balance:** 24.664 → 22.108 SOL (−2.556). No SOL was deposited or withdrawn. 17.488 SOL left as stablecoins (see section 3). −2.556 + 17.488 = **+14.932**.
- **Parts:** trading +12.470, rent refunds +2.683, failed-tx fees −0.221, nonce-only txs −0.0006. Total **+14.932**.

**Costs over 1,312 round trips (MEASURED).**

| Item | SOL |
|---|---|
| Curve result before any fee | +57.80 |
| pump.fun fees | −33.12 |
| Tips | −5.47 |
| Network fees | −4.06 |
| Failed-tx fees | −0.22 |
| Bot fee | 0 |
| Net | +14.93 |

**Per day, PKT (MEASURED).**

| Day | Profit (SOL) | Buys | Withdrawn as stablecoins (SOL) |
|---|---|---|---|
| 10-20 (from 18:19) | +0.70 | 147 | 1.6 |
| 10-21 | +7.93 | 527 | 6.19 |
| 10-22 | +7.35 | 470 | 9.70 |
| 10-23 (to 07:26) | −1.05 | 168 | 0 |

**By period, per-token PnL (MEASURED).**

| Period (PKT) | Tokens | PnL (SOL) |
|---|---|---|
| Before R1 | 723 | +8.64 |
| R1 (10-22 03:07 → 18:00) | 274 | +4.10 |
| Gap | 71 | +1.30 |
| R2 (10-22 20:43 → 10-23 05:35) | 195 | +1.55 |
| After R2 | 49 | −0.45 |

**Per token (MEASURED).**
- Mean +0.0115 SOL, median −0.0169. Best +0.958, worst −0.484.
- Tokens at ≥ +0.10 SOL: 210 tokens, +50.5 SOL. Tokens at ≤ −0.03 SOL: 484 tokens, −41.2 SOL.

**Venue (MEASURED).**
- 100% pump.fun bonding curve, SOL-quoted.
- No AMM trades, USDC-quoted tokens or mayhem launches.
- Its only other swaps convert SOL to stablecoins, via Jupiter, DFlow and the RFQ program 61DFfeTK…TpYH.
- 22.108 SOL held now; no open positions.

## 3. Funding and relations

**Wallet age (MEASURED, public RPC).**
- First tx 07-03 14:46 PKT: 66,341 txs before the owner's RPC horizon.
- First funding: 1.99 SOL on **07-22 02:03 PKT** from [iGdFcQoyR2MwbXMHQskhmNsqddZ6rinsipHc4TNSdwu](https://solscan.io/account/iGdFcQoyR2MwbXMHQskhmNsqddZ6rinsipHc4TNSdwu) ([tx](https://solscan.io/tx/4zUWPXYXRVGqfPt4uMNtoK1i6SVkPnEXEFSHpcSJH9hL8wyuex3g1ojRbLJfsHzjWiQCgxSUJjiUxpuhtC9vmpm9)). That address does about 208 txs/h, so it looks like an exchange-style hot wallet (**INFERRED**).
- History after funding:
  - July: ordinary Raydium swaps.
  - From 08-22: direct pump.fun buys with tips.
  - From at least 09-26: the same router.
- Its balance moved between 5 and 49 SOL across September–October, so there were more deposits and withdrawals than this window shows; the full older ledger was not fetched.

**Money out in the window (MEASURED).** Stablecoins only, no SOL. It swapped 0.6 / 1.0 / 1.18 / 5.0 / 8.0 / 1.7 SOL into stablecoins ([8 SOL → 835 USDT](https://solscan.io/tx/3jrBVXX6wYeuT9vZRR7Tmj8cPpwTM2DWS3vBSFieJa36CAQBmhGCe5MsmsKErGvZksMrWpiPsSw188V57WPpQY64)), then sent:
- **449.53 USDC** in 3 transfers to [AguYev2TP6npfnkPHKoEVaXnDxZs5PYoaJxM4t4rHB32](https://solscan.io/account/AguYev2TP6npfnkPHKoEVaXnDxZs5PYoaJxM4t4rHB32) ([1](https://solscan.io/tx/2THCmsUmhousLGHtbsnmswmoEB9ybMoiZRMN4G29M1fvfPhSukA2AJD6YYEv66VrrsAo2K4oMF3FoHuEU1JZpTkk), [2](https://solscan.io/tx/JjhEBwTPWSx43r5RqpS8yf5s33a1eAovBqgnruSeNguX5uzxxv8Dd4bCRXqaGStRAHVhZoCKKYgBAWDxcdYEmhG), [3](https://solscan.io/tx/5bWmcGXWoJGYq5aQgpQsi3a5fMGa3ikenqxe9R4MBu5B9MTKSDYxfJhGhbrKSMxq8hUFpb3NxNDaN6fsb2UrZbAD)).
- **1,368.46 USDT** in 2 transfers to [9fufb3TE9LrXdQpbHzTFCWMpkWeW6P4njL62FFCzALiW](https://solscan.io/account/9fufb3TE9LrXdQpbHzTFCWMpkWeW6P4njL62FFCzALiW) ([1](https://solscan.io/tx/5VQmxMXxwsznUfcJRDmGGzeVE2mkQPxEQL2c66eEDq4Xt7uVaBGaZQk6CYcPyLPZQSeE8A441DPDevdcSNmDrSSo), [2](https://solscan.io/tx/5tsPndZ9aKG9DqoUKMSrikxXQ2VYhffe5LYrCfXYza8tK81SeEjXedU2sgUWixLFEv585qpTd1wk62gFhwv55DSp)).
- Both destinations are low-activity, so they look like personal or exchange-deposit addresses (**INFERRED**).
- **25 + 105 USDC** with memos `pi_ePWfW4P7aq4xWAX2` and `pi_VDPDs9GSG7ZJ95cQ` to [CEs84tEowsXpH8u4VBf8rJSVgSRypFMfXw9CpGRtQgb6](https://solscan.io/account/CEs84tEowsXpH8u4VBf8rJSVgSRypFMfXw9CpGRtQgb6) ([1](https://solscan.io/tx/4rQZRAYErgkYMhR1WbeBtgdEmrj4fgMPie4FL8uViuCQUMgZG5R1gPKUXYcLpAix6hfmHLF4BmwHYfAnFkJUeFhh), [2](https://solscan.io/tx/5v6CBKuCKE95yxknoxsrwUac3j14rWjWYPQ9Ktbikh5pGxENkLC6HY8zoAXEScHCj6JoojUrQaqNDG3vSJyNJQhA)). `pi_` is Stripe's payment-intent format, so these look like payments to a merchant, possibly an infrastructure subscription (**INFERRED**).
- Look-alike dust (address poisoning) followed each withdrawal (MEASURED). This confirms AguYev2T and 9fufb3TE are its regular destinations (**INFERRED**).

**Linked key A5GQaNc3 (MEASURED).**
- It is the router's upgrade authority and the lookup table's authority.
- It has more than 20,000 txs, 94% of them failed.
- From 08-23 to 08-31 PKT it sent trading txs through an older router, [FxbKFRYxhWRwHjYJqSyVwCYRk8UMRaPuYU7VxWemSnxG](https://solscan.io/account/FxbKFRYxhWRwHjYJqSyVwCYRk8UMRaPuYU7VxWemSnxG) (`ExecuteRoute`). Those txs paid the same tip accounts CWiNFA uses now: the Helius accounts, D1Mc6j9x and tKq5esiQ.
- On 10-18 15:19 PKT it sent 0.2286 SOL to [3E43HEFeYChueMZxk68qsW8qgB4PAndm7mfBKUB5tjHv](https://solscan.io/account/3E43HEFeYChueMZxk68qsW8qgB4PAndm7mfBKUB5tjHv) ([tx](https://solscan.io/tx/3HhMXuXbHfhmx6K1TAqenf4vqDQiaxHDVK4SfzenTbrzURuKMcUnymEEgvajdzvzZvssbX7xACVRqjWCeqUnHgXG)).
- Reading: this is the developer's key, used for an earlier version of the same bot (**INFERRED**).

**Cluster (MEASURED).**
- No other wallet uses the router.
- No shared funder or deposit address with 9Sh2fd, DGmspi or D24ipY.

## 4. Selection

**Data.** 27,603 SOL-quoted, non-mayhem launches; CWiNFA attempted 488 (1.8%). The predictors below use **create-time features only** (MEASURED).

**Dev buy and bundle.**
- Attempt rate by dev buy: none 0%, 0.5–1.5 SOL 3.2%, 2.5–3.5 SOL 6.5%, 3.5–5 SOL 7.7%.
- With a 3-wallet glued bundle: 8.3%.
- The rule "dev buy ≥1 SOL plus a bundle" covers 60% of its attempts at 7.3% precision.

**Launcher.** J7Tracker accounts for 53% of attempts (2.9% of its launches), Uxento 19% (5.4%), pump.fun IPFS 20% (0.8%).

**A followed-dev list, not a full dev list.**
- 109 deployers. 78% of attempts are on a dev it attempted before.
- After the first attempt it takes only about 30% of that dev's later launches.

**Streaks and momentum.**
- After an attempted launch it attempts the dev's next launch 61% of the time, vs 14% after a skipped one.
- 37% after a launch that rose, vs 11% after a flat one.
- 13% for relaunches less than 60 s apart, vs 39% for gaps of 30 min or more.

**Reading (INFERRED).** A live "hot dev" list, partly driven by off-chain signals. No single create-time rule reproduces its picks.

**Size.** Always 1 SOL; nothing predicts it.

**Are its picks better? Yes, broadly, over 2–10 s (MEASURED).** Price relative to the post-bundle price; "fast snipers" = the 412 wallets defined in section 6. The two right-hand columns are the comparison group (skipped bundled launches) at the same points.

| | Its picks +2 s | Its picks +10 s | Skipped bundled +2 s | Skipped bundled +10 s |
|---|---|---|---|---|
| With its own trades removed | 1.052 | 1.067 | 1.005 | 0.944 |
| Also all 412 fast snipers removed | **1.013** | **1.048** | 1.000 | 0.945 |

- Same-dev launches it skipped reach 0.983 at +10 s.
- The +10 s result holds in both runs: R1 1.021 vs 0.965, R2 1.063 vs 0.929.
- So the first ~2 s of the rise is fast bots, and the 2–10 s rise is generic flow.

**Generic-demand features at +10 s, all fast bots removed, held in both runs (MEASURED).**
- Dev's previous launch rose: 1.037 (R1) / 1.006 (R2). If it fell: 0.929 / 0.860.
- Relaunch less than 1 min after the previous one is bad: 0.929 / 0.829.
- Dev buy ≥4 SOL is bad: 0.924 / 0.819.
- But a pure "hot dev" selection traded our way loses at every hold: −1.3 to −4.8 SOL on R2 (hot.txt).

## 5. Entry and exits

**Entry (MEASURED).**
- 1 SOL, one buy and one sell per token.
- 69% land in the create slot, 30% in the next.
- Outside buys ahead: 0 for 48%, 1 for 33%, 2 for 12%, 3+ for 8%.
- **Arrival in our engine's clock:** median 49 ms (p25 31, p75 109); 47% arrive before 45 ms and 65% before 75 ms.
- Its entry price is a median 1.043× the post-bundle price.

**PnL by position (ledger, our windows, 516 tokens).**

| Group | PnL (SOL) |
|---|---|
| 0 outside buys ahead | +7.31 |
| 1 ahead | +0.28 |
| 2 ahead | −2.63 |
| 3+ ahead | +0.08 |
| Create slot | +6.31 |
| Next slot | −1.03 |
| Dev buy >3.5 SOL | +3.97 |
| Dev buy ~1 SOL | −1.06 |

**Failures (MEASURED).**
- 63 buy slippage failures.
- 10 duplicate sells that failed with `NotEnoughTokensToSell` ([example](https://solscan.io/tx/5pFxJjPEhUWEfmn4C4h84DJq6BgSTKUdvrrJc4nqbKiW1ymjh8VNQZjHmGvQ7ATCxsxQSW6TMNf4xeUZEajZAyk6)).
- 10 trades failed with a wrong-program error, plus 33 close-account failures.
- Failed-only attempts arrive at a median 42 ms, so they fail on price, not speed.

**Exits.** Sell types come from the router's flag byte (MEASURED). The trigger readings in the last column are **INFERRED** from what happened before each sell.

| Sell type | Tokens | PnL (SOL) | Hold (slots, median) | Sell / entry price | Trigger |
|---|---|---|---|---|---|
| normal | 1,030 | +10.64 | 7.5 | 1.017 | timed, about 1–2 s, near the local peak |
| dev or bundle sold (urgent) | 149 | −16.97 | 8 | 0.943 | an insider sold first in 66 of 66; it sells in the **same slot** |
| take-profit (urgent) | 58 | +17.62 | 7 | 1.341 | price about 1.5× at the sell |
| quick | 61 | +3.05 | 6 | 1.063 | one slot after an outside buy |
| instant (urgent) | 13 | +0.44 | 0 | 1.014 | sold in the same slot as the buy |

## 6. Copyability for us (paper replay; INFERRED from the model)

**Setup.**
- Engine: rp.py with block-order placement (`place_bo2`) and failed-tx anchors.
- Launches: the 7,875 with our engine's timelines, 10-22 22:10 → 10-23 07:39 PKT.
- Our buy: at 45 or 75 ms, 1% guard, 0.5 SOL, sold at the end of the next slot.
- **Owner's rule checks:**
  - **"Generic flow":** CWiNFA's and all 412 **fast sniper wallets'** trades after our entry are removed. A fast sniper buys within 2 slots of the create on 5+ launches and on at least half of its launches.
  - **"Slip":** we run `rp.sim(..., slip=rp.load_slip())` plus CWiNFA's own min-outs. The slip map holds 34,255 decoded follower limits and covers 29% of the follower buys here.
  - **Top 10 most frequent buyers right after us:** all are fast snipers. CWiNFA appears in 148 of 220 fills, then [5xFhXswZ…](https://gmgn.ai/sol/address/5xFhXswZ7ncwEoKfhRYuoajJ6YYmFAvuL5pumo9FAxJm) 49, [Ake3LcHT…](https://gmgn.ai/sol/address/Ake3LcHTM8jUGNQVewyVnDtRiy9YNBGHegynCbxTYRbr) 25, [9FQnf1QF…](https://gmgn.ai/sol/address/9FQnf1QFTg8TZ6AJEffsfa7CNQJGALecmPtkYoTYUPFj) 20, H6obho / HVE899 / [ViTjB3dR…](https://gmgn.ai/sol/address/ViTjB3dRqXLkSEyHPnwjVS82Kr5bRkpDbxw7525QRyd) / AHwJSn / D24ipY 19 each, [9qz7cWBq…](https://gmgn.ai/sol/address/9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw) 18.

**(a) Oracle: its 232 attempts.**

| Our sell at the end of the next slot | 45 ms | 75 ms |
|---|---|---|
| As replayed | +3.62 (94 fills) | +1.80 (61 fills) |
| With slip | +2.77 | +1.21 |
| Without CWiNFA | +1.08 | +0.18 |
| Generic flow + slip | **−2.28** | **−1.91** |

- Its own buy comes right after ours in 90 of 94 fills.
- With all fast snipers removed, 59–66% of fills have no outside buy before our sell.

**(b) Walk-forward deployer list plus our gate.**

| | 45 ms | 75 ms |
|---|---|---|
| As replayed | +3.22 (88/190 fills, halves +1.53 / +1.69) | +1.65 (51/176, halves +0.94 / +0.72) |
| With slip | +2.32 | +0.99 |
| Generic flow + slip | **−2.34** | **−1.78** |
| Win rate, generic | 10% | 8% |
| No outside buy before our sell | 59% (2% as replayed) | 65% (10% as replayed) |
| Older run R1, as replayed | +1.94 | +0.55 |

- **→ Rejected: depends on CWiNFA, 5xFhXs, Ake3Lc, 9FQnf1, H6obho, HVE899, ViTjB3, AHwJSn, D24ipY and 9qz7cW.**
- At 75 ms its list also adds nothing over S4G (vs_s4.txt: −0.02 SOL on launches not already on the S4 list).

**(c) Its own pattern on our entries (1 SOL, sell at 1 s, its fees).**

| | 45 ms | 75 ms |
|---|---|---|
| As replayed | +8.86 | +5.36 |
| With slip | +6.00 | +3.17 |
| Generic flow + slip | **−0.36** | **−0.21** |

- **→ Rejected, same dependency.** Most of its gain over our sell is the doubled size, which only pays while fast followers buy after us.

**Hold ~10 s on its list (gate on our own 10 s results).**

| Generic flow + slip | 45 ms | 75 ms |
|---|---|---|
| Newer run R2 | **+3.30** (112/220 fills, halves +1.05 / +2.25) | **+3.71** (88/258, halves +2.31 / +1.40) |
| Older run R1 (pessimistic placement) | +0.62 (halves +0.84 / −0.22) | −0.11 |

- On R2 only 1–3% of fills have no outside buy within the 10 s, so the profit comes from generic flow.
- The oracle at 10 s, generic flow + slip: +2.50 / +2.50.
- Bigger bundled pools lose at every hold length (generic.txt).
- **→ Unproven** because R1 is flat. Paper forward test only.
- It still uses CWiNFA's attempts as the selection signal, though not as the profit source.

**Takeaways (INFERRED; worth testing):**
- Fan one nonce-bound tx out to several landing services at about a 0.3% tip.
- Sell in the same slot when the dev or bundle sells.
- Send take-profit sells as urgent.
- On selective picks, generic flow peaks around 5–10 s, not at the next slot.
- Re-score S4G with the same generic-flow check; it likely has the same dependency.

## Files

All in `/home/moiz/sniper/ops/overnight/cwinfa/`. Every script runs with `python3 -I` and is read-only; RPC use stayed at or below 4 requests/s through rpcw.py.

**Page:** CWiNFA_snipes.html (render_cw.py, from snipes15.json, built by collect15_cw.py).

**Chain data:**
- fetch.py → txc/ (3,225 raw txs) and sigs_CWiNFA.json
- ledger_cw.py → ledger_CWiNFA.json
- pnl.py → pnl.txt / pnl.json: the ground truth. ana_ledger.py was a first pass that wrongly counts the stablecoin withdrawals as a loss.
- funding.py, funding2.py, funding3.py → funding*.json, sigs_CWiNFA_old.json

**Our data:**
- coll.py → coll_cw.json
- phaseA_snap/: hard-linked 3.5 GB snapshot of phaseA_dry, plus scores_v3_snap.jsonl
- arrival, guard, guard2, exits, bypos, sel, picks_vs_pool, sel_generic, hot, fast_snipers (each .py with its .txt/.json output)

**Replays:**
- replay.py, replay_nocw.py
- q6.py, q6_r1.py, boot.py, vs_s4.py
- rescore.py (rescore.txt / rescore_summary.json)
- decomp.py (decomp.txt)
- generic.py (generic.txt)
- walk10.py (walk10.txt / walk10_summary.json)
- slipcov.py (slip-map coverage)