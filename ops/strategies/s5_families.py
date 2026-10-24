#!/usr/bin/env python3
# FAMILIES: group the carded winners by entry-trigger / exit profile in code (rules below, thresholds read off the
# winners' feature table), attach the LLM labels (s4_llm.py fetch cards), and quantify each family: wallets, realized P&L,
# P&L per trip and per SOL, size, hold, speed (tx-index distance after the trigger, same-slot share), CROWDING (how many
# wallets start a trip in the same token in the same slot), fees/tips. -> families.json, families.txt
import json, gzip, glob, collections, statistics, os
OUT = "/home/moiz/sniper-data/strategies"
F = json.load(open(f"{OUT}/trips/FIELDS.json")); X = {k: i for i, k in enumerate(F)}
C = json.load(open(f"{OUT}/cards.json"))
LAB = {}
if os.path.exists(f"{OUT}/llm/labels_cards.jsonl"):
    for l in open(f"{OUT}/llm/labels_cards.jsonl"):
        o = json.loads(l); LAB[o["id"]] = o
def P(u, k): return C[u]["P"][k]
FAM = [  # (id, name, rule)
 ("F1", "Dev-dump backrun (same block)", lambda u, a: P(u, "E:sell>=0.5 same slot before") >= 0.3 and P(u, "E:dip>=5% from 3-slot high") >= 0.5 and P(u, "E:creator sold in window") >= 0.4 and (a["hold_med"] or 0) <= 70),
 ("F2", "Big-sell dip backrun, fast exit", lambda u, a: P(u, "E:sell>=0.5 same slot before") >= 0.3 and P(u, "E:dip>=5% from 3-slot high") >= 0.5 and (a["hold_med"] or 0) <= 70),
 ("F3", "Dip buy, slower exit (15 s+)", lambda u, a: P(u, "E:sell>=0.5 same slot before") + P(u, "E:sell>=0.5 in prev 1-3 slots") >= 0.55 and P(u, "E:dip>=5% from 3-slot high") >= 0.45),
 ("F4", "Big-buy backrun scalp (sub-second)", lambda u, a: P(u, "E:buy>=0.5 same slot before") >= 0.5 and P(u, "E:prev trade = BUY same slot") >= 0.7 and (a["hold_med"] or 99) <= 12),
 ("F5", "Early-launch momentum (first 5 s)", lambda u, a: P(u, "E:token age <=25 slots (5 s)") >= 0.45 and P(u, "E:price +10% in last 10 slots") >= 0.45),
 ("F6", "Momentum entry + ladder exit", lambda u, a: (P(u, "E:buy>=0.5 same slot before") >= 0.45 or P(u, "E:net flow >=+1 SOL (3 slots)") >= 0.6) and P(u, "X:>=3 sells (ladder)") >= 0.5),
 ("F7", "Quiet-token / ATH breakout swing", lambda u, a: P(u, "E:quiet >=20 slots before") >= 0.25),
 ("F8", "Follow-the-buy, scale-in swing", lambda u, a: P(u, "X:scaled in (>=2 buys)") >= 0.4 and (a["hold_med"] or 0) >= 60),
 ("F9", "Active-token scalper, 10-60 s holds", lambda u, a: a["n_clean"] >= 300 and 20 <= (a["hold_med"] or 0) <= 300),
 ("F10", "Late swing / other", lambda u, a: True),
]
def assign(u):
    a = C[u]["a"]
    for fid, name, rule in FAM:
        if rule(u, a): return fid
fam_of = {u: assign(u) for u in C}
# ---------------------------------------------------------------- crowding + speed from all trips
print("loading trips...", flush=True)
starts = collections.Counter(); rows = collections.defaultdict(list)
for f in sorted(glob.glob(f"{OUT}/trips/*.jsonl.gz")):
    for l in gzip.open(f, "rt"):
        r = json.loads(l)
        starts[(r[1], r[X["s0"]])] += 1
        if r[0] in fam_of and not (r[X["cslot"]] or r[X["ins"]] or r[X["st"]] == "G"): rows[r[0]].append(r)
res = {}
for fid, name, _ in FAM:
    us = [u for u in C if fam_of[u] == fid]
    if not us: continue
    rs = [r for u in us for r in rows[u]]
    n = len(rs); pnl = sum(r[X["pnl"]] for r in rs); vol = sum(r[X["spent"]] for r in rs)
    hold = [r[X["hold"]] for r in rs if r[X["st"]] == "C" and r[X["hold"]] is not None and r[X["hold"]] >= 0]
    crowd = [starts[(r[1], r[X["s0"]])] for r in rs]
    trig_s = [r[X["bs_di"]] for r in rs if r[X["bs_gap"]] == 0 and r[X["bs_sol"]] >= 0.5]
    trig_b = [r[X["bb_di"]] for r in rs if r[X["bb_gap"]] == 0 and r[X["bb_sol"]] >= 0.5]
    same = sum(1 for r in rs if (r[X["bs_gap"]] == 0 and r[X["bs_sol"]] >= 0.5) or (r[X["bb_gap"]] == 0 and r[X["bb_sol"]] >= 0.5)) / max(n, 1)
    tips = [r[X["tip0"]] or 0 for r in rs]
    # same family wallets entering the same token in the same slot (shared triggers)
    fam_starts = collections.Counter((r[1], r[X["s0"]]) for r in rs)
    shared = sum(1 for r in rs if fam_starts[(r[1], r[X["s0"]])] >= 2) / max(n, 1)
    per_w = sorted(((u, C[u]["a"]["pnl"], C[u]["a"]["n_clean"]) for u in us), key=lambda x: -x[1])
    labs = [LAB[u[:60]] for u in us if u[:60] in LAB]
    res[fid] = dict(name=name, wallets=len(us), trips=n, pnl=round(pnl, 2), pnl_R2=round(sum(C[u]["a"]["pnl_R2"] for u in us), 2), pnl_R3=round(sum(C[u]["a"]["pnl_R3"] for u in us), 2),
                    per_trip=round(pnl / max(n, 1), 4), edge=round(pnl / max(vol, 1e-9), 4), vol=round(vol, 1),
                    size_med=round(statistics.median(r[X["spent"]] for r in rs), 3), hold_med_slots=statistics.median(hold) if hold else None,
                    hold_med_s=round(statistics.median(hold) * 0.212, 1) if hold else None,
                    win=round(sum(1 for r in rs if r[X["pnl"]] > 0) / max(n, 1), 3),
                    same_slot_trigger=round(same, 3), idx_after_sell_med=statistics.median(trig_s) if trig_s else None, idx_after_buy_med=statistics.median(trig_b) if trig_b else None,
                    crowd_med=statistics.median(crowd), crowd_p90=sorted(crowd)[int(0.9 * len(crowd))] if crowd else None, shared_trigger=round(shared, 3),
                    tip_share=round(sum(1 for t in tips if t > 0) / max(n, 1), 3), tip_med=statistics.median([t for t in tips if t > 0] or [0]),
                    age_med=statistics.median(r[X["age"]] for r in rs),
                    top=[(u[:8], round(p, 1), k) for u, p, k in per_w[:8]], members=[u for u, _, _ in per_w],
                    llm_families=collections.Counter(o.get("family", "?") for o in labs).most_common(6),
                    llm_info=collections.Counter(o.get("info_source", "?") for o in labs).most_common(4),
                    llm_speed=collections.Counter(o.get("speed", "?") for o in labs).most_common(4),
                    llm_dip=sum(1 for o in labs if o.get("dip_backrun")), llm_n=len(labs))
json.dump(dict(fam_of=fam_of, fams=res), open(f"{OUT}/families.json", "w"), indent=1)
with open(f"{OUT}/families.txt", "w") as f:
    for fid, v in sorted(res.items(), key=lambda kv: -kv[1]["pnl"]):
        f.write(f"\n{fid} {v['name']}: {v['wallets']} wallets, {v['trips']} trips, P&L {v['pnl']:+.1f} SOL (day1 {v['pnl_R2']:+.1f}, day2 {v['pnl_R3']:+.1f}),"
                f" {v['per_trip']:+.4f}/trip, {v['edge']:+.2%}/SOL, win {v['win']:.0%}, size {v['size_med']}, hold {v['hold_med_slots']} slots ({v['hold_med_s']} s), age {v['age_med']} slots\n")
        f.write(f"   speed: same-slot trigger {v['same_slot_trigger']:.0%}, tx-index after sell {v['idx_after_sell_med']}, after buy {v['idx_after_buy_med']}; tips on {v['tip_share']:.0%} (median {v['tip_med']})\n")
        f.write(f"   crowding: trip starts in same token+slot median {v['crowd_med']} p90 {v['crowd_p90']}; entries shared with another family wallet {v['shared_trigger']:.0%}\n")
        f.write(f"   top: {v['top']}\n   LLM: {v['llm_families']} | {v['llm_info']} | {v['llm_speed']} | dip_backrun {v['llm_dip']}/{v['llm_n']}\n")
print(open(f"{OUT}/families.txt").read())
