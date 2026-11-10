#!/usr/bin/env python3
"""VERIFY step 8: (a) is the ctx-limit effect the holder condition or just 'shallow fills'? (b) the r37 skipped fills of nbuyers50;
(c) COMBINED rules on all runs (skip sets, overlaps); (d) r38: the six losses vs each rule, and the lock path with the rules on."""
import pickle, collections, datetime as dt, json
OUT = "/home/it/sniper-data/prevent/verify"
T = pickle.load(open(f"{OUT}/tables.pkl", "rb")); F = pickle.load(open(f"{OUT}/feats.pkl", "rb"))
PKT = dt.timezone(dt.timedelta(hours=5))
def pk(t): return dt.datetime.fromtimestamp(t, PKT).strftime("%H:%M:%S")
R20 = ["F21", "F22", "F23", "F24", "F26", "F27", "F28", "A16", "A17", "A19", "A20", "A24", "A25", "A26", "A27", "A34", "A35", "A36", "A37", "A38"]
tw = {(x["run"], x["w"]): x for x in T["trades"]}
WS = [w for w in T["wins"] if w["run"] in R20]
for w in WS:
    x = tw.get((w["run"], w["w"])); w["tr"] = x; w["f"] = F.get((w["run"], w["w"]), {})
    w["v"] = -w["wfee"] + ((x["s"] if x["kind"] == "t2" else x["unit"]) if x else 0.0)
    w["vr"] = -w["wfee"] + (x["unit"] if x else 0.0)
lines = []; P = lines.append
# (a) depth split for T2 fills
P("== (a) T2 fills by depth band and 'another wallet >= 6% at signing' (20 runs; scaled SOL; n / sum / mean mSOL)")
fills = [w for w in WS if w["tr"] and w["kind"] == "t2" and w["f"].get("depth") is not None]
for lo, hi in ((0.0, 0.12), (0.12, 0.15), (0.15, 0.18), (0.18, 0.25), (0.25, 1.0)):
    for h in (True, False):
        xs = [w["v"] + w["wfee"] for w in fills if lo <= w["f"]["depth"] < hi and bool(w["f"].get("oth6_sign")) == h]
        if xs: P(f"   depth {lo:.2f}-{hi:.2f} other6={h!s:5s}: n {len(xs):4d} sum {sum(xs):+7.3f} mean {1000*sum(xs)/len(xs):+6.1f}")
for nm, sel in (("PICK", lambda r: r not in ("A37", "A38")), ("r37", lambda r: r == "A37"), ("r38", lambda r: r == "A38")):
    a = [w for w in fills if sel(w["run"]) and w["f"]["depth"] < 0.15]
    P(f"   {nm}: remove ALL depth<15% T2 fills (plain limit 0.85): {-sum(w['v'] + w['wfee'] for w in a):+.3f} ({len(a)} fills); only with other6: {-sum(w['v'] + w['wfee'] for w in a if w['f'].get('oth6_sign')):+.3f}; only without: {-sum(w['v'] + w['wfee'] for w in a if not w['f'].get('oth6_sign')):+.3f}")
# (b) r37 / r38 fills skipped by nbuyers50
P("\n== (b) fills skipped by nbuyers50<=1 in r37 / r38 (real SOL)")
for w in WS:
    if w["run"] in ("A37", "A38") and w["tr"] and w["kind"] == "t2" and w["f"].get("ok") and w["f"]["nbuyers50"] <= 1:
        P(f"   {w['run']} {pk(w['t'])} {w['mint'][:8]} real {w['vr']:+.4f} age {w['age']} whale {w['pct']:.1f}% nbuy50 {w['f']['nbuyers50']}")
# (c) combined
def gcr_mask(rows, m_=2, S_=0.05):
    rows = sorted(rows, key=lambda w: w["t"]); ev = collections.defaultdict(list)
    for w in rows:
        if w["tr"] and w["f"].get("ok") and w["f"].get("creator") and w["f"]["cre_pct"] >= 3:
            ev[w["f"]["creator"]].append((w["tr"]["t_sell"] + 2.0, w["v"] + w["wfee"]))
    out = {}
    for w in rows:
        f = w["f"]; s = False
        if f.get("ok") and f.get("creator") and f["cre_pct"] >= 3:
            past = [v for t, v in ev[f["creator"]] if t < w["t"]]; s = len(past) >= m_ and sum(past) <= -S_
        out[(w["run"], w["w"])] = s
    return out
G = gcr_mask(WS)
def rules(w):
    f = w["f"]; r = set()
    if w["kind"] == "t2" and f.get("ok") and f["nbuyers50"] <= 1: r.add("NB")
    if w["kind"] == "t2" and w["tr"] and f.get("oth6_sign") and f.get("depth") is not None and f["depth"] < 0.15: r.add("CTX")
    if G.get((w["run"], w["w"])): r.add("GCR")
    return r
P("\n== (c) COMBINED (nbuyers50 skip + ctx limit direct + G-cr m2 S0.05); scaled SOL; window-level, overlaps counted once")
P(f"{'run':4s} {'NB':>7s} {'CTX':>7s} {'GCR':>7s} {'union':>7s} | fills hit NB/CTX/GCR, in 2+ rules")
tot = collections.Counter(); per_union = {}
for run in R20:
    rs = [w for w in WS if w["run"] == run]
    s = collections.Counter(); hit = collections.Counter(); multi = 0
    for w in rs:
        r = rules(w)
        for k in r:
            # CTX removes only the fill (failed-try fees stay); NB / GCR skip the window (fill + fees)
            s[k] += -(w["v"] + w["wfee"]) if k == "CTX" else -w["v"]
            if w["tr"]: hit[k] += 1
        if r:
            s["U"] += -w["v"] if (r & {"NB", "GCR"}) else -(w["v"] + w["wfee"])
            if w["tr"] and len(r) >= 2: multi += 1
    per_union[run] = s["U"]
    for k in ("NB", "CTX", "GCR", "U"): tot[(k, "PICK" if run not in ("A37", "A38") else run)] += s[k]
    P(f"{run:4s} {s['NB']:+7.3f} {s['CTX']:+7.3f} {s['GCR']:+7.3f} {s['U']:+7.3f} | {hit['NB']}/{hit['CTX']}/{hit['GCR']}, {multi}")
for grp in ("PICK", "A37", "A38"):
    P(f"  {grp}: NB {tot[('NB', grp)]:+.3f} CTX {tot[('CTX', grp)]:+.3f} GCR {tot[('GCR', grp)]:+.3f} union {tot[('U', grp)]:+.3f}")
P(f"  PICK runs helped/hurt by the union: +{sum(1 for r in R20[:-2] if per_union[r] > 1e-9)}/-{sum(1 for r in R20[:-2] if per_union[r] < -1e-9)}")
# (d) r38 six losses + lock path
P("\n== (d) r38: the six big losses (real SOL) and which rule catches them")
six = {"9wU2Ppxt": "rearm", "HDnCHWDi": "t2", "7fNXHMXV": None, "27Jgn5V6": "t2", "9hGUm3RK": "rearm", "AJvBnYDt": "rearm"}
for w in sorted([w for w in WS if w["run"] == "A38" and w["tr"]], key=lambda w: w["t"]):
    if w["mint"][:8] in six:
        f = w["f"]
        P(f"   {pk(w['tr']['t'])} {w['mint'][:8]} {w['kind']:5s} {w['vr']:+.4f} | NB {'skip' if 'NB' in rules(w) else '-'} (nbuy50 {f.get('nbuyers50')}) | CTX {'remove' if 'CTX' in rules(w) else '-'} (other6 {f.get('oth6_sign')}, depth {f.get('depth', 0):.3f}) | GCR {'skip' if 'GCR' in rules(w) else '-'} (creator {(f.get('creator') or '?')[:8]} {f.get('cre_pct', 0):.1f}%)")
def path(run, active, G_=0.65):
    ev = []
    for w in WS:
        if w["run"] != run: continue
        r = rules(w) & active
        if r & {"NB", "GCR"}: continue
        if w["wfee"]: ev.append((w["t"], -w["wfee"]))
        if w["tr"] and not (r & {"CTX"}): ev.append((w["tr"]["t_sell"] + 4.0, w["tr"]["unit"]))
    ev.sort(); cum = 0.0; peak = 0.0; trip = None; low = (9, None)
    for t, v in ev:
        cum += v; peak = max(peak, cum)
        fl = max(-0.5, peak - max(G_, 0.3 * peak))
        if cum - fl < low[0]: low = (cum - fl, t)
        if trip is None and cum < fl: trip = (t, cum, peak)
    return cum, peak, trip, low
for act in (set(), {"NB"}, {"CTX"}, {"GCR"}, {"NB", "CTX", "GCR"}):
    cum, peak, trip, low = path("A38", act)
    P(f"   r38 real path with {sorted(act) or 'no rule'}: end (03:38) {cum:+.3f}, peak {peak:+.3f}, 0.65 lock {'TRIPS at ' + pk(trip[0]) + f' P&L {trip[1]:+.3f}' if trip else 'does NOT trip'}; closest approach to the floor {low[0]:+.3f} at {pk(low[1]) if low[1] else '-'}")
open(f"{OUT}/combined.txt", "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
