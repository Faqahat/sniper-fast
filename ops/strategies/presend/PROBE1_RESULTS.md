# Pre-send LIVE probe 1: results (Amsterdam run 16, 10-25 08:49 → ~10:00 PKT)

Engine dip13, `--presend-live`. Settings:
- 0.2 SOL per fill, 4 attempts per slot, limit = latest price × 0.88, deadline +1 slot.
- Route: helius-ps (keyed Helius SWQoS) only.
- Caps: 20 fills, 0.03 SOL of failed-attempt fees. The normal dip bot (IMIT1, no-BAM list) ran alongside.

The probe stopped at the 20-fill cap. Evaluator: `ps13_live_eval.py`; full output in `/home/moiz/sniper-data/presend_live/eval_final.txt`. All numbers MEASURED.

## Verdict
- **Live matches paper.**
  - On the same 118 windows, live filled 20 of paper's 27 fills and never filled where paper didn't.
  - Per SOL: live realized +0.30% vs paper +0.31% (paper's row c, gross).
- **Break-even this hour:**
  - realized +0.012 SOL on 20 fills (9 wins);
  - failed-attempt fees 0.019 SOL;
  - net −0.007 SOL.
- **The margin goes to costs.**
  - The price move averaged about +3.8% per fill (curve P&L +0.153 SOL).
  - Pump fees took about 2.5%, tips and priority about 1%, failed attempts about 0.5%.
  - At 0.2 SOL it nets about zero. INFERRED: at 0.55 SOL it is about +0.8% (~+0.004 SOL per fill), the study's estimate.
- **We are not first after the dump.**
  - Landed a median 53 ms after the crossing trade (p25 32, p10 16).
  - CORRECTED by `instant/INSTANT_BOTS.md`: the "instant bots ahead 79 of 80" count was 14 dumps (our repeated landings counted many times).
    - Of their 19 instant buys: 5 were the seller's own tool (sell + rebuy in one bundle, so no real dip), 3 were pre-senders (FUru6V3L, and our own attempts twice), 11 were chance.
- **The mechanics work.**
  - 99% of 3,808 attempts landed; the limit, the deadline and the double-fill guard all held.
  - A failed attempt costs 5,120 lamports, about 0.001 SOL per fill.

## Numbers
| | Value |
|---|---|
| Windows armed | 118 (skipped: 28 create-slot, 15 overlapping, 5 missing launch accounts) |
| Fills | 20 (16.9% of windows), 190 attempts per fill |
| Exits | take-profit 5, time 13, stop-loss 2 |
| Realized | +0.0119 SOL (median per fill −3.8 mSOL, p90 +30.5, p10 −22.7) |
| Failed-attempt fees / tips | 0.0192 / 0.0040 SOL |
| Net | −0.0073 SOL |

By leader client (realized):

| Client | Fills | SOL |
|---|---|---|
| BAM | 8 | +0.060 |
| Firedancer | 4 | +0.014 |
| Harmonic | 3 | −0.022 |
| Harmonic-FD | 2 | −0.011 |
| Jito | 3 | −0.029 |

## What would change it (INFERRED; needs the owner's call)
1. **Land earlier.**
   - Today one attempt every ~53 ms gives a ~53 ms median.
   - The study's best row needs ~20 attempts per slot: more send capacity (Helius caps 50/s per region) and about 5× the failed-attempt fees.
   - The real instant dip catchers (9K5QgBKa, CZ77onJz, Dk2jdQ93, FNuoWSQc, FUru6V3L) send 26–85 attempts per slot, 650–1,700 failed attempts per fill. 91–100% of what they catch is the creator's own dump on 4–12 s old tokens (`instant/INSTANT_BOTS.md`, MEASURED).
   - At 25–60 attempts per slot, our failed-attempt cost would be 0.006–0.015 SOL per fill against T2's +0.003–0.006 edge, so copying their density on T2 loses (INFERRED).
2. **Bigger size** (0.55 SOL): fixed costs weigh less.
3. **Filter:** BAM leaders were positive and Jito/Harmonic negative (small samples).
4. **More hours:** the same paper made +2.6 SOL from 06:09–08:06 and about 0 in this hour. Results swing a lot by hour, so run the free shadow for a full day before scaling.
