#!/usr/bin/env python3
# READ-ONLY, offline: CWiNFA's buy price guard. Every buy is BuyExactQuoteInV3(spend 1 SOL, min_tokens_out). For buys inside
# our collector windows, compare min_tokens_out with the tokens 1 SOL would buy at reference curve states:
#   fresh curve (30 SOL / 1.073e15), after the creator's own buy (create tx), after the glued bundle, and the state its buy
#   actually met. A constant ratio at one reference state reveals the rule (ratio = 1 - slippage tolerance).
# Also the failed buys (BuySlippageBelowMinTokensOut): where the price was when they failed.
import os, sys, json, statistics, collections
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["RP_PHASEA_R2"] = os.path.join(HERE, "phaseA_snap")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
W = "CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J"
L = rp.load_launches(); LED = json.load(open(os.path.join(HERE, "ledger_CWiNFA.json")))["txs"]
buys = {}
for r in LED:
    if r.get("missing") or not r.get("router") or r["router"].get("tag") != 2: continue
    mint = next((m for m in (r.get("tok") or {}) if r["tok"][m] > 0), None) or (r["ev"][0]["mint"] if r.get("ev") else None)
    if mint is None:   # failed buy: find the mint by the seed among launches
        seed = r["router"].get("seed")
        cand = [m for m in L if m.startswith(seed)] if seed else []
        mint = cand[0] if len(cand) == 1 else None
    if mint: buys.setdefault(mint, []).append(r)
ms = [m for m in buys if m in L]
byb = collections.defaultdict(set)
for m in ms: byb[(L[m]["run"], rp.bucket(m))].add(m)
def toks(V, T, fr): X = int(1e9 / (1 + fr)); return T * X // (V + X)
rows = []
for key, mm in byb.items():
    tra = rp.read_bucket(key[0], key[1], mm)
    for m, tr in tra.items():
        c = L[m]; st = rp.structure(tr, c); g = st["g_end"]
        if g < 1 or st["dev_k"] is None: continue
        fr = (tr[0]["fbps"] + tr[0]["cbps"]) / 1e4
        dv = tr[st["dev_k"]]; ge = tr[g - 1]
        for b in buys[m]:
            mo = b["router"]["min_out"]
            k0 = next((k for k, t in enumerate(tr) if t["sig"] == b["sig"]), None)
            pre = tr[k0 - 1] if k0 else None
            got = b["ev"][0]["tok"] if b.get("ev") else None
            if not b["err"] and pre is None: continue
            # failed buys: state = last trade before its slot/idx is unknown exactly; use the last trade in an earlier slot
            if b["err"]:
                prev = [t for t in tr if t["s"] < b["slot"]] or [ge]
                pre = prev[-1] if prev[-1]["s"] >= c["slot"] else ge
            rows.append(dict(m=m, sig=b["sig"], err=b["err"], min_out=mo, got=got, dev=round(dv["sol"] / 1e9, 4), glued=len(st["glued"]),
                             r_fresh=mo / toks(30e9, 1.073e15, fr), r_dev=mo / toks(dv["vsol"], dv["vtok"], fr), r_bundle=mo / toks(ge["vsol"], ge["vtok"], fr),
                             r_met=mo / toks(pre["vsol"], pre["vtok"], fr), mult_met=(pre["vsol"] / pre["vtok"]) / (ge["vsol"] / ge["vtok"])))
json.dump(rows, open(os.path.join(HERE, "guard.json"), "w"))
ok = [r for r in rows if not r["err"]]; bad = [r for r in rows if r["err"]]
q = lambda xs, p: sorted(xs)[int(p * (len(xs) - 1))]
out = [f"buys matched to collector launches: {len(ok)} filled, {len(bad)} failed"]
for k in ("r_fresh", "r_dev", "r_bundle", "r_met"):
    xs = [r[k] for r in ok]
    out.append(f"  min_out / tokens at {k[2:]:7}: p5 {q(xs, .05):.3f} p25 {q(xs, .25):.3f} median {statistics.median(xs):.3f} p75 {q(xs, .75):.3f} p95 {q(xs, .95):.3f} (spread p95/p5 {q(xs, .95) / q(xs, .05):.2f})")
xs = [r["got"] / r["min_out"] for r in ok if r["got"]]
out.append(f"  tokens received / min_out (filled): p5 {q(xs, .05):.3f} median {statistics.median(xs):.3f} p95 {q(xs, .95):.3f}")
if bad:
    xs = [r["mult_met"] for r in bad]
    out.append(f"  failed buys: price before them vs post-bundle price: median {statistics.median(xs):.3f} (min {min(xs):.3f}, max {max(xs):.3f}); r_met median {statistics.median(r['r_met'] for r in bad):.3f}")
xs = [r["mult_met"] for r in ok]
out.append(f"  filled buys: price met vs post-bundle price: median {statistics.median(xs):.3f} p90 {q(xs, .9):.3f} max {max(xs):.3f}")
# implied max entry price: min_out means the bot accepts paying up to (1 SOL net / min_out) per token
for k in ("r_dev", "r_bundle"):
    g = collections.defaultdict(list)
    for r in ok: g[(r["dev"], r["glued"])].append(r[k])
    top = sorted(g.items(), key=lambda kv: -len(kv[1]))[:6]
    out.append(f"  {k} by (dev buy, glued txs): " + " | ".join(f"{d}/{gl}: med {statistics.median(v):.3f} sd {statistics.pstdev(v):.3f} n {len(v)}" for (d, gl), v in top))
open(os.path.join(HERE, "guard.txt"), "w").write("\n".join(out) + "\n"); print("\n".join(out))
