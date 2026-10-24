#!/usr/bin/env python3
# Landing probes of the dip engine (--dip-probe): block-position ms of each probe after its dump (same scale as frz_all.py /
# dip_speed.py: (slot diff + index/size diff) x 212 ms), per leader client and route. READ-ONLY RPC.
# usage: python3 -I probe_speed.py <label>=<probe.jsonl> [<label>=<probe.jsonl> ...]
import sys, json, statistics, collections, importlib.util
spec = importlib.util.spec_from_file_location("osp", "/home/moiz/sniper/ops/speedcheck/our_speed.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
allrows = []
for arg in sys.argv[1:]:
    label, path = arg.split("=", 1)
    ev = [json.loads(l) for l in open(path)]
    lands = {e["sig"]: e for e in ev if e["ev"] == "probe_land"}
    for p in [e for e in ev if e["ev"] == "probe"]:
        l = lands.get(p["buy_sig"])
        slot = l["slot"] if l else None
        if slot is None:
            st = S.rpc("getSignatureStatuses", [[p["buy_sig"]], {"searchTransactionHistory": True}])
            v = (st or {}).get("value", [None])[0] if isinstance(st, dict) else None
            slot = v["slot"] if v else None
        row = dict(label=label, client=p["client"], route=p["route"].replace("route:", ""), paths="+".join(w["path"] for w in p["writes"]), landed=slot is not None,
                   decision_us=p["decision_us"], ms=None, dslot=None)
        if slot is not None:
            pb = S.pos(slot, p["buy_sig"]); pd = S.pos(p["slot"], p["dump_sig"])
            if pb and pd:
                row["ms"] = round((slot - p["slot"]) * S.SLOT_MS + (pb[0] / pb[1] - pd[0] / pd[1]) * S.SLOT_MS, 1); row["dslot"] = slot - p["slot"]
        allrows.append(row)
json.dump(allrows, open("/home/moiz/sniper/ops/dip/speed/probe_speed.json", "w"), indent=1)
by = collections.defaultdict(list)
for r in allrows: by[(r["client"], r["label"], r["paths"])].append(r)
print(f"{'leader':20s} {'session':8s} {'paths':22s}  n  landed  same-slot  median ms   all ms")
for k in sorted(by):
    v = by[k]; ms = sorted(r["ms"] for r in v if r["ms"] is not None)
    print(f"{k[0]:20s} {k[1]:8s} {k[2]:22s} {len(v):2d}  {sum(r['landed'] for r in v):2d}      {sum(1 for r in v if r['dslot'] == 0):2d}       {statistics.median(ms) if ms else float('nan'):7.1f}   {ms}")
for lab in sorted({r["label"] for r in allrows}):
    ms = [r["ms"] for r in allrows if r["label"] == lab and r["ms"] is not None]
    n = sum(1 for r in allrows if r["label"] == lab)
    print(f"{lab}: {n} probes, landed {len(ms)}, median {statistics.median(ms) if ms else float('nan'):.1f} ms, same slot {sum(1 for r in allrows if r['label'] == lab and r['dslot'] == 0)}")
