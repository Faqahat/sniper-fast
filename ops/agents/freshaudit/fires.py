#!/usr/bin/env python3
# build one row per fire from our live run logs (dip_r1..r5.jsonl) -> out/fires.json
import json, glob, os, datetime, collections
D = "/home/moiz/sniper/ops/dip/speed"
rows = []
for n in range(1, 6):
    f = f"{D}/dip_r{n}.jsonl"
    ev = [json.loads(l) for l in open(f)]
    start = ev[0]
    fires = {}; order = []
    picks = {}
    for e in ev:
        k = e.get("ev")
        if k == "pick": picks[e["sig"]] = e
        if k == "fire":
            fires[e["buy_sig"]] = dict(run=n, fire=e, pick=picks.get(e["dump_sig"])); order.append(e["buy_sig"])
    for e in ev:
        k = e.get("ev"); bs = e.get("buy_sig") or e.get("sig")
        if k == "close" and e["buy_sig"] in fires: fires[e["buy_sig"]]["close"] = e
        elif k == "timing" and e.get("buy_sig") in fires: fires[e["buy_sig"]]["timing"] = e
        elif k == "land_poll" and e["sig"] in fires: fires[e["sig"]]["poll"] = e
        elif k == "buy_land" and e["sig"] in fires: fires[e["sig"]]["land"] = e
        elif k == "buy_failed" and e["sig"] in fires: fires[e["sig"]]["failed"] = e
    for bs in order:
        x = fires[bs]; fe = x["fire"]; cl = x.get("close", {}); tm = x.get("timing", {}); po = x.get("poll", {})
        t = fe["t_dump_rx"] / 1e9
        rows.append(dict(run=n, pkt=(datetime.datetime.fromtimestamp(t, datetime.UTC) + datetime.timedelta(hours=5)).strftime("%m-%d %H:%M:%S"), t=t,
                         mint=fe["mint"], buy_sig=bs, dump_sig=fe["dump_sig"], dump_slot=fe["slot"], deadline=fe.get("deadline"),
                         leader=fe.get("leader"), client=fe.get("client"), route=fe.get("route"), tips=fe.get("tips"), spend=fe.get("spend"),
                         paths=[w["path"] for w in fe.get("writes", [])], wst=[w["st"] for w in fe.get("writes", [])],
                         decision_us=fe.get("decision_us"), lat_us=fe.get("lat_us"), dev=fe.get("dev"),
                         score=(x["pick"] or {}).get("score"), age=(x["pick"] or {}).get("age"), dump_idx=(x["pick"] or {}).get("idx"),
                         result=cl.get("result"), err=json.dumps(cl.get("err")) if cl.get("err") else None, curve_pnl=cl.get("curve_pnl"),
                         land=cl.get("land") or ([po.get("land_slot")] if po else None), exit_why=cl.get("exit_why"), held_s=cl.get("held_s"),
                         sell_land=cl.get("sell_land"), exit_slot=cl.get("exit_slot"),
                         reaction_ms=tm.get("reaction_ms"), fire_to_seen_ms=tm.get("fire_to_seen_ms"), exec_lag_ms=tm.get("exec_lag_ms"),
                         dump_poh=tm.get("dump_poh"), buy_poh=tm.get("buy_poh"), land_ms_poh=tm.get("land_ms_poh"), slot_ms=tm.get("slot_ms"),
                         dump_first_feed=tm.get("dump_first_feed"), buy_first_feed=tm.get("buy_first_feed"),
                         poll_slot=po.get("land_slot"), poll_err=json.dumps(po.get("err")) if po.get("err") else None))
json.dump(rows, open("/home/moiz/sniper/ops/agents/freshaudit/out/fires.json", "w"), indent=0)
print(len(rows))
c = collections.Counter((r["result"], r["err"]) for r in rows); print(c)
for r in rows:
    print(r["run"], r["pkt"], r["mint"][:6], f"sc={r['score']:.2f}" if r["score"] else "", r["client"], r["route"], ",".join(r["paths"]), r["tips"], r["spend"],
          r["result"], (r["err"] or "")[:40], "dslot", r["dump_slot"], "didx", r["dump_idx"], "land", r["land"], "poll", r["poll_slot"],
          "pnl", r["curve_pnl"], r["exit_why"], "react", r["reaction_ms"] and round(r["reaction_ms"], 1), "f2s", r["fire_to_seen_ms"] and round(r["fire_to_seen_ms"], 1),
          "poh", r["dump_poh"], r["buy_poh"])
