# Analyst K (recon): exact 24 h reconciliation of haqq's bots to his wallet: residual 0 lamports (10-28 ~03:50 PKT)
Saved by the main session from the agent's reply. Window 10-26 23:15 → 10-27 23:15 PKT. Code: this folder. Data: /home/moiz/sniper-data/haqq_dissect/recon/:
- r6.txt: reconciliation and per-bot cash;
- r7.txt: the two P&L views and the bridge;
- r7b_boot.txt: bootstrap ranges;
- r8.txt: evidence and every non-bot movement;
- r9.txt: payouts.

## Chain (MEASURED, public RPC)
- **Balance:** start 39.547922862, end 42.421531683, change **+2.873608821 SOL**.
- **Signatures:** 13,530 (972 failed). 12,863 are in our recordings; all 667 others were fetched (625 zero-lamport txs by another program, 28 bot trades the recorder missed, 5 payouts, 3 WSOL unwraps, 6 inbound).
- **Second account:** a WSOL account with a 5 SOL float receives PumpSwap sale proceeds.

## Reconciliation (exact)

| Line | SOL |
|---|---|
| Bots' cash flow | **+31.662685** |
| PumpSwap proceeds that landed as WSOL | −3.121850 |
| WSOL unwraps | +3.413346 |
| Rent for 3,055 token accounts opened | −4.547184 |
| Rent back from 3,293 accounts closed | +4.901433 |
| Infrastructure | −0.000580 |
| **Payouts (5 Jupiter txs)** | **−29.437600** |
| Inbound | +0.003360 |
| **= predicted change** | **+2.873608821** |
| Chain change | +2.873608821 |
| **Residual** | **0 lamports** |

**Per-tx exactness:** all 12,863 recorded txs rebuild exactly; 82 random txs match RPC pre/post balances to 0 lamports.

## Per bot (code = CU price mod 1000)

| Bot | Lots | Size | Hold p50 | **Lot P&L (24 h)** | 90% range | Cash in window | Earlier table |
|---|---|---|---|---|---|---|---|
| 248 | 2,081 | 0.40 | 4 s | **+11.808** | +4.5..+19.0 | +11.352 | +11.768 |
| 247 | 1,045 | 0.40 | 4 s | **+8.907** | +3.5..+14.5 | +8.907 | +8.899 |
| 244 | 1,416 | 0.25 | 9 s | **+3.416** | −1.6..+8.7 | +3.416 | +3.166 |
| 226 | 403 | 0.50 | 1 s | **+1.562** | −0.8..+3.9 | +1.562 | +1.573 |
| 234 | 568 | 0.50–1.25 | 1,199 s | **+1.375** | −2.7..+5.9 | +5.130 (timing at the window edges) | +1.384 |
| 231 | 62 | 0.25 | 1 s | **+0.693** | | +0.693 | +0.705 |
| 251 | 129 | 0.35 | 4 s | **+0.602** | | +0.602 | +0.605 |
| 249 / 252 | 0 (inactive) | | | 0 | | | |
| **All** | **5,704** | | | **+28.363** | | **+31.663** | +28.100 |

The earlier +28.1 is CONFIRMED (the +0.28 difference is 13 lots touched by trades the recorder missed).

**Tail dependence:** the median lot loses for every bot. The top 1% of lots carry the day: 248 +9.13 of 11.81, 247 +4.75 of 8.91.

## Payouts (MEASURED)
- 5 payouts, each fired when the balance reached 45.0–47.7 SOL and each leaving exactly 40.0000013 SOL.
- **Split:** 30% → 2WH2MMkm, 30% → 2eGYbuBG, 25% → USDC via Jupiter (FNgKVDxo, BZWeswZ9, 8wYMocyf), 10% → 9tk6L2AE, 5% → 8wYMocyf.
- **So:** his bots earn ~28 SOL/day, but his balance stays at ~40 SOL. That explains GMGN's flat ~38–40 SOL balance.

## MAIN-SESSION VERIFICATION
I fetched payout 5 (yThh9Doh…) myself with public RPC:
- 10-27 22:31:43 PKT, slot 462156099;
- haqq 47.698320595 → 40.000001303 (−7.698319292);
- receivers 2WH2 +2.3093 (30%), 2eGY +2.3093 (30%), HgFLBWQu +1.9244 (25%, the USDC swap route), 9tk6 +0.7698 (10%), 8wYM +0.3849 (5%).

Matches the agent exactly. **CONFIRMED.**
