#!/usr/bin/env python3
"""APEX-REALISM r3: launch replay with the LIVE-MEASURED landing model built in.
For every launch and every draw c of our arrival clock (81 live-measured chain positions, slots after the create; also
x0.75 / x1.25): rows ahead = tape rows (our wallet removed) with clock < c; our buy is replayed right after them with the
hold clock starting at our real landing time (create clock + c).  Curve/fee/drop/graduation rules = apex3 s3_sim verbatim.
Guards per draw: first (no other buy >= 0.05 SOL ahead), top2 (<= 1), none, Ap (creator-bundle-aware: buys landing within
0.02 slot of the create count as bundle).  Stores per launch, per (scale, guard, size, phi, exit): mean gross value over
landed draws x P(land) and P(land); plus the old sim-A value (tl at the create, as APEX-3 assumed).
usage: r3_sim.py DAY  (all serial launches of that day; picks get sizes 0.2/0.4/1.0 x phi 0/0.2 x 3 exits, others 0.4/phi0/h2)
       r3_sim.py LIVE (the 81 live attempts at their own size, + value at our ACTUAL measured clock)"""
import sys, os, json, pickle, numpy as np
from multiprocessing import Pool
PAYER = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"; RD = "/home/it/sniper-data/apex2/realism"
SLOT_S = 0.2125; SL = 1 / SLOT_S; EXLAT = 0.29; OBS = 0.15; SLIP = 0.10
TFLOOR = 1_073_000_000_000_000 - 793_100_000_000_000; V0, T0 = 30_000_000_000, 1_073_000_000_000_000
THR = 0.05; INST = 0.02; SCALES = (0.75, 1.0, 1.25); GUARDS = ("first", "top2", "none", "Ap")
OC = np.array(json.load(open(f"{RD}/landing_model.json"))["our_clk"])
EXITS = ("h2", "w0.4_6.0", "b0.3"); PHIS = (0.0, 0.2)
G = {}
def cdiv(a, b): return -(-a // b)
def clock(s, i):
    k = G["sidx"].get(s); b = G["bsz"][k] if k is not None else 700.0
    return s + min(i / b, 0.999999)
def drop_hash(u, phi): return phi > 0 and ((u * 2654435761 + 97) % 1000) < phi * 1000

def traj(D, k0, tl0, S, phi):
    """replay with our buy of S SOL inserted before tape row k0; returns (tt, tv, buy-events) or None (guard drop)"""
    nn, usr, buy, sol, tok, vs, vt, fb, cb, ik, syn, tk, Vref, Tref = D
    V, T = (V0, T0) if k0 <= 0 else (vs[k0 - 1], vt[k0 - 1])
    kk = max(0, min(k0, nn - 1)); fbk = fb[kk] + cb[kk]
    L = int(S * 1e9); net = L * 10000 // (10000 + fbk)
    qq = net * T // (V + net); qref = net * Tref // (Vref + net)
    if qq * 1.20 < qref or T - qq < TFLOOR: return None
    V2 = V + net; T2 = T - qq; dropped = set(); deficit = {}; grad = False; f_now = fbk; cbn = cb[kk]
    def val(V2, T2):
        pr = qq * V2 // (T2 + qq); return pr - cdiv(pr * (f_now - cbn), 10000) - cdiv(pr * cbn, 10000) - L
    tt = [tl0]; tv = [val(V2, T2)]; ev = []; k = k0
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
        tt.append(tk[k]); v = val(V2, T2); tv.append(int((v + L) * 0.9) - L if grad else v)
        if happened and buy[k]: ev.append((tk[k], sol[k]))
        k += 1
    return np.array(tt), np.array(tv, np.float64) / 1e9, ev

def exits(tr, tl):
    tt, tv, ev = tr
    def at(t):
        j = np.searchsorted(tt, t, "right") - 1; return tv[max(j, 0)]
    out = [at(tl + 2.0 * SL + EXLAT)]
    X = 0.4 * SL; Y = tl + 6.0 * SL; lastb = tl; d = None
    for t_, _ in ev:
        if t_ < tl: continue
        if t_ - lastb >= X: d = lastb + X; break
        lastb = max(lastb, t_)
    if d is None: d = lastb + X
    out.append(at(min(d, Y) + OBS + EXLAT))
    d = next((t_ for t_, s_ in ev if t_ >= tl and s_ >= 0.3e9), None)
    d = tl + 6 * SL if d is None or d > tl + 6 * SL else d + OBS
    out.append(at(d + EXLAT)); return out

def run(q):
    c, sizes, full, extra_clk = G["C"][q]
    mid = G["mid"].get(c["mint"])
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
    ik = tr["ixk"][:nn].tolist(); syn = tr["syn"][:nn].tolist(); txf = tr["txfee"][:nn].tolist(); tps = tr["tips"][:nn].tolist()
    tk = [clock(sv[k], iv[k]) for k in range(nn)]
    k = 0
    while k < nn and sv[k] == cs and iv[k] == ci: k += 1
    ncre = k; last = ci
    while k < nn and sv[k] == cs and iv[k] in (last, last + 1) and buy[k]: last = iv[k]; k += 1
    kb = k; c0 = clock(cs, ci)
    Vref, Tref = (V0, T0) if ncre <= 0 else (vs[ncre - 1], vt[ncre - 1])
    D = (nn, usr, buy, sol, tok, vs, vt, fb, cb, ik, syn, tk, Vref, Tref)
    rclk = np.array([tk[x] - c0 for x in range(kb, nn)]); rel = np.array([bool(buy[x] and sol[x] >= THR * 1e9 and not syn[x]) for x in range(kb, nn)], bool)
    relc = rclk[rel] if len(rel) else np.zeros(0)
    feat = dict(nb=kb - ncre, rc=float(relc[0]) if len(relc) else 9.0,
                n_inst=int((relc <= INST).sum()), rc_after_inst=float(relc[relc > INST][0]) if (relc > INST).any() else 9.0,
                first=(None if not rel.any() else (lambda x: (sgn[x], txf[x], tps[x], sol[x] / 1e9))(kb + int(np.flatnonzero(rel)[0]))))
    feat["first"] = None if feat["first"] is None else (G["ids"][feat["first"][0]],) + feat["first"][1:]
    phis = PHIS if full else (0.0,); exn = 3 if full else 1
    cache = {}
    def tj(j, zi, hi):
        key = (j, zi, hi)
        if key not in cache:
            k0 = kb + j; tl0 = (tk[k0 - 1] + 1e-6) if k0 > 0 else c0
            cache[key] = traj(D, k0, tl0, sizes[zi], phis[hi])
        return cache[key]
    # old sim-A reference (tl at the end of the bundle)
    Aref = np.full((len(sizes), len(phis), exn), np.nan, np.float32)
    for zi in range(len(sizes)):
        for hi in range(len(phis)):
            t_ = tj(0, zi, hi)
            if t_ is not None: Aref[zi, hi] = exits(t_, t_[0][0])[:exn]
    EV = np.zeros((len(SCALES), len(GUARDS), len(sizes), len(phis), exn), np.float32)   # sum over draws of gross value when landed / N
    PL = np.zeros((len(SCALES), len(GUARDS), len(sizes)), np.float32)
    for si, sc in enumerate(SCALES):
        for cv in OC * sc:
            j = int(np.searchsorted(rclk, cv, "left")) if len(rclk) else 0
            nra = int(rel[:j].sum()); nrb = int((rel[:j] & (rclk[:j] > INST)).sum())
            oks = (nra == 0, nra <= 1, True, nrb == 0)
            if not any(oks): continue
            for zi in range(len(sizes)):
                for hi in range(len(phis)):
                    t_ = tj(j, zi, hi)
                    if t_ is None: continue
                    ex = exits(t_, max(t_[0][0], c0 + cv))[:exn]
                    for gi, ok in enumerate(oks):
                        if ok:
                            EV[si, gi, zi, hi] += ex
                            if hi == 0: PL[si, gi, zi] += 1
    EV /= len(OC); PL /= len(OC)
    draws = None
    if extra_clk is not None:   # live: per-draw net-of-nothing value under guard first (nan = revert), scale 1.0
        draws = []
        for cv in OC:
            j = int(np.searchsorted(rclk, cv, "left")) if len(rclk) else 0
            t_ = tj(j, 0, 0) if int(rel[:j].sum()) == 0 else None
            draws.append(np.nan if t_ is None else exits(t_, max(t_[0][0], c0 + cv))[0])
    act = None
    if extra_clk is not None:   # live: value at our measured clock (no guard) and the rows ahead
        j = int(np.searchsorted(rclk, extra_clk, "left")) if len(rclk) else 0
        t_ = tj(j, 0, 0); act = (j, None if t_ is None else exits(t_, max(t_[0][0], c0 + extra_clk)), int(rel[:j].sum()))
    return q, (c["mint"], feat, Aref, EV, PL, act, draws)

def run_one(q):
    try: return run(q)
    except Exception:
        import traceback; return q, ("ERR", traceback.format_exc()[-800:])

def load_day(run_):
    TAB = (f"{RD}/tab/" if run_ == "run_20261103_1245" else "/home/it/sniper-data/apex2/tab/") + run_
    T = np.load(f"{TAB}/trades.npy"); S = np.load(f"{TAB}/slots.npy"); C = json.load(open(f"{TAB}/creates.json"))
    ids = json.load(open(f"{TAB}/ids.json"))
    o = np.argsort(T["mint"], kind="stable"); T = T[o]
    um, gs = np.unique(T["mint"], return_index=True); ge = np.append(gs[1:], len(T))
    GS = np.zeros(len(ids), np.int64); GE = np.zeros(len(ids), np.int64); GS[um] = gs; GE[um] = ge
    G.update(T=T, gs=GS, ge=GE, mid={ids[i]: i for i in um.tolist()}, ids=ids, pid=(ids.index(PAYER) if PAYER in ids else -1),
             sidx={int(s): k for k, s in enumerate(S["slot"].tolist())}, bsz=(S["maxi"].astype(np.float64) + 1))
    return C

def go(jobs, outf):
    G["C"] = jobs; out = []; ne = 0
    with Pool(3) as Pp:
        for i, (q, r) in enumerate(Pp.imap_unordered(run_one, range(len(jobs)), chunksize=25)):
            if r[0] == "ERR":
                ne += 1
                if ne <= 3: print("ERR", r[1], flush=True)
                continue
            out.append(r)
            if i % 5000 == 0: print(outf, i, len(jobs), flush=True)
    pickle.dump(out, open(outf, "wb")); print(outf, "done", len(out), "errors", ne, flush=True)

if __name__ == "__main__":
    os.makedirs(f"{RD}/sim3", exist_ok=True)
    if sys.argv[1] == "LIVE":
        C = load_day("run_20261103_1245")
        live = {(x["run"], x["id"]): x for x in json.load(open(f"{RD}/live_tape.json"))}
        jobs = [(C[x["mint"]], (x["size"],), False, x["ours_tape"]["clk"]) for x in live.values()]
        go(jobs, f"{RD}/sim3/LIVE.pkl")
    else:
        d = int(sys.argv[1]); A = json.load(open(f"{RD}/all_launches.json"))
        P = json.load(open(f"{RD}/picks.json")); run_ = "run_" + P["runs"][d]
        C = load_day(run_)
        jobs = [(C[x["mint"]], (0.2, 0.4, 1.0) if x["sel"] else (0.4,), x["sel"], None) for x in A if x["day"] == d and x["mint"] in C]
        go(jobs, f"{RD}/sim3/{run_}.pkl")
