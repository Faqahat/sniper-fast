#!/usr/bin/env python3
# Task 1: the non-SOL-quoted universe (MEASURED from the collector, both runs). -> universe.txt
import sys, os, json, collections, statistics, time, math
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/nonsol"); sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import ns
HERE = "/home/moiz/sniper/ops/overnight/nonsol"; DATA = os.path.join(HERE, "data")
rows = [json.loads(l) for l in open(os.path.join(DATA, "table.jsonl"))]
L, CR, TR, W = ns.load()
import ns_table as NT
out = []
def P(*a): out.append(" ".join(str(x) for x in a))
def qcls(q):
    n = ns.qname(q)
    if n in ("PUMP", "USDC", "USD1", "USDT"): return n
    if q.endswith("pump"): return "pump-token"
    if q.startswith("Xs"): return "xStock"
    return "other"
def pct(v, p):
    v = sorted(v); return v[min(len(v) - 1, int(p * len(v)))] if v else None
HRS = {r: (NT.WIN[r][1] - NT.WIN[r][0]) / 3600 for r in NT.WIN}
# ---- SOL-side counts in the same windows for scale
solc = collections.Counter()
for m, cr in CR.items():
    c = L.get(m)
    if not c or not c.get("bt") or cr["quote"] != "SOL": continue
    a, b = NT.WIN[c["run"]]
    if a <= c["bt"] < b: solc[(c["run"], cr["mayhem"])] += 1
P("=== 1. Volume (launches per hour), windows R1 %.1f h, R2 %.1f h" % (HRS["R1"], HRS["R2"]))
for run in ("R1", "R2"):
    rr = [r for r in rows if r["run"] == run]
    nm = [r for r in rr if not r["mayhem"]]
    P(f"{run}: non-SOL launches {len(rr)} ({len(rr)/HRS[run]:.0f}/h; mayhem {len(rr)-len(nm)}) vs SOL-quoted {solc[(run,0)]+solc[(run,1)]} ({(solc[(run,0)]+solc[(run,1)])/HRS[run]:.0f}/h, mayhem {solc[(run,1)]})")
    P(f"   non-mayhem non-SOL: {len(nm)}; with ANY trade {sum(1 for r in nm if r.get('ntr'))}; with a dev buy in the create tx {sum(1 for r in nm if r.get('g_end',0)>=1)}; tradeable (priced quote, dev buy) {sum(1 for r in nm if r.get('rep') is not None and r.get('g_end',0)>=1)}")
    qc = collections.Counter(qcls(r["quote"]) for r in nm)
    qa = collections.Counter(qcls(r["quote"]) for r in nm if r.get("g_end", 0) >= 1)
    P("   by quote class (all / with dev buy), per hour: " + "; ".join(f"{k} {v} ({v/HRS[run]:.1f}/h) / {qa[k]}" for k, v in qc.most_common()))
    top = collections.Counter(ns.qname(r["quote"]) for r in nm).most_common(12)
    P("   top quote tokens: " + ", ".join(f"{k} {v}" for k, v in top))
# hourly profile PKT
P("\n   per PKT hour (non-mayhem non-SOL launches | of them with a dev buy):")
hh = collections.Counter(); hd = collections.Counter()
for r in rows:
    if r["mayhem"]: continue
    k = (r["run"], time.strftime("%m-%d %H", time.gmtime(r["bt"] + ns.PKT))); hh[k] += 1
    if r.get("g_end", 0) >= 1: hd[k] += 1
P("   " + " | ".join(f"{k[1]}h {v}/{hd[k]}" for k, v in sorted(hh.items())))
T = [r for r in rows if not r["mayhem"] and r.get("g_end", 0) >= 1 and r.get("rate")]
P("\n=== 2. Dev / bundle patterns (non-mayhem launches with a dev buy, both runs, n=%d)" % len(T))
for run in ("R1", "R2"):
    tt = [r for r in T if r["run"] == run]
    dv = [r["dev_sol"] for r in tt]
    P(f"{run}: dev buy SOL-eq p10/p50/p90 {pct(dv,.1):.3f}/{pct(dv,.5):.3f}/{pct(dv,.9):.3f}; >=1 SOL {sum(1 for x in dv if x>=1)/len(dv):.0%}; >=2 SOL {sum(1 for x in dv if x>=2)/len(dv):.0%}")
    gc = collections.Counter(min(r["n_glued"], 4) for r in tt)
    P(f"     glued bundle txs: " + ", ".join(f"{k}{'+' if k==4 else ''}: {v/len(tt):.0%}" for k, v in sorted(gc.items())) + f"; bundle SOL-eq p50 (if any) {pct([r['glued_sol'] for r in tt if r['n_glued']],.5)}")
    cb = collections.Counter(r["cbps"] for r in tt); fb = collections.Counter(r["fbps"] for r in tt)
    P(f"     creator fee bps: " + ", ".join(f"{k}: {v/len(tt):.0%}" for k, v in cb.most_common(6)) + " | protocol fee bps: " + ", ".join(f"{k}: {v/len(tt):.0%}" for k, v in fb.most_common(3)))
    P(f"     curve depth (initial virtual quote reserves in SOL-eq) p10/p50/p90 {pct([r['vq0_sol'] for r in tt],.1)}/{pct([r['vq0_sol'] for r in tt],.5)}/{pct([r['vq0_sol'] for r in tt],.9)} (SOL curves: 30)")
    P(f"     payer is creator {sum(r['payer_is_creator'] for r in tt)/len(tt):.0%}; create tx with a tip {sum(1 for r in tt if r.get('create_tips'))/len(tt):.0%}")
for qc_ in ("PUMP", "USDC", "xStock", "pump-token", "other"):
    tt = [r for r in T if qcls(r["quote"]) == qc_]
    if not tt: continue
    dv = [r["dev_sol"] for r in tt]
    P(f"   {qc_:10s} n={len(tt):5d} dev p50 {pct(dv,.5):.3f} SOL; glued>=1 {sum(1 for r in tt if r['n_glued'])/len(tt):.0%}; creator fee 300bps {sum(1 for r in tt if r['cbps']>=300)/len(tt):.0%}; depth p50 {pct([r['vq0_sol'] for r in tt],.5)} SOL")
P("\n=== 3. Price vs post-bundle price at 1/2/5/10/30/60 s after the create (median | mean | share > 1.10x | share < 0.90x)")
CK = (1, 2, 5, 10, 30, 60)
def pxline(sel, key, lab):
    cells = []
    for j, x in enumerate(CK):
        v = [r[key][j] for r in sel if r.get(key)]
        if not v: continue
        cells.append(f"{x}s {statistics.median(v):.3f}|{statistics.mean(v):.3f}|{sum(1 for y in v if y>1.1)/len(v):.0%}|{sum(1 for y in v if y<0.9)/len(v):.0%}")
    P(f"   {lab:34s} " + "  ".join(cells))
for run in ("R1", "R2"):
    sel = [r for r in T if r["run"] == run]
    P(f"{run} (n={len(sel)})")
    pxline(sel, "px", "all trades"); pxline(sel, "px_nofast", "fast snipers removed"); pxline(sel, "px_nofp", "fast snipers + pros removed")
for qc_ in ("PUMP", "USDC", "xStock", "pump-token", "other"):
    sel = [r for r in T if qcls(r["quote"]) == qc_]
    if sel: pxline(sel, "px_nofp", f"{qc_} (n={len(sel)}) no fast/pro")
sel = [r for r in T if r["dev_sol"] >= 1]; pxline(sel, "px_nofp", f"dev>=1 SOL (n={len(sel)}) no fast/pro")
sel = [r for r in T if r["n_glued"] >= 1]; pxline(sel, "px_nofp", f"glued>=1 (n={len(sel)}) no fast/pro")
P("\n=== 4. Who buys (after the bundle, SOL-eq summed over launches; distinct buyers summed): share by class per window")
for run in ("R1", "R2"):
    sel = [r for r in T if r["run"] == run]
    for win, lab in (("w0", "0-2 s"), ("w2", "2-10 s"), ("w10", "10-60 s")):
        v = {cl: sum(r["flow"].get(f"{cl}_{win}_b", 0) for r in sel) for cl in ("ins", "fast", "pro", "gen")}
        nb = {cl: sum(r["nbuyers"].get(f"{cl}_{win}", 0) for r in sel) for cl in ("ins", "fast", "pro", "gen")}
        tot = sum(v.values()) or 1
        P(f"   {run} {lab:7s} buy SOL-eq {tot:8.1f}: " + ", ".join(f"{cl} {v[cl]/tot:.0%}" for cl in v) + " | buyers: " + ", ".join(f"{cl} {nb[cl]}" for cl in nb)
          + f" | launches with >=1 generic buyer {sum(1 for r in sel if r['nbuyers'].get('gen_'+win))/len(sel):.0%}")
    g = sorted(r["flow"].get("gen_w2_b", 0) for r in sel)
    P(f"   {run} generic buy SOL-eq in 2-10 s per launch: p50 {pct(g,.5):.3f} p75 {pct(g,.75):.3f} p90 {pct(g,.9):.3f} p99 {pct(g,.99):.2f}; launches with >= 1 SOL {sum(1 for x in g if x>=1)/len(g):.1%}")
    f2 = sum(1 for r in sel if r.get("fast_buys_2slot")); P(f"   {run} launches with a fast-sniper buy within 2 slots: {f2/len(sel):.0%}")
# ---- wallet PnL on non-SOL curves (realized SOL-eq flows incl. pump fees; open positions valued at the last curve price)
P("\n=== 5. Who makes money on these curves (all wallets; realized quote flows in SOL-eq incl. pump fees, open tokens at last price; non-mayhem; both runs)")
FASTS = set(json.load(open(os.path.join(DATA, "fast_snipers.json")))["sol"]) | set(json.load(open(os.path.join(DATA, "fast_snipers.json")))["nonsol"])
pnl = collections.defaultdict(float); nl = collections.Counter(); first_dt = collections.defaultdict(list); byrun = collections.defaultdict(float)
rowd = {r["m"]: r for r in rows}
for m, r in rowd.items():
    if r["mayhem"] or not r.get("rate") or not r.get("ntr"): continue
    tr = NT.clean(TR.get(m, []))
    if not tr: continue
    rt = r["rate"]; S = L[m]["slot"]; pos = collections.Counter(); seen = set()
    for t in tr:
        if t["buy"]: pnl[t["user"]] -= (t["sol"] + t["feeq"] + t["cfeeq"]) * rt / 1e9; byrun[(t["user"], r["run"])] -= (t["sol"] + t["feeq"] + t["cfeeq"]) * rt / 1e9; pos[t["user"]] += t["tok"]
        else: pnl[t["user"]] += (t["sol"] - t["feeq"] - t["cfeeq"]) * rt / 1e9; byrun[(t["user"], r["run"])] += (t["sol"] - t["feeq"] - t["cfeeq"]) * rt / 1e9; pos[t["user"]] -= t["tok"]
        if t["buy"] and t["user"] not in seen: seen.add(t["user"]); nl[t["user"]] += 1; first_dt[t["user"]].append((t["s"] - S) * 0.212)
    pl = tr[-1]["vsol"] / tr[-1]["vtok"]
    for u, k in pos.items():
        if k > 0: v = k * pl * rt / 1e9 * 0.98; pnl[u] += v; byrun[(u, r["run"])] += v
top = sorted(pnl.items(), key=lambda x: -x[1])[:15]
PRO_INV = {v: k for k, v in NT.PRO.items()}
for u, v in top:
    fd = first_dt[u]
    P(f"   {u[:8]}… {v:+8.2f} SOL-eq (R1 {byrun[(u,'R1')]:+.1f} / R2 {byrun[(u,'R2')]:+.1f}) launches {nl[u]:4d}, median first-buy {statistics.median(fd) if fd else -1:.1f} s after create, "
      f"{'FAST' if u in FASTS else 'not-fast'}{' PRO '+PRO_INV[u] if u in PRO_INV else ''}")
tot_pos = sum(v for v in pnl.values() if v > 0); tot_neg = sum(v for v in pnl.values() if v < 0)
P(f"   all wallets: winners +{tot_pos:.0f}, losers {tot_neg:.0f} SOL-eq (creators/insiders included)")
for p, u in NT.PRO.items():
    if nl[u]: P(f"   PRO {p}: {nl[u]} non-SOL launches bought, PnL here {pnl[u]:+.2f} SOL-eq (R1 {byrun[(u,'R1')]:+.2f} / R2 {byrun[(u,'R2')]:+.2f}), median first buy {statistics.median(first_dt[u]):.1f} s after create")
json.dump(dict(top=[(u, v, nl[u]) for u, v in sorted(pnl.items(), key=lambda x: -x[1])[:200]]), open(os.path.join(DATA, "wallet_pnl.json"), "w"))
open(os.path.join(HERE, "universe.txt"), "w").write("\n".join(out) + "\n")
print("\n".join(out))
