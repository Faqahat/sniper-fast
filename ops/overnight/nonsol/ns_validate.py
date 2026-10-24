#!/usr/bin/env python3
# Validation of the quote-curve replay: (1) fee + curve math against real events (our formula vs the event's token amount
# for real buys / quote amount for real sells), (2) placement: R2 launches scored with BOTH our arrival timeline and the
# block-position proxy (R1 only has the proxy) -> bias of the proxy. -> validate.txt
import sys, os, json, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/nonsol"); sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import ns, rp, ns_table as NT
from ns_lib import *
L, CR, TR, W = ns.load()
rows = {r["m"]: r for r in load_rows()}
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1])
# (1) curve math: for each consecutive pair (a, b) on the same curve, predict b's token out (buy) / quote out (sell) from a's reserves
err_b = []; err_s = []; feechk = collections.Counter()
for m, r in list(rows.items()):
    if not tradeable(r): continue
    tr = NT.clean(TR.get(m, []))
    for a, b in zip(tr, tr[1:]):
        if b["vsol"] - a["vsol"] != (b["sol"] if b["buy"] else -b["sol"]): continue      # only gap-free pairs
        V, T = a["vsol"], a["vtok"]
        if b["buy"]:
            pred = T * b["sol"] // (V + b["sol"]); err_b.append((pred - b["tok"]) / max(b["tok"], 1))
            if b["fbps"]: feechk[abs(b["feeq"] - b["sol"] * b["fbps"] / 1e4) <= 1 + 1e-6 * b["sol"]] += 1
        else:
            pred = V * b["tok"] // (T + b["tok"]); err_s.append((pred - b["sol"]) / max(b["sol"], 1))
    if len(err_b) > 200000: break
q = lambda v, p: sorted(v)[int(p * (len(v) - 1))]
P(f"(1) constant-product check on gap-free consecutive trades: buys n={len(err_b)} rel.err p1/p50/p99 {q(err_b,.01):+.2e}/{q(err_b,.5):+.2e}/{q(err_b,.99):+.2e}; "
  f"sells n={len(err_s)} p1/p50/p99 {q(err_s,.01):+.2e}/{q(err_s,.5):+.2e}/{q(err_s,.99):+.2e}; protocol fee == q x bps: {dict(feechk)}")
# (2) placement bias: R2 launches with a timeline, scored with the proxy too
O = rp.load_obs()
r2 = [r for r in rows.values() if tradeable(r) and r["run"] == "R2" and r["plc"] == "obs"]
byb = collections.defaultdict(list)
for r in r2: byb[rp.bucket(r["m"])].append(r["m"])
res = collections.defaultdict(lambda: collections.Counter()); pn = collections.defaultdict(lambda: [0.0, 0.0, 0, 0])
for b, ms in byb.items():
    for m in ms:
        r = rows[m]; tr = NT.clean(TR[m]); c = L[m]; st = rp.structure(tr, c)
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]
        for Lm in (30, 45, 75):
            ibp, _ = rp.place_proxy(tr, c, st, Lm)
            e = r["rep"].get(str(Lm))
            if not e: continue
            fill_obs = "strict" in e
            prp = (tr[ibp - 1]["vsol"] / tr[ibp - 1]["vtok"]) / p_b if ibp >= 1 else 9
            fill_px = prp <= 1.005
            res[Lm][(fill_obs, fill_px)] += 1
            res[Lm]["same_idx"] += int(ibp == e["ib"])
P("(2) R2 placement, timeline vs proxy on the same launches (fill_timeline, fill_proxy): counts")
for Lm in (30, 45, 75):
    d = res[Lm]; n = sum(v for k, v in d.items() if k != "same_idx")
    P(f"   L{Lm}: both fill {d[(True,True)]}, timeline only {d[(True,False)]}, proxy only {d[(False,True)]}, neither {d[(False,False)]}; same entry index {d['same_idx']}/{n}")
open(os.path.join(HERE, "validate.txt"), "w").write("\n".join(out) + "\n")
