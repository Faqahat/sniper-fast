#!/usr/bin/env python3
# haqq SELL study, step 19: haqq-style exits vs our 1.3 s exit on our engine's IMIT1 shadow picks (every dump the live engine scored
# as a buy, FRA + AMS runs 9+, deduped). Hypothetical 0.35 SOL buy landing 40 ms after the dump (block-position proxy), skipped if the
# price is > 5% above the post-dump price (our guard). Exits land L = 35/50/75 ms after the decision. Costs: buy 0.0015 (priority +
# tip), sell 0.000605. Curve replay with our buy inserted (others' buys = SOL in, sells = tokens out).
import sys, json, glob, pickle, zlib, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H, h_gbdt as G
SS = {}
for run in ("R1", "R2", "R3", "R4"):
    for k, v in json.load(open(f"{H.OUT}/slotmax_{run}.json")).items(): SS[int(k)] = max(SS.get(int(k), 0), v + 1)
def A(s, i): return s * H.SMS + i / max(SS.get(s, 400), i + 1) * H.SMS
B_SOL = 0.35e9; BUY_C = 0.0015e9; SELL_C = 0.000605e9; DM = 210; LATS = (35, 50, 75); LAND = 40.0
MOD = pickle.load(open(f"{H.OUT}/h13b_models.pkl", "rb"))["FULL"]; TAU = pickle.load(open(f"{H.OUT}/h20_tau.pkl", "rb"))["FULL"]   # causal: first slot with hazard >= TAU
pnl_rows = pickle.load(open(f"{H.OUT}/pnl_rows.pkl", "rb"))
HD = {}
for pf in ("C.30", "D.40"):
    a = [min(r["act"], DM) for r in pnl_rows if r["pf"] == pf and r["run"] in ("R1", "R2") and r["dip"]]
    if len(a) < 300: a = [min(r["act"], DM) for r in pnl_rows if r["pf"] == pf and r["dip"]]
    h = np.bincount(np.clip(a, 0, DM), minlength=DM + 1).astype(float); HD[pf] = h / h.sum()
picks = {}
for f in sorted(glob.glob("/home/moiz/sniper-data/runs/fra/runs/dip_r*.jsonl") + glob.glob("/home/moiz/sniper-data/runs/ams/runs/dip_ams_r*.jsonl")):
    run = int(f.split("_r")[-1].split(".")[0])
    if run < 9: continue
    for l in open(f):
        if '"pass":true' not in l.replace(" ", ""): continue
        r = json.loads(l)
        if r.get("ev") == "dump" and r.get("pass"): picks.setdefault(r["sig"], dict(r, srv="AMS" if "ams" in f else "FRA", run=run))
by = collections.defaultdict(list)
for p in picks.values(): by[zlib.crc32(p["mint"].encode()) % 64].append(p)
out = []; miss = collections.Counter()
for b, ps in by.items():
    tp = pickle.load(open(f"{H.OUT}/tp/b{b:02d}.pkl", "rb"))
    for p in ps:
        d = tp.get(p["mint"])
        if d is None: miss["no tape"] += 1; continue
        T = d["T"]; sig = p["sig"][:16]
        kd = next((j for j, s in enumerate(d["sig"]) if s == sig), None)
        if kd is None: miss["dump not on tape"] += 1; continue
        if T[-1, 0] < T[kd, 0] + DM: miss["tape too short"] += 1; continue
        ref = int(T[kd, 0]); a_d = A(ref, int(T[kd, 1])); p_dump = T[kd, 9] / T[kd, 10]
        AR = np.array([A(int(x), int(y)) for x, y in zip(T[:, 0], T[:, 1])])
        k = int(np.searchsorted(AR, a_d + LAND, side="right"))       # we land before trade k
        V = float(T[k - 1, 9]); Tk = float(T[k - 1, 10]); fr = (T[k - 1, 13] + T[k - 1, 14]) / 1e4
        if (V / Tk) / p_dump > 1.05: miss["guard"] += 1; continue
        X = B_SOL / (1 + fr); q = Tk * X / (V + X); V += X; Tk -= q
        cost = (B_SOL + BUY_C) / 1e9
        bslot = int(T[k - 1, 0]) if k - 1 >= 0 else ref
        bslot = max(bslot, ref); bs = bslot - ref
        ev = [(a_d + LAND, V, Tk, fr)]
        re = np.full(DM + 1, np.nan); ob = np.zeros(DM + 1); os_ = np.zeros(DM + 1); nb = np.zeros(DM + 1); ns = np.zeros(DM + 1); mb = np.zeros(DM + 1); ms = np.zeros(DM + 1); ntr = np.zeros(DM + 1)
        re[bs] = (V * q / (Tk + q) * (1 - fr) - SELL_C) / 1e9 / cost - 1
        for j in range(k, len(T)):
            dd = int(T[j, 0] - ref)
            if dd > DM: break
            if T[j, 6]: x = float(T[j, 7]); V, Tk = V + x, Tk - Tk * x / (V + x)
            else: tq = float(T[j, 8]); so = V * tq / (Tk + tq); V, Tk = V - so, Tk + tq
            fr = (T[j, 13] + T[j, 14]) / 1e4; ev.append((AR[j], V, Tk, fr))
            re[dd] = (V * q / (Tk + q) * (1 - fr) - SELL_C) / 1e9 / cost - 1; ntr[dd] += 1
            if T[j, 6]: ob[dd] += T[j, 7] / 1e9; nb[dd] += 1; mb[dd] = max(mb[dd], T[j, 7] / 1e9)
            else: os_[dd] += T[j, 7] / 1e9; ns[dd] += 1; ms[dd] = max(ms[dd], T[j, 7] / 1e9)
        last = re[bs]
        for dd in range(bs, DM + 1):
            if np.isnan(re[dd]): re[dd] = last
            else: last = re[dd]
        ar = np.array([e[0] for e in ev]); val = np.array([(e[1] * q / (e[2] + q) * (1 - e[3]) - SELL_C) / 1e9 for e in ev]) - cost
        vL = {}
        for L in (0,) + LATS:
            t = (ref + np.arange(DM + 1)) * H.SMS + L; jj = np.searchsorted(ar, t, side="right") - 1
            vL[L] = np.where(jj >= 0, val[np.maximum(jj, 0)], np.nan)
        rec = dict(srv=p["srv"], run=p["run"], mint=p["mint"], bs=bs, score=p["score"])
        sl_d = next((x for x in range(bs + 1, bs + 6) if re[x - 1] <= -0.10), None)
        for L in LATS:
            rec[f"ours_{L}"] = float(vL[L][sl_d if sl_d else min(bs + 5, DM)])
            for pf in ("C.30", "D.40"):
                h = HD[pf].copy(); h[:bs + 1] = 0; h /= h.sum(); v = vL[L]; ok = ~np.isnan(v)
                rec[f"hdist_{pf}_{L}"] = float(np.sum(h[ok] * v[ok]) / h[ok].sum())
            for Hh in (6, 10, 15, 20, 30):
                rec[f"h{Hh}_{L}"] = float(vL[L][max(Hh, bs + 1)])
        # haqq FULL model (as a 0.40 lot)
        rows = []; ds = []; peak = -9.0; mn = 9.0; lb = lb3 = ls3 = lt = bs
        drop = float(1 - p_dump / ((T[kd, 9] + T[kd, 7]) / max(1, T[kd, 10] - T[kd, 8])))
        for dd in range(bs + 1, DM + 1):
            j = dd - 1; r = float(re[j]); peak = max(peak, r); mn = min(mn, r)
            if j > bs:
                if ob[j] > 0 or os_[j] > 0: lt = j
                if mb[j] >= 0.1: lb = j
                if mb[j] >= 0.3: lb3 = j
                if ms[j] >= 0.3: ls3 = j
            w = lambda a_, n: float(a_[max(bs + 1, j - n + 1):j + 1].sum())
            rch = lambda n: float(r - re[max(bs, j - n)])
            rows.append([dd, dd - bs, dd % 8, dd % 5, 3, 0.4, 1, T[kd, 7] / 1e9, drop, p.get("age", 5.0), (T[k - 1, 9]) / 1e9, LAND, 0, r, peak, mn, peak - r, rch(1), rch(4), rch(8),
                         w(ob, 1), w(ob, 2), w(ob, 4), w(ob, 8), w(nb, 1), w(nb, 4), w(nb, 8), w(os_, 1), w(os_, 4), w(os_, 8), w(ns, 4), w(ns, 8),
                         float(ob[bs + 1:j + 1].sum()), float(os_[bs + 1:j + 1].sum()), float(nb[bs + 1:j + 1].sum()), j - lb, j - lb3, j - ls3, j - lt,
                         float(mb[max(bs + 1, j - 3):j + 1].max()) if j > bs else 0.0, float(ms[max(bs + 1, j - 3):j + 1].max()) if j > bs else 0.0, 0.0, w(ntr, 4), H.pkth(p["t"] / 1e9)])
            ds.append(dd)
        pr = G.predict(MOD["trees"], MOD["F0"], G.apply_edges(np.array(rows, np.float32), MOD["edges"]), MOD["lr"])
        jj = np.flatnonzero(pr >= TAU); dm = int(ds[jj[0]]) if len(jj) else DM; rec["model_d"] = dm
        for L in LATS: rec[f"model_{L}"] = float(vL[L][dm])
        rec["oracle"] = float(np.nanmax(vL[35][bs + 1:]))
        out.append(rec)
json.dump(out, open(f"{H.OUT}/shadow_replay.json", "w"))
print("unique picks", len(picks), "| skipped:", dict(miss), "| replayed", len(out), collections.Counter(r["srv"] for r in out))
cols = ["ours", "h6", "h10", "h15", "h20", "h30", "hdist_C.30", "hdist_D.40", "model"]
print(f"\n{'exit (SOL total, win%)':24s} " + " ".join(f"{L:>16d} ms" for L in LATS))
for c in cols:
    print(f"{c:24s} " + " ".join(f"{sum(r[f'{c}_{L}'] for r in out):+10.3f} ({np.mean([r[f'{c}_{L}'] > 0 for r in out]):3.0%})   " for L in LATS))
print("model exit slots:", collections.Counter(r["model_d"] for r in out).most_common(10))
