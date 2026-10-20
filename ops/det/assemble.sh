#!/bin/bash
# Build /root/det/report.txt from the saved outputs (READ-ONLY).
cd /root/det
{
echo "##### det audit report — $(date -u +%FT%TZ)"
echo; echo "##### binaries"; md5sum /root/sniper-det/snipe_engine.BEFORE /root/det/snipe_engine.BEFORE.frozen /root/sniper-det/snipe_engine.AFTER /root/sniper-det/snipe_engine.AFTER_FINAL
echo; echo "##### diff stat (det.diff)"; grep "^+++" det.diff; echo "added $(grep -c '^+[^+]' det.diff) removed $(grep -c '^-[^-]' det.diff) lines"
echo; echo "##### 1. on-chain truth sample (20 min, before the runs): truth_an.py truth_sample.jsonl"; cat an_truth_sample.txt
echo; echo "##### drill.py (creator mismatch, quote-mint location, false keeps, failed creates)"; cat an_drill.txt
echo; echo "##### trail.py (raw trailing create_v2 bytes vs CreateEvent; CPI router)"; cat an_trail.txt
echo; echo "##### cpi.py (CPI router txs, flag mismatches, failed-create errors)"; cat an_cpi.txt
echo; echo "##### run-window truth: truth_an.py truth_run.jsonl"; cat an_truth_run.txt
echo; echo "##### 2. BEFORE vs AFTER paper comparison: cmp.py"; cat an_cmp.txt
echo; echo "##### feed race / lag: lat.py paper_A.log"; cat an_lat.txt
echo; echo "##### paper run bookkeeping"; for t in B A; do echo "$t: $(head -1 paper_$t.log | cut -c1-200)"; echo "   launches $(grep -c 'PAPER launch' paper_$t.log) done $(grep -c 'PAPER done' paper_$t.log) (re)launches $(grep -c 'PAPER_DET (re)launch' paper_$t.log) stall-kills $(grep -c 'PAPER_DET stall' paper_$t.log) $(grep PAPER_DET_DONE paper_$t.log)"; done
echo "AFTER FEEDSTATUS lines: $(grep -c FEEDSTATUS paper_A.log)"; grep FEEDSTATUS paper_A.log | head -20
echo "AFTER FEEDS heartbeat (first/last):"; grep "FEEDS t=" paper_A.log | sed -n '1p;$p'
echo; echo "##### PAPER-TRADE RESULT blocks (engine summary)"; for t in B A; do echo "--- $t"; sed -n '/PAPER-TRADE RESULT/,/=======================================$/p' paper_$t.log | tail -40; done
echo; echo "##### 3. close-leaders gate: leaders.py"; cat an_leaders.txt
echo; echo "##### 4. send path: keep-alive round trips (curl, warm = 2nd/3rd line)"; cat an_pings.txt
echo; echo "##### our live landings: measure_land.py live_land_{helius,staked,dual,fast}.log"; cat measure_land.out
echo; echo "##### zero-cost checks: simulateTransaction of our v3 buy on two cap-family launches (AFTER-only fires)"; cat an_sim.txt 2>/dev/null
echo; echo "##### --unwrap dry run (no --live) with probe_det.toml: path build / guards / keep-alive"; cat an_dryrun.txt 2>/dev/null
echo; echo "##### AFTER_FINAL short paper validations (router creates, PoH clock, path dump)"; cat an_final_validation.txt
echo; echo "##### router decode validation (router2.py on the run-window truth)"; cat an_router.txt 2>/dev/null
echo; echo "##### probe_det.toml vs probe_shadow.toml"; diff /root/sniper-det/probe_shadow.toml /root/det/probe_det.toml
} > /root/det/report.txt 2>&1
wc -l /root/det/report.txt
