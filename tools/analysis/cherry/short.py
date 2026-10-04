#!/usr/bin/env python3
"""Gated memecoin attempts: which leg came back short, was it the trigger's pool, did the trigger itself touch both
pools (a rival arb), and who else moved the short pool between the trigger and our simulation. usage: short.py <seg>"""
import json, collections, sys, re
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
def jl(f):
    for l in open(f):
        try: yield json.loads(l)
        except Exception: pass
rx = re.compile(r"sim_gated after ([\d.]+) ms: (.*?) \| legs \[(\d+), (\d+)\] predicted \[(\d+), (\d+)\]")
d = f"/root/arb-lab/runs/{sys.argv[1]}"
A = {a["attempt"]: a for a in jl(f"{d}/attempts.jsonl")}
P = {p["id"]: p for p in jl(f"{d}/opportunities.jsonl")}
G = []
for o in jl(f"{d}/outcomes.jsonl"):
    m = rx.match(o.get("settle_error") or "")
    a = A.get(o["attempt"])
    if not m or not a or a["mint"] == USDC: continue
    p = P.get(a["opp"]) or {}
    l1, l2, mid, back = map(int, m.groups()[2:])
    e1 = (l1 - mid) / mid * 1e4 if mid else 0
    e2 = ((l2 / l1) / (back / mid) - 1) * 1e4 if l1 and mid and back else 0
    short = "buy" if e1 < e2 else "sell"
    G.append({"a": a, "p": p, "t": o["t_ns"], "e1": e1, "e2": e2, "short": short,
              "short_pool": a["buy_pool"] if short == "buy" else a["sell_pool"], "trig": p.get("trigger"), "tpool": p.get("trigger_pool"),
              "t_trig": min((p.get("arrivals") or {}).values() or [o["t_ns"] - 1e9])})
pools = {g["short_pool"] for g in G} | {g["a"]["buy_pool"] for g in G} | {g["a"]["sell_pool"] for g in G}
mv = collections.defaultdict(list)
for l in open(f"{d}/moves.log"):
    s = l.split()
    if len(s) == 4 and s[2] in pools: mv[s[2]].append((int(s[3]), s[0], int(s[1])))
need = {g["trig"] for g in G}
for g in G:
    g["between"] = [x for x in mv[g["short_pool"]] if g["t_trig"] - 5e6 <= x[0] <= g["t"] and x[1] != g["trig"]]
    need |= {x[1] for x in g["between"]}
R = {}
for r in jl(f"{d}/rivals.jsonl"):
    if r.get("sig") in need: R[r["sig"]] = r
c = collections.Counter()
for g in G:
    tr = R.get(g["trig"]) or {}
    both = g["a"]["buy_pool"] in (tr.get("pools") or []) and g["a"]["sell_pool"] in (tr.get("pools") or [])
    c[("short leg is trigger pool" if g["short_pool"] == g["tpool"] else "short leg is OTHER pool")] += 1
    c[("trigger touched both pools" if both else "trigger touched one pool")] += 1
    c[("someone moved short pool before our sim" if g["between"] else "nobody moved it (in moves.log)")] += 1
print(len(G), "gated memecoin attempts"); [print("  ", k, v) for k, v in sorted(c.items())]
for g in G[:14]:
    tr = R.get(g["trig"]) or {}
    print(f'{g["a"]["buy_venue"]:>8}>{g["a"]["sell_venue"]:<8} leg1 {g["e1"]:7.0f} leg2 {g["e2"]:7.0f} bps  short={g["short"]:4} '
          f'trigpool={"short" if g["short_pool"]==g["tpool"] else "other"} trig n_pools={len(tr.get("pools") or [])} progs={[p[:6] for p in tr.get("progs") or []]} '
          f'between={[(round((x[0]-g["t_trig"])/1e6), x[1][:6], (R.get(x[1]) or {}).get("progs", ["?"])[0][:6]) for x in g["between"]][:4]} ms_to_sim={round((g["t"]-g["t_trig"])/1e6)}')
