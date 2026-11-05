# TEN — the path to 10 SOL/day (FILTERS-3, 11-03, PKT)

(Saved by the coordinator from the TEN agent's final message. DEV 74.3 h = 10-29 07:31 → 11-01 12:00; VAL 20.6 h = 11-01 12:00 →
11-02 08:36 incl. the attack. Holdout not opened. FROZEN.json + score.py (sha256 8bde9ac1…6440b43) in this folder; tables in
/home/moiz/sniper-data/filters3/ten/.)

## Verdict
10 SOL/day is NOT reachable with what the data supports today. Even with near-perfect loss filters (assumed) plus two
unproven levers: DEV ≈ +9.8/day, VAL (today's market) ≈ +6/day.

## Today's money (proven, live realized)
| | DEV | VAL |
|---|---|---|
| all | +6.43/day, win 52%, w/o top 5 +5.73 | −1.09/day, win 41%, w/o top 5 −2.63 |
| T2 / re-arm | +4.48 / +1.96 | −1.12 / +0.03 |
| wins | +14.8 | +16.8 |
| small / big losses | −3.2 / −5.1 | −7.0 / −11.0 |
Wins did not drop DEV→VAL; losses doubled. VAL without the attack window +1.50/day. Trades with 8+ later buyers ≈ +8.4/day on
both; trades with 0–3 lose 3.8 (DEV) to 10.0 (VAL)/day (post-hoc, not usable at signing). No band of whale %, whale SOL, dip,
age, curve size or hour holds on both. Failed-try fees ≈ 0.65 SOL/day are not in realized.
Loss-cut ceilings (not rules): no-follower trades cut → DEV +8.05 / VAL +2.20; every trade with < 4 followers → +10.3 / +8.9;
every loser → +14.8 / +16.8.
Skips cost nothing: every live skip is right or ≈0 (create_slot −1.79 / −5.63 per day, QUIET −0.46 / +0.06, age-1 −0.24 /
+0.87, w/o top 5 −0.33).

## Levers that add money (ESTIMATES)
- SIZE15 (frozen): T2 at 1.5× size when the token had >= 15 trades in the 60 s before the trigger. Per-position tape replay
  (exact at live size on 2,270 positions). Depends on price-out of followers (beta 3 frozen, from the 10-27 size study):
  DEV +1.24 / VAL +0.45 per day; no price-out +2.06 / +1.73; heavy −0.32 / −2.81; 20% fewer buyers +0.30 / −0.57.
- WIDE5 (frozen): whale threshold 5% (wide shadow 5–6% windows, token age >= 2, drop if a live window within 12 slots):
  DEV +0.82/day (w/o top 5 +0.33), VAL +0.50 (w/o top 5 −0.54). 3–4% loses both; 4–5% mixed.
- More windows: re-arm age 142–200 +0.48 DEV (top-5 driven) ≈0 VAL; re-arm with no holder −0.49 / −1.48; 20-slot T2 window
  −0.27 / −0.08. → no.
- Exits: keep 200 ms. Hold-while-buying +3.0 on 986 DEV fills / +1.5 on 98 VAL, but −2.5 DEV with 20% fewer buyers.

## Ladder (SOL/day; w/o top 5 in brackets)
Loss-filter step = ASSUMED best case: remove every trade with no other buyer within 10 slots + the attack.
| | today | + loss filters (assumed) | + WIDE5 (est) | + SIZE15 (est) |
|---|---|---|---|---|
| DEV all | +6.43 (+5.73) | +8.05 (+7.35) | — | +9.83 (+9.13) |
| DEV r41 + r42 part (33.5 h) | +6.30 | +7.55 | +8.37 | +9.39 |
| VAL | −1.09 (−2.63) | +4.79 (+3.25) | +5.29 (+3.63) | +5.97 (+4.31) |
Per run today (DEV): r37 +6.38, r38 +3.51, r39 +3.02, r40 +7.64, r41 −9.35, r42-DEV +6.95.

## What is missing for 10+/day
- Followers: all profit is follower money; with 20% fewer later buyers DEV ≈ +0.9/day, VAL ≈ −9.4 (replay).
- Landing speed: on armed-but-unfilled windows, the replay fills right behind the dump for ≈ +14..+25 SOL/day of replay money
  per trade type — UNCALIBRATED upper bound (instant landing, nobody ahead), but the only large pot found.
- Not capital: size is capped by pricing out followers.

Holdout pass bar (FROZEN.json): lever > 0 and > 0 w/o top 5; SIZE15 no worse than −0.5/day under heavy price-out.
