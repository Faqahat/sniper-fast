#!/usr/bin/env python3
# PASS 2 (read-only): which wallets make money sniping new pump.fun launches, and where do they land?
# Input: w1_pairs.py output of both runs (pairs/, other/, launch/), the shadow engine timelines (obs), optional exact
# SOL-delta rows from w3_sd.py. Output: wallets.json (per-wallet stats), cands.json (wallet list for w3_sd.py), summary.
# usage: python3 -I w2_wallets.py <work dir> <out dir> [sd_R1.jsonl.gz,sd_R2.jsonl.gz]
import sys, os, json, gzip, glob, collections, statistics, re, datetime
WORK, OUTD = sys.argv[1], sys.argv[2]; SDF = sys.argv[3].split(",") if len(sys.argv) > 3 and sys.argv[3] else []
RUNS = ["R1", "R2"]; SNIPE = 5; MIN_TOK = 15; MIN_RUN = 6
AGENTS = {"BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s"}          # pump.fun mayhem agent (not a trader)
FOCUS = ["9Sh2fdqMQcec7W9LzzfvkYphrdyR3S8aUBsKdv9xNYa1", "DGmspiBs2ePJ7WgN1pyX5RJDpzhyxYrBN1P4bXNC1NR3", "D24ipYXuDt6PXEPV6rZqfWb35WJaTJW3gDoXwt7yJCwQ"]
SHADOW = "/home/moiz/sniper-data/collect/shadow"
KNOWN = {w: k + 1 for k, w in enumerate(dict.fromkeys(re.findall(r'gmgn\.ai/sol/address/([1-9A-HJ-NP-Za-km-z]{32,44})',
         open("/home/moiz/sniper/ops/snipers/CANDIDATES.md").read())))}
TIPMAP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
med = lambda xs: statistics.median(xs) if xs else None
def q(xs, p):
    if not xs: return None
    xs = sorted(xs); return xs[min(len(xs) - 1, int(p * (len(xs) - 1) + 0.5))]
BAD = ["nigg", "nigr", "niga", "fagg", "faggot", "retard", "kike", "chink", "spic", "tranny", "cunt", "fuck", "shit", "bitch", "whore",
       "slut", "rape", "hitler", "nazi", "coon", "dyke", "negro", "neeg", "jew", "pussy", "dick", "cock", "porn", "sex", "anal"]
BADRE = re.compile("|".join(BAD), re.I)
def mask(s): return BADRE.sub("[masked]", s or "")

# ---------- launches ----------
LI = {}; SIGN = {r: collections.Counter() for r in RUNS}; RUNT = {}
for run in RUNS:
    ts = []
    for f in sorted(glob.glob(os.path.join(WORK, run, "launch", "*.jsonl.gz"))):
        for l in gzip.open(f, "rt"):
            r = json.loads(l); r["run"] = run; LI[r["m"]] = r; SIGN[run][r["signer"]] += 1; ts.append(r["bt"] or 0)
    ts = [t for t in ts if t]; RUNT[run] = (min(ts), max(ts), (min(ts) + max(ts)) / 2)
print("launches", {r: sum(SIGN[r].values()) for r in RUNS}, flush=True)

# ---------- pairs: count, then load candidates ----------
def pair_files():
    for run in RUNS:
        for f in sorted(glob.glob(os.path.join(WORK, run, "pairs", "*.jsonl.gz"))): yield run, f
is_snipe = lambda p: (not p.get("role")) and (not p.get("failed_only")) and p.get("fs") is not None and p["fs"] <= SNIPE
cnt = collections.Counter(); rolec = collections.Counter(); runc = collections.Counter()
G = collections.defaultdict(lambda: [0, 0, 0, 0])     # global: ahead bucket -> n, pnl, n>0, buy
def abk(a):
    return "0" if a == 0 else "1-3" if a <= 3 else "4-10" if a <= 10 else "11+"
for run, f in pair_files():
    for l in gzip.open(f, "rt"):
        p = json.loads(l); w = p["w"]
        if w in AGENTS: continue
        if p.get("role"): rolec[w] += 1
        elif is_snipe(p):
            cnt[w] += 1; runc[(w, run)] += 1
            if not p["may"] and not p["gopen"]:
                g = G[abk(p["ahead"])]; g[0] += 1; g[1] += p["pnl"]; g[2] += p["pnl"] > 0; g[3] += p["bsol"]
cands = {w for w, n in cnt.items() if n >= MIN_TOK} | set(FOCUS)
print("wallets with snipes", len(cnt), "with >=", MIN_TOK, len(cands), flush=True)
P = collections.defaultdict(list)
for run, f in pair_files():
    for l in gzip.open(f, "rt"):
        p = json.loads(l)
        if p["w"] in cands: p["run"] = run; P[p["w"]].append(p)
OTH = {}
for run in RUNS:
    for f in sorted(glob.glob(os.path.join(WORK, run, "other", "*.jsonl.gz"))):
        for l in gzip.open(f, "rt"):
            r = json.loads(l)
            if r[0] in cands:
                o = OTH.setdefault((r[0], run), [0] * 8)
                for k in range(8): o[k] += r[k + 1]

# ---------- shadow obs: arrival ms of each outside tx (first 6 chars of the wallet) ----------
OBS = {}
for v in ("scores_v1.jsonl", "scores_v2.jsonl", "scores_v3.jsonl"):
    for l in open(os.path.join(SHADOW, v)):
        try: r = json.loads(l)
        except Exception: continue
        if r.get("type") != "obs" or r.get("mint") in OBS: continue
        outs = []
        for x in (r.get("outs") or "-").split(","):
            y = x.split(":")
            if len(y) == 4:
                try: outs.append((float(y[0]), float(y[1]), y[2] == "1", y[3]))
                except ValueError: pass
        OBS[r["mint"]] = outs
def arrival_ms(m, w, fsol):
    o = OBS.get(m)
    if o is None: return None, False
    w6 = w[:6]; best = anyw = None          # the engine logs some router / new-instruction buys as isbuy=0 sol=0: fall back to
    for ms, sol, isb, ww in o:              # the wallet's first tx on the mint (a sniper's first tx is its buy)
        if ww != w6: continue
        if anyw is None: anyw = ms
        if isb:
            if best is None: best = ms
            if fsol and abs(sol - fsol / 1e9) <= max(0.002, 0.02 * fsol / 1e9): return ms, True
    return (best if best is not None else anyw), True

# ---------- exact SOL deltas (w3_sd.py) ----------
SD = collections.defaultdict(lambda: [0, 0, 0, 0])   # (w, m) -> delta, n_tx, n_fail, fail_fee
TIPS = collections.defaultdict(collections.Counter)  # w -> service -> n txs
SDW = set()
for f in SDF:
    if not f or not os.path.exists(f): continue
    for l in gzip.open(f, "rt"):
        w, sig, s, i, bt, mints, delta, fee, tips, err, signer, ixn = json.loads(l)
        SDW.add(w)
        if not mints: continue
        m = mints[0]; x = SD[(w, m)]; x[0] += delta; x[1] += 1
        if err: x[2] += 1; x[3] += fee or 0
        if signer == w and not err:
            for acc, lam in tips: TIPS[w][TIPMAP.get(acc, "other")] += 1
        if signer == w and not err and not tips: TIPS[w]["none"] += 1

# ---------- which SOL-delta source fits each wallet (native SOL vs WSOL vs relayed) ----------
def sd_type(w):
    if w not in SDW: return "nosd"
    nat = ws = n = 0
    for p in P.get(w, []):
        if not is_snipe(p) or p["gopen"] or p["bsol"] < 1e7: continue
        sd = SD.get((w, p["m"]))
        if not sd: continue
        n += 1; tol = 0.05 * p["bsol"] + 1e7
        if abs(sd[0] + p["lval"] - p["pnl"]) <= tol: nat += 1
        elif abs(sd[0] + p["fee"] + p["efee"]) <= tol: ws += 1
    return "native" if n and nat / n >= 0.7 else "wsol" if n and ws / n >= 0.7 else "mixed" if n else "nosd"
def true_pnl(w, p, typ):
    sd = SD.get((w, p["m"])) if typ != "nosd" else None
    if not sd: return p["pnl"], "T"
    nat = sd[0] + p["lval"]; tol = 0.05 * p["bsol"] + 1e7; x = sd[0] + p["fee"] + p["efee"]
    if typ == "native" and p["gopen"]: return nat, "sd"             # graduated: the AMM sells only show up in the SOL deltas
    if abs(nat - p["pnl"]) <= tol: return nat, "sd"
    if abs(x) <= tol: return p["pnl"] + x, "sd_wsol"                  # traded through a WSOL account: events + native-SOL extras
    return p["pnl"], "T"

# ---------- per-wallet stats ----------
def lam(x): return round(x / 1e9, 4) if x is not None else None
BASE = {}
def trait_block(ms):
    ls = [LI[m] for m in ms if m in LI]
    if not ls: return {}
    sc = [SIGN[x["run"]][x["signer"]] for x in ls]
    co = collections.Counter((x.get("created_on") or "-").replace("https://", "")[:24] for x in ls)
    hrs = collections.Counter(datetime.datetime.fromtimestamp(x["bt"], datetime.UTC).hour for x in ls if x.get("bt"))
    return dict(n=len(ls), serial3=round(sum(c >= 3 for c in sc) / len(ls), 3), signer_launches_med=med(sc),
                dev_buy_med=lam(med([x["dev_buy"] for x in ls])), dev_ge1=round(sum(x["dev_buy"] >= 1e9 for x in ls) / len(ls), 3),
                glued_n_med=med([x["glued_n"] for x in ls]), glued_sol_med=lam(med([x["glued_sol"] for x in ls])),
                bundled=round(sum(x["glued_n"] > 0 for x in ls) / len(ls), 3), jito_create=round(sum(x["jito_n"] > 0 for x in ls) / len(ls), 3),
                tw=round(sum(x["tw"] for x in ls) / len(ls), 3), web=round(sum(x["web"] for x in ls) / len(ls), 3),
                mayhem=round(sum(x["may"] for x in ls) / len(ls), 3), grad=round(sum(x["grad"] for x in ls) / len(ls), 3),
                out_buys_slot_med=med([x["out_buys_slot"] for x in ls]), out_buys_5_med=med([x["out_buys_5"] for x in ls]),
                pk60_med=med([x["pk60"] for x in ls]), p30s_med=med([x.get("p30s") for x in ls if x.get("p30s") is not None]),
                tools=[[mask(k), v] for k, v in co.most_common(4)], hours_top=[[h, v] for h, v in hrs.most_common(4)])
def wstats(w):
    prs = P.get(w, [])
    sn = [p for p in prs if is_snipe(p)]
    fails = [p for p in prs if p.get("failed_only") and not p.get("role") and (p.get("fail_s") or 0) <= SNIPE]
    roles = collections.Counter(p["role"] for p in prs if p.get("role"))
    if not sn: return dict(w=w, n=0, roles=dict(roles))
    typ = sd_type(w); srcs = collections.Counter()
    for p in sn:
        p["pnl_x"], s_ = true_pnl(w, p, typ); srcs[s_] += 1
        p["ms"], p["obs"] = arrival_ms(p["m"], w, p.get("fsol"))
        p["unres"] = int(p["gopen"] and p["left"] > 0.05 * max(1, p["tb"]))   # still held a graduated token at the end: AMM value unknown
    src = typ
    def pn(p, s): return p["pnl_x"] if s != "T" else p["pnl"]
    def agg(ps, s=src, fl=None):
        v = [pn(p, s) for p in ps]; b = sum(p["bsol"] for p in ps); fc = sum(p["efee"] for p in (fl or []))   # failed-only launches: fee cost
        top2 = sorted(v, reverse=True)[:2]
        t = (statistics.mean(v) / (statistics.stdev(v) / len(v) ** 0.5)) if len(v) >= 3 and statistics.stdev(v) > 0 else None
        return dict(n=len(ps), pnl=lam(sum(v) - fc), pnl_ex_top2=lam(sum(v) - sum(top2) - fc), buy=lam(b), roi=round((sum(v) - fc) / b, 4) if b else None,
                    win=round(sum(x > 0 for x in v) / len(v), 3) if v else None, med=lam(med(v)), fail_cost=lam(fc), t=round(t, 2) if t is not None else None,
                    unrealized=lam(sum(p["lval"] for p in ps)), n_held_end=sum(1 for p in ps if p["lval"] > 0.05 * max(1, p["bsol"])))
    fail_cost = sum(p["efee"] for p in fails)
    out = dict(w=w, src=src, pnl_sources=dict(srcs), n=len(sn), n_fail_only=len(fails), fail_cost=lam(fail_cost), roles=dict(roles),
               role_share=round(sum(roles.values()) / (sum(roles.values()) + len(sn)), 3), known=KNOWN.get(w))
    out["all"] = agg(sn, fl=fails); out["all_T"] = agg(sn, "T", fails)
    out["ex_mayhem"] = agg([p for p in sn if not p["may"]])
    out["ex_gopen"] = agg([p for p in sn if not p["gopen"]]); out["n_gopen"] = sum(p["gopen"] for p in sn)
    out["ex_unres"] = agg([p for p in sn if not p["unres"]], fl=fails); out["n_unres"] = sum(p["unres"] for p in sn)
    for run in RUNS:
        rp = [p for p in sn if p["run"] == run]; rf = [p for p in fails if p["run"] == run]; out[run] = agg(rp, fl=rf)
        mid = RUNT[run][2]; early_ = lambda p: (LI.get(p["m"], {}).get("bt") or 0) < mid
        out[run + "a"] = agg([p for p in rp if early_(p)], fl=[p for p in rf if early_(p)])
        out[run + "b"] = agg([p for p in rp if not early_(p)], fl=[p for p in rf if not early_(p)])
    # position
    ah = [p["ahead"] for p in sn if p.get("ahead") is not None and p["ahead"] >= 0]
    msl = [p["ms"] for p in sn if p["ms"] is not None]
    out["land"] = dict(fs_med=med([p["fs"] for p in sn]), create_slot=round(sum(p["fs"] == 0 for p in sn) / len(sn), 3),
                       ahead_med=med(ah), ahead_p25=q(ah, .25), ahead_p75=q(ah, .75),
                       ahead_dist={k: sum(abk(a) == k for a in ah) for k in ("0", "1-3", "4-10", "11+")},
                       mult_med=med([p["mult"] for p in sn if p.get("mult")]),
                       ms_med=med(msl), ms_p25=q(msl, .25), ms_p75=q(msl, .75), ms_n=len(msl), obs_n=sum(1 for p in sn if p["obs"]),
                       feetip_pct_med=med([round(100 * ((p.get("ffee") or 0) + (p.get("ftips") or 0)) / p["fsol"], 3) for p in sn if p.get("fsol")]),
                       tip_sol_med=lam(med([p.get("ftips") or 0 for p in sn])), cup_med=med([p.get("fcup") for p in sn if p.get("fcup") is not None]),
                       payer_self=round(sum(p.get("fself", 0) for p in sn) / len(sn), 3),
                       tips_services=TIPS[w].most_common(5) if w in TIPS else None)
    by = {}
    for k in ("0", "1-3", "4-10", "11+"):
        ps = [p for p in sn if p.get("ahead") is not None and p["ahead"] >= 0 and abk(p["ahead"]) == k]
        if ps: by[k] = agg(ps)
    out["by_ahead"] = by
    byms = {}
    for lo, hi, nm in ((-1e9, 25, "<25ms"), (25, 50, "25-50"), (50, 100, "50-100"), (100, 250, "100-250"), (250, 1e9, ">=250")):
        ps = [p for p in sn if p["ms"] is not None and lo <= p["ms"] < hi]
        if ps: byms[nm] = agg(ps)
    out["by_ms"] = byms
    # sizing / exits
    fsol = [p["fsol"] for p in sn if p.get("fsol")]
    tiers = collections.Counter(round(x / 1e9, 2) for x in fsol)
    out["size"] = dict(first_buy_med=lam(med(fsol)), p25=lam(q(fsol, .25)), p75=lam(q(fsol, .75)), tiers=tiers.most_common(5),
                       buy_total_med=lam(med([p["bsol"] for p in sn])), nbuys_med=med([p["nb"] for p in sn]))
    hold = [p["bt_ls"] - p["fbt"] for p in sn if p.get("bt_ls") and p.get("fbt")]
    out["exit"] = dict(hold_s_med=med(hold), hold_s_p25=q(hold, .25), hold_s_p75=q(hold, .75), nsells_med=med([p["ns"] for p in sn]),
                       sold_all=round(sum(p["ts"] >= 0.99 * p["tb"] for p in sn if p["tb"]) / len(sn), 3),
                       first_sell_slots_med=med([p["s1"] - p["fs"] for p in sn if p.get("s1") is not None]),
                       never_sold=sum(p["ns"] == 0 for p in sn), xfer_out=sum(p["xo"] > 0.05 * p["tb"] for p in sn if p["tb"]))
    ms_ = [p["m"] for p in sn]
    cr = collections.Counter(LI[m]["signer"] for m in ms_ if m in LI)
    out["sel"] = trait_block(ms_); out["sel"]["distinct_creators"] = len(cr)
    out["sel"]["top_creator_share"] = round(cr.most_common(1)[0][1] / len(ms_), 3) if cr else None
    out["sel"]["names"] = [mask(LI[m]["name"]) for m in ms_[:8] if m in LI]
    out["sel"]["top_devs"] = [[d[:8], c] for d, c in cr.most_common(6)]
    devpnl = collections.defaultdict(float)
    for p in sn: devpnl[LI.get(p["m"], {}).get("signer")] += pn(p, src)
    tops = sorted(devpnl.items(), key=lambda kv: -kv[1])
    out["sel"]["best_devs"] = [[(d or "?")[:8], cr.get(d, 0), lam(v)] for d, v in tops[:5]]
    out["sel"]["pnl_serial_devs"] = lam(sum(v for d, v in devpnl.items() if d and SIGN[LI[next(p["m"] for p in sn if LI.get(p["m"], {}).get("signer") == d)]["run"]][d] >= 3))
    oth = [OTH.get((w, r)) for r in RUNS]
    out["other_tokens"] = dict(n=sum(o[0] for o in oth if o), pnl_T=lam(sum(o[7] for o in oth if o)))
    best = sorted(sn, key=lambda p: -pn(p, src))[:3]; worst = sorted(sn, key=lambda p: pn(p, src))[:2]
    out["examples"] = [dict(m=p["m"], name=mask(LI.get(p["m"], {}).get("name")), pnl=lam(pn(p, src)), pnl_T=lam(p["pnl"]), fsig=p.get("fsig"),
                            fs=p["fs"], ahead=p.get("ahead"), ms=p["ms"], fsol=lam(p.get("fsol")), hold_s=(p["bt_ls"] - p["fbt"]) if p.get("bt_ls") else None,
                            nsells=p["ns"]) for p in best + worst]
    # survival tests
    r1, r2 = out["R1"], out["R2"]
    if r1["n"] >= MIN_RUN and r2["n"] >= MIN_RUN: split = "runs"; ok_split = r1["pnl"] > 0 and r2["pnl"] > 0
    else:
        big = "R1" if r1["n"] >= r2["n"] else "R2"; split = "halves_" + big
        a, b = out[big + "a"], out[big + "b"]; ok_split = a["n"] >= 3 and b["n"] >= 3 and a["pnl"] > 0 and b["pnl"] > 0
    out["split"] = split; out["ok_split"] = ok_split
    out["insider_like"] = bool(out["role_share"] > 0.25 or (out["sel"].get("top_creator_share") or 0) >= 0.5 and out["sel"]["distinct_creators"] <= 3)
    out["pass"] = bool(len(sn) >= MIN_TOK and ok_split and out["all"]["pnl"] > 0 and out["all"]["pnl_ex_top2"] > 0 and not out["insider_like"])
    out["pass_strict"] = bool(out["pass"] and out["ex_unres"]["pnl"] > 0 and out["ex_unres"]["pnl_ex_top2"] > 0)
    PP[w] = [[p["run"], int((LI.get(p["m"], {}).get("bt") or 0) >= RUNT[p["run"]][2]), round(pn(p, src)), p["bsol"], p.get("ahead"), p["ms"], p["fs"], p["m"],
              p.get("fsig"), p["unres"], p["may"], p.get("fsol"), (p["bt_ls"] - p["fbt"]) if p.get("bt_ls") and p.get("fbt") else None, p["ns"]] for p in sn]
    PP[w + "|fail"] = [[p["run"], int((LI.get(p["m"], {}).get("bt") or 0) >= RUNT[p["run"]][2]), -p["efee"]] for p in fails]
    lm = out["land"]
    out["like_us"] = bool((lm["ahead_med"] is not None and lm["ahead_med"] >= 1) or (lm["ms_med"] is not None and lm["ms_med"] >= 50))
    return out

res = {}; PP = {}
for w in sorted(cands):
    res[w] = wstats(w)
os.makedirs(OUTD, exist_ok=True)
# candidate list for the exact SOL-delta pass: every wallet that passes on trade events, or is close, + focus wallets
loose = [w for w, s in res.items() if s.get("n", 0) >= MIN_TOK and s["all_T"]["pnl"] > -0.5] + FOCUS
json.dump(sorted(set(loose)), open(os.path.join(OUTD, "cands.json"), "w"))
json.dump(res, open(os.path.join(OUTD, "wallets_all.json"), "w"), separators=(",", ":"))
with gzip.open(os.path.join(OUTD, "pairs_cands.json.gz"), "wt") as f: json.dump(PP, f, separators=(",", ":"))
json.dump({m: dict(name=mask(x.get("name")), symbol=mask(x.get("symbol")), signer=x.get("signer"), run=x["run"], bt=x.get("bt"), dev_buy=x.get("dev_buy"),
           glued_n=x.get("glued_n"), glued_sol=x.get("glued_sol"), grad=x.get("grad"), created_on=x.get("created_on"), tw=x.get("tw"), web=x.get("web"))
           for w in PP if not w.endswith("|fail") for m in [r[7] for r in PP[w]] for x in [LI.get(m, {"run": "?"})]},
          open(os.path.join(OUTD, "launch_cands.json"), "w"), separators=(",", ":"))
print("cands for sd", len(set(loose)))
print("global snipe pairs by outside-buys-ahead (no mayhem, no graduated-open): n, pnl SOL, win, roi")
for k in ("0", "1-3", "4-10", "11+"):
    g = G[k]; print(f"  {k:5s} n={g[0]} pnl={g[1]/1e9:.1f} win={g[2]/max(1,g[0]):.3f} roi={g[1]/max(1,g[3]):.4f}")
ps = sorted((s for s in res.values() if s.get("pass")), key=lambda s: -s["all"]["pnl"])
print("PASS", len(ps), "like_us", sum(s["like_us"] for s in ps))
for s in ps[:40]:
    lm = s["land"]
    print(f'{mask(s["w"][:8])} {s["src"]} n={s["n"]} pnl={s["all"]["pnl"]:+.2f} ex2={s["all"]["pnl_ex_top2"]:+.2f} R1={s["R1"]["pnl"]:+.2f}/{s["R1"]["n"]} R2={s["R2"]["pnl"]:+.2f}/{s["R2"]["n"]} '
          f'fs={lm["fs_med"]} ahead={lm["ahead_med"]} ms={lm["ms_med"]} size={s["size"]["first_buy_med"]} hold={s["exit"]["hold_s_med"]} like_us={s["like_us"]} split={s["split"]}')
for w in FOCUS:
    s = res.get(w, {})
    print("FOCUS", w[:6], s.get("n"), s.get("all"), s.get("R1"), s.get("R2"), s.get("roles"))
