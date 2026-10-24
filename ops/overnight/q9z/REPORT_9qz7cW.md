# 9qz7cW: complete dissection (read-only, 2026-10-23, times PKT = UTC+5)

Wallet **9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw** ([gmgn](https://gmgn.ai/sol/address/9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw) · [solscan](https://solscan.io/account/9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw)).

Nothing was sent or traded, and no server was changed. Labels: **MEASURED** = chain or collector data; **INFERRED** = my reading of it; **PAPER** = rp.py replay. Page: `9qz7cW_snipes.html`.

## Verdict
- **What it is.** A custom, multi-strategy pump.fun bot with an on-chain equity of about **2,155 SOL**: 89.6 SOL plus about 2,066 SOL of quote tokens. It also has about **1,373 SOL** in 3 treasury wallets it feeds. It is not an AKbot-style customer. MEASURED / INFERRED.
- **Profit.** SOL side **+406.5 SOL** over 61.5 h, all of it swept to the treasuries (405 SOL withdrawn). The last 36 h made **+283 SOL** after all costs.
  - Daily SOL side by PKT day: 10-20 (6 h) +43.1; 10-21 +257.7; 10-22 +95.3; 10-23 (8 h) +10.5. MEASURED.
- **Two behaviours.**
  - Create-slot snipes: 75% first outside buyer, median 35 ms in our feed. **−11.9 SOL net.**
  - Later entries into active buy waves: **+119.9 SOL net**, driven by size; its 10+ SOL buys made +53.6 SOL. MEASURED.
- **For us.** Nothing copyable at 0.5 SOL. The later-entry edge needs its size and timing plus a pick signal we cannot see at decision time (§6).

## 1. Infrastructure and bot identity (MEASURED unless marked)

**Router and fees**
- Router `2eFuLSK4McKonBcB6XLax8gSgxwR56zNfrjHsvkNkftj` carries all its sells and its backup buys.
- Only 6 signers ever call it in our collector:
  - 9qz7cW: 24,112 txs
  - 3KspVijg…: 336; 53JGzWmn…: 287; 5cxJRGr4…: 158; DF4qVoMn…: 154; 4XYMGFnd…: 119
- No 1% bot-fee transfers in 36 h of fully read history.
- INFERRED: private software, not a commercial bot.

**Buy transaction (v1)**
- advanceNonce, rotating 4 nonce accounts (5nUdEsBk…, 895KeyJj…, CMXoxdGU…, DgGakg9Z…).
- Compute-unit limit = units used + about 400 (it pre-computes the cost).
- createAccountWithSeed + initializeAccount3 (Token-2022, no ATA program).
- pump.fun `buy_exact_quote_in` called directly, then an optional tip transfer.
- Priority fee sits in the v1 header. One signer, no lookup tables. v0 is used only for 409 Jupiter swaps of quote tokens.

**Landed buy copies (collector, about 26 h)**

| Copy that landed | Count | Median spend |
|---|---|---|
| Priority-fee copy | 895 | 0.029 SOL |
| Jito-tip copy | 311 | 0.053 SOL |
| Transfer to `b1ooMngj…` / `b1oomst2…` | 142 | 0.06 SOL |
| Router backup with a 0.001 SOL tip (LandX, Helius, Nozomi, Everstake) | 11 | 0.001 SOL |

- "b1oo…" is not in our tip map. 15 other snipers pay it too, including 4yFAz7dp, 8RvtT818 and 2mqrindM. INFERRED: a landing service; worth adding to tipmap.json.
- Landing spend:
  - Snipes: 2.8% of the SOL bought.
  - Later entries: 4.8% of the SOL bought.

**Sells**
- Fee 5,000 lamports, plus an optional Jito tip of 0.00011 SOL (2,878 of 5,658 sells).
- Each sell is sent as about 3 copies. The spares fail inside the router with error 0xaa (170) at 476 CU, for 5,000 lamports each.

**Failures**
- 57,552 of 81,206 signatures failed (71%).
- The costly ones are nonce copies that land after the price moved. They fail on pump error 6042 (BuySlippageBelowMinTokensOut) and still pay their full priority fee: **32.5 of the 36.8 SOL** of failed-tx fees in the collector.

**Slippage**
- On 808 landed buys it received a median **+9.8%** more tokens than its min-out (p25 5%, p75 18%).

**Compared with 9Sh2fd**
- Same pro toolkit: v1, durable nonce, seeded token account.
- 9Sh2fd uses one landing service (LandX, about 2% tip) and pays AKbot 1%.
- 9qz7cW fans each buy out over several paths, runs its own sell router and pays no bot fee. INFERRED: built in-house.

## 2. Profit — ground truth

**Coverage**
- 81,206 signatures on the owner's RPC, from 10-20 18:14 PKT to now.
- 36 h window (10-21 20:00 → 10-23 07:40 PKT): every successful tx read. Sources: 7,249 fetched from the RPC; 6,295 from our collector's raw txs, with quote legs decoded from pump V3 events (checked exact against RPC on 299 txs).
- Failed txs: 19,687 measured. The 16,564 unread ones are priced from the SOL-balance gap at 0.00176 SOL each (the collector mean is 0.00187).

**36 h ledger (MEASURED)**

| Category | SOL |
|---|---|
| Trading | +329.7 |
| Quote swaps | +19.5 (mostly price drift) |
| Failed-tx fees | **−65.9** |
| Other | +0.1 |
| **PnL excluding transfers** | **+283.4** |
| Withdrawals | −212.3 |
| Deposits | 0.02 |

- **Cross-check (SOL side):** the SOL balance went 113.12 → 88.88 while 212.25 SOL was withdrawn, so **+188.0 SOL** exact on the SOL side.
- **Quote inventory:** +95.4 SOL at current prices. USDC +6,844, PUMP, AMZN, BTC/XMR wrappers and others; no implied negative starting balance on any of 152 mints.

**By venue, 36 h**

| Venue | Tokens | SOL |
|---|---|---|
| pump.fun curve, SOL | 1,351 | +149.9 |
| pump.fun curve, non-SOL quote | 604 | +97.5 |
| LaunchLab | 79 | +37.6 |
| Raydium CPMM | 3 | +13.7 |
| Orca | 3 | +9.3 |
| PumpSwap AMM | 31 | −5.2 |

**Concentration:** 2,060 tokens, +320 SOL. Without the top 10: +140.9; without the top 20: +72.5. Median token −0.03 SOL.

**By behaviour (collector windows, about 26 h, all costs incl. failed attempts)**

| Behaviour | Net | SOL-quoted | Non-SOL quote | Failed-only launches |
|---|---|---|---|---|
| Later | **+119.9 SOL** (930 launches) | +82.5 | +50.9 | −13.5 |
| Snipes | **−11.9 SOL** (972 launches) | −3.2 | +3.4 | −12.2 |

- Later entries without the top 10 tokens: still +11.6 SOL. Snipes without the top 5: −40.8 SOL.
- Pump launches outside our collector: +108.5 SOL. Their behaviour can't be classified (no create times).

**Older period (25.8 h).** Balance 87.66 → 113.12 SOL, plus 193.0 SOL withdrawn = **+218.4 SOL on the SOL side**. Built from hourly checkpoints and the treasury txs. Quote inventory was not measured there.

## 3. Funding and relations
- **Withdrawals: 405 SOL in 61.5 h to 3 sink wallets.** Their recent inflows come only from 9qz7cW and they show no outflows. INFERRED: the operator's own treasuries.

  | Treasury | Balance now | Received from it |
  |---|---|---|
  | 9BhkaAybG824w5Hk2A1Np22ZwYN74f6kisJtLEK9C6Ns | 813 SOL | 10–15 SOL every 1–3 h |
  | GBXnrHXZENJZrpCHjSX177XR78e9Pmjmawp2ZukiJcv6 | 489 SOL | |
  | 3UEJbmddD8zWDKUKZQieGQwTEXrHhyy3MXbsNk6pZFnq | 72 SOL | |

- **Deposits:** none besides 0.018 SOL. It runs on its own profits.
- **First funding not reached.** It has at least 481k signatures; public-RPC paging went back to 10-06 23:07 PKT and was still going.
- **Router co-users.** 3KspVijg, 4XYMGFnd, 5cxJRGr4, DF4qVoMn and 53JGzWmn each hold about 20–25 SOL, have 84–93% failed txs, and appear in each other's txs. No transfers with 9qz7cW were seen. INFERRED: same software, likely the same operator's or a small private group's wallets.
- **Not linked to AKbot.**

## 4. Selection (MEASURED: 46,223 launches; 961 snipe attempts, 930 later attempts)

| Feature | Snipe attempt rate | Later attempt rate |
|---|---|---|
| All launches | 2.1% | 2.0% |
| Mayhem launches | 0% (2 of 11,141) | 0% |
| Dev buy <0.5 SOL | 0.6% | 0.2% |
| Dev buy 2–3 SOL | 8.2% | 5.2% |
| Dev buy 3–5 SOL | 6.6% | 10.1% |
| Dev buy ≥5 SOL | 5.4% | 7.4% |
| No glued bundle | 1.0% | 0.7% |
| 2-tx glued bundle | 7.9% | 10.5% |
| Create paid by a wallet other than the creator | 5.6% (vs 1.3%) | 6.1% (vs 1.1%) |
| Fresh deployer (0 prior launches) | 5.7% | 6.1% |
| Deployer with ≥100 prior launches | 1.1% | 1.5% |
| No socials | 0.5% | 0.2% |
| Twitter + website | 3.1% | 3.4% |
| Metadata host uxento | 7.3% | 4.3% |
| Metadata host j7tracker | 2.8% | 4.2% |
| Metadata host ipfs.io | 1.4% | 0.4% |
| Non-SOL quote | 3.6% | 4.2% |
| Tools "otc" / "pump_v2" / "pumpstocks" | 0% | 9.0% / 9.4% / 4.6% |

- **Not a dev list.** 795 different creators; 687 launched only once. For repeat creators it took 17–54% of their launches.
- **Time of day:** flat.
- INFERRED snipe profile: fresh deployer, dev buy 1–5 SOL, a bundle, socials, pro launch tools.

**Later entries — when it enters (166 SOL-quoted first buys)**
- Age: median 25 s after the create (p10 4.7 s, p90 7.7 min).
- Price: **1.41×** the post-bundle price (p25 1.11, p75 2.0). Curve 38–64 SOL.
- Last 10 s: price +11.6%, **net inflow +4.2 SOL** from 13 buys.
- It buys into a live wave: the trade just before its buy is someone else's buy in 153 of 162 cases (127 in the same slot).
- Among the 3,234 launches that met a generic momentum test, its picks had serial deployers (median 100 prior launches vs 3) and a stronger 15-s price (1.41× vs 1.16×).

## 5. Entry and exits (MEASURED)

**Snipe landing**
- 77% in the create slot, the rest in the next slot.
- First outside buyer 75%.
- Entry price median 1.000× the post-bundle price (p90 1.167×).
- Arrival in our feed: p10 14.5 ms, median 34.6 ms, p90 134 ms.

**Size tiers**
- Round gross amounts. Snipes: 1.8 SOL (174), 1.2 (107), 3.0 (103). Later entries: 2–7 SOL, up to 35 SOL.
- No single launch feature sets the tier; every tier appears in every bucket and over time. INFERRED: several filter profiles, each with a fixed size.

**Snipe exits**
- If the price is below entry at about 8 slots (1.7 s), it sells everything at once: 84–86% of cases.
- If the price is ≥1.05×, it sells 30–40% within 2–3 slots and ladders the rest.
- Single-sell tokens (204): **−28.2 SOL**. Tokens with 3–5 sells: +20.8 SOL.

**Later-entry exits**
- A fixed ladder: 25–40% at about 3 s, then 10% or 17% of the position every 2–3 s regardless of price.
- 6–12 sells, last sell median 19 s (p90 77 s). Tokens with 6+ sells: +65.7 SOL.

**What drives the later-entry result**

| Its buy size | Tokens | Result (SOL) | Its price impact | Others' buys after it |
|---|---|---|---|---|
| <2 SOL | 29 | +0.7 | ×1.08 | 6 SOL |
| 2–3 SOL | 128 | +15.3 | ×1.13 | 13 SOL |
| 3–5 SOL | 74 | +9.1 | ×1.16 | 14 SOL |
| 10+ SOL | 8 | **+53.6** | **×1.77** | 68 SOL |

- Other wallets bought 9,749 SOL between its later buys and its last sells; only 0.3% of that came from fast snipers.
- INFERRED: the edge is size buying into a live wave, with its ladder selling into the followers.

## 6. Copyability for us (PAPER)

**Set-up.** Our 45/75 ms landing, 1% guard, 0.5 SOL, sell at the end of the next slot.
- "Fast snipers" = 380 wallets (≥5 launches with a buy within 2 slots and ≥50% of their buys that fast); 9qz7cW is one.
- Slippage limits: 34,935 known (core/slip_args.jsonl plus its own 808).

**(a) Its snipe picks, as an oracle** (220 attempts in the replay window)

| Landing | Base | Its own after-us buys removed | All fast-sniper after-us buys removed | Top-10 after-us buyers removed | Slippage-aware |
|---|---|---|---|---|---|
| 45 ms (83 fills) | **+7.05** | +3.61 | **−1.90** | +2.04 | +6.64 |
| 75 ms (57 fills) | **+4.17** | +1.78 | **−1.85** | +0.67 | +3.94 |

- The top-10 after-us buyers are 9 fast snipers plus one other wallet.
- **Rejected: depends on 9qz7cW, Ake3Lc…, dKMjeG…, G9sQPg…, DpBUrt…, CWiNFA…**
- For comparison, every R2 launch with the same mechanics: −125.9 SOL at 45 ms.

**(b) Walk-forward creator list from its snipes, with the quality gate**

| Variant | 45 ms | 75 ms | Fast-sniper buys removed |
|---|---|---|---|
| K=1 | +4.96 (+2.3 / +2.6 by half) | +3.70 | −1.48 / −1.36 |
| K=2 | +4.07 | +3.08 | −1.24 / −1.22 |

- **Rejected, same dependency.**

**(c) Later entries** (our tx lands 300–500 ms after the decision, so every trade in that window is ahead of us; costs = pump fees + 0.0001 SOL per tx)
- **Following its later buys** (248 entries): −2.7 to −5.9 SOL for every exit (end of next slot, 5 s, 20 s, its ladder). The +1% worse fill is about 1.2 SOL worse. With the top-10 after-us buyers removed: down to −9 SOL.
- **Generic trigger from its own medians** (5–300 s old, ≥1.10× the post-bundle price, ≥3 SOL net inflow from ≥8 buys in 10 s; 3,234 entries): **−39 to −156 SOL**, negative in both halves.
- **The same trigger with its decision-time profile** (≥15 s, ≥1.3×, deployer with ≥20 launches; 825 entries): **−10 to −27 SOL** in both halves and both runs.
- Its actual later picks score +11 SOL with our early generic entry, against −110 SOL on the candidates it skipped. That is look-ahead: it decides about 20 s after our trigger. Not actionable.

## Files (`ops/overnight/q9z/`)
- **Page:** `9qz7cW_snipes.html` (made by collect15.py, facts.py, render15.py).
- **Ledger:** sigs.json, txc/, raw_q9z.jsonl.gz, ev_q9z.json, ledger_q9z.py / .json / .txt, ledger_hourly.json, ledger_inventory.json, older_wd.json, fetch.py, fetch_plan*.json.
- **Behaviour:** perlaunch_q9z.json, an_launch.txt, select_q9z.txt, later_dive.txt.
- **Infrastructure:** infra.txt, decoded.json, router_users.json, slip_q9z.json(l), quote_by_mint.json, prices.json, holdings_now.json.
- **Relations:** relations.json, treasury.json, oldest_sigs.json.
- **Replays:** sim_copy(2).txt, later_strat.txt, l3.txt, fast_snipers.json.