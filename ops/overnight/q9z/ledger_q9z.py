#!/usr/bin/env python3
# READ-ONLY, offline: 9qz7cW's ledger over the owner's RPC horizon (10-20 13:14 -> now). Every signature is placed:
#   - fetched raw tx (txc/): exact SOL change, every token change of its accounts, pump.fun trade events, SOL transfers
#   - collector raw tx (raw_q9z): exact SOL change + launch-token change (its quote leg is fetched separately for
#     non-SOL-quoted tokens, so those come from txc)
#   - not fetched: failed txs (fee estimated from the measured fees of its failed txs of the same hour) and successful
#     txs in the ODD UTC hours of the older period (10-20 13:14 -> 10-21 15:00, a 50% hour-block sample, scaled x2)
# Value of a tx = SOL change + (quote / stable token changes x current price in SOL). Launch (meme) tokens are not
# valued per tx; what is still held now is listed. Categories: trading / failed-tx fees / transfers (deposit, withdrawal) /
# other. Per token: realized result, venue, behaviour (from the collector: snipe = first attempt in the create slot or
# the next; later = >= 2 slots after). Cross-check: SOL balance change over the fully fetched 36 h window.
import os, json, gzip, glob, collections, datetime, statistics, base64
HERE = os.path.dirname(os.path.abspath(__file__)); W = "9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw"
WSOL = "So11111111111111111111111111111111111111112"; TM = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"; PAMM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"; ROUTER = "2eFuLSK4McKonBcB6XLax8gSgxwR56zNfrjHsvkNkftj"
OTHER_DEX = {"LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj": "LaunchLab", "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C": "Raydium CPMM", "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium AMM",
             "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": "Raydium CLMM", "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Orca", "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo": "Meteora DLMM",
             "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG": "Meteora DAMM", "dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN": "Meteora DBC", "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter"}
FULL_FROM = 1792594800
PR = json.load(open(os.path.join(HERE, "prices.json"))); SOLUSD = PR["sol_usd"]; PX = {m: v["usd"] / SOLUSD for m, v in PR["prices"].items()}
Q = json.load(open(os.path.join(HERE, "quote_by_mint.json")))
QUOTES = {q for q in Q.values() if q not in ("SOL", "old-event")} | {"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB", "USD1ttGY1N17NEEHLmELoaybftRBUSErhqYiQzvEmuB", WSOL}
PL = json.load(open(os.path.join(HERE, "perlaunch_q9z.json")))
S = json.load(open(os.path.join(HERE, "sigs.json")))
PLAN = json.load(open(os.path.join(HERE, "fetch_plan.json")))
RAW = {}
for l in gzip.open(os.path.join(HERE, "raw_q9z.jsonl.gz"), "rt"):
    r = json.loads(l); RAW[r[4]] = r
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238])
import sys; sys.path.insert(0, HERE)
from v3event import decode as v3decode
EVQUOTES = set()
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
def parse_txc(sig):
    f = os.path.join(HERE, "txc", sig + ".json.gz")
    if not os.path.exists(f): return None
    try: tx = json.load(gzip.open(f, "rt"))
    except Exception: return None
    m = tx["transaction"]["message"]; meta = tx["meta"]
    keys = [k["pubkey"] for k in m["accountKeys"]]
    i = keys.index(W) if W in keys else None
    sol = (meta["postBalances"][i] - meta["preBalances"][i]) / 1e9 if i is not None else 0.0
    pre = {b["accountIndex"]: b for b in meta.get("preTokenBalances") or []}; post = {b["accountIndex"]: b for b in meta.get("postTokenBalances") or []}
    tok = collections.defaultdict(float)
    for ai in set(pre) | set(post):
        b = post.get(ai) or pre.get(ai)
        if b.get("owner") != W: continue
        a0 = float(((pre.get(ai) or {}).get("uiTokenAmount") or {}).get("uiAmount") or 0); a1 = float(((post.get(ai) or {}).get("uiTokenAmount") or {}).get("uiAmount") or 0)
        if a1 != a0: tok[b["mint"]] += a1 - a0
    progs = {ix.get("programId") for ix in m["instructions"]} | {ix.get("programId") for inn in (meta.get("innerInstructions") or []) for ix in inn["instructions"]}
    xin, xout, tips = [], [], []
    for ix in list(m["instructions"]) + [ix for inn in (meta.get("innerInstructions") or []) for ix in inn["instructions"]]:
        p = ix.get("parsed")
        if isinstance(p, dict) and p.get("type") in ("transfer", "transferWithSeed") and isinstance(p.get("info"), dict) and "lamports" in p["info"]:
            inf = p["info"]
            if inf.get("source") == W:
                d = inf.get("destination")
                (tips if d in TM else xout).append((d, inf["lamports"] / 1e9))
            elif inf.get("destination") == W: xin.append((inf.get("source"), inf["lamports"] / 1e9))
        if isinstance(p, dict) and p.get("type") in ("createAccount", "createAccountWithSeed") and isinstance(p.get("info"), dict) and p["info"].get("source") == W:
            xout.append(("__create:" + str(p["info"].get("newAccount"))[:8], p["info"].get("lamports", 0) / 1e9))
    ev = []
    for l in meta.get("logMessages") or []:
        if not l.startswith("Program data: "): continue
        e3 = v3decode(l[14:])
        if e3 and e3["user"] == W:
            ev.append((e3["mint"], e3["buy"], e3["sol"] / 1e9))
            if e3.get("quote"): EVQUOTES.add(e3["quote"])
            continue
        s = l[14:].strip(); s += "=" * (-len(s) % 4)
        try: raw = base64.b64decode(s)
        except Exception: continue
        if raw[:8] == TD and len(raw) >= 129 and b58(raw[57:89]) == W: ev.append((b58(raw[8:40]), raw[56] == 1, int.from_bytes(raw[40:48], "little") / 1e9))
    cfg = m.get("transactionConfig") or {}
    return dict(sol=sol, tok=dict(tok), progs=progs, xin=xin, xout=xout, tips=tips, ev=ev, fee=meta["fee"] / 1e9, err=meta.get("err") is not None,
                ver=tx.get("version"), prio=(cfg.get("priorityFee") or 0) / 1e9, pre_bal=meta["preBalances"][i] / 1e9 if i is not None else None,
                post_bal=meta["postBalances"][i] / 1e9 if i is not None else None, slot=tx["slot"], bt=tx.get("blockTime"))
EVQ = json.load(open(os.path.join(HERE, "ev_q9z.json")))          # decoded pump.fun V3 events (quote leg) of its raw collector txs
DEC = {m: v.get("dec") for m, v in PR["prices"].items() if v.get("dec") is not None}
for h in json.load(open(os.path.join(HERE, "holdings_now.json")))["tokens"]: DEC.setdefault(h["mint"], h["dec"])
NODEC = collections.Counter()
def from_raw(r):
    tok = {}
    for x in r[14]:
        if len(x) >= 4: tok[x[0]] = tok.get(x[0], 0) + ((x[3] or 0) - (x[2] or 0)) / 1e6
    for e in EVQ.get(r[4], []):                                        # quote-token leg of non-SOL-quoted trades (exact, from the event)
        if not e.get("quote") or e.get("qamt") is None: continue
        d = DEC.get(e["quote"])
        if d is None: NODEC[e["quote"]] += 1; continue
        q = (-(e["qamt"] + e["fee"] + e["cfee"]) if e["buy"] else (e["qamt"] - e["fee"] - e["cfee"])) / 10 ** d
        tok[e["quote"]] = tok.get(e["quote"], 0) + q
    progs = set(r[10])
    return dict(sol=r[13] / 1e9, tok=tok, progs=progs, xin=[], xout=[], tips=[(a, l / 1e9) for a, l in r[12]], ev=[(m, None, None) for m in r[9][:1]] if any(("Buy" in x or "Sell" in x) for x in r[11]) else [],
                fee=(r[6] or 0) / 1e9, err=bool(r[5]), ver=None, prio=max(0, (r[6] or 5000) - 5000) / 1e9, pre_bal=None, post_bal=None, slot=r[1], bt=r[3], mints=r[9])
hr = lambda bt: datetime.datetime.fromtimestamp(bt, datetime.timezone.utc).strftime("%m-%d %H") if bt else "?"
day = lambda bt: datetime.datetime.fromtimestamp(bt, datetime.timezone.utc).strftime("%m-%d") if bt else "?"
X = []
for s in S:
    sig = s["signature"]; bt = s.get("blockTime"); e = s.get("err") is not None
    d = parse_txc(sig)
    src = "txc" if d else None
    if d is None and sig in RAW: d = from_raw(RAW[sig]); src = "raw"
    if d is None:
        old = (bt or 0) < FULL_FROM
        d = dict(missing=True, err=e, slot=s["slot"], bt=bt, odd_hour_skipped=(not e) and old and int(hr(bt)[-2:]) % 2 == 1 if bt else False)
        src = "missing"
    d["sig"] = sig; d["src"] = src; d["slot"] = s["slot"]; d["bt"] = bt; d["err"] = e
    X.append(d)
print("signatures", len(X), collections.Counter((x["src"], x["err"]) for x in X), "| quote legs without decimals:", sum(NODEC.values()))
EVQUOTES |= {e["quote"] for v in EVQ.values() for e in v if e.get("quote")}
MAJORS = {"DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", "PEPEqnuuCDbBC89p1u9vpnP1KQ2oj1xTcQBsjt9X55m", "shib5gSoVKPjwkXrxRk7SbQFzb2R9rQB3TgQWYX4RwW", "pumpCmXqMfrsAkQ5r49WcJnRayYRqmXz6ae8H7H9Dfn"}
STABLELIKE = {m for m, v in PR["prices"].items() if (v.get("usd") or 0) >= 0.5 and (v.get("liq") or 0) >= 20000}   # USD-pegged / liquid majors held as inventory
QUOTES |= EVQUOTES | MAJORS | STABLELIKE
print("quote / inventory mints:", len(QUOTES))
# ---- failed-tx fee model: measured failed fees by hour (collector + fetched sample); unknown ones get the hour's mean
ff = collections.defaultdict(list)
for x in X:
    if x["err"] and x["src"] != "missing": ff[hr(x["bt"])].append(x["fee"])
allf = [f for v in ff.values() for f in v]
glob_mean = statistics.mean(allf)
samp = [x["fee"] for x in X if x["err"] and x["src"] == "txc"]
print(f"failed fees measured: {len(allf)} txs, mean {glob_mean:.6f} SOL (fetched random sample: n {len(samp)}, mean {statistics.mean(samp) if samp else 0:.6f})")
samp_mean = statistics.mean(samp) if samp else glob_mean
# ---- classify
def qval(tok):
    return sum(v * PX.get(m, 0) for m, v in tok.items() if m in QUOTES)
def main_mint(x):
    ms = [m for m, v in (x.get("tok") or {}).items() if m not in QUOTES and abs(v) > 0]
    if x.get("ev"): return x["ev"][0][0]
    if ms: return ms[0]
    if x.get("mints"): return x["mints"][0]
    return None
def venue(x):
    p = x.get("progs") or set()
    if PAMM in p: return "PumpSwap AMM (graduated)"
    for k, v in OTHER_DEX.items():
        if k in p: return v
    if PUMP in p or ROUTER in p:
        mm = main_mint(x); qq = Q.get(mm)
        if qq == "SOL": return "pump.fun curve, SOL"
        if qq and qq != "SOL": return "pump.fun curve, non-SOL quote"
        if any(m in QUOTES and m != WSOL and m != mm for m, v in (x.get("tok") or {}).items() if abs(v) > 0): return "pump.fun curve, non-SOL quote"
        return "pump.fun curve, SOL"
    return "other"
for x in X:
    if x["src"] == "missing":
        if x["err"]: x["kind"] = "failed"; x["val"] = -samp_mean; x["est"] = True
        else: x["kind"] = "unfetched (odd-hour sample gap)"; x["val"] = 0.0; x["est"] = True
        continue
    x["val"] = x["sol"] + qval(x.get("tok") or {})
    other_tok = any(m not in QUOTES and abs(v) > 0 for m, v in (x.get("tok") or {}).items())
    qmove = any(m in QUOTES and m != WSOL and abs(v) > 0 for m, v in (x.get("tok") or {}).items())
    if x["err"]: x["kind"] = "failed"
    elif x.get("ev") or other_tok: x["kind"] = "trading"
    elif qmove and (x["progs"] & ({PAMM, PUMP, ROUTER} | set(OTHER_DEX))): x["kind"] = "quote swap"
    elif x.get("xin") and abs(x["val"]) >= 0.01 and x["val"] > 0: x["kind"] = "deposit"
    elif x.get("xout") and x["val"] <= -0.01 and not any(d.startswith("__create") for d, _ in x["xout"]): x["kind"] = "withdrawal"
    else: x["kind"] = "other"
    if x["kind"] in ("trading", "quote swap"): x["mint"] = main_mint(x); x["venue"] = venue(x)
K = collections.Counter(x["kind"] for x in X); print("kinds", K)
# ---- totals per period
def period(bt):
    if not bt: return "?"
    return "36h full (10-21 15:00 -> now)" if bt >= FULL_FROM else "older 10-20 13:14 -> 10-21 15:00 (even hours fetched)"
tot = collections.defaultdict(collections.Counter)
for x in X:
    tot[period(x["bt"])][x["kind"]] += x["val"]
for p_, c in tot.items():
    print(f"\n== {p_}: " + " | ".join(f"{k} {v:+.2f}" for k, v in sorted(c.items())))
# ---- cross-check on the full 36 h window: SOL balance change vs sum of SOL changes
win = sorted([x for x in X if (x["bt"] or 0) >= FULL_FROM], key=lambda x: (x["slot"]))
first = next((x for x in win if x["src"] == "txc" and x.get("pre_bal") is not None), None)
H = json.load(open(os.path.join(HERE, "holdings_now.json")))
last = max((x for x in win if x["src"] == "txc" and x.get("post_bal") is not None), key=lambda x: x["slot"])
known_sol = sum(x["sol"] for x in win if x["src"] != "missing" and x["slot"] >= first["slot"] and x["slot"] <= last["slot"]) - first["sol"] + first["sol"]
n_unknown_fail = sum(1 for x in win if x["src"] == "missing" and x["err"] and first["slot"] <= x["slot"] <= last["slot"])
bal_chg = last["post_bal"] - first["pre_bal"]
gap = bal_chg - known_sol
print(f"\n== cross-check 36 h: SOL balance {first['pre_bal']:.4f} (slot {first['slot']}) -> {last['post_bal']:.4f} (slot {last['slot']}) = {bal_chg:+.4f}; sum of known SOL changes {known_sol:+.4f}; "
      f"gap {gap:+.4f} over {n_unknown_fail} unfetched failed txs = {(-gap / n_unknown_fail) if n_unknown_fail else 0:.6f} SOL each (estimate used: {samp_mean:.6f})")
FAIL_EACH = (-gap / n_unknown_fail) if n_unknown_fail and gap < 0 else samp_mean
for x in X:
    if x["src"] == "missing" and x["err"]: x["val"] = -FAIL_EACH
tot = collections.defaultdict(collections.Counter)
for x in X: tot[period(x["bt"])][x["kind"]] += x["val"]
for p_, c in tot.items():
    print(f"== FINAL {p_}: " + " | ".join(f"{k} {v:+.2f}" for k, v in sorted(c.items())) + f" | PnL ex transfers {sum(v for k, v in c.items() if k not in ('deposit', 'withdrawal')):+.2f}")
# ---- per token (trading + failed with a known mint)
T = collections.defaultdict(lambda: dict(val=0.0, n=0, buys=0, sells=0, venue=None, t0=None, t1=None, sol_in=0.0, fail=0.0, nfail=0))
for x in sorted(X, key=lambda x: x["slot"]):
    if x["kind"] == "trading" and x.get("mint"):
        t = T[x["mint"]]; t["val"] += x["val"]; t["n"] += 1; t["venue"] = t["venue"] or x["venue"]
        isbuy = any(e[1] for e in x.get("ev") or [] if e[1] is not None) or (x.get("tok", {}).get(x["mint"], 0) > 0)
        if isbuy: t["buys"] += 1; t["sol_in"] += max(0, -x["val"]); t["t0"] = t["t0"] or x["bt"]
        else: t["sells"] += 1; t["t1"] = x["bt"]
    elif x["kind"] == "failed" and x["src"] != "missing":
        mm = (x.get("mints") or [None])[0] or main_mint(x)
        if mm: t = T[mm]; t["fail"] += x["val"]; t["nfail"] += 1
for m, t in T.items():
    p = PL.get(m); t["beh"] = p["beh"] if p else None; t["d0"] = day(t["t0"] or t["t1"])
    t["held"] = None
held = {h["mint"]: h["ui"] for h in H["tokens"] if h["ui"]}
# ---- report
def show(name, rows, key):
    g = collections.defaultdict(lambda: [0, 0.0, 0.0, 0])
    for t in rows:
        k = key(t); a = g[k]; a[0] += 1; a[1] += t["val"]; a[2] += t["fail"]; a[3] += t["val"] > 0
    print(f"\n== by {name}: tokens | trading result SOL | failed-tx fees on them | win")
    for k, (n, v, f, wn) in sorted(g.items(), key=lambda kv: str(kv[0])): print(f"   {str(k):40} {n:5d} {v:+9.2f} {f:+8.2f}  {wn / n:.0%}")
TR = [t for t in T.values() if t["n"]]
show("venue", TR, lambda t: t["venue"])
show("behaviour (collector launches; others = outside the collector or not first-bought by it)", TR, lambda t: t["beh"] or "unknown")
show("day (UTC of first trade)", TR, lambda t: t["d0"])
show("day x behaviour", TR, lambda t: (t["d0"], t["beh"] or "unknown"))
dd = collections.defaultdict(collections.Counter); ddp = collections.defaultdict(collections.Counter)
for x in X:
    dd[day(x["bt"])][x["kind"]] += x["val"]
    ddp[day((x["bt"] or 0) + 5 * 3600) if x["bt"] else "?"][x["kind"]] += x["val"]          # PKT day (UTC+5)
    if x["kind"] == "trading": ddp[day((x["bt"] or 0) + 5 * 3600)]["trading:" + (PL[x["mint"]]["beh"] if x.get("mint") in PL else "outside")] += x["val"]
    if x["kind"] == "failed": ddp[day((x["bt"] or 0) + 5 * 3600)]["failed:" + ("estimated" if x.get("est") else "measured")] += x["val"]
print("\n== per UTC day, all categories (failed = measured + estimated):")
for d_, c in sorted(dd.items()): print(f"   {d_}: " + " | ".join(f"{k} {v:+.2f}" for k, v in sorted(c.items())) + f" | net ex deposits/withdrawals {sum(v for k, v in c.items() if k not in ('deposit', 'withdrawal')):+.2f}")
# transfers
xf = collections.defaultdict(lambda: [0, 0.0])
for x in X:
    if x["kind"] in ("deposit", "withdrawal"):
        cps = x["xin"] if x["kind"] == "deposit" else x["xout"]
        for cp, l in cps: a = xf[(x["kind"], cp)]; a[0] += 1; a[1] += l
print("\n== deposits / withdrawals (counterparty, n, SOL):")
for (k, cp), (n, l) in sorted(xf.items(), key=lambda kv: -kv[1][1])[:20]: print(f"   {k:10} {cp} {n:4d} {l:9.3f}")
oth = collections.defaultdict(lambda: [0, 0.0])
for x in X:
    if x["kind"] == "other":
        k = tuple(sorted({(d[:12] if not d.startswith("__") else d[:9]) for d, _ in x.get("xout") or []} | {"in:" + (s_ or "")[:8] for s_, _ in x.get("xin") or []}))[:3] or ("no transfer",)
        a = oth[k]; a[0] += 1; a[1] += x["val"]
print("\n== other txs (top):")
for k, (n, v) in sorted(oth.items(), key=lambda kv: kv[1][1])[:12]: print(f"   {str(k):70} {n:5d} {v:+.4f}")
json.dump(dict(fail_each=FAIL_EACH, samp_mean=samp_mean, n=len(X), kinds=dict(K), totals={p_: dict(c) for p_, c in tot.items()},
               cross=dict(first_slot=first["slot"], pre=first["pre_bal"], last_slot=last["slot"], post=last["post_bal"], known=known_sol, gap=gap, n_unknown_fail=n_unknown_fail),
               tokens={m: t for m, t in T.items()}, per_day={d_: dict(c) for d_, c in dd.items()}, per_day_pkt={d_: dict(c) for d_, c in ddp.items()}, xfers=[[k, cp, n, l] for (k, cp), (n, l) in xf.items()]),
          open(os.path.join(HERE, "ledger_q9z.json"), "w"), default=str)
# ---- hourly SOL balance (from fetched txs' pre/post balances: first and last fetched tx of each hour), PKT = UTC+5
hb = {}
for x in sorted([x for x in X if x["src"] == "txc" and x.get("pre_bal") is not None], key=lambda x: x["slot"]):
    h = hr(x["bt"])
    if h not in hb: hb[h] = [x["pre_bal"], x["post_bal"], x["slot"], x["slot"]]
    else: hb[h][1] = x["post_bal"]; hb[h][3] = x["slot"]
wd_h = collections.defaultdict(float)
for x in X:
    if x["kind"] == "withdrawal": wd_h[hr(x["bt"])] += x["val"]
print("\n== hourly SOL balance (UTC hour: start -> end of the fetched txs; withdrawals seen that hour):")
for h in sorted(hb): print(f"   {h} UTC: {hb[h][0]:9.3f} -> {hb[h][1]:9.3f}  withdrawals {wd_h.get(h, 0):+.2f}")
json.dump(dict(hourly=hb, withdrawals_by_hour=dict(wd_h)), open(os.path.join(HERE, "ledger_hourly.json"), "w"))
# ---- quote-inventory change over the fully read 36 h window, and the implied balance at its start (must be >= 0)
inv = collections.defaultdict(float)
for x in X:
    if x["src"] == "missing" or (x["bt"] or 0) < FULL_FROM: continue
    for m, v in (x.get("tok") or {}).items():
        if m in QUOTES: inv[m] += v
now = {h["mint"]: h["ui"] for h in H["tokens"]}; now[WSOL] = now.get(WSOL, 0)
rows = sorted(((m, d, d * PX.get(m, 0), now.get(m, 0)) for m, d in inv.items()), key=lambda r: -abs(r[2]))
print("\n== quote inventory change over the 36 h window (top 15 by SOL value at current prices): mint | change | SOL value | balance now | implied balance at start")
for m, d, v, n in rows[:15]: print(f"   {m[:8]} {d:+16,.4f} {v:+9.2f} {n:16,.4f} {n - d:16,.4f}")
neg = [(m[:8], round(n - d, 4)) for m, d, v, n in rows if n - d < -1e-6 * max(1, abs(d))]
print(f"   total inventory change {sum(r[2] for r in rows):+.2f} SOL over {len(rows)} mints; mints whose implied start balance is negative: {len(neg)} {neg[:8]}")
json.dump(dict(inv_change={m: [d, v, n] for m, d, v, n in rows}), open(os.path.join(HERE, "ledger_inventory.json"), "w"))
