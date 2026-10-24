#!/usr/bin/env python3
# Walk-forward strategy experiments on the precomputed outcome table (allres.json). Every decision uses only data from
# before the launch: deployer launch counts, attempts by the copied wallets, and our own simulated guarded-flip results
# on that deployer (counted 60 s after each launch, when the result is known).
import sys, os, json, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
L = rp.load_launches(); R = json.load(open("allres.json"))
ATT = collections.defaultdict(dict)
for f, keys in (("attempts.json", None), ("attempts_ahw.json", None), ("attempts_top8.json", None), ("attempts_fifaw.json", None)):
    if os.path.exists(f):
        for m, v in json.load(open(f)).items(): ATT[m].update(v)
DC = "/home/moiz/sniper/ops/snipers/devcheck"; LED = []
for w in ("9Sh2fd", "DGmspi"):
    for f in (f"devs_{w}.json", f"att_{w}.json"):
        p = os.path.join(DC, f)
        if os.path.exists(p):
            for m, v in json.load(open(p)).items():
                if v.get("signer") and v.get("bt") and m not in L: LED.append((v["bt"], v["signer"], w))
def run(strategy, Lm, name, verbose=True):
    ev = sorted([(bt, 0, d, w) for bt, d, w in LED] + [(c["bt"], 1, m, None) for m, c in L.items() if c.get("bt")])
    att = collections.defaultdict(collections.Counter); nl = collections.Counter(); hist = collections.defaultdict(list); pend = []
    out = collections.defaultdict(list)
    for bt, kind, x, w in ev:
        while pend and pend[0][0] <= bt:
            _, d, v = pend.pop(0); hist[d].append(v)
        if kind == 0: att[w][x] += 1; continue
        m = x; c = L[m]; d = c["user"]; r = R.get(m)
        if r and str(Lm) in r:
            st = dict(att={k: att[k][d] for k in att}, n=nl[d], hist=hist[d], r=r)
            B = strategy(st)
            if B:
                o = r[str(Lm)]
                v = (o.get(str(B)) if o["ok"] else -0.005)
                if v is not None: out[r["run"]].append((bt, v, B))
            if r[str(Lm)]["ok"] and r[str(Lm)].get("0.5") is not None:
                pend.append((bt + 60, d, r[str(Lm)]["0.5"])); pend.sort()
        nl[d] += 1
        for k in ATT.get(m, {}): att[k][d] += 1
    res = {}
    for run_ in ("R1", "R2"):
        v = out[run_]
        if not v: res[run_] = None; continue
        tot = sum(x for _, x, _ in v); t0, t1 = v[0][0], v[-1][0]; mid = t0 + (t1 - t0) / 2; a = sum(x for t, x, _ in v if t < mid)
        res[run_] = dict(tot=tot, n=len(v), fills=sum(1 for _, x, _ in v if x != -0.005), h1=a, h2=tot - a, sol_in=sum(B for _, x, B in v if x != -0.005))
    if verbose:
        print(f"{name:58} L{Lm}: " + " | ".join(f"{k} {x['tot']:+6.2f} ({x['h1']:+.1f}/{x['h2']:+.1f}) fills {x['fills']}/{x['n']}" if x else f"{k} -" for k, x in res.items()))
    return res
def listed(st, srcs, k=2, rate=0.10):
    a = sum(st["att"].get(s, 0) for s in srcs); n = st["n"]
    return a >= k and (n == 0 or a / n >= rate)
def gate_ok(st, kmin=3, thr=0.0):
    h = st["hist"]; return not (len(h) >= kmin and statistics.mean(h) < thr)
S9 = ("9Sh2fd", "DGmspi"); MULTI = ("9Sh2fd", "DGmspi", "AHwJSn", "dKMjeG", "CWiNFA", "D24ipY", "FiFawH")
STRATS = {
    "S4 (9Sh2fd+DGmspi list) 0.5": lambda st: 0.5 if listed(st, S9) else 0,
    "S4 + gate (drop deployers whose own fills avg < 0)": lambda st: 0.5 if listed(st, S9) and gate_ok(st) else 0,
    "S4 + size 1.0 when own history >= 3 fills avg >= +0.02": lambda st: (1.0 if len(st["hist"]) >= 3 and statistics.mean(st["hist"]) >= 0.02 else 0.5) if listed(st, S9) else 0,
    "S4 + gate + size": lambda st: (1.0 if len(st["hist"]) >= 3 and statistics.mean(st["hist"]) >= 0.02 else 0.5) if listed(st, S9) and gate_ok(st) else 0,
    "MULTI list (7 wallets) 0.5": lambda st: 0.5 if listed(st, MULTI) else 0,
    "MULTI list + gate": lambda st: 0.5 if listed(st, MULTI) and gate_ok(st) else 0,
    "MULTI list + gate + size": lambda st: (1.0 if len(st["hist"]) >= 3 and statistics.mean(st["hist"]) >= 0.02 else 0.5) if listed(st, MULTI) and gate_ok(st) else 0,
    "AUTO: any deployer with >= 3 own fills avg >= +0.02 (no copying)": lambda st: 0.5 if len(st["hist"]) >= 3 and statistics.mean(st["hist"]) >= 0.02 else 0,
    "AUTO + S4": lambda st: 0.5 if (listed(st, S9) or (len(st["hist"]) >= 3 and statistics.mean(st["hist"]) >= 0.02)) else 0,
}
if __name__ == "__main__":
    for Lm in (75, 45):
        print(f"\n=== landing {Lm} ms (R2 = real place in line; R1 = pessimistic proxy) ===")
        for n, f in STRATS.items(): run(f, Lm, n)
