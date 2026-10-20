#!/bin/bash
# RUN 1 of the 5-run plan (ops/comp/RUNPLAN.md, sim: ops/comp/sim_ladder.py). Shared flags for live + dry.
# Rule #2 + gates unchanged from live test 2. Changes vs live_final2.sh (all measured/simulated 2026-10-20):
#   size 1.5 SOL (--spend-lamports), fee ~0.025 SOL/buy: CU 95k x 110M uL = 0.0105 priority + Jito tip 0.012 (toml)
#   + relay tips 0.001; exit = sell ALL ~3 slots after the landing (sim: best at every landing position; ladders /
#   longer holds lose at our landing); sells CU 5M; run kill -0.5 SOL (open positions at cost), profit lock
#   0.3:0 / 0.6:0.3; 20 landed buys or 180 min; 2 in flight.
# AUDIT FIXES (2026-10-20, /home/moiz/sniper-audit/FIXES.md) — new flags:
#   --slip-cap-bps 1500       M1: min_tokens_out = 85% of the quote on the curve after dev + glued bundle (re-signed at the
#                             decision); --fill-cap 1.6 stays as the fallback when the bundle total is not known
#   --land-timeout-ms 3000    M3: buy land poll (signature status + token account every 100 ms), then the late-land watch
#                             (--sell-robust) until the buy's blockhash is dead (~33 s)
#   --hold-slots 3            M3: sell DECISION when the shred feed reaches the buy's landing slot + 3 (~3 x 217 ms after
#   --hold-ms 450             that slot began, i.e. ~0.55-0.65 s after the real landing; the sell lands ~1 slot later, as
#   --hold-max-ms 1500        in the sim). Landing seen only via the token account (no exact slot): 450 ms after it was
#                             seen (~0.6-0.7 s after the real landing). Capped 1.5 s after the landing was seen.
#   --sell-fallback-path nozomi  C2: every sell RETRY goes to staked-rpc AND nozomi (one signature, nozomi's 0.001 tip);
#   --sell-deadline-s 30      sells retry until the token account reads 0 for >= 30 s, then UNSOLD is logged
#   --max-buys 20             L4: 20 LANDED buys; --max-total-sol is now a budget on landed buys incl. fees
#                             (20 x ~1.526 = 30.5 SOL, so 31 keeps --max-buys 20 the binding limit)
#   --fast-verify             L10: every fired message (and, M1, every re-signed request) checked against the full compile
#   (--sell-retries removed: the sell loop is bounded by --sell-deadline-s now)
# RE-AUDIT FIXES (2026-10-20, FIXES.md "Re-audit"):
#   --sell-cu-limit 120000    N4: sells have their own CU limit (sell tx measured 44-56k CU for SellV3 + ATA close,
#                             ops/review/REPORT.md section 5); a sell that lands FAILED retries with 1.5x the limit.
#                             Verify with cu_check.sh (zero-cost sell simulation) before the run.
# AUDIT 3 FIXES (2026-10-20; M-3 + M-5 send-path changes approved by the owner):
#   --buy-max-slot-delta 1    M-3: ON-CHAIN slot deadline: a Lighthouse AssertSysvarClock (slot <= create slot + 1) right
#                             before the buy; a later landing fails on chain (no tokens, fees only). Verified by
#                             simulation at start-up or the engine refuses to start. CU: checked by cu_check.sh.
#   --rpc-fallback-url-env RMR_RPC_URL   H-1: the exit path's second RPC (blockhash, statuses, token reads, balance);
#                             a sell with no fresh blockhash uses the cached one (<= 25 s); UNSOLD keeps retrying in the
#                             background every 5 s until the exit; EXIT CHECK tries one more sell of anything held
#   --sell-retry-s 1          M-5: re-send a sell not seen within 1 s (was 4); every sell (the first too) goes to
#                             staked-rpc + nozomi (--sell-fallback-path) with one signature
#   --alt-cache-file /root/run1/alt_tables.txt   ALT fix (dry run of 39810395): lookup tables of raw-shred txs are
#                             resolved from a cache (known launchpad table HQ4G6Fjm… + this file's last 200 tables preloaded;
#                             a new table is fetched async on first sight, that tx stays fail-closed, ALT-MISS logged once)
#   (engine, no flag: M-1 SIGHUP = stop + drain; M-2 every failed buy's real error is logged and classified, 3 non-slippage
#    failures stop new fires; M-4 --sell-held resolves router creates; L-1 the kill logs open positions + worst case)
#   (engine behaviour, no flag: N1 sold = CONFIRMED 0 at slot >= the sell's landing; N2 kill/lock on 2 consecutive polls;
#    N3 late-landing watch until the buy's blockhash is dead, cap --late-land-s default 120; every fired mint re-read
#    at exit; N5 unknown flags / bad values refuse to start)
set -a; . /root/sniper/deploy/.env; set +a
: "${KALDERA_TOKEN:?KALDERA_TOKEN must be set in /root/sniper/deploy/.env}"
B=/root/sniper-run1/target/release/snipe_engine
C=/root/run1/run1_landing.toml
ROUTES="bam=jito-bundle+landx-fra3+staked-rpc;harmonic=jito-bundle+nozomi+staked-rpc;jito=jito-bundle+landx-fra3+staked-rpc;fd=jito-bundle+astralane+nozomi+staked-rpc;agave=helius+nozomi+staked-rpc;other=helius+nozomi+landx-fra3+staked-rpc;default=jito-bundle+landx-fra3+helius+staked-rpc"
FLAGS=(--uri-blacklist --min-dev-buy 500000000 --max-dev-buy-sol 8
  --dev-from-cap --race-gate --race-min-bundle 1 --race-min-bundle-sol 3 --race-max-bundle-sol 5 --race-create-tip-prefix moon --race-bundle-ms 3 --race-glued
  --race-pros /root/race/pros.json --race-early
  --close-leaders /root/fix2/close_leaders_5ms.txt --max-create-ms 150
  --spend-lamports 1500000000 --slip-cap-bps 1500 --fill-cap 1.6 --max-sol 1.6 --max-total-sol 31 --max-buys 20 --max-loss-sol 0.5 --lock-tiers 0.3:0,0.6:0.3 --max-inflight 2 --minutes 180
  --cu-price-micro 110000000 --cu-limit 100000 --sell-cu-limit 120000 --sell-cu-price-micro 5000000 --hold-slots 3 --hold-ms 450 --hold-max-ms 1500 --land-poll-ms 100 --land-timeout-ms 3000
  --sell-robust --sell-retry-s 1 --sell-deadline-s 30 --sell-fallback-path nozomi --buy-max-slot-delta 1 --rpc-fallback-url-env RMR_RPC_URL --alt-cache-file /root/run1/alt_tables.txt --strict-balance --jito-poll --landed-via
  --send-path helius --sell-path staked-rpc --route-by-client "$ROUTES"
  --config $C --env-file /root/sniper/deploy/.env
  --fast-send --jito-h2 --fast-presign --fast-derive --fast-verify --busy-poll --pin-core 1)
