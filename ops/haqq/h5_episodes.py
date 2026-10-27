#!/usr/bin/env python3
# haqq SELL study, step 5: haqq positions ("episodes") per token with full tape context + a causal tick dataset.
# Episode = from a buy at zero holding to the sell that brings the holding back to zero (adds / partial sells inside).
# Per buy: entry type (dip = outside sell >= 1 SOL within 300 ms and <= 5 trades before), trigger, delay.
# Per tick (every trade on the token while haqq holds, incl. its own): features computable in real time from the trade feed.
# Costs: pump fee + creator fee from the events, tx fee + tips from the recording (rent excluded: reclaimed later in batches).
# Output: /home/moiz/sniper-data/haqq/ep/b{bb}.pkl = dict(eps=[...], X=float32 ticks x feats, meta arrays)
import sys, os, json, glob, pickle, collections, bisect, math
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H
from multiprocessing import Pool
D = "/home/moiz/sniper-data/collect"; OUT = H.OUT
RUNS = {"R1": "run_20261021_2207", "R2": "run_20261022_1543", "R3": "run_20261023_1426", "R4": "run_20261024_1425"}
COH = set(json.load(open("/home/moiz/sniper/ops/overnight/sel/cohort_train.json")))
DYX = "DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw"
WT = dict(other=0, creator=1, bundle=2, sniper=3, cohort=4, hk=5, dyx=6, ours=7, haqq=8)
FEATS = ["hold_ms", "hold_slots", "since_lastbuy_ms", "since_lastsell_ms", "nbuys", "nsells", "pos_frac", "ret", "ret_peak", "dd",
         "pchg_entry", "pchg_lastbuy", "pchg_1s", "pchg_3s", "pchg_10s", "ob_sol", "os_sol", "n_ob", "n_os",
         "since_ob01", "since_ob03", "since_ob1", "since_os03", "since_os1", "last_buy", "last_sol", "last_wt", "last_gap_ms",
         "imb_1", "imb_3", "imb_10", "nb_3", "ns_3", "maxb_3", "maxs_3", "dev_sold_any", "dev_sell_since", "ins_sell_since",
         "coh_buy_since", "coh_sell_since", "hk_buy_since", "hk_sell_since", "vsol", "age_ms", "share", "slot_in_leader", "intra",
         "n_follow", "follow_sol", "entry_dip", "entry_sol", "cost_sol", "tick_own", "tick_buy", "tick_sol", "tick_wt", "ret_lastbuy",
         "ob_since_lastbuy", "os_since_lastbuy", "price_vs_peak", "n_trades_since", "ret_min", "own_sold_frac"]
FI = {k: n for n, k in enumerate(FEATS)}
G = {}
def init():
    L = {}
    for run, d in RUNS.items():
        for l in open(f"{D}/{d}/launches.jsonl"):
            try: c = json.loads(l)
            except Exception: continue
            m = c.get("mint")
            if not m or m in L: continue
            L[m] = (c["slot"], c.get("idx") or 0, c.get("bt") or 0, c.get("creator") or c.get("user"), c.get("user"), 1 if "InitializeMayhemState" in (c.get("ixn") or []) else 0, run)
    G["L"] = L
    gs = set()
    for run, d in RUNS.items():
        p = f"{D}/{d}/gaps.jsonl"
        if os.path.exists(p):
            for l in open(p):
                try: gs.add(json.loads(l)["slot"])
                except Exception: pass
    G["gaps"] = np.array(sorted(gs), np.int64)
    # slot sizes (max recorded index + 1) as a dense array
    lo, hi = 459_700_000, 461_200_000; ss = np.zeros(hi - lo, np.int32)
    for run in RUNS:
        for k, v in json.load(open(f"{OUT}/slotmax_{run}.json")).items():
            k = int(k)
            if lo <= k < hi: ss[k - lo] = max(ss[k - lo], v + 1)
    G["ss"] = ss; G["sslo"] = lo
    led = json.load(open(f"{OUT}/ledger.json"))
    G["dend"] = {run: max(r["bt"] for r in led if r["run"] == run) for run in RUNS}
    G["dend"]["R4"] -= 1800                             # the last ~30 min of the live-synced run are ignored
def arr_ms(s, i):
    ss = G["ss"]; lo = G["sslo"]
    n = ss[s - lo] if lo <= s < lo + len(ss) else 0
    n = max(int(n), i + 1, 1)
    return s * H.SMS + (i / n) * H.SMS
def gaps_in(a, b):
    g = G["gaps"]; return int(np.searchsorted(g, b, side="right") - np.searchsorted(g, a, side="left"))
def wtype(u, creator, signer, bundle, snipers):
    if u == H.W: return WT["haqq"]
    if u in H.US: return WT["ours"]
    if u == creator or u == signer: return WT["creator"]
    if u in bundle: return WT["bundle"]
    if u == H.HK: return WT["hk"]
    if u == DYX: return WT["dyx"]
    if u in COH: return WT["cohort"]
    if u in snipers: return WT["sniper"]
    return WT["other"]
def proc_mint(m, d):
    L = G["L"].get(m)
    T = d["T"]; Wl = d["W"]
    if L is None or len(T) == 0: return [], None
    S0, cidx, cbt, creator, signer, mayhem, lrun = L
    n = len(T)
    s = T[:, 0]; ii = T[:, 1]; users = [Wl[x] for x in T[:, 5]]
    buy = T[:, 6].astype(bool); sol = T[:, 7].astype(np.float64); tok = T[:, 8].astype(np.float64)
    V = T[:, 9].astype(np.float64); Tk = T[:, 10].astype(np.float64)
    pfee = T[:, 11].astype(np.float64); cfee = T[:, 12].astype(np.float64); fr = (T[:, 13] + T[:, 14]) / 1e4
    txc = (T[:, 15] + T[:, 19]).astype(np.float64)                         # tx fee + tips
    A = np.array([arr_ms(int(a), int(b)) for a, b in zip(s, ii)])
    p = V / np.maximum(Tk, 1)
    Vpre = np.where(buy, V - sol, V + sol); Tpre = np.where(buy, Tk + tok, Tk - tok)
    brk = np.zeros(n, bool); brk[1:] = (Vpre[1:] != V[:-1]) | (Tpre[1:] != Tk[:-1])
    hq = [k for k in range(n) if users[k] == H.W]
    if not hq: return [], None
    bundle = {users[k] for k in range(n) if s[k] == S0 and buy[k]} - {creator, signer}
    snipers = {users[k] for k in range(n) if S0 < s[k] <= S0 + 24 and buy[k]} - bundle - {creator, signer}
    wt = np.array([wtype(u, creator, signer, bundle, snipers) for u in users], np.int8)
    cre = (wt == WT["creator"]); ins = cre | (wt == WT["bundle"])
    a_create = arr_ms(S0, cidx)
    eps = []; cur = None; pos = 0
    for k in hq:
        if buy[k]:
            if pos == 0: cur = dict(m=m, run=lrun, S0=S0, a_create=a_create, mayhem=mayhem, creator=creator, ks=[], kb=[], kss=[]); eps.append(cur)
            pos += int(T[k, 8]); cur["kb"].append(k); cur["ks"].append(k)
        else:
            if cur is None or pos == 0: continue
            pos -= int(T[k, 8]); cur["kss"].append(k); cur["ks"].append(k)
            if pos <= 0: pos = 0; cur["closed"] = True; cur = None
    out = []; ticks = []
    for e in eps:
        kb0 = e["kb"][0]; kend = e["ks"][-1] if e.get("closed") else n - 1
        e["closed"] = bool(e.get("closed"))
        # entry info per buy
        bl = []
        for k in e["kb"]:
            trig = None
            for q in range(k - 1, max(-1, k - 6), -1):
                if users[q] == H.W: continue
                if A[k] - A[q] > 300: break
                if (not buy[q]) and sol[q] >= 1e9: trig = q; break
            prev = next((q for q in range(k - 1, -1, -1) if users[q] != H.W), None)
            bl.append(dict(k=k, s=int(s[k]), i=int(ii[k]), a=float(A[k]), sol=float(sol[k]) / 1e9, tok=float(tok[k]), cost=float(sol[k] + pfee[k] + cfee[k] + txc[k]) / 1e9,
                           dip=trig is not None, trig_sol=float(sol[trig]) / 1e9 if trig is not None else None, trig_wt=int(wt[trig]) if trig is not None else None,
                           delay=float(A[k] - A[trig]) if trig is not None else (float(A[k] - A[prev]) if prev is not None else None),
                           trig_ds=int(s[k] - s[trig]) if trig is not None else None, prev_buy=bool(buy[prev]) if prev is not None else None,
                           prev_sol=float(sol[prev]) / 1e9 if prev is not None else None, prev_wt=int(wt[prev]) if prev is not None else None,
                           age=float(A[k] - a_create), vsol=float(Vpre[k]) / 1e9, drop=float(1 - p[trig] / (Vpre[trig] / max(Tpre[trig], 1))) if trig is not None else None,
                           txc=float(txc[k]) / 1e9, tip=int(T[k, 19]), cup=int(T[k, 16])))
        sl = [dict(k=k, s=int(s[k]), i=int(ii[k]), a=float(A[k]), sol=float(sol[k]) / 1e9, tok=float(tok[k]), proceeds=float(sol[k] - pfee[k] - cfee[k] - txc[k]) / 1e9,
                   txc=float(txc[k]) / 1e9, tip=int(T[k, 19]), cup=int(T[k, 16])) for k in e["kss"]]
        cost = sum(b["cost"] for b in bl); got = sum(x["proceeds"] for x in sl)
        held = sum(b["tok"] for b in bl) - sum(x["tok"] for x in sl)
        mtm = 0.0
        if held > 0:
            mtm = float(V[kend] * held / (Tk[kend] + held) * (1 - fr[kend])) / 1e9
        a_end = A[kend]; dend_ms = None
        rr = G["dend"].get(e["run"])
        e2 = dict(m=m, run=e["run"], S0=int(S0), mayhem=e["mayhem"], closed=e["closed"], buys=bl, sells=sl, cost=cost, got=got, mtm=mtm, pnl=got + mtm - cost,
                  held_tok=held, k0=kb0, kend=int(kend), brk=int(brk[kb0 + 1:kend + 1].sum()), gaps=gaps_in(int(s[kb0]), int(s[kend])),
                  bt0=int(T[kb0, 3]), bt_end=int(T[kend, 3]), censored=(not e["closed"]) or (int(T[kend, 3]) > (rr or 9e18) - 60),
                  ntr=int(kend - kb0 + 1), a_create=float(a_create), vsol0=float(Vpre[kb0]) / 1e9)
        out.append(e2)
        # ---- ticks: every trade from the first buy to the episode end (cap 3000 slots)
        if not e["closed"]: continue
        kcap = kend
        if s[kend] - s[kb0] > 3000: continue
        tk_tot = 0.0; tk_cost = 0.0; nb = 0; ns = 0; maxtok = 0.0; sold_tok = 0.0
        ret_peak = -1.0; ret_min = 9.0; p_entry = None; p_lastbuy = None; a_lastbuy = None; a_lastsell = None
        ob = os_ = 0.0; nob = nos = 0; l01 = l03 = l1 = None; ls03 = ls1 = None
        dsince = isince = 0.0; chb = chs = 0.0; hkb = hks = 0.0; nfol = 0; folsol = 0.0; obl = osl = 0.0
        dev_any = bool(((~buy[:kb0]) & cre[:kb0]).any()); pk_p = p[:kb0 + 1].max() if kb0 >= 0 else p[0]
        e_dip = 1.0 if bl[0]["dip"] else 0.0
        for k in range(kb0, kcap + 1):
            u = users[k]; own = u == H.W
            if own:
                if buy[k]:
                    tk_tot += tok[k]; tk_cost += (sol[k] + pfee[k] + cfee[k] + txc[k]); nb += 1; a_lastbuy = A[k]; p_lastbuy = p[k]; nfol = 0; folsol = 0.0; obl = osl = 0.0
                    if p_entry is None: p_entry = p[k]
                    maxtok = max(maxtok, tk_tot - sold_tok)
                else:
                    sold_tok += tok[k]; ns += 1; a_lastsell = A[k]
            else:
                if buy[k]:
                    ob += sol[k]; nob += 1; obl += sol[k]
                    if sol[k] >= 0.1e9: l01 = A[k]
                    if sol[k] >= 0.3e9: l03 = A[k]
                    if sol[k] >= 1e9: l1 = A[k]
                    nfol += 1; folsol += sol[k]
                    if wt[k] == WT["cohort"]: chb += sol[k]
                    if wt[k] == WT["hk"]: hkb += sol[k]
                else:
                    os_ += sol[k]; nos += 1; osl += sol[k]
                    if sol[k] >= 0.3e9: ls03 = A[k]
                    if sol[k] >= 1e9: ls1 = A[k]
                    if cre[k]: dsince += sol[k]; dev_any = True
                    if ins[k]: isince += sol[k]
                    if wt[k] == WT["cohort"]: chs += sol[k]
                    if wt[k] == WT["hk"]: hks += sol[k]
            pk_p = max(pk_p, p[k])
            held_k = tk_tot - sold_tok
            if held_k <= 0 and k > kb0: break
            basis = tk_cost * held_k / tk_tot if tk_tot > 0 else 0.0
            val = V[k] * held_k / (Tk[k] + held_k) * (1 - fr[k]) if held_k > 0 else 0.0
            ret = val / basis - 1 if basis > 0 else 0.0
            ret_peak = max(ret_peak, ret); ret_min = min(ret_min, ret)
            # window stats over last 1/3/10 slots (trades with slot > s[k]-w, up to k)
            def win(w):
                j0 = k
                while j0 - 1 >= 0 and s[j0 - 1] > s[k] - w: j0 -= 1
                bsum = float(np.sum(np.where(buy[j0:k + 1], sol[j0:k + 1], 0))); ssum = float(np.sum(np.where(~buy[j0:k + 1], sol[j0:k + 1], 0)))
                return j0, bsum, ssum
            j1, b1, s1 = win(1); j3, b3, s3 = win(3); j10, b10, s10 = win(10)
            seg = slice(j3, k + 1)
            maxb3 = float(np.max(np.where(buy[seg], sol[seg], 0))) / 1e9; maxs3 = float(np.max(np.where(~buy[seg], sol[seg], 0))) / 1e9
            def pch(w):
                j = bisect.bisect_right(s[:k + 1].tolist(), s[k] - w) - 1 if False else None
                q = k
                while q - 1 >= 0 and s[q - 1] > s[k] - w: q -= 1
                ref = p[q - 1] if q - 1 >= 0 else (Vpre[q] / max(Tpre[q], 1))
                return p[k] / ref - 1
            prev = k - 1
            hm = A[k] - A[kb0]
            sil = int(((s[k] - (s[k] // 432000 * 432000)) % 4))
            f = np.zeros(len(FEATS), np.float32)
            f[FI["hold_ms"]] = hm; f[FI["hold_slots"]] = s[k] - s[kb0]; f[FI["since_lastbuy_ms"]] = A[k] - a_lastbuy
            f[FI["since_lastsell_ms"]] = (A[k] - a_lastsell) if a_lastsell is not None else -1
            f[FI["nbuys"]] = nb; f[FI["nsells"]] = ns; f[FI["pos_frac"]] = held_k / maxtok if maxtok > 0 else 0
            f[FI["ret"]] = ret; f[FI["ret_peak"]] = ret_peak; f[FI["dd"]] = ret_peak - ret; f[FI["ret_min"]] = ret_min
            f[FI["pchg_entry"]] = p[k] / p_entry - 1; f[FI["pchg_lastbuy"]] = p[k] / p_lastbuy - 1
            f[FI["pchg_1s"]] = pch(1); f[FI["pchg_3s"]] = pch(3); f[FI["pchg_10s"]] = pch(10)
            f[FI["ob_sol"]] = ob / 1e9; f[FI["os_sol"]] = os_ / 1e9; f[FI["n_ob"]] = nob; f[FI["n_os"]] = nos
            f[FI["since_ob01"]] = A[k] - (l01 if l01 is not None else A[kb0]); f[FI["since_ob03"]] = A[k] - (l03 if l03 is not None else A[kb0])
            f[FI["since_ob1"]] = A[k] - (l1 if l1 is not None else A[kb0]); f[FI["since_os03"]] = A[k] - (ls03 if ls03 is not None else A[kb0])
            f[FI["since_os1"]] = A[k] - (ls1 if ls1 is not None else A[kb0])
            f[FI["last_buy"]] = buy[k]; f[FI["last_sol"]] = sol[k] / 1e9; f[FI["last_wt"]] = wt[k]; f[FI["last_gap_ms"]] = A[k] - A[prev] if prev >= 0 else -1
            f[FI["imb_1"]] = (b1 - s1) / 1e9; f[FI["imb_3"]] = (b3 - s3) / 1e9; f[FI["imb_10"]] = (b10 - s10) / 1e9
            f[FI["nb_3"]] = int(buy[j3:k + 1].sum()); f[FI["ns_3"]] = int((~buy[j3:k + 1]).sum()); f[FI["maxb_3"]] = maxb3; f[FI["maxs_3"]] = maxs3
            f[FI["dev_sold_any"]] = dev_any; f[FI["dev_sell_since"]] = dsince / 1e9; f[FI["ins_sell_since"]] = isince / 1e9
            f[FI["coh_buy_since"]] = chb / 1e9; f[FI["coh_sell_since"]] = chs / 1e9; f[FI["hk_buy_since"]] = hkb / 1e9; f[FI["hk_sell_since"]] = hks / 1e9
            f[FI["vsol"]] = V[k] / 1e9; f[FI["age_ms"]] = A[k] - a_create; f[FI["share"]] = held_k / 1e15 * 100
            f[FI["slot_in_leader"]] = sil; f[FI["intra"]] = (A[k] - s[k] * H.SMS) / H.SMS
            f[FI["n_follow"]] = nfol; f[FI["follow_sol"]] = folsol / 1e9; f[FI["entry_dip"]] = e_dip; f[FI["entry_sol"]] = bl[0]["sol"]
            f[FI["cost_sol"]] = tk_cost / 1e9; f[FI["tick_own"]] = own; f[FI["tick_buy"]] = buy[k]; f[FI["tick_sol"]] = sol[k] / 1e9; f[FI["tick_wt"]] = wt[k]
            f[FI["ret_lastbuy"]] = p[k] / p_lastbuy - 1
            f[FI["ob_since_lastbuy"]] = obl / 1e9; f[FI["os_since_lastbuy"]] = osl / 1e9; f[FI["price_vs_peak"]] = p[k] / pk_p - 1
            f[FI["n_trades_since"]] = k - kb0; f[FI["own_sold_frac"]] = sold_tok / tk_tot if tk_tot > 0 else 0
            ticks.append((len(out) - 1, k, int(s[k]), int(ii[k]), float(A[k]), f))
    return out, ticks
def work(b):
    tp = pickle.load(open(f"{OUT}/tp/b{b:02d}.pkl", "rb"))
    eps = []; TI = []; TF = []
    for m, d in tp.items():
        o, t = proc_mint(m, d)
        if not o: continue
        base = len(eps); eps += o
        if t:
            for (ei, k, s_, i_, a_, f) in t:
                TI.append((base + ei, k, s_, i_, a_)); TF.append(f)
    TI = np.array(TI, np.float64) if TI else np.zeros((0, 5)); TF = np.vstack(TF) if TF else np.zeros((0, len(FEATS)), np.float32)
    os.makedirs(f"{OUT}/ep", exist_ok=True)
    with open(f"{OUT}/ep/b{b:02d}.pkl", "wb") as f: pickle.dump(dict(eps=eps, TI=TI, TF=TF, feats=FEATS), f, protocol=4)
    return b, len(eps), len(TI)
if __name__ == "__main__":
    init()
    P = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    bs = [int(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else list(range(64))
    with Pool(P) as p:
        for b, ne, nt in p.imap_unordered(work, bs): print(b, ne, nt, flush=True)
    print("DONE", flush=True)
