#!/usr/bin/env python3
"""migpaper scorer (PAPER ONLY): score the frozen near-graduation rule on one window [start, end) of block time.
Decodes the recorder chunks covering [start - LOOKBACK, end + LOOKAHEAD] (local keeper copies first; a chunk the keeper
has not copied yet is fetched read-only from FRA with `ssh … sudo cat`, decoded, raw copy deleted), builds one tape,
finds every first crossing of vSOL >= 105 inside the window, computes the m1 features, scores p30 with the frozen model,
replays both entry modes (react / pre-send, 2 SOL) with the frozen exits, appends one line per window to --out and one per
entrable crossing to --trades, then extends the wallet / creator stores with the tape's trips (unless --no-store-update).
Usage: mp_score.py --start BT --end BT [--models frozen|val] [--cache DIR] [--out F] [--trades F] [--state F]
       [--procs N] [--no-fetch] [--no-store-update] [--wstore F] [--cstore F] [--label S] [--lookback S] [--lookahead S]"""
import sys, os, glob, json, time, subprocess, argparse
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mplib
from mplib import D, V, THETA, EXITS, MODES, pkt, pday, SLOT_S

LOCAL = ["/home/moiz/sniper-data/collect"]
SCRATCH = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/e2x1_migpaper/fetch"
SSH = ["ssh", "-p", "1996", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "it@84.32.100.36"]
CHUNK_S = 300

def local_chunks(lo, hi, dirs):
    out = {}
    for d in dirs:
        for fn in glob.glob(f"{d}/run_*/txs/txs_*.jsonl.gz"):
            t = mplib.chunk_ts(fn)
            if lo <= t <= hi: out[(os.path.basename(os.path.dirname(os.path.dirname(fn))), t)] = fn
    return out

def server_chunks(lo, hi):
    try:
        r = subprocess.run(SSH + ["sudo ls -d /root/sniper-collect/run_*/txs/txs_*.jsonl.gz"], capture_output=True, text=True, timeout=60)
    except Exception as ex:
        print("server list failed:", ex, flush=True); return {}
    out = {}
    for ln in r.stdout.split():
        try: t = mplib.chunk_ts(ln)
        except Exception: continue
        if lo <= t <= hi: out[(ln.split("/")[3], t)] = ln
    return out

def fetch(remote, run, ts):
    os.makedirs(f"{SCRATCH}/{run}/txs", exist_ok=True)
    loc = f"{SCRATCH}/{run}/txs/txs_{ts}.jsonl.gz"
    with open(loc + ".part", "wb") as f:
        r = subprocess.run(SSH + [f"sudo cat {remote}"], stdout=f, timeout=600)
    if r.returncode != 0: os.unlink(loc + ".part"); return None
    os.replace(loc + ".part", loc); return loc

def decode(cache, files, procs):
    os.makedirs(cache, exist_ok=True)
    from multiprocessing import Pool
    with Pool(procs) as p:
        for o, msg in p.imap_unordered(mplib.g1_decode.one, [(f, cache) for f in files]):
            if msg != "cached": print("  decoded", os.path.basename(o), msg[:60], flush=True)

def ensure_cache(lo, hi, cache, procs, dirs, allow_fetch=True, min_age=240):
    have = local_chunks(lo, hi, dirs); now = time.time()
    have = {k: v for k, v in have.items() if now - os.path.getmtime(v) >= min_age}
    need = {k: v for k, v in have.items() if not os.path.exists(mplib.cache_name(cache, v))}
    if need:
        print(f"decoding {len(need)} local chunks", flush=True); decode(cache, sorted(need.values()), procs)
    files = {k: mplib.cache_name(cache, v) for k, v in have.items()}
    if allow_fetch:
        srv = server_chunks(lo, hi)
        miss = {k: v for k, v in srv.items() if k not in files and not os.path.exists(f"{cache}/{k[0]}__txs_{k[1]}.npz")}
        miss = {k: v for k, v in miss.items() if now - k[1] >= CHUNK_S + min_age}
        for k, remote in sorted(miss.items()):
            loc = fetch(remote, k[0], k[1])
            if not loc: print("fetch failed", remote, flush=True); continue
            decode(cache, [loc], 1); os.unlink(loc)
            files[k] = mplib.cache_name(cache, loc); print("fetched+decoded (server, read-only)", k, flush=True)
    for fn in glob.glob(f"{cache}/*.npz"):
        if fn.endswith(".tmp.npz"): continue
        t = mplib.chunk_ts(fn)
        if lo <= t <= hi: files[(os.path.basename(fn).split("__")[0], t)] = fn
    return sorted(set(files.values()))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, required=True); ap.add_argument("--end", type=int, required=True)
    ap.add_argument("--models", default="frozen"); ap.add_argument("--cache", default=f"{D}/cache")
    ap.add_argument("--out", default=f"{D}/out/results.jsonl"); ap.add_argument("--trades", default=f"{D}/out/trades.jsonl")
    ap.add_argument("--state", default=f"{D}/out/state.json"); ap.add_argument("--procs", type=int, default=2)
    ap.add_argument("--local", nargs="*", default=LOCAL); ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--no-store-update", action="store_true"); ap.add_argument("--wstore", default=f"{D}/wstore.npz"); ap.add_argument("--cstore", default=f"{D}/cstore.npz")
    ap.add_argument("--label", default=""); ap.add_argument("--lookback", type=int, default=mplib.LOOKBACK); ap.add_argument("--lookahead", type=int, default=mplib.LOOKAHEAD)
    a = ap.parse_args()
    t0 = time.time()
    lo, hi = a.start - a.lookback, a.end + a.lookahead
    files = ensure_cache(lo, hi, a.cache, a.procs, a.local, allow_fetch=not a.no_fetch)
    if not files: print("no chunks"); return 2
    T = mplib.WTape(files)
    print(f"tape: {len(files)} chunks, {len(T.T)} trades, {len(T.P)} pool events, bt {pkt(T.bt_lo).strftime('%m-%d %H:%M')}..{pkt(T.bt_hi).strftime('%m-%d %H:%M')} PKT, {time.time() - t0:.0f}s", flush=True)
    pre = "val_" if a.models == "val" else ""
    MD = D + "/models"
    M30 = mplib.NPModel(f"{MD}/{pre}p30.json"); M120 = mplib.NPModel(f"{MD}/{pre}p120.json"); MC = mplib.NPModel(f"{MD}/{pre}cont.json")
    names = M30.names; DLY = mplib.dly()
    ws = mplib.WStore(a.wstore); cs = mplib.CStore(a.cstore)
    cands = mplib.candidates(T)
    n_cross = n_in_window = n_entrable = n_sel = n_sel_arm = 0; rows_out = []
    hour_ix = names.index("hour")
    for m in cands:
        rows = T.trades(m)
        if len(rows) == 0: continue
        k = mplib.first_crossing(rows)
        if k is None: continue
        n_cross += 1
        t = int(rows["bt"][k])
        if not (a.start <= t < a.end): continue
        n_in_window += 1
        if rows["rtok"][k] == 0: continue              # the crossing trade completes the curve: not entrable
        n_entrable += 1
        f = mplib.features(T, m, rows, k, ws, cs)
        x = np.array([[float(f[q]) for q in names]], np.float32).astype(np.float64)   # the models were fit on float32 features (m1/m2)
        p30 = float(M30.proba(x)[0]); p120 = float(M120.proba(x)[0])
        c_ = np.nonzero(rows["rtok"] == 0)[0]; c = int(c_[0]) if len(c_) else None
        mg = T.mig.get(m); cmp_ = T.cmp.get(m)
        rec = dict(mint=m, bt=t, pkt=pkt(t).strftime("%m-%d %H:%M:%S"), day=pday(t), slot=int(rows["slot"][k]), idx=int(rows["idx"][k]), k=int(k),
                   p30=round(p30, 4), p120=round(p120, 4), vsol=round(f["vsol"], 3), sol_left=round(f["sol_left"], 3), age_s=int(f["age_s"]),
                   cross_sol=round(f["cross_sol"], 3), grad=c is not None, t_complete=round((rows["slot"][c] - rows["slot"][k]) * SLOT_S, 3) if c is not None else None,
                   has_mig=mg is not None, mig_slot=mg["slot"] if mg else None, cmp_slot=cmp_["slot"] if cmp_ else None,
                   entered=p30 >= THETA, window=a.start, label=a.label, models=a.models,
                   tape_tail_s=int(T.bt_hi - t))
        # ARM-gate (FROZEN.md 10-29 addendum): same frozen p30 on the features at the pre-send arm trade a (first trade of the
        # run of vSOL >= V - DELTA ending at the crossing; = sim_row's arm_k). Strictly causal: features use rows[:a + 1] only.
        vs_ = rows["vsol"].astype(float) / 1e9; a_ = k
        while a_ > 0 and vs_[a_ - 1] >= V - mplib.DELTA: a_ -= 1
        if a_ == k: p30a = p30
        else:
            fa = mplib.features(T, m, rows[:a_ + 1], a_, ws, cs)
            xa = np.array([[float(fa[q]) for q in names]], np.float32).astype(np.float64)
            p30a = float(M30.proba(xa)[0])
        rec.update(arm_k=int(a_), arm_lead_rows=int(k - a_), arm_vsol=round(float(vs_[a_]), 3), arm_bt=int(rows["bt"][a_]),
                   arm_lead_slots=int(rows["slot"][k] - rows["slot"][a_]), p30_arm=round(p30a, 4), entered_arm=p30a >= THETA)
        if p30 >= THETA or p30a >= THETA:
            ck = mplib.ck_feats(rows, k, V, p120, float(x[0, hour_ix]))
            PCrow = {}
            for sec, v in ck.items():
                PCrow[sec] = float(MC.proba(v[0][None, :].astype(np.float64))[0]) if v is not None else None
            rec["pc"] = {str(s): (round(v, 3) if v is not None else None) for s, v in PCrow.items()}
        if p30 >= THETA:
            n_sel += 1
            for mode in MODES:
                r = mplib.sim_row(T, m, rows, k, mode, PCrow, DLY)
                rec[mode] = {kk: (round(vv, 6) if isinstance(vv, float) else vv) for kk, vv in r.items() if kk != "mode"}
        if p30a >= THETA:
            n_sel_arm += 1
            if "pre" in rec: rec["pre_arm"] = rec["pre"]
            else:
                r = mplib.sim_row(T, m, rows, k, "pre", PCrow, DLY)
                rec["pre_arm"] = {kk: (round(vv, 6) if isinstance(vv, float) else vv) for kk, vv in r.items() if kk != "mode"}
        rows_out.append(rec)
    # ---- window summary
    ent = [r for r in rows_out if r["entered"]]
    summ = dict(start=a.start, end=a.end, start_pkt=pkt(a.start).strftime("%m-%d %H:%M"), end_pkt=pkt(a.end).strftime("%m-%d %H:%M"), label=a.label, models=a.models,
                chunks=len(files), tape_bt=[T.bt_lo, T.bt_hi], lookahead_ok=bool(T.bt_hi >= a.end + 600), trunc=sum(1 for mm in T.metas if mm.get("trunc")),
                n_cross=n_cross, n_in_window=n_in_window, n_entrable=n_entrable, n_selected=n_sel, scored_at=int(time.time()), secs=round(time.time() - t0))
    for mode in MODES:
        for xi, ex in enumerate(EXITS):
            tag = f"{mode}_{'stop' if isinstance(ex[1], float) else 'pd'}"
            rr = np.array([r[mode]["res"][xi] for r in ent]) if ent else np.zeros(0)
            g = np.array([r["grad"] for r in ent], bool) if ent else np.zeros(0, bool)
            summ[tag] = float(np.nansum(rr)); summ[tag + "_grad"] = float(np.nansum(rr[g])); summ[tag + "_fail"] = float(np.nansum(rr[~g]))
            summ[tag + "_try03"] = float(np.nansum([r[mode]["res_try03"][xi] for r in ent])); summ[tag + "_rev005"] = float(np.nansum([r[mode]["res_rev005"][xi] for r in ent]))
        summ[f"{mode}_fills"] = float(sum(r[mode]["fill"] for r in ent)); summ[f"{mode}_tries"] = float(sum(r[mode]["tries"] for r in ent))
        summ[f"{mode}_unresolved"] = int(sum(1 for r in ent if r[mode]["unresolved"])); summ[f"{mode}_nomig"] = int(sum(1 for r in ent if r[mode]["nomig"]))
    summ["n_grad"] = int(sum(1 for r in ent if r["grad"]))
    # ARM-gate row (pre-send, -20 % stop column only; FROZEN.md 10-29 addendum)
    ea = [r for r in rows_out if r.get("entered_arm")]
    rr = np.array([r["pre_arm"]["res"][0] for r in ea]) if ea else np.zeros(0); g = np.array([r["grad"] for r in ea], bool) if ea else np.zeros(0, bool)
    summ["n_selected_arm"] = n_sel_arm; summ["n_grad_arm"] = int(g.sum())
    summ["pre_arm_stop"] = float(np.nansum(rr)); summ["pre_arm_stop_grad"] = float(np.nansum(rr[g])); summ["pre_arm_stop_fail"] = float(np.nansum(rr[~g]))
    summ["pre_arm_stop_try03"] = float(np.nansum([r["pre_arm"]["res_try03"][0] for r in ea]))
    summ["pre_arm_fills"] = float(sum(r["pre_arm"]["fill"] for r in ea)); summ["pre_arm_tries"] = float(sum(r["pre_arm"]["tries"] for r in ea))
    summ["pre_arm_unresolved"] = int(sum(1 for r in ea if r["pre_arm"]["unresolved"]))
    # ---- store update (causal history for the next windows)
    if not a.no_store_update:
        keep = {m for m, v in T.M["mx"].items() if v >= 78e9 and m in T.cr and not T.cr[m].get("mayhem")}
        new = mplib.trips_from_tape(T, keep); n1 = ws.upsert(new); ws.save()
        n2 = cs.upsert_tape(T); cs.save()
        print(f"stores: +{n1} trips (now {len(ws.W)}, {len(new)} upserted from {len(keep)} mints), +{n2} creates (now {len(cs.Cr)}), {time.time() - t0:.0f}s", flush=True)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "a") as f: f.write(json.dumps(summ) + "\n")
    with open(a.trades, "a") as f:
        for r in rows_out: f.write(json.dumps(r) + "\n")
    print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in summ.items()}), flush=True)
    if not a.no_store_update:
        st = json.load(open(a.state)) if os.path.exists(a.state) else {}
        st["last_end"] = a.end; st["last_scored_at"] = int(time.time())
        tmp = a.state + ".tmp"; json.dump(st, open(tmp, "w")); os.replace(tmp, a.state)
    return 0

if __name__ == "__main__":
    sys.exit(main())
