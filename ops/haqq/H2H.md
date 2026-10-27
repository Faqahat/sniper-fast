# haqq vs us on the SAME dumps — why it makes money and we don't

10-25 PKT. Read-only, local recording only. Our live runs FRA 9–14 and AMS 9–14, 10-24 16:47 → 10-25 06:22 PKT (13.2 h of live time).

Labels: MEASURED = counted from the data. INFERRED = my reading.

Clock: block position, slot × 212 ms + index ÷ block size × 212 ms. It is the same clock used for haqq in PATHS.md.

## 1. Verdict

Same 13.2 hours: **haqq +16.3 SOL on 4,415 lots. Us −0.33 SOL on 116 fills and 162 failed attempts.** All MEASURED. Ranked by SOL:

1. **Coverage (selection × scale).** haqq made +18.5 SOL on 2,289 dip lots on dumps we never fired at (+8.1 mSOL each). On the 126 dumps we both went for it made +1.9. It buys about 179 dips an hour; we fire on about 21 and fill about 9.
2. **Costs.** Our fills earned +0.24 SOL before tx costs. Tx costs were 0.57 SOL (4.9 mSOL per fill, failed attempts included). haqq pays 0.8 mSOL per lot. At haqq's cost level we would have made about +0.17 SOL instead of −0.33.
3. **Adverse selection.** We fill the dumps the fast crowd doesn't want, and fail the ones it does.
   - haqq bought only 28% of the dumps we filled, and lost money on them (−7.9 mSOL per lot).
   - It bought 57% of the dumps where we failed the +5% guard, and made +23.6 mSOL per lot there.
4. **Exit, on crowded dumps only.**
   - On the 93 crowded dumps haqq bought, its entry spot with our 1.3 s exit makes about 0 (+0.02 SOL). With its own exit timing it makes +2.36.
   - On quiet dumps our fast exit is better: on the 33 dumps we both filled, we made +0.64 and it made −0.26.
5. **Speed is NOT the gap against haqq, but it is against the instant bots.**
   - All our attempts land a median 52 ms after the dump, the same as haqq. On shared dumps: us 57 ms, haqq 56 ms, haqq first 47% of the time.
   - On the dumps we fail, an outside buyer landed within 25 ms of the dump 69% of the time. Being first after the dump on those 162 dumps would have been worth up to +6.0 SOL (upper bound).
6. **Price tolerance alone does not help us.** At our real landing spot, accepting the run-up loses money with any exit we can run:
   - our exit: −0.5 to −2.0 SOL;
   - fixed 6–30 slot holds: −0.2 to −1.9 SOL.
   - It only pays on the dumps haqq picked, sold at haqq's own exit slot (+1.6 SOL).

**What to change first** (INFERRED; send-path and engine changes need the owner's OK):

1. **Cut cost per trade.** It is the cheapest fix and flips our sign.
   - Sell: tip 0.001 and priority 0.0006 against haqq's 0.0002 and 0.00012.
   - Buy priority: 0.0005 against 0.00012.
2. **Keep the +5% guard and the 1.3 s exit** for the dumps we can fill.
3. **Then widen coverage** (more parallel positions, more dumps per hour), but only for dumps that still clear costs. haqq's per-lot edge is small (+3.7 mSOL over all lots, +8.1 on dips), so it only works at low cost and high count.
4. **The profitable crowded dumps need a much faster landing** (first after the dump), not a looser guard.

## 2. Evidence

### Our attempts on the same clock as haqq (MEASURED, 278 fires)

| | n | landing after dump, p25 / 50 / 75 ms | same slot | price at landing vs post-dump (median) |
|---|---|---|---|---|
| all attempts | 278 | 33 / 52 / 90 | 77% | 1.067 |
| fills | 116 | 29 / 44 / 68 | 77% | 1.022 |
| failed (160 × 6042, 2 other) | 162 | 39 / 63 / 101 | 77% | 1.113 |

- Every fire landed a tx, either a fill or a failed tx. None went missing.
- FRA median 56 ms, AMS 46 ms.
- By leader client (median ms, fill rate):

| client | median ms | fill rate |
|---|---|---|
| BAM | 39 | 48% |
| Harmonic-Agave | 49 | 53% |
| Firedancer | 66 | 27% |
| Harmonic-FD | 69 | 31% |
| Jito | 72 | 36% |

### haqq on our fired dumps (its buy within 400 ms, before the next ≥ 1 SOL sell; MEASURED)

| our result | dumps | haqq filled | haqq failed | haqq absent | haqq lot P&L there |
|---|---|---|---|---|---|
| we filled | 116 | 33 (28%) | 5 | 78 | −0.26 SOL (−7.9 mSOL/lot, 30% win) |
| we failed | 162 | 93 (57%) | 15 | 54 | +2.19 SOL (+23.6 mSOL/lot, 42% win) |

- haqq's price at its fill vs the post-dump price: 1.058 (median) where we filled; 1.096 where we failed (p90 1.24).

### Who landed between the dump and us (MEASURED)

| | buyers ahead (median) | SOL ahead (median) | nobody ahead | haqq ahead | a buyer within 25 ms of the dump ahead |
|---|---|---|---|---|---|
| our fills | 1 | 0.49 | 27% | 8% | 39% |
| our failed | 4 | 2.20 | 0% | 32% | 69% |

### Counterfactuals on our 162 failed attempts (0.35 SOL, our tx costs, our own trades taken out of the curve)

| scenario | fills | P&L SOL |
|---|---|---|
| at our real landing spot, guard 1.10 | 65 | −0.54 |
| at our real landing spot, guard 1.17 (haqq's p95) | 120 | −1.37 |
| at our real landing spot, no guard | 162 | −1.95 |
| landing where haqq landed, guard 1.05 (93 dumps haqq filled) | 15 | +0.38 |
| landing first after the dump, guard 1.05 | 162 | +5.99 (upper bound) |

### The 93 crowded dumps we failed and haqq filled: entry spot × exit (0.35 SOL, our costs)

| entry spot | haqq's exit slot | our exit (5 slots / SL −10%) |
|---|---|---|
| haqq's spot | +2.36 | +0.02 |
| our spot (no guard) | +1.57 | −1.11 |

- haqq's real result on these: +2.19 SOL.
- Fixed holds at our spot on these 93: −0.11 (6 slots) to +0.44 (30 slots).
- The 69 failed dumps haqq skipped or failed: every fixed hold loses (−0.6 to −1.8 SOL).
- INFERRED: haqq's exit TIMING matters on crowded dumps. Its sells come just before small drops: the replayed value falls 0.5–0.6% of cost in the next 1–3 slots, against +0.1–0.2% at random moments. This study cannot tell foresight apart from other bots copying its sells.

### Dumps we both filled (33; MEASURED replay)

- Real: us +0.64 SOL (mean +3.2%), haqq −0.26 (mean −4.2%). haqq landed first on only 21% of these.
- Our entries sold at haqq's exit slot: −0.05. haqq's spot sold at our exit slot: −0.07; at its own: −0.47.

### Selection and scale in the same 13.2 h (MEASURED)

| haqq lots | lots | P&L SOL | mSOL/lot | win |
|---|---|---|---|---|
| on dumps we fired at | 126 | +1.93 | +15.3 | 39% |
| dips we never fired at | 2,289 | +18.51 | +8.1 | 40% |
| non-dip entries | 2,000 | −4.12 | −2.1 | 35% |
| total | 4,415 (333/h) | +16.31 (+29.6/day) | +3.7 | |

- Dips we never fired at, by its size: 0.40 → +8.8 SOL (769 lots), 0.30 → +5.8 (698), 0.27 → +0.8, 0.49 → +1.0.
- By token age: < 2 s +4.8, 2–5 s +9.9, 5–30 s +6.7, 30 s or older −2.9.
- Us: 278 fires, 116 fills (8.8/h, one open position per server), −0.33 SOL; −2.8 mSOL per fill all-in.

### Costs in the same hours (MEASURED)

| | per buy | per sell | per failed attempt | failed share of attempts | all-in per trade |
|---|---|---|---|---|---|
| haqq | 0.325 mSOL | 0.325 mSOL | 0.017 mSOL | 16% | 0.79 mSOL/lot |
| us, runs 9–10 (one tx, all tips) | 2.71 | 1.60 | 0.51 | 57% | |
| us, runs 11–14 (nonce fan-out) | 1.51 | 1.60 | 0.51 | 60% | |
| us, all | 2.71 | 1.60 | 0.51 | 58% | 4.94 mSOL/fill |

- Runs 11–14: gross +0.217, tx 0.179, failed fees 0.060, net −0.022 SOL. At haqq's cost level: about +0.18 SOL.
- Runs 9–10: gross +0.027, net −0.307.

## 3. Caveats

- The replay is optimistic for our own exits: our 116 fills replayed with our rule give +0.31 SOL; the real result is −0.23. So treat replay SOL as relative, not absolute. Run 10 also used an 18-slot limit.
- The "first after the dump" scenario ignores the instant bots that really landed there. It is an upper bound on what speed is worth, not a plan.
- haqq's lot P&L uses its real fills, sizes (0.25–0.40) and costs. The entry-spot × exit tables use 0.35 SOL and our costs.
- Small samples: 33 shared fills, 93 crowded dumps.
- Scripts: `ops/haqq/h30_h2h.py` (matching), `h31_decomp.py`, `h32_scale.py`, `h33_contested.py`, `h34_policy.py`, `h36` (costs, run inline).
- Outputs: `sniper-data/haqq/h2h_fires.json`, `h31.txt` … `h36_costs_by_run.txt`.
