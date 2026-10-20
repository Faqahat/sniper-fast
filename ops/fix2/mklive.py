s = open("/root/lat/live_final.sh").read()
hdr_old = s.split("TAG=${1:-final1}")[0]
new_hdr = """#!/bin/bash
# ===== LIVE — THE OWNER RUNS THIS, NOBODY ELSE. Real transactions, real SOL. NOT RUN by the fix2 agent. =====
# FIX2 engine (2026-10-19, /root/fix2/NOTES.md): /root/sniper-final2 (= /root/sniper-final + the fix2 changes), config
# /root/fix2/final2_landing.toml (= /root/lat/final_landing.toml + harmonic-bundle). Same rule (PREREG_v2 #2), same caps
# as live_final.sh (17 buys: --max-total-sol 0.017, per-buy 0.0015, kill-switch 0.170, cu 105k, 90 min, 2 in flight). New:
#  * gates: --close-leaders /root/fix2/close_leaders_5ms.txt (190 leaders < 5 ms RTT, 34% of slots, measured 2026-10-19
#    ~16:05 UTC for epochs 1062+1063) and --max-create-ms 150 (create's PoH position in its slot; unknown -> skip).
#    Expect ~10 rule-#2 fires/h (census), so 17 buys may not fill in 90 min.
#  * routes: no helius on BAM / Jito-Solana leaders (a bundle landing is then unambiguously ours); harmonic leaders get
#    harmonic-bundle first. NOTE: Harmonic's public endpoint answered "rate limited" (429) to EVERY request on 2026-10-19
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
"""
body = s[len(hdr_old):]
body = body.replace("TAG=${1:-final1}", "TAG=${1:-final2}")
old_routes = [l for l in body.splitlines() if l.startswith("ROUTES=")][0]
body = body.replace(old_routes, 'ROUTES="bam=jito-bundle+landx-fra3+staked-rpc;harmonic=harmonic-bundle+jito-bundle+nozomi+staked-rpc;jito=jito-bundle+landx-fra3+staked-rpc;fd=jito-bundle+astralane+nozomi+staked-rpc;agave=helius+nozomi+staked-rpc;other=helius+nozomi+landx-fra3+staked-rpc;default=jito-bundle+landx-fra3+helius+staked-rpc"')
n0 = body.count("/root/sniper-final/target/release/snipe_engine")
body = body.replace("/root/sniper-final/target/release/snipe_engine", "/root/sniper-final2/target/release/snipe_engine")
a = "--race-pros /root/race/pros.json --race-early \\\n"
assert a in body
body = body.replace(a, a + "  --close-leaders /root/fix2/close_leaders_5ms.txt --max-create-ms 150 \\\n")
b = "--land-poll-ms 100 \\\n"
assert b in body
body = body.replace(b, b + "  --sell-robust --sell-retries 2 --sell-retry-s 4 --strict-balance --jito-poll --landed-via \\\n")
assert "--config /root/lat/final_landing.toml" in body
body = body.replace("--config /root/lat/final_landing.toml", "--config /root/fix2/final2_landing.toml")
body = body.replace("LIVE_FINAL_DONE", "LIVE_FINAL2_DONE")
open("/root/lat/live_final2.sh", "w").write(new_hdr + body)
print("binary refs replaced:", n0)
