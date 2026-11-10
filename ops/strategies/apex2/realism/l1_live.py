#!/usr/bin/env python3
"""APEX-REALISM step 1: per-attempt table of the 4 live probes (r10/r11/r13/r14). Out: realism/live.json"""
import json, collections
P = "/home/it/sniper-data/apex2/probes"; OUT = "/home/it/sniper-data/apex2/realism/live.json"
rows = []
for r in ("r10", "r11", "r13", "r14"):
    L = [json.loads(l) for l in open(f"{P}/apex_{r}.jsonl") if l.strip()]
    st = [x for x in L if x["ev"] == "start"][0]
    by = collections.defaultdict(dict)
    for x in L:
        if "id" in x and x["ev"] != "send_ack": by[x["id"]].setdefault(x["ev"], x)
    for i, d in sorted(by.items()):
        if "attempt" not in d: continue
        a = d["attempt"]; bs = d.get("buy_sent", {}); bl = d.get("buy_landed"); bf = d.get("buy_failed"); rz = d.get("realized", {})
        cps = a.get("copies") or []
        rows.append(dict(run=r, id=i, mint=a["mint"], size=st["size"] / 1e9, outcome=a["outcome"], cls=a.get("class"), client=a.get("client"),
                         leader=a.get("leader"), slot=a.get("slot"), index=a.get("index"), slot_delta=a.get("slot_delta"),
                         cs=(bl or bf or {}).get("create_slot") or bs.get("slot"), creator=bs.get("creator"), signer=bs.get("signer"),
                         dev_buy=bs.get("dev_buy"), bundle_pulled=bs.get("bundle_pulled"), bundle_seen=bs.get("bundle_seen"),
                         rx_to_sent_us=bs.get("rx_to_sent_us"), feed=bs.get("feed"), t=bs.get("t"),
                         c2s=(bl or bf or {}).get("create_to_shred_ms"), err=(bf or {}).get("err_line"), why=(bf or {}).get("why"),
                         cost=a.get("cost_lamports"), pnl=rz.get("pnl"), lanes=[(c["lane"], c.get("tip"), c.get("prio"), c.get("outcome"),
                         c.get("err_code"), c.get("sig")) for c in cps], create_sig=bs.get("create_sig"),
                         pos=(d.get("position") or {}).get("pos"), rivals=(d.get("position") or {}).get("rivals")))
json.dump(rows, open(OUT, "w"))
c = collections.Counter((x["run"], x["outcome"]) for x in rows); print(sorted(c.items()))
print(collections.Counter((x["cls"], x["outcome"]) for x in rows))
print(collections.Counter((x["outcome"], x["slot_delta"]) for x in rows))
for x in rows:
    if x["outcome"] != "landed": print(x["run"], x["id"], x["outcome"], x["cls"], x["slot_delta"], x["cost"], x["why"], (x["err"] or "")[-30:], [(l[0], l[3], l[4]) for l in x["lanes"]])
