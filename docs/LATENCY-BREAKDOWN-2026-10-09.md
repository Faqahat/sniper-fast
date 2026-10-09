# Per-stage send latency, 3 real big gaps (fastL1, 2026-10-07)

All times are **measured** from the run's own records (`attempts.stages`, `copies.jsonl`) plus the signature→first-arrival
match in our shred feeds (`fastl1_landed.json`). Each gap was sent as 3 durable-nonce copies at once (Astralane, Helius
Sender Max, Bolt); only one copy can land. Jito-bundle copies were also built on band ≤2 but these are band 3–4.

ms are relative to **first shred of the trigger swap (t=0)**.

## Attempt 19 — gross 1.9M lamports, 0.05 SOL, Jito leader (Amsterdam), WON by Astralane
| Stage | At (ms) | Step (ms) | Note |
|---|---|---|---|
| shred received | 0.000 | — | trigger swap seen in DoubleZero |
| commit / engine | 0.151 | +0.151 | |
| opportunity priced (detected) | 0.515 | +0.364 | |
| decision made | 0.516 | +0.001 | |
| build start | 0.557 | +0.040 | |
| built | 1.080 | +0.524 | ATA create/close + encode |
| signed | 1.100 | +0.019 | |
| enqueued (Jito queue) | 1.141 | +0.042 | |
| **send started** | **1.182** | +0.041 | astralane first |
| provider ack | — | — | astralane 0.607, helius 0.474, **bolt 0.466** |
| **landed on chain** | **~26.7** | **+25.6** | won by Astralane, **same slot** |

## Attempt 90 — gross 5.3M lamports, 0.05 SOL, Jito leader (Frankfurt), WON by Helius
| Stage | At (ms) | Step (ms) |
|---|---|---|
| shred received | 0.000 | — |
| commit / engine | 0.068 | +0.068 |
| opportunity priced | 0.133 | +0.065 |
| decision | 0.133 | +0.001 |
| built | 0.877 | +0.700 |
| signed | 0.906 | +0.029 |
| **send started** | **1.217** | | 
| provider ack | — | **bolt 0.294**, helius 0.392, astralane 0.453 |
| **landed on chain** | **~81** | **+79.9**, won by Helius, **same slot** |

## Attempt 23 — gross 7.6M lamports, 0.198 SOL, BAM leader (Amsterdam), WON by Bolt
| Stage | At (ms) | Step (ms) |
|---|---|---|
| shred received | 0.000 | — |
| commit / engine | 0.240 | +0.240 |
| opportunity priced | 0.683 | +0.443 |
| decision | 0.684 | +0.002 |
| built | 1.334 | +0.650 |
| signed | 1.393 | +0.059 |
| **send started** | **1.511** | |
| provider ack | — | **bolt 0.495**, astralane 0.692, helius 7.985 |
| **landed on chain** | **~177** | **+175.6**, won by Bolt, **NEXT slot (+1)** — sent 134 ms into the current slot |

## Summary

| Phase | Time | Measured? |
|---|---|---|
| Detect → price → decide (shred to decision) | **0.1–0.7 ms** | yes (stages) |
| Build + sign + enqueue | **0.5–0.9 ms** | yes (stages) |
| Send start | **~1.0–1.5 ms** after shred | yes |
| Provider ack (received, not forwarded) | bolt 0.3–0.5, astralane 0.45–0.7, **helius 0.4–8.0 (variable)** | yes |
| **Send → landed on chain** | **25.6 / 79.9 / 175.6 ms** | yes (sig in our shred feeds; incl. ~1–7 ms return trip) |

**Biggest bottleneck: send → landed.** It is 25–176 ms, which is **95–99% of the whole wall clock**. Everything on
our side — detect, price, build, sign, send — is **under 1.5 ms combined**. Detection and building are not the problem.

**Which path is fastest:**
- **Ack:** Bolt is fastest and most consistent (0.3–0.5 ms). Helius is sometimes very slow (up to 8 ms).
- **Landed (the one that matters):** depends on the leader. Across all 20 fastL1 landings: Astralane 8, Bolt 8, Helius 4.
  Astralane won 5 of 9 non-BAM leaders (both sub-30 ms landings); Bolt won 6 of 11 BAM leaders. **No single path wins;
  it tracks what fronts the leader.**

**Target slot vs actual:**
- Attempts 19 and 90 landed in the **current slot** (fast, 26 and 81 ms).
- Attempt 23 was sent **134 ms into the slot** to a **BAM** leader → rolled to the **next slot** → 176 ms. Missing the
  current slot roughly tripled the time.

**Why the delay (attempt 23):** late in the slot + BAM leader (batch auction + advertises the BAM node, not its own
address). This is the dominant cause of slow landings across the run.

## What we CANNOT measure directly (not guessed)
- The exact instant the leader admitted/executed our tx. We infer it from when our signature first reappears in our own
  shred feeds (send→landed), which includes the ~1–7 ms return trip.
- The landed time of the **losing** copies. Durable nonce means only one copy lands; the others are consumed, so we
  cannot see which provider *would* have landed and when on the same gap.
- Provider-internal forwarding time. "Ack" is when the provider received the tx, not when it reached the leader.
- All three of these big gaps were **phantoms at band 4** in a separate check (trigger swap failed), but these three
  (19/90/23) are real landings used only for the latency measurement.
