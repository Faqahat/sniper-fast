#!/usr/bin/env python3
"""CLIENTS study: does the short first block of a leader window explain the turn-slot-1 spills? (MEASURED + CODE model)
CODE (agave core/src/block_creation_loop.rs block_timeout): block k of the window ends at 200*(k+1) - 56 ms after the window start,
so block 1 lasts <= 144 ms and blocks 2-4 200 ms. Model the time left after the dump as (1 - idx/n) x block length."""
import csv, collections
rows = list(csv.DictReader(open("/home/moiz/sniper-data/speed_truth/attempts.csv")))
def blen(r): return 144.0 if int(r["dump_slot"]) % 4 == 0 else 200.0
agave_family = {"JitoLabs", "AgaveBam", "HarmonicAgave", "Rakurai", "Agave"}
for fam, sel in (("Agave-family", lambda r: r["client"] in agave_family and r["client"] != "Rakurai"),
                 ("JitoLabs", lambda r: r["client"] == "JitoLabs"), ("AgaveBam", lambda r: r["client"] == "AgaveBam"),
                 ("Harmonic(both)", lambda r: "Harmonic" in r["client"])):
    t = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        if not sel(r): continue
        n, i = int(r["dump_block_n"]), int(r["dump_idx"])
        left = (1 - i / max(n, i + 1)) * blen(r)
        land = float(r["land_feed_ms"])
        need = "ours<left" if land < left else "ours>=left"
        k = ("T1" if int(r["dump_slot"]) % 4 == 0 else "T2-4", need)
        t[k][0] += 1; t[k][1] += r["slot_delta"] != "0"
    print(fam, "  ".join(f"{a}/{b}: spill {t[(a,b)][1]}/{t[(a,b)][0]}" for a in ("T1", "T2-4") for b in ("ours<left", "ours>=left")))

print("\nspill rate by MODELED time left after the dump (block 1 = 144 ms, blocks 2-4 = 200 ms) vs the old 212 ms model")
for fam, sel in (("JitoLabs", lambda r: r["client"] == "JitoLabs"), ("Agave-family excl. Rakurai", lambda r: r["client"] in agave_family and r["client"] != "Rakurai")):
    for model in ("new", "old212"):
        t = collections.defaultdict(lambda: [0, 0])
        for r in rows:
            if not sel(r): continue
            n, i = int(r["dump_block_n"]), int(r["dump_idx"])
            L = blen(r) if model == "new" else 212.0
            left = (1 - i / max(n, i + 1)) * L
            b = "<40" if left < 40 else "40-80" if left < 80 else "80-120" if left < 120 else ">=120"
            k = ("T1" if int(r["dump_slot"]) % 4 == 0 else "T2-4", b)
            t[k][0] += 1; t[k][1] += r["slot_delta"] != "0"
        print(f"  {fam:27s} {model:6s} " + " | ".join(f"{tt} " + " ".join(f"{b}:{t[(tt,b)][1]}/{t[(tt,b)][0]}" for b in ("<40", "40-80", "80-120", ">=120")) for tt in ("T1", "T2-4")))
