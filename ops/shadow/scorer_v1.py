#!/usr/bin/env python3
# SHADOW SCORER (no wallet, no sends). Tails the shadow engine's log (paper mode, every launch watched, gate never
# passes) and, at each launch's glued-bundle decision, builds the LIVE model's 51 features exactly like training
# (create tx + bundle from the engine lines, own create stream, 10-minute outcome history from the running collector),
# scores it with the frozen model and logs score / picks / decision timing; the later RACE obs line adds the timeline of
# competing outside buyers (ms after the create). History comes from: a seed (all launches before start) + the
# collector's closed txs chunks (outcomes resolved 10 min after each create).
# usage: python3 scorer.py <engine log> <frozen model.json> <seed.json> <collector run dir> <tipmap.json> <out dir>
import sys, os, re, json, gzip, time, glob, base64, math, collections, datetime
LOG, MODEL, SEED, CRUN, TIPMAP, OUT = sys.argv[1:7]
os.makedirs(OUT, exist_ok=True)
M = json.load(open(MODEL)); TIPS = json.load(open(TIPMAP))
V0, T0 = 30_000_000_000, 1_073_000_000_000_000
KV = re.compile(r"(\w+)=(\S*)")
norm = lambda x: re.sub(r"[^a-z0-9]", "", (x or "").lower())
# ---------------- state ----------------
cr_times = collections.defaultdict(list)                    # creator -> create times (own stream)
recent = collections.deque()                                # (t, normname, normsym) last 60 min
h_creator = collections.defaultdict(list); h_name = collections.defaultdict(list); h_bund = collections.defaultdict(lambda: [0, 0])
res_recent = collections.deque()                            # (resolve t, win) last 60 min
def add_create(t, creator, nn, ns):
    cr_times[creator].append(t); recent.append((t, nn, ns))
def add_resolved(t, creator, nn, win, bwal):
    h_creator[creator].append(win); h_name[nn].append(win); res_recent.append((t, win))
    for b in bwal: h_bund[b][0] += 1; h_bund[b][1] += win
S = json.load(open(SEED))
for t, c, nn, ns in S["creates"]: add_create(t, c, nn, ns)
seed_res = collections.deque(S["resolved"]); seen_res = set(); SEED_MINTS = {x[5] for x in S["resolved"]}
START_BT = S["last_bt"]
# ---------------- model ----------------
def score(x):
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
                    trades[m].append((r["s"], r["i"], j, raw[56] == 1, u(40), b58(raw[57:89]), u(97), u(105), r["sig"]))
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
        add_resolved(c.get("bt", 0) + 600, c.get("creator") or c.get("user"), norm(c.get("name")), win, bus)
    while seed_res and seed_res[0][0] <= time.time():
        t, cr, nn, win, bwal, m = seed_res.popleft()
        if m not in seen_res: seen_res.add(m); add_resolved(t, cr, nn, win, bwal)
# ---------------- engine log tail ----------------
seen = {}; pending_obs = {}; stats = collections.Counter()
out = open(os.path.join(OUT, "shadow_scores.jsonl"), "a")
def feat(sl, dec, t):
    creator, payer = sl.get("creator"), sl.get("payer")
    dev = int(sl.get("dev", 0) or 0) / 1e9; gsol = float(dec.get("bundle_sol", 0) or 0); n = int(dec.get("bundle_n", 0) or 0)
    gw = int(dec.get("g_signers", 0) or 0); gp = int(dec.get("g_payers", 0) or 0)
    vq = int(dec.get("vq_after", 0) or 0) or int(V0 + dev * 1e9 + gsol * 1e9)
    Tt = V0 * T0 / vq
    cup = int(sl.get("cu_price", 0) or 0) or None; cul = int(sl.get("cu_limit", 0) or 0) or None
    tip_to = sl.get("tip_to", "-"); tip = int(sl.get("tip", 0) or 0) / 1e9
    tips = tip if (tip_to in TIPS or tip_to.startswith("noz")) else 0.0
    nm = sl.get("name", "") or ""; sy = sl.get("sym", "") or ""; nn, ns = norm(nm), norm(sy)
    ct = cr_times.get(creator, [])
    hc = h_creator.get(creator, []); hn = h_name.get(nn, [])
    bw = [w for w in (dec.get("g_wallets") or "-").split(",") if w and w != "-"]   # glued-bundle signers (training: glued trade users)
    bh = [h_bund[w] for w in bw if w in h_bund]
    rr = [w for tq, w in res_recent if tq >= t - 3600]
    x = dict(P0_mc_sol=vq * 1e6 / Tt / 1e9, bundle_avg=(gsol / gw) if gw else 0.0, cr_creates_window=len(ct),
             cr_min_since_prev_create=((t - ct[-1]) / 60) if ct else None, create_cul=cul, create_cup=cup,
             create_fee=5000 * int(sl.get("nsig", 1) or 1) + ((cup or 0) * (cul or 0) + 999_999) // 1_000_000, create_tips=tips, dev_buy=dev,
             dev_share=(dev / (dev + gsol)) if (dev + gsol) > 0 else None, glued_n=n, glued_payer_is_creator=int(dec.get("g_payer_creator", 0) or 0),
             glued_same_payer=int(gp == 1) if n else 0, glued_sol=gsol, glued_wallets=gw,
             h_bund_launches=sum(v[0] for v in bh), h_bund_seen=len(bh), h_bund_wins=sum(v[1] for v in bh),
             h_cr_last_win=int(hc[-1]) if hc else -1, h_cr_n=len(hc), h_cr_wins=sum(hc), h_name_n=len(hn), h_name_wins=sum(hn),
             heat_launches_10m=sum(1 for q in recent if q[0] >= t - 600), heat_win_rate_60m=(sum(rr) / len(rr)) if len(rr) >= 20 else None,
             hour_utc=int((t % 86400) // 3600), mayhem=int(sl.get("mayhem", 0) or 0), name_digits=int(bool(re.search(r"\d", nm))),
             name_len=int(sl.get("name_len", len(nm)) or 0), name_nonascii=int(any(ord(ch) > 127 for ch in nm + sy)), name_upper=int(nm.isupper()),
             payer_is_creator=int(payer == creator), sym_eq_name=int(sy.lower() == nm.lower()), sym_len=len(sy),
             wave_name_10m=sum(1 for q in recent if q[0] >= t - 600 and q[1] == nn and nn), wave_name_60m=sum(1 for q in recent if q[1] == nn and nn),
             wave_sym_60m=sum(1 for q in recent if q[2] == ns and ns),
             create_variant="CreateV2" if sl.get("_kind") in ("v2", None) else "CreateCoinAndBuyBondingCurveV3", uri_host=sl.get("host"),
             fp=f"{cup}|{cul}|{int(tips > 0)}")
    return x
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
        if m and m not in seen and m not in pending_obs: seen[m] = {"_t": now, "_kind": d.get("kind")}; stats["detect"] += 1
    elif "RACE seen" in line:
        d = dict(KV.findall(line.split("RACE seen", 1)[1])); m = d.get("mint")
        e = seen.setdefault(m, {"_t": now}); e.update(d); stats["seen"] += 1
        add_create(now, d.get("creator"), norm(d.get("name")), norm(d.get("sym")))
    elif "RACE decide" in line:
        d = dict(KV.findall(line)); m = d.get("mint"); sl = seen.pop(m, None)
        if not sl or "creator" not in sl: stats["decide_no_seen"] += 1; continue
        t_ev = sl["_t"]; x = feat(sl, d, t_ev); sc = score(x); th = M["thresholds"]
        rec = dict(type="decide", mint=m, slot=int(d.get("slot", 0)), t=t_ev, t_scored=time.time(), at_ms=float(d.get("at_ms", 0)),
                   glued_closed=d.get("glued_closed"), glued_unknown=d.get("glued_unknown"), score=sc, pick1=sc >= th["1%"], pick2=sc >= th["2%"], features=x)
        out.write(json.dumps(rec, default=str) + "\n"); out.flush(); stats["scored"] += 1; stats["pick2"] += rec["pick2"]; stats["pick1"] += rec["pick1"]
        pending_obs[m] = now
    elif "RACE obs" in line:
        d = dict(KV.findall(line)); m = d.get("mint")
        if m in pending_obs:
            pending_obs.pop(m)
            out.write(json.dumps(dict(type="obs", mint=m, first_ms=float(d.get("first_ms", -1)), n25=d.get("n25"), n50=d.get("n50"), n100=d.get("n100"),
                                      n200=d.get("n200"), outs=d.get("outs"))) + "\n"); out.flush()
    if len(seen) > 5000:
        for k in list(seen)[:1000]: seen.pop(k, None)
