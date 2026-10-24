#!/usr/bin/env python3
# Task 1 (pros): what 9qz7cW / FiFawH / dKMjeG / the AKbot wallets / other top non-insider earners buy on non-SOL curves,
# how fast, how big, and how their picks' prices move vs the post-bundle price WITH THEIR OWN TRADES REMOVED (vs all other
# tradeable launches). Also: non-insider wallet PnL (open tokens valued by selling into the last curve state). -> pros.txt
import sys, os, json, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/nonsol"); sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import ns, rp, ns_table as NT
from ns_lib import load_rows, tradeable
rows = {r["m"]: r for r in load_rows()}
L, CR, TR, W = ns.load()
SL = 0.212; CK = (1, 2, 5, 10, 30, 60)
out = []
import re
BAD = re.compile(r"[A-Za-z0-9]*(nigg|fagg|retard|kike)[A-Za-z0-9]*", re.I)
def P(*a): out.append(BAD.sub("[masked]", " ".join(str(x) for x in a))); print(out[-1])
FS = json.load(open(os.path.join(NT.DATA, "fast_snipers.json"))); FAST = set(FS["sol"]) | set(FS["nonsol"])
# ---- non-insider wallet PnL on non-SOL curves
pnl = collections.defaultdict(float); byrun = collections.defaultdict(float); nl = collections.Counter(); fdt = collections.defaultdict(list); picks = collections.defaultdict(list)
opn = collections.defaultdict(float)
for m, r in rows.items():
    if r.get("mayhem") or not r.get("rate") or not r.get("ntr"): continue
    tr = NT.clean(TR.get(m, []))
    if not tr: continue
    c = L[m]; st = rp.structure(tr, c); ins = st["insiders"]; rt = r["rate"]; S = c["slot"]
    fr = ((r.get("fbps") or 95) + (r.get("cbps") or 30)) / 1e4
    acc = {}
    for t in tr:
        if t["user"] in ins: continue
        a = acc.setdefault(t["user"], [0, 0.0, 0, 0.0, None])        # tokens bought, cost, tokens sold, proceeds, first buy slot
        if t["buy"]:
            a[0] += t["tok"]; a[1] += (t["sol"] + t["feeq"] + t["cfeeq"]) * rt / 1e9
            if a[4] is None: a[4] = t["s"]
        else: a[2] += t["tok"]; a[3] += (t["sol"] - t["feeq"] - t["cfeeq"]) * rt / 1e9
    V, T = tr[-1]["vsol"], tr[-1]["vtok"]; grad = T <= NT.GRAD_VTOK
    for u, (tb, cb, ts, ps, fs) in acc.items():
        if tb == 0: continue                                       # sell-only wallets (tokens received off-curve) are not counted
        if ts > tb: ps *= tb / ts; ts = tb                          # only the part of the sells covered by its own buys
        k = tb - ts; ov = 0.0 if grad else (V * k / (T + k) * (1 - fr) * rt / 1e9 if k > 0 else 0.0)
        v = ps - cb + ov; pnl[u] += v; byrun[(u, r["run"])] += v; opn[u] += ov
        nl[u] += 1; fdt[u].append((fs - S) * SL); picks[u].append(m)
P("=== Non-insider wallets on non-SOL curves (both runs, non-mayhem): realized SOL-eq (sells capped at own buys) + open tokens sold into the last curve state (0 if the curve graduated)")
P(f"   all non-insider wallets: sum {sum(pnl.values()):+.1f} SOL-eq over {len(pnl)} wallets; winners {sum(v for v in pnl.values() if v>0):+.1f}; losers {sum(v for v in pnl.values() if v<0):+.1f}")
PRO_INV = {v: k for k, v in NT.PRO.items()}
for u, v in sorted(pnl.items(), key=lambda x: -x[1])[:20]:
    fd = fdt[u]
    P(f"   {u[:8]}… {v:+8.2f} (R1 {byrun[(u,'R1')]:+7.2f} / R2 {byrun[(u,'R2')]:+7.2f}) open {opn[u]:+6.1f}, launches {nl[u]:4d}, first buy p50 {statistics.median(fd):6.1f} s (p10 {sorted(fd)[len(fd)//10]:.1f}), "
      f"{'FAST' if u in FAST else 'not-fast'}{' PRO '+PRO_INV[u] if u in PRO_INV else ''}")
cls = collections.defaultdict(float)
for u, v in pnl.items(): cls["pro" if u in PRO_INV else ("fast" if u in FAST else "generic")] += v
for p_, u_ in NT.PRO.items():
    if nl[u_]: P(f"   PRO {p_}: {pnl[u_]:+7.2f} SOL-eq (R1 {byrun[(u_,'R1')]:+6.2f} / R2 {byrun[(u_,'R2')]:+6.2f}) on {nl[u_]} non-SOL launches, first buy p50 {statistics.median(fdt[u_]):.2f} s")
P("   by class: " + ", ".join(f"{k} {v:+.1f}" for k, v in cls.items()))
# ---- pros' picks: own trades removed
def px_wo(m, drop):
    r = rows[m]; tr = NT.clean(TR.get(m, [])); c = L[m]; st = rp.structure(tr, c)
    if st["g_end"] < 1: return None
    ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; trr = NT.rebase(tr, drop, st["g_end"])
    return [NT.at(trr, c["slot"] + int(x / SL), p_b) / p_b for x in CK]
TRD = [m for m, r in rows.items() if tradeable(r)]
base = [rows[m]["px"] for m in TRD]
def line(lab, v):
    if not v: return
    cells = []
    for j, x in enumerate(CK):
        y = [a[j] for a in v]
        cells.append(f"{x}s {statistics.median(y):.3f}|{statistics.mean(y):.3f}|{sum(1 for z in y if z>1.1)/len(y):.0%}")
    P(f"   {lab:40s} " + "  ".join(cells))
P("\n=== Pros' non-SOL picks: price vs post-bundle with the pro's OWN trades removed (median|mean|share>1.10x); baseline = all tradeable launches, all trades")
line(f"all tradeable launches (n={len(base)})", base)
top_np = [u for u, v in sorted(pnl.items(), key=lambda x: -x[1])[:20] if u not in PRO_INV and nl[u] >= 5][:5]
for lab, u in list(NT.PRO.items()) + [(u[:8] + "(top earner)", u) for u in top_np]:
    ms = [m for m in picks.get(u, []) if tradeable(rows[m])]
    if len(ms) < 5: continue
    fd = [ (min(t["s"] for t in NT.clean(TR[m]) if t["user"] == u and t["buy"]) - L[m]["slot"]) * SL for m in ms]
    sz = []
    for m in ms:
        tt = [t for t in NT.clean(TR[m]) if t["user"] == u and t["buy"]]
        sz.append(sum((t["sol"] + t["feeq"] + t["cfeeq"]) for t in tt[:1]) * rows[m]["rate"] / 1e9)
    v = [x for x in (px_wo(m, {u}) for m in ms) if x]
    qc = collections.Counter(ns.qname(rows[m]["quote"]) if ns.qname(rows[m]["quote"]) in ("PUMP", "USDC") else ("pump-token" if rows[m]["quote"].endswith("pump") else ("xStock" if rows[m]["quote"].startswith("Xs") else "other")) for m in ms)
    P(f"\n   {lab}: {len(ms)} tradeable picks; first buy p50 {statistics.median(fd):.2f} s (within 2 slots {sum(1 for x in fd if x<=0.43)/len(fd):.0%}); first-buy size p50 {statistics.median(sz):.2f} SOL-eq; quotes {dict(qc.most_common(4))}")
    P(f"      dev buy p50 {statistics.median(rows[m]['dev_sol'] for m in ms):.2f} SOL-eq (all launches {statistics.median(rows[m]['dev_sol'] for m in TRD):.2f}); glued>=1 {sum(1 for m in ms if rows[m]['n_glued'])/len(ms):.0%} (all {sum(1 for m in TRD if rows[m]['n_glued'])/len(TRD):.0%}); "
      f"creator fee>=100bps {sum(1 for m in ms if rows[m]['cbps']>=100)/len(ms):.0%} (all {sum(1 for m in TRD if rows[m]['cbps']>=100)/len(TRD):.0%}); generic 2-10 s buy p50 {statistics.median(rows[m]['flow'].get('gen_w2_b',0) for m in ms):.2f} SOL-eq (all {statistics.median(rows[m]['flow'].get('gen_w2_b',0) for m in TRD):.2f})")
    line(f"{lab} picks, own trades removed", v)
open(os.path.join(NT.HERE, "pros.txt"), "w").write("\n".join(out) + "\n")
