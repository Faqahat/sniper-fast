#!/usr/bin/env python3
# r15: is our slowness linked to the dumps that pay? Shuffle the measured latencies across fires WITHIN strata
# (leader client x dump position in its block); if this reproduces the exact-landing result, those two observables explain
# the link and can be used to price the dumps we did not fire on.
import sys, os, json, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib as R, rsim as S
from r13_corrected import outcome
P = json.load(open(f"{R.WORK}/pertrade.json")); runs = {(r["srv"], r["run"]): r for r in json.load(open(f"{R.WORK}/fires.json"))["runs"]}
TPS = {tag: S.Tapes(tag) for tag in ("NEW", "OLD")}
cost = {}; fcost = {}
for k in runs:
    fl = [o for o in P if (o["srv"], o["run"]) == k and o["live_fill"] and o.get("buy_txcost") is not None]
    fa = [o for o in P if (o["srv"], o["run"]) == k and not o["live_fill"]]
    cost[k] = float(np.mean([o["buy_txcost"] + o["sell_txcost"] for o in fl])) if fl else 0.0031
    fcost[k] = float(np.mean([-o["chain_pnl"] for o in fa])) if fa else 0.000505
def ctype(c):
    c = c or "?"
    if "Jito" in c: return "jito"
    if "Bam" in c or "BAM" in c: return "bam"
    if "Harmonic" in c: return "harmonic"
    return "other"
def ib(i): return 0 if i < 100 else (1 if i < 200 else (2 if i < 300 else 3))
items = []
for o in P:
    k = (o["srv"], o["run"]); cfg = runs[k]["cfg"]; sl = cfg["sl"] if cfg["sl"] < 0.5 else None
    TP = TPS[o["tape"]]; t, j0 = TP.find(o["mint"], o["dump_slot"], o["dump_idx"], o.get("sell")); tp = TP.token(t)
    items.append(dict(o=o, k=k, cfg=cfg, sl=sl, tp=tp, j0=j0, st=(ctype(o["client"]), ib(o["dump_idx"]))))
def val(it, L):
    res = S.run_path(it["tp"], it["j0"], it["o"]["size"], L=L)
    return outcome(res, it["cfg"]["hold_slots"], it["sl"], cost[it["k"]], fcost[it["k"]])["pnl"]
exact = sum(val(it, float(it["o"]["L_meas"]) + 1e-6) for it in items)
print(f"exact landing {exact:+.3f}")
for name, keyf in (("client", lambda it: it["st"][0]), ("dump idx bucket", lambda it: it["st"][1]), ("client x idx", lambda it: it["st"])):
    groups = collections.defaultdict(list)
    for n, it in enumerate(items): groups[keyf(it)].append(n)
    rng = np.random.default_rng(5); draws = []
    for rep in range(5):
        L = np.array([it["o"]["L_meas"] for it in items], float); L2 = L.copy()
        for g, ix in groups.items():
            ix = np.array(ix); L2[ix] = L[rng.permutation(ix)]
        draws.append(sum(val(it, float(L2[n])) for n, it in enumerate(items)))
    print(f"shuffled within {name:16s}: {np.mean(draws):+.3f} (draws {', '.join(f'{x:+.2f}' for x in draws)})")
# per stratum: n, median L, live, exact model, model at 35
print("\nby stratum: n, our median landing, LIVE, model at our landing, model at 35 ms, model at 20 ms")
st = collections.defaultdict(list)
for it in items: st[it["st"][0]].append(it)
for it in items: st["idx%d" % it["st"][1]].append(it)
for g, lst in sorted(st.items(), key=lambda x: str(x[0])):
    Ls = [it["o"]["L_meas"] for it in lst]
    print(f"  {g:9s} n {len(lst):3d} L50 {np.median(Ls):5.0f}  live {sum(it['o']['chain_pnl'] for it in lst):+.3f}  exact {sum(val(it, float(it['o']['L_meas']) + 1e-6) for it in lst):+.3f}"
          f"  @35 {sum(val(it, 35.0) for it in lst):+.3f}  @20 {sum(val(it, 20.0) for it in lst):+.3f}")
