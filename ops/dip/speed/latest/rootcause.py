#!/usr/bin/env python3
# ROOT CAUSE of our landing delay: join every fire's timeline with the chain rows. Tests:
#  A) slot boundary / leader handover: dump late in its slot or in the leader's LAST slot -> our tx spills to the next slot / next leader
#  B) our tx shape: number of tip transfers (= hot write-locked tip accounts), CU price, CU limit
#  C) rivals that beat us: tips, CU price, CU limit, pre-sends (failed attempts by the same signer on the same token in the 5 slots before)
import json, collections, statistics, glob
T = json.load(open("latest/timeline.json")); C = json.load(open("latest/chain_rows.json"))
TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
OURS = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
dumpsig = {}
for fn in glob.glob("dip_r*.jsonl") + glob.glob("dip_ams_r*.jsonl") + glob.glob("latest/*.jsonl"):
    for l in open(fn):
        try: r = json.loads(l)
        except Exception: continue
        if r.get("ev") == "fire": dumpsig[r["buy_sig"]] = r.get("dump_sig")
med = lambda v: statistics.median(v) if v else float("nan")
rows = []
for r in T:
    cr = {x["sig"]: x for x in C.get(r["mint"], [])}
    me = cr.get(r["sig"]); dp = cr.get(dumpsig.get(r["sig"]))
    if not me or not dp or r["fire_to_seen"] is None: continue
    size = max([x["i"] for x in C[r["mint"]] if x["s"] == dp["s"]] + [SS.get(dp["s"], 0)]) + 1
    tips = me.get("tips") or []
    allrows = sorted(C[r["mint"]], key=lambda x: (x["s"], x["i"]))
    winners = [x for x in allrows if (dp["s"], dp["i"]) < (x["s"], x["i"]) < (me["s"], me["i"]) and x["signer"] not in OURS and x["err"] in ("None", "null")]
    pre = {}
    for w in winners:
        pre[w["sig"]] = sum(1 for x in allrows if x["signer"] == w["signer"] and x["err"] not in ("None", "null") and dp["s"] - 5 <= x["s"] <= dp["s"] and (x["s"], x["i"]) < (dp["s"], dp["i"]))
    rows.append(dict(region=r["region"], client=r["client"], fts=r["fire_to_seen"], ours_ms=r["ours_ms"], first_rival=r["first_rival_ms"], result=r["result"],
                     dump_pos=dp["i"] / size, leader_slot=dp["s"] % 4, slots_late=me["s"] - dp["s"], our_idx_after=(me["i"] - dp["i"]) if me["s"] == dp["s"] else None,
                     n_tips=len(tips), tip_svc="+".join(sorted({TIP.get(a, "?") for a, _ in tips})), cup=int(me.get("cup") or 0), cul=int(me.get("cul") or 0),
                     winners=[dict(signer=w["signer"][:8], tips=len(w.get("tips") or []), cup=int(w.get("cup") or 0), cul=int(w.get("cul") or 0), pre=pre[w["sig"]],
                                   same_slot=w["s"] == dp["s"], gap_idx=(w["i"] - dp["i"]) if w["s"] == dp["s"] else None, ixn=w["ixn"][:3]) for w in winners if w["ixn"]]))
json.dump(rows, open("latest/rootcause.json", "w"))
print(f"fires joined with chain rows: {len(rows)}")
print("\n== A) does the slot boundary / leader handover explain the slow ones?")
for lab, f in (("same slot as the dump", lambda x: x["slots_late"] == 0), ("1 slot later", lambda x: x["slots_late"] == 1), ("2+ slots later", lambda x: x["slots_late"] >= 2)):
    v = [x for x in rows if f(x)]; print(f"   our tx {lab:22s}: {len(v):3d} fires ({len(v)/len(rows):.0%}) | fire->seen median {med([x['fts'] for x in v]):6.1f} ms")
for a, b in ((0, .25), (.25, .5), (.5, .75), (.75, 1.01)):
    v = [x for x in rows if a <= x["dump_pos"] < b]
    print(f"   dump at {a:.0%}-{min(b,1):.0%} of its block: n={len(v):3d} | our tx in a LATER slot {sum(1 for x in v if x['slots_late'] > 0)/max(len(v),1):4.0%} | fire->seen median {med([x['fts'] for x in v]):6.1f}")
for s in range(4):
    v = [x for x in rows if x["leader_slot"] == s]
    print(f"   dump in the leader's slot #{s+1} of 4: n={len(v):3d} | our tx later slot {sum(1 for x in v if x['slots_late'] > 0)/max(len(v),1):4.0%} | fire->seen median {med([x['fts'] for x in v]):6.1f}")
print("\n== B) our tx shape vs delay (same-slot landings only, to remove the slot-boundary effect)")
same = [x for x in rows if x["slots_late"] == 0]
for k in sorted({x["n_tips"] for x in same}):
    v = [x for x in same if x["n_tips"] == k]; print(f"   {k} tip transfers in our tx: n={len(v):3d} | fire->seen median {med([x['fts'] for x in v]):5.1f} | txs between dump and us median {med([x['our_idx_after'] for x in v]):5.0f}")
print("   by leader client (same slot):", {c: (len(v), round(med([x['fts'] for x in v]), 1)) for c in sorted({x['client'] for x in same}) for v in [[x for x in same if x['client'] == c]]})
print("\n== C) the rivals that landed between the dump and us")
W = [w for x in rows for w in x["winners"]]
print(f"   rival buys ahead of us: {len(W)} | same slot as the dump {sum(w['same_slot'] for w in W)/max(len(W),1):.0%}")
print(f"   their tip transfers: {collections.Counter(w['tips'] for w in W).most_common()} | ours: {collections.Counter(x['n_tips'] for x in rows).most_common()}")
print(f"   their CU price median {med([w['cup'] for w in W]):,.0f} vs ours {med([x['cup'] for x in rows]):,.0f} | CU limit {med([w['cul'] for w in W]):,.0f} vs ours {med([x['cul'] for x in rows]):,.0f}")
print(f"   rivals with failed attempts on the same token in the 5 slots before the dump (pre-senders): {sum(1 for w in W if w['pre'] > 0)/max(len(W),1):.0%}")
g = [w["gap_idx"] for w in W if w["gap_idx"] is not None]
print(f"   rivals in the dump's slot: position after the dump median {med(g):.0f} txs | within 10 txs: {sum(1 for x in g if x <= 10)/max(len(g),1):.0%}")
ours_g = [x["our_idx_after"] for x in rows if x["our_idx_after"] is not None]
print(f"   ours in the dump's slot: position after the dump median {med(ours_g):.0f} txs")
