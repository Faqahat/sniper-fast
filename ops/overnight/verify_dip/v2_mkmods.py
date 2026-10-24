#!/usr/bin/env python3
# Build patched copies of the claim's replay modules (from v2_snap/) into v2_mods/, each with an explicit, asserted patch:
#   all:   follower slippage limits read from V2_SLIP (a frozen snapshot), not the live, still-growing core/slip_args.jsonl
#   dipbuy5_stalesel: event selection (sell >= 1 SOL, vsol < 100) uses the STALE-curve sell size / vsol that a lagged engine
#                     would compute (dipbuy5 selects on the true values)
#   dipbuy5_dw:       extra exit keys "<H>w<DW>": same rt_fixed, but a follower's slippage limit can only make it fail if it
#                     arrived within DW ms after our buy (block-position proxy); later followers saw our buy and are replayed as-is
import os, re
HERE = os.path.dirname(os.path.abspath(__file__)); SNAP = os.path.join(HERE, "v2_snap"); OUT = os.path.join(HERE, "v2_mods")
os.makedirs(OUT, exist_ok=True)
def rep(s, a, b, n=1):
    assert s.count(a) == n, (a[:80], s.count(a)); return s.replace(a, b)
SLIP_OLD = 'open("/home/moiz/sniper/ops/overnight/core/slip_args.jsonl")'
SLIP_NEW = 'open(os.environ["V2_SLIP"])'
for name in ("dipbuy4", "dipbuy5"):
    s = open(os.path.join(SNAP, name + ".py")).read()
    s = rep(s, SLIP_OLD, SLIP_NEW)
    open(os.path.join(OUT, name + "_s.py"), "w").write(s)
# stale selection
s = open(os.path.join(OUT, "dipbuy5_s.py")).read()
s = rep(s, 'if t["buy"] or t["sol"] < MIN_SELL or t.get("syn") or k < st["g_end"]: continue',
        'if t["buy"] or t["sol"] < (0.3 * MIN_SELL if HLAG > 0 else MIN_SELL) or t.get("syn") or k < st["g_end"]: continue')
s = rep(s, 'if age < 1 or age > MAX_AGE or t["vsol"] >= 100e9 or t["vsol"] < MIN_VSOL or t["s"] <= busy: continue',
        'if age < 1 or age > MAX_AGE or t["s"] <= busy: continue')
s = rep(s, '            w20 = [x for x in tr[max(0, kv - 60):kv] if t["s"] - x["s"] <= 20]\n',
        '            if f_sol < MIN_SELL or f_vsol >= 100e9 or f_vsol < MIN_VSOL: continue      # v2: select on what the lagged engine sees\n'
        '            w20 = [x for x in tr[max(0, kv - 60):kv] if t["s"] - x["s"] <= 20]\n')
open(os.path.join(OUT, "dipbuy5_stalesel.py"), "w").write(s)
# drop-window exits
s = open(os.path.join(OUT, "dipbuy5_s.py")).read()
fn = '''
DWS = tuple(int(x) for x in os.environ.get("V2_DWS", "").split(",") if x)
def rt_fixed_dw(tr, ke, fr, H, s_land, t_land, DW):
    """= rt_fixed, but a follower's slippage limit (real or imputed) is only applied if it arrived <= DW ms after our buy (proxy);
    followers arriving later had seen our buy (their limit was set on the curve that includes it), so they fill as on chain."""
    V, T = tr[ke - 1]["vsol"], tr[ke - 1]["vtok"]
    X = int(B * 1e9 / (1 + fr)); q = T * X // (V + X); V += X; T -= q; q = int(q * (1 - PEN))
    s_in = max(tr[ke - 1]["s"], s_land) if s_land is not None else tr[ke - 1]["s"]; frs = fr
    SL = float(os.environ.get("SELL_LAT", "0"))
    for t in tr[ke:]:
        if t["s"] >= s_in + H and (SL <= 0 or t["s"] > s_in + H or (t["i"] / max(SS.get(t["s"], 400), t["i"] + 1)) * SMS >= SL): break
        lim = arr(t) <= t_land + DW
        if t["buy"] and lim and t["sig"] in REAL and not t.get("syn"):
            kind, a1, a2 = REAL[t["sig"]]
            if kind == "sol":
                d = T * t["sol"] // (V + t["sol"])
                if d < a2: continue
                V += t["sol"]; T -= d
            else:
                if a1 >= T: continue
                cst = V * a1 // (T - a1) + 1
                if cst * (1 + fr) > a2: continue
                V += cst; T -= a1
        elif t["buy"] and lim and SLIPIMP and not t.get("syn"):
            d = T * t["sol"] // (V + t["sol"])
            if d < t["tok"] / (1 + slack(t["sig"])): continue
            V += t["sol"]; T -= d
        elif t["buy"]: d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d
        else: so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
        frs = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
        if V >= 110e9: break
    so = V * q // (T + q); return so * (1 - frs) / 1e9 - TXC - (B + TXC)
'''
s = rep(s, "def rt_tp(tr, ke, fr, tp=1.05, hmax=30):", fn + "def rt_tp(tr, ke, fr, tp=1.05, hmax=30):")
s = rep(s, '                row["pnl"][str(Lm)] = {str(H): round(rt_fixed(tr, ke, fr, H, s_land), 5) for H in HSET}\n',
        '                row["pnl"][str(Lm)] = {str(H): round(rt_fixed(tr, ke, fr, H, s_land), 5) for H in HSET}\n'
        '                for DW in DWS:\n'
        '                    for H in HSET: row["pnl"][str(Lm)][f"{H}w{DW}"] = round(rt_fixed_dw(tr, ke, fr, H, s_land, a0 + Lm, DW), 5)\n')
open(os.path.join(OUT, "dipbuy5_dw.py"), "w").write(s)
print("written:", sorted(os.listdir(OUT)))
