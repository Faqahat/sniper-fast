# Analyst C (exits) — his edge = riding the follower wave; for us, a faster "wave exit" (10-28 ~03:20 PKT)
Saved by the main session from the agent's reply. Code: this folder (x0–x18, xlib.py, xsim.py). Tables: /home/moiz/sniper-data/haqq_dissect/exit/. Read x3, x8, x13, x14, x15, x16 and x18 first.

## His sells (MEASURED, 6 days, 20,344 non-DEAD positions)
- **Lot by lot:** 89.6% of sells close exactly one lot; 6.9% are 50% partials, and those lose. Never before 2 slots.
- **Hold time:** 2–14 slots made +188 SOL; 15–39 slots −30. Past 15 slots, exits fall on a timer menu.
- **Wave rule:** from 2 slots after his buy, sell at the first 1 s gap with no outside buy (cap 20 s). It gives +189.7 against his own exits at +222.9 (85%). The best fixed timer gives +138.6; take-profit rules at most +125.8.
- **B's split (%/SOL, lots bought above 1.05× post-dump):**

  | Lots | His exit | 5-slot timer | Wave rule |
  |---|---|---|---|
  | Added to later | +3.97 | +1.26 | +4.54 |
  | Never added to | −0.05 | −0.46 | +0.10 |

  So his after-entry edge is the wave exit, and it is causal.
- **Fragile:** with 10% fewer followers his exits go from +222.9 to −81.4.

## On OUR fills (exit replay matches realized to 0.04 mSOL/fill at the actual sell position)
- **Sell landing (MEASURED):** reactive sells land a median 59 ms after the trigger; timer sells ~93–103 ms after the decision slot starts.
- **The bounce peaks** ~250 ms after our pre-send entry and ~400 ms after regular entries.

| Fills | Current exit | Sell 200 ms after fill | Wave exit |
|---|---|---|---|
| Pre-send, all 1,143 | +7.48 | +10.05 | **+10.93** (150 ms gap, 1 s cap) |
| Pre-send, 10% fewer followers | +3.81 | +6.71 | **+7.32** |
| Regular, all 596 | +2.63 | +5.34 | **+5.85** (300 ms gap +6.22) |
| Regular, 10% fewer followers | −0.93 | +3.40 | **+3.67** |

**Walk-forward vs current exit:**

| Fills | Gain [90%] | Per fill | With 10% fewer followers |
|---|---|---|---|
| Pre-send | +3.09 SOL [+1.98..+4.20] | +2.7 mSOL | +3.19 |
| Regular | +2.23 [+0.87..+3.66] | +4.5 mSOL | +3.25 |

Positive on every test day. **His own exit style at his scale loses on our fills:** we enter at 29–55 ms, he at ~80 ms, and he is one of the followers we sell to.

## Engine change proposed (needs owner OK)
1. **Pre-send:** a wave exit. From 150 ms after the fill, hold while an outside buy landed within the last 150 ms; sell at the first 150 ms gap, 1 s cap. Simple fallback: sell 200 ms after the fill, which captures ~75% of the gain.
2. **Regular:** the same with a 300 ms gap and 2 s cap.
3. **Mechanics:** track the last outside-buy time per open position (pslive.rs ~1246, dipmode.rs ~640) and check every ~10 ms. Watch pre-send in-flight tries landing after an earlier sell (the dip19 rounds handle it).

## MAIN-SESSION INDEPENDENT CHECK (verify_main_v1.py, own code; only the tape is shared)
Method:
- the value of our exact tokens at the curve state at decision + 59 ms;
- capped at our real sell position;
- pre-send vs regular by the buy's CU limit;
- curve P&L only, tx costs excluded.

| Fills | Actual | 100 ms | 200 ms | 300 ms | 400 ms | Wave |
|---|---|---|---|---|---|---|
| Pre-send 1,144 | +7.86 | +8.49 | **+9.77** | +8.85 | +8.05 | +9.62 |
| Regular 498 | +2.58 | +3.35 | +3.78 | +3.93 | +3.82 | **+4.12** |

**Pre-send per day (actual → wave):**

| Day | Actual | Wave |
|---|---|---|
| 10-25 | +0.59 | +0.66 |
| 10-26 | +1.56 | +2.26 |
| 10-27 | +5.04 | +5.95 |
| 10-28 | +0.68 | +0.75 |

The wave exit is better on all 4 days.

**Verdict: CONFIRMED in direction, about half the size.** Pre-send gains +1.6 mSOL/fill (the agent said +2.7); regular gains +3.1 (the agent said +4.5). The difference is likely sell-landing variance and the agent's exact re-pricing. At ~600 pre-send fills/day that is ≈ +1.0..1.6 SOL/day.
