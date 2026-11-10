#!/usr/bin/env python3
"""export every APEX-3 serial-creator launch (mint, creator, bt, day, sel) for the realistic-label watchlist"""
import sys, json, numpy as np
sys.path.insert(0, "/home/it/sniper-studies/sniper-apexcmp/code")
import run3_lib as R3
L, day, sel = R3.L, R3.day, R3.sel
json.dump([dict(mint=r[0], creator=r[1], bt=int(r[2]), day=int(day[i]), sel=bool(sel[i])) for i, r in enumerate(L)],
          open("/home/it/sniper-data/apex2/realism/all_launches.json", "w"))
print(len(L))
