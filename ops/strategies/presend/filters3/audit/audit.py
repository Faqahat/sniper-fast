#!/usr/bin/env python3
"""FILTERS-3 AUDIT step 2: every LIVE filter and every LOG-ONLY rule, per run (r37..r46), from the extracted pickles (extract.py).
Read-only on the data. Writes /home/moiz/sniper-data/filters3/audit/core.pkl (positions + per-run tables) and prints the tables.

Money:
  * trades we took: the live realized P&L (presend_live_realized.pnl). A rule that would have BLOCKED a trade saves exactly -pnl.
  * live skips / stops (trades we did not take): the main shadow's row c (net_cheap) on the same T2 trigger, scaled to the live T2
    size, CALIBRATED as wide_report.py: per run, mean (live realized - paper) over the live T2 windows whose shadow window filled;
    every shadow fill gets that gap added. ESTIMATE. Re-arm windows have no shadow: counted only.
  * "w/o top 5": the 5 trades that helped the rule's verdict most are dropped (if the rule saves money, its 5 biggest blocked
    losers; if it costs, its 5 biggest blocked winners).
usage: audit.py"""
import pickle, json, collections, os, time, subprocess
EX = "/home/moiz/sniper-data/filters3/audit/ex"
OUT = "/home/moiz/sniper-data/filters3/audit"
RUNS = [f"r{i}" for i in range(37, 47)]
CUT = int(time.mktime(time.strptime("2026-11-01 07:00:00", "%Y-%m-%d %H:%M:%S")) - time.timezone) * 10**9   # 11-01 12:00 PKT
def pkt(t): return time.strftime("%m-%d %H:%M", time.gmtime(t / 1e9 + 5 * 3600)) if t else "?"
def period(run, t):
    if run in ("r43", "r44", "r45", "r46"): return "HOLD"
    if run == "r42" and t and t >= CUT: return "VAL"
    return "DEV"
MECH = {"blocked_armed", "blocked_position", "blocked_ata_open", "reactive_position", "no_launch_accounts", "legacy_create", "mayhem", "stopped"}

def summ(vals, sign=+1):
    """vals = P&L of the trades a rule touches. -> dict n, win n/sol, loss n/sol, net, saved (-net), saved w/o top 5"""
    v = [x for x in vals if x is not None]
    w = [x for x in v if x > 0]; l = [x for x in v if x <= 0]
    net = sum(v); saved = -net
    s = sorted(v)                     # ascending: biggest losers first
    if saved >= 0: rest = s[5:]       # drop its 5 biggest blocked losers
    else: rest = s[:-5] if len(s) > 5 else []
    return dict(n=len(v), wn=len(w), ws=sum(w), ln=len(l), ls=sum(l), net=net, saved=saved, saved_wo5=-sum(rest))

# bad-creator seed (built from VERIFY tables up to AMS r38: in-sample for r37/r38, so the rule is scored from r39 on)
SEED = json.load(open("/home/moiz/sniper-data/prevent/forward/gcr_seed.json"))
led = collections.defaultdict(lambda: [0, 0.0])
for c, d in SEED.items(): led[c] = [d["n"], d["sum"]]

def deep_windows(run):
    """r40 only (deeper limit live): live windows with an attempt sent at the deeper drop"""
    if run != "r40": return set()
    out = set()
    p = subprocess.run(["grep", '"ev":"presend_attempt"', f"/home/moiz/sniper-data/filters3/runs/{run}.presend.jsonl"], capture_output=True, text=True).stdout
    for l in p.splitlines():
        d = json.loads(l)
        if (d.get("drop") or 0) > 0.125: out.add((1, d["w"]))
    return out

POS, TAB, CAL, SKIPV, EXTRA = [], {}, {}, [], {}
ITEMS = collections.defaultdict(list)     # (run, rule) -> [(period, value SOL or None, t ns)]
for run in RUNS:
    S = pickle.load(open(f"{EX}/{run}.pkl", "rb"))
    nseg = len(S.get("qstate", []))
    # config per segment: the run_start whose t is the latest <= the segment's first record (quiet_state t)
    starts = sorted(S["starts"], key=lambda x: x["t"])
    cfg = {}
    for i, q in enumerate(S.get("qstate", []), 1):
        c = [s for s in starts if s["t"] <= q["t"]]
        cfg[i] = (c[-1] if c else starts[0])["presend_live"]
    seg_t = {}
    for k, a in S["larm"].items():
        t = (a.get("trig") or {}).get("t") or (a.get("dump") or {}).get("t")
        if t: lo, hi = seg_t.get(k[0], (t, t)); seg_t[k[0]] = (min(lo, t), max(hi, t))
    for st in S["stops"]:
        lo, hi = seg_t.get(st["seg"], (st["t"], st["t"])); seg_t[st["seg"]] = (min(lo, S["qstate"][st["seg"] - 1]["t"]), max(hi, st["t"]))
    hours = sum((hi - lo) / 3.6e12 for lo, hi in seg_t.values())
    spend = {s: cfg[s]["spend"] / 1e9 for s in cfg}
    # ---- the main shadow
    sig2sh = {}
    for k, a in S["sh_arm"].items(): sig2sh[(k[0], a["sig"])] = k
    def paper(k):
        x = S["sh_exit"].get(k); f = S["sh_fill"].get(k)
        if x is None or f is None: return None
        return x["net"] * (spend[k[0]] * 1e9 / f["sol_in"] if f.get("sol_in") else 1.0)
    # ---- live windows: realized per window
    win_real = collections.defaultdict(float)
    for r in S["lreal"]: win_real[(r["seg"], r["w"])] += r["pnl"] / 1e9
    # ---- calibration (wide_report.py's): live T2 windows whose shadow window filled
    pairs = []
    for k, a in S["larm"].items():
        if a["kind"] != "t2": continue
        sk = sig2sh.get((k[0], a["trig"]["sig"]))
        if sk is None: continue
        p = paper(sk)
        if p is None: continue
        pairs.append((p, win_real.get(k, 0.0)))
    gap = sum(r - p for p, r in pairs) / len(pairs) if pairs else 0.0
    # the reverse view: live T2 fills whose shadow window did NOT fill
    live_only = [win_real[k] for k, a in S["larm"].items() if a["kind"] == "t2" and k in win_real and paper(sig2sh.get((k[0], a["trig"]["sig"]), (0, 0))) is None]
    CAL[run] = dict(pairs=len(pairs), paper=sum(p for p, _ in pairs), live=sum(r for _, r in pairs), gap=gap, live_only_n=len(live_only), live_only_sol=sum(live_only), hours=hours)
    def est(k):
        p = paper(k)
        return (None, None) if p is None else (p, p + gap)
    # ---- positions
    for r in S["lreal"]:
        seg, w, m = r["seg"], r["w"], r["mint"]
        a = S["larm"].get((seg, w), {}); f = S["lfill"].get((seg, w, m), {}); c = S["lclose"].get((seg, w, m, r.get("pid")), {})
        dis = S["ldis"].get((seg, w), {})
        kind = r.get("kind", "t2")
        trig = a.get("trig") or {}; dump = a.get("dump") or {}
        sells = [x[0] for x in (c.get("sell_lands") or [])]
        att = S["att_ok"].get(f.get("sig")) or {}
        ann = f.get("ann") or {}; aann = a.get("ann") or {}
        sk = sig2sh.get((seg, trig.get("sig"))) if kind == "t2" else None
        POS.append(dict(run=run, seg=seg, w=w, mint=m, pid=r.get("pid"), kind=kind, pnl=r["pnl"] / 1e9, t=f.get("t"), slot=f.get("slot"), idx=f.get("idx"),
                        sell_slot=max(sells) if sells else c.get("exit_slot"), exit_why=c.get("exit_why"), held_s=c.get("held_s"),
                        whale=trig.get("wallet") or dump.get("seller"), trig_slot=trig.get("slot") or dump.get("slot"), trig_sig=trig.get("sig") or dump.get("sig"),
                        trig_pct=trig.get("pct") or dump.get("pct"), age=trig.get("age_slots") if kind == "t2" else dump.get("age_slots"),
                        quiet=a.get("quiet"), v2=a.get("v2"), nb=a.get("nb"), nb50=aann.get("nb50"), creator=aann.get("creator"), cr_pct=aann.get("cr_pct"),
                        holders_arm=a.get("holders"), ann=ann, deep=f.get("deep"), sat=f.get("slots_after_trigger"), dis_quiet=dis.get("quiet"), rearm_dis=dis.get("rearm"),
                        att_between=att.get("between"), att_after=att.get("after"), att_d=att.get("d"), inst_before=att.get("instant_before_us"), inst_after=att.get("instant_after_us"),
                        extra_fills=f.get("extra_fills"), sh_paper=(paper(sk) if sk else None), period=period(run, f.get("t"))))
    pos_run = [p for p in POS if p["run"] == run]
    # ---- LIVE T2 skips
    rows = collections.OrderedDict()
    by_why = collections.defaultdict(list)
    for d in S["skips"]:
        why = d.get("why") or "?"; tr = d.get("trig") or {}
        sk = sig2sh.get((d["seg"], tr.get("sig")))
        p, e = est(sk) if sk else (None, None)
        q = d.get("quiet") or {}
        rec = dict(run=run, seg=d["seg"], why=why, sig=tr.get("sig"), mint=tr.get("mint"), wallet=tr.get("wallet"), t=tr.get("t"), slot=tr.get("slot"), pct=tr.get("pct"),
                   age=tr.get("age_slots"), paper=p, est=e, all4=q.get("all4"), q=q.get("q"), nb=d.get("nb"), v2skip=(d.get("v2") or {}).get("skip"), sh=sk,
                   sh_fill=S["sh_fill"].get(sk) if sk else None, sh_exit=S["sh_exit"].get(sk) if sk else None, period=period(run, tr.get("t")))
        SKIPV.append(rec); by_why[why].append(rec)
    for why, recs in sorted(by_why.items(), key=lambda kv: -len(kv[1])):
        ITEMS[(run, f"skip:{why}")] = [(x["period"], x["est"], x["t"], x["paper"]) for x in recs]
        s = summ([x["est"] for x in recs]); sp = summ([x["paper"] for x in recs])
        rows[f"skip:{why}"] = dict(type="LIVE" if why not in MECH else "MECH", trig=len(recs), filled=s["n"], est=s, paper=sp,
                                   ov_quiet_all4=sum(1 for x in recs if x["all4"]), ov_lone=sum(1 for x in recs if x["nb"] is not None and x["nb"] <= 1),
                                   ov_v2=sum(1 for x in recs if x["v2skip"]))
    # ---- re-arm skips: counts only (no shadow of re-arm windows)
    rc = collections.Counter(d["why"] for d in S["rskips"])
    for why, n in rc.most_common(): rows[f"rearm_skip:{why}"] = dict(type="LIVE" if why in ("rearm_no_holder", "rearm_age", "rearm_r5") else "MECH", trig=n, filled=None, est=None, paper=None)
    # ---- QUIET stop, T2 (5:2): live windows disarmed "quiet" that never filled live -> the shadow's fill at or after the stop slot
    qs_rec = []
    for k, dd in S["ldis"].items():
        if dd.get("kind", "t2") != "t2" or dd.get("why") != "quiet" or dd.get("filled"): continue
        a = S["larm"].get(k) or {}; sk = sig2sh.get((k[0], (a.get("trig") or {}).get("sig")))
        p, e = (None, None)
        if sk and S["sh_fill"].get(sk) and S["sh_fill"][sk]["s_in"] is not None and S["sh_fill"][sk]["s_in"] >= dd.get("slot", 0):
            p, e = est(sk)
        qs_rec.append(dict(w=k, paper=p, est=e, mint=dd.get("mint"), sh=sk, t=dd.get("t"), stop_slot=dd.get("slot"), trig_slot=dd.get("trig_slot")))
    ITEMS[(run, "stop:quiet_t2")] = [(period(run, x["t"]), x["est"], x["t"], x["paper"]) for x in qs_rec]
    s = summ([x["est"] for x in qs_rec]); rows["stop:quiet_t2"] = dict(type="LIVE", trig=len(qs_rec), filled=s["n"], est=s, paper=summ([x["paper"] for x in qs_rec]))
    EXTRA.setdefault("qstop_t2", {})[run] = qs_rec
    # the shadow's own view of the T2 stop on EVERY trigger (traded or skipped): fills it would cut (at / after the stop slot) vs keep
    cut, keep = [], []
    for k, dd in S["sh_dis"].items():
        qs = dd.get("qs") or {}
        if not qs.get("stop"): continue
        f = S["sh_fill"].get(k)
        if not f or f.get("s_in") is None: continue
        p, e = est(k)
        (cut if f["s_in"] >= (qs.get("slot") or 0) else keep).append(e)
        if f["s_in"] >= (qs.get("slot") or 0): ITEMS[(run, "stop:quiet_t2_shadow_all")].append((period(run, f.get("t")), e, f.get("t"), p))
    rows["stop:quiet_t2_shadow_all"] = dict(type="INFO", trig=sum(1 for d in S["sh_dis"].values() if (d.get("qs") or {}).get("stop")), filled=len(cut), est=summ(cut), paper=None, note=f"fills before the stop slot kept: {len(keep)}")
    # QUIET stop, re-arm (6:2): counts only
    rq = [dd for dd in S["ldis"].values() if dd.get("kind") == "rearm" and dd.get("why") == "quiet"]
    rows["stop:quiet_rearm"] = dict(type="LIVE", trig=len(rq), filled=None, est=None, paper=None)
    # ---- deeper limit (r40, live)
    if run == "r40":
        dw = deep_windows(run)
        filled_w = {(p["seg"], p["w"]) for p in pos_run}
        refused = []
        for k in dw:
            a = S["larm"].get(k) or {}
            if a.get("kind") != "t2" or k in filled_w: continue
            sk = sig2sh.get((k[0], a["trig"]["sig"]))
            refused.append(est(sk)[1] if sk else None)
        df = [p["pnl"] for p in pos_run if p["deep"]]
        ITEMS[(run, "live:deep_limit_refused")] = [("DEV", x, None, None) for x in refused]
        ITEMS[(run, "live:deep_limit_deep_fills")] = [("DEV", x, None, None) for x in df]
        rows["live:deep_limit_refused"] = dict(type="LIVE", trig=len([k for k in dw if (S["larm"].get(k) or {}).get("kind") == "t2" and k not in filled_w]), filled=summ(refused)["n"], est=summ(refused), paper=None)
        rows["live:deep_limit_deep_fills"] = dict(type="LIVE-real", trig=len(df), filled=len(df), est=summ(df), paper=None, note="real P&L of fills bought >= 15% down")
    # ---- profit lock / kill switch (from the logs: r38 lock, r41 kill, r44 lock, r45 kill): shadow fills after the stop
    for st in S["stops"]:
        aft = [est(k)[1] for k, f in S["sh_fill"].items() if k[0] == st["seg"] and f.get("t") and f["t"] > st["t"]]
        rows[f"stop:run_stop_seg{st['seg']}"] = dict(type="INFO", trig=None, filled=len([x for x in aft if x is not None]), est=summ(aft), paper=None, note=f"shadow fills after the stop {pkt(st['t'])} PKT until the process ended")
    # ---- LOG-ONLY rules on the run's real trades
    def gr(a):
        if "grp_block" in a: return bool(a["grp_block"])
        return sum(h.get("pct", 0) for h in a.get("holders", []) if (h.get("risk") or 0) >= 5 and (h.get("hz3") or 0) >= 0.3) >= 6.0
    has_ann = any(p["ann"] for p in pos_run)
    LOG = collections.OrderedDict()
    if has_ann:
        LOG["log:safe_sell_timer"] = ("st_block", lambda p: p["ann"].get("st_block") if "st_block" in p["ann"] else None)
        LOG["log:holder_clock"] = ("holders", lambda p: any(h.get("pct", 0) >= 6 and h.get("n", 0) >= 5 and (h.get("h3") or 0) >= 0.3 for h in p["ann"].get("holders", [])) if p["ann"].get("holders") is not None else None)
        LOG["log:group_risk"] = ("grp", lambda p: gr(p["ann"]) if p["ann"] else None)
        LOG["log:landing_guard"] = ("guard", lambda p: (p["ann"].get("guard") or {}).get("block") if "guard" in p["ann"] else None)
        LOG["log:ctx85"] = ("ctx85", lambda p: p["ann"].get("ctx85") if (run != "r40" and "ctx85" in p["ann"]) else None)
    LOG["log:quiet_v2"] = ("v2", lambda p: (p["v2"] or {}).get("skip") if p["kind"] == "t2" and p["v2"] else None)
    LOG["log:quiet_warmup_would_skip"] = ("qw", lambda p: bool((p["quiet"] or {}).get("would_skip")) if p["kind"] == "t2" and p["quiet"] else None)
    LOG["log:nb50_le2_t2"] = ("nb", lambda p: (p["nb50"] <= 2) if p["kind"] == "t2" and p["nb50"] is not None else None)
    LOG["log:nb50_le1_rearm"] = ("nb", lambda p: (p["nb50"] <= 1) if p["kind"] == "rearm" and p["nb50"] is not None else None)
    flags = {}
    for name, (_, fn) in LOG.items():
        vals = []
        for p in pos_run:
            try: v = fn(p)
            except Exception: v = None
            p.setdefault("flags", {})[name] = v
            if v: vals.append(p["pnl"]); ITEMS[(run, name)].append((p["period"], p["pnl"], p["t"], None))
        cov = sum(1 for p in pos_run if p["flags"][name] is not None)
        rows[name] = dict(type="LOG", trig=cov, filled=len(vals), est=summ(vals), paper=None, note=f"trades with the field: {cov}")
    # bad creator, chained ledger (seed = up to r38 -> scored from r39)
    if run >= "r39":
        vals = []
        for p in sorted(pos_run, key=lambda x: x["t"] or 0):
            c = p["creator"]; n, s_ = led[c] if c else (0, 0.0)
            fl = bool(c and (p["cr_pct"] or 0) >= 3 and n >= 2 and s_ <= -0.05)
            p.setdefault("flags", {})["log:bad_creator"] = fl if c else None
            if fl: vals.append(p["pnl"]); ITEMS[(run, "log:bad_creator")].append((p["period"], p["pnl"], p["t"], None))
            if c and (p["cr_pct"] or 0) >= 3: led[c][0] += 1; led[c][1] += p["pnl"]
        rows["log:bad_creator"] = dict(type="LOG", trig=sum(1 for p in pos_run if p["creator"]), filled=len(vals), est=summ(vals), paper=None)
    # ---- wide shadow (r41+): wide_report.py's calibrated estimate, after the age-1/create-slot skip
    if S["wa"]:
        wv, wp = [], []
        for k, a in S["wa"].items():
            if k not in S["wx"] or (a.get("age_slots") or 0) < 2: continue
            sz = S["wf"].get(k); p = S["wx"][k] * (spend[k[0]] * 1e9 / sz if sz else 1.0)
            wp.append(p); wv.append(p + gap); ITEMS[(run, "log:wide_shadow_3to6")].append((period(run, a.get("t")), p + gap, a.get("t"), p))
        rows["log:wide_shadow_3to6"] = dict(type="ADD-EST", trig=len(S["wa"]), filled=len(wv), est=summ(wv), paper=summ(wp), note="ESTIMATE of trades ADDED (QUIET/10-sec skip not applied); saved = minus the gain")
    # ---- overlap of log rules on the run's trades
    names = [n for n in rows if n.startswith("log:") and n != "log:wide_shadow_3to6"]
    ov = {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            n = sum(1 for p in pos_run if (p.get("flags") or {}).get(a) and (p.get("flags") or {}).get(b))
            if n: ov[f"{a}&{b}"] = n
    core = ["log:safe_sell_timer", "log:holder_clock", "log:group_risk", "log:landing_guard", "log:bad_creator", "log:quiet_v2"]
    uni = [p["pnl"] for p in pos_run if any((p.get("flags") or {}).get(n) for n in core)]
    ITEMS[(run, "log:UNION_core6")] = [(p["period"], p["pnl"], p["t"], None) for p in pos_run if any((p.get("flags") or {}).get(n) for n in core)]
    rows["log:UNION_core6"] = dict(type="LOG", trig=None, filled=len(uni), est=summ(uni), paper=None, note="any of safe timer / holder clock / group risk / landing guard / bad creator / QUIET v2")
    real = [p["pnl"] for p in pos_run]
    TAB[run] = dict(rows=rows, overlap=ov, hours=hours, n=len(real), pnl=sum(real), win=sum(1 for x in real if x > 0), cal=CAL[run], spend=spend,
                    t2=summ([p["pnl"] for p in pos_run if p["kind"] == "t2"]), rearm=summ([p["pnl"] for p in pos_run if p["kind"] == "rearm"]),
                    first=min((p["t"] for p in pos_run if p["t"]), default=None), last=max((p["t"] for p in pos_run if p["t"]), default=None))
    print(f"{run}: {len(real)} trades {sum(real):+.3f} SOL in {hours:.1f} h | calibration gap {gap*1000:+.2f} mSOL/window on {len(pairs)} pairs (paper {CAL[run]['paper']:+.3f} vs live {CAL[run]['live']:+.3f}; live-only fills {CAL[run]['live_only_n']} {CAL[run]['live_only_sol']:+.3f})", flush=True)

pickle.dump(dict(POS=POS, TAB=TAB, CAL=CAL, SKIPV=SKIPV, EXTRA=EXTRA, ITEMS=dict(ITEMS)), open(f"{OUT}/core.pkl", "wb"))
for run in RUNS:
    T = TAB[run]
    print(f"\n=== {run}  {pkt(T['first'])} -> {pkt(T['last'])} PKT  {T['hours']:.1f} h  trades {T['n']}  real {T['pnl']:+.3f}  win {T['win']}/{T['n']}  (T2 {T['t2']['n']} {T['t2']['net']:+.3f} | re-arm {T['rearm']['n']} {T['rearm']['net']:+.3f})")
    print(f"{'filter':34s} {'type':7s} {'trig':>6s} {'n$':>5s} | {'win n':>5s} {'win SOL':>8s} | {'loss n':>6s} {'loss SOL':>9s} | {'saved':>7s} {'w/o5':>7s} | paper")
    for name, r in T["rows"].items():
        e = r.get("est")
        if e is None: print(f"{name:34s} {r['type']:7s} {r['trig'] or 0:6d}   (no money view)"); continue
        pp = r.get("paper"); pps = f"{-pp['net']:+.3f}" if pp else ""
        print(f"{name:34s} {r['type']:7s} {r['trig'] if r['trig'] is not None else '':>6} {e['n']:5d} | {e['wn']:5d} {e['ws']:+8.3f} | {e['ln']:6d} {e['ls']:+9.3f} | {e['saved']:+7.3f} {e['saved_wo5']:+7.3f} | {pps} {r.get('note','')}")
    if T["overlap"]: print("  overlap:", T["overlap"])
