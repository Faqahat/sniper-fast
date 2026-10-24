#!/usr/bin/env python3
"""verify_dip / bk_tolerance: how much price move do the fast dip-backrunners accept? For every dip event (claim filter), every
tx by the top backrunner wallets (fee payer) in the sell's slot .. +3 slots: successful buys and FAILED txs. The price just
before that tx's block position (after every successful trade before it) relative to the price right after the dip sell.
If failures sit at higher ratios than successes, the wallet uses a tight limit vs the dip price: our 0.5 SOL buy ahead of it
(+1-2.5% on the price) would make it fail, and its buy would not lift our exit.
usage: python3 -I -B bk_tolerance.py"""
import sys, os, json, gzip, zlib, collections
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import vx_replay as R
TOP = None
def init2():
    global TOP
    R.init("mine"); TOP = set(json.load(open(os.path.join(HERE, "out", "fast_backrunners.json"))))
def work(arg):
    (tag, b), keys = arg
    data = json.load(gzip.open(os.path.join(R.WORK, tag, f"b{b:03d}.json.gz"), "rt")); out = []
    want = collections.defaultdict(set)
    for m, a in keys: want[m].add(a)
    for m, ages in want.items():
        c = R.G["L"][m]; tr, _ = R.tape(data[m]["t"]); S = c["slot"]; fl = data[m]["f"]
        for k, t in enumerate(tr):
            if t["buy"] or t["syn"] or t["sol"] < R.MIN_SELL: continue
            age = round((t["s"] - S) * R.SMS / 1000, 2)
            if age not in ages: continue
            ages.discard(age)
            p0 = t["vsol"] / t["vtok"]; s0 = t["s"]
            units = []           # (s, i, kind, payer, buy_sol)
            for x in tr[k + 1:]:
                if x["s"] > s0 + 3: break
                if x["syn"]: continue
                units.append((x["s"], x["i"], "ok", x["payer"], x["sol"] if x["buy"] else -x["sol"], x))
            for f in fl:
                if s0 <= f[0] <= s0 + 3 and (f[0], f[1]) > (t["s"], t["i"]):
                    units.append((f[0], f[1], "fail", f[2], 0, None))
            units.sort(key=lambda u: (u[0], u[1]))
            V, T = t["vsol"], t["vtok"]; nb_before = 0; seen_pay = set()
            for s, i, kind, payer, bs, x in units:
                ratio = (V / T) / p0
                if payer in TOP and (payer, kind) not in seen_pay:
                    seen_pay.add((payer, kind))
                    out.append((payer, kind, round(ratio, 5), nb_before, round(R.arr(dict(s=s, i=i)) - R.arr(t), 1), m, age))
                if kind == "ok":
                    V, T = x["vsol"], x["vtok"]
                    if x["buy"]: nb_before += 1
    return out
if __name__ == "__main__":
    ev = [json.loads(l) for l in gzip.open(os.path.join(HERE, "out", "vx_events_mine.jsonl.gz"), "rt")]
    ev = [r for r in ev if r["cf"]]
    R.init("mine")
    by = collections.defaultdict(list)
    for r in ev: by[(r["run"], zlib.crc32(r["m"].encode()) % 256)].append((r["m"], r["age"]))
    res = []
    with Pool(8, initializer=init2) as p:
        for o in p.imap_unordered(work, sorted(by.items())): res += o
    json.dump(res, open(os.path.join(HERE, "out", "bk_tolerance.json"), "w"))
    bins = [(0, 1.002), (1.002, 1.01), (1.01, 1.02), (1.02, 1.03), (1.03, 1.05), (1.05, 1.1), (1.1, 99)]
    def tab(rows, label):
        cells = []
        for lo, hi in bins:
            v = [r for r in rows if lo <= r[2] < hi]
            ok = sum(1 for r in v if r[1] == "ok"); fl = sum(1 for r in v if r[1] == "fail")
            cells.append(f"[{lo:.3f},{hi if hi < 9 else 'inf'}): ok {ok:5d} fail {fl:5d} ({fl / max(1, ok + fl):.0%} fail)")
        print(f"{label}\n   " + "\n   ".join(cells))
    tab(res, f"ALL {len(set(r[0] for r in res))} fast backrunners, price before their tx / price right after the dip:")
    cnt = collections.Counter(r[0] for r in res)
    for u, n in cnt.most_common(8):
        tab([r for r in res if r[0] == u], f"{u[:10]} ({n} txs)")
    oks = sorted(r[2] for r in res if r[1] == "ok"); n = len(oks)
    print(f"successful backrunner buys: price ratio p50 {oks[n // 2]:.4f} p90 {oks[9 * n // 10]:.4f} p99 {oks[99 * n // 100]:.4f}")
