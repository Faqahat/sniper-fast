#!/usr/bin/env python3
# Our PROD dip runs 1-8 (2g wallet), every fired buy at its exact landing spot (slot + block index; reverted ones as if filled), at the
# run's size, under different exits: the run's exit (SL -10% or sold at 6 slots), fixed holds, and haqqiUUX-style holds (sell when
# outside buying stalls, wide stop, long cap; optional adds). Every later action lands 60 ms after its decision. Collector tapes (R3),
# read-only RPC for slot / index. Pump fees + 0.0008 SOL per tx; plain curve (no follower limits).
import os, sys, json, time, urllib.request, collections, concurrent.futures as cf
os.environ.setdefault("RP_PHASEA_R2", "phaseA_selfwd"); os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3"); os.environ["RP_REPAIR"] = "0"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
def rpc(m, p):
    for i in range(6):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=90))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(0.6 * (i + 1))
SS = {int(k): v for k, v in json.load(open("/home/moiz/sniper/ops/overnight/core/slotsize2.json")).items()}
def arr(t): return t["s"] * 212.0 + t["i"] / max(SS.get(t["s"], 400), t["i"] + 1) * 212.0
X = json.load(open("/home/moiz/sniper/ops/overnight/hkq7/2g_closes.json"))
def where(x):
    t = rpc("getTransaction", [x["sig"], {"encoding": "json", "maxSupportedTransactionVersion": 1}])
    if not t: return None
    b = rpc("getBlock", [t["slot"], {"encoding": "json", "transactionDetails": "signatures", "maxSupportedTransactionVersion": 1, "rewards": False}])
    return (t["slot"], b["signatures"].index(x["sig"]) if b and x["sig"] in b["signatures"] else None)
with cf.ThreadPoolExecutor(8) as ex: WH = list(ex.map(where, X))
TXC = 0.0008; LAT = 60.0
def fr(t): return ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
EXITS = {"run exit: SL -10% or 6 slots": dict(kind="tpsl", tp=9, sl=0.10, cap=6), "hold 6 slots": dict(kind="tpsl", tp=9, sl=9, cap=6),
         "hold 12 slots": dict(kind="tpsl", tp=9, sl=9, cap=12), "hold 30 slots": dict(kind="tpsl", tp=9, sl=9, cap=30),
         "haqq: stall 1.5 s, SL -25%, cap 60 s": dict(kind="haqq", G=1500, sl=0.25, T=60, N=0, A=0),
         "haqq: stall 4 s, no SL, cap 60 s": dict(kind="haqq", G=4000, sl=9, T=60, N=0, A=0),
         "haqq: stall 1.5 s, SL -25%, cap 60 s, 3 adds": dict(kind="haqq", G=1500, sl=0.25, T=60, N=3, A=1.5)}
def sim(tr, ke, s_in, B, e):
    A_ = [arr(t) for t in tr]
    V, Tk = tr[ke - 1]["vsol"], tr[ke - 1]["vtok"]; f = fr(tr[ke - 1]); Xs = int(B / (1 + f)); q = Tk * Xs // (V + Xs); V += Xs; Tk -= q
    cost = B / 1e9 + TXC; frs = f; a_in = A_[ke] if ke < len(tr) else 0
    if e["kind"] == "tpsl":
        s_out = s_in + e["cap"]
        for t in tr[ke:]:
            if t["s"] >= s_out: break
            if t["buy"]: d = Tk * t["sol"] // (V + t["sol"]); V += t["sol"]; Tk -= d
            else: so = V * t["tok"] // (Tk + t["tok"]); V -= so; Tk += t["tok"]
            frs = fr(t); v = ((V * q / (Tk + q)) * (1 - frs) / 1e9 - TXC) / cost
            if s_out > t["s"] + 1 and (v >= 1 + e["tp"] or v <= 1 - e["sl"]): s_out = t["s"] + 1
        return (V * q / (Tk + q)) * (1 - frs) / 1e9 - TXC - cost
    adds = 0; flow = 0.0; last_buy = a_in; pend_add = None; pend_exit = None
    for k in range(ke, len(tr)):
        t = tr[k]; a = A_[k]
        if pend_exit is None and a - last_buy >= e["G"]: pend_exit = last_buy + e["G"] + LAT
        if pend_exit is not None and a >= pend_exit: break
        if pend_add is not None and a >= pend_add:
            Xs = int(B / (1 + fr(t))); dq = Tk * Xs // (V + Xs); V += Xs; Tk -= dq; q += dq; cost += B / 1e9 + TXC; adds += 1; pend_add = None
        if t["buy"]:
            d = Tk * t["sol"] // (V + t["sol"]); V += t["sol"]; Tk -= d
            if t["sol"] >= 0.1e9: last_buy = a; flow += t["sol"] / 1e9
        else: so = V * t["tok"] // (Tk + t["tok"]); V -= so; Tk += t["tok"]
        frs = fr(t)
        if V >= 114e9: break
        val = (V * q / (Tk + q)) * (1 - frs) / 1e9 - TXC
        if pend_exit is None and (val <= (1 - e["sl"]) * cost or a - a_in >= e["T"] * 1000): pend_exit = a + LAT
        if pend_add is None and pend_exit is None and adds < e["N"] and flow >= e["A"]: pend_add = a + LAT; flow = 0.0
    return (V * q / (Tk + q)) * (1 - frs) / 1e9 - TXC - cost
L = rp.load_launches(); byb = collections.defaultdict(set)
for x in X:
    if x["mint"] in L: byb[(L[x["mint"]]["run"], rp.bucket(x["mint"]))].add(x["mint"])
tapes = {}
for k, ms in byb.items(): tapes.update(rp.read_bucket(k[0], k[1], ms))
rows = []
for x, w in zip(X, WH):
    tr = tapes.get(x["mint"])
    if not tr or not w or w[1] is None or not x.get("spend"): continue
    ke = next((k for k, t in enumerate(tr) if t["s"] > w[0] or (t["s"] == w[0] and t["i"] > w[1])), None)
    if not ke: continue
    rows.append(dict(x, res={n: sim(tr, ke, w[0], x["spend"], e) for n, e in EXITS.items()}))
json.dump(rows, open("/home/moiz/sniper/ops/overnight/hkq7/runs_haqqstyle.json", "w"), default=str)
print(f"fires replayed: {len(rows)} of {len(X)}")
for grp, lab in (("sold", "FILLED buys (real fills)"), ("buy_failed", "REVERTED buys (as if filled)"), (None, "ALL fires (if every buy had filled)")):
    v = [r for r in rows if grp is None or r["result"] == grp]
    print(f"\n== {lab}: {len(v)}" + (f" | their real curve P&L {sum((r['curve_pnl'] or 0) for r in v) / 1e9:+.3f} SOL" if grp == "sold" else ""))
    for n in EXITS:
        p = [r["res"][n] for r in v]
        print(f"   {n:44s} total {sum(p):+7.3f} | win {sum(1 for a in p if a > 0):3d}/{len(p)} | best {max(p):+.3f} worst {min(p):+.3f}")
by = collections.defaultdict(lambda: collections.defaultdict(float))
for r in rows:
    if r["result"] == "sold":
        for n in ("run exit: SL -10% or 6 slots", "haqq: stall 1.5 s, SL -25%, cap 60 s", "haqq: stall 4 s, no SL, cap 60 s"): by[r["run"]][n] += r["res"][n]
print("\nfilled buys by run (run exit | haqq stall 1.5 s | haqq stall 4 s):")
for k in sorted(by): print(f"   run {k}: " + " | ".join(f"{v:+.3f}" for v in by[k].values()))
