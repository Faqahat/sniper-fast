#!/usr/bin/env python3
"""APEX2 step 3: per-launch replay with OUR buy inserted at fixed POSITIONS in the create slot (speed-independent rows).

usage: s1_sim.py RUN [--procs 3]      (needs tab/RUN from b1_build.py and tab/creator_counts.json from s0_creators.py)
Launches: standard SOL curves (b1_build filter), create bt <= run end - 180 s, creator with >= 2 launches in all tapes.

Create-slot structure (tape order = block order):
  create tx (dev buy inside) -> creator bundle = contiguous tx indices right after the create, each a buy of this mint
  -> other create-slot trades ("snipers") -> slot cs+1 ...
Positions (where our buy is inserted):
  P18  old APEX assumption: index ci + 0.085 * block size (18 ms on a linear in-block clock), never inside ci..ci+5
  A    right after the create + creator bundle (first non-bundle position)
  R1/R2 after the first 1 / 2 non-bundle create-slot trades (we lost the race to the fastest sniper(s))
  M    after half of the create-slot non-bundle trades
  E    end of the create slot (after every create-slot trade)
  N    middle of slot cs+1 (reactive next-slot reference)
Our buy: buy_exact_sol_in with S lamports all-in; pump fees (protocol + creator bps of the curve at that moment, ceil each);
tokens = floor(net*T/(V+net)) (verified against recorded reserves, c1_curvecheck.py).
Guard: revert if tokens < tokens at the post-create-tx state / 1.20 (only the tx fee is lost).
Replay after us (curve state = our modified one):
  fixed-token buys (Buy/BuyV3 ix): cost = floor(tok*V/(T-tok))+1; dropped if cost > real cost * (1+SLIP)
  other buys (BuyExactSolIn, routers): tokens = floor(sol*T/(V+sol)); dropped if tokens < real * (1-SLIP);
     a wallet that got fewer tokens sells that many fewer later
  dropped wallets' later sells are dropped; phi rows also drop 20%/40% of other wallets' buys after us (wallet hash)
  sells: proceeds floor(q*V/(T+q)); synthetic gap trades applied as recorded token deltas
Exits: sell decided at landing + HOLD, lands EXLAT slot later at that block position: h2 (2 s), h2L (2 s + 1 slot), h6 (6 s).
Curve completion (T below the real-token floor) freezes the replay; value x0.9.
Out: res/RUN.pkl  list of (mint, creator, bt, cs, ci, info dict, R float32[pos, size, phi, exit] curve net SOL, G bool[pos,size])"""
import sys, os, json, pickle, numpy as np
from multiprocessing import Pool

TAB = "/home/moiz/sniper-data/apex2/tab"; RES = os.environ.get("APEX2_RES", "/home/moiz/sniper-data/apex2/res")
POS = ("P18", "A", "R1", "R2", "M", "E", "N"); SIZES = (0.05, 0.2, 0.4); PHIS = (0.0, 0.2, 0.4); EXITS = ("h2", "h2L", "h6")
SLOT_S = 0.2125; SL = 1 / SLOT_S; EXLAT = 0.29; SLIP = float(os.environ.get("APEX2_SLIP", "0.10"))
HOLD = {"h2": 2 * SL, "h2L": 2 * SL + 1.0, "h6": 6 * SL}
TFLOOR = 1_073_000_000_000_000 - 793_100_000_000_000
V0, T0 = 30_000_000_000, 1_073_000_000_000_000
G = {}

def cdiv(a, b): return -(-a // b)

def clock(s, i):
    k = G["sidx"].get(s)
    b = G["bsz"][k] if k is not None else 700.0
    return s + min(i / b, 0.999999)

def drop_hash(u, phi):
    return phi > 0 and ((u * 2654435761 + 97) % 1000) < phi * 1000

def run(q):
    c = G["C"][q]; mid = G["mid"].get(c["mint"])
    if mid is None: a = b = 0                     # no trade at all on the tape: we would still buy (only us)
    else: a, b = G["gs"][mid], G["ge"][mid]
    tr = G["T"][a:b]
    cs, ci = int(c["slot"]), int(c["idx"])
    sv = tr["slot"].astype(np.int64).tolist(); iv = tr["idx"].astype(np.int64).tolist()
    n = len(sv)
    hz = cs + 6 * SL + 3 * SL + 4               # replay horizon (slots) for exits + margin
    nn = 0
    while nn < n and sv[nn] <= hz: nn += 1
    usr = tr["user"][:nn].tolist(); sgn = tr["signer"][:nn].tolist(); buy = tr["buy"][:nn].tolist()
    sol = [int(x) for x in tr["sol"][:nn]]; tok = [int(x) for x in tr["tok"][:nn]]
    vs = [int(x) for x in tr["vsol"][:nn]]; vt = [int(x) for x in tr["vtok"][:nn]]
    fb = tr["fee_bps"][:nn].tolist() or [95]; cb = tr["cfee_bps"][:nn].tolist() or [int(c.get("cfee_bps") or 30)]; ik = tr["ixk"][:nn].tolist(); syn = tr["syn"][:nn].tolist()
    txf = tr["txfee"][:nn].tolist(); tips = tr["tips"][:nn].tolist()
    tk = [clock(sv[k], iv[k]) for k in range(nn)]
    info = {"notrade": int(n == 0)}
    # first-trade chain check vs the initial curve
    if nn:
        pV, pT = (vs[0] - sol[0], vt[0] + tok[0]) if buy[0] else (vs[0] + sol[0], vt[0] - tok[0])
        info["chain0"] = (pV == V0 and pT == T0)
    # create tx trades, bundle, create-slot trades
    k = 0
    while k < nn and sv[k] == cs and iv[k] == ci: k += 1
    ncre = k; last = ci
    while k < nn and sv[k] == cs and iv[k] in (last, last + 1) and buy[k]:
        last = iv[k]; k += 1
    kb = k
    ke = kb
    while ke < nn and sv[ke] == cs: ke += 1
    k1 = ke
    while k1 < nn and sv[k1] == cs + 1: k1 += 1
    dev = usr[0] if ncre and buy[0] else None
    info.update(ncre=ncre, nb=kb - ncre, ncs=ke - kb, ns1=k1 - ke, dev_sol=(sol[0] / 1e9 if ncre and buy[0] else 0.0),
                bund_sol=sum(sol[x] for x in range(ncre, kb)) / 1e9, bund_users=len(set(usr[ncre:kb])),
                cs_buy_sol=sum(sol[x] for x in range(kb, ke) if buy[x]) / 1e9,
                cs_users=sorted(set(usr[x] for x in range(kb, ke) if buy[x])))
    # create-slot trades detail (for competitor study): (user, signer, offset idx-ci, rank, buy, sol, txfee, tips, in_bundle)
    info["sellc"] = [txf[x] + tips[x] for x in range(nn) if (not buy[x]) and (not syn[x]) and cs + 5 <= sv[x] <= cs + 20][:12]
    info["cst"] = [(usr[x], sgn[x], iv[x] - ci, x - ncre, buy[x], sol[x], txf[x], tips[x], int(x < kb)) for x in range(ncre, ke)]
    def state_before(k0):
        if k0 <= 0: return V0, T0
        return vs[k0 - 1], vt[k0 - 1]
    Vref, Tref = state_before(ncre)
    bsz = G["bsz"][G["sidx"][cs]] if cs in G["sidx"] else 700.0
    # positions -> (k0, landing clock)
    pos = {}
    ie = max(ci + 0.085 * bsz, ci + 6)
    kp = ncre
    while kp < nn and (sv[kp] < cs or (sv[kp] == cs and iv[kp] < ie)): kp += 1
    kp = max(kp, kb)
    pos["P18"] = (kp, cs + min(ie / bsz, 0.9999) if kp < ke or ke == kb else tk[kp - 1] + 1e-6)
    pos["A"] = (kb, (tk[kb - 1] + 1e-6) if kb > 0 else cs + ci / bsz)
    for nm_, r_ in (("R1", 1), ("R2", 2)):
        kr = min(kb + r_, ke)
        pos[nm_] = (kr, (tk[kr - 1] + 1e-6) if kr > 0 else cs + ci / bsz)
    km = kb + (ke - kb) // 2
    pos["M"] = (km, (tk[km - 1] + 1e-6) if km > 0 else cs + ci / bsz)
    pos["E"] = (ke, (tk[ke - 1] + 1e-6) if ke > 0 else cs + ci / bsz)
    kn = ke + (k1 - ke) // 2
    pos["N"] = (kn, max(cs + 1.5, (tk[kn - 1] + 1e-6) if kn > 0 else 0))
    info["pos_k"] = {p: v[0] for p, v in pos.items()}
    R = np.full((len(POS), len(SIZES), len(PHIS), len(EXITS)), np.nan, np.float32)
    Gd = np.zeros((len(POS), len(SIZES)), bool)
    for pi_, p in enumerate(POS):
        k0, tl = pos[p]
        V, T = state_before(k0)
        fbk = fb[max(0, min(k0, nn - 1))] + cb[max(0, min(k0, nn - 1))]
        for zi, S in enumerate(SIZES):
            L = int(S * 1e9)
            net = L * 10000 // (10000 + fbk)
            qq = net * T // (V + net); qref = net * Tref // (Vref + net)
            if qq * 1.20 < qref or T - qq < TFLOOR:
                continue
            Gd[pi_, zi] = True
            for hi, phi in enumerate(PHIS):
                V2 = V + net; T2 = T - qq
                tsell = {e: tl + HOLD[e] + EXLAT for e in EXITS}
                done = {}; dropped = set(); deficit = {}; grad = False
                k = k0; f_now = fbk
                def val(V2, T2, f_now):
                    pr = qq * V2 // (T2 + qq)
                    return pr - cdiv(pr * (f_now - cb_now[0]), 10000) - cdiv(pr * cb_now[0], 10000) - L
                cb_now = [cb[max(0, min(k0, nn - 1))]]
                while True:
                    t_k = tk[k] if k < nn else 1e18
                    for e in EXITS:
                        if e not in done and tsell[e] <= t_k: done[e] = val(V2, T2, f_now)
                    if len(done) == len(EXITS) or k >= nn or grad:
                        v = val(V2, T2, f_now)
                        for e in EXITS:
                            if e not in done: done[e] = v if not grad else int((v + L) * 0.9) - L
                        break
                    u = usr[k]; f_now = fb[k] + cb[k]; cb_now[0] = cb[k]
                    if syn[k]:
                        if buy[k]:
                            if T2 - tok[k] > 0:
                                need = tok[k] * V2 // (T2 - tok[k]) + 1; V2 += need; T2 -= tok[k]
                        else:
                            pr = tok[k] * V2 // (T2 + tok[k]); V2 -= pr; T2 += tok[k]
                    elif buy[k]:
                        drop = drop_hash(u, phi)
                        if not drop:
                            if ik[k] & 3:
                                if T2 - tok[k] <= TFLOOR // 2: drop = True
                                else:
                                    need = tok[k] * V2 // (T2 - tok[k]) + 1
                                    if need > sol[k] * (1 + SLIP): drop = True
                                    else: V2 += need; T2 -= tok[k]
                            else:
                                got = sol[k] * T2 // (V2 + sol[k])
                                if got < tok[k] * (1 - SLIP): drop = True
                                else:
                                    V2 += sol[k]; T2 -= got
                                    if got < tok[k]: deficit[u] = deficit.get(u, 0) + tok[k] - got
                        if drop: dropped.add(u)
                    elif u not in dropped:
                        qd = tok[k]; d = deficit.get(u, 0)
                        if d: x = min(d, qd); qd -= x; deficit[u] = d - x
                        if qd > 0:
                            pr = qd * V2 // (T2 + qd); V2 -= pr; T2 += qd
                    if T2 < TFLOOR: grad = True
                    k += 1
                for xi, e in enumerate(EXITS): R[pi_, zi, hi, xi] = done[e] / 1e9
    # pristine outcome of every create-slot buyer on this mint over the whole kept window (competitor P&L)
    allu = set(x[0] for x in info["cst"] if x[4])
    if allu:
        trA = tr; uA = trA["user"].tolist(); bA = trA["buy"].tolist(); sA = trA["sol"].tolist(); tA = trA["tok"].tolist()
        fA = (trA["fee_bps"].astype(np.int64)); cA = trA["cfee_bps"].astype(np.int64); xA = trA["txfee"].tolist(); pA = trA["tips"].tolist()
        synA = trA["syn"].tolist(); slA = trA["slot"].tolist()
        P = {u: [0, 0, 0, None, None, 0] for u in allu}   # sol net, tokens held, fees paid, first buy slot, first sell slot, n trades
        seen_tx = set()
        for x in range(len(uA)):
            u = uA[x]
            if u not in P or synA[x]: continue
            st = P[u]; s_ = int(sA[x])
            fee = cdiv(s_ * int(fA[x]), 10000) + cdiv(s_ * int(cA[x]), 10000)
            if bA[x]: st[0] -= s_ + fee; st[1] += int(tA[x]); st[3] = st[3] if st[3] is not None else slA[x]
            else: st[0] += s_ - fee; st[1] -= int(tA[x]); st[4] = st[4] if st[4] is not None else slA[x]
            key = (slA[x], int(trA["idx"][x]))
            if key not in seen_tx: seen_tx.add(key); st[2] += int(xA[x]) + int(pA[x])
            st[5] += 1
        Vl, Tl = int(trA["vsol"][-1]), int(trA["vtok"][-1])
        out = {}
        for u, st in P.items():
            h = max(st[1], 0); mark = (h * Vl // (Tl + h)) if h else 0
            out[u] = (st[0] / 1e9, st[2] / 1e9, mark / 1e9, st[3], st[4], st[5])
        info["cs_pnl"] = out
    info["bsz"] = bsz
    return q, (c["mint"], c["creator"], int(c["bt"]), cs, ci, info, R, Gd)

def main(run, procs):
    T = np.load(f"{TAB}/{run}/trades.npy"); S = np.load(f"{TAB}/{run}/slots.npy")
    ids = json.load(open(f"{TAB}/{run}/ids.json")); C = json.load(open(f"{TAB}/{run}/creates.json"))
    cc = json.load(open(f"{TAB}/creator_counts.json"))
    bt_end = int(S["bt"][-1])
    cl = [c for c in C.values() if c.get("std") and int(c["bt"]) <= bt_end - 180 and cc.get(c["creator"], 0) >= 2]
    cl.sort(key=lambda c: (c["slot"], c["idx"]))
    o = np.argsort(T["mint"], kind="stable"); T = T[o]
    um, gs = np.unique(T["mint"], return_index=True); ge = np.append(gs[1:], len(T))
    nm = len(ids); GS = np.zeros(nm, np.int64); GE = np.zeros(nm, np.int64); GS[um] = gs; GE[um] = ge
    G.update(T=T, gs=GS, ge=GE, C=cl, mid={ids[i]: i for i in um.tolist()},
             sidx={int(s): k for k, s in enumerate(S["slot"].tolist())}, bsz=(S["maxi"].astype(np.float64) + 1))
    out = [None] * len(cl)
    with Pool(procs) as P:
        for j, (q, r) in enumerate(P.imap_unordered(run_one, range(len(cl)), chunksize=200)):
            if r is not None and r[0] == "ERR":
                nerr = G.setdefault("nerr", 0) + 1; G["nerr"] = nerr
                if nerr <= 3: print("ERR", r[1], flush=True)
                r = None
            out[q] = r
            if j % 5000 == 0: print(run, j, len(cl), flush=True)
    out = [r for r in out if r is not None]
    os.makedirs(RES, exist_ok=True)
    pickle.dump(out, open(f"{RES}/{run}.pkl", "wb")); print(run, "saved", len(out), "of", len(cl), "errors", G.get("nerr", 0), flush=True)

def run_one(q):
    try: return run(q)
    except Exception as ex:
        import traceback
        return q, ("ERR", traceback.format_exc()[-400:])

if __name__ == "__main__":
    a = sys.argv[1:]; procs = 3
    if "--procs" in a: k = a.index("--procs"); procs = int(a[k + 1]); del a[k:k + 2]
    main(a[0], procs)
