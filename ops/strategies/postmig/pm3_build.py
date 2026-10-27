#!/usr/bin/env python3
# POST-MIGRATION STUDY, pass 3: per-token migration dataset + per-row effective pool state.
#  - effective quote reserve Qv = vault quote + virtual reserve V; V implied per clean trade (buy_exact_quote_in: Qv =
#    B(e-1)/out - (e-1); sell: Qv = q(B+b)/b), forward-filled within the pool (backfilled before the first clean trade)
#  - post-trade state: buy B-out, Qv+e+lp_fee(e); sell B+b, Qv-q+lp_fee(q); price p = Qv/B (lamports per raw token unit)
#  - arrival(tx) = slot*212 + index/blocksize*212 ms (blocksize = max index seen + 1)
# Outputs: <RUN>_rows.npz (amm rows sorted by mint,s,i,k + Qv, p_pre, p_post, arr, F) and <RUN>_tokens.jsonl
import sys, os, json, pickle, collections, time, datetime
import numpy as np
OUT = "/home/moiz/sniper-data/strategies/postmig"
COL = "/home/moiz/sniper-data/collect"
RUNS = {"R1": "run_20261021_2207", "R2": "run_20261022_1543", "R3": "run_20261023_1426", "R4": "run_20261024_1425"}
SMS = 212.0
W = {"slot0": 0, "1s": 5, "10s": 47, "1m": 283, "10m": 2830, "1h": 16981}
FARM = {"6tzAKfHtQA4zLwgaXn97kU5C1dYsKcRy8XZhZUWmWU23", "4G9JAzftaydKjB2558MLnkYw175KMN6NGGgyxkeRuwwA"}

def pkt(bt): return datetime.datetime.fromtimestamp(bt + 5 * 3600, datetime.UTC).strftime("%m-%d %H:%M:%S")

def load(run):
    A = dict(np.load(os.path.join(OUT, f"{run}_amm.npz")))
    BC = dict(np.load(os.path.join(OUT, f"{run}_bc.npz")))
    S = dict(np.load(os.path.join(OUT, f"{run}_slots.npz")))
    st = pickle.load(open(os.path.join(OUT, f"{run}_strs.pkl"), "rb"))
    migs = json.load(open(os.path.join(OUT, f"{run}_migs.json")))
    return A, BC, S, st, migs

def labels():
    L = {}
    for l in open("/home/moiz/sniper-data/llm/launch_labels/labels.jsonl"):
        try: d = json.loads(l); L[d["mint"]] = d
        except Exception: pass
    return L

def launches(run):
    L = {}
    for l in open(os.path.join(COL, RUNS[run], "launches.jsonl")):
        try: c = json.loads(l)
        except Exception: continue
        if c.get("err"): continue
        L[c["mint"]] = dict(s=c["slot"], i=c.get("idx") or 0, bt=c.get("bt"), creator=c.get("creator") or c.get("user"), name=c.get("name"),
                            symbol=c.get("symbol"), mayhem=int("InitializeMayhemState" in (c.get("ixn") or [])))
    return L

def effective_state(A):
    n = len(A["s"])
    B = A["B"].astype(np.float64); Q = A["Q"].astype(np.float64); base = A["base"].astype(np.float64); qc = A["qcurve"].astype(np.float64)
    side = A["side"]; ixc = A["ixc"]
    cb = (side == 1) & np.isin(ixc, (1, 3)) & (base >= 1e6) & (qc > 1e4)
    cs = (side == -1) & (base >= 1e6) & (qc > 1e4)
    Qv_i = np.full(n, np.nan)
    Qv_i[cb] = B[cb] * (qc[cb] - 1) / base[cb] - (qc[cb] - 1)
    Qv_i[cs] = qc[cs] * (B[cs] + base[cs]) / base[cs]
    V_i = Qv_i - Q
    ok = np.isfinite(V_i) & (V_i > -1e9) & (V_i < 1e12)
    # group by mint (rows already sorted by mint, s, i, k)
    m = A["mint"]; starts = np.r_[0, np.nonzero(np.diff(m))[0] + 1]; ends = np.r_[starts[1:], n]
    gstart = np.repeat(starts, ends - starts)
    ar = np.arange(n)
    ff = np.maximum.accumulate(np.where(ok, ar, -1))
    bf = np.minimum.accumulate(np.where(ok, ar, n)[::-1])[::-1]
    gend = np.repeat(ends, ends - starts)
    use = np.where(ff >= gstart, ff, np.where(bf < gend, bf, -1))
    V = np.where(use >= 0, V_i[np.maximum(use, 0)], 0.0)
    Qv = Q + V
    lp = A["lpb"].astype(np.float64) / 1e4
    buy = side == 1
    B_post = np.where(buy, B - base, B + base)
    Qv_post = np.where(buy, Qv + qc + np.ceil(qc * lp), Qv - qc + np.ceil(qc * lp))
    return Qv, Qv / B, Qv_post / np.maximum(B_post, 1), ok, starts, ends

def main(run):
    t0 = time.time()
    A, BC, S, st, migs = load(run); strs = st["strs"]
    LB = labels(); LA = launches(run)
    # sort rows by mint, s, i, k
    o = np.lexsort((A["k"], A["i"], A["s"], A["mint"])); A = {c: v[o] for c, v in A.items()}
    # buys: the exact-out `buy`/`buy_v2` events carry the curve amount in quote_amount_in and the total debit in
    # user_quote_amount_in (the reverse of buy_exact_quote_in): debit = max, curve amount = min
    b = A["side"] == 1
    hi = np.maximum(A["qtot"], A["qcurve"]); lo = np.minimum(A["qtot"], A["qcurve"])
    A["qtot"] = np.where(b, hi, A["qtot"]); A["qcurve"] = np.where(b, lo, A["qcurve"])
    bs_map = dict(zip(S["s"].tolist(), S["bs"].tolist()))
    bs = np.array([bs_map.get(s, 400) for s in A["s"].tolist()], np.float64)
    A["arr"] = A["s"].astype(np.float64) * SMS + A["i"] / np.maximum(bs, A["i"] + 1) * SMS
    Qv, p_pre, p_post, clean, starts, ends = effective_state(A)
    A["Qv"] = Qv; A["p_pre"] = p_pre; A["p_post"] = p_post; A["clean"] = clean.astype(np.int8)
    A["F"] = (A["lpb"].astype(np.int32) + A["prb"] + A["ccb"]).astype(np.int16)
    np.savez(os.path.join(OUT, f"{run}_rows.npz"), **A)
    print(run, "rows", len(A["s"]), f"{time.time()-t0:.0f}s", flush=True)
    end_slot = int(S["s"].max()); slot_bt = dict(zip(S["s"].tolist(), S["bt"].tolist()))
    # BC grouped by mint
    ob = np.lexsort((BC["k"], BC["i"], BC["s"], BC["mint"])); BC = {c: v[ob] for c, v in BC.items()}
    bm = BC["mint"]; bst = np.r_[0, np.nonzero(np.diff(bm))[0] + 1]; ben = np.r_[bst[1:], len(bm)]
    bcg = {int(bm[a]): (a, b) for a, b in zip(bst, ben)} if len(bm) else {}
    amg = {int(A["mint"][a]): (a, b) for a, b in zip(starts, ends)}
    gid = {x: j for j, x in enumerate(strs)}
    toks = []
    for mint, mg in migs.items():
        c = mg["cpe"]; g = mg["mig"] or {}
        la = LA.get(mint, {}); lb = LB.get(mint, {})
        ms = mg["s"]; mi = mg["i"]
        T = dict(run=run, mint=mint, pool=c["pool"], name=la.get("name"), symbol=la.get("symbol"), creator=la.get("creator"),
                 coin_creator=c.get("coin_creator"), create_s=la.get("s"), create_bt=la.get("bt"), mig_s=ms, mig_i=mi, mig_bt=mg["bt"],
                 mig_pkt=pkt(mg["bt"]), hour=int(((mg["bt"] + 5 * 3600) // 3600) % 24), mig_sig=mg["sig"], mig_signers=mg["signers"],
                 mig_user=g.get("user"), mig_nev=mg["nev"], mig_nbc=mg["nbc"], attempts=mg.get("attempts", 1),
                 mayhem=int(la.get("mayhem", 0) or c.get("tail", "00")[:2] == "01"), pool_base0=c["pool_base"], pool_quote0=c["pool_quote"],
                 cover_s=round((end_slot - ms) * SMS / 1000), th=lb.get("th"), xl=lb.get("x"), eff=lb.get("eff"), cpy=lb.get("cpy"),
                 fun=lb.get("fun"), rw=lb.get("rw"))
        T["age_s"] = round((ms - la["s"]) * SMS / 1000, 1) if la.get("s") else None
        T["p0"] = c["pool_quote"] / max(c["pool_base"], 1)
        # ---- bonding-curve context
        mid = gid.get(mint)
        if mid is not None and mid in bcg:
            a, b = bcg[mid]
            s_ = BC["s"][a:b]; i_ = BC["i"][a:b]; u_ = BC["user"][a:b]; isb = BC["isbuy"][a:b]; sol = BC["sol"][a:b]; tok = BC["tok"][a:b]
            rs = BC["rsol"][a:b]
            pre = (s_ < ms) | ((s_ == ms) & (i_ <= mi))
            s_, i_, u_, isb, sol, tok, rs = s_[pre], i_[pre], u_[pre], isb[pre], sol[pre], tok[pre], rs[pre]
            T["bc_n"] = int(len(s_)); T["bc_buyers"] = int(len(np.unique(u_[isb == 1])))
            T["bc_buy_sol"] = float(sol[isb == 1].sum() / 1e9); T["bc_sell_sol"] = float(sol[isb == 0].sum() / 1e9)
            net = collections.defaultdict(int)
            for uu, bb, tk in zip(u_.tolist(), isb.tolist(), tok.tolist()): net[uu] += tk if bb else -tk
            cr = gid.get(la.get("creator") or "", -9)
            T["creator_buy_sol"] = float(sol[(u_ == cr) & (isb == 1)].sum() / 1e9); T["creator_sell_sol"] = float(sol[(u_ == cr) & (isb == 0)].sum() / 1e9)
            T["creator_tok_mig"] = max(0, net.get(cr, 0)) / 1e15
            cs_ = la.get("s")
            bund = set(u_[(s_ == cs_) & (isb == 1)].tolist()) - {cr} if cs_ else set()
            T["bundle_n"] = len(bund); T["bundle_sol"] = float(sol[np.isin(u_, list(bund)) & (isb == 1)].sum() / 1e9) if bund else 0.0
            T["bundle_tok_mig"] = sum(max(0, net.get(x, 0)) for x in bund) / 1e15
            hold = sorted((v for v in net.values() if v > 0), reverse=True)
            T["holders_mig"] = len(hold); T["top10_mig"] = sum(hold[:10]) / 1e15
            T["last5m_n"] = int(((s_ >= ms - 1415)).sum())
            T["last_sol"] = float(sol[-1] / 1e9) if len(sol) else 0.0; T["last_isbuy"] = int(isb[-1]) if len(isb) else -1
            T["last_buyer"] = strs[int(u_[-1])] if len(u_) else None
            T["last_same_tx"] = int(len(s_) > 0 and s_[-1] == ms and i_[-1] == mi)
            half = np.nonzero(rs >= 42.5e9)[0]
            T["t50_100_s"] = round((ms - int(s_[half[0]])) * SMS / 1000, 1) if len(half) else None
            T["bc_first_s"] = int(s_[0]) if len(s_) else None
            T["big_last"] = float(sol[(s_ >= ms - 5) & (isb == 1)].sum() / 1e9)
            T["insider_set"] = [strs[x] for x in list(bund)[:50]]
        # ---- post-migration path
        pid = gid.get(mint)
        if pid is not None and pid in amg:
            a, b = amg[pid]
            s_ = A["s"][a:b]; i_ = A["i"][a:b]; sd = A["side"][a:b]; u_ = A["user"][a:b]; qt = A["qtot"][a:b]; pp = A["p_post"][a:b]
            post = (s_ > ms) | ((s_ == ms) & (i_ >= mi))
            s_, i_, sd, u_, qt, pp = s_[post], i_[post], sd[post], u_[post], qt[post], pp[post]
            first = a + int(np.argmax(post)) if post.any() else a
            T["n_trades"] = int(len(s_)); T["p0_eff"] = float(A["p_pre"][first]) if post.any() else None
            T["fee0"] = [int(A["lpb"][first]), int(A["prb"][first]), int(A["ccb"][first])] if post.any() else None
            p0 = T["p0_eff"] or T["p0"]
            for w, dsl in W.items():
                sel = s_ <= ms + dsl
                if sel.any():
                    T[f"r_{w}"] = float(pp[sel][-1] / p0); T[f"max_{w}"] = float(pp[sel].max() / p0); T[f"min_{w}"] = float(pp[sel].min() / p0)
                    T[f"nb_{w}"] = int((sd[sel] == 1).sum()); T[f"ns_{w}"] = int((sd[sel] == -1).sum())
                    T[f"vb_{w}"] = float(qt[sel & (sd == 1)].sum() / 1e9); T[f"vs_{w}"] = float(qt[sel & (sd == -1)].sum() / 1e9)
                    T[f"ub_{w}"] = int(len(np.unique(u_[sel & (sd == 1)]))); T[f"us_{w}"] = int(len(np.unique(u_[sel & (sd == -1)])))
                else:
                    T[f"r_{w}"] = 1.0 if ms + dsl <= end_slot else None
                if ms + dsl > end_slot: T[f"r_{w}"] = None
            T["r_last"] = float(pp[-1] / p0) if len(pp) else None; T["last_trade_s"] = int(s_[-1]) if len(s_) else None
            T["ath"] = float(pp.max() / p0) if len(pp) else None
            fb = (s_ == ms) & (sd == 1)
            T["fb_buys"] = int(fb.sum()); T["fb_sol"] = float(qt[fb].sum() / 1e9); T["fb_wallets"] = [strs[x] for x in np.unique(u_[fb]).tolist()][:40]
            T["farm"] = int(any(w in FARM for w in T["fb_wallets"]))
        toks.append(T)
    with open(os.path.join(OUT, f"{run}_tokens.jsonl"), "w") as f:
        for T in toks: f.write(json.dumps(T) + "\n")
    print(run, "tokens", len(toks), f"{time.time()-t0:.0f}s", flush=True)

if __name__ == "__main__":
    for r in sys.argv[1:]: main(r)
