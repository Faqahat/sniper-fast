#!/usr/bin/env python3
"""LAST_HOUR (10-26 ~04:05 PKT, read-only, offline): pre-send T2 replayed on the newest chain recording with FRA run 22's
live settings (taken from run 22's own run_start: whale >= 6%, k 4, helius-ps 20/s path + 20/s global, 0.40 SOL, limit 0.88,
deadline +1, 10-slot window, exit 2 slots / TP 10% / SL 20%, one position, create-slot triggers skipped) and the probe-3
landing model (s48/donors123.pkl P3 donor windows, ModelN over P1-P3, pace slot from p3check.json). The simulator (sim.py)
and detector (rlib.detect) are unchanged; only the tape (lh/tab: recordings 10-25 15:57 -> newest) and the settings are new.
  main stream : every T2 trigger from START to END (engine assumed on the whole time, token history from 15:57 PKT)
  validation  : run 22's own live span, as its own stream, only tokens created after run 22 started (the live engine skips
                older tokens as no_history); compared with run 22's live pre-send and its paper shadow (MEASURED, jsonl)
Our live runs' own pre-send fills and sells (probes, FRA r21/r22, AMS r20/r21) are removed from the tape; the replay puts
its own buy in. Nothing here sends, starts or stops anything.
usage: lasthour.py [--start "10-25 22:00"] [--end "10-26 04:04"] [--draws 200] [--procs 14] [--cut 0.2 --tag cut20]"""
import sys, os, json, pickle, argparse, collections, time, hashlib, math
import numpy as np
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s48lib, rlib, sim, variants

LH = "/home/moiz/sniper-data/presend_real/lh"
TAB = f"{LH}/tab"
rlib.TAB = TAB
R22 = "/home/moiz/sniper-data/runs/fra/runs/dip_r22.jsonl"
LIVE_FILES = list(s48lib.LIVE_FILES) + ["/home/moiz/sniper-data/runs/fra/runs/dip_r21.jsonl", "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r20.jsonl",
                                        R22, "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r21.jsonl"]
BIN = 300                      # coverage bins (s); a bin is used when >= 95% of its slots are recorded
G = {}

def sh(s): return int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "little")

class TapeLH(rlib.Tape):
    def __init__(self):
        super().__init__(tab=TAB, with_ours=False)
        self.skip_sigh = set(); n = 0
        for fn in LIVE_FILES:
            if not os.path.exists(fn): continue
            for l in open(fn):
                if '"presend_live_fill"' in l or '"presend_live_sell_land"' in l:
                    r = json.loads(l); self.skip_sigh.add(sh(r["sig"])); n += 1
                elif '"presend_attempt_land"' in l and '"res":"ok"' in l:          # any landed buy of ours (e.g. a double fill)
                    r = json.loads(l); self.skip_sigh.add(sh(r["sig"])); n += 1
        self.n_skip = n

def s48_clock():
    """the chain clock of the s48 tape (covers probes 1-3): ModelN measures the probes' view jitter on it"""
    S = np.load(f"{s48lib.TAB48}/slots.npy")
    slot0 = int(S["slot"][0]); n = int(S["slot"][-1]) - slot0 + 1
    bs = np.zeros(n, np.int32); bs[S["slot"].astype(np.int64) - slot0] = S["maxi"].astype(np.int32) + 1
    return rlib.Clock(slot0, bs)

def r22_cfg():
    for l in open(R22):
        r = json.loads(l)
        if r.get("ev") == "run_start": return r["presend_live"], r["t"] / 1e9
    raise SystemExit("no run_start")

def make_cfg(c, slot_ms):
    rate = c["path_max_per_sec"]
    cfg = sim.Cfg(slot_ms=slot_ms, size=c["spend"], k=c["k"], drop=c["drop"], deadline_slots=c["deadline_slots"], window_slots=c["window_slots"],
                  live_ms=c["live_ms"], whale_sell_ms=c["whale_sell_ms"], paths=[(rate, rate)], global_rate=c["max_per_sec"], exit_slots=c["exit_slots"],
                  tp=c["tp"], sl=c["sl"], whale_pct=c["whale_pct"], create_slot=c["create_slot"], one_position=c["one_position"])
    cfg.cost = sim.Cost(fail_fee=c["fail_fee"])
    return cfg

def bins_of(tp, ts, te):
    S = np.load(f"{TAB}/slots.npy"); bt = S["bt"].astype(np.int64)
    out = []
    for b0 in range(ts, te, BIN):
        b1 = min(b0 + BIN, te)
        n = int(((bt >= b0) & (bt < b1)).sum()); cov = n / ((b1 - b0) / 0.2118)
        out.append(dict(t0=b0, t1=b1, cov=round(cov, 3), use=cov >= 0.95))
    return out

def to_wins(tp, trig):
    wins = []
    for d in trig:
        ws = None
        if d["sells"]:
            k = d["sells"][0]; ws = (int(tp.s[k]), int(tp.i[k]))
        wins.append(dict(mint=d["mint"], slot=d["slot"], idx=d["idx"], j=d["j"], age_slots=d["age_slots"], v2=d["v2"], cashback=d["cashback"],
                         whale=d["whale"], whale_sell=ws, pred=None, quick=0, bt=d["bt"], half=1, pct=d["pct"], create_slot=d["create_slot"]))
    return wins

def one(job):
    stream, seed = job
    rng = np.random.default_rng(seed)
    res = sim.run(G["ck"], G["store"], G["streams"][stream], G["cfg"], G["land"], G["model"], G["view"], rng)
    rows = []
    for r in res:
        if not r["armed"]: continue
        rows.append((r["trig"]["bt"], int(r.get("filled", False)), int(r.get("net", 0)), int(r.get("pnl", 0)), int(r.get("fees", 0)), r.get("exit") or "",
                     r["trig"]["mint"], r["trig"]["slot"], r.get("fill_S")))
    return stream, seed, rows

# ---------------------------------------------------------------------------------------------------------------------------
def live_r22(tp_bt_of_slot):
    """MEASURED from run 22's jsonl: live pre-send (arms, skips, fills, realized, failed-try fees) and the paper shadow"""
    L = collections.defaultdict(list); start = stop = None
    for l in open(R22):
        r = json.loads(l); ev = r.get("ev")
        if ev == "run_start": start = r["t"] / 1e9
        elif ev == "presend_live_stop": stop = r
        elif ev and ev.startswith("presend"): L[ev].append(r)
    arms = {r["w"]: r for r in L["presend_live_arm"]}
    fills = collections.defaultdict(list)
    for r in L["presend_live_fill"]: fills[r["w"]].append(r)
    real = {r["w"]: r for r in L["presend_live_realized"]}
    closes = {r["w"]: r for r in L["presend_live_close"]}
    fee_of = lambda r: r["fee"] if r.get("fee") is not None else 5120          # "unseen" tries carry fee 0 (never landed)
    fail_fee = sum(fee_of(r) for r in L["presend_attempt_land"] if r.get("res") not in ("ok", "unseen"))
    fail_n = sum(1 for r in L["presend_attempt_land"] if r.get("res") not in ("ok", "unseen"))
    res_c = collections.Counter(r.get("res") for r in L["presend_attempt_land"])
    skips = collections.Counter(r.get("why") for r in L["presend_live_skip"])
    W = []
    for w, a in arms.items():
        t = a["trig"]; f = fills.get(w, []); rz = real.get(w); c = closes.get(w)
        W.append(dict(w=w, mint=t["mint"], slot=t["slot"], t=t["t"] / 1e9, nfill=len(f), pnl=(rz["pnl"] / 1e9 if rz else None),
                      curve_pnl=(c["curve_pnl"] / 1e9 if c else None), sol_in_curve=(c["sol_in_curve"] / 1e9 if c else None),
                      exit=(c or {}).get("exit_why"), age=t["age_slots"]))
    # paper shadow (rows a / b / c = 0 / 5 / 10 ms), scaled 0.55 -> 0.40 as the owner's numbers
    sarm = {(r["mint"], r["w"]): r for r in L["presend_arm"]}
    SH = []
    for r in L["presend_exit"]:
        a = sarm.get((r["mint"], r["w"]))
        SH.append(dict(row=r["row"], mint=r["mint"], s_in=r["s_in"], bt=tp_bt_of_slot(r["s_in"]), net=r["net_cheap"] * 0.40 / 0.55,
                       age=(a or {}).get("age_slots"), t_arm=((a or {}).get("t", 0) / 1e9)))
    return dict(start=start, stop=stop, W=W, fail_fee=fail_fee / 1e9, fail_n=fail_n, res=res_c, skips=skips, shadow=SH,
                n_att=len(L["presend_attempt"]), n_land=len(L["presend_attempt_land"]), arms_shadow=len(L["presend_arm"]))

def band(x):
    x = np.asarray(x, float)
    return float(np.mean(x)), float(np.percentile(x, 5)), float(np.percentile(x, 95))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="10-25 22:00"); ap.add_argument("--end", default="10-26 04:04")
    ap.add_argument("--draws", type=int, default=200); ap.add_argument("--procs", type=int, default=14); ap.add_argument("--tag", default="main"); ap.add_argument("--cut", type=float, default=0.0)
    A = ap.parse_args()
    t0 = time.time()
    tp = TapeLH()
    S = np.load(f"{TAB}/slots.npy"); slot_bt = dict(zip(S["slot"].astype(np.int64).tolist(), S["bt"].astype(np.int64).tolist()))
    def bt_of_slot(s):
        for d in range(0, 50):
            if s - d in slot_bt: return slot_bt[s - d]
        return None
    c22, r22_t0 = r22_cfg()
    slot_ms = json.load(open(f"{s48lib.S48}/p3check.json"))["slot_ms"]
    cfg = make_cfg(c22, slot_ms); cfg.follower_cut = A.cut          # stress test: drop this share of later buys at random
    D = pickle.load(open(f"{s48lib.S48}/donors123.pkl", "rb"))
    G["land"] = sim.Landing(D, probes=("P3",))
    G["model"] = s48lib.ModelN(D, s48_clock(), ("P1", "P2", "P3")); G["view"] = sim.View(); G["ck"] = tp.clock(); G["cfg"] = cfg
    ts, te = rlib.pk(A.start), rlib.pk(A.end)
    bins = bins_of(tp, ts, te); use = {b["t0"] for b in bins if b["use"]}
    trig = rlib.detect(tp, whale_pct=6.0)
    for d in trig: d.pop("mid", None)
    allw = to_wins(tp, trig)
    armable = lambda w: w["age_slots"] > 0 and w["v2"] and not w["cashback"]
    main = [w for w in allw if ts <= w["bt"] < te and (w["bt"] - ts) // BIN * BIN + ts in use]
    LV = live_r22(bt_of_slot)
    v0 = int(LV["start"]); v1 = int(LV["stop"]["t"] / 1e9) if LV["stop"] else v0 + 1800
    cbt = {m: c.get("bt", 0) for m, c in tp.creates.items()}
    val = [w for w in allw if v0 <= w["bt"] < v1 and cbt.get(w["mint"], 0) >= v0]
    G["streams"] = {"main": [w for w in main if armable(w)], "val": [w for w in val if armable(w)]}
    G["store"] = sim.build_store(tp, variants.spans_for(G["streams"]["main"] + G["streams"]["val"]))
    print(f"tape {rlib.pkt(int(S['bt'][0]), '%m-%d %H:%M:%S')} -> {rlib.pkt(int(S['bt'][-1]), '%m-%d %H:%M:%S')} PKT | removed our live pre-send txs {tp.n_skip} | "
          f"window {rlib.pkt(ts)} -> {rlib.pkt(te)} PKT, bins used {len(use)}/{len(bins)} ({len(use) * BIN / 3600:.2f} h); low: "
          f"{[(rlib.pkt(b['t0']), b['cov']) for b in bins if not b['use']]}", flush=True)
    print(f"triggers in window {len(main)}, armable {len(G['streams']['main'])} | validation span {rlib.pkt(v0, '%H:%M:%S')}->{rlib.pkt(v1, '%H:%M:%S')}: "
          f"triggers (token created after run start) {len(val)}, armable {len(G['streams']['val'])} | cfg k {cfg.k} paths {cfg.paths} global {cfg.global_rate} "
          f"size {cfg.size} slot_ms {slot_ms:.1f} | prep {time.time() - t0:.0f} s", flush=True)
    tp.slim()
    import gc; gc.collect()
    jobs = [(s, 900 + d) for s in ("main", "val") for d in range(A.draws)]
    R = collections.defaultdict(list)
    with Pool(A.procs) as p:
        for stream, seed, rows in p.imap_unordered(one, jobs, chunksize=1):
            R[stream].append((seed, rows))
    out = dict(R=dict(R), bins=bins, start=ts, end=te, live=LV, cfg=c22, slot_ms=slot_ms, val_span=(v0, v1),
               n_main=len(G["streams"]["main"]), n_val=len(G["streams"]["val"]),
               main_trig=[(w["bt"], w["mint"], w["slot"], w["age_slots"]) for w in main], val_trig=[(w["bt"], w["mint"], w["slot"]) for w in val])
    pickle.dump(out, open(f"{LH}/lasthour_{A.tag}.pkl", "wb"))
    for s in ("main", "val"):
        nets = [sum(r[2] for r in rows) / 1e9 for _, rows in R[s]]; fl = [sum(r[1] for r in rows) for _, rows in R[s]]
        print(s, "net %+.3f [%+.3f, %+.3f]" % band(nets), "fills %.1f" % np.mean(fl))
    print(f"done {time.time() - t0:.0f} s")
