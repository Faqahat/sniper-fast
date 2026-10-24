#!/usr/bin/env python3
# STRATEGY CENSUS pass 2: rank wallets by REALIZED P&L on their round trips (s1_trips.py), split insiders / create-slot
# entries off, keep consistent winners (>=30 clean trips, positive on R2 AND R3, positive in most active 6-h PKT blocks).
# -> /home/moiz/sniper-data/strategies/{wallets.json, winners.json, insiders.json, sel_trips.jsonl.gz, base.json}
import json, gzip, glob, collections, statistics, os, sys
OUT = "/home/moiz/sniper-data/strategies"
F = json.load(open(f"{OUT}/trips/FIELDS.json")); X = {k: i for i, k in enumerate(F)}
NSEL = int(os.environ.get("NSEL", "300"))
PKT = 5 * 3600
def blk(bt): return (bt + PKT) // (6 * 3600)                    # 6-h PKT block id
rows = []
for f in sorted(glob.glob(f"{OUT}/trips/*.jsonl.gz")):
    for l in gzip.open(f, "rt"): rows.append(json.loads(l))
print("trips", len(rows))
W = collections.defaultdict(list)
for r in rows: W[r[0]].append(r)
print("wallets", len(W))
iP, iSt, iC, iIns, iRun, iBt, iSp, iHold, iAge = X["pnl"], X["st"], X["cslot"], X["ins"], X["run"], X["bt"], X["spent"], X["hold"], X["age"]
creators = set(); MAY = set()
for run in ("run_20261021_2207", "run_20261022_1543", "run_20261023_1426"):
    for l in open(f"/home/moiz/sniper-data/collect/{run}/launches.jsonl"):
        try:
            c = json.loads(l); creators.add(c.get("creator")); creators.add(c.get("user"))
            if "InitializeMayhemState" in (c.get("ixn") or []): MAY.add(c["mint"])
        except Exception: pass
agg = {}
for u, v in W.items():
    if len(v) < 10: continue
    ins = [r for r in v if r[iC] or r[iIns]]
    clean = [r for r in v if not (r[iC] or r[iIns]) and r[iSt] != "G"]
    a = dict(u=u, n=len(v), n_ins=len(ins), n_clean=len(clean), n_grad=sum(1 for r in v if r[iSt] == "G"),
             n_open=sum(1 for r in clean if r[iSt] == "O"),
             pnl_all=round(sum(r[iP] for r in v if r[iP] is not None), 3), pnl_ins=round(sum(r[iP] for r in ins if r[iP] is not None), 3),
             is_creator=u in creators)
    if clean:
        pn = [r[iP] for r in clean]
        a["pnl"] = round(sum(pn), 3)
        a["pnl_R2"] = round(sum(r[iP] for r in clean if r[iRun] == "R2"), 3); a["pnl_R3"] = round(sum(r[iP] for r in clean if r[iRun] == "R3"), 3)
        a["n_R2"] = sum(1 for r in clean if r[iRun] == "R2"); a["n_R3"] = len(clean) - a["n_R2"]
        B = collections.defaultdict(lambda: [0, 0.0])
        for r in clean: b = B[blk(r[iBt])]; b[0] += 1; b[1] += r[iP]
        act = {k: x for k, x in B.items() if x[0] >= 3}
        a["blk_act"] = len(act); a["blk_pos"] = sum(1 for x in act.values() if x[1] > 0)
        a["blocks"] = {str(k): [x[0], round(x[1], 3)] for k, x in sorted(B.items())}
        a["win"] = round(sum(1 for x in pn if x > 0) / len(pn), 3)
        a["spent_med"] = round(statistics.median(r[iSp] for r in clean), 4); a["vol"] = round(sum(r[iSp] for r in clean), 2)
        a["edge"] = round(a["pnl"] / max(a["vol"], 1e-9), 4)
        a["pnl_wo_top5"] = round(a["pnl"] - sum(sorted(pn)[-5:]), 3)
        hold = [r[iHold] for r in clean if r[iHold] is not None and r[iHold] >= 0]
        a["hold_med"] = statistics.median(hold) if hold else None
        a["age_med"] = statistics.median(r[iAge] for r in clean)
        a["open_share"] = round(a["n_open"] / len(clean), 3)
        a["pnl_closed"] = round(sum(r[iP] for r in clean if r[iSt] == "C"), 3)
        a["may_share"] = round(sum(1 for r in clean if r[1] in MAY) / len(clean), 3)
        a["xs_share"] = round(sum(1 for r in clean if r[X["xs"]]) / len(clean), 3)
        a["pnl_may"] = round(sum(r[iP] for r in clean if r[1] in MAY), 3)
    agg[u] = a
print("wallets n>=10", len(agg))
def cons(a):
    return (a["n_clean"] >= 30 and a.get("pnl", 0) > 0 and a.get("pnl_R2", 0) > 0 and a.get("pnl_R3", 0) > 0
            and a.get("blk_act", 0) >= 3 and a["blk_pos"] >= 0.6 * a["blk_act"] and a["open_share"] <= 0.3 and a["pnl_closed"] > 0)
win = sorted([a for a in agg.values() if cons(a) and a["n_ins"] < 0.5 * a["n"]], key=lambda a: -a["pnl"])
hold = sorted([a for a in agg.values() if a["n_clean"] >= 30 and a.get("open_share", 0) > 0.3 and a.get("pnl", 0) > 0], key=lambda a: -a["pnl"])
json.dump(hold[:100], open(f"{OUT}/holders.json", "w"))
print(f"excluded holders (open share > 30%, paper P&L): {len(hold)}; top: " + ", ".join(f"{a['u'][:8]} {a['pnl']:+.0f} open {a['open_share']:.0%} mayhem {a['may_share']:.0%}" for a in hold[:6]))
insd = sorted([a for a in agg.values() if a["n_ins"] >= 0.5 * a["n"] and a["n"] >= 30], key=lambda a: -a["pnl_all"])
n30 = [a for a in agg.values() if a["n_clean"] >= 30]
print(f"wallets with >=30 clean trips: {len(n30)}; positive: {sum(1 for a in n30 if a.get('pnl', 0) > 0)}; consistent winners: {len(win)}; insider-type (>=50% create-slot/insider trips, n>=30): {len(insd)}")
print(f"consistent winners total realized P&L {sum(a['pnl'] for a in win):+.1f} SOL; top {NSEL}: {sum(a['pnl'] for a in win[:NSEL]):+.1f}")
for name in ("HkQ7hMjy", "DYXDDrZC", "haqqiUUX", "bwamJzzt", "BwWK17cb", "ARu4n5mF", "9qz7cWBq", "4yFAz", "dKMjeGJ4"):
    hits = [a for a in agg.values() if a["u"].startswith(name)]
    for a in hits:
        rank = next((k for k, w in enumerate(win) if w["u"] == a["u"]), None)
        print(f"  {name}: n {a['n']} clean {a['n_clean']} pnl_clean {a.get('pnl')} R2 {a.get('pnl_R2')} R3 {a.get('pnl_R3')} blocks {a.get('blk_pos')}/{a.get('blk_act')} ins {a['n_ins']} -> consistent rank {rank}")
    if not hits: print(f"  {name}: <10 trips in R2+R3")
json.dump(agg, open(f"{OUT}/wallets.json", "w"))
json.dump(win, open(f"{OUT}/winners.json", "w"))
json.dump(insd[:200], open(f"{OUT}/insiders.json", "w"))
sel = {a["u"] for a in win[:NSEL]}
with gzip.open(f"{OUT}/sel_trips.jsonl.gz", "wt") as f:
    for r in rows:
        if r[0] in sel: f.write(json.dumps(r, separators=(",", ":")) + "\n")
print("\nTOP consistent winners (clean trips):")
print("  wallet    n_cl   pnl     R2      R3   blk  win  edge   size  hold_med age_med open  w/o_top5 mayhem")
for a in win[:60]:
    print(f"  {a['u'][:8]} {a['n_clean']:5d} {a['pnl']:+7.2f} {a['pnl_R2']:+7.2f} {a['pnl_R3']:+7.2f} {a['blk_pos']}/{a['blk_act']} {a['win']:4.0%} {a['edge']:+.3f} {a['spent_med']:6.3f} {str(a['hold_med']):>6} {a['age_med']:7.0f} {a['open_share']:4.0%} {a['pnl_wo_top5']:+7.2f} {a['may_share']:4.0%}")
print("\nTOP insider-type wallets (>=50% create-slot / insider trips):")
for a in insd[:15]:
    print(f"  {a['u'][:8]} n {a['n']} ins {a['n_ins']} pnl_all {a['pnl_all']:+.2f} pnl_ins {a['pnl_ins']:+.2f} creator={a['is_creator']}")
