#!/usr/bin/env python3
"""Per-slot max pump tx index (block-size proxy, same convention as dv8/haqqml slots.npy) for slots after the haqqml/fresh
slot table ends (10-28 18:41 PKT) up to the end of the local recordings. Out: sniper-data/e2x1_dissect/exec/slots_tail.npy"""
import gzip, glob, re, numpy as np, os
S0 = 462496998
fs = sorted(f for f in glob.glob("/home/moiz/sniper-data/collect/run_2026102[78]_*/txs/txs_*.jsonl.gz") if int(re.findall(r"txs_(\d+)", f)[0]) >= 1793194200)
pat = re.compile(rb'^\{"s":(\d+),"i":(\d+),"bt":(\d+)')
mx = {}; bt = {}; n = {}
for f in fs:
    try:
      with gzip.open(f) as g:
        for line in g:
            m = pat.match(line)
            if not m: continue
            s = int(m.group(1))
            if s <= S0: continue
            i = int(m.group(2))
            if i > mx.get(s, -1): mx[s] = i
            n[s] = n.get(s, 0) + 1; bt[s] = int(m.group(3))
    except EOFError:
        print("truncated (still being written):", f)
    print(f, len(mx), flush=True)
ks = sorted(mx)
a = np.zeros(len(ks), dtype=[('slot', '<u8'), ('maxi', '<u4'), ('n', '<u4'), ('bt', '<u4')])
a['slot'] = ks; a['maxi'] = [mx[k] for k in ks]; a['n'] = [n[k] for k in ks]; a['bt'] = [bt[k] for k in ks]
np.save("/home/moiz/sniper-data/e2x1_dissect/exec/slots_tail.npy", a); print(len(a), ks[0], ks[-1])
