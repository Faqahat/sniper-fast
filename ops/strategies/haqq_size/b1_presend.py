#!/usr/bin/env python3
"""HAQQ_SIZE step B1 (read-only, offline): pre-send T2 on the held-out 24 h (10-26 23:15 -> 10-27 23:15 PKT), run 28's settings
(k4, QUIET on, R28 donor landing + calibration), haqq_sel/h3_presend.py's machinery imported unchanged, with a PER-WINDOW size.
Only the exit/P&L model depends on size (our limit is a price limit: which try fills does not depend on size, size study);
real/sim.exit_path is wrapped so it uses the window's size: pump's exact curve math at that size, the followers our bigger buy
prices out dropped (measured slack table), every cost. Stress: 20% of later buyers removed (cfg.follower_cut = 0.2).
Schemes (all scaled so the mean size over the IDEAL chances = 0.50 SOL; clip 0.10..1.50):
  FLAT   : 0.50 everywhere (as live)
  HAQQ   : haqq's depth-2 rule (a3_model.py, fit on 10-23..10-26, no test data): curve SOL <= 30.52 -> 0.936, <= 31.06 -> 0.606,
           else 0.350 (every T2 fill is a dump, so his "no recent dump -> 0.258" branch never applies). The curve is what the engine
           can know when it signs the tries: the curve SOL after the whale's full dump, v*t/(t+whale tokens), at the trigger.
  HAQQ_FILL (hindsight sensitivity): the same rule on the curve SOL at the ideal fill (not knowable at arm time).
  SCORE  : haqq_model score (+14-slot model if the trigger is >= create + 14 slots, else the create-slot model): terciles of the
           chances' scores -> 0.30 / 0.50 / 0.70 (x scale).
Out: OUT/presend.pkl"""
import sys, os, json, pickle, time, collections, copy
import numpy as np
from multiprocessing import Pool
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_sel")
import h3_presend as H3
import lib28, sim28, rlib, sim, s48lib, variants
OUT = "/home/moiz/sniper-data/haqq_size"; HQS = "/home/moiz/sniper-data/haqq_sel"; HM = "/home/moiz/sniper-data/haqq_model"
W0, W1 = H3.W0, H3.W1
CUR = [None]
_exit0 = sim.exit_path
_cfgc = {}


def exit_sized(ck, tk, w, cfg, model, rng):
    s = w.trig.get("size") if hasattr(w, "trig") else CUR[0]
    if s is None: return _exit0(ck, tk, w, cfg, model, rng)
    key = (id(cfg), s)
    c = _cfgc.get(key)
    if c is None:
        c = copy.copy(cfg); c.size = int(round(s * 1e9)); _cfgc[key] = c
    return _exit0(ck, tk, w, c, model, rng)


sim.exit_path = exit_sized; sim28.exit_path = exit_sized
G = H3.G


def one(job):
    scheme, stress, seed = job
    cfg = G["cfg_s"] if stress else G["cfg"]
    res = sim28.run28(G["ck"], G["store"], G["streams"][scheme], cfg, G["land"], G["model"], G["view"], seed, qstop=(6, 2),
                      our_id=-1, whale_ids=G["whale_ids"], qdelta_pool=G["qpool"])
    out = {}
    for r in res:
        x = r["trig"]
        out[x["key"]] = (int(r["armed"]), int(bool(r.get("filled", False))), int(r.get("net", 0)), int(r.get("pnl", 0)), int(r.get("fees", 0)))
    return scheme, stress, seed, out


def one_ideal(job):
    scheme, stress, keys = job
    cfg = G["cfg_s"] if stress else G["cfg"]
    out = {}
    for key in keys:
        x = G["byk"][scheme][key]; CUR[0] = x["size"]
        out[key] = H3.ideal(x, cfg)
    CUR[0] = None
    return scheme, stress, out


def haqq_rule(v):
    return 0.936 if v <= 30.52 else 0.606 if v <= 31.06 else 0.350


if __name__ == "__main__":
    draws = int(os.environ.get("DRAWS", "100")); procs = 12
    t0 = time.time()
    tp = rlib.Tape(tab=H3.TAB, with_ours=False)
    idm = tp.id_map()
    tp.drop_users = {idm[w] for w in rlib.WALLETS if w in idm}
    S = np.load(f"{H3.TAB}/slots.npy"); bt = S["bt"].astype(np.int64)
    bins = {b0: int(((bt >= b0) & (bt < b0 + 300)).sum()) / (300 / 0.2118) for b0 in range(W0, W1, 300)}
    use = {b for b, c in bins.items() if c >= 0.90}
    trig = rlib.detect(tp, whale_pct=6.0)
    DU = H3.dumps_by_seller(tp)
    coh_ids = {idm[w] for w in H3.COH if w in idm}; fb_ids = {idm[w] for w in H3.FB if w in idm}
    SC = {}
    for n in (0, 14):
        Z = pickle.load(open(f"{HM}/model_n{n}.pkl", "rb"))
        SC[n] = {m: (float(s), int(sl)) for m, s, sl in zip(Z["mint"], Z["score"], Z["slot"])}
    wins = []
    for d in trig:
        if not (W0 <= d["bt"] < W1) or (d["bt"] - W0) // 300 * 300 + W0 not in use: continue
        if not (d["age_slots"] > 0 and d["v2"] and not d["cashback"]): continue
        ws = None
        if d["sells"]:
            k = d["sells"][0]; ws = (int(tp.s[k]), int(tp.i[k]))
        q = H3.quiet_feats(tp, d, DU, coh_ids, fb_ids)
        m = d["mint"]
        v_post = d["vsol"] * d["vtok"] / (d["vtok"] + d["bal"]) / 1e9
        if m in SC[14] and d["slot"] >= SC[14][m][1] + 14: sc = SC[14][m][0]; scn = 14
        elif m in SC[0]: sc = SC[0][m][0]; scn = 0
        else: sc = np.nan; scn = -1
        wins.append(dict(mint=m, slot=d["slot"], idx=d["idx"], j=d["j"], age_slots=d["age_slots"], v2=True, cashback=False, whale=d["whale"],
                         whale_b58=tp.ids[d["whale"]], whale_sell=ws, bt=d["bt"], pct=d["pct"], qmodel=True, v_trig=d["vsol"] / 1e9, v_post=v_post,
                         score=sc, score_n=scn, **q))
    for x in wins: x["key"] = (x["mint"], x["slot"], x["idx"], x["j"])
    print(f"armable {len(wins)} (QUIET skip {sum(x['quiet_skip'] for x in wins)}) ({time.time() - t0:.0f}s)", flush=True)
    R = lib28.load_run(); cfg = lib28.cfg28(R, 212.6); cfg.arm_filter = lambda x: not x["quiet_skip"]
    cfg_s = copy.copy(cfg); cfg_s.follower_cut = 0.2
    G["cfg"] = cfg; G["cfg_s"] = cfg_s
    D3 = pickle.load(open(f"{s48lib.S48}/donors123.pkl", "rb"))
    D28 = pickle.load(open(f"{lib28.DATA}/donors28.pkl", "rb")); G["land"] = sim.Landing(D28, probes=("R28",))
    G["model"] = s48lib.ModelN(D3, H3.s48_clock(), ("P1", "P2", "P3")); G["view"] = sim.View(); G["ck"] = tp.clock()
    Q = json.load(open(f"{lib28.DATA}/qcheck.json")); G["qpool"] = np.array([s["d"] - s["t6"] for s in Q["stops"]])
    G["whale_ids"] = {x["whale_b58"]: x["whale"] for x in wins}
    G["store"] = sim.build_store(tp, variants.spans_for(wins))
    tp.slim(); import gc; gc.collect()
    keys = [x["key"] for x in wins if not x["quiet_skip"]]
    # pass 1: ideal at flat 0.50 -> the chance set (size independent) and the fill-time curve
    for x in wins: x["size"] = 0.50
    G["byk"] = {"FLAT": {x["key"]: x for x in wins}}
    chunks = [keys[i::procs * 4] for i in range(procs * 4)]
    IDE = collections.defaultdict(dict)
    with Pool(procs) as p:
        for sch, st, o in p.imap_unordered(one_ideal, [("FLAT", False, c) for c in chunks]): IDE[("FLAT", False)].update(o)
    ch = {k for k, v in IDE[("FLAT", False)].items() if v["chance"]}
    # fill-time curve SOL for the hindsight variant (the trade the ideal fill sits behind)
    store = G["store"]
    for x in wins:
        v = IDE[("FLAT", False)].get(x["key"])
        x["v_fill"] = np.nan
        if v and v["chance"]:
            tk = store[x["mint"]]; fs = v["fill_slot"]
            # first crossing trade at the fill slot: use the lowest curve among trades at that slot after the trigger
            kt = max(tk.before(x["slot"], x["idx"] + 0.5), 0)
            vv = [tk.vsol[q] for q in range(kt + 1, tk.n) if tk.s[q] == fs]
            x["v_fill"] = float(min(vv)) / 1e9 if vv else np.nan
    chx = [x for x in wins if x["key"] in ch]
    print(f"chances {len(ch)} of {len(keys)} armed windows; v_post <= 31.06 in chances: {sum(x['v_post'] <= 31.06 for x in chx)}, "
          f"v_fill <= 31.06: {sum((x['v_fill'] <= 31.06) for x in chx)} ({time.time() - t0:.0f}s)", flush=True)
    # scheme sizes
    sc_ch = np.array([x["score"] for x in chx]); t1, t2 = np.nanpercentile(sc_ch, [100 / 3, 200 / 3])
    raw = {"FLAT": lambda x: 0.50, "HAQQ": lambda x: haqq_rule(x["v_post"]),
           "HAQQ_FILL": lambda x: haqq_rule(x["v_fill"]) if x["v_fill"] == x["v_fill"] else 0.350,
           "SCORE": lambda x: 0.50 if x["score"] != x["score"] else (0.30 if x["score"] < t1 else 0.50 if x["score"] < t2 else 0.70)}
    SCH = {}; scale = {}
    for nm, f in raw.items():
        r = np.array([f(x) for x in chx]); k = 0.50 / r.mean() if nm != "FLAT" else 1.0
        for _ in range(5):                         # clip then rescale
            k = k * 0.50 / np.clip(r * k, 0.10, 1.50).mean()
        scale[nm] = k
        SCH[nm] = []
        for x in wins:
            y = dict(x); y["size"] = float(np.clip(f(x) * k, 0.10, 1.50)); SCH[nm].append(y)
        sz = np.array([y["size"] for y in SCH[nm] if y["key"] in ch])
        print(f"  {nm:9s} scale {k:.3f}: chance sizes mean {sz.mean():.3f}, " + ", ".join(f"{a:.2f}:{c}" for a, c in sorted(collections.Counter(np.round(sz, 2)).items())), flush=True)
    G["streams"] = SCH; G["byk"] = {nm: {x["key"]: x for x in v} for nm, v in SCH.items()}
    # ideal for each scheme, base and stress
    jobs = [(nm, st, c) for nm in SCH for st in (False, True) for c in chunks]
    IDE = collections.defaultdict(dict)
    with Pool(procs) as p:
        for sch, st, o in p.imap_unordered(one_ideal, jobs): IDE[(sch, st)].update(o)
    print(f"ideal done ({time.time() - t0:.0f}s)", flush=True)
    jobs = [(nm, st, 1000 + d) for nm in SCH for st in (False, True) for d in range(draws)]
    RR = collections.defaultdict(list)
    with Pool(procs) as p:
        for k_, (nm, st, seed, out) in enumerate(p.imap_unordered(one, jobs, chunksize=1)):
            RR[(nm, st)].append((seed, out))
            if (k_ + 1) % 100 == 0: print(f"  realistic {k_ + 1}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
    meta = [{k: v for k, v in x.items() if k not in ("qmodel",)} for x in wins]
    sizes = {nm: {x["key"]: x["size"] for x in v} for nm, v in SCH.items()}
    pickle.dump(dict(wins=meta, ideal=dict(IDE), real=dict(RR), sizes=sizes, scale=scale, terc=(float(t1), float(t2)), chances=sorted(ch)),
                open(f"{OUT}/presend.pkl", "wb"))
    for key in sorted(RR):
        nets = [sum(v[2] for v in out.values()) / 1e9 for _, out in RR[key]]; fl = [sum(v[1] for v in out.values()) for _, out in RR[key]]
        print(key, f"realistic net {np.mean(nets):+.3f} [{np.percentile(nets, 5):+.3f}, {np.percentile(nets, 95):+.3f}] fills {np.mean(fl):.1f}", flush=True)
    print(f"done {time.time() - t0:.0f}s")
