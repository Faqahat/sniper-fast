#!/usr/bin/env python3
"""verify2 / a2: data integrity for the 238 picks (raw chunks via x1): create found, standard SOL curve, curve continuity
(every trade's pre-state = previous trade's post-state) in the first 60 s, slot coverage, collector restart window,
glued bundle vs the engine's decide-time view."""
import sys, os, json, gzip, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v2core as V

P = V.load_picks(); L = V.load_launches(P); D, O = V.load_scores(P); X = V.load_x1()
slots = {int(k): v for k, v in json.load(gzip.open(os.path.join(V.WORK, "x1_slots.json.gz"), "rt")).items()}
meta = json.load(open(os.path.join(V.WORK, "x1_meta.json")))
out = dict(per={}, notes=[])
bad_create = []; nonstd = []; cont_breaks = {}; empty_slots = {}; glued_cmp = collections.Counter(); glued_diff = []
for m in P:
    M = V.Mint(m, L[m], X.get(m, []))
    r = dict(n_units=len(M.units), n_trades=len(M.trades), create_found=M.cu is not None)
    if M.cu is None or (M.units[M.cu]["s"], M.units[M.cu]["i"]) != (L[m]["slot"], L[m]["idx"]): bad_create.append(m)
    ce = M.create_ev
    r["create_ev"] = bool(ce)
    if ce:
        r.update(vsol0=ce["vsol0"], vtok0=ce["vtok0"], rtok0=ce["rtok0"], tp=ce["token_program"])
        if ce["vsol0"] != 30_000_000_000 or ce["vtok0"] != 1_073_000_000_000_000: nonstd.append((m, ce["vsol0"], ce["vtok0"]))
    # continuity over the first 60 s (slots S..S+283)
    prev = (ce["vsol0"], ce["vtok0"]) if ce else None; br = []
    for t in M.trades:
        if t["s"] - M.S > 283: break
        pre = (t["vsol"] - t["sol"], t["vtok"] + t["tok"]) if t["buy"] else (t["vsol"] + t["sol"], t["vtok"] - t["tok"])
        if prev is not None and pre != prev: br.append(dict(s=t["s"], i=t["i"], sig=t["sig"][:10], dv=pre[0] - prev[0], dt=pre[1] - prev[1]))
        prev = (t["vsol"], t["vtok"])
    if br: cont_breaks[m] = br
    r["cont_breaks"] = len(br)
    # slot coverage S..S+45 (hold window at 75 ms + 8 s ~ S+40)
    es = [s for s in range(M.S, M.S + 46) if slots.get(s, 0) == 0]
    if es: empty_slots[m] = es
    r["empty_slots_0_45"] = len(es)
    # glued bundle: mine (chain) vs the engine's decide-time features
    d = D.get(m, {}); f = d.get("features", {})
    my_n = len(M.glued_units); my_sol = sum(t["sol"] for t in M.trades if t["u"] in M.glued_units) / 1e9
    en_n = f.get("glued_n"); en_sol = f.get("glued_sol")
    r.update(glued_n_chain=my_n, glued_sol_chain=round(my_sol, 4), glued_n_engine=en_n, glued_sol_engine=en_sol,
             glued_closed=d.get("glued_closed"), glued_unknown=d.get("glued_unknown"), dev_buy_engine=f.get("dev_buy"))
    same = (en_n == my_n) and abs((en_sol or 0) - my_sol) <= max(0.002, 0.02 * my_sol)
    glued_cmp["same" if same else "diff"] += 1
    if not same: glued_diff.append(dict(m=m, chain=(my_n, round(my_sol, 4)), engine=(en_n, en_sol), closed=d.get("glued_closed"), unk=d.get("glued_unknown")))
    # post-bundle price: chain vs engine vq_after (engine features carry P0_mc_sol = vq*1e6/T/1e9 with T = V0*T0/vq)
    if M.post_bundle and f.get("P0_mc_sol"):
        pb = M.post_bundle[0] / M.post_bundle[1]
        # engine: P0 = vq*1e6/(V0*T0/vq)/1e9 = vq^2*1e6/(V0*T0*1e9)  -> price per raw token = vq/T = vq^2/(V0*T0)
        vq = (f["P0_mc_sol"] * 1e9 * 30e9 * 1.073e15 / 1e6) ** 0.5
        pe = vq * vq / (30e9 * 1.073e15)
        r["pb_ratio_engine_over_chain"] = pe / pb
    out["per"][m] = r
rat = sorted(r["pb_ratio_engine_over_chain"] for r in out["per"].values() if "pb_ratio_engine_over_chain" in r)
print("picks", len(P), "| create unit not found / slot-idx mismatch:", len(bad_create), bad_create[:5])
print("non-standard curve (vsol0/vtok0):", len(nonstd), nonstd[:5])
print("token programs:", collections.Counter(r.get("tp") for r in out["per"].values()))
print("continuity breaks in first 60 s: picks with breaks", len(cont_breaks), "total breaks", sum(len(v) for v in cont_breaks.values()))
for m, v in list(cont_breaks.items())[:12]: print("   ", m[:10], v[:3])
print("picks with empty slots in S..S+45:", len(empty_slots), "| total empty", sum(len(v) for v in empty_slots.values()))
for m, v in list(empty_slots.items())[:10]: print("   ", m[:10], "S=", L[m]["slot"], [s - L[m]["slot"] for s in v][:12])
print("glued bundle chain vs engine:", dict(glued_cmp))
for g in glued_diff[:20]: print("   ", g)
if rat: print("engine post-bundle price / chain post-bundle price: min %.4f p50 %.4f max %.4f (n=%d)" % (rat[0], rat[len(rat) // 2], rat[-1], len(rat)))
far = [(m, round(r["pb_ratio_engine_over_chain"], 4)) for m, r in out["per"].items() if "pb_ratio_engine_over_chain" in r and abs(r["pb_ratio_engine_over_chain"] - 1) > 0.002]
print("picks where engine and chain post-bundle price differ by >0.2%:", len(far), far[:15])
# collector restart: chunks truncated, slot gap around it
tr = [x for x in meta if x["trunc"]]
print("truncated chunks:", [(x["file"], x["slot_min"], x["slot_max"]) for x in tr])
ss = sorted(slots); gaps = [(a, b) for a, b in zip(ss, ss[1:]) if b - a > 3]
print("slot gaps > 3 slots in processed range:", len(gaps), gaps[:20])
near = []
for a, b in gaps:
    for m in P:
        S = L[m]["slot"]
        if S - 60 <= b and a <= S + 60: near.append((m, S, a, b))
print("picks with a >3-slot gap within +-60 slots of create:", near)
out.update(bad_create=bad_create, nonstd=nonstd, cont_breaks=cont_breaks, empty_slots=empty_slots, glued_diff=glued_diff, gaps=gaps, near_gap=near)
json.dump(out, open(os.path.join(V.WORK, "a2_integrity.json"), "w"), indent=1)
