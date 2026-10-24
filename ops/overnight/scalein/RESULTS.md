# haqqiUUX-style scale-in replay (10-24 PKT) — scalein.py / report.py / scalein.json
Every action lands 60 ms after its decision (also 35 / 75). 0.3 SOL first buy, +0.3 per add on >= A SOL outside buying, exit on stall
(no >= 0.1 SOL buy for G), SL, or cap. TRAIN < 10-23 06:00 PKT (27 h), TEST to 18:31 (13 h), LIVE = run R3 (21 h).
- Entries = haqqiUUX's own decisions (we act 60 ms after its trigger), 8,778 tokens:
  best (chosen on TRAIN) = NO adds, exit when buying stalls 1.5 s, SL -25%, cap 60 s: TRAIN +7.4 (+0.27/h), TEST -2.2 (-0.18/h), LIVE +10.5 (+0.50/h), PF 0.93-1.16, win 34-37%.
  at 35 ms: TEST +1.9, LIVE +17.7; at 75 ms: TEST -3.8, LIVE +7.4. Quick single exit (6 slots) ~0.
  ADDING HURTS at our speed: 3 adds -12 / -30 / -2; 8 adds -52 / -52 / -45 (TRAIN / TEST / LIVE).
- Entries = simple momentum (token 0.4-5 s, outside buy >= 1 SOL): loses at every setting (-1 to -1.6 SOL/h TRAIN/TEST).
- haqqiUUX itself made +60 SOL on the curve on the LIVE tokens: its edge = earlier fills (median 15 ms after the trigger) + its own
  add / exit decisions (not reproducible by a simple flow rule).
