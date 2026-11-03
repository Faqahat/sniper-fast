#!/usr/bin/env python3
"""VERIFY step 7: score STATE nbuyers50 skip, GUARDS ctx limit 0.85 (direct), WHO G-cr creator fair-list on all live runs (own code).
Window value (scaled to 0.696, verifier fixed costs; re-arm at real 0.65): v = -failed-try fees + trade value if filled.
Skip saving = -sum(v of skipped windows). CI = block bootstrap over (run, PKT hour) blocks, 5000 draws, 90%."""
import pickle, collections, json, random, datetime as dt, sys
OUT = "/home/moiz/sniper-data/prevent/verify"
T = pickle.load(open(f"{OUT}/tables.pkl", "rb")); F = pickle.load(open(f"{OUT}/feats.pkl", "rb"))
PKT = dt.timezone(dt.timedelta(hours=5))
R20 = ["F21", "F22", "F23", "F24", "F26", "F27", "F28", "A16", "A17", "A19", "A20", "A24", "A25", "A26", "A27", "A34", "A35", "A36", "A37", "A38"]
R26 = R20[:-2] + ["A28", "A29", "A30", "A31", "A32", "A33"] + ["A37", "A38"]
tw = {(x["run"], x["w"]): x for x in T["trades"]}
def val(w, mode="s"):
    x = tw.get((w["run"], w["w"])); v = -w["wfee"]
    if x: v += (x["s"] if (mode == "s" and x["kind"] == "t2") else x["unit"])
    return v, x
WS = [w for w in T["wins"] if w["run"] in R26]
for w in WS:
    w["v"], w["tr"] = val(w); w["vr"], _ = val(w, "r"); w["f"] = F.get((w["run"], w["w"]), {})
    w["hour"] = (w["run"], int(w["t"] // 3600))
lines = []; P = lines.append; RES = {}

def score(name, rows, mask, pick_runs, test="A37", show_runs=None, valkey="v"):
    sk = [w for w, m in zip(rows, mask) if m]
    per = collections.defaultdict(float); nsk = collections.Counter(); nfill = collections.Counter(); nall = collections.Counter()
    for w, m in zip(rows, mask):
        nall[w["run"]] += 1
        if m: per[w["run"]] += -w[valkey]; nsk[w["run"]] += 1; nfill[w["run"]] += bool(w["tr"])
    pick = sum(per[r] for r in pick_runs); help_ = sum(1 for r in pick_runs if per[r] > 1e-9); hurt = sum(1 for r in pick_runs if per[r] < -1e-9)
    pt_rows = [w for w in sk if w["run"] in pick_runs or w["run"] == test]
    gains = sorted((-w[valkey] for w in pt_rows), reverse=True)
    pt = sum(gains); wo1 = pt - sum(gains[:1]); wo5 = pt - sum(gains[:5])
    pick_g = sorted((-w[valkey] for w in sk if w["run"] in pick_runs), reverse=True)
    lose = sum(-w[valkey] for w in pt_rows if w["tr"] and w[valkey] < 0); win = sum(w[valkey] for w in pt_rows if w["tr"] and w[valkey] > 0)
    # block bootstrap over (run, hour) of PICK+TEST
    blocks = collections.defaultdict(float)
    for w in rows:
        if w["run"] in pick_runs or w["run"] == test: blocks[w["hour"]] += 0.0
    for w in pt_rows: blocks[w["hour"]] += -w[valkey]
    bv = list(blocks.values()); rnd = random.Random(7); B = []
    for _ in range(5000): B.append(sum(bv[rnd.randrange(len(bv))] for _ in range(len(bv))))
    B.sort(); ci = (B[int(0.05 * len(B))], B[int(0.95 * len(B))])
    d = dict(pick=pick, help=help_, hurt=hurt, test=per[test], r38=per["A38"], pt=pt, wo1=wo1, wo5=wo5, pick_wo1=sum(pick_g) - sum(pick_g[:1]),
             ci=ci, lose=lose, win=win, n_skip=len(sk), n_fill_skip=sum(1 for w in sk if w["tr"]), share=len(sk) / max(1, len(rows)),
             per={r: round(per[r], 4) for r in (show_runs or [])}, nsk={r: nsk[r] for r in (show_runs or [])}, nfill={r: nfill[r] for r in (show_runs or [])})
    RES[name] = d
    P(f"{name}\n   PICK {pick:+.3f} (runs +{help_}/-{hurt}; PICK w/o1 {d['pick_wo1']:+.3f}) | TEST r37 {per[test]:+.3f} | r38 {per['A38']:+.3f} | PICK+TEST {pt:+.3f} CI90 {ci[0]:+.2f}..{ci[1]:+.2f}"
      f" w/o1 {wo1:+.3f} w/o5 {wo5:+.3f} | skipped loser SOL {lose:.2f} winner SOL {win:.2f} | windows skipped {len(sk)} ({d['share']:.1%}), fills {d['n_fill_skip']}")
    if show_runs: P("   per run: " + " ".join(f"{r}:{per[r]:+.3f}({nfill[r]}f)" for r in show_runs))
    return d

# ---------- 1. STATE: nbuyers50 <= 1 (T2) ----------
P("== STATE candidate: skip a T2 window when nbuyers50 <= 1 (whale's buy is the only buy in the last 50 slots)")
t2 = [w for w in WS if w["kind"] == "t2"]
PICK26 = [r for r in R26 if r not in ("A37", "A38")]; PICK20 = [r for r in R20 if r not in ("A37", "A38")]
m = [bool(w["f"].get("ok") and w["f"]["nbuyers50"] <= 1) for w in t2]
score("S1 nbuyers50<=1, all live T2 windows as they ran, 26 runs (scaled 0.696)", t2, m, PICK26, show_runs=R26)
score("S1r same, REAL SOL (no scaling)", t2, m, PICK26, valkey="vr")
t2b = [w for w in t2 if w["run"] in R20]; mb = [bool(w["f"].get("ok") and w["f"]["nbuyers50"] <= 1) for w in t2b]
score("S1b same, 20-run set (REGIME/GUARDS runs)", t2b, mb, PICK20)
t2c = [w for w in t2 if (w["age"] or 0) >= 2]; mc = [bool(w["f"].get("ok") and w["f"]["nbuyers50"] <= 1) for w in t2c]
score("S1c only windows with trigger age >= 2 (current min age), 26 runs", t2c, mc, PICK26)
QON = ["A28", "A31", "A32", "A33", "A34", "A35", "A36"]
t2d = [w for w in t2 if w["run"] in QON + ["A37", "A38"] and (w["age"] or 0) >= 2]; md = [bool(w["f"].get("ok") and w["f"]["nbuyers50"] <= 1) for w in t2d]
score("S1d closest to current config: QUIET-on runs (A28 A31-A36) + r37/r38, age >= 2", t2d, md, QON, show_runs=QON + ["A37", "A38"])
for k, thr in (("nbuyers50_pre", 0), ("oth50", 0), ("nbuy50", 1), ("nbuyers20", 1), ("nbuyers100", 1)):
    mm = [bool(w["f"].get("ok") and w["f"].get(k, 99) <= thr) for w in t2]
    score(f"S2 variant {k} <= {thr} (26 runs)", t2, mm, PICK26)
# lone-whale fills (WHO's lonewhale): T2 fills with nbuyers50 <= 1
lw = [w for w, mm_ in zip(t2, m) if mm_ and w["tr"] and w["run"] in R20]
P(f"   lone-whale FILLS (20 runs): n {len(lw)} real sum {sum(w['vr'] for w in lw):+.3f} scaled {sum(w['v'] for w in lw):+.3f}; big losses (< -7.2% of spend) {sum(1 for w in lw if w['tr']['pnl']/w['tr']['spend'] < -0.072)}")

# ---------- 2. GUARDS: limit 0.85 when another wallet >= 6% at signing (direct, T2 fills) ----------
P("\n== GUARDS candidate: limit 0.85 (drop 15%) when another wallet holds >= 6% at signing; DIRECT = remove T2 fills with that holder and depth < 15% (no refills)")
t2f = [w for w in t2 if w["tr"]]
def rm(w, D=0.15):
    f = w["f"]; return bool(f.get("oth6_sign") and f.get("depth") is not None and f["depth"] < D)
mg = [rm(w) for w in t2f]
P(f"   T2 fills {len(t2f)}, with sign-pos {sum(1 for w in t2f if 'oth6_sign' in w['f'])}, with other6 at signing {sum(1 for w in t2f if w['f'].get('oth6_sign'))}")
score("G1 direct, 20 runs, scaled (fills only; failed-try fees unchanged)", [w for w in t2f if w["run"] in R20], [rm(w) for w in t2f if w["run"] in R20], PICK20, show_runs=R20)
score("G1r direct, 20 runs, REAL SOL", [w for w in t2f if w["run"] in R20], [rm(w) for w in t2f if w["run"] in R20], PICK20, valkey="vr")
score("G1x direct, 26 runs", t2f, mg, PICK26)
score("G2 direct, 18% variant (20 runs)", [w for w in t2f if w["run"] in R20], [rm(w, 0.18) for w in t2f if w["run"] in R20], PICK20)
# -20% followers proxy is a replay quantity; not computable from the direct count

# ---------- 3. WHO: G-cr creator fair-list (online) ----------
P("\n== WHO candidate: G-cr creator fair-list (online): skip when creator holds >= 3% at arm AND our past fills (known by sell + 2 s) where this creator held >= 3% at arm number >= m with sum <= -S")
def gcr(rows_all, m_, S_, known_lag=2.0, scope_runs=R20):
    rows = sorted([w for w in rows_all if w["run"] in scope_runs], key=lambda w: w["t"])
    ev = collections.defaultdict(list)   # creator -> list of (t_known, value)
    for w in rows:
        if w["tr"] and w["f"].get("ok") and w["f"].get("creator") and w["f"]["cre_pct"] >= 3:
            ev[w["f"]["creator"]].append((w["tr"]["t_sell"] + known_lag, w["v"] + w["wfee"]))
    for c in ev: ev[c].sort()
    mask = []
    for w in rows:
        f = w["f"]; s = False
        if f.get("ok") and f.get("creator") and f["cre_pct"] >= 3:
            past = [v for t, v in ev[f["creator"]] if t < w["t"]]
            s = len(past) >= m_ and sum(past) <= -S_
        mask.append(s)
    return rows, mask
for (m_, S_) in ((2, 0.05), (3, 0.05), (2, 0.2)):
    rows, mask = gcr(WS, m_, S_)
    d = score(f"W1 G-cr m{m_} S{S_}, 20 runs, T2 + re-arm windows", rows, mask, PICK20, show_runs=R20)
    # contribution by creator
    by = collections.defaultdict(float)
    for w, mm_ in zip(rows, mask):
        if mm_: by[(w["f"]["creator"] or "?")[:8]] += -w["v"]
    P("   by creator: " + ", ".join(f"{c} {v:+.3f}" for c, v in sorted(by.items(), key=lambda kv: -abs(kv[1]))[:6]))
rows, mask = gcr(WS, 2, 0.05, scope_runs=R26); score("W1x G-cr m2 S0.05, 26 runs", rows, mask, PICK26)
rows, mask = gcr(WS, 2, 0.05, known_lag=60.0); score("W1L G-cr m2 S0.05, outcome usable only 60 s after the sell (20 runs)", rows, mask, PICK20)
json.dump({k: {kk: vv for kk, vv in v.items()} for k, v in RES.items()}, open(f"{OUT}/score.json", "w"), indent=1, default=str)
open(f"{OUT}/score.txt", "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
