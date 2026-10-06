# Rival dossier: GLiCiNEn (program GLCNMEV6) compared with arbx

**Date:** 2026-10-06. **Subject:** wallet `GLiCiNEnku3pQsmkVkRvnDLbfUN9BWbsrPDWLdPaADng`. Read-only; nothing was signed or sent.

**Sources:**
- **[R]** public-RPC `getTransaction` on two even samples of its 4,152 signatures from 11:53–14:32 UTC, none failed. A = every 20th of the first 3,000 (150 txs); B = 100 spread over all 4,152. Together: 218 arbitrage txs and 32 lookup-table (ALT) txs.
- **[RPC]** other public-RPC reads; **[J]** the Jito bundle explorer.
- **[FT4]/[FT5]** arbx records pulled to `/home/moiz/arbx-offload/rival-glici/`: FT-004 p1+p2, and FT-005 p1 to 14:26.
- **[RS3]** the 2026-10-03 rival-study outputs.

USDC is valued at 120.4 USDC/SOL, the median of 15 sampled WSOL→USDC legs. *Inference* marks what is not measured directly.

## 1. Bottom line

- **A breadth bot, not a speed bot.** One wallet and one program land ≈1,560 txs/h, all successful [RPC]. 87% are 2–4-leg arbitrages over 438 distinct pools on 12 venues; 13% maintain its own ALTs [R].
- **Self-tipped single-tx Jito bundles at ≈15% of gross,** with no priority fee. 41% land on BAM leaders, matching BAM's 37% of slots [R, J, RPC].
- **Tiny trades, small steady money.** Median size 0.00065 SOL, median net +3,267 lamports, no loss in 218 trades. Net ≈0.009–0.023 SOL/h, 240–620× FT-004's +37,053 lamports/h [R, FT4].
- **Our speed class.** On our pools its tx reaches shreds p50 124 ms after the previous write to that pool; 1% sit at idx+1 and none is a same-bundle backrun: rung 3–4 [FT4, J].
- **Rarely takes our gaps.** It was the first pool writer after our trigger on 6 of our 806 unlanded FT-004/FT-005 bundles (0.7%). In both landed overlaps we landed first [FT4, FT5].

## 2. Identity

| Item | Finding | Src |
|---|---|---|
| Wallet | System-owned. 4.719 SOL native (slot 453,922,813), 62.19 WSOL (ATA `CWYbW9nN…`), 4,332.97 USDC (`98gTqoZ6…`): ≈102.9 SOL-equivalent | RPC, R |
| Age, funding | First tx 2026-09-10 10:35:37 UTC. `BAAQZJF6h5baeQZJmQwvMH2fDiHSoJh7x5yYWoBZ2PSK` opened its WSOL ATA with 8.0 WSOL and sent 0.02 SOL. From 11:19 to 11:42 it sent ≈2,000 txs that burn and close token accounts (3 sampled; the close paid its rent to GLiCiNEn), and it has not signed since (0.0018 SOL left). *Inference:* the operator's retired bot wallet | RPC |
| Later capital | WSOL + native: 50.6 SOL (09-20), 48.9 (09-23), 58.8 (09-30), 61.3 (10-04), 66.9 (10-06); USDC 3,622 (09-28) → 4,333. *Inference:* ≳35 SOL was deposited before 09-20 (trading cannot explain it); the source was not found | R |
| Co-signers | None: GLiCiNEn alone signs and pays in 250/250 txs, and is the only GLCNMEV6 caller in FT-004 (215 rows). A 1,000-lamport deposit from lookalike `BAAQpAEss…` is address poisoning (*inference*) | R, FT4 |
| Program | `GLCNMEV6Z7P72YtUciTUzMczWPALAkV9F6k5z9jHsfwy`, upgradeable. Programdata `CdmWbG64…`: 524,333 bytes (ours: 42 KB), 2.664 SOL. Upgrade authority GLiCiNEn. Deployed 09-10 11:13; 18 programdata txs, the last 10-04 13:09 UTC | RPC |
| Verified / known | Not verified (verify.osec.io). Stripped ELF: no security.txt, no Anchor strings, raw syscalls. RS3: 338 wins in 0.97 h on 10-03, the most by count of 4,925 [PS], but 0.06% of win SOL. 12 of our 1,500 `data/templates.json` entries came from its CPIs | OSEC, RS3 |
| Lookup tables | 99 distinct in 218 arbs (p50 3 per tx). The main one, `6KhVYPGy…` (154/218), was built 10-04. The 5 checked are its own, active, with 254–256 addresses. 16 other signers reuse them, as is common | R, RPC, FT4 |

## 3. How it lands

| Item | GLiCiNEn [R, J] | arbx [FT4] |
|---|---|---|
| Path | 216/218 arbs are 1-tx Jito bundles it tips itself (explorer: all found, all size 1). Its two biggest in B (gross 1.34M, 1.37M) used Helius Sender at a 75–80% tip, no bundle. ALT txs: plain, no tip | 1-tx Jito bundles |
| Tip | One top-level transfer after the arb instruction; no CPI tip. All 8 Jito accounts, Helius twice; none to Nozomi, Astralane, bloXroute or others (arbx tip map). p10/50/90 1,043 / 1,515 / 4,518 lamports = 14.2 / 15.5 / 19.1% of gross. 62–80% on its three trades above 1M gross | 0.7 × (gross − fee): 48% of landed gross |
| Fees, CU | Fee 5,000 on 250/250 (no priority fee). CU limit p50 150,189 against 133,030 used (1.12×); loaded-data limit 32 MiB | price 0; limit p50 183,000, 1.79× used |
| Block idx | p10/50/90 173 / 803 / 1,214 | landed 51–1,607, median 804 |
| Leaders | 128 Jito (59%), 88 BAM (41%), 0 other; slot shares 61.7 / 37.0 / 1.2% (getSlotLeaders × validators-meta, which matched FT-004's live kinds for 252/252 leaders) | 170/415 sends to BAM, 2/12 landings |

## 4. Strategy

**Routes** [R]:
- **Venues** (644 legs): DAMMv2 217, PumpSwap 116, DLMM 79, Whirlpool 63, Raydium CLMM 51, Tessera V 33, Raydium CPMM 32, AMM v4 26, DAMMv1 9, Pancake CLMM 8 (program inferred), Byreal 5, Manifest 5.
- **Shape:** 2/3/4 legs in 42/20/38%. Hub WSOL 83%, USDC 17%; USDC appears in 40% of sample-A routes.
- **Pairs:** mostly memecoins (DAMMv2↔PumpSwap commonest); pure USDC/WSOL routes are 7%.

**Size and profit** (218 arbs) [R]:

| | p10 | p50 | p90 | max |
|---|---|---|---|---|
| Size (SOL) | 0.0001 | 0.00065 | 0.025 | 8.28 |
| Gross (lamports) | 6,367 | 10,056 | 27,280 | 3,909,201 |
| Net after fee + tip | 253 | 3,267 | 17,835 | 1,482,828 |
| Gross / size (bps) | 6 | 172 | 1,007 | |

- **No losses:** the smallest net was +14 lamports. 30 trades (14%) create a token account (1.49–1.57M rent) and leave it open.
- **Per hour, from the samples:** A gives gross 0.056, tips 0.026, net 0.023 SOL/h; one 8.28-SOL trade is 60% of that net, and without it the net is 0.009. B gives 0.060 / 0.036 / 0.017.
- **Per hour, from the wallet:** native + WSOL + USDC rose 0.0042 SOL/h from 11:54 to 14:03, after rent locked in new accounts and ALTs.
  - *Inference:* it recovers rent in batch closes our samples missed. The sampled creations imply ≈1.16 SOL locked in 2.15 h, yet native SOL fell only 0.153.

**Triggers and rung:**
- **No same-bundle backruns:** all 216 bundles hold only its tx [J].
- **On our pools** [FT4 moves, slotidx, txarr], 398 of its FT-004 txs, measured against the previous write to the same pool:

  | Position | Share | Shred-arrival gap |
  |---|---|---|
  | idx+1 / idx+2..5 | 1.0% / 2.5% | |
  | Later in the same slot | 35.2% | p50 51 ms |
  | Next slot / 2+ slots | 22.6% / 20.1% | p50 195 ms (next) |
  | No write within 50 slots | 18.6% | |
  | **All with an earlier write** | | **p50 124 ms; 10.5% ≤20 ms** |

  - That earlier write was a non-arb (or unsampled) tx in 245 of 324 cases, and its own tx in 28.
- **On any pool,** in 10 sampled txs checked against full blocks: the nearest earlier write to its pools was 75–379 positions back (7) or in an earlier slot (3) [RPC].
- **Rung 3–4** (RS3's gap age at its 10-03 wins: p50 112.5 ms). It reacts to state, not to openers. *Inference:* it re-prices many pools per update and sends any cycle that clears fee + tip.

**Program features** [R]:
- **Instruction:** `0x03 | amount_in u64 | cost u64 | n_legs u8 | per-leg bytes` (n_legs matched in 218/218).
- **`cost` is the guard:** it equals fee + tip in 180/180 WSOL trades. On USDC trades it is (fee + tip) × 132.5 USDC/SOL, ≈10% over market. *Inference:* a guard of hub gain ≥ fee + tip, like our min_profit.
- **On-chain down-sizing (*inference*):** its venue calls are exact-in, yet the first leg used less than `amount_in` in 54 of 174 checkable trades (median ratio 0.96, p10 0.74), never more.
- **Other traits:**
  - one route per tx, no baskets;
  - no CPI tip, no nonce;
  - v0 txs with ALTs, one v1 tx;
  - 12.8% of its txs create or extend its own ALTs (sample A: 168 addresses added).
- **No-op vs revert:** RS3 classed its 10-03 build as no-op on a miss (33/558 flat). The 10-04 build showed 0 flat in 218.

## 5. Overlap with arbx

| | FT-004 (12:38–13:39) | FT-005 p1 (13:40–14:26) |
|---|---|---|
| Our bundles sent / landed | 415 / 12 | 415 / 12 |
| GLiCiNEn txs; those writing a watched pool | 1,551; 398 | 1,416; 375 |
| Our bundles where it wrote a route pool, trigger slot −1 to target +1 | 29 (10 in the trigger slot) | 35 |
| It was the first writer after our trigger (likely closer) | 3: 2 guard verdicts (0x4e580002), 1 other | 3: 1 guard, 2 other |
| It was the second writer | 4 | 6 |
| Landed overlaps | 1; we landed first (rank 363 vs 483) | 1; we landed first (50 vs 88) |

- **Same pools, different moments:** 320 of our 415 FT-004 bundles used a pool it traded that hour, but only 29 came within a slot of its trades.
- **Where it beat us:** 5 of its 6 first writes were USDC/WSOL routes with a DLMM leg, arriving 2–107 ms after our decision.
- **Estimate:** of our ~403 unlanded FT-004 bundles it took 2–3 (≤0.7%), or at most 7 (1.7%) counting second writes.
- **Who took the rest:** En3NPq8o 22, GgGap6ti 18, rLsi2DPw 14, 4XBqViD1 9, MriyaNN8 8, R32xAccF 7, GLiCiNEn 3; 255 first writers had no rivals row (users or sampled out) [FT4].

## 6. What arbx can learn

1. **Tip share (X4): test below 0.35.**
   - It lands ≈1,360 arbitrages/h, 99% as Jito bundles, at ~15% of gross on Jito and BAM leaders alike, and escalates only on big gaps (62–80% above 1M gross).
   - Our misses were not lost auctions (STAGE1-PLAN §4).
   - Add a 0.15–0.2 arm for gaps under ~50k gross. At 15%, FT-004's 12 wins would have kept ≈62,700 more lamports, if they still landed (my sum).
2. **Coverage beats speed.** It is no faster than us (p50 124 ms, against our ≈97 ms from trigger to landing: 13.6 ms to decide + ≈83 ms to first sighting [FT4]), yet nets 240–620× more.
   - Its edge is breadth: 79% of its 438 pools are outside our 1,843, 58% of its trades have 3–4 legs, and 17% use a USDC hub. Only 9 of 218 (4%) are 2-leg WSOL routes entirely on our pools, the kind arbx prices today.
   - The levers that compete directly are coverage: discovery (WP-14/X8, seed refresh), 3–4-leg and USDC routes (rival-synthesis §8 item 3), and Whirlpool, Raydium CLMM and Tessera V.
   - Its most-used unwatched pools: Tessera V USDC/WSOL `FLckHLGM…` (16 trades); `EUvenWZq…`'s DAMMv2/PumpSwap pair `6VMgv8yV…`/`BziS3SEG…` (13 each); Whirlpool ORCA/WSOL `Hxw77h9f…` (7); AMM v4 `95512Hcj…` and CPMM `De469KJo…` (6 each).
3. **Size (the WP-11 size arm).** Its median size is 0.00065 SOL against our median send of 0.056 SOL; 75% of its trades are under 0.003 SOL, and its trades net +253 to +17,835 lamports (p10–p90).
   - Cap the arm well below 0.05 SOL and size to the gap.
   - Its on-chain down-sizing is WP-17, which waits for the $500 stage.
4. **BAM (X5).** Its plain bundles land on BAM in proportion (41% of landings, 37% of slots). Ours land on 1.2% of BAM-targeted sends against 4.1% on Jito leaders. *Inference:* the defect is in our path; check BAM submission (region, timing).
5. **Cheap engineering that works for it:** CU limits at 1.12× use (ours 1.79×), self-built ALTs, and Helius Sender for the rare big gap. Our rent-neutral create+close (WP-06) already beats its open token accounts.
6. **Not the lever here:** the conflict filter (1a) and send delay (X2) target faster rivals.

## 7. Limits

- **Its land rate is unknown:** failed bundles never land.
- **Hourly P&L is a range:** one trade is 60% of sample A's net.
- **"First writer" is approximate:** moves.log sees only our watched pools, and it counts swaps that leave a gap open.
- **Funding after 09-10** is inferred from balances at 9 anchors.
- **Other inferred labels:** the Pancake CLMM program and the Tessera V pool account.
- **Cost:** 216 MB scp'd read-only, ≈418 public-RPC requests (with retries), ≈450 Jito lookups.
