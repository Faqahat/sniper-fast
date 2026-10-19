#!/bin/bash
# Assemble /root/race/report.txt (READ-ONLY steps; no engine is started here).
cd /root/race
{
echo "RACE / 4yFAz-LIKE SELECTION STUDY — full output ($(date -u)). Slot time 217 ms. Realistic model = hc_search.sim (2 SOL, land S <=100 txs, x1.03, own impact, pump 1.25%/side, 0.009 SOL buy prio, 0.001/sell)."
echo; echo "################ 0. FINAL OVERNIGHT FORWARD VALIDATION (eval_night.py night) ################"; cat eval_night.txt 2>/dev/null
echo; echo "################ 00. SOL/DAY RANKING on the blind run (eval_rank.py night; exits frozen in EXIT_FREEZE.json) ################"; cat eval_rank_night.txt 2>/dev/null; cat EXIT_FREEZE.json
echo; echo "################ 0a. same frozen gate on the MERGED binary (eval_night.py mnight) ################"; cat eval_mnight.txt 2>/dev/null
echo; echo "################ 0b. realistic scorer on the overnight runs (score_run.py night / mnight) ################"; cat score_night.txt 2>/dev/null; cat score_mnight.txt 2>/dev/null
echo; echo "################ 0c. LANDING STUDY (landing_study.py) ################"; cat landing_study.txt 2>/dev/null
echo; echo "################ 0d. X/Twitter signal, forward, fetched at launch time (tweets_fwd.py) ################"; cat tweets_fwd.txt 2>/dev/null
echo; echo "################ 1. FROZEN gate / pre-registration ################"; cat FROZEN_GATE.txt; cat PREREG_v2.json
echo; echo "################ 2. LANDING REQUIREMENT (land_req.py) ################"; cat land_req.txt
echo; echo "################ 3. HIGH-CONVICTION search, realistic (hc_search.py on hist + forward run 1) ################"; cat hc_fwd1.txt
echo; echo "################ 4. MULTI-PERIOD robust search (hc_multi_v2.txt) ################"; cat hc_multi_v2.txt
echo; echo "################ 5. HIS-LIKE SCORE + X/Twitter features (his_score.py) ################"; cat his_score.txt
echo; echo "################ 6. Forward run 1 realistic scorer (score_run.py fwd) ################"; cat score_fwd.txt
echo; echo "################ 7. Forward run 1, older cost model (fwd_eval.py) ################"; cat fwd_eval.txt
echo; echo "################ 8. Off-chain latency measured live (meta_night.jsonl) ################"
python3 - <<PY
import json, statistics as st
R=[json.loads(l) for l in open("/root/race/meta_night.jsonl")]
ok=[r for r in R if r.get("meta")]; tw=[r for r in R if r.get("tw_ms")]
q=lambda v,p: sorted(v)[int(p*(len(v)-1))] if v else None
print("launches", len(R), "| metadata ok", len(ok), "meta_ms p50/p90", q([r["meta_ms"] for r in ok],.5), q([r["meta_ms"] for r in ok],.9),
      "| with X data", len(tw), "total_ms p50/p90", q([r["total_ms"] for r in tw],.5), q([r["total_ms"] for r in tw],.9))
PY
echo; echo "################ 9. HISTORICAL RACE ANALYSIS (race_an.py; OLDER cost model) ################"; cat an_final.txt
echo; echo "################ 10. ROBUSTNESS (gate_variants.py; OLDER cost model) ################"; cat gate_variants.txt
echo; echo "################ 11. TODAY'S 42 LIVE FIRES ON CHAIN ################"; python3 label_onchain.py live_fires.jsonl; cat live_land_pos.txt
echo; echo "################ 12. EXISTING SCRIPT /root/bsplit/real_his.py on forward run 1 (entry behind the bundle x slip; optimistic) ################"
python3 mk_bsplit_out.py paper_fwd.log fwd_onchain.jsonl /root/race/out_fwd > /dev/null 2>&1
echo "--- FIRED by the run-1 stream gate"; python3 /root/bsplit/real_his.py fwd_fired /root/race/out_fwd_fired.jsonl /root/race/paths_fwd.jsonl 2>&1 | grep -A2 "########\|FORWARD"
echo "--- REJECTED"; python3 /root/bsplit/real_his.py fwd_rejected /root/race/out_fwd_rejected.jsonl /root/race/paths_fwd.jsonl 2>&1 | grep -A2 "########\|FORWARD"
} > report.txt 2>&1
wc -l report.txt
