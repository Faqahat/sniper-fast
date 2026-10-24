#!/usr/bin/env python3
# SHADOW SCORER (no wallet, no sends). Tails the shadow engine's log (paper mode, every launch watched, gate never
# passes) and, at each launch's glued-bundle decision, builds the LIVE model's 51 features exactly like training
# (create tx + bundle from the engine lines, own create stream, 10-minute outcome history from the running collector),
# scores it with the frozen model and logs score / picks / decision timing; the later RACE obs line adds the timeline of
# competing outside buyers (ms after the create). History comes from: a seed (all launches before start) + the
# collector's closed txs chunks (outcomes resolved 10 min after each create).
# FINAL config (optional 7th arg): pick = SOL-quoted and pick-model score >= its top-k threshold and (if set) the fast-dump
# veto model's score < veto_cut. Anti-dump history (f_dump.py): how fast each creator's / wallet's earlier launches dumped.
# usage: python3 scorer.py <engine log> <frozen model.json,...> <seed.json> <collector run dir> <tipmap.json> <out dir> [final_config.json]
import sys, os, re, json, gzip, time, glob, base64, math, statistics, collections, datetime, urllib.parse
LOG, MODEL, SEED, CRUN, TIPMAP, OUT = sys.argv[1:7]
os.makedirs(OUT, exist_ok=True)
MODELS = [json.load(open(p)) for p in MODEL.split(",")]; M = MODELS[0]; TIPS = json.load(open(TIPMAP))   # first = picks
MBYF = {os.path.basename(p): Mo for p, Mo in zip(MODEL.split(","), MODELS)}
CFG = json.load(open(sys.argv[7])) if len(sys.argv) > 7 else None
if CFG: MP = MBYF[CFG["model_file"]]; MV = MBYF.get(CFG.get("veto_file")) if CFG.get("veto_file") else None
V0, T0 = 30_000_000_000, 1_073_000_000_000_000
KV = re.compile(r"(\w+)=(\S*)")
norm = lambda x: re.sub(r"[^a-z0-9]", "", (x or "").lower())
nkey = lambda x: (x or "").strip().lower()                  # training's name-history key (exact name)
VARIANT = {"v2": "CreateV2", "v1": "Create", "router": "CreateCoinAndBuyBondingCurveV3"}
def host(u):
    try: return urllib.parse.urlparse(u if "://" in u else "https://" + u).hostname or ""
    except Exception: return ""
def unb64(v, fb):
    try: return base64.b64decode(v).decode("utf-8", "replace") if v not in (None, "", "-") else (fb or "")
    except Exception: return fb or ""
# ---------------- state ----------------
cr_times = collections.defaultdict(list)                    # creator -> create times (own stream)
recent = collections.deque()                                # (t, normname, normsym) last 60 min
h_creator = collections.defaultdict(list); h_name = collections.defaultdict(list); h_bund = collections.defaultdict(lambda: [0, 0])
res_recent = collections.deque()                            # (resolve t, win) last 60 min
in_stream = set()
def add_create(t, creator, nn, ns, mint=None):
    if mint:
        if mint in in_stream: return
        in_stream.add(mint)
    cr_times[creator].append(t); recent.append((t, nn, ns))
hc_d = collections.defaultdict(list); hw = collections.defaultdict(list)   # anti-dump history: creator -> (fast, first, out); wallet -> first-sell delays
FAST_FIRST, FAST_OUT = 25, 75
def add_dump(creator, fast, first, out_d, wsell):
    hc_d[creator].append((fast, first if first is not None else 2860, out_d if out_d is not None else 2860))
    for w, d in wsell.items(): hw[w].append(d if d is not None else 2860)
def add_resolved(t, creator, nk, win, bwal):
    h_creator[creator].append(win); h_name[nk].append(win); res_recent.append((t, win))
    for b in bwal: h_bund[b][0] += 1; h_bund[b][1] += win
S = json.load(open(SEED))
for t, c, nn, ns in S["creates"]: add_create(t, c, nn, ns)
seed_res = collections.deque(S["resolved"]); seen_res = set(); SEED_MINTS = {x[5] for x in S["resolved"]}
seed_dump = collections.deque(S.get("dump", []))
START_BT = S["last_bt"]
def fill_gap():
    """creates between the seed's last launch and now, from the running collector (closes the seed->start gap)"""
    p = os.path.join(CRUN, "launches.jsonl"); n = 0
    if not os.path.exists(p): return 0
    for l in open(p):
        try: c = json.loads(l)
        except Exception: continue
        if c.get("err") or not c.get("bt") or c["bt"] <= START_BT: continue
        add_create(c["bt"], c.get("creator") or c.get("user"), norm(c.get("name")), norm(c.get("symbol")), c["mint"]); n += 1
    return n
# ---------------- model ----------------
def score(x, M=M):
    f = M["F0"]
    for j_edges, k in zip(M["edges"], M["features"]): pass
    vals = []
    for k in M["features"]:
        if "==" in k:
            a, v = k.split("==", 1); vals.append(1.0 if str(x.get(a)) == v else 0.0)
        else:
            v = x.get(k); vals.append(float(v) if isinstance(v, (int, float)) and v is not None and not (isinstance(v, float) and math.isnan(v)) else float("nan"))
    bins = []
    for v, e in zip(vals, M["edges"]):
        if math.isnan(v): bins.append(0)
        else:
            lo, hi = 0, len(e)
            while lo < hi:
                mid = (lo + hi) // 2
                if e[mid] <= v: lo = mid + 1
                else: hi = mid
            bins.append(lo + 1)
    for t in M["trees"]:
        n = t
        while "w" not in n: n = n["l"] if bins[n["f"]] <= n["b"] else n["r"]
        f += M["lr"] * n["w"]
    return f
# ---------------- collector outcome tracker (closed chunks only) ----------------
DISC = bytes([189, 219, 127, 211, 78, 230, 97, 238])
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
CL = {}; cl_pos = 0; done_chunks = set(); trades = collections.defaultdict(list); maxslot = [0]
def read_launches():
    global cl_pos
    p = os.path.join(CRUN, "launches.jsonl")
    if not os.path.exists(p): return
    with open(p) as f:
        f.seek(cl_pos)
        for l in f:
            if not l.endswith("\n"): break
            cl_pos += len(l.encode())
            try: c = json.loads(l)
            except Exception: continue
            if c.get("err") or c["mint"] in CL or c["mint"] in SEED_MINTS: continue   # the seed already resolved it
            CL[c["mint"]] = c
def read_chunks():
    files = sorted(glob.glob(os.path.join(CRUN, "txs", "*.jsonl.gz")))
    for fn in files[:-1]:                                           # the newest chunk is still being written
        if fn in done_chunks: continue
        try:
            for l in gzip.open(fn, "rt"):
                r = json.loads(l); maxslot[0] = max(maxslot[0], r["s"])
                for j, e in enumerate(r.get("ev") or []):
                    try: raw = base64.b64decode(e + "=" * (-len(e) % 4))
                    except Exception: continue
                    if raw[:8] != DISC or len(raw) < 129: continue
                    m = b58(raw[8:40])
                    if m not in CL: continue
                    u = lambda o: int.from_bytes(raw[o:o + 8], "little")
                    trades[m].append((r["s"], r["i"], j, raw[56] == 1, u(40), b58(raw[57:89]), u(97), u(105), r["sig"], u(48)))
        except (EOFError, OSError): pass
        done_chunks.add(fn); resolve()
def resolve():
    """launches whose first 10 minutes are fully inside processed chunks -> history (same rule as training)"""
    for m, c in list(CL.items()):
        if m in seen_res or c["slot"] + 2860 + 50 > maxslot[0]: continue
        seen_res.add(m); S_ = c["slot"]; tr = sorted(trades.pop(m, []))
        tr = list({(t[8], t[2]): t for t in tr}.values()); tr.sort()
        gi = 0; prev = c.get("idx"); bus = set()
        for k, t in enumerate(tr):
            if t[8] == c["sig"]: gi = k + 1; continue
            if t[0] == S_ and t[1] in (prev, prev + 1) and t[3]: bus.add(t[5]); prev = t[1]; gi = k + 1
            elif t[0] == S_ and t[1] > prev + 1: break
            elif t[0] > S_: break
        pre = tr[gi - 1] if gi > 0 else None
        win = 0
        if pre and pre[7] and pre[6] > 0 and pre[6] <= 200e9:
            P0 = pre[6] / pre[7]; pk = max([t[6] / t[7] for t in tr[gi:] if t[7] and t[0] - S_ <= 2860] + [P0]) / P0; win = int(pk >= 2.0)
        add_resolved(c.get("bt", 0) + 600, c.get("creator") or c.get("user"), nkey(c.get("name")), win, bus)
        if tr:                                                  # anti-dump facts exactly as f_dump.py
            creator = c.get("creator") or c.get("user"); ins = {creator, c.get("user"), c.get("payer")} | bus
            hold = collections.Counter(); mx = 0; first = out_d = None; wfirst = {}
            for t in tr:
                d = t[0] - S_
                if d > 2860: break
                if t[5] not in ins: continue
                hold[t[5]] += t[9] if t[3] else -t[9]
                tot = sum(max(v, 0) for v in hold.values()); mx = max(mx, tot)
                if not t[3]:
                    if first is None: first = d
                    wfirst.setdefault(t[5], d)
                    if out_d is None and mx > 0 and tot <= 0.05 * mx: out_d = d
            fast = int((first is not None and first <= FAST_FIRST) or (out_d is not None and out_d <= FAST_OUT))
            add_dump(creator, fast, first, out_d, {w: wfirst.get(w) for w in bus | {c.get("user")} if w})
    while seed_res and seed_res[0][0] <= time.time():
        t, cr, nn, win, bwal, m = seed_res.popleft()
        if m not in seen_res: seen_res.add(m); add_resolved(t, cr, nn, win, bwal)
    while seed_dump and seed_dump[0][0] <= time.time():
        t, cr, fast, first, out_d, wsell, m = seed_dump.popleft(); add_dump(cr, fast, first, out_d, wsell)
# ---------------- engine log tail ----------------
seen = {}; pending_obs = {}; stats = collections.Counter()
out = open(os.path.join(OUT, "shadow_scores.jsonl"), "a")
def feat(sl, dec, t, m):
    # pump records a per-mint creator on holder-reward launches (CreateEvent creator != the args creator): training keys
    # creator history / payer==creator on the EVENT creator, so such a launch has no creator past
    hr = sl.get("hr") == "1"
    creator = ("hr:" + m) if hr else sl.get("creator"); payer = sl.get("payer")
    vqc = int(dec.get("vq_create", 0) or 0)
    dn = int(sl.get("dev_net", 0) or 0)
    dev = (dn if dn > 0 else max(vqc - V0, 0)) / 1e9            # TradeEvent SOL (net of pump's fee)
    gsol = float(dec.get("bundle_sol", 0) or 0); n = int(dec.get("bundle_n", 0) or 0)
    gw = int(dec.get("g_signers", 0) or 0); gp = int(dec.get("g_payers", 0) or 0)
    vq = int(dec.get("vq_after", 0) or 0) or int(V0 + dev * 1e9 + gsol * 1e9)
    Tt = V0 * T0 / vq
    has_ct = dev > 0                                            # training: create-tx fields exist only if the create tx traded
    raw = lambda k: (int(sl[k]) if sl.get(k) not in (None, "", "-") else None)
    cup = raw("cup_raw") if has_ct else None; cul = raw("cul_raw") if has_ct else None
    xf = [(a, int(b)) for a, _, b in (e.partition(":") for e in (sl.get("xfers") or "-").split(",")) if b]
    tips = (sum(v for k, v in xf if k in TIPS or k.startswith("noz")) / 1e9) if has_ct else None
    nm = unb64(sl.get("name64"), sl.get("name")); sy = unb64(sl.get("sym64"), sl.get("sym")); nn, ns = norm(nm), norm(sy)
    ct = cr_times.get(creator, [])
    hc = h_creator.get(creator, []); hn = h_name.get(nkey(nm), [])
    bw = [w for w in (dec.get("g_wallets") or "-").split(",") if w and w != "-"]   # glued-bundle signers (training: glued trade users)
    bh = [h_bund[w] for w in bw if w in h_bund]
    rr = [w for tq, w in res_recent if tq >= t - 3600]
    hd = hc_d.get(creator, []); ws = [hw[w] for w in bw if w in hw]; dvh = hw.get(payer, []) if payer else []; allw = [d for v in ws for d in v]
    med = statistics.median
    x = dict(hd_cr_n=len(hd), hd_cr_fast=(sum(a[0] for a in hd) / len(hd)) if hd else None, hd_cr_first_s=(med([a[1] for a in hd]) / 5) if hd else None,
             hd_cr_out_s=(med([a[2] for a in hd]) / 5) if hd else None, hd_bw_seen=len(ws), hd_bw_n=len(allw),
             hd_bw_fast=(sum(1 for d in allw if d <= FAST_FIRST) / len(allw)) if allw else None, hd_bw_first_s=(med(allw) / 5) if allw else None,
             hd_bw_worst=(max(sum(1 for d in v if d <= FAST_FIRST) / len(v) for v in ws)) if ws else None,
             hd_dev_n=len(dvh), hd_dev_fast=(sum(1 for d in dvh if d <= FAST_FIRST) / len(dvh)) if dvh else None,
             P0_mc_sol=(vq * 1e6 / Tt / 1e9) if (has_ct or n) else None, bundle_avg=(gsol / gw) if gw else 0.0, cr_creates_window=len(ct),
             cr_min_since_prev_create=((t - ct[-1]) / 60) if ct else None, create_cul=cul, create_cup=cup,
             create_fee=5000 * int(sl.get("nsig", 1) or 1) + ((cup or 0) * (cul or 0) + 999_999) // 1_000_000, create_tips=tips, dev_buy=dev,
             dev_share=(dev / (dev + gsol)) if (dev + gsol) > 0 else None, glued_n=n,
             glued_payer_is_creator=0 if hr else int(dec.get("g_payer_creator", 0) or 0),
             glued_same_payer=int(gp == 1) if n else 0, glued_sol=gsol, glued_wallets=gw,
             h_bund_launches=sum(v[0] for v in bh), h_bund_seen=len(bh), h_bund_wins=sum(v[1] for v in bh),
             h_cr_last_win=int(hc[-1]) if hc else -1, h_cr_n=len(hc), h_cr_wins=sum(hc), h_name_n=len(hn), h_name_wins=sum(hn),
             heat_launches_10m=sum(1 for q in recent if q[0] >= t - 600), heat_win_rate_60m=(sum(rr) / len(rr)) if len(rr) >= 20 else None,
             hour_utc=int((t % 86400) // 3600), mayhem=int(sl.get("mayhem", 0) or 0), name_digits=int(bool(re.search(r"\d", nm))),
             name_len=len(nm), name_nonascii=int(any(ord(ch) > 127 for ch in nm + sy)), name_upper=int(nm.isupper()),
             payer_is_creator=int(payer == creator), sym_eq_name=int(sy.lower() == nm.lower()), sym_len=len(sy),
             wave_name_10m=sum(1 for q in recent if q[0] >= t - 600 and q[1] == nn and nn), wave_name_60m=sum(1 for q in recent if q[1] == nn and nn),
             wave_sym_60m=sum(1 for q in recent if q[2] == ns and ns),
             create_variant=VARIANT.get(sl.get("_kind"), sl.get("_kind")), uri_host=host(sl.get("uri") if sl.get("uri") not in (None, "-") else ""),
             fp=f"{cup}|{cul}|{int((tips or 0) > 0)}")
    return x, creator, nn, ns
def follow(path):
    f = None; ino = None
    while True:
        try:
            st = os.stat(path)
            if f is None or st.st_ino != ino: f = open(path, errors="replace"); ino = st.st_ino; f.seek(0, 2) if os.environ.get("FROM_END") else None
        except FileNotFoundError: time.sleep(1); continue
        l = f.readline()
        if not l: yield None; continue
        yield l
last_hist = 0; last_stat = 0
stats["gap_creates"] = fill_gap()
read_launches()
for line in follow(LOG):
    now = time.time()
    if now - last_hist > 30: read_launches(); read_chunks(); resolve(); last_hist = now
    while recent and recent[0][0] < now - 3600: recent.popleft()
    while res_recent and res_recent[0][0] < now - 3600: res_recent.popleft()
    if now - last_stat > 60:
        json.dump(dict(now=now, stats=dict(stats), recent=len(recent), resolved_hist=len(seen_res), chunks=len(done_chunks), pending=len(seen)),
                  open(os.path.join(OUT, "shadow_status.json"), "w")); last_stat = now
    if line is None: time.sleep(0.05); continue
    if "DETECT" in line and " first=1 " in line:
        d = dict(KV.findall(line)); m = d.get("mint")
        t_rx = int(d.get("t_rx", 0) or 0) / 1e9                # the engine's receive time (the scorer may lag while loading history)
        if m and m not in seen and m not in pending_obs: seen[m] = {"_t": t_rx or now, "_kind": d.get("kind"), "_quote": d.get("quote")}; stats["detect"] += 1
    elif "RACE seen" in line:
        d = dict(KV.findall(line.split("RACE seen", 1)[1])); m = d.get("mint")
        e = seen.setdefault(m, {"_t": now}); e.update(d); stats["seen"] += 1
    elif "RACE decide" in line:
        d = dict(KV.findall(line)); m = d.get("mint"); sl = seen.pop(m, None)
        if not sl or "creator" not in sl: stats["decide_no_seen"] += 1; continue
        t_ev = sl["_t"]; x, cr_key, nn, ns = feat(sl, d, t_ev, m); sc = score(x); th = M["thresholds"]
        add_create(t_ev, cr_key, nn, ns, m)                    # after its own features (training excludes the launch itself)
        sol = sl.get("_quote") == "sol"                         # we only buy SOL-quoted launches
        rec = dict(type="decide", mint=m, slot=int(d.get("slot", 0)), t=t_ev, t_scored=time.time(), at_ms=float(d.get("at_ms", 0)), quote=sl.get("_quote"),
                   glued_closed=d.get("glued_closed"), glued_unknown=d.get("glued_unknown"), score=sc, pick1=sol and sc >= th["1%"], pick2=sol and sc >= th["2%"],
                   other=[dict(featset=Mo.get("featset"), label=Mo.get("label"), score=(so := score(x, Mo)), pick1=sol and so >= Mo["thresholds"]["1%"], pick2=sol and so >= Mo["thresholds"]["2%"]) for Mo in MODELS[1:]],
                   features=x)
        if CFG:                                                 # the FINAL config's own pick (pick model top-k minus the fast-dump veto)
            sp = score(x, MP); sv = score(x, MV) if MV else None
            guard = True                                        # exact guards on top of the models
            if "payer_is_creator" in CFG.get("guards", []): guard = guard and x.get("payer_is_creator") == 1
            if "no_bundle_small_dev" in CFG.get("guards", []): guard = guard and not ((x.get("glued_n") or 0) == 0 and (x.get("dev_buy") or 0) < 1)
            rec.update(final=CFG["name"], final_score=sp, veto_score=sv, guard=guard,
                       final_pick=bool(sol and guard and sp >= MP["thresholds"][CFG["top"]] and (sv is None or sv < CFG["veto_cut"])))
            stats["final_pick"] += rec["final_pick"]
        out.write(json.dumps(rec, default=str) + "\n"); out.flush(); stats["scored"] += 1; stats["scored_sol"] += sol; stats["pick2"] += rec["pick2"]; stats["pick1"] += rec["pick1"]
        pending_obs[m] = now
    elif "RACE obs" in line:
        d = dict(KV.findall(line)); m = d.get("mint")
        if m in pending_obs:
            pending_obs.pop(m)
            out.write(json.dumps(dict(type="obs", mint=m, first_ms=float(d.get("first_ms", -1)), n25=d.get("n25"), n50=d.get("n50"), n100=d.get("n100"),
                                      n200=d.get("n200"), outs=d.get("outs"))) + "\n"); out.flush()
    if len(seen) > 5000:
        for k in list(seen)[:1000]: seen.pop(k, None)
