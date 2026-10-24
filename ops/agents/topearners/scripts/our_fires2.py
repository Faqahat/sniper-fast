import json, collections
J = json.load(open("/home/moiz/sniper/ops/agents/topearners/work/our_join.json"))
fires, mine, races, ev = J["fires"], J["mine"], J["races"], J["ev"]
TOP = {l.strip()[:10] for l in open("/home/moiz/sniper/ops/agents/topearners/work/top10.txt") if l.strip()}
rows = []
for f in fires:
    x = mine.get(f["buy_sig"]); r = races.get(f["dump_sig"])
    tm = ev.get("timing", {}).get(f["buy_sig"], {})
    if not x: print("no chain tx", f["buy_sig"][:12], f["run"]); continue
    row = dict(run=f["run"], ok=x["ok"], ec=x["ec"], s=x["s"], i=x["i"], client=f["client"], route=f["route"], paths=[w["path"] for w in f["writes"]],
               tips=f["tips"], cup=x["cup"], cul=x["cul"], fee=x["fee"], tipacc=[t[0] for t in x["tips"]], react=tm.get("reaction_ms"), f2s=tm.get("fire_to_seen_ms"), land_ms_poh=tm.get("land_ms_poh"))
    if r:
        row.update(ds=x["s"] - r["s"], di=(x["i"] - r["i"]) if x["s"] == r["s"] else None, dump_sol=r["sol"] / 1e9)
        pd = r["vsol"] / r["vtok"]
        ahead = [b for b in r["buys"] if (b[1] + r["s"], b[2]) < (x["s"], x["i"])]
        row["n_ahead"] = len(ahead); row["sol_ahead"] = round(sum(b[6] for b in ahead) / 1e9, 3)
        row["who_ahead"] = [(b[0][:6], b[1], b[2] - r["i"] if b[1] == 0 else b[2], round(b[6] / 1e9, 2)) for b in ahead[:8]]
        row["top_ahead"] = sum(1 for b in ahead if b[0][:10] in TOP)
        if ahead:
            lb = ahead[-1]; row["px_before_us"] = round((lb[13] / lb[14]) / pd, 4)
        else: row["px_before_us"] = 1.0
        # first buyer in this race
        row["first"] = (r["buys"][0][0][:6], r["buys"][0][1], r["buys"][0][2] - r["i"] if r["buys"][0][1] == 0 else None) if r["buys"] else None
    rows.append(row)
json.dump(rows, open("/home/moiz/sniper/ops/agents/topearners/work/our_fires_rows.json", "w"))
for r in rows:
    print(f"r{r['run']} ok={int(r['ok'])} ec={r['ec']} ds={r.get('ds')} di={r.get('di')} ahead={r.get('n_ahead')} ({r.get('sol_ahead')} SOL, top={r.get('top_ahead')}) px={r.get('px_before_us')} client={r['client'][:10]} paths={','.join(p[:6] for p in r['paths'])} tipacc={r['tipacc']} react={r['react'] and round(r['react'],1)} f2s={r['f2s'] and round(r['f2s'],1)} first={r.get('first')}")
