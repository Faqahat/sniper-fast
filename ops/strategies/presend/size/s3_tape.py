#!/usr/bin/env python3
"""SIZE study step 3: REPLAY_065 tape.py on the r26-r28 extraction (same code, paths patched). MEASURED chain tape.
Writes /home/moiz/sniper-data/presend_size/tape.pkl"""
import sys
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real/r065")
import tape as T
T.RAW = "/home/moiz/sniper-data/presend_size/raw"
T.OUT = "/home/moiz/sniper-data/presend_size/tape.pkl"
if __name__ == "__main__":
    T.main()
