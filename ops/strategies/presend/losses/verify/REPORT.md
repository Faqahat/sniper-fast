# Verify: skip arm at trigger age 1 slot (2026-10-29, independent)

Code: verify.py (extract) + analyze.py (tables). Data: /home/moiz/sniper-data/presend_losses/verify/ (fills.json, analyze_out.txt, raw/ = read-only copies of AMS r28-r33, r36).

Rule as the engine applies it: age_slots = trigger trade slot - create slot (presend_live.rs:149); engine skips `age_slots == 0` (pslive.rs:1372). Change = `< 2`. I read age_slots straight from each arm record, so no off-by-one risk. Age-0 fills: 0 in all runs (correct).
P&L = sum of presend_live_realized.pnl per position (buy+sell wallet deltas, rent back included). Failed tries NOT included (reported apart).

Runs: 24 live pre-send runs, 79.5 h, 1,829 fills (FRA r21-r28 minus r25; AMS r16-r36). r36 copied 07:06 PKT (partial).
Cross-check with the earlier agent: r28/r34/r35 match fill for fill (same mints, age, P&L). r36 differs only because my copy has 17 more fills (theirs 13 age-1 -0.506; mine 16 age-1 -0.468).

## Totals (age-1 skip)
| set | runs | h | fills | P&L | skipped (W/L) | saved | /day | /day @0.696 INFERRED | CI90 saved | w/o top 5 | runs help/hurt |
|---|---|---|---|---|---|---|---|---|---|---|---|
| all | 24 | 79.5 | 1829 | +9.08 | 226 (76/150) | +1.99 | +0.60 | +0.84 | [+0.84, +3.14] | +1.18 | 17/7 |
| out-of-sample (not r28/34/35/36) | 20 | 63.0 | 1351 | +5.99 | 164 (60/104) | +0.55 | +0.21 | +0.40 | [-0.29, +1.40] | +0.05 | 13/7 |
| the 4 used runs | 4 | 16.5 | 478 | +3.09 | 62 (16/46) | +1.44 | +2.10 | +2.50 | [+0.67, +2.27] | +0.63 | 4/0 |

Failed tries on age-1 arms that never filled: 17,939 tries over 790 age-1 arms; est. fees saved <= 0.08 SOL total (INFERRED upper bound).

Adversarial: not one whale (68 whales; worst whale out still -1.64). Mostly a night effect: 22-06 PKT age-1 -1.76 (-0.014/fill) vs day -0.23 (-0.002/fill). Mayhem excluded by engine. Age 2-9 are not bad (+0.82 together), so the loss is only at age 1.

## Second rules (owner ask)
- whale buy >= 6 SOL: all +1.78 saved, OOS +0.25 (CI [-0.66,+1.21], w/o top5 -0.51, 10 help/10 hurt) -> FAILS out-of-sample.
- whale >= 6 SOL AND fill leader Firedancer: all +1.15, OOS +0.11 (CI [-0.53,+0.82], w/o top5 -0.49) -> FAILS. Also leader client is known only per attempt at send time (lat::leader_of(slot)), not at arm; dropping those attempts may let a later attempt fill, so the skip P&L is not the real effect.
- combo (age-1 OR whale>=6+FD): OOS +0.81 (+0.53/day @0.696), CI [-0.20,+1.86], w/o top5 +0.04. Gain over age-1 alone is fit on the 4 used runs.

## Verdict
Age-1 skip is real but small out-of-sample: ~+0.4 SOL/day at 0.696 SOL (INFERRED), CI touches 0, ~0 without top 5. On the runs that picked it, +2.5/day - that is the optimistic number. Low risk, cheap: ship it, expect ~+0.4/day, not +2.

## Per run (P&L SOL; rest = all fills except age-1; w6 = whale buy >= 6 SOL; FD = Firedancer leader at fill)
| reg | run | PKT span | h | size | fills | P&L | age1 n | age1 P&L | win/lose | rest | unfilled age1 tries | w6 n/P&L | w6+FD n/P&L |
| FRA | r21 | 10-26 00:26–02:01 | 1.6 | 0.350 | 49 | +0.020 | 5 | +0.011 | 2/3 | +0.008 | 549 | 6/-0.107 | 1/+0.029 |
| FRA | r22 | 10-26 02:18–02:48 | 0.5 | 0.400 | 21 | -0.151 | 5 | -0.333 | 0/5 | +0.182 | 130 | 1/-0.091 | 0/+0.000 |
| FRA | r23 | 10-26 04:26–16:08 | 11.7 | 0.400 | 100 | -0.243 | 13 | -0.262 | 2/11 | +0.019 | 801 | 6/-0.047 | 1/-0.023 |
| FRA | r24 | 10-26 16:10–21:40 | 5.5 | 0.400 | 100 | +0.655 | 11 | +0.316 | 8/3 | +0.339 | 794 | 5/+0.167 | 1/+0.181 |
| FRA | r26 | 10-28 00:32–02:24 | 1.9 | 0.450 | 43 | +0.645 | 6 | +0.136 | 4/2 | +0.509 | 861 | 4/+0.037 | 1/+0.028 |
| FRA | r27 | 10-28 02:26–14:26 | 12.0 | 0.450 | 200 | +1.424 | 13 | -0.097 | 7/6 | +1.520 | 2151 | 19/-0.229 | 2/-0.316 |
| FRA | r28 | 10-28 14:31–20:02 | 5.5 | 0.450 | 78 | +0.455 | 10 | -0.338 | 1/9 | +0.794 | 924 | 12/-0.513 | 9/-0.503 |
| AMS | r16 | 10-25 08:48–10:18 | 1.5 | 0.200 | 20 | +0.012 | 4 | -0.010 | 2/2 | +0.022 | 262 | 3/+0.013 | 1/+0.030 |
| AMS | r17 | 10-25 15:30–17:30 | 2.0 | 0.350 | 13 | -0.001 | 7 | -0.001 | 3/4 | +0.000 | 645 | 1/+0.004 | 0/+0.000 |
| AMS | r19 | 10-25 22:20–00:20 | 2.0 | 0.350 | 66 | +0.886 | 7 | +0.068 | 5/2 | +0.818 | 1611 | 2/+0.065 | 0/+0.000 |
| AMS | r20 | 10-26 01:16–02:00 | 0.7 | 0.350 | 34 | -0.161 | 4 | -0.034 | 2/2 | -0.126 | 92 | 5/+0.028 | 1/+0.041 |
| AMS | r24 | 10-26 21:47–02:57 | 5.2 | 0.340 | 178 | +0.977 | 21 | -0.081 | 6/15 | +1.058 | 962 | 21/+0.178 | 1/-0.021 |
| AMS | r25 | 10-27 02:58–06:09 | 3.2 | 0.340 | 95 | +0.952 | 10 | +0.071 | 5/5 | +0.881 | 941 | 8/-0.033 | 1/+0.008 |
| AMS | r26 | 10-27 06:58–14:03 | 7.1 | 0.500 | 143 | +0.134 | 13 | -0.046 | 4/9 | +0.180 | 1515 | 10/-0.118 | 1/-0.152 |
| AMS | r27 | 10-27 15:26–17:36 | 2.2 | 0.350 | 49 | +0.570 | 9 | -0.053 | 1/8 | +0.623 | 220 | 5/+0.012 | 2/+0.031 |
| AMS | r34 | 10-28 20:06–23:17 | 3.2 | 0.450 | 120 | +0.431 | 14 | -0.094 | 3/11 | +0.526 | 957 | 11/-0.068 | 2/+0.014 |
| AMS | r35 | 10-28 23:18–03:31 | 4.2 | 0.650 | 158 | +1.621 | 22 | -0.538 | 7/15 | +2.158 | 1320 | 15/-0.195 | 3/-0.044 |
| AMS | r28 | 10-27 18:20–22:03 | 3.7 | 0.500 | 150 | +0.124 | 19 | +0.051 | 6/13 | +0.073 | 1071 | 17/+0.069 | 7/+0.160 |
| AMS | r29 | 10-27 22:04–22:17 | 0.2 | 0.500 | 9 | -0.033 | 1 | +0.001 | 1/0 | -0.033 | 128 | 2/-0.076 | 1/-0.045 |
| AMS | r30 | 10-27 22:18–22:31 | 0.2 | 0.350 | 17 | -0.061 | 2 | -0.037 | 0/2 | -0.025 | 110 | 2/-0.017 | 0/+0.000 |
| AMS | r31 | 10-27 22:32–23:15 | 0.7 | 0.350 | 26 | +0.029 | 6 | -0.009 | 2/4 | +0.039 | 232 | 1/+0.019 | 0/+0.000 |
| AMS | r32 | 10-27 23:17–23:48 | 0.5 | 0.350 | 18 | -0.003 | 4 | -0.125 | 0/4 | +0.122 | 292 | 2/-0.101 | 1/-0.064 |
| AMS | r33 | 10-27 23:49–00:29 | 0.7 | 0.350 | 20 | +0.211 | 4 | -0.117 | 0/4 | +0.328 | 357 | 1/-0.024 | 0/+0.000 |
| AMS | r36 | 10-29 03:33–07:06 | 3.5 | 0.696 | 122 | +0.586 | 16 | -0.468 | 5/11 | +1.054 | 1014 | 20/-0.755 | 7/-0.501 |
