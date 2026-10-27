#!/usr/bin/env python3
"""REPLAY_065: could a try that FAILED live have filled at another size? (the engine's exact limits, pump's exact math)
  pre-send: every landed attempt that failed on price (6042): min tokens out at size S from its own signing state vs pump's
            tokens out at its real landing spot; also every filled attempt (does it still fill at S?)
  regular : every fired buy that failed on price (6042 at the buy): the guard's min out at S vs pump's tokens out there
Inputs MEASURED (records + chain); the answer at another size is INFERRED (pure math, no landing change)."""
import sys, json, pickle, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real/r065")
import core, pmath as PM

def state_before(trades, s, i):
    last = None
    for t in trades:
        if (t["s"], t["i"]) < (s, i): last = t
        else: break
    return last

def presend(D, sizes):
    out = {S: collections.Counter() for S in sizes}; flips = {S: [] for S in sizes}
    for run, X in D.live.items():
        lands = X["land"]
        for sig, a in X["att"].items():
            L = lands.get(sig) or {}
            res = L.get("res"); s = L.get("slot"); i = L.get("idx")
            if res in (None, "unseen"):
                # the engine did not see it land: look for it in the chain recording
                fl = [x for x in D.tape[a["mint"]]["fails"] if x[2] == sig]
                if fl:
                    s, i = fl[0][0], fl[0][1]; res = "6042" if "6042" in fl[0][3] else "chain_other"
                else: continue
            if res not in ("6042", "ok"): continue
            trs = D.tape[a["mint"]]["trades"]
            pre = state_before(trs, s, i)
            if pre is None: continue
            tsig = next((t for t in trs if (t["s"], t["i"], t["j"]) == tuple(a["pos"])), None)
            if tsig is None: continue
            fr = core.fee_rate_ps(tsig["fbps"], tsig["cbps"])
            for S in sizes:
                mo = core.limit_min_out(a["vsol"], a["vtok"], S, fr, 0.12)
                n = PM.net_of_budget(S, pre["fbps"], pre["cbps"])
                q = pre["vtok"] * (n - 1) // (pre["vsol"] + n - 1)
                fill = mo is not None and q >= mo
                out[S][(res, "fills" if fill else "fails")] += 1
                if (res == "6042") == fill: flips[S].append((run, a["mint"][:8], sig[:10], res))
    return out, flips

def regular(D, RF, RG, sizes):
    out = {S: collections.Counter() for S in sizes}; flips = {S: [] for S in sizes}
    for p in RF:
        fl = [x for x in p.fails if "6042" in x[3]]
        if not fl or p.dump is None: 
            for S in sizes: out[S][("not_price", "-")] += 1
            continue
        s, i = fl[0][0], fl[0][1]
        trs = D.tape[p.mint]["trades"]; pre = state_before(trs, s, i)
        d = p.dump
        for S in sizes:
            mo = core.guard_min_out(d["vsol"], d["vtok"], S, d["fbps"], d["cbps"], p.guard)
            n = PM.net_of_budget(S, pre["fbps"], pre["cbps"]); q = pre["vtok"] * (n - 1) // (pre["vsol"] + n - 1)
            fill = q >= mo
            out[S][("6042", "fills" if fill else "fails")] += 1
            if fill: flips[S].append((p.run, p.mint[:8], round((q / mo - 1) * 1e4, 2)))
    for p in RG:
        d = p.dump; pre = p.pre
        for S in sizes:
            mo = core.guard_min_out(d["vsol"], d["vtok"], S, d["fbps"], d["cbps"], p.guard)
            n = PM.net_of_budget(S, pre["fbps"], pre["cbps"]); q = pre["vtok"] * (n - 1) // (pre["vsol"] + n - 1)
            out[S][("ok", "fills" if q >= mo else "fails")] += 1
            if q < mo: flips[S].append((p.run, p.mint[:8], "filled live, fails at S"))
    return out, flips

if __name__ == "__main__":
    D = core.Data()
    PS, RG, RF = pickle.load(open(f"{core.BASE}/pos_cal.pkl", "rb"))
    sizes = [340_000_000, 500_000_000, 650_000_000, 1_000_000_000]
    a, fa = presend(D, sizes)
    for S in sizes: print("pre-send", S / 1e9, dict(a[S]), "flips", fa[S][:5])
    rs = [350_000_000, 500_000_000, 650_000_000, 1_000_000_000]
    b, fb = regular(D, RF, RG, rs)
    for S in rs: print("regular", S / 1e9, dict(b[S]), "flips", fb[S][:8])
    json.dump(dict(presend={str(S): {"|".join(k): v for k, v in a[S].items()} for S in sizes}, presend_flips={str(S): fa[S] for S in sizes},
                   regular={str(S): {"|".join(k): v for k, v in b[S].items()} for S in rs}, regular_flips={str(S): fb[S] for S in rs}),
              open(f"{core.BASE}/failcheck.json", "w"), indent=1)
