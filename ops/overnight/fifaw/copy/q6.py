#!/usr/bin/env python3
# READ-ONLY, offline copyability engine for FiFawH-derived strategies (rp.py replay, our mechanics, NEW realism rules).
# Modes:  L45 / L75 = snipe: we land 45 / 75 ms after the create (R2: rp.place_bo2 with failed-tx anchors on our engine's
#         timelines; R1: rp.place_proxy), 1% price guard vs the post-bundle price (fail = -0.005 SOL), 2% buy overhead.
#         D1 / D2 / D5 = later entry: decide t_d s after the create, land after EVERY trade in slots up to t_d + 0.4 s
#         (fill = price after every trade within ~400 ms of our decision), no guard, low-fee send (0.5% overhead).
# Exits:  eos1 (end of the slot after our buy), t1, t2, t5, t10 (~1/2/5/10 s after our buy). Size 0.5 SOL, fill_pen 1.5%.
# Variants (path after our insert): v0 as on chain, no slip | v1 + followers' own slippage limits (rp slip) |
#         v2 = v1 without FiFawH's trades after our insert (when it is not already ahead of us) |
#         v3 = v1 without ALL fast snipers' trades after our insert (fast_snipers.json; incl. FiFawH) |
#         v4 = v1 without the top-10 most frequent after-us buyers of that set+mode | v5 = v3 + v4.
# Also per launch: generic follow-on demand (distinct non-sniper, non-insider buyers and their SOL in 0-2 s / 2-10 s / 10-60 s).
import sys, os, json, gzip, glob, zlib, collections, math, pickle
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core"); import rp
from multiprocessing import Pool
D = "/home/moiz/sniper-data/collect"; PA = {"R1": "phaseA", "R2": "phaseA_fwd"}
W = "FiFawHqxeTVBhv6YbqbLwDVuvokRpPUM1bNwAyxhGc6W"; B = 0.5; SLOT = 0.212
EX = [rp.R("eos1", [(1.0, ("slot", 1))], 5), rp.R("t1", [(1.0, ("t", 1.0))], 2), rp.R("t2", [(1.0, ("t", 2.0))], 3),
      rp.R("t5", [(1.0, ("t", 5.0))], 6), rp.R("t10", [(1.0, ("t", 10.0))], 11)]
EXW = {"eos1": None, "t1": 1.0, "t2": 2.0, "t5": 5.0, "t10": 10.0}
MODES = ["L45", "L75", "D0.15", "D1", "D2", "D5"]
L = rp.load_launches(); SETS = json.load(open("sets.json"))["sets"]
SIM = set().union(*map(set, SETS.values()))
FAST = set(json.load(open("fast_snipers.json"))["wallets"]); FAST.add(W)
O = SL = None
def init():
    global O, SL
    O = rp.load_obs(); SL = rp.load_slip()
def read(run, b, mints):
    out = collections.defaultdict(list); seen = set()
    for f in glob.glob(os.path.join(D, PA[run], f"b{b:03d}", "*.jsonl.gz")):
        try:
            for line in gzip.open(f, "rt"):
                if line[2] != "T": continue
                m = line[6:line.index('"', 6)]
                if m not in mints: continue
                r = json.loads(line)
                (_, _, s, i, bt, sig, payer, fee, cup, cul, cu, tips, err, j, user, buy, sol, tok, vsol, vtok, fl, cfl, fbps, cbps) = r
                if err or (sig, j) in seen: continue
                seen.add((sig, j))
                out[m].append(dict(s=s, i=i, j=j, sig=sig, payer=payer, user=user, buy=buy == 1, sol=sol, tok=tok, vsol=vsol, vtok=vtok, fbps=fbps or 95, cbps=cbps or 30))
        except (EOFError, OSError, zlib.error, ValueError): pass
    for m in out: out[m].sort(key=lambda t: (t["s"], t["i"], t["j"]))
    return out
def demand(tr, c, st):
    S = c["slot"]; ins = st["insiders"]; d = {}
    for nm, a, b_ in (("0_2", 0, 2), ("2_10", 2, 10), ("10_60", 10, 60)):
        g = set(); f = set(); gs = 0; gsell = 0
        for t in tr:
            el = (t["s"] - S) * SLOT
            if el < a or el >= b_ or t["user"] in ins or t["user"] == W: continue
            if t["buy"]:
                if t["user"] in FAST: f.add(t["user"])
                else: g.add(t["user"]); gs += t["sol"]
            elif t["user"] not in FAST: gsell += t["sol"]
        d[nm] = [len(g), len(f), round(gs / 1e9, 3), round(gsell / 1e9, 3)]
    return d
def place(mode, tr, c, st, failed):
    S = c["slot"]
    if mode[0] == "L":
        Lm = int(mode[1:])
        if c["run"] == "R2":
            if c["mint"] not in O: return None
            return rp.place_bo2(tr, c, st, O[c["mint"]]["outs"], Lm, failed)[0]
        return rp.place_proxy(tr, c, st, Lm)[0]
    k_land = math.floor((float(mode[1:]) + 0.4) / SLOT)
    k = next((k for k, t in enumerate(tr) if t["s"] - S > k_land), len(tr))
    return max(k, st["g_end"])
def strip(tr, idx, wallets):
    if not wallets: return tr
    ahead = {t["user"] for t in tr[:idx]}; rm = set(wallets) - ahead
    return tr[:idx] + [t for t in tr[idx:] if t["user"] not in rm]
def run_variants(tr, c, st, idx, mode, variants):
    S = c["slot"]; fee = 0.02 if mode[0] == "L" else 0.005; res = {}
    for vn, (use_slip, rm) in variants.items():
        p = strip(tr, idx, rm)
        if not p or idx > len(p): return None
        o = rp.sim(p, c, st, idx, B, EX, fee_buy_pct=fee, fill_pen=0.015, slip=SL if use_slip else None)
        if o is None: return None
        bs = max(S, p[idx - 1]["s"]) if idx > 0 else S
        r = {}
        for e, w in EXW.items():
            win = [t for t in p[idx:] if (t["s"] <= bs + 1 if w is None else (t["s"] - bs) * SLOT < w)]
            nb = sum(1 for t in win if t["buy"]) - (o[e]["slipped"] if use_slip else 0)
            r[e] = [o[e]["pnl"], nb, o[e]["slipped"] if use_slip else 0]
        res[vn] = r
    return res
def ref_price(tr, st):
    if st["g_end"] >= 1: ge = tr[st["g_end"] - 1]; return ge["vsol"] / ge["vtok"] if ge["vtok"] else None
    return 30e9 / 1.073e15
def sim_mint(m, tr, failed):
    c = dict(L[m]); c["mint"] = m; st = rp.structure(tr, c); p_b = ref_price(tr, st)
    out = dict(run=c["run"], bt=c["bt"], dep=c["user"], modes={})
    if not p_b: return out
    for mode in MODES:
        idx = place(mode, tr, c, st, failed)
        if idx is None: continue
        pr = (tr[idx - 1]["vsol"] / tr[idx - 1]["vtok"]) if idx > 0 and tr[idx - 1]["vtok"] else 30e9 / 1.073e15
        ok = (pr / p_b <= 1.01) if mode[0] == "L" else True
        d = dict(ok=ok, idx=idx, W_ahead=any(t["user"] == W for t in tr[:idx]), ahead=sum(1 for t in tr[st["g_end"]:idx] if t["user"] not in st["insiders"]))
        if ok:
            v = run_variants(tr, c, st, idx, mode, {"v0": (False, None), "v1": (True, None), "v2": (True, {W}), "v3": (True, FAST)})
            if v is None: continue
            d["v"] = v
            bs = max(c["slot"], tr[idx - 1]["s"]) if idx > 0 else c["slot"]
            d["aft"] = sorted({t["user"] for t in tr[idx:] if t["buy"] and (t["s"] - bs) * SLOT < 5.0 and t["user"] not in st["insiders"]})
        out["modes"][mode] = d
    return out
def work(job):
    run, b, mints = job
    tra = read(run, b, mints); fa = rp.read_failed(run, b, mints) if run == "R2" else {}
    res = {}; dem = {}; keep = {}
    for m, tr in tra.items():
        c = L[m]
        if "InitializeMayhemState" in (c.get("ixn") or []): continue
        st = rp.structure(tr, dict(c, mint=m))
        dem[m] = demand(tr, c, st)
        if m in SIM:
            try: res[m] = sim_mint(m, tr, fa.get(m, []))
            except Exception as e: res[m] = dict(run=c["run"], bt=c["bt"], dep=c["user"], modes={}, error=repr(e)[:120]); continue
            keep[m] = ([t for t in tr if t["s"] <= c["slot"] + 100], fa.get(m, []))
    return res, dem, keep
def work2(args):
    m, tr, failed, todo = args          # todo: [(mode, vname, wallets)]
    c = dict(L[m]); c["mint"] = m; st = rp.structure(tr, c); out = {}
    for mode, vn, wl in todo:
        idx = place(mode, tr, c, st, failed)
        if idx is None: continue
        try: v = run_variants(tr, c, st, idx, mode, {vn: (True, wl)})
        except Exception: v = None
        if v: out[(mode, vn)] = v[vn]
    return m, out
if __name__ == "__main__":
    byb = collections.defaultdict(set)
    for m in SIM:
        if m in L: byb[(L[m]["run"], rp.bucket(m))].add(m)
    jobs = [(run, b, ms) for (run, b), ms in sorted(byb.items())]
    RES = {}; DEM = {}; KEEP = {}
    with Pool(8, initializer=init) as p:
        for i, (r, d, k) in enumerate(p.imap_unordered(work, jobs)):
            RES.update(r); DEM.update(d); KEEP.update(k)
            if i % 100 == 0: print("pass1", i, "/", len(jobs), flush=True)
    # top-10 after-us buyers per set and mode (over that set's fills)
    TOP = {}
    for sn, ms in SETS.items():
        for mode in MODES:
            cnt = collections.Counter(u for m in ms if m in RES and mode in RES[m]["modes"] and "aft" in RES[m]["modes"][mode] for u in RES[m]["modes"][mode]["aft"])
            TOP[(sn, mode)] = [u for u, _ in cnt.most_common(10)]
    # pass 2: v4 / v5 per set (the same launch can be in several sets with different top-10 lists)
    jobs2 = []
    for m, (tr, fl) in KEEP.items():
        todo = []
        for sn, ms in SETS.items():
            if m not in set(ms): continue
            for mode in MODES:
                if mode in RES[m]["modes"] and "v" in RES[m]["modes"][mode]:
                    t10 = set(TOP[(sn, mode)]); todo += [(mode, f"v4|{sn}", t10), (mode, f"v5|{sn}", t10 | FAST)]
        if todo: jobs2.append((m, tr, fl, todo))
    with Pool(8, initializer=init) as p:
        for i, (m, o) in enumerate(p.imap_unordered(work2, jobs2, chunksize=8)):
            for (mode, vn), v in o.items(): RES[m]["modes"][mode]["v"][vn] = v
    json.dump(dict(res=RES, demand=DEM, top10={f"{k[0]}|{k[1]}": v for k, v in TOP.items()}), open("q6_res.json", "w"))
    print("done: simulated", len(RES), "demand rows", len(DEM))
