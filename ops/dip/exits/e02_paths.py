#!/usr/bin/env python3
# e02: corrected-replay paths for every dump of the study universe (envelope dumps with M2 >= -0.005, plus every IMIT1 top4 pick),
# at 13 landing points each: the 10 deciles of OUR MEASURED landing for that slot leader's client group (recon fires, 309 live
# buys) + fixed 35 / 50 / 75 ms. 0.35 SOL, +5% guard vs the post-dump price.
# For every fill: tick values (sell decided at the start of slot s_in + k, k = 1..30, landing rows: MEASURED time-limit sells /
# 35 / 50 / 75 ms), causal tick features, and the post-entry event stream with the value of a sell triggered by each event
# (landing rows: MEASURED stop-loss sells / 35 / 50 / 75 ms after the trigger).
# -> /home/moiz/sniper-data/exits/paths/part_*.npz  (then e03 concatenates)
import sys, os, json, zlib, bisect, time
import numpy as np
from multiprocessing import get_context
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import exit_lib as E

K = 30
OUTD = f"{E.DATA}/paths"
CROWD = float(os.environ.get("EX_CROWD", "0"))          # model check "+crowd" sensitivity (0.4); output paths2_crowd.npz
HAQQ = zlib.crc32(b"haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq")
G = {}


def dump_crowd(tp, j0):
    """real-tape crowd measures of the dump (for SEGMENTING results only, never a feature): distinct target fast bots / cohort
    bots buying in the dump slot .. +3 slots, their SOL, haqq present, all outside buys in that window"""
    S = tp["s"]; B = tp["buy"]; CL = tp["cls"]; U = tp["uid"]; SOL = tp["sol"]
    s_end = S[j0] + 3; tg = set(); co = set(); tsol = 0.0; nb = 0; bsol = 0.0; hq = 0
    for j in range(j0 + 1, tp["n"]):
        if S[j] > s_end: break
        if not B[j] or CL[j] == 9: continue
        nb += 1; bsol += SOL[j]
        if CL[j] == 1: tg.add(U[j]); tsol += SOL[j]
        elif CL[j] == 2: co.add(U[j])
        if U[j] == HAQQ: hq = 1
    return len(tg), tsol / 1e9, len(co), hq, nb, bsol / 1e9


def work(job):
    tag, t, rows = job                           # rows: list of (dump id, local j0, group)
    TP = G["tapes"][tag]; tp = TP.token(t); CV = G["CV"]; LT = G["LT"]; RTL = G["RTL"]; REV = G["REV"]
    ent = []; trj = []; feats = []; tvals = []; evs = []
    for did, j0, grp in rows:
        rowkey = zlib.crc32(f"{tp['s'][j0]}:{int(tp['arr'][j0] * 1000)}:{j0}".encode())
        crowd = dump_crowd(tp, j0)
        cb = 1 if crowd[0] >= 3 else 0
        Ls = list(LT[grp]) + [35.0, 50.0, 75.0] + list(G["LTC"][(grp, cb)])
        for li, L in enumerate(Ls):
            res = E.simulate(tp, j0, L=float(L), CV=CV, rowkey=rowkey, kmax=K + 6, crowd=CROWD)
            st = res["st"]
            ent.append((did, li, L, st, res["ratio"], res["ahead"]) + crowd)
            if st != 0: continue
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
            # events before the forced sell decision (tick K): the trigger value per landing row
            tK = (s_in + K) * E.SMS
            ne = bisect.bisect_left(ea, tK)
            sv = np.zeros((ne, 4), np.float32)
            for e in range(ne):
                for r in range(4): sv[e, r] = np.mean([va(ea[e] + x) for x in REV[r]])
            ph = E.pre_holders(tp, j0, res)
            ft = E.tick_features(res, tp, j0, K, ph)
            trj.append((did, li, L, s_in, res["a_in"], v0, res["q"], res["ahead"], res["ratio"], len(ph[0])))
            feats.append(ft); tvals.append(tv)
            evs.append((np.array(ea[:ne], np.float64), np.array([x[1] for x in ev[:ne]], np.int64), np.array([x[2] for x in ev[:ne]], np.int8),
                        np.array([x[3] for x in ev[:ne]], np.float64) / 1e9, np.array([x[4] for x in ev[:ne]], np.int8),
                        np.array(ev_val[:ne], np.float32), sv))
    return ent, trj, feats, tvals, evs


def main():
    procs = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    T0 = time.time()
    D = dict(np.load(f"{E.DATA}/dumps.npz"))
    U = (D["env"] & (D["m2"] >= -0.005)) | D["pick_im"] | D["pick_m2"]
    ids = np.flatnonzero(U)
    print(f"universe: {len(ids)} dumps (env & M2 >= -0.005, + IMIT1 / M2 picks)", flush=True)
    G["tapes"] = {"A": E.Tape("A"), "B": E.Tape("B")}
    G["CV"] = E.Curves()
    lt, ln = E.landing_tables()
    gname = {v: k for k, v in E.GI.items()}
    G["LT"] = {gi: lt.get(gname[gi], lt["ALL"]) for gi in gname}
    tl, sl, ntl, nsl = E.sell_latency_tables()
    G["RTL"] = [list(tl), [35.0], [50.0], [75.0]]; G["REV"] = [list(sl), [35.0], [50.0], [75.0]]
    print("landing deciles by group (n):", {g: (ln.get(g), np.round(v).astype(int).tolist()) for g, v in lt.items()}, flush=True)
    # crowd-conditional landing (li 13..22): our measured landing on the live fires split by the dump's crowd (distinct fast bots
    # buying in the dump slot .. +3: 0-2 vs 3+), per client group when the cell has >= 20 fires, else the group's (n < 40) or the
    # bucket's pooled distribution
    zl = np.load(f"{E.DATA}/paths/paths_live.npz"); le = zl["ent"]
    lg = D["grp"][le[:, 0].astype(np.int64)]; lL = le[:, 2]; lcb = (le[:, 6] >= 3).astype(int)
    LTC = {}
    for gi in gname:
        for cb in (0, 1):
            cell = lL[(lg == gi) & (lcb == cb)]; grp_all = lL[lg == gi]
            if len(cell) >= 20: LTC[(gi, cb)] = E.deciles(cell)
            elif 0 < len(grp_all) < 40: LTC[(gi, cb)] = E.deciles(grp_all)
            else: LTC[(gi, cb)] = E.deciles(lL[lcb == cb])
    G["LTC"] = LTC
    print("crowd-conditional landing deciles:", {f"{gname[g]}/{'crowd' if c else 'quiet'}": np.round(v).astype(int).tolist() for (g, c), v in LTC.items()}, flush=True)
    print(f"sell landing deciles: time-limit (n {ntl}) {np.round(tl).astype(int).tolist()}, stop-loss (n {nsl}) {np.round(sl).astype(int).tolist()}", flush=True)
    jobs = {}
    tagn = {0: "A", 1: "B"}
    for did in ids.tolist():
        tag = tagn[int(D["tag"][did])]; TP = G["tapes"][tag]; t = int(D["tok"][did]); j0 = int(D["k"][did]) - int(TP.off[t])
        assert 0 <= j0 < TP.cnt[t]
        jobs.setdefault((tag, t), []).append((did, j0, int(D["grp"][did])))
    jl = [(tag, t, rows) for (tag, t), rows in jobs.items()]
    os.makedirs(OUTD, exist_ok=True)
    ENT = []; TRJ = []; FT = []; TV = []; EVL = []
    with get_context("fork").Pool(procs) as p:
        for i, (ent, trj, feats, tvals, evs) in enumerate(p.imap_unordered(work, jl, chunksize=4)):
            ENT += ent; TRJ += trj; FT += feats; TV += tvals; EVL += evs
            if (i + 1) % 500 == 0: print(f"  {i + 1}/{len(jl)} tokens, {len(ENT)} entries, {len(TRJ)} fills, {time.time() - T0:.0f} s", flush=True)
    # deterministic order (dump id, landing index): saved decisions stay aligned across rebuilds
    oe = sorted(range(len(ENT)), key=lambda x: (ENT[x][0], ENT[x][1])); ENT = [ENT[x] for x in oe]
    ot = sorted(range(len(TRJ)), key=lambda x: (TRJ[x][0], TRJ[x][1]))
    TRJ = [TRJ[x] for x in ot]; FT = [FT[x] for x in ot]; TV = [TV[x] for x in ot]; EVL = [EVL[x] for x in ot]
    EVA = []; EVS = []; EVB = []; EVSOL = []; EVC = []; EVV = []; EVSV = []; EVO = [0]
    for ea, es, eb, esol, ec, ev, sv in EVL:
        EVA.append(ea); EVS.append(es); EVB.append(eb); EVSOL.append(esol); EVC.append(ec); EVV.append(ev); EVSV.append(sv); EVO.append(EVO[-1] + len(ea))
    ENT = np.array(ENT, np.float64); TRJ = np.array(TRJ, np.float64)
    np.savez(f"{OUTD}/paths2{'_crowd' if CROWD > 0 else ''}.npz", ent=ENT, trj=TRJ, ft=np.stack(FT), tv=np.stack(TV), ev_a=np.concatenate(EVA), ev_s=np.concatenate(EVS),
             ev_b=np.concatenate(EVB), ev_sol=np.concatenate(EVSOL), ev_c=np.concatenate(EVC), ev_v=np.concatenate(EVV), ev_sv=np.concatenate(EVSV),
             ev_off=np.array(EVO, np.int64), K=K, tf=np.array(E.TF), rtl=np.array(G["RTL"][0]), rev=np.array(G["REV"][0]))
    print(f"done: {len(ENT)} entries, {len(TRJ)} fills, {EVO[-1]} events, {time.time() - T0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
