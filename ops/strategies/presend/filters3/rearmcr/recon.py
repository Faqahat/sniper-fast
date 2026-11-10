#!/usr/bin/env python3
"""REARM-CREATOR step 2: rebuild the creator's holding at a re-arm arm from the raw 24/7 recording (r38 has no ann.cr_pct).
Validated on r39/r40 (same recording) against the engine's own ann.cr_pct. Creator = launches.jsonl "creator";
holding = creator's token balance (tb post, owner == creator) after the last tx on the mint with slot < arm_slot.
out: /home/it/sniper-data/filters3/rearmcr/recon.json {"r38:w": pct, ...}"""
import json, gzip, os, sys
from multiprocessing import Pool
D = "/home/it/sniper-data"; RD = f"{D}/collect/run_20261029_1400"
arms = {}
for r in (38, 39, 40):
    for l in open(f"{D}/filters3/rearmcr/ext/r{r}.jsonl"):
        if '"presend_live_arm"' not in l or '"kind":"rearm"' not in l: continue
        d = json.loads(l)
        arms[f"r{r}:{d['w']}"] = (d["mint"], d["arm_slot"], d["dump"]["t"] // 10**9, (d.get("ann") or {}).get("cr_pct"))
mints = {a[0] for a in arms.values()}
cre = {}
for l in open(f"{RD}/launches.jsonl"):
    i = l.find('"mint":"'); m = l[i + 8:l.find('"', i + 8)]
    if m in mints: d = json.loads(l); cre[m] = d["creator"]
t0 = min(a[2] for a in arms.values()) - 600; t1 = max(a[2] for a in arms.values()) + 60
files = [f for f in sorted(os.listdir(f"{RD}/txs")) if t0 - 300 <= int(f.split("_")[1].split(".")[0]) <= t1]
def job(fn):
    out = []
    with gzip.open(f"{RD}/txs/{fn}", "rt", errors="replace") as f:
        try:
            for l in f:
                i = l.find('"mints":[')
                if i < 0: continue
                seg = l[i + 9:l.find("]", i)]
                ms = [x.strip('"') for x in seg.split(",") if x.strip('"') in cre]
                if not ms: continue
                d = json.loads(l)
                if d.get("err") is not None: continue
                for mm, own, pre, post in d.get("tb") or []:
                    if mm in cre and own == cre[mm]: out.append((mm, d["s"], d.get("i") or 0, post or 0))
        except EOFError: pass
    return out
if __name__ == "__main__":
    ev = {}
    with Pool(3) as p:
        for o in p.imap_unordered(job, files):
            for mm, s, i, post in o: ev.setdefault(mm, []).append((s, i, post))
    for v in ev.values(): v.sort()
    res = {}; cmp = []
    for k, (m, aslot, _, cp) in arms.items():
        if m not in cre: res[k] = None; continue
        bal = 0
        for s, i, post in ev.get(m, []):
            if s >= aslot: break
            bal = post
        pct = bal / 1e15 * 100; res[k] = pct
        if cp is not None: cmp.append((cp, pct))
    json.dump({"files": len(files), "creators": len(cre), "arms": len(arms), "pct": res}, open(f"{D}/filters3/rearmcr/recon.json", "w"))
    import statistics
    ok = sum(1 for a, b in cmp if abs(a - b) < 0.5); band = lambda x: 0 if x < 2 else 1 if x < 6 else 2
    agree = sum(1 for a, b in cmp if band(a) == band(b)); a6 = sum(1 for a, b in cmp if (a >= 6) == (b >= 6))
    print("files", len(files), "creators", len(cre), "/", len(mints), "validated", len(cmp), "within0.5pt", ok, "band_agree", agree, "6pct_agree", a6)
    bad = [(a, b) for a, b in cmp if (a >= 6) != (b >= 6)][:15]; print("disagree@6", bad)
    r38 = [v for k, v in res.items() if k.startswith("r38:")]
    print("r38 arms", len(r38), "none", sum(v is None for v in r38), ">=6", sum(1 for v in r38 if v is not None and v >= 6))
