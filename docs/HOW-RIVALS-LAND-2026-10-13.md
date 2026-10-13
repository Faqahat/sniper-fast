# How the ~1 SOL/h arb bots send and land (read-only study, 2026-10-13)

Studied 7 genuine single-tx arb bots (~0.8-1.5 SOL/h). Method: genuine single-tx flat round-trips only
(excluded solver flow-through, SOL-recipient wallets, and bare WSOL-close rent txs). Bundle membership via
bundles.jito.wtf with 429 retries. All timing is BLOCK-POSITION PROXY, not ms.

## Headline: they DON'T win by paying. They win by landing FIRST and SAME-SLOT, direct.

| Wallet | Venue | Bundle? | Tip | Priority | Leaders | First-arb/same-slot | Win p50/max | Win% | Type |
|---|---|---|---|---|---|---|---|---|---|
| F5ZSNG7 | DLMM (no prog) | **NO 0/30** | **0** | **0** | jito 13 / bam 17 | 15/30 | 1.04/1.04 | 49% | pure direct racer |
| DLMM1J | DLMM (SHARKobt) | NO 0/10 | 0 | ~38k | jito 6 / bam 4 | 3/10 | 0.07/0.15 | 42% | direct racer |
| 2FFQQq | DLMM | **YES 8/8** | tiny 8-77k (~0%) in-tx | 40-73k | jito 6 / bam 2 | 5/8 | 0.88/1.26 | 31% | jito bundle, trivial tip |
| 4yFAz | PumpFun (custom) | YES | **big 0.004** sidecar | **0.002** | — | — | 2.17/2.17 | **1%** | spammer — DO NOT COPY |
| A2Az | custom (CPI) | NO 0/30 | 0 | ~0 | jito 19 / bam 11 | 0/30 | 0.006/0.006 | 92% | HFT direct racer |
| 3CcX | PumpFun/PumpSwap | mostly NO 2/13 | 0 direct | ~7-14k | jito 7 / bam 6 | 3/13 | 0.04/1.72 | 62% | direct racer + occasional flow |
| 5CSoq | custom (VRF) | NO 0/20 | 0 | ~450 | jito 16 / bam 4 | 0/20 | 0.003/0.005 | 50% | HFT direct racer |

## The common recipe
- **DIRECT submission, NOT Jito bundles.** 5 of 7 are 0% bundled. They land on BOTH jito AND bam leaders in a
  roughly even split -> they are NOT bundle-gated; they broadcast to whatever leader is up. This strongly implies a
  **staked / SWQoS direct-TPU connection** (validator/staked-lane advantage), not a fee advantage.
- **Zero/negligible tip** (wallet 1 = literally 0; the one bundler tips ~0% of profit).
- **Zero/negligible priority / CU price.**
- **Win by being FIRST + SAME-SLOT:** first arb behind the trigger (0 arbs between), in the trigger's own slot
  ~50-62% of the time (DLMM racers).
- **Meteora DLMM dominates** the reliable earners (1, 2, 3). A custom program is NOT required (wallet 1 uses raw DLMM
  swaps, no custom prog).
- **No durable nonce anywhere.** DLMM racers: single atomic tx, 4 ATA-create + 1 close, ~860-930 bytes, CU ~450k.
- HFT bots (5, 7) have no discrete trigger — they arb continuous micro-spreads on volume (thousands of 0.003-0.006
  SOL wins/h), not size.
- **Racing dominates; orderflow is the minority** (only wallet 3's small top-of-block wins and wallet 6's custom
  bundles have the trigger inside their own bundle).
- **The outlier wallet 4** (Jito bundle + big tip + big priority) FAILS 74%, wins 1% -- the strategy to AVOID.

## Path to copy for us
1. **Do NOT build around Jito bundles or tip auctions.** The winners submit DIRECT. The lever is a **staked /
   SWQoS direct-TPU lane** (Helius swqos / Astralane staked / Paladin P3 / rented stake) so our tx reaches the
   current leader directly, on BOTH jito and bam leaders. This, not fees, is what lands them in the trigger's slot.
2. **Stop paying priority/tips as the primary lever** -- it is not what lands these. Keep priority modest, tip ~0;
   spend the budget on latency/connectivity.
3. **Same-slot = submission latency.** Our 80-200 ms send-to-land spills into the next slot (gap gone). Target
   <~50 ms and co-locate near the leader schedule.
4. **Match the DLMM tx shape:** single atomic tx, 4 ATA-create + 1 close, raw Meteora DLMM swaps (no custom router
   needed), CU ~450k, ~860 bytes, base fee only.
5. Orderflow (wallet 3/6 minority) = secondary; smaller per-trade, needs flow access.

## Caveats
- Bundle "NO" results are real empty arrays (not throttle nulls).
- SOL/h not re-derivable cleanly from RPC (ATA rent lockup + landed-fail attempts contaminate per-tx delta); trust the
  externally-measured ~1 SOL/h. Per-win sizes/frequencies are measured.
- "First-arb/same-slot" are block-position proxies, not ms.
