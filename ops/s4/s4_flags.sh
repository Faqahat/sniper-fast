#!/bin/bash
# S4 (overnight study 2026-10-23, ops/overnight/report/S4_STRATEGY.html) — PROPOSED flags, NOT deployed, NOT run.
# ON HOLD (owner, 2026-10-23 ~08:00 PKT): not confident; owner checks it manually. Open issue: the replay keeps followers
# that our own buy would push past their slippage limit (seen live on 8HSxaXd3: ops/overnight/live/LIVE_TAPES.md).
# Needs the owner's OK. Start on FRZ (dev wallet) with tiny size, then PROD.
#
# What S4 is (replay, verifier-matched: +3.75 SOL (1 s hold) / +4.0 (sell at end of next slot) per 7.4 h at our measured 75 ms landing, 0.5 SOL):
#   select : create tx SIGNED by a deployer on the list (--deployer-list; file rebuilt from 9Sh2fd/DGmspi attempts by
#            ops/overnight/dryrun/build_list.py: >= 2 attempts and >= 10% of the deployer's launches)
#   buy    : at the glued-bundle close (race gate, no bundle-size / tip filters), min-out = post-bundle quote - 1%
#            (--slip-cap-bps 50): the buy FAILS if anyone bought ahead of us (fill only when first)
#   sell   : all, at the end of the slot after the buy. ENGINE MAPPING (checked 2026-10-23 08:10 PKT in hold_wait()): --hold-slots N
#            sends the sell when the feed FIRST SEES slot land+N, so the sell lands early in land+N. The replay's exit
#            (after every trade of slot land+1) is therefore --hold-slots 2, NOT 1 (1 sells about a slot earlier than replayed).
#            --hold-slots 2 is also Run 2's exit: the only difference from rule #2 is the deployer list + the guard.
#
# Differences vs Run 2 (ops/run1/run1_common.sh), each one deliberate:
#   - rule #2 race filters removed (--race-min-bundle/-sol, --race-max-bundle-sol, --race-create-tip-prefix)
#   - --deployer-list added (new engine flag, compiled on the host, not yet built into the server binary)
#   - --slip-cap-bps 1500 -> 50 (the price guard: min-out = 99.5% of our buy's quote on the post-bundle curve, engine M1;
#     a 0.1-0.5% guard beat 1% in both periods: fills where even a small buy got in first lose on average)
#   - --fill-cap 1.6 -> 1.005: when the glued-bundle total is NOT known the engine falls back to the dev-only floor x
#     fill-cap; 1.005 keeps that fallback strict (a bundled launch then fails instead of filling behind other buyers)
#   - --min-dev-buy 0 --max-dev-buy-sol 100 (the replay did not filter on dev buy)
#   - --close-leaders / --max-create-ms removed (the replay did not use them; with the guard a late buy just fails)
#   - --hold-slots stays 2 (same as Run 2): it is the replay's "end of the next slot" exit (see sell above)
#   - size: --spend-lamports 500000000 (0.5 SOL), --max-buys 15, --max-loss-sol 0.3 for the FRZ test. NOT 0.1 SOL: at Run 2's
#     fees (~0.024 SOL per buy, 0.011 per failed buy) a 0.1-0.25 SOL test loses even though the strategy works
#     (ops/overnight/report: fee table)
#   - FEES (owner's call, paid settings): Run 2 paid ~0.025 SOL per buy (0.011 priority + Jito/relay tips). At 0.5 SOL
#     that is 5%, and a FAILED guarded buy still pays the 0.011 priority fee. Replay at 75 ms: +4.9 SOL with 2% overhead
#     and 0.005 per fail; with Run 2's fees about +2.4. Lower priority fee + tips (tips revert on a failed tx) keeps more.
DEPLOYER_LIST=${DEPLOYER_LIST:-/root/sniper-s4/deployer_list.txt}
S4_FLAGS=(--uri-blacklist --min-dev-buy 0 --max-dev-buy-sol 100
  --deployer-list "$DEPLOYER_LIST"
  --dev-from-cap --race-gate --race-bundle-ms 3 --race-glued --race-pros /root/race/pros.json --race-early --create-ms-src wall
  --spend-lamports 500000000 --slip-cap-bps 50 --fill-cap 1.005 --max-sol 0.6 --max-total-sol 8 --max-buys 15 --max-loss-sol 0.3 --ks-blind-s 10 --max-inflight 2 --minutes 120
  --hold-slots 2 --hold-ms 400 --hold-max-ms 1500 --land-poll-ms 100 --land-timeout-ms 3000
  --sell-robust --sell-retry-s 1 --sell-deadline-s 30 --sell-fallback-path nozomi --buy-max-slot-delta 1)
# The send/route/fee flags (--cu-price-micro, --route-by-client, --send-path, ...) stay as in run1_common.sh until the
# owner decides on fees and on the landing-path change (ops/overnight/landing/LANDING_PATHS.md). Replay guidance:
# keep the PRIORITY fee low (a failed guarded buy pays it; ~2 of 3 attempts fail) and pay for landing with tips (they
# revert on a failed tx). E.g. --cu-price-micro ~10000000 (0.001 SOL at 100k CU) instead of 110000000 (0.011 SOL).
