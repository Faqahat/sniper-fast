# Venue census: the DEX venues rival arbitrage uses, and what arbx is missing

**Date:** 2026-10-06. Read-only: nothing was signed or sent, and no code was changed.

**Sources:**
- **[S]** public-RPC `getTransaction` samples of 16 arbitrage signers, spread evenly over each one's latest 1,000 signatures **[P]**. Most pages cover 5–60 min before 15:23 UTC; GgGap6ti's covers 12 h. In total: 851 successes (769 arbitrages) and 49 failures.
  - **The signers:** the five named rivals (GLiCiNEn reuses the dossier's 250 cached transactions), the ten top arbitrage signers in FT-004's records, and DcQNaByv (11th).
  - **Ranking:** by landed swaps on watched pools, rivals.jsonl ⨝ moves.log **[F4]**.
  - **Skipped as non-arbitrage:**
    - AgmLJBMD (DFlow flow) and the retail users of 6Vo3245e and FLASHX8D, all per rival-synthesis;
    - the users of GMGN, by its program name;
    - HAWK3BVn: none of its 10 sampled successes is an arbitrage; each moves WSOL between third-party accounts around DLMM calls.
- **[B]** a market census: 30 full blocks evenly spaced over slots 453,905,675–453,944,825 (13:00–15:45 UTC). They hold 16,000 non-vote transactions and 173 arbitrages by 73 signers.
- **Other inputs:**
  - **[D]** pooldisco's candidates.csv (disco-20261006-1426);
  - **[J]** Jupiter's public program-id-to-label map;
  - **[IDL]** on-chain Anchor IDLs;
  - **[SRC]** the Whirlpool clone in scratch-wp21.
- **Cost:** 772 public-RPC requests (retries included), one label GET and one scp. Files are in /home/moiz/arbx-offload/venue-census/ (64 MB).

**Method:**
- **Arbitrage:** a successful transaction with two or more swap legs that closes in one hub (SOL/WSOL, USDC or USDT) with gross ≥ 0.
  - **Leg:** a venue call, top-level or CPI (inside aggregators too), that moves two assets under two authorities.
  - **Left out:** cross-hub routes (5 in [S], 25 in [B]) and loss-making round trips (36 in [B]).
- **Gross:** as in the GLiCiNEn dossier: the signer's hub change + fee + tips.
  - Tips also include SOL left with fresh third-party accounts.
  - USDC is valued at each block's SOL/USDC median (120.2–121.9).
  - **Check:** the analyzer reproduces the dossier exactly: 218 arbitrages, gross p10/50/90 of 6,367 / 10,056 / 27,280 lamports, and the same 644 legs.
- **Weights:** each signer counts by its arbitrages per hour: successes per hour [P] × the arbitrage share of its sampled successes.
  - An arbitrage counts once per venue it touches, so shares sum to more than 100%.
  - CIs are 90%, bootstrapped within each signer.
- **Totals:** the 16 land about 18,800 arbitrages/h for 7.2 SOL/h gross. MriyaNN8 makes 4.9 SOL/h of that, so shares are also given without it.

## 1. Bottom line

- **arbx prices about 4% of rival arbitrage today.**
  - 20.8% of rival arbitrages (30.0% of gross) stay on our five venues.
  - 4.1% are 2-leg SOL routes entirely on watched pools [S].
- **WP-21 phase A** lifts venue coverage to 40.0% of rival arbitrages and 49.2% of gross. All of it comes from Whirlpool and the Raydium CLMM family.
  - The curves add 0.0 points: 0 of 769 rival arbitrages, and 2.3% of market arbitrages [B].
- **Whirlpool is the most valuable missing venue:** 29% of rival arbitrages, 40% of rival gross (CI 25–54%), 36% of market arbitrages.
- **60% of rival arbitrages need a venue that is not allowlisted.** They carry 51% of gross, or 66% without Mriya.
  - The largest are the prop AMMs BisonFi (24% of rival and 35% of market arbitrages) and Tessera V (18% / 12% of gross).
  - Next is Manifest, an open-source order book (11% / 9%).
- **Prop AMMs:**
  - **Constantly requoted:** their operators post an update 4–18 times per block [B].
  - **No public code:** *inference:* the only exact pricing is running their deployed binaries on fresh state.
  - **Aggregator-only:** BisonFi, GoonFi V2 and Scorch were never called directly (0 of 356, 0 of 134 and 0 of 106 legs, [S] plus all [B] transactions).
- **Aggregator-heavy rivals fail most:** 92% of 4XBqViD1's landed transactions fail, 86% of 4B8srvot's and 69% of En3NPq8o's [P].
- **Missing pools matter as much as missing venues.**
  - On our own venues, rival legs hit a watched pool 73% of the time on DLMM, but only 17% on DAMM v2, 21% on PumpSwap, 36% on CPMM and 48% on AMM v4 [S].
  - pooldisco scans none of the CLMM venues.

## 2. Ranked venues

Ranked by share of rival gross ([S], activity-weighted); venues with fewer than 5 arbitrages are listed below the table.

**Status:**
- **a** — traded now.
- **b** — allowlisted, not traded (WP-21A).
- **c** — needs a program upgrade.

| # | Venue | Program | Type | Rival arb txs | Rival gross [90% CI] | Excl. Mriya | Market arb txs [B] | St. | Maths and replay |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Meteora DLMM | LBUZKhRx… | DLMM | 25.0% | 65.0% [51–76] | 37.3% | 17.3% | a | exact (WP-16) |
| 2 | Orca Whirlpool | whirLbMi… | CLMM | 29.0% | 40.1% [25–54] | 39.9% | 35.8% | b | open source; fixed and dynamic tick arrays, adaptive-fee oracle, Token-2022 [SRC] |
| 3 | PumpSwap | pAMMBay6… | CPMM | 19.5% | 29.5% [16–42] | 10.6% | 10.4% | a | exact |
| 4 | Meteora DAMM v2 | cpamdpZC… | CPMM | 21.9% | 16.5% [7–27] | 17.7% | 11.6% | a | exact |
| 5 | Tessera V | TessVdML… | prop AMM | 17.8% | 11.9% [4–21] | 9.5% | 9.2% | c | closed; one operator requotes about 11×/block; 52 of 94 legs direct |
| 6 | BisonFi | BiSoNHVp… | prop AMM | 23.5% | 10.7% [4–19] | 11.9% | 34.7% | c | closed; about 18 updates/block; never direct (DFlow 208, Jupiter 142, OKX 6) |
| 7 | Raydium CLMM | CAMMCzo5… | CLMM | 23.4% | 9.2% [6–14] | 17.1% | 20.2% | b | open source; tick arrays plus bitmap extension |
| 8 | Manifest | MNFSTqtC… | order book | 10.9% | 9.0% [3–17] | 8.6% | 12.7% | c | open-source CLOB, deterministic; state is the whole market account; 35 of 49 legs direct |
| 9 | ZeroFi | ZERor4xh… | prop AMM | 1.8% | 6.9% [1–15] | 2.5% | 2.3% | c | closed; n = 6 (one large trade) |
| 10 | Raydium CPMM | CPMMoo8L… | CPMM | 4.7% | 6.8% [1–14] | 2.2% | 2.3% | a | exact |
| 11 | PancakeSwap v3 | HpNfyc2S… | CLMM (Raydium fork) | 9.8% | 6.7% [1–15] | 3.5% | 5.2% | b | CLMM maths; check layouts against the binary |
| 12 | Orca V2 | 9W959DqE… | CPMM | 1.5% | 4.5% [1–9] | 1.0% | 1.7% | c | trivial maths; Mriya uses it |
| 13 | Scorch | SCoRcH8c… | prop AMM *(inference)* | 4.5% | 1.9% [1–3] | 6.0% | 5.2% | c | prices via ojh19o…; requoted about 7×/block; aggregator-only |
| 14 | Flux | FLUX6xBa… | prop AMM? | 1.5% | 0.8% | 2.4% | 2.9% | c | aggregator-only; n = 5 |
| 15 | HumidiFi | 9H6tua7j… | prop AMM | 1.5% | 0.7% | 2.1% | 1.7% | c | 44 of 49 [B] legs via aggregators |
| 16 | Deriverse | DRVSpZ2Y… | unknown | 5.7% | 0.6% | 2.0% | 4.6% | c | USDC/USDT, SOL/USDC; En3NPq8o, mostly direct |
| 17 | AlphaQ | ALPHAQme… | prop AMM | 2.9% | 0.6% | 1.8% | 4.0% | c | 35 of 36 [B] legs via aggregators |
| 18 | Meteora DAMM v1 | Eo7WjKq6… | CP/stable + vaults | 5.2% | 0.5% | 0.8% | 1.7% | c | open source; the vault price decays with the clock |
| 19 | Byreal CLMM | REALQqNE… | CLMM (Raydium fork) | 2.7% | 0.4% | 1.3% | 3.5% | b | CLMM maths |
| 20 | GoonFi V2 | goonuddt… | prop AMM | 2.1% | 0.3% | 1.0% | 9.8% | c | aggregator-only |
| 21 | Raydium AMM v4 | 675kPX9M… | CPMM | 5.9% | 0.3% | 0.6% | 5.8% | a | exact |

**Other venues:**
- **Fewer than 5 rival arbitrages** (shares from 1–4 trades):
  - Hadron 7.4%;
  - Obsidian 7.2% (one operator requotes about 11×/block, so a prop AMM *(inference)*);
  - MetaDAO 3.8%;
  - Denali 2.6%;
  - SolFi V2, Archer, Omnipair, JupLend AMM and a few others, including one unnamed program with no IDL (8iQtGj9m…).
- **Only in [B]:** Quantum 1.7%, Meteora DBC 1.2%, pump.fun and LaunchLab 0.6% each.
- **Market gross [B]** is too noisy to rank: 173 arbitrages total 0.0098 SOL, and one trade can move a venue's share by 16 points.

## 3. Aggregators (status d)

| Aggregator | Program | Underlying venues in rival arbitrages [S] (legs) | In market arbitrages [B] (legs) |
|---|---|---|---|
| Jupiter v6 | JUP6LkbZ… | Tessera V 42, Whirlpool 29, CLMM 21, DLMM 19, Scorch 18, DAMM v2 15, Manifest 14, AlphaQ 10, BisonFi 10, PumpSwap 9, HumidiFi 6, GoonFi 5, ZeroFi 5 | Whirlpool 22, CLMM 16, DLMM 13, Tessera V 12, GoonFi 9, Manifest 8, BisonFi 7, Obsidian 7 |
| DFlow | DF1ow4ts… | BisonFi 70, Deriverse 1 | BisonFi 53, Whirlpool 6, CLMM 5 |
| OKX DEX Router [IDL] | proVF4pM… | GoonFi V2 4 | GoonFi 9, Whirlpool 9, Manifest 6, Scorch 6, AlphaQ 4 |
| Titan | T1TANpTe… | — | Archer 2 |

- **Not seen:** the older OKX router (6m2CDdhR…) and Dexlab.
- **DFlow is in effect BisonFi access:** 70 of its 71 legs in rival arbitrages are BisonFi.
- **Aggregator legs by signer:**

  | Signer | Arbitrages with an aggregator leg | Landed transactions that fail [P] |
  |---|---|---|
  | GxDC9e7S | 93% | |
  | NALUnJA2 | 92% | |
  | En3NPq8o | 83% | 69% |
  | 4XBqViD1 | 76% | 92% |
  | 4B8srvot | 67% | 86% |
  | MriyaNN8 | 8% | |
  | GLiCiNEn, rLsi2DPw, GgGap6ti, 78Bo7xxG, HuTshmtw, 9ZAPm4VS | 0% | |

- **Failures:** weighted by failures per hour, Jupiter v6 appears in 45% of failed samples [S].

## 4. Route shapes

| | 2 legs | 3 legs | 4 legs | 5+ legs | SOL base | USDC base | USDT base |
|---|---|---|---|---|---|---|---|
| Rivals [S], by count | 55.0% | 26.9% | 16.9% | 1.2% | 69.6% | 30.0% | 0.5% |
| Rivals [S], by gross | 46.0% | 39.3% | 14.7% | 0.0% | 54.5% | 45.4% | 0.1% |
| Market [B], by count | 63.6% | 28.3% | 8.1% | 0% | 62.4% | 35.8% | 1.7% |

- **Different venues serve different pairs:**
  - **SOL/USDC:** prop-AMM legs mostly trade it (BisonFi 65 of 80, Tessera V 61 of 94).
  - **USDC/token:** Manifest, ZeroFi and GoonFi.
  - **SOL/token:** our venues (PumpSwap 194 of 240).
- *Inference:* prop-AMM arbitrages are mostly SOL–USDC triangles, which a 2-leg SOL engine cannot express.

## 5. Missing venues that pair with venues we trade

Rival arbitrages/h [S] that combine the missing venue with a traded venue, and those whose traded leg is on a pool we already watch (FT-004 pools.json ∪ the 2026-10-06 seed list):

| Missing venue | St. | Arbitrages/h using it | …with a traded venue | …on a watched pool (share of all rival arbitrages) | Main partners (arbitrages/h) |
|---|---|---|---|---|---|
| Orca Whirlpool | b | 5,451 | 2,028 (37%) | 1,374 (7.3%) | DLMM 944, AMM v4 494, DAMM v2 447, CPMM 292 |
| Raydium CLMM | b | 4,400 | 1,778 (40%) | 1,189 (6.3%) | DLMM 865, DAMM v2 422, PumpSwap 285 |
| Tessera V | c | 3,339 | 1,095 (33%) | 581 (3.1%) | DLMM 622, DAMM v2 299, AMM v4 181 |
| BisonFi | c | 4,415 | 602 (14%) | 513 (2.7%) | DLMM 513 |
| Manifest | c | 2,049 | 409 (20%) | 379 (2.0%) | DLMM 367 |
| Meteora DAMM v1 | c | 986 | 620 (63%) | 325 (1.7%) | AMM v4 275, DLMM 196, DAMM v2 181 |
| PancakeSwap v3 | b | 1,845 | 546 (30%) | 148 (0.8%) | DLMM 179, DAMM v2 127, PumpSwap 124 |

- **DLMM is everyone's partner.**
- **In [B] too:** a traded venue appears in 15 of 62 Whirlpool arbitrages, 9 of 35 CLMM, 4 of 16 Tessera V and 5 of 60 BisonFi.
- *Inference:* most of what these venues unlock also needs new pools and multi-leg routes.

## 6. Recommended WP-21 order (value × feasibility)

Value is the coverage reachable with the venues added so far. It starts at 20.8% of rival arbitrages and 30.0% of gross [S], and 11.0% of market arbitrages [B]. It ignores discovery and route shape.

**Phase A:**

| Step | Add | Coverage after (rival arbitrages / rival gross; market) | Feasibility |
|---|---|---|---|
| A1 | Orca Whirlpool | 25.8% / 40.3%; 17.3% | open source and exact; dynamic tick arrays and the adaptive-fee oracle add work [SRC] |
| A2 | Raydium CLMM, then PancakeSwap v3 and Byreal | 40.0% / 49.2%; 26.0% | one maths for three programs (the allowlist calls both forks); prove each fork in the harness |
| A3 | With A1 and A2: pooldisco for the CLMM venues; 3–4-leg and USDC routes | most of the realisable value: 45% of rival arbitrages have 3+ legs, 30% close in USDC | pooldisco's `enum V` has 8 venues and no CLMM |
| A4 | Curves last: DBC, then pump.fun and LaunchLab | +0.0 points [S]; +2.3 points [B] | simple maths; the value is bursty: pooldisco's top two candidates are DBC↔DAMM v2 pairs (an estimated 2.8 SOL/h each) that the samples never caught *(inference)* |

- **Check of the planned order (CLMM, Whirlpool, forks, curves):** curves last is right, but Whirlpool should come first.
  - **Alone:** Whirlpool adds 5.0 points of arbitrages and 10.3 of gross, against 4.1 and 3.4 for Raydium CLMM; in [B], 6.3 points against 3.5.
  - **Together:** Whirlpool and the CLMM family add 19.2 points, against 11.4 for the sum of each alone. So ship both before anything else.
  - If CLMM maths is clearly cheaper to finish, starting with the whole family is acceptable: it reaches 27.2% / 37.5% on its own.

**Phase B (one owner-approved upgrade).** It is justified by:

| Step | Add | Gain after phase A (rival arbitrages / gross; market) | Feasibility and risk |
|---|---|---|---|
| B1 | Tessera V, direct CPI | +7.5 / +10.5 points; +2.9 / +1.3 | 4 rivals call it directly. Closed, so a black-box quote: its binary in an SVM (as venue-harness does) on shred-fresh state, against about 11 requotes/block *(inference: unproven)* |
| B2 | DFlow (= BisonFi) | +11.4 / +2.6; +23.1 / +9.6 | DFlow quotes needed; aggregator-heavy rivals fail 69–92% |
| B3 | Manifest, direct | +2.5 / +6.6; +2.9 / +1.3 | open source and exact; state-heavy |
| B4 | Jupiter v6 | phase A plus every aggregator leg: 76.3% / 64.6%; 87.9% of market | the long tail (GoonFi V2, Scorch, SolFi V2, HumidiFi, AlphaQ); quote latency is WP-21's gate |
| B5 | Meteora DAMM v1 and Orca V2, in the same upgrade | +4.9 / +0.5 and +0.4 / +3.9 | open source and cheap; DAMM v1 pairs with our venues in 63% of its arbitrages |

## 7. Limits

- **Short windows:** most pages cover minutes, and heavy tails dominate profit. Mriya's mean is 11.0M lamports per arbitrage, and one trade decides each low-n venue.
- **Small census:** [B] has 173 arbitrages, so its transaction shares are ±4–7 points.
- **Names** come from [J], [IDL] and public knowledge. The prop-AMM labels for Obsidian, Scorch, Flux and Hadron are inferred from their requote pattern.
- **Custody:** gross counts only the signer's own accounts. A bot keeping funds in PDAs would be undercounted; none in [S] did.
- **Selection:** the ten come from FT-004 only (FT-005 has no rivals.jsonl pulled), and the rivals stream records only transactions touching our venues or pools; [B] offsets that bias.
- **Upper bounds:** coverage gains count reachable routes, not captured ones.
