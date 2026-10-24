#!/usr/bin/env python3
# Our live dip buys on the SAME scale as the 10-23 landing probe (ops/speedcheck/frz_all.py): block-position ms of our buy tx
# after the trigger tx (here the DUMP, there the create): (slot diff + index/size diff) x 400 ms. READ-ONLY RPC (getBlock).
# usage: python3 -I dip_speed.py <run.jsonl> [more.jsonl ...]
import sys, json, statistics, importlib.util
spec = importlib.util.spec_from_file_location("osp", "/home/moiz/sniper/ops/speedcheck/our_speed.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
rows = []
for run in sys.argv[1:]:
    ev = [json.loads(l) for l in open(run)]
    for f in [e for e in ev if e["ev"] == "fire"]:
        cl = next((e for e in ev if e["ev"] == "close" and e.get("buy_sig") == f["buy_sig"]), {})
        lp = next((e for e in ev if e["ev"] == "land_poll" and e.get("sig") == f["buy_sig"]), {})
        bl = next((e for e in ev if e["ev"] == "buy_land" and e.get("sig") == f["buy_sig"]), None)
        bf = next((e for e in ev if e["ev"] == "buy_failed" and e.get("sig") == f["buy_sig"]), None)
        land_slot = (bl or {}).get("slot") or lp.get("land_slot") or (bf or {}).get("slot")
        if not land_slot: continue
        pb = S.pos(land_slot, f["buy_sig"]); pd = S.pos(f["slot"], f["dump_sig"])
        if not pb or not pd: print("no block position for", f["mint"][:6]); continue
        ms = (land_slot - f["slot"]) * S.SLOT_MS + (pb[0] / pb[1] - pd[0] / pd[1]) * S.SLOT_MS
        feed = ((bl or bf)["t"] - f["t_dump_rx"]) / 1e6 if (bl or bf) else None
        err = json.dumps(cl.get("err") or lp.get("err") or "")
        why = "FILLED" if bl else ("deadline" if "6001" in err else "guard" if "6042" in err else "failed")
        rows.append(dict(run=run.split("/")[-1][:6], mint=f["mint"][:6], client=f["client"], route=f["route"].replace("route:", ""), dslot=land_slot - f["slot"],
                         ms=round(ms, 1), feed=round(feed, 1) if feed is not None else None, why=why, idx=f"{pb[0]}/{pb[1]}", didx=f"{pd[0]}/{pd[1]}"))
for r in rows:
    print(f"{r['run']} {r['mint']} {r['client']:20s} via {r['route']:14s} +{r['dslot']} slot | block-position {r['ms']:6.1f} ms (dump {r['didx']}, ours {r['idx']}) | feed {r['feed']} ms | {r['why']}")
ms = [r["ms"] for r in rows]
print(f"{len(rows)} dip buys: block-position median {statistics.median(ms):.1f} ms, same slot as the dump {sum(1 for r in rows if r['dslot'] == 0)}/{len(rows)}")
json.dump(rows, open("/home/moiz/sniper/ops/dip/speed/dip_speed.json", "w"), indent=1)
