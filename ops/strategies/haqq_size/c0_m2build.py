#!/usr/bin/env python3
"""HAQQ_SIZE step C0 (read-only, offline): regular-dip (M2) dump rows at another size for the held-out 24 h, exactly
haqq_model/m0_m2build55.py (haqq_sel's day arrays, dipdetect/dd1_build.py unchanged, epoch 1068/1069 leader map), only DD_SIZE
differs. usage: DD_SIZE=0.80 c0_m2build.py   -> /home/moiz/sniper-data/haqq_size/m2/dd1_HQ_s0.8.npz"""
import os, sys
SZ = os.environ["DD_SIZE"]
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_sel")
import h2_m2build as H2
os.environ["DD_SIZE"] = SZ
import dd1_build as DB
assert abs(DB.SIZE - float(SZ)) < 1e-9
DB.DAYS["HQ"] = "/home/moiz/sniper-data/haqq_sel/m2/work"; DB.RUNDIR["HQ"] = "../haqq_sel/m2/run_HQ"; DB.IMIT2["HQ"] = []
DB.OUT = "/home/moiz/sniper-data/haqq_size/m2"
DB.leader_map = H2.leader_map
if __name__ == "__main__":
    DB.main("HQ", 10)
