#!/usr/bin/env python3
# READ-ONLY, offline. Same exit-policy grid as combo.py on the 73 recorded rule #2 launches (exit_sim.py data: exact block
# order for S..S+2, tapes to ~S+60), entry = 0.5 SOL at our MEASURED landing (Jito-client 75 ms, Harmonic 80, others as the
# model), 15% cap (refused = -0.011). Search on these 73, then test the best policy on the 17 real-spot buys (combo.py).
import sys, os, json, itertools
HERE = os.path.dirname(os.path.abspath(__file__)); C = os.path.join(HERE, "..", "research", "competitors")
SP = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad"
os.environ["SIZE"] = "0.5"; os.environ["SEL"] = "r2"; os.environ["T_OVR"] = "jito=75,harmonic=80"
sys.argv = ["exit_sim.py", os.path.join(C, "..", "filters3_rows.json"), "/home/moiz/sniper-data/research/competitors/tapes", f"{SP}/filt/launches2.json",
            f"{SP}/f3/paper/launches_ready.json", "/home/moiz/sniper-data/research/rec", f"{SP}/f2/paper/rec", f"{SP}/f3/paper/rec"]
src = open(os.path.join(C, "exit_sim.py")).read()
exec(src[:src.index("def simulate(")], globals())                     # loaders + pre/clean/chain_order/extend/entry, unchanged
CRE = {}
for f in (sys.argv[3], sys.argv[4]):
    for l in json.load(open(f))["launches"]: CRE.setdefault(l["mint"], l.get("creator"))
X, COST, OVER, L = 493827160, 516585000, 91160, 1e9
R2 = lambda r: r["tipc"] == "lunar" and 3 <= r["gsol"] <= 5 and r["create_ms"] is not None and r["create_ms"] <= 150
TOK = []; skipped = 0
for r in rows:
    if not R2(r): continue
    rec = REC.get(r["mint"]); outs = OUTS.get(r["mint"])
    tp = os.path.join(TD, r["mint"] + ".tape.json")
    if not rec or outs is None or not os.path.exists(tp): skipped += 1; continue
    tape = json.load(open(tp))
    rec = clean(dict(rec, create_ms=r["create_ms"], slot_ms=rec.get("slot_ms") or 217.0))
    tr, hz = extend(rec, tape)
    e, fee, seq = entry(rec, tr, outs, T_OVR.get(r["cls"], r["T"] + T_ADD))
    S = rec["S"]; dev = CRE.get(r["mint"]) or (tr[0]["user"] if tr else None)
    if e is None:
        TOK.append(dict(grp=r["grp"], name=r["mint"][:8], refused=True, path=[dict(d=0, pnl=-0.011, buy=None, who="us")])); continue
    V, Tk, q, _ = e
    fb = (tr[0].get("fbps") or 95); cb = (tr[0].get("cbps") or 30)
    def pnl(V, Tk):
        x = int(V * q // (Tk + q)); return (x - (-(-x * fb // 10000)) - (-(-x * cb // 10000)) - OVER - COST) / L
    seqids = {id(t) for t in seq}
    early = {t["user"] for t in tr if id(t) not in seqids and t["buy"]}
    path = [dict(d=0, pnl=pnl(V, Tk), buy=None, who="us")]
    for t in seq:
        if t["buy"]: dd = Tk * t["sol"] // (V + t["sol"]); V += t["sol"]; Tk -= dd
        else: so = V * t["tok"] // (Tk + t["tok"]); V -= so; Tk += t["tok"]
        who = "dev" if t["user"] == dev else ("early" if t["user"] in early else "other")
        path.append(dict(d=t["slot"] - S, pnl=pnl(V, Tk), buy=t["buy"], who=who))
    TOK.append(dict(grp=r["grp"], name=r["mint"][:8], refused=False, path=path))
print(f"launches: {len(TOK)} (refused by the 15% cap at real speed: {sum(t['refused'] for t in TOK)}; skipped without tape {skipped})")


def run(t, tp, sl, ts, ev_exit, trail):
    P = t["path"]
    if t.get("refused"): return P[0]["pnl"]
    peak = P[0]["pnl"]; prev = P[0]
    for p in P[1:]:
        if p["d"] > ts: return prev["pnl"]
        v = p["pnl"]; peak = max(peak, v)
        if ev_exit == "dev" and p["who"] == "dev" and p["buy"] is False: return v
        if ev_exit == "dev/early" and p["who"] in ("dev", "early") and p["buy"] is False: return v
        if ev_exit == "any sell" and p["buy"] is False: return v
        if tp is not None and v >= tp * 0.5166: return v
        if sl is not None and v <= -sl * 0.5166: return v
        if trail and peak >= trail[0] * 0.5166 and v <= peak - trail[1] * 0.5166: return v
        prev = p
    return prev["pnl"]
POL = list(itertools.product([0.05, 0.10, 0.15, 0.20, 0.30, 0.50, None], [0.08, 0.12, 0.15, 0.20, 0.30, None], [3, 5, 10, 20, 30, 50],
                             [None, "dev", "dev/early", "any sell"], [None, (0.05, 0.05), (0.10, 0.05), (0.10, 0.10), (0.20, 0.10)]))
name = lambda p: (f"TP {p[0]:.0%}" if p[0] else "no TP") + " / " + (f"SL {p[1]:.0%}" if p[1] else "no SL") + f" / time S+{p[2]}" + (f" / exit on {p[3]} sell" if p[3] else "") + (f" / trail {p[4][0]:.0%}-{p[4][1]:.0%}" if p[4] else "")
M = [[run(t, *p) for t in TOK] for p in POL]
ids = range(len(TOK)); A = [j for j in ids if TOK[j]["grp"] == "A"]; H = [j for j in ids if TOK[j]["grp"] != "A"]
tot = lambda i, s: sum(M[i][j] for j in s)
base = POL.index((None, None, 3, None, None))
print(f"{len(POL)} policies (tapes reach ~S+60, so time stops <= S+50). baseline sell at S+3: all {tot(base, ids):+.3f} | A {tot(base, A):+.3f} | B-E {tot(base, H):+.3f}")
print("IN-SAMPLE best on all 73 (optimistic):")
for i in sorted(range(len(POL)), key=lambda i: -tot(i, ids))[:6]:
    print(f"   all {tot(i, ids):+.3f} (A {tot(i, A):+.3f}, B-E {tot(i, H):+.3f})  {name(POL[i])}")
bi = max(range(len(POL)), key=lambda i: tot(i, A))
print(f"PICK ON A ({len(A)}, the period rule #2 was chosen on) -> TEST ON B-E ({len(H)}): '{name(POL[bi])}' A {tot(bi, A):+.3f} -> B-E {tot(bi, H):+.3f} (baseline B-E {tot(base, H):+.3f})")
bh = max(range(len(POL)), key=lambda i: tot(i, H))
print(f"PICK ON B-E -> TEST ON A: '{name(POL[bh])}' B-E {tot(bh, H):+.3f} -> A {tot(bh, A):+.3f}")
pos = sum(1 for i in range(len(POL)) if tot(i, ids) > 0)
print(f"policies net positive on all 73: {pos} of {len(POL)}")
# the best policy on the 73, applied to the 17 real-spot buys
sys.argv = ["x"]; csrc = open(os.path.join(HERE, "combo.py")).read().split("# ---------- facts ----------")[0]
ns = {"__file__": os.path.join(HERE, "combo.py"), "__name__": "c"}; exec(csrc, ns)
T17 = ns["TOK"]
b73 = max(range(len(POL)), key=lambda i: tot(i, ids)); p = POL[b73]
r17 = [run(t, *p) for t in T17]
print(f"BEST ON THE 73 -> on the 17 real-spot buys: '{name(p)}' = {sum(r17):+.3f} SOL ({sum(v > 0 for v in r17)} of 17 positive)")
