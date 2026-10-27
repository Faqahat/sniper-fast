#!/usr/bin/env python3
# M2 live-shadow evaluation (agent 10-25; ops/strategies/dipdetect/PORT.md). Read-only on the study data; writes only to --work.
# After a live run with --dip-m2 (shadow or gate), for the run's hours:
#  (a) PARITY: rebuilds the study's features and M2 scores OFFLINE from the raw 24/7 recording with the study's own code, run
#      unchanged into a work folder (ops/select/a_extract.py -> patterns/p1_build.py -> dipdetect/dd1_build.py; = how R4 was
#      built, dd0_extract_r4.py / dd0_build_r4.py), and compares them with every live "dump" record's m2 / m2_feats / m2_pick
#      (exact equality expected: features are float32, the score bit-identical);
#  (b) REPLAY: Stage A (M2 >= min inside the study envelope, exit c4) with the OFFLINE scores and with the engine's own live
#      picks, vs IMIT1 top4 (the live IMIT1 scores) with exits c4 and c6_tpnone_sl10, dd_lib.sim at 35 / 50 / 75 ms, FRA + AMS
#      near leaders (both servers, one position each, all costs) -- results per landing-latency row.
# usage: python3 dd20_shadow_eval.py --jsonl dip_rN.jsonl [dip_ams_rN.jsonl ...] --run /home/moiz/sniper-data/collect/run_<date>_<time>
#          [--from "MM-DD HH:MM" --to "MM-DD HH:MM"]  (PKT; default = the span of the dump records)
#          [--work DIR] [--procs 4] [--schedule FILE ...] (leader schedules beyond epoch 1066, schedule_cur.json format)
#          [--bundle FILE] [--fill-m2-from-offline] (TEST ONLY: records without m2 fields get the offline values: plumbing check)
#          [--check-study R4] (self-check: offline rows vs the study's dd1_<day>.npz rows of the same window)
import sys, os, json, time, glob, pickle, argparse, calendar, hashlib, zlib
import numpy as np
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dd_lib as L
import dd_gbdt as GT
PATTERNS = "/home/moiz/sniper/ops/strategies/patterns"; SELECT = "/home/moiz/sniper/ops/select"
COLLECT = "/home/moiz/sniper-data/collect"
TAG = "SH"
E4 = L.EXI["c4_tpnone_slnone"]; E6 = L.EXI["c6_tpnone_sl10"]
LOG = []
def say(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); LOG.append(s)
def pk(s): return calendar.timegm(time.strptime("2026-" + s, "%Y-%m-%d %H:%M")) - 18000
def pkt(t): return time.strftime("%m-%d %H:%M:%S", time.gmtime(t + 5 * 3600))

def load_live(files):
    dumps, starts = [], []
    for f in files:
        srv = "AMS" if "ams" in os.path.basename(f) else "FRA"
        for l in open(f):
            if '"ev":"dump"' not in l and '"ev":"run_start"' not in l: continue
            try: o = json.loads(l)
            except Exception: continue
            o["srv"] = srv
            (starts if o["ev"] == "run_start" else dumps).append(o)
    return dumps, starts

def bundle_scores(bpath, X):
    """the engine's bundle (strings -> exact floats), scored the study's way (dd_gbdt bins, F0 + lr x leaf, mean of the seeds)"""
    B = json.load(open(bpath))
    E = [np.array([float(x) for x in e], np.float64) for e in B["edges"]]
    Bm = GT.binize(X, E); rows = np.arange(len(X)); ps = []
    for s in B["seeds"]:
        f = np.array(s["f"]); b = np.array(s["b"]); l = np.array(s["l"]); r = np.array(s["r"]); w = np.array([float(x) for x in s["w"]])
        out = np.full(len(X), float(s["F0"])); lr = float(s["lr"])
        for root in s["roots"]:
            idx = np.full(len(X), root)
            for _ in range(8):
                leaf = f[idx] < 0
                if leaf.all(): break
                fi = np.where(leaf, 0, f[idx]); go = Bm[rows, fi] <= b[idx]
                idx = np.where(leaf, idx, np.where(go, l[idx], r[idx]))
            out += lr * w[idx]
        ps.append(out)
    p = ps[0]
    for q in ps[1:]: p = p + q
    return p / len(ps), B

def load_dd1(path, t0, t1):
    """dd_lib.load for a dd1 file outside the study folder, windowed on [t0, t1)"""
    z = np.load(path); d = {k: z[k] for k in z.files}
    bt = d["bt"].astype(np.int64); ok = bt > 0
    if (~ok).any() and ok.sum() > 2:
        a = np.polyfit(d["s"][ok].astype(float), bt[ok].astype(float), 1); bt = np.where(ok, bt, np.round(np.polyval(a, d["s"].astype(float))).astype(np.int64))
    d["t"] = bt
    m = (d["t"] >= t0) & (d["t"] < t1)
    d = {k: v[m] for k, v in d.items()}
    d["Xall"] = np.concatenate([d["F"], d["X"], d["f1"][:, None]], 1).astype(np.float32)
    X = d["Xall"]; f = lambda k: X[:, L.FNI[k]]
    d["env"] = (f("age_s") <= 343.67) & (f("drop_pct") >= 4.65) & (f("since_buy_s") <= 3.869) & (f("sol") >= 1.08)
    d["hour"] = ((d["t"] + 5 * 3600) // 3600) % 24
    d["order"] = np.argsort(d["arr"], kind="stable")
    return d

def near_from_schedules(d, files):
    """near_f / near_a recomputed from leader schedules (schedule_cur.json format) where dd1_build's map had no leader"""
    fra = {l.strip() for l in open("/home/moiz/sniper/ops/region/near_leaders_fra.txt") if l.strip()}
    ams = {l.strip() for l in open("/home/moiz/sniper/ops/region/near_leaders_ams.txt") if l.strip()}
    known = d["lead"] >= 0; n_new = 0
    for fp in files:
        sc = json.load(open(fp)); st = sc["start"]; sl = sc["slot_leader"]; ids = sc["ids"]
        for r in np.flatnonzero(~known).tolist():
            o = int(d["s"][r]) - st
            if 0 <= o < len(sl):
                u = ids[sl[o]]; d["near_f"][r] = u in fra; d["near_a"][r] = u in ams; known[r] = True; n_new += 1
    return known, n_new

def stage_extract(run, files, pha, procs):
    argv = sys.argv; sys.argv = [argv[0], run, pha]
    sys.path.insert(0, SELECT); import a_extract as A
    sys.argv = argv
    A.RUN = run; A.OUT = pha
    for b in range(A.NB): os.makedirs(os.path.join(pha, f"b{b:03d}"), exist_ok=True)
    tot = 0
    with Pool(procs) as p:
        for k, n in enumerate(p.imap_unordered(A.work, files), 1):
            tot += n
            if k % 10 == 0 or k == len(files): say(f"    phase A: {k}/{len(files)} chunks, {tot} txs")

def stage_days(run, pha, work, procs):
    sys.path.insert(0, PATTERNS); import p1_build as B
    B.TMP = f"{work}/tmp"; os.makedirs(B.TMP, exist_ok=True)
    B.D = os.path.dirname(run); B.RUNS[TAG] = (os.path.basename(run), [pha])
    first = {}
    with Pool(procs) as p:
        for _, fs in p.imap_unordered(B.stage_a, [(TAG, b) for b in range(256)]):
            for u, k in fs.items():
                if u not in first or k < first[u]: first[u] = k
    pickle.dump(first, open(f"{B.TMP}/{TAG}_first.pkl", "wb"), protocol=4)
    tot = 0
    with Pool(procs, initializer=B.init_b, initargs=(TAG,)) as p:
        for _, b, n in p.imap_unordered(B.stage_b, [(TAG, b) for b in range(256)]): tot += n
    po = B.PO; B.PO = work
    nt = B.concat(TAG); B.PO = po
    say(f"    day arrays: {tot} trades, {nt} tokens")

def stage_dd1(run, work, live_files, procs):
    import dd1_build as DB
    DB.DAYS[TAG] = work; DB.RUNDIR[TAG] = os.path.basename(run); DB.IMIT2[TAG] = []; DB.OUT = work
    os.makedirs(f"{work}/live", exist_ok=True)
    for f in live_files:                                  # the live IMIT1 scores (dd1_build.imit_scores reads OUT/live/dip_*.jsonl)
        dst = f"{work}/live/{os.path.basename(f) if os.path.basename(f).startswith('dip_') else 'dip_' + os.path.basename(f)}"
        if not os.path.exists(dst): os.symlink(os.path.abspath(f), dst)
    DB.main(TAG, procs)

def parity(srv, pm, d, cols, P, MIN, fn, res):
    """one server's live records vs the offline rows: features (exact), scores, picks"""
    F = np.array([o["m2_feats"] for o, _ in pm], np.float64); X = d["Xall"][[r for _, r in pm]][:, cols].astype(np.float64)
    bad = F != X; S = np.array([o["m2"] for o, _ in pm]); So = P[[r for _, r in pm]]
    rows_bad = bad.any(1)
    say(f"  features: {len(pm)} scored records, {int(rows_bad.sum())} with any feature different ({100 * rows_bad.mean():.2f}%)")
    for j in np.argsort(-bad.sum(0)):
        if bad[:, j].sum() == 0: break
        dj = np.abs(F[:, j] - X[:, j])[bad[:, j]]
        say(f"    {fn[j]:16s} differs on {int(bad[:, j].sum()):5d} ({100 * bad[:, j].mean():.2f}%), |diff| median {np.median(dj):.4g} max {dj.max():.4g}")
    gaps = np.array([o.get("m2_gaps", 0) > 0 for o, _ in pm])
    if gaps.any(): say(f"    records on tokens with feed gaps (m2_gaps > 0): {int(gaps.sum())}, of them with a feature difference {int((rows_bad & gaps).sum())}")
    ex = [i for i in np.flatnonzero(rows_bad)[:8]]
    for i in ex:
        o, r = pm[i]
        say(f"    e.g. {o['mint']} slot {o['slot']} idx {o['idx']}: " + ", ".join(f"{fn[j]} live {F[i, j]:.6g} offline {X[i, j]:.6g}" for j in np.flatnonzero(bad[i])))
    ds = np.abs(S - So)
    corr = float(np.corrcoef(S, So)[0, 1]) if len(S) > 2 and S.std() > 0 and So.std() > 0 else float("nan")
    lp = np.array([bool(o.get("m2_pick")) for o, _ in pm]); op = np.array([bool(d["env"][r]) and So[i] >= MIN for i, (o, r) in enumerate(pm)])
    say(f"  scores: |live - offline| max {ds.max():.3g}, mean {ds.mean():.3g}, exact {int((ds == 0).sum())}/{len(ds)}, corr {corr:.6f}")
    say(f"  picks (M2 >= {MIN}): live {int(lp.sum())}, offline (study envelope) {int(op.sum())}, both {int((lp & op).sum())}, "
        f"agreement {(lp & op).sum() / max(1, (lp | op).sum()):.3f} (both / union)")
    res["servers"][srv] = dict(n=len(pm), feat_rows_bad=int(rows_bad.sum()), score_max_diff=float(ds.max()), score_corr=corr, picks_live=int(lp.sum()), picks_off=int(op.sum()), picks_both=int((lp & op).sum()))

def sim_cells(d, sel, ex):
    return [L.sim(d, sel, li, ex) for li in range(3)]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", nargs="+", required=True); ap.add_argument("--run", required=True)
    ap.add_argument("--from", dest="t_from"); ap.add_argument("--to", dest="t_to")
    ap.add_argument("--work"); ap.add_argument("--procs", type=int, default=4); ap.add_argument("--schedule", nargs="*", default=[])
    ap.add_argument("--bundle", default=f"{L.OUT}/m2_v3_reg4_top25.json"); ap.add_argument("--fill-m2-from-offline", action="store_true")
    ap.add_argument("--check-study"); ap.add_argument("--keep-phasea", action="store_true")
    a = ap.parse_args()
    T0 = time.time()
    run = a.run.rstrip("/")
    if os.path.dirname(run) != COLLECT: sys.exit(f"--run must be a recording folder under {COLLECT} (dd1_build reads its launches.jsonl there)")
    dumps, starts = load_live(a.jsonl)
    if not dumps: sys.exit("no dump records in the --jsonl files")
    t_from = pk(a.t_from) if a.t_from else int(min(o["t"] for o in dumps) // 1e9)
    t_to = pk(a.t_to) if a.t_to else int(max(o["t"] for o in dumps) // 1e9) + 1
    work = a.work or f"{L.OUT}/shadow/{os.path.basename(run)}_{time.strftime('%m%d_%H%M', time.gmtime(t_from + 5 * 3600))}"
    os.makedirs(work, exist_ok=True)
    say(f"M2 shadow evaluation | window {pkt(t_from)} -> {pkt(t_to)} PKT ({(t_to - t_from) / 3600:.2f} h) | records {', '.join(a.jsonl)} | recording {run} | work {work}")
    m2cfg = [s["m2"] for s in starts if s.get("m2")]
    bsha = hashlib.sha256(open(a.bundle, "rb").read()).hexdigest()
    min_live = None
    for c in m2cfg:
        say(f"  live run M2 config: {c}")
        if c.get("sha256") and c["sha256"] != bsha: say(f"  WARNING: the live bundle sha256 {c['sha256']} != {a.bundle} ({bsha})")
        min_live = c.get("min", min_live)
    # ---- (0) the study pipeline on the recording (cached in the work folder)
    pha = f"{work}/phaseA"; dd1p = f"{work}/dd1_{TAG}.npz"
    if not os.path.exists(dd1p):
        files = []
        for f in sorted(glob.glob(f"{run}/txs/txs_*.jsonl.gz")):
            ts = int(os.path.basename(f).split("_")[1].split(".")[0])
            if t_from - 16 * 60 <= ts <= t_to + 11 * 60: files.append(f)
        if not files: sys.exit("no recording chunks cover the window")
        say(f"  recording chunks {len(files)}: {os.path.basename(files[0])} .. {os.path.basename(files[-1])}")
        if not os.path.exists(f"{work}/day_{TAG}.npz"):
            if not os.path.exists(f"{pha}/.done"):
                stage_extract(run, files, pha, a.procs); open(f"{pha}/.done", "w").write("ok")
            stage_days(run, pha, work, a.procs)
        stage_dd1(run, work, a.jsonl, a.procs)
        if not a.keep_phasea:
            import shutil; shutil.rmtree(pha, ignore_errors=True); shutil.rmtree(f"{work}/tmp", ignore_errors=True)
        say(f"  study pipeline done in {time.time() - T0:.0f} s")
    d = load_dd1(dd1p, t_from, t_to)
    day = np.load(f"{work}/day_{TAG}.npz"); meta = json.load(open(f"{work}/day_{TAG}_meta.json"))["meta"]
    I = day["i"]; mint = np.array([meta[t]["m"] for t in d["tok"]]); txi = I[d["k"]]
    if a.schedule:
        known, n_new = near_from_schedules(d, a.schedule); say(f"  leaders: {n_new} rows filled from --schedule")
    else: known = d["lead"] >= 0
    if (~known).mean() > 0.2:
        say(f"  WARNING: the slot leader is unknown for {100 * (~known).mean():.0f}% of the dumps (leader schedule not covered: pass --schedule FILE, "
            f"e.g. from ops/agents/competitors2/fetch_schedule.py); those rows count as NOT near for both servers")
    # offline M2 scores (the bundle the engine loads)
    B0 = json.load(open(a.bundle)); cols = [L.FNI[f] for f in B0["fn"]]
    P, B = bundle_scores(a.bundle, d["Xall"][:, cols])
    MIN = float(min_live) if min_live is not None else float(B["thr_default"])
    say(f"  offline: {len(d['k'])} study dump rows in the window ({int(d['env'].sum())} in the envelope), M2 min {MIN}")
    # ---- (a) parity: live dump records <-> offline rows by (mint, slot, tx index), closest sell size
    key = {}
    for r in range(len(d["k"])): key.setdefault((mint[r], int(d["s"][r]), int(txi[r])), []).append(r)
    inwin = [o for o in dumps if t_from * 1e9 <= o["t"] < t_to * 1e9]
    live_m2 = [o for o in inwin if "m2" in o]
    say(f"\n(a) PARITY: {len(inwin)} live dump records in the window ({sum(1 for o in inwin if o.get('m2_extra'))} M2 extra dumps), "
        f"{len(live_m2)} with M2 fields ({sum(1 for o in live_m2 if o.get('m2') is None)} not scored: "
        f"{dict(sorted({w: sum(1 for o in live_m2 if o.get('m2_skip') == w) for w in {o.get('m2_skip') for o in live_m2 if o.get('m2_skip')}}.items()))})")
    filled = 0
    if a.fill_m2_from_offline and not live_m2:
        say("  TEST MODE (--fill-m2-from-offline): the records have no M2 fields; the matched offline values are filled in (plumbing check only)")
    match = []; unmatched = []
    for o in inwin:
        rr = key.get((o["mint"], int(o["slot"]), int(o["idx"])))
        if not rr: unmatched.append(o); continue
        r = min(rr, key=lambda x: abs(float(d["Xall"][x, L.FNI["sol"]]) - o["sell"]))
        if a.fill_m2_from_offline and "m2" not in o:
            o = dict(o); o["m2"] = float(P[r]); o["m2_feats"] = [float(v) for v in d["Xall"][r, cols]]; o["m2_pick"] = bool(o.get("launch_ok", True) and P[r] >= MIN); filled += 1
        match.append((o, r))
    say(f"  matched to an offline row {len(match)}, unmatched {len(unmatched)}" + (f" (filled {filled})" if filled else ""))
    if unmatched:
        known_tok = set(mint.tolist())
        nt = sum(1 for o in unmatched if o["mint"] not in known_tok)
        say(f"    unmatched: {nt} on tokens with no study row in the window (non-standard launch, or created before the recording window), "
            f"{len(unmatched) - nt} on known tokens (no >= 2% candidate row at that trade)")
    res = {"window": [t_from, t_to], "n_live": len(inwin), "n_m2": len(live_m2), "matched": len(match), "unmatched": len(unmatched), "servers": {}}
    for srv in sorted({o["srv"] for o, _ in match}):
        pm = [(o, r) for o, r in match if o.get("m2") is not None and o["srv"] == srv]
        if pm:
            say(f"  --- {srv}: {len(pm)} scored records")
            parity(srv, pm, d, cols, P, MIN, B0["fn"], res)
    # offline in-envelope dumps the engine did not record (it follows only tokens created after its start; the IMIT1 book needs
    # the dev's create-tx buy; feed gaps)
    seen = {r for _, r in match}
    t_start = min((s["t"] for s in starts), default=0) / 1e9
    miss = [r for r in np.flatnonzero(d["env"]).tolist() if r not in seen]
    if miss:
        old = sum(1 for r in miss if meta[d["tok"][r]].get("cbt") and meta[d["tok"][r]]["cbt"] < t_start)
        say(f"  offline in-envelope dumps with no live record: {len(miss)} of {int(d['env'].sum())} ({old} on tokens created before the engine started)")
    # ---- (b) replay
    h = (t_to - t_from) / 3600
    say(f"\n(b) REPLAY of the window ({h:.2f} h; dd_lib.sim: FRA + AMS near leaders, one position each, 0.55 SOL, all costs; SOL / fills / attempts)")
    sel_off = d["env"] & (P >= MIN)
    lpick = np.zeros(len(d["k"]), bool)
    for o, r in match:
        if o.get("m2_pick"): lpick[r] = True
    base = np.isfinite(d["f1"]) & (d["f1"] >= L.THR["top4"])
    rows = [("Stage A, offline M2 scores, c4", sel_off, E4), ("Stage A, the engine's live M2 picks, c4", lpick & d["env"], E4),
            ("IMIT1 top4 (live scores), c4", base, E4), ("IMIT1 top4 (live scores), c6_tpnone_sl10", base, E6)]
    rep = {}
    for nm, sel, ex in rows:
        cs = sim_cells(d, sel, ex)
        rep[nm] = [[c["pnl"], c["fill"], c["att"], c["per_fill"]] for c in cs]
        say(f"  {nm:42s} " + " | ".join(f"{lat} ms {c['pnl']:+6.2f} ({c['pnl'] / max(h, 1e-9):+5.2f}/h) {c['fill']}/{c['att']}" for lat, c in zip((35, 50, 75), cs)))
    res["replay"] = rep
    # ---- self-check against the study's own rows (when the window lies inside a study day)
    if a.check_study:
        ddir = L.OUT if a.check_study == "R4" else "/home/moiz/sniper-data/strategies/patterns"
        zs = np.load(f"{L.OUT}/dd1_{a.check_study}.npz"); ms = json.load(open(f"{ddir}/day_{a.check_study}_meta.json"))["meta"]
        dzs = np.load(f"{ddir}/day_{a.check_study}.npz")
        Xs = np.concatenate([zs["F"], zs["X"], zs["f1"][:, None]], 1).astype(np.float32)
        ks = {}
        Is = dzs["i"]; ztok = zs["tok"]; zsl = zs["s"]; zk = zs["k"]
        for r in range(len(zk)): ks[(ms[ztok[r]]["m"], int(zsl[r]), int(Is[zk[r]]), float(Xs[r, L.FNI["sol"]]))] = r
        envr = np.flatnonzero(d["env"]).tolist(); same = diff = absent = 0; ex = []
        for r in envr:
            q = ks.get((mint[r], int(d["s"][r]), int(txi[r]), float(d["Xall"][r, L.FNI["sol"]])))
            if q is None: absent += 1; continue
            if np.array_equal(Xs[q, cols], d["Xall"][r, cols]): same += 1
            else:
                diff += 1
                if len(ex) < 5: ex.append((mint[r], [B0["fn"][j] for j in np.flatnonzero(Xs[q, cols] != d["Xall"][r, cols])]))
        say(f"\nSELF-CHECK vs the study's dd1_{a.check_study}.npz (in-envelope rows of the window): identical 25 features {same}, different {diff}, "
            f"not in the study file {absent}" + (f"; e.g. {ex}" if ex else ""))
        res["self_check"] = dict(same=same, diff=diff, absent=absent)
    say(f"\ndone in {time.time() - T0:.0f} s; report {work}/dd20_report.txt")
    open(f"{work}/dd20_report.txt", "w").write("\n".join(LOG) + "\n")
    json.dump(res, open(f"{work}/dd20_report.json", "w"), default=float)
