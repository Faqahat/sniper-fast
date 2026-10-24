#!/usr/bin/env python3
# FINAL-2(+guards) picks: which are FAST DUMPS / DEAD (no other buyers) and which KEEP TRADING (outside buyers for
# 5 s / 20 s / 60 s+)? What pre-buy facts separate them? Rules chosen on BUILD (run 1), checked on TEST (forward run).
# Entry = first in line right after the creator's bundle (selection only, landing set aside on the owner's request).
# usage: python3 g_losers.py <table_dump.jsonl.gz> <demand.jsonl.gz> <run2 start bt> <final_config.json> <out dir>
import sys, os, json, gzip, math, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from live2score import load
TAB, DEM, FWD0, CFG, OUT = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4], sys.argv[5]; os.makedirs(OUT, exist_ok=True)
C = json.load(open(CFG)); D = os.path.dirname(os.path.abspath(TAB))
M3, s3 = load(os.path.join(D, C["model_file"])); Mv, sv = load(os.path.join(D, C["veto_file"]))
dm = {}
for l in gzip.open(DEM, "rt"): x = json.loads(l); dm[x["mint"]] = x
P = []
for l in gzip.open(TAB, "rt"):
    r = json.loads(l)
    if not (r.get("quote_sol") == 1 and (r.get("max_vsol") or 0) <= 200 and r.get("bt") and r.get("E_bundle_h5s") is not None and r["mint"] in dm): continue
    if s3(r) < M3["thresholds"][C["top"]] or sv(r) >= C["veto_cut"] or r.get("payer_is_creator") != 1 or ((r.get("glued_n") or 0) == 0 and (r.get("dev_buy") or 0) < 1): continue
    r.update(dm[r["mint"]]); r["_pnl"] = (r["E_bundle_fsell_30s_eos"] - 0.03) * 0.5; P.append(r)
P.sort(key=lambda r: r["bt"])
def cat(r):
    if r["d_min5s"] <= 0.85: return "A fast dump (<=0.85x within 5 s)"
    if r["d_ub_10s"] <= 1: return "B dead (0-1 other buyers in 10 s)"
    la = r.get("d_last_out_buy_s") or 0
    if la < 5: return "C buyers stop before 5 s"
    if la < 20: return "D trades 5-20 s"
    if la < 60: return "E trades 20-60 s"
    return "F trades 60 s+"
for r in P: r["_cat"] = cat(r); r["_bad"] = r["_cat"][0] in "AB"; r["_good"] = r["_cat"][0] in "DEF"
BUILD = [r for r in P if r["bt"] < FWD0]; TEST = [r for r in P if r["bt"] >= FWD0]
def table(rs, lab):
    print(f"\n{lab}: {len(rs)} picks")
    c = collections.defaultdict(list)
    for r in rs: c[r["_cat"]].append(r)
    for k in sorted(c):
        v = np.array([r["_pnl"] for r in c[k]])
        print(f"  {k:36} n={len(v):4} ({len(v) / len(rs):4.0%}) | our trade: total {v.sum():+7.2f} SOL mean {v.mean():+.4f} win {(v > 0).mean():4.0%}")
table(BUILD, "BUILD (run 1, 10-21 22:07 - 10-22 14:00 UTC)"); table(TEST, "TEST (forward, 10-22 15:43 - 10-23 ~09:50 UTC)")
# ---- what separates bad (A+B) from good (D+E+F): single conditions and pairs, chosen on BUILD
FE = ["dev_buy", "glued_n", "glued_wallets", "glued_sol", "dev_share", "bundle_avg", "P0_mc_sol", "create_cup", "create_cul", "create_tips", "name_len", "sym_len",
      "heat_launches_10m", "heat_win_rate_60m", "wave_name_10m", "wave_name_60m", "wave_sym_60m", "cr_creates_window", "cr_min_since_prev_create",
      "h_cr_n", "h_cr_wins", "h_cr_last_win", "h_name_n", "h_name_wins", "h_bund_seen", "h_bund_launches", "h_bund_wins",
      "hd_cr_n", "hd_cr_fast", "hd_cr_first_s", "hd_cr_out_s", "hd_bw_seen", "hd_bw_fast", "hd_bw_first_s", "hd_bw_worst", "hd_dev_n", "hd_dev_fast", "hour_utc"]
def val(r, k):
    v = r.get(k); return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else float("nan")
atoms = []
for k in FE:
    v = np.array([val(r, k) for r in BUILD]); t = v[~np.isnan(v)]
    if len(t) < 50: continue
    for q in np.unique(np.round(np.quantile(t, [.1, .2, .3, .4, .5, .6, .7, .8, .9]), 4)):
        atoms.append((f"{k} >= {q:g}", lambda r, k=k, q=q: not (val(r, k) < q)))      # unknown passes
        atoms.append((f"{k} <= {q:g}", lambda r, k=k, q=q: not (val(r, k) > q)))
for k in ("uri_host",):
    for v, n in collections.Counter(r.get(k) for r in BUILD).most_common(6):
        if n >= 30: atoms.append((f"{k} != {v}", lambda r, k=k, v=v: r.get(k) != v)); atoms.append((f"{k} == {v}", lambda r, k=k, v=v: r.get(k) == v))
def score(rs, f):
    keep = [r for r in rs if f(r)]
    if len(keep) < 0.5 * len(rs): return None
    bad0 = sum(r["_bad"] for r in rs); good0 = sum(r["_good"] for r in rs)
    rb = 1 - sum(r["_bad"] for r in keep) / max(bad0, 1); kg = sum(r["_good"] for r in keep) / max(good0, 1)
    pnl = sum(r["_pnl"] for r in keep)
    return dict(n=len(keep), removed_bad=rb, kept_good=kg, pnl=pnl, pnl_all=sum(r["_pnl"] for r in rs), bad_rate=sum(r["_bad"] for r in keep) / len(keep))
cands = []
for lab, f in atoms:
    s = score(BUILD, f)
    if s and s["removed_bad"] - (1 - s["kept_good"]) > 0.05: cands.append((s["removed_bad"] - (1 - s["kept_good"]) + 0.002 * (s["pnl"] - s["pnl_all"]), (lab,), f))
cands.sort(key=lambda x: -x[0]); top1 = cands[:25]
for sc, lab, f in list(top1):                                 # pairs from the best singles
    for sc2, lab2, f2 in top1:
        if lab2[0].split(" ")[0] == lab[0].split(" ")[0]: continue
        g = lambda r, f=f, f2=f2: f(r) and f2(r); s = score(BUILD, g)
        if s: cands.append((s["removed_bad"] - (1 - s["kept_good"]) + 0.002 * (s["pnl"] - s["pnl_all"]), lab + lab2, g))
cands.sort(key=lambda x: -x[0]); seen = set(); best = []
for sc, lab, f in cands:
    key = tuple(sorted(lab))
    if key in seen: continue
    seen.add(key); best.append((sc, lab, f))
    if len(best) >= 12: break
print("\nBEST CONDITIONS (chosen on BUILD; TEST never used): keep the pick only if ...")
for sc, lab, f in best:
    b, t = score(BUILD, f), score(TEST, f)
    print(f"  {' AND '.join(lab)}")
    for nm, s, rs in (("BUILD", b, BUILD), ("TEST ", t, TEST)):
        if not s: print(f"     {nm} keeps < 50%"); continue
        print(f"     {nm} keeps {s['n']:3}/{len(rs)} | removes {s['removed_bad']:4.0%} of the dumps+dead, keeps {s['kept_good']:4.0%} of the 5 s+ traders | dumps+dead in what is left {s['bad_rate']:4.0%}"
              f" (was {sum(r['_bad'] for r in rs) / len(rs):.0%}) | our trades {s['pnl']:+.2f} SOL (was {s['pnl_all']:+.2f})")
# per-trade list for the owner (TEST)
with open(os.path.join(OUT, "picks_by_type.txt"), "w") as fo:
    for r in TEST:
        fo.write(f"{r['_cat'][:1]} {r['mint']}  pnl {r['_pnl']:+.4f} SOL | other buyers 5 s {r['d_ub_5s']} / 10 s {r['d_ub_10s']} / 60 s {r['d_ub_60s']} | last outside buy {r.get('d_last_out_buy_s')} s"
                 f" | low in 5 s {r['d_min5s']:.2f}x | dev {r.get('dev_buy', 0):.2f} bundle {r.get('glued_n')}/{(r.get('glued_sol') or 0):.2f} SOL | https://gmgn.ai/sol/token/{r['mint']}\n")
