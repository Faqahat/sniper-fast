#!/bin/bash
# FINAL-2 "become them" strategy (ops/overnight/BECOME_THEM.md) — PROPOSED flags, NOT deployed, NOT run. Needs the owner's OK.
#   select : FINAL-2 (our own GBDT + fast-dump veto + guards), asked at the glued-bundle close over a local socket
#            (--final2-sock; ops/shadow/scorer.py with FINAL2_SOCK=<path> must be running and tailing this engine's log)
#   buy    : 0.5 SOL right after the dev's glued bundle, ONLY if first (price guard: min-out = post-bundle quote - 0.5%)
#   sell   : everything ~8 s after the buy (--hold-ms counts from the landing being SEEN, ~0.1-0.4 s after it lands)
# Replay (pro buys after us removed + follower slippage, pro costs): 45 ms +2..+16 SOL/day, 75 ms +2..+8 (daytime / overnight PKT);
# at TODAY's costs and 75 ms about break-even in daytime PKT -> run it first in PKT evening/night (US hours), and only after the
# landing upgrade if possible.
F2_SOCK=${F2_SOCK:-/root/sniper-f2/f2.sock}
F2_FLAGS=(--min-dev-buy 0 --max-dev-buy-sol 100
  --race-gate --race-glued --race-bundle-ms 3 --race-pros /root/race/pros.json --create-ms-src wall
  --final2-sock "$F2_SOCK" --final2-timeout-ms 5
  --spend-lamports 500000000 --slip-cap-bps 50 --fill-cap 1.005 --max-sol 0.6 --max-total-sol 8 --max-buys 15 --max-loss-sol 0.3 --ks-blind-s 10 --max-inflight 2 --minutes 120
  --hold-slots 0 --hold-ms 7700 --hold-max-ms 9000 --land-poll-ms 100 --land-timeout-ms 3000
  # optional (A7 activity check, frozen 09:23 PKT; enable only if the forward test confirms it):
  # --hold-activity-k 1 --hold-activity-cap-ms 800
  --sell-robust --sell-retry-s 1 --sell-deadline-s 30 --sell-fallback-path nozomi --buy-max-slot-delta 1)
# Send/route/fee flags stay as in ops/run1/run1_common.sh until the owner decides on fees and the landing-path change.
# Scorer (same box, before the engine):
#   FINAL2_SOCK=$F2_SOCK python3 scorer.py <this engine's log> <paper>/frozen_live3_fsell.json,<paper>/frozen_dump2.json <paper>/shadow_seed.json \
#       <collector run dir (must be RUNNING: history)> <tipmap.json> <out dir> final_config2.json
