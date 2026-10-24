#!/usr/bin/env python3
# PAPER DRY RUN -> TELEGRAM (no wallet, no buys, no sends). Every FINAL-2 pick of the live shadow scorer is traded on
# paper WITH ALL COSTS: pump fee on both sides (from the events), our 0.5 SOL buy's own curve impact, and a fixed
# 0.015 SOL per round trip (priority fee + tip + base fees of the buy and the sell).
#   BUY message the moment the scorer picks it; RESULT message once the collector's closed chunks hold its first 30 s:
#   entry right after the creator's bundle (first in line) AND at our measured landing (behind every outside tx the
#   engine saw before decide + 74 ms); exit at the first sell (filled at the end of that slot), 30 s cap.
#   A curve that fills (graduates) before our sell is reported but not counted (no AMM price in our data).
# Telegram token / chat from the environment (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID); never printed or logged.
# usage: python3 tg_paper.py <shadow_scores.jsonl> <collector run dir> <out dir>
import sys, os, json, gzip, glob, time, base64, urllib.request, urllib.parse, datetime
SC, CRUN, OUT = sys.argv[1:4]
TOKEN, CHAT = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")
X = 493827160; FIX = 0.015; SIZE = 0.5; LAND = 74.0; CAP = 150
DISC = bytes([189, 219, 127, 211, 78, 230, 97, 238])
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
def log(msg):
    with open(os.path.join(OUT, "tg_paper.log"), "a") as f: f.write(f"{datetime.datetime.utcnow():%H:%M:%S} {msg}\n")
def tg(text):
    if not TOKEN or not CHAT: log("telegram not configured"); return
    data = urllib.parse.urlencode(dict(chat_id=CHAT, text=text, disable_web_page_preview="true")).encode()
    for k in range(3):
        try:
            urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=data), timeout=15).read(); return
        except Exception as e:                                   # never log str(e): it can carry the request URL (token)
            log(f"telegram send failed: {e.__class__.__name__} {getattr(e, 'code', '')}"); time.sleep(2 + 3 * k)
STATE_F = os.path.join(OUT, "tg_paper_state.json")
ST = json.load(open(STATE_F)) if os.path.exists(STATE_F) else dict(n=0, first=0.0, real=0.0, wins_first=0, wins_real=0, grad=0, pos=0)
pend = {}; obs = {}; L = {}; trades = {}; done_chunks = set(); maxslot = [0]; sc_pos = [0]; lj_pos = [0]
def read_scores():
    if not os.path.exists(SC): return
    with open(SC) as f:
        f.seek(sc_pos[0])
        for l in f:
            if not l.endswith("\n"): break
            sc_pos[0] += len(l.encode())
            try: r = json.loads(l)
            except Exception: continue
            if r.get("type") == "decide" and r.get("final_pick") and r["mint"] not in CLOSED and r.get("t", 0) >= RESUME_T:
                m = r["mint"]; pend[m] = r; trades.setdefault(m, [])
                closed = sorted(done_chunks)                     # the collector lags ~15 s: its create may sit in the chunk that just closed
                if closed: done_chunks.discard(closed[-1])
                if r.get("t", 0) >= ANNOUNCE_T:                 # owner: BUY messages only (results are kept quietly, given on request)
                    x = r["features"]
                    tg(f"🟡 PAPER BUY (no money) | {r.get('final')}\n{m}\nscore {r['final_score']:+.2f} | dev {x.get('dev_buy', 0):.2f} SOL | bundle {x.get('glued_n')} tx / {x.get('glued_sol', 0):.2f} SOL"
                       f" | decided {r.get('at_ms', 0):.1f} ms after the create\nhttps://gmgn.ai/sol/token/{m}")
                log(f"pick {m}")
            elif r.get("type") == "obs" and r["mint"] in pend: obs[r["mint"]] = r
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
            L.setdefault(c["mint"], c)
def read_chunks():
    files = sorted(glob.glob(os.path.join(CRUN, "txs", "*.jsonl.gz")))
    for fn in files[:-1]:                                        # the newest chunk is still being written
        if fn in done_chunks: continue
        if pend:
            try:
                for l in gzip.open(fn, "rt"):
                    r = json.loads(l); maxslot[0] = max(maxslot[0], r["s"])
                    if not any(m in pend for m in r.get("mints") or []): continue
                    for j, e in enumerate(r.get("ev") or []):
                        try: raw = base64.b64decode(e + "=" * (-len(e) % 4))
                        except Exception: continue
                        if raw[:8] != DISC or len(raw) < 217: continue
                        m = b58(raw[8:40])
                        if m not in pend: continue
                        u = lambda o: int.from_bytes(raw[o:o + 8], "little")
                        trades[m].append(dict(s=r["s"], i=r["i"], j=j, sig=r["sig"], buy=raw[56] == 1, sol=u(40), tok=u(48), user=b58(raw[57:89]), vsol=u(97), vtok=u(105), fbps=u(161), cbps=u(209)))
            except (EOFError, OSError): pass
        done_chunks.add(fn)
def paper(m):
    r, c = pend[m], L[m]; S = c["slot"]; creator = c.get("creator") or c.get("user")
    tr = sorted({(t["sig"], t["j"]): t for t in trades.get(m, [])}.values(), key=lambda t: (t["s"], t["i"], t["j"]))
    ci = c.get("idx"); gl = []; prev = ci; gi = 0
    for k, t in enumerate(tr):
        if t["sig"] == c.get("sig"): gi = k + 1; continue
        if t["s"] == S and t["i"] in (prev, prev + 1) and t["buy"]: gl.append(t); prev = t["i"]; gi = k + 1
        elif t["s"] == S and t["i"] > prev + 1: break
        elif t["s"] > S: break
    bus = {t["user"] for t in gl}; outside = lambda t: t["user"] != creator and t["user"] not in bus
    o = obs.get(m) or {}
    land = float(r.get("at_ms", 0)) + LAND
    ahead = [x for x in (o.get("outs") or "-").split(",") if x and x != "-" and float(x.split(":")[0]) < land]
    res = {}
    for view, n_ahead in (("first", 0), ("real", len(ahead))):
        k0 = gi; n_o = 0
        while k0 < len(tr) and n_o < n_ahead:
            if outside(tr[k0]): n_o += 1
            k0 += 1
        st = tr[k0 - 1] if k0 > 0 else None
        V, T = (st["vsol"], st["vtok"]) if st else (30_000_000_000, 1_073_000_000_000_000)
        if not T or V >= 114e9: res[view] = dict(grad=True); continue
        fb, cb = ((tr[0]["fbps"] or 95), (tr[0]["cbps"] or 30)) if tr else (95, 30)
        q = T * X // (V + X); V += X; T -= q; cost = X * (1 + (fb + cb) / 1e4)
        val = lambda V, T: (V * q // (T + q)) * (1 - (fb + cb) / 1e4) / cost - 1
        trig = None; ret = None; grad = False
        for t in tr[k0:]:
            if trig is not None and t["s"] > trig["s"]: ret = val(V, T); break
            if t["s"] - S > CAP: ret = val(V, T); break
            if trig is None and t["vsol"] >= 114e9: grad = True
            if t["buy"]: dd = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= dd
            else: so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
            if trig is None and not t["buy"]: trig = t
        if ret is None: ret = val(V, T)
        who = None if trig is None else ("dev" if trig["user"] == creator else "bundle wallet" if trig["user"] in bus else "outside wallet")
        res[view] = dict(grad=grad, ret=ret, pnl=ret * SIZE - FIX, after=(st["sig"] if st else c.get("sig")), trig=trig, who=who,
                         exit_s=((trig["s"] - S) / 5) if trig else None, ahead=n_ahead)
    return res
def close_ready():
    for m in list(pend):
        c = L.get(m)
        if not c or maxslot[0] < c["slot"] + CAP + 20: continue
        res = paper(m); r = pend.pop(m); trades.pop(m, None)
        f, rl = res["first"], res["real"]
        if f.get("grad"):
            ST["grad"] += 1
            RES(f"⚪ PAPER RESULT {m[:6]}…: the curve filled (graduated) before our sell; the AMM price is not in our data, so it is NOT counted.\nhttps://gmgn.ai/sol/token/{m}")
        else:
            ST["n"] += 1; ST["first"] += f["pnl"]; ST["wins_first"] += f["pnl"] > 0
            if not rl.get("grad"): ST["real"] += rl["pnl"]; ST["wins_real"] += rl["pnl"] > 0
            ex = (f"sold at the first sell ({f['who']}, {f['exit_s']:.1f} s after the create)" if f["trig"] else "no sell within 30 s: sold at 30 s")
            RES(f"{'✅' if f['pnl'] > 0 else '❌'} PAPER RESULT {m[:6]}… (all costs counted)\n"
               f"first in line: {f['ret']:+.1%} -> {f['pnl']:+.4f} SOL\n"
               f"at our real 74 ms ({rl.get('ahead', 0)} ahead of us): " + ("curve filled, not counted" if rl.get("grad") else f"{rl['ret']:+.1%} -> {rl['pnl']:+.4f} SOL") + "\n"
               f"{ex}\n"
               f"buy right after https://solscan.io/tx/{f['after']}\n" + (f"sell trigger https://solscan.io/tx/{f['trig']['sig']}\n" if f["trig"] else "") +
               f"https://gmgn.ai/sol/token/{m}\n"
               f"TOTAL {ST['n']} trades: first in line {ST['first']:+.3f} SOL ({ST['wins_first']} wins) | at 74 ms {ST['real']:+.3f} SOL ({ST['wins_real']} wins)")
            with open(os.path.join(OUT, "tg_paper_trades.jsonl"), "a") as fo:
                fo.write(json.dumps(dict(mint=m, t=r["t"], score=r["final_score"], first=dict((k, v) for k, v in f.items() if k != "trig"),
                                         real=dict((k, v) for k, v in rl.items() if k != "trig"), exit_sig=f["trig"]["sig"] if f["trig"] else None)) + "\n")
        json.dump(ST, open(STATE_F, "w")); log(f"closed {m}")
os.makedirs(OUT, exist_ok=True)
# resume without losing open trades: picks of the last 15 min that have no RESULT yet are picked up again, and the
# chunks that can hold their trades (closed in the last 25 min) are read again
CLOSED = set()
if os.path.exists(os.path.join(OUT, "tg_paper_trades.jsonl")):
    for l in open(os.path.join(OUT, "tg_paper_trades.jsonl")):
        try: CLOSED.add(json.loads(l)["mint"])
        except Exception: pass
if os.path.exists(os.path.join(OUT, "tg_paper.log")):
    for l in open(os.path.join(OUT, "tg_paper.log")):
        if " closed " in l: CLOSED.add(l.split(" closed ")[1].strip())
RESUME_T = time.time() - 900; ANNOUNCE_T = time.time() - 60   # no repeat BUY messages for picks announced before a restart
def RES(text):                                              # RESULT messages: not sent to Telegram (owner), kept in a file
    with open(os.path.join(OUT, "tg_paper_results.txt"), "a") as f: f.write(text + "\n\n")
for fn in sorted(glob.glob(os.path.join(CRUN, "txs", "*.jsonl.gz")))[:-1]:
    if os.path.getmtime(fn) < time.time() - 1500: done_chunks.add(fn)
read_launches()
while True:
    try:
        read_scores(); read_launches(); read_chunks(); close_ready()
    except Exception as e:
        log(f"loop error: {e.__class__.__name__}: {str(e)[:200]}")
    time.sleep(5)
