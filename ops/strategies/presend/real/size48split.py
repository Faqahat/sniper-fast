#!/usr/bin/env python3
"""SIZE_48H: the 48 h result split by hour type (REAL_REPLAY's old test hours / live-probe hours / hours newer than REAL_REPLAY's
tape), and each probe's own hours inside the 48 h stream (read-only; from s48/size48_<tag>.pkl)."""
import sys, os, pickle, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s48lib, rlib
tag = sys.argv[1] if len(sys.argv) > 1 else "main"
X = pickle.load(open(f"{s48lib.S48}/size48_{tag}.pkl", "rb")); H = X["H"]
st = {x["t0"]: (x["status"], x["probe"]) for x in H["use"]}
hrs = collections.Counter(v[0] for v in st.values()); hp = collections.Counter(v[1] for v in st.values() if v[1])
for (size, cut), lst in sorted(X["R"].items()):
    if cut not in (0.0, 0.2): continue
    by = collections.defaultdict(list); bp = collections.defaultdict(list); fp = collections.defaultdict(list)
    for seed, rows in lst:
        a = collections.Counter(); b = collections.Counter(); f = collections.Counter()
        for r in rows:
            s, p = st[r[0] // 600 * 600]; a[s] += r[2]
            if p: b[p] += r[2]; f[p] += r[1]
        for k in hrs: by[k].append(a[k] / 1e9)
        for k in hp: bp[k].append(b[k] / 1e9); fp[k].append(f[k])
    print(f"size {size:.2f} cut {cut:.1f}: " + " | ".join(f"{k} {hrs[k] / 6:.1f} h: {np.mean(v):+.2f} SOL ({np.mean(v) / hrs[k] * 6 * 24:+.2f}/day)" for k, v in sorted(by.items()))
          + " || " + " | ".join(f"{k} ({hp[k] / 6:.1f} h) net {np.mean(v):+.3f} [{np.percentile(v, 5):+.3f}, {np.percentile(v, 95):+.3f}] fills {np.mean(fp[k]):.0f}" for k, v in sorted(bp.items())))
