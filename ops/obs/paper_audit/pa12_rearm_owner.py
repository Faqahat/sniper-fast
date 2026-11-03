#!/usr/bin/env python3
"""PAPER AUDIT step 12 [records only]: the observatory re-arm paper as the owner scored it (row c, 'live' exit policy, sizes 0.40 / 0.65,
minus tries x 5,120 lamports) next to what it leaves out (per-fill fixed costs, MEASURED 2.015 mSOL cash per round trip on r37), per row.
usage: pa12_rearm_owner.py OUT.json OBS.jsonl ..."""
import sys, json, collections
FIX = 2.015e-3; FAIL = 5120 / 1e9
rows = collections.defaultdict(lambda: collections.defaultdict(float))
seen = set(); tries_ok = tries_n = 0; wins = 0; t0 = t1 = None
for p in sys.argv[2:]:
    for line in open(p, errors="replace"):
        if '"ev":"rearm_window"' not in line: continue
        r = json.loads(line)
        k = (r["mint"], r["dump"]["sig"])
        if k in seen: continue
        seen.add(k); wins += 1
        t = r["arm"]["t"]; t0 = t if t0 is None else min(t0, t); t1 = t if t1 is None else max(t1, t)
        tr = r.get("tries") or {}; tries_ok += tr.get("ok", 0); tries_n += tr.get("n", 0)
        for rn, rv in (r.get("rows") or {}).items():
            f = (rv or {}).get("fill")
            if not f: continue
            R = rows[rn]; R["fills"] += 1
            for sz in ("0.40", "0.65"):
                for var in ("px", "px_naive"):
                    for pol in ("live", "t200", "s2"):
                        R[f"{var}_{sz}_{pol}"] += f[var][sz][pol] / 1e3
hours = (t1 - t0) / 3.6e12
out = {"windows": wins, "hours": hours, "tries_ok": tries_ok, "tries_n": tries_n, "tries_fee": tries_ok * FAIL, "rows": {}}
for rn, R in sorted(rows.items()):
    d = dict(R)
    for sz in ("0.40", "0.65"):
        d[f"owner_{sz}"] = R[f"px_{sz}_live"] - tries_ok * FAIL
        d[f"owner_{sz}_minus_fixed"] = d[f"owner_{sz}"] - R["fills"] * FIX
        d[f"owner_{sz}_per_day"] = d[f"owner_{sz}"] / hours * 24
        d[f"owner_{sz}_minus_fixed_per_day"] = d[f"owner_{sz}_minus_fixed"] / hours * 24
    out["rows"][rn] = d
json.dump(out, open(sys.argv[1], "w"), indent=1)
print(json.dumps(out, indent=1))
