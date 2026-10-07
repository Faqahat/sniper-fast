# Landing within 50 ms of send (research, 2026-10-07)

Read-only study by a research agent. Scripts, outputs, raw extracts and web notes (with citations) were in the session
scratchpad `landing-research/` (`web-notes.md`, `data-section.md`, `fastl1_landed.py`, `bundles_landed.py`,
`bundles_by_ingress.py`, `leader_reach.py` and their `.out` files).

Corrections to the handoff:
- fastL1 overall median send -> landed is **125.7 ms** (per landed copy, first arrival in `txarr`), not 202 ms. The
  per-kind medians (Jito-kind leaders 58.7 ms, BAM 175.6 ms) are unchanged.
- **Bug:** `outcomes.landed.leader` records the leader at send time, not the landed slot's leader. It is wrong on 4 of
  20 landings (attempts 5, 25, 76, 90). Take the leader from `leaders.jsonl`.
- **All 20 fastL1 landings failed the profit check, including the 19 ms and 26 ms ones.** Speed alone did not keep
  the edge there.

## Headline
1. **What fronts the leader's transaction port matters more than "Jito vs BAM".** Shares of 6,804 leader slots:

   | Front | Share of slots |
   |---|---|
   | BAM node (port 5010, shared by up to 105 validators) | 37.7% |
   | Harmonic front | 23.0% |
   | The validator's own address, no front | 34.9% |
   | Other shared front (maybe a jito-relayer) | 4.5% |

   Jito switched off its hosted relayers in August 2025.
2. **Every landing under 30 ms went to an unfronted leader near Frankfurt, in the current slot.**
   - Astralane: 19.1 ms and 25.6 ms, both JitoLabs leaders.
   - Harmonic leaders land at about 50 ms, because Harmonic builds blocks in 50 ms batch auctions.
   - BAM leaders take 55–134 ms even in the same slot.
3. **Missing the current slot is the biggest cost.**
   - 284 bundles: same slot p50 55 ms vs next slot 176 ms.
   - fastL1: same slot 80 ms, next slot 202 ms, later leader 411–1,065 ms (4 of 20).
4. **Slots are about 250 ms now** (SIMD-0525). A step to 200 ms is pending, possibly at epoch 1052.
5. **Alpenglow is targeted for mid-October.** Before it, BAM nodes go into maintenance and BAM leaders run as plain
   Jito-Agave. That gives a free A/B test.

## fastL1 landings, fastest first
"Ms" is send to landed; "into slot" is ms since the current slot's first shred reached Cherry; "+n" is the landed slot
relative to the slot current at send.

| Attempt | Won by | Ms | Leader | Front | RTT ms | Into slot | Landed |
|---|---|---|---|---|---|---|---|
| 79 | astralane | 19.1 | JitoLabs DE | none | 1.1 | 30 | +0 |
| 19 | astralane | 25.6 | JitoLabs NL | none | 6.9 | 142 | +0 |
| 45 | bolt | 49.0 | HarmonicAgave DE | Harmonic | 0.8 | 72 | +0 |
| 18 | astralane | 52.6 | HarmonicAgave DE | Harmonic | 1.1 | 228 | +1 |
| 31 | helius | 54.7 | AgaveBam | BAM Amsterdam | 6.5 | 108 | +0 |
| 104 | bolt | 58.7 | HarmonicAgave | Harmonic Amsterdam | 12.3 | 212 | +1 |
| 90 | helius | 79.9 | JitoLabs DE | none | 1.3 | 113 | +0 |
| 99 / 98 / 80 | bolt / bolt / astralane | 101.5 / 117.7 / 133.6 | AgaveBam | BAM London | 11.8 | 46–61 | +0 |
| 89 | bolt | 114.0 | AgaveBam | BAM Frankfurt | 0.7 | 254 | +1 |
| 23 / 43 | bolt | 175.6 / 227.8 | AgaveBam | BAM Amsterdam | 6.5 | 134 / 50 | +1 |
| 10 | astralane | 186.1 | JitoLabs DE | none | 0.8 | 29 | +0 |
| 9 / 35 / 29 | helius / bolt / astralane | 201.9 / 301.6 / 319.6 | AgaveBam | BAM Tokyo / Ashburn / Singapore | 81–213 | — | +1 |
| 25 | astralane | 371.0 | AgaveBam | BAM Dublin | 19.3 | 2 | +1, new leader |
| 5 | helius | 452.2 | JitoLabs NL | none | 7.6 | 89 | +2, new leader |
| 76 | astralane | 1065.3 | JitoLabs DE | none | 3.5 | 169 | +4, new leader |

Copies that won: Astralane 8, Bolt 8, Helius 4. Astralane won 5 of 9 on non-BAM leaders, including both landings
under 30 ms. Bolt won 6 of 11 on BAM leaders.

## Landing-study bundles by front (near = RTT under 15 ms)

| Front | Same slot: n, p10 / p50, share under 50 ms | Later slot: n, p50 |
|---|---|---|
| none | 34, 22.7 / 50.7 ms, 50% | 31, 98.2 ms |
| Harmonic | 23, 43.1 / 61.8 ms, 35% | 16, 108.6 ms |
| BAM node | 12, 26.8 / 59.4 ms, 42% | 21, 229.5 ms |
| other shared | 11, 32.1 / 41.9 ms, 73% | 4, 75.7 ms |

- By client, near leaders only: Firedancer p50 50.1 ms, JitoLabs 68.0, HarmonicAgave 69.5, AgaveBam 123.4.
- In the next slot, our bundle runs about 33 ms in on non-BAM leaders and about 95 ms in on BAM leaders.

## Leader reach from Frankfurt (RTT to the front)

| Front | Slots | Under 5 ms | 5–15 ms | 15–30 ms | 30 ms+ or unknown |
|---|---|---|---|---|---|
| none | 34.9% | 12.5% | 8.2% | 3.4% | 10.8% |
| Harmonic | 23.0% | 9.9% | 3.2% | 6.3% | 3.6% |
| BAM | 37.7% | 5.7% | 9.8% | 4.6% | 17.6% |
| other | 4.5% | 4.0% | — | — | 0.5% |

- No landing to a leader 30 ms or more away has ever come in under 50 ms.
- **Unfronted near leaders (under 15 ms) are 20.7% of slots.** They are the only class with landings under 30 ms.
- DoubleZero: 52.4% of slots have a leader on DoubleZero unicast (IBRL). Only 12.9% advertise a transaction address on
  it, because BAM and Harmonic fronts are not on DoubleZero.

## Why BAM is about 3x slower
- **A BAM leader advertises the BAM node's address**, not its own. So every route to that leader (Helius, Bolt,
  Astralane, direct, bundles) goes through the BAM node.
- **BAM runs batch auctions** every 25–50 ms. Bundles and plain transactions compete on one priority score within a
  batch; arrival time decides across batches.
- **We miss the current slot more often on BAM leaders:** 7 of 11 BAM landings came after the slot that was current at
  send, against 2 of 9 on non-BAM leaders. BAM drops packets that arrive too late in the rotation. In the next slot,
  BAM runs us about 95 ms in.
- **Best path into a BAM leader today: a same-slot Jito bundle**, p50 59 ms on near BAM leaders. Worth testing:
  - a direct QUIC send to the BAM node, with a priority fee in the top 10%:
    - Frankfurt `198.13.141.173:5010`
    - Amsterdam `63.254.167.199:5010`
    - London `64.130.46.155:5010`
  - Astralane's claimed BAM route.

## Ranked plan
Items 1–4 change send paths, so each needs the owner's OK.

1. **Slot-aware targeting plus next-leader copies.** Small effort, no cost.
   - Estimate time left in the current slot. With under about 40 ms left, treat the send as next-slot.
   - In the last slot of a leader's 4-slot window, also send a copy to the next leader. The nonce makes the copies
     mutually exclusive.
   - Removes the later-leader tail and moves sends from the ~176 ms class toward the ~55 ms class.
2. **Route by front.** Expected 20–35 ms median on unfronted near slots.
   - Unfronted near leaders: a warm direct QUIC copy next to Astralane.
   - Harmonic leaders: Astralane and Bolt, accepting about 50 ms.
   - Keep connections warm; one cold connect cost 276 ms.
3. **BAM path:** a direct QUIC copy to the BAM node and/or a Jito bundle copy. Maybe 110 → 60 ms, not under 50 ms.
4. **Stake for the direct path.** Mostly cuts drops and the slow tail.
   - Free through a partner validator, or Everstake at $500/month (RPC) to $1,300/month (QUIC).
5. **A/B test Helius Sender Max against `swqos_only`.** Max's top-of-block tip buffer may hold transactions.
6. **Regional sender boxes** (US, Tokyo) for far leaders. Large effort.
7. **DoubleZero IBRL and regional block engines.** About zero gain for European leaders.

**Under 50 ms median:**
- **Realistic for unfronted near leaders** (items 1 + 2), where we already see 19–26 ms.
- **Borderline for Harmonic** leaders, at about 50 ms.
- **Not possible for BAM** until its batching changes or the maintenance window arrives.

**How to measure:**
1. Join `copies.t_sent` to the first arrival in `txarr`.
2. Take the leader from `leaders.jsonl`.
3. Classify the front from `tpu_quic` and `tpu_shared_by`.
4. Get the slot offset from `slots-feed` and the position in the slot from `poh.log`.
5. Report the median and share under 50 ms per front, near or far, and same or later slot.

## Caveats
- fastL1 has n=20.
- The fronts were read on a later day than the 284 bundles.
- Send → landed includes the return trip.
- BAM's batch cadence, each Harmonic validator's builder mode and Bolt's delivery are published claims or unknown.
