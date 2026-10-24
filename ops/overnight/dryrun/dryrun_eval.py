#!/usr/bin/env python3
# DRY RUN evaluator (read-only, no money, no sends): the frozen strategies on every launch our shadow engine watched since
# the test window start. Simulated buy at our real place in line (35/45/60/75 ms), simulated sells, exact curve replay of
# everyone's real trades, costs as frozen. Deployer lists are walk-forward (only attempts before each launch).
import sys, os, json, gzip, time, collections, statistics, datetime
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
HERE = "/home/moiz/sniper/ops/overnight/dryrun"
FZ = json.load(open(os.path.join(HERE, "frozen.json")))
T0 = datetime.datetime(2026, 10, 23, 0, 35, tzinfo=datetime.timezone.utc).timestamp()
NOW = time.time(); T1 = NOW - 300
L = rp.load_launches(); O = rp.load_obs(); A = json.load(open(os.environ.get("ATTEMPTS_OUT", "/home/moiz/sniper/ops/overnight/core/attempts.json")))
DC = "/home/moiz/sniper/ops/snipers/devcheck"
# attempt events (time, wallet, deployer): ledger owner-RPC window + collector
ev = []
for w in ("9Sh2fd", "DGmspi"):
    for f in (f"devs_{w}.json", f"att_{w}.json"):
        p = os.path.join(DC, f)
        if os.path.exists(p):
            for m, v in json.load(open(p)).items():
                if v.get("signer") and v.get("bt"): ev.append((v["bt"], w, v["signer"]))
for m, v in A.items():
    c = L.get(m)
    if c and c.get("bt"):
        for w in v: ev.append((c["bt"], w, c["user"]))
lev = sorted((c["bt"], c["user"]) for c in L.values() if c.get("bt"))
AHW = json.load(open(os.path.join(HERE, "attempts_ahw_dry.json"))) if os.path.exists(os.path.join(HERE, "attempts_ahw_dry.json")) else {}
ahw_ev = sorted((L[m]["bt"], L[m]["user"]) for m in AHW if m in L and L[m].get("bt"))
T_S5 = datetime.datetime(2026, 10, 23, 1, 35, tzinfo=datetime.timezone.utc).timestamp()
def ahw_ok(d, t):
    a = sum(1 for bt, dd in ahw_ev if dd == d and bt < t)
    n = sum(1 for bt, dd in lev if dd == d and bt < t)
    return a >= 2 and (n == 0 or a / n >= 0.10)
ev.sort()
T_S3 = datetime.datetime(2026, 10, 23, 1, 10, tzinfo=datetime.timezone.utc).timestamp()
def rate_ok(d, t):
    a = sum(1 for bt, w, dd in ev if dd == d and bt < t and w in ("9Sh2fd", "DGmspi"))
    n = sum(1 for bt, dd in lev if dd == d and bt < t)
    return a >= 2 and (n == 0 or a / n >= 0.10)
R = rp.R
EXITS = [R("eos1", [(1.0, ("slot", 1))], 5), R("eos0", [(1.0, ("slot", 0))], 5), R("eos2", [(1.0, ("slot", 2))], 5),
         R("tp1.1_eos2", [(1.0, ("x", 1.1)), (1.0, ("slot", 2))], 5), R("fsell_any_c2", [(1.0, ("ev", "any_sell"))], 2),
         R("hold1s", [(1.0, ("t", 1))], 2), R("hold5s", [(1.0, ("t", 5))], 6), R("hold10s", [(1.0, ("t", 10))], 11),
         R("pD_25at_slots1_3_6_10", [(0.25, ("slot", 1)), (0.25, ("slot", 3)), (0.25, ("slot", 6)), (0.25, ("slot", 10))], 5),
         R("pI_50eos0_50hold10s", [(0.5, ("slot", 0)), (1.0, ("t", 10))], 11),
         R("twap_10pct_every2s_20s", [(0.1, ("t", 2 * k)) for k in range(1, 11)], 21),
         R("lad_33@1.3_33@1.6_trail", [(0.33, ("x", 1.3)), (0.33, ("x", 1.6)), (1.0, ("dd", 1.6, 0.2)), (1.0, ("sl", 0.75))], 300)]
NAMES = [e["name"] for e in EXITS]; LAND = FZ["landing_ms_reported"]
cand = [m for m, c in L.items() if c["run"] == "R2" and c.get("bt") and T0 <= c["bt"] <= T1 and m in O and "InitializeMayhemState" not in (c.get("ixn") or [])]
def lists_at(t):
    s2, s3 = set(), set()
    for bt, w, d in ev:
        if bt >= t: break
        s3.add(d)
        if w in ("9Sh2fd", "DGmspi"): s2.add(d)
    return s2, s3
sel = {}
for m in cand:
    c = L[m]; s2, s3 = lists_at(c["bt"]); a = A.get(m, {})
    tags = []
    if c["user"] in s2: tags.append("S1_DEVLIST_FLIP")
    if c["user"] in s3: tags.append("S2_DEVLIST3_FLIP")
    s3any = c["user"] in s2 and rate_ok(c["user"], c["bt"])
    if c["bt"] >= T_S3 and s3any: tags.append("S3_DEVLIST_RATE_FLIP")
    if s3any: tags.append("S3ANY")
    if s3any or ahw_ok(c["user"], c["bt"]): tags.append("S5ANY")
    if "9Sh2fd" in a or "DGmspi" in a: tags.append("REF_ORACLE")
    if tags: sel[m] = tags
byb = collections.defaultdict(set)
for m in sel: byb[rp.bucket(m)].add(m)
trades = []
for b, ms in byb.items():
    tra = rp.read_bucket("R2", b, ms); fa = rp.read_failed("R2", b, ms)
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; st = rp.structure(tr, c)
        ge = tr[st["g_end"] - 1] if st["g_end"] > 0 else None
        p_b = (ge["vsol"] / ge["vtok"]) if ge else None
        row = dict(mint=m, name=c.get("name"), symbol=c.get("symbol"), deployer=c["user"], create_sig=c.get("sig"), bt=c["bt"], s3any="S3ANY" in sel[m], s5any="S5ANY" in sel[m],
                   t=datetime.datetime.fromtimestamp(c["bt"], datetime.timezone.utc).strftime("%m-%d %H:%M:%S"), tags=sel[m], land={})
        for ms_ in LAND:
            idx, na = rp.place_bo2(tr, c, st, O[m]["outs"], ms_, fa.get(m, []))   # block-order placement (verifier-matched)
            if idx < 1: continue
            out = rp.sim(tr, c, st, idx, FZ["size_sol"], EXITS, fill_pen=0.015)
            if not out: continue
            pf = tr[idx - 1]["vsol"] / tr[idx - 1]["vtok"]
            s500 = rp.flip(tr, idx, rp.place_ms(tr, c, st, O[m]["outs"], 500, idx), FZ["size_sol"])
            row["land"][str(ms_)] = dict(ahead=na, after_sig=tr[idx - 1]["sig"], pnl={n: out[n]["pnl"] for n in NAMES}, grad=any(out[n]["grad"] for n in NAMES),
                                         guard_ratio=(round(pf / p_b, 5) if p_b else None), sell500=round(s500, 6))
        if row["land"]: trades.append(row)
trades.sort(key=lambda r: r["bt"])
with open(os.path.join(HERE, "dryrun_trades.jsonl"), "w") as f:
    for r in trades: f.write(json.dumps(r) + "\n")
hours = max(1e-9, (min(T1, max((r["bt"] for r in trades), default=T0)) - T0) / 3600)
lines = [f"DRY RUN progress at {datetime.datetime.fromtimestamp(NOW, datetime.timezone.utc):%Y-%m-%d %H:%M} UTC | window {datetime.datetime.fromtimestamp(T0, datetime.timezone.utc):%H:%M} -> {datetime.datetime.fromtimestamp(T1, datetime.timezone.utc):%H:%M} UTC ({hours:.2f} h) | launches watched {len(cand)}",
         f"size {FZ['size_sol']} SOL/trade, costs: pump fees + {FZ['costs']['buy_overhead_pct']}% buy overhead + {FZ['costs']['sell_fee_sol']} SOL/sell tx, fill penalty {FZ['costs']['fill_penalty_pct']}%"]
T_S4 = datetime.datetime(2026, 10, 23, 1, 10, tzinfo=datetime.timezone.utc).timestamp()
def guarded(r, ms_, G, ex):
    x = r["land"][str(ms_)]
    if x.get("guard_ratio") is None or x["guard_ratio"] > 1 + G: return -0.002, 0
    return (x["sell500"] if ex == "sell500" else x["pnl"][ex]), 1
for nm, G, key, tcl in (("S4a_GUARD_1pct", 0.01, "s3any", T_S4), ("S4b_GUARD_3pct", 0.03, "s3any", T_S4), ("S5_UNION_AHW_GUARD_1pct", 0.01, "s5any", T_S5)):
    for lab, t_from in ((f"since {datetime.datetime.fromtimestamp(tcl, datetime.timezone.utc):%H:%M} (clean test)", tcl), ("since 00:35", T0)):
        T = [r for r in trades if r["bt"] >= t_from and r.get(key)]
        lines.append(f"\n{nm} [{lab}]: {len(T)} attempts")
        for ex in ("eos1", "hold1s", "sell500"):
            cells = []
            for ms_ in LAND:
                v = [guarded(r, ms_, G, ex) for r in T if str(ms_) in r["land"]]
                cells.append(f"{ms_}ms {sum(a for a, _ in v):+7.3f} ({sum(1 for a, f in v if f and a > 0)}/{sum(f for _, f in v)} fills win)" if v else f"{ms_}ms -")
            lines.append(f"   {ex:24} " + " | ".join(cells))
for s in ("S1_DEVLIST_FLIP", "S2_DEVLIST3_FLIP", "S3_DEVLIST_RATE_FLIP", "REF_ORACLE"):
    T = [r for r in trades if s in r["tags"]]
    lines.append(f"\n{s}: {len(T)} trades")
    for ex in ("eos1", "eos0", "eos2", "tp1.1_eos2", "hold10s", "pD_25at_slots1_3_6_10", "twap_10pct_every2s_20s", "lad_33@1.3_33@1.6_trail"):
        cells = []
        for ms_ in LAND:
            v = [r["land"][str(ms_)]["pnl"][ex] for r in T if str(ms_) in r["land"]]
            cells.append(f"{ms_}ms {sum(v):+7.3f} ({sum(1 for x in v if x > 0)}/{len(v)} win)" if v else f"{ms_}ms -")
        lines.append(f"   {ex:24} " + " | ".join(cells))
open(os.path.join(HERE, "dryrun_progress.txt"), "w").write("\n".join(lines) + "\n")
with open(os.path.join(HERE, "progress_log.txt"), "a") as f: f.write("\n".join(lines[:1] + [l for l in lines if "eos1" in l or l.startswith("S") or l.startswith("\nS")]) + "\n")
print("\n".join(lines))
