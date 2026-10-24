#!/usr/bin/env python3
# Claim 5: re-run of dipshadow/dip_census.py with the SAME matching (every same-slot buy <= 150 ms (proxy) after a dip trigger of the
# event file, that wallet's next sells within 600 slots, "FIFO approximation"), recording what the census throws away or hides:
#   sigs of the buy and the sells (for chain hand-checks), tokens bought / sold, trips with NO sell (census drops them),
#   the unsold remainder of partial trips (census values it at 0), the wallet's holding before the buy, re-use of one sell by
#   several trips of the same wallet, and real tx costs (collector fee + tips of the buy and the sells used).
# Local files only. usage: python3 -I v2_census.py ev_file.jsonl.gz out.jsonl.gz
import sys, os, json, gzip, collections
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "v2_mods"))
import dipbuy4_s as D          # snapshot copy (module forces RP_REPAIR=1, exactly like the census run)
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
                pre = sum((y["tok"] if y["buy"] else -y["tok"]) for y in tr[:j] if y["user"] == x["user"])
                need = x["tok"]; got = 0.0; last = None; sells = []; endk = j
                for jj in range(j + 1, len(tr)):
                    y = tr[jj]
                    if y["s"] - x["s"] > 600: break
                    endk = jj
                    if y["user"] != x["user"] or y["buy"]: continue
                    take = min(need, y["tok"]); got += y["sol"] * take / y["tok"]; need -= take; last = y
                    sells.append((y["sig"], y["s"], take, y["tok"], ((y["fee"] or 0) + (y["tips"] or 0)) if isinstance(y["tips"], int) else (y["fee"] or 0)))
                    if need <= 0: break
                # value of the unsold remainder at the last curve state inside the window (constant product, minus fee)
                ze = tr[endk]; rem = max(need, 0)
                remv = (ze["vsol"] * rem // (ze["vtok"] + rem)) * (1 - FEE) / 1e9 if rem else 0.0
                buy_cost_tx = ((x["fee"] or 0) + (x["tips"] if isinstance(x["tips"], int) else 0)) / 1e9
                sell_cost_tx = sum(c * take / tok for _, _, take, tok, c in sells) / 1e9
                out.append(dict(u=x["user"], m=m, run=run, dt=round(dt, 1), cost=round(x["sol"] * (1 + FEE) / 1e9, 6), back=round(got * (1 - FEE) / 1e9, 6),
                                hold=(last["s"] - x["s"]) if last else None, full=need <= 0, nosell=last is None, tok=x["tok"], sold=x["tok"] - rem,
                                remv=round(remv, 6), pre=pre, bsig=x["sig"], bslot=x["s"], sells=[[s, sl, tk, stok, round(c / 1e9, 6)] for s, sl, tk, stok, c in sells],
                                txc=round(buy_cost_tx + sell_cost_tx, 6), trig_sol=round(t["sol"] / 1e9, 3), tsig=t["sig"]))
    return out
if __name__ == "__main__":
    R = []
    with Pool(int(os.environ.get("NPROC", "6"))) as p:
        for o in p.imap_unordered(work, sorted(byb), chunksize=2): R += o
    with gzip.open(OUT, "wt") as f:
        for r in R: f.write(json.dumps(r) + "\n")
    print("trips (incl. no-sell)", len(R), "with a sell", sum(1 for r in R if not r["nosell"]))
