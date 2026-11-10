#!/usr/bin/env python3
"""APEX-REALISM r1: replay APEX-3 picks with OUR buy inserted after j non-bundle trades (P0 = s3 position A, P1..P8),
sizes 0.2/0.4/1.0, phi 0/0.2, exits h2 / w0.4_6.0 / b0.3.  Curve, fee, slippage-drop and graduation rules copied verbatim
from apex3 s3_sim.py (which matched chain to the lamport on live fills).  Our own wallet's trades are removed from the tape.
Also stores every non-bundle trade in cs..cs+3 (clock offset from the create in slots, buy, SOL, signer, fee, tips) for the
landing model.  usage: r1_sim.py DAYIDX  (reads realism/picks.json)  -> realism/sim/<run>.pkl"""
import sys, os, json, pickle, numpy as np
from multiprocessing import Pool
PAYER = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"
SLOT_S = 0.2125; SL = 1 / SLOT_S; EXLAT = 0.29; OBS = 0.15; SLIP = 0.10
TFLOOR = 1_073_000_000_000_000 - 793_100_000_000_000; V0, T0 = 30_000_000_000, 1_073_000_000_000_000
NJ = 9; SIZES = (0.2, 0.4, 1.0); PHIS = (0.0, 0.2); EXITS = ("h2", "w0.4_6.0", "b0.3")
G = {}
def cdiv(a, b): return -(-a // b)
def clock(s, i):
    k = G["sidx"].get(s); b = G["bsz"][k] if k is not None else 700.0
    return s + min(i / b, 0.999999)
def drop_hash(u, phi): return phi > 0 and ((u * 2654435761 + 97) % 1000) < phi * 1000

def run(q):
    c = G["C"][q]; mid = G["mid"].get(c["mint"])
    a, b = (0, 0) if mid is None else (G["gs"][mid], G["ge"][mid])
    tr = G["T"][a:b]; tr = tr[tr["signer"] != G["pid"]]
    cs, ci = int(c["slot"]), int(c["idx"])
    sv = tr["slot"].astype(np.int64).tolist(); iv = tr["idx"].astype(np.int64).tolist(); n = len(sv)
    hz = cs + 14 * SL + 6; nn = 0
    while nn < n and sv[nn] <= hz: nn += 1
    usr = tr["user"][:nn].tolist(); buy = tr["buy"][:nn].tolist(); sgn = tr["signer"][:nn].tolist()
    sol = [int(x) for x in tr["sol"][:nn]]; tok = [int(x) for x in tr["tok"][:nn]]
    vs = [int(x) for x in tr["vsol"][:nn]]; vt = [int(x) for x in tr["vtok"][:nn]]
    fb = tr["fee_bps"][:nn].tolist() or [95]; cb = tr["cfee_bps"][:nn].tolist() or [int(c.get("cfee_bps") or 30)]
    ik = tr["ixk"][:nn].tolist(); syn = tr["syn"][:nn].tolist()
    txf = tr["txfee"][:nn].tolist(); tps = tr["tips"][:nn].tolist()
    tk = [clock(sv[k], iv[k]) for k in range(nn)]
    k = 0
    while k < nn and sv[k] == cs and iv[k] == ci: k += 1
    ncre = k; last = ci
    while k < nn and sv[k] == cs and iv[k] in (last, last + 1) and buy[k]: last = iv[k]; k += 1
    kb = k
    c0 = clock(cs, ci)
    riv = [(tk[x] - c0, buy[x], sol[x] / 1e9, G["ids"][sgn[x]], txf[x], tps[x], syn[x]) for x in range(kb, nn) if sv[x] <= cs + 3][:40]
    def state_before(k0): return (V0, T0) if k0 <= 0 else (vs[k0 - 1], vt[k0 - 1])
    Vref, Tref = state_before(ncre)
    R = np.full((NJ, len(SIZES), len(PHIS), len(EXITS)), np.nan, np.float32)
    for pj in range(NJ):
        k0 = kb + pj
        if k0 > nn: break
        tl = (tk[k0 - 1] + 1e-6) if k0 > 0 else c0
        V, T = state_before(k0); kk = max(0, min(k0, nn - 1)); fbk = fb[kk] + cb[kk]
        for zi, S in enumerate(SIZES):
            L = int(S * 1e9); net = L * 10000 // (10000 + fbk)
            qq = net * T // (V + net); qref = net * Tref // (Vref + net)
            if qq * 1.20 < qref or T - qq < TFLOOR: continue
            for hi, phi in enumerate(PHIS):
                V2 = V + net; T2 = T - qq; dropped = set(); deficit = {}; grad = False; f_now = fbk; cbn = cb[kk]
                def val(V2, T2):
                    pr = qq * V2 // (T2 + qq); return pr - cdiv(pr * (f_now - cbn), 10000) - cdiv(pr * cbn, 10000) - L
                traj_t = [tl]; traj_v = [val(V2, T2)]; ev = []; k = k0
                while k < nn and not grad:
                    u = usr[k]; f_now = fb[k] + cb[k]; cbn = cb[k]; happened = True
                    if syn[k]:
                        if buy[k]:
                            if T2 - tok[k] > 0: need = tok[k] * V2 // (T2 - tok[k]) + 1; V2 += need; T2 -= tok[k]
                        else: pr = tok[k] * V2 // (T2 + tok[k]); V2 -= pr; T2 += tok[k]
                        happened = False
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
                        if drop: dropped.add(u); happened = False
                    elif u not in dropped:
                        qd = tok[k]; d = deficit.get(u, 0)
                        if d: x = min(d, qd); qd -= x; deficit[u] = d - x
                        if qd > 0: pr = qd * V2 // (T2 + qd); V2 -= pr; T2 += qd
                    else: happened = False
                    if T2 < TFLOOR: grad = True
                    traj_t.append(tk[k]); v = val(V2, T2)
                    traj_v.append(int((v + L) * 0.9) - L if grad else v)
                    if happened: ev.append((tk[k], buy[k], sol[k]))
                    k += 1
                tt = np.array(traj_t); tv = np.array(traj_v, np.float64)
                def at(t):
                    j = np.searchsorted(tt, t, "right") - 1; return tv[max(j, 0)] / 1e9
                out = [at(tl + 2.0 * SL + EXLAT)]
                X = 0.4 * SL; Y = tl + 6.0 * SL; lastb = tl; d = None
                for t_ in (x[0] for x in ev if x[1]):
                    if t_ - lastb >= X: d = lastb + X; break
                    lastb = max(lastb, t_)
                if d is None: d = lastb + X
                out.append(at(min(d, Y) + OBS + EXLAT))
                d = next((x[0] for x in ev if x[1] and x[2] >= 0.3e9), None)
                d = tl + 6 * SL if d is None or d > tl + 6 * SL else d + OBS
                out.append(at(d + EXLAT))
                R[pj, zi, hi, :] = out
    return q, (c["mint"], cs, ci, kb - ncre, riv, R)

def run_one(q):
    try: return run(q)
    except Exception:
        import traceback; return q, ("ERR", traceback.format_exc()[-600:])

def main(d):
    P = json.load(open("/home/it/sniper-data/apex2/realism/picks.json")); run_ = "run_" + P["runs"][d]
    TAB = ("/home/it/sniper-data/apex2/realism/tab/" if run_ == "run_20261103_1245" else "/home/it/sniper-data/apex2/tab/") + run_
    want = {p["mint"] for p in P["picks"] if p["day"] == d}
    T = np.load(f"{TAB}/trades.npy"); S = np.load(f"{TAB}/slots.npy"); C = json.load(open(f"{TAB}/creates.json"))
    ids = json.load(open(f"{TAB}/ids.json"))
    cl = [C[m] for m in want if m in C]
    o = np.argsort(T["mint"], kind="stable"); T = T[o]
    um, gs = np.unique(T["mint"], return_index=True); ge = np.append(gs[1:], len(T))
    GS = np.zeros(len(ids), np.int64); GE = np.zeros(len(ids), np.int64); GS[um] = gs; GE[um] = ge
    G.update(T=T, gs=GS, ge=GE, C=cl, mid={ids[i]: i for i in um.tolist()}, ids=ids, pid=(ids.index(PAYER) if PAYER in ids else -1),
             sidx={int(s): k for k, s in enumerate(S["slot"].tolist())}, bsz=(S["maxi"].astype(np.float64) + 1))
    out = []; ne = 0
    with Pool(3) as Pp:
        for q, r in Pp.imap_unordered(run_one, range(len(cl)), chunksize=20):
            if r[0] == "ERR":
                ne += 1
                if ne <= 3: print("ERR", r[1], flush=True)
                continue
            out.append(r)
    os.makedirs("/home/it/sniper-data/apex2/realism/sim", exist_ok=True)
    pickle.dump(out, open(f"/home/it/sniper-data/apex2/realism/sim/{run_}.pkl", "wb"))
    print(run_, "picks", len(want), "replayed", len(out), "errors", ne, flush=True)

if __name__ == "__main__": main(int(sys.argv[1]))
