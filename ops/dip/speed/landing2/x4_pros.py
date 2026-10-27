#!/usr/bin/env python3
# Per wallet: first landing after each dump (sell >= MIN_SOL, drop >= MIN_DROP), within 3 slots. Offsets (block positions MEASURED;
# ms on the block clock INFERRED), same-slot rate, landed route (tip service of the landed tx), CU price, tip, copies landed,
# split by leader client, dump quartile in its block, the dump's window slot, leader location.
import sys, json, collections, statistics as st
sys.path.insert(0, "/home/moiz/sniper/ops/dip/speed/landing2")
import lib2
MIN_SOL = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
MIN_DROP = float(sys.argv[2]) if len(sys.argv) > 2 else 0.04
R = lib2.load(); LS = lib2.leaders(); WAL = json.load(open(f"{lib2.D}/wallets.json"))
DU = R["dumps"]
rows = []; per = collections.defaultdict(list)
# failed-early txs (no Buy/Sell log): keep only if their program set is one this wallet uses for BUYS and never for sells
DROP = {"pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"}
def psig(x): return frozenset(p for p in x["progs"] if p not in DROP)
BUYSIG = collections.defaultdict(collections.Counter)
for x in R["landings"]:
    if x.get("kind") == "buy": BUYSIG[x["w"]][psig(x)] += 1
EARLY = collections.Counter()
for x in R["landings"]:
    if x.get("kind") == "other":
        if BUYSIG[x["w"]][psig(x)] < 3: continue
        EARLY[x["w"]] += 1
    d = DU.get(x["dump"])
    if not d: continue
    s0, i0, sol, drop, seller, mint, _ = d
    if sol < MIN_SOL * 1e9 or drop < MIN_DROP or x["w"] == seller: continue
    per[(x["w"], x["dump"])].append(x)
for (w, dk), v in per.items():
    v.sort(key=lambda x: (x["s"], x["i"]))
    x = v[0]; d = DU[dk]; s0, i0 = d[0], d[1]
    n0 = lib2.nblk(R, s0); n1 = lib2.nblk(R, x["s"])
    if not n0 or not n1: continue
    ld = LS.get(s0); ll = LS.get(x["s"])
    svcs = [lib2.route(x["tips"], x["sdp"])]
    tip = sum(v_ for _, v_ in x["tips"])
    rows.append(dict(w=w, dump=dk, s0=s0, i0=i0, n0=n0, s=x["s"], i=x["i"], n=n1, ds=x["s"] - s0, dpos=(x["i"] - i0) if x["s"] == s0 else None,
                     ms=round(lib2.tms(x["s"], x["i"], n1) - lib2.tms(s0, i0, n0), 1), q=min(3, int(4 * i0 / n0)), k=s0 % 4,
                     cl=lib2.client(ld) if ld else "?", cl_land=lib2.client(ll) if ll else "?", loc=lib2.loc(ld) if ld else "?",
                     same_leader=(ld == ll), ok=x["err"] is None, svc="+".join(svcs), tip=tip, cup=x["cup"] or 0, cul=x["cul"] or 0, cu=x["cu"],
                     fee=x["fee"], copies=len(v), copies_ok=sum(1 for y in v if y["err"] is None), sig=x["sig"], nsig=x["nsig"],
                     sol=d[2], drop=d[3], leader=ld))
json.dump(rows, open(f"{lib2.D}/pro_rows_{MIN_SOL}_{MIN_DROP}.json", "w"))
med = lambda v: round(st.median(v), 1) if v else None
def pct(v, p): v = sorted(v); return round(v[min(len(v) - 1, int(p * len(v)))], 1) if v else None
by = collections.defaultdict(list)
for r in rows: by[r["w"]].append(r)
order = sorted(by, key=lambda w: (WAL[w]["grp"] != "ours", WAL[w]["grp"] != "pro", WAL[w]["grp"], -len(by[w])))
print(f"dump = sell >= {MIN_SOL} SOL, drop >= {MIN_DROP:.0%}; reaction = the wallet's first landed buy (failed too) <= 3 slots after; "
      f"ms = block clock (INFERRED); pos = block positions (MEASURED)\n")
print(f"{'wallet':10s} {'grp':7s} {'n':>5s} {'ok%':>4s} {'same':>5s} {'pos p25/50':>11s} {'ms p25/50/75':>16s} {'copies>1':>8s} {'CUprice med':>11s} {'CUlim':>6s} {'tip med':>8s}  routes (share)")
for w in order:
    v = by[w]
    if len(v) < 20: continue
    ss = [r for r in v if r["ds"] == 0]
    svc = collections.Counter(r["svc"] for r in v)
    tot = len(v)
    print(f"{WAL[w]['name'][:10]:10s} {WAL[w]['grp'][:7]:7s} {tot:5d} {sum(r['ok'] for r in v)/tot:4.0%} {len(ss)/tot:5.0%} "
          f"{str(pct([r['dpos'] for r in ss],.25))+'/'+str(med([r['dpos'] for r in ss])):>11s} "
          f"{str(pct([r['ms'] for r in v],.25))+'/'+str(med([r['ms'] for r in v]))+'/'+str(pct([r['ms'] for r in v],.75)):>16s} "
          f"{sum(1 for r in v if r['copies']>1)/tot:8.0%} {med([r['cup'] for r in v]) or 0:11.0f} {med([r['cul'] for r in v]) or 0:6.0f} {(med([r['tip'] for r in v]) or 0)/1e9:8.5f}  "
          + ", ".join(f"{k} {n/tot:.0%}" for k, n in svc.most_common(6)))
