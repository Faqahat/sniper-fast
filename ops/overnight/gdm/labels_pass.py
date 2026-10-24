#!/usr/bin/env python3
# GDM step 1 (read-only, offline): per-launch LABELS for a generic-demand selection model, one pass over the trade data.
#  (a) market label, independent of our placement: price at create-slot + 3/5/8/10/15 s vs the post-bundle price, with
#      EVERY trade (buys and sells) of the 321 sniper + 9 pro wallets after the bundle removed and reserves rebased
#      ("what generic flow alone did to the price"); also the raw ratio (nothing removed) for reference.
#  (c) generic demand: distinct non-sniper / non-pro / non-insider buyers (and their SOL) 2-10 s and 0-10 s after the create.
#  (b) our replay at 30 ms landing (same mechanics as core/precompute_bt.py: guard 1.005 vs post-bundle price, 0.5 SOL,
#      fill_pen 1.5%, delay 1 slot): base / slip / ps (slip + pro buys after us removed) / ns (slip + all sniper+pro buys
#      after us removed), exits eos1,t3,t5,t8,t10,t15. 45/75 ms already exist in core/allres_bt.json.
# Also stores the glued bundle wallets (for walk-forward history features).
# usage: RP_PHASEA_R2=phaseA_gf python3 -I labels_pass.py  -> gdm/labels.json
import sys, os, json, collections, math
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
CORE = "/home/moiz/sniper/ops/overnight/core"; OUT = "/home/moiz/sniper/ops/overnight/gdm"
assert os.environ.get("RP_PHASEA_R2") == "phaseA_gf"
L = rp.load_launches(); O = rp.load_obs(); W = json.load(open(f"{CORE}/gf_wallets.json")); LS = json.load(open(f"{CORE}/gf_launches.json"))
SNIPER = {u for u, v in W.items() if v[1] >= 5 and v[1] >= 0.5 * v[0]}
PRO = set()
for p in ("9Sh2fd", "DGmspi", "D24ipY", "dKMjeG", "CWiNFA", "9qz7cW", "FiFawH", "AHwJSn", "4yFAz"):
    c = [u for u in W if u.startswith(p)]
    if c: PRO.add(max(c, key=lambda u: W[u][0]))
if os.environ.get("GDM_SNIPER_FILE"): SNIPER = set(json.load(open(os.environ["GDM_SNIPER_FILE"])))   # leakage check: R1-only list
DROP = SNIPER | PRO
SL = rp.SLOT_MS / 1000.0
EX = [rp.R("eos1", [(1.0, ("slot", 1))], 5)] + [rp.R(f"t{h}", [(1.0, ("t", float(h)))], h + 1) for h in (3, 5, 8, 10, 15)]
XN = [e["name"] for e in EX]; G = 1.005; LAND = int(os.environ.get("GDM_LAND", "30"))
HS = (3, 5, 8, 10, 15)
todo = [m for m in LS if m in L]
byb = collections.defaultdict(set)
for m in todo: byb[(LS[m]["run"], rp.bucket(m))].add(m)
SLP = None
def init():
    global SLP
    SLP = rp.load_slip()
def rebase_after(tr, g_end, drop, ins):
    """tr with every trade of `drop` wallets (not insiders) after the bundle removed; reserves recomputed"""
    out = list(tr[:g_end]); V = T = None
    for t in tr[g_end:]:
        if t["user"] in drop and t["user"] not in ins:
            if V is None: V, T = (out[-1]["vsol"], out[-1]["vtok"]) if out else (None, None)
            continue
        if V is None: out.append(t); continue
        x = dict(t)
        if t["buy"]: d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d; x["tok"] = d
        else:
            so = V * t["tok"] // (T + t["tok"]) if T + t["tok"] > 0 else 0; V -= so; T += t["tok"]; x["sol"] = so
        x["vsol"], x["vtok"] = V, T; out.append(x)
    return out
def px_at(tr, k, p0):
    p = p0
    for t in tr:
        if t["s"] > k: break
        if t["vtok"]: p = t["vsol"] / t["vtok"]
    return p
def work(key):
    run, b = key; tra = rp.read_bucket(run, b, byb[key]); fa = rp.read_failed(run, b, byb[key]) if run == "R2" else {}; out = {}
    for m, tr in tra.items():
        if not tr or min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; S = c["slot"]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ins = st["insiders"]; ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]
        r = dict(run=run, bt=c["bt"], bw=sorted({t["user"] for t in st["glued"]}), ng=len(st["glued"]))
        pn = rebase_after(tr, st["g_end"], DROP, ins)
        r["a"] = [round(px_at(pn, S + int(h / SL), p_b) / p_b, 5) for h in HS]           # nosnip ratio at 3,5,8,10,15 s
        r["raw"] = [round(px_at(tr, S + int(h / SL), p_b) / p_b, 5) for h in HS]
        r["amax10"] = round(max([p_b] + [t["vsol"] / t["vtok"] for t in pn[st["g_end"]:] if t["s"] <= S + int(10 / SL) and t["vtok"]]) / p_b, 5)
        k2, k10 = S + int(2 / SL), S + int(10 / SL)
        gen = [t for t in tr[st["g_end"]:] if t["user"] not in ins and t["user"] not in DROP and t["s"] <= k10]
        g210 = [t for t in gen if t["buy"] and t["s"] > k2]; g010 = [t for t in gen if t["buy"]]
        r["c"] = [len({t["user"] for t in g210}), round(sum(t["sol"] for t in g210) / 1e9, 4), len({t["user"] for t in g010}), round(sum(t["sol"] for t in g010) / 1e9, 4),
                  round(sum(t["sol"] for t in gen if not t["buy"]) / 1e9, 4)]
        snp = [t for t in tr[st["g_end"]:] if t["user"] in DROP and t["user"] not in ins and t["s"] <= k10 and t["buy"]]
        r["snp10"] = [len({t["user"] for t in snp}), round(sum(t["sol"] for t in snp) / 1e9, 4)]
        insell = [t for t in tr[st["g_end"]:] if t["user"] in ins and not t["buy"] and t["s"] <= k10]
        r["ins_sell10"] = round(sum(t["sol"] for t in insell) / 1e9, 4)
        if run == "R1" or m in O:
            ib, _ = rp.place_bo2(tr, c, st, O[m]["outs"], LAND, fa.get(m, [])) if run == "R2" else rp.place_proxy(tr, c, st, LAND)
            if ib >= 1:
                if (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b > G: r[str(LAND)] = None
                else:
                    d = {}
                    for var, kw in (("base", {}), ("slip", dict(slip=SLP)), ("ps", dict(slip=SLP, drop_after=PRO)), ("ns", dict(slip=SLP, drop_after=SNIPER | PRO))):
                        o = rp.sim(tr, c, st, ib, 0.5, EX, fill_pen=0.015, delay_slots=1, **kw)
                        if o: d[var] = [round(o[x]["pnl"], 5) for x in XN]
                    bs = max(c["slot"], tr[ib - 1]["s"]); d["nb"] = sum(1 for t in tr[ib:] if t["s"] <= bs + 1 and t["buy"])
                    r[str(LAND)] = d
        out[m] = r
    return out
if __name__ == "__main__":
    keys = sorted(byb)
    if os.environ.get("GDM_TEST"): keys = keys[:int(os.environ["GDM_TEST"])]
    res = {}
    with Pool(6, initializer=init) as p:
        for i, o in enumerate(p.imap_unordered(work, keys)):
            res.update(o)
            if i % 64 == 0: print(f"  {i}/{len(keys)} buckets", flush=True)
    fn = f"{OUT}/labels{'_test' if os.environ.get('GDM_TEST') else ''}{os.environ.get('GDM_SUFFIX', '')}.json"
    json.dump(dict(hs=list(HS), exits=XN, land=LAND, res=res), open(fn, "w"))
    n = collections.Counter((v["run"], "fill" if v.get(str(LAND)) else ("guard" if str(LAND) in v else "nodata")) for v in res.values())
    print("launches", len(res), dict(n), "->", fn)
