#!/usr/bin/env python3
"""WHO step 5: score the pre-registered identity rules (PREREG.txt) ONLINE on every live window (and paper windows), per run.
A rule = skip the window at arm time (+stop: also skip a fill when the condition appears between arm and the fill slot).
Saving of a skipped window = failed-try fees - fill P&L (@0.696 scaled; raw also kept).
Out: rules.pkl (per-rule per-window skip vectors + summary), printed summary."""
import pickle, json, bisect, collections, itertools, sys, math
import numpy as np

D = "/home/moiz/sniper-data/prevent/who"
SCALE = 0.696
PICK_RUNS = ["FRA21", "FRA22", "FRA23", "FRA24", "FRA26", "FRA27", "FRA28", "AMS16", "AMS17", "AMS19", "AMS20", "AMS24", "AMS25", "AMS26", "AMS27", "AMS34", "AMS35", "AMS36"]
TEST_RUNS = ["AMS37"]
R38 = ["AMS38"]
PAPER_RUNS = ["AMS14", "AMS15", "AMS21", "AMS22", "AMS23", "FRA15", "FRA16", "FRA20", "FRA25"]
LAG = 5.0  # a fill's outcome is usable 5 s after the fill


def load():
    W = pickle.load(open(f"{D}/windows.pkl", "rb")); F = pickle.load(open(f"{D}/feats.pkl", "rb"))
    C = pickle.load(open(f"{D}/creates.pkl", "rb")); DU = pickle.load(open(f"{D}/dumps.pkl", "rb"))
    bots = json.load(open(f"{D}/bots.json"))
    return W, F, C, DU, bots


def prep(W, F):
    rows = []
    for w, f in zip(W, F):
        if "hold" not in f: continue
        if w["mode"] == "live":
            fee = (w.get("fee_fail") or 0) / 1e9
            if w.get("filled"):
                ps = w["pnl"] * SCALE / (w["spend"] / 1e9); pr = w["pnl"]
            else: ps = pr = 0.0
            val_s = ps - fee; val_r = pr - fee; filled = bool(w.get("filled"))
        else:
            x = w.get("fill_c")
            if x is None or x.get("net") is None: ps = pr = 0.0; filled = False
            else:
                pr = x["net"]; ps = x["net"] * SCALE / ((x.get("sol_in") or 543209876) / 1e9); filled = True
            val_s, val_r = ps, pr
        rows.append(dict(w=w, f=f, t=w["t_arm"], run=w["run"], mode=w["mode"], val_s=val_s, val_r=val_r, pnl_s=ps, filled=filled))
    rows.sort(key=lambda r: r["t"])
    return rows


class Online:
    """per-wallet sorted event times (outcome known at time) -> count / sums before t"""
    def __init__(self): self.ev = collections.defaultdict(list)
    def add(self, k, t, v=1.0): self.ev[k].append((t, v))
    def done(self):
        for k in self.ev: self.ev[k].sort()
        self.ts = {k: [x[0] for x in v] for k, v in self.ev.items()}
        self.cs = {k: np.cumsum([x[1] for x in v]) for k, v in self.ev.items()}
    def n(self, k, t):
        ts = self.ts.get(k)
        return 0 if ts is None else bisect.bisect_left(ts, t)
    def s(self, k, t):
        ts = self.ts.get(k)
        if ts is None: return 0.0
        i = bisect.bisect_left(ts, t)
        return float(self.cs[k][i - 1]) if i else 0.0


def main():
    W, F, C, DU, bots = load()
    R = prep(W, F)
    print("windows scored", len(R), "live", sum(r["mode"] == "live" for r in R), flush=True)
    live_fills = [r for r in R if r["mode"] == "live" and r["filled"]]
    # ---------- online stores built from our LIVE fills ----------
    # A: listing events per (X, L): wallet sold >= X SOL inside our hold on a fill with pnl@0.696 < -L
    A_ev = {}
    for X in (0.5, 1.0, 2.0):
        for L in (0.03, 0.05):
            o = Online()
            for r in live_fills:
                if r["pnl_s"] < -L:
                    for u, x in r["f"]["sellers"].items():
                        if x["sol"] >= X: o.add(u, r["w"]["fill_t"] + LAG)
            o.done(); A_ev[(X, L)] = o
    # C2: our past fills by trigger wallet; D3: by creator  (sum pnl@0.696, count)
    trig_o, trig_n, cre_o, cre_n = Online(), Online(), Online(), Online()
    for r in live_fills:
        t = r["w"]["fill_t"] + LAG
        trig_o.add(r["w"]["wallet"], t, r["pnl_s"]); trig_n.add(r["w"]["wallet"], t)
        c = r["f"].get("creator")
        if c: cre_o.add(c, t, r["pnl_s"]); cre_n.add(c, t)
    for o in (trig_o, trig_n, cre_o, cre_n): o.done()
    # ---------- market-wide stores ----------
    need = set()
    for r in R:
        need.update(u for u, p in r["f"]["hold"].items() if p >= 1)
        need.add(r["w"]["wallet"])
    du_u = DU["user"]; m = np.array([u in need for u in du_u]) & (DU["drop"] >= 0.10)
    dd = collections.defaultdict(list)
    for u, bt, mi, tok in zip(du_u[m], DU["bt"][m], DU["mint"][m], DU["tok"][m]):
        dd[u].append((int(bt), mi, tok / 1e13))  # pct of supply
    for u in dd: dd[u].sort(key=lambda z: z[0])
    ddt = {u: [z[0] for z in v] for u, v in dd.items()}
    print("dump users needed", len(dd), flush=True)

    def ndumps(u, t, mint, P, N):
        ts = ddt.get(u)
        if not ts: return 0
        a = bisect.bisect_left(ts, t - N * 3600); b = bisect.bisect_left(ts, t - 1)
        return len({z[1] for z in dd[u][a:b] if z[2] >= P and z[1] != mint})
    # creates per creator
    cre_t = collections.defaultdict(list)
    for mk, c in C.items():
        if c[0]: cre_t[c[0]].append(c[2])
    for k in cre_t: cre_t[k].sort()

    def nlaunch(c, t, N=24):
        ts = cre_t.get(c)
        if not ts: return 0
        return bisect.bisect_left(ts, t - 1) - bisect.bisect_left(ts, t - N * 3600)
    botset = None
    coh = {c if isinstance(c, str) else (c.get("wallet") or c.get("w")) for c in json.load(open("/home/moiz/sniper/ops/overnight/sel/cohort_train.json"))}
    import re
    cand = set(re.findall(r"gmgn\.ai/sol/address/([1-9A-HJ-NP-Za-km-z]{32,44})", open("/home/moiz/sniper/ops/snipers/CANDIDATES.md").read()))
    botset = coh | cand | set(bots["rivals"].values())

    # ---------- per-window precompute ----------
    for r in R:
        w, f = r["w"], r["f"]; t = r["t"]; tw = w["wallet"]; mint = w["mint"]
        hold = f["hold"]
        r["h"] = hold
        # B: per holder >= 1%: dumps counts for (P,N)
        r["Bc"] = {u: {(P, N): ndumps(u, t, mint, P, N) for P in (3, 6) for N in (6, 24)} for u, p in hold.items() if p >= 1}
        r["C1"] = ndumps(tw, t, mint, 3, 24) if tw else 0
        r["C3"] = w["kind"] == "t2" and f.get("trig_sold_before", 0) > 0.05
        cr = f.get("creator")
        r["D1"] = f.get("creator_pct", 0.0)
        r["D2"] = nlaunch(cr, t) if cr else 0
        r["D3s"] = cre_o.s(cr, t) if cr else 0.0; r["D3n"] = cre_n.n(cr, t) if cr else 0
        r["D4"] = w["kind"] == "rearm" and cr is not None and tw == cr
        s0 = f.get("s0")
        bund = [(u, p) for u, p in hold.items() if u != cr and u != tw and f["first"].get(u) is not None and f["first"][u] - s0 <= 2]
        r["E1"] = sum(p for u, p in bund); r["E2"] = sum(1 for u, p in bund if p >= 1)
        tf = f.get("trig_first")
        r["E3"] = tf is not None and any(u != tw and p >= 3 and f["first"].get(u) == tf for u, p in hold.items())
        r["Fb"] = max([p for u, p in hold.items() if u in botset] or [0.0])
        r["C2s"] = trig_o.s(tw, t); r["C2n"] = trig_n.n(tw, t)
    # ---------- rules ----------
    rules = {}
    for X, n, L, Y, stop in itertools.product((0.5, 1.0, 2.0), (1, 2), (0.03, 0.05), (0.5, 1.0, 3.0), (False, True)):
        o = A_ev[(X, L)]
        def fA(r, o=o, n=n, Y=Y, stop=stop):
            t = r["t"]
            if any(p >= Y and o.n(u, t) >= n for u, p in r["h"].items()): return True
            if stop and r["filled"] and r["mode"] == "live":
                return any(p >= Y and o.n(u, t) >= n for u, p in r["f"]["win_buyers"].items())
            return False
        rules[f"A X{X} n{n} L{L} Y{Y}{' +stop' if stop else ''}"] = ("A", fA)
    for P, K, N, Y, inc in itertools.product((3, 6), (2, 3, 5), (6, 24), (1.0, 3.0), (True, False)):
        def fB(r, P=P, K=K, N=N, Y=Y, inc=inc):
            tw = r["w"]["wallet"]
            return any(r["h"].get(u, 0) >= Y and c[(P, N)] >= K for u, c in r["Bc"].items() if inc or u != tw)
        rules[f"B P{P} K{K} N{N} Y{Y} {'incl' if inc else 'excl'}-trig"] = ("B", fB)
    for K in (1, 2, 3, 5):
        rules[f"C1 whale dumps24h>={K}"] = ("C", lambda r, K=K: r["C1"] >= K)
    for mm in (1, 2):
        rules[f"C2 trig past fills<0 n>={mm}"] = ("C", lambda r, mm=mm: r["C2n"] >= mm and r["C2s"] < 0)
    rules["C3 whale sold this token before"] = ("C", lambda r: r["C3"])
    for Y in (1.0, 3.0, 6.0):
        rules[f"D1 creator holds>={Y}"] = ("D", lambda r, Y=Y: r["D1"] >= Y)
    for K in (3, 10, 30):
        rules[f"D2 creator launches24h>={K}"] = ("D", lambda r, K=K: r["D2"] >= K)
    for mm in (1, 2):
        rules[f"D3 creator past fills<0 n>={mm}"] = ("D", lambda r, mm=mm: r["D3n"] >= mm and r["D3s"] < 0)
    rules["D4 rearm dumper is creator"] = ("D", lambda r: r["D4"])
    for Y in (5.0, 10.0, 20.0):
        rules[f"E1 bundle sum>={Y}"] = ("E", lambda r, Y=Y: r["E1"] >= Y)
    for K in (2, 4):
        rules[f"E2 bundle wallets>={K}"] = ("E", lambda r, K=K: r["E2"] >= K)
    rules["E3 holder>=3 same first slot as trigger"] = ("E", lambda r: r["E3"])
    for Y in (0.5, 1.0, 3.0):
        rules[f"F bot holds>={Y}"] = ("F", lambda r, Y=Y: r["Fb"] >= Y)
    print("rules", len(rules), flush=True)
    res = {}
    for name, (fam, fn) in rules.items():
        sk = np.array([bool(fn(r)) for r in R])
        res[name] = (fam, sk)
    meta = [dict(run=r["run"], mode=r["mode"], t=r["t"], val_s=r["val_s"], val_r=r["val_r"], pnl_s=r["pnl_s"], filled=r["filled"], kind=r["w"]["kind"], mint=r["w"]["mint"],
                 wallet=r["w"]["wallet"], creator=r["f"].get("creator"), fill_t=r["w"].get("fill_t"), C1=r["C1"], D1=r["D1"], D2=r["D2"], E1=r["E1"], E2=r["E2"], Fb=r["Fb"],
                 C2n=r["C2n"], C2s=r["C2s"], D3n=r["D3n"], D3s=r["D3s"]) for r in R]
    pickle.dump({"meta": meta, "res": res}, open(f"{D}/rules.pkl", "wb"))
    print("saved", flush=True)


if __name__ == "__main__":
    main()
