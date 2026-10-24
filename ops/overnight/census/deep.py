#!/usr/bin/env python3
# Deep look at chosen census wallets: realized vs marked PnL, PnL by entry delay / hold / size, completed curves, per-run.
import json, gzip, glob, collections, statistics, sys
WANT = sys.argv[1].split(",")
A = collections.defaultdict(list)
for f in glob.glob("/home/moiz/sniper/ops/overnight/census/parts/*.jsonl.gz"):
    for l in gzip.open(f, "rt"):
        r = json.loads(l)
        for w in WANT:
            if r[0].startswith(w): A[r[0]].append(r); break
# r: [u, m, run, bt, fb_s, fb_k, fb_sol, spent, got, mark, cost, pnl, nb, ns, ls_s, done, open]
for u, v in sorted(A.items(), key=lambda kv: -sum(r[11] for r in kv[1])):
    spent = sum(r[7] for r in v); got = sum(r[8] for r in v); mark = sum(r[9] for r in v); cost = sum(r[10] for r in v); pnl = sum(r[11] for r in v)
    realized = sum(r[11] for r in v if not r[16]); marked_rows = [r for r in v if r[16]]
    done = [r for r in v if r[15]]
    print(f"\n{u}  n={len(v)} spent {spent:.1f} got {got:.1f} mark {mark:.1f} txcost {cost:.2f} pnl {pnl:+.2f} | closed-only pnl {realized:+.2f} | open {len(marked_rows)} (pnl {sum(r[11] for r in marked_rows):+.2f}) | curve-completed {len(done)} (pnl {sum(r[11] for r in done):+.2f})")
    for run in ("R1", "R2"):
        x = [r for r in v if r[2] == run]
        if x: print(f"   {run}: n {len(x)} pnl {sum(r[11] for r in x):+.2f}")
    def band(title, key, edges):
        out = []
        for lo, hi in zip(edges[:-1], edges[1:]):
            x = [r for r in v if key(r) is not None and lo <= key(r) < hi]
            if x: out.append(f"[{lo},{hi}) n{len(x)} {sum(r[11] for r in x):+.1f} win{sum(1 for r in x if r[11] > 0) / len(x):.0%}")
        print(f"   {title}: " + " | ".join(out))
    band("entry slots", lambda r: r[4], [0, 1, 3, 6, 15, 30, 60, 150, 300, 900, 10 ** 7])
    band("hold slots", lambda r: (r[14] - r[4]) if r[14] is not None else None, [0, 3, 10, 25, 50, 100, 250, 500, 1500, 10 ** 7])
    band("spent SOL", lambda r: r[7], [0, 0.1, 0.3, 0.6, 1, 2, 5, 100])
    R = sorted(r[11] for r in v); n = len(R)
    print(f"   pnl distribution: p10 {R[n // 10]:+.3f} p50 {R[n // 2]:+.3f} p90 {R[9 * n // 10]:+.3f} max {R[-1]:+.2f} | top10 sum {sum(R[-10:]):+.2f} | bottom10 {sum(R[:10]):+.2f}")
    print("   biggest:", [(r[1][:8], r[2], r[4], round(r[7], 2), round(r[11], 2), "open" if r[16] else "", "done" if r[15] else "") for r in sorted(v, key=lambda r: -r[11])[:6]])
