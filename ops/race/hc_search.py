#!/usr/bin/env python3
# READ-ONLY. HIGH-CONVICTION tier: the strictest create-time gate (create tx + creator bundle, <= ~3 ms) that maximises the
# REALISTIC return per trade, then the exit for it. Realistic = 2 SOL, land in slot S behind every trade at offset <= 100
# txs, entry price x1.03 slip, own impact on every leg, pump fee 1.25%/side, 0.009 SOL priority on the buy and 0.001 per
# sell leg. Fit on the first 60% of the historical random sample (by slot), judge on the last 40% and on the FORWARD paper
# run (engine log + chain), which nothing was fitted on.
# usage: hc_search.py [paper_fwd.log fwd_onchain.jsonl paths_fwd.jsonl]
import json, sys, math, itertools, statistics as st, collections
sys.path.insert(0, "/root/race")

K = 30.0 * 1.073e9
FEE = 0.0125
SIZE, SLIP, PRIO_BUY, PRIO_SELL = 2.0, 1.03, 0.009, 0.001
D_LAND = 100
WGT = 107544 / 3976
BOT = {"gg.sc", "ipfs.launchblitz.ai", "pf.jake-98f.workers.dev", "storage.googleapis.com"}


def hostbad(h):
    h = h or ""
    return h in BOT or h.endswith(".trycloudflare.com") or not h


def entry_vsol(r, d_land):
    v = r["base"]
    for d, vs in r["sv"]:
        if d <= d_land:
            v = vs
        else:
            break
    return v


def sim(r, ex, d_land=D_LAND, size=SIZE, land_s1=False):
    """ex = dict(legs=[(frac, tp)], T=ms, trail=None|f, sl=None|f). Returns PnL as a fraction of size."""
    if land_s1:
        v0, t0 = (r["sv"][-1][1] if r["sv"] else r["base"]) / 1e9, 217.0
    else:
        v0, t0 = entry_vsol(r, d_land) / 1e9, d_land * r["ms_per_tx"]
    ve = v0 * math.sqrt(SLIP)                     # our fill: price x SLIP (price ~ vsol^2)
    s_in = size * (1 - FEE)
    tok = K / ve - K / (ve + s_in)
    left, net_in, proceeds, nsell, peak = 1.0, s_in, 0.0, 0, 0.0
    legs = sorted(ex.get("legs") or [], key=lambda z: z[1])
    T, tr, sl = ex["T"], ex.get("trail"), ex.get("sl")
    wh, whf = ex.get("whale"), ex.get("whale_frac", 1.0)   # sell into a big outside buy (one trade adding >= wh SOL)
    pa = ex.get("part_at")   # (ms, frac): sell frac at t0+ms regardless of price (scale out), keep the runner
    pa_done = False
    cf = ex.get("confirm")   # (W ms, Y SOL): if net outside SOL into the curve since our entry < Y at t0+W -> sell all (dead-token cut)
    cf_done = False

    def sell(frac, v):
        nonlocal left, net_in, proceeds, nsell
        frac = min(frac, left)
        if frac <= 1e-9:
            return
        vq = v + net_in
        out = vq - K / (K / vq + tok * frac)
        net_in -= out
        proceeds += out * (1 - FEE)
        left -= frac
        nsell += 1
    vx = v0
    prev = v0
    whale_done = False
    for t, v in r["path"]:
        if t <= t0:
            prev = v / 1e9
            continue
        if t - t0 > T:
            break
        vx = v / 1e9
        rr = (vx / ve) ** 2
        peak = max(peak, rr)
        if pa and not pa_done and t - t0 >= pa[0]:
            pa_done = True
            sell(pa[1], vx)
            if left <= 1e-9:
                break
        if cf and not cf_done and t - t0 >= cf[0]:
            cf_done = True
            if vx - v0 < cf[1]:
                sell(left, vx)
                break
        if wh and not whale_done and vx - prev >= wh and rr >= 1.0:
            whale_done = True
            sell(whf, vx)
            if left <= 1e-9:
                break
        prev = vx
        while legs and rr >= legs[0][1] and left > 1e-9:
            f, _ = legs.pop(0)
            sell(f, vx)
        if left <= 1e-9:
            break
        if (sl and rr <= sl) or (tr and peak >= 1.1 and rr <= peak * tr):
            sell(left, vx)
            break
    if left > 1e-9:
        sell(left, vx)
    return (proceeds - size - PRIO_BUY - PRIO_SELL * nsell) / size


# ---------------------------------------------------------------- exits
EXITS = {}
for T in (200, 400, 600, 1000, 1500, 2000, 3000, 5000, 10000, 20000, 40000):
    EXITS[f"time {T / 1000:g}s"] = dict(legs=[], T=T)
for tp, T, sl in itertools.product((1.1, 1.2, 1.3, 1.5, 2.0), (3000, 10000, 40000), (None, 0.8)):
    EXITS[f"tp{tp} T{T // 1000}s sl{sl}"] = dict(legs=[(1.0, tp)], T=T, sl=sl)
for a, b2, T in itertools.product((1.1, 1.2, 1.3), (1.5, 2.0, 3.0), (3000, 10000, 40000)):
    EXITS[f"half@{a} half@{b2} T{T // 1000}s"] = dict(legs=[(0.5, a), (0.5, b2)], T=T)
for T in (3000, 10000, 40000):
    EXITS[f"thirds@1.15/1.3/1.6 T{T // 1000}s"] = dict(legs=[(1 / 3, 1.15), (1 / 3, 1.3), (1 / 3, 1.6)], T=T)
    EXITS[f"thirds@1.1/1.25/1.5 T{T // 1000}s"] = dict(legs=[(1 / 3, 1.1), (1 / 3, 1.25), (1 / 3, 1.5)], T=T)
for tr, T, first in itertools.product((0.8, 0.9), (10000, 40000), (False, True)):
    EXITS[f"trail{tr} T{T // 1000}s" + (" +half@1.2" if first else "")] = dict(legs=[(0.5, 1.2)] if first else [], T=T, trail=tr)
for wh, whf, T in itertools.product((1.0, 2.0, 3.0), (0.5, 1.0), (3000, 10000)):
    EXITS[f"whale>={wh:g}SOL sell {whf:g} T{T // 1000}s"] = dict(legs=[], T=T, whale=wh, whale_frac=whf)
for W, Y, T in itertools.product((200, 400, 600), (0.5, 1.0, 2.0), (1000, 2000, 3000)):
    EXITS[f"confirm {W}ms>={Y:g}SOL else cut, T{T / 1000:g}s"] = dict(legs=[], T=T, confirm=(W, Y))
for f, tr, T in itertools.product((0.5, 0.7, 0.85), (0.7, 0.8, 0.9), (10000, 20000, 40000)):
    EXITS[f"runner: sell {f:g} at 1s, trail{tr:g} rest, T{T // 1000}s"] = dict(legs=[], T=T, trail=tr, part_at=(1000, f))
REF = "time 3s"   # reference exit for ranking gates (4yFAz's typical ~3 s hold)


# ---------------------------------------------------------------- conditions (common to historical + forward rows)
C = {}


def add(name, fn):
    C[name] = fn


for t in (1.0, 1.5, 2.0, 3.0, 4.0, 5.0):
    add(f"dev>={t}", lambda r, t=t: r["dev_sol"] >= t)
for t in (3.0, 5.0):
    add(f"dev<={t}", lambda r, t=t: r["dev_sol"] <= t)
add("dev sized", lambda r: r["dev_kind"] == "sized")
add("dev cap", lambda r: r["dev_kind"] == "cap")
for k in (1, 2, 3):
    add(f"bundle>={k}tx", lambda r, k=k: r["glued"] >= k)
add("no bundle", lambda r: r["glued"] == 0)
for t in (1.0, 2.0, 3.0, 5.0):
    add(f"bundle>={t}SOL", lambda r, t=t: r["gsol"] >= t)
for t in (3.0, 5.0, 10.0):
    add(f"bundle<={t}SOL", lambda r, t=t: r["gsol"] <= t)
for L in (8, 10, 12, 16):
    add(f"name<={L}", lambda r, L=L: r["n_len"] <= L)
for h in ("ipfs.io", "metadata.j7tracker.io", "meta.uxento.io"):
    add(f"host={h}", lambda r, h=h: r["uri_host"] == h)
    add(f"host!={h}", lambda r, h=h: r["uri_host"] != h)
add("cu_price>=1M", lambda r: (r["cu_price"] or 0) >= 1_000_000)
add("cu_price<100k", lambda r: (r["cu_price"] or 0) < 100_000)
add("tip=lunar", lambda r: r["ctip_label"] == "lunar")
add("no sender tip", lambda r: not r["ctip"])
add("tip!=jito/nozomi/astralane", lambda r: r["ctip_label"] not in ("jito", "nozomi", "astralane"))
add("mint ends pump", lambda r: bool(r["mint_pump"]))


def stats(v):
    if not v:
        return dict(n=0, avg=float("nan"), med=float("nan"), ex3=float("nan"), win=float("nan"))
    ex = sorted(v)[:-3] if len(v) > 12 else v
    return dict(n=len(v), avg=st.mean(v), med=st.median(v), ex3=st.mean(ex), win=sum(x > 0 for x in v) / len(v))


def fmt(s):
    return f"n={s['n']:3} avg {s['avg']:+6.1%} med {s['med']:+6.1%} ex-top3 {s['ex3']:+6.1%} win {s['win']:4.0%}"


def main():
    R = [json.loads(l) for l in open("/root/race/race_ds.jsonl")]
    H = [r for r in R if r["in_rand"] and not r["quote"] and not r["mayhem"] and not hostbad(r.get("uri_host")) and 0.5 <= r["dev_sol"] <= 8 and r["has_path"] and not r.get("bad_ev")]
    H.sort(key=lambda r: r["slot"])
    cut = H[int(len(H) * 0.6)]["slot"]
    TR = [r for r in H if r["slot"] < cut]
    TE = [r for r in H if r["slot"] >= cut]
    span_te_h = (TE[-1]["slot"] - TE[0]["slot"]) * 0.217 / 3600
    span_tr_h = (TR[-1]["slot"] - TR[0]["slot"]) * 0.217 / 3600
    FW = []
    if len(sys.argv) >= 4:
        from fwdrows import build
        FW = [o for o in build(*sys.argv[1:4]) if not hostbad(o["uri_host"]) and 0.5 <= o["dev_sol"] <= 8]
    span_fw_h = ((FW[-1]["slot"] - FW[0]["slot"]) * 0.217 / 3600) if len(FW) > 1 else float("nan")
    print(f"HIGH-CONVICTION SEARCH | size {SIZE} SOL, land S @<= {D_LAND} txs, slip x{SLIP}, fees: pump {FEE:.2%}/side + {PRIO_BUY} SOL buy prio + {PRIO_SELL}/sell")
    print(f"historical FIX-filter random rows with paths: train {len(TR)} (~{span_tr_h:.0f} h), test {len(TE)} (~{span_te_h:.0f} h); forward rows {len(FW)} (~{span_fw_h:.1f} h, all base launches of the paper run)")
    per_day = lambda n, h, w: n * w / h * 24 if h else float("nan")

    # baseline: whole FIX universe at a few exits
    print("\n-- baseline (FIX filter, no gate)")
    for xn in ("time 1s", "time 3s", "tp1.3 T10s slNone"):
        print(f"   {xn:22} TRAIN {fmt(stats([sim(r, EXITS[xn]) for r in TR]))} | TEST {fmt(stats([sim(r, EXITS[xn]) for r in TE]))} | FWD {fmt(stats([sim(o, EXITS[xn]) for o in FW]))}")

    # gate search on TRAIN with the reference exit. Robust ranking: TRAIN is cut into 3 time folds and a rule scores the
    # WORST fold mean (each fold needs >= 10 trades), so a rule must work in every part of the training period.
    names = list(C)
    ref = {id(r): sim(r, EXITS[REF]) for r in TR}
    f1, f2 = TR[len(TR) // 3]["slot"], TR[2 * len(TR) // 3]["slot"]
    fold = {id(r): (0 if r["slot"] < f1 else 1 if r["slot"] < f2 else 2) for r in TR}
    res = []
    for k in (1, 2, 3):
        for combo in itertools.combinations(names, k):
            g = [r for r in TR if all(C[c](r) for c in combo)]
            if len(g) < 45:
                continue
            fm = []
            for fi in range(3):
                v = [ref[id(r)] for r in g if fold[id(r)] == fi]
                if len(v) < 10:
                    break
                fm.append(st.mean(v))
            if len(fm) < 3:
                continue
            res.append((min(fm), combo, stats([ref[id(r)] for r in g]), fm))
    res.sort(key=lambda z: -z[0])
    print(f"\n-- gate search: {len(res)} rules with >= 45 TRAIN trades and >= 10 in each of 3 train folds, ranked by the WORST fold mean at exit '{REF}'")
    print(f"{'rule':58} | folds          | TRAIN @{REF:8}                                  | TEST @{REF:8}                                   | FWD @{REF}")
    top = []
    for score, combo, s_, fm in res[:20]:
        fn = lambda r, combo=combo: all(C[c](r) for c in combo)
        te = stats([sim(r, EXITS[REF]) for r in TE if fn(r)])
        fw = stats([sim(o, EXITS[REF]) for o in FW if fn(o)])
        print(f"{' & '.join(combo)[:58]:58} | {' '.join(f'{x:+.1%}' for x in fm)} | {fmt(s_)} | {fmt(te)} | {fmt(fw)}")
        top.append((combo, fn))

    # exit optimisation on TRAIN for the top gates; judge on TEST + FWD
    print("\n-- exit optimisation for the top 6 gates: best exit on TRAIN (worst train-fold mean), then TEST and FORWARD; trades/day from the population weights")
    best_overall = None
    for combo, fn in top[:6]:
        g_tr = [r for r in TR if fn(r)]
        g_te = [r for r in TE if fn(r)]
        g_fw = [o for o in FW if fn(o)]
        scored = []
        for xn, ex in EXITS.items():
            v = [(fold[id(r)], sim(r, ex)) for r in g_tr]
            fm = [st.mean([x for fi, x in v if fi == k]) for k in range(3) if any(fi == k for fi, _ in v)]
            s = stats([x for _, x in v])
            scored.append((min(fm), xn, s))
        scored.sort(key=lambda z: -z[0])
        print(f"\n   GATE: {' & '.join(combo)}   (fires/day: TEST ~{per_day(len(g_te), span_te_h, WGT):.0f}, FWD ~{per_day(len(g_fw), span_fw_h, 1):.0f})")
        for sc, xn, s in scored[:3]:
            te = stats([sim(r, EXITS[xn]) for r in g_te])
            fw = stats([sim(o, EXITS[xn]) for o in g_fw])
            s1 = stats([sim(r, EXITS[xn], land_s1=True) for r in g_te])
            print(f"     exit {xn:30} TRAIN {fmt(s)}")
            print(f"     {'':35} TEST  {fmt(te)} | land S+1: avg {s1['avg']:+.1%}")
            print(f"     {'':35} FWD   {fmt(fw)}")
        xn = scored[0][1]
        te = stats([sim(r, EXITS[xn]) for r in g_te])
        fw = stats([sim(o, EXITS[xn]) for o in g_fw])
        if best_overall is None:   # the pick = rank-1 gate on TRAIN with its TRAIN-best exit (no test data used to choose)
            best_overall = (None, combo, xn, te, fw, per_day(len(g_te), span_te_h, WGT), per_day(len(g_fw), span_fw_h, 1))
    if best_overall:
        _, combo, xn, te, fw, pd_te, pd_fw = best_overall
        print(f"\n== HIGH-CONVICTION pick (rank-1 gate on TRAIN, exit fitted on TRAIN only; TEST and FWD untouched): {' & '.join(combo)} | exit {xn}")
        for nm, s, pdy in (("TEST", te, pd_te), ("FWD", fw, pd_fw)):
            sol_day = s["avg"] * SIZE * pdy if s["n"] else float("nan")
            print(f"   {nm}: {fmt(s)} | ~{pdy:.0f} trades/day -> ~{sol_day:+.1f} SOL/day at {SIZE} SOL")
    # ---- GATE-B family: the race-precision-selected create-time gate (section 3 of race_an, chosen on TRAIN race precision,
    # not on PnL) and its stricter variants, defined up front. Ranked on TRAIN only; every row shows TEST and FWD.
    print("\n-- GATE-B FAMILY (creator bundle + dev + short name; all visible ~3 ms after the create). Exit fixed at 'time 3s' (4yFAz's hold), not fitted")
    print(f"{'variant':40} | {'TRAIN':52} | {'TEST':52} | {'FWD':52} | per day TEST/FWD")
    fam = []
    for dv, bt, nl in itertools.product((2.0, 3.0, 4.0, 5.0), (1, 2, 3), (10, 12, 99)):
        fn = lambda r, dv=dv, bt=bt, nl=nl: r["dev_sol"] >= dv and r["glued"] >= bt and r["n_len"] <= nl
        g_tr, g_te, g_fw = [r for r in TR if fn(r)], [r for r in TE if fn(r)], [o for o in FW if fn(o)]
        if len(g_tr) < 20:
            continue
        s_tr, s_te, s_fw = (stats([sim(r, EXITS[REF]) for r in g]) for g in (g_tr, g_te, g_fw))
        nm = f"dev>={dv:g} & bundle>={bt}tx" + (f" & name<={nl}" if nl < 99 else "")
        fam.append((s_tr["ex3"], nm, fn))
        print(f"{nm:40} | {fmt(s_tr)} | {fmt(s_te)} | {fmt(s_fw)} | {per_day(len(g_te), span_te_h, WGT):4.0f}/{per_day(len(g_fw), span_fw_h, 1):4.0f}")
    fam.sort(key=lambda z: -z[0])
    for rank, (sc, nm, fn) in enumerate(fam[:2]):
        g_tr, g_te, g_fw = [r for r in TR if fn(r)], [r for r in TE if fn(r)], [o for o in FW if fn(o)]
        scored = []
        for xn, ex in EXITS.items():
            v = [(fold[id(r)], sim(r, ex)) for r in g_tr]
            fm = [st.mean([x for fi, x in v if fi == k]) for k in range(3) if any(fi == k for fi, _ in v)]
            scored.append((min(fm), xn, stats([x for _, x in v])))
        scored.sort(key=lambda z: -z[0])
        print(f"\n   {'HIGH-CONVICTION' if rank == 0 else 'runner-up'} (best TRAIN ex-top3 in the family): {nm} — exits ranked on TRAIN (worst fold mean); TEST/FWD untouched")
        for sc2, xn, s_tr in scored[:4] + [z for z in scored if z[1] == REF]:
            s_te = stats([sim(r, EXITS[xn]) for r in g_te])
            s_fw = stats([sim(o, EXITS[xn]) for o in g_fw])
            s_s1 = stats([sim(r, EXITS[xn], land_s1=True) for r in g_te + g_fw])
            print(f"     {xn:30} TRAIN {fmt(s_tr)}\n     {'':30} TEST  {fmt(s_te)}\n     {'':30} FWD   {fmt(s_fw)} | TEST+FWD landing in S+1: avg {s_s1['avg']:+.1%}")
        if rank == 0:
            xn = scored[0][1]
            pd_te, pd_fw = per_day(len(g_te), span_te_h, WGT), per_day(len(g_fw), span_fw_h, 1)
            s_te = stats([sim(r, EXITS[xn]) for r in g_te])
            s_fw = stats([sim(o, EXITS[xn]) for o in g_fw])
            print(f"\n   ==> HC tier = {nm}, exit '{xn}' (fitted on TRAIN):")
            for per, s_, pdy in (("TEST", s_te, pd_te), ("FWD", s_fw, pd_fw)):
                print(f"       {per}: {fmt(s_)} | ~{pdy:.0f} fires/day -> {s_['avg'] * SIZE * pdy:+.1f} SOL/day at {SIZE} SOL (ex-top3: {s_['ex3'] * SIZE * pdy:+.1f})")
            print("       landing sensitivity (TEST+FWD): " + "  ".join(f"d{d}: {stats([sim(r, EXITS[xn], d_land=d) for r in g_te + g_fw])['avg']:+.1%}" for d in (5, 25, 50, 100, 150, 200))
                  + f"  S+1: {stats([sim(r, EXITS[xn], land_s1=True) for r in g_te + g_fw])['avg']:+.1%}")
            print("       size sensitivity (TEST+FWD, same exit): " + "  ".join(f"{sz:g} SOL: {stats([sim(r, EXITS[xn], size=sz) for r in g_te + g_fw])['avg']:+.1%}" for sz in (0.5, 1, 2, 3, 5)))

    # reference rows at realistic costs
    print("\n-- reference sets at the SAME realistic costs (exit: 1 s / 3 s / tp1.3-10 s / half@1.2 half@2.0 10 s)")
    REFS = [("GATE B dev>=3 & bundle>=2tx & name<=12", lambda r: r["dev_sol"] >= 3 and r["glued"] >= 2 and r["n_len"] <= 12),
            ("HINDSIGHT perfect race pick", lambda r: r["out2s_nx"] >= 3 and r["out2s_solx"] >= 3)]
    for nm, fn in REFS:
        for per, g in (("TEST", [r for r in TE if fn(r)]), ("FWD", [o for o in FW if fn(o)])):
            cells = " | ".join(f"{xn}: {stats([sim(r, EXITS[xn]) for r in g])['avg']:+.1%}" for xn in ("time 1s", "time 3s", "tp1.3 T10s slNone", "half@1.2 half@2.0 T10s"))
            print(f"   {nm:42} {per:4} n={len(g):3} | {cells}")
    if FW:
        g = [o for o in FW if o["fired"]]
        cells = " | ".join(f"{xn}: {stats([sim(r, EXITS[xn], d_land=100 + int(100 / r['ms_per_tx'])) for r in g])['avg']:+.1%}" for xn in ("time 1s", "time 3s", "tp1.3 T10s slNone", "half@1.2 half@2.0 T10s"))
        print(f"   {'STREAM RACE GATE (fired, +100 ms wait)':42} FWD  n={len(g):3} | {cells}")
    Rall = [json.loads(l) for l in open("/root/race/race_ds.jsonl")]
    Hh = [r for r in Rall if r["his"] and r["has_path"] and r["slot"] >= cut]
    cells = " | ".join(f"{xn}: {stats([sim(r, EXITS[xn]) for r in Hh])['avg']:+.1%}" for xn in ("time 1s", "time 3s", "tp1.3 T10s slNone", "half@1.2 half@2.0 T10s"))
    print(f"   {'4yFAz picks, if we knew them (TEST period)':42} TEST n={len(Hh):3} | {cells}")
    for d in (5, 25):
        cells = " | ".join(f"{xn}: {stats([sim(r, EXITS[xn], d_land=d) for r in Hh])['avg']:+.1%}" for xn in ("time 1s", "time 3s"))
        print(f"   {'   ..landing behind the first %d txs' % d:42} TEST n={len(Hh):3} | {cells}")

    # landing sensitivity for the pick
    if best_overall:
        fn = lambda r: all(C[c](r) for c in best_overall[1])
        print("\n-- landing sensitivity of the pick (TEST + FWD pooled), exit as fitted")
        g = [r for r in TE if fn(r)] + [o for o in FW if fn(o)]
        for d in (5, 25, 50, 100, 150, 200):
            print(f"   land behind the first {d:3} txs: {fmt(stats([sim(r, EXITS[best_overall[2]], d_land=d) for r in g]))}")
        print(f"   land in S+1 (behind all of S):  {fmt(stats([sim(r, EXITS[best_overall[2]], land_s1=True) for r in g]))}")


if __name__ == "__main__":
    main()
