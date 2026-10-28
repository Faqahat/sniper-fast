#!/usr/bin/env python3
"""Our engine's own records (AMS r20-r33, FRA r20-r26): copies per regular fire, which path lands fills vs failures, landing ms by path,
sell latency (exit decision -> sell landed on our feed), pre-send tries. MEASURED. Out: sniper-data/haqq_dissect/exec/t4_engine.txt"""
import json, glob, collections, statistics as st
D = "/home/moiz/sniper-data/haqq_dissect/exec"
files = sorted(glob.glob("/home/moiz/sniper-data/runs/fra/runs/dip_r2[0-6].jsonl")) + sorted(glob.glob("/home/moiz/sniper-data/runs/ams/runs/dip_ams_r2[0-7].jsonl")) + \
        ["/home/moiz/sniper-data/presend_filter/live28/dip_ams_r28.jsonl"] + sorted(glob.glob("/home/moiz/sniper-data/haqq_strat/live/dip_ams_r*.jsonl"))
out = []
def P(*a): out.append(" ".join(str(x) for x in a))
def med(x): return round(st.median(x), 1) if x else None
def q(x, p):
    x = sorted(x); return round(x[int(p * (len(x) - 1))], 1) if x else None
nvar = collections.Counter(); fire_tipsum = []
landp = collections.defaultdict(lambda: collections.Counter()); land_ms = collections.defaultdict(list); land_slots = collections.defaultdict(list)
sell_ms = collections.defaultdict(list); sell_slots = collections.defaultdict(list)
ps = collections.Counter(); ps_ms = []; psfill_ms = collections.defaultdict(list); ps_paths = collections.Counter()
for f in files:
    reg = "FRA" if "/fra/" in f else "AMS"
    exits = {}; pexits = {}
    for l in open(f):
        if '"ev":"' not in l: continue
        try: r = json.loads(l)
        except Exception: continue
        ev = r.get("ev")
        if ev == "fire":
            v = (r.get("nonce") or {}).get("variants") or []
            nvar[len(v)] += 1
            fire_tipsum.append(sum(x.get("tip", 0) for x in v))
        elif ev == "buy_land":
            p = "+".join((r.get("variant") or {}).get("paths") or ["?"])
            landp[p]["fill"] += 1
            if r.get("rx_ms_after_dump") is not None: land_ms[p].append(r["rx_ms_after_dump"])
            if r.get("slots_after_dump") is not None: land_slots[p].append(r["slots_after_dump"])
        elif ev == "close" and r.get("result") == "buy_failed":
            p = "+".join((r.get("variant") or {}).get("paths") or ["?"])
            landp[p]["fail"] += 1
        elif ev == "exit":
            exits[r["mint"]] = r
        elif ev == "sell_land":
            e = exits.pop(r.get("mint"), None)
            if e:
                sell_ms["regular"].append((r["t"] - e["t"]) / 1e6); sell_slots["regular"].append(r["slot"] - e["slot"])
        elif ev == "presend_live_exit":
            pexits[(r["mint"], r.get("pid"))] = r
        elif ev == "presend_live_sell_land":
            e = pexits.pop((r.get("mint"), r.get("pid")), None)
            if e:
                sell_ms["presend"].append((r["t"] - e["t"]) / 1e6); sell_slots["presend"].append(r["slot"] - e["slot"])
        elif ev == "presend_attempt":
            ps["attempt"] += 1; ps_paths[r.get("path")] += 1
            ps["cu_" + str(r.get("cu")) + "_" + str(r.get("cu_price")) + "_tip" + str(r.get("tip"))] += 1
        elif ev == "presend_attempt_land":
            ps["land_" + str(r.get("res"))] += 1
            if r.get("ms_send_to_first_rx") is not None: ps_ms.append(r["ms_send_to_first_rx"])
        elif ev == "presend_live_fill":
            ps["fill"] += 1
            if r.get("ms_send_to_rx") is not None: psfill_ms[r.get("client")].append(r["ms_send_to_rx"])
        elif ev == "presend_live_arm":
            ps["arm"] += 1
P("## Our regular fires (engine records AMS r20-r33, FRA r20-r26; MEASURED)")
P("variants (copies) per fire, each with its own tip, one shared durable nonce:", dict(sorted(nvar.items())))
P("sum of tips across a fire's variants, mSOL: median", med([x / 1e6 for x in fire_tipsum]), "(only the landed variant's tip is paid; failures pay none)")
P(f"{'landed variant path':28} {'fills':>5} {'fails':>5} {'fill%':>6} {'ms after dump (fills) med/p75':>30} {'slots>0 %':>9}")
for p, c in sorted(landp.items(), key=lambda x: -(x[1]["fill"] + x[1]["fail"])):
    n = c["fill"] + c["fail"]
    if n < 5: continue
    P(f"{p:28} {c['fill']:5} {c['fail']:5} {100*c['fill']/n:6.1f} {str(med(land_ms[p]))+' / '+str(q(land_ms[p],0.75)):>30} {100*sum(1 for s in land_slots[p] if s>0)/max(1,len(land_slots[p])):9.1f}")
P("")
P("## Sell latency: exit decision (engine exit event) -> our sell seen landed on our feed (feed clock, ms; slots)")
for k in sell_ms:
    x = sell_ms[k]; s = sell_slots[k]
    P(f"{k:8} n={len(x)} ms med {med(x)} p25 {q(x,0.25)} p75 {q(x,0.75)} p90 {q(x,0.9)}; same slot {100*sum(1 for v in s if v==0)/len(s):.0f}%, +1 {100*sum(1 for v in s if v==1)/len(s):.0f}%, >=2 {100*sum(1 for v in s if v>=2)/len(s):.0f}%")
P("")
P("## Pre-send tries (engine)")
P(dict(ps.most_common(20)))
P("try paths:", dict(ps_paths))
P("try send->first seen ms: med", med(ps_ms), "p75", q(ps_ms, 0.75))
P("pre-send fill send->rx ms by leader client:", {k: (len(v), med(v)) for k, v in psfill_ms.items()})
open(f"{D}/t4_engine.txt", "w").write("\n".join(out) + "\n")
print("\n".join(out))
