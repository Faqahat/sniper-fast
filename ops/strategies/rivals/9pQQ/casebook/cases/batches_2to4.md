# Cases 17–64 — batches 2 (10-28/29, V1), 3 (10-31/11-01, V3/V3b) and 4 (10-29/30, V2)
Each token: full tape built (tapes/<run>/<mint>.{tl.txt,ev.jsonl.gz,digest.txt}); per-token verdicts computed by code/c15_tokentest.py
(criteria in the script) and checked by reading the one-line-per-trip view (code/c6s.py). Only what is new is written here.

## New or sharpened observations
- **LAUNCH first entries (age 9–40) are a high-variance lane**: 47S1AcwJ age 9 behind 1.7+1.5 SOL sells in a 13.9 SOL inflow → −49 % in 2 s;
  CTMQ8eqh age 18 behind a 3.9 SOL buy after a 34 SOL holder dump → −68 %; GQJsb9ti age 13 +54 %; 6y3kstwt age 19 +270 % (893 slots);
  8FkiARd2 age 59 +187 % (72 slots); 4pDNmhxT age 81 +194 %. Entries are behind big trades in a frenzy (|ch10| 15–90 %). Exits fast.
- **Re-entry farming on busy tokens (V3, 4pDNmhxT 30 trips, 6StLoZfc 25, GqgEiwuu 20, 3qxzWWbk 23, BqjiKPhH 16)**: identical soft profile
  on every token: trigger 2–9× bigger than skipped (0.31–0.93 vs 0.10–0.25 SOL), more often a BUY (0.56–0.87 vs ~0.5), |ch10| larger
  (5–11 vs 1.5–6.6 %), entries below the 450-slot high. Exits: on an outside SELL 0.55–0.81 vs base 0.36–0.45, after a buying pause
  (since_ob at sell 5–16 vs 1–2). GqgEiwuu: 8 of 20 exits are burst exits (sells into ≥2 SOL of buys in 3 slots, in profit).
- **Wake-up lane on dead tokens** (EfZzaPTZ, BWVBerwH, 47S1… no; EY5Qvvgx, vRJNbvpd, HkMDiFM3, 4WP3p6Y7, FHoWaFeU, PH5bJmDZ): first trade
  after a long silence (often a single 0.1–1.5 SOL buy) → buy; holds run to the cap (300 s / 600 s) with 0–20 outside trades; P&L ≈ 0 to −0.04.
- **V1 (10-28/29)** looks like V3 for entries; caps 4–7 per busy token (300 s), exits otherwise on outside sells after pauses.
- **Rugs it walks into** (one-trip big losers): BtAkqmnA −65 % (36 s), 6y3kstwt T2 −76 %, FhP8kUkX T3 −79 %, A3A7cxPN −0.47 SOL over 3 trips.
  No sign of a rug filter (HK05).
- **Why it stops on a token (scale, 10-30 + 10-31, trips followed by ≥5 outside ≥0.5 SOL buys in the next 1,500 slots)**:
  P(another trip) ≈ 0.90–0.93 after a win and 0.89–0.90 after a loss (no tilt), ~0.85 on the first trip, ~0.95 after 5+ trips;
  by exit MC: 0.83–0.85 below MC 60, **0.94–0.99 at MC 60–200, 0.88–0.90 at 200–300, 0.40–0.55 above MC 300**.
  MC 300 ≈ curve vsol ~98 SOL; graduation is at MC ~411. → "quits while busy" = the curve ceiling (vsol ≥ ~80–100), not boredom.
