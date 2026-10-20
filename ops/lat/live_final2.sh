#!/bin/bash
# ===== LIVE — THE OWNER RUNS THIS, NOBODY ELSE. Real transactions, real SOL. NOT RUN by the fix2 agent. =====
# FIX2 engine (2026-10-19, /root/fix2/NOTES.md): /root/sniper-final2 (= /root/sniper-final + the fix2 changes), config
# /root/fix2/final2_landing.toml (= /root/lat/final_landing.toml + harmonic-bundle). Same rule (PREREG_v2 #2), same caps
# as live_final.sh (17 buys: --max-total-sol 0.007, per-buy 0.0015, kill-switch 0.170, cu 105k, 90 min, 2 in flight). New:
#  * gates: --close-leaders /root/fix2/close_leaders_5ms.txt (190 leaders < 5 ms RTT, 34% of slots, measured 2026-10-19
#    ~16:05 UTC for epochs 1062+1063) and --max-create-ms 150 (create's PoH position in its slot; unknown -> skip).
#    Expect ~10 rule-#2 fires/h (census), so 17 buys may not fill in 90 min.
#  * routes: no helius on BAM / Jito-Solana leaders (a bundle landing is then unambiguously ours); harmonic leaders get
#    harmonic-bundle first ONLY once whitelisted (ROUTES_HB; default ROUTES leaves it out). NOTE: Harmonic's public endpoint answered "rate limited" (429) to EVERY request on 2026-10-19
#    (/root/fix2/harmonic_poll.log): until that changes (or our key is whitelisted) the harmonic-bundle copy is refused
#    and costs nothing; jito-bundle + nozomi + staked-rpc still carry Harmonic buys.
#  * logging: --jito-poll (bundle status at +0.5/+2/+10 s with the error detail), --landed-via (which copy landed);
#    jito-h2 refusals now carry grpc-status/grpc-message.
#  * sell: --sell-robust (late-landing watch 45 s, token balance re-read) --sell-retries 2 --sell-retry-s 4;
#    --strict-balance (refuses to start without a start balance; prints it).
# BEFORE RUNNING: stop every other engine / build / paper run (pgrep -af "snipe_engine|cargo|bpftrace|python3"); the
# engine pins core 1. Alpenglow ~2026-10-21 14:50 UTC changes BAM (maintenance) and PoH ticks: re-check the gates after.
# usage: live_final2.sh <tag>   then: python3 /root/lat/lat_measure.py /root/lat/live_land_<tag>.log /root/lat/sends_<tag>.jsonl
#        and grep -E "LANDED-VIA|JITO-POLL|GATE-CREATE-MS|SELL-RETRY" /root/lat/live_land_<tag>.log
TAG=${1:-final2}
cd /root/lat
set -a; . /root/sniper/deploy/.env; set +a
export KALDERA_TOKEN=$(grep -o 'KALDERA_TOKEN=[^ ]*' /root/collect_blfwd.sh | head -1 | cut -d= -f2)
# harmonic-bundle stays OUT of the route until Harmonic confirms the whitelist of 8C1hako7...; then use ROUTES_HB:
ROUTES_HB="bam=jito-bundle+landx-fra3+staked-rpc;harmonic=harmonic-bundle+jito-bundle+nozomi+staked-rpc;jito=jito-bundle+landx-fra3+staked-rpc;fd=jito-bundle+astralane+nozomi+staked-rpc;agave=helius+nozomi+staked-rpc;other=helius+nozomi+landx-fra3+staked-rpc;default=jito-bundle+landx-fra3+helius+staked-rpc"
ROUTES="bam=jito-bundle+landx-fra3+staked-rpc;harmonic=jito-bundle+nozomi+staked-rpc;jito=jito-bundle+landx-fra3+staked-rpc;fd=jito-bundle+astralane+nozomi+staked-rpc;agave=helius+nozomi+staked-rpc;other=helius+nozomi+landx-fra3+staked-rpc;default=jito-bundle+landx-fra3+helius+staked-rpc"
LOG=/root/lat/live_land_${TAG}.log
: > $LOG
/root/sniper-final2/target/release/snipe_engine --snipe-once --concurrent --live \
  --uri-blacklist --min-dev-buy 500000000 --max-dev-buy-sol 8 \
  --dev-from-cap --race-gate --race-min-bundle 1 --race-min-bundle-sol 3 --race-max-bundle-sol 5 --race-create-tip-prefix moon --race-bundle-ms 3 --race-glued \
  --race-pros /root/race/pros.json --race-early \
  --close-leaders /root/fix2/close_leaders_5ms.txt --max-create-ms 150 \
  --spend-lamports 1000000 --fill-cap 2.5 --max-sol 0.0015 --max-total-sol 0.007 --max-loss-sol 0.070 --max-inflight 2 --minutes 90 \
  --cu-price-micro 30000000 --cu-limit 105000 --sell-cu-price-micro 1500000 --land-poll-ms 100 \
  --sell-robust --sell-retries 2 --sell-retry-s 4 --strict-balance --jito-poll --landed-via \
  --send-path helius --sell-path staked-rpc --route-by-client "$ROUTES" --send-log /root/lat/sends_${TAG}.jsonl \
  --config /root/fix2/final2_landing.toml --env-file /root/sniper/deploy/.env \
  --fast-send --jito-h2 --fast-presign --fast-derive --busy-poll --pin-core 1 --lat-trace /root/lat/trace_${TAG}.jsonl \
  < /root/.nexus-v2-trading-wallet.pass >> $LOG 2>&1
echo "LIVE_FINAL2_DONE $TAG $(date -u)" >> $LOG
