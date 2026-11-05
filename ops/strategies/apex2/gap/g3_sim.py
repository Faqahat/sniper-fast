#!/usr/bin/env python3
"""APEX-GAP step 3: the study's simulator (s1_sim.run, unchanged) on each probe launch, with OUR wallet's trades removed from
the tape (= the tape the study would have seen), plus an instrumented copy of its replay loop that also values the position
at arbitrary sell clocks (our REAL sell slot/idx) and reports the tape during the hold.
Checks the copy reproduces s1_sim's R exactly. Out: /home/moiz/sniper-data/apex2/gap/sim_probes.json"""
import sys, os, json, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/apex2")
import s1_sim as S
GAP = "/home/moiz/sniper-data/apex2/gap"; RUN = "run_20261103_1245"; US = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"
D = f"{GAP}/tab/{RUN}"
cdiv = S.cdiv

def setup(drop_us=True, mints=None):
    T = np.load(f"{D}/trades.npy"); SL = np.load(f"{D}/slots.npy"); ids = json.load(open(f"{D}/ids.json")); C = json.load(open(f"{D}/creates.json"))
    I = {k: i for i, k in enumerate(ids)}
    if drop_us and US in I: T = T[(T["user"] != I[US]) & (T["signer"] != I[US])]
    o = np.argsort(T["mint"], kind="stable"); T = T[o]
    um, gs = np.unique(T["mint"], return_index=True); ge = np.append(gs[1:], len(T))
    nm = len(ids); GS = np.zeros(nm, np.int64); GE = np.zeros(nm, np.int64); GS[um] = gs; GE[um] = ge
    cl = [C[m] for m in mints] if mints is not None else None
    S.G.clear()
    S.G.update(T=T, gs=GS, ge=GE, C=cl, mid={ids[i]: i for i in um.tolist()},
               sidx={int(s): k for k, s in enumerate(SL["slot"].tolist())}, bsz=(SL["maxi"].astype(np.float64) + 1))
    return ids, I, C

def replay(q, Sz, sell_clocks, pos="A"):
    """instrumented copy of s1_sim.run's replay for one position/size at phi 0; returns value (curve net, lamports) at each
    sell clock, plus h2/h2L/h6 like the original, our tokens and entry state"""
    G = S.G; c = G["C"][q]; mid = G["mid"].get(c["mint"])
    a, b = (G["gs"][mid], G["ge"][mid]) if mid is not None else (0, 0)
    tr = G["T"][a:b]; cs, ci = int(c["slot"]), int(c["idx"])
    sv = tr["slot"].astype(np.int64).tolist(); iv = tr["idx"].astype(np.int64).tolist(); n = len(sv)
    hz = cs + 6 * S.SL + 3 * S.SL + 4 + 40
    nn = 0
    while nn < n and sv[nn] <= hz: nn += 1
    usr = tr["user"][:nn].tolist(); buy = tr["buy"][:nn].tolist()
    sol = [int(x) for x in tr["sol"][:nn]]; tok = [int(x) for x in tr["tok"][:nn]]
    vs = [int(x) for x in tr["vsol"][:nn]]; vt = [int(x) for x in tr["vtok"][:nn]]
    fb = tr["fee_bps"][:nn].tolist() or [95]; cb = tr["cfee_bps"][:nn].tolist() or [30]; ik = tr["ixk"][:nn].tolist(); syn = tr["syn"][:nn].tolist()
    tk = [S.clock(sv[k], iv[k]) for k in range(nn)]
    k = 0
    while k < nn and sv[k] == cs and iv[k] == ci: k += 1
    ncre = k; last = ci
    while k < nn and sv[k] == cs and iv[k] in (last, last + 1) and buy[k]: last = iv[k]; k += 1
    kb = k; ke = kb
    while ke < nn and sv[ke] == cs: ke += 1
    def sb(k0): return (V0, T0) if k0 <= 0 else (vs[k0 - 1], vt[k0 - 1])
    V0, T0 = S.V0, S.T0
    bsz = G["bsz"][G["sidx"][cs]] if cs in G["sidx"] else 700.0
    if pos == "A": k0 = kb; tl = (tk[kb - 1] + 1e-6) if kb > 0 else cs + ci / bsz
    elif pos == "E": k0 = ke; tl = (tk[ke - 1] + 1e-6) if ke > 0 else cs + ci / bsz
    V, T = sb(k0); Vref, Tref = sb(ncre)
    fbk = fb[max(0, min(k0, nn - 1))] + cb[max(0, min(k0, nn - 1))]
    L = int(Sz * 1e9); net = L * 10000 // (10000 + fbk); qq = net * T // (V + net); qref = net * Tref // (Vref + net)
    out = dict(kb=kb, ke=ke, ncre=ncre, nb=kb - ncre, ncs=ke - kb, V_entry=V, T_entry=T, qq=qq, net_in=net, tl=tl, bsz=bsz,
               guard_ok=not (qq * 1.20 < qref or T - qq < S.TFLOOR))
    tsell = {f"h2": tl + S.HOLD["h2"] + S.EXLAT, "h2L": tl + S.HOLD["h2L"] + S.EXLAT, "h6": tl + S.HOLD["h6"] + S.EXLAT}
    for j, x in enumerate(sell_clocks): tsell[f"x{j}"] = x
    V2 = V + net; T2 = T - qq; cbn = [cb[max(0, min(k0, nn - 1))]]; f_now = fbk
    done = {}; dropped = set(); deficit = {}; grad = False; k = k0; hold = []
    def val(V2, T2, f_now):
        pr = qq * V2 // (T2 + qq)
        return pr - cdiv(pr * (f_now - cbn[0]), 10000) - cdiv(pr * cbn[0], 10000) - L, pr
    while True:
        t_k = tk[k] if k < nn else 1e18
        for e in tsell:
            if e not in done and tsell[e] <= t_k: done[e] = val(V2, T2, f_now) + (k,)
        if len(done) == len(tsell) or k >= nn or grad:
            v = val(V2, T2, f_now)
            for e in tsell:
                if e not in done: done[e] = ((v[0] if not grad else int((v[0] + L) * 0.9) - L), v[1], k)
            break
        u = usr[k]; f_now = fb[k] + cb[k]; cbn[0] = cb[k]
        ev = None
        if syn[k]:
            if buy[k]:
                if T2 - tok[k] > 0: need = tok[k] * V2 // (T2 - tok[k]) + 1; V2 += need; T2 -= tok[k]
            else: pr = tok[k] * V2 // (T2 + tok[k]); V2 -= pr; T2 += tok[k]
            ev = ("syn", buy[k], tok[k])
        elif buy[k]:
            drop = False
            if ik[k] & 3:
                if T2 - tok[k] <= S.TFLOOR // 2: drop = True
                else:
                    need = tok[k] * V2 // (T2 - tok[k]) + 1
                    if need > sol[k] * (1 + S.SLIP): drop = True
                    else: V2 += need; T2 -= tok[k]
            else:
                got = sol[k] * T2 // (V2 + sol[k])
                if got < tok[k] * (1 - S.SLIP): drop = True
                else:
                    V2 += sol[k]; T2 -= got
                    if got < tok[k]: deficit[u] = deficit.get(u, 0) + tok[k] - got
            if drop: dropped.add(u)
            ev = ("B", u, sol[k], int(drop))
        elif u not in dropped:
            qd = tok[k]; d = deficit.get(u, 0)
            if d: x = min(d, qd); qd -= x; deficit[u] = d - x
            if qd > 0: pr = qd * V2 // (T2 + qd); V2 -= pr; T2 += qd
            ev = ("S", u, sol[k], 0)
        else: ev = ("S", u, sol[k], 1)
        hold.append((sv[k] - cs, iv[k], round(tk[k] - tl, 3)) + ev)
        if T2 < S.TFLOOR: grad = True
        k += 1
    out["vals"] = {e: (int(v[0]), int(v[1]), int(v[2])) for e, v in done.items()}
    out["hold"] = hold
    out["users_ncre"] = usr[:ncre]; out["bundle_users"] = usr[ncre:kb]
    return out

if __name__ == "__main__":
    P = json.load(open(f"{GAP}/probes.json"))
    mints = [r["mint"] for r in P]
    ids, I, C = setup(True, mints)
    res = []
    for q, r in enumerate(P):
        _, (mint, cre, bt, cs, ci, info, R, Gd) = S.run(q)
        sz = r["spend"] / 1e9; zi = S.SIZES.index(sz)
        clocks = []
        if r.get("sell_slot"):
            clocks.append(S.clock(r["sell_slot"], r["sell_idx"]))
        x = replay(q, sz, clocks)
        x4 = replay(q, 0.4, clocks)
        chk = all(abs(x["vals"][e][0] / 1e9 - float(R[1, zi, 0, j])) < 2e-6 for j, e in enumerate(("h2", "h2L", "h6"))) if Gd[1, zi] else None
        x["hold"] = [(h[0], h[1], h[2], h[3], ids[h[4]] if isinstance(h[4], int) and h[3] in ("B", "S") else h[4]) + tuple(h[5:]) for h in x["hold"]]
        res.append(dict(run=r["run"], id=r["id"], mint=mint, ev_creator=cre, bt=bt, cs=cs, ci=ci, size=sz,
                        R_A={e: float(R[1, zi, 0, j]) for j, e in enumerate(("h2", "h2L", "h6"))}, G_A=bool(Gd[1, zi]),
                        R_A04_h2=float(R[1, 2, 0, 0]), R_E_h2=float(R[5, zi, 0, 0]), R_P18_h2=float(R[0, zi, 0, 0]),
                        info={k: info[k] for k in ("nb", "ncs", "ns1", "dev_sol", "bund_sol", "bund_users", "cs_buy_sol")},
                        check_copy_eq_s1=chk, sim=x, sim04_vals=x4["vals"]))
        print(r["run"], r["id"], mint[:6], r["outcome"], "R_A h2 %+.2f mSOL" % (R[1, zi, 0, 0] * 1e3), "check", chk, "nb", info["nb"], "ncs", info["ncs"],
              "vals", {e: round(v[0] / 1e6, 2) for e, v in x["vals"].items()})
    json.dump(res, open(f"{GAP}/sim_probes.json", "w"), default=lambda o: o.item() if hasattr(o, "item") else str(o))
