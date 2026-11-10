#!/usr/bin/env python3
"""BOTREG step 5 [MEASURED]: proof tables for the hour-by-hour replay (x4).
 (a) wallet switches: detection + link lag      (b) precision of admissions      (c) coverage per PKT day vs the fixed cohort
 (e) SELLS-INTO-US class on our live positions: DEV r37-r54 first, then r55 once (flatsig run extracts; P&L = engine-realized)
Out: /home/it/sniper-data/botreg/eval.txt (+ eval.json)"""
import sys, os, json, pickle, collections, glob
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C, hourly_table as HT, reg as R

D = C.DATA
OUT = []
def say(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); OUT.append(s)


def main():
    reg = pickle.load(open(f"{D}/backtest/registry_state.pkl", "rb"))
    J = json.load(open(f"{D}/registry.json"))
    T = HT.load()
    cov = sorted(set(int(x) for x in T["_G"]["h"]))
    t_end = cov[-1] + C.H
    b58 = {int(w["u64"]): w["wallet"] for w in J["wallets"]}
    fpb = {}
    for w in J["wallets"]: fpb[int(w["u64"])] = w["wallet"]
    name = lambda u: fpb.get(u) or str(u)
    seedname = lambda u: C.SEED_NAMES.get(fpb.get(u, ""), "")
    data_start = cov[0]
    say(f"BOTREG proof tables (MEASURED, replay of hourly updates {C.pkt(cov[0])} -> {C.pkt(t_end)} PKT; {len(cov)} covered hours; "
        f"gap 11-01 19:06 -> 11-02 17:50 not recorded)")

    # ---------------- (a) switches
    say("\n(a) WALLET SWITCHES: operators with >= 2 wallets linked at HIGH confidence (join rule); lag from the wallet's first recorded pump.fun trade")
    say("    op | wallet | first trade | in engine view | linked (high) | engine lag h | link lag h | link evidence (top)")
    rows_a = []
    for op, o in reg.ops.items():
        ws = [u for u in o["wallets"]]
        if len(ws) < 2: continue
        ws.sort(key=lambda u: reg.first_seen.get(u, 0))
        lab = next((seedname(u) for u in ws if seedname(u)), "")
        for u in ws:
            r = reg.W[u]; fs = reg.first_seen.get(u)
            es = next((a for a, b, _ in r["hist"] if b == "probation"), None)
            lh = r.get("link_high_t")
            cens = fs is not None and fs < data_start + 6 * C.H
            lag_e = (es - fs) / 3600 if es and fs else None
            lag_l = (lh - fs) / 3600 if lh and fs else None
            ev = "; ".join(e.split(" (")[0] for e in (r["link"] or {}).get("evidence", [])[:4]) if r["link"] else ""
            rows_a.append({"op": op, "label": lab, "wallet": name(u), "first": fs, "engine": es, "link_high": lh, "lag_engine_h": lag_e,
                           "lag_link_h": lag_l, "censored": cens, "state": r["state"]})
            say(f"    {op}{'(' + lab + ')' if lab else ''} | {name(u)} | {C.pkt(fs) if fs else '-'}{' (data start)' if cens else ''} | "
                f"{C.pkt(es) if es else '-'} | {C.pkt(lh) if lh else '-'} | {lag_e if lag_e is None else round(lag_e, 1)} | "
                f"{lag_l if lag_l is None else round(lag_l, 1)} | {r['state']} | {ev[:150]}")
    un = [x for x in rows_a if not x["censored"] and x["lag_link_h"] is not None]
    if un:
        la = np.array([x["lag_link_h"] for x in un]); le = np.array([x["lag_engine_h"] for x in un if x["lag_engine_h"] is not None])
        say(f"    uncensored later wallets: {len(un)}; link lag median {np.median(la):.1f} h (max {la.max():.1f}); engine-view lag median {np.median(le):.1f} h")
    say("    MEDIUM links (possible same operator, NOT joined):")
    for u, r in reg.W.items():
        lk = r["link"]
        if lk and lk["confidence"] == "medium" and r["state"] != "new":
            say(f"      {name(u)} -> {name(lk['to'])} [{seedname(u)}/{seedname(lk['to'])}] {'; '.join(e.split(' (')[0] for e in lk['evidence'][:5])[:160]}")

    say("\n    NEW WALLETS since 11-01 00:00 PKT that entered the engine view (first recorded trade >= 11-01):")
    c11 = 1793473200   # 11-01 00:00 PKT
    for w in sorted(J["wallets"], key=lambda w: -(w["w48"]["pnl_sol_per_day"])):
        fs = w.get("first_seen_epoch")
        if fs and fs >= c11 and w["engine_since_epoch"]:
            lk = w["link"]
            say(f"      {w['wallet']} {w['state']:9s} op {w['operator']}{'(' + w['operator_label'] + ')' if w['operator_label'] else ''} "
                f"first {w['first_seen_pkt']} in-view {C.pkt(w['engine_since_epoch'])} | 48h: {w['w48']['trips_per_day']}/d "
                f"{w['w48']['pnl_sol_per_day']:+.2f} SOL/d dip {w['w48']['dip_share']:.2f} fol {w['w48']['our_fills_followed']} | "
                f"link {lk['confidence'] + '->' + lk['to_wallet'][:8] if lk else '-'}")

    # ---------------- membership series
    M = np.load(f"{D}/backtest/members.npz")
    mem = collections.defaultdict(set)
    for t, u in zip(M["t"], M["u"]): mem[int(t)].add(int(u))
    fixed = {int(x) for x in json.load(open("/home/it/sniper-data/flatsig/cohort.json"))["ids"]}
    named = set(C.SEED64)
    fpn = fixed | named

    # ---------------- (b) precision
    say("\n(b) PRECISION of admissions (each new -> probation event; forward = next 24 covered hours after admission)")
    adm = [(r["hist"], u) for u, r in reg.W.items()]
    ev = []
    for hist, u in adm:
        for a, b, why in hist:
            if b == "probation" and why.startswith(("P1", "P2", "P3")):
                ev.append((a, u, why[:2]))
    ok = collections.Counter(); tot = collections.Counter(); pos = collections.Counter(); vanish = collections.Counter(); infix = collections.Counter()
    for a, u, why in ev:
        fh = [h for h in cov if h >= a][:24]
        if len(fh) < 12: continue
        w = R.Window(T, fh); s = w.get(u)
        tot[why] += 1
        if s and s["n_dip"] >= 10 and s["dip_share"] >= 0.2 and s["n_trip"] >= 10: ok[why] += 1
        if s and s["pnl"] > 0: pos[why] += 1
        if not s or s["n_dip"] < 3: vanish[why] += 1
        if u in fpn: infix[why] += 1
    for k in sorted(tot):
        say(f"    {k}: admissions {tot[k]} | still dip-trading next 24h {ok[k]} ({ok[k] / tot[k]:.0%}) | profitable next 24h {pos[k]} "
            f"({pos[k] / tot[k]:.0%}) | went quiet (<3 dip buys) {vanish[k]} | in fixed cohort/named {infix[k]}")
    n = sum(tot.values())
    say(f"    all: {n} admissions, {sum(ok.values()) / max(n, 1):.0%} still dip-trading, {sum(pos.values()) / max(n, 1):.0%} profitable next 24 h")

    # ---------------- (c) coverage per PKT day
    say("\n(c) COVERAGE per PKT day: share captured by each list (dynamic = registry engine view as of the start of each hour, built only from earlier hours)")
    say("    DIP SOL = post-dump buy SOL (DUMP def. in x1); BOT DIP SOL = same, by wallets that are dip bots on that day in hindsight")
    say("    (day: >= 20 dip buys, dip share >= 0.3, >= 20 closed trips); FOLLOW = buys <= 2 slots after one of our fills")
    day = (T["h"] + 5 * 3600) // 86400
    days = sorted(set(int(x) for x in day))
    key = np.stack([T["u"], day.astype(np.uint64)], 1)
    uk, inv = np.unique(key, axis=0, return_inverse=True); inv = inv.ravel()
    sm = lambda c: np.bincount(inv, weights=T[c].astype(np.float64))
    xpost = (sm("n_dip") >= 20) & (sm("n_dip") >= 0.3 * np.maximum(sm("n_buy"), 1)) & (sm("n_trip") >= 20)
    xp = set(map(tuple, uk[xpost].astype(np.int64).tolist()))
    inmem = np.array([int(u) in mem.get(int(h), ()) for u, h in zip(T["u"], T["h"])])
    infx = np.isin(T["u"], np.array(sorted(fixed), dtype=np.uint64)); infn = np.isin(T["u"], np.array(sorted(fpn), dtype=np.uint64))
    isxp = np.array([(int(u), int(d)) in xp for u, d in zip(T["u"], day)])
    say("    day   hours | DIP SOL: dyn / fixed / fixed+named | BOT DIP SOL: dyn / fixed / fixed+named | FOLLOW buys: dyn / fixed / fixed+named | n listed dyn")
    res_c = []
    for d in days:
        m = day == d
        nh = len(set(T["h"][m]))
        dip = T["dip_sol"][m].astype(float); fol = T["n_fol"][m].astype(float)
        a = dip.sum(); b = dip[isxp[m]].sum(); f = fol.sum()
        r = [dip[inmem[m]].sum() / a, dip[infx[m]].sum() / a, dip[infn[m]].sum() / a,
             dip[isxp[m] & inmem[m]].sum() / b, dip[isxp[m] & infx[m]].sum() / b, dip[isxp[m] & infn[m]].sum() / b,
             fol[inmem[m]].sum() / max(f, 1), fol[infx[m]].sum() / max(f, 1), fol[infn[m]].sum() / max(f, 1)]
        hs = sorted(set(int(x) for x in T["h"][m]))
        nl = np.mean([len(mem.get(h, ())) for h in hs])
        res_c.append({"day": d, "hours": nh, "r": r, "n_dyn": nl})
        lab = C.pkt(d * 86400 - 5 * 3600 + 1)[:5]
        say(f"    {lab} {nh:5d} | {r[0]:.0%} / {r[1]:.0%} / {r[2]:.0%} | {r[3]:.0%} / {r[4]:.0%} / {r[5]:.0%} | {r[6]:.0%} / {r[7]:.0%} / {r[8]:.0%} | {nl:.0f}")
    say("    NOTE: the fixed cohort was fit on rows < 11-01 12:00, so on 10-27..11-01 it is IN-SAMPLE (it knows which wallets will be bots);")
    say("          the dynamic list is causal everywhere. Fair comparison = days after 11-01 12:00.")
    # volume precision: share of the dynamic list's dip SOL that comes from hindsight day-bots
    vp = [T["dip_sol"][(day == d) & inmem & isxp].sum() / max(T["dip_sol"][(day == d) & inmem].sum(), 1) for d in days]
    vf = [T["dip_sol"][(day == d) & infx & isxp].sum() / max(T["dip_sol"][(day == d) & infx].sum(), 1) for d in days]
    say("    volume precision (share of a list's dip SOL bought by hindsight day-bots): dyn " + " ".join(f"{x:.0%}" for x in vp)
        + " | fixed " + " ".join(f"{x:.0%}" for x in vf))
    json.dump({"a": rows_a, "c": res_c}, open(f"{D}/eval.json", "w"), indent=1, default=str)
    open(f"{D}/eval.txt", "w").write("\n".join(OUT) + "\n")


if __name__ == "__main__":
    main()
