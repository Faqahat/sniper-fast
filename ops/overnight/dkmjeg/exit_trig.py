#!/usr/bin/env python3
# READ-ONLY, offline: what triggers dKMjeG's sells? Slot-level hazard on its R1/R2 tokens (SOL-quoted, collector rows):
# P(it sells in slot s | event in s or s-1) vs P(it sells | no event), events = dev/bundle sell, outside sell, price below
# entry, new high; plus what separates "dump all at ~2 s" from "sell half at ~2 s" (follow-on buying after its buy).
import sys, json, collections, statistics as S
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
W = "dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK"
L = rp.load_launches(); C = json.load(open("/home/moiz/sniper/ops/overnight/dkmjeg/coll.json"))
todo = [m for m, v in C.items() if "dk" in v and "sells" in v["dk"] and v["solq"]]
byb = collections.defaultdict(set)
for m in todo: byb[(L[m]["run"], rp.bucket(m))].add(m)
def work(key):
    run, b = key; tra = rp.read_bucket(run, b, byb[key]); out = []
    for m, tr in tra.items():
        c = L[m]; st = rp.structure(tr, c); ins = st["insiders"]
        k0 = next((k for k, t in enumerate(tr) if t["user"] == W and t["buy"]), None)
        if k0 is None: continue
        b0 = tr[k0]; pin = b0["sol"] / b0["tok"]; bs = b0["s"]
        my_sells = collections.Counter(t["s"] for t in tr if t["user"] == W and not t["buy"])
        first = min(my_sells) if my_sells else None
        ev = collections.defaultdict(set); peak = pin; px_end = {}
        V, T = b0["vsol"], b0["vtok"]
        for t in tr[k0 + 1:]:
            if t["s"] > bs + 60: break
            if t["user"] == W: continue
            if not t["buy"]: ev[t["s"]].add("ins_sell" if t["user"] in ins else "out_sell")
            else: ev[t["s"]].add("out_buy")
            p = t["vsol"] / t["vtok"] if t["vtok"] else None
            if p:
                if p > peak * 1.0001: ev[t["s"]].add("new_high"); peak = p
                px_end[t["s"]] = p / pin
        # follow-on buying in the first 8 slots after its buy (other wallets)
        fb = [t for t in tr[k0 + 1:] if t["s"] <= bs + 8 and t["buy"] and t["user"] != W]
        fs = [t for t in tr[k0 + 1:] if t["s"] <= bs + 8 and not t["buy"] and t["user"] != W]
        first_frac = None
        if first is not None:
            tot = sum(t["tok"] for t in tr if t["user"] == W and t["buy"]); first_frac = sum(t["tok"] for t in tr if t["user"] == W and not t["buy"] and t["s"] == first) / tot
        last_px = 1.0; slots = []
        for s in range(bs, bs + 41):
            if s in px_end: last_px = px_end[s]
            slots.append(dict(s=s - bs, sell=int(my_sells.get(s, 0) > 0), ins=int("ins_sell" in ev[s] or "ins_sell" in ev[s - 1]), outs=int("out_sell" in ev[s]),
                              hi=int("new_high" in ev[s]), below=int(last_px < 1.0), first=int(s == first)))
        out.append(dict(m=m, first=None if first is None else first - bs, first_frac=first_frac, fb_n=len(fb), fb_sol=sum(t["sol"] for t in fb) / 1e9, fs_n=len(fs),
                        px8=px_end.get(max([s for s in px_end if s <= bs + 8], default=bs), 1.0) if px_end else 1.0, slots=slots))
    return out
if __name__ == "__main__":
    res = []
    with Pool(12) as p:
        for o in p.imap_unordered(work, sorted(byb)): res += o
    print("tokens", len(res))
    for evn in ("ins", "outs", "hi", "below"):
        a = [z for r in res for z in r["slots"] if z[evn] and z["s"] >= 1]; b = [z for r in res for z in r["slots"] if not z[evn] and z["s"] >= 1]
        print(f"P(it sells in a slot | {evn:5}) {sum(z['sell'] for z in a) / max(1, len(a)):.3f} (n={len(a)}) vs without {sum(z['sell'] for z in b) / max(1, len(b)):.3f} (n={len(b)})")
    # dump-all vs half at the ~2 s decision (first sell in slots 7..12)
    g = collections.defaultdict(list)
    for r in res:
        if r["first"] is None or not (7 <= r["first"] <= 12): continue
        k = "100%" if r["first_frac"] > 0.99 else ("~50%" if 0.4 < r["first_frac"] < 0.6 else "other")
        g[k].append(r)
    for k, v in g.items():
        print(f"first sell at slot 7-12, {k:5}: n={len(v)} | other wallets' buys in 8 slots after its buy: n med {S.median(r['fb_n'] for r in v)}, SOL med {S.median(r['fb_sol'] for r in v):.2f} | sells med {S.median(r['fs_n'] for r in v)} | price at slot 8 vs its entry med {S.median(r['px8'] for r in v):.3f}")
    json.dump([{k: v for k, v in r.items() if k != "slots"} for r in res], open("/home/moiz/sniper/ops/overnight/dkmjeg/exit_trig.json", "w"))
