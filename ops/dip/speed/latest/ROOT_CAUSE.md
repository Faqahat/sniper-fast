# Why our buys land late — root cause (10-25, read-only)

## Data
- **Live fires:** 255 (FRA runs 1–10 + AMS runs 9–10, 10-24 02:00 → 10-25 00:14 PKT).
- **Probes:** 110 single-path landing probes (probeA–E).
- **Chain rows:** every tx on those tokens around each fire (raw recordings).
- **Scripts (latest/):** timeline.py, chainside.py, rootcause.py, ourtx.py.

## Where the time goes (fire → our tx back in the feed)
- **Mean 62 ms, median 37 ms.** The gap between them is the next-slot spills.
- **Our code (dump seen → fire): 1.2 ms.** Not the problem.
- **Waiting for the EXECUTED feed before firing: +1.5–1.7 ms median, +5.7 ms p90** (FRA). The shred feeds (kaldera / turbo-kaldera) see the dump first in ~97% of fires.
- **26% of our buys miss the dump's block and land in the NEXT block** (fire→seen 118 ms vs 33 ms same-slot). That is **62% of all our extra delay** (delay above 20 ms).
  - **Dump late in its block:** dump in the last quarter of its block → 81% spill.
  - **Leader client and turn position:**

    | Leader client | Spill rate |
    |---|---|
    | Jito | 31% (first slot of a Jito leader's turn: 58%) |
    | Rakurai | 83% |
    | AgaveBam | 27% |
    | HarmonicAgave | 20% |
    | FireBAM | 9% |
    | HarmonicFiredancer | 12% |

  - **NOT** per-account CU limits: spills happen on QUIETER blocks for the token (1.3M CU requested on the curve vs 2.8M when we land same-slot).
- **Same-slot landings:** fire→seen ~33 ms, but much of that is the feed bringing the block back to us.
  - In-block position: we land a median 98 txs after the dump (fills 70, failed buys 128). The first rival lands 38–48 txs after it.
  - 26–35% of the first rivals are inside the dump's own burst (≤ 25 txs): pre-sent / spam txs that cannot be beaten by reacting.
- **The feed is bursty:** each block reaches us in bursts ~13–38 ms apart.
  - The dump plus the next ~25 txs arrive together (~2 ms).
  - The next burst arrives ~18 ms later, then ~36 ms…
  - Our txs are seen exactly when others' at the same position are (residual −4.7 ms), so the feed treats us the same.
- **Paths (single-path probes, same-slot fire→seen):**

  | Path | ms |
  |---|---|
  | nozomi | 29 |
  | bolt | 30 |
  | landx | 31 |
  | staked-rpc | 33 |
  | helius | 38.5 |
  | astralane | 42 |
  | tpu-direct | 42.5 |
  | haan | 49 |
  | helius-swqos | 50 |

  - Jito leaders are worst: 49.5 ms same-slot, 45% spill.

## Not the cause (measured)
- **Fees and tips:** rivals ahead of us pay a 1.43M CU price vs our 5M, and carry 0–1 tips vs our 2–4.
- **Number of tip transfers / hot tip accounts:** our 4-tip buys are not slower than 2–3-tip buys.
- **Per-account (curve) CU limit:** see above.
- **Our own code or the feed handling our tx differently.**

## Fixes (no stake purchase)
1. **Fire on the shred feed, not the executed feed.**
   - Decode the sell (token amount) from the instruction; take the SOL size from our curve book.
   - Rely on min_out to protect us if the dump failed.
   - Gain: ~1.7 ms median, ~5.7 ms p90.
2. **Slot-timing gate.**
   - At fire time, estimate the time left in the current block (our slot clock / first-shred time of the slot).
   - If the dump is in the last ~25% of the block, the buy lands next block 81% of the time. Either skip it (for HOT1 1-s trades) or target the next slot's leader route explicitly.
   - The dip strategy's spills were still profitable (+0.75 SOL on 71 fires), so decide per strategy.
3. **Leader-turn handover.**
   - On Jito leaders, the first slot of the turn spills 58%. This is likely relays/RPC forwarding to the previous leader at the turn start (inference).
   - Send copies on both the previous and the current leader's routes around turn boundaries, or skip Jito slot #1.
4. **Route pruning.**
   - Drop the slow paths: helius-swqos 50 ms, haan 49, tpu-direct 42.5, astralane 42.
   - Lead with nozomi / bolt / landx (29–31 ms).
   - For Jito leaders, probe the paths rivals win with there (soyas / glaive / speedlanding: 21–33 ms in the Jito study).
5. **Pre-senders.**
   - 26–35% of the first rivals sit in the dump's own burst and can't be beaten by reacting.
   - Optional: skip tokens where a wallet already has failed attempts on that token in the last 5 slots.

Expected: fixes 2–3 remove most of the spill tail (mean 62 → ~35 ms); fix 1 −2..6 ms; fix 4 −5..10 ms on same-slot fills.
Engine / send-path changes need the owner's OK.

## Re-check from chain (verify.py: real block sizes via getBlock, real leader schedule, RPC slots) — 240 fires
- **Spills:** 62 / 240 (26%). Same-slot 32.8 ms vs spilled 118 ms; mean 62.1 ms; spills = 62% of the delay above 20 ms. **Confirmed.**
- **Spill by TRUE dump position in its block:**

  | Dump position | Spill rate |
  |---|---|
  | 0–25% | 15% |
  | 25–50% | 11% |
  | 50–75% | 29% |
  | 75–100% | **80%** |

  **Confirmed.**
- **Leader turn start (real schedule):**
  - Jito: first slot of the turn 11/19 (58%) vs other slots 9/45 (20%). **Confirmed.**
  - HarmonicAgave: 5/16 vs 4/30.
  - BAM: no turn effect (6/21 vs 15/58).
- **51 of 62 spills land in the SAME leader's next slot** (only 11 go to another leader). So it is mostly the same leader putting us in its next block, not a far handover.
- **Executed-feed wait:** the engine fires on the executed-feed time in 240 / 240 fires; the lag behind the first (shred) feed is median 1.17 ms, p90 4.76 ms (all regions).
