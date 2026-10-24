#!/usr/bin/env python3
# OOS check of the pattern shared by the profitable like-us wallets (read-only): "snipe launches of SERIAL deployers
# (watchlist), buy at our place in line, sell after a few seconds". Uses the phase-B per-launch replays (exact curve
# math, pump fees per side; a 0.494 SOL buy behind the first k OUTSIDE trades after the creator's glued bundle).
# Watchlists are built ONLY from run 1 (R1) and tested on run 2 (R2) launches, plus the reverse direction.
# usage: python3 -I w4_devlist.py <phaseB R1> <phaseB R2> <run1 launches> <run2 launches> <wallets_all.json>
import sys, os, json, gzip, glob, collections, statistics
PB1, PB2, L1, L2, WJ = sys.argv[1:6]
COST = {"cost3%": 0.03, "cost1%": 0.01}          # fixed cost per round trip as a share of size (ours ~0.015 SOL / 0.5 SOL = 3%)
COLS = ["E_k1_h3s", "E_k2_h3s", "E_k3_h3s", "E_k2_h5s", "E_k2_h2s", "E_k2_h10s", "E_k2_fsell_30s_eos", "E_slot_h3s", "E_bundle_h3s"]
def signers(lf):
    s = {}
    for l in open(lf):
        try: c = json.loads(l)
        except Exception: continue
        s[c["mint"]] = c.get("user")
    return s
def load(pb, lf):
    sg = signers(lf); rows = []
    for f in sorted(glob.glob(os.path.join(pb, "*.jsonl.gz"))):
        for l in gzip.open(f, "rt"):
            r = json.loads(l)
            if not r.get("quote_sol") or (r.get("max_vsol") or 0) > 200 or r.get("mayhem") or r.get("E_k2_h3s") is None: continue
            if (r.get("max_vsol") or 0) >= 114: continue      # graduated: AMM price unknown, replay invalid after it
            rows.append(dict(m=r["mint"], dev=sg.get(r["mint"]) or r.get("creator"), dev_buy=r.get("dev_buy") or 0, glued=r.get("glued_n") or 0,
                             **{c: r.get(c) for c in COLS}))
    return rows
R1 = load(PB1, L1); R2 = load(PB2, L2)
print("SOL non-mayhem non-graduated launches with replays: R1", len(R1), "R2", len(R2))
W = json.load(open(WJ))
likeus = [w for w, s in W.items() if s.get("pass") and s.get("like_us")]
def stats(rows, col, cost):
    v = [r[col] - cost for r in rows if r.get(col) is not None]
    if not v: return "n=0"
    return f"n={len(v)} mean={statistics.mean(v):+.4f} med={statistics.median(v):+.4f} win={sum(x > 0 for x in v) / len(v):.2f} sum@0.5SOL={0.5 * sum(v):+.2f}"
def cnt(rows): return collections.Counter(r["dev"] for r in rows)
for train, test, nm in ((R1, R2, "train R1 -> test R2"), (R2, R1, "train R2 -> test R1")):
    c_tr = cnt(train); c_te = cnt(test)
    print(f"\n===== {nm}")
    # serial devs by count in the TRAIN run
    for k in (3, 10):
        ser = {d for d, n in c_tr.items() if n >= k}
        te = [r for r in test if r["dev"] in ser]
        print(f"devs with >= {k} launches in train ({len(ser)} devs): test launches {len(te)}")
        for col in ("E_k1_h3s", "E_k2_h3s", "E_k3_h3s", "E_k2_h5s", "E_k2_fsell_30s_eos"):
            print(f"   {col:20s} {stats(te, col, COST['cost3%'])} | at 1% cost {stats(te, col, COST['cost1%'])}")
    # devs whose train launches were positive at E_k2_h3s (>= 3 launches)
    by = collections.defaultdict(list)
    for r in train: by[r["dev"]].append(r)
    good = {d for d, rs in by.items() if len(rs) >= 3 and statistics.mean(x["E_k2_h3s"] for x in rs) - 0.03 > 0}
    te = [r for r in test if r["dev"] in good]
    print(f"devs positive at E_k2_h3s in train (>=3 launches, {len(good)} devs): test launches {len(te)}")
    for col in ("E_k1_h3s", "E_k2_h3s", "E_k3_h3s", "E_k2_h5s", "E_k2_fsell_30s_eos"):
        print(f"   {col:20s} {stats(te, col, COST['cost3%'])} | at 1% cost {stats(te, col, COST['cost1%'])}")
    # big dev buy + bundle (rule-like, no dev identity)
    te = [r for r in test if r["dev_buy"] >= 2.5 and r["glued"] >= 1]
    print(f"rule dev_buy>=2.5 & glued bundle (no identity): test launches {len(te)}")
    for col in ("E_k1_h3s", "E_k2_h3s", "E_k3_h3s"):
        print(f"   {col:20s} {stats(te, col, COST['cost3%'])}")
    te = [r for r in test if r["dev_buy"] >= 2.5 and r["glued"] >= 1 and c_te[r["dev"]] >= 10]
    print(f"rule dev_buy>=2.5 & bundle & dev has >=10 launches in the SAME run (not known in advance): {len(te)}")
    for col in ("E_k1_h3s", "E_k2_h3s", "E_k3_h3s"):
        print(f"   {col:20s} {stats(te, col, COST['cost3%'])}")
    print("baseline all launches:")
    for col in ("E_k1_h3s", "E_k2_h3s", "E_k3_h3s"):
        print(f"   {col:20s} {stats(test, col, COST['cost3%'])}")
