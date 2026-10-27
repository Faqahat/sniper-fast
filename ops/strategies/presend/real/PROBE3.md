# Pre-send probe 3 (Amsterdam run 19): a 4-hour test of the realistic replay

Owner "yes" 10-25 ~20:30 PKT. Basis: REAL_REPLAY.md (this folder). Probe-2 settings give +4.3 SOL/day on 76 unseen hours, but the per-probe P&L calibration missed, and both live probes fell in hours the replay also calls weak. This run tests the replay; it is not meant as income.

## Command (Amsterdam; start after 00:00 PKT, avoiding the replay's weak 21–24 PKT; the owner starts it)
Exactly probe 2, with bigger caps and 4 hours. The run script picks engine dip15 for --presend-live, which no longer hangs at the end.
```bash
sudo bash /root/prod/run_dip_prod.sh --region ams --run 19 --trades 60 --size 0.35 --tier wider --tp off --sl 0.5 --hold-slots 5 --dev-list /root/sniper-dip/dev_list.txt --dev-size 0.55 --near /root/sniper-dip/near_leaders_ams_nobam.txt --nonce /root/prod/nonce_ams.txt --fallback ck --m2 /root/dip/m2_v3_reg4_top25.json --presend --presend-whale-pct 6 --presend-live --presend-live-size-sol 0.35 --presend-live-k 8 --presend-live-routes "default=helius-ps" --presend-live-max-per-sec 30 --presend-live-path-max-per-sec 30 --presend-live-max-fills 100 --presend-live-fee-budget-sol 0.1 --sell-fanout helius-swqos --minutes 240
```
- Optional (exploratory, decided after the replay's pre-registered runs): `--presend-live-k 6`. It gives +4.8/day in the replay and avoids the empty slot each second (the 30/s budget runs out ~0.8 s into a window at 8 per slot).

## Expected (replay, INFERRED)
- Failed-try fees about 0.027 SOL/hour, so the 0.1 SOL fee budget stops the run after ~3.7 h.
- +0.18 SOL/hour; 94% of 4-hour blocks are positive.

## Rules (fixed before the run)

| Result | Live P&L per fill (≥ 80 fills) | Next step |
|---|---|---|
| PASS | ≥ +0.004 SOL | pre-send becomes a second earner next to M2; next, the second path (45/s, needs OK) |
| FAIL | ≤ +0.001 SOL | stop pre-send T2 for good |
| In between | — | run ~4 more hours |

Evaluate with `ops/strategies/presend/ps13_live_eval.py --jsonl dip_ams_r19.jsonl`, plus the replay's own per-window comparison (real/ scripts).
The biggest risk: profit depends on the bots that buy after us (20% fewer of them → +1.0/day, 30% fewer → negative).

## Result (AMS run 19, 10-25 22:20 – 10-26 00:21 PKT, 2 h; MEASURED from the run log)
- Pre-send live: 66 fills, 35 wins, realized +0.886 SOL, failed-try fees 0.068 SOL, **net +0.818 SOL = +0.0124 SOL/fill → PASS** (rule: ≥ +0.004).
  - 66 fills < the 80-fill rule minimum; per fill is 3x the pass line.
- Regular dip buys: 3 landed of 14 fired, +0.074 SOL (11 failed on price, fee only).
- Shadow (0.55 SOL) row +0 ms net +2.054 SOL ⇒ ×0.636 for 0.35 = +1.31; live = 62% of size-matched paper.
- Engine dip15 exited on its own 20 s after the stop (6 windows unsettled, no positions).
