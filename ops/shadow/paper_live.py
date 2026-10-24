#!/usr/bin/env python3
# PAPER TRADE of the FINAL CONFIG (read-only, offline, no money). Every forward launch the config's model picks
# (scored offline on the training table = the features the live scorer reproduces) is traded on paper:
#  - our place in the on-chain order: every OUTSIDE tx the shadow engine saw before our landing (its decision ms + the
#    measured landing ms) is ahead of us; launches the engine did not watch are left out (no timeline = no honest fill)
#  - fill and exit: exact bonding-curve replay of everyone's real trades from the collector (same math as training),
#    pump fee per side from the events, fixed cost per round trip
#  - also marks whether the LIVE shadow scorer picked the same launch (the live system finds these tokens by itself)
# usage: python3 paper_live.py <final_config.json> <table_all.jsonl.gz> <phaseA dir> <launches.jsonl> <scores.jsonl,...> <out dir>
import sys, os, json, gzip, glob, zlib, math, re, collections, datetime, statistics, warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
CFG, TAB, PA, LJ, SC, OUT = sys.argv[1:7]
C = json.load(open(CFG)); os.makedirs(OUT, exist_ok=True)
for k, f in (("land_ms", float), ("top", str), ("exit_fill", str), ("model_file", str)):     # sweep overrides: LAND_MS=35 TOP=1% ...
    if os.environ.get(k.upper()): C[k] = f(os.environ[k.upper()])
M = json.load(open(os.path.join(os.path.dirname(os.path.abspath(TAB)), C["model_file"])))
THR = M["thresholds"][C["top"]]; X = 493827160; FIX = C["fixed_cost_sol"]; SIZE = C["size_sol"]
MV = json.load(open(os.path.join(os.path.dirname(os.path.abspath(TAB)), C["veto_file"]))) if C.get("veto_file") else None   # fast-dump veto

def score(x, M=M):
    f = M["F0"]; bins = []
    for k, e in zip(M["features"], M["edges"]):
        if "==" in k:
            a, v = k.split("==", 1); val = 1.0 if str(x.get(a)) == v else 0.0
        else:
            v = x.get(k); val = float(v) if isinstance(v, (int, float)) and v is not None and not (isinstance(v, float) and math.isnan(v)) else float("nan")
        if math.isnan(val): bins.append(0); continue
        lo, hi = 0, len(e)
        while lo < hi:
            mid = (lo + hi) // 2
            if e[mid] <= val: lo = mid + 1
            else: hi = mid
        bins.append(lo + 1)
    for t in M["trees"]:
        n = t
        while "w" not in n: n = n["l"] if bins[n["f"]] <= n["b"] else n["r"]
        f += M["lr"] * n["w"]
    return f

# ---- shadow engine timeline (decision ms, outside txs) + live picks
dec, obs, live_pick = {}, {}, {}
for p in SC.split(","):
    if not os.path.exists(p): continue
    for l in open(p):
        try: r = json.loads(l)
        except Exception: continue
        if r.get("type") == "decide":
            dec[r["mint"]] = r
            if r.get("final") == C["name"]:            # the live scorer ran this very config
                if r.get("quote") == "sol": live_pick[r["mint"]] = bool(r.get("final_pick"))
            elif r.get("other") is not None and not C.get("veto_file"):   # fixed scorer (score = LIVE2, other = [LIVE]); the first run's features had parity bugs
                sc = r["score"] if M.get("featset") == "liveh2" else next((o["score"] for o in r["other"] if o.get("featset") == M.get("featset")), None)
                if sc is not None and r.get("quote") == "sol": live_pick[r["mint"]] = sc >= THR
        elif r.get("type") == "obs": obs[r["mint"]] = r
L = {}
for l in open(LJ):
    try: c = json.loads(l)
    except Exception: continue
    L.setdefault(c["mint"], c)
# ---- offline picks on the forward table (watched launches only)
rows = []
t_first = min((d["t"] for d in dec.values()), default=0); t_last = max((d["t"] for d in dec.values()), default=0)
for l in gzip.open(TAB, "rt"):
    r = json.loads(l)
    if r["mint"] not in dec or not r.get("bt"): continue
    if r.get("quote_sol") != 1 or dec[r["mint"]].get("quote", "sol") != "sol": continue
    r["_score"] = score(r); r["_veto"] = score(r, MV) if MV else None; rows.append(r)
data_end = max((c.get("bt") or 0) for c in L.values())
def guard_ok(r):
    g = C.get("guards", [])
    if "payer_is_creator" in g and r.get("payer_is_creator") != 1: return False
    if "no_bundle_small_dev" in g and (r.get("glued_n") or 0) == 0 and (r.get("dev_buy") or 0) < 1: return False
    return True
picks = [r for r in rows if r["_score"] >= THR and (MV is None or r["_veto"] < C["veto_cut"]) and guard_ok(r) and r["bt"] <= data_end - 120]

def bucket(m): return zlib.crc32(m.encode()) % 256
def trades_of(m):
    tr = []; seen = set()
    for f in glob.glob(os.path.join(PA, f"b{bucket(m):03d}", "*.jsonl.gz")):
        try:
            for line in gzip.open(f, "rt"):
                if m not in line: continue
                r = json.loads(line)
                if r[0] != "T" or r[1] != m: continue
                (_, _, s, i, bt, sig, payer, fee, cup, cul, cu, tips, err, j, user, buy, sol, tok, vsol, vtok, fl, cfl, fbps, cbps) = r
                if (sig, j) in seen: continue
                seen.add((sig, j)); tr.append(dict(s=s, i=i, j=j, sig=sig, payer=payer, user=user, buy=buy == 1, sol=sol, tok=tok, vsol=vsol, vtok=vtok, fbps=fbps, cbps=cbps))
        except (EOFError, OSError): pass
    tr.sort(key=lambda t: (t["s"], t["i"], t["j"])); return tr

def paper(r):
    m = r["mint"]; c = L[m]; S = c["slot"]; creator = c.get("creator") or c.get("user"); tr = trades_of(m)
    d, o = dec[m], obs.get(m)
    if o is None: return dict(skip="no engine timeline")
    land = float(d.get("at_ms", 0)) + C["land_ms"]
    outs = [x.split(":") for x in (o.get("outs") or "-").split(",") if x and x != "-"]
    ahead = [x for x in outs if float(x[0]) < land]
    # glued bundle exactly as training
    ci = c.get("idx"); g = []; prev = ci; gi = 0
    for k, t in enumerate(tr):
        if t["sig"] == c.get("sig"): gi = k + 1; continue
        if t["s"] == S and t["i"] in (prev, prev + 1) and t["buy"]: g.append(t); prev = t["i"]; gi = k + 1
        elif t["s"] == S and t["i"] > prev + 1: break
        elif t["s"] > S: break
    busers = {t["user"] for t in g}
    k0 = gi; n_o = 0
    while k0 < len(tr) and n_o < len(ahead):
        if tr[k0]["user"] != creator and tr[k0]["user"] not in busers: n_o += 1
        k0 += 1
    st = tr[k0 - 1] if k0 > 0 else None
    V, T = (st["vsol"], st["vtok"]) if st else (30_000_000_000, 1_073_000_000_000_000)
    if not T: return dict(skip="no curve state")
    fb, cb = ((tr[0]["fbps"] or 95), (tr[0]["cbps"] or 30)) if tr else (95, 30)
    mc_in = V / T * 1e6
    q = T * X // (V + X); V += X; T -= q; cost = X * (1 + (fb + cb) / 1e4)
    val = lambda V, T: (V * q // (T + q)) * (1 - (fb + cb) / 1e4) / cost - 1
    trig = None; r_inst = r_eos = None; r_cap = None; ex_slot = None; grad = False
    for k in range(k0, len(tr)):
        t = tr[k]
        if trig is None and t["vsol"] >= 114e9: grad = True    # curve complete before our sell: it moves to the AMM, whose price we don't have
        if trig is not None and t["s"] > trig["s"]: r_eos = val(V, T); break
        if t["s"] - S > C["cap_slots"]:
            r_cap = val(V, T); break
        if t["buy"]: dd = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= dd
        else: so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
        if trig is None and not t["buy"]: trig = t; r_inst = val(V, T)
    if trig is not None and r_eos is None: r_eos = val(V, T)
    if trig is None: r_inst = r_eos = r_cap if r_cap is not None else val(V, T)
    rr = r_eos if C["exit_fill"] == "eos" else r_inst
    return dict(mint=m, t=datetime.datetime.utcfromtimestamp(r["bt"]).strftime("%H:%M:%S"), score=round(r["_score"], 3), live_pick=live_pick.get(m),
                dev_buy=round(r.get("dev_buy") or 0, 3), glued_n=r.get("glued_n"), glued_sol=round(r.get("glued_sol") or 0, 3), mc_in_sol=round(mc_in, 1),
                decide_ms=float(d.get("at_ms", 0)), land_ms=round(land, 1), ahead_n=len(ahead), ahead=[f"{x[3]}@{x[0]}ms" for x in ahead][:6],
                entry_after_tx=st["sig"] if st else c.get("sig"), create_tx=c.get("sig"),
                exit_trigger_tx=trig["sig"] if trig else None, exit_trigger_wallet=trig["user"] if trig else None,
                exit_trigger_who=("dev" if trig and trig["user"] == creator else "bundle" if trig and trig["user"] in busers else "outside" if trig else None),
                exit_slot=(trig["s"] - S) if trig else None, ret_eos=round(r_eos, 4), ret_instant=round(r_inst, 4),
                pnl_sol=round(rr * SIZE - FIX, 4), pnl_sol_instant=round(r_inst * SIZE - FIX, 4), fast_dump=r.get("y_dump5"), good=r.get("y_good"), graduated=grad)

res = [paper(r) for r in sorted(picks, key=lambda r: r["bt"])]
grads = [x for x in res if "skip" not in x and x["graduated"]]
done = [x for x in res if "skip" not in x and not x["graduated"]]
def summ(v):
    if not v: return "n=0"
    w = sum(1 for a in v if a > 0)
    return f"n={len(v)} win={w / len(v):.0%} mean={statistics.mean(v):+.4f} SOL median={statistics.median(v):+.4f} total={sum(v):+.3f} SOL"
hours = max((t_last - t_first) / 3600, 1e-9)
lines = [f"=== PAPER TRADE {C['name']}: {C['what']} ===",
         f"model {M.get('featset')} top {C['top']} (score >= {THR:.3f}){' minus fast-dump veto (score >= %.3f)' % C['veto_cut'] if MV else ''}, SOL-quoted, {SIZE} SOL/trade, landing {C['land_ms']} ms after the engine's bundle decision, exit fill {C['exit_fill']}, fixed {FIX} SOL/round trip",
         f"watched window {datetime.datetime.utcfromtimestamp(t_first):%H:%M}-{datetime.datetime.utcfromtimestamp(t_last):%H:%M} UTC ({hours:.2f} h), SOL launches scored {len(rows)}, picks {len(picks)}, traded {len(done)}, skipped {len(res) - len(done)}",
         f"RESULT (eos exit):     {summ([x['pnl_sol'] for x in done])}  ->  {sum(x['pnl_sol'] for x in done) / hours:+.2f} SOL/h",
         f"RESULT (instant exit): {summ([x['pnl_sol_instant'] for x in done])}",
         f"fast dumpers (price <= 0.85x within 5 s of the bundle): {sum(1 for x in done if x['fast_dump'])} of {sum(1 for x in done if x['fast_dump'] is not None)}; good tokens: {sum(1 for x in done if x['good'])}",
         f"by place in line:  " + "  ".join(f"{k} ahead: {summ([x['pnl_sol'] for x in done if min(x['ahead_n'], 3) == k])}" for k in range(4)),
         f"left out: {len(grads)} graduated before our sell (curve filled, trading moved to the AMM: no honest exit price in our data): " + " ".join(x["mint"] for x in grads),
         f"live scorer picked the same launch: {sum(1 for x in done if x['live_pick'])} of {sum(1 for x in done if x['live_pick'] is not None)} scored live", ""]
for x in done:
    lines.append(f"{x['t']} {x['mint']}  score {x['score']:+.2f} live_pick={x['live_pick']}  dev {x['dev_buy']} SOL, bundle {x['glued_n']} tx / {x['glued_sol']} SOL, MC in {x['mc_in_sol']} SOL")
    lines.append(f"   ahead of us: {x['ahead_n']} {' '.join(x['ahead'])}  | exit: first sell by {x['exit_trigger_who']} {x['exit_trigger_wallet']} at slot +{x['exit_slot']}  | ret eos {x['ret_eos']:+.1%} instant {x['ret_instant']:+.1%}  PnL {x['pnl_sol']:+.4f} SOL")
    lines.append(f"   gmgn https://gmgn.ai/sol/token/{x['mint']}  create https://solscan.io/tx/{x['create_tx']}")
    lines.append(f"   we fill right after https://solscan.io/tx/{x['entry_after_tx']}  exit trigger https://solscan.io/tx/{x['exit_trigger_tx']}")
for x in res:
    if "skip" in x: pass
open(os.path.join(OUT, "paper_trades.txt"), "w").write("\n".join(lines) + "\n")
json.dump(dict(config=C, threshold=THR, trades=done, n_skipped=len(res) - len(done)), open(os.path.join(OUT, "paper_trades.json"), "w"), indent=1)
print("\n".join(lines[:8]))
