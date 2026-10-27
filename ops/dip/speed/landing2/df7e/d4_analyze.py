#!/usr/bin/env python3
# DF7eRXHn study, pass 4 (read-only, local): entry triggers, size, exits, P&L (exact wallet SOL deltas from the raw recorder), routes, fees.
import sys, json, collections, gzip, bisect, statistics as st, datetime
sys.path.insert(0, "/home/moiz/sniper/ops/dip/speed/landing2")
import lib2
D = "/home/moiz/sniper-data/landing2/df7e"; W = "DF7eRXHnvRQ9QeVCrdfS56a7RpBD6se6mgPvzApHPNr9"
AMM = {a["sig"]: a for a in json.load(open(f"{D}/amm_exits.json"))}
R = json.load(open(f"{D}/buys.json")); SD = json.load(open(f"{D}/raw_sd.json"))
TR = collections.defaultdict(list)
for l in gzip.open(f"{D}/T_mints.jsonl.gz", "rt"):
    r = json.loads(l); TR[r[5]].append(r)
for m in TR:
    _u = {}
    for r in TR[m]: _u.setdefault((r[2], r[6], r[7]), r)
    TR[m] = sorted(_u.values(), key=lambda r: (r[0], r[1]))
KS = {m: [(r[0], r[1]) for r in v] for m, v in TR.items()}
def q(v, ps=(25, 50, 75)):
    v = sorted(x for x in v if x is not None)
    return "/".join(f"{v[min(len(v)-1, int(p/100*len(v)))]:.3g}" for p in ps) if v else "-"
def med(v):
    v = [x for x in v if x is not None]; return st.median(v) if v else None
for x in R:
    v = TR.get(x["mint"], []); ks = KS.get(x["mint"], [])
    j = bisect.bisect_left(ks, (x["s"], x["i"]))
    win = [p for p in v[:j] if x["s"] - p[0] <= 3 and p[4] != W]
    t = None
    dumps = [p for p in win if p[6] == 0 and p[7] >= 300_000_000 and 1 - (p[8] / (p[8] + p[7])) ** 2 >= 0.03]
    bigb = [p for p in win if p[6] == 1 and p[7] >= 500_000_000]
    trig = None
    if t is None and dumps:
        t = "dump backrun" + (" (token <=10 s old)" if (x.get("age_s") or 99) <= 10 else ""); trig = max(dumps, key=lambda p: p[7])
    if t is None and x.get("age_s") is not None and x["age_s"] <= 10 and x.get("created_in_window"): t = "launch (age<=10 s, no dump)"
    if t is None and bigb:
        trig = bigb[0]; k = bisect.bisect_left(ks, (trig[0], trig[1]))
        gap = trig[0] - v[k - 1][0] if k > 0 else 999
        t = "wake-up buy (quiet>=10 slots)" if gap >= 10 else "big-buy follow"
        x["gap"] = gap
    if t is None: t = "other"
    x["trig"] = t
    if trig:
        x["tms"] = round(lib2.tms(x["s"], x["i"], x["n"]) - lib2.tms(trig[0], trig[1], x["n"] if trig[0] == x["s"] else 500), 1) if trig[0] == x["s"] else None
        x["tds"] = x["s"] - trig[0]; x["tsol"] = trig[7]
        k = bisect.bisect_left(ks, (trig[0], trig[1]))
        x["ahead"] = sum(1 for p in v[k + 1:j] if p[6] == 1 and p[4] != W)
        x["trig_sig"] = trig[2]
    # exact SOL
    b = SD.get(x["sig"]); x["d_buy"] = b["d"] if b else None
    if x["ok"] and x.get("sell_sigs"):
        ds = [SD.get(s, {}).get("d") * sh if s in SD else None for s, sh in zip(x["sell_sigs"], x["sell_share"])]
        x["net"] = (x["d_buy"] + sum(ds)) if (x["d_buy"] is not None and None not in ds) else None
    elif not x["ok"]: x["net"] = x["d_buy"]
    elif x["sig"] in AMM and AMM[x["sig"]].get("net") is not None:          # graduated: exit on PumpSwap, paid in WSOL (d5_amm.py)
        a = AMM[x["sig"]]; x["net"] = a["net"]; x["hold_slots"] = a["hold_slots"]; x["hold_ms"] = a["hold_slots"] * 200.0; x["amm"] = True
    else: x["net"] = None
    x["hour"] = (datetime.datetime.fromtimestamp(x["bt"], datetime.UTC) + datetime.timedelta(hours=5)).hour if x.get("bt") else None
json.dump(R, open(f"{D}/buys2.json", "w"))
def table(key, rows, title):
    print(f"\n## {title}")
    print("| group | attempts | landed ok | failed | net SOL | net/trade mSOL | win% | trigger SOL p50 | ms after trigger p25/50/75 (same slot) | bots ahead p50 | curve SOL p50 | age s p50 | hold s p50 |")
    G = collections.defaultdict(list)
    for x in rows: G[key(x)].append(x)
    for g, v in sorted(G.items(), key=lambda kv: -len(kv[1])):
        ok = [x for x in v if x["ok"]]; fl = [x for x in v if not x["ok"]]
        net = [x["net"] for x in v if x["net"] is not None]; nok = [x["net"] for x in ok if x["net"] is not None]
        tot = sum(net) / 1e9
        print(f"| {g} | {len(v)} | {len(ok)} | {len(fl)} ({len(fl)/len(v):.0%}) | {tot:+.2f} | {1e3*tot/max(1,len(ok)):+.2f} | {sum(n>0 for n in nok)/max(1,len(nok)):.0%} | "
              f"{(med([x.get('tsol') for x in v]) or 0)/1e9:.2f} | {q([x.get('tms') for x in v])} | {med([x.get('ahead') for x in v])} | "
              f"{(med([x['vsol_before'] for x in v if x['vsol_before']]) or 30e9)/1e9-30:.1f} | {med([x.get('age_s') for x in v])} | {(med([x.get('hold_ms') for x in ok]) or 0)/1e3:.1f} |")
table(lambda x: x["trig"], R, "By trigger")
def cb(x):
    c = (x["vsol_before"] or 30e9) / 1e9 - 30
    return "curve <3" if c < 3 else "curve 3-10" if c < 10 else "curve 10-25" if c < 25 else "curve 25-50" if c < 50 else "curve >=50"
table(cb, R, "By curve size at entry (real SOL in curve)")
def ab(x):
    a = x.get("age_s")
    if a is None: return "?"
    return "age <15 s" if a < 15 else "15-60 s" if a < 60 else "1-5 min" if a < 300 else "5-30 min" if a < 1800 else ">30 min"
table(ab, R, "By token age")
table(lambda x: "first entry" if x["own_prior_buys"] == 0 else ("re-entry 1-2" if x["own_prior_buys"] <= 2 else "re-entry 3+"), R, "First entry vs re-entry on the same token")
def hb(x):
    h = x.get("hold_slots")
    if h is None: return "no sell / failed"
    if x.get("amm"): return "graduated, exit on PumpSwap"
    return "<=12 slots (~2.5 s)" if h <= 12 else "13-60 slots" if h <= 60 else "61-300" if h <= 300 else ">300 slots (>1 min)"
table(hb, [x for x in R if x["ok"]], "By hold (landed buys)")
table(lambda x: f"{x['hour']:02d}" if x["hour"] is not None else "?", R, "By hour (PKT)")
# totals
okn = [x for x in R if x["ok"]]
print("\nTOTAL net (round trips + failed fees):", sum(x["net"] for x in R if x["net"] is not None) / 1e9,
      "ok trips with net", sum(1 for x in okn if x["net"] is not None), "fail cost", sum(x["net"] for x in R if not x["ok"] and x["net"] is not None) / 1e9)
# costs per trip
bf = [x["fee"] for x in okn]; tips = [x["tip"] for x in okn]
print("buy fee p50", med(bf), "tip p50", med(tips), "buy cost (fee+tip) mean", st.mean([a + b for a, b in zip(bf, tips)]))
sf = [SD[s]["fee"] for x in okn for s in x.get("sell_sigs") or [] if s in SD]
print("sell fee p50", med(sf), "mean", st.mean(sf))
# gross curve vs fees: buy d vs 0.3
print("buy d p50", med([x["d_buy"] for x in okn]))
