#!/usr/bin/env python3
"""SIZE_48H step 0 (read-only): on the new tape (s48/tab), the live T2 detector (whale >= 6%) -> s48/trig_6.pkl, and the
10-minute bins of the 48 h window with their recording coverage -> s48/hours48.json.
Window: [START, END) PKT; a bin is used when >= 95% of its slots are recorded (as hours.py). Probe hours are NOT excluded
(this is "what would we have accumulated"), only flagged.
usage: s48prep.py [--start "10-24 00:20"] [--end "10-26 00:20"]"""
import sys, os, json, pickle, argparse, time, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s48lib
s48lib.use_tab48()
import rlib

PROBES = {"P1": ("10-25 08:38", "10-25 10:28"), "P2": ("10-25 15:20", "10-25 17:40"), "P3": ("10-25 22:20", "10-26 00:20")}
OLD_TEST_END = "10-25 18:00"      # REAL_REPLAY's test hours ended here (its tape's newest 40 min were excluded)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--start", default="10-24 00:20"); ap.add_argument("--end", default="10-26 00:20")
    ap.add_argument("--no-detect", action="store_true"); A = ap.parse_args()
    t0 = time.time()
    tp = s48lib.Tape48()
    S = np.load(f"{s48lib.TAB48}/slots.npy")
    slot = S["slot"].astype(np.int64); bt = S["bt"].astype(np.int64)
    ts, te = rlib.pk(A.start), rlib.pk(A.end)
    B = 600
    old_test = {x["t0"] for x in json.load(open(f"{s48lib.BASE}/hours.json"))["test"]}
    bins = []
    for b0 in range(ts, te, B):
        m = (bt >= b0) & (bt < b0 + B)
        n = int(m.sum()); cov = n / (600 / 0.2123)
        why = None if cov >= 0.95 else "coverage"
        probe = next((k for k, (a, e) in PROBES.items() if b0 + B > rlib.pk(a) and b0 < rlib.pk(e)), None)
        status = "old_test" if b0 in old_test else ("probe" if probe else ("new" if b0 >= rlib.pk(OLD_TEST_END) else "old_excluded"))
        bins.append(dict(t0=b0, t1=b0 + B, cov=round(cov, 3), why=why, probe=probe, status=status,
                         s_lo=int(slot[m].min()) if n else None, s_hi=int(slot[m].max()) if n else None))
    use = [x for x in bins if x["why"] is None]
    J = dict(start=ts, end=te, bins=bins, use=use, hours=len(use) / 6.0)
    json.dump(J, open(f"{s48lib.S48}/hours48.json", "w"))
    print("window", rlib.pkt(ts), "->", rlib.pkt(te), "PKT | bins", len(bins), "used", len(use), "hours %.2f" % (len(use) / 6.0),
          "| low coverage:", [(rlib.pkt(x["t0"]), x["cov"]) for x in bins if x["why"]])
    print("bin status (hours):", {k: round(v / 6.0, 2) for k, v in collections.Counter(x["status"] for x in use).items()})
    if not A.no_detect:
        trig = rlib.detect(tp, whale_pct=6.0)
        for d in trig: d.pop("mid", None)
        pickle.dump(trig, open(f"{s48lib.S48}/trig_6.pkl", "wb"))
        inwin = [d for d in trig if ts <= d["bt"] < te]
        print("T2 triggers (>= 6%%): %d, in the window %d, armable-type (age > 0, v2, not cashback) %d | %.0f s" % (
            len(trig), len(inwin), sum(1 for d in inwin if d["age_slots"] > 0 and d["v2"] and not d["cashback"]), time.time() - t0))
