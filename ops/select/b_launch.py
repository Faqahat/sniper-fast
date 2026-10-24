#!/usr/bin/env python3
# PHASE B (read-only, offline): one row per launch from its bucket of trade rows (phase A) + launches.jsonl.
#  - flags: quote (SOL / other), mayhem, create variant, dedup of resumed-run duplicates
#  - create-slot structure: dev buy, glued bundle (consecutive mint txs right after the create), every create-slot buyer
#  - early-flow features at checkpoints (end of create slot, +5 slots ~1 s, +25 ~5 s, +75 ~15 s) for delayed entries
#  - outcome paths: price multiple vs post-bundle price at horizons, peak, time of peak, volume, holders proxy
#  - RETURNS of a 0.5 SOL buy (exact bonding-curve replay of everyone else's trades, pump fee per side from the events,
#    FIX SOL fixed cost per round trip) for entries E_bundle (right after the glued bundle = best realistic case),
#    E_slot (after the whole create slot = our measured landing reality), E_1s, E_5s, E_15s and many exits
#  - first 30 outside buyers (wallet, slot offset, SOL, fee, priority price, tips) for the wallet-identity phase
# usage: python3 b_launch.py <phaseA dir> <run dir> <out dir> [procs]
import sys, os, json, gzip, glob, statistics, collections
from multiprocessing import Pool
A, RUN, OUT = sys.argv[1], sys.argv[2], sys.argv[3]; PROCS = int(sys.argv[4]) if len(sys.argv) > 4 else 14
X = 493827160; SLOT = 0.4 * 0  # slot duration is measured below from block times
HZ = {"2s": 10, "3s": 15, "5s": 25, "10s": 50, "15s": 75, "30s": 150, "60s": 300, "2m": 600, "5m": 1500, "10m": 2860}
TRAIL = [("trail30_20_s30_10m", .3, .2, 2860, .3), ("trail50_25_s30_10m", .5, .25, 2860, .3), ("trail100_40_s40_10m", 1.0, .4, 2860, .4),
         ("trail20_10_s15_2m", .2, .1, 600, .15)]
TPSL = [("tp25_sl25_60s", .25, .25, 300), ("tp50_sl30_5m", .5, .3, 1500), ("tp100_sl40_10m", 1.0, .4, 2860), ("tp20_sl10_30s", .2, .1, 150),
        ("tp30_none_2m", .3, None, 600), ("tp200_sl50_10m", 2.0, .5, 2860)]
ENTRIES = {"E_bundle": None, "E_k1": "k1", "E_k2": "k2", "E_k3": "k3", "E_slot": 0, "E_s1": 1, "E_1s": 5, "E_5s": 25, "E_15s": 75}
CK = {"slot": 0, "1s": 5, "5s": 25, "15s": 75}
L = {}
def load_launches():
    for l in open(os.path.join(RUN, "launches.jsonl")):
        try: c = json.loads(l)
        except Exception: continue
        L.setdefault(c["mint"], c)

EVX_DELAY = True   # every event exit also gets an "_eos" twin: sell at the END of the trigger slot (our sell lands ~0.1-0.2 s later)
EVX = [("sk1_10s", "nbuy", 1, 50), ("sk2_10s", "nbuy", 2, 50), ("sk3_10s", "nbuy", 3, 50), ("sk5_30s", "nbuy", 5, 150),
       ("sv1_10s", "bsol", 1e9, 50), ("sv2_10s", "bsol", 2e9, 50), ("sv5_30s", "bsol", 5e9, 150), ("fsell_30s", "fsell", 0, 150)]
def sim(trades, start, V, T, fb, cb, S, exits, outside=None):
    """our 0.5 SOL buy into state (V,T) placed before trades[start:]; returns gross return (fees per side, no fixed cost)
    for each exit; exits = list of ('h', horizon_slot) or ('tpsl', tp, sl, cap_slot)"""
    q = T * X // (V + X); V += X; T -= q
    cost = X * (1 + (fb + cb) / 1e4)
    def val(V, T):
        x = V * q // (T + q); return (x * (1 - (fb + cb) / 1e4)) / cost - 1
    res = {}; hz = sorted((e for e in exits if e[0] == "h"), key=lambda e: e[1]); hi = 0
    tp_open = [e for e in exits if e[0] == "tpsl"]; tpres = {}
    tr_open = [e for e in exits if e[0] == "trail"]; peak = {e: -1.0 for e in tr_open}
    ev_open = [e for e in exits if e[0] == "ev"]; nb_o = 0; bs_o = 0
    eos_open = [("eos",) + e[1:] for e in ev_open]; eos_trig = {}
    r0 = val(V, T); best = r0; best_d = 0; mdd_before_best = 0.0; worst = r0
    for k in range(start, len(trades)):
        t = trades[k]; d = t["s"] - S
        while hi < len(hz) and d > hz[hi][1]: res[hz[hi]] = val(V, T); hi += 1
        for e, ts in list(eos_trig.items()):        # delayed twin: first trade of a later slot -> sell at the state before it
            if t["s"] > ts: tpres[e] = val(V, T); del eos_trig[e]
        for e in tp_open[:]:
            if d > e[3]: tpres[e] = val(V, T); tp_open.remove(e)
        if t["buy"]:
            dd = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= dd
        else:
            so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
        v = val(V, T)
        if d <= 2860:
            if v > best: best = v; best_d = d; mdd_before_best = worst
            worst = min(worst, v)
        for e in tp_open[:]:
            if v >= e[1] or (e[2] is not None and v <= -e[2]): tpres[e] = v; tp_open.remove(e)
        if outside is not None and outside(t):
            if t["buy"]: nb_o += 1; bs_o += t["sol"]
        for e in ev_open[:]:                       # ('ev', kind, threshold, cap): sell right after the triggering trade (sell INTO the snipers)
            if d > e[3]: tpres[e] = v; ev_open.remove(e); continue
            if (e[1] == "nbuy" and nb_o >= e[2]) or (e[1] == "bsol" and bs_o >= e[2]) or (e[1] == "fsell" and not t["buy"]):
                tpres[e] = v; ev_open.remove(e); eos_trig[("eos",) + e[1:]] = t["s"]
        for e in tr_open[:]:                       # ('trail', arm, drop, cap, stop): arm at +arm, exit at peak-drop, hard stop, cap
            if d > e[3]: tpres[e] = v; tr_open.remove(e); continue
            peak[e] = max(peak[e], v)
            if (peak[e] >= e[1] and v <= peak[e] - e[2]) or v <= -e[4]: tpres[e] = v; tr_open.remove(e)
    for e in hz[hi:]: res[e] = val(V, T)
    for e in tp_open + tr_open + ev_open: tpres[e] = val(V, T)
    for e in eos_open:
        if e not in tpres: tpres[e] = val(V, T)
    res.update(tpres); res["now"] = r0; res["best"] = best; res["best_d"] = best_d; res["dd_before_best"] = mdd_before_best
    return res

def feats_flow(trades, k0, upto_d, S, creator, bundle_users, P0):
    """flow features over trades[k0:] with slot offset <= upto_d (outside = not creator, not bundle wallets)"""
    nb = ns = 0; bsol = ssol = 0; users = set(); maxb = 0; dev_sold = 0; bundle_sold = 0; cups = []; tips = 0; payer_ne = 0; last = None
    for t in trades[k0:]:
        if t["s"] - S > upto_d: break
        last = t
        if t["user"] == creator:
            if not t["buy"]: dev_sold += t["sol"]
            continue
        if t["user"] in bundle_users:
            if not t["buy"]: bundle_sold += t["sol"]
            continue
        if t["buy"]:
            nb += 1; bsol += t["sol"]; users.add(t["user"]); maxb = max(maxb, t["sol"])
            if t["cup"]: cups.append(t["cup"])
            tips += t["tips"]; payer_ne += t["payer"] != t["user"]
        else: ns += 1; ssol += t["sol"]
    px = (last["vsol"] / last["vtok"]) / P0 if (last and P0 and last["vtok"]) else 1.0
    return dict(nb=nb, ns=ns, bsol=bsol / 1e9, ssol=ssol / 1e9, net=(bsol - ssol) / 1e9, ub=len(users), maxb=maxb / 1e9, dev_sold=dev_sold / 1e9,
                bundle_sold=bundle_sold / 1e9, cup_med=statistics.median(cups) if cups else 0, tips=tips / 1e9, via_router=payer_ne, px=px)

def work(bdir):
    rows = collections.defaultdict(list); xrows = collections.defaultdict(list)
    for f in glob.glob(os.path.join(bdir, "*.jsonl.gz")):
        for line in gzip.open(f, "rt"):
            r = json.loads(line)
            if r[0] == "T":
                (_, m, s, i, bt, sig, payer, fee, cup, cul, cu, tips, err, j, user, buy, sol, tok, vsol, vtok, fl, cfl, fbps, cbps) = r
                rows[m].append(dict(s=s, i=i, bt=bt, sig=sig, payer=payer, fee=fee, cup=cup, cul=cul, cu=cu, tips=tips, j=j, user=user, buy=buy == 1,
                                    sol=sol, tok=tok, vsol=vsol, vtok=vtok, fbps=fbps, cbps=cbps))
            else:
                xrows[r[1]].append(r)
    out = []
    for m, tr in rows.items():
        c = L.get(m)
        if not c: continue
        seen = set(); t2 = []
        for t in sorted(tr, key=lambda t: (t["s"], t["i"], t["j"])):
            k = (t["sig"], t["j"])
            if k in seen: continue
            seen.add(k); t2.append(t)
        tr = t2; S = c["slot"]; creator = c.get("creator") or c.get("user")
        ixn = c.get("ixn") or []
        row = dict(mint=m, S=S, bt=c.get("bt"), creator=creator, payer=c.get("payer"), name=c.get("name"), symbol=c.get("symbol"), uri=c.get("uri"),
                   create_idx=c.get("idx"), create_fee=c.get("fee"), create_ixn=ixn[:3], mayhem=int("InitializeMayhemState" in ixn),
                   n_trades=len(tr), n_x=len(xrows.get(m, [])))
        sol_quote = any(t["vsol"] > 0 for t in tr)
        row["quote_sol"] = int(sol_quote)
        maxv = max((t["vsol"] for t in tr), default=0) / 1e9; row["max_vsol"] = maxv
        ct = [t for t in tr if t["sig"] == c.get("sig")]
        row["dev_buy"] = sum(t["sol"] for t in ct if t["buy"]) / 1e9
        row["create_cup"] = ct[0]["cup"] if ct else None; row["create_tips"] = ct[0]["tips"] / 1e9 if ct else None
        row["create_cu"] = ct[0]["cu"] if ct else None; row["create_cul"] = ct[0]["cul"] if ct else None
        row["graduated"] = int(maxv >= 114)
        # glued bundle: mint txs whose index follows the create tx contiguously in slot S
        ci = c.get("idx"); g = []; prev = ci; gi = 0
        for k, t in enumerate(tr):
            if t["sig"] == c.get("sig"): gi = k + 1; continue
            if t["s"] == S and t["i"] in (prev, prev + 1) and t["buy"]:
                g.append(t); prev = t["i"]; gi = k + 1
            elif t["s"] == S and t["i"] > prev + 1: break
            elif t["s"] > S: break
        busers = {t["user"] for t in g}
        row.update(glued_n=len({t["sig"] for t in g}), glued_wallets=len(busers), glued_sol=sum(t["sol"] for t in g) / 1e9,
                   glued_same_payer=int(len({t["payer"] for t in g}) == 1) if g else 0, glued_payer_is_creator=int(any(t["payer"] == creator for t in g)))
        pre = tr[gi - 1] if gi > 0 else None
        P0 = (pre["vsol"] / pre["vtok"]) if (pre and pre["vtok"]) else None
        row["P0_mc_sol"] = (pre["vsol"] * 1e6 / pre["vtok"] / 1e9) if (pre and pre["vtok"]) else None
        # create-slot buyers after the bundle
        sl = [t for t in tr[gi:] if t["s"] == S]
        row.update(slot_buys=sum(1 for t in sl if t["buy"]), slot_buy_sol=sum(t["sol"] for t in sl if t["buy"]) / 1e9,
                   slot_sells=sum(1 for t in sl if not t["buy"]), slot_buyers=len({t["user"] for t in sl if t["buy"]}))
        # early flow checkpoints
        for nm, dlt in CK.items():
            for k2, v in feats_flow(tr, gi, dlt, S, creator, busers, P0).items(): row[f"f{nm}_{k2}"] = v
        # block-time based seconds per slot for this launch (for labels only)
        # outcome path
        if sol_quote and P0 and maxv <= 200:
            px = {}; pk = 0; pk_d = 0; pk10 = 0; vol = 0; hi = 0; hzl = sorted(HZ.items(), key=lambda x: x[1])
            V = pre["vsol"]; T = pre["vtok"]
            for t in tr[gi:]:
                d = t["s"] - S
                while hi < len(hzl) and d > hzl[hi][1]: px[hzl[hi][0]] = (V / T) / P0; hi += 1
                V, T = t["vsol"], t["vtok"]; vol += t["sol"]
                if T and (V / T) / P0 > pk: pk = (V / T) / P0; pk_d = d
                if T and d <= 2860 and (V / T) / P0 > pk10: pk10 = (V / T) / P0
            for nm, _ in hzl[hi:]: px[nm] = (V / T) / P0 if T else None
            row.update({f"px_{k}": v for k, v in px.items()}); row.update(peak_px=pk, peak_slot=pk_d, peak_10m=pk10, vol_sol=vol / 1e9,
                       holders_proxy=len({t["user"] for t in tr if t["buy"]}), last_slot=tr[-1]["s"] - S)
            fb, cb = (tr[0]["fbps"] or 95), (tr[0]["cbps"] or 30)
            exits = [("h", v) for v in HZ.values()] + [("tpsl",) + x[1:] for x in TPSL] + [("trail",) + x[1:] for x in TRAIL] + [("ev",) + x[1:] for x in EVX]
            outside = lambda t: t["user"] != creator and t["user"] not in busers
            for en, dl in ENTRIES.items():
                if dl is None: k0 = gi
                elif isinstance(dl, str):          # behind the first k OUTSIDE trades after the bundle (any slot)
                    need = int(dl[1:]); k0 = gi; seen_o = 0
                    while k0 < len(tr) and seen_o < need:
                        if tr[k0]["user"] != creator and tr[k0]["user"] not in busers: seen_o += 1
                        k0 += 1
                else:
                    k0 = next((k for k in range(gi, len(tr)) if tr[k]["s"] - S > dl), len(tr))
                st = tr[k0 - 1] if k0 > 0 else pre
                if not st["vtok"]: continue
                r = sim(tr, k0, st["vsol"], st["vtok"], fb, cb, S, exits, outside)
                row[f"{en}_entry_px"] = (st["vsol"] / st["vtok"]) / P0
                dln = dl if isinstance(dl, int) else -1
                for nm, v in HZ.items():
                    if dln < v: row[f"{en}_h{nm}"] = round(r[("h", v)], 5)
                for x in TPSL:
                    if dln < x[3]: row[f"{en}_{x[0]}"] = round(r[("tpsl",) + x[1:]], 5)
                for x in TRAIL:
                    row[f"{en}_{x[0]}"] = round(r[("trail",) + x[1:]], 5)
                for x in EVX:
                    row[f"{en}_{x[0]}"] = round(r[("ev",) + x[1:]], 5); row[f"{en}_{x[0]}_eos"] = round(r[("eos",) + x[1:]], 5)
                row[f"L{en}_best"] = round(r["best"], 4); row[f"L{en}_best_d"] = r["best_d"]; row[f"L{en}_dd"] = round(r["dd_before_best"], 4)
        # first 30 outside buyers
        eb = []
        for t in tr[gi:]:
            if t["buy"] and t["user"] != creator and t["user"] not in busers:
                eb.append([t["user"], t["s"] - S, round(t["sol"] / 1e9, 4), t["cup"], round(t["tips"] / 1e9, 5), t["payer"] != t["user"]])
                if len(eb) >= 30: break
        row["early_buyers"] = eb; row["bundle_wallets"] = sorted(busers)
        row["dev_sell_first_slot"] = next((t["s"] - S for t in tr if t["user"] == creator and not t["buy"]), None)
        row["dev_sold_all_slot"] = None
        xs = xrows.get(m, [])
        row["migrated"] = int(any("Migrate" in " ".join(r[13]) for r in xs if isinstance(r[13], list)))
        out.append(row)
    fn = os.path.join(OUT, os.path.basename(bdir) + ".jsonl.gz")
    with gzip.open(fn, "wt") as f:
        for r in out: f.write(json.dumps(r, separators=(",", ":")) + "\n")
    return len(out)

if __name__ == "__main__":
    load_launches(); os.makedirs(OUT, exist_ok=True)
    bd = sorted(glob.glob(os.path.join(A, "b*")))
    n = 0
    with Pool(PROCS) as p:
        for k, c in enumerate(p.imap_unordered(work, bd), 1):
            n += c
            if k % 32 == 0: print(f"{k}/{len(bd)} buckets, {n} launches", flush=True)
    print("DONE", n, flush=True)
