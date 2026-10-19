#!/usr/bin/env python3
# READ-ONLY analysis of /root/race/race_ds.jsonl -> report on stdout.
# 1) race-label definitions + sensitivity, 2) what predicts a race at create time (tiers by what is visible when),
# 3) time-split OOS validation of rule combos, 4) realistic PnL at our landing.
import json, sys, math, itertools, statistics as st, collections

R = [json.loads(l) for l in open("/root/race/race_ds.jsonl")]
R = [r for r in R if not r["quote"]]
R.sort(key=lambda r: r["slot"])
N_POP, N_RAND = 107544, 3976          # creates in the window / random sample size (nob)
WGT = N_POP / N_RAND                  # each random row stands for ~27 creates
BOT = {"gg.sc", "ipfs.launchblitz.ai", "pf.jake-98f.workers.dev", "storage.googleapis.com"}
K = 30.0 * 1.073e9
FEE = 0.0125
PRIO_RT = 0.0013                      # our buy (Helius tip+prio ~0.001) + sell (~0.0003), SOL
HOURS = None


def hostbad(r):
    h = r.get("uri_host") or ""
    return h in BOT or h.endswith(".trycloudflare.com")


def eng_dev(r):           # what the CURRENT engine reads: sized buys only
    return r["dev_sol"] if r["dev_kind"] == "sized" else 0.0


def old_filter(r):
    return (not hostbad(r)) and (not r["mayhem"]) and 0.5 <= eng_dev(r) <= 8 and bool(r.get("uri_host"))


def fix_filter(r):        # same filter, dev read correctly for cap-family buys too (--dev-from-cap)
    return (not hostbad(r)) and (not r["mayhem"]) and 0.5 <= r["dev_sol"] <= 8 and bool(r.get("uri_host"))


LABELS = {   # all counts EXCLUDE 4yFAz himself (so "his picks are races" is not circular); outsider rules in race_lib.labels
    "S>=1 out": lambda r: r["outS_nx"] >= 1,
    "S+S1>=2 out": lambda r: r["out01_nx"] >= 2,
    "S+S1>=3 out": lambda r: r["out01_nx"] >= 3,
    "S+S1>=5 out": lambda r: r["out01_nx"] >= 5,
    "2s out SOL>=1": lambda r: r["out2s_solx"] >= 1,
    "2s out SOL>=3": lambda r: r["out2s_solx"] >= 3,
    "2s out SOL>=5": lambda r: r["out2s_solx"] >= 5,
    "RACE 2s>=3 buyers&>=3 SOL": lambda r: r["out2s_nx"] >= 3 and r["out2s_solx"] >= 3,
    "2s>=5 buyers&>=5 SOL": lambda r: r["out2s_nx"] >= 5 and r["out2s_solx"] >= 5,
}
RACE = lambda r: r["out2s_nx"] >= 3 and r["out2s_solx"] >= 3   # primary label (sensitivity shown for the others)


def wsum(rows):
    return sum(1 for r in rows if r["in_rand"])


# ---------------------------------------------------------------- price sim at our landing
def entry_vsol(r, d_land):
    v = r["base"]
    for d, vs in r["sv"]:
        if d <= d_land:
            v = vs
        else:
            break
    return v


def sim(r, d_land=100, size=1.0, tp=1.3, T=10000, sl=None, land_s1=False):
    """buy behind every S trade at offset <= d_land (or behind all of S when land_s1); exit at TP/SL/T on the path."""
    if land_s1:
        ve, t0 = (r["sv"][-1][1] if r["sv"] else r["base"]), 217.0
    else:
        ve, t0 = entry_vsol(r, d_land), d_land * r["ms_per_tx"]
    ve /= 1e9
    s_in = size * (1 - FEE)
    tok = K / ve - K / (ve + s_in)
    vx = ve
    for t, v in r["path"]:
        if t <= t0:
            continue
        if t - t0 > T:
            break
        vx = v / 1e9
        rr = (vx / ve) ** 2
        if (tp and rr >= tp) or (sl and rr <= sl):
            break
    vq = vx + s_in
    out = (vq - K / (K / vq + tok)) * (1 - FEE)
    return (out - size - PRIO_RT) / size, (ve * 1e9 / r["base"]) ** 2


EXITS = [(tp, T, sl) for tp in (1.1, 1.2, 1.3, 1.5, 2.0, None) for T in (1000, 3000, 10000, 30000) for sl in (None, 0.8)]


def pnl_stats(v):
    if not v:
        return "n=0"
    ex = sorted(v)[:-3] if len(v) > 12 else v
    return f"n={len(v):4} avg {st.mean(v):+.1%} med {st.median(v):+.1%} ex-top3 {st.mean(ex):+.1%} win {sum(x > 0 for x in v) / len(v):.0%}"


# ---------------------------------------------------------------- features / conditions
def live_rows():
    try:
        sys.path.insert(0, "/root/race")
        from race_lib import labels
        pros = frozenset(json.load(open("/root/race/pros.json")))
        out = []
        for l in open("/root/race/live_fires.jsonl"):
            x = json.loads(l)
            b, s = x.get("b") or {}, x.get("s") or {}
            if "csig" in b and s and "sig_err" not in s:
                o = labels(b, s, pros)
                o["glued"] = b.get("glued", 0)
                out.append(o)
        return out
    except Exception as ex:
        print("live fires:", ex)
        return []


def mx(a):
    return max(a) if a else 0


def first_n_within(r, w_tx):
    ds = [d for d in r["outS_d"] if d <= w_tx]
    return len(ds)


def within_ms(r, ms):
    return first_n_within(r, ms / r["ms_per_tx"])


C = {}  # name -> (tier, fn)


def add(tier, name, fn):
    C[name] = (tier, fn)


# tier A: the create tx itself (zero latency)
for t in (0.5, 1.0, 1.5, 2.0, 3.0):
    add("A", f"dev>={t}", lambda r, t=t: r["dev_sol"] >= t)
for t in (3.0, 5.0):
    add("A", f"dev<={t}", lambda r, t=t: r["dev_sol"] <= t)
add("A", "dev=sized", lambda r: r["dev_kind"] == "sized")
add("A", "dev=cap", lambda r: r["dev_kind"] == "cap")
add("A", "dev_ix=BuyV2", lambda r: r["dev_ix"] == "BuyV2")
add("A", "dev_ix=BuyV3", lambda r: r["dev_ix"] == "BuyV3")
add("A", "dev_ix=Buy", lambda r: r["dev_ix"] == "Buy")
add("A", "dev_ix=ExactSolIn", lambda r: r["dev_ix"] == "BuyExactSolIn")
add("A", "dev_ix=QuoteIn", lambda r: r["dev_ix"] == "BuyExactQuoteI")
for t in (100_000, 1_000_000, 3_000_000, 10_000_000):
    add("A", f"cu_price>={t}", lambda r, t=t: (r["cu_price"] or 0) >= t)
add("A", "cu_price<100k", lambda r: (r["cu_price"] or 0) < 100_000)
for t in (0.0005, 0.002, 0.005):
    add("A", f"prio>={t}", lambda r, t=t: (r["prio_sol"] or 0) >= t)
add("A", "ctip", lambda r: bool(r["ctip"]))
add("A", "no ctip", lambda r: not r["ctip"])
for lab in ("jito", "lunar", "helius_sender", "nozomi", "astralane"):
    add("A", f"tip={lab}", lambda r, lab=lab: r["ctip_label"] == lab)
    add("A", f"tip!={lab}", lambda r, lab=lab: r["ctip_label"] != lab)
add("A", "nsig=1", lambda r: r["nsig"] == 1)
add("A", "nsig>=2", lambda r: r["nsig"] >= 2)
add("A", "txver=0", lambda r: str(r["txver"]) == "0")
add("A", "txver=legacy", lambda r: str(r["txver"]) != "0")
add("A", "t22", lambda r: bool(r["t22"]))
add("A", "payer!=creator", lambda r: not r["payer_is_creator"])
add("A", "payer=creator", lambda r: bool(r["payer_is_creator"]))
add("A", "nkeys<=20", lambda r: r["nkeys"] <= 20)
add("A", "nkeys>=26", lambda r: r["nkeys"] >= 26)
add("A", "progs=pump-only", lambda r: r["progs"] == "6EF8rr")
add("A", "progs has 111111 first", lambda r: r["progs"].startswith("111111"))
add("A", "progs=6EF8rr>AToken>6EF8rr", lambda r: r["progs"] == "6EF8rr>AToken>6EF8rr")
for h in ("ipfs.io", "metadata.j7tracker.io", "meta.uxento.io", "m.rapidlaunch.io"):
    add("A", f"host={h}", lambda r, h=h: r["uri_host"] == h)
    add("A", f"host!={h}", lambda r, h=h: r["uri_host"] != h)
add("A", "host in (ipfs.io,j7)", lambda r: r["uri_host"] in ("ipfs.io", "metadata.j7tracker.io"))
add("A", "mint_pump", lambda r: bool(r["mint_pump"]))
add("A", "name<=12", lambda r: r["n_len"] <= 12)
add("A", "name 1 word", lambda r: r["n_words"] == 1)
add("A", "sym upper", lambda r: bool(r["s_upper"]))
add("A", "sym_eq_name", lambda r: bool(r["sym_eq_name"]))
for cl in ("AgaveBam", "Harmonic", "JitoLabs", "Firedancer"):
    add("A", f"client={cl}", lambda r, cl=cl: r["client"] == cl)
add("A", "client!=Harmonic", lambda r: r["client"] != "Harmonic")
add("A", "dev_n>=2", lambda r: (r["dev_n"] or 0) >= 2)
# tier B: + the glued creator bundle (same entry, ~1 ms later)
add("B", "bundle", lambda r: r["glued"] >= 1)
add("B", "no bundle", lambda r: r["glued"] == 0)
add("B", "bundle>=1SOL", lambda r: r["gsol"] >= 1)
add("B", "bundle<3SOL", lambda r: r["gsol"] < 3)
add("B", "bundle>=3SOL", lambda r: r["gsol"] >= 3)
add("B", "bundle>=2tx", lambda r: r["glued"] >= 2)
# tier C: + creator wallet lookup (one RPC, or a cache)
add("C", "creator 0 prior launches", lambda r: r.get("cr_nlaunch") == 0)
add("C", "creator <3 prior launches", lambda r: (r.get("cr_nlaunch") if r.get("cr_nlaunch") is not None else 99) < 3)
add("C", "creator >=5 prior launches", lambda r: (r.get("cr_nlaunch") or 0) >= 5)
for t in (10, 50):
    add("C", f"creator prior txs<={t}", lambda r, t=t: (r.get("cr_nprior") if r.get("cr_nprior") is not None else 9999) <= t)
for t in (300, 1800):
    add("C", f"creator idle>={t}s", lambda r, t=t: (r.get("cr_idle_s") or 0) >= t)
for t in (2, 11):
    add("C", f"creator bal>={t}", lambda r, t=t: (r.get("cpre_sol") or 0) >= t)
add("C", "creator age>=24h", lambda r: (r.get("cr_age_h") or 0) >= 24)
# tier D: + metadata JSON fetch (50-500 ms)
add("D", "socials>=1", lambda r: (r.get("n_socials") or 0) >= 1)
add("D", "socials>=2", lambda r: (r.get("n_socials") or 0) >= 2)
add("D", "has twitter", lambda r: bool(r.get("has_tw")))
add("D", "tw=status", lambda r: r.get("tw_kind") == "status")
add("D", "tw=profile", lambda r: r.get("tw_kind") == "profile")
add("D", "has web", lambda r: bool(r.get("has_web")))
add("D", "has tg", lambda r: bool(r.get("has_tg")))
add("D", "meta keys>=8", lambda r: (r.get("meta_nkeys") or 0) >= 8)
add("D", "community", lambda r: bool(r.get("has_community")))
# tier E: + the first outside buys seen in the shred stream in S (we wait, then fire behind them)
for ms in (25, 50, 100, 200):
    add("E", f">=1 out-buy in {ms}ms", lambda r, ms=ms: within_ms(r, ms) >= 1)
    add("E", f">=2 out-buys in {ms}ms", lambda r, ms=ms: within_ms(r, ms) >= 2)
for ms in (50, 100, 200):
    for sol in (0.5, 2.0):
        add("E", f">={sol} SOL out in {ms}ms", lambda r, ms=ms, sol=sol: sum(v for d, v in zip(r["outS_d"], r["outS_sv"]) if d * r["ms_per_tx"] <= ms) >= sol)
add("E", "out-buy prio>=1M in 100ms", lambda r: any(d * r["ms_per_tx"] <= 100 and cu >= 1_000_000 for d, cu in zip(r["outS_d"], r["outS_cu"])))
TIERS = {"A": "create tx only (0 ms)", "B": "+ creator bundle (~1 ms)", "C": "+ creator wallet RPC (10-50 ms or cache)",
         "D": "+ metadata fetch (50-500 ms)", "E": "+ wait for first outside buys in S (25-200 ms)"}
TIER_WAIT_MS = {"A": 0, "B": 1, "C": 30, "D": 200}


def main():
    rand = [r for r in R if r["in_rand"]]
    his = [r for r in R if r["his"]]
    span_h = (R[-1]["slot"] - R[0]["slot"]) * 0.217 / 3600
    pop_per_h = len(rand) * WGT / span_h
    print(f"rows {len(R)} (SOL-quoted) | random {len(rand)} | 4yFAz picks {len(his)} | slots {R[0]['slot']}..{R[-1]['slot']} (~{span_h:.0f} h)")
    print(f"each random row ~{WGT:.1f} creates; ~{pop_per_h:.0f} SOL launches per hour in the population")
    print(f"window coverage: S+1..S+5 fetched for every row (cap 90 txs; capped rows {sum(r['s1_capped'] for r in R)}); later path present {sum(r['has_path'] for r in R)}")

    # ---------------- 1. label definitions
    print("\n=== 1. RACE LABEL: share of launches that are 'races' under each definition ===")
    groups = [("all SOL launches (random)", rand), ("not mayhem (random)", [r for r in rand if not r["mayhem"]]),
              ("OLD filter fires (sized dev 0.5-8, host ok, not mayhem)", [r for r in rand if old_filter(r)]),
              ("FIX filter (true dev 0.5-8 incl. cap buys)", [r for r in rand if fix_filter(r)]),
              ("  ..of which skipped by the dev bug (cap-family dev)", [r for r in rand if fix_filter(r) and not old_filter(r)]),
              ("4yFAz picks (all)", his), ("4yFAz picks, no bundle", [r for r in his if r["glued"] == 0])]
    live = live_rows()
    if live:
        groups.append(("OUR 42 LIVE FIRES today (on-chain)", live))
    hdr = " | ".join(f"{k:>10}" for k in LABELS)
    print(f"{'group':58} {'n':>5} | " + " | ".join(f"{k[:16]:>16}" for k in LABELS))
    for gn, g in groups:
        if not g:
            continue
        print(f"{gn:58} {len(g):5} | " + " | ".join(f"{sum(1 for r in g if fn(r)) / len(g):16.0%}" for fn in LABELS.values()))
    print("(outsider = a buy tx in the window whose payer and buyers are not the creator, the create payer, or a glued-bundle wallet; 4yFAz counts as outsider)")
    print("Primary label RACE = >=3 distinct outside buyers AND >=3 SOL of outside buys in S..S+5 (~2 s), 4yFAz excluded. Second label: bought by 4yFAz.")
    # how outsiders and 4yFAz relate
    for gn, g in groups[2:4]:
        rc = [r for r in g if RACE(r)]
        print(f"   {gn[:40]:40}: races {len(rc)}/{len(g)}; 4yFAz bought {sum(r['his'] for r in rc)} of the races (random rows)")
    print(f"   4yFAz picks that are races: {sum(RACE(r) for r in his)}/{len(his)} = {sum(RACE(r) for r in his)/max(1,len(his)):.0%}")
    # distribution of outsider count among his picks vs fix-filter
    print("\n   outsiders in S+S1 excl. 4yFAz (distribution):  0 / 1 / 2 / 3-4 / 5-9 / 10+")
    for gn, g in [groups[2], groups[3], groups[5]] + groups[7:]:
        b = collections.Counter(0 if r["out01_nx"] == 0 else 1 if r["out01_nx"] == 1 else 2 if r["out01_nx"] == 2 else 3 if r["out01_nx"] <= 4 else 5 if r["out01_nx"] <= 9 else 10 for r in g)
        print(f"   {gn[:52]:52} " + " / ".join(f"{b[k] / len(g):4.0%}" for k in (0, 1, 2, 3, 5, 10)))
    print("   2 s outside SOL excl. 4yFAz: median / p75 / p90")
    for gn, g in [groups[2], groups[3], groups[5]] + groups[7:]:
        v = sorted(r["out2s_solx"] for r in g)
        print(f"   {gn[:52]:52} {v[len(v) // 2]:6.2f} / {v[int(len(v) * .75)]:6.2f} / {v[int(len(v) * .9)]:6.2f}")

    # ---------------- 2. single-feature lifts (base = not mayhem, host ok)
    base = [r for r in R if not r["mayhem"] and not hostbad(r)]
    n = len(base)
    cut = base[int(n * 0.6)]["slot"]
    TR = [r for r in base if r["slot"] < cut]
    TE = [r for r in base if r["slot"] >= cut]
    print(f"\n=== 2. SINGLE CONDITIONS (base: not mayhem, host not a bot pad). time split at slot {cut}: train {sum(r['in_rand'] for r in TR)} random rows, test {sum(r['in_rand'] for r in TE)} ===")

    def evalc(rows, fn, lab=RACE):
        rr = [r for r in rows if r["in_rand"]]
        p = [r for r in rr if fn(r)]
        hp = [r for r in rows if r["his"] and fn(r)]
        hall = [r for r in rows if r["his"]]
        prec = sum(lab(r) for r in p) / len(p) if p else float("nan")
        base_rate = sum(lab(r) for r in rr) / len(rr) if rr else float("nan")
        his_prec = len(hp) / (len(p) * WGT) if p else float("nan")
        return dict(n=len(p), prec=prec, lift=prec / base_rate if base_rate else float("nan"), his_prec=his_prec,
                    his_rec=len(hp) / len(hall) if hall else float("nan"), nh=len(hp), share=len(p) / len(rr) if rr else 0)

    b_tr, b_te = evalc(TR, lambda r: True), evalc(TE, lambda r: True)
    print(f"base race rate: train {b_tr['prec']:.1%} test {b_te['prec']:.1%}; his precision train {b_tr['his_prec']:.2%} test {b_te['his_prec']:.2%}")
    print(f"{'condition':34} tier | {'TRAIN n':>7} race% lift | {'TEST n':>6} race% lift | his-prec tr/te | his-recall te")
    sing = []
    for name, (tier, fn) in C.items():
        a, b = evalc(TR, fn), evalc(TE, fn)
        if a["n"] < 20:
            continue
        sing.append((a["lift"], name, tier, a, b))
    for lift, name, tier, a, b in sorted(sing, key=lambda z: -z[0]):
        print(f"{name:34} {tier:4} | {a['n']:7} {a['prec']:5.0%} {a['lift']:4.1f} | {b['n']:6} {b['prec']:5.0%} {b['lift']:4.1f} | {a['his_prec']:6.2%} / {b['his_prec']:6.2%} | {b['his_rec']:5.0%}")

    # ---------------- 3. combo search per tier (cumulative), on top of the dev-fixed base filter
    print("\n=== 3. RULE COMBOS (on top of FIX filter: true dev 0.5-8, host ok, not mayhem). Fit = TRAIN race precision with n>=40, "
          "Wilson lower bound; then TEST. his-prec is population-weighted. ===")
    FB = [r for r in base if fix_filter(r)]
    TRf = [r for r in FB if r["slot"] < cut]
    TEf = [r for r in FB if r["slot"] >= cut]
    o_tr, o_te = evalc([r for r in TR if old_filter(r)], lambda r: True), evalc([r for r in TE if old_filter(r)], lambda r: True)
    f_tr, f_te = evalc(TRf, lambda r: True), evalc(TEf, lambda r: True)
    # his recall vs ALL his picks in the test period (any filter)
    allhis_te = [r for r in R if r["his"] and r["slot"] >= cut]
    hr_old = sum(1 for r in allhis_te if old_filter(r)) / max(1, len(allhis_te))
    hr_fix = sum(1 for r in allhis_te if fix_filter(r)) / max(1, len(allhis_te))
    print(f"OLD filter : train n={o_tr['n']} race {o_tr['prec']:.0%} his-prec {o_tr['his_prec']:.2%} | test n={o_te['n']} race {o_te['prec']:.0%} his-prec {o_te['his_prec']:.2%} his-recall {hr_old:.0%} | fires/h {o_te['n'] * WGT / (span_h * 0.4):.0f}")
    print(f"FIX filter : train n={f_tr['n']} race {f_tr['prec']:.0%} his-prec {f_tr['his_prec']:.2%} | test n={f_te['n']} race {f_te['prec']:.0%} his-prec {f_te['his_prec']:.2%} his-recall {hr_fix:.0%} | fires/h {f_te['n'] * WGT / (span_h * 0.4):.0f}")
    print(f"(test period: {len(allhis_te)} 4yFAz picks; his-recall = share of ALL his test picks that the rule fires on)")

    def wilson(k, n, z=1.64):
        if n == 0:
            return 0
        p = k / n
        return (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)

    best_all = {}
    for upto in "ABCDE":
        names = [nm for nm, (t, _) in C.items() if t <= upto]
        RM = sum(1 << i for i, r in enumerate(TRf) if r["in_rand"])
        LM = sum(1 << i for i, r in enumerate(TRf) if r["in_rand"] and RACE(r))
        bm = {nm: sum(1 << i for i, r in enumerate(TRf) if C[nm][1](r)) & RM for nm in names}
        res = []
        for k in (1, 2, 3):
            for combo in itertools.combinations(names, k):
                if upto != "A" and not any(C[c][0] == upto for c in combo):
                    continue
                m = RM
                for c in combo:
                    m &= bm[c]
                nn = bin(m).count("1")
                if nn < 40:
                    continue
                kk = bin(m & LM).count("1")
                res.append((wilson(kk, nn), combo, nn, kk))
        res.sort(key=lambda z: -z[0])
        print(f"\n-- tier <= {upto} ({TIERS[upto]}): top combos by TRAIN lower-bound race precision")
        print(f"{'rule':78} | TRAIN n race% | TEST n race% his-prec his-rec(all his) | fires/h")
        shown = 0
        seen = set()
        for lb, combo, nn, kk in res:
            key = frozenset(combo)
            if key in seen:
                continue
            seen.add(key)
            fn = lambda r, combo=combo: all(C[c][1](r) for c in combo)
            b = evalc(TEf, fn)
            hr = sum(1 for r in allhis_te if fix_filter(r) and fn(r)) / max(1, len(allhis_te))
            fph = b["share"] * f_te["n"] * WGT / (span_h * 0.4) if span_h else 0
            print(f"{' & '.join(combo):78} | {nn:5} {kk / nn:5.0%} | {b['n']:4} {b['prec']:5.0%} {b['his_prec']:6.2%} {hr:5.0%} | {fph:5.1f}")
            if shown == 0:
                best_all[upto] = (combo, nn, kk / nn, b)
            shown += 1
            if shown >= 10:
                break

    # ---------------- 4. realistic PnL
    print("\n=== 4. REALISTIC PnL at our landing: 1 SOL, entry behind every S trade at offset <= d_land txs (d_land = 100 + the "
          "rule's wait), pump fee 1.25%/side, 0.0013 SOL fees/RT, own impact on both legs. Random rows with a later path. ===")
    print("Exits (fixed, not fitted per rule): X1 = sell at +1 s; X2 = TP +30% else 10 s; X3 = TP +100% else 30 s. "
          "'S+1' = land one slot late (behind all of S). 80/20 = 0.8 x S + 0.2 x S+1 (Helius lands in S ~4 of 5).")
    XS = {"X1 1s": (None, 1000, None), "X2 tp1.3/10s": (1.3, 10000, None), "X3 tp2/30s": (2.0, 30000, None)}
    rules = [("OLD filter", lambda r: old_filter(r), 0), ("FIX filter (dev-from-cap)", lambda r: fix_filter(r), 0)]
    for upto, (combo, *_rest) in best_all.items():
        rules.append((f"best tier<={upto}: " + " & ".join(combo), (lambda r, combo=combo: fix_filter(r) and all(C[c][1](r) for c in combo)), wait_of(combo)))
    for extra in EXTRA_RULES:
        rules.append((extra[0], (lambda r, combo=extra[1]: fix_filter(r) and all(C[c][1](r) for c in combo)), wait_of(extra[1])))
    rules.append(("HINDSIGHT: FIX filter & RACE=1 (perfect race selection)", lambda r: fix_filter(r) and RACE(r), 0))
    rules.append(("HINDSIGHT: FIX filter & RACE=0", lambda r: fix_filter(r) and not RACE(r), 0))
    PR = [r for r in base if r["in_rand"]]
    HR = [r for r in base if r["his"]]
    for rn, fn, wait in rules + [("4yFAz picks (if we knew them; entry at OUR landing)", None, 0)]:
        for period, rows in (("TEST", [r for r in PR if r["slot"] >= cut]), ("ALL", PR)):
            g = [r for r in (HR if fn is None else rows) if (fn is None and (period == "ALL" or r["slot"] >= cut)) or (fn is not None and fn(r))]
            if len(g) < 5:
                print(f"{rn[:100]} [{period}] n={len(g)} too few")
                continue
            dl = lambda r: 100 + int(wait / r["ms_per_tx"])
            fills = [sim(r, d_land=dl(r))[1] for r in g]
            line = f"{rn[:100]} [{period}] n={len(g)} race {sum(RACE(r) for r in g) / len(g):.0%} entry/floor med {st.median(fills):.2f}x"
            print(line)
            for xn, (tp, T, sl) in XS.items():
                gg = g if T <= 1500 else [r for r in g if r["has_path"]]
                if len(gg) < 5:
                    print(f"      {xn:13} n={len(gg)} (no later path)")
                    continue
                vS = [sim(r, d_land=dl(r), tp=tp, T=T, sl=sl)[0] for r in gg]
                v1 = [sim(r, land_s1=True, tp=tp, T=T, sl=sl)[0] for r in gg]
                mix = [0.8 * a + 0.2 * b for a, b in zip(vS, v1)]
                print(f"      {xn:13} land S: {pnl_stats(vS)} | S+1 avg {st.mean(v1):+.1%} | 80/20 avg {st.mean(mix):+.1%} ex-top3 {st.mean(sorted(mix)[:-3]) if len(mix) > 12 else st.mean(mix):+.1%}")
    # landing-position sensitivity
    print("\n-- landing-position sensitivity (ALL random rows, exit X1 = sell at +1 s): avg PnL / median entry multiple when we land behind the first d txs")
    for rn, fn, wait in rules + [("4yFAz picks", lambda r: r["his"], 0)]:
        g = [r for r in (HR if rn == "4yFAz picks" else PR) if fn(r)]
        if len(g) < 10:
            continue
        cells = []
        for d in (5, 25, 50, 100, 200):
            v = [sim(r, d_land=d + int(wait / r["ms_per_tx"]), tp=None, T=1000)[0] for r in g]
            f = [sim(r, d_land=d + int(wait / r["ms_per_tx"]), tp=None, T=1000)[1] for r in g]
            cells.append(f"d{d}: {st.mean(v):+.1%}/{st.median(f):.2f}x")
        print(f"   {rn[:70]:70} n={len(g):4} " + "  ".join(cells))
    return best_all


EXTRA_RULES = [
    ("E50: >=1 out-buy in 50ms", [">=1 out-buy in 50ms"]),
    ("E50: >=0.5 SOL out in 50ms", [">=0.5 SOL out in 50ms"]),
    ("E50: >=2.0 SOL out in 50ms", [">=2.0 SOL out in 50ms"]),
    ("E100: >=2.0 SOL out in 100ms", [">=2.0 SOL out in 100ms"]),
    ("E100: >=2 out-buys in 100ms", [">=2 out-buys in 100ms"]),
    ("A: dev>=2.0", ["dev>=2.0"]),
    ("B: dev>=2.0 & bundle>=1SOL", ["dev>=2.0", "bundle>=1SOL"]),
]


def wait_of(combo):
    import re
    w = 0
    for c in combo:
        m = re.search(r"in (\d+)ms", c)
        if m:
            w = max(w, int(m.group(1)))
        elif C[c][0] in TIER_WAIT_MS:
            w = max(w, TIER_WAIT_MS[C[c][0]])
    return w


def pnl_search(base, cut):
    """section 5: rank rules by TRAIN mean PnL at our landing (exit X1, d_land = 100 + wait), then check TEST."""
    print("\n=== 5. PnL-FIRST SEARCH: rules of <= 2 conditions (tiers A, B, and E windows <= 100 ms) on top of the FIX filter, ranked "
          "by TRAIN mean PnL (exit X1, land S at d<=100+wait, random rows, n>=30); TEST shown. Multiple-testing warning: ~3k rules tried. ===")
    FB = [r for r in base if fix_filter(r) and r["in_rand"]]
    TR = [r for r in FB if r["slot"] < cut]
    TE = [r for r in FB if r["slot"] >= cut]
    names = [n for n, (t, _) in C.items() if t in "AB" or (t == "E" and wait_of([n]) <= 100)]
    cache = {}

    def pn(r, w):
        k = (r["mint"], w)
        if k not in cache:
            cache[k] = sim(r, d_land=100 + int(w / r["ms_per_tx"]), tp=None, T=1000)[0]
        return cache[k]
    res = []
    for k in (1, 2):
        for combo in itertools.combinations(names, k):
            g = [r for r in TR if all(C[c][1](r) for c in combo)]
            if len(g) < 30:
                continue
            w = wait_of(combo)
            v = [pn(r, w) for r in g]
            res.append((st.mean(v), combo, len(g), w))
    res.sort(key=lambda z: -z[0])
    print(f"{'rule':70} | TRAIN n  avg   ex3  | TEST n  avg   med   ex3  win | race% his-prec")
    for a, combo, n, w in res[:15]:
        g = [r for r in TE if all(C[c][1](r) for c in combo)]
        v = [pn(r, w) for r in g]
        vt = [pn(r, w) for r in TR if all(C[c][1](r) for c in combo)]
        ex = lambda x: st.mean(sorted(x)[:-3]) if len(x) > 12 else st.mean(x)
        if len(v) < 3:
            continue
        hp = sum(1 for r in base if r["his"] and r["slot"] >= cut and fix_filter(r) and all(C[c][1](r) for c in combo)) / (len(g) * WGT)
        print(f"{' & '.join(combo)[:70]:70} | {n:4} {a:+.1%} {ex(vt):+.1%} | {len(v):4} {st.mean(v):+.1%} {st.median(v):+.1%} {ex(v):+.1%} {sum(x > 0 for x in v) / len(v):.0%} | "
              f"{sum(RACE(r) for r in g) / len(g):.0%} {hp:.1%}")


def _wait_tx(rn, r):
    if "tier<=E" not in rn:
        return 0
    import re
    m = re.search(r"in (\d+)ms", rn)
    return int(int(m.group(1)) / r["ms_per_tx"]) if m else 0


def summary(base, cut, span_h):
    print("\n=== 6. SUMMARY OF THE CANDIDATE GATES (TEST period = last 40% by slot; random rows; PnL exit X1 = sell at +1 s, 1 SOL) ===")
    G = [("OLD filter (today)", lambda r: old_filter(r), 0),
         ("FIX filter (--dev-from-cap only)", lambda r: fix_filter(r), 0),
         ("G-B  dev>=2 & creator bundle>=1 SOL (~3 ms)", lambda r: fix_filter(r) and r["dev_sol"] >= 2 and r["gsol"] >= 1, 3),
         ("G-E50 >=1 outsider & >=0.5 SOL in 50 ms", lambda r: fix_filter(r) and C[">=1 out-buy in 50ms"][1](r) and C[">=0.5 SOL out in 50ms"][1](r), 50),
         ("G-E100 >=2 SOL outside in 100 ms (fwd gate)", lambda r: fix_filter(r) and C[">=2.0 SOL out in 100ms"][1](r), 100),
         ("G-E100b >=2 outsiders & >=2 SOL in 100 ms", lambda r: fix_filter(r) and C[">=2 out-buys in 100ms"][1](r) and C[">=2.0 SOL out in 100ms"][1](r), 100),
         ("HINDSIGHT perfect race pick (FIX & RACE)", lambda r: fix_filter(r) and RACE(r), 0),
         ("4yFAz's own picks (FIX universe)", None, 0)]
    TE = [r for r in base if r["slot"] >= cut]
    hall = [r for r in TE if r["his"]]
    print(f"{'gate':46} | n  | race% | S+S1>=2 | his-prec | his-recall | fires/h | entry | X1 d100+w | 80/20 S/S+1 | X1 d25+w | win")
    for gn, fn, w in G:
        if fn is None:
            g = [r for r in hall if fix_filter(r)]
            n_eff = len(g)
            hp, hr, fph = float("nan"), len(g) / max(1, len(hall)), float("nan")
        else:
            g = [r for r in TE if r["in_rand"] and fn(r)]
            hp = sum(1 for r in hall if fn(r)) / (len(g) * WGT) if g else float("nan")
            hr = sum(1 for r in hall if fn(r)) / max(1, len(hall))
            fph = len(g) * WGT / (span_h * 0.4)
        if not g:
            continue
        v = [sim(r, d_land=100 + int(w / r["ms_per_tx"]), tp=None, T=1000)[0] for r in g]
        v1 = [sim(r, land_s1=True, tp=None, T=1000)[0] for r in g]
        v25 = [sim(r, d_land=25 + int(w / r["ms_per_tx"]), tp=None, T=1000)[0] for r in g]
        fl = [sim(r, d_land=100 + int(w / r["ms_per_tx"]))[1] for r in g]
        mix = st.mean([0.8 * a + 0.2 * b for a, b in zip(v, v1)])
        print(f"{gn:46} | {len(g):3} | {sum(RACE(r) for r in g) / len(g):4.0%} | {sum(r['out01_nx'] >= 2 for r in g) / len(g):6.0%} | "
              f"{hp:7.2%} | {hr:9.0%} | {fph:7.0f} | {st.median(fl):.2f}x | {st.mean(v):+8.1%} | {mix:+10.1%} | {st.mean(v25):+7.1%} | {sum(x > 0 for x in v) / len(v):.0%}")
    print("his-prec = share of the gate's fires that 4yFAz also bought (population-weighted); his-recall = share of all his TEST picks the gate fires on.")


if __name__ == "__main__":
    main()
    _b0 = [r for r in R if not r["mayhem"] and not hostbad(r)]
    summary(_b0, _b0[int(len(_b0) * 0.6)]["slot"], (R[-1]["slot"] - R[0]["slot"]) * 0.217 / 3600)
    _b = [r for r in R if not r["mayhem"] and not hostbad(r)]
    pnl_search(_b, _b[int(len(_b) * 0.6)]["slot"])
