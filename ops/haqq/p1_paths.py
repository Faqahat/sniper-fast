#!/usr/bin/env python3
# haqq SEND PATHS, part 1 (local recording only): which relay landed each haqq tx (tip account of the landed copy), tip amounts,
# CU price / limit, by buy / sell, leader client, leader distance (RTT from Frankfurt), size, block position; failed (6042) rate
# by leader client. Output: sniper-data/haqq/paths1.json + printed tables.
import json, collections, statistics as st, sys
sys.path.insert(0, "/home/moiz/sniper/ops/haqq")
import h_lib as H
R = json.load(open(f"{H.OUT}/ledger.json"))
rows = []
for r in R:
    if r["kind"] not in ("buy", "sell", "fail"): continue
    ld, cl, rtt, cc = H.leader_info(r["s"])
    svcs = [H.svc_of(a) for a in r["tipacc"]]
    svc = "none" if not svcs else (svcs[0] if len(set(svcs)) == 1 else "multi:" + "+".join(sorted(set(svcs))))
    ss, exact = H.slot_size(r["s"])
    sz = None
    if r["evs"]: sz = r["evs"][0]["sol"] / 1e9
    kind = r["kind"]
    if kind == "fail": kind = "fail_sell" if "Sell" in r["ixn"] else ("fail_buy" if "Buy" in r["ixn"] else "fail_other")
    rows.append(dict(run=r["run"], s=r["s"], i=r["i"], bt=r["bt"], kind=kind, svc=svc, tip=r["tips"], cup=r["cup"] or 0, cul=r["cul"] or 0, cu=r["cu"] or 0,
                     fee=r["fee"], leader=ld, client=cl, rtt=rtt, cc=cc, size=sz, pos=(r["i"] / ss if ss else None), err=r["err"]))
json.dump(rows, open(f"{H.OUT}/paths1.json", "w"))
def pct(c, n): return f"{100 * c / max(1, n):.0f}%"
def table(sel, key, top=10):
    c = collections.Counter(key(x) for x in sel); n = len(sel)
    return ", ".join(f"{k} {v} ({pct(v, n)})" for k, v in c.most_common(top))
land = [x for x in rows if x["kind"] in ("buy", "sell")]
print(f"landed haqq trades: {len(land)} (buys {sum(1 for x in land if x['kind'] == 'buy')}, sells {sum(1 for x in land if x['kind'] == 'sell')}); failed {sum(1 for x in rows if x['kind'].startswith('fail'))}")
for k in ("buy", "sell"):
    sel = [x for x in land if x["kind"] == k]
    print(f"\n== {k}s n {len(sel)} — landed path: {table(sel, lambda x: x['svc'], 12)}")
    for run in ("R1", "R2", "R3", "R4"):
        s2 = [x for x in sel if x["run"] == run]; print(f"   {run} n {len(s2)}: {table(s2, lambda x: x['svc'], 8)}")
    # tips per path
    for sv, n in collections.Counter(x["svc"] for x in sel).most_common(8):
        t = [x["tip"] for x in sel if x["svc"] == sv]
        tc = collections.Counter(t).most_common(4)
        print(f"   tip {sv:12s} n {n:5d}: median {st.median(t) / 1e9:.6f} SOL; most common {[(v / 1e9, c) for v, c in tc]}")
    cu = [x["cup"] for x in sel]; cl = [x["cul"] for x in sel]; used = [x["cu"] for x in sel]; fee = [x["fee"] for x in sel]
    print(f"   CU price median {st.median(cu):,.0f} (p10 {st.quantiles(cu, n=10)[0]:,.0f}, p90 {st.quantiles(cu, n=10)[8]:,.0f}) | CU limit median {st.median(cl):,.0f} | used median {st.median(used):,.0f} | fee median {st.median(fee):,} lamports")
    print(f"   CU price values: {collections.Counter(cu).most_common(6)}")
    print(f"   CU limit values: {collections.Counter(cl).most_common(6)}")
print("\n== landed path by leader client (buys+sells)")
for cl in ("bam", "jito", "harmonic", "fd", "agave", "other", "?"):
    sel = [x for x in land if x["client"] == cl]
    if sel: print(f"   {cl:9s} n {len(sel):5d}: {table(sel, lambda x: x['svc'], 7)}")
print("\n== landed path by leader distance (RTT from Frankfurt)")
for lab, lo, hi in (("<5 ms", 0, 5), ("5-20", 5, 20), ("20-60", 20, 60), ("60-120", 60, 120), (">=120", 120, 1e9), ("unknown", None, None)):
    sel = [x for x in land if (x["rtt"] is None if lo is None else (x["rtt"] is not None and lo <= x["rtt"] < hi))]
    if sel: print(f"   {lab:8s} n {len(sel):5d}: {table(sel, lambda x: x['svc'], 7)}")
print("\n== landed path by buy size")
for lab, lo, hi in (("<0.05", 0, 0.05), ("0.05-0.3", 0.05, 0.3), ("0.3-0.5", 0.3, 0.5), ("0.5-0.8", 0.5, 0.8), (">=0.8", 0.8, 99)):
    sel = [x for x in land if x["kind"] == "buy" and lo <= x["size"] < hi]
    if sel: print(f"   {lab:9s} n {len(sel):5d}: {table(sel, lambda x: x['svc'], 6)} | tip median {st.median([x['tip'] for x in sel]) / 1e9:.6f}")
print("\n== failed attempts (landed but failed) by leader client: buys")
for cl in ("bam", "jito", "harmonic", "fd", "agave", "other", "?"):
    ok = sum(1 for x in land if x["client"] == cl and x["kind"] == "buy"); bad = sum(1 for x in rows if x["client"] == cl and x["kind"] == "fail_buy")
    oks = sum(1 for x in land if x["client"] == cl and x["kind"] == "sell"); bads = sum(1 for x in rows if x["client"] == cl and x["kind"] == "fail_sell")
    if ok + bad: print(f"   {cl:9s} buys landed ok {ok:5d}, failed {bad:4d} ({pct(bad, ok + bad)}) | sells ok {oks:5d}, failed {bads:3d} ({pct(bads, oks + bads)})")
print("   fail codes:", collections.Counter((x["kind"], (x["err"] or "")[:46]) for x in rows if x["kind"].startswith("fail")).most_common(6))
print("\n== block position (index / block size) of landed txs by path (median)")
for sv, n in collections.Counter(x["svc"] for x in land).most_common(8):
    p = [x["pos"] for x in land if x["svc"] == sv and x["pos"] is not None]
    if p: print(f"   {sv:12s} n {n:5d}: median pos {st.median(p):.2f}, p25 {st.quantiles(p, n=4)[0]:.2f}, p75 {st.quantiles(p, n=4)[2]:.2f}")
