#!/usr/bin/env python3
"""REAL replay: the test hours (pre-registered in REAL_REPLAY.md 0.2). Every 10-minute bin of the four recordings with >= 95% of
its slots recorded, minus the probe hours (10-25 08:38-10:28 and 15:20-17:40 PKT), minus the first 30 min of each recording
(tokens created before a recording starts have no history, as after an engine start), minus the newest 40 min (the
recording's tail may still be copying). Halves: the test bins in time order, split at half the total hours.
Writes /home/moiz/sniper-data/presend_real/hours.json"""
import sys, os, json, glob
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib

REC = ["run_20261021_2207", "run_20261022_1543", "run_20261023_1426", "run_20261024_1425"]
PROBES = [("10-25 08:38", "10-25 10:28"), ("10-25 15:20", "10-25 17:40")]

def main():
    S = np.load(f"{rlib.TAB}/slots.npy")
    slot = S["slot"].astype(np.int64); bt = S["bt"].astype(np.int64)
    # slot -> time: a linear fit per recording region on block times (bt has 1 s resolution)
    starts = [json.load(open(f"/home/moiz/sniper-data/collect/{r}/run.json"))["start_time"] for r in REC]
    t_lo = int(bt[bt > 0].min()); t_hi = int(bt[bt > 0].max())
    B = 600
    b0 = t_lo // B * B
    nb = (t_hi - b0) // B + 1
    # recorded slots per bin vs expected slots per bin (from the slot range spanned by the bin's block times)
    k = (bt - b0) // B
    rec = np.bincount(k, minlength=nb)
    smin = np.full(nb, np.iinfo(np.int64).max); smax = np.full(nb, -1)
    np.minimum.at(smin, k, slot); np.maximum.at(smax, k, slot)
    out = []
    for b in range(nb):
        t0 = b0 + b * B
        if rec[b] == 0: continue
        exp = 600 / 0.2123                              # ~2826 slots per 10 min (212.3 ms slots, MEASURED over the recording)
        cov = rec[b] / exp
        ok = cov >= 0.95
        why = None if ok else "coverage"
        for a, e in PROBES:
            if t0 + B > rlib.pk(a) and t0 < rlib.pk(e): why = "probe"
        for st in starts:
            if st <= t0 < st + 1800: why = why or "warmup"
        if t0 + B > t_hi - 2400: why = why or "tail"
        out.append(dict(t0=t0, t1=t0 + B, cov=round(float(cov), 3), why=why, s_lo=int(smin[b]), s_hi=int(smax[b])))
    test = [x for x in out if x["why"] is None]
    tot = len(test) * B / 3600
    half = len(test) // 2
    for i, x in enumerate(test): x["half"] = 1 if i < half else 2
    J = dict(bins=out, test=test, hours=tot, half_split=rlib.pkt(test[half]["t0"]))
    json.dump(J, open("/home/moiz/sniper-data/presend_real/hours.json", "w"))
    from collections import Counter
    print("bins", len(out), "excluded", Counter(x["why"] for x in out if x["why"]), "test hours %.1f" % tot,
          "from", rlib.pkt(test[0]["t0"]), "to", rlib.pkt(test[-1]["t1"]), "| half 2 starts", J["half_split"])
    # per day (PKT date) hours
    d = Counter(rlib.pkt(x["t0"], "%m-%d") for x in test)
    print("test hours per PKT day", {k: round(v * B / 3600, 1) for k, v in sorted(d.items())})

if __name__ == "__main__":
    main()
