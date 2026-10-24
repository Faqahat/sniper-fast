# value of landing earlier on OUR fired dumps: replay a 0.35 SOL buy (+5% guard) inserted at same-slot index gap d,
# exit at the curve state at the end of dump slot + 6 (our exit rule ~1.3 s), pump fees 1.25%/side + fixed send costs.
import os, sys, json, collections
os.environ["RP_PHASEA_R2"] = "phaseA_selfwd"; os.environ["RP_PHASEA_R3"] = "phaseA_r3day"
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
B = "/home/moiz/sniper/ops/agents/topearners/work/"
J = json.load(open(B + "our_join.json")); mine = J["mine"]; races = J["races"]
SOL = 0.35e9; FR = 0.0125; G = float(os.environ.get("GUARD", "1.05"))
FIX_US = 0.0035e9; FIX_PRO = 0.0005e9        # our round-trip tips+prio (~3.5 mSOL) vs a pro's (~0.5 mSOL)
launch = rp.load_launches()
need = collections.defaultdict(set); fl = []
for f in J["fires"]:
    r = races.get(f["dump_sig"]); x = mine.get(f["buy_sig"])
    if not r or not x: continue
    m = r["m"]; need[(launch[m]["run"], rp.bucket(m))].add(m); fl.append((f, r, x))
T = {}
for (run, b), ms in need.items(): T.update(rp.read_bucket(run, b, ms))
def tout(V, Tk, x): X = x / (1 + FR); return Tk * X / (V + X)
def sol_out(V, Tk, q): return V * q / (Tk + q) * (1 - FR)
res = collections.defaultdict(list)
for f, r, x in fl:
    tr = T.get(r["m"]) or []
    k0 = next((k for k, t in enumerate(tr) if t["sig"] == r["sig"]), None)
    if k0 is None: continue
    V0, T0 = tr[k0]["vsol"], tr[k0]["vtok"]; need_q = tout(V0, T0, SOL) / G
    s0 = r["s"]
    # exit state: last trade at slot <= s0+6 (others only)
    ex = None
    for t in tr[k0:]:
        if t["s"] <= s0 + 6: ex = t
        else: break
    for label, pos in [("d=10", (s0, r["i"] + 10)), ("d=50", (s0, r["i"] + 50)), ("d=100", (s0, r["i"] + 100)), ("actual", (x["s"], x["i"]))]:
        # state before pos (others' trades only, excluding ours)
        V, Tk = V0, T0; kk = k0
        for k in range(k0 + 1, len(tr)):
            t = tr[k]
            if t["user"] == "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE": continue
            if (t["s"], t["i"]) < pos: V, Tk = t["vsol"], t["vtok"]; kk = k
            else: break
        q = tout(V, Tk, SOL)
        if q < need_q: res[label].append(None); continue
        # our buy shifts the curve: approximate every later state as (V + Xn, T - q). Exit rule like ours: TP +5% / SL -10%
        # seen on a trade -> our sell fills at the state at the END of the next slot; else at the end of dump slot + 6.
        Xn = SOL / (1 + FR); bslot = pos[0]
        later = [t for t in tr[kk + 1:] if t["user"] != "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"]
        def state_end(slot):
            st = None
            for t in later:
                if t["s"] <= slot: st = t
                else: break
            return (st["vsol"], st["vtok"]) if st else (V + 0, Tk + 0)
        exit_slot = s0 + 6
        for t in later:
            if t["s"] > s0 + 6: break
            val = sol_out(t["vsol"] + Xn, t["vtok"] - q, q) / SOL
            if val >= 1.05 or val <= 0.90: exit_slot = min(s0 + 6, t["s"] + 1); break
        Ve, Te = state_end(exit_slot)
        if Ve == V and Te == Tk: Ve, Te = V, Tk
        out = sol_out(Ve + Xn, Te - q, q)
        res[label].append(out - SOL)
for label, v in res.items():
    fills = [p for p in v if p is not None]
    n = len(v); nf = len(fills)
    tot = sum(fills)
    print(f"{label:7s} fires={n} fills={nf} ({nf/n:.0%})  sum PnL before fixed costs={tot/1e9:+.3f} SOL  per fill={tot/max(1,nf)/1e9:+.4f}  after our fixed costs={ (tot - nf*FIX_US)/1e9:+.3f}  after pro-level costs={(tot - nf*FIX_PRO)/1e9:+.3f}")
