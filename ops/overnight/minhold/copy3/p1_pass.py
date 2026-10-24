#!/usr/bin/env python3
# ONE PASS over all phase-A tapes (R1, R2, R3), read-only:
#  1. per-slot max tx index seen (block-size estimate, like core/slotsize2.py) -> raw/slotmax_<run>.json
#  2. full tapes (+ failed-tx rows) of every token the 3 study wallets traded -> raw/tapes/<run>_<b>.pkl.gz
#  3. snapshot features at fixed ages for a 25% random sample of launches (the "what they skip" control) -> out/snap_ctl.jsonl.gz
#  4. light summary of every launch (trades, max curve SOL, mayhem) -> out/launch_sum.json
import os, sys, json, gzip, pickle, zlib, collections
os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd"); os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3"); os.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core"); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rp, feat
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__))
L = rp.load_launches()
C3 = json.load(open(os.path.join(HERE, "out/census3.json")))
WM = collections.defaultdict(set)
for r in C3: WM[r[2]].add(r[1])
G = [5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 240, 300, 420, 600, 900, 1200, 1800]
def ctl(m): return zlib.crc32((m + "ctl").encode()) % 4 == 0
def work(key):
    run, b = key
    keep = {m for m in WM[run] if feat.bucket(m) == b}
    tapes, fail, mx = feat.read_bucket_all(run, b, keep)
    snaps = []; summ = {}
    for m, tr in tapes.items():
        c = L.get(m)
        if not c or c["run"] != run: continue
        may = feat.is_mayhem(tr)
        summ[m] = (len(tr), max(t["vsol"] for t in tr) / 1e9, may)
        if may or not ctl(m) or m in keep: continue
        st = feat.structure(tr, c); S = c["slot"]; n = 0
        for g in G:
            now = S + int(g / feat.SL)
            while n < len(tr) and tr[n]["s"] < now: n += 1
            if n == 0: continue
            last = tr[n - 1]
            if last["vsol"] >= 110e9: break
            if g > 30 and (now - last["s"]) * feat.SL > 120: continue
            f = feat.snapshot(tr, c, st, n, now)
            f.update(feat.forward(tr, n, now, feat.px(last["vsol"], last["vtok"])))
            f.update(m=m, run=run, g=g, bt=c["bt"])
            snaps.append(f)
    os.makedirs(os.path.join(HERE, "raw/tapes"), exist_ok=True)
    with gzip.open(os.path.join(HERE, f"raw/tapes/{run}_{b:03d}.pkl.gz"), "wb") as fo:
        pickle.dump(dict(tapes={m: tapes[m] for m in keep if m in tapes}, fail={m: fail.get(m, []) for m in keep}), fo)
    return run, mx, snaps, summ
if __name__ == "__main__":
    keys = [(run, b) for run in ("R1", "R2", "R3") for b in range(256)]
    MX = collections.defaultdict(dict); SUM = {}; n = 0
    with Pool(8) as p, gzip.open(os.path.join(HERE, "out/snap_ctl.jsonl.gz"), "wt") as fs:
        for run, mx, snaps, summ in p.imap_unordered(work, keys):
            for s, i in mx.items():
                if i > MX[run].get(s, -1): MX[run][s] = i
            for f in snaps: fs.write(json.dumps(f, separators=(",", ":")) + "\n")
            SUM.update(summ); n += 1
            if n % 32 == 0: print("buckets", n, "/", len(keys), flush=True)
    for run in MX: json.dump({str(s): i + 1 for s, i in MX[run].items()}, open(os.path.join(HERE, f"raw/slotmax_{run}.json"), "w"))
    json.dump(SUM, open(os.path.join(HERE, "out/launch_sum.json"), "w"))
    print("done", flush=True)
