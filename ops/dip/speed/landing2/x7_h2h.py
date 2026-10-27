#!/usr/bin/env python3
# Head to head: on the dumps where WE fired (live dip runs), where did each pro / fast bot land vs us?
# Our landing = the landed variant of our fire (chain position from the recording). ms = block clock (INFERRED), positions MEASURED.
import sys, json, collections, statistics as st
sys.path.insert(0, "/home/moiz/sniper/ops/dip/speed/landing2")
import lib2
R = lib2.load(); LS = lib2.leaders(); WAL = json.load(open(f"{lib2.D}/wallets.json"))
DU = R["dumps"]; FOL = R["followers"]
FIRES = json.load(open(f"{lib2.D}/our_fires.json"))
OURS = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
BYSIG = {x["sig"]: x for x in R["landings"]}
# first landing per (wallet, dump) for every target wallet (failed-early kept only if the wallet's buy program set)
DROP = {"pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"}
def psig(x): return frozenset(p for p in x["progs"] if p not in DROP)
BUYSIG = collections.defaultdict(collections.Counter)
for x in R["landings"]:
    if x.get("kind") == "buy": BUYSIG[x["w"]][psig(x)] += 1
FIRST = {}
for x in R["landings"]:
    if x.get("kind") == "other" and BUYSIG[x["w"]][psig(x)] < 3: continue
    k = (x["w"], x["dump"])
    if k not in FIRST or (x["s"], x["i"]) < (FIRST[k]["s"], FIRST[k]["i"]): FIRST[k] = x
PERDUMP = collections.defaultdict(dict)
for (w, dk), x in FIRST.items(): PERDUMP[dk][w] = x
def ms(s0, i0, s, i): return lib2.tms(s, i, lib2.nblk(R, s) or i + 1) - lib2.tms(s0, i0, lib2.nblk(R, s0) or i0 + 1)
def svc(tips, sdp=()): return lib2.route(tips, sdp)
rows = []
for f in FIRES:
    d = DU.get(f["dump_sig"])
    if not d: continue
    s0, i0, sol, drop, seller, mint, _ = d
    n0 = lib2.nblk(R, s0)
    if not n0: continue
    # our landing
    ours = None
    for _, sig, _, _ in f["variants"] or []:
        if sig in BYSIG: ours = BYSIG[sig]
    if ours is None and f.get("land_sig") in BYSIG: ours = BYSIG[f["land_sig"]]
    ld = LS.get(s0)
    row = dict(srv=f["srv"], run=f["run"], dump=f["dump_sig"], mint=mint, s0=s0, i0=i0, n0=n0, q=min(3, int(4 * i0 / n0)), k=s0 % 4,
               cl=lib2.client(ld) if ld else "?", loc=lib2.loc(ld) if ld else "?", leader=ld, result=f.get("result"), sol=sol, drop=drop,
               our_paths=[v[0] for v in f["variants"] or []], timing=f.get("timing"))
    if ours:
        row.update(our_s=ours["s"], our_i=ours["i"], our_ms=round(ms(s0, i0, ours["s"], ours["i"]), 1), our_ds=ours["s"] - s0, our_ok=ours["err"] is None,
                   our_svc=svc(ours["tips"], ours["sdp"]), our_sig=ours["sig"], our_cup=ours["cup"], our_tip=sum(v for _, v in ours["tips"]))
    rv = []
    for w, x in PERDUMP.get(f["dump_sig"], {}).items():
        if w in OURS or w == seller: continue
        rv.append(dict(w=w, name=WAL[w]["name"], grp=WAL[w]["grp"], s=x["s"], i=x["i"], ms=round(ms(s0, i0, x["s"], x["i"]), 1), ds=x["s"] - s0,
                       ok=x["err"] is None, svc=svc(x["tips"], x["sdp"]), cup=x["cup"], tip=sum(v for _, v in x["tips"]), sig=x["sig"], cul=x["cul"]))
    rv.sort(key=lambda r: (r["s"], r["i"]))
    row["rivals"] = rv
    # all buyers ahead of our landing (any wallet) from the follower list
    fl = FOL.get(f["dump_sig"]) or []
    if ours:
        ahead = [r for r in fl if (r[0], r[1]) < (ours["s"], ours["i"]) and r[2] not in OURS]
        row["n_ahead"] = len(ahead)
        row["first_buyer"] = dict(user=ahead[0][2], pos=ahead[0][1] - i0 if ahead[0][0] == s0 else None, ds=ahead[0][0] - s0,
                                  svc=ahead[0][10] or "none", cup=ahead[0][5], ms=round(ms(s0, i0, ahead[0][0], ahead[0][1]), 1)) if ahead else None
    rows.append(row)
json.dump(rows, open(f"{lib2.D}/h2h.json", "w"))
med = lambda v: round(st.median(v), 1) if v else None
have = [r for r in rows if "our_ms" in r]
print(f"our fires matched to a recorded dump: {len(rows)}; with our landing found on chain: {len(have)}")
# per pro: on dumps where both landed, pro ms vs ours
print("\n== same dumps, both landed: pro vs us (block clock ms, INFERRED; 'ahead' = pro landed earlier in chain order, MEASURED)")
agg = collections.defaultdict(list)
for r in have:
    for x in r["rivals"]:
        agg[x["w"]].append((r, x))
for w, v in sorted(agg.items(), key=lambda kv: -len(kv[1])):
    if len(v) < 8: continue
    ahead = sum(1 for r, x in v if (x["s"], x["i"]) < (r["our_s"], r["our_i"]))
    print(f"  {WAL[w]['name'][:9]:9s} {WAL[w]['grp']:7s} dumps {len(v):4d} | pro ahead of us {ahead/len(v):4.0%} | pro ms med {med([x['ms'] for r,x in v])} vs ours {med([r['our_ms'] for r,x in v])} "
          f"| diff (ours - pro) med {med([r['our_ms']-x['ms'] for r,x in v])} | pro same-slot {sum(1 for r,x in v if x['ds']==0)/len(v):.0%} vs ours {sum(1 for r,x in v if r['our_ds']==0)/len(v):.0%}")
print("\n== by client: our landing vs the FIRST landed pro/bot on the same dump (median ms, n)")
for c in ("Jito-own", "Jito-relayer", "BAM", "Harmonic", "Firedancer", "Rakurai"):
    v = [r for r in have if r["cl"] == c]
    v2 = [r for r in v if r["rivals"]]
    if not v: continue
    first = [r["rivals"][0] for r in v2]
    print(f"  {c:12s} n={len(v):3d} | ours {med([r['our_ms'] for r in v])} ms, same-slot {sum(1 for r in v if r['our_ds']==0)/len(v):.0%} | "
          f"first bot {med([x['ms'] for x in first])} ms (n={len(first)}), ahead of us {sum(1 for r in v2 if (r['rivals'][0]['s'],r['rivals'][0]['i'])<(r['our_s'],r['our_i']))/max(1,len(v2)):.0%} | "
          f"first bot routes {collections.Counter(x['svc'] for x in first).most_common(4)}")
print("\n== by dump quartile / window slot (ours)")
for q in range(4):
    v = [r for r in have if r["q"] == q]
    print(f"  Q{q+1}: n={len(v)} ours {med([r['our_ms'] for r in v])} ms same-slot {sum(1 for r in v if r['our_ds']==0)/max(1,len(v)):.0%}")
for k in range(4):
    v = [r for r in have if r["k"] == k]
    print(f"  window slot {k+1}: n={len(v)} ours {med([r['our_ms'] for r in v])} ms same-slot {sum(1 for r in v if r['our_ds']==0)/max(1,len(v)):.0%}")
