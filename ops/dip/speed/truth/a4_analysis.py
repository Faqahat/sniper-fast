#!/usr/bin/env python3
# SPEED TRUTH step 4 (read-only): distributions, competitors, guard what-ifs, root causes. Prints every table to stdout
# (saved as OUT/analysis.txt by the caller) and writes OUT/summary.json for the report.
#
# Clocks (all chain-side numbers are on BOTH, labelled):
#   B400 = the brief's block-position clock: slot x 212 + idx / max(400, idx+1) x 212 (ms)
#   Bmix = the same with the block size raised to the recorded size when the block has more than 400 txs
#          (recorded size = largest pump.fun tx index in that slot + 1, a lower bound): idx / max(400, size, idx+1)
# Wall clock (our server, ms after the dump's FIRST sighting on any feed): exec wait, decision, writes, our tx seen.
import json, sys, os, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tl

R = json.load(open(f"{tl.OUT}/timeline.json"))
SS = {int(k): v for k, v in json.load(open(f"{tl.OUT}/slot_stats.json")).items()}
INSTANT_DI = 3
SUMMARY = {}


def size(s):
    v = SS.get(s)
    return v[1] + 1 if v else None


def B400(s, i): return s * tl.SMS + i / max(400, i + 1) * tl.SMS
def Bmix(s, i): return s * tl.SMS + i / max(400, size(s) or 400, i + 1) * tl.SMS
CLOCKS = {"B400": B400, "Bmix": Bmix}


def P(v, ps=(10, 50, 90), f="{:.1f}"): return tl.pct(v, ps, f)


def n_(v): return len([x for x in v if x is not None])


def g_at(r, t, K):
    """does our buy pass the +5% guard if it lands t ms after the dump (clock K)? state = after the last trade strictly before t"""
    c = r["C"]; d0 = K(c["dump_slot"], c["dump_idx"])
    ok = True
    for s, i, j, ps, *_ in c["gseq"]:
        if K(s, i) - d0 < t or (s, i) == (c["dump_slot"], c["dump_idx"]): ok = ps
        else: break
    return ok


def g_before(r, s0, i0):
    """guard just before chain position (s0, i0)"""
    ok = True
    for s, i, j, ps, *_ in r["C"]["gseq"]:
        if (s, i) < (s0, i0): ok = ps
        else: break
    return ok


def first_cross(r, K):
    c = r["C"]; d0 = K(c["dump_slot"], c["dump_idx"])
    for s, i, j, ps, *_ in c["gseq"]:
        if not ps: return K(s, i) - d0, (s, i)
    return None, None


def our_ms(r, K): c = r["C"]; return K(c["our_slot"], c["our_idx"]) - K(c["dump_slot"], c["dump_idx"])


def cls(r): return r["L"]["dump_class"]


def label(u):
    if u in tl.NAMED: return tl.NAMED[u]
    return "cohort" if u in tl.COHORT else "other"


def section(t): print("\n" + "=" * 100 + "\n" + t + "\n" + "=" * 100)


# ------------------------------------------------------------------------------------------------ A. coverage
section("A. COVERAGE + VALIDATION")
by = collections.defaultdict(list)
for r in R: by[(r["srv"], r["run"])].append(r)
for k in sorted(by):
    v = by[k]; t0 = min(x["t_fire"] for x in v) / 1e9; t1 = max(x["t_fire"] for x in v) / 1e9
    print(f"  {k[0]} run {k[1]:2d}: fires {len(v):3d} fills {sum(x['filled'] for x in v):3d} ({sum(x['filled'] for x in v)/len(v):.0%}) nonce {v[0]['nonce']} "
          f"| first/last fire {tl.pkt(t0)} -> {tl.pkt(t1)} PKT")
print(f"  ALL: {len(R)} attempts, {sum(r['filled'] for r in R)} fills, {sum(not r['filled'] for r in R)} failed buys "
      f"({sum(1 for r in R if r['C']['our_err'] and '6042' in json.dumps(r['C']['our_err']))} pump 6042 guard, others: "
      f"{[str(r['C']['our_err']) for r in R if r['C']['our_err'] and '6042' not in json.dumps(r['C']['our_err'])]})")
print(f"  chain: dump tx found {sum(r['C']['found_dump'] for r in R)}/{len(R)}, our landed tx found {sum(r['C']['found_ours'] for r in R)}/{len(R)}, "
      f"more than one of our copies landed: {sum(1 for r in R if r['C'].get('ours_landed_n', 0) > 1)}")
print(f"  engine fill/fail == chain: {sum(1 for r in R if r['C']['our_ok'] == r['filled'])}/{len(R)}; curve model predicts the chain result at our "
      f"position: {sum(1 for r in R if r['C']['pred_pass'] == r['C']['our_ok'])}/{len(R)}")
SUMMARY["n"] = len(R); SUMMARY["fills"] = sum(r["filled"] for r in R)

# ------------------------------------------------------------------------------------------------ B. stage timeline
section("B. STAGE TIMELINE (p10 / p50 / p90). Wall clock = ms after the dump's first sighting on our feeds; chain = ms after the dump")
def stage_rows(sel):
    W = lambda k: [r["W"].get(k) for r in sel]
    out = dict(
        n=len(sel),
        exec_wait=P(W("exec_wait")), decision=P(W("decision")), first_write=P(W("first_write")), last_write=P(W("last_write")),
        seen=P(W("seen")), send_to_seen=P(W("send_to_seen")),
        land_B400=P([our_ms(r, B400) for r in sel]), land_Bmix=P([our_ms(r, Bmix) for r in sel]),
        same_slot=f"{sum(1 for r in sel if r['C']['slot_delta'] == 0)}/{len(sel)}",
        dump_pos=P([r["C"]["dump_idx"] / max(400, size(r["C"]["dump_slot"]) or 400, r["C"]["dump_idx"] + 1) for r in sel], f="{:.2f}"))
    return out
def print_stage(title, groups):
    print(f"\n-- {title}")
    print(f"  {'group':22s} {'n':>4s} | {'exec wait':>15s} | {'decision':>13s} | {'1st write':>14s} | {'our tx seen':>17s} | {'land B400':>17s} | {'land Bmix':>17s} | same slot | dump pos")
    for g, sel in groups:
        if not sel: continue
        s = stage_rows(sel)
        print(f"  {g:22s} {s['n']:4d} | {s['exec_wait']:>15s} | {s['decision']:>13s} | {s['first_write']:>14s} | {s['seen']:>17s} | {s['land_B400']:>17s} | {s['land_Bmix']:>17s} | {s['same_slot']:>9s} | {s['dump_pos']}")
fills = [r for r in R if r["filled"]]; fails = [r for r in R if not r["filled"]]
print_stage("all / fills / fails", [("ALL", R), ("fills", fills), ("fails", fails)])
print_stage("by server", [(f"{s} {k}", [r for r in R if r["srv"] == s and (r["filled"] if k == "fills" else (not r["filled"]) if k == "fails" else True)])
                          for s in ("FRA", "AMS") for k in ("all", "fills", "fails")])
print_stage("by leader client (dump slot)", [(c, [r for r in R if cls(r) == c]) for c in ("bam", "harmonic", "jito", "fd", "firebam", "rakurai", "other", "?")])
print_stage("by run", [(f"{r0['srv']} r{r0['run']}", [r for r in R if (r['srv'], r['run']) == (r0['srv'], r0['run'])]) for r0 in
                       {(r['srv'], r['run']): r for r in R}.values()])
print_stage("by landed path (nonce runs r11+; one copy per path, the first to execute lands)",
            [(p, [r for r in R if r["nonce"] and r["C"]["our_path"] == p]) for p in ("nozomi", "helius", "helius-swqos", "bolt", "landx-fra3", "jito-bundle", "staked-rpc")])
print_stage("before nonce (one multi-tip tx on all paths) vs nonce fan-out", [("pre-nonce", [r for r in R if not r["nonce"]]), ("nonce", [r for r in R if r["nonce"]])])
SUMMARY["stage_all"] = stage_rows(R); SUMMARY["stage_fills"] = stage_rows(fills); SUMMARY["stage_fails"] = stage_rows(fails)
SUMMARY["stage_srv"] = {s: stage_rows([r for r in R if r["srv"] == s]) for s in ("FRA", "AMS")}
SUMMARY["stage_client"] = {c: stage_rows([r for r in R if cls(r) == c]) for c in ("bam", "harmonic", "jito", "fd", "firebam", "rakurai") if any(cls(r) == c for r in R)}

# decision internals
section("B2. DECISION INTERNALS (lat_us, microseconds p10/p50/p90) and per-path writes")
for k in ("queue", "book", "score", "checks_logs", "prepare", "fire"):
    for s in ("FRA", "AMS"):
        v = [r["lat_us"][k] for r in R if r["srv"] == s and r.get("lat_us")]
        print(f"  {k:12s} {s}: {P(v, f='{:.0f}')} us")
print("  first write per path: ms after the dump's first sighting (p10/p50/p90) | offset after our first write (p50, us) | write order rank | HTTP ack ms (p50/p90) | 429s")
paths = sorted({w for r in R for w in r["W"]["writes"]})
for p in paths:
    rows = [r for r in R if p in r["W"]["writes"]]
    t0 = [r["W"]["writes"][p]["t0"] for r in rows]
    offs = [(r["W"]["writes"][p]["t0"] - r["W"]["first_write"]) * 1000 for r in rows]
    rank = [sorted(r["W"]["writes"], key=lambda q: r["W"]["writes"][q]["t0"]).index(p) + 1 for r in rows]
    ack = [r["W"]["acks"][p]["ack_ms"] for r in rows if p in r["W"]["acks"]]
    n429 = sum(1 for r in rows if p in r["W"]["acks"] and r["W"]["acks"][p]["status"] == 429)
    nnone = sum(1 for r in rows if p in r["W"]["acks"] and r["W"]["acks"][p]["status"] is None)
    print(f"  {p:13s} n={len(rows):3d} | {P(t0, f='{:.2f}')} | +{np.median(offs):6.0f} us | rank p50 {np.median(rank):.0f} | ack {P(ack, (50, 90), '{:.2f}')} | 429: {n429} | no answer: {nnone}")

# ------------------------------------------------------------------------------------------------ C. where the time goes
section("C. WHERE THE TIME GOES (means and medians, ms)")
for K in ("B400", "Bmix"):
    k = CLOCKS[K]
    tot = [our_ms(r, k) for r in R]
    eng = [r["W"]["first_write"] for r in R]
    spill_after = [max(0.0, k(r["C"]["our_slot"], r["C"]["our_idx"]) - (r["C"]["dump_slot"] + 1) * tl.SMS) for r in R]
    print(f"  [{K}] landing delay mean {np.mean(tot):.1f} median {np.median(tot):.1f} | engine (first write after first sighting) mean {np.mean(eng):.1f} "
          f"median {np.median(eng):.1f} | after send mean {np.mean(tot) - np.mean(eng):.1f} | of which after the dump's block closed (spills) mean {np.mean(spill_after):.1f} "
          f"(= {np.mean(spill_after) / np.mean(tot):.0%} of all delay)")
    for g, sel in (("fills", fills), ("fails", fails)):
        tt = [our_ms(r, k) for r in sel]; ee = [r["W"]["first_write"] for r in sel]
        sa = [max(0.0, k(r["C"]["our_slot"], r["C"]["our_idx"]) - (r["C"]["dump_slot"] + 1) * tl.SMS) for r in sel]
        print(f"     {g}: delay mean {np.mean(tt):.1f} | engine {np.mean(ee):.1f} ({np.mean(ee) / np.mean(tt):.0%}) | exec wait {np.mean([r['W']['exec_wait'] for r in sel]):.1f} "
              f"| decision {np.mean([r['W']['decision'] for r in sel]):.1f} | after-send same-slot part {np.mean(tt) - np.mean(ee) - np.mean(sa):.1f} | after block close {np.mean(sa):.1f}")
    SUMMARY[f"time_{K}"] = dict(mean=np.mean(tot), median=float(np.median(tot)), engine_mean=float(np.mean(eng)), spill_after_mean=float(np.mean(spill_after)))
# same-feed cross-check of the chain clock
d = [(r["W"]["seen"], our_ms(r, B400), our_ms(r, Bmix)) for r in R if r["W"]["seen"] is not None]
a = np.array(d)
print(f"  same-feed clock (our tx seen - dump seen) vs chain clock: median {np.median(a[:, 0]):.1f} vs B400 {np.median(a[:, 1]):.1f} / Bmix {np.median(a[:, 2]):.1f}; "
      f"corr {np.corrcoef(a[:, 0], a[:, 1])[0, 1]:.2f} / {np.corrcoef(a[:, 0], a[:, 2])[0, 1]:.2f}")
ss = [r for r in R if r["C"]["slot_delta"] == 0 and r["W"]["seen"] is not None]
print(f"  same-slot only: seen {P([r['W']['seen'] for r in ss])} | B400 {P([our_ms(r, B400) for r in ss])} | Bmix {P([our_ms(r, Bmix) for r in ss])}")
poh = [r for r in R if r["timing"].get("land_ms_poh") is not None]
print(f"  PoH clock (FRA only, {len(poh)} attempts): dump PoH 'ms' p10/50/90 {P([r['timing']['dump_poh'][1] for r in poh])} in a 212 ms slot -> NOT usable "
      f"(corr with dump index {np.corrcoef([r['timing']['dump_poh'][1] for r in poh], [r['C']['dump_idx'] for r in poh])[0, 1]:.2f})")

# ------------------------------------------------------------------------------------------------ D. guard
section("D. THE +5% GUARD ON THE CHAIN (curve model validated 309/309)")
for K in ("B400", "Bmix"):
    k = CLOCKS[K]
    print(f"  [{K}] share of ALL attempts that would pass if our buy landed d ms after the dump | of the FAILED ones")
    rowsd = {}
    for dms in (0, 2, 5, 10, 15, 20, 25, 30, 35, 40, 50, 60, 75, 100, 150):
        a1 = sum(g_at(r, dms, k) for r in R); a2 = sum(g_at(r, dms, k) for r in fails)
        rowsd[dms] = (a1 / len(R), a2)
        print(f"     {dms:4d} ms: all {a1:3d}/{len(R)} ({a1 / len(R):4.0%}) | failed {a2:3d}/{len(fails)} ({a2 / len(fails):4.0%})")
    SUMMARY[f"guard_curve_{K}"] = rowsd
    fc = [first_cross(r, k)[0] for r in fails]
    ne = [our_ms(r, k) - first_cross(r, k)[0] for r in fails]
    print(f"  [{K}] failed buys: the price first crossed our guard {P(fc, (10, 25, 50, 75, 90))} ms after the dump; we landed {P(ne, (10, 25, 50, 75, 90))} ms after that")
    SUMMARY[f"fail_cross_{K}"] = P(fc, (10, 25, 50, 75, 90)); SUMMARY[f"fail_late_by_{K}"] = P(ne, (10, 25, 50, 75, 90))
    # fills: margin = time from our landing to the first crossing after us (if any within the window)
    mg = []
    for r in fills:
        d0 = k(r["C"]["dump_slot"], r["C"]["dump_idx"]); us = our_ms(r, k)
        nxt = next((k(s, i) - d0 for s, i, j, ps, *_ in r["C"]["gseq"] if (s, i) > (r["C"]["our_slot"], r["C"]["our_idx"]) and not ps), None)
        mg.append(None if nxt is None else nxt - us)
    print(f"  [{K}] fills: next crossing came {P(mg, (10, 25, 50, 75, 90))} ms after our landing (n={n_(mg)}; {sum(1 for x in mg if x is None)} never crossed in the window)")
inst = [r for r in fails if (first_cross(r, B400)[0] or 1e9) <= 1.6]
print(f"  failed buys whose guard was crossed within 1.6 ms of the dump (<= 3 txs: unbeatable by reacting): {len(inst)}")
cm = collections.Counter(label(r["C"]["cross_user"]) for r in fails if r["C"].get("cross_user"))
print(f"  who made the crossing buy (the last pass->fail flip before our failed buy): {cm.most_common()}")
SUMMARY["cross_makers"] = cm.most_common()

# ------------------------------------------------------------------------------------------------ E. competitors
section("E. COMPETITORS ON THE SAME DUMPS (chain clock; first buy attempt per wallet per dump)")
def first_attempts(r):
    """per wallet its first buy attempt (ok or failed) after the dump: dict user -> rival row"""
    out = {}
    for x in r["C"]["rivals"]:
        if x["user"] == r["C"].get("dump_user"): continue
        if x["user"] not in out: out[x["user"]] = x
    return out
for K in ("B400", "Bmix"):
    k = CLOCKS[K]
    def ms_of(r, x): return k(x["s"], x["i"]) - k(r["C"]["dump_slot"], r["C"]["dump_idx"])
    print(f"\n  [{K}] fastest rivals per dump vs us (successful buys)")
    fa, fr_, us_ = [], [], []
    for r in R:
        ok = [x for x in r["C"]["rivals"] if x["ok"] and x["user"] != r["C"].get("dump_user")]
        if ok: fa.append(ms_of(r, ok[0]))
        okr = [x for x in ok if not (x["ds"] == 0 and x["di"] <= INSTANT_DI)]
        if okr: fr_.append(ms_of(r, okr[0]))
        us_.append(our_ms(r, k))
    print(f"     first rival buy (any)         {P(fa, (10, 25, 50, 75, 90))} (n={len(fa)})")
    print(f"     first REACTING rival (> {INSTANT_DI} txs) {P(fr_, (10, 25, 50, 75, 90))} (n={len(fr_)})")
    print(f"     us (all attempts)             {P(us_, (10, 25, 50, 75, 90))}")
    SUMMARY[f"first_rival_{K}"] = P(fa, (10, 25, 50, 75, 90)); SUMMARY[f"first_react_{K}"] = P(fr_, (10, 25, 50, 75, 90)); SUMMARY[f"us_{K}"] = P(us_, (10, 25, 50, 75, 90))
    # per class / named wallet
    groups = collections.defaultdict(list)    # label -> [(attempt, row)]
    for r in R:
        fa_ = first_attempts(r)
        cl_first = {}
        for u, x in fa_.items():
            lb = label(u)
            if x["ds"] == 0 and x["di"] <= INSTANT_DI: groups["(instant <=3 txs, any wallet)"].append((r, x))
            groups[lb].append((r, x))
            if lb not in ("other",): cl_first.setdefault("ANY named/cohort", x)
        if "ANY named/cohort" in cl_first: groups["ANY named/cohort (first)"].append((r, cl_first["ANY named/cohort"]))
    print(f"\n  [{K}] wallet / class: dumps (of {len(R)}) | landing ms p10/50/90 of ITS first attempt | same slot | its attempt failed | landed before our tx | by client median ms")
    order = ["(instant <=3 txs, any wallet)", "Dk2jdQ93", "A9KKBdLy", "haqqiUUX", "HkQ7hMjy", "8PgC4ngp", "6n2cCJrr", "G9G3dCBG", "5w8xtjc6", "9k78QZyw",
             "DYXDDrZC", "CZ77onJz", "6VzXcLk9", "cohort", "ANY named/cohort (first)", "other"]
    SUMMARY[f"wallets_{K}"] = {}
    for lb in order:
        v = groups.get(lb, [])
        if not v: continue
        ms = [ms_of(r, x) for r, x in v]
        before = sum(1 for r, x in v if (x["s"], x["i"]) < (r["C"]["our_slot"], r["C"]["our_idx"]))
        byc = {c: np.median([ms_of(r, x) for r, x in v if cls(r) == c]) for c in ("bam", "harmonic", "jito") if any(cls(r) == c for r, x in v)}
        print(f"     {lb:28s} {len(v):4d} | {P(ms):>18s} | {sum(1 for r, x in v if x['ds'] == 0) / len(v):4.0%} | {sum(1 for r, x in v if not x['ok']) / len(v):4.0%} "
              f"| {before:3d}/{len(v):3d} | " + " ".join(f"{c} {m:.0f}" for c, m in byc.items()))
        SUMMARY[f"wallets_{K}"][lb] = dict(n=len(v), ms=P(ms), same=sum(1 for r, x in v if x["ds"] == 0) / len(v), before=before)
# rival buys ahead of us
for g, sel in (("fills", fills), ("fails", fails)):
    ah = [sum(1 for x in r["C"]["rivals"] if x["ok"] and x["ahead"]) for r in sel]
    fah = [sum(1 for x in r["C"]["rivals"] if (not x["ok"]) and x["ahead"]) for r in sel]
    print(f"  {g}: successful rival buys landed before ours {P(ah, (10, 50, 90), '{:.0f}')} | failed rival buys before ours {P(fah, (10, 50, 90), '{:.0f}')}")
# instant wallets
iw = collections.Counter(x["user"][:8] for r in R for x in r["C"]["rivals"] if x["ok"] and x["ds"] == 0 and x["di"] <= INSTANT_DI)
print(f"  instant (<= 3 txs after the dump, same slot) successful buyers: {iw.most_common(12)}")

# ------------------------------------------------------------------------------------------------ F. upper bound
section("F. UPPER BOUND: our failed buys that would have passed the guard had we landed like ...")
def ub(sel_fn, name):
    res = {}
    for K in ("B400", "Bmix"):
        k = CLOCKS[K]; n = 0; have = 0
        for r in fails:
            pos = sel_fn(r, k)
            if pos is None: continue
            have += 1
            if pos == "pass" or (isinstance(pos, tuple) and g_before(r, *pos)) or (isinstance(pos, float) and g_at(r, pos, k)): n += 1
        res[K] = (n, have)
    print(f"  {name:62s} B400 {res['B400'][0]:3d}/{res['B400'][1]:3d} | Bmix {res['Bmix'][0]:3d}/{res['Bmix'][1]:3d} (of {len(fails)} failed)")
    return res
def pos_first(r, k, react=False):
    ok = [x for x in r["C"]["rivals"] if x["ok"] and x["user"] != r["C"].get("dump_user") and not (react and x["ds"] == 0 and x["di"] <= INSTANT_DI)]
    return (ok[0]["s"], ok[0]["i"]) if ok else None
def pos_wallet(r, k, w):
    fa_ = first_attempts(r); x = fa_.get(w)
    return (x["s"], x["i"]) if x else None
SUMMARY["ub"] = {}
SUMMARY["ub"]["fastest_any"] = ub(lambda r, k: pos_first(r, k), "the fastest rival buy on that dump (any, incl. instant)")
SUMMARY["ub"]["fastest_react"] = ub(lambda r, k: pos_first(r, k, True), "the fastest REACTING rival on that dump (> 3 txs after)")
SUMMARY["ub"]["hkq7"] = ub(lambda r, k: pos_wallet(r, k, tl.HKQ7), "HkQ7hMjy, on dumps it bought")
SUMMARY["ub"]["haqq"] = ub(lambda r, k: pos_wallet(r, k, tl.HAQQ), "haqqiUUX, on dumps it bought")
for dms in (10, 20, 30, 35, 40, 50):
    SUMMARY["ub"][f"at{dms}"] = ub(lambda r, k, d=dms: float(d), f"every buy landing {dms} ms after the dump")
# median delay of the pros on our dumps
SUMMARY["ub"]["same_slot_at_our_ms"] = ub(lambda r, k: (float(min(our_ms(r, k), (r["C"]["dump_slot"] + 1) * tl.SMS - k(r["C"]["dump_slot"], r["C"]["dump_idx"]) - 0.01))
                                                         if r["C"]["slot_delta"] > 0 else None), "spilled fails landing at the END of the dump's slot instead")

# ------------------------------------------------------------------------------------------------ G. root causes
section("G. ROOT CAUSES: ms lost and failed buys each explains (counterfactual shifts on the MEASURED chain guard; INFERRED)")
def shifted(r, k, dt):
    """our landing moved dt ms earlier on the same clock (same-slot landings only; a spilled buy keeps its slot)"""
    return g_at(r, our_ms(r, k) - dt, k)
RC = {}
for K in ("B400", "Bmix"):
    k = CLOCKS[K]
    same_f = [r for r in fails if r["C"]["slot_delta"] == 0]; sp_f = [r for r in fails if r["C"]["slot_delta"] > 0]
    res = {}
    res["exec_wait"] = sum(1 for r in same_f if shifted(r, k, r["W"]["exec_wait"]))
    res["decision"] = sum(1 for r in same_f if shifted(r, k, max(0.0, r["W"]["decision"] - 0.2)))
    res["engine_all"] = sum(1 for r in same_f if shifted(r, k, max(0.0, r["W"]["first_write"] - 0.2)))
    for dt in (5, 10, 15, 20, 30):
        res[f"shift{dt}"] = sum(1 for r in same_f if shifted(r, k, dt))
    res["spill_end_of_slot"] = sum(1 for r in sp_f if g_at(r, (r["C"]["dump_slot"] + 1) * tl.SMS - k(r["C"]["dump_slot"], r["C"]["dump_idx"]) - 0.01, k))
    RC[K] = res
    print(f"  [{K}] same-slot failed buys {len(same_f)}, spilled failed buys {len(sp_f)}")
    print(f"     fire at the first (shred) sighting, no exec-feed wait: rescues {res['exec_wait']} same-slot fails")
    print(f"     decision 0.2 ms instead of measured:                   rescues {res['decision']}")
    print(f"     both (first write 0.2 ms after the first sighting):    rescues {res['engine_all']}")
    for dt in (5, 10, 15, 20, 30):
        print(f"     same-slot landing {dt:2d} ms earlier (send-leg fix):           rescues {res[f'shift{dt}']}")
    print(f"     spilled fails landing at the END of the dump's slot:   rescues {res['spill_end_of_slot']} of {len(sp_f)}")
SUMMARY["rc"] = RC
# per-cause ms lost
print("\n  ms lost per cause (mean over all attempts, B400):")
eng = np.mean([r["W"]["first_write"] for r in R]); ew = np.mean([r["W"]["exec_wait"] for r in R]); dc = np.mean([r["W"]["decision"] for r in R])
sp = np.mean([max(0.0, B400(r["C"]["our_slot"], r["C"]["our_idx"]) - (r["C"]["dump_slot"] + 1) * tl.SMS) for r in R])
print(f"     exec-feed wait {ew:.2f} | decision {dc:.2f} | engine total (first write) {eng:.2f} | after the dump's block closed (spills) {sp:.1f} | "
      f"total {np.mean([our_ms(r, B400) for r in R]):.1f}")
# spills deep dive
section("G2. NEXT-SLOT SPILLS")
def left(r): return (1 - r["C"]["dump_idx"] / max(400, size(r["C"]["dump_slot"]) or 400, r["C"]["dump_idx"] + 1)) * tl.SMS
SP = [r for r in R if r["C"]["slot_delta"] > 0]
print(f"  spills {len(SP)}/{len(R)} ({len(SP)/len(R):.0%}); fills among spills {sum(r['filled'] for r in SP)}; into the same leader's next slot {sum(1 for r in SP if r['L'].get('same_leader'))}")
for lab_, lo, hi in (("< 40 ms left in the dump's block", 0, 40), ("40-80 ms left", 40, 80), (">= 80 ms left", 80, 1e9)):
    v = [r for r in R if lo <= left(r) < hi]; s = [r for r in v if r["C"]["slot_delta"] > 0]
    print(f"  {lab_:34s} attempts {len(v):3d} spills {len(s):3d} ({len(s) / max(1, len(v)):4.0%}) | by client {dict(collections.Counter(cls(r) for r in s))} "
          f"| first slot of the leader's turn {sum(1 for r in s if r['L']['turn_pos'] == 0)}")
print("  spill rate by client, first slot of the turn vs other slots:")
for c in ("bam", "harmonic", "jito", "fd", "firebam", "rakurai"):
    v = [r for r in R if cls(r) == c]
    if not v: continue
    t0 = [r for r in v if r["L"]["turn_pos"] == 0]; t1 = [r for r in v if r["L"]["turn_pos"] > 0]
    print(f"     {c:9s} {sum(r['C']['slot_delta'] > 0 for r in v):3d}/{len(v):3d} | turn slot 1: {sum(r['C']['slot_delta'] > 0 for r in t0)}/{len(t0)} | slots 2-4: {sum(r['C']['slot_delta'] > 0 for r in t1)}/{len(t1)}")
k2 = 0
for r in SP:
    if any(x["ok"] and x["ds"] == 0 and x["di"] > INSTANT_DI for x in r["C"]["rivals"]): k2 += 1
print(f"  spills where a REACTING rival still landed in the dump's slot after the dump: {k2}/{len(SP)}")
print(f"  our position in the next block: idx {P([r['C']['our_idx'] for r in SP], (10, 25, 50, 75, 90), '{:.0f}')}")
SUMMARY["spill"] = dict(n=len(SP), fills=sum(r["filled"] for r in SP), rivals_in_slot=k2)

# ------------------------------------------------------------------------------------------------ H. paths
section("H. PATHS (nonce runs: the copy that executed first landed; others were dropped)")
N = [r for r in R if r["nonce"]]
tab = collections.defaultdict(lambda: [0, 0, []])
for r in N:
    t = tab[(cls(r), r["C"]["our_path"])]; t[0 if r["filled"] else 1] += 1; t[2].append(our_ms(r, B400))
print("  client / landed path: fills | fails | landing ms (B400) p10/50/90")
for key in sorted(tab):
    f_, x_, ms = tab[key]
    print(f"     {key[0]:9s} {key[1]:13s} {f_:3d} | {x_:3d} | {P(ms)}")
tp = collections.Counter(r["C"]["our_path"] for r in N if r["filled"]); tx = collections.Counter(r["C"]["our_path"] for r in N if not r["filled"])
print(f"  fills by landed path {tp.most_common()}\n  fails by landed path {tx.most_common()}")
# tipless copy: fails that landed through the tipless staked-rpc copy
print(f"  failed buys landed by the TIPLESS staked-rpc copy: {tx['staked-rpc']}/{sum(tx.values())}; fills by it: {tp['staked-rpc']}/{sum(tp.values())}")
# 429 / no-answer on helius at fire time
h429 = [r for r in R if any(a["status"] == 429 for a in r["W"]["acks"].values())]
print(f"  attempts with an HTTP 429 on a helius path: {len(h429)} (fills {sum(r['filled'] for r in h429)}), clients {dict(collections.Counter(cls(r) for r in h429))}")
SUMMARY["paths"] = dict(fills=tp.most_common(), fails=tx.most_common(), h429=len(h429))

# ------------------------------------------------------------------------------------------------ I. distance / region
section("I. DISTANCE TO THE LEADER (RTT from the firing server) and region")
for s in ("FRA", "AMS"):
    v = [r for r in R if r["srv"] == s]
    print(f"  {s}: leader RTT ms {P([r['L']['rtt'] for r in v], (10, 50, 90), '{:.2f}')} | cities {collections.Counter((r['L']['geo'] or [None])[0] for r in v).most_common(5)}")
    for lo, hi in ((0, 1), (1, 3), (3, 10), (10, 1e9)):
        w = [r for r in v if r["L"]["rtt"] is not None and lo <= r["L"]["rtt"] < hi]
        if w: print(f"     RTT {lo}-{hi} ms: n={len(w):3d} landing B400 {P([our_ms(r, B400) for r in w])} | same-slot {sum(1 for r in w if r['C']['slot_delta'] == 0)}/{len(w)} | fill {sum(r['filled'] for r in w)}/{len(w)}")
print("  same client, FRA vs AMS (same-slot landings, B400 median / fill rate):")
for c in ("bam", "harmonic", "jito"):
    out = []
    for s in ("FRA", "AMS"):
        w = [r for r in R if r["srv"] == s and cls(r) == c]
        ws = [our_ms(r, B400) for r in w if r["C"]["slot_delta"] == 0]
        out.append(f"{s} n={len(w)} same-slot med {np.median(ws) if ws else float('nan'):.0f} ms spill {sum(1 for r in w if r['C']['slot_delta'] > 0)}/{len(w)} fill {sum(r['filled'] for r in w)}/{len(w)}")
    print(f"     {c:9s} " + " | ".join(out))

# ------------------------------------------------------------------------------------------------ J. per-attempt table
section("J. PER-ATTEMPT TABLE (ms; wall clock from the dump's first sighting; chain B400 from the dump)")
print("  srv run  time PKT  client    path         res  E    D    1stW  seen   land  ds  cross  late  rivals-ahead  crossing-wallet")
for r in sorted(R, key=lambda r: r["t_fire"]):
    c = r["C"]; fc_, _ = first_cross(r, B400)
    late = our_ms(r, B400) - fc_ if (fc_ is not None and not r["filled"]) else None
    print(f"  {r['srv']} r{r['run']:<2d} {tl.pkt(r['t_fire'] / 1e9)[6:]} {cls(r):9s} {str(c['our_path'])[:12]:12s} {'FILL' if r['filled'] else 'fail'} "
          f"{r['W']['exec_wait']:4.1f} {r['W']['decision']:4.1f} {r['W']['first_write']:5.1f} {r['W']['seen'] if r['W']['seen'] is not None else float('nan'):6.1f} "
          f"{our_ms(r, B400):6.1f} {c['slot_delta']:2d} {fc_ if fc_ is not None else float('nan'):6.1f} {late if late is not None else float('nan'):6.1f} "
          f"{sum(1 for x in c['rivals'] if x['ok'] and x['ahead']):3d} {label(c['cross_user']) if c.get('cross_user') else '-'}")

json.dump(SUMMARY, open(f"{tl.OUT}/summary.json", "w"), default=str, indent=1)
