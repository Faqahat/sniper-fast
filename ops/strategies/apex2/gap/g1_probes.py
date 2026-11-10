#!/usr/bin/env python3
"""APEX-GAP step 1: flatten the two live probe records into one row per buy attempt.
Out: /home/it/sniper-data/apex2/gap/probes.json"""
import json, collections
P = "/home/it/sniper-data/apex2/probes"
rows = []
for run in ("r10", "r11"):
    ev = collections.defaultdict(dict); start = None
    for l in open(f"{P}/apex_{run}.jsonl"):
        d = json.loads(l); e = d["ev"]
        if e == "start": start = d; continue
        if "id" not in d: continue
        k = d["id"]
        if e in ("sell_sent",): ev[k].setdefault("sell_sent", []).append(d)
        elif e == "position": ev[k].setdefault("position", d)
        else: ev[k][e] = d
    for k, E in sorted(ev.items()):
        bs = E.get("buy_sent", {}); bl = E.get("buy_landed"); bf = E.get("buy_failed"); sl = E.get("sell_landed"); rz = E.get("realized", {})
        at = E.get("attempt", {}); pos = (E.get("position") or {}).get("pos") or {}
        txs = rz.get("txs", [])
        r = dict(run=run, id=k, mint=bs.get("mint"), creator=bs.get("creator"), spend=bs.get("spend"), create_slot=bs.get("slot"),
                 t_rx=bs.get("t_rx"), dev_buy=bs.get("dev_buy"), bundle_seen=bs.get("bundle_seen"), bundle_end=bs.get("bundle_end"),
                 expected_tokens=bs.get("expected_tokens"), vq=bs.get("vq_state"), client=(bs.get("route") or {}).get("client"),
                 copies=[(c["lane"], c["tip"], c["prio"]) for c in bs.get("copies", [])],
                 outcome=at.get("outcome"), landed=int(bool(bl)), pnl=rz.get("pnl"), buy_delta=txs[0]["delta"] if txs else None,
                 sell_delta=sum(t["delta"] or 0 for t in txs[1:]) if len(txs) > 1 else None, ntx=len(txs))
        if bl:
            r.update(buy_slot=bl["slot"], buy_idx=bl["index"], tokens=bl["tokens"], buy_sol=bl["buy_sol"], fill=bl["fill_vs_expected"],
                     t_buy_seen=bl["t"], c2shred=bl.get("create_to_shred_ms"), landed_copy=[c["lane"] for c in at.get("copies", []) if c["outcome"] == "landed"])
        if bf:
            r.update(fail_slot=bf.get("slot"), fail_why=bf.get("why"), fail_err=json.dumps(bf.get("err")), fail_copy=[(c["lane"], c.get("err_code")) for c in at.get("copies", []) if c["outcome"] == "reverted"])
        if sl:
            ss = E.get("sell_sent", [])
            r.update(sell_slot=sl["slot"], sell_idx=sl["index"], sell_sol=sl["sol"], sell_attempts=sl["attempt"], t_sell_land=sl["t"],
                     t_sell_sent=ss[0]["t"] if ss else None, sell_expected=ss[0]["expected_sol"] if ss else None, sell_hold_to_land_ms=sl["hold_to_land_ms"])
        r["position"] = pos
        rows.append(r)
json.dump(rows, open("/home/it/sniper-data/apex2/gap/probes.json", "w"), indent=0)
for r in rows:
    print(r["run"], r["id"], r["mint"][:6], r["creator"][:6], r["outcome"], r["pnl"], r.get("buy_delta"), r.get("sell_delta"), r.get("buy_slot"), r.get("sell_slot"),
          (r.get("sell_slot") or 0) - (r.get("buy_slot") or 0), r["copies"], r.get("fail_copy"), pos.get("buyers_ahead"))
