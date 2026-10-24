#!/usr/bin/env python3
"""verify_dip / backrunners: who buys right after the >=1 SOL sells (the dip events)? For every event (claim filter), the buys
within 300 ms (proxy) after the sell: wallet, proxy delay, SOL. Ranks wallets that backrun dips repeatedly.
Also: for the claim's L=35 CV-selected trades, how much of the SOL bought between our entry and our exit comes from them.
usage: python3 -I -B backrunners.py"""
import sys, os, json, gzip, zlib, collections, statistics
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import vx_replay as R
def work(arg):
    (tag, b), keys = arg
    data = json.load(gzip.open(os.path.join(R.WORK, tag, f"b{b:03d}.json.gz"), "rt")); out = []
    want = collections.defaultdict(set)
    for m, a in keys: want[m].add(a)
    for m, ages in want.items():
        c = R.G["L"][m]; tr, _ = R.tape(data[m]["t"]); S = c["slot"]
        for k, t in enumerate(tr):
            if t["buy"] or t["syn"] or t["sol"] < R.MIN_SELL: continue
            age = round((t["s"] - S) * R.SMS / 1000, 2)
            if age not in ages: continue
            ages.discard(age)                     # the event = the first >= 1 SOL sell of that slot
            a0 = R.arr(t); fol = []
            for x in tr[k + 1:]:
                dly = R.arr(x) - a0
                if x["s"] > t["s"] + 5: break
                fol.append((x["user"], round(dly, 1), x["buy"], x["sol"], x["s"] - t["s"], x["sig"], x["payer"], x["tips"], x["cup"]))
            out.append((m, age, fol))
    return out
if __name__ == "__main__":
    ev = [json.loads(l) for l in gzip.open(os.path.join(HERE, "out", "vx_events_mine.jsonl.gz"), "rt")]
    ev = [r for r in ev if r["cf"]]
    R.init("mine")
    by = collections.defaultdict(list)
    for r in ev: by[(r["run"], zlib.crc32(r["m"].encode()) % 256)].append((r["m"], r["age"]))
    res = []
    with Pool(8, initializer=R.init, initargs=("mine",)) as p:
        for o in p.imap_unordered(work, sorted(by.items())): res += o
    cnt = collections.Counter(); dl = collections.defaultdict(list); sol = collections.defaultdict(float); tipped = collections.Counter()
    for m, age, fol in res:
        seen = set()
        for u, dly, isb, s, ds, sig, payer, tips, cup in fol:
            if isb and dly <= 150 and u not in seen:
                seen.add(u); cnt[u] += 1; dl[u].append(dly); sol[u] += s / 1e9; tipped[u] += 1 if tips else 0
    print(f"events {len(res)}; distinct wallets buying within 150 ms (proxy) after a dip: {len(cnt)}")
    top = cnt.most_common(25)
    for u, n in top:
        d = sorted(dl[u]); print(f"  {u} dips backrun {n:5d} ({n / len(res):.1%}) delay p10 {d[len(d) // 10]:6.1f} median {d[len(d) // 2]:6.1f} ms  avg buy {sol[u] / n:.3f} SOL  tipped {tipped[u] / n:.0%}")
    fast = [u for u, n in cnt.items() if n >= 50 and statistics.median(dl[u]) <= 100]
    json.dump(fast, open(os.path.join(HERE, "out", "fast_backrunners.json"), "w"))
    json.dump([u for u, _ in top[:1]], open(os.path.join(HERE, "out", "top1_backrunner.json"), "w"))
    json.dump({f"{m}|{age}": fol for m, age, fol in res}, open(os.path.join(HERE, "out", "followers_5slots.json"), "w"))
    print(f"fast repeat backrunners (>= 50 dips, median delay <= 100 ms): {len(fast)} wallets -> out/fast_backrunners.json")
