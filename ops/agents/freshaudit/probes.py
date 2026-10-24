#!/usr/bin/env python3
# team's probe buys (tiny real buys, often one forced send path): landing time + block position by path / leader
import sys, json, collections, statistics as st, glob, gzip
sys.path.insert(0, "/home/moiz/sniper/ops/agents/freshaudit")
from load import *
SP = "/home/moiz/sniper/ops/dip/speed"
rt = json.load(open(f"{SP}/leaders/leader_rtt_new.json"))["leaders"]
P = []
for f in ["probeA", "probeB", "probeC", "probeD", "probeE"]:
    ev = [json.loads(l) for l in open(f"{SP}/{f}.jsonl")]
    pl = {e["sig"]: e for e in ev if e["ev"] == "probe_land"}
    tm = {e.get("buy_sig"): e for e in ev if e["ev"] == "timing"}
    for e in ev:
        if e["ev"] != "probe": continue
        l = pl.get(e["buy_sig"], {}); t = tm.get(e["buy_sig"], {})
        P.append(dict(set=f, route=e["route"], paths=[w["path"] for w in e["writes"]], client=e["client"], leader=e["leader"], rtt=rt.get(e["leader"], {}).get("rtt"),
                      dump_sig=e["dump_sig"], buy_sig=e["buy_sig"], mint=e["mint"], dslot_log=(l.get("slot") or 0) - e["slot"], ms_feed=l.get("ms_after_dump_feed"),
                      f2s=t.get("fire_to_seen_ms"), react=t.get("reaction_ms"), t=e["t_fire"] / 1e9, dump_slot=e["slot"], dump_idx=e["idx"], tips=e["tips"]))
t0 = int(min(p["t"] for p in P)) - 400; t1 = int(max(p["t"] for p in P)) + 400
L = load("r3", t0, t1, kinds=("D", "F"), aggs=True)
F = L["F"]; SL = L["SL"]
D = {r["sig"]: r for r in L["D"]}
M = by_mint(F)
for p in P:
    tx = F.get(p["buy_sig"]); d = D.get(p["dump_sig"])
    p["chain"] = None
    if tx and d:
        p["chain"] = dict(ds=tx["s"] - d["s"], di=d["i"], oi=tx["i"], err=tx["err"], bs=SL.get(d["s"], [None])[0], tips=tx["tips"], cup=tx["cup"])
        # buys ahead between dump and probe
        seq = [r for r in M.get(p["mint"], []) if (d["s"], d["i"]) < (r["s"], r["i"]) < (tx["s"], tx["i"])]
        p["chain"]["ahead_ok_buys"] = sum(1 for r in seq if not r["err"] and any(e[0] == p["mint"] and e[1] == 1 for e in r["ev"]))
json.dump(P, open("/home/moiz/sniper/ops/agents/freshaudit/out/probes.json", "w"))
print("probes", len(P), "with chain position", sum(1 for p in P if p["chain"]))
def cat(p):
    if p["route"].startswith("forced:"): return p["route"]
    return "multi:" + "+".join(sorted(p["paths"]))
G = collections.defaultdict(list)
for p in P: G[cat(p)].append(p)
print(f"{'path':<34} {'n':>3} {'same-slot':>9} {'f2s med(ss)':>11} {'ms_feed med(ss)':>15} {'dIdx med(ss)':>12} | local-leader(rtt<1ms): n ss f2s-med dIdx-med")
for k, v in sorted(G.items()):
    ss = [p for p in v if p["chain"] and p["chain"]["ds"] == 0]
    f2s = [p["f2s"] for p in ss if p["f2s"]]; msf = [p["ms_feed"] for p in ss if p["ms_feed"]]
    didx = [p["chain"]["oi"] - p["chain"]["di"] for p in ss]
    loc = [p for p in v if p["rtt"] is not None and p["rtt"] < 1 and p["chain"]]
    lss = [p for p in loc if p["chain"]["ds"] == 0]
    lf = [p["f2s"] or p["ms_feed"] for p in lss if (p["f2s"] or p["ms_feed"])]
    ld = [p["chain"]["oi"] - p["chain"]["di"] for p in lss]
    print(f"{k:<34} {len(v):>3} {len(ss):>4}/{sum(1 for p in v if p['chain']):<4} {st.median(f2s) if f2s else float('nan'):>11.1f} {st.median(msf) if msf else float('nan'):>15.1f} {st.median(didx) if didx else float('nan'):>12.0f} | {len(loc):>2} {len(lss):>2} {st.median(lf) if lf else float('nan'):6.1f} {st.median(ld) if ld else float('nan'):6.0f}")
print()
for p in sorted(P, key=lambda p: (cat(p), p["rtt"] or 999)):
    if p["route"].startswith("forced"):
        c = p["chain"] or {}
        print(f"{cat(p):<22} {p['client']:<18} rtt={p['rtt']} ds={c.get('ds')} dIdx={(c.get('oi',0)-c.get('di',0)) if c else None} bs={c.get('bs')} f2s={p['f2s'] and round(p['f2s'],1)} ms_feed={p['ms_feed'] and round(p['ms_feed'],1)} ahead={c.get('ahead_ok_buys')} err={c.get('err')} tips={c.get('tips')} cup={c.get('cup')}")
