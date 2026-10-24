#!/usr/bin/env python3
# FORWARD test of the frozen DIP2 models (2-slot exit, spacing 5) on dips AFTER their freeze, split by whether the trigger is a
# DIRECT pump sell (top-level instruction, readable from shreds) or routed. Direct = the trigger tx invokes no program outside
# the non-routing whitelist (dipshadow/direct_rule.py, 99.8% vs RPC truth), from the collector's raw rows. Local data only.
# usage: python3 -I dipfwd_direct.py
import sys, os, json, time, glob, gzip, collections
os.environ.setdefault("RP_PHASEA_R2", "phaseA_dry"); os.environ["SLIPIMP"] = "1"; os.environ["SELL_LAT"] = "75"
os.environ["DIP_LATS"] = "35,50,75"; os.environ["DIP_B"] = "0.5"; os.environ["DIP_HS"] = "2"; os.environ["DIP_BUSY"] = "5"; os.environ["DIP_REAL_SLIP"] = "1"
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/dip")
import dipbuy4 as D
import gbdt_np as G
from dipcv import fv
from multiprocessing import Pool
STEMS = os.environ.get("FWD_MODELS", "dip2_L35,dip2_L50,dip2_L75,dip2r_L35,dip2r_L50,dip2r_L75").split(",")
M = {st: json.load(open(f"/home/moiz/sniper/ops/overnight/dip/frozen_{st}.json")) for st in STEMS}
T0 = min(m["frozen_at"] for m in M.values())
D.byb.clear()
for m, c in D.L.items():
    if c.get("bt") and c["bt"] >= T0 - 130: D.byb[(c["run"], D.rp.bucket(m))].add(m)
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
WL = {"11111111111111111111111111111111", "ComputeBudget111111111111111111111111111111", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
      "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr",
      "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo", "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ", "L2TExMFKdjpN9kozasaurPirfHy9P8sbXoAN1qA3S95", PUMP}
def score(model, R):
    X = np.array([fv(r) for r in R]) if R else np.zeros((0, len(model["features"])))
    Bm = np.zeros(X.shape, np.int16)
    for j in range(X.shape[1]):
        b = np.searchsorted(np.array(model["edges"][j]), X[:, j], side="right") + 1; b[np.isnan(X[:, j])] = 0; Bm[:, j] = b
    f = np.full(len(R), model["F0"])
    for t in model["trees"]: f += model["lr"] * G.pred(t, Bm)
    return f
def trig_sig(e):
    S0 = D.L[e["m"]]["slot"]
    tr = D.rp.read_bucket(e["run"], D.rp.bucket(e["m"]), {e["m"]}).get(e["m"], [])
    t = next((t for t in tr if (not t["buy"]) and t["sol"] >= D.MIN_SELL and t["user"].startswith(e["seller"]) and round((t["s"] - S0) * D.SMS / 1000, 2) == e["age"]), None)
    return t["sig"] if t else None
if __name__ == "__main__":
    ev = []
    with Pool(8) as p:
        for o, _ in p.imap_unordered(D.work, sorted(D.byb), chunksize=1): ev += o
    ev = [r for r in ev if r["bt"] + r["age"] > T0]; ev.sort(key=lambda r: r["bt"] + r["age"])
    span = ((ev[-1]["bt"] + ev[-1]["age"] - T0) / 3600) if ev else 0
    picks = {}
    for lat, model in M.items():
        f = score(model, ev)
        picks[lat] = [r for r, s in zip(ev, f) if s >= model["thresholds"]["5%"] and r["bt"] + r["age"] > model["frozen_at"]]
    need = {(r["m"], r["age"]): r for v in picks.values() for r in v}
    sig = {k: trig_sig(r) for k, r in need.items()}
    want = {s for s in sig.values() if s}
    progs = {}
    files = sorted(glob.glob("/home/moiz/sniper-data/collect/run_20261022_1543/txs/*.jsonl.gz"))[-40:]
    for fn in files:
        try:
            for line in gzip.open(fn, "rt"):
                a = line.find('"sig":"')
                if a < 0: continue
                sg = line[a + 7:line.find('"', a + 7)]
                if sg in want: progs[sg] = json.loads(line).get("progs") or []
        except (EOFError, OSError): pass
    print(f"FORWARD DIP2 direct-only test (real limits where decoded), evaluated {time.strftime('%Y-%m-%d %H:%M', time.gmtime(time.time() + 18000))} PKT | "
          f"forward dips {len(ev)} over {span:.2f} h | trigger txs found {len(progs)} of {len(want)}")
    for lat, v in picks.items():
        for kind in ("direct", "routed", "unknown"):
            rows = []
            for r in v:
                s = sig.get((r["m"], r["age"])); g = progs.get(s)
                k = "unknown" if g is None else ("direct" if not (set(g) - WL) else "routed")
                if k == kind: rows.append(r)
            if not rows: continue
            cells = []
            for Lm in ("35", "50", "75"):
                p = [r["pnl"][Lm]["2"] for r in rows if Lm in r["pnl"]]
                g = [(r["pnl"][Lm]["2"] if r["px"].get(Lm, 1) <= 1.02 else -0.0002) for r in rows if Lm in r["pnl"]]
                cells.append(f"L{Lm}: n {len(p)} {sum(p):+.2f} (guard {sum(g):+.2f})")
            print(f"  {M[lat]['name'].replace('FRZ-', '')} top 5% [{kind}] since its freeze: " + " | ".join(cells))
            if os.environ.get("DUMP"):
                with open(os.environ["DUMP"], "a") as fo:
                    for r in rows: fo.write(json.dumps(dict(model=lat, kind=kind, m=r["m"], age=r["age"], bt=r["bt"], seller=r["seller"], sell=r["sell"], ins=r["ins"],
                                                            drop=r["drop"], vsol=r["vsol"], pnl={L: r["pnl"][L]["2"] for L in r["pnl"]}, px=r["px"])) + "\n")
