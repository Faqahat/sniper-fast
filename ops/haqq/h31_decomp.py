#!/usr/bin/env python3
# H2H step 2 (read-only, local): decomposition of the gap between haqq and us on the SAME dumps (h2h_fires.json) and in the same hours.
import sys, json, pickle, zlib, collections, numpy as np, glob
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H
R = json.load(open(f"{H.OUT}/h2h_fires.json")); lots = json.load(open(f"{H.OUT}/lots.json"))
SS = {}
for run in ("R1", "R2", "R3", "R4"):
    for k, v in json.load(open(f"{H.OUT}/slotmax_{run}.json")).items(): SS[int(k)] = max(SS.get(int(k), 0), v + 1)
def A(s, i): return s * H.SMS + i / max(SS.get(int(s), 400), int(i) + 1) * H.SMS
WAL = {"FRA": "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "AMS": "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
q = lambda v, ps=(25, 50, 75): " / ".join(f"{x:.0f}" for x in np.percentile(v, ps)) if len(v) else "-"
fills = [r for r in R if r["status"] == "fill"]; fails = [r for r in R if r["status"] == "fail"]
print(f"== our attempts (FRA runs 9-14 + AMS runs 9-14, 10-24 16:47 -> 10-25 06:22 PKT): fires {len(R)}, fills {len(fills)}, failed {len(fails)} (codes {dict(collections.Counter(r.get('fail_code') for r in fails))}); unique dumps {len({r['dump_sig'] for r in R})}")
# ---------- 1. our landing delay, all attempts, same clock as haqq
print("\n[1] our landing delay after the dump (block-position ms), ALL attempts:")
for lab, sel in (("all attempts", R), ("fills", fills), ("failed", fails), ("FRA", [r for r in R if r["srv"] == "FRA"]), ("AMS", [r for r in R if r["srv"] == "AMS"])):
    d = [r["our_delay"] for r in sel if r.get("our_delay") is not None]
    print(f"   {lab:13s} n {len(d):3d}: p25/50/75 {q(d)} ms | same slot as dump {np.mean([r['our_same'] for r in sel if 'our_same' in r]):.0%} | price at landing vs post-dump: median {np.median([r['our_pratio'] for r in sel if r.get('our_pratio')]):.3f}, >1.05 {np.mean([r['our_pratio'] > 1.05 for r in sel if r.get('our_pratio')]):.0%}")
print("   by leader client (all attempts): " + "; ".join(f"{c} n {len(s)} {np.median([r['our_delay'] for r in s]):.0f} ms, fill {np.mean([r['status'] == 'fill' for r in s]):.0%}"
      for c, s in sorted(collections.defaultdict(list, {c: [r for r in R if r.get('client') == c and r.get('our_delay') is not None] for c in {r.get('client') for r in R}}).items()) if s))
# ---------- 2. haqq on the same dumps
print("\n[2] haqq on OUR fired dumps (its buy within 400 ms, before the next outside sell >= 1 SOL):")
for lab, sel in (("we filled", fills), ("we failed", fails)):
    c = collections.Counter(r["haqq"] for r in sel)
    hp = [r["h_pnl"] for r in sel if r.get("haqq") == "fill" and r.get("h_pnl") is not None]
    print(f"   {lab:10s} n {len(sel):3d}: haqq filled {c['fill']} ({c['fill'] / len(sel):.0%}), haqq failed {c['fail']}, haqq absent {c['none']} | haqq lot P&L there {sum(hp):+.3f} SOL (n {len(hp)}, mean {np.mean(hp) * 1000 if hp else 0:+.1f} mSOL, win {np.mean([x > 0 for x in hp]) if hp else 0:.0%})")
sh = [r for r in R if r.get("haqq") == "fill" and r.get("our_delay") is not None]
print(f"   shared dumps (haqq filled, we landed a tx): {len(sh)}; haqq landed first {np.mean([r['h_first'] for r in sh]):.0%}; haqq delay p25/50/75 {q([r['h_delay'] for r in sh])} vs ours {q([r['our_delay'] for r in sh])}")
print(f"   haqq price ratio at its fill vs post-dump: where we filled median {np.median([r['h_pratio'] for r in fills if r.get('haqq') == 'fill']):.3f}; where we failed median {np.median([r['h_pratio'] for r in fails if r.get('haqq') == 'fill']):.3f}, p90 {np.percentile([r['h_pratio'] for r in fails if r.get('haqq') == 'fill'], 90):.3f}")
# ---------- 3. who was ahead of us
print("\n[3] outside buyers that landed between the dump and our tx:")
for lab, sel in (("fills", fills), ("failed", fails)):
    n_ah = [len(r["ahead"]) for r in sel]; sol_ah = [sum(x[1] for x in r["ahead"]) for r in sel]
    wh = collections.Counter(x[0] for r in sel for x in r["ahead"])
    inst = [sum(1 for x in r["ahead"] if x[2] <= 25) for r in sel]
    print(f"   {lab:7s}: buyers ahead median {np.median(n_ah):.0f} (mean {np.mean(n_ah):.1f}), SOL ahead median {np.median(sol_ah):.2f}; none ahead {np.mean([x == 0 for x in n_ah]):.0%}; haqq ahead {np.mean([any(x[0] == 'haqq' for x in r['ahead']) for r in sel]):.0%}; "
          f"a buyer within 25 ms of the dump ahead {np.mean([x > 0 for x in inst]):.0%} | who: {dict(wh.most_common(5))}")
# ---------- helper: replay a hypothetical 0.35 SOL buy of ours at a tape position with our exit (5 slots, SL -10%) or a given exit slot
TPC = {}
def tape(m):
    b = zlib.crc32(m.encode()) % 64
    if b not in TPC: TPC.clear(); TPC[b] = pickle.load(open(f"{H.OUT}/tp/b{b:02d}.pkl", "rb"))
    return TPC[b].get(m)
BUY_TX = np.median([r["our_buy_tx"] for r in fills]); SELL_TX = np.median([r["our_sell_tx"] for r in fills if r.get("our_sell_tx")])
def sim(r, pos, guard=None, exit_slot=None, size=0.35, skip_wal=True):
    d = tape(r["mint"]); T = d["T"]; Wl = d["W"]; wal = WAL[r["srv"]]
    key = T[:, 0] * 100000 + T[:, 1]; k = int(np.searchsorted(key, pos[0] * 100000 + pos[1]))
    if k == 0: return None
    V = float(T[k - 1, 9]); Tk = float(T[k - 1, 10]); fr = (T[k - 1, 13] + T[k - 1, 14]) / 1e4
    p_post = None
    if guard is not None:
        kd = next(j for j in range(len(T)) if T[j, 0] == r["dump_s"] and T[j, 1] == r["dump_i"]); p_post = T[kd, 9] / T[kd, 10]
        if (V / Tk) / p_post > guard: return "guard"
    X = size * 1e9 / (1 + fr); qq = Tk * X / (V + X); V += X; Tk -= qq; cost = size + BUY_TX
    s_buy = pos[0]; s_exit = exit_slot if exit_slot is not None else s_buy + 5
    for j in range(k, len(T)):
        if skip_wal and Wl[T[j, 5]] == wal: continue
        if T[j, 0] >= s_exit: break
        if T[j, 6]: x = float(T[j, 7]); V, Tk = V + x, Tk - Tk * x / (V + x)
        else: tq = float(T[j, 8]); so = V * tq / (Tk + tq); V, Tk = V - so, Tk + tq
        fr = (T[j, 13] + T[j, 14]) / 1e4
        if exit_slot is None and (V * qq / (Tk + qq) * (1 - fr) / 1e9 - SELL_TX) / cost - 1 <= -0.10: break
    return (V * qq / (Tk + qq) * (1 - fr)) / 1e9 - SELL_TX - cost
# ---------- 4. P&L accounting, ours
our_fill_pnl = sum(r["our_pnl"] for r in fills if r.get("our_pnl") is not None); our_fail_cost = sum(r.get("fail_fee", 0) for r in fails)
print(f"\n[4] OUR result on chain: fills {our_fill_pnl:+.4f} SOL ({len(fills)} fills, mean {our_fill_pnl / len(fills) * 1000:+.1f} mSOL) + failed-attempt fees {-our_fail_cost:+.4f} ({len(fails)}) = {our_fill_pnl - our_fail_cost:+.4f} SOL")
print(f"   our tx cost per fill: buy {BUY_TX:.6f} + sell {SELL_TX:.6f} = {BUY_TX + SELL_TX:.6f} SOL; per failed attempt {np.median([r['fail_fee'] for r in fails]):.6f} (median); total tx costs {sum(r['our_buy_tx'] + r['our_sell_tx'] for r in fills) + our_fail_cost:.4f} SOL")
gross = sum((r["our_pnl"] + r["our_buy_tx"] + r["our_sell_tx"]) for r in fills if r.get("our_pnl") is not None)
print(f"   our fills before tx costs (curve + pump fees only): {gross:+.4f} SOL")
# ---------- 5. (b)(c) haqq on our failed vs filled dumps + what a looser guard / haqq-speed would have given us
print("\n[5] price tolerance / speed counterfactuals for OUR failed attempts (0.35 SOL, our exit: 5 slots or SL -10%; our own trades removed):")
for lab, guard in (("at our real landing spot, guard 1.05 (check)", 1.05), ("at our real landing spot, guard 1.10", 1.10), ("at our real landing spot, guard 1.17 (haqq p95)", 1.17), ("at our real landing spot, no guard", None)):
    v = [sim(r, (r["our_s"], r["our_i"]), guard=guard) for r in fails]
    ok = [x for x in v if isinstance(x, float)]
    print(f"   {lab:44s}: would fill {len(ok):3d} of {len(fails)}; P&L {sum(ok):+.3f} SOL (mean {np.mean(ok) * 1000 if ok else 0:+.1f} mSOL, win {np.mean([x > 0 for x in ok]) if ok else 0:.0%})")
hf = [r for r in fails if r.get("haqq") == "fill"]
v = [sim(r, (r["h_s"], r["h_i"]), guard=1.05) for r in hf]; ok = [x for x in v if isinstance(x, float)]
print(f"   landing where haqq landed (just before its buy), guard 1.05, on the {len(hf)} failed dumps haqq filled: fill {len(ok)}; P&L {sum(ok):+.3f} SOL (mean {np.mean(ok) * 1000 if ok else 0:+.1f} mSOL)")
for lab, sel in (("our FILLED dumps", fills), ("our FAILED dumps", fails)):
    v = []
    for r in sel:
        d = tape(r["mint"]); T = d["T"]
        kd = next(j for j in range(len(T)) if T[j, 0] == r["dump_s"] and T[j, 1] == r["dump_i"])
        if kd + 1 < len(T): v.append(sim(r, (int(T[kd + 1, 0]), int(T[kd + 1, 1])), guard=1.05))
    ok = [x for x in v if isinstance(x, float)]
    print(f"   instant landing (right after the dump), guard 1.05, {lab}: fill {len(ok)} of {len(sel)}; P&L {sum(ok):+.3f} SOL (mean {np.mean(ok) * 1000 if ok else 0:+.1f} mSOL)")
v = [sim(r, (r["our_s"], r["our_i"]), guard=None) for r in fills]; ok = [x for x in v if isinstance(x, float)]
print(f"   check, our FILLS replayed at our real spot with our rule: {sum(ok):+.3f} SOL vs real {our_fill_pnl:+.3f}")
# ---------- 6. (d) exit on dumps we both filled
both = [r for r in fills if r.get("haqq") == "fill" and r.get("h_pnl") is not None and r.get("our_pnl") is not None]
print(f"\n[6] dumps we BOTH filled: {len(both)}")
if both:
    our = sum(r["our_pnl"] for r in both); hq = sum(r["h_pnl"] for r in both)
    our_ret = np.mean([r["our_pnl"] / r["our_cost"] for r in both]); h_ret = np.mean([r["h_pnl"] / r["h_cost"] for r in both])
    print(f"   our P&L {our:+.4f} SOL (mean return {our_ret:+.1%}) | haqq {hq:+.4f} SOL (mean return {h_ret:+.1%}); haqq landed first {np.mean([r['h_first'] for r in both]):.0%}")
    oh = [sim(r, (r["our_s"], r["our_i"]), exit_slot=r["h_exit_s"]) for r in both if r.get("h_exit_s")]
    print(f"   OUR entries with HAQQ's exit slot: {sum(x for x in oh if isinstance(x, float)):+.4f} SOL (n {len(oh)})")
    ho = [sim(r, (r["h_s"], r["h_i"]), exit_slot=r["our_exit_s"], size=0.35) for r in both if r.get("our_exit_s")]
    hh = [sim(r, (r["h_s"], r["h_i"]), exit_slot=r["h_exit_s"], size=0.35) for r in both if r.get("h_exit_s")]
    print(f"   HAQQ's entry spot (0.35 SOL, our costs) with OUR exit slot: {sum(x for x in ho if isinstance(x, float)):+.4f} | with ITS exit slot: {sum(x for x in hh if isinstance(x, float)):+.4f}")
json.dump(dict(BUY_TX=BUY_TX, SELL_TX=SELL_TX), open(f"{H.OUT}/h31_costs.json", "w"))
