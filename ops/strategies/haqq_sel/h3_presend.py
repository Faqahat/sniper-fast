#!/usr/bin/env python3
"""HAQQ_SEL step 3 (read-only, offline): pre-send T2 on the 24 h chain tape, run 28's live settings at 0.50 SOL, with QUIET.
  * triggers: real/rlib.detect (the live T2 detector, whale >= 6%), armable (not create-slot, v2, not cashback), in the window, in
    5-min bins with >= 90% of slots recorded;
  * QUIET skip (filter/rules.quiet_arm's 4 signals, computed on the tape: since_last >= 1, no cohort wallet holding, < 2 follower
    bots ever traded, the whale's dumps of the last 24 h drew < 2.24 followers or none known) and QUIET stop (6:2, live28/sim28's
    modeled stop with run 28's measured decision offsets);
  * REALISTIC: live28/sim28.run28 (real/sim.py + QUIET) with run 28's own live tries as landing donors (MEASURED landing), one
    position, the engine's rate limits, N draws;
  * IDEAL: every window evaluated alone; a pre-sent try lands right behind the first trade (from the trigger to the window end, the
    whale's first-sell slot or the QUIET stop) whose price is <= 0.88 x the price at the end of the previous slot (the limit a try
    sent before that slot carries); the same exit model (real/sim.exit_path: TP 10 / SL 20 / 2 slots, measured sell delays,
    followers our buy prices out dropped) and costs; failed-try fees = the realistic replay's mean for that window.
Streams: ALL (every trigger) and HQ (triggers on haqq's tokens only). haqq's trades are used ONLY for the token list (tokens.json).
Our two wallets' trades are removed from the tape. Out: DATA/presend_<stream>.pkl"""
import sys, os, json, pickle, time, collections, math, argparse
import numpy as np
from multiprocessing import Pool
LIVE28 = "/home/moiz/sniper/ops/strategies/presend/filter/live28"; REAL = "/home/moiz/sniper/ops/strategies/presend/real"
sys.path.insert(0, LIVE28); sys.path.insert(0, REAL)
import lib28, sim28                       # lib28 points rlib.TAB at run 28's tape on import; reset below
import rlib, sim, s48lib, variants
DATA = "/home/moiz/sniper-data/haqq_sel"; TAB = f"{DATA}/tab"; rlib.TAB = TAB
SMS = rlib.SMS
W0 = 1793038500; W1 = 1793124900
COH = set(json.load(open("/home/moiz/sniper/ops/overnight/sel/cohort_train.json")))
FB = set(json.load(open("/home/moiz/sniper/ops/strategies/presend/filter/fbots_frozen.json")))
G = {}


def s48_clock():
    S = np.load(f"{s48lib.TAB48}/slots.npy")
    slot0 = int(S["slot"][0]); n = int(S["slot"][-1]) - slot0 + 1
    bs = np.zeros(n, np.int32); bs[S["slot"].astype(np.int64) - slot0] = S["maxi"].astype(np.int32) + 1
    return rlib.Clock(slot0, bs)


def dumps_by_seller(tp):
    """every sell >= 0.3 SOL that by itself drops the price >= 8%, curve < 100 SOL; followers = distinct other wallets buying after
    it up to slot + 2 on the same token (filter/e1_events.py's definition) -> seller id -> [(slot, bt, n_followers)]"""
    out = collections.defaultdict(list)
    for mid, (a, e) in tp.span.items():
        s = tp.s[a:e]; b = tp.buy[a:e]; sol = tp.sol[a:e]; v = tp.vsol[a:e]; t = tp.vtok[a:e]; u = tp.user[a:e]
        if e - a < 2: continue
        p = v / np.maximum(t, 1)
        cand = np.flatnonzero((~b[1:]) & (sol[1:] >= 3e8) & (v[1:] < 100e9) & (p[1:] <= 0.92 * p[:-1])) + 1
        for k in cand.tolist():
            sk = s[k]; q = k + 1; bs = set()
            while q < len(s) and s[q] <= sk + 2:
                if b[q] and u[q] != u[k]: bs.add(int(u[q]))
                q += 1
            out[int(u[k])].append((int(sk), int(tp.blockt[a + k]), len(bs)))
    for v_ in out.values(): v_.sort()
    return out


def quiet_feats(tp, d, DU, coh_ids, fb_ids):
    mid = d["mid"]; a, e = tp.span[mid]; k = d["k"]; s0 = d["slot"]
    since_last = int(s0 - tp.s[k - 1]) if k > a else 9999
    U = tp.user[a:k]; TK = np.where(tp.buy[a:k], tp.tok[a:k], -tp.tok[a:k])
    bal = collections.defaultdict(int)
    for u_, x in zip(U.tolist(), TK.tolist()): bal[u_] += x
    coh_hold = sum(1 for u_ in coh_ids & set(bal) if bal[u_] > 0)
    fb_n = len(fb_ids & set(U.tolist()))
    tb = d["bt"]
    x = [nf for (s_, bt_, nf) in DU.get(d["whale"], []) if s_ + 2 < s0 and bt_ >= tb - 24 * 3600]
    wdf = float(np.mean(x)) if x else -1.0
    q = (since_last >= 1) and (coh_hold == 0) and (fb_n < 2) and (wdf < 2.24)
    return dict(since_last=since_last, coh_hold=coh_hold, fb_n=fb_n, wh_dump_fol=wdf, quiet_skip=bool(q))


# ---------------------------------------------------------------------------------------------------------------------------
class _W: pass


def ideal(x, cfg, nd=24):
    """the best realistic spot: first in line right behind the first crossing trade (see the module doc). -> dict"""
    ck, tp, model = G["ck"], G["store"], G["model"]
    tk = tp[x["mint"]]
    kt = max(tk.before(x["slot"], x["idx"] + 0.5), 0)
    en = int(math.floor((rlib.arr(x["slot"], x["idx"]) + cfg.live_ms + cfg.window_slots * SMS) / SMS))
    last = en
    if x.get("whale_sell") is not None: last = min(last, x["whale_sell"][0])
    # QUIET stop 6:2 with an instant view: other trades (not the whale) after the trigger before slot trigger + 6
    wid = x["whale"]
    oth = sum(1 for q in range(kt + 1, tk.n) if tk.s[q] < x["slot"] + 6 and tk.user[q] != wid)
    if oth < 2: last = min(last, x["slot"] + 5)
    ref = tk.vsol[kt] / tk.vtok[kt]; cur_slot = x["slot"]; fk = None
    for q in range(kt + 1, tk.n):
        sq = tk.s[q]
        if sq > last: break
        if sq != cur_slot:
            ref = tk.vsol[q - 1] / tk.vtok[q - 1]; cur_slot = sq
        if tk.vtok[q] > 0 and tk.vsol[q] / tk.vtok[q] <= ref * (1 - cfg.drop) and tk.vsol[q] < rlib.UNTRADE_V:
            fk = q; break
    if fk is None: return dict(chance=False, pnl=0.0)
    w = _W(); w.fill = dict(S=tk.s[fk], I=tk.i[fk] + 0.5, kb=fk)
    rng = np.random.default_rng([7, sim28.wkey(x)])
    ps = [exit_path_safe(ck, tk, w, cfg, model, rng) for _ in range(nd)]
    return dict(chance=True, pnl=float(np.mean([p["pnl"] for p in ps])) / 1e9, win=float(np.mean([p["pnl"] > 0 for p in ps])),
                exit=collections.Counter(p["why"] for p in ps).most_common(1)[0][0], fill_slot=int(tk.s[fk]), dslot=int(tk.s[fk] - x["slot"]))


def exit_path_safe(ck, tk, w, cfg, model, rng):
    return sim.exit_path(ck, tk, w, cfg, model, rng)


def one(job):
    stream, seed = job
    res = sim28.run28(G["ck"], G["store"], G["streams"][stream], G["cfg"], G["land"], G["model"], G["view"], seed, qstop=(6, 2),
                      our_id=-1, whale_ids=G["whale_ids"], qdelta_pool=G["qpool"])
    out = {}
    for r in res:
        x = r["trig"]
        out[x["key"]] = (int(r["armed"]), int(bool(r.get("filled", False))), int(r.get("net", 0)), int(r.get("pnl", 0)), int(r.get("fees", 0)),
                         r.get("why") or "", r.get("exit") or "")
    return stream, seed, out


def one_ideal(keys):
    out = {}
    for key in keys:
        x = G["byk"][key]
        out[key] = ideal(x, G["cfg"])
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--draws", type=int, default=100); ap.add_argument("--procs", type=int, default=12)
    ap.add_argument("--pool", default="R28"); ap.add_argument("--drop-haqq", action="store_true")
    A = ap.parse_args()
    t0 = time.time()
    tp = rlib.Tape(tab=TAB, with_ours=False)
    idm = tp.id_map()
    tp.drop_users = {idm[w] for w in rlib.WALLETS if w in idm}
    if A.drop_haqq: tp.drop_users.add(idm["haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"])     # sensitivity: haqq's own trades removed from the market
    TOK = json.load(open(f"{DATA}/tokens.json"))
    HQ = {x["mint"]: x for x in TOK["tokens"]}
    # coverage bins (5 min, >= 90% of slots recorded)
    S = np.load(f"{TAB}/slots.npy"); bt = S["bt"].astype(np.int64)
    bins = {}
    for b0 in range(W0, W1, 300):
        n = int(((bt >= b0) & (bt < b0 + 300)).sum()); bins[b0] = n / (300 / 0.2118)
    use = {b for b, c in bins.items() if c >= 0.90}
    print(f"bins used {len(use)}/{len(bins)} ({len(use) * 300 / 3600:.2f} h); prep {time.time() - t0:.0f}s", flush=True)
    trig = rlib.detect(tp, whale_pct=6.0)
    print(f"detected {len(trig)} T2 triggers on the tape {time.time() - t0:.0f}s", flush=True)
    DU = dumps_by_seller(tp)
    print(f"dumps {sum(len(v) for v in DU.values())} by {len(DU)} sellers {time.time() - t0:.0f}s", flush=True)
    coh_ids = {idm[w] for w in COH if w in idm}; fb_ids = {idm[w] for w in FB if w in idm}
    wins = []
    for d in trig:
        if not (W0 <= d["bt"] < W1) or (d["bt"] - W0) // 300 * 300 + W0 not in use: continue
        if not (d["age_slots"] > 0 and d["v2"] and not d["cashback"]): continue
        ws = None
        if d["sells"]:
            k = d["sells"][0]; ws = (int(tp.s[k]), int(tp.i[k]))
        q = quiet_feats(tp, d, DU, coh_ids, fb_ids)
        h = HQ.get(d["mint"])
        inspan = bool(h) and (h["first_bt"] - 60 <= d["bt"] <= h["last_bt"] + 60)
        wins.append(dict(mint=d["mint"], slot=d["slot"], idx=d["idx"], j=d["j"], age_slots=d["age_slots"], v2=True, cashback=False, whale=d["whale"],
                         whale_b58=tp.ids[d["whale"]], whale_sell=ws, bt=d["bt"], pct=d["pct"], hq=bool(h), inspan=inspan, qmodel=True, **q))
    for x in wins: x["key"] = (x["mint"], x["slot"], x["idx"], x["j"])
    print(f"armable triggers in window {len(wins)} (QUIET skips {sum(x['quiet_skip'] for x in wins)}), on haqq tokens {sum(x['hq'] for x in wins)} "
          f"(in his active span {sum(x['inspan'] for x in wins)}) {time.time() - t0:.0f}s", flush=True)
    R = lib28.load_run()                   # run 28's records: settings (run_start)
    cfg = lib28.cfg28(R, 212.6)
    cfg.arm_filter = lambda x: not x["quiet_skip"]
    print("cfg", dict(size=cfg.size, k=cfg.k, drop=cfg.drop, win=cfg.window_slots, exit=cfg.exit_slots, tp=cfg.tp, sl=cfg.sl, rate=cfg.paths, glob=cfg.global_rate), flush=True)
    G["cfg"] = cfg
    D3 = pickle.load(open(f"{s48lib.S48}/donors123.pkl", "rb"))
    if A.pool == "R28":
        D28 = pickle.load(open(f"{lib28.DATA}/donors28.pkl", "rb")); G["land"] = sim.Landing(D28, probes=("R28",))
    else:
        G["land"] = sim.Landing(D3, probes=("P3",))
    G["model"] = s48lib.ModelN(D3, s48_clock(), ("P1", "P2", "P3")); G["view"] = sim.View(); G["ck"] = tp.clock()
    Q = json.load(open(f"{lib28.DATA}/qcheck.json")); G["qpool"] = np.array([s["d"] - s["t6"] for s in Q["stops"]])
    G["whale_ids"] = {x["whale_b58"]: x["whale"] for x in wins}
    G["streams"] = {"ALL": wins, "HQ": [x for x in wins if x["hq"]]}
    G["store"] = sim.build_store(tp, variants.spans_for(wins))
    G["byk"] = {x["key"]: x for x in wins}
    tp.slim(); import gc; gc.collect()
    print(f"store built {time.time() - t0:.0f}s", flush=True)
    # ideal (every window that QUIET does not skip, alone)
    keys = [x["key"] for x in wins if not x["quiet_skip"]]
    chunks = [keys[i::A.procs * 4] for i in range(A.procs * 4)]
    IDE = {}
    with Pool(A.procs) as p:
        for o in p.imap_unordered(one_ideal, chunks): IDE.update(o)
    print(f"ideal done: chances {sum(v['chance'] for v in IDE.values())} of {len(IDE)} armed {time.time() - t0:.0f}s", flush=True)
    jobs = [(s, 1000 + d) for s in ("HQ", "ALL") for d in range(A.draws)]
    RR = collections.defaultdict(list)
    with Pool(A.procs) as p:
        for k_, (stream, seed, out) in enumerate(p.imap_unordered(one, jobs, chunksize=1)):
            RR[stream].append((seed, out))
            if (k_ + 1) % 20 == 0: print(f"  realistic {k_ + 1}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
    meta = [{k: v for k, v in x.items() if k not in ("qmodel",)} for x in wins]
    pickle.dump(dict(wins=meta, ideal=IDE, real=dict(RR), bins=bins, use=sorted(use), pool=A.pool, cfg=dict(size=cfg.size)),
                open(f"{DATA}/presend_{A.pool}{'_nohaqq' if A.drop_haqq else ''}.pkl", "wb"))
    for s in ("HQ", "ALL"):
        nets = [sum(v[2] for v in out.values()) / 1e9 for _, out in RR[s]]; fl = [sum(v[1] for v in out.values()) for _, out in RR[s]]
        print(s, f"realistic net {np.mean(nets):+.3f} [{np.percentile(nets, 5):+.3f}, {np.percentile(nets, 95):+.3f}] fills {np.mean(fl):.1f}", flush=True)
    print(f"done {time.time() - t0:.0f}s")
