#!/usr/bin/env python3
# "Become them" test for snipe-time strategies: our OWN selection (here FINAL-2's live picks, logged by the shadow at
# bundle close, or any mint list), our buy at our landing with the price guard (fills only if first after the bundle),
# exits from our landing. Each pick is scored 5 ways:
#   base   : the real path
#   slip   : followers our buy pushes past their own slippage limit are dropped (rp.load_slip)
#   nosnip : every buy by a SNIPER (321 wallets) or PRO (9 shared wallets) after our entry dropped
#   nopro  : the 9 shared pro wallets removed ENTIRELY (buys and sells, before and after us), curve and our place in line
#            recomputed without them  -> what we make if we had replaced them, not fed on them
#   nopro+slip
# usage: RP_PHASEA_R2=phaseA_gf python3 -I become_eval.py <picks.json> [B=0.5] [guard=1.005]
import sys, os, json, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
CORE = "/home/moiz/sniper/ops/overnight/core"
LANDS = [int(x) for x in os.environ.get("LANDS", "45,75").split(",")]
PICKS = json.load(open(sys.argv[1])); B = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5; G = float(sys.argv[3]) if len(sys.argv) > 3 else 1.005
L = rp.load_launches(); O = rp.load_obs(); W = json.load(open(f"{CORE}/gf_wallets.json"))
SNIPER = {u for u, v in W.items() if v[1] >= 5 and v[1] >= 0.5 * v[0]}
PRO = set()
for p in ("9Sh2fd", "DGmspi", "D24ipY", "dKMjeG", "CWiNFA", "9qz7cW", "FiFawH", "AHwJSn", "4yFAz"):
    c = [u for u in W if u.startswith(p)]
    if c: PRO.add(max(c, key=lambda u: W[u][0]))
P6 = {u[:6] for u in PRO}
CWB = set(json.load(open("/home/moiz/sniper/ops/overnight/dip/drop_cw.json"))) | SNIPER | PRO
RND = set(json.load(open("/home/moiz/sniper/ops/overnight/dip/drop_rand.json")))       # calibration: 541 random active non-winner wallets
CWO = set(json.load(open("/home/moiz/sniper/ops/overnight/dip/drop_cw.json")))          # consistent winners only (no snipers / pros)     # every bot cohort (census consistent winners + snipers + pros)
EX = [rp.R("eos1", [(1.0, ("slot", 1))], 5), rp.R("fsell", [(1.0, ("ev", "any_sell"))], 30)]
EX += [rp.R(f"t{h}", [(1.0, ("t", float(h)))], h + 1) for h in (1, 2, 3, 5, 8, 10, 15, 20, 30)]
EX += [rp.R("tp1.3_sl.9_c20", [(1.0, ("x", 1.3)), (1.0, ("sl", 0.9))], 20), rp.R("tp1.5_sl.85_c30", [(1.0, ("x", 1.5)), (1.0, ("sl", 0.85))], 30),
       rp.R("tp2_sl.8_c60", [(1.0, ("x", 2.0)), (1.0, ("sl", 0.8))], 60), rp.R("tr1.2_15_c60", [(1.0, ("dd", 1.2, 0.15)), (1.0, ("sl", 0.85))], 60)]
EX += [rp.R("t10_devsell", [(1.0, ("t", 10.0)), (1.0, ("ev", "ins_sell"))], 11), rp.R("t10_sell1", [(1.0, ("t", 10.0)), (1.0, ("ev", "sell1"))], 11),
       rp.R("t10_sell2", [(1.0, ("t", 10.0)), (1.0, ("ev", "sell2"))], 11), rp.R("t15_devsell", [(1.0, ("t", 15.0)), (1.0, ("ev", "ins_sell"))], 16)]
EX += [rp.R("dk_pieces", [(0.5, ("t", 1.7)), (0.125, ("t", 4.0)), (0.125, ("t", 6.0)), (0.125, ("t", 9.0)), (0.125, ("t", 12.0))], 13),
       rp.R("p20_2to10", [(0.2, ("t", float(k))) for k in (2, 4, 6, 8, 10)], 11),
       rp.R("half5_half10", [(0.5, ("t", 5.0)), (0.5, ("t", 10.0))], 11),
       rp.R("third3_6_10", [(0.34, ("t", 3.0)), (0.33, ("t", 6.0)), (0.33, ("t", 10.0))], 11)]
EX += [rp.R("t8_tp1.4", [(1.0, ("t", 8.0)), (1.0, ("x", 1.4))], 9), rp.R("t10_tp1.4", [(1.0, ("t", 10.0)), (1.0, ("x", 1.4))], 11),
       rp.R("t10_tp1.3", [(1.0, ("t", 10.0)), (1.0, ("x", 1.3))], 11), rp.R("t10_tp1.6", [(1.0, ("t", 10.0)), (1.0, ("x", 1.6))], 11)]
EX += [rp.R(f"idle{g}_c{c}", [(1.0, ("idle", g)), (1.0, ("t", float(c)))], c + 1) for g in (1.0, 1.5, 2.0, 3.0) for c in (10, 15, 20, 30)]
EX += [rp.R("t10_prosell", [(1.0, ("t", 10.0)), (1.0, ("ev", "pro_sell"))], 11), rp.R("t15_prosell", [(1.0, ("t", 15.0)), (1.0, ("ev", "pro_sell"))], 16),
       rp.R("t10_snpsell", [(1.0, ("t", 10.0)), (1.0, ("ev", "snp_sell"))], 11), rp.R("t20_prosell", [(1.0, ("t", 20.0)), (1.0, ("ev", "pro_sell"))], 21)]
EX += [rp.R(f"tu{T}_a{a}_d{d}_c{c}", [(1.0, ("tu", float(T), a)), (1.0, ("dd", a, d))], c) for T in (8, 10) for (a, d, c) in ((1.2, 0.15, 60), (1.3, 0.2, 60), (1.5, 0.25, 120), (1.3, 0.3, 120))]
XN = [e["name"] for e in EX]
def rebase(tr, drop):
    """the trade list without `drop` wallets, reserves recomputed from the first dropped trade on"""
    out = []; V = T = None
    for t in tr:
        if t["user"] in drop:
            if V is None:
                if out: V, T = out[-1]["vsol"], out[-1]["vtok"]
                else: V, T = (t["vsol"] - t["sol"], t["vtok"] + t["tok"]) if t["buy"] else (t["vsol"] + t["sol"], t["vtok"] - t["tok"])
            continue
        if V is None: out.append(t); continue
        x = dict(t)
        if t["buy"]: d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d; x["tok"] = d
        else: so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]; x["sol"] = so
        x["vsol"], x["vtok"] = V, T; out.append(x)
    return out
byb = collections.defaultdict(set)
for m in PICKS:
    if m in L and (m in O or L[m]["run"] == "R1"): byb[(L[m]["run"], rp.bucket(m))].add(m)      # R1: no timelines -> position proxy
SLIP = None
def init():
    global SLIP
    SLIP = rp.load_slip(); rp.PROS = PRO; rp.SNIPERS = SNIPER
def one(tr, c, outs, fa, Lm, slip, drop_after):
    st = rp.structure(tr, c)
    if st["g_end"] < 1: return None
    ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]
    ib, _ = rp.place_bo2(tr, c, st, outs, Lm, fa) if outs is not None else rp.place_proxy(tr, c, st, Lm)
    if ib < 1: return None
    if (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b > G: return dict(fill=False)
    o = rp.sim(tr, c, st, ib, B, EX, fill_pen=0.015, delay_slots=1, slip=slip, drop_after=drop_after)
    if not o: return None
    bs = max(c["slot"], tr[ib - 1]["s"]); w = [t for t in tr[ib:] if t["s"] <= bs + 1 and t["buy"] and not t.get("syn")]
    return dict(fill=True, pnl={x: o[x]["pnl"] for x in XN}, nb=len(w), px=o["eos1"]["slipped"], after=tr[ib - 1]["user"][:8])
def work(key):
    run, b = key; tra = rp.read_bucket(run, b, byb[key]); fa = rp.read_failed(run, b, byb[key]) if run == "R2" else {}; res = []
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; outs = O[m]["outs"] if run == "R2" else None; f = fa.get(m, [])
        trp = rebase(tr, PRO); outsp = [o for o in outs if o[3][:6] not in P6] if outs is not None else None; fp = [x for x in f if (x[2] if len(x) > 2 else "")[:6] not in P6]
        r = dict(m=m, run=run, name=c.get("name"), bt=c["bt"], pro_in=sorted({t["user"][:6] for t in tr if t["user"] in PRO}))
        for Lm in LANDS:
            r[str(Lm)] = dict(base=one(tr, c, outs, f, Lm, None, None), slip=one(tr, c, outs, f, Lm, SLIP, None),
                              nosnip=one(tr, c, outs, f, Lm, None, SNIPER | PRO), nopro=one(trp, c, outsp, fp, Lm, None, None),
                              nopro_slip=one(trp, c, outsp, fp, Lm, SLIP, None), proafter_slip=one(tr, c, outs, f, Lm, SLIP, PRO), nobots_slip=one(tr, c, outs, f, Lm, SLIP, CWB), nocw_slip=one(tr, c, outs, f, Lm, SLIP, CWO), norand_slip=one(tr, c, outs, f, Lm, SLIP, RND))
        res.append(r)
    return res
if __name__ == "__main__":
    res = []
    with Pool(8, initializer=init) as p:
        for o in p.imap_unordered(work, sorted(byb)): res += o
    res.sort(key=lambda r: r["bt"])
    out = sys.argv[1].replace(".json", f"_become_B{B}" + os.environ.get("OUT_SFX", "") + ".json"); json.dump(res, open(out, "w"))
    print(f"{len(res)} picks with data, size {B} SOL, guard {G}; failed guarded buy = -0.005 SOL; 2% buy overhead")
    for Lm in [str(x) for x in LANDS]:
        print(f"\n landing {Lm} ms")
        for var in ("base", "slip", "proafter_slip", "nopro_slip", "nosnip", "nobots_slip", "nocw_slip", "norand_slip"):
            v = [r[Lm][var] for r in res if r[Lm][var] is not None]
            fills = [x for x in v if x["fill"]]; nf = len(v) - len(fills)
            cells = []
            for xn in XN:
                tot = sum(x["pnl"][xn] for x in fills) - 0.005 * nf
                cells.append(f"{xn} {tot:+5.2f}")
            flat = sum(1 for x in fills if x["nb"] == 0)
            print(f"   {var:10s} fills {len(fills):3d}/{len(v):3d} (no buyer after us {flat:3d}) | " + " | ".join(cells))
