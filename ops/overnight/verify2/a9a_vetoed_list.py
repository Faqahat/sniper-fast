#!/usr/bin/env python3
"""verify2 / a9a: launches the FINAL-2 models picked but the mid-window guards (added 00:18 PKT) vetoed, up to the last pick
(07:06 PKT bt cutoff of the pick list) -> work/a9_guard_vetoed.json. Then: python3 -I x1_extract.py work/a9_guard_vetoed.json x9"""
import json, os, datetime
PKT = datetime.timezone(datetime.timedelta(hours=5))
th = json.load(open("/home/moiz/sniper-data/collect/paper/frozen_live3_fsell.json"))["thresholds"]["5%"]
cut = -1.360678720987847                                           # final_config2.json veto_cut
vet = []; first_g = None
for l in open("/home/moiz/sniper-data/collect/shadow/scores_v3.jsonl"):
    r = json.loads(l)
    if r.get("type") != "decide" or r.get("final") != "FINAL-2+guards": continue
    first_g = first_g or r["t"]
    if r.get("quote") == "sol" and r["final_score"] >= th and (r["veto_score"] is None or r["veto_score"] < cut) and not r.get("guard"):
        if r["t"] <= 1792724764 + 5: vet.append(r["mint"])
print("first FINAL-2+guards record", datetime.datetime.fromtimestamp(first_g, PKT), "| guard-vetoed would-be picks:", len(vet))
json.dump(vet, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "work", "a9_guard_vetoed.json"), "w"))
