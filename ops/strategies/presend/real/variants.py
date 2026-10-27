#!/usr/bin/env python3
"""REAL replay: the pre-registered variants (REAL_REPLAY.md 0.2) on every unseen test hour (hours.json), and the null.
Read-only. The tape is read once in the parent; workers fork and share the small token store.
usage: variants.py [--draws 6] [--nulls 20] [--procs 14] [--only NAME,NAME] [--tag main] [--mode interp|corr]"""
import sys, os, json, pickle, time, argparse, collections, math
import numpy as np
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib, sim

OUT = "/home/moiz/sniper-data/presend_real"
G = {}

# ---------------------------------------------------------------------------------------------------------------------------
def variant_list():
    V = {}
    base = dict(k=8, paths=[(30, 30)], global_rate=30, size=350_000_000)
    V["V0"] = dict(base)
    V["V1a"] = dict(base, whale_sell_ms=30.0 + 212.0)
    V["V1b"] = dict(base, whale_sell_ms=30.0 + 424.0)
    for k in (4, 8, 16, 32):
        V[f"V2_k{k}_c30"] = dict(base, k=k)
        V[f"V2_k{k}_c45"] = dict(base, k=k, paths=[(30, 30), (30, 30)], global_rate=45)
        V[f"V2_k{k}_c60"] = dict(base, k=k, paths=[(30, 30), (30, 30)], global_rate=60)
    for cap in (30, 60):
        pc = dict(paths=[(30, 30)], global_rate=30) if cap == 30 else dict(paths=[(30, 30), (30, 30)], global_rate=60)
        V[f"V3a_c{cap}"] = dict(base, **pc, v3="a")
        V[f"V3b_c{cap}"] = dict(base, **pc, v3="b")
        for k in (16, 32):
            V[f"V4a_k{k}_c{cap}"] = dict(base, **pc, k=k, v4=1)
            V[f"V4b_k{k}_c{cap}"] = dict(base, **pc, k=k, v4=2)
    # EXPLORATORY (added after the pre-registered runs; not part of the pass / fail): caps set so the path's 1-second budget never empties
    V["X_k8_g25"] = dict(base, k=8, global_rate=25)
    V["X_k6_c30"] = dict(base, k=6)
    return V

def make_cfg(spec):
    spec = dict(spec)
    v3 = spec.pop("v3", None); v4 = spec.pop("v4", None)
    cfg = sim.Cfg(**spec)
    if v3:
        def kfun(w, E, cfg_k=cfg.k):
            pred = w.trig.get("pred")
            if pred is None: return cfg_k
            return 32 if abs((E - w.st) - pred) <= 1 else 2
        cfg.kfun = kfun
        if v3 == "b": cfg.arm_filter = lambda x: x.get("pred") is not None
    if v4: cfg.arm_filter = lambda x, n=v4: x.get("quick", 0) >= n
    return cfg

# ---------------------------------------------------------------------------------------------------------------------------
def prepare(whale_pct=6):
    tp = rlib.Tape()
    H = json.load(open(f"{OUT}/hours.json"))
    test = H["test"]
    bin_of = {}
    for x in test: bin_of[x["t0"]] = x
    trig = pickle.load(open(f"{OUT}/trig_{whale_pct}.pkl", "rb"))
    # whale history (causal): every T2 trigger of the whale, any token, chain order
    trig.sort(key=lambda d: (d["slot"], d["idx"], d["j"]))
    hist = collections.defaultdict(list)       # whale -> list of (slot, delay slots or None, drop ratio or None)
    wins = []
    for d in trig:
        ws = None; delay = None; drop = None
        if d["sells"]:
            k = d["sells"][0]
            ws = (int(tp.s[k]), int(tp.i[k]))
            delay = ws[0] - d["slot"]
            v, t, so, tk = int(tp.vsol[k]), int(tp.vtok[k]), int(tp.sol[k]), int(tp.tok[k])
            drop = (v / t) / ((v + so) / max(t - tk, 1))
        H_ = [h for h in hist[d["whale"]] if h[0] < d["slot"]]
        qs = [h for h in H_ if h[1] is not None and h[1] <= 10 and h[0] + h[1] < d["slot"]]      # the sell already happened (no lookahead)
        quick = sum(1 for h in qs if h[2] is not None and h[2] <= 0.88)
        pred = float(np.median([h[1] for h in qs])) if qs else None
        hist[d["whale"]].append((d["slot"], delay, drop))
        t0 = d["bt"] // 600 * 600
        b = bin_of.get(t0)
        if b is None: continue
        wins.append(dict(mint=d["mint"], slot=d["slot"], idx=d["idx"], j=d["j"], age_slots=d["age_slots"], v2=d["v2"], cashback=d["cashback"],
                         whale=d["whale"], whale_sell=ws, pred=(round(pred) if pred is not None else None), quick=quick, bt=d["bt"], half=b["half"],
                         pct=d["pct"]))
    # skip create-slot / legacy / cashback triggers before the run (the simulator would skip them; they never arm)
    armable = [w for w in wins if w["age_slots"] > 0 and w["v2"] and not w["cashback"]]
    return tp, H, wins, armable

def null_windows(tp, H, counts, seed):
    """null: at random times inside each test bin, on random followed tradeable tokens (a trade in the last 10 slots, curve < 100 SOL,
    not in their create slot); counts[t0] windows per bin. The 'trigger' is that token's latest trade; no whale."""
    rng = np.random.default_rng(seed)
    Ss, Sm, Sv = G["slot_sorted"]
    out = []
    for b in H["test"]:
        n = counts.get(b["t0"], 0)
        for _ in range(n):
            for attempt in range(30):
                s = int(rng.integers(b["s_lo"], b["s_hi"] + 1))
                a = np.searchsorted(Ss, s - 10, side="left"); e = np.searchsorted(Ss, s, side="right")
                if e <= a: continue
                k = int(rng.integers(a, e))
                if int(Sm[k]) not in G["followed"]: continue
                mint = tp.ids[int(Sm[k])]
                c = tp.creates.get(mint)
                if c is None or c.get("mayhem") or c.get("mayhem_ix") or not c.get("v2") or c.get("cashback"): continue
                if int(Sv[k]) >= rlib.UNTRADE_V or int(Ss[k]) == c["slot"]: continue
                # the token's latest trade at or before slot s
                mid = int(Sm[k]); a2, e2 = tp.span[mid]
                ss = tp.s[a2:e2]; kk = a2 + int(np.searchsorted(ss, s, side="right")) - 1
                if kk < a2 or tp.vsol[kk] >= rlib.UNTRADE_V: continue
                out.append(dict(mint=mint, slot=int(tp.s[kk]), idx=int(tp.i[kk]), j=int(tp.j[kk]), age_slots=int(tp.s[kk]) - c["slot"], v2=True, cashback=False,
                                whale=-1, whale_sell=None, pred=None, quick=0, bt=int(tp.blockt[kk]), half=b["half"], null=True))
                break
    return out

def spans_for(ws, spans=None):
    spans = spans if spans is not None else {}
    for x in ws:
        lo, hi = spans.get(x["mint"], (1 << 62, 0))
        spans[x["mint"]] = (min(lo, x["slot"] - 40), max(hi, x["slot"] + 70))
    return spans

# ---------------------------------------------------------------------------------------------------------------------------
def arm_rule(spec):
    if spec.get("v4"): return f"v4_{spec['v4']}"
    if spec.get("v3") == "b": return "v3b"
    return "none"

def one(job):
    name, seed, kind = job
    spec = G["V"][name]
    cfg = make_cfg(spec)
    rng = np.random.default_rng(seed)
    if kind == "main":
        ws = G["armable"]; store = G["store_main"]
    else:
        ws, spans = G["nulls"][(arm_rule(spec), seed)]
        store = sim.LazyStore(G["tp"], spans)
    res = sim.run(G["ck"], store, ws, cfg, G["land"], G["model"], G["view"], rng)
    rows = []
    for r in res:
        if not r["armed"]: continue
        rows.append((r["trig"]["half"], r["trig"]["bt"], int(r.get("filled", False)), r.get("net", 0), r.get("pnl", 0), r.get("fees", 0), r.get("sent", 0),
                     r.get("landed", 0), sum((r.get("rate") or {}).values()), r.get("paused", 0), r.get("exit") or "", r["trig"]["mint"], r.get("xgap")))
    return name, seed, kind, rows

def summarize(rows, hours, half_hours):
    a = rows
    tot = sum(r[3] for r in a) / 1e9
    fills = sum(r[2] for r in a); fees = sum(r[5] for r in a) / 1e9; pnl = sum(r[4] for r in a) / 1e9
    h = {1: sum(r[3] for r in a if r[0] == 1) / 1e9, 2: sum(r[3] for r in a if r[0] == 2) / 1e9}
    return dict(day=tot / hours * 24, h1=h[1] / half_hours[1] * 24, h2=h[2] / half_hours[2] * 24, fills_day=fills / hours * 24, armed_day=len(a) / hours * 24,
                fee_per_fill=(fees / fills if fills else float("nan")), pnl_per_fill=(pnl / fills if fills else float("nan")), net=tot, fills=fills,
                sent_day=sum(r[6] for r in a) / hours * 24, refused_day=sum(r[8] for r in a) / hours * 24)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--draws", type=int, default=4); ap.add_argument("--nulls", type=int, default=20); ap.add_argument("--procs", type=int, default=14)
    ap.add_argument("--only", default=""); ap.add_argument("--tag", default="main"); ap.add_argument("--mode", default="interp")
    ap.add_argument("--null-all", action="store_true", help="null runs for every variant (default: only those positive in both halves)")
    ap.add_argument("--size", type=float, default=0.0, help="override the size (SOL) of every selected variant (V5)")
    ap.add_argument("--drop-ours", action="store_true", help="remove our own wallets' trades (FRA / AMS bots) from the tape")
    ap.add_argument("--cut", type=float, default=0.0, help="stress: drop this share of later buys at random")
    ap.add_argument("--lag", type=float, default=0.0, help="stress: every try lands this many ms later")
    A = ap.parse_args()
    t0 = time.time()
    tp, H, wins, armable = prepare(6)
    if A.drop_ours:
        idm = tp.id_map(); tp.drop_users = {idm[w] for w in rlib.WALLETS if w in idm}
        print("our wallets' own trades removed from the tape:", len(tp.drop_users), flush=True)
    hours = H["hours"]; half_hours = {1: sum(1 for x in H["test"] if x["half"] == 1) / 6.0, 2: sum(1 for x in H["test"] if x["half"] == 2) / 6.0}
    print(f"test hours {hours:.1f} (halves {half_hours[1]:.1f} / {half_hours[2]:.1f}); triggers in test hours {len(wins)}, armable {len(armable)} "
          f"(create-slot {sum(1 for w in wins if w['age_slots'] == 0)}, legacy {sum(1 for w in wins if not w['v2'])}, cashback {sum(1 for w in wins if w['cashback'])})", flush=True)
    V = variant_list()
    if A.only: V = {k: v for k, v in V.items() if k in A.only.split(",")}
    if A.size > 0: V = {k: dict(v, size=int(round(A.size * 1e9))) for k, v in V.items()}
    if A.cut > 0: V = {k: dict(v, follower_cut=A.cut) for k, v in V.items()}
    if A.lag != 0: V = {k: dict(v, extra_lag_ms=A.lag) for k, v in V.items()}
    G["V"] = V
    D = pickle.load(open(f"{OUT}/donors.pkl", "rb"))
    G["land"] = sim.Landing(D, mode=A.mode); G["model"] = sim.Model(D, tp); G["view"] = sim.View(); G["ck"] = tp.clock()
    G["armable"] = armable
    G["store_main"] = sim.build_store(tp, spans_for(armable))
    T = np.load(f"{rlib.TAB}/trades.npy")
    G["slot_sorted"] = (np.ascontiguousarray(T["slot"]).astype(np.int64), np.ascontiguousarray(T["mint"]), np.ascontiguousarray(T["vsol"]))
    del T
    G["followed"] = rlib.followed_mints(tp)
    tp.slim(); G["tp"] = tp
    print(f"main store {len(G['store_main'])} tokens, {sum(t.n for t in G['store_main'].values()):,} trades; prep {time.time() - t0:.0f} s", flush=True)
    import gc; gc.collect()
    # phase 1: every variant on the real triggers
    R = collections.defaultdict(list)
    jobs = [(n, 100 + d, "main") for n in V for d in range(A.draws)]
    with Pool(A.procs) as p:
        for name, seed, kind, rows in p.imap_unordered(one, jobs, chunksize=1):
            R[(name, kind)].append((seed, rows))
    print(f"phase 1 done {time.time() - t0:.0f} s", flush=True)
    # phase 2: the null (random arming at each variant's own armed rate per 10-min bin), for the variants positive in both halves
    need = []
    for name in V:
        sm = [summarize(rows, hours, half_hours) for seed, rows in R[(name, "main")]]
        h1 = np.mean([x["h1"] for x in sm]); h2 = np.mean([x["h2"] for x in sm])
        if A.null_all or (h1 > 0 and h2 > 0): need.append(name)
    G["nulls"] = {}
    if A.nulls > 0 and need:
        for rule in sorted({arm_rule(V[n]) for n in need}):
            ref = next(n for n in need if arm_rule(V[n]) == rule)
            counts = collections.Counter()
            for seed, rows in R[(ref, "main")]:
                for r in rows: counts[r[1] // 600 * 600] += 1
            nd = len(R[(ref, "main")])
            counts = {k: int(round(v / nd)) for k, v in counts.items()}
            for sd in range(A.nulls):
                ws = null_windows(tp, H, counts, 5000 + sd)
                G["nulls"][(rule, 5000 + sd)] = (ws, spans_for(ws))
            print(f"null sets for rule {rule}: {A.nulls} x {sum(counts.values())} windows", flush=True)
        G.pop("slot_sorted", None); gc.collect()
        jobs = [(n, 5000 + sd, "null") for n in need for sd in range(A.nulls)]
        with Pool(A.procs) as p:
            for name, seed, kind, rows in p.imap_unordered(one, jobs, chunksize=1):
                R[(name, kind)].append((seed, rows))
    out = {}
    for (name, kind), lst in R.items():
        sm = [summarize(rows, hours, half_hours) for seed, rows in lst]
        keys = sm[0].keys()
        out[f"{name}|{kind}"] = dict(mean={k: float(np.nanmean([s_[k] for s_ in sm])) for k in keys}, draws=sm)
    pickle.dump(dict(R=R, hours=hours, half_hours=half_hours, need_null=need), open(f"{OUT}/variants_{A.tag}_raw.pkl", "wb"))
    json.dump(out, open(f"{OUT}/variants_{A.tag}.json", "w"), indent=1)
    print(f"done {time.time() - t0:.0f} s")
    for key in sorted(out):
        m = out[key]["mean"]
        print("%-16s SOL/day %+7.2f | h1 %+7.2f h2 %+7.2f | fills/day %6.1f armed/day %6.0f | fee/fill %.4f pnl/fill %+.4f | sent/day %8.0f refused/day %7.0f" % (
            key, m["day"], m["h1"], m["h2"], m["fills_day"], m["armed_day"], m["fee_per_fill"], m["pnl_per_fill"], m["sent_day"], m["refused_day"]))
