#!/usr/bin/env python3
"""GAP step 3 (read-only): the reconciled ledger haqq vs us, per day (24 h windows ending 23:15 PKT).

haqq side: every lot (g1) is put in exactly one bucket, in this order:
  NOCOV  his buy falls in a tape hour that is not usable (dv8 c0 coverage) -> context unreliable
  e / f  SHARED: we landed a buy tx on the same mint after the same dump (window = dump (slot, idx) .. his buy slot + 2;
         no dump within 5 slots -> his buy slot +-2): f = we filled, e = every landed attempt failed (guard etc.)
  a      no trading engine running on either server (probe-only runs count as not trading)
  b      his lot is a type we never trade: ADD, DEAD, LAUNCH, MOMO, OTHER, DIP_LATE, PROBE (<= 0.05 SOL)
  c      DIP (>= 5 % single-sell drop, <= 2 slots before his buy) that our running engine(s) refused; reason from the engine logs
         (dump / pick / pick_skip / fire / pre-send arm / skip / disarm) and, for dumps the engine never logged, from the tape
         against the engine's dump envelope. Several servers -> the server that got furthest towards a fire.
our side: every wallet tx of FRA 2g7r / AMS Egxf (dv8/tab/ours.jsonl, SOL delta incl. fees, tips, rent; MEASURED) grouped into
  episodes per (wallet, mint) (gap > 300 slots starts a new one); path by signature (run logs: regular fire / pre-send);
  F_shared (fill, haqq lot on it) / F_own (fill, no haqq lot) / X_shared (no fill, haqq filled) / X_own (no fill, no haqq lot).
Out: gap/g3_rows.pkl (per lot + per episode), gap/g3_*.txt"""
import json, pickle, collections, sys, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/gap"
REG_MAP = {"far_leader": "near-only (far leader)", "spacing": "cooldown/fee budget", "paused": "cooldown/fee budget", "balance": "cooldown/fee budget",
           "open_on_token": "one-position busy", "max_open": "one-position busy", "presend_armed": "one-position busy",
           "presend_position": "one-position busy", "presend_position_open": "one-position busy"}
PS_MAP = {"quiet": "QUIET skip", "blocked_armed": "one-position busy", "blocked_position": "one-position busy", "blocked_ata_open": "one-position busy",
          "reactive_position": "one-position busy", "stopped": "cooldown/fee budget"}


def main():
    t0 = time.time()
    Z = pickle.load(open(f"{OUT}/g1_lots.pkl", "rb")); B = Z["buys"]; meta = Z["meta"]
    RUNS = pickle.load(open(f"{OUT}/g2_engine.pkl", "rb"))
    ids, idm = L.ids_map()
    HR = json.load(open(f"{L.D}/hours.json"))["rows"]
    usable = {r["h"]: r["usable"] for r in HR}
    def hour_ok(t): return usable.get(int((t + 18000) // 3600 * 3600 - 18000), False)
    # ---------------- runs
    runs = []
    for run, X in RUNS.items():
        if not X["start"]: continue
        live_arms = [a for a in X["arms"] if not a[9]]
        X["ps_on"] = len(live_arms) > 0 or len(X["patt"]) > 0
        X["arms_by"] = collections.defaultdict(list); X["sk_by"] = collections.defaultdict(list)
        for a in live_arms: X["arms_by"][(a[0], a[1])].append(a)
        for s in X["pskips"]: X["sk_by"][(s[0], s[1])].append(s)
        runs.append((X["start"], X["end"], run, X))
    runs.sort()
    sig_reg = set(); sig_ps = set()
    for X in RUNS.values(): sig_reg |= X["sigs_reg"]; sig_ps |= X["sigs_ps"]
    def active(t): return [(r, X) for s, e, r, X in runs if s <= t <= e]
    # ---------------- our txs -> episodes
    W2N = {v: k for k, v in L.WAL.items()}
    tx = []
    for l in open(f"{L.TAB}/ours.jsonl"):
        d = json.loads(l); w = d["signers"][0]
        if w not in W2N: continue
        sd = d["sd"]; sd = json.loads(sd.replace("'", '"')) if isinstance(sd, str) else sd
        v = sum(x for a, x in sd if a == w) / 1e9
        ix = d.get("ixn") or []
        isbuy = any(x.startswith("Buy") for x in ix); issell = any(x.startswith("Sell") for x in ix)
        ok = d["err"] is None
        kind = "buy_ok" if (ok and isbuy) else "sell" if issell else "close" if (ok and "CloseAccount" in ix) else "buy_fail" if not ok else "other"
        path = "reg" if d["sig"] in sig_reg else "ps" if d["sig"] in sig_ps else None
        es = str(d["err"]); code = None if ok else ("6042" if "6042" in es else "6001" if "6001" in es else "IllegalOwner" if "IllegalOwner" in es else "6005" if "6005" in es else "other")
        tx.append(dict(w=W2N[w], mint=(d["mints"] or [None])[0], s=d["s"], i=d["i"], bt=d["bt"], v=v, kind=kind, path=path, sig=d["sig"], code=code,
                       fee=(d["fee"] + sum(x for a, x in (d.get("tips") or []))) / 1e9))
    tx.sort(key=lambda x: (x["w"], str(x["mint"]), x["s"], x["i"]))
    eps = []; cur = None
    for x in tx:
        if cur is None or (x["w"], x["mint"]) != (cur["w"], cur["mint"]) or x["s"] - cur["s1"] > 300:
            cur = dict(w=x["w"], mint=x["mint"], s0=x["s"], s1=x["s"], bt=x["bt"], tx=[]); eps.append(cur)
        cur["tx"].append(x); cur["s1"] = x["s"]
    for E in eps:
        T_ = E["tx"]
        E["pnl"] = sum(x["v"] for x in T_); E["day"] = L.day_of(E["bt"])
        E["n_ok"] = sum(x["kind"] == "buy_ok" for x in T_); E["n_fail"] = sum(x["kind"] == "buy_fail" for x in T_)
        ps = [x["path"] for x in T_ if x["path"]]
        E["path"] = ("ps" if "ps" in ps and "reg" not in ps else "reg" if "reg" in ps and "ps" not in ps else "mixed" if ps else "unk")
        E["fill"] = E["n_ok"] > 0; E["shared"] = False; E["his"] = []
        E["att"] = [(x["s"], x["i"], x["kind"], x["code"], x["path"]) for x in T_ if x["kind"] in ("buy_ok", "buy_fail")]
    ep_by_mint = collections.defaultdict(list)
    for k, E in enumerate(eps):
        if E["mint"]: ep_by_mint[E["mint"]].append(k)
    ours_b = [b for b in B if b["w"] in ("FRA", "AMS")]
    ob_by = collections.defaultdict(list)
    for b in ours_b: ob_by[(b["w"], b["mint"])].append(b)
    for E in eps:
        E["lots"] = [b for b in ob_by.get((E["w"], E["mint"]), []) if E["s0"] - 1 <= b["slot"] <= E["s1"] + 1]
        E["size"] = sum(b["size"] for b in E["lots"]); E["gross"] = sum(b["gross"] for b in E["lots"])
    print(f"our txs {len(tx):,}, episodes {len(eps):,} ({time.time() - t0:.0f}s)", flush=True)
    # ---------------- haqq lots
    H = [b for b in B if b["w"] == "haqq"]
    rows = []
    for b in H:
        r = dict(b=b, day=b["day"], net=b["net"], size=b["size"], type="PROBE" if b["probe"] else b["type"])
        mint = b["mint"]
        if b.get("d_slot") is not None and b["d_slots"] <= 5: lo = (b["d_slot"], b["d_i"]); hi = b["slot"] + 2
        else: lo = (b["slot"] - 2, 0); hi = b["slot"] + 2
        hit_ok = None; hit_fail = None; m_att = []
        for k in ep_by_mint.get(mint, []):
            E = eps[k]
            if E["s1"] < lo[0] or E["s0"] > hi: continue
            for (s, i, kd, code, pth) in E["att"]:
                if (s, i) > lo and s <= hi:
                    m_att.append((kd, code, pth or E["path"], E["w"], s - (b["d_slot"] if b.get("d_slot") is not None else b["slot"])))
                    if kd == "buy_ok": hit_ok = hit_ok if hit_ok is not None else k
                    else: hit_fail = hit_fail if hit_fail is not None else k
        r["m_att"] = m_att
        r["ep"] = hit_ok if hit_ok is not None else hit_fail
        act = active(b["bt"]); trading = [(rn, X) for rn, X in act if not X["probe_run"]]
        r["servers"] = sorted(set(X["srv"] for rn, X in trading)); r["runs"] = [rn for rn, X in trading]
        if not hour_ok(b["bt"]): r["bucket"] = "NOCOV"; r["reason"] = "tape hour not usable"
        elif hit_ok is not None: r["bucket"] = "f"; r["reason"] = "both filled"
        elif hit_fail is not None: r["bucket"] = "e"; r["reason"] = "we fired, guard/fail; he filled"
        elif not trading: r["bucket"] = "a"; r["reason"] = "probe run only" if act else "no engine running"
        elif r["type"] != "DIP": r["bucket"] = "b"; r["reason"] = r["type"]
        else:
            r["bucket"] = "c"; r.update(classify(b, trading, ids))
        if r["ep"] is not None: eps[r["ep"]]["shared"] = True; eps[r["ep"]]["his"].append(len(rows))
        rows.append(r)
    print(f"haqq lots {len(rows):,} ({time.time() - t0:.0f}s)", flush=True)
    pickle.dump(dict(rows=rows, eps=eps, meta=meta), open(f"{OUT}/g3_rows.pkl", "wb"))
    report(rows, eps, meta)


def envelope_reason(b):
    """why the engine never logged this dump, from the tape (IMIT1 envelope + dump_events rules)"""
    if b.get("d_type", "").startswith("wallet:"): return "other: dump = our own sell"
    if b["d_sol"] < 1.08 or b["d_drop"] < 0.0465: return "dump below thresholds"
    if b["d_age_s"] is not None and b["d_age_s"] > 343.67: return "token too old"
    if not b["lf_ok"]: return "other: launch filter (mayhem/abnormal curve)"
    if b["d_age_s"] is not None and b["d_age_s"] < 1.0: return "other: dump < 1 s after create"
    if b["d_vpost"] >= 100: return "other: curve >= 100 SOL"
    if not b["d_first_big"]: return "other: 2nd >=1 SOL sell in its slot"
    if b["d_since_buy"] > 3.869: return "other: no buy in 3.9 s before the dump"
    return "other: in envelope, not logged"


def classify(b, trading, ids):
    """per server: regular path stage + pre-send stage -> the server that got furthest; returns reason fields"""
    best = None
    seller = ids[b["d_user"]] if b.get("d_user") is not None and b["d_user"] >= 0 else None
    for rn, X in trading:
        # regular path
        recs = X["dumps"].get((b["mint"], b["d_slot"]), [])
        rec = next((x for x in recs if x[0] == b["d_i"]), recs[0] if recs else None)
        if rec is None:
            for ds in (b["d_slot"] - 1, b["d_slot"] - 2):
                rr = X["dumps"].get((b["mint"], ds), [])
                if rr: rec = rr[0]; break
        if rec is None: rs, rr_ = 0, envelope_reason(b)
        else:
            idx, sig, pas, m2p, lok, dev, sell, drop, age, t = rec
            if not pas:
                rs = 1
                rr_ = "other: launch filter (mayhem/abnormal curve)" if lok is False else ("M2 gate score too low" if X["m2mode"] == "gate" and not dev else "gate (IMIT1) score too low")
            elif sig in X["skip"]: rs, rr_ = 2, REG_MAP.get(X["skip"][sig], "other: pick skipped (" + str(X["skip"][sig]) + ")")
            elif sig in X["fire"]: rs, rr_ = 3, "other: fired, nothing landed after the dump"
            else: rs, rr_ = 2, "other: picked, not fired"
        # pre-send path
        ps_s, ps_r = -1, "pre-send off" if not X["ps_on"] else "no whale >= 6%"
        if X["ps_on"] and seller:
            arms = [a for a in X["arms_by"].get((b["mint"], seller), []) if a[2] <= b["d_slot"]]
            sks = [s for s in X["sk_by"].get((b["mint"], seller), []) if s[2] is not None and s[2] <= b["d_slot"]]
            cover = [a for a in arms if (a[4] or a[3] or 0) >= b["d_slot"]]
            if cover: ps_s, ps_r = 3, "other: pre-send armed, nothing landed after the dump"
            elif sks:
                why = sks[-1][3]
                if why in PS_MAP: ps_s, ps_r = 2, PS_MAP[why]
                else: ps_s, ps_r = 0.5, "pre-send not armed: " + str(why)
            elif arms:
                why = arms[-1][5]
                ps_s, ps_r = (2, "QUIET skip") if why == "quiet" else (1.5, "pre-send window ended before the dump (" + str(why) + ")")
            elif (b.get("d_bal_pct") or 0) >= 6.0: ps_s, ps_r = 0.4, "pre-send: whale >= 6% but no trigger"
        # primary: the pre-send reason only when it is a specific refusal or an armed window
        if ps_s >= 2 and ps_s >= rs: st, why, path = ps_s, ps_r, "ps"
        else: st, why, path = rs, rr_, "reg"
        cand = dict(stage=st, reason=why, path=path, reg_reason=rr_, ps_reason=ps_r, srv=X["srv"], run=rn)
        if best is None or st > best["stage"]: best = cand
    # near/far of the dump slot for each region (info)
    best["near"] = {reg: L.leader_info(b["d_slot"], reg)[2] for reg in ("FRA", "AMS")}
    return best


def grp(reason):
    if reason.startswith("other"): return "other"
    if reason.startswith("pre-send not armed") or reason.startswith("pre-send window") or reason.startswith("pre-send: whale") or reason == "no whale >= 6%":
        return "pre-send not armed"
    if reason in ("M2 gate score too low", "gate (IMIT1) score too low"): return "gate refused (M2/IMIT1)"
    return reason


def report(rows, eps, meta):
    out = []
    def P(*a):
        s = " ".join(str(x) for x in a); print(s); out.append(s)
    days = sorted(set(r["day"] for r in rows))
    def agg(v):
        n = len(v); net = sum(r["net"] for r in v); sol = sum(r["size"] for r in v)
        return n, net, sol, (100 * np.mean([r["net"] > 0 for r in v]) if n else 0)
    P("# haqq lots per day and bucket (lot view: P&L of each lot assigned to its buy day; MEASURED tape flows, his tx costs MEASURED from")
    P("# 10-25 19:20 PKT, before that INFERRED at 0.392 mSOL/tx; open lots at tape end marked x0.9875, INFERRED)")
    for d in days:
        V = [r for r in rows if r["day"] == d]
        n, net, sol, win = agg(V)
        P(f"\n## {L.day_name(d)}: {n:,} lots, net {net:+.2f} SOL, SOL in {sol:,.0f}, win {win:.0f}%  (failed-tx fees {meta['hq_failfee'].get(d, float('nan')):.3f} not in lots)")
        P("| bucket | detail | lots | his net SOL | win % | SOL in | net per SOL |"); P("|---|---|---|---|---|---|---|")
        g = collections.defaultdict(list)
        for r in V:
            det = r["reason"] if r["bucket"] in ("a", "b", "NOCOV", "e", "f") else grp(r["reason"]) + " | " + r["reason"]
            g[(r["bucket"], det)].append(r)
        for (bk, det), v in sorted(g.items(), key=lambda kv: ("NOCOV a b c e f".split().index(kv[0][0]), -sum(r["net"] for r in kv[1]))):
            n, net, sol, win = agg(v)
            P(f"| {bk} | {det} | {n:,} | {net:+.2f} | {win:.0f} | {sol:.0f} | {100 * net / max(sol, 1e-9):+.2f}% |")
    open(f"{OUT}/g3_haqq.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
