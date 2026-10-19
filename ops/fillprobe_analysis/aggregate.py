import json, statistics
out=json.load(open("results.json"))
rows=[]
for r in out:
    p=r["probe"]; our=r["our"]; fl=r["floor"]
    ratio=our["avg"]/fl
    # in-landed-slot rank: successful buys in buy_slot with idx < our idx, +1
    our_slot=p["buy_slot"]; our_idx=our["idx"]
    before_in_slot=sum(1 for s in r["seq"] if s["slot"]==our_slot and s["idx"]<our_idx)
    rows.append({
      "n":p["n"],"mint":p["mint"][:8],"dev":p["dev"],
      "create":p["create"],"buy":p["buy_slot"],"land":p["buy_slot"]-p["create"],
      "floor":fl,"fill":our["avg"],"ratio":ratio,
      "exec_marg_ratio":our["marg_pre"]/fl,
      "seq_rank":r["rank"],"buys_before":r["buys_before_us"],
      "inslot_rank":before_in_slot+1,"inslot_before":before_in_slot,
      "cs_create":r["buyers_by_slot"].get(str(p["create"]), r["buyers_by_slot"].get(p["create"])),
    })
ratios=[x["ratio"] for x in rows]
print(f"{'P':>2} {'mint':8} {'dev':>4} {'land':>4} {'floor(lam/tok)':>14} {'fill':>12} {'ratio':>6} {'seqRank':>7} {'before':>6} {'inslotRank':>10}")
for x in rows:
    print(f"{x['n']:>2} {x['mint']:8} {x['dev']:>4} c+{x['land']:<2} {x['floor']:>14.4e} {x['fill']:>12.4e} {x['ratio']:>6.3f} {x['seq_rank']:>7} {x['buys_before']:>6} {x['inslot_rank']:>10}")
print()
print("fill_ratio  median = %.4f  mean = %.4f  min=%.3f max=%.3f"%(statistics.median(ratios),statistics.mean(ratios),min(ratios),max(ratios)))
em=[x['exec_marg_ratio'] for x in rows]
print("exec_marg/floor median = %.4f mean=%.4f"%(statistics.median(em),statistics.mean(em)))
bb=[x['buys_before'] for x in rows]
print("buys_before_us (successful): ",bb,"median",statistics.median(bb))
isr=[x['inslot_rank'] for x in rows]
print("in-landed-slot rank:",isr,"median",statistics.median(isr))
json.dump(rows,open("rows.json","w"))
