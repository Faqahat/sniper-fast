#!/usr/bin/env python3
"""Local analysis of tmp-patterns/scan-*.json + sizes.json -> tables (markdown) on stdout."""
import json, glob, collections, datetime, sys, os
D = os.path.dirname(os.path.abspath(__file__)) + "/data"
OURS = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"
MRIYA = "MriyaNN8TMp6qRWjfr723PK7xgQK7yCt7Kg2v2PQu7X"
def q(v, p):
    v = sorted(x for x in v if x is not None)
    return v[min(len(v) - 1, int(len(v) * p))] if v else None
def f(x, n=1):
    if x is None: return "-"
    if isinstance(x, float): return f"{x:,.{n}f}"
    return f"{x:,}"
def pct(a, b): return f"{100 * a / b:.0f}%" if b else "-"
SEGS = sorted(glob.glob(D + "/scan-*.json"), key=lambda s: int(s.split("-p")[-1].split(".")[0]))
S = {}; W = []; OUR = []; SIG = collections.defaultdict(collections.Counter); SVC = collections.defaultdict(collections.Counter)
BINS = collections.defaultdict(collections.Counter); Q4 = collections.Counter(); POOLS = collections.defaultdict(collections.Counter); POOLBOTS = collections.defaultdict(int)
DEN = []
for fn in SEGS:
    d = json.load(open(fn)); seg = d["seg"]
    S[seg] = {"hours": d["hours"], "start": datetime.datetime.fromtimestamp(d["t_first"] / 1e9, datetime.UTC).strftime("%H:%M"), "end": datetime.datetime.fromtimestamp(d["t_last"] / 1e9, datetime.UTC).strftime("%H:%M"),
              "arb_seen": d["arb_seen"], "arb_in_exec": d["arb_in_exec"]}
    for w in d["wins"]: w["seg"] = seg; W.append(w)
    for x in d["ours"]: x["seg"] = seg; OUR.append(x)
    for k, v in d["signers"].items():
        svc = v.pop("svc", {})
        SIG[k].update(v); SVC[k].update(svc)
    for k, v in d["signer_bins"].items():
        for a, b, o, n in v: BINS[k][(a, b, o)] += n
    for *k, n in d["q4"]: Q4[tuple(k)] += n
    for p, c in d["pools"].items():
        b = c.pop("bots", 0); POOLS[p].update(c); POOLBOTS[p] = max(POOLBOTS[p], b)
    for x in d.get("denied") or []: x["seg"] = seg; DEN.append(x)
H = sum(v["hours"] for v in S.values())
SZ = json.load(open(D + "/sizes.json")) if os.path.exists(D + "/sizes.json") else {}
for w in W:
    z = SZ.get(w["sig"]); w["size"] = z["size"] if z else None
    w["gross"] = w["gain"] + w["fee"] + w["tip"]
    w["bid"] = w["prio"] + w["tip"]
# ---- universe: on our pools, not our own, not one-off position exits through Jupiter
excl_np = [w for w in W if w["n_watched"] == 0]
# non-arb profit pattern: net gain > 25% of the SOL that went through the pools (claims / position exits); flag signers whose sized big wins mostly look like that
_cl = collections.defaultdict(lambda: [0, 0])
for w in W:
    if w["size"]: _cl[w["signer"]][0] += 1; _cl[w["signer"]][1] += w["gain"] / 1e9 > .25 * w["size"]
CLAIMERS = {k for k, (n, c) in _cl.items() if n >= 2 and c / n >= .5}
excl_cl = [w for w in W if w["n_watched"] > 0 and (w["signer"] in CLAIMERS or (w["size"] and w["gain"] / 1e9 > .25 * w["size"]))]
excl_lv = [w for w in W if w["n_watched"] > 0 and "jupiter" in w["vp"] and SIG[w["signer"]]["seen"] < 20]
ourw = [w for w in W if w["signer"] == OURS]
_ex = {w["sig"] for w in excl_cl}
A = [w for w in W if w["n_watched"] > 0 and w["signer"] != OURS and not ("jupiter" in w["vp"] and SIG[w["signer"]]["seen"] < 20) and w["sig"] not in _ex]
out = []
P = out.append
P(f"Observation: {len(S)} segments, {H:.2f} h of recording (w5h-p1..p15, {S['w5h-p1']['start']}-{S['w5h-p15']['end']} UTC).")
P(f"Excluded: {len(excl_np)} 'wins' not touching any watched pool ({sum(w['gain'] for w in excl_np) / 1e9:.1f} SOL: pump.fun migrations etc.), "
  f"{len(excl_lv)} one-off Jupiter position exits by signers with <20 arb-like txs ({sum(w['gain'] for w in excl_lv) / 1e9:.1f} SOL), "
  f"{len(excl_cl)} non-arb 'claims' (gain > 25% of SOL through the pools, or signer mostly so: {sorted(k[:8] for k in CLAIMERS)}; {sum(w['gain'] for w in excl_cl) / 1e9:.2f} SOL), our own {len(ourw)} wins.")
P(f"UNIVERSE: {len(A)} profitable round trips by other bots on our pools, {sum(w['gain'] for w in A) / 1e9:.2f} SOL net ({len(A) / H:.0f}/h, {sum(w['gain'] for w in A) / 1e9 / H:.2f} SOL/h)")
P(f"timing source of gap age: {dict(collections.Counter(w['dt_src'] for w in A))}")
def bands(ws, lab):
    pass
# ======================= Q1 BIG WINS
def summarize(ws, lab):
    n = len(ws); sol = sum(w["gain"] for w in ws) / 1e9
    by = collections.defaultdict(list)
    for w in ws: by[w["signer"]].append(w)
    top = sorted(by.items(), key=lambda x: -sum(w["gain"] for w in x[1]))
    sh = lambda k: sum(sum(w["gain"] for w in v) for _, v in top[:k]) / 1e9 / sol if sol else 0
    dts = [w["dt"] for w in ws if w["dt"] is not None]
    two = [w for w in ws if w["n_watched"] >= 2 and w["dt"] is not None]
    r = {"n": n, "per_h": n / H, "sol": sol, "sol_h": sol / H, "bots": len(by), "top1": sh(1), "top3": sh(3), "top5": sh(5),
         "size": [q([w["size"] for w in ws], p) for p in (.1, .25, .5, .75, .9)], "gain": [q([w["gain"] / 1e9 for w in ws], p) for p in (.25, .5, .75, .9)],
         "dt": [q(dts, p) for p in (.1, .25, .5, .75, .9)], "same_slot": sum(1 for w in ws if w["prev_slot"] == w["slot"]) / max(1, sum(1 for w in ws if w["prev_slot"])),
         "dt_lt": {t: sum(1 for x in dts if x < t) / max(1, len(dts)) for t in (1, 7, 20, 50, 150, 300)},
         "nonce": sum(w["nonce"] for w in ws) / max(1, n), "prio": q([w["prio"] for w in ws], .5), "tip": q([w["tip"] for w in ws], .5),
         "tip_any": sum(1 for w in ws if w["tip"]) / max(1, n), "bidshare": q([w["bid"] / w["gross"] for w in ws if w["gross"] > 0], .5),
         "bidshare_q": [q([w["bid"] / w["gross"] for w in ws if w["gross"] > 0], p) for p in (.25, .75, .9)],
         "copies": q([w["copies"] for w in ws], .5), "rivals": q([w["rivals"] for w in ws], .5), "rivals_q": [q([w["rivals"] for w in ws], p) for p in (.25, .75, .9)],
         "own": q([w["own_copies"] for w in ws], .5), "svc": collections.Counter(w["svc"] for w in ws), "svc_sol": collections.Counter(), "lk": collections.Counter(w["lk"][0] for w in ws),
         "loc": collections.Counter(w["lk"][1] for w in ws), "vp": collections.Counter(), "vp_n": collections.Counter(w["vp"] for w in ws), "tok": collections.Counter(), "prev_arb": sum(1 for w in ws if w["prev_arb"]) / max(1, sum(1 for w in ws if w["prev_arb"] is not None)),
         "top": top}
    for w in ws:
        r["vp"][w["vp"]] += w["gain"] / 1e9; r["svc_sol"][w["svc"]] += w["gain"] / 1e9
        for m in w["mints"][:1] or ["?"]: r["tok"][m] += w["gain"] / 1e9
    return r
BIG1 = [w for w in A if w["gain"] >= 10_000_000]; BIG2 = [w for w in A if w["gain"] >= 100_000_000]; SMALL = [w for w in A if w["gain"] < 10_000_000]
R1, R2 = summarize(BIG1, ">=0.01"), summarize(BIG2, ">=0.1")
P("\n## Q1 BIG WINS")
P("| metric | >= 0.01 SOL | >= 0.1 SOL |\n|---|---|---|")
for lab, k, fm in [("wins", "n", lambda v: f(v)), ("wins per hour", "per_h", lambda v: f(v)), ("SOL total (net to winner)", "sol", lambda v: f(v, 2)), ("SOL per hour", "sol_h", lambda v: f(v, 2)),
                   ("distinct winning bots", "bots", lambda v: f(v)), ("top-1 bot share of SOL", "top1", lambda v: f"{100 * v:.0f}%"), ("top-3 share", "top3", lambda v: f"{100 * v:.0f}%"), ("top-5 share", "top5", lambda v: f"{100 * v:.0f}%"),
                   ("trade size SOL p10/p25/p50/p75/p90", "size", lambda v: " / ".join(f(x, 2) for x in v)), ("net gain SOL p25/p50/p75/p90", "gain", lambda v: " / ".join(f(x, 3) for x in v)),
                   ("gap age ms (win - last state change on its pools) p10/p25/p50/p75/p90", "dt", lambda v: " / ".join(f(x, 1) for x in v)),
                   ("share landed in the SAME slot as the state change", "same_slot", lambda v: f"{100 * v:.0f}%"),
                   ("share gap age < 1 / 7 / 20 / 50 / 150 / 300 ms", "dt_lt", lambda v: " / ".join(f"{100 * v[t]:.0f}%" for t in (1, 7, 20, 50, 150, 300))),
                   ("previous state change was another bot's arb", "prev_arb", lambda v: f"{100 * v:.0f}%"),
                   ("durable nonce share", "nonce", lambda v: f"{100 * v:.0f}%"), ("priority fee p50 (lamports)", "prio", lambda v: f(v)), ("tip p50 (lamports)", "tip", lambda v: f(v)),
                   ("share with any tip", "tip_any", lambda v: f"{100 * v:.0f}%"), ("(prio+tip)/gross profit p50", "bidshare", lambda v: f"{100 * v:.0f}%"),
                   ("(prio+tip)/gross p25/p75/p90", "bidshare_q", lambda v: " / ".join(f"{100 * x:.0f}%" for x in v)),
                   ("landed arb txs on the same pools in window (copies) p50", "copies", lambda v: f(v)), ("other bots landing txs in window p50", "rivals", lambda v: f(v)),
                   ("other bots p25/p75/p90", "rivals_q", lambda v: " / ".join(f(x) for x in v)), ("winner's own extra copies p50", "own", lambda v: f(v))]:
    P(f"| {lab} | {fm(R1[k])} | {fm(R2[k])} |")
P("\nper segment (big wins >= 0.01 SOL / >= 0.1 SOL):")
P("| seg | UTC | min | wins>=0.01 | SOL | /h | wins>=0.1 | SOL | top bot (share) |\n|---|---|---|---|---|---|---|---|---|")
for seg, s in S.items():
    b1 = [w for w in BIG1 if w["seg"] == seg]; b2 = [w for w in BIG2 if w["seg"] == seg]
    by = collections.Counter()
    for w in b1: by[w["signer"]] += w["gain"]
    tb = by.most_common(1)
    P(f"| {seg} | {s['start']}-{s['end']} | {s['hours'] * 60:.0f} | {len(b1)} | {sum(w['gain'] for w in b1) / 1e9:.2f} | {sum(w['gain'] for w in b1) / 1e9 / s['hours']:.2f} | {len(b2)} | {sum(w['gain'] for w in b2) / 1e9:.2f} | "
      f"{(tb[0][0][:8] + ' (' + pct(tb[0][1], sum(by.values())) + ')') if tb else '-'} |")
P("\ntop bots (>= 0.01 SOL wins):")
P("| bot | wins | SOL | median gain | median size | gap age p50 ms | same-slot | nonce | path (tip service) | prio p50 | tip p50 | bid/gross p50 | other bots in window p50 |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for sg, ws in R1["top"][:12]:
    P(f"| {sg[:8]}{' (Mriya)' if sg == MRIYA else ''} | {len(ws)} | {sum(w['gain'] for w in ws) / 1e9:.2f} | {q([w['gain'] / 1e9 for w in ws], .5):.3f} | {f(q([w['size'] for w in ws], .5), 2)} | {f(q([w['dt'] for w in ws], .5), 1)} | "
      f"{pct(sum(1 for w in ws if w['prev_slot'] == w['slot']), len(ws))} | {pct(sum(w['nonce'] for w in ws), len(ws))} | {', '.join(f'{k}:{v}' for k, v in collections.Counter(w['svc'] for w in ws).most_common(2))} | "
      f"{f(q([w['prio'] for w in ws], .5))} | {f(q([w['tip'] for w in ws], .5))} | {pct(q([w['bid'] / w['gross'] for w in ws if w['gross'] > 0], .5) or 0, 1)} | {q([w['rivals'] for w in ws], .5)} |")
P("\nsize bands (>= 0.01 SOL wins with a fetched size):")
P("| size band SOL | wins | SOL | median gain | gap age p50 ms | share gap >= 150 ms |\n|---|---|---|---|---|---|")
for lo, hi in ((0, .2), (.2, 1), (1, 2.1), (2.1, 4.2), (4.2, 8.4), (8.4, 1e9)):
    ws = [w for w in BIG1 if w["size"] is not None and lo <= w["size"] < hi]
    dd = [w["dt"] for w in ws if w["dt"] is not None]
    P(f"| {lo}-{hi if hi < 1e9 else '+'} | {len(ws)} | {sum(w['gain'] for w in ws) / 1e9:.2f} | {f(q([w['gain'] / 1e9 for w in ws], .5), 3)} | {f(q(dd, .5), 1)} | {pct(sum(1 for x in dd if x >= 150), len(dd))} |")
P(f"(sizes unknown for {sum(1 for w in BIG1 if w['size'] is None)} wins)")
P("\nvenue sets (>= 0.01 SOL): " + "; ".join(f"{k} {v:.2f} SOL ({R1['vp_n'][k]} wins)" for k, v in R1["vp"].most_common(8)))
P("\ntokens (>= 0.01 SOL): " + "; ".join(f"{k[:8]} {v:.2f} SOL" for k, v in R1["tok"].most_common(12)))
P("\npath (tip service) of big wins: " + "; ".join(f"{k}: {R1['svc'][k]} wins / {v:.2f} SOL" for k, v in R1["svc_sol"].most_common(8)))
P("\nleader kind (>= 0.01): " + str(dict(R1["lk"])) + "  location: " + str(dict(R1["loc"])))
# ---- the slow slice
P("\n### The slow slice: big wins whose gap was older than our reaction (both legs on watched pools)")
P("| slice (>= 0.01 SOL, n_watched >= 2) | wins | per hour | SOL | SOL/h | bots | top bot share | median size | median gain | same-slot | other bots p50 | tip-path mix | leader kinds |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|")
B2W = [w for w in BIG1 if w["n_watched"] >= 2 and w["dt"] is not None]
for lo, hi in ((0, 20), (20, 50), (50, 150), (150, 300), (300, 1e9), (150, 1e9)):
    ws = [w for w in B2W if lo <= w["dt"] < hi]
    by = collections.Counter()
    for w in ws: by[w["signer"]] += w["gain"]
    sol = sum(w["gain"] for w in ws) / 1e9
    P(f"| gap age {lo}-{hi if hi < 1e9 else '+'} ms | {len(ws)} | {len(ws) / H:.1f} | {sol:.2f} | {sol / H:.2f} | {len(by)} | {pct(by.most_common(1)[0][1], sum(by.values())) if by else '-'} | {f(q([w['size'] for w in ws], .5), 2)} | "
      f"{f(q([w['gain'] / 1e9 for w in ws], .5), 3)} | {pct(sum(1 for w in ws if w['prev_slot'] == w['slot']), len(ws))} | {q([w['rivals'] for w in ws], .5)} | "
      f"{', '.join(f'{k}:{v}' for k, v in collections.Counter(w['svc'] for w in ws).most_common(3))} | {dict(collections.Counter(w['lk'][0] for w in ws))} |")
SLOW = [w for w in B2W if w["dt"] >= 150]
P(f"\nslow slice (>= 150 ms) detail: n={len(SLOW)}; venue sets {collections.Counter(w['vp'] for w in SLOW).most_common(5)}; "
  f"tokens {[(k[:8], round(v, 3)) for k, v in sum((collections.Counter({(w['mints'] or ['?'])[0]: w['gain'] / 1e9}) for w in SLOW), collections.Counter()).most_common(8)]}; "
  f"bots {[(k[:8], n) for k, n in collections.Counter(w['signer'] for w in SLOW).most_common(8)]}; prev state change by an arb: {pct(sum(1 for w in SLOW if w['prev_arb']), len(SLOW))}; "
  f"size p25/p50/p75 {[f(q([w['size'] for w in SLOW], p), 2) for p in (.25, .5, .75)]}; prio p50 {q([w['prio'] for w in SLOW], .5)}; tip p50 {q([w['tip'] for w in SLOW], .5)}; bid/gross p50 {f(100 * (q([w['bid'] / w['gross'] for w in SLOW if w['gross'] > 0], .5) or 0), 0)}%; "
  f"per segment {dict(collections.Counter(w['seg'] for w in SLOW))}")
P("\nbiggest slow-slice wins:")
for w in sorted(SLOW, key=lambda w: -w["gain"])[:12]:
    P(f"- {w['seg']} {w['signer'][:8]} +{w['gain'] / 1e9:.3f} SOL size {f(w['size'], 2)} {w['vp']} {(w['mints'] or ['?'])[0][:8]} gap age {w['dt']:.0f} ms (prev slot {w['prev_slot']} -> win slot {w['slot']}, idx {w['idx']}) {w['svc']} tip {w['tip']} prio {w['prio']} leader {w['lk'][0]}/{w['lk'][1]} other bots {w['rivals']} prev-by-arb {w['prev_arb']}")
ONE = [w for w in BIG1 if w["n_watched"] == 1 and w["dt"] is not None]
P(f"\n(one-watched-leg big wins, gap age unreliable: n={len(ONE)}, {sum(w['gain'] for w in ONE) / 1e9:.2f} SOL; share >= 150 ms {pct(sum(1 for w in ONE if w['dt'] >= 150), len(ONE))})")
# all-size slow slice for our capital: <= 4.2 SOL size
cap = [w for w in B2W if w["size"] is not None and w["size"] <= 4.2]
for th in (150, 300):
    ws = [w for w in cap if w["dt"] >= th]
    P(f"slow slice >= {th} ms AND size <= 4.2 SOL: {len(ws)} wins, {sum(w['gain'] for w in ws) / 1e9:.3f} SOL ({sum(w['gain'] for w in ws) / 1e9 / H:.3f} SOL/h, {len(ws) / H:.1f}/h)")
# ======================= Q2 SMALL
P("\n## Q2 SMALL WINS (< 0.01 SOL)")
sm = SMALL
jit = [w for w in sm if w["svc"] == "jito"]
P(f"market: {len(sm)} wins ({len(sm) / H:.0f}/h), {sum(w['gain'] for w in sm) / 1e9:.3f} SOL ({sum(w['gain'] for w in sm) / 1e9 / H:.3f} SOL/h), median gain {q([w['gain'] for w in sm], .5)} lamports")
P(f"Jito-tipped-only: {len(jit)} ({pct(len(jit), len(sm))}), {sum(w['gain'] for w in jit) / 1e9:.3f} SOL; tip p25/p50/p75 {[q([w['tip'] for w in jit], p) for p in (.25, .5, .75)]}; tip/gross p50 {f(100 * (q([w['tip'] / w['gross'] for w in jit if w['gross'] > 0], .5) or 0), 0)}%; gap age p50 {f(q([w['dt'] for w in jit], .5), 1)} ms; same slot {pct(sum(1 for w in jit if w['prev_slot'] == w['slot']), len(jit))}")
nt = [w for w in sm if w["svc"] == "no tip"]
P(f"no-tip: {len(nt)} ({pct(len(nt), len(sm))}), {sum(w['gain'] for w in nt) / 1e9:.3f} SOL; prio p50 {q([w['prio'] for w in nt], .5)}; gap age p50 {f(q([w['dt'] for w in nt], .5), 1)} ms")
P("small wins by venue set: " + "; ".join(f"{k}: {n}" for k, n in collections.Counter(w["vp"] for w in sm).most_common(8)))
P("small Jito wins by venue set: " + "; ".join(f"{k}: {n}" for k, n in collections.Counter(w["vp"] for w in jit).most_common(6)))
P("small wins top tokens: " + "; ".join(f"{k[:8]}: {n}" for k, n in collections.Counter((w["mints"] or ["?"])[0] for w in sm).most_common(10)))
P(f"small-win gap age p25/p50/p75/p90: {[f(q([w['dt'] for w in sm], p), 1) for p in (.25, .5, .75, .9)]}; share >= 150 ms {pct(sum(1 for w in sm if (w['dt'] or 0) >= 150), sum(1 for w in sm if w['dt'] is not None))}")
ow = [x for x in OUR if x["verdict"] == "WIN"]
P(f"OURS: {len(ow)} wins, {sum(x['profit'] or 0 for x in ow) / 1e9:.5f} SOL net; size p50 {f(q([x['size'] / 1e9 for x in ow], .5), 3)} SOL; tip p50 {q([x['tip'] for x in ow], .5)}; pairs {collections.Counter(x['pair'] for x in ow).most_common(6)}; tokens {collections.Counter((x['mint'] or '?')[:8] for x in ow).most_common(6)}")
ourpools = {p for x in ow for p in x["pools"]}
mk = [w for w in sm if set(w["pools"]) & ourpools]
P(f"market small wins on the pools where we won at least once: {len(mk)} ({sum(w['gain'] for w in mk) / 1e9:.3f} SOL); our share of wins there: {pct(len(ow), len(ow) + len(mk))}; Jito-tipped among them {pct(sum(1 for w in mk if w['svc'] == 'jito'), len(mk))}")
P(f"our wins per segment: {dict(collections.Counter(x['seg'] for x in ow))}")
# ======================= Q3 strategy types
P("\n## Q3 VOLUME vs RESULTS by strategy type (other bots, all segments)")
def btype(k, c):
    sv = SVC[k]; tot = sum(sv.values()) or 1
    jito = sv.get("jito", 0) / tot; notip = sv.get("no tip", 0) / tot
    paths = [s for s, n in sv.items() if n / tot >= .1]
    path = "bundle-only" if jito >= .9 else "no-tip(TPU/prio)" if notip >= .9 else "multi-sender" if len(paths) >= 2 else "single tip-sender"
    rate = c["seen"] / H
    vol = "sprayer(>=1000/h)" if rate >= 1000 else "mid(100-1000/h)" if rate >= 100 else "sniper(<100/h)"
    return path, vol
def excess(c): return (c["okloss"] + (c["fee"] - c["fail_fee"] - c["fee_wins"]) + (c["tip_paid"] - c["tip_wins"])) / 1e9
VOL = {k for k, c in SIG.items() if excess(c) < -.2 and c["wins"] < 10 * max(1, -excess(c))}
P(f"volume/wash-like signers excluded (ok round trips losing more than fees+tips, i.e. LP fees; few wins): {len(VOL)}, their losses {sum(excess(SIG[k]) for k in VOL):.2f} SOL; e.g. {[k[:8] for k in sorted(VOL, key=lambda k: excess(SIG[k]))[:5]]}")
T = collections.defaultdict(lambda: collections.Counter())
TB = collections.defaultdict(list)
for k, c in SIG.items():
    if k == OURS or c["seen"] < 20 or k in VOL or k in CLAIMERS: continue
    t = btype(k, c); T[t].update(c); T[t]["bots"] += 1; TB[t].append((k, c))
P("| path | volume | bots | arb txs/h | landed | win/landed | wins/h | gross won SOL (gain+fees+tips on wins) | fees+tips spent SOL | net SOL | net SOL/h | profitable bots | median bot net SOL |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for t, c in sorted(T.items(), key=lambda x: -(x[1]["gain"] + x[1]["okloss"] - x[1]["fail_fee"])):
    gross = (c["gain"] + c["tip_wins"] + c["fee_wins"]) / 1e9
    spent = (c["fee"] + c["tip_paid"]) / 1e9
    net = (c["gain"] + c["okloss"] - c["fail_fee"]) / 1e9
    nets = [(x["gain"] + x["okloss"] - x["fail_fee"]) / 1e9 for _, x in TB[t]]
    P(f"| {t[0]} | {t[1]} | {c['bots']} | {c['seen'] / H:,.0f} | {pct(c['landed'], c['seen'])} | {100 * c['wins'] / max(1, c['landed']):.2f}% | {c['wins'] / H:.0f} | {gross:.2f} | {spent:.2f} | {net:.2f} | {net / H:.2f} | {sum(1 for x in nets if x > 0)} | {f(q(nets, .5), 4)} |")
P("\nbundle-only bots (>= 90% of txs Jito-tipped), top by gross: " + "; ".join(f"{k[:8]}: {c['seen'] / H:,.0f} tx/h, {c['wins']} wins, gross {(c['gain'] + c['tip_wins'] + c['fee_wins']) / 1e9:.3f}, tips {c['tip_paid'] / 1e9:.3f}, net {(c['gain'] + c['okloss'] - c['fail_fee']) / 1e9:.3f}" for k, c in sorted(((k, c) for t, l in TB.items() if t[0] == 'bundle-only' for k, c in l), key=lambda x: -(x[1]['gain'] + x[1]['tip_wins']))[:6]))
P("\ntop 15 bots by net (other bots):")
P("| bot | type | arb txs/h | landed | ok | wins | win/landed | gross SOL | fees+tips SOL | failed-tx fees SOL | net SOL | nonce | paths |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|")
nets = sorted(((k, c) for k, c in SIG.items() if k != OURS and c["seen"] >= 20 and k not in VOL and k not in CLAIMERS), key=lambda x: -(x[1]["gain"] + x[1]["okloss"] - x[1]["fail_fee"]))
for k, c in nets[:15]:
    t = btype(k, c)
    P(f"| {k[:8]}{' (Mriya)' if k == MRIYA else ''} | {t[0]} / {t[1]} | {c['seen'] / H:,.0f} | {pct(c['landed'], c['seen'])} | {pct(c['ok'], c['landed'])} | {c['wins']} | {100 * c['wins'] / max(1, c['landed']):.2f}% | {(c['gain'] + c['tip_wins'] + c['fee_wins']) / 1e9:.3f} | "
      f"{(c['fee'] + c['tip_paid']) / 1e9:.3f} | {c['fail_fee'] / 1e9:.3f} | {(c['gain'] + c['okloss'] - c['fail_fee']) / 1e9:.3f} | {pct(c['nonce'], c['seen'])} | {', '.join(f'{a}:{pct(b, sum(SVC[k].values()))}' for a, b in SVC[k].most_common(3))} |")
P("\nbiggest losers (net):")
for k, c in nets[-6:]:
    t = btype(k, c)
    P(f"- {k[:8]} {t[0]}/{t[1]}: {c['seen'] / H:,.0f} txs/h, wins {c['wins']}, gross {(c['gain'] + c['tip_wins'] + c['fee_wins']) / 1e9:.3f}, failed fees {c['fail_fee'] / 1e9:.3f}, net {(c['gain'] + c['okloss'] - c['fail_fee']) / 1e9:.3f} SOL")
allb = [(c["gain"] + c["okloss"] - c["fail_fee"]) for k, c in SIG.items() if k != OURS and c["seen"] >= 20 and k not in VOL and k not in CLAIMERS]
P(f"bots with >= 20 arb txs: {len(allb)}; net-positive {sum(1 for x in allb if x > 0)}; total net {sum(allb) / 1e9:.2f} SOL; top-10 net {sum(sorted(allb)[-10:]) / 1e9:.2f} SOL")
P(f"exec coverage: arb-like txs seen in shreds that have an execution record: {pct(sum(s['arb_in_exec'] for s in S.values()), sum(s['arb_seen'] for s in S.values()))} (fees of the rest are not counted)")
# ======================= Q4 fees
P("\n## Q4 FEES THAT WIN")
def wr(filt):
    w = sum(n for k, n in Q4.items() if filt(k) and k[5] == "win"); l = sum(n for k, n in Q4.items() if filt(k))
    return w, l
PB = ["0", "<=1000", "<=10000", "<=100000", "<=1000000", ">1000000"]
TBk = ["0", "<=10000", "<=100000", "<=1000000", "<=10000000", ">10000000"]
P("win rate per landed arb tx by priority fee paid (lamports), by path:")
P("| priority fee | no-tip: landed | win% | jito: landed | win% | other senders: landed | win% |\n|---|---|---|---|---|---|---|")
for b in PB:
    row = []
    for cls in ("no tip", "jito", "other"):
        fl = (lambda k, cls=cls, b=b: k[1] == b and ((k[0] == cls) if cls != "other" else k[0] not in ("no tip", "jito")))
        w_, l_ = wr(fl); row += [f(l_), f"{100 * w_ / max(1, l_):.2f}%"]
    P(f"| {b} | " + " | ".join(row) + " |")
P("\nwin rate of Jito-tipped (no other sender) landed txs by tip:")
P("| tip lamports | landed | wins | win% |\n|---|---|---|---|")
for b in TBk:
    w_, l_ = wr(lambda k, b=b: k[0] == "jito" and k[2] == b)
    P(f"| {b} | {f(l_)} | {f(w_)} | {100 * w_ / max(1, l_):.2f}% |")
P("\nwin rate by leader kind and path:")
for lkk in ("Jito", "BAM", "non-Jito"):
    parts = []
    for cls in ("no tip", "jito"):
        w_, l_ = wr(lambda k, lkk=lkk, cls=cls: k[3] == lkk and k[0] == cls)
        parts.append(f"{cls}: {w_}/{l_} = {100 * w_ / max(1, l_):.2f}%")
    P(f"- {lkk}: " + "; ".join(parts))
# within-bot: win rate by own priority bucket
P("\nwithin-bot (same bot, wins vs losses) — win rate by the bot's own priority-fee bucket (bots with >= 500 landed txs):")
P("| bot | " + " | ".join(PB) + " | tip buckets used (win% by tip bucket) |\n|---|" + "---|" * (len(PB) + 1))
rich = sorted(((k, sum(v.values())) for k, v in BINS.items() if k != OURS and sum(v.values()) >= 500), key=lambda x: -SIG[x[0]]["gain"])[:14]
up = dn = same = 0
for k, n in rich:
    cells = []; rates = []
    for b in PB:
        l_ = sum(v for (a, t, o), v in BINS[k].items() if a == b); w_ = sum(v for (a, t, o), v in BINS[k].items() if a == b and o == "win")
        cells.append(f"{100 * w_ / l_:.1f}% ({l_})" if l_ >= 30 else "-")
        if l_ >= 30: rates.append(w_ / l_)
    if len(rates) >= 2:
        if rates[-1] > rates[0] * 1.2: up += 1
        elif rates[-1] < rates[0] / 1.2: dn += 1
        else: same += 1
    tcells = []
    for b in TBk:
        l_ = sum(v for (a, t, o), v in BINS[k].items() if t == b); w_ = sum(v for (a, t, o), v in BINS[k].items() if t == b and o == "win")
        if l_ >= 30: tcells.append(f"{b}:{100 * w_ / l_:.1f}%({l_})")
    P(f"| {k[:8]} | " + " | ".join(cells) + f" | {' '.join(tcells)} |")
P(f"within-bot: highest-priority bucket wins more often than lowest in {up} bots, less in {dn}, similar in {same}")
# bid share vs gain size among wins
P("\nbid (priority+tip) as share of gross profit, by win size:")
P("| gross band SOL | wins | bid/gross p25 | p50 | p75 | no-tip share | jito share |\n|---|---|---|---|---|---|---|")
for lo, hi in ((0, .0001), (.0001, .001), (.001, .01), (.01, .1), (.1, 1e9)):
    ws = [w for w in A if lo <= w["gross"] / 1e9 < hi]
    bs = [w["bid"] / w["gross"] for w in ws if w["gross"] > 0]
    P(f"| {lo}-{hi if hi < 1e9 else '+'} | {len(ws)} | {f(100 * (q(bs, .25) or 0), 0)}% | {f(100 * (q(bs, .5) or 0), 0)}% | {f(100 * (q(bs, .75) or 0), 0)}% | {pct(sum(1 for w in ws if w['svc'] == 'no tip'), len(ws))} | {pct(sum(1 for w in ws if w['svc'] == 'jito'), len(ws))} |")
# ======================= Q5 time / regime
P("\n## Q5 TIME and REGIME")
P("| seg | UTC | min | arb wins/h | SOL/h (all sizes) | big wins/h | top token share of SOL | top token | bots winning | our live attempts | our wins |\n|---|---|---|---|---|---|---|---|---|---|---|")
for seg, s in S.items():
    ws = [w for w in A if w["seg"] == seg]
    tok = collections.Counter()
    for w in ws: tok[(w["mints"] or ["?"])[0]] += w["gain"]
    tt = tok.most_common(1)
    oa = [x for x in OUR if x["seg"] == seg]
    P(f"| {seg} | {s['start']}-{s['end']} | {s['hours'] * 60:.0f} | {len(ws) / s['hours']:.0f} | {sum(w['gain'] for w in ws) / 1e9 / s['hours']:.2f} | {sum(1 for w in ws if w['gain'] >= 1e7) / s['hours']:.0f} | "
      f"{pct(tt[0][1], sum(tok.values())) if tt else '-'} | {tt[0][0][:8] if tt else '-'} | {len({w['signer'] for w in ws})} | {len(oa)} | {sum(1 for x in oa if x['verdict'] == 'WIN')} |")
P("\ntoken lifetimes (top 12 tokens by SOL, all sizes): SOL per segment")
tokseg = collections.defaultdict(collections.Counter)
for w in A: tokseg[(w["mints"] or ["?"])[0]][w["seg"]] += w["gain"] / 1e9
for t, c in sorted(tokseg.items(), key=lambda x: -sum(x[1].values()))[:12]:
    P(f"- {t[:10]}: total {sum(c.values()):.2f} SOL, active in {len(c)} segments: " + ", ".join(f"{k.split('-')[1]}:{v:.2f}" for k, v in sorted(c.items(), key=lambda x: int(x[0].split('-p')[1]))))
# crowding: per pool bots vs our attempts/wins
P("\ncrowding: pools binned by number of distinct arb signers that touched them (all night):")
ourp = collections.defaultdict(lambda: [0, 0])
for x in OUR:
    for p in x["pools"]: ourp[p][0] += 1; ourp[p][1] += x["verdict"] == "WIN"
P("| arb bots on pool | pools | market wins | market SOL | wins per pool | our attempts | our wins | our win% |\n|---|---|---|---|---|---|---|---|")
for lo, hi in ((1, 5), (5, 20), (20, 60), (60, 150), (150, 10 ** 6)):
    ps = [p for p in POOLS if lo <= POOLBOTS[p] < hi]
    a_ = sum(ourp[p][0] for p in ps); w_ = sum(ourp[p][1] for p in ps)
    P(f"| {lo}-{hi if hi < 10 ** 6 else '+'} | {len(ps)} | {sum(POOLS[p]['wins'] for p in ps)} | {sum(POOLS[p]['gain'] for p in ps) / 1e9:.2f} | {sum(POOLS[p]['wins'] for p in ps) / max(1, len(ps)):.1f} | {a_} | {w_} | {100 * w_ / max(1, a_):.1f}% |")
# ======================= Q6 contrast
P("\n## Q6 CONTRAST: our attempts vs the winners of the same gaps")
WS = {w["sig"]: w for w in W}
live = OUR
P(f"our live attempts: {len(live)}; verdicts {dict(collections.Counter(x['verdict'] for x in live))}; arms {dict(collections.Counter(x['arm'] for x in live))}; jito verdicts {dict(collections.Counter(x['jito'] for x in live if x['jito']))}")
rows = []
for x in live:
    if x["verdict"] == "WIN" or not x.get("winner"): continue
    w = WS.get(x["winner"])
    if not w: continue
    rows.append((x, w))
P(f"lost attempts with a profitable winner on the same pools within 5 slots: {len(rows)} of {sum(1 for x in live if x['verdict'] != 'WIN')}")
P("| our size band | lost w/ winner | our size p50 | our expected p50 | our tip p50 | our send ms p50 | winner gain p50 | winner size p50 | winner gap age p50 ms | winner same-slot | winner path mix | winner bid p50 | winner gain / our expected p50 |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for lo, hi in ((0, .1), (.1, 1), (1, 4.3)):
    rr = [(x, w) for x, w in rows if lo <= x["size"] / 1e9 < hi]
    if not rr: continue
    P(f"| {lo}-{hi} | {len(rr)} | {f(q([x['size'] / 1e9 for x, _ in rr], .5), 3)} | {f(q([x['exp'] for x, _ in rr], .5))} | {f(q([x['tip'] for x, _ in rr], .5))} | {f(q([x['sent_ms'] for x, _ in rr], .5), 1)} | "
      f"{f(q([w['gain'] for _, w in rr], .5))} | {f(q([w['size'] for _, w in rr], .5), 2)} | {f(q([w['dt'] for _, w in rr], .5), 1)} | {pct(sum(1 for _, w in rr if w['prev_slot'] == w['slot']), len(rr))} | "
      f"{', '.join(f'{k}:{v}' for k, v in collections.Counter(w['svc'] for _, w in rr).most_common(3))} | {f(q([w['bid'] for _, w in rr], .5))} | {f(q([w['gain'] / max(1, x['exp']) for x, w in rr], .5), 2)} |")
big = [x for x in live if x["size"] >= 1e9]
P(f"\nour attempts >= 1 SOL: {len(big)}; with a profitable winner within 5 slots: {sum(1 for x in big if x.get('winner') and x['winner'] in WS)}; winner gain >= 50% of our expected: "
  f"{sum(1 for x in big if x.get('winner') in WS and WS[x['winner']]['gain'] >= .5 * x['exp'])}; our expected p50 {q([x['exp'] for x in big], .5)}; jito verdicts {dict(collections.Counter(x['jito'] for x in big))}")
ws_big = [WS[x["winner"]] for x in big if x.get("winner") in WS]
P(f"winners of our >= 1 SOL attempts: gap age p25/p50/p75 {[f(q([w['dt'] for w in ws_big], p), 1) for p in (.25, .5, .75)]}; same-slot {pct(sum(1 for w in ws_big if w['prev_slot'] == w['slot']), len(ws_big))}; "
  f"top winners {[(k[:8], n) for k, n in collections.Counter(w['signer'] for w in ws_big).most_common(6)]}; path {collections.Counter(w['svc'] for w in ws_big).most_common(4)}")
if DEN:
    P(f"\nseg.py 'denied' lists (p4,p6,p7,p10,p12; winner timing vs the opportunity's trigger): n={len(DEN)}; winner ms p25/p50/p75 {[f(q([d['ms'] for d in DEN], p), 1) for p in (.25, .5, .75)]}; our first send ms p50 {f(q([d['ours_ms'] for d in DEN], .5), 1)}; "
      f"winner later than our send {pct(sum(1 for d in DEN if d['ms'] is not None and d['ours_ms'] is not None and d['ms'] > d['ours_ms']), sum(1 for d in DEN if d['ms'] is not None and d['ours_ms'] is not None))}; "
      f"winner size p50 {f(q([d['size'] for d in DEN], .5), 2)} SOL; profit p50 {f(q([d['profit'] for d in DEN], .5), 5)} SOL; our expected p50 {f(q([d['our_exp'] for d in DEN], .5))}")
print("\n".join(out))
