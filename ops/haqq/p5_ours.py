#!/usr/bin/env python3
# haqq SEND PATHS, part 5 (local): OUR fires/fills (FRA 2g7rYv7y, AMS EgxfYgEb; runs 9+) with the same block-position delay proxy
# as haqq's dip buys: landed path, leader client, delay after the dump, same-slot share, guard / 6042 failures, fees.
import sys, json, glob, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H
SS = {}
for run in ("R1", "R2", "R3", "R4"):
    for k, v in json.load(open(f"{H.OUT}/slotmax_{run}.json")).items(): SS[int(k)] = max(SS.get(int(k), 0), v + 1)
def A(s, i): return s * H.SMS + i / max(SS.get(s, 400), i + 1) * H.SMS
rows = []
for f in sorted(glob.glob("/home/moiz/sniper-data/runs/fra/runs/dip_r*.jsonl") + glob.glob("/home/moiz/sniper-data/runs/ams/runs/dip_ams_r*.jsonl")):
    srv = "AMS" if "ams" in f else "FRA"; run = int(f.split("_r")[-1].split(".")[0])
    if run < 9: continue
    fires = {}; lands = {}; fails = {}; closes = {}
    for l in open(f):
        try: r = json.loads(l)
        except Exception: continue
        e = r.get("ev")
        if e == "fire": fires[r["buy_sig"]] = r
        elif e == "buy_land": lands[r["mint"]] = r
        elif e == "buy_failed": fails[r["mint"]] = r
        elif e == "close": closes[r["buy_sig"]] = r
    for sig, fr in fires.items():
        c = closes.get(sig) or {}
        bl = lands.get(fr["mint"]) if c.get("result") == "sold" or fr["mint"] in lands else None
        row = dict(srv=srv, run=run, client=fr.get("client"), mint=fr["mint"], filled=bl is not None, result=c.get("result"))
        if bl and c.get("dump_slot") is not None:
            row.update(path="+".join(bl["variant"]["paths"]) if bl.get("variant") else "?", tip=bl.get("variant", {}).get("tip"), fee=bl.get("fee"),
                       delay=A(bl["slot"], bl["idx"]) - A(c["dump_slot"], c["dump_idx"]), same=bl["slot"] == c["dump_slot"], ds=bl["slot"] - c["dump_slot"])
        rows.append(row)
json.dump(rows, open(f"{H.OUT}/ours_fires.json", "w"))
for grp, sel in (("FRA runs 9-15", [r for r in rows if r["srv"] == "FRA"]), ("AMS runs 9-14", [r for r in rows if r["srv"] == "AMS"]), ("both, runs 11+", [r for r in rows if r["run"] >= 11])):
    fl = [r for r in sel if r["filled"] and "delay" in r]
    print(f"\n== {grp}: fires {len(sel)}, fills {sum(r['filled'] for r in sel)} ({sum(r['filled'] for r in sel) / max(1, len(sel)):.0%})")
    if fl:
        d = [r["delay"] for r in fl]
        print(f"   delay after the dump (block-position ms) p25/50/75: {' / '.join(f'{x:.0f}' for x in np.percentile(d, (25, 50, 75)))}; same slot {np.mean([r['same'] for r in fl]):.0%}")
        print("   landed path:", collections.Counter(r["path"] for r in fl).most_common(6))
        print("   leader client of fills:", collections.Counter(r["client"] for r in fl).most_common(6))
        print("   buy fee lamports:", collections.Counter(r["fee"] for r in fl).most_common(3), "| tip:", collections.Counter(r["tip"] for r in fl).most_common(4))
    print("   fill rate by leader client:", {k: f"{sum(r['filled'] for r in sel if r['client'] == k)}/{sum(1 for r in sel if r['client'] == k)}" for k in sorted({r['client'] for r in sel if r['client']})})
