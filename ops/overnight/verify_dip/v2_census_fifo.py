#!/usr/bin/env python3
# Claim 5, proper accounting: the census's trips (same matching: every same-slot buy <= 150 ms (proxy) after a dip trigger of the
# event file) priced with a real per-wallet FIFO over ALL of the wallet's trades on that mint (earlier holdings and other buys
# included, so one sell can never be counted twice), sells within 600 slots of the lot's buy; whatever is left after 600 slots
# (or at the end of the tape) is marked to market at the curve state then (constant product, minus 1.25%). Pump fees as the
# census (+-1.25%); tx costs from the collector rows (fee + tips) of the buy and, pro rata, of the sells.
# Local files only. usage: python3 -I v2_census_fifo.py ev_file.jsonl.gz out.jsonl.gz
import sys, os, json, gzip, collections, bisect
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "v2_mods"))
import dipbuy4_s as D
from multiprocessing import Pool
EVF, OUT = sys.argv[1], sys.argv[2]
bym = collections.defaultdict(set)
for l in gzip.open(EVF, "rt"):
    r = json.loads(l); bym[r["m"]].add(r["age"])
byb = collections.defaultdict(set)
for m in bym: byb[(D.L[m]["run"], D.rp.bucket(m))].add(m)
FEE = 0.0125; WIN = 600
def txc(t): return ((t["fee"] or 0) + (t["tips"] if isinstance(t["tips"], int) else 0)) / 1e9
def work(key):
    run, b = key; out = []
    for m, tr in D.rp.read_bucket(run, b, byb[key]).items():
        S0 = D.L[m]["slot"]; slots = [t["s"] for t in tr]
        def mtm(tok, slot):                     # value of tok at the last curve state at or before `slot`
            k = bisect.bisect_right(slots, slot) - 1
            if k < 0 or tok <= 0: return 0.0
            V, T = tr[k]["vsol"], tr[k]["vtok"]; return (V * tok // (T + tok)) * (1 - FEE) / 1e9
        trips = {}                              # trade index of the trip buy -> (trigger index, dt)
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
                if j not in trips: trips[j] = (k, round(dt, 1))
        users = {tr[j]["user"] for j in trips}
        for u in users:
            lots = collections.deque()          # [tok_left, buy_slot, trip_j or None, proceeds, sold_tok, sell_txc]
            res = {}
            def expire(now_slot):
                while lots and lots[0][1] + WIN < now_slot:
                    lo = lots.popleft()
                    if lo[2] is not None: res[lo[2]] = (lo[3], mtm(lo[0], lo[1] + WIN), lo[4], lo[5])
                # lots behind the head can also be old; FIFO head first is enough because buy slots are increasing
            for j, y in enumerate(tr):
                if y["user"] != u: continue
                expire(y["s"])
                if y["buy"]:
                    lots.append([y["tok"], y["s"], j if j in trips else None, 0.0, 0, 0.0])
                else:
                    left = y["tok"]; px = y["sol"] * (1 - FEE) / y["tok"] / 1e9; c = txc(y)
                    while left > 0 and lots:
                        lo = lots[0]; tk = min(left, lo[0]); lo[0] -= tk; left -= tk; lo[3] += tk * px; lo[4] += tk; lo[5] += c * tk / y["tok"]
                        if lo[0] <= 0:
                            lots.popleft()
                            if lo[2] is not None: res[lo[2]] = (lo[3], 0.0, lo[4], lo[5])
            for lo in lots:
                if lo[2] is not None: res[lo[2]] = (lo[3], mtm(lo[0], min(lo[1] + WIN, slots[-1])), lo[4], lo[5])
            for j, (proceeds, mv, sold, stc) in res.items():
                x = tr[j]; k, dt = trips[j]
                out.append(dict(u=u, m=m, run=run, dt=dt, cost=round(x["sol"] * (1 + FEE) / 1e9, 6), back=round(proceeds, 6), mtm=round(mv, 6),
                                tok=x["tok"], sold=sold, txc=round(txc(x) + stc, 6), bslot=x["s"]))
    return out
if __name__ == "__main__":
    R = []
    with Pool(int(os.environ.get("NPROC", "6"))) as p:
        for o in p.imap_unordered(work, sorted(byb), chunksize=2): R += o
    with gzip.open(OUT, "wt") as f:
        for r in R: f.write(json.dumps(r) + "\n")
    print("trips", len(R))
