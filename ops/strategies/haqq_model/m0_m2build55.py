#!/usr/bin/env python3
"""HAQQ_MODEL step M0 (read-only, offline): regular-dip (M2) dump rows at 0.55 SOL for the haqq_sel 24 h window
(10-26 23:15 -> 10-27 23:15 PKT). Reuses haqq_sel's day arrays (haqq_sel/m2/work/day_HQ.npz, built by haqq_sel/h2_m2build.py)
and runs only the study's dd1 stage (dipdetect/dd1_build.py, unchanged) at DD_SIZE=0.55 with the epoch 1068/1069 leader map.
Out: /home/moiz/sniper-data/haqq_model/m2/dd1_HQ.npz (+ dd1_meta.json)."""
import os, sys
os.environ["DD_SIZE"] = "0.55"
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_sel")
import h2_m2build as H2          # (sets DD_SIZE=0.5 on import; reset next)
os.environ["DD_SIZE"] = "0.55"
import dd1_build as DB
assert DB.SFX == "" and DB.SIZE == 0.55
DB.DAYS["HQ"] = "/home/moiz/sniper-data/haqq_sel/m2/work"; DB.RUNDIR["HQ"] = "../haqq_sel/m2/run_HQ"; DB.IMIT2["HQ"] = []
DB.OUT = "/home/moiz/sniper-data/haqq_model/m2"; os.makedirs(f"{DB.OUT}/live", exist_ok=True)
DB.leader_map = H2.leader_map
if __name__ == "__main__":
    DB.main("HQ", 10)
