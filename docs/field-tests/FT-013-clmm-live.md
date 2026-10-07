# FT-013: first live sends through Raydium CLMM and Orca Whirlpool (3 h, live canary on frz)

- **Status:** owner decisions on 2026-10-07: "Yes u can" (live sends after FT-009 passed) and "Ok do it first" (before FT-012).
  - FT-012, which started at about 08:36, is stopped and runs after this test.
- **Build:** master 4c6f2c9 (WP-21 + the commit-wait fix + WP-11 with experiments off), `bin/arbx-4c6f2c9`.
- **Mode:** canary under `arbx campaign`, 3 × 60 min, bundle-only, one send a second (as FT-005..FT-010).
- **Budget:** WP-07 allotment 5,000,000 lamports within the cumulative hard cap (about +1,200,000 in profit overall).
- **Config:** `deploy/arbx-ft013-frz.toml`, which is FT-008's config (0.2 tips, 0.05 SOL cap and small rungs, BAM fix) with:
  - the seed list `data/seed-pools-wp21-shadow.csv`: the 1,500-pool list plus 242 vetted CLMM/Whirlpool SOL pools;
  - `[pools] rayclmm = "send"` and `whirlpool = "send"`;
  - `[pool_refresh]` off, per the FT-009 plan (WP-22 does not read CLMM swaps).
- **Evidence for the run:**
  - FT-009 part 1 (shadow): all 8 criteria passed. About 1,000 CLMM would-sends an hour, 42.5% of them closed by winning rivals.
  - FT-009 part 2 (dry run): 1,050 of 1,050 bundles verified and simulated, with no account, CU or loaded-data error, and every CLMM leg ran. CLMM commit timeouts fell from 50% to 8%.

## Pass/fail (safety, written before the run)
1. Bundle-only; 0 failed-landing fees.
2. Every landed trade nets > 0 after fee + tip + rent (0 exceptions), CLMM trades included; create+close rent fully returned.
3. Reconciliation ok at every stop; spend within budget; no refused bundle lands.
4. No CLMM/Whirlpool bundle fails in Jito's simulation for an account, CU or loaded-data reason. Profit-check reverts are expected and fine.

## What is measured (decision rule, written before the run)
- **CLMM's share:** wins, net and sends through a CLMM/Whirlpool leg (by venue pair).
- **Realised vs quoted** on CLMM wins (median within ±10%).
- **Against FT-008** (same settings, older venues only):
  - net SOL/h, wins/h, win ratio, net per win;
  - `canary_wait` refusals per send (more opportunities compete for the same one-send-a-second slot);
  - the meme vs common mix.
- **Safety nets:** commit timeouts for CLMM groups (≤ ~10%), and late members or `torn_suspect` on accounts left out of the write set (review finding 1).
- **Decision:**
  - Keep CLMM/Whirlpool sends on if the safety list holds and CLMM wins realise their quotes.
  - Then FT-012 (tips × sizes) runs with them on.
  - Net SOL/h against FT-008 is reported. It is time-separated and the one-a-second slot binds, so it is indicative only.

## Results
(filled in)
