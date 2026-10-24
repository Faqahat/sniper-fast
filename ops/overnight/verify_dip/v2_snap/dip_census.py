#!/usr/bin/env python3
# Census of dip backrunners: for every dip trigger (>=1 SOL sell, launch aged 1-120 s, from the dip event file), every wallet
# that bought in the same slot within 150 ms after it (block-position proxy) -> that wallet's round trip on the mint (its buy,
# then its next sell(s) until the tokens bought are sold or 600 slots pass). Per wallet: trades, P&L (SOL out - SOL in, from the
# TradeEvents: buys net into the curve, sells gross out, so pump fees are approximated by -1.25% on each side), hold, delay.
# Local data only.  usage: python3 -I dip_census.py ev_file.jsonl.gz out.json
import sys, os, json, gzip, collections, statistics
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry"); os.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/dip")
import dipbuy4 as D
from multiprocessing import Pool
EVF, OUT = sys.argv[1], sys.argv[2]
bym = collections.defaultdict(set)
for l in gzip.open(EVF, "rt"):
    r = json.loads(l); bym[r["m"]].add(r["age"])
byb = collections.defaultdict(set)
for m in bym: byb[(D.L[m]["run"], D.rp.bucket(m))].add(m)
FEE = 0.0125
def work(key):
    run, b = key; out = []
    for m, tr in D.rp.read_bucket(run, b, byb[key]).items():
        S0 = D.L[m]["slot"]
        for k, t in enumerate(tr):
            if t["buy"] or t["sol"] < D.MIN_SELL or round((t["s"] - S0) * D.SMS / 1000, 2) not in bym[m]: continue
            a0 = D.arr(t); seen = set()
            for j in range(k + 1, min(k + 40, len(tr))):
                x = tr[j]
                if x["s"] > t["s"]: break
                dt = D.arr(x) - a0
                if dt > 150: break
                if not x["buy"] or x["user"] in seen or x["user"] == t["user"]: continue
                seen.add(x["user"])
                # its round trip: sell the tokens of this buy (FIFO approximation: its next sells until the amount is covered)
                need = x["tok"]; got = 0.0; last = None
                for y in tr[j + 1:]:
                    if y["s"] - x["s"] > 600: break
                    if y["user"] != x["user"]: continue
                    if y["buy"]: continue
                    take = min(need, y["tok"]); got += y["sol"] * take / y["tok"]; need -= take; last = y
                    if need <= 0: break
                if last is None: continue
                cost = x["sol"] * (1 + FEE) / 1e9; back = got * (1 - FEE) / 1e9
                out.append(dict(u=x["user"], m=m, dt=round(dt, 1), cost=round(cost, 4), back=round(back, 4), hold=last["s"] - x["s"], full=need <= 0,
                                pos=round(x["i"] / max(D.SS.get(x["s"], 400), x["i"] + 1), 3), trig_sol=round(t["sol"] / 1e9, 3)))
    return out
if __name__ == "__main__":
    R = []
    with Pool(int(os.environ.get("NPROC", "6"))) as p:
        for o in p.imap_unordered(work, sorted(byb), chunksize=2): R += o
    json.dump(R, open(OUT, "w"))
    W = collections.defaultdict(list)
    for r in R: W[r["u"]].append(r)
    print("round trips", len(R), "wallets", len(W))
    rows = []
    for u, v in W.items():
        if len(v) < 30: continue
        pnl = sum(r["back"] - r["cost"] for r in v); rows.append((pnl, u, v))
    rows.sort(reverse=True)
    print("top dip backrunners by P&L (>=30 round trips): wallet, trades, P&L SOL, mean per trade, mean size, median hold slots, median delay ms, win")
    for pnl, u, v in rows[:25]:
        print(f"  {u[:10]} n {len(v):5d} pnl {pnl:+8.2f} mean {pnl / len(v):+.4f} size {statistics.mean(r['cost'] for r in v):.2f} hold {statistics.median(r['hold'] for r in v):4.0f} "
              f"delay {statistics.median(r['dt'] for r in v):5.1f} win {sum(1 for r in v if r['back'] > r['cost']) / len(v):.0%}")
    tot = sum(p for p, _, _ in rows); pos = sum(p for p, _, _ in rows if p > 0)
    print(f"wallets with >=30: {len(rows)}, total P&L {tot:+.1f}, positive wallets {sum(1 for p, _, _ in rows if p > 0)} (their P&L {pos:+.1f})")
