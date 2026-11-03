#!/usr/bin/env python3
"""PAPER AUDIT step 9: the follower effect on the try-level model's fills (pa7). The try-level exit walks the real tape as it was (every
later buy kept: "naive"); on windows we did not trade live, a follower whose min-out our buy breaks would have failed. Per model fill:
the same entry (our buy right before the fill position) and the same sell time (the model's sell landing on the real block clock) on the
CLEAN tape (our wallets removed), with and without the shadow's follower-drop model (presend.rs slack table) -> delta = slip - naive.
Check: the port's naive value vs the model's own gross (they walk the same trades; token vs SOL accounting).
usage: pa9_slip.py PT.pkl OUT.pkl"""
import sys, pickle, collections, statistics
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/obs/paper_audit")
import pa_lib as L


def main(pp, outp):
    R = pickle.load(open(pp, "rb"))
    tp = L.Tape()
    per, meta = R["per"], R["meta"]
    cache = {}
    adj = {}
    chk = []
    for key, v in per.items():
        w, sz, var = key
        mint = meta[w]["mint"]
        out = []
        for x in v:
            if not x["filled"] or x.get("fs") is None or x.get("c_sell") is None: out.append(None); continue
            if mint not in cache:
                t = tp.trades(mint)
                cache[mint] = None if t is None else L.build_recs(t, tp.ours, drop_ours=True)
            recs = cache[mint]
            if recs is None: out.append(None); continue
            mi = L.last_before(recs, (x["fs"], x["fi"], -1))
            if mi is None: out.append(None); continue
            vn = L.value_at(recs, mi, sz, False, x["c_sell"], tp.maxi, by_cc=True)
            vs = L.value_at(recs, mi, sz, True, x["c_sell"], tp.maxi, by_cc=True)
            if vn is None or vs is None: out.append(None); continue
            out.append({"naive": vn["gross"], "slip": vs["gross"], "delta": vs["gross"] - vn["gross"], "dropped": vs["dropped"], "followers": vs["followers"]})
            chk.append(vn["gross"] - x["gross"])
        adj[key] = out
    c = np.array(chk)
    print(f"port naive - model gross per fill: n {len(c)} median {1e3 * np.median(c):+.3f} mSOL, mean {1e3 * c.mean():+.3f}, |d| < 1 mSOL {np.mean(abs(c) < 1e-3) * 100:.1f}%")
    pickle.dump({"adj": adj, "check": {"n": len(c), "median_mSOL": 1e3 * float(np.median(c)), "mean_mSOL": 1e3 * float(c.mean()), "share_lt_1mSOL": float(np.mean(abs(c) < 1e-3))}}, open(outp, "wb"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
