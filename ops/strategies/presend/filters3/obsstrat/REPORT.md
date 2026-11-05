# OBS-STRAT — run 42 observatory to strategies (11-03, PKT)

(Saved by the coordinator from the agent's final message. DEV 74.35 h, VAL 20.61 h, HOLDOUT r43-46 14.23 h; holdout opened after
FROZEN.json. Data/tables: /home/moiz/sniper-data/filters3/obsstrat/, holdout outputs in hold/.)

## Levers (ranked)
1. EXIT125 `--presend-live-exit-ms 125` (today 200). ESTIMATE (own sells replayed on hold tapes; replay hits our real sell's curve
   state on all 2,119 positions; sell lands after the position's own measured send->land delay; TP/SL decided > 147 ms become timer).
   | period | changed | gain own L | /day | w/o 5 best | model vs model (/day) | win |
   | DEV | 1330 | +1.85 | +0.60 | +0.99 | +0.34 (+0.11) | 52.0->53.8% |
   | VAL | 713 | +4.75 | +5.53 | +2.80 | +2.72 (+3.16) | 41.2->43.8% |
   | HOLD | 407 | +1.44 | +2.43 | +0.71 | +0.83 (+1.40) | 45.8->48.1% |
   Per run + everywhere (r44 carries most of HOLD); 8 of 9 twelve-hour blocks +, 9th ~0. Longer holds lose (225 ms DEV -1.25/day,
   300 ms VAL -1.15/day). Inference: after followers left, price falls in the ~75 ms after our 200 ms decision. Not modelled: whether
   followers react to our earlier sell.
2. R5 re-arm skip `--presend-live-rearm-r5-skip on` (run script: --presend-rearm-r5 on). PROVEN (realized), thin; on top of dip32's
   creator gate: DEV +0.93 (+0.30/day, w/o 5 +0.13), VAL +0.45 (+0.52/day, +0.20), HOLD +0.30 (+0.50/day, -0.01). Idle during
   QUIET's warm-up.
Both together on top of the creator gate: DEV +19.92 -> +23.58 (+7.61/day; model-vs-model +7.12), VAL -0.93 -> +5.27 (+6.14/day;
+3.86), HOLD -0.33 -> +1.52 (+2.57/day; +1.79). Win 52.0->55.7 / 41.2->46.5 / 45.8->51.6%.

## Failed
Sell at once on a big sell in our hold (every size 0.3-2 SOL negative on DEV; price already down when seen, backrunners lift it);
sell into another wallet's >= 0.5 SOL buy (DEV -0.58/day, VAL +2.10: market-dependent); re-arm paper overstates live (live 0.47x
paper DEV, ~0x VAL; VAL live re-arm +0.03 on 303 trades -> no re-arm size-up); missed re-arm windows = speed (88/132 DEV, 45/75 VAL
landed in the dump's slot after the dump); re-arm while a position/ATA is open ~+0.66/day DEV ~0 VAL (needs engine change, not
recommended); selection census dead (live 26% of paper DEV, 6% VAL; "insider" = create-slot buyers, already skipped); re-arm gap 10
and T2 window 7 slots fail w/o top 5; shallower limit adds the worst fills; faster sell landing = DEV -0.74/day, VAL +3.42 (market).
Optional untested: an exact exit timer (p90 today 292 ms after the fill).
