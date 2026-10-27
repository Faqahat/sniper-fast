#!/usr/bin/env python3
# r04: our MEASURED landing position for every live fire (fill or failed copy) on the replay's block-position clock
# (slot x 212 ms + idx / max(400, idx + 1) x 212 ms), vs the dump's position -> WORK/landing.json + distribution tables.
import sys, os, json, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib as R

def q(a, ps=(10, 25, 50, 75, 90)):
    a = np.asarray(a, float)
    return " / ".join(f"{np.percentile(a, p):.0f}" for p in ps) if len(a) else "-"

if __name__ == "__main__":
    F = json.load(open(f"{R.WORK}/fires.json")); rows = F["rows"]
    want = {r["dump_sig"] for r in rows}
    dumps = {}
    for srv, rn, base in R.RUN_FILES:
        for l in open(f"{R.LIVE}/{base}.jsonl"):
            if '"dump"' not in l[:400]: continue
            o = json.loads(l)
            if o.get("ev") == "dump" and o.get("sig") in want: dumps.setdefault(o["sig"], o)
    out = []
    for r in rows:
        d = dumps.get(r["dump_sig"])
        r["dump_idx_live"] = d["idx"] if d else r.get("dump_idx")
        r["dump_rec"] = {k: d.get(k) for k in ("age", "drop_pct", "sell", "score", "m2", "m2_pick", "pass", "dev", "vsol", "vtok", "t", "idx", "slot")} if d else None
        if r.get("land_slot") is None or r["dump_idx_live"] is None: continue
        a_d = R.arrival(r["dump_slot"], r["dump_idx_live"]); a_b = R.arrival(r["land_slot"], r["land_idx"])
        r["L_meas"] = a_b - a_d; r["slots_after"] = r["land_slot"] - r["dump_slot"]
        r["fill"] = r["live_result"] == "sold"
        out.append(r)
    json.dump(dict(rows=rows, runs=F["runs"], extra=F["extra"]), open(f"{R.WORK}/fires.json", "w"), default=str)
    print(f"fires with a measured landing: {len(out)} of {len(rows)}")
    print("L_meas (block-position ms after the dump), p10 / p25 / median / p75 / p90; share same block; share <= 35 / 50 / 75 ms")
    def line(nm, rr):
        L = [r["L_meas"] for r in rr]; same = np.mean([r["slots_after"] == 0 for r in rr]) if rr else 0
        return (f"  {nm:28s} n {len(rr):3d}  {q(L):24s} same-block {100 * same:3.0f}%  <=35 {100 * np.mean(np.array(L) <= 35):3.0f}%  "
                f"<=50 {100 * np.mean(np.array(L) <= 50):3.0f}%  <=75 {100 * np.mean(np.array(L) <= 75):3.0f}%" if rr else f"  {nm}: none")
    print(line("ALL", out))
    for k in ("srv", "fill"):
        for v in sorted({r[k] for r in out}, key=str): print(line(f"{k}={v}", [r for r in out if r[k] == v]))
    for v in sorted({(r["srv"], r["run"]) for r in out}): print(line(f"run {v}", [r for r in out if (r["srv"], r["run"]) == v]))
    cl = collections.defaultdict(list)
    for r in out: cl[(r["client"] or "?").replace("Agave", "").replace("Firedancer", "FD")].append(r)
    for k, v in sorted(cl.items(), key=lambda x: -len(x[1])): print(line(f"client {k}", v))
    # dump position inside its block
    for lo, hi in ((0, 100), (100, 200), (200, 300), (300, 400), (400, 10 ** 6)):
        print(line(f"dump idx {lo}-{hi}", [r for r in out if lo <= r["dump_idx_live"] < hi]))
