#!/usr/bin/env python3
"""vs248 step 4 (read-only): the difference tables bot 248 vs our engine (MEASURED unless marked), per day + 90 % bootstrap.
Out: vs248/v4_tables.txt, vs248/v4.json (numbers for the bridge)"""
import pickle, sys, collections, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/vs248"
DAYS = (2, 3, 4, 5)
ND = len(DAYS)


def boot_mean(v, n=2000, seed=1):
    v = np.asarray(v, float)
    if len(v) < 2: return (float("nan"), float("nan"))
    r = np.random.default_rng(seed); s = v[r.integers(0, len(v), (n, len(v)))].mean(1)
    return float(np.percentile(s, 5)), float(np.percentile(s, 95))


def boot_daysum(rows, key, n=1000, seed=2):
    """90 % range of the D2-D5 mean per day of sum(key) (resample within day)"""
    per = [np.asarray([key(r) for r in rows if r["day"] == d], float) for d in DAYS]
    g = np.random.default_rng(seed); s = []
    for _ in range(n): s.append(np.mean([x[g.integers(0, len(x), len(x))].sum() if len(x) else 0.0 for x in per]))
    return float(np.percentile(s, 5)), float(np.percentile(s, 95))


def q(v, p): v = [x for x in v if x is not None]; return float(np.percentile(v, p)) if v else float("nan")


def main():
    Z = pickle.load(open(f"{OUT}/v2.pkl", "rb")); H, O, F, WAL = Z["H"], Z["O"], Z["ofail"], Z["wal"]
    R = pickle.load(open(f"{OUT}/v3.pkl", "rb")); RO, PP = R["O"], R["P"]
    Z1 = pickle.load(open(f"{OUT}/v1.pkl", "rb")); HF = [f for f in Z1["hfail"] if f["code"] == 248]
    out = []; J = {}
    def P(*a):
        s = " ".join(str(x) for x in a); print(s); out.append(s)
    hD = [h for h in H if h["day"] in DAYS]; oD = [x for x in O if x["day"] in DAYS]; fD = [f for f in F if f["day"] in DAYS]
    # ------------------------------------------------------------------ 0. overview
    P("# 0. Overview per day (MEASURED tape lots; P&L after pump fees and MEASURED tx costs of the lot's own buy+sell txs)")
    P("| day | 248 lots | 248 net SOL | 248 mSOL/lot | 248 SOL in/lot | our fills (ps/reg/other) | our lot net | our mSOL/fill | our failed-attempt cost | our wallet |")
    P("|---|---|---|---|---|---|---|---|---|---|")
    for d in range(7):
        h = [x for x in H if x["day"] == d]; o = [x for x in O if x["day"] == d]; f = [x for x in F if x["day"] == d]
        c = collections.Counter(x["path"] for x in o)
        P(f"| {L.day_name(d)} | {len(h):,} | {sum(x['net'] for x in h):+.2f} | {1e3 * np.mean([x['net'] for x in h]) if h else 0:+.1f} | {np.mean([x['cost'] for x in h]) if h else 0:.3f} | "
          f"{len(o)} ({c['ps']}/{c['reg']}/{c['other']}) | {sum(x['net'] for x in o):+.3f} | {1e3 * np.mean([x['net'] for x in o]) if o else 0:+.1f} | {-sum(x['cost'] for x in f):+.3f} | {WAL.get(d, 0):+.3f} |")
    # ------------------------------------------------------------------ 1. selection
    P("\n# 1. Selection\n## 1a. Every bot-248 lot in exactly one bucket, D2-D5 (engines running those days); SOL/day = mean of the 4 days (MEASURED; reasons from the run records)")
    P("| bucket | lots | net SOL | SOL/day [90%] | mSOL/lot [90%] | win % | days > 0 |"); P("|---|---|---|---|---|---|---|")
    bk = collections.defaultdict(list)
    for h in hD: bk[h["bucket"]].append(h)
    J["h_bucket"] = {}
    for k, v in sorted(bk.items(), key=lambda kv: -sum(x["net"] for x in kv[1])):
        per = [sum(x["net"] for x in v if x["day"] == d) for d in DAYS]
        lo, hi = boot_daysum(v, lambda r: r["net"]); ml, mh = boot_mean([1e3 * x["net"] for x in v])
        J["h_bucket"][k] = dict(n=len(v), net=sum(x["net"] for x in v), per=per)
        P(f"| {k} | {len(v):,} | {sum(x['net'] for x in v):+.2f} | {np.mean(per):+.2f} [{lo:+.2f}..{hi:+.2f}] | {1e3 * np.mean([x['net'] for x in v]):+.1f} [{ml:+.1f}..{mh:+.1f}] | "
          f"{100 * np.mean([x['net'] > 0 for x in v]):.0f} | {sum(p > 0 for p in per)}/4 |")
    P(f"| ALL 248 D2-D5 | {len(hD):,} | {sum(x['net'] for x in hD):+.2f} | {sum(x['net'] for x in hD) / ND:+.2f} | {1e3 * np.mean([x['net'] for x in hD]):+.1f} | | |")
    P("\n## 1b. Our lots (fills) D2-D5 by whether bot 248 bought the same dump (MEASURED tape lot net incl. the lot's buy+sell tx costs; failed attempts separate)")
    P("| our bucket | path | fills | net SOL | SOL/day | mSOL/fill [90%] | win % |"); P("|---|---|---|---|---|---|---|")
    J["o_bucket"] = {}
    for b in ("H2H", "NEAR", "OWN"):
        for p in ("ps", "reg", "other"):
            v = [x for x in oD if x["bucket"] == b and x["path"] == p]
            if not v: continue
            ml, mh = boot_mean([1e3 * x["net"] for x in v])
            J["o_bucket"][b + ":" + p] = dict(n=len(v), net=sum(x["net"] for x in v), per=[sum(x["net"] for x in v if x["day"] == d) for d in DAYS])
            P(f"| {b} | {p} | {len(v)} | {sum(x['net'] for x in v):+.3f} | {sum(x['net'] for x in v) / ND:+.3f} | {1e3 * np.mean([x['net'] for x in v]):+.1f} [{ml:+.1f}..{mh:+.1f}] | {100 * np.mean([x['net'] > 0 for x in v]):.0f} |")
    # trigger types
    def ttype(x):
        if not x["dumpre"]: return "no dump (<5% or >2 slots)"
        c = x["d_cls"]
        if c == "dev": return "dev chunk (<5% supply)" if x["d_pct"] < 5 else "dev big (>=5% supply)"
        return {"bundler": "bundler", "whale": "whale (>=6% holder)", "early": "early buyer", "other": "other seller"}.get(c, c)
    P("\n## 1c. By trigger type (seller of the dump), D2-D5. dev = creator; bundler = bought in the create slot; whale = held >= 6 % before the dump;")
    P("## early = bought <= create+10 slots. 248 split: what we did with it. Ours split by path. (MEASURED)")
    P("| trigger | 248 lots | 248 mSOL/lot | 248 SOL/day | of which S_FILL / S_FAIL / REF:gate / REF:other refusals / NOENG+NOCOV | 248 net on REF:gate SOL/day | our ps fills, mSOL/fill | our reg fills, mSOL/fill |")
    P("|---|---|---|---|---|---|---|---|")
    tt = collections.defaultdict(list); to = collections.defaultdict(list)
    for h in hD: tt[ttype(h)].append(h)
    for x in oD: to[ttype(x)].append(x)
    J["ttype"] = {}
    for k in sorted(set(tt) | set(to), key=lambda k: -sum(x["net"] for x in tt.get(k, []))):
        v = tt.get(k, []); o = to.get(k, [])
        c = collections.Counter("S_FILL" if x["bucket"] in ("S_FILL", "S_NEAR") else "S_FAIL" if x["bucket"] == "S_FAIL" else "REF:gate" if x["bucket"].startswith("REF:gate")
                                else "REF:x" if x["bucket"].startswith("REF") else "NO" for x in v)
        g = [x for x in v if x["bucket"].startswith("REF:gate")]
        ps = [x for x in o if x["path"] == "ps"]; rg = [x for x in o if x["path"] == "reg"]
        J["ttype"][k] = dict(n=len(v), net=sum(x["net"] for x in v), gate=sum(x["net"] for x in g), ps=(len(ps), sum(x["net"] for x in ps)), reg=(len(rg), sum(x["net"] for x in rg)))
        P(f"| {k} | {len(v):,} | {1e3 * np.mean([x['net'] for x in v]) if v else 0:+.1f} | {sum(x['net'] for x in v) / ND:+.2f} | {c['S_FILL']} / {c['S_FAIL']} / {c['REF:gate']} / {c['REF:x']} / {c['NO']} | "
          f"{sum(x['net'] for x in g) / ND:+.2f} | {len(ps)}, {1e3 * np.mean([x['net'] for x in ps]) if ps else 0:+.1f} | {len(rg)}, {1e3 * np.mean([x['net'] for x in rg]) if rg else 0:+.1f} |")
    P("\n## 1d. 248 dev-seller dumps by the 'chunk' pattern (sell < 5 % of supply AND pre-buy price 4-30 % below the 10-slot high), D2-D5 (MEASURED)")
    P("| set | 248 lots | mSOL/lot | SOL/day | our fills on them |"); P("|---|---|---|---|---|")
    for nm, f in (("dev, chunk", lambda x: x["dumpre"] and x["d_cls"] == "dev" and x["chunk"]), ("dev, not chunk", lambda x: x["dumpre"] and x["d_cls"] == "dev" and not x["chunk"]),
                  ("any seller, chunk", lambda x: x["dumpre"] and x["chunk"]), ("any seller, not chunk", lambda x: x["dumpre"] and not x["chunk"])):
        v = [x for x in hD if f(x)]; o = [x for x in oD if f(x)]
        P(f"| {nm} | {len(v):,} | {1e3 * np.mean([x['net'] for x in v]) if v else 0:+.1f} | {sum(x['net'] for x in v) / ND:+.2f} | {len(o)} ({1e3 * np.mean([x['net'] for x in o]) if o else 0:+.1f} mSOL/fill) |")
    P("\n## 1e. 248's refused dumps (REF:*) by engine reason x trigger, D2-D5: lots / SOL per day (MEASURED)")
    rs = sorted(set(x["bucket"] for x in hD if x["bucket"].startswith("REF")))
    tk_ = sorted(set(ttype(x) for x in hD if x["bucket"].startswith("REF")))
    P("| reason | " + " | ".join(tk_) + " | total |"); P("|---|" + "---|" * (len(tk_) + 1))
    for r_ in rs:
        cells = []
        for t in tk_:
            v = [x for x in hD if x["bucket"] == r_ and ttype(x) == t]
            cells.append(f"{len(v)} / {sum(x['net'] for x in v) / ND:+.2f}")
        v = [x for x in hD if x["bucket"] == r_]
        P(f"| {r_} | " + " | ".join(cells) + f" | {len(v)} / {sum(x['net'] for x in v) / ND:+.2f} |")
    # gate detail: regular reason vs pre-send reason
    P("\n## 1f. REF:gate lots: what the pre-send path saw (runs with pre-send live) (MEASURED)")
    g = [x for x in hD if x["bucket"].startswith("REF:gate")]
    c = collections.defaultdict(list)
    for x in g: c[x.get("ps_reason", "?")].append(x)
    for k, v in sorted(c.items(), key=lambda kv: -len(kv[1])):
        P(f"- {k}: {len(v)} lots, {sum(x['net'] for x in v) / ND:+.2f} SOL/day, {1e3 * np.mean([x['net'] for x in v]):+.1f} mSOL/lot")
    # ------------------------------------------------------------------ 2. timing
    P("\n# 2. Timing and position (MEASURED, chain clock = slot x 212 ms + index share of the block)")
    P("## 2a. Overall, dump-reactive buys (>= 5 % outside drop <= 2 slots before), D2-D5 (248) / all days (ours)")
    P("| who | buys | dump->buy ms p25/p50/p75 | same slot % | trades ahead (all rows) p25/p50/p75 | 0 ahead % | price paid / post-dump p25/p50/p75 | net mSOL/lot |")
    P("|---|---|---|---|---|---|---|---|")
    def tim(v, nm):
        v = [x for x in v if x["dumpre"]]
        if not v: return
        P(f"| {nm} | {len(v):,} | {q([x['d_ms'] for x in v], 25):.0f} / {q([x['d_ms'] for x in v], 50):.0f} / {q([x['d_ms'] for x in v], 75):.0f} | {100 * np.mean([x['d_slots'] == 0 for x in v]):.0f} | "
          f"{q([x['n_ahead'] for x in v], 25):.0f} / {q([x['n_ahead'] for x in v], 50):.0f} / {q([x['n_ahead'] for x in v], 75):.0f} | {100 * np.mean([x['n_ahead'] == 0 for x in v]):.0f} | "
          f"{q([x['px_vs_post'] for x in v], 25):.3f} / {q([x['px_vs_post'] for x in v], 50):.3f} / {q([x['px_vs_post'] for x in v], 75):.3f} | {1e3 * np.mean([x['net'] for x in v]):+.1f} |")
    tim(hD, "248 (D2-D5)"); tim(H, "248 (all 6 days)")
    tim([x for x in O if x["path"] == "ps"], "ours pre-send"); tim([x for x in O if x["path"] == "reg"], "ours regular")
    P("\n## 2b. HEAD TO HEAD on the same dump row (S_FILL pairs, all days)")
    PA = []
    hk = {(h["slot"], h["idx"]): h for h in H}; ok = {(x["slot"], x["idx"]): x for x in O}
    for r in PP:
        h = hk[r["h"]]; x = ok[r["o"]]; PA.append((r, h, x))
    for p in ("ps", "reg", "other", "ALL"):
        v = [(r, h, x) for r, h, x in PA if p == "ALL" or x["path"] == p]
        if not v: continue
        first = np.mean([(x["slot"], x["idx"]) < (h["slot"], h["idx"]) for r, h, x in v])
        P(f"- {p}: {len(v)} pairs; we land first {100 * first:.0f}%; dump->buy ms p50 ours {q([x['d_ms'] for r, h, x in v], 50):.0f} vs 248 {q([h['d_ms'] for r, h, x in v], 50):.0f}; "
          f"248 lands after us by p25/p50/p75 {q([h['cc'] - x['cc'] for r, h, x in v], 25):.0f}/{q([h['cc'] - x['cc'] for r, h, x in v], 50):.0f}/{q([h['cc'] - x['cc'] for r, h, x in v], 75):.0f} ms; "
          f"trades ahead p50 ours {q([x['n_ahead'] for r, h, x in v], 50):.0f} vs 248 {q([h['n_ahead'] for r, h, x in v], 50):.0f}; "
          f"price/post-dump p50 ours {q([x['px_vs_post'] for r, h, x in v], 50):.3f} vs 248 {q([h['px_vs_post'] for r, h, x in v], 50):.3f}; "
          f"248 price / our price p50 {q([h['px_pre'] / x['px_pre'] for r, h, x in v], 50):.3f}")
    P("\n## 2c. 248's dump-reactive lots by its position after the dump, D2-D5 (MEASURED): does 248 profit behind the crowd?")
    P("| trades ahead | lots | mSOL/lot [90%] | win % | price/post p50 |"); P("|---|---|---|---|---|")
    for lo_, hi_ in ((0, 0), (1, 1), (2, 3), (4, 7), (8, 15), (16, 10 ** 9)):
        v = [x for x in hD if x["dumpre"] and lo_ <= x["n_ahead"] <= hi_]
        if not v: continue
        ml, mh = boot_mean([1e3 * x["net"] for x in v])
        P(f"| {lo_}-{hi_ if hi_ < 10 ** 9 else '+'} | {len(v):,} | {1e3 * np.mean([x['net'] for x in v]):+.1f} [{ml:+.1f}..{mh:+.1f}] | {100 * np.mean([x['net'] > 0 for x in v]):.0f} | {q([x['px_vs_post'] for x in v], 50):.3f} |")
    P("| price/post-dump bucket | lots | mSOL/lot [90%] | win % | |"); P("|---|---|---|---|---|")
    for lo_, hi_ in ((0, 1.0), (1.0, 1.035), (1.035, 1.05), (1.05, 1.10), (1.10, 1.20), (1.20, 99)):
        v = [x for x in hD if x["dumpre"] and x["px_vs_post"] is not None and lo_ < x["px_vs_post"] <= hi_]
        if not v: continue
        ml, mh = boot_mean([1e3 * x["net"] for x in v])
        P(f"| {lo_:.3f}-{hi_:.3f} | {len(v):,} | {1e3 * np.mean([x['net'] for x in v]):+.1f} [{ml:+.1f}..{mh:+.1f}] | {100 * np.mean([x['net'] > 0 for x in v]):.0f} | |")
    # ------------------------------------------------------------------ 3. limit / fill
    P("\n# 3. Limit and fill rate on the dumps BOTH of us went for (248 filled; we landed >= 1 attempt after the dump), D2-D5 (MEASURED)")
    P("| our path | events | we filled (S_FILL+S_NEAR) | we failed (S_FAIL) | fail share | 248 net on our fails SOL/day | 248 mSOL/lot there | 248 price/post p50 there | share of those 248 buys > 1.05 x post | our failed-attempt cost SOL/day |")
    P("|---|---|---|---|---|---|---|---|---|---|")
    def opath(h):
        if h["bucket"] in ("S_FILL", "S_NEAR"): return collections.Counter(x["path"] for x in h["pair"]).most_common(1)[0][0]
        return collections.Counter(f["path"] for f in h["fails"]).most_common(1)[0][0]
    J["limit"] = {}
    for p in ("ps", "reg", "other", "ALL"):
        ev = [h for h in hD if h["bucket"] in ("S_FILL", "S_NEAR", "S_FAIL") and (p == "ALL" or opath(h) == p)]
        fl = [h for h in ev if h["bucket"] == "S_FAIL"]
        if not ev: continue
        fc = sum(f["cost"] for h in fl for f in h["fails"])
        J["limit"][p] = dict(ev=len(ev), fail=len(fl), net=sum(x["net"] for x in fl))
        P(f"| {p} | {len(ev)} | {len(ev) - len(fl)} | {len(fl)} | {100 * len(fl) / len(ev):.0f}% | {sum(x['net'] for x in fl) / ND:+.2f} | {1e3 * np.mean([x['net'] for x in fl]) if fl else 0:+.1f} | "
              f"{q([x['px_vs_post'] for x in fl if x['dumpre']], 50):.3f} | {100 * np.mean([(x['px_vs_post'] or 0) > 1.05 for x in fl if x['dumpre']]) if fl else 0:.0f}% | {-fc / ND:+.3f} |")
    fl = [h for h in hD if h["bucket"] == "S_FAIL" and h["dumpre"]]
    P("- 248 on our failed events by its price paid vs post-dump (MEASURED):")
    for lo_, hi_ in ((0, 1.05), (1.05, 1.10), (1.10, 99)):
        v = [x for x in fl if lo_ < (x["px_vs_post"] or 0) <= hi_]
        if v: P(f"  - {lo_:.2f}-{hi_:.2f}: {len(v)} lots, {1e3 * np.mean([x['net'] for x in v]):+.1f} mSOL/lot, {sum(x['net'] for x in v) / ND:+.2f} SOL/day")
    nf = collections.Counter(f["code"] for h in hD if h["bucket"] == "S_FAIL" for f in h["fails"])
    P(f"- our failure codes on those events: {dict(nf)}")
    P(f"- 248's own failed buy txs (code 248): {len(HF)} over all days vs {len(H):,} lots ({100 * len(HF) / (len(HF) + len(H)):.1f}% fail), errors {collections.Counter(f['err'][:30] for f in HF).most_common(3)}")
    # ------------------------------------------------------------------ 4. size
    P("\n# 4. Size (MEASURED sizes; P&L at the other size = exact-curve replay at the SAME tape position and exit, INFERRED)")
    P(f"- 248 SOL in per lot p5/p50/p95: {q([h['cost'] for h in H], 5):.3f} / {q([h['cost'] for h in H], 50):.3f} / {q([h['cost'] for h in H], 95):.3f}; "
      f"ours: pre-send {q([x['cost'] for x in O if x['path'] == 'ps'], 50):.3f}, regular {q([x['cost'] for x in O if x['path'] == 'reg'], 50):.3f} (p5 {q([x['cost'] for x in O], 5):.3f}, p95 {q([x['cost'] for x in O], 95):.3f})")
    for p in ("ps", "reg"):
        v = [(x, RO[("O", x["slot"], x["idx"])]) for x in oD if x["path"] == p and ("O", x["slot"], x["idx"]) in RO]
        a = sum(r["A"] for x, r in v); s = sum(r["s30"] for x, r in v)
        per = [sum(r["s30"] - r["A"] for x, r in v if x["day"] == d) for d in DAYS]
        P(f"- all our {p} fills D2-D5 ({len(v)}): actual {a:+.3f} SOL, at 0.30 SOL {s:+.3f} -> {(s - a) / ND:+.3f} SOL/day ({1e3 * (s - a) / len(v):+.2f} mSOL/fill); per day {', '.join(f'{x:+.3f}' for x in per)}")
    dsz = [r["S1"] - r["Ap"] for r in PP]
    P(f"- shared pairs (all days, {len(PP)}): our fills re-sized to 248's size: {sum(dsz):+.3f} SOL ({1e3 * np.mean(dsz):+.2f} mSOL/pair)")
    # ------------------------------------------------------------------ 5. exit
    P("\n# 5. Exit")
    P("## 5a. Hold (buy -> last sell, chain clock) (MEASURED)")
    P("| set | lots | hold s p10/p25/p50/p75/p90 | sells per lot = 1 % |"); P("|---|---|---|---|")
    def hl(v, nm):
        hs = [x["hold_ms"] / 1000 for x in v if x["hold_ms"] is not None]
        P(f"| {nm} | {len(v):,} | {q(hs, 10):.2f} / {q(hs, 25):.2f} / {q(hs, 50):.2f} / {q(hs, 75):.2f} / {q(hs, 90):.2f} | {100 * np.mean([len(x['sells']) == 1 for x in v]):.0f}% |")
    hl(H, "248 all"); hl([h for h in H if h["dumpre"]], "248 dump-reactive")
    hl([h for r, h, x in PA], "248 on shared pairs"); hl([x for r, h, x in PA], "ours on shared pairs")
    hl([x for x in O if x["path"] == "ps"], "ours pre-send all"); hl([x for x in O if x["path"] == "reg"], "ours regular all")
    P("\n## 5b. Same tokens, swapped exit time (exact replay; a sell at the other's sell row valued half before / half after it), shared pairs, all days (INFERRED replay of MEASURED rows)")
    for p in ("ps", "reg", "ALL"):
        v = [(r, h, x) for r, h, x in PA if p == "ALL" or x["path"] == p]
        if not v: continue
        d1 = [r["o_at_h"] - r["A"] for r, h, x in v]; d2 = [r["Hh"] - r["h_at_o"] for r, h, x in v]
        b1 = boot_mean([1e3 * z for z in d1]); b2 = boot_mean([1e3 * z for z in d2])
        P(f"- {p} ({len(v)} pairs): OUR tokens sold at 248's time instead of ours: {sum(d1):+.3f} SOL ({1e3 * np.mean(d1):+.2f} mSOL/pair [{b1[0]:+.2f}..{b1[1]:+.2f}]); "
          f"248's tokens: its own time vs OUR time: {sum(d2):+.3f} SOL ({1e3 * np.mean(d2):+.2f} [{b2[0]:+.2f}..{b2[1]:+.2f}]) "
          f"(248 had bought before our sell in {100 * np.mean([r['h_bought_before_our_sell'] for r, h, x in v]):.0f}%)")
    P("\n## 5c. All our fills: alternative timer exits (decision at fill + T, sell lands +59 ms; exact replay, INFERRED), SOL per day D2-D5")
    for p in ("ps", "reg"):
        v = [(x, RO[("O", x["slot"], x["idx"])]) for x in oD if x["path"] == p and ("O", x["slot"], x["idx"]) in RO]
        row = []
        for k in ("A", "t1s", "t2s", "t42", "t8s"):
            per = [sum(r[k] for x, r in v if x["day"] == d) for d in DAYS]
            row.append(f"{k} {np.mean(per):+.3f} ({', '.join(f'{z:+.2f}' for z in per)})")
        P(f"- {p}: " + " | ".join(row))
    # ------------------------------------------------------------------ 6. costs
    P("\n# 6. Tx costs per lot (MEASURED fee + tips of every landed tx; failed attempts spread over fills), D2-D5")
    hc = [h["txc"] for h in hD]
    hfc = sum(f["fee"] for f in HF if L.day_of(f["bt"]) in DAYS)
    P(f"- 248: buy {1e3 * np.mean([h['txc_buy'] for h in hD]):.3f} + sell {1e3 * np.mean([h['sxc'] for h in hD]):.3f} + failed {1e3 * hfc / len(hD):.3f} = {1e3 * (np.mean(hc) + hfc / len(hD)):.3f} mSOL/lot")
    J["cost"] = {}
    for p in ("ps", "reg"):
        v = [x for x in oD if x["path"] == p]; fc = sum(f["cost"] for f in fD if f["path"] == p)
        J["cost"][p] = dict(n=len(v), lot=float(np.mean([x["txc"] for x in v])), fail=fc / len(v))
        P(f"- ours {p}: buy {1e3 * np.mean([x['txc_buy'] for x in v]):.3f} + sell {1e3 * np.mean([x['sxc'] for x in v]):.3f} + failed attempts {1e3 * fc / len(v):.3f} "
          f"(= {sum(1 for f in fD if f['path'] == p):,} failed txs / {len(v)} fills) = {1e3 * (np.mean([x['txc'] for x in v]) + fc / len(v)):.3f} mSOL/fill")
    # ------------------------------------------------------------------ 7. concurrency
    P("\n# 7. Concurrency (MEASURED)")
    iv = sorted((h["cc"], h["close_cc"] if h["close_cc"] else h["cc"] + 60000) for h in H)
    tot = collections.Counter()
    for a, b in iv:
        d = L.day_of(L.slot_time(a / 212.0)) if False else None
    starts = np.array([a for a, b in iv]); ends = np.array([b for a, b in iv])
    ends_s = np.sort(ends)
    def nopen(t): return int(np.searchsorted(starts, t, side="left") - np.searchsorted(ends_s, t, side="right"))
    for h in H: h["n_open248"] = nopen(h["cc"])
    span = (max(ends) - min(starts)) / 1000
    P(f"- 248 open lots, time-weighted mean over the tape: {sum(b - a for a, b in iv) / 1000 / span:.2f}; at its own buys (other 248 lots open) p50 {q([h['n_open248'] for h in H], 50):.0f}, p90 {q([h['n_open248'] for h in H], 90):.0f}, max {max(h['n_open248'] for h in H)}")
    P("| other 248 lots open at the buy | lots D2-D5 | SOL/day | mSOL/lot |"); P("|---|---|---|---|")
    J["conc"] = {}
    for lo_, hi_ in ((0, 0), (1, 1), (2, 3), (4, 10 ** 9)):
        v = [h for h in hD if lo_ <= h["n_open248"] <= hi_]
        J["conc"][f"{lo_}-{hi_}"] = dict(n=len(v), net=sum(h["net"] for h in v))
        P(f"| {lo_}-{hi_ if hi_ < 10 ** 9 else '+'} | {len(v):,} | {sum(h['net'] for h in v) / ND:+.2f} | {1e3 * np.mean([h['net'] for h in v]):+.1f} |")
    v = [h for h in hD if h["bucket"] == "REF:one-position busy"]
    P(f"- 248 lots on dumps our engine refused because a position/arm was open (REF:one-position busy): {len(v)} lots, {sum(h['net'] for h in v) / ND:+.3f} SOL/day")
    # ------------------------------------------------------------------ 8. head to head P&L
    P("\n# 8. Head-to-head P&L on the same dump (S_FILL pairs) (MEASURED tape P&L incl. each side's buy+sell tx costs)")
    P("| day | pairs | ours SOL | 248 SOL | ours mSOL/pair | 248 mSOL/pair | ours - 248 mSOL/pair [90%] |"); P("|---|---|---|---|---|---|---|")
    for d in list(range(7)) + ["ALL"]:
        v = [(r, h, x) for r, h, x in PA if d == "ALL" or x["day"] == d]
        if not v: continue
        df = [1e3 * (r["A"] - r["Hh"]) for r, h, x in v]; b = boot_mean(df)
        P(f"| {L.day_name(d) if d != 'ALL' else 'ALL'} | {len(v)} | {sum(r['A'] for r, h, x in v):+.3f} | {sum(r['Hh'] for r, h, x in v):+.3f} | {1e3 * np.mean([r['A'] for r, h, x in v]):+.1f} | "
          f"{1e3 * np.mean([r['Hh'] for r, h, x in v]):+.1f} | {np.mean(df):+.1f} [{b[0]:+.1f}..{b[1]:+.1f}] |")
    for p in ("ps", "reg", "other"):
        v = [(r, h, x) for r, h, x in PA if x["path"] == p]
        if v:
            df = [1e3 * (r["A"] - r["Hh"]) for r, h, x in v]; b = boot_mean(df)
            P(f"- {p}: {len(v)} pairs, ours {1e3 * np.mean([r['A'] for r, h, x in v]):+.1f} vs 248 {1e3 * np.mean([r['Hh'] for r, h, x in v]):+.1f} mSOL/pair, diff {np.mean(df):+.1f} [{b[0]:+.1f}..{b[1]:+.1f}]")
    P("## 8b. Decomposition of 248 - ours on the pairs (exact replay chain; residuals R1/R2 = replay vs measured)")
    for p in ("ps", "reg", "other", "ALL"):
        v = [r for r, h, x in PA if p == "ALL" or x["path"] == p]
        if not v: continue
        S = lambda k: sum(r[k] for r in v)
        P(f"- {p} ({len(v)}): ours {S('A'):+.3f} | R1 {S('A') - S('Ap'):+.4f} | size {S('S1') - S('Ap'):+.3f} | exit {S('S2') - S('S1'):+.3f} | entry {S('S3') - S('S2'):+.3f} | "
          f"costs {S('S4') - S('S3'):+.3f} | R2 {S('Hh') - S('S4'):+.4f} | = 248 {S('Hh'):+.3f}")
    J["pairs"] = [dict(day=x["day"], path=x["path"], **{k: r[k] for k in ("A", "Ap", "S1", "S2", "S3", "S4", "Hh")}, hn=sum(1 for z in PA if z[1] is h), on=len(x["pair"]), h=r["h"], o=r["o"]) for r, h, x in PA]
    open(f"{OUT}/v4_tables.txt", "w").write("\n".join(out) + "\n")
    json.dump(J, open(f"{OUT}/v4.json", "w"), default=float)


if __name__ == "__main__":
    main()
