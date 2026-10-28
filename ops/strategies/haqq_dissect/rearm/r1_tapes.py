#!/usr/bin/env python3
"""REARM step 1 (read-only): cut the dv8 chain tape (/home/moiz/sniper-data/dv8/tab, built by presend/real/decode.py + build.py from
the 24/7 recording, 10-22 03:07 -> 10-28 01:12 PKT) into sub-tabs the presend/real replay (rlib.Tape) can load:
  * one per test day D0..D6 (dv8 days, 23:15 PKT boundaries), slots from day start - 60 min to day end + 10 min;
  * one per live pre-send run used for validation (its run_start - 60 min .. its last record + 10 min).
Each sub-tab: trades.npy (the rows of that slot range, chain order kept), slots.npy, ids.json (symlink to the full id list: the
ids stay global), creates.json (creates inside the sub-tab's range only: a token created before the range is not followed, as the
live engine follows only tokens it saw created). Out: /home/moiz/sniper-data/haqq_dissect/rearm/tab_<name>/"""
import os, sys, json, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L

OUT = "/home/moiz/sniper-data/haqq_dissect/rearm"
RUNS = {
    "a24": "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r24.jsonl", "a25": "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r25.jsonl",
    "a26": "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r26.jsonl", "a27": "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r27.jsonl",
    "a28": "/home/moiz/sniper-data/presend_filter/live28/dip_ams_r28.jsonl",
    "a29": "/home/moiz/sniper-data/haqq_strat/live/dip_ams_r29.jsonl", "a30": "/home/moiz/sniper-data/haqq_strat/live/dip_ams_r30.jsonl",
    "a31": "/home/moiz/sniper-data/haqq_strat/live/dip_ams_r31.jsonl", "a32": "/home/moiz/sniper-data/haqq_strat/live/dip_ams_r32.jsonl",
    "a33": "/home/moiz/sniper-data/haqq_strat/live/dip_ams_r33.jsonl", "f26": "/home/moiz/sniper-data/runs/fra/runs/dip_r26.jsonl",
    "f24": "/home/moiz/sniper-data/runs/fra/runs/dip_r24.jsonl", "f23": "/home/moiz/sniper-data/runs/fra/runs/dip_r23.jsonl",
}


def run_range(fn):
    t0 = t1 = None
    for l in open(fn, errors="ignore"):
        if '"presend_live_arm"' in l or '"presend_live_disarm"' in l or ('"run_start"' in l and t0 is None):
            try: r = json.loads(l)
            except Exception: continue
            if r.get("ev") == "run_start" and not r.get("presend_live"): continue
            t = r.get("t")
            if t is None: continue
            t0 = t if t0 is None else min(t0, t); t1 = t if t1 is None else max(t1, t)
    return t0 / 1e9, t1 / 1e9


def main(which):
    T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
    S = np.load(f"{L.TAB}/slots.npy")
    sl_all = np.asarray(T["slot"])
    bt = S["bt"].astype(np.int64); ss = S["slot"].astype(np.int64)
    print("loading creates ...", flush=True)
    C = json.load(open(f"{L.TAB}/creates.json"))
    jobs = []
    for w in which:
        if w.startswith("D"):
            k = int(w[1:]); a = L.DAY0 + k * 86400; b = a + 86400
            jobs.append((w, a - 3600, b + 600))
        else:
            a, b = run_range(RUNS[w]); jobs.append((w, a - 3600, b + 600))
    for name, a, b in jobs:
        t0 = time.time()
        sa = int(ss[np.searchsorted(bt, a, side="left")]) if a > bt[0] else int(ss[0])
        jb = np.searchsorted(bt, b, side="right") - 1
        sb = int(ss[min(max(jb, 0), len(ss) - 1)])
        i0 = int(np.searchsorted(sl_all, sa, side="left")); i1 = int(np.searchsorted(sl_all, sb, side="right"))
        d = f"{OUT}/tab_{name}"; os.makedirs(d, exist_ok=True)
        sub = np.array(T[i0:i1])
        np.save(f"{d}/trades.npy", sub)
        Sm = S[(S["slot"] >= sa) & (S["slot"] <= sb)]
        np.save(f"{d}/slots.npy", Sm)
        if not os.path.exists(f"{d}/ids.json"): os.symlink(f"{L.TAB}/ids.json", f"{d}/ids.json")
        cr = {m: c for m, c in C.items() if sa <= c["slot"] <= sb}
        json.dump(cr, open(f"{d}/creates.json", "w"))
        print(f"{name}: {L.pkt(a)} -> {L.pkt(b)} slots {sa}..{sb} trades {len(sub):,} creates {len(cr):,} ({time.time() - t0:.0f} s)", flush=True)


if __name__ == "__main__":
    main(sys.argv[1].split(","))
