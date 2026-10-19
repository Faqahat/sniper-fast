#!/usr/bin/env python3
# READ-ONLY: validate the engine's in-slot create time (CREATE-POH lines: the leader's PoH clock from the shred walk /
# entries feed) against on-chain truth: the create's position among the block's non-vote txs x slot length
# (truth_ms = (idx + 0.5) / n_nonvote * slot_ms). usage: pohval.py <engine log> [max_creates=220]
import sys, re, json, os, statistics, random
sys.path.insert(0, "/root/indep")
from common import get_block, is_vote
LOG = sys.argv[1]
N = int(sys.argv[2]) if len(sys.argv) > 2 else 220
CACHE = "/root/fix2/blkcache"; os.makedirs(CACHE, exist_ok=True)
slot_ms = 203.5
rows = []
for l in open(LOG, errors="replace"):
    m = re.search(r"POH CLOCK: \d+ slots in \d+ s -> ([\d.]+) ms a slot", l)
    if m:
        slot_ms = float(m.group(1))
    m = re.search(r"CREATE-POH slot=(\d+) mint=(\w+) sig=(\w+) poh_ms=([\d.\-]+) src=([\w-]+) arrival_poh_ms=([\d.\-]+)", l)
    if m:
        rows.append(dict(slot=int(m.group(1)), mint=m.group(2), sig=m.group(3), poh=None if m.group(4) == "-" else float(m.group(4)),
                         src=m.group(5), arr=None if m.group(6) == "-" else float(m.group(6))))
print(f"CREATE-POH lines: {len(rows)}; with a PoH position: {sum(1 for r in rows if r['poh'] is not None)} "
      f"(poh-index {sum(1 for r in rows if r['src']=='poh-index')}, arrival {sum(1 for r in rows if r['src']=='arrival')}, none {sum(1 for r in rows if r['src']=='none')}); slot_ms {slot_ms}")
random.seed(7)
sample = rows if len(rows) <= N else random.sample(rows, N)


def blk(s):
    p = f"{CACHE}/{s}.json"
    if os.path.exists(p):
        return json.load(open(p))
    b = get_block(s)
    if isinstance(b, dict) and "transactions" in b:
        # keep only what we need: per tx (first sig, vote?)
        small = {"txs": [[t["transaction"]["signatures"][0], bool(is_vote(t))] for t in b["transactions"]]}
        json.dump(small, open(p, "w"))
        return small
    return None


out = []
for r in sample:
    b = blk(r["slot"])
    if not b:
        continue
    nv = [s for s, v in b["txs"] if not v]
    idx = next((i for i, s in enumerate(nv) if s.startswith(r["sig"])), None)
    if idx is None:
        r["truth"] = None
        out.append(r)
        continue
    r["idx"], r["nnv"] = idx, len(nv)
    r["truth"] = (idx + 0.5) / len(nv) * slot_ms
    out.append(r)
val = [r for r in out if r.get("truth") is not None and r["poh"] is not None]
print(f"checked on chain: {len(out)} creates; found in their block {sum(1 for r in out if r.get('truth') is not None)}; with PoH + truth: {len(val)}")
json.dump(out, open("/root/fix2/pohval_rows.json", "w"))


def q(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, max(0, int(round(p * (len(v) - 1)))))]


if val:
    e = [r["poh"] - r["truth"] for r in val]
    ae = [abs(x) for x in e]
    print(f"error engine - chain (ms): median {statistics.median(e):+.1f}, mean {statistics.mean(e):+.1f}; |error| p50 {q(ae,.5):.1f} p75 {q(ae,.75):.1f} p90 {q(ae,.9):.1f} p95 {q(ae,.95):.1f} max {max(ae):.1f}")
    for src in ("poh-index", "arrival"):
        v = [abs(r["poh"] - r["truth"]) for r in val if r["src"] == src]
        if v:
            print(f"  src={src}: n={len(v)} |error| p50 {q(v,.5):.1f} p90 {q(v,.9):.1f}")
    if len(val) > 3:
        x = [r["truth"] for r in val]; y = [r["poh"] for r in val]
        mx, my = statistics.mean(x), statistics.mean(y)
        cov = sum((a - mx) * (b - my) for a, b in zip(x, y)); vx = sum((a - mx) ** 2 for a in x); vy = sum((b - my) ** 2 for b in y)
        print(f"  correlation {cov / (vx * vy) ** 0.5:.3f}; fit poh = {cov/vx:.3f} x truth {my - cov/vx*mx:+.1f}")
    for X in (130, 150, 170):
        tp = sum(1 for r in val if r["poh"] > X and r["truth"] > X)
        fp = sum(1 for r in val if r["poh"] > X and r["truth"] <= X)
        fn = sum(1 for r in val if r["poh"] <= X and r["truth"] > X)
        tn = sum(1 for r in val if r["poh"] <= X and r["truth"] <= X)
        print(f"  gate X={X}: skip&late {tp}, skip&early(wrong skip) {fp}, keep&late(missed) {fn}, keep&early {tn}; agreement {(tp+tn)/len(val):.1%}")
    by = {}
    for r in val:
        k = min(int(r["truth"] // 50) * 50, 200)
        by.setdefault(k, []).append(r["poh"] - r["truth"])
    print("  by chain position: " + ", ".join(f"{k}-{k+50}ms n={len(v)} med err {statistics.median(v):+.1f}" for k, v in sorted(by.items())))
