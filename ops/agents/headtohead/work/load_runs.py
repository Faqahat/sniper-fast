#!/usr/bin/env python3
# read-only loader for our run records -> work/runs.json (dumps, fires, outcomes per fire)
import json, collections
SP = "/home/moiz/sniper/ops/dip/speed"
dumps = {}; fires = []
for r in range(1, 6):
    rows = []
    for l in open(f"{SP}/dip_r{r}.jsonl"):
        try: rows.append(json.loads(l))
        except Exception: pass
    bysig = {}
    for d in rows:
        if d["ev"] == "dump":
            x = dict(run=r, sig=d["sig"], mint=d["mint"], slot=d["slot"], idx=d["idx"], sell=d["sell"], vsol=d["vsol"], vtok=d["vtok"],
                     score=d["score"], passed=d["pass"], age=d["age"], drop=d["drop_pct"], t=d["t"], launch_ok=d.get("launch_ok"))
            dumps.setdefault(d["sig"], x)
    # fires and their outcomes (match by buy sig)
    out = {}
    for d in rows:
        if d["ev"] in ("buy_land", "buy_failed", "land_poll", "close", "timing", "exit", "sell_land"):
            s = d.get("sig") or d.get("buy_sig")
            if d["ev"] in ("exit", "sell_land"): continue
            out.setdefault(s, {})[d["ev"]] = d
    picks = {d["sig"]: d for d in rows if d["ev"] == "pick"}
    for d in rows:
        if d["ev"] != "fire": continue
        o = out.get(d["buy_sig"], {})
        p = picks.get(d["dump_sig"], {})
        f = dict(run=r, mint=d["mint"], dump_sig=d["dump_sig"], buy_sig=d["buy_sig"], slot=d["slot"], deadline=d.get("deadline"), leader=d["leader"],
                 client=d.get("client"), route=d["route"], tips=d["tips"], spend=d["spend"], min_out=d["min_out"], decision_us=d.get("decision_us"),
                 lat_us=d.get("lat_us"), t_dump_rx=d.get("t_dump_rx"), t_fire=d.get("t_fire"), writes=d["writes"], score=p.get("score"),
                 paths=p.get("paths"), kind=p.get("kind"))
        if "buy_land" in o: f["land"] = dict(slot=o["buy_land"]["slot"], idx=o["buy_land"]["idx"], rx_ms=o["buy_land"]["rx_ms_after_dump"], fee=o["buy_land"]["fee"])
        if "land_poll" in o: f["poll"] = dict(ok=o["land_poll"]["ok"], land_slot=o["land_poll"].get("land_slot"), err=o["land_poll"].get("err"))
        if "timing" in o:
            t = o["timing"]; f["timing"] = {k: t.get(k) for k in ("reaction_ms", "fire_to_seen_ms", "exec_lag_ms", "land_ms_poh", "dump_poh", "buy_poh", "dump_first_feed", "buy_first_feed", "dump_first_rx", "dump_exec_rx", "buy_first_rx", "slot_ms")}
        f["result"] = o.get("close", {}).get("result")
        fires.append(f)
json.dump(dict(dumps=list(dumps.values()), fires=fires), open("/home/moiz/sniper/ops/agents/headtohead/work/runs.json", "w"))
print(len(dumps), "dumps", len(fires), "fires")
print(collections.Counter(f["result"] for f in fires))
miss = [f["dump_sig"][:8] for f in fires if f["dump_sig"] not in dumps]
print("fires whose dump not in dump list:", miss)
print("timing present:", sum(1 for f in fires if "timing" in f))
