# join focus-wallet lots (phaseA, with trigger) + raw tx rows (relays, cup, tips) + race rank + leader of the slots
import json, gzip, collections
B = "/home/moiz/sniper/ops/agents/topearners/work/"
LB = json.load(open("/home/moiz/sniper/ops/overnight/dipshadow/leaders_book.json"))
LEAD = LB["leaders"]; NODES = LB["nodes"]
tx = {}
for line in gzip.open(B + "txrows.jsonl.gz", "rt"):
    x = json.loads(line)
    if x["kind"] == "buy" and x["ok"]: tx[x["sig"]] = x
# race rank: (dump sig) -> ordered buyer list
rank = {}
for line in gzip.open(B + "races.jsonl.gz", "rt"):
    r = json.loads(line)
    for k, b in enumerate(r["buys"]):
        rank[(r["sig"], b[4])] = (k, len(r["buys"]))
out = gzip.open(B + "buys.jsonl.gz", "wt")
n = 0
for line in gzip.open(B + "lots.jsonl.gz", "rt"):
    L = json.loads(line)
    x = tx.get(L["sig"])
    row = dict(w=L["w"], run=L["run"], m=L["m"], s=L["s"], i=L["i"], bt=L["bt"], sig=L["sig"], sol=L["sol"], cost=L["cost"], pnl=L.get("pnl"), pnl_mtm=L.get("pnl_mtm"),
               nsell=len(L["sells"]), hold=(L["sells"][-1][0] - L["s"]) if L["sells"] else None, cup=L["cup"], cul=L["cul"], fee=L["fee"], tips=L["tips"])
    if x: row.update(relays=sorted(set(t[0] for t in x["tips"])), tipl=[t[1] for t in x["tips"]], progs=x["progs"])
    t = L.get("trig")
    if t:
        row.update(ts=t[0], ti=t[1], tsig=t[2], tsol=t[3], tuser=t[4], ds=L["s"] - t[0], di=(L["i"] - t[1]) if L["s"] == t[0] else None)
        rk = rank.get((t[2], L["sig"]))
        if rk: row.update(rank=rk[0], nbuy=rk[1])
        ld = LEAD.get(str(t[0])); row["lead0"] = ld; row["cls0"] = NODES.get(ld, {}).get("client") if ld else None
        ld1 = LEAD.get(str(t[0] + 1)); row["cls1"] = NODES.get(ld1, {}).get("client") if ld1 else None
        row["same_leader_next"] = (ld == ld1) if ld and ld1 else None
    ldb = LEAD.get(str(L["s"])); row["clsb"] = NODES.get(ldb, {}).get("client") if ldb else None; row["leadb"] = ldb
    out.write(json.dumps(row, separators=(",", ":")) + "\n"); n += 1
out.close(); print("rows", n)
