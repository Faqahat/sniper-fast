#!/usr/bin/env python3
# SELECTION study of FiFawH (READ-ONLY, offline). Step 1: build one row per collected launch in the attempt window with
# features (feature table), deployer history (from the collected launches), FiFawH attempt labels, and outcome price
# multiples. For every attempted launch (+ a random control sample) the price path is REPLAYED from the chain trades
# (phase-A buckets) WITH and WITHOUT FiFawH's own trades (its buys are ~1.5-2 SOL and lift the price ~10%), and the
# with-FiFawH replay is checked against the feature-table values (same definitions as select/b_launch.py).
# Price multiples are relative to P0 = price right after the dev's glued bundle (create tx buy + consecutive buy txs).
# out: sel_dataset.jsonl.gz, s1_build.log
import sys, os, json, gzip, glob, random, collections, statistics, datetime
from multiprocessing import Pool
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core"); import rp
OUT = "/home/moiz/sniper/ops/overnight/fifaw/selection"
W = "FiFawHqxeTVBhv6YbqbLwDVuvokRpPUM1bNwAyxhGc6W"
D = "/home/moiz/sniper-data/collect"; PA = {"R1": ["phaseA"], "R2": ["phaseA_fwd"]}
CK = {"slot": 0, "1s": 5, "5s": 25, "15s": 75, "30s": 150, "60s": 300, "2m": 600, "10m": 2860}
FEAT = ["S", "bt", "creator", "payer", "name", "symbol", "uri", "uri_host", "quote_sol", "mayhem", "dev_buy", "glued_n", "glued_wallets", "glued_sol",
        "glued_same_payer", "glued_payer_is_creator", "P0_mc_sol", "cr_prior_n", "cr_prior_fail", "cr_age_s", "cr_last_tx_s", "funder", "fund_amt",
        "cr_recent_creates", "cr_same_name_before", "has_tw", "has_tg", "has_web", "tw_status", "tw_community", "web_host", "img_host", "created_on",
        "show_name", "meta_ok", "desc_len", "meta_keys", "hour_utc", "name_len", "sym_len", "name_upper", "name_digits", "name_nonascii", "sym_eq_name",
        "payer_is_creator", "create_variant", "create_ixn", "create_fee", "create_idx", "create_cup", "create_tips", "create_cu", "create_cul", "fp",
        "heat_launches_10m", "wave_name_10m", "wave_name_60m", "wave_sym_60m", "cr_creates_window", "cr_min_since_prev_create", "fd_creators_so_far",
        "fd_is_creator", "dev_share", "bundle_avg", "h_cr_n", "h_cr_wins", "h_fd_n", "h_name_n", "h_bund_seen", "h_bund_launches", "n_trades", "no_trades"]
OUTC = ["fslot_px", "f1s_px", "f5s_px", "f15s_px", "px_2s", "px_5s", "px_15s", "px_30s", "px_60s", "px_2m", "px_5m", "px_10m", "peak_px", "peak_10m",
        "max_vsol", "graduated", "migrated", "fslot_nb", "fslot_ub", "f1s_nb", "f1s_ub", "f5s_nb", "slot_buys", "slot_buyers", "slot_buy_sol",
        "dev_sell_first_slot", "dev_sold_all_slot", "y_dump5", "y_good", "y_fast", "fslot_dev_sold", "fslot_bundle_sold", "f1s_dev_sold",
        "f1s_bundle_sold", "f5s_dev_sold", "f5s_bundle_sold", "vol_sol"]

def load_table():
    T = {}
    for l in gzip.open(os.path.join(D, "paper", "table_dump.jsonl.gz"), "rt"):
        r = json.loads(l); T[r["mint"]] = {k: r.get(k) for k in FEAT + OUTC}
    return T

def read_mints(args):
    run, b, mints = args
    out = collections.defaultdict(list); seen = set()
    for pa in PA[run]:
        for f in glob.glob(os.path.join(D, pa, f"b{b:03d}", "*.jsonl.gz")):
            try:
                for line in gzip.open(f, "rt"):
                    if line[2] != "T": continue
                    m = line[6:line.index('"', 6)]
                    if m not in mints: continue
                    r = json.loads(line)
                    (_, _, s, i, bt, sig, payer, fee, cup, cul, cu, tips, err, j, user, buy, sol, tok, vsol, vtok, fl, cfl, fbps, cbps) = r
                    if err or (sig, j) in seen: continue
                    seen.add((sig, j))
                    out[m].append(dict(s=s, i=i, j=j, sig=sig, user=user, buy=buy == 1, sol=sol, tok=tok, vsol=vsol, vtok=vtok))
            except (EOFError, OSError, ValueError): pass
    for m in out: out[m].sort(key=lambda t: (t["s"], t["i"], t["j"]))
    return dict(out)

def path_metrics(tr, c):
    """with-W (recorded states) and ex-W (replayed without W's trades) price multiples vs P0 at checkpoints"""
    st = rp.structure(tr, c); gi = st["g_end"]; S = c["slot"]
    if gi > 0: V0, T0 = tr[gi - 1]["vsol"], tr[gi - 1]["vtok"]
    else: V0, T0 = 30_000_000_000, 1_073_000_000_000_000          # no dev buy / bundle: initial curve
    if not V0 or not T0: return None
    P0 = V0 / T0
    res = {}
    # "w": recorded states (as on chain, incl. FiFawH's own trades)
    # "x": world without FiFawH, DELTA method (robust to the collector's few missing trades): k = V*T is constant on the
    #      curve, so price = V^2/k and the multiple vs P0 = (V/V0)^2. Others' buys add the recorded SOL change; others'
    #      sells remove the recorded SOL change scaled by (Vx/Vw)^2 (same tokens sold at a different price); FiFawH's
    #      own buys/sells are skipped.
    # "r": plain constant-product replay without FiFawH (cross-check of "x")
    for tag in ("w", "x", "r"):
        V, T = V0, T0; Vw = V0; px = {}; pk = 1.0; maxv = V0; hi = 0; ck = sorted(CK.items(), key=lambda x: x[1])
        mult = lambda V, T: (V / V0) ** 2 if tag == "x" else (V / T) / P0
        for t in tr[gi:]:
            d = t["s"] - S
            while hi < len(ck) and d > ck[hi][1]: px[ck[hi][0]] = mult(V, T); hi += 1
            if tag == "x":
                if not t["vsol"]: break
                dv = t["vsol"] - Vw; Vprev_w = Vw; Vw = t["vsol"]
                if t["user"] == W: continue
                V = V + dv if t["buy"] else V + dv * (V / Vprev_w) ** 2
                T = 1
            elif tag == "r":
                if t["user"] == W: continue
                if t["buy"]: dd = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= dd
                else: so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
                if T <= 0: break
            else:
                V, T = t["vsol"], t["vtok"]
                if not T: break
            maxv = max(maxv, V)
            if d <= 2860: pk = max(pk, mult(V, T))
        for nm, _ in ck[hi:]: px[nm] = mult(V, T) if T > 0 else None
        res[tag] = dict(px=px, peak_10m=pk, max_vsol=maxv / 1e9)
    # replay fidelity: one-step replay from the previous recorded state must give the next recorded state
    bad = 0; n = 0; prev = tr[gi - 1] if gi > 0 else dict(vsol=V0, vtok=T0)
    for t in tr[gi:]:
        if not t["vsol"] or not prev["vsol"]: break
        V, T = prev["vsol"], prev["vtok"]
        if t["buy"]: V += t["sol"]
        else: V -= V * t["tok"] // (T + t["tok"])
        n += 1; bad += abs(V / t["vsol"] - 1) > 1e-6; prev = t
    me = [t for t in tr if t["user"] == W]
    mb = [t for t in me if t["buy"]]; ms = [t for t in me if not t["buy"]]
    w_info = dict(buy_s=(mb[0]["s"] - S) if mb else None, buy_i=mb[0]["i"] if mb else None, buy_sol=sum(t["sol"] for t in mb) / 1e9,
                  sell_s=(ms[0]["s"] - S) if ms else None, last_sell_s=(ms[-1]["s"] - S) if ms else None,
                  n_before=sum(1 for t in tr[gi:] if mb and (t["s"], t["i"]) < (mb[0]["s"], mb[0]["i"]) and t["user"] not in st["insiders"] and t["buy"]))
    return dict(gi=gi, glued=len(st["glued"]), w=res["w"], x=res["x"], r=res["r"], rep_bad=bad, rep_n=n, me=w_info)

if __name__ == "__main__":
    log = open(os.path.join(OUT, "s1_build.log"), "w")
    def P(*a):
        s = " ".join(str(x) for x in a); print(s); log.write(s + "\n"); log.flush()
    L = rp.load_launches()
    A = json.load(open("/home/moiz/sniper/ops/overnight/core/attempts_fifaw.json"))
    ST = json.load(open(os.path.join(OUT, "att_status.json")))
    T = load_table()
    P("launches", len(L), "table", len(T), "attempts", len(A))
    lo = min(L[m]["bt"] for m in A); hi = max(L[m]["bt"] for m in A)
    P("window", datetime.datetime.fromtimestamp(lo, datetime.UTC), "->", datetime.datetime.fromtimestamp(hi, datetime.UTC))
    # trade-file coverage end per run (for 10-min outcomes)
    cov_end = {}
    for run, pas in PA.items():
        ts = [int(os.path.basename(f)[4:-9]) for pa in pas for f in glob.glob(os.path.join(D, pa, "b000", "*.jsonl.gz"))]
        cov_end[run] = max(ts) + 300
    P("trade coverage end", {k: str(datetime.datetime.fromtimestamp(v, datetime.UTC)) for k, v in cov_end.items()})
    # deployer history over ALL collected launches (both runs, non-err), in time order
    allL = sorted((c for c in L.values() if not c.get("err") and c.get("bt")), key=lambda c: (c["bt"], c["slot"], c.get("idx") or 0))
    tot_sig = collections.Counter(c["user"] for c in allL); tot_cr = collections.Counter(c.get("creator") or c["user"] for c in allL)
    seen_sig = collections.Counter(); att_sig = collections.Counter(); prev_bt = {}
    hist = {}
    for c in allL:
        u = c["user"]; m = c["mint"]
        hist[m] = dict(dep_total=tot_sig[u], dep_prior=seen_sig[u], dep_prior_att=att_sig[u], cr_total=tot_cr[c.get("creator") or u],
                       dep_gap_min=((c["bt"] - prev_bt[u]) / 60) if u in prev_bt else None, signer_is_creator=int(u == (c.get("creator") or u)))
        seen_sig[u] += 1; prev_bt[u] = c["bt"]
        if m in A: att_sig[u] += 1
    # population = table rows in window
    pop = [m for m, r in T.items() if r["bt"] and lo <= r["bt"] <= hi]
    P("population (table rows in window)", len(pop), "attempted in pop", sum(1 for m in pop if m in A))
    # replay set: attempted + random controls
    random.seed(7)
    ctrl = set(random.sample([m for m in pop if m not in A and (T[m].get("n_trades") or 0) > 0], 3000))
    rset = set(A) | ctrl
    byb = collections.defaultdict(set)
    for m in rset: byb[(L[m]["run"], rp.bucket(m))].add(m)
    jobs = [(run, b, ms) for (run, b), ms in sorted(byb.items())]
    TR = {}
    with Pool(10) as p:
        for o in p.imap_unordered(read_mints, jobs): TR.update(o)
    P("replayed mints with trades", len(TR), "of", len(rset))
    REP = {}
    for m, tr in TR.items():
        r = path_metrics(tr, L[m])
        if r: REP[m] = r
    # validation: with-W replay vs table (attempted + controls with P0 defined and SOL quote)
    for grp, ms in (("attempted", [m for m in A if m in REP]), ("controls", [m for m in ctrl if m in REP])):
        dif = collections.defaultdict(list)
        for m in ms:
            t = T[m]
            if not t.get("quote_sol") or not t.get("P0_mc_sol"): continue
            for k_tab, k_rep in (("fslot_px", "slot"), ("f1s_px", "1s"), ("f5s_px", "5s"), ("f15s_px", "15s"), ("px_30s", "30s"), ("px_60s", "60s")):
                if t.get(k_tab) is not None and REP[m]["w"]["px"].get(k_rep) is not None:
                    dif[k_tab].append(abs(REP[m]["w"]["px"][k_rep] / t[k_tab] - 1) < 1e-4)
            if t.get("peak_10m") is not None: dif["peak_10m(max1)"].append(abs(REP[m]["w"]["peak_10m"] / max(1.0, t["peak_10m"]) - 1) < 1e-4)
            dif["max_vsol"].append(abs(REP[m]["w"]["max_vsol"] - t["max_vsol"]) < 1e-3)
        P("validation", grp, {k: f"{sum(v)}/{len(v)} match" for k, v in dif.items()})
    rb = sum(r["rep_bad"] for r in REP.values()); rn = sum(r["rep_n"] for r in REP.values())
    P("one-step replay fidelity: state mismatches", rb, "of", rn, "trades")
    for grp, ms in (("attempted", [m for m in A if m in REP]), ("controls", [m for m in ctrl if m in REP])):
        P("  ", grp, "mismatch", sum(REP[m]["rep_bad"] for m in ms), "of", sum(REP[m]["rep_n"] for m in ms))
    # x (delta) vs r (plain replay) agreement on attempted, and x == w on controls (no FiFawH trades there)
    for k in ("1s", "5s", "15s", "60s"):
        a = [abs(REP[m]["x"]["px"][k] / REP[m]["r"]["px"][k] - 1) for m in A if m in REP and REP[m]["x"]["px"].get(k) and REP[m]["r"]["px"].get(k) and T[m].get("quote_sol") and T[m].get("P0_mc_sol")]
        a.sort(); c2 = [abs(REP[m]["x"]["px"][k] / REP[m]["w"]["px"][k] - 1) for m in ctrl if m in REP and REP[m]["x"]["px"].get(k) and REP[m]["w"]["px"].get(k)]
        c2.sort()
        P(f"  {k}: attempted |x/r-1| median {a[len(a)//2]:.2e} p90 {a[int(.9*(len(a)-1))]:.2e} max {a[-1]:.2e} | controls |x/w-1| p99 {c2[int(.99*(len(c2)-1))]:.2e}")
    # write dataset
    n = 0
    with gzip.open(os.path.join(OUT, "sel_dataset.jsonl.gz"), "wt") as fo:
        for m in pop:
            t = dict(T[m]); c = L[m]
            t["mint"] = m; t["run"] = c["run"]; t["signer"] = c["user"]; t["creator_l"] = c.get("creator") or c["user"]
            t.update(hist.get(m, {}))
            a = A.get(m, {}).get("FiFawH"); s = ST.get(m)
            t["att"] = int(a is not None); t["att_filled"] = a[0] if a else None; t["att_off"] = a[1] if a else None
            t["snipe"] = int(a is not None and a[1] <= 5)
            t["out_ok"] = int(bool(t.get("quote_sol")) and bool(t.get("P0_mc_sol")))
            t["cov10m"] = int(t["bt"] + 620 <= cov_end[c["run"]])
            if m in REP:
                R = REP[m]; t["rep"] = 1
                for k, v in R["x"]["px"].items(): t[f"x_{k}"] = v
                for k, v in R["w"]["px"].items(): t[f"w_{k}"] = v
                t["x_peak_10m"] = R["x"]["peak_10m"]; t["x_max_vsol"] = R["x"]["max_vsol"]; t["w_peak_10m"] = R["w"]["peak_10m"]; t["w_max_vsol"] = R["w"]["max_vsol"]
                for k, v in R["r"]["px"].items(): t[f"r_{k}"] = v
                t["r_peak_10m"] = R["r"]["peak_10m"]; t["rep_bad"] = R["rep_bad"]; t["rep_n"] = R["rep_n"]
                t["me"] = R["me"]
            fo.write(json.dumps(t, separators=(",", ":")) + "\n"); n += 1
    P("rows written", n)
