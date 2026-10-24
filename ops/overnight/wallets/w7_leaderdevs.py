#!/usr/bin/env python3
# Is a create-time leader's selection just a DEV LIST? (read-only) For each leader: share of its devs' launches it bought,
# then a fair out-of-sample test: devs the leader(s) bought in run A -> ALL launches of those devs in run B, replayed at
# our place in line (phase-B replays: behind 1 / 2 outside trades, hold 3 / 5 / 10 s), net of our 3% fixed cost.
# usage: python3 -I w7_leaderdevs.py <w2 out dir> <phaseB R1> <phaseB R2> <launches R1> <launches R2>
import sys, os, json, gzip, glob, collections, statistics
OUTD, PB1, PB2, LF1, LF2 = sys.argv[1:6]
R = json.load(open(os.path.join(OUTD, "wallets_all.json"))); PP = json.load(gzip.open(os.path.join(OUTD, "pairs_cands.json.gz"), "rt"))
def signers(lf):
    s = {}
    for l in open(lf):
        try: c = json.loads(l)
        except Exception: continue
        s[c["mint"]] = c.get("user")
    return s
SG = {"R1": signers(LF1), "R2": signers(LF2)}
COLS = ["E_k1_h3s", "E_k1_h5s", "E_k1_h10s", "E_k2_h3s", "E_k2_h5s", "E_k2_h10s"]
PB = {}
for run, pb in (("R1", PB1), ("R2", PB2)):
    rows = {}
    for f in sorted(glob.glob(os.path.join(pb, "*.jsonl.gz"))):
        for l in gzip.open(f, "rt"):
            r = json.loads(l)
            if not r.get("quote_sol") or (r.get("max_vsol") or 0) > 200 or r.get("mayhem") or r.get("E_k1_h3s") is None: continue
            rows[r["mint"]] = dict(dev=SG[run].get(r["mint"]) or r.get("creator"), grad=(r.get("max_vsol") or 0) >= 114, **{c: r.get(c) for c in COLS})
    PB[run] = rows
devl = {run: collections.Counter(v["dev"] for v in PB[run].values()) for run in PB}
def st(rows, col, cost=0.03):
    v = [r[col] - cost for r in rows if r.get(col) is not None and not r["grad"]]
    if not v: return "n=0"
    return f"n={len(v)} mean={statistics.mean(v):+.3f} med={statistics.median(v):+.3f} win={sum(x > 0 for x in v)/len(v):.2f} sum@0.5={0.5*sum(v):+.2f}"
LEAD = ["6Kj5ChEZ", "3yrJE1A8", "FeCAXCyH", "5g8bviwg", "CWNAJ1ZT", "mwamTohZ", "AuTncroT", "A21wCG8H", "8jsPACii", "CBKgS8Nj", "E8s9tiRt", "dKMjeGJ4", "AHwJSnFN", "CWiNFAEk", "54YNHFVt"]
full = {w[:8]: w for w in R}
print("== how much of each dev's launches does the leader buy? (top devs)")
for l8 in LEAD:
    w = full[l8]; c = collections.Counter(); have = collections.Counter()
    for p in PP.get(w, []):
        d = SG[p[0]].get(p[7]); c[(p[0], d)] += 1
    tops = c.most_common(5)
    print(l8, [(run, (d or "?")[:6], n, devl[run].get(d, 0)) for (run, d), n in tops])
print("\n== OOS dev-list test: devs a leader bought in one run -> all launches of those devs in the other run (our place in line)")
for grp in (["6Kj5ChEZ"], ["3yrJE1A8"], ["FeCAXCyH"], ["5g8bviwg"], ["6Kj5ChEZ", "3yrJE1A8", "FeCAXCyH", "5g8bviwg", "CWNAJ1ZT", "mwamTohZ", "AuTncroT"], ["dKMjeGJ4"], ["AHwJSnFN"], ["CWiNFAEk"]):
    for a, b in (("R1", "R2"), ("R2", "R1")):
        devs = set()
        for l8 in grp:
            for p in PP.get(full[l8], []):
                if p[0] == a: devs.add(SG[a].get(p[7]))
        devs.discard(None)
        te = [r for r in PB[b].values() if r["dev"] in devs]
        print(f"{'+'.join(grp)[:40]:40s} {a}->{b} devs={len(devs)} | k1 h3s {st(te,'E_k1_h3s')} | k1 h10s {st(te,'E_k1_h10s')} | k2 h5s {st(te,'E_k2_h5s')}")
