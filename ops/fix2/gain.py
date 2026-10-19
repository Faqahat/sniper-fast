#!/usr/bin/env python3
# READ-ONLY: for the census fires (census_rows.json: gate verdicts from chain), the first OUTSIDER buy seen in shreds after
# the create (RACE obs first_ms, ms after our first sight; -1 = none in the 200 ms window). We are first outsider if our
# copy lands before it: our bundle path lands ~45-60 ms after the create = ~33-48 ms after our first sight (final1).
import sys, re, json, collections
rows = {r["mint"]: r for r in json.load(open("/root/fix2/census_rows.json"))}
obs = {}
for f in sys.argv[1:]:
    for l in open(f, errors="replace"):
        m = re.search(r"RACE obs slot=\d+ mint=(\w+) .*?first_ms=([\-\d.]+)", l)
        if m:
            obs.setdefault(m.group(1), float(m.group(2)))
for name, sel in (("all fires", lambda r: True), ("near (<5 ms)", lambda r: r["close"]), ("near + create<=150 (both gates)", lambda r: r["close"] and r["truth"] is not None and r["truth"] <= 150)):
    rs = [r for r in rows.values() if sel(r) and r["mint"] in obs]
    if not rs:
        continue
    out = []
    for T in (35, 50):
        ok = sum(1 for r in rs if obs[r["mint"]] < 0 or obs[r["mint"]] > T)
        out.append(f"P(no outsider seen before +{T} ms) {ok}/{len(rs)} = {ok/len(rs):.0%}")
    fm = sorted(obs[r["mint"]] for r in rs if obs[r["mint"]] >= 0)
    print(f"{name}: n={len(rs)}; " + "; ".join(out) + (f"; first outsider median {fm[len(fm)//2]:.0f} ms (n={len(fm)}, none {len(rs)-len(fm)})" if fm else ""))
