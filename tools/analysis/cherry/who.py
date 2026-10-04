#!/usr/bin/env python3
"""Who takes our opportunities: the signer of every taker the engine recorded (first transaction after the trigger that
touched both pools of the round trip), with its fee, tip and gain. Read-only RPC (getTransaction)."""
import json, time, collections, sys
import types
# reuse takers.py's helpers (rpc, facts, ...) without running its analysis
T = types.SimpleNamespace()
_src = open("/root/arb-lab/takers.py").read().split('out = open("/root/arb-lab/runs/takers.jsonl"')[0]
_ns = {}
exec(_src, _ns)
T.__dict__.update(_ns)

RUNS = ["shadow-3", "shadow-4", "exec-1", "live-run-1", "live-run-2"]
rows = []
for r in RUNS:
    try: f = open(f"/root/arb-lab/runs/{r}/opportunities.jsonl")
    except OSError: continue
    for l in f:
        o = json.loads(l)
        t = o.get("taker")
        if t and t.get("sig"): rows.append((r, o, t))
out = open("/root/arb-lab/runs/who.jsonl", "w")
for r, o, t in rows:
    tx = T.rpc("getTransaction", [t["sig"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    time.sleep(0.05)
    if not tx or "_error" in tx: continue
    f = T.facts(tx, -1, tx["slot"])
    rec = {"run": r, "opp": o["id"], "trigger": o["trigger"], "trigger_slot": o["slot"], "buy_pool": o["buy_pool"], "sell_pool": o["sell_pool"],
           "source": o["buy_source"] + "/" + o["sell_source"], "net_predicted": o["net_lamports"], "size": o["size_lamports"],
           "taker_sig": t["sig"], "taker_slot": tx["slot"], "window_ms": t.get("window_ms"),
           **{k: f[k] for k in ("signer", "ok", "fee", "priority_fee", "cu_price", "cu_limit", "cu_used", "tip", "signer_sol_wsol_change", "programs", "version", "nsig")}}
    out.write(json.dumps(rec) + "\n")
out.close()
R = [json.loads(l) for l in open("/root/arb-lab/runs/who.jsonl")]
arb = [x for x in R if x["ok"] and x["signer_sol_wsol_change"] > 0]
print("takers looked up", len(R), "; successful and gained SOL/WSOL (arbs):", len(arb))
c = collections.Counter(x["signer"] for x in arb)
for s, n in c.most_common(12):
    xs = [x for x in arb if x["signer"] == s]
    med = lambda k: sorted(x[k] or 0 for x in xs)[len(xs) // 2]
    print(f"{s}  {n:>3} wins | cu_price med {med('cu_price')} | prio med {med('priority_fee')} | tip med {med('tip')} | gain med {med('signer_sol_wsol_change')}"
          f" | v{collections.Counter(x['version'] for x in xs).most_common(1)[0][0]} | pools {collections.Counter(x['source'] for x in xs).most_common(2)} | program {collections.Counter(p for x in xs for p in x['programs'] if not p.startswith('ComputeBudget') and p != '11111111111111111111111111111111').most_common(1)}")
