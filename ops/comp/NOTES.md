# /root/comp — competitor buy size / fees / exits on rule-#2 race launches (READ-ONLY research, 2026-10-19)

Status: IN PROGRESS (data fetch running). Labels: **[M]** measured from chain/logs, **[I]** inferred/modelled.

## Data
- Launch universe: /root/race/*_onchain.jsonl (engine-seen launches, on-chain labelled), 10-18 18:00 → 10-19 14:33 UTC.
  - unique base-filter launches 8,124; **rule #2 (bundle 3–5 SOL + create tips moon…) = 1,271**; contested (bundle ≥2 SOL) = 3,633. [M]
  - r2 per hour: 28–95, median ≈ 58/h. [M]
- Tapes: `fetch_tapes.py` → `tapes_r2*.jsonl`: every successful tx on the mint from create slot S to S+300 (~2 min), full TradeEvent
  (sol, tok, vsol, vtok, fee bps, creator fee), CU price/limit, tx fee, tips (known tip accounts), all system transfers from signers, slot leaders.
  Random (seed 7) order over the 1,271 r2 launches, 3 shards x 2 RPC threads.
- Trade order: create slot by block index d (from race `later` lists); later slots by chaining curve pre/post states (exact).
- 4yFAz: /root/sizing/tx.jsonl (5,222 of his txs, 556 mints bought, 10-18 → 10-19) + 348 mint tapes (create → his last sell, capped +30 slots).
  The sizing agent's 4 tape.py jobs were stopped at 348/556 mints to free RPC threads.

## Gates / fire rate inputs [M]
- live_land_final1 (no leader gate): 10 rule-#2 passes in 0.28 h → 36/h.
- live_land_final2 (close-leader gate on): 40 race decides in 0.91 h, 12 rule-#2 passes (13/h), 7 of 12 pass create ≤150 ms → 7 fires (7.7/h).
- create ≤150 ms into slot: 68% of 7,078 base-pass launches (erpc poh_ms, live logs).

## 4yFAz7dp (the reference sniper): 554 first buys, 10-17 08:00 → 10-19 17:00 UTC; 377 with mint tapes (w4.py, w4_report.txt, w4_exit.txt)
**Buy size [M]: fixed discrete tiers, NOT liquidity- or MC-scaled.**
- Tiers (SOL into the curve): 0.49 (34), 0.721 (60), 1.171 (22), 1.432 (94), 2.153 (79), 2.926 (113); 152 off-tier (mostly 1.2–2.1, a few 4.1 / 6.63).
  His program's spend arg = curve SOL × 1.0125 (fee-inclusive), e.g. 2.963 SOL for the 2.926 tier.
- Each tier spans the whole entry range (vsol 30–69 SOL). R² of log(size) on log(vsol_pre) 0.034, on log(MC) 0.034,
  dev 0.044, bundle SOL 0.020, slot offset 0.005, outsiders ahead 0.001, price vs post-bundle 0.000 (n=377–554).
- So his own price impact varies with the size: median 3% (0.49 tier) → 17% (2.93 tier). There is no impact cap.
- Weak tiering by dev buy [M]: dev <2 SOL → median 1.43 SOL; dev 2–4 → 2.15; dev ≥4 → 2.93.
  The bigger tiers do better: 2.15 / 2.93 tiers win 51–53%, mean +0.17 / +0.12 SOL per trade; 0.49–1.43 tiers win 24–45% with mean ≈ 0.
  → **[I] the tier is a confidence score** from a signal we can't see on chain (the earlier finding: off-chain/X).
- Entry state: median MC 31–41 SOL ($3.2–4.2k); entry price = post-bundle price (median 1.00x; he enters before other outsiders).
  Median position in the create slot d=53 (q25 25, q75 110); 76% of buys land in the create slot.
**Fees [M]**
- Two fee families:
  - priority only (234): CU price up to ~1e9 µlam, CU limit 53–61k → 0.015–0.14 SOL;
  - tip only (≈260): Nozomi 92, Helius Sender 72, Raiden Bolt 12, Jito 10, LandX 10, SpeedLanding 6, at 0.015–0.025 SOL;
  - plus 60 prio+tip and 51 with only ~0.0001 SOL.
- Median landing cost 0.020 SOL = 1.75% of size.
- **Fee scales with size (the confidence factor):** corr(size, land) 0.60 (R² 0.36).
  Median land: <1 SOL 0.020; 1–2 SOL 0.015; 2–2.5 SOL 0.050; 2.5–3.5 SOL 0.060; >3.5 SOL 0.140. The 2.93 tier's median priority is 0.059 SOL, against 0.0013 for the other tiers.
- Fee is unrelated to dev (corr 0.11), bundle (−0.01), leader client (0.015–0.025 for all) and outcome (0.020 for winners and losers alike).
- **A higher fee did not buy him a better position:** land <0.02 → in S 82%, median d 35; land 0.04–0.06 → 77%, d 79; >0.06 → 70%, d 41.
  The 0.0001-SOL path (36 buys) still landed in S 83% at median d 41 → [I] a staked / SWQoS connection, not the fee, gets him in.
**Exits [M]: scale-out ladder, with a ~4 s go/no-go check.**
- 45% sell everything at once. Median at 10 slots (≈4 s), price ≈ entry (q25 0.99x, median 1.01x): a timeout/stop.
  These trades: mean −1.9%, median −3.5%.
- 55% scale out:
  - If the price is up ≥~1.05–1.1x within 0–2 slots, he sells **30% immediately** (108 of 268 first sells; median 1.11x entry).
  - At slot 8–12 (~4 s) he sells **all** if the price is ≤1.05x entry (79% sell all in the 1.00–1.05x band); otherwise 1/3.
  - Then he sells **1/3 of the remainder every ~5 slots (2 s)** (fractions 0.33 → 0.22 → 0.15 → 0.10 of the original); the final remainder goes when the price fades.
  - Median last sell 11.6 s (q75 50 s, q90 74 s). Scale-out trades: mean +7.8%, median +3.6%.
- Sells are cheap: 0.0001–0.0002 SOL (CU price 1M µlam, no tip).
- Reacting to others? 28% of first sells had another wallet's sell ≥0.5 SOL in the prior 1 s, and 16% a bundle sell in the prior 3 s.
  → mostly not reactive; the ladder is price/time driven [I].
- Result: mean +3.43% per trade, median −1.5%, win 44%; **+66.95 SOL net of all fees over 554 buys in ~57 h (≈28 SOL/day, ≈9.7 buys/h)**.
