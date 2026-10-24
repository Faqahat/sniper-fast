#!/usr/bin/env python3
# F7 / quiet-bait mechanism check (read-only): for every Q event (a 0.9-3 SOL buy on a token quiet >= 20 slots, age >= 150
# slots, curve <= 45 SOL; s7_replay.py), who buys right after it and how fast? Bot-like followers (wallets with >= 100 trips
# in 48 h) reacting within a few slots = a mechanical reaction a newcomer could trigger too; slow fresh wallets = informed /
# coordinated buying (not reproducible). Also splits the replay P&L by the trigger buyer's type.
import sys, os, json, gzip, glob, zlib, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/strategies")
import s1_trips as S1
from multiprocessing import Pool
OUT = "/home/moiz/sniper-data/strategies"
F = json.load(open(f"{OUT}/trips/FIELDS.json")); X = {k: i for i, k in enumerate(F)}
def load():
    ev = []
    for f in sorted(glob.glob(f"{OUT}/replay/*.jsonl.gz")):
        for l in gzip.open(f, "rt"):
            if '"kind":"Q"' in l: ev.append(json.loads(l))
    return ev
NT = None
def init(nt):
    global NT; NT = nt
def work(key):
    run, b, items = key
    tra = S1.read(run, b, {m for m, _, _ in items}); out = []
    for m, s, i in items:
        tr = tra.get(m)
        if not tr: continue
        k = next((j for j, t in enumerate(tr) if t[0] == s and t[1] == i and t[10]), None)
        if k is None: continue
        U = tr[k][9]; fol = []
        for t in tr[k + 1:]:
            if t[0] - s > 20: break
            if t[9] == U: continue
            fol.append((t[0] - s, t[10], t[11] / 1e9, NT.get(t[9][:8], 0)))
        out.append(dict(m=m, s=s, n_buy5=sum(1 for d, bb, sol, n in fol if bb and d <= 5), sol_buy5=round(sum(sol for d, bb, sol, n in fol if bb and d <= 5), 3),
                        n_buy20=sum(1 for d, bb, sol, n in fol if bb), sol_buy20=round(sum(sol for d, bb, sol, n in fol if bb), 3),
                        bot_sol5=round(sum(sol for d, bb, sol, n in fol if bb and d <= 5 and n >= 100), 3),
                        first_buy_gap=next((d for d, bb, sol, n in fol if bb), None), buyer_trips=NT.get(U[:8], 0)))
    return out
if __name__ == "__main__":
    ev = load()
    nt = collections.Counter()
    for f in sorted(glob.glob(f"{OUT}/trips/*.jsonl.gz")):
        for l in gzip.open(f, "rt"): nt[l[2:10]] += 1
    nt = dict(nt)
    by = collections.defaultdict(list)
    for r in ev: by[(r["run"], zlib.crc32(r["m"].encode()) % 256)].append((r["m"], r["s"], r["i"]))
    res = []
    with Pool(9, initializer=init, initargs=(nt,)) as p:
        for o in p.imap_unordered(work, [(run, b, it) for (run, b), it in by.items()]): res += o
    F_ = {(o["m"], o["s"]): o for o in res}
    rows = []
    for r in ev:
        o = F_.get((r["m"], r["s"]))
        if o: rows.append({**r, **o})
    print("Q events with tape", len(rows))
    def show(title, rs):
        if not rs: return
        v = sum(r["B"] for r in rs)
        print(f"  {title:<44} n {len(rs):5d}  P&L t20 {sum(r['pnl']['t20'] for r in rs):+7.1f}  t100 {sum(r['pnl']['t100'] for r in rs):+7.1f} ({sum(r['pnl']['t100'] for r in rs) / v:+.3f}/SOL)"
              f"  buys<=5 slots med {statistics.median(r['n_buy5'] for r in rs)}, SOL {statistics.median(r['sol_buy5'] for r in rs):.2f}, bot share {sum(r['bot_sol5'] for r in rs) / max(1e-9, sum(r['sol_buy5'] for r in rs)):.0%}")
    for run in ("R2", "R3"):
        rs = [r for r in rows if r["run"] == run]
        print(f"\n{run}:")
        show("all", rs)
        show("buyer = bot-like (>=100 trips)", [r for r in rs if r["buyer_trips"] >= 100])
        show("buyer 10-99 trips", [r for r in rs if 10 <= r["buyer_trips"] < 100])
        show("buyer <10 trips (fresh / human / one-off)", [r for r in rs if r["buyer_trips"] < 10])
        show("followers: >=1 buy within 5 slots", [r for r in rs if r["n_buy5"] >= 1])
        show("followers: none within 5 slots", [r for r in rs if r["n_buy5"] == 0])
        show("first follower buy in same slot / next slot", [r for r in rs if r["first_buy_gap"] is not None and r["first_buy_gap"] <= 1])
        show("first follower buy 2-20 slots", [r for r in rs if r["first_buy_gap"] is not None and r["first_buy_gap"] > 1])
        show("no follower buy within 20 slots", [r for r in rs if r["first_buy_gap"] is None])
    json.dump(rows, open(f"{OUT}/q_events.json", "w"))
