#!/usr/bin/env python3
"""HAQQ_MODEL step 3 (read-only, offline): pre-send T2 replay on the held-out 24 h (10-26 23:15 -> 10-27 23:15 PKT), run 28's
settings at 0.50 SOL (k4, QUIET on, R28 donor landing + calibration), exactly haqq_sel/h3_presend.py's machinery (its functions
are imported unchanged), with extra streams restricted to the model's picks:
  MODEL80 / MODEL85: triggers on tokens whose decision-time (+14 slots) score >= the threshold frozen at VALIDATION recall 80% / 85%,
                     and only triggers at slot >= create slot + 14 (before that the model has not decided; those are not armed);
  MODEL80_N0: the +0-slot model (decides at the end of the create slot), threshold at val recall 80%.
ALL and HQ (haqq's tokens, hindsight) are rerun in the same pass for like-for-like comparison.
Out: DATA/presend.pkl"""
import sys, os, json, pickle, time, collections
import numpy as np
from multiprocessing import Pool
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_sel")
import h3_presend as H3
import lib28, sim28, rlib, sim, s48lib, variants
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_model")
from m1_train import thr_for_recall, TR1, VA1
DATA = "/home/moiz/sniper-data/haqq_model"; HQS = "/home/moiz/sniper-data/haqq_sel"
W0, W1 = H3.W0, H3.W1


def picks(n, rec):
    Z = pickle.load(open(f"{DATA}/model_n{n}.pkl", "rb"))
    va = (Z["bt"] >= TR1) & (Z["bt"] < VA1)
    thr = thr_for_recall(Z["y"][va].astype(int), Z["score"][va], rec)
    pk = Z["score"] >= thr
    return {m: int(s) + n for m, s, p in zip(Z["mint"], Z["slot"], pk) if p}, thr, {m: int(s) for m, s in zip(Z["mint"], Z["slot"])}


if __name__ == "__main__":
    draws = 100; procs = 12
    t0 = time.time()
    tp = rlib.Tape(tab=H3.TAB, with_ours=False)
    idm = tp.id_map()
    tp.drop_users = {idm[w] for w in rlib.WALLETS if w in idm}
    TOK = json.load(open(f"{HQS}/tokens.json")); HQ = {x["mint"]: x for x in TOK["tokens"]}
    S = np.load(f"{H3.TAB}/slots.npy"); bt = S["bt"].astype(np.int64)
    bins = {b0: int(((bt >= b0) & (bt < b0 + 300)).sum()) / (300 / 0.2118) for b0 in range(W0, W1, 300)}
    use = {b for b, c in bins.items() if c >= 0.90}
    trig = rlib.detect(tp, whale_pct=6.0)
    DU = H3.dumps_by_seller(tp)
    coh_ids = {idm[w] for w in H3.COH if w in idm}; fb_ids = {idm[w] for w in H3.FB if w in idm}
    P80, t80, cslot = picks(14, 0.80); P85, t85, _ = picks(14, 0.85); P80n0, t80n0, _ = picks(0, 0.80)
    print(f"thresholds: n14 rec80 {t80:.3f} rec85 {t85:.3f}; n0 rec80 {t80n0:.3f}", flush=True)
    wins = []
    for d in trig:
        if not (W0 <= d["bt"] < W1) or (d["bt"] - W0) // 300 * 300 + W0 not in use: continue
        if not (d["age_slots"] > 0 and d["v2"] and not d["cashback"]): continue
        ws = None
        if d["sells"]:
            k = d["sells"][0]; ws = (int(tp.s[k]), int(tp.i[k]))
        q = H3.quiet_feats(tp, d, DU, coh_ids, fb_ids)
        h = HQ.get(d["mint"]); m = d["mint"]
        wins.append(dict(mint=m, slot=d["slot"], idx=d["idx"], j=d["j"], age_slots=d["age_slots"], v2=True, cashback=False, whale=d["whale"],
                         whale_b58=tp.ids[d["whale"]], whale_sell=ws, bt=d["bt"], pct=d["pct"], hq=bool(h),
                         hq_known=bool(h) and h["first_slot"] < d["slot"], in_univ=m in cslot,
                         m80=(m in P80) and d["slot"] >= P80[m], m85=(m in P85) and d["slot"] >= P85[m], m80n0=(m in P80n0) and d["slot"] >= P80n0[m],
                         m80_any=m in P80, m85_any=m in P85, early=(m in cslot) and d["slot"] < cslot[m] + 14, qmodel=True, **q))
    for x in wins: x["key"] = (x["mint"], x["slot"], x["idx"], x["j"])
    print(f"armable {len(wins)} (QUIET skip {sum(x['quiet_skip'] for x in wins)}); in model universe {sum(x['in_univ'] for x in wins)}; "
          f"before +14 slots {sum(x['early'] for x in wins)}; MODEL80 {sum(x['m80'] for x in wins)} (any time {sum(x['m80_any'] for x in wins)}), "
          f"MODEL85 {sum(x['m85'] for x in wins)}, MODEL80_N0 {sum(x['m80n0'] for x in wins)}, HQ {sum(x['hq'] for x in wins)} ({time.time() - t0:.0f}s)", flush=True)
    R = lib28.load_run(); cfg = lib28.cfg28(R, 212.6); cfg.arm_filter = lambda x: not x["quiet_skip"]
    G = H3.G; G["cfg"] = cfg
    D3 = pickle.load(open(f"{s48lib.S48}/donors123.pkl", "rb"))
    D28 = pickle.load(open(f"{lib28.DATA}/donors28.pkl", "rb")); G["land"] = sim.Landing(D28, probes=("R28",))
    G["model"] = s48lib.ModelN(D3, H3.s48_clock(), ("P1", "P2", "P3")); G["view"] = sim.View(); G["ck"] = tp.clock()
    Q = json.load(open(f"{lib28.DATA}/qcheck.json")); G["qpool"] = np.array([s["d"] - s["t6"] for s in Q["stops"]])
    G["whale_ids"] = {x["whale_b58"]: x["whale"] for x in wins}
    G["streams"] = {"ALL": wins, "HQ": [x for x in wins if x["hq"]], "MODEL80": [x for x in wins if x["m80"]],
                    "MODEL85": [x for x in wins if x["m85"]], "MODEL80_N0": [x for x in wins if x["m80n0"]]}
    G["store"] = sim.build_store(tp, variants.spans_for(wins)); G["byk"] = {x["key"]: x for x in wins}
    tp.slim(); import gc; gc.collect()
    keys = [x["key"] for x in wins if not x["quiet_skip"]]
    chunks = [keys[i::procs * 4] for i in range(procs * 4)]
    IDE = {}
    with Pool(procs) as p:
        for o in p.imap_unordered(H3.one_ideal, chunks): IDE.update(o)
    print(f"ideal done ({time.time() - t0:.0f}s)", flush=True)
    jobs = [(s, 1000 + d) for s in G["streams"] for d in range(draws)]
    RR = collections.defaultdict(list)
    with Pool(procs) as p:
        for k_, (stream, seed, out) in enumerate(p.imap_unordered(H3.one, jobs, chunksize=1)):
            RR[stream].append((seed, out))
            if (k_ + 1) % 100 == 0: print(f"  realistic {k_ + 1}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
    meta = [{k: v for k, v in x.items() if k not in ("qmodel",)} for x in wins]
    pickle.dump(dict(wins=meta, ideal=IDE, real=dict(RR), thr=dict(n14_80=t80, n14_85=t85, n0_80=t80n0)), open(f"{DATA}/presend.pkl", "wb"))
    for s in G["streams"]:
        nets = [sum(v[2] for v in out.values()) / 1e9 for _, out in RR[s]]; fl = [sum(v[1] for v in out.values()) for _, out in RR[s]]
        print(s, f"realistic net {np.mean(nets):+.3f} [{np.percentile(nets, 5):+.3f}, {np.percentile(nets, 95):+.3f}] fills {np.mean(fl):.1f}", flush=True)
    print(f"done {time.time() - t0:.0f}s")
