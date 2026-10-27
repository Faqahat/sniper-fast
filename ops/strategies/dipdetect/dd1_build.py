#!/usr/bin/env python3
# DIPDETECT dataset (read-only, owner 10-24 ~22:45 PKT: "find a better and improved way of detecting dips", incl. dumps that did
# NOT qualify). Universe = EVERY sell that dropped the price >= 2% on a standard pump.fun bonding curve (any age / size / time
# since the last buy), in and out of the live envelope, from the day arrays (patterns/day_R1..R3.npz, dipdetect/day_R4.npz).
# Per dump:
#  - causal features AT the dump: the 76 day-array features (p1_build.py) + extras below (only trades <= the dump),
#  - the IMIT1 score where known (imit2 rows of sel/imit2_build.py for R1-R3, else the live engine's "dump" events),
#  - the slot leader and near flags (Frankfurt / Amsterdam lists; leaders_book 1064-1065 + schedule_cur 1066),
#  - OUR replay at 35 / 50 ms landing (block-position proxy, as the IMIT1 replays): trades arriving before us are ahead; +5%
#    guard vs the post-dump price (else a failed buy); 0.55 SOL; follower buys whose slippage limit our buy breaks are dropped
#    (p1_build slack model); sells applied as tokens in; pump fee (event bps) both sides; no fixed costs here (eval adds them).
#    Exit grid from ONE replayed path (selexit2.rt_path semantics): time limit `cap` slots after the entry slot, take-profit /
#    stop-loss on the position value after each applied trade; a TP/SL trigger in slot S sells in slot S+1, a time-limit sell in
#    slot s_in+cap, both SELL_LAT = 75 ms into the slot (trades before that are applied first).
# -> /home/moiz/sniper-data/strategies/dipdetect/dd1_<day>.npz + dd1_meta.json
# usage: python3 dd1_build.py R2 [procs]
import sys, os, json, gzip, glob, zlib, time
import numpy as np
from multiprocessing import get_context

PO = "/home/moiz/sniper-data/strategies/patterns"; OUT = "/home/moiz/sniper-data/strategies/dipdetect"
SEL = "/home/moiz/sniper/ops/overnight/sel"; SPD = "/home/moiz/sniper/ops/dip/speed"
DAYS = {"R1": PO, "R2": PO, "R3": PO, "R4": OUT}
RUNDIR = {"R1": "run_20261021_2207", "R2": "run_20261022_1543", "R3": "run_20261023_1426", "R4": "run_20261024_1425"}
IMIT2 = {"R1": ["r1"], "R2": ["r2"], "R3": ["r3", "g", "r7f", "t2"], "R4": []}
SMS = 212.0; GUARD = 1.05; SELL_LAT = 75.0; HMAX = 40; SIZE = float(os.environ.get("DD_SIZE", "0.55")); LATS = (35, 50, 75); GRADV = 110e9
SFX = "" if SIZE == 0.55 else f"_s{SIZE:g}"          # other sizes -> dd1_<day>_s<size>.npz (same rows, only the replay differs)
CAPS = (2, 4, 6, 9, 12, 19, 28, 38); TPS = (None, 0.05, 0.10, 0.20, 0.40); SLS = (None, 0.05, 0.10, 0.20, 0.30)
EXITS = [(c, tp, sl) for c in CAPS for tp in TPS for sl in SLS]
NEX = len(EXITS)
NANROW = np.full(len(EXITS), np.nan, np.float32); ZROW = np.zeros(len(EXITS), np.int8)
EXN = [f"c{c}_tp{'none' if tp is None else round(tp * 100)}_sl{'none' if sl is None else round(sl * 100)}" for c, tp, sl in EXITS]
XF = ["since_buy_s", "since_big_s", "n_big", "slotpos_c", "s_frac", "s_pnl", "s_nb", "s_entry", "s_buy", "s_hold", "coh_n", "coh_sol",
      "coh_held", "coh_seller", "coh_20", "tgt_n", "tgt_hold", "top_n", "top_hold", "bundle_sol", "dev_tok", "n_sells_slot",
      "sold_slot_sol", "first_big_slot", "slot_drop", "pro_after_prev", "age_s", "drop_pct", "vmax", "uniq_b", "n_dumps2",
      "since_dump2_s", "s_is_pro", "buys_slot", "buy_sol_slot"]
XI = {k: i for i, k in enumerate(XF)}
DEV = {"bwamJzztZsepfkteWRChggmXuiiCQvpLqPietdNfSXa"}
T3 = ["HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ", "DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw", "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"]
TOP10 = [l.strip() for l in open("/home/moiz/sniper/ops/agents/topearners/work/top10.txt") if l.strip()]
COH = json.load(open(f"{SEL}/cohort_train.json"))
U3 = {zlib.crc32(u.encode()) for u in T3}; UT = {zlib.crc32(u.encode()) for u in TOP10}; UC = {zlib.crc32(u.encode()) for u in COH}
UPRO = U3 | UC          # 'pro' = the 3 IMIT1 wallets + the TRAIN-hours cohort; the top-10 list (built on data up to 10-24 06:27) is NOT used in features
G = {}

def leader_map():
    lb = json.load(open("/home/moiz/sniper/ops/overnight/dipshadow/leaders_book.json"))["leaders"]
    sc = json.load(open(f"{SPD}/leaders/schedule_cur.json"))
    LS0 = 459648000; ids = sorted(set(lb.values()) | set(sc["ids"])); ix = {u: i for i, u in enumerate(ids)}
    lead = np.full(sc["start"] + len(sc["slot_leader"]) - LS0, -1, np.int32)
    for s, u in lb.items(): lead[int(s) - LS0] = ix[u]
    lead[sc["start"] - LS0:] = [ix[sc["ids"][i]] for i in sc["slot_leader"]]
    fra = {l.strip() for l in open("/home/moiz/sniper/ops/region/near_leaders_fra.txt") if l.strip()}
    ams = {l.strip() for l in open("/home/moiz/sniper/ops/region/near_leaders_ams.txt") if l.strip()}
    nf = np.array([u in fra for u in ids]); na = np.array([u in ams for u in ids])
    return LS0, lead, ids, nf, na

def imit_scores(day, mints):
    """(mint, slot) -> list of (sell SOL, score, src): imit2 replay rows (src 1) first, live engine dump events (src 2) after"""
    out = {}
    for w in IMIT2[day]:
        for l in gzip.open(f"{SEL}/imit2_rows_{w}.jsonl.gz", "rt"):
            o = json.loads(l)
            if o["m"] in mints: out.setdefault((o["m"], o["s"]), []).append((o["sell"], o["f1"], 1))
    fresh = sorted(glob.glob(f"{OUT}/live/dip_*.jsonl"))          # fresh read-only copies (run 10 to ~22:56 PKT) replace the old ones
    fb = {os.path.basename(f) for f in fresh}
    for f in [f for f in sorted(glob.glob(f"{SPD}/dip_r*.jsonl") + glob.glob(f"{SPD}/dip_ams_r*.jsonl")) if os.path.basename(f) not in fb] + fresh:
        for l in open(f):
            if '"ev":"dump"' not in l: continue
            try: o = json.loads(l)
            except Exception: continue
            if o.get("mint") in mints and o.get("score") is not None:
                key = (o["mint"], o["slot"]); lst = out.setdefault(key, [])
                if not any(abs(x[0] - o["sell"]) < 0.0015 and x[2] == 1 for x in lst): lst.append((o["sell"], o["score"], 2))
    return out

def load(day):
    z = np.load(f"{DAYS[day]}/day_{day}.npz"); M = json.load(open(f"{DAYS[day]}/day_{day}_meta.json"))
    d = {k: z[k] for k in z.files}; d["meta"] = M["meta"]; d["FI"] = {k: i for i, k in enumerate(M["feats"])}; d["feats"] = M["feats"]
    nt = len(M["meta"]); cnt = np.bincount(d["tok"], minlength=nt); off = np.concatenate([[0], np.cumsum(cnt)[:-1]]).astype(np.int64)
    d["off"] = off; d["cnt"] = cnt
    return d

def path(Sl, Al, Bl, SOLl, TKl, Vl, Tl, FRl, SKl, UIDl, n, j0, L):
    """our buy L ms after the dump at local index j0 -> (status, ratio, ahead, ahead_buys, ahead_pro, s_in, pnl[NEX], off[NEX],
    maxval6, minval6). status 0 filled, 1 guard fail, 2 untradeable (graduated)."""
    a0 = Al[j0]; fr0 = FRl[j0]; p_after = Vl[j0] / Tl[j0]
    ke = j0 + 1
    while ke < n and Al[ke] < a0 + L: ke += 1
    ahead = ke - j0 - 1; ab = 0; ap = 0
    for x in range(j0 + 1, ke):
        if Bl[x]: ab += 1; ap += UIDl[x] in UPRO
    Vb = Vl[ke - 1]; Tb = Tl[ke - 1]
    ratio = (Vb / Tb) / p_after
    if Vb >= 100e9: return (2, ratio, ahead, ab, ap, 0, None, None, 0.0, 0.0)
    if ratio > GUARD: return (1, ratio, ahead, ab, ap, 0, None, None, 0.0, 0.0)
    X = SIZE * 1e9 / (1 + fr0); q = Tb * X / (Vb + X); V = Vb + X; T = Tb - q
    s_land = int((a0 + L) // SMS); s_in = max(Sl[ke - 1], s_land); frs = fr0
    cur = V * q / (T + q) * (1 - frs) / 1e9 - SIZE
    poff = [None] * (HMAX + 2); dn = 0
    ftp = [None] * len(TPS); fsl = [None] * len(SLS)
    mx6 = mn6 = (cur + SIZE) / SIZE; s6 = s_in + 6; s_cut = s_in + HMAX + 1
    for j in range(ke, n):
        sj = Sl[j]; pos = Al[j] - sj * SMS
        kj = 2 * sj + (1 if pos >= SELL_LAT else 0)
        while dn <= HMAX + 1 and 2 * (s_in + dn) + 1 <= kj: poff[dn] = cur; dn += 1
        if sj > s_cut or dn > HMAX + 1: break
        applied = True
        if Bl[j]:
            sol = SOLl[j]; dt = T * sol / (V + sol)
            if dt < TKl[j] / (1.0 + SKl[j]): applied = False
            else: V += sol; T -= dt
        else:
            tk = TKl[j]; so = V * tk / (T + tk); V -= so; T += tk
        if applied: frs = FRl[j]
        cur = V * q / (T + q) * (1 - frs) / 1e9 - SIZE
        if V >= GRADV: break
        if applied:
            val = (cur + SIZE) / SIZE
            if sj <= s6:
                if val > mx6: mx6 = val
                if val < mn6: mn6 = val
            for a in range(1, len(TPS)):
                if ftp[a] is None and val >= 1 + TPS[a]: ftp[a] = sj
            for b in range(1, len(SLS)):
                if fsl[b] is None and val <= 1 - SLS[b]: fsl[b] = sj
    while dn <= HMAX + 1: poff[dn] = cur; dn += 1
    pn = [0.0] * NEX; of = [0] * NEX
    for e, (c, tp, sl) in enumerate(EXITS):
        co = s_in + c; a = ftp[TPS.index(tp)] if tp is not None else None; b = fsl[SLS.index(sl)] if sl is not None else None
        if a is not None and a + 1 >= co: a = None
        if b is not None and b + 1 >= co: b = None
        if a is None and b is None: so_ = co
        elif b is None: so_ = a + 1
        elif a is None: so_ = b + 1
        else: so_ = min(a, b) + 1
        dd = so_ - s_in; pn[e] = poff[dd]; of[e] = dd
    return (0, ratio, ahead, ab, ap, s_in, pn, of, mx6, mn6)

def work(toks):
    d = G["d"]; FI = d["FI"]; meta = d["meta"]; cand = G["cand"]; devtok = G["devtok"]
    K = []; XL = []; NL = len(LATS)
    ST = [[] for _ in range(NL)]; RA = [[] for _ in range(NL)]; AH = [[] for _ in range(NL)]; SI = [[] for _ in range(NL)]; MM = [[] for _ in range(NL)]
    PN = [[] for _ in range(NL)]; OF = [[] for _ in range(NL)]
    for t in toks:
        o = int(d["off"][t]); n = int(d["cnt"][t]); cl = cand.get(t)
        if not cl: continue
        sl = slice(o, o + n)
        Sl = d["s"][sl].tolist(); Al = d["arr"][sl].tolist(); Bl = d["buy"][sl].astype(bool).tolist(); SOLl = d["sol"][sl].tolist()
        TKl = d["tokn"][sl].tolist(); Vl = d["vsol"][sl].tolist(); Tl = d["vtok"][sl].tolist(); FRl = d["fr"][sl].astype(float).tolist()
        SKl = d["slack"][sl].astype(float).tolist(); UIDl = d["uid"][sl].tolist(); Il = d["i"][sl].tolist()
        S0 = meta[t]["S0"]; cs = set(cl)
        bundle = sum(SOLl[x] for x in range(n) if Sl[x] == S0 and Bl[x]) / 1e9
        W = {}; cohb = set(); cohbal = {}; cohsol = 0.0; tgtn = topn = 0; bal3 = {}; balT = {}
        last_buy = None; last_big = None; nbig = 0; n2 = 0; last2 = None; vmax = 0.0; ub = set()
        slot_cur = None; ns_slot = 0; ssol_slot = 0.0; big_slot = False; p_slot0 = None; nb_slot = 0; bsol_slot = 0.0
        pro_after = 0; big_arr = None
        for j in range(n):
            u = UIDl[j]; b = Bl[j]; sol = SOLl[j]; tk = TKl[j]
            if Sl[j] != slot_cur:
                slot_cur = Sl[j]; ns_slot = 0; ssol_slot = 0.0; big_slot = False; nb_slot = 0; bsol_slot = 0.0
                p_slot0 = (Vl[j] - sol) / (Tl[j] + tk) if b else (Vl[j] + sol) / (Tl[j] - tk)
            if j in cs:
                st = W.get(u)
                if st:
                    held = st[2] - st[3]; s_frac = min(tk / held, 2.0) if held > 0 else 2.0
                    s_pnl = (st[1] + sol - st[0]) / 1e9; s_nb = st[4]; s_entry = (st[5] - S0) if st[4] else -1; s_buy = st[0] / 1e9
                    s_hold = (Sl[j] - st[5]) if st[4] else -1
                else: s_frac, s_pnl, s_nb, s_entry, s_buy, s_hold = 2.0, sol / 1e9, 0, -1, 0.0, -1
                coh_held = sum(1 for w, v in cohbal.items() if (v - (tk if w == u else 0)) > 0)
                c20 = set()
                for x in range(max(0, j - 80), j):
                    if Bl[x] and Sl[j] - Sl[x] <= 20 and UIDl[x] in UC: c20.add(UIDl[x])
                tgt_hold = sum(1 for w, v in bal3.items() if (v - (tk if w == u else 0)) > 0)
                top_hold = sum(1 for w, v in balT.items() if (v - (tk if w == u else 0)) > 0)
                p_after = Vl[j] / Tl[j]
                xf = [(Al[j] - last_buy) / 1000 if last_buy is not None else 1e9, (Al[j] - last_big) / 1000 if last_big is not None else 1e9, nbig,
                      min(Il[j] / 400.0, 1.0), s_frac, s_pnl, s_nb, s_entry, s_buy, s_hold, len(cohb), cohsol / 1e9, coh_held, int(u in UC),
                      len(c20), tgtn, tgt_hold, topn, top_hold, bundle, devtok[t], ns_slot, ssol_slot / 1e9, int(not big_slot),
                      (p_after / p_slot0 - 1) * 100 if p_slot0 else 0.0, pro_after, (Sl[j] - S0) * SMS / 1000, (1 - p_after / ((Vl[j] + sol) / (Tl[j] - tk))) * 100,
                      max(vmax, Vl[j]) / 1e9, len(ub), n2, (Al[j] - last2) / 1000 if last2 is not None else 1e9, int(u in UPRO), nb_slot, bsol_slot / 1e9]
                outs = [path(Sl, Al, Bl, SOLl, TKl, Vl, Tl, FRl, SKl, UIDl, n, j, L) for L in LATS]
                K.append(o + j); XL.append(xf)
                for li, ot in enumerate(outs):
                    ST[li].append(ot[0]); RA[li].append(ot[1]); AH[li].append((ot[2], ot[3], ot[4])); SI[li].append(ot[5]); MM[li].append((ot[8], ot[9]))
                    PN[li].append(np.array(ot[6], np.float32) if ot[0] == 0 else NANROW); OF[li].append(np.array(ot[7], np.int8) if ot[0] == 0 else ZROW)
            # ---- update running state with trade j (after the candidate features, which include trade j only via F / p_after)
            st = W.get(u)
            if st is None: st = W[u] = [0.0, 0.0, 0.0, 0.0, 0, Sl[j]]
            if b:
                st[0] += sol; st[2] += tk; st[4] += 1
                if st[4] == 1: st[5] = Sl[j]
                last_buy = Al[j]; ub.add(u); nb_slot += 1; bsol_slot += sol
                if u in UC: cohb.add(u); cohbal[u] = cohbal.get(u, 0) + tk; cohsol += sol
                if u in U3: tgtn += 1; bal3[u] = bal3.get(u, 0) + tk
                if u in UT: topn += 1; balT[u] = balT.get(u, 0) + tk
                if u in UPRO and big_arr is not None and Al[j] - big_arr <= 1000: pro_after += 1
            else:
                st[1] += sol; st[3] += tk; ns_slot += 1; ssol_slot += sol
                if u in cohbal: cohbal[u] -= tk
                if u in bal3: bal3[u] -= tk
                if u in balT: balT[u] -= tk
                if sol >= 1e9: last_big = Al[j]; nbig += 1; big_slot = True; big_arr = Al[j]
                if (1 - (Vl[j] / Tl[j]) / ((Vl[j] + sol) / (Tl[j] - tk))) * 100 >= 2.0: n2 += 1; last2 = Al[j]
            if Vl[j] > vmax: vmax = Vl[j]
    if not K: return None
    return dict(k=np.array(K, np.int64), X=np.array(XL, np.float32), st=np.array(ST, np.int8).T, ratio=np.array(RA, np.float32).T,
                ahead=np.array(AH, np.int16).transpose(1, 0, 2), sin=np.array(SI, np.int64).T, mm=np.array(MM, np.float32).transpose(1, 0, 2),
                pnl=np.stack([np.stack(PN[li]) for li in range(NL)], 1), off=np.stack([np.stack(OF[li]) for li in range(NL)], 1))

def main(day, procs):
    t0 = time.time()
    d = load(day); FI = d["FI"]; F = d["F"]; meta = d["meta"]
    s_end = int(d["s"].max())
    # candidates: sells that moved the price <= -2%, curve < 100 SOL after, token >= 5 slots old, >= 300 slots before the data end
    age = F[:, FI["age"]]
    m = (d["buy"] == 0) & (F[:, FI["move"]] <= -2.0) & (d["vsol"] < 100e9) & (age >= 5) & (d["s"] <= s_end - 300)
    ci = np.flatnonzero(m); tk = d["tok"][ci]
    cand = {}
    for k, t in zip(ci.tolist(), tk.tolist()): cand.setdefault(t, []).append(k - int(d["off"][t]))
    mints = {meta[t]["m"] for t in cand}
    # dev tokens (create signer / creator / payer on the dev list)
    devm = set()
    for l in open(f"/home/moiz/sniper-data/collect/{RUNDIR[day]}/launches.jsonl"):
        try: c = json.loads(l)
        except Exception: continue
        if DEV & {c.get("user"), c.get("creator"), c.get("payer")}: devm.add(c.get("mint"))
    devtok = np.array([1 if x["m"] in devm else 0 for x in meta], np.int8)
    G["d"] = d; G["cand"] = cand; G["devtok"] = devtok
    print(f"{day}: {len(ci)} candidate dumps on {len(cand)} tokens ({time.time() - t0:.0f} s)", flush=True)
    toks = sorted(cand); chunks = [toks[i::procs * 8] for i in range(procs * 8)]
    parts = []
    with get_context("fork").Pool(procs) as p:
        for i, r in enumerate(p.imap_unordered(work, chunks)):
            if r is not None: parts.append(r)
            if (i + 1) % 8 == 0: print(f"  {i + 1}/{len(chunks)} chunks, {sum(len(x['k']) for x in parts)} rows, {time.time() - t0:.0f} s", flush=True)
    A = {key: np.concatenate([x[key] for x in parts]) for key in parts[0]}
    o_ = np.argsort(A["k"], kind="stable"); A = {key: v[o_] for key, v in A.items()}
    k = A["k"]; N = len(k); X = A["X"]; st = A["st"]; ratio = A["ratio"]; ahead = A["ahead"]; sin = A["sin"]; pnl = A["pnl"]; off = A["off"]; mm = A["mm"]
    # leaders / near flags
    LS0, lead, ids, nf, na = leader_map()
    sl_ = d["s"][k] - LS0; ok = (sl_ >= 0) & (sl_ < len(lead)); li_ = np.full(N, -1, np.int32); li_[ok] = lead[sl_[ok]]
    near_f = np.where(li_ >= 0, nf[np.maximum(li_, 0)], False); near_a = np.where(li_ >= 0, na[np.maximum(li_, 0)], False)
    # IMIT1 scores
    sc = imit_scores(day, mints); f1 = np.full(N, np.nan, np.float32); src = np.zeros(N, np.int8)
    tokk = d["tok"][k]; solk = d["sol"][k] / 1e9; sk = d["s"][k]
    for i in range(N):
        lst = sc.get((meta[tokk[i]]["m"], int(sk[i])))
        if not lst: continue
        best = min(lst, key=lambda x: (abs(x[0] - solk[i]), x[2]))
        if abs(best[0] - solk[i]) < 0.0015: f1[i] = best[1]; src[i] = best[2]
    np.savez(f"{OUT}/dd1_{day}{SFX}.npz", k=k, tok=tokk, s=sk, arr=d["arr"][k], bt=d["bt"][k], F=F[k], X=X, st=st, ratio=ratio, ahead=ahead, sin=sin,
             pnl=pnl, off=off, mm=mm, lead=li_, near_f=near_f, near_a=near_a, f1=f1, f1src=src, uid=d["uid"][k], wt=d["wt"][k])
    if SFX: print(f"{day}: size {SIZE} written to dd1_{day}{SFX}.npz", flush=True); return
    json.dump(dict(feats=d["feats"], xf=XF, exits=EXN, caps=CAPS, tps=TPS, sls=SLS, lats=LATS, size=SIZE, guard=GUARD, sell_lat=SELL_LAT,
                   hmax=HMAX), open(f"{OUT}/dd1_meta.json", "w"))
    print(f"{day}: rows {N}, filled@35 {(st[:, 0] == 0).sum()}, guard-fail@35 {(st[:, 0] == 1).sum()}, near_f {near_f.sum()}, near_a {near_a.sum()}, "
          f"lead unknown {(li_ < 0).sum()}, IMIT1 scored {np.isfinite(f1).sum()} (imit2 {(src == 1).sum()}, live {(src == 2).sum()}), "
          f"dev rows {devtok[tokk].sum()}, {time.time() - t0:.0f} s", flush=True)

if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 4)
