#!/usr/bin/env python3
"""DENSITY step 2 (read-only, offline): replay one run's live pre-send windows under every execution scenario, N draws each.
Streams:
  cal      : the live windows forced armed, live QUIET stops kept, live settings (k 4, helius-ps 20/s, one position): calibration
  <others> : as live (A0 of REPORT28): windows armed with the dynamic checks (blocked_armed / blocked_position); QUIET's live stops
             at their live time and no fill before them; the lever changed as named (see SCEN)
Every window draws from its own generator (common random numbers), so the difference between two scenarios is the lever (and the
knock-on it causes), not noise.
usage: drun.py RUN [--draws 100] [--procs 14] [--only a,b]"""
import sys, os, json, pickle, argparse, collections, time, copy
import numpy as np
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlib, dsim
sys.path.insert(0, dlib.REAL)
import sim, s48lib

H, N, G, L = "helius-ps", "nozomi", "glaive", "landx-fra3"
H2, H3 = "helius-ps#2", "helius-ps#3"


def R(default, **cls): return dict(default=default, **cls)


B1 = R([H], bam=[N], harmonic=[N], jito=[G], fd=[L])
B2 = R([H], bam=[N, H], harmonic=[N, H], jito=[G, H], fd=[L, H])
# name: (k, routes, max_pos, extra)
SCEN = {
    "cal": (4, R([H]), 1, dict(force=True)),
    "base": (4, R([H]), 1, {}),
    "k8_1p": (8, R([H]), 1, {}), "k16_1p": (16, R([H]), 1, {}),
    "cap2_k4": (4, R([H, H2]), 1, {}), "cap2_k8": (8, R([H, H2]), 1, {}), "cap2_k16": (16, R([H, H2]), 1, {}),
    "cap3_k4": (4, R([H, H2, H3]), 1, {}), "cap3_k8": (8, R([H, H2, H3]), 1, {}), "cap3_k16": (16, R([H, H2, H3]), 1, {}),
    "a2_k4": (4, R([H, N]), 1, {}), "a2_k8": (8, R([H, N]), 1, {}), "a2_k16": (16, R([H, N]), 1, {}),
    "a3_k4": (4, R([H, N, G]), 1, {}), "a3_k8": (8, R([H, N, G]), 1, {}), "a3_k16": (16, R([H, N, G]), 1, {}),
    "b1_k4": (4, B1, 1, {}), "b2_k8": (8, B2, 1, {}), "b2_k16": (16, B2, 1, {}),
    "pos2": (4, R([H]), 2, {}),
    "cap3_k8_pos2": (8, R([H, H2, H3]), 2, {}), "cap3_k16_pos2": (16, R([H, H2, H3]), 2, {}),
    "a3_k8_pos2": (8, R([H, N, G]), 2, {}), "a3_k16_pos2": (16, R([H, N, G]), 2, {}),
    "b2_k8_pos2": (8, B2, 2, {}), "b1_k4_pos2": (4, B1, 2, {}), "a2_k8_pos2": (8, R([H, N]), 2, {}),
    # landing-model bounds for dense k: a try between two donor tries takes the earlier one's delay (no interpolation)
    "base_corr": (4, R([H]), 1, dict(corr=True)), "cap3_k8_corr": (8, R([H, H2, H3]), 1, dict(corr=True)),
    "cap3_k16_corr": (16, R([H, H2, H3]), 1, dict(corr=True)), "a3_k8_pos2_corr": (8, R([H, N, G]), 2, dict(corr=True)),
    # path-model bounds: half the measured path delta / the near delta applied on far leaders too
    "a3_k8_half": (8, R([H, N, G]), 1, dict(scale=0.5)), "b1_k4_half": (4, B1, 1, dict(scale=0.5)),
    "a3_k8_far": (8, R([H, N, G]), 1, dict(far=True)), "b1_k4_far": (4, B1, 1, dict(far=True)),
    # 20% fewer later buyers
    "base_cut": (4, R([H]), 1, dict(cut=0.2)), "pos2_cut": (4, R([H]), 2, dict(cut=0.2)),
    "cap3_k8_cut": (8, R([H, H2, H3]), 1, dict(cut=0.2)), "cap3_k16_cut": (16, R([H, H2, H3]), 1, dict(cut=0.2)),
    "a3_k8_cut": (8, R([H, N, G]), 1, dict(cut=0.2)), "a3_k8_pos2_cut": (8, R([H, N, G]), 2, dict(cut=0.2)),
    "cap3_k16_pos2_cut": (16, R([H, H2, H3]), 2, dict(cut=0.2)), "b1_k4_cut": (4, B1, 1, dict(cut=0.2)),
    "cap3_k8_pos2_cut": (8, R([H, H2, H3]), 2, dict(cut=0.2)),
    # every try lands 15 ms later (REPORT28's lag stress: live lands later than the replay on bouncing dumps)
    "base_lag15": (4, R([H]), 1, dict(lag=15.0)), "pos2_lag15": (4, R([H]), 2, dict(lag=15.0)),
    "cap3_k8_lag15": (8, R([H, H2, H3]), 1, dict(lag=15.0)), "cap3_k16_lag15": (16, R([H, H2, H3]), 1, dict(lag=15.0)),
    "a3_k8_pos2_lag15": (8, R([H, N, G]), 2, dict(lag=15.0)), "cap3_k8_pos2_lag15": (8, R([H, H2, H3]), 2, dict(lag=15.0)),
    "b1_k4_lag15": (4, B1, 1, dict(lag=15.0)),
    # the whale-sell stop 80 ms after the engine sees the whale's first sell (live 30): faster paths have fewer tries in flight
    "base_ws80": (4, R([H]), 1, dict(ws=80.0)), "b1_k4_ws80": (4, B1, 1, dict(ws=80.0)), "a3_k8_ws80": (8, R([H, N, G]), 1, dict(ws=80.0)),
    "cap3_k8_ws80": (8, R([H, H2, H3]), 1, dict(ws=80.0)),
    # the recommended lever's checks: k 8 on 2 paths' capacity (helius-ps-like / + nozomi / + glaive)
    "cap2_k8_cut": (8, R([H, H2]), 1, dict(cut=0.2)), "cap2_k8_lag15": (8, R([H, H2]), 1, dict(lag=15.0)),
    "cap2_k8_corr": (8, R([H, H2]), 1, dict(corr=True)), "a2_k8_cut": (8, R([H, N]), 1, dict(cut=0.2)),
    "hg_k8": (8, R([H, G]), 1, {}), "hg_k8_cut": (8, R([H, G]), 1, dict(cut=0.2)),
}

G_ = {}


def near_map():
    """P3 (AMS run 19) tries: sig -> leader prefix (MEASURED, presend_attempt.leader); near = ops/region/near_leaders_ams.txt"""
    m = {}
    for l in open("/home/moiz/sniper-data/runs/ams/runs/dip_ams_r19.jsonl", errors="ignore"):
        if '"ev":"presend_attempt"' not in l: continue
        x = json.loads(l); m[x["sig"]] = (x.get("leader") or "")[:8]
    m["__set__"] = set(l.split()[0][:8] for l in open("/home/moiz/sniper/ops/region/near_leaders_ams.txt") if l.strip() and not l.startswith("#"))
    return m


def s48_clock():
    S = np.load(f"{s48lib.TAB48}/slots.npy")
    slot0 = int(S["slot"][0]); n = int(S["slot"][-1]) - slot0 + 1
    bs = np.zeros(n, np.int32); bs[S["slot"].astype(np.int64) - slot0] = S["maxi"].astype(np.int32) + 1
    import rlib
    return rlib.Clock(slot0, bs)


def make_cfg(base, name):
    k, routes, mp, ex = SCEN[name]
    c = copy.copy(base)
    c.k = k; c.routes = routes; c.max_pos = mp
    npaths = len({p for v in routes.values() for p in v})
    c.path_rate = base.paths[0][0]; c.global_rate = base.global_rate * npaths
    c.path_scale = ex.get("scale", 1.0); c.far_too = ex.get("far", False)
    c.follower_cut = ex.get("cut", 0.0); c.extra_lag_ms = ex.get("lag", 0.0); c.whale_sell_ms = ex.get("ws", base.whale_sell_ms)
    return c


def wlist(name):
    out = []
    force = SCEN[name][3].get("force", False)
    for x in G_["S"]["live"]:
        y = dict(x)
        if force:
            y["force_arm"] = True
            if x["d_stop"] is not None: y["stop_at_d"] = x["d_stop"]
        else:
            if x["d_stop"] is not None:
                if not x.get("stop_filled"): y["nofill_before_d"] = x["d_stop"]
                y["stop_at_d"] = x["d_stop"]
        out.append(y)
    return out


def one(job):
    name, seed = job
    S = G_["S"]; cfg = G_["cfgs"][name]
    land = G_["landc"] if SCEN[name][3].get("corr") else G_["land"]
    res = dsim.run_d(S["ck"], S["store"], wlist(name), cfg, land, G_["model"], G_["view"], seed, G_["pm"], exclude_self=True,
                     our_id=S["our_id"], whale_ids=S["whale_ids"])
    by = {}
    for r in res:
        k = r["trig"]["w"]
        if not r["armed"]: by[k] = (0, 0, 0, 0, 0, 0, None); continue
        rs = sum((r.get("rate") or {}).values())
        by[k] = (1, int(r["filled"]), int(r["pnl"]), int(r["fees"]), int(r.get("sent", 0)), rs, r.get("fill_path"))
    return name, seed, by


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=int); ap.add_argument("--draws", type=int, default=100); ap.add_argument("--procs", type=int, default=14)
    ap.add_argument("--only", default=""); ap.add_argument("--tag", default="main")
    A = ap.parse_args()
    t0 = time.time()
    S = dlib.setup_run(A.run)
    D3 = pickle.load(open(f"{s48lib.S48}/donors123.pkl", "rb"))
    pm = dsim.PathModel()
    nm = near_map()
    G_["S"] = S; G_["pm"] = pm
    G_["land"] = dsim.LandingX(D3, pm, nm, probes=("P3",))
    G_["landc"] = dsim.LandingX(D3, pm, nm, probes=("P3",), mode="corr")
    G_["model"] = s48lib.ModelN(D3, s48_clock(), ("P1", "P2", "P3"))
    G_["view"] = sim.View()
    names = [n for n in SCEN if not A.only or n in A.only.split(",")]
    G_["cfgs"] = {n: make_cfg(S["cfg"], n) for n in names}
    meta = dict(run=A.run, draws=A.draws, slot_ms=S["slot_ms"], size=S["cfg"].size, hours=S["hours"], start_ns=S["start_ns"], end_ns=S["end_ns"],
                scen={n: dict(k=SCEN[n][0], routes=SCEN[n][1], max_pos=SCEN[n][2], extra=SCEN[n][3]) for n in names},
                live=[dict(w=x["w"], mint=x["mint"], t_ns=x["t_ns"], dumped=x["dumped"], d_stop=x["d_stop"], live=x["live"]) for x in S["live"]],
                lanes=[list(k) for k in pm.used])
    S.pop("R", None)
    import gc; gc.collect()
    print(f"r{A.run}: {len(S['live'])} windows, size {S['cfg'].size / 1e9:.2f}, slot_ms {S['slot_ms']:.1f}, {S['hours']:.2f} h, setup {time.time() - t0:.0f} s", flush=True)
    jobs = [(n, 9000 + d) for n in names for d in range(A.draws)]
    out = collections.defaultdict(list)
    with Pool(A.procs) as p:
        for k, (name, seed, by) in enumerate(p.imap_unordered(one, jobs, chunksize=2)):
            out[name].append((seed, by))
            if k % 500 == 0: print(f"  {k}/{len(jobs)} {time.time() - t0:.0f} s", flush=True)
    for s in out: out[s].sort(key=lambda z: z[0])
    fn = f"{dlib.DATA}/rep_r{A.run}_{A.tag}.pkl"
    pickle.dump(dict(meta=meta, out=dict(out)), open(fn, "wb"))
    print(f"wrote {fn}: {len(names)} scenarios x {A.draws} draws, {time.time() - t0:.0f} s", flush=True)
