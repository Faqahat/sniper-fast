# Why paper said profit and live breaks even (10-25 PKT, 4 studies)

The owner's question: "the paper numbers at our speed are nothing like live; we should have made 10 SOL in 30 h and made < 0.5".
Four independent read-only studies were run on the live runs (FRA 9–15, AMS 9–14, 309 buys) and 3 days of recording.
MEASURED unless marked INFERRED.

## Verdict
- **The paper model is right.**
  - Re-run with our REAL landing times, it predicts live within noise: −0.44 SOL vs live −0.37 on the same 309 buys. Entry tokens are exact on all 128 checkable fills, and the guard call matches on 308 of 309.
  - Checked on 125,918 real dip buys by 75 fast bots: it reproduces their real P&L to within 0.02 mSOL per trade.
- **The forecasts assumed the wrong speed.**
  - They assumed every buy lands 35 ms after the dump.
  - Real (same block-position clock): median 58 ms, the middle half 33–101 ms; 22% land in a later block; only 29% within 35 ms.
- **Late exactly where the money is.**
  - On dumps that bounce, rivals land first and our +5% guard blocks us.
  - We filled 29% of the best third of dumps and 65% of the worst third.
  - Our fills are about zero even at 35 ms. The paper's profit sat on the dumps we failed.
- **Our engine is not slow.**
  - We send 2.7 ms after seeing the dump (p90 7.3).
  - 94% of the time is after the send: feed delay plus relay → leader → block.
  - The rival buys that beat us usually paid a LOWER priority fee: arrival decides the order, not the fee.
- **Costs eat the rest.**
  - A round trip costs us 4.3–4.9 mSOL of transaction costs. Most fast bots pay 0.2–2.4; haqq pays 0.8.
  - Pump fees are 85% of our fills' gross gain.
- **The profit depends entirely on the ~75 fast bots buying after us.** If none of them bought, every pick set loses 3–4.6 SOL over 61 h.

## Median landing after the dump (feed clock)
| Leader | Us | First rival | HkQ7 | haqq |
|---|---|---|---|---|
| BAM | 29 ms | 18 | 21 | 33 |
| Harmonic | 41 ms | 27 | 34 | 47 |
| Jito | 54 ms | 26 | 32 | 42 |

How often our buy passes the guard by landing time: 10 ms → 85–93%, 20 ms → 76–81%, 35 ms → 51–61%, 50 ms → 38–47%. We land at a median 40 ms on the feed clock, which predicts about 43%; we filled 42%.

## What speed is worth
Corrected replay, both servers, today's exit (~0.85 s, no stop-loss, 0.35 SOL), SOL per day. One night of data: use it to rank options, not as a forecast.

| Our landing | SOL/day |
|---|---|
| as now | +1.1 |
| 5 ms faster | +4.9 |
| 10 ms faster | +6.4 |
| 20 ms faster | +8.7 |
| first in line after every dump | +13 |

## What to do (ranked; send-path or engine changes need the owner's OK)
1. **Land faster after the send** (SPEED_TRUTH). Failed buys each fix would have rescued, out of 180 (INFERRED):
   - same-slot send leg 10 ms faster: 45–49 (20 ms faster: 70–73);
   - Jito send leg brought to our BAM speed: 23–25;
   - Harmonic send leg brought to our BAM speed: 24–25;
   - fire on the shred feed instead of waiting for the executed feed: 13–21;
   - spills landing at the end of the dump's slot: 16;
   - skip Rakurai leaders (7 of 8 went to the next slot).
2. **Pre-send** (the extreme version of landing first): live probe started on Amsterdam 10-25 (dry run first). Paper shadow: +2.3–3.0 SOL over 2 h.
3. **Cut cost per trade** (H2H, MODEL_CHECK). Today: sell tip 0.001 with priority 0.0006, buy priority 0.0005. haqq: tip 0.0002, priority 0.00012. Fees can change landing order, so test on one server.
4. **Exits that ride winners** (MODEL_CHECK, H2H).
   - The bots' own exits beat our c4 exit by 5.3 mSOL per trade.
   - On crowded dumps, haqq's longer hold earns +2.36 SOL where our exit makes 0.
   - Study an exit that holds winners on crowded dumps only.
5. **Trade more dumps** (H2H: haqq ~180 dips/h vs our ~21 fires), but only once a trade clears its costs.

## Not the cause
- The follower model (small, cancelling biases).
- Feed gaps, the near-leader filter, model pick differences.
- A guard that is too tight: a looser guard loses money at our speed (guard sweep, 61 h).

## Sources
- `ops/dip/recon/RECON.md` (replay vs live, trade by trade).
- `ops/dip/speed/truth/SPEED_TRUTH.md` (where the time goes).
- `ops/dip/modelcheck/MODEL_CHECK.md` (model vs 125,918 real bot trades).
- `ops/haqq/H2H.md` (haqq vs us on the same dumps).
- `ops/strategies/dipdetect/dd24_guard_eval.py` (guard sweep).
