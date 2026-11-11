#!/usr/bin/env python3
"""dipmon v5: export the chain tape probe_check.py prices dip46 probes on, for `dipmon --probe-tape FILE` (offline; reads a run's
dip log and the collector's tape through harness/hlib, read-only; writes FILE only).

The same window and mints as ops/probe46/probe_check.py: every landed presend_live_probe_land, t0 = first - 60 s, t1 = last + 600 s,
the tape's trades of those mints. Lines: {"s", "i", "mint", "vtok"} (vtok > 0) and {"s", "maxi"} (the block clock's largest idx per
slot, over those mints' trades, as probe_check.py's Tape).

usage: probe_tape.py DIP_LOG.jsonl OUT.jsonl"""
import sys, json
HARN = "/home/it/sniper-studies/sniper-plan1110/harness"


def main():
    if len(sys.argv) != 3:
        print(__doc__); sys.exit(1)
    lands = []
    with open(sys.argv[1]) as f:
        for line in f:
            if '"presend_live_probe_land"' not in line:
                continue
            r = json.loads(line)
            if r.get("ev") == "presend_live_probe_land" and r["res"] != "unseen" and r.get("idx") is not None:
                lands.append(r)
    if not lands:
        print("no landed probe"); sys.exit(1)
    ts = [l["t"] / 1e9 for l in lands if l.get("t")]
    mints = {l["mint"] for l in lands}
    sys.path.insert(0, HARN)
    import hlib                                           # noqa: E402
    df = hlib.tape_df(min(ts) - 60, max(ts) + 600)
    df = df[df["mint"].isin(mints)]
    maxi = {}
    n = 0
    with open(sys.argv[2], "w") as out:
        for s, i, mint, vtok in zip(df["s"].values, df["i"].values, df["mint"].values, df["vtok"].values):
            if vtok > 0:
                out.write(json.dumps({"s": int(s), "i": int(i), "mint": mint, "vtok": float(vtok)}) + "\n")
                n += 1
            maxi[int(s)] = max(maxi.get(int(s), 0), int(i))
        for s in sorted(maxi):
            out.write(json.dumps({"s": s, "maxi": maxi[s]}) + "\n")
    print(f"{n} trades of {len(mints)} mints, {len(maxi)} slots -> {sys.argv[2]}")


if __name__ == "__main__":
    main()
