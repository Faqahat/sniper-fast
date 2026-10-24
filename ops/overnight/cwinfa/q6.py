#!/usr/bin/env python3
# READ-ONLY, offline: copyability of CWiNFA for us (question 6) on the replay table (replay_all.json).
#  (a) ORACLE: the launches it attempted (filled or failed), traded our way at our landing with the 1% guard.
#  (b) WALK-FORWARD LIST: a deployer is listed when CWiNFA attempted >= k of its earlier launches and >= rate of them;
#      quality gate: skip deployers whose own simulated guarded fills (our eos05, known 60 s after each launch) average < 0
#      after >= 3 fills (the S4G gate). R1 launches feed the history (proxy placement); only R2 is traded/evaluated.
#  (c) its pattern on our entries: 1.0 SOL, sell ~1 s (or 7 slots), its costs, vs our 0.5 SOL end-of-next-slot sell.
import os, sys, json, collections, statistics
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
L = rp.load_launches(); R = json.load(open(os.path.join(HERE, "replay_all.json"))); C = json.load(open(os.path.join(HERE, "coll_cw.json")))
ATT = {m for m, v in C.items() if v.get("buy") or v.get("failed")}
FILL = {m for m, v in C.items() if v.get("buy")}
R2 = sorted([m for m, r in R.items() if r["run"] == "R2"], key=lambda m: R[m]["bt"])
FAILC = -0.005
def tally(ms, Lm, key="eos05", guard=True):
    v = []
    for m in ms:
        o = R[m].get(str(Lm))
        if not o: continue
        if guard: x = o.get(key) if o["ok"] else FAILC
        else: x = o.get("ng_" + key)
        if x is None: continue
        v.append((R[m]["bt"], x, o["ok"] or not guard))
    if not v: return dict(n=0, tot=0, fills=0, h1=0, h2=0)
    t0, t1 = v[0][0], v[-1][0]; mid = t0 + (t1 - t0) / 2
    tot = sum(x for _, x, _ in v); a = sum(x for t, x, _ in v if t < mid)
    f = [x for _, x, ok in v if ok]
    return dict(n=len(v), tot=round(tot, 3), fills=len(f), h1=round(a, 3), h2=round(tot - a, 3), per_fill=round(statistics.mean(f), 4) if f else None,
                win=round(sum(1 for x in f if x > 0) / len(f), 3) if f else None)
def fmt(d): return f"{d['tot']:+7.2f} SOL ({d['h1']:+.2f}/{d['h2']:+.2f}) fills {d['fills']}/{d['n']}" + (f", per fill {d['per_fill']:+.4f}, win {d['win']:.0%}" if d.get("per_fill") is not None else "")
out = {}
# ---------------- (a) oracle
A = [m for m in R2 if m in ATT]; AF = [m for m in R2 if m in FILL]
print(f"R2 launches with our timeline: {len(R2)}; attempted by CWiNFA: {len(A)} (filled {len(AF)})")
for Lm in (45, 75):
    for key in ("eos05", "h1_05", "cw10", "cw10_7", "eos10c", "eos05c"):
        d = tally(A, Lm, key); out[f"a_{Lm}_{key}"] = d
        print(f"(a) oracle picks L{Lm} {key:7} guard: {fmt(d)}")
    for key in ("eos05", "cw10"):
        d = tally(A, Lm, key, guard=False); out[f"a_{Lm}_{key}_noguard"] = d
        print(f"(a) oracle picks L{Lm} {key:7} NO guard: {fmt(d)}")
base = {}
for Lm in (45, 75):
    d = tally(R2, Lm, "eos05"); base[Lm] = d; out[f"all_{Lm}"] = d
    print(f"reference: ALL R2 launches L{Lm} eos05 guard: {fmt(d)}")
    bund = [m for m in R2 if R[m]["dev"] >= 1 and R[m]["glued"] >= 1]
    d = tally(bund, Lm, "eos05"); out[f"bund_{Lm}"] = d
    print(f"reference: R2 bundled (dev>=1 SOL, glued>=1) L{Lm} eos05 guard: {fmt(d)}")
# ---------------- (b) walk-forward
def walk(Lm, k=2, rate=0.10, gate=True, kmin=3, thr=0.0, key="eos05", src=ATT):
    ev = sorted((c["bt"], m) for m, c in L.items() if c.get("bt"))
    natt = collections.Counter(); nl = collections.Counter(); hist = collections.defaultdict(list); pend = []; picks = []
    for bt, m in ev:
        while pend and pend[0][0] <= bt:
            _, d, v = pend.pop(0); hist[d].append(v)
        d = L[m]["user"]; r = R.get(m)
        listed = natt[d] >= k and (nl[d] == 0 or natt[d] / nl[d] >= rate)
        gok = not (gate and len(hist[d]) >= kmin and statistics.mean(hist[d]) < thr)
        if r and r["run"] == "R2" and str(Lm) in r and listed and gok: picks.append(m)
        if r and str(Lm) in r and r[str(Lm)]["ok"] and r[str(Lm)].get("eos05") is not None:
            pend.append((bt + 60, d, r[str(Lm)]["eos05"])); pend.sort()
        nl[d] += 1
        if m in src: natt[d] += 1
    return picks
for Lm in (45, 75):
    for name, kw in (("list k>=2 rate>=10%, no gate", dict(gate=False)), ("list k>=2 rate>=10% + gate (S4G rule)", dict()),
                     ("list k>=1 + gate", dict(k=1)), ("list k>=3 rate>=20% + gate", dict(k=3, rate=0.2)), ("list k>=2 + gate thr +0.01", dict(thr=0.01))):
        P = walk(Lm, **kw)
        for key in ("eos05", "cw10", "h1_05", "eos10c"):
            d = tally(P, Lm, key); out[f"b_{Lm}_{name}_{key}"] = d
            print(f"(b) L{Lm} {name:42} {key:6}: {fmt(d)}")
json.dump(out, open(os.path.join(HERE, "q6.json"), "w"), indent=1)
# ---------------- (a') the same picks with CWiNFA's own trades removed from the path (does our profit need its buy?)
NC = json.load(open(os.path.join(HERE, "replay_nocw.json")))
def tally_nc(ms, Lm, key):
    v = []
    for m in ms:
        o = R[m].get(str(Lm))
        if not o: continue
        if not o["ok"]: v.append(FAILC); continue
        n = NC.get(m, {}).get(str(Lm))
        if n and n.get(key) is not None: v.append(n[key])
    f = [x for x in v if x != FAILC]
    return dict(n=len(v), tot=round(sum(v), 3), fills=len(f), per_fill=round(statistics.mean(f), 4) if f else None)
for Lm in (45, 75):
    cwa = [NC[m][str(Lm)]["cw_after"] for m in A if str(Lm) in NC.get(m, {})]
    for key in ("eos05", "cw10"):
        d = tally_nc(A, Lm, key); out[f"a_nocw_{Lm}_{key}"] = d
        print(f"(a') oracle picks L{Lm} {key:6} WITHOUT its own trades: {d['tot']:+.2f} SOL fills {d['fills']}/{d['n']} per fill {d['per_fill']}")
    print(f"    guard fills where CWiNFA's buy lands after ours: {sum(cwa)}/{len(cwa)}")
    P = walk(Lm)
    for key in ("eos05", "cw10"):
        d = tally_nc(P, Lm, key); out[f"b_nocw_{Lm}_{key}"] = d
        print(f"(b') walk-forward list+gate L{Lm} {key:6} WITHOUT its own trades: {d['tot']:+.2f} SOL fills {d['fills']}/{d['n']} per fill {d['per_fill']}")
json.dump(out, open(os.path.join(HERE, "q6.json"), "w"), indent=1)
