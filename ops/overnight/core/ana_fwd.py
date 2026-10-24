#!/usr/bin/env python3
# analysis of the forward replay: selection x landing config x exit rule -> PnL (total, per trade, win, without top-2, halves)
import sys, json, gzip, collections, statistics, datetime
F = sys.argv[1] if len(sys.argv) > 1 else "fwd.jsonl.gz"
rows = []
with gzip.open(F, "rt") as f:
    meta = json.loads(f.readline()); NAMES = meta["rules"]
    for l in f: rows.append(json.loads(l))
rows.sort(key=lambda r: r["bt"] or 0)
t0, t1 = rows[0]["bt"], rows[-1]["bt"]; mid = t0 + (t1 - t0) / 2
print(f"launches {len(rows)}; window {datetime.datetime.utcfromtimestamp(t0):%m-%d %H:%M} -> {datetime.datetime.utcfromtimestamp(t1):%m-%d %H:%M} UTC; halves split at {datetime.datetime.utcfromtimestamp(mid):%H:%M}")
def stats(v):
    if not v: return None
    s = sorted(v)
    return dict(n=len(v), tot=sum(v), mean=statistics.mean(v), med=statistics.median(v), win=sum(1 for x in v if x > 0) / len(v), tot_x2=sum(s[:-2]) if len(s) > 2 else 0)
def table(sel_name, sel, cfgs=("L75",), top=8, min_n=10):
    R = [r for r in rows if sel(r)]
    print(f"\n== {sel_name}: {len(R)} launches")
    for cf in cfgs:
        res = []
        for i, n in enumerate(NAMES):
            v = [r["cfg"][cf]["pnl"][i] for r in R if cf in r["cfg"]]
            if len(v) < min_n: continue
            h1 = [r["cfg"][cf]["pnl"][i] for r in R if cf in r["cfg"] and r["bt"] < mid]; h2 = [r["cfg"][cf]["pnl"][i] for r in R if cf in r["cfg"] and r["bt"] >= mid]
            st = stats(v); res.append((st["tot"], n, st, sum(h1), sum(h2)))
        res.sort(reverse=True)
        for tot, n, st, a, b in res[:top]:
            print(f"   [{cf}] {n:32} n {st['n']:5} total {tot:+8.3f} SOL  mean {st['mean']:+.4f} med {st['med']:+.4f} win {st['win']:.0%}  w/o top2 {st['tot_x2']:+.3f}  halves {a:+.3f} / {b:+.3f}")
    return R
if __name__ == "__main__":
    table("ALL launches (no selection)", lambda r: True, cfgs=("L75", "L0"), top=5)
    table("dev buy >= 1 SOL and glued bundle >= 2 txs", lambda r: r["dev_buy"] >= 1 and r["glued_n"] >= 2, cfgs=("L75", "L0"), top=5)
    for w in ("9Sh2fd", "DGmspi", "D24ipY"):
        table(f"launches {w} ATTEMPTED (oracle copy of its picks)", lambda r, w=w: w in r["att"], cfgs=("L75", "L60", "L35", "L0"), top=5)
