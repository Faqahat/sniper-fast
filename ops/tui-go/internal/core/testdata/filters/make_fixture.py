"""Trim a run's records to what the Filters table reads (plus run_start / the live position records so the UI shows
trades): every presend_* record but presend_attempt (one deep T2 try per window kept), presend_attempt_land, tape.
usage: python3 -I make_fixture.py IN.jsonl OUT.jsonl"""
import sys, json
KEEP = {"presend_arm", "presend_exit", "presend_fill", "presend_live_skip", "presend_live_arm", "presend_live_fill",
        "presend_live_realized", "presend_live_close", "presend_live_exit", "presend_live_disarm", "presend_live_sell_land",
        "presend_live_ata_close", "run_start", "run_end"}
seen = set()
with open(sys.argv[1], errors="replace") as f, open(sys.argv[2], "w") as o:
    for line in f:
        i = line.find('"ev":"')
        if i < 0: continue
        ev = line[i + 6:line.find('"', i + 6)]
        if ev == "presend_attempt":
            if '"drop":' not in line or '"kind":"rearm"' in line: continue
            d = json.loads(line)
            if d.get("drop") is None or not d["drop"] > 0.125 or d.get("w") in seen: continue
            seen.add(d.get("w"))
            o.write(line)
        elif ev in KEEP:
            o.write(line)
