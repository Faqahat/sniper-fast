# sssssDdM: what it does, and can we copy it (10-24 ~21:55 PKT)

Wallet sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d. Read-only study, agent + Haiku 5.5 ($0.09). MEASURED unless marked.
Outputs: /home/moiz/sniper-data/strategies/sssss/.

## Bottom line
- **What it is:** a buy-burst momentum scalper on busy curves, one of a fleet of 4 "sssss…" wallets. About +75–90 SOL a day
  on R2 and R3.
- **Where the profit comes from:** ~1% of trips, about 45 "runners" a day, held 1.5–2.5 min and sold near the top.
- **Its edge is landing first plus exit timing, not token choice.** Its failed attempts do no better than random moments in
  the same tokens.
- **Verdict: we can't run it.** Even with its exact trades known in advance and one position at a time, it makes only +3 to
  +17 SOL a day.

## Fleet
- sssssDdM trades about 0.9 SOL; ssssswdk about 0.37 SOL (also about +154 SOL / 46 h); sssssCUP and sssssyv2 trade the V2 curves.
- DdM and wdk act as a pair: wdk already holds the token at 55% of DdM's entries, and sells just before DdM in 38% of exits.

## Strategy
- **Tokens:** curve 38–71 SOL (median 49), age 12 s to 41 min (median 2.7 min), at least 10 trades so far and a trade in the
  last 1–2 slots. Never the create slot, never mayhem launches, never a token it already holds.
- **Trigger:** a burst of buying inside the current slot. It fires 6.2% of the time when more than 3.7 SOL was bought in the
  slot, against 0.08% when less than 0.02 SOL was.
- **Speed:** it lands about 15 ms (~30 txs) after the last trade, about 33 ms after the biggest buy; 71% of entries are in the
  same slot.
- **Attempts:** 10–11k buy txs a day; 56–58% fail on the price limit (pump code 6002), and 93% of those are never retried.
- **Entry rule (Haiku, checked in code):** "3 or more buys and at least 1 SOL of buys this slot, curve 37–75, at least
  20 trades so far". It catches 39% of its buys, at 7% precision. An ML model reaches AUC 0.93–0.94, but only about 1 in 5
  of its flags are its picks.
- **Size:** always 1.88% of the curve's SOL, a fixed ~3.8% price move. One buy and one full sell (99.9% of trips).
- **Exit:** 85% of sells come right after another wallet's sell (73% in the same slot).
  - A sell is far more likely when the price has fallen 7% or more inside the slot (8–12%) than when it is flat or up (0.2%).
  - No take-profit, stop-loss or timer (INFERRED). Its best exits sell into big buys.
  - Hold: median 21 s, p10 2 s, p90 3.2 min. It holds 4–11 positions at once (max 19).
- **Fees:** priority 1 lamport/CU, a Helius tip on about 26% of landed txs. About 0.0004 SOL per round trip — ours is about
  9× higher.
- **Hours:** 24/7, positive in 15 of 16 three-hour blocks.

## Numbers (P&L before its tx fees)

| Day | Closed trips | P&L |
|---|---|---|
| R1 | 3,147 | +28.4 SOL |
| R2 | 4,138 | +89.4 SOL |
| R3 | 4,799 | +77.3 SOL |
| R4 (partial) | 259 | +5.8 SOL |

- Win rate 41–43%.
- **Top 1% of trips: +59.5 of +89.4 (R2) and +75.3 of +77.3 (R3).**
- Holds of 1 min or longer: +86 / +112 SOL; shorter: +3 / −35.
- Sold into a big buy: +60 / +83; sold after a big sell: −25 / −63.
- The money is at curve 40–60 SOL; at 70+ it is about zero.

## Entry edge or exit edge? (replay at our 35 ms)

| Trigger group (same exits) | R2 | R3 |
|---|---|---|
| Its landed buys | −0.004 / trade | −0.006 |
| Its failed attempts | −0.020 | −0.026 |
| Random moments in the same tokens | −0.025 | −0.025 |

- Failed attempts look like random moments, so the moment choice carries no edge; it just lands first.
- Its real exit timing beats every rule we tested by about +0.02–0.03 SOL per trade.

## Can we run it?
- **Dream case (its exact buys and sells known in advance):**

  | Setup | R2 | R3 | R1 |
  |---|---|---|---|
  | All trades, 35 ms (needs 4–11 positions) | +47 | +42 | +5 |
  | All trades, 50 ms | +37 | +32 | +1 |
  | One position at a time | +17 | +9 | +3 |
  | One position, our sell 35 ms after its exit trigger | +14 | +5 | +2 |

- **Copy-trading its wallet live:** −167 / −214 / −158 SOL a day.
- **What we can build all loses:**
  - ML entries with 13 exit rules: −11 to −121 SOL a day.
  - Haiku's rules: −17 to −145.
  - Its exact entries plus a trained exit model: +4.5 / −13.8 / −33.5.
- **What we would need:** its exit decision, ~15 ms landing, ≤0.0004 SOL per round trip, 5–10 SOL working across 4–11
  positions, and patience — 99% of its trips net about zero.

## My own check (10-24 ~22:30 PKT; ss20_mine.py, results mine_ss20.json)

Owner asked me to check it myself: replay, and see if a strategy can be built on it. All results MEASURED, in SOL per day
(R2 train / R3 test / R1 test). Fee 0.0035 per round trip; 0.001 in brackets.

- **Speed alone doesn't fix it.** Its own entry moments, landing at ITS speed (15 ms), with a 6 s timer and one position:
  −6.6 / −21.4 / −31.9 (with the cheaper fee: +0.5 / −13.2 / −26.4).
  At 35 ms: −13.2 / −29.6 / −36.9.
- **"Cut fast unless it runs, then ride" exits** (cut after 2–10 slots without follow-through, otherwise a 10–20% trailing stop
  for up to 2–5 min, optionally selling into a big buy): every version is negative on both test days, even at 15 ms and with
  the cheaper fee. Best: −0.7 / −22.6 / −16.2 (+3.2 / −18.4 / −13.6 with the cheaper fee).
- **Holding many positions at once** is worse: −40 to −75 SOL a day.
- **Haiku's flow entry rule** ("3+ buys and 1+ SOL bought this slot", curve 37–75) with any exit: −86 to −213 SOL a day.
- **Verdict:** confirmed. Its money is in its specific exits on ~45 runners a day. No public-data exit captures them, and even
  its exact trades held one at a time only make +3 to +17 SOL a day at our speed.
