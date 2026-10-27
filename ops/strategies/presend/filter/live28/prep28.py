#!/usr/bin/env python3
"""LIVE28 step 0 (read-only): run 28's live tries as landing donors (lib28.build_donors, as real/p3donors.py) -> DATA/donors28.pkl,
plus the recording-coverage check: every slot the engine's records reference (try landings, fills, sells, trigger slots, dumps)
must have a block on the tape; slots in the run span with no block are listed (leader-skipped or recording holes)."""
import sys, os, pickle, json, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib28 as L

if __name__ == "__main__":
    R = L.load_run(); ours = L.load_ours(); L.chain_fees(R, ours)
    tp = L.Tape28(R)
    D = L.build_donors(tp, R, ours)
    pickle.dump(D, open(f"{L.DATA}/donors28.pkl", "wb"))
    print("donors", len(D["R28"]["wins"]), "tries", sum(len(w["tries"]) for w in D["R28"]["wins"]),
          "res", dict(collections.Counter(t["res"] for w in D["R28"]["wins"] for t in w["tries"])))
    # coverage
    refs = collections.Counter()
    for x in R["W"].values():
        refs[x["arm"]["trig"]["slot"]] += 1
        for a in x["atts"]:
            l = a["land"] or {}
            if l.get("slot"): refs[l["slot"]] += 1
        for k in ("fill", "sell"):
            if x[k] and x[k].get("slot"): refs[x[k]["slot"]] += 1
    for s in R["skips"]:
        refs[s["trig"]["slot"]] += 1
    for d in R["dumps"]:
        if d.get("slot"): refs[d["slot"]] += 1
    lo = min(refs); hi = max(refs)
    empty = [s for s in range(lo, hi + 1) if tp.nblk(s) == 0]
    miss = sorted(s for s in refs if tp.nblk(s) == 0)
    print(f"run slot span {lo}..{hi} ({hi - lo + 1} slots): {len(empty)} without a block; {sum(refs.values())} slot references, "
          f"{len(miss)} referenced slots without a block: {miss[:40]}")
    S = np.load(f"{L.TAB}/slots.npy"); bt = S["bt"] if "bt" in S.dtype.names else None
    print("tape slots", int(S["slot"].min()), int(S["slot"].max()), "block time PKT", L.hm(int(bt.min()) * 10**9) if bt is not None else "", L.hm(int(bt.max()) * 10**9) if bt is not None else "")
    # per 5-min bin coverage
    if bt is not None:
        sl = S["slot"].astype(np.int64); m = (sl >= lo) & (sl <= hi)
        ts = bt[m].astype(np.int64); bins = collections.Counter((t - 1793107200) // 300 for t in ts)
        exp = (hi - lo + 1) / max(len(bins), 1)
        worst = sorted(bins.items(), key=lambda kv: kv[1])[:5]
        print("5-min bins", len(bins), "fewest blocks:", [(L.hm((1793107200 + b * 300) * 10**9, "%H:%M"), n) for b, n in worst])
    json.dump(dict(span=[lo, hi], empty=len(empty), missing=miss), open(f"{L.DATA}/coverage.json", "w"))
