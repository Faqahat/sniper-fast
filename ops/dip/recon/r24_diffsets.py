#!/usr/bin/env python3
# r24: dumps the replay (engine rules, measured landing) would trade but live did not, and the reverse, with the live reason.
import sys, os, json, collections, pickle
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib as R, rsim as S
from r08_forecast import load_dumps, engine
F = json.load(open(f"{R.WORK}/fires.json")); runs = {(r["srv"], r["run"]): r for r in F["runs"]}
detail = pickle.load(open(f"{R.WORK}/forecast_rows.pkl", "rb"))     # r08 rows with outcomes per latency incl. "meas"
skips = {}
for srv, rn, base in R.RUN_FILES:
    for l in open(f"{R.LIVE}/{base}.jsonl"):
        if '"pick_skip"' in l[:200] or '"pick_skip"' in l:
            try: o = json.loads(l)
            except Exception: continue
            if o.get("ev") == "pick_skip": skips[(srv, o["sig"])] = o["why"]
fired = {(r["srv"], r["dump_sig"]) for r in F["rows"]}
c = collections.Counter(); val = collections.defaultdict(float); rev = collections.Counter()
for (srv, rn), rows in detail.items():
    e = engine(rows, lambda x: x["oc"].get("meas"))
    used = {r_["sig"] for r_, oc, p in e["used"]}
    for r_, oc, p in e["used"]:
        if (srv, r_["sig"]) not in fired:
            why = skips.get((srv, r_["sig"]), "no live skip record")
            c[why] += 1; val[why] += p
    for r_ in rows:
        if (srv, r_["sig"]) in fired and r_["sig"] not in used:
            rev["replay busy/spacing (live fired)"] += 1
print("replay attempts that live did not fire:", dict(c), {k: round(v, 3) for k, v in val.items()})
print("live fires the replay did not attempt:", dict(rev))
