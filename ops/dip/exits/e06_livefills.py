#!/usr/bin/env python3
# e06: the SAME exits on our REAL live buys (recon pertrade.json: FRA r10-r15, AMS r9-r14, 10-24 16:59 -> 10-25 07:50 PKT) at their
# EXACT chain landing position (no landing model at all: this removes the "independent landing draw" optimism), 0.35 SOL, the
# corrected replay with our own trades removed. Output in the e02 format (li = 0) so every policy and model applies unchanged.
# -> /home/moiz/sniper-data/exits/paths/paths_live.npz (+ live_index.json: did, live fill flag, server, run)
import sys, os, json, zlib, bisect, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import exit_lib as E
import e02_paths as P2

if __name__ == "__main__":
    T0 = time.time()
    PT = json.load(open("/home/moiz/sniper-data/recon/work/pertrade.json"))
    D = dict(np.load(f"{E.DATA}/dumps.npz"))
    TP = {"A": E.Tape("A"), "B": E.Tape("B")}
    m2t = {tag: {m["m"]: t for t, m in enumerate(TP[tag].meta)} for tag in TP}
    key = {}
    for did in range(len(D["t"])):
        key[(int(D["tag"][did]), int(D["k"][did]))] = did
    CV = E.Curves()
    tl, sl, _, _ = E.sell_latency_tables()
    RTL = [list(tl), [35.0], [50.0], [75.0]]; REV = [list(sl), [35.0], [50.0], [75.0]]
    K = P2.K
    ENT = []; TRJ = []; FT = []; TV = []; EVS = []; idx = []
    miss = 0
    for o in PT:
        hit = None
        for ti, tag in enumerate(("A", "B")):
            t = m2t[tag].get(o["mint"])
            if t is None: continue
            tp = TP[tag].token(t)
            js = [j for j in range(tp["n"]) if tp["s"][j] == o["dump_slot"] and tp["i"][j] == o["dump_idx"] and not tp["buy"][j]]
            if not js: continue
            j0 = min(js, key=lambda j: abs(tp["sol"][j] / 1e9 - (o.get("sell") or 0)))
            did = key.get((ti, int(TP[tag].off[t]) + j0))
            if did is None: continue
            hit = (tag, t, j0, did); break
        if hit is None: miss += 1; continue
        tag, t, j0, did = hit; tp = TP[tag].token(t)
        rowkey = zlib.crc32(f"{tp['s'][j0]}:{int(tp['arr'][j0] * 1000)}:{j0}".encode())
        res = E.simulate(tp, j0, at=(o["land_slot"], o["land_idx"]), CV=CV, rowkey=rowkey, kmax=K + 6)
        crowd = P2.dump_crowd(tp, j0)
        ENT.append((did, 0, o["L_meas"], res["st"], res["ratio"], res["ahead"]) + crowd)
        idx.append(dict(did=did, srv=o["srv"], run=o["run"], live_fill=o["live_fill"], st=res["st"], chain_pnl=o["chain_pnl"], size=o["size"], t=o["t_fire"]))
        if res["st"] != 0: continue
        ev = res["ev"]; ea = [x[0] for x in ev]; ev_val = [x[6] for x in ev]; v0 = res["v0"]
        def va(tt):
            lo = bisect.bisect_left(ea, tt)
            return ev_val[lo - 1] if lo > 0 else v0
        s_in = res["s_in"]
        tv = np.zeros((4, K + 1), np.float32)
        for k in range(1, K + 1):
            base = (s_in + k) * E.SMS
            for r in range(4): tv[r, k] = np.mean([va(base + x) for x in RTL[r]])
        tv[:, 0] = v0
        tK = (s_in + K) * E.SMS; ne = bisect.bisect_left(ea, tK)
        sv = np.zeros((ne, 4), np.float32)
        for e in range(ne):
            for r in range(4): sv[e, r] = np.mean([va(ea[e] + x) for x in REV[r]])
        ph = E.pre_holders(tp, j0, res)
        FT.append(E.tick_features(res, tp, j0, K, ph)); TV.append(tv)
        TRJ.append((did, 0, o["L_meas"], s_in, res["a_in"], v0, res["q"], res["ahead"], res["ratio"], len(ph[0])))
        EVS.append((np.array(ea[:ne], np.float64), np.array([x[1] for x in ev[:ne]], np.int64), np.array([x[2] for x in ev[:ne]], np.int8),
                    np.array([x[3] for x in ev[:ne]], np.float64) / 1e9, np.array([x[4] for x in ev[:ne]], np.int8), np.array(ev_val[:ne], np.float32), sv))
    EVO = [0]
    for e in EVS: EVO.append(EVO[-1] + len(e[0]))
    cat = lambda i, dt: np.concatenate([e[i] for e in EVS]).astype(dt)
    np.savez(f"{E.DATA}/paths/paths_live.npz", ent=np.array(ENT, np.float64), trj=np.array(TRJ, np.float64), ft=np.stack(FT), tv=np.stack(TV),
             ev_a=cat(0, np.float64), ev_s=cat(1, np.int64), ev_b=cat(2, np.int8), ev_sol=cat(3, np.float64), ev_c=cat(4, np.int8), ev_v=cat(5, np.float32),
             ev_sv=np.concatenate([e[6] for e in EVS]), ev_off=np.array(EVO, np.int64), K=K, tf=np.array(E.TF), rtl=np.array(RTL[0]), rev=np.array(REV[0]))
    json.dump(idx, open(f"{E.DATA}/paths/live_index.json", "w"))
    nf = sum(1 for x in idx if x["st"] == 0); lf = sum(1 for x in idx if x["live_fill"])
    agree = sum(1 for x in idx if (x["st"] == 0) == bool(x["live_fill"]))
    print(f"live fires {len(PT)}: located {len(idx)}, missing {miss}; replay fills {nf} (live fills {lf}); fill/fail agreement {agree}/{len(idx)}; {time.time() - T0:.0f} s")
