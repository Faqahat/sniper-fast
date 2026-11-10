#!/usr/bin/env python3
"""FILTERS-3 AUDIT step 4: the QUIET deep-dive. Read-only. Needs core.pkl (audit.py), ex/*.pkl (extract.py), win.pkl (windows.py).
Labels every live trade by how busy its token was, with
  * the RECORDS (every run): presend_live_tape (trades while our position was open: our fill -> about our sell) and the filled
    attempt's landing record (the trades in our slot before / after us); "rec" labels = within our hold only;
  * the RAW 24/7 recordings where they cover the time (win.pkl): every trade, any N.
Labels (others = any wallet but ours and the trigger whale / the re-arm dumper):
  (a) N: no trade by others after our fill up to our sell slot + N
  (b) K: no BUY by others in our fill slot (before or after us) or after us up to our sell slot + K
  (c) N: no trade by a known dip bot (ops/strategies/presend/botpnl list) from our fill slot to our sell slot + N
Then: loss share of quiet trades per run / day; QUIET's four arm signals on them (which one said "not quiet"); what QUIET skipped
that was not quiet (shadow ESTIMATE, calibrated as audit.py); QUIET stop T2 5:2 (audit.py) and re-arm 6:2 (raw-recording proxy
replay, calibrated on the live re-arm fills; ESTIMATE).
usage: quiet.py"""
import pickle, json, collections, time, math
A = "/home/it/sniper-data/filters3/audit"
C = pickle.load(open(f"{A}/core.pkl", "rb")); POS, TAB, CAL, SKIPV = C["POS"], C["TAB"], C["CAL"], C["SKIPV"]
W = pickle.load(open(f"{A}/win.pkl", "rb")); ROWS, COV = W["rows"], W["cov"]
OURS = ("EgxfYgEb", "2g7rYv7y")
BOTS = {"haqqiUUX", "2VggYpPu", "haqq6qnV", "8yYMhuYo", "DF7eRXHn", "E2x1ewwX", "HkQ7hMjy", "DYXDDrZC", "CvHEVC7S", "HLU8QbLd", "6VzXcLk9", "4ggJqUDD", "DSvgfynk"}
RUNS = [f"r{i}" for i in range(37, 47)]
CUT = int(time.mktime(time.strptime("2026-11-01 07:00:00", "%Y-%m-%d %H:%M:%S")) - time.timezone) * 10**9   # 11-01 12:00 PKT
def pkt(t): return time.strftime("%m-%d %H:%M", time.gmtime(t / 1e9 + 5 * 3600)) if t else "?"
def day(t): return time.strftime("%m-%d", time.gmtime(t / 1e9 + 5 * 3600)) if t else "?"
def covered(lo, hi): return any(c[0] is not None and c[0] <= lo and hi <= c[1] for c in COV.values())
def is_us(u): return u is not None and u[:8] in OURS
NS = [0, 2, 5, 10, 20]

def raw_labels(p):
    F, I, X = p["slot"], p["idx"] or 0, p["sell_slot"] or p["slot"]
    if F is None or not covered(F - 2, X + 25): return None
    rows = [r for r in ROWS.get(p["mint"], []) if not r[5]]
    wh = p["whale"]
    oth = [r for r in rows if not is_us(r[2]) and r[2] != wh]
    out = {}
    for N in NS:
        out[f"a{N}"] = not any((r[0], r[1]) > (F, I) and r[0] <= X + N for r in oth)
        out[f"b{N}"] = not any(r[3] > 0 and (r[0] == F or ((r[0], r[1]) > (F, I) and r[0] <= X + N)) for r in oth)
        out[f"c{N}"] = not any(r[2] and r[2][:8] in BOTS and F <= r[0] <= X + N for r in rows)
    out["n_oth_buyers_b5"] = len({r[2] for r in oth if r[3] > 0 and (r[0] == F or ((r[0], r[1]) > (F, I) and r[0] <= X + 5))})
    return out

def rec_labels(p, tape):
    """records only: our slot (attempt landing: trades before / after us) + the live tape (fill -> about the sell)"""
    F, I, X = p["slot"], p["idx"] or 0, p["sell_slot"] or p["slot"]
    whp = (p["whale"] or "")[:8]
    tr = []      # (slot, idx, user8, buy)
    for x in (p["att_between"] or []) + (p["att_after"] or []):
        tr.append((x.get("slot", F), x.get("idx", 0), (x.get("user") or "")[:8], x.get("buy")))
    for (s, i, u, b, sol, t, vs, vt) in tape:
        if F <= s <= X: tr.append((s, i, u[:8], b))
    oth = [x for x in tr if x[2] not in OURS and x[2] != whp]
    return dict(a=not any((x[0], x[1]) > (F, I) for x in oth), b=not any(x[3] and (x[0] == F or (x[0], x[1]) > (F, I)) for x in oth),
                c=not any(x[2] in BOTS for x in tr))

EX = {r: pickle.load(open(f"{A}/ex/{r}.pkl", "rb")) for r in RUNS}
for p in POS:
    S = EX[p["run"]]
    tape = [x for x in S["tape"].get(p["mint"], []) if p["t"] and p["t"] - 2e9 <= x[5] <= p["t"] + 60e9]
    p["rec"] = rec_labels(p, tape)
    p["raw"] = raw_labels(p)

def sm(v):
    v = list(v); n = len(v); s = sum(v)
    return dict(n=n, net=s, win=sum(1 for x in v if x > 0), loss_sol=sum(x for x in v if x < 0), mean=(s / n * 1000 if n else 0.0))

OUT = collections.OrderedDict()
# ---------------- Q1: quiet trades per run (records labels, all runs) + raw labels where covered
q1 = collections.OrderedDict()
for run in RUNS + ["ALL"]:
    ps = [p for p in POS if run == "ALL" or p["run"] == run]
    tot_loss = sum(p["pnl"] for p in ps if p["pnl"] < 0)
    row = dict(n=len(ps), net=sum(p["pnl"] for p in ps), tot_loss=tot_loss)
    for lab in ("a", "b", "c"):
        qs = [p for p in ps if p["rec"][lab]]; bs = [p for p in ps if not p["rec"][lab]]
        row[f"rec_{lab}"] = dict(quiet=sm(p["pnl"] for p in qs), busy=sm(p["pnl"] for p in bs),
                               loss_share=(sum(p["pnl"] for p in qs if p["pnl"] < 0) / tot_loss if tot_loss else 0.0))
    cov = [p for p in ps if p["raw"]]
    row["raw_cov"] = len(cov)
    for lab in ("a5", "b2", "b5", "c5", "c10"):
        qs = [p for p in cov if p["raw"][lab]]; bs = [p for p in cov if not p["raw"][lab]]
        tl = sum(p["pnl"] for p in cov if p["pnl"] < 0)
        row[f"raw_{lab}"] = dict(quiet=sm(p["pnl"] for p in qs), busy=sm(p["pnl"] for p in bs), loss_share=(sum(p["pnl"] for p in qs if p["pnl"] < 0) / tl if tl else 0.0))
    for kind in ("t2", "rearm"):
        ks = [p for p in ps if p["kind"] == kind]
        row[f"rec_b_{kind}"] = dict(quiet=sm(p["pnl"] for p in ks if p["rec"]["b"]), busy=sm(p["pnl"] for p in ks if not p["rec"]["b"]))
    q1[run] = row
OUT["q1"] = q1
# sensitivity in N on the raw-covered trades
sens = collections.OrderedDict()
cov = [p for p in POS if p["raw"]]
for lab in ("a", "b", "c"):
    for N in NS:
        k = f"{lab}{N}"; qs = [p for p in cov if p["raw"][k]]
        sens[k] = dict(quiet=sm(p["pnl"] for p in qs), busy=sm(p["pnl"] for p in cov if not p["raw"][k]))
OUT["sens"] = sens
# agreement records-vs-raw on (b)
agree = collections.Counter((p["rec"]["b"], p["raw"]["b0"]) for p in cov)
OUT["agree_b_rec_vs_raw_b0"] = {f"rec={a} raw={b}": n for (a, b), n in agree.items()}
# per day (PKT), records label (b)
byday = collections.OrderedDict()
for p in sorted(POS, key=lambda x: x["t"] or 0):
    d = day(p["t"]); x = byday.setdefault(d, dict(q=[], b=[]))
    (x["q"] if p["rec"]["b"] else x["b"]).append(p["pnl"])
OUT["byday_rec_b"] = {d: dict(quiet=sm(x["q"]), busy=sm(x["b"])) for d, x in byday.items()}
by6 = collections.OrderedDict()
for p in sorted(POS, key=lambda x: x["t"] or 0):
    h = time.gmtime(p["t"] / 1e9 + 5 * 3600); k = f"{h.tm_mon:02d}-{h.tm_mday:02d} {h.tm_hour // 6 * 6:02d}h"
    x = by6.setdefault(k, dict(q=[], b=[])); (x["q"] if p["rec"]["b"] else x["b"]).append(p["pnl"])
OUT["by6h_rec_b"] = {d: dict(quiet=sm(x["q"]), busy=sm(x["b"])) for d, x in by6.items()}
# by period
OUT["byperiod_rec_b"] = {per: dict(quiet=sm(p["pnl"] for p in POS if p["period"] == per and p["rec"]["b"]), busy=sm(p["pnl"] for p in POS if p["period"] == per and not p["rec"]["b"])) for per in ("DEV", "VAL", "HOLD")}

# ---------------- Q2: QUIET's arm signals on the quiet T2 trades we took
FL = ["since_last>=1", "no cohort holder", "<2 follower bots", "whale fol<4"]
q2 = collections.OrderedDict()
for scope in ("ALL", "DEV", "VAL", "HOLD"):
    ps = [p for p in POS if p["kind"] == "t2" and p["quiet"] and p["quiet"].get("q") and (scope == "ALL" or p["period"] == scope)]
    for lab in ("quiet", "busy"):
        sel = [p for p in ps if p["rec"]["b"] == (lab == "quiet")]
        fail = collections.Counter(); combo = collections.Counter(); pnl_by = collections.defaultdict(list)
        for p in sel:
            q = p["quiet"]["q"]
            bad = tuple(FL[i] for i, x in enumerate(q) if not x)
            combo[" + ".join(bad) or "(all four held: rule off?)"] += 1; pnl_by[" + ".join(bad) or "(all four held)"].append(p["pnl"])
            for b in bad: fail[b] += 1
        q2[f"{scope}:{lab}"] = dict(n=len(sel), net=sum(p["pnl"] for p in sel), signal_false=dict(fail), combos={k: dict(n=v, **{x: y for x, y in sm(pnl_by[k]).items() if x in ("net", "mean", "win")}) for k, v in combo.most_common()})
    # leave-one-signal-out (DIAGNOSTIC, not a rule): trades we took that 3 of the 4 signals call quiet (the one that failed alone)
    loo = {}
    for i, name in enumerate(FL):
        sel = [p for p in ps if not p["quiet"]["q"][i] and all(x for j, x in enumerate(p["quiet"]["q"]) if j != i)]
        loo[f"only '{name}' failed"] = dict(all=sm(p["pnl"] for p in sel), quiet=sm(p["pnl"] for p in sel if p["rec"]["b"]), busy=sm(p["pnl"] for p in sel if not p["rec"]["b"]))
    q2[f"{scope}:loo"] = loo
# signal values on quiet trades: since_last, wh_fol, coh_hold distributions
dist = collections.defaultdict(collections.Counter)
for p in POS:
    if p["kind"] != "t2" or not p["quiet"] or not p["quiet"].get("q"): continue
    lab = "quiet" if p["rec"]["b"] else "busy"; q = p["quiet"]
    dist[f"{lab}:since_last"][min(q.get("since_last", 0), 5)] += 1
    dist[f"{lab}:coh_hold"][min(q.get("coh_hold", 0), 3)] += 1
    wf = q.get("wh_fol", -1); dist[f"{lab}:wh_fol"]["none" if wf < 0 else ("<1" if wf < 1 else "<2.24" if wf < 2.24 else "<4" if wf < 4 else "<8" if wf < 8 else ">=8")] += 1
OUT["q2"] = q2; OUT["q2_dist"] = {k: dict(v) for k, v in dist.items()}
# re-arm trades: QUIET never looks at them (r5_skip off)
OUT["q2_rearm"] = {per: dict(quiet=sm(p["pnl"] for p in POS if p["kind"] == "rearm" and p["rec"]["b"] and (per == "ALL" or p["period"] == per)),
                             busy=sm(p["pnl"] for p in POS if p["kind"] == "rearm" and not p["rec"]["b"] and (per == "ALL" or p["period"] == per))) for per in ("ALL", "DEV", "VAL", "HOLD")}

# ---------------- Q3: trigger-level busy-ness (raw), QUIET skips vs live arms; what QUIET skipped that was NOT quiet
def trig_busy(mint, slot, whale, K=12):
    if not covered(slot - 2, slot + 45): return None
    rows = [r for r in ROWS.get(mint, []) if not r[5] and slot < r[0] <= slot + K and not is_us(r[2]) and r[2] != whale]
    return dict(buyers=len({r[2] for r in rows if r[3] > 0}), bots=len({r[2] for r in rows if r[2] and r[2][:8] in BOTS}), trades=len(rows))
def fill_busy(mint, s_in, x_slot, whale, K=2):
    if s_in is None or not covered(s_in - 2, (x_slot or s_in) + 25): return None
    rows = [r for r in ROWS.get(mint, []) if not r[5] and not is_us(r[2]) and r[2] != whale]
    X = x_slot or s_in + 2
    return not any(r[3] > 0 and s_in <= r[0] <= X + K for r in rows)
q3 = collections.OrderedDict()
SKIX = {(x["run"], x["seg"], x["sig"]): x for x in SKIPV}
for run in RUNS:
    S = EX[run]
    armed_sig = {(k[0], (a.get("trig") or {}).get("sig")): k for k, a in S["larm"].items() if a.get("kind") == "t2"}
    filled_w = {(p["seg"], p["w"]) for p in POS if p["run"] == run}
    rows = []
    for k, a in S["sh_arm"].items():
        tb = trig_busy(a["mint"], a["slot"], a["wallet"])
        if tb is None: continue
        q = a.get("quiet") or {}
        lk = armed_sig.get((k[0], a["sig"]))
        skip = SKIX.get((run, k[0], a["sig"])) if lk is None else None
        rows.append(dict(all4=q.get("all4"), armed=lk is not None, filled=lk in filled_w if lk else False, why=(skip or {}).get("why"), **tb))
    q3[run] = rows
def agg3(rs):
    out = {}
    for name, sel in (("QUIET-skipped", [r for r in rs if r["why"] == "quiet"]), ("armed live", [r for r in rs if r["armed"]]),
                      ("all4 true (any)", [r for r in rs if r["all4"]]), ("all4 false (any)", [r for r in rs if r["all4"] is False])):
        n = len(sel)
        out[name] = dict(n=n, no_buyer_12=sum(1 for r in sel if r["buyers"] == 0) / n if n else 0, ge2_buyers=sum(1 for r in sel if r["buyers"] >= 2) / n if n else 0,
                         bot_in=sum(1 for r in sel if r["bots"] > 0) / n if n else 0, med_buyers=sorted(r["buyers"] for r in sel)[n // 2] if n else 0)
    return out
OUT["q3_trigger_busy"] = {run: agg3(rs) for run, rs in q3.items() if rs}
OUT["q3_trigger_busy"]["ALL"] = agg3([r for rs in q3.values() for r in rs])
# QUIET skips the shadow filled: busy or quiet around the shadow fill, and their ESTIMATE value
qs = []
for x in SKIPV:
    if x["why"] != "quiet": continue
    f, e = x.get("sh_fill"), x.get("sh_exit")
    lab = fill_busy(x["mint"], f["s_in"], (e or {}).get("exit_slot"), x["wallet"]) if f else None
    tb = trig_busy(x["mint"], x["slot"], x["wallet"]) if x["slot"] else None
    qs.append(dict(run=x["run"], period=x["period"], est=x["est"], paper=x["paper"], fill_quiet=lab, trig=tb))
def agg_q(sel):
    return dict(n=len(sel), est=sm(x["est"] for x in sel if x["est"] is not None), paper=sm(x["paper"] for x in sel if x["paper"] is not None))
OUT["q3_quiet_skips"] = {}
for per in ("ALL", "DEV", "VAL", "HOLD"):
    sel = [x for x in qs if per == "ALL" or x["period"] == per]
    OUT["q3_quiet_skips"][per] = dict(all=agg_q(sel), shadow_filled=agg_q([x for x in sel if x["est"] is not None]),
                                      filled_raw_cov=agg_q([x for x in sel if x["fill_quiet"] is not None]),
                                      filled_NOT_quiet=agg_q([x for x in sel if x["fill_quiet"] is False]), filled_quiet=agg_q([x for x in sel if x["fill_quiet"] is True]),
                                      trig_cov=sum(1 for x in sel if x["trig"]), trig_ge1_buyer=sum(1 for x in sel if x["trig"] and x["trig"]["buyers"] >= 1),
                                      trig_ge2_buyers=sum(1 for x in sel if x["trig"] and x["trig"]["buyers"] >= 2))

# ---------------- Q4: QUIET stop. T2 5:2 from audit.py; re-arm 6:2 by a raw-recording proxy replay, calibrated on live re-arm fills
K_CURVE = 30e9 * 1073e12        # pump: virtual sol x virtual tokens
V0 = 73e12                      # vtok = curve token balance + 73e12
FR = 0.0125                     # pump fee + creator fee (the live fills' fr)
COST = 0.0002 + 0.00001         # tip + fees per trip (SOL), live
def vt(c): return c + V0
def proxy(mint, start, end, holders_end_check, size, drop=0.12):
    """first trade after slot `start` (exclusive) up to `end` whose post price <= (1-drop) x the previous slot's last post price;
    we buy right after it (same slot), sell at the end of slot fill + 2 (others' net token flow applied to our shifted curve)."""
    rows = [r for r in ROWS.get(mint, []) if not r[5] and r[6] is not None and r[7] is not None and start < r[0] <= end + 2 and not is_us(r[2])]
    if not rows: return None
    last_post = {}
    for r in ROWS.get(mint, []):
        if not r[5] and r[7] is not None and r[0] <= start: last_post[0] = r[7]
    ref_c = last_post.get(0); cur_slot = None; slot_ref = ref_c
    for j, r in enumerate(rows):
        if r[0] > end: break
        if r[0] != cur_slot:
            cur_slot = r[0]; slot_ref = ref_c
        ref_c = r[7]
        if slot_ref is None: continue
        p_ref = 1 / vt(slot_ref) ** 2; p_post = 1 / vt(r[7]) ** 2
        if r[3] < 0 and p_post <= (1 - drop) * p_ref:
            # fill after r: buy on the curve after r
            vtok = vt(r[7]); vsol = K_CURVE / vtok
            sin = size * 1e9 * (1 - FR); tok = vtok - K_CURVE / (vsol + sin)
            ex = [q for q in rows if q[0] <= r[0] + 2 and (q[0], q[1]) > (r[0], r[1])]
            c_e = ex[-1][7] if ex else r[7]
            vtok2 = vt(r[7]) - tok + (c_e - r[7])
            if vtok2 <= 0: return None
            vsol2 = K_CURVE / vtok2
            out = (vsol2 - K_CURVE / (vtok2 + tok)) * (1 - FR) / 1e9
            pnl = out - size - COST
            return None if abs(pnl) > 1.0 else dict(slot=r[0], pnl=pnl)      # |P&L| > 1 SOL on a 0.65 SOL trip = a bad curve row
    return None
pairs, stopped, nofill = [], [], []
for run in RUNS:
    S = EX[run]
    for k, a in S["larm"].items():
        if a.get("kind") != "rearm" or not a.get("dump"): continue
        d = S["ldis"].get(k) or {}
        arm_slot = a.get("arm_slot") or a["dump"]["slot"] + 3; en = a.get("en_slot") or a["dump"]["slot"] + 23
        if not covered(arm_slot - 2, en + 25): continue
        size = (a.get("spend") or 650000000) / 1e9
        if d.get("filled"):
            real = sum(p["pnl"] for p in POS if p["run"] == run and p["seg"] == k[0] and p["w"] == k[1])
            pr = proxy(a["mint"], arm_slot - 1, en, None, size)
            t = (a.get("dump") or {}).get("t")
            pairs.append(dict(run=run, real=real, proxy=(pr or {}).get("pnl"), period=("HOLD" if run >= "r43" else ("VAL" if run == "r42" and t and t >= CUT else "DEV"))))
        elif d.get("why") in ("expired", "whale_dump", "no_holder"):
            # windows that ran to their end without a live fill: how often does the proxy fill anyway (its false-fill rate)
            pr = proxy(a["mint"], arm_slot - 1, en, None, size)
            nofill.append(dict(run=run, proxy=(pr or {}).get("pnl"), why=d.get("why")))
        elif d.get("why") == "quiet":
            stop_slot = d.get("slot") or arm_slot + 6
            pr = proxy(a["mint"], stop_slot - 1, en, None, size)
            t = (a.get("dump") or {}).get("t")
            per = "HOLD" if run >= "r43" else ("VAL" if run == "r42" and t and t >= CUT else "DEV")
            stopped.append(dict(run=run, proxy=(pr or {}).get("pnl"), t=t, period=per))
pp = [x for x in pairs if x["proxy"] is not None]
gapr = sum(x["real"] - x["proxy"] for x in pp) / len(pp) if pp else 0.0
OUT["q4_rearm_stop"] = dict(live_filled_windows_covered=len(pairs), proxy_also_filled=len(pp), proxy_sum=sum(x["proxy"] for x in pp), real_sum_same=sum(x["real"] for x in pp),
                            real_sum_all=sum(x["real"] for x in pairs), gap_msol=gapr * 1000,
                            nofill_windows=len(nofill), nofill_proxy_fills=sum(1 for x in nofill if x["proxy"] is not None),
                            nofill_proxy_fills_by_end={w: [sum(1 for x in nofill if x["why"] == w), sum(1 for x in nofill if x["why"] == w and x["proxy"] is not None)] for w in ("expired", "whale_dump", "no_holder")},
                            pairs_sign_agree=sum(1 for x in pp if (x["proxy"] > 0) == (x["real"] > 0)) / len(pp) if pp else 0,
                            stopped_covered=len(stopped), stopped_would_fill=sum(1 for x in stopped if x["proxy"] is not None),
                            stopped_proxy=sm(x["proxy"] for x in stopped if x["proxy"] is not None),
                            stopped_est=sm(x["proxy"] + gapr for x in stopped if x["proxy"] is not None),
                            stopped_est_by_period={per: sm(x["proxy"] + gapr for x in stopped if x["proxy"] is not None and x["period"] == per) for per in ("DEV", "VAL", "HOLD")},
                            pairs_by_period={per: dict(n=sum(1 for x in pp if x["period"] == per), proxy=sum(x["proxy"] for x in pp if x["period"] == per), real=sum(x["real"] for x in pp if x["period"] == per)) for per in ("DEV", "VAL", "HOLD")},
                            by_run={run: dict(n=sum(1 for x in stopped if x["run"] == run), fills=sum(1 for x in stopped if x["run"] == run and x["proxy"] is not None),
                                              est=sum(x["proxy"] + gapr for x in stopped if x["run"] == run and x["proxy"] is not None)) for run in RUNS})
# the T2 stop from audit.py, all runs
OUT["q4_t2_stop"] = {run: {k: TAB[run]["rows"][k]["est"] for k in ("stop:quiet_t2", "stop:quiet_t2_shadow_all")} | {"trig": TAB[run]["rows"]["stop:quiet_t2"]["trig"]} for run in RUNS}

pickle.dump(dict(POS=POS, OUT=OUT, q3=q3, qs=qs, pairs=pairs, stopped=stopped), open(f"{A}/quiet.pkl", "wb"))
json.dump(OUT, open(f"{A}/quiet.json", "w"), indent=1, default=str)
print(json.dumps(OUT, indent=1, default=str)[:20000])
