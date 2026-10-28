#!/usr/bin/env python3
"""8yYMhu s1 (read-only): the selection universe = every outside pump.fun curve SELL >= 1 SOL from 10-25 11:30 to 10-29 00:50 PKT
(market tape), with on-chain features at the moment of the sell and paper forward returns, plus whether 8yYMhu took it
(an on-chain attempt of his has this sell as trigger) / filled it (landed buy) and his realized lot P&L.
Paper trade (same model for taken and skipped): buy 0.75 SOL into the curve at entry, sell all at exit, 1.25 % pump+creator fee each
way, constant product k = vsol*vtok; curve path with HIS OWN trades removed (vsol_free = vsol - his net SOL in the curve).
Entry variants: 'e0' right after the trigger; 'e73' after the outside trades that land within 73 txs of it in the same slot (his median).
Exit: end of slot trigger+{2,5,9,20,40}. Out: DATA/uni.npz (+ uni_cols.json)"""
import sys, os, pickle, json, time, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, rlib as X, tlib as T
t0 = time.time()
M, um, ua, ub = T.tape()
mints, users = T.names(); wid = T.uid()[X.W]
A = pickle.load(open(f"{X.D}/att.pkl", "rb")); L = pickle.load(open(f"{X.D}/lots.pkl", "rb"))
lot = {l["lot_id"]: l for l in L}
took = collections.defaultdict(lambda: [0, 0, None])     # (mint, trig slot, trig idx) -> [attempts, landed, lot pnl]
for a in A:
    if "trig_slot" not in a: continue
    k = (a["mint"], a["trig_slot"], a["trig_idx"]); took[k][0] += 1
    if a["out"] == "landed":
        took[k][1] += 1; l = lot.get(a["lot"])
        if l is not None: took[k][2] = (took[k][2] or 0) + l["pnl_cash"]
CR = json.load(open("/home/moiz/sniper-data/dv8/tab/creates.json"))
CR.update(json.load(open("/home/moiz/sniper-data/e2x1_dissect/select/creates_new.json")))
mid = T.mid(); uidm = T.uid()
cr_slot = {}; cr_user = {}; mayhem = {}
for m, v in CR.items():
    k = mid.get(m)
    if k is None or not v.get("slot"): continue
    cr_slot[k] = int(v["slot"]); cr_user[k] = uidm.get(v.get("creator"), -1); mayhem[k] = bool(v.get("mayhem"))
TA, TB = 1792915200, 1793220600        # 10-25 13:00 PKT .. 10-29 00:50 PKT  (wallet active from 10-25 11:28)
FEE = 0.0125; SZ = 0.75e9; EX = (1, 2, 3, 6, 9, 20, 40, 61)
cols = collections.defaultdict(list)
def paper(k_, V0, V1):
    """buy SZ lamports at curve vsol V0, sell all at curve vsol V1 (without us); returns net SOL P&L"""
    tok = k_ / V0 - k_ / (V0 + SZ)
    T1 = k_ / V1
    if T1 - tok <= 0: return np.nan
    out = k_ / (T1 - tok) - V1
    return (out * (1 - FEE) - SZ * (1 + FEE)) / 1e9
nm = 0
for p in range(len(um)):
    a0, b0 = int(ua[p]), int(ub[p])
    if b0 - a0 < 3: continue
    tr = np.asarray(M[a0:b0])
    isS = (tr["buy"] == 0) & (tr["sol"] >= 1_000_000_000) & (tr["user"] != wid) & (tr["bt"] >= TA) & (tr["bt"] < TB)
    if not isS.any(): continue
    nm += 1
    k = int(um[p])
    slot = tr["slot"].astype(np.int64); idx = tr["idx"].astype(np.int64); key = slot * 4096 + idx
    vs = tr["vsol"].astype(np.float64); vt = tr["vtok"].astype(np.float64); sol = tr["sol"].astype(np.float64); buy = tr["buy"] == 1
    me = tr["user"] == wid
    mine = np.where(me, np.where(buy, sol, -sol), 0.0); vfree = vs - np.cumsum(mine)
    kk = vs * vt
    first_slot = int(slot[0]); cs = cr_slot.get(k, first_slot if (int(tr["vsol"][0]) - int(tr["sol"][0])) == 30_000_000_000 else -1)
    cu = cr_user.get(k, int(tr["user"][0]) if cs == first_slot else -1)
    peak = np.maximum.accumulate(vs)
    csb = np.cumsum(np.where(buy & ~me, sol, 0.0)); css = np.cumsum(np.where(~buy & ~me, sol, 0.0))
    users_ = tr["user"]
    for q in np.nonzero(isS)[0]:
        s_ = int(slot[q]); i_ = int(idx[q]); u = int(users_[q])
        V_after = vfree[q]; V_before = vfree[q] + sol[q]
        # entry e0: right after the trigger ; e73: after outside trades within 73 txs in the same slot
        e0 = V_after
        j73 = int(np.searchsorted(key, s_ * 4096 + i_ + 73, side="right")) - 1
        e73 = vfree[j73] if j73 >= q else V_after
        j150 = int(np.searchsorted(key, s_ * 4096 + i_ + 150, side="right")) - 1
        e150 = vfree[j150] if j150 >= q else V_after
        jns = int(np.searchsorted(slot, s_, side="right")) - 1          # end of the trigger slot (= first lands next slot)
        ens = vfree[max(jns, q)]
        jn2 = int(np.searchsorted(key, (s_ + 1) * 4096 + 150, side="right")) - 1   # next slot, +150 txs (our reactive ~ 60-90 ms)
        en2 = vfree[max(jn2, q)]
        # exits: last trade at or before end of slot s_+x (his-free); if no trade, curve unchanged since last
        ex = []
        for x in EX:
            jx = int(np.searchsorted(slot, s_ + x, side="right")) - 1
            ex.append(vfree[max(jx, q)])
        h = tr[:q]; hu = h[(h["user"] == u)]
        btok = float(hu["tok"][hu["buy"] == 1].sum()); stok = float(hu["tok"][hu["buy"] == 0].sum())
        fb = np.nonzero(hu["buy"] == 1)[0]
        fbslot = int(hu["slot"][fb[0]]) if len(fb) else -1
        # rank of seller among distinct buyers (order of first buy)
        if len(fb):
            fbi = int(np.nonzero((users_[:q] == u) & buy[:q])[0][0])
            rank = len(np.unique(users_[:fbi][buy[:fbi]]))
        else: rank = -1
        w10 = slot[:q] >= s_ - 10
        tk = took.get((mints[k], s_, i_))
        cols["mint"].append(k); cols["slot"].append(s_); cols["idx"].append(i_); cols["bt"].append(int(tr["bt"][q])); cols["user"].append(u)
        cols["sol"].append(sol[q] / 1e9); cols["vsol_after"].append(V_after / 1e9); cols["vsol_before"].append(V_before / 1e9)
        cols["drop"].append(1 - (V_after / V_before) ** 2)
        cols["age_slots"].append(s_ - cs if cs >= 0 else -1); cols["create_known"].append(cs >= 0)
        cols["n_before"].append(q); cols["peak_vsol"].append(peak[q - 1] / 1e9 if q else V_before / 1e9)
        cols["dd_peak"].append(1 - (V_after / (peak[q - 1] if q else V_before)) ** 2)
        cols["buy10"].append((csb[q - 1] - (csb[np.searchsorted(slot, s_ - 10) - 1] if np.searchsorted(slot, s_ - 10) > 0 else 0)) / 1e9 if q else 0)
        cols["sell10"].append((css[q - 1] - (css[np.searchsorted(slot, s_ - 10) - 1] if np.searchsorted(slot, s_ - 10) > 0 else 0)) / 1e9 if q else 0)
        cols["n10"].append(int(w10.sum()))
        cols["seller_creator"].append(u == cu); cols["seller_btok"].append(btok); cols["seller_stok_before"].append(stok)
        cols["seller_frac"].append(float(tr["tok"][q]) / btok if btok > 0 else -1.0)
        cols["seller_first_slot"].append(fbslot); cols["seller_rank"].append(rank)
        cols["seller_hold_slots"].append(s_ - fbslot if fbslot >= 0 else -1)
        cols["seller_cslot"].append(fbslot == cs and cs >= 0)
        cols["seller_supply_pct"].append(100 * float(tr["tok"][q]) / 1e15)
        cols["mayhem"].append(mayhem.get(k, False))
        cols["k"].append(kk[q])
        for e_lab, V0 in (("e0", e0), ("e73", e73), ("e150", e150), ("ens", ens), ("en2", en2)):
            for x, V1 in zip(EX, ex):
                cols[f"r_{e_lab}_{x}"].append(paper(kk[q], V0, V1))
        cols["taken"].append(tk[0] if tk else 0); cols["filled"].append(tk[1] if tk else 0); cols["his_pnl"].append(tk[2] if tk and tk[2] is not None else np.nan)
    if nm % 20000 == 0: print(nm, len(cols["mint"]), time.time() - t0, flush=True)
arr = {k: np.array(v) for k, v in cols.items()}
np.savez_compressed(f"{X.D}/uni.npz", **arr)
print("sells", len(arr["mint"]), "taken", int((arr["taken"] > 0).sum()), "filled", int((arr["filled"] > 0).sum()), "mints", nm, "s", time.time() - t0)
