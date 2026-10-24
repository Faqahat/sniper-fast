#!/usr/bin/env python3
# GDM forward test, one-time: a frozen copy of the phase-B rows of R2 launches created BEFORE `cut` (from phaseB_fwd, built
# by the 05:38 PKT paper cycle; complete 10-min windows for these launches), so our pipeline never depends on other jobs
# rebuilding phaseB_fwd. usage: python3 -I mk_hist.py <phaseB_fwd> <out dir> <cut_bt>
import sys, os, glob, gzip, json
SRC, OUT, CUT = sys.argv[1], sys.argv[2], float(sys.argv[3])
tmp = OUT + ".tmp"; os.makedirs(tmp, exist_ok=True); n = k = 0
for f in sorted(glob.glob(os.path.join(SRC, "b*.jsonl.gz"))):
    with gzip.open(os.path.join(tmp, os.path.basename(f)), "wt") as fo:
        for l in gzip.open(f, "rt"):
            r = json.loads(l); n += 1
            if (r.get("bt") or 0) < CUT: fo.write(l if l.endswith("\n") else l + "\n"); k += 1
open(os.path.join(tmp, "_ok"), "w").write(f"{k} of {n} rows with bt < {CUT}\n")
os.replace(tmp, OUT)
print(f"phase-B history copy: kept {k} of {n} rows (bt < {CUT:.0f}) -> {OUT}")
