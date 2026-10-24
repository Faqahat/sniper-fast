#!/usr/bin/env python3
# Replay the PROD dip runs' REVERTED buys as if they had filled (and the filled ones as a check): our buy goes exactly where the
# failed tx landed (its slot + index in the block), size = that run's spend, then exits: run exit (SL -10% or sold at 6 slots),
# TP +5% / SL -10% / 6 slots, plain 6 slots, 12 slots, 30 slots. Pump fees + 0.0008 per tx. Collector tapes (run R3), read-only RPC
# for the slot / block index. usage: python3 -I replay_reverted.py
import os, sys, json, time, urllib.request, collections, concurrent.futures as cf
os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd"); os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3"); os.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
def rpc(m, p):
    for i in range(6):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=60))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(0.6 * (i + 1))
X = json.load(open("/home/moiz/sniper/ops/overnight/hkq7/2g_closes.json"))
def where(x):
    t = rpc("getTransaction", [x["sig"], {"encoding": "json", "maxSupportedTransactionVersion": 0}])
    if not t: return None
    b = rpc("getBlock", [t["slot"], {"encoding": "json", "transactionDetails": "signatures", "maxSupportedTransactionVersion": 0, "rewards": False}])
    return (t["slot"], b["signatures"].index(x["sig"]) if b and x["sig"] in b["signatures"] else None)
with cf.ThreadPoolExecutor(8) as ex: W = list(ex.map(where, X))
L = rp.load_launches(); TXC = 0.0008
EX = {"run exit (SL-10%/6 slots)": (9.0, 0.10, 6), "TP+5%/SL-10%/6 slots": (0.05, 0.10, 6), "sell at 6 slots": (9.0, 9.0, 6),
      "sell at 12 slots": (9.0, 9.0, 12), "sell at 30 slots": (9.0, 9.0, 30)}
def sim(tr, ke, s_in, B):
    fr = ((tr[ke - 1]["fbps"] or 95) + (tr[ke - 1]["cbps"] or 30)) / 1e4
    V0, T0 = tr[ke - 1]["vsol"], tr[ke - 1]["vtok"]; Xs = int(B / (1 + fr)); q = T0 * Xs // (V0 + Xs)
    out = {}
    for nm, (tp, sl, cap) in EX.items():
        V, T = V0 + Xs, T0 - q; frs = fr; s_out = s_in + cap; cost = B / 1e9 + TXC
        for t in tr[ke:]:
            if t["s"] >= s_out: break
            if t["buy"]: d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d
            else: so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
            frs = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
            v = ((V * q / (T + q)) * (1 - frs) / 1e9 - TXC) / cost
            if s_out > t["s"] + 1 and (v >= 1 + tp or v <= 1 - sl): s_out = t["s"] + 1
        out[nm] = (V * q / (T + q)) * (1 - frs) / 1e9 - TXC - cost
    return out
byb = collections.defaultdict(set)
for x in X:
    if x["mint"] in L: byb[(L[x["mint"]]["run"], rp.bucket(x["mint"]))].add(x["mint"])
tapes = {}
for k, ms in byb.items(): tapes.update(rp.read_bucket(k[0], k[1], ms))
rows = []
for x, w in zip(X, W):
    tr = tapes.get(x["mint"])
    if not tr or not w or w[1] is None: rows.append(dict(x, ok=False, why="no tape" if not tr else "no block index")); continue
    slot, idx = w
    ke = next((k for k, t in enumerate(tr) if t["s"] > slot or (t["s"] == slot and t["i"] > idx)), None)
    if not ke: rows.append(dict(x, ok=False, why="no trade after")); continue
    rows.append(dict(x, ok=True, slot=slot, idx=idx, res=sim(tr, ke, slot, x["spend"])))
json.dump(rows, open("/home/moiz/sniper/ops/overnight/hkq7/replay_reverted.json", "w"), default=str)
for grp in ("buy_failed", "sold"):
    v = [r for r in rows if r["result"] == grp and r["ok"]]
    print(f"\n== {'REVERTED buys, as if filled' if grp == 'buy_failed' else 'FILLED buys (check vs real curve P&L)'}: {len(v)} replayed of {sum(1 for r in rows if r['result'] == grp)}")
    for nm in EX:
        p = [r["res"][nm] for r in v]
        if p: print(f"   {nm:28s} total {sum(p):+.3f} SOL | win {sum(1 for a in p if a > 0)}/{len(p)} | avg {sum(p) / len(p):+.4f} | best {max(p):+.3f} worst {min(p):+.3f}")
    if grp == "sold": print(f"   real curve P&L of these fills: {sum((r['curve_pnl'] or 0) for r in v) / 1e9:+.3f} SOL")
    by = collections.defaultdict(list)
    for r in v: by[r["run"]].append(r["res"]["run exit (SL-10%/6 slots)"])
    print("   by run (run exit): " + ", ".join(f"r{k} {sum(p):+.3f} ({len(p)})" for k, p in sorted(by.items())))
print("not replayed:", collections.Counter(r.get("why") for r in rows if not r["ok"]))
