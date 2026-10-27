#!/usr/bin/env python3
# haqq SELL study, step 18: haqq-style exits replayed on OUR live fills (FRA 2g7rYv7y, AMS EgxfYgEb; runs 9+ with tapes in the
# recording). For each fill: the curve replayed with our own sell removed; our exit vs haqq's exits, sell landing L = 35/50/75 ms
# after the decision (block-position time proxy). Costs: our real buy cost (spend + buy fee + tips), one sell tx 0.000605 SOL.
#   OURS-1.3s   our rule: sell decided 5 slots after the buy slot (= the live time limit; SL -10% included)
#   HAQQ-dist   expected value if our exit slot followed haqq's hold distribution for 0.30 / 0.40 SOL lots (TRAIN lots)
#   HAQQ-H      fixed holds 15 / 20 / 30 slots after the dump slot (its common timer values)
#   HAQQ-model  its FULL hazard model, causal: sell at the first slot whose hazard >= tau (as a 0.40 lot), features from our tape
import sys, json, glob, pickle, zlib, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H, h_gbdt as G
SS = {}
for run in ("R1", "R2", "R3", "R4"):
    for k, v in json.load(open(f"{H.OUT}/slotmax_{run}.json")).items(): SS[int(k)] = max(SS.get(int(k), 0), v + 1)
def A(s, i): return s * H.SMS + i / max(SS.get(s, 400), i + 1) * H.SMS
WAL = {"FRA": "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "AMS": "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
SELL_TX = 0.000605e9; DM = 210; LATS = (35, 50, 75)
MOD = pickle.load(open(f"{H.OUT}/h13b_models.pkl", "rb"))["FULL"]; TAU = pickle.load(open(f"{H.OUT}/h20_tau.pkl", "rb"))["FULL"]   # causal: first slot with hazard >= TAU; FEATS = json.load(open(f"{H.OUT}/ds_meta.json"))["feats"]
lots = json.load(open(f"{H.OUT}/lots.json")); pnl_rows = pickle.load(open(f"{H.OUT}/pnl_rows.pkl", "rb"))
HD = {}
for pf in ("C.30", "D.40"):
    a = [min(r["act"], DM) for r in pnl_rows if r["pf"] == pf and r["run"] in ("R1", "R2") and r["dip"]]
    if len(a) < 300: a = [min(r["act"], DM) for r in pnl_rows if r["pf"] == pf and r["dip"]]
    h = np.bincount(np.clip(a, 0, DM), minlength=DM + 1).astype(float); HD[pf] = h / h.sum()
fills = []
for f in sorted(glob.glob("/home/moiz/sniper-data/runs/fra/runs/dip_r*.jsonl") + glob.glob("/home/moiz/sniper-data/runs/ams/runs/dip_ams_r*.jsonl")):
    srv = "AMS" if "ams" in f else "FRA"; run = int(f.split("_r")[-1].split(".")[0])
    if run < 9: continue
    lands = {}; closes = []
    for l in open(f):
        try: r = json.loads(l)
        except Exception: continue
        if r.get("ev") == "buy_land": lands[r["sig"]] = r
        elif r.get("ev") == "close" and r.get("result") == "sold": closes.append(r)
    for c in closes:
        bl = lands.get(c["buy_sig"]) or next((x for x in lands.values() if x["mint"] == c["mint"]), None)
        if bl: fills.append(dict(srv=srv, run=run, c=c, bl=bl))
print("our sold fills (runs 9+):", len(fills), collections.Counter(f["srv"] for f in fills))
def feats_rows(T, Wl, k, q, cost, ref, own_sells, trig, prof_id, size):
    """slot aggregates + h12 feature rows for d = bslot+1 .. DM (state up to the end of slot d-1), our own sell removed from the curve"""
    s = T[:, 0]; bs = int(s[k] - ref)
    D = DM; re = np.full(D + 1, np.nan); ob = np.zeros(D + 1); os_ = np.zeros(D + 1); nb = np.zeros(D + 1); ns = np.zeros(D + 1); mb = np.zeros(D + 1); ms = np.zeros(D + 1); own = np.zeros(D + 1); ntr = np.zeros(D + 1)
    V = float(T[k, 9]); Tk = float(T[k, 10]); fr = (T[k, 13] + T[k, 14]) / 1e4
    re[bs] = V * q / (Tk + q) * (1 - fr) / cost - 1
    for j in range(k + 1, len(T)):
        dd = int(s[j] - ref)
        if dd > D: break
        if j in own_sells: continue
        if T[j, 6]: x = float(T[j, 7]); V, Tk = V + x, Tk - Tk * x / (V + x)
        else: tq = float(T[j, 8]); so = V * tq / (Tk + tq); V, Tk = V - so, Tk + tq
        fr = (T[j, 13] + T[j, 14]) / 1e4; re[dd] = V * q / (Tk + q) * (1 - fr) / cost - 1; ntr[dd] += 1
        if T[j, 6]: ob[dd] += T[j, 7] / 1e9; nb[dd] += 1; mb[dd] = max(mb[dd], T[j, 7] / 1e9)
        else: os_[dd] += T[j, 7] / 1e9; ns[dd] += 1; ms[dd] = max(ms[dd], T[j, 7] / 1e9)
    last = re[bs]
    for dd in range(bs, D + 1):
        if np.isnan(re[dd]): re[dd] = last
        else: last = re[dd]
    rows = []; ds = []; peak = -9.0; mn = 9.0; last_b = last_b03 = last_s03 = last_tr = bs
    for d in range(bs + 1, D + 1):
        j = d - 1; r = float(re[j]); peak = max(peak, r); mn = min(mn, r)
        if j > bs:
            if ob[j] > 0 or os_[j] > 0: last_tr = j
            if mb[j] >= 0.1: last_b = j
            if mb[j] >= 0.3: last_b03 = j
            if ms[j] >= 0.3: last_s03 = j
        w = lambda a, n: float(a[max(bs + 1, j - n + 1):j + 1].sum())
        rch = lambda n: float(r - re[max(bs, j - n)])
        row = [d, d - bs, d % 8, d % 5, prof_id, size, 1, trig["sol"], trig["drop"], trig["age"], trig["vsol"], trig["delay"], 0,
               r, peak, mn, peak - r, rch(1), rch(4), rch(8), w(ob, 1), w(ob, 2), w(ob, 4), w(ob, 8), w(nb, 1), w(nb, 4), w(nb, 8), w(os_, 1), w(os_, 4), w(os_, 8), w(ns, 4), w(ns, 8),
               float(ob[bs + 1:j + 1].sum()), float(os_[bs + 1:j + 1].sum()), float(nb[bs + 1:j + 1].sum()), j - last_b, j - last_b03, j - last_s03, j - last_tr,
               float(mb[max(bs + 1, j - 3):j + 1].max()) if j > bs else 0.0, float(ms[max(bs + 1, j - 3):j + 1].max()) if j > bs else 0.0, w(own, 4), w(ntr, 4), trig["hour"]]
        rows.append(row); ds.append(d)
    return np.array(rows, np.float32), np.array(ds), bs
out = []
for fx in fills:
    c = fx["c"]; bl = fx["bl"]; m = c["mint"]; wal = WAL[fx["srv"]]
    b = zlib.crc32(m.encode()) % 64
    d = pickle.load(open(f"{H.OUT}/tp/b{b:02d}.pkl", "rb")).get(m)
    if d is None: continue
    T = d["T"]; Wl = d["W"]; users = [Wl[x] for x in T[:, 5]]
    k = next((j for j in range(len(T)) if users[j] == wal and T[j, 6] and T[j, 0] == bl["slot"] and T[j, 1] == bl["idx"]), None)
    if k is None: continue
    ref = c["dump_slot"]
    kd = next((j for j in range(k - 1, -1, -1) if T[j, 0] == ref and T[j, 1] == c.get("dump_idx")), None)
    own = {j for j in range(k + 1, len(T)) if users[j] == wal and not T[j, 6]}
    q = float(T[k, 8]); cost = (c["spend"] + bl.get("fee", 505000) + (c.get("tips") or 0)) / 1e9 if False else (float(T[k, 7]) + float(T[k, 11]) + float(T[k, 12]) + float(T[k, 15]) + float(T[k, 19])) / 1e9
    # replay values at L ms after (ref + d) x 212
    V = float(T[k, 9]); Tk = float(T[k, 10]); fr = (T[k, 13] + T[k, 14]) / 1e4
    ev = [(A(int(T[k, 0]), int(T[k, 1])), V, Tk, fr)]
    for j in range(k + 1, len(T)):
        a = A(int(T[j, 0]), int(T[j, 1]))
        if a > (ref + DM + 1) * H.SMS + 100: break
        if j in own: continue
        if T[j, 6]: x = float(T[j, 7]); V, Tk = V + x, Tk - Tk * x / (V + x)
        else: tq = float(T[j, 8]); so = V * tq / (Tk + tq); V, Tk = V - so, Tk + tq
        ev.append((a, V, Tk, (T[j, 13] + T[j, 14]) / 1e4))
    ar = np.array([e[0] for e in ev]); val = np.array([(e[1] * q / (e[2] + q) * (1 - e[3]) - SELL_TX) / 1e9 for e in ev])
    vL = {}
    for L in (0,) + LATS:
        t = (ref + np.arange(DM + 1)) * H.SMS + L; jj = np.searchsorted(ar, t, side="right") - 1
        vL[L] = np.where(jj >= 0, val[np.maximum(jj, 0)], np.nan) - cost
    bs = int(T[k, 0] - ref)
    trig = dict(sol=float(T[kd, 7]) / 1e9 if kd is not None else 1.5, drop=0.1, age=(int(T[k, 0]) - 0) * 0 + 5.0, vsol=float(T[k, 9] - T[k, 7]) / 1e9,
                delay=A(int(T[k, 0]), int(T[k, 1])) - (A(int(T[kd, 0]), int(T[kd, 1])) if kd is not None else A(ref, 0)), hour=H.pkth(c["land"][2] / 1e9) if c.get("land") else 12)
    if kd is not None:
        pre = (T[kd, 9] + T[kd, 7]) / max(1, (T[kd, 10] - T[kd, 8])); trig["drop"] = float(1 - (T[kd, 9] / T[kd, 10]) / pre)
    real = (c["sell_land"][3] - 0) / 1e9 if c.get("sell_land") else None
    real_net = None
    if c.get("sell_land"):
        ks = next((j for j in sorted(own) if T[j, 0] == c["sell_land"][0]), None)
        if ks is not None: real_net = (float(T[ks, 7]) - float(T[ks, 11]) - float(T[ks, 12]) - float(T[ks, 15]) - float(T[ks, 19])) / 1e9 - cost
    rec = dict(srv=fx["srv"], run=fx["run"], mint=m, bs=bs, real=real_net, why=c.get("exit_why"), held=c["sell_land"][0] - bl["slot"] if c.get("sell_land") else None)
    for L in LATS:
        dd = min(bs + 5, DM)
        # our rule = SL -10% (value known at any slot end) or the 5-slot time limit, whichever first
        v_end = vL[0]; sl_d = next((x for x in range(bs + 1, bs + 6) if not np.isnan(v_end[x - 1]) and v_end[x - 1] / cost <= -0.10), None)
        rec[f"ours_{L}"] = float(vL[L][sl_d if sl_d else dd])
        for pf in ("C.30", "D.40"):
            h = HD[pf].copy(); h[:bs + 1] = 0; h /= h.sum(); v = vL[L]; ok = ~np.isnan(v)
            rec[f"hdist_{pf}_{L}"] = float(np.sum(h[ok] * v[ok]) / h[ok].sum())
        for Hh in (15, 20, 30):
            rec[f"h{Hh}_{L}"] = float(vL[L][max(Hh, bs + 1)])
    for pid, size, lab in ((3, 0.4, "D.40"), (2, 0.3, "C.30")):
        Xr, ds, _ = feats_rows(T, Wl, k, q, cost * 1e9, ref, own, trig, pid, size)
        p = G.predict(MOD["trees"], MOD["F0"], G.apply_edges(Xr, MOD["edges"]), MOD["lr"])
        jj = np.flatnonzero(p >= TAU); dm = int(ds[jj[0]]) if len(jj) else DM
        rec[f"model_{lab}_d"] = dm
        for L in LATS: rec[f"model_{lab}_{L}"] = float(vL[L][min(dm, DM)])
    out.append(rec)
json.dump(out, open(f"{H.OUT}/ours_replay.json", "w"))
print("replayed fills:", len(out), collections.Counter(r["srv"] for r in out), "| real P&L (curve, fees in) of these fills:", round(sum(r["real"] for r in out if r["real"] is not None), 4))
cols = ["ours", "hdist_C.30", "hdist_D.40", "h15", "h20", "h30", "model_D.40", "model_C.30"]
print(f"\n{'exit':14s} " + " ".join(f"{L:>14d}ms" for L in LATS))
for cname in cols:
    print(f"{cname:14s} " + " ".join(f"{sum(r[f'{cname}_{L}'] for r in out):+10.4f} ({np.mean([r[f'{cname}_{L}'] > 0 for r in out]):3.0%})" for L in LATS))
print("\nby server (35 ms):", {s: {cname: round(sum(r[f'{cname}_35'] for r in out if r['srv'] == s), 4) for cname in ("ours", "hdist_D.40", "h20", "model_D.40")} for s in ("FRA", "AMS")})
print("model exit slots (D.40 / C.30):", collections.Counter(r["model_D.40_d"] for r in out).most_common(8), collections.Counter(r["model_C.30_d"] for r in out).most_common(8))
