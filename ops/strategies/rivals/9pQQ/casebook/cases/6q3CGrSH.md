# Case 03 — 6q3CGrSH (run 10-30, launch 10-31 01:35 PKT, "SpaceX Super Intelligence", X link) — stratum A multi-win, V3
30 trips in 35 min (age +39..+9542), +0.93 SOL. 3,615 trades.

## What happened
- First buy at age 39, right after a coordinated 4-wallet FLASH dump (CS8rC/59xSf/4sAr9/51TPS, 1.6–2.1 SOL each, consecutive positions)
  and a 41Pr4 buy; T2 (age 64) bought the same 4 wallets' second dump wave (0.9–1.0 SOL each). Both trips +26–30 % in 1–2 s.
- Early holds are tiny (5–54 slots) with big returns; later holds 20–900 slots.
- Taken triggers: size 0.55 vs 0.15 SOL; **ch10 is spread to both tails** (quartiles −12.4/−0.5/+9.5 vs skipped −3/0/+2.1): it buys after
  strong moves either way. Last trade side B 19/30 (= base). Busy slots (gap 0).
- Exits: 22/30 behind an outside SELL; dd at sell small (−0.3..−8 %). Teacher-forced rules on tokens 2+3 (45 non-cap V3 trips):
  stale5 2 % exact (31 early), dd3 2 % (33 early), burst 4 % (23 early), stale5|burst 4 %. Every simple exit rule fires much earlier than it.
  So it also "lets go by" most qualifying exit moments.
- Example tapes: T7 bought first-in-slot (+319/4) after 3 fresh GMGN ~1 SOL buys in the previous slot; sold first-in-slot +395/26
  after a 0.11 sell (5 slots without buys) at +2.2 %. T22 sold after a 35-slot pause on a 0.011 sell; a 4.14 SOL buy landed right after its sell.
- Cross-token checks (scale, own txs 10-30/10-31): its sells are not coupled to its buys on other tokens (±0–2 slots: 2.4/6.3/10.4 %
  vs shifted baseline 2.3/6.4/10.1 %). Tokens are traded independently.
- Quit at +9542 (MC ~250) while the token went on (62 outside buys ≥ 0.5 SOL after, peak MC 411).

## Hypotheses
| id | cat | hypothesis | here |
|---|---|---|---|
| HB19 | buy | Volatility trigger: buys after a strong price move either way (|ch10| ≥ ~5 %), not in calm. | support |
| HB16 | buy | coordinated group dumps | support (T1, T2) |
| HM02 | meta | Tokens are independent (no capital rotation / cross-token coupling). | support (scale) |
| HS12 | sell | Exit is not a first-passage rule on landed-trade state (all simple rules fire early on 45 trips). | support |
| HK03 | skip | quits a token above MC ~250–300 | support |
