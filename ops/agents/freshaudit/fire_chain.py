#!/usr/bin/env python3
# per fire: the dump tx, our buy tx (on chain), every tx on that mint between the dump and our landing (and up to dump+2)
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/agents/freshaudit")
from load import *
fires = json.load(open("/home/moiz/sniper/ops/agents/freshaudit/out/fires.json"))
t0 = int(min(f["t"] for f in fires)) - 400; t1 = int(max(f["t"] for f in fires)) + 60
L = load("r3", t0, t1)
F = L["F"]; M = by_mint(F)
for r in L["O"]: F.setdefault(r["sig"], r)
O = {r["sig"]: r for r in L["O"]}
D = {r["sig"]: r for r in L["D"]}
print("loaded", len(F), len(O), len(D))
out = []
for f in fires:
    m = f["mint"]; d = D.get(f["dump_sig"]); ob = O.get(f["buy_sig"])
    rec = dict(f)
    if d is None:
        print("NO DUMP", f["run"], m[:6], f["dump_sig"][:10]); out.append(rec); continue
    de = d["ev"][d["j"]]
    P0 = de[5] / de[6]
    rec["dump"] = dict(s=d["s"], i=d["i"], sol=de[2] / 1e9, signer=d["sg"], user=de[4], relays=relays(d), tip=tipsum(d), cup=d["cup"], vsol=de[5])
    if ob is None:
        print("NO OURS", f["run"], m[:6]); out.append(rec); continue
    rec["ours"] = dict(s=ob["s"], i=ob["i"], err=ob["err"], fee=ob["fee"], cup=ob["cup"], cul=ob["cul"], cu=ob["cu"], tips=ob["tips"], relays=relays(ob), ixn=ob["ixn"], sd=ob.get("sd"))
    seq = [r for r in M.get(m, []) if (d["s"], d["i"]) < (r["s"], r["i"]) <= (d["s"] + 2, 10**6)]
    ahead = [r for r in seq if (r["s"], r["i"]) < (ob["s"], ob["i"])]
    rows = []
    last_state = (de[5], de[6])
    for r in seq:
        e = trade_of(r, m)
        rr = dict(s=r["s"], i=r["i"], sg=r["sg"], err=r["err"], relays=relays(r), tip=tipsum(r), cup=r["cup"], cul=r["cul"], fee=r["fee"], progs=r["progs"],
                  buy=(e[1] == 1) if e else is_buy_attempt(r, m), sol=(e[2] / 1e9) if e else None, user=e[4] if e else None,
                  pr=((e[5] / e[6]) / P0) if e else None, ours=(r["sig"] == f["buy_sig"]), ixn=r["ixn"][:4])
        if (r["s"], r["i"]) < (ob["s"], ob["i"]) and e: last_state = (e[5], e[6])
        rows.append(rr)
    rec["seq"] = rows
    rec["pre_ratio"] = (last_state[0] / last_state[1]) / P0
    rec["n_ahead_buys_ok"] = sum(1 for r in rows if (r["s"], r["i"]) < (ob["s"], ob["i"]) and r["buy"] and not r["err"])
    rec["n_ahead_buys_fail"] = sum(1 for r in rows if (r["s"], r["i"]) < (ob["s"], ob["i"]) and r["buy"] and r["err"])
    rec["sol_ahead_buys"] = sum(r["sol"] or 0 for r in rows if (r["s"], r["i"]) < (ob["s"], ob["i"]) and r["buy"] and not r["err"])
    rec["sol_ahead_sells"] = sum(r["sol"] or 0 for r in rows if (r["s"], r["i"]) < (ob["s"], ob["i"]) and r["buy"] is False and not r["err"])
    out.append(rec)
json.dump(out, open("/home/moiz/sniper/ops/agents/freshaudit/out/fire_chain.json", "w"))
for r in out:
    if "ours" not in r: continue
    o = r["ours"]; d = r["dump"]
    print(f"r{r['run']} {r['pkt']} {r['mint'][:6]} {r['client']:<18} {r['route']:<16} res={r['result']:<10} dump s={d['s']} i={d['i']} sol={d['sol']:.2f} | ours s+{o['s']-d['s']} i={o['i']} err={o['err']} paid_tips={o['tips']} fee={o['fee']} | ahead ok-buys={r['n_ahead_buys_ok']} ({r['sol_ahead_buys']:.2f} SOL) fail-buys={r['n_ahead_buys_fail']} sells={r['sol_ahead_sells']:.2f} pre_ratio={r['pre_ratio']:.4f}")
    for x in r["seq"]:
        if (x["s"], x["i"]) <= (o["s"], o["i"]) or (x["s"] == o["s"] and x["buy"] and not x["err"] and x["i"] - o["i"] < 60):
            tag = "OURS" if x["ours"] else ("buy " if x["buy"] else "sell") + (" FAIL " + str(x["err"]) if x["err"] else "")
            print(f"     s+{x['s']-d['s']} i={x['i']:<4} {tag:<22} {x['sg'][:8] if x['sg'] else '?':<8} sol={x['sol'] if x['sol'] is None else round(x['sol'],3)} pr={x['pr'] and round(x['pr'],4)} relays={x['relays']} tip={x['tip']} cup={x['cup']} progs={x['progs'][:3]}")
