#!/usr/bin/env python3
# DUMP-BOUNCE PAPER TRADER (no wallet, no buys, no sends). Reads the running collector's closed chunks; for every launch
# whose first 5 minutes are complete it finds the dumps (one sell >= 1 SOL that drops the price >= 5%), scores each with
# the frozen bounce model (same features as the backtest, incl. the leak-free "profitable wallets" history, which keeps
# growing as tokens finish their first 10 minutes), and paper-trades the top 4%: 0.5 SOL right behind the dump (also
# the view where 1 trade gets in first, skipped if the price already bounced > 2%), sell at +8% / -5% / 1.3 s with the
# sell filled at the end of the trigger's block (never inside the buy's block). Costs: pump fee per side + fixed
# 0.0015 SOL (wallet-like) and 0.015 SOL (our usual) per round trip. Telegram: BUY messages only (owner), no results.
# usage: python3 dump_paper.py <frozen_dump_bounce.json> <wallet_hist_seed.json> <collector run dir> <out dir>
import sys, os, json, gzip, glob, time, base64, math, collections, urllib.request, urllib.parse, datetime
MOD, SEED, CRUN, OUT = sys.argv[1:5]; os.makedirs(OUT, exist_ok=True)
M = json.load(open(MOD)); HIST = collections.defaultdict(lambda: [0, 0.0], {u: v for u, v in json.load(open(SEED)).items()})
TOKEN, CHAT = ("", "") if os.environ.get("NO_TG") else (os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", ""))   # owner 2026-10-23: no Telegram
RESUME_BEFORE = float(os.environ.get("RESUME_BEFORE", "0"))   # restart: launches created before this were already handled
X = 493827160; SPS = 5; FIXES = (0.0015, 0.015); START = time.time()
MIN_SELL, MIN_DROP, TP, SL, HOLD, THR = M["min_sell"], M["min_drop"], M["tp"], M["sl"], M["hold_slots"], M["threshold"]
DISC = bytes([189, 219, 127, 211, 78, 230, 97, 238])
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
def log(msg):
    with open(os.path.join(OUT, "dump_paper.log"), "a") as f: f.write(f"{datetime.datetime.now(datetime.UTC):%m-%d %H:%M:%S} {msg}\n")
def tg(text):
    if not TOKEN or not CHAT: return
    data = urllib.parse.urlencode(dict(chat_id=CHAT, text=text, disable_web_page_preview="true")).encode()
    for k in range(3):
        try: urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=data), timeout=15).read(); return
        except Exception as e: log(f"telegram send failed: {e.__class__.__name__} {getattr(e, 'code', '')}"); time.sleep(2 + 3 * k)   # never log str(e) (URL holds the token)
def score(x):
    f = M["F0"]; bins = []
    for k, e in zip(M["features"], M["edges"]):
        v = x.get(k); v = float(v) if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v)) else float("nan")
        if math.isnan(v): bins.append(0); continue
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
def trade(tr, k0, fb, cb):
    """the backtest's realistic sim: 0.5 SOL into the state after tr[k0-1]; +TP / -SL on price or HOLD slots; the sell
    fills at the end of the trigger's block, never inside the buy's block; None if the curve fills meanwhile"""
    st = tr[k0 - 1]; V, T = st[7], st[9]
    if not T or V >= 114e9: return None
    p_in = V / T; q = T * X // (V + X); V += X; T -= q; cost = X * (1 + (fb + cb) / 1e4); S0 = st[0]
    val = lambda V, T: (V * q // (T + q)) * (1 - (fb + cb) / 1e4) / cost - 1
    hit = None; fill_after = None
    for t in tr[k0:]:
        if fill_after is not None and t[0] > fill_after: return (val(V, T), hit, fill_after - S0)
        if hit is None and t[0] - S0 > HOLD:
            hit = "time"; fill_after = max(t[0] - 1, S0)
            if t[0] > fill_after: return (val(V, T), hit, fill_after - S0)
        if t[7] >= 114e9: return None
        if t[5]: dd = T * t[6] // (V + t[6]); V += t[6]; T -= dd
        else: so = V * t[8] // (T + t[8]); V -= so; T += t[8]
        p = (V - X) / (T + q) if T + q else p_in
        if hit is None and (p >= p_in * (1 + TP) or p <= p_in * (1 - SL)):
            hit = "profit" if p >= p_in * (1 + TP) else "loss"; fill_after = max(t[0], S0 + 1)
    return (val(V, T), hit or "end", (fill_after or S0) - S0)
L = {}; TR = collections.defaultdict(dict); done_chunks = set(); maxslot = [0]; lj_pos = [0]; detected = set(); resolved = set()
if os.path.exists(os.path.join(OUT, "dump_paper_trades.jsonl")):       # restart: never trade a launch twice
    for l in open(os.path.join(OUT, "dump_paper_trades.jsonl")):
        try: detected.add(json.loads(l)["mint"])
        except Exception: pass
ST_F = os.path.join(OUT, "dump_paper_state.json")
ST = json.load(open(ST_F)) if os.path.exists(ST_F) else dict(n=0, by={})
def read_launches():
    p = os.path.join(CRUN, "launches.jsonl")
    if not os.path.exists(p): return
    with open(p) as f:
        f.seek(lj_pos[0])
        for l in f:
            if not l.endswith("\n"): break
            lj_pos[0] += len(l.encode())
            try: c = json.loads(l)
            except Exception: continue
            if not c.get("err") and "InitializeMayhemState" not in (c.get("ixn") or []):
                L.setdefault(c["mint"], c)
                if (c.get("bt") or 0) < RESUME_BEFORE: detected.add(c["mint"])   # handled before the restart (history still rebuilt)
def read_chunks():
    files = sorted(glob.glob(os.path.join(CRUN, "txs", "*.jsonl.gz")))
    for fn in files[:-1]:                                          # the newest chunk is still being written
        if fn in done_chunks: continue
        try:
            for l in gzip.open(fn, "rt"):
                r = json.loads(l); maxslot[0] = max(maxslot[0], r["s"])
                for j, e in enumerate(r.get("ev") or []):
                    try: raw = base64.b64decode(e + "=" * (-len(e) % 4))
                    except Exception: continue
                    if raw[:8] != DISC or len(raw) < 217: continue
                    m = b58(raw[8:40])
                    if m not in L or m in resolved: continue
                    u = lambda o: int.from_bytes(raw[o:o + 8], "little")
                    TR[m][(r["sig"], j)] = (r["s"], r["i"], j, r["sig"], b58(raw[57:89]), raw[56] == 1, u(40), u(97), u(48), u(105), u(161), u(209))
        except (EOFError, OSError): pass
        done_chunks.add(fn)
def process():
    for m, c in list(L.items()):
        S = c["slot"]
        if m not in detected and maxslot[0] >= S + 1500 + 30:
            detected.add(m); dumps(m, c)
        if m not in resolved and maxslot[0] >= S + 2860 + 30:
            resolved.add(m); finish(m, c); TR.pop(m, None); L.pop(m, None)
def finish(m, c):
    """the token's first 10 minutes are over: each wallet's realized result on it joins the history (leak-free)"""
    S = c["slot"]; w = collections.defaultdict(lambda: [0, 0])
    for t in sorted(TR.get(m, {}).values()):
        if t[0] - S > 2860: break
        a = w[t[4]]
        if t[5]: a[0] += t[6]
        else: a[1] += t[6]
    for u, a in w.items():
        if a[0] > 0 and a[1] > 0: h = HIST[u]; h[0] += 1; h[1] += (a[1] - a[0]) / 1e9
def dumps(m, c):
    tr = sorted(TR.get(m, {}).values())
    if len(tr) < 5 or max(t[7] for t in tr) > 200e9: return       # as the backtest: >= 5 trades, no fake (> 200 SOL) reserves
    S = c["slot"]; creator = c.get("creator") or c.get("user"); ins = {creator, c.get("user"), c.get("payer")}
    ci = c.get("idx"); prev = ci; gi = 0; gl = []
    for k, t in enumerate(tr):
        if t[3] == c.get("sig"): gi = k + 1; continue
        if t[0] == S and t[1] in (prev, prev + 1) and t[5]: ins.add(t[4]); gl.append(t); prev = t[1]; gi = k + 1
        elif t[0] == S and t[1] > prev + 1: break
        elif t[0] > S: break
    if gi == 0 or not tr[gi - 1][9]: return
    dev = sum(t[6] for t in tr if t[3] == c.get("sig") and t[5]) / 1e9; gn = len({t[3] for t in gl}); gs = sum(t[6] for t in gl) / 1e9
    fb, cb = (tr[0][10] or 95), (tr[0][11] or 30); P0 = tr[gi - 1][7] / tr[gi - 1][9]
    px = [(t[7] / t[9]) if t[9] else None for t in tr]
    nb = ns = 0; peak = P0; buys = collections.deque()
    for k in range(gi, len(tr)):
        t = tr[k]; d = t[0] - S
        if d > 1500 or t[7] >= 114e9: break
        pb = px[k - 1] if px[k - 1] else P0; p = px[k]
        while buys and t[0] - buys[0][0] > 15: buys.popleft()
        if not t[5] and t[6] >= MIN_SELL and p and pb and p <= pb * (1 - MIN_DROP):
            b3 = {x[2] for x in buys}; good = {u for u in b3 if HIST[u][0] >= 5 and HIST[u][1] > 0}
            f = dict(drop=1 - p / pb, sell_sol=t[6] / 1e9, age_s=d / SPS, runup=pb / P0, runup_peak=pb / peak, from_peak=p / peak, vsol=t[7] / 1e9, nb=nb, ns=ns,
                     buys3=len(buys), buys3_sol=sum(x[1] for x in buys) / 1e9, seller_insider=int(t[4] in ins), dev=dev, gn=gn, gs=gs,
                     pbots3=len(good), pbots3_share=len(good) / max(len(b3), 1))
            sc = score(f)
            if sc >= THR:
                r1 = trade(tr, k + 1, fb, cb) if k + 1 <= len(tr) else None
                r2 = None
                if k + 2 <= len(tr):
                    r2 = "skip" if (px[k + 1] and px[k + 1] > p * 1.02) else trade(tr, k + 2, fb, cb)
                if r1 is not None:
                    rec = dict(mint=m, name=c.get("name"), t=(c.get("bt") or 0) + d / SPS, dump_sig=t[3], seller=t[4], score=sc, f=f,
                               behind=dict(ret=r1[0], why=r1[1], held_blocks=r1[2], pnl={str(x): r1[0] * 0.5 - x for x in FIXES}),
                               one_ahead=("skip" if r2 == "skip" else None if r2 is None else dict(ret=r2[0], why=r2[1], pnl={str(x): r2[0] * 0.5 - x for x in FIXES})))
                    with open(os.path.join(OUT, "dump_paper_trades.jsonl"), "a") as fo: fo.write(json.dumps(rec) + "\n")
                    ST["n"] += 1
                    for x in FIXES: ST["by"][f"behind_{x}"] = ST["by"].get(f"behind_{x}", 0) + r1[0] * 0.5 - x
                    if isinstance(r2, tuple):
                        for x in FIXES: ST["by"][f"one_ahead_{x}"] = ST["by"].get(f"one_ahead_{x}", 0) + r2[0] * 0.5 - x
                    json.dump(ST, open(ST_F, "w"))
                    if rec["t"] >= START - 60:                     # no Telegram for the backlog before the start
                        tg(f"🟡 DUMP-BOUNCE paper BUY (no money)\n{c.get('name') or ''} {m}\na {t[6] / 1e9:.2f} SOL sell dropped the price {f['drop']:.0%} at {d / SPS:.0f} s | score {sc:+.2f}\nhttps://gmgn.ai/sol/token/{m}")
        if t[5]:
            buys.append((t[0], t[6], t[4]))
            if t[4] not in ins: nb += 1
        else: ns += 1
        if p and p > peak: peak = p
log(f"started: model {M['n_events']} dumps, threshold {THR:.3f}, wallet history {len(HIST)}")
while True:
    try: read_launches(); read_chunks(); process()
    except Exception as e: log(f"loop error: {e.__class__.__name__}: {str(e)[:200]}")
    time.sleep(10)
