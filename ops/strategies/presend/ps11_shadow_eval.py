#!/usr/bin/env python3
# PRE-SEND SHADOW evaluation (agent 10-25 PKT; ops/strategies/presend/SHADOW.md). Read-only on the study data and the recording;
# writes only to --work. After a run with --presend-shadow (engine dip12_presend), for the run's hours:
#  (0) the study's tape of those hours, built OFFLINE from the raw 24/7 recording with the study's own code, unchanged
#      (ops/select/a_extract.py -> patterns/p1_build.py day arrays, as dipdetect/dd0_build_r4.py and dd20_shadow_eval.py do), and
#      the study's T2 detection on it: presend/ps4_replay.py `work` (windows, first fill per queue row, paths) + ps5_lib.run's
#      per-token arming, config "T2|c" (htype 3, holding >= 5%, W 10 slots, y 0.12 trailing, 0.55 SOL, exit c2_tp10_sl20);
#  (a) PARITY: every live presend_arm / _fill / _exit / _disarm record vs that offline detection (exact equality expected:
#      trigger, per-row armed flag, crossing trade, last trade ahead, landing / fill time, entry slot, exit slot, gross P&L as float32,
#      armed slots); live-only and offline-only windows are explained (no history = token created before the engine started; the
#      study's tape rules: < 5 trades on the token over the recording, or the tape's last 300 slots);
#  (b) REPLAY of the LIVE windows (each server's presend_arm records, mapped to the tape) with ps4 / ps5 mechanics (ps5_lib.run
#      unchanged): SOL per queue row (a / b / c = the live rows; r20 / r4 / r1 = k attempts per slot, landing drawn offline) and
#      cost row (cheap-k = the study's main row, cheap-k1 = 1 charged attempt per slot, +selltip, now-k = today's fees), with the
#      study's 2-server engine and with this server alone; next to it the same from the live records' own numbers (live-reported);
#  (c) per server (each --jsonl file is one server: "ams" in the file name = AMS, else FRA) and both servers pooled (2 servers).
# Pre-sent orders need no near leader: every window counts on every server (the study). The reactive bot's overlap is read from
# the fill records' "imit" marks (the IMIT1 / M2 decision on the crossing trade).
# usage: python3 ps11_shadow_eval.py --jsonl dip_rN.jsonl [dip_ams_rN.jsonl] --run /home/moiz/sniper-data/collect/run_<date>_<time>
#          [--from "MM-DD HH:MM" --to "MM-DD HH:MM"] (PKT; default = the live records' span) [--work DIR] [--procs 4]
#        TESTS: --day R4 (use the study's own day array instead of building one from --run)
#               --make-synthetic OUT.jsonl (write live-format records from the OFFLINE detection, then exit)
import sys, os, json, time, glob, pickle, argparse, calendar, collections, zlib
import numpy as np
from multiprocessing import Pool, get_context
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ps_common as C
import ps4_replay as P4
import ps5_lib as E
PATTERNS = "/home/moiz/sniper/ops/strategies/patterns"; SELECT = "/home/moiz/sniper/ops/select"
COLLECT = "/home/moiz/sniper-data/collect"
TAG = "PS"
CFG = dict(W=10, y=0.12, size=0.55, ex="c2_tp10_sl20", htype=3, hpct_min=5.0)
LIVE_ROWS = ("a", "b", "c"); ALL_ROWS = ("a", "b", "c", "r20", "r4", "r1")
DFIX = {"a": 0.0, "b": 5.0, "c": 10.0}
SMS = 212.0; MARGIN = 300.0
LOG = []
def say(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); LOG.append(s)
def pk(s): return calendar.timegm(time.strptime("2026-" + s, "%Y-%m-%d %H:%M")) - 18000
def pkt(t): return time.strftime("%m-%d %H:%M:%S", time.gmtime(t + 5 * 3600))

# ---------------------------------------------------------------------------------------------------------------- tape
def stage_extract(run, files, pha, procs):
    """phase A of the recording chunks (ops/select/a_extract.py `work`, unchanged; as dd20_shadow_eval.py)"""
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
    """the day arrays of the study (patterns/p1_build.py stage_a / stage_b / concat, unchanged; as dd20_shadow_eval.py)"""
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

def load_tape(npz, meta):
    """ps_common.load for a day array outside the study folders"""
    z = np.load(npz); M = json.load(open(meta))
    d = {k: z[k] for k in C.COLS}
    d["meta"] = M["meta"]; d["feats"] = M["feats"]; d["FI"] = {k: i for i, k in enumerate(M["feats"])}
    nt = len(M["meta"]); cnt = np.bincount(d["tok"], minlength=nt); off = np.concatenate([[0], np.cumsum(cnt)[:-1]]).astype(np.int64)
    d["off"] = off; d["cnt"] = cnt; d["day"] = TAG
    b = d["buy"].astype(bool); V = d["vsol"]; T = d["vtok"]
    Vpre = np.where(b, V - d["sol"], V + d["sol"]); Tpre = np.where(b, T + d["tokn"], T - d["tokn"])
    d["p"] = V / T; d["ppre"] = Vpre / np.maximum(Tpre, 1.0); d["move"] = (d["p"] / d["ppre"] - 1) * 100
    bt = d["bt"].astype(np.int64); ok = bt > 0
    if (~ok).any() and ok.sum() > 100:
        a = np.polyfit(d["s"][ok].astype(float), bt[ok].astype(float), 1)
        bt = np.where(ok, bt, np.round(np.polyval(a, d["s"].astype(float))).astype(np.int64))
    d["t"] = bt
    return d

# ---------------------------------------------------------------------------------------------------------------- offline T2
def offline(d, procs):
    """ps4_replay.work over every token of the tape (the study's code: all families; T2 is selected after), as ps4_replay.main
    assembles it, then the arrays ps5_lib.run reads (ps5_lib.load without the study-day window)"""
    P4.G["d"] = d; P4.G["s_end"] = int(d["s"].max())
    try: P4.G["crehist"] = json.load(open(f"{C.OUT}/crehist.json"))
    except Exception: P4.G["crehist"] = {}
    nt = len(d["meta"]); toks = list(range(nt)); chunks = [toks[i::procs * 6] for i in range(procs * 6)]
    W = []; F = []; P = []
    with get_context("fork").Pool(procs) as pool:
        for R in pool.imap_unordered(P4.work, chunks):
            w0 = len(W); p0 = len(P)
            W += R["W"]; P += R["P"]
            F += [(a + w0, b, c, e, f, g, h + p0) for (a, b, c, e, f, g, h) in R["F"]]
    D = dict(w_fam=np.array([x[0] for x in W], np.int8), w_tok=np.array([x[1] for x in W], np.int32), w_j=np.array([x[2] for x in W], np.int64),
             w_start=np.array([x[3] for x in W]), w_end=np.array([x[4] for x in W]), w_f=np.array([x[5] for x in W], np.float32))
    Fa = np.array(F, np.float64) if F else np.zeros((0, 7))
    fx = Fa[:, 3].astype(np.int64)
    D.update(f_w=Fa[:, 0].astype(np.int32), f_y=Fa[:, 1].astype(np.int8), f_d=Fa[:, 2].astype(np.int8), f_x=fx.astype(np.int32), f_m=Fa[:, 4].astype(np.int32),
             f_D=(Fa[:, 5] - d["arr"][fx]).astype(np.float32), f_pid=Fa[:, 6].astype(np.int32),
             p_m=np.array([x[0] for x in P], np.int64), p_sin=np.array([x[1] for x in P], np.int64), p_pnl=np.array([x[2] for x in P], np.float32),
             p_off=np.array([x[3] for x in P], np.int8), p_min=np.array([x[4] for x in P], np.float32))
    D["arr"] = d["arr"]; D["s_tape"] = d["s"]; D["t_tape"] = d["t"]; D["w_t"] = d["t"][D["w_j"]]
    D["f_time"] = d["arr"][D["f_x"]] + D["f_D"]
    nW = len(D["w_fam"]); D["nW"] = nW
    FR = np.full((len(E.YS), len(E.DMOD), nW), -1, np.int64)
    if len(D["f_w"]): FR[D["f_y"], D["f_d"], D["f_w"]] = np.arange(len(D["f_w"]))
    D["FR"] = FR
    f = D["w_f"]
    D["t2"] = (D["w_fam"] == 2) & (f[:, E.FI["htype"]] == CFG["htype"]) & (f[:, E.FI["hpct"]] >= CFG["hpct_min"])
    return D

def arming(D, sel, dm):
    """ps5_lib.run's per-token arming (before its server engine), per window of `sel`: armed, fill row, valid, fill time, sell
    time, aend, slots charged"""
    yi = E.YS.index(CFG["y"]); di = E.DMOD.index(dm); si = E.SIZES.index(CFG["size"]); e = E.EXI[CFG["ex"]]
    st = D["w_start"][sel]; en = np.minimum(D["w_end"][sel], st + CFG["W"] * SMS); tok = D["w_tok"][sel]
    fr = D["FR"][yi, di, sel]; has = fr >= 0
    ft = np.where(has, D["f_time"][np.maximum(fr, 0)], np.inf); valid = has & (ft < en)
    pid = np.where(has, D["f_pid"][np.maximum(fr, 0)], -1)
    sin = np.where(has, D["p_sin"][np.maximum(pid, 0)], 0); off = np.where(has, D["p_off"][np.maximum(pid, 0), si, e], 0).astype(np.int64)
    pn = np.where(has, D["p_pnl"][np.maximum(pid, 0), si, e], 0.0); xt = (sin + off) * SMS + 75.0
    o = np.lexsort((st, tok)); armed = np.zeros(len(sel), bool); aend = np.zeros(len(sel))
    last_tok = -1; free_at = -np.inf
    for q in o.tolist():
        t = tok[q]
        if t != last_tok: last_tok = t; free_at = -np.inf
        if st[q] < free_at: continue
        armed[q] = True
        if valid[q]: aend[q] = ft[q]; free_at = xt[q] + MARGIN
        else: aend[q] = en[q]; free_at = en[q]
    slots = np.where(armed, np.maximum(np.ceil(np.maximum(aend - st, 0.0) / SMS), 1.0), 0.0)
    return dict(st=st, en=en, armed=armed, has=has, valid=valid, ft=ft, fr=fr, pid=pid, sin=sin, off=off, pn=pn, xt=xt, aend=aend, slots=slots)

# ---------------------------------------------------------------------------------------------------------------- live
def load_live(files):
    """per file (server): run_start / run_end and the presend records grouped by window id"""
    out = {}
    for f in files:
        srv = "AMS" if "ams" in os.path.basename(f).lower() else "FRA"
        if srv in out: srv = f"{srv}:{os.path.basename(f)}"
        L = dict(file=f, starts=[], ends=[], wins=collections.defaultdict(dict), skips=[], other=0)
        for l in open(f):
            if '"presend' not in l and '"run_start"' not in l and '"run_end"' not in l: continue
            try: o = json.loads(l)
            except Exception: continue
            ev = o.get("ev")
            if ev == "run_start": L["starts"].append(o)
            elif ev == "run_end": L["ends"].append(o)
            elif ev == "presend_skip": L["skips"].append(o)
            elif ev in ("presend_arm", "presend_disarm"): L["wins"][o["w"]][ev[8:]] = o
            elif ev in ("presend_fill", "presend_exit"): L["wins"][o["w"]].setdefault(ev[8:], {})[o["row"]] = o
            else: L["other"] += 1
        out[srv] = L
    return out

def tape_index(d):
    """(mint, slot, tx index, buy, tokens) -> tape rows (one engine trade = one tape row; same-key repeats in order)"""
    K = collections.defaultdict(list)
    tok = d["tok"]; s = d["s"]; i = d["i"]; b = d["buy"]; tk = d["tokn"]; M = d["meta"]
    for r in range(len(tok)):
        K[(M[tok[r]]["m"], int(s[r]), int(i[r]), int(b[r]), int(tk[r]))].append(r)
    return K

def find_row(K, mint, x, used=None):
    rr = K.get((mint, int(x["slot"]), int(x["idx"]), 1 if x.get("buy", True) else 0, int(x["tok"])), [])
    if not rr: return None
    if used is None: return rr[0]
    for r in rr:
        if r not in used: used.add(r); return r
    return rr[0]

# ---------------------------------------------------------------------------------------------------------------- synthetic
def make_synthetic(D, d, sel_ids, path):
    """live-format records (what the engine writes) from the OFFLINE detection of the windows `sel_ids`: plumbing test"""
    A = {r: arming(D, sel_ids, r) for r in LIVE_ROWS}
    M = d["meta"]; n = 0
    with open(path, "w") as f:
        f.write(json.dumps({"ev": "run_start", "t": 0, "synthetic": True, "presend": {"whale_pct": CFG["hpct_min"]}}) + "\n")
        for q, w in enumerate(sel_ids.tolist()):
            j = int(D["w_j"][w]); t = int(d["tok"][j]); mint = M[t]["m"]
            tr = lambda r: {"slot": int(d["s"][r]), "idx": int(d["i"][r]), "j": 0, "buy": bool(d["buy"][r]), "sol": int(d["sol"][r]), "tok": int(d["tokn"][r]), "sig": "", "t": 0,
                            "a": float(d["arr"][r])}
            rows = {r: ("armed" if A[r]["armed"][q] else "blocked") for r in LIVE_ROWS}
            f.write(json.dumps({"ev": "presend_arm", "w": q + 1, "mint": mint, "wallet": "", "pct": float(D["w_f"][w, E.FI["hpct"]]), "sig": "", **{k: v for k, v in tr(j).items() if k != "sig"},
                                "st": float(D["w_start"][w]), "en0": float(D["w_start"][w]) + CFG["W"] * SMS, "rows": rows}) + "\n"); n += 1
            for r in LIVE_ROWS:
                X = A[r]
                if not (X["armed"][q] and X["valid"][q]): continue
                fr = int(X["fr"][q]); x = int(D["f_x"][fr]); m = int(D["f_m"][fr])
                f.write(json.dumps({"ev": "presend_fill", "w": q + 1, "mint": mint, "row": r, "x": tr(x), "m": tr(m), "a_land": float(d["arr"][x]) + DFIX[r], "ft": float(X["ft"][q]),
                                    "s_in": int(X["sin"][q]), "imit": {"dump": False, "env": False, "pick": False, "fired": False, "m2": False}}) + "\n")
                f.write(json.dumps({"ev": "presend_exit", "w": q + 1, "mint": mint, "row": r, "s_in": int(X["sin"][q]), "hold_slots": int(X["off"][q]), "pnl": float(X["pn"][q]),
                                    "xt": float(X["xt"][q])}) + "\n"); n += 2
            f.write(json.dumps({"ev": "presend_disarm", "w": q + 1, "mint": mint, "st": float(A["a"]["st"][q]), "en": float(A["a"]["en"][q]),
                                "rows": {r: {"armed": bool(A[r]["armed"][q]), "filled": bool(A[r]["armed"][q] and A[r]["valid"][q]), "hit": None,
                                             "aend": float(A[r]["aend"][q]) if A[r]["armed"][q] else None, "slots": int(A[r]["slots"][q])} for r in LIVE_ROWS}}) + "\n"); n += 1
    return n

# ---------------------------------------------------------------------------------------------------------------- P&L
def live_D(D, srv_w, rmap):
    """a ps5_lib.run input made of the LIVE records' own numbers (one window per live arm; for rows a / b / c only)"""
    ids = [w for w in srv_w if srv_w[w].get("arm") and srv_w[w].get("disarm")]
    nW = len(ids); X = {}
    X["w_start"] = np.array([srv_w[w]["arm"]["st"] for w in ids], np.float64)
    X["w_end"] = np.array([srv_w[w]["disarm"]["en"] for w in ids], np.float64)
    X["w_tok"] = np.array([zlib.crc32(srv_w[w]["arm"]["mint"].encode()) & 0x7fffffff for w in ids], np.int64)
    X["w_f"] = np.zeros((nW, len(E.FI)), np.float32)
    X["w_t"] = np.array([rmap.get(w, (0, 0))[1] for w in ids], np.int64)
    X["w_in"] = np.ones(nW, bool)
    fills = []
    FR = np.full((len(E.YS), len(E.DMOD), nW), -1, np.int64)
    si = E.SIZES.index(CFG["size"]); e = E.EXI[CFG["ex"]]; yi = E.YS.index(CFG["y"])
    p_sin, p_off, p_pnl, f_time, f_x, p_min = [], [], [], [], [], []
    for q, w in enumerate(ids):
        for r in LIVE_ROWS:
            fl = srv_w[w].get("fill", {}).get(r); ex = srv_w[w].get("exit", {}).get(r)
            if not fl or not ex: continue
            k = len(f_time); FR[yi, E.DMOD.index(r), q] = k
            f_time.append(fl["ft"]); f_x.append(0); p_sin.append(ex["s_in"])
            po = np.zeros((len(E.SIZES), len(E.EXN)), np.int8); po[si, e] = ex["hold_slots"]; p_off.append(po)
            pp = np.zeros((len(E.SIZES), len(E.EXN)), np.float32); pp[si, e] = ex["pnl"]; p_pnl.append(pp)
            p_min.append(np.zeros(len(P4.MINCAPS), np.float32))
    X["FR"] = FR; X["f_time"] = np.array(f_time, np.float64); X["f_pid"] = np.arange(len(f_time), dtype=np.int64); X["f_x"] = np.array(f_x, np.int64)
    X["p_sin"] = np.array(p_sin, np.int64); X["p_off"] = np.array(p_off, np.int8).reshape(-1, len(E.SIZES), len(E.EXN))
    X["p_pnl"] = np.array(p_pnl, np.float32).reshape(-1, len(E.SIZES), len(E.EXN)); X["p_min"] = np.array(p_min, np.float32).reshape(-1, len(P4.MINCAPS))
    X["nW"] = nW
    return X, np.ones(nW, bool)

COSTS = [("cheap-k", {}), ("cheap-k1", {"k": 1}), ("+selltip", {"sell_tip": 0.001}), ("now-k", {"fee": "now"})]

def pnl_table(Dx, mask, h, rows, servers, tag):
    res = {}
    for r in rows:
        for cn, kw in COSTS:
            if cn == "cheap-k1" and r not in LIVE_ROWS: continue
            o = E.run(Dx, mask, CFG["W"], CFG["y"], r, CFG["size"], CFG["ex"], servers=servers, **kw)
            res[f"{r}|{cn}"] = dict(pnl=o["pnl"], per24=o["pnl"] / max(h, 1e-9) * 24, fill=o["fill"], armed=o["armed"], att=o["att"], per_fill=o["per_fill"],
                                    winr=o["winr"], skip=o["skip"], att_per_fill=o["att_per_fill"], gross=o["gross"])
        c = res[f"{r}|cheap-k"]
        say(f"    {tag} row {r:3s} (k {E.KDEF[r]:2d}/slot): {c['pnl']:+7.3f} SOL ({c['per24']:+6.2f}/24h) fills {c['fill']:4d} of {c['armed']:5d} armed (skip {c['skip']}), "
            f"net {c['per_fill']:+.4f}/fill, win {100 * c['winr']:3.0f}%, att/fill {c['att_per_fill']:6.0f} | "
            + " | ".join(f"{cn} {res[f'{r}|{cn}']['pnl']:+.3f}" for cn, _ in COSTS[1:] if f"{r}|{cn}" in res))
    return res

# ---------------------------------------------------------------------------------------------------------------- main
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", nargs="*", default=[]); ap.add_argument("--run")
    ap.add_argument("--from", dest="t_from"); ap.add_argument("--to", dest="t_to")
    ap.add_argument("--work"); ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--day"); ap.add_argument("--make-synthetic"); ap.add_argument("--keep-phasea", action="store_true")
    a = ap.parse_args()
    T0 = time.time()
    live = load_live(a.jsonl)
    # the window: --from / --to, else the live records' span (run_start .. run_end, else the records' slots)
    ts = [o["t"] / 1e9 for L in live.values() for o in L["starts"] + L["ends"] if o.get("t")] + \
         [o["arm"]["t"] / 1e9 for L in live.values() for o in L["wins"].values() if o.get("arm") and o["arm"].get("t")]
    slots = [o["arm"]["slot"] for L in live.values() for o in L["wins"].values() if o.get("arm")]
    t_from = pk(a.t_from) if a.t_from else (int(min(ts)) if ts else None)
    t_to = pk(a.t_to) if a.t_to else (int(max(ts)) + 1 if ts else None)
    work = a.work or f"{C.OUT}/shadow/{a.day or os.path.basename(a.run.rstrip('/'))}_{time.strftime('%m%d_%H%M', time.gmtime((t_from or time.time()) + 5 * 3600))}"
    os.makedirs(work, exist_ok=True)
    # ---- (0) the tape + the offline detection
    if a.day:
        d = C.load(a.day); src = f"study day array {a.day}"
    else:
        if not a.run: sys.exit("--run (the recording folder) or --day is needed")
        run = a.run.rstrip("/")
        if os.path.dirname(run) != COLLECT: sys.exit(f"--run must be a recording folder under {COLLECT} (p1_build reads its launches.jsonl there)")
        if t_from is None: sys.exit("no time window: pass --from / --to, or live records with times")
        npz = f"{work}/day_{TAG}.npz"
        if not os.path.exists(npz):
            pha = f"{work}/phaseA"
            files = [f for f in sorted(glob.glob(f"{run}/txs/txs_*.jsonl.gz")) if t_from - 16 * 60 <= int(os.path.basename(f).split("_")[1].split(".")[0]) <= t_to + 11 * 60]
            if not files: sys.exit("no recording chunks cover the window")
            say(f"  recording chunks {len(files)}: {os.path.basename(files[0])} .. {os.path.basename(files[-1])}")
            if not os.path.exists(f"{pha}/.done"): stage_extract(run, files, pha, a.procs); open(f"{pha}/.done", "w").write("ok")
            stage_days(run, pha, work, a.procs)
            if not a.keep_phasea:
                import shutil; shutil.rmtree(pha, ignore_errors=True); shutil.rmtree(f"{work}/tmp", ignore_errors=True)
        d = load_tape(npz, f"{work}/day_{TAG}_meta.json"); src = f"recording {run}"
    s_end = int(d["s"].max()); M = d["meta"]
    D = offline(d, a.procs)
    if t_from is None and slots:
        lo, hi = min(slots), max(slots)
        win = (D["s_tape"][D["w_j"]] >= lo) & (D["s_tape"][D["w_j"]] <= hi)
        sm = (d["s"] >= lo) & (d["s"] <= hi); h = (d["t"][sm].max() - d["t"][sm].min()) / 3600 if sm.any() else 0.0
        wdesc = f"slots {lo}..{hi} (the live records' span)"
    elif t_from is None:
        win = np.ones(D["nW"], bool); h = (d["t"].max() - d["t"].min()) / 3600; wdesc = "the whole tape"
    else:
        win = (D["w_t"] >= t_from) & (D["w_t"] < t_to); h = (t_to - t_from) / 3600; wdesc = f"{pkt(t_from)} -> {pkt(t_to)} PKT"
    D["w_in"] = win
    s_lo, s_hi = int(d["s"].min()), int(d["s"].max())
    if t_from is None and slots: in_win = lambda r: lo <= int(d["s"][r]) <= hi
    elif t_from is None: in_win = lambda r: True
    else: in_win = lambda r: t_from <= int(d["t"][r]) < t_to
    t2 = np.flatnonzero(D["t2"])
    # trigger in the token's create slot: in practice the create's SIGNER buying in the create tx of a launch that names another
    # creator (the study code counts it as htype 3); split out in (b) because these lose on every study day (R1-R4, row c)
    D["cslot"] = D["s_tape"][D["w_j"]] == np.array([M[int(t)]["S0"] for t in D["w_tok"]], np.int64)
    say(f"PRE-SEND SHADOW evaluation | {src} | window {wdesc} ({h:.2f} h) | offline: {D['nW']} windows, T2 config windows {len(t2)} "
        f"({int((D['t2'] & win).sum())} in the window) | {time.time() - T0:.0f} s")
    if a.make_synthetic:
        sel = np.flatnonzero(D["t2"] & win)
        n = make_synthetic(D, d, sel, a.make_synthetic)
        say(f"synthetic live records: {n} records for {len(sel)} windows -> {a.make_synthetic}"); sys.exit(0)
    if not live: sys.exit("no --jsonl records")
    K = tape_index(d)
    # offline per-row arming over every T2 window of the tape (the engine has no window cut)
    A = {r: arming(D, t2, r) for r in LIVE_ROWS}
    wpos = {int(w): q for q, w in enumerate(t2.tolist())}
    trig = {int(D["w_j"][w]): int(w) for w in t2.tolist()}
    res = {"window": wdesc, "hours": h, "servers": {}}
    eng_start = {}
    pooled_ids = set()
    for srv, L in live.items():
        say(f"\n=== {srv}: {L['file']} | {len(L['wins'])} windows in the records, {len(L['skips'])} presend_skip (no history), runs {len(L['starts'])}")
        start_t = min([o["t"] / 1e9 for o in L["starts"] if o.get("t")], default=None)
        # the engine's run intervals (a restart = a new run_start: the shadow then follows only tokens created after it)
        st_ = sorted(o["t"] / 1e9 for o in L["starts"] if o.get("t")); en_ = sorted(o["t"] / 1e9 for o in L["ends"] if o.get("t"))
        runs = [(a_, min([e for e in en_ if e >= a_] + [b for b in st_ if b > a_] + [float("inf")])) for a_ in st_]
        def run_of(tw):
            for a_, b_ in runs:
                if a_ <= tw < b_: return a_
            return None
        # ---- (a) parity
        P = collections.Counter(); ex = []
        rmap = {}; used = set(); matched = set(); live_in = set()
        for wid, o in L["wins"].items():
            ar = o.get("arm")
            if not ar: P["records without an arm"] += 1; continue
            j = find_row(K, ar["mint"], dict(ar, buy=True), used)
            # only windows inside the evaluation window (by the trigger's time on the tape; with no times: the records' slots)
            if j is not None and not in_win(j): P["outside the window (not compared)"] += 1; continue
            if j is None and not (s_lo <= int(ar["slot"]) <= s_hi): P["outside the tape (not compared)"] += 1; continue
            live_in.add(wid)
            w = trig.get(j) if j is not None else None
            if w is None:
                ti = d["tok"][j] if j is not None else None
                if j is None: why = "trigger not in the tape (token not in the study's tape: non-standard / not in launches.jsonl)"
                elif d["cnt"][ti] < 5: why = "the study's tape rule: < 5 trades on the token"
                elif d["s"][j] > s_end - 300: why = "the study's tape rule: last 300 slots"
                else: why = "UNEXPLAINED"
                P[f"live-only arm: {why}"] += 1
                if why == "UNEXPLAINED" and len(ex) < 8: ex.append(f"live-only arm w{wid} {ar['mint']} slot {ar['slot']} idx {ar['idx']}")
                continue
            matched.add(w); rmap[wid] = (w, int(D["w_t"][w])); pooled_ids.add(w)
            q = wpos[w]
            P["arms matched"] += 1
            if float(ar["st"]) != float(D["w_start"][w]): P["st differs"] += 1
            if float(ar["pct"]) != float(D["w_f"][w, E.FI["hpct"]]): P["holding % differs"] += 1
            dis = o.get("disarm")
            if dis is None: P["no disarm record (run end?)"] += 1; continue
            if dis.get("why") == "run_end": P["windows open at the run end"] += 1; continue
            if float(dis["en"]) != float(A["a"]["en"][q]): P["window end differs"] += 1
            for r in LIVE_ROWS:
                X = A[r]; lr = dis["rows"][r]; P[f"rows {r}"] += 1
                if bool(lr["armed"]) != bool(X["armed"][q]):
                    P[f"row {r}: armed flag differs"] += 1
                    if len(ex) < 8: ex.append(f"w{wid} {ar['mint']} row {r}: live armed {lr['armed']} offline {bool(X['armed'][q])}")
                    continue
                if not X["armed"][q]: continue
                if lr.get("aend") is not None and float(lr["aend"]) != float(X["aend"][q]): P[f"row {r}: armed-until differs"] += 1
                if int(lr["slots"]) != int(X["slots"][q]): P[f"row {r}: armed slots differ"] += 1
                fl = o.get("fill", {}).get(r); off_fill = bool(X["valid"][q])
                if bool(fl) != off_fill:
                    P[f"row {r}: fill / no fill differs"] += 1
                    if len(ex) < 8: ex.append(f"w{wid} {ar['mint']} row {r}: live fill {bool(fl)} offline {off_fill}")
                    continue
                if not fl: continue
                P[f"row {r}: fills"] += 1
                fr = int(X["fr"][q]); xo = int(D["f_x"][fr]); mo = int(D["f_m"][fr])
                xl = find_row(K, ar["mint"], fl["x"]); ml = find_row(K, ar["mint"], fl["m"])
                if xl != xo or ml != mo or float(fl["a_land"]) != float(d["arr"][xo]) + DFIX[r] or float(fl["ft"]) != float(X["ft"][q]) or int(fl["s_in"]) != int(X["sin"][q]):
                    P[f"row {r}: fill differs"] += 1
                    if len(ex) < 8: ex.append(f"w{wid} {ar['mint']} row {r}: fill live x {xl} m {ml} ft {fl['ft']} | offline x {xo} m {mo} ft {X['ft'][q]}")
                ext = o.get("exit", {}).get(r)
                if not ext: P[f"row {r}: exit missing"] += 1; continue
                if np.float32(ext["pnl"]) != np.float32(X["pn"][q]) or int(ext["hold_slots"]) != int(X["off"][q]) or float(ext["xt"]) != float(X["xt"][q]):
                    P[f"row {r}: exit differs"] += 1
                    if len(ex) < 8: ex.append(f"w{wid} {ar['mint']} row {r}: exit live {ext['pnl']} {ext['hold_slots']} | offline {X['pn'][q]} {X['off'][q]}")
        # offline windows the server did not record
        srv_slots = [o["arm"]["slot"] for o in L["wins"].values() if o.get("arm")]
        slo = min(srv_slots, default=0); shi = max(srv_slots, default=0)
        for w in np.flatnonzero(D["t2"] & win).tolist():
            if w in matched: continue
            t = int(D["w_tok"][w]); cbt = M[t].get("cbt") or 0; tw = int(D["w_t"][w])
            r0 = run_of(tw) if runs else None
            if runs and r0 is None: P["offline-only: the engine was not running then"] += 1
            elif r0 is not None and cbt and cbt < r0: P["offline-only: token created before the engine (re)started (no history)"] += 1
            elif start_t is None and not (slo <= D["s_tape"][D["w_j"][w]] <= shi): P["offline-only: outside the records' slots"] += 1
            else:
                P["offline-only: UNEXPLAINED"] += 1
                if len(ex) < 8: ex.append(f"offline-only window {M[t]['m']} trigger slot {int(D['s_tape'][D['w_j'][w]])}")
        say("  (a) PARITY " + "; ".join(f"{k} {v}" for k, v in sorted(P.items())))
        for e_ in ex: say(f"    e.g. {e_}")
        # the reactive bot on the same dumps
        fills_c = [o["fill"]["c"] for o in L["wins"].values() if o.get("fill", {}).get("c")]
        if fills_c:
            im = collections.Counter(k for f in fills_c for k, v in (f.get("imit") or {}).items() if v)
            say(f"  reactive bot on the crossing trade of the {len(fills_c)} row-c fills: " + ", ".join(f"{k} {v} ({100 * v / len(fills_c):.0f}%)" for k, v in sorted(im.items()))
                + "  (dump = an IMIT1 dump event, env = in its envelope, pick = passed its gate, fired = sent live, m2 = M2 picked)")
        # ---- (b) replay
        ids = np.array(sorted(matched), np.int64)
        mask = np.zeros(D["nW"], bool); mask[ids] = True
        say(f"  (b) REPLAY of this server's {len(ids)} live windows on the tape (ps4 / ps5 mechanics; cheap-k = study main row):")
        rr = {}
        for servers in (2, 1):
            rr[f"offline_{servers}"] = pnl_table(D, mask & win, h, ALL_ROWS, servers, f"offline, {servers} server{'s' if servers > 1 else ''}")
        say(f"  split by the trigger's slot (offline, 2 servers, cheap-k): create slot = the create's signer buying in the create tx (the study counts it; "
            f"it lost on R1-R4) vs later (the whale buys the REPORT describes)")
        rr["split"] = {}
        for nm, mm in (("create-slot triggers", mask & D["cslot"]), ("later triggers", mask & ~D["cslot"])):
            cells = []
            for r in ("a", "b", "c", "r4"):
                o = E.run(D, mm & win, CFG["W"], CFG["y"], r, CFG["size"], CFG["ex"])
                rr["split"][f"{nm}|{r}"] = dict(pnl=o["pnl"], per24=o["pnl"] / max(h, 1e-9) * 24, fill=o["fill"], armed=o["armed"], per_fill=o["per_fill"])
                cells.append(f"{r} {o['pnl']:+.3f} ({o['pnl'] / max(h, 1e-9) * 24:+.2f}/24h, {o['fill']} fills)")
            say(f"    {nm:21s} " + " | ".join(cells))
        Xl, ml_ = live_D(D, {w: o for w, o in L["wins"].items() if w in live_in}, rmap)
        if Xl["nW"]:
            rr["live_2"] = pnl_table(Xl, ml_, h, LIVE_ROWS, 2, "live-reported, 2 servers")
        res["servers"][srv] = dict(parity=dict(P), pnl=rr)
    # ---- (c) both servers pooled (the study's 2-server engine on the union of the live windows)
    if len(live) > 1:
        ids = np.array(sorted(pooled_ids), np.int64); mask = np.zeros(D["nW"], bool); mask[ids] = True
        say(f"\n=== POOLED (both servers' windows, deduplicated: {len(ids)}), the study's 2-server engine")
        res["pooled"] = pnl_table(D, mask & win, h, ALL_ROWS, 2, "pooled")
    say(f"\n  (all rows: 0.55 SOL, exit c2_tp10_sl20, cheap = 5,060 lamports per failed attempt + 0.001 tip + 2 tx per fill; now = 100k CU x 5M uL/CU) "
        f"| done in {time.time() - T0:.0f} s; report {work}/ps11_report.txt")
    open(f"{work}/ps11_report.txt", "w").write("\n".join(LOG) + "\n")
    json.dump(res, open(f"{work}/ps11_report.json", "w"), default=float, indent=1)
