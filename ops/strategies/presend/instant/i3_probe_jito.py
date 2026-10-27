#!/usr/bin/env python3
# INSTANT-BOTS study, step 3 (read-only): for each probe instant event, ask the public Jito bundle API whether the dump and each
# instant buy landed in a Jito bundle, and whether they share ONE bundle (= a bundle/backrun with the dump).
# usage: python3 -I i3_probe_jito.py probe_map.json OUT.json
import sys, json
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/instant")
import jito_api as J
out = json.load(open(sys.argv[1])); res = []
for x in out:
    if x.get("missing"): continue
    d = x["dump"]; bd = J.bundle_of(d["sig"])
    for r in x["tape"]:
        if not r["instant"]: continue
        bb = J.bundle_of(r["sig"])
        same = isinstance(bd, dict) and isinstance(bb, dict) and bd.get("bundle_id") == bb.get("bundle_id")
        row = dict(mint=x["mint"], slot=x["slot"], client=x["client"], dump_user=d["user"], dump_sig=d["sig"], dump_tip=d["tip"], dump_tipsvc=d["tipsvc"],
                   dump_bundle=bd, buy_user=r["user"], buy_sig=r["sig"], gap=r["gap"], buy_tip=r["tip"], buy_tipsvc=r["tipsvc"], buy_bundle=bb, same_bundle=same)
        res.append(row)
        nb = lambda b: ("no bundle" if b is None else ("ERR" if b == "ERR" else f"bundle {b['bundle_id'][:10]} n={len(b.get('txs') or [])} tip {b.get('tip')} idx {b.get('block_index')}"))
        print(f"{x['slot']} {x['client']:8s} dump {d['user'][:8]} [{nb(bd)}] -> buy {r['user'][:8]} gap {r['gap']} [{nb(bb)}] SAME={same}", flush=True)
    J.save()
json.dump(res, open(sys.argv[2], "w"), indent=1)
print("jito calls", J.calls())
