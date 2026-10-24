#!/usr/bin/env python3
# Owner 10-24 02:25 PKT: "what if we raise the tolerance to 15%? on the same trades we lost because of tolerance".
# Every buy of ours that the price guard blocked (pump 6042) in the FRZ tests + PROD run 1: re-bought on the collector's full
# tape at the EXACT block position where our tx executed (getBlock index), 0.25 SOL, same exit (TP +5% / SL -10% / 6 slots,
# sell lands in the next slot as the study's model), same follower model as the backtest. The guard only decides IF the buy
# goes through: allowed when (price just before our tx) / (price right after the dump) <= guard.
# P&L "model" = the study's costs (pump fees + 0.0008/tx); "real" = minus the extra live costs measured tonight (two buy tips
# 0.002 + sell tip 0.001 + priority 0.0011 = 0.0041 vs 0.0016 → −0.0025 per fill). A blocked buy costs 0.0005 (fee only).
# usage: python3 -I guard_whatif.py <run.jsonl> [...]   (env RP_PHASEA_R3 = the extracted collector window)
import os, sys, json, importlib.util
os.environ.setdefault("RP_PHASEA_R3", "phaseA_r3guard")
os.environ.update(RP_PHASEA_R2="phaseA_selfwd", SELL_LAT="75", SLIPIMP="1", DIP_REAL_SLIP="1", SEL_SLIP="1", DIP_LATS="35,50,75", DIP_B="0.25")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import numpy as np
import selexit2 as X
import live_exits as LE
spec = importlib.util.spec_from_file_location("osp", "/home/moiz/sniper/ops/speedcheck/our_speed.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
EXI = [e for e in LE.EXITS if e[0] == "tp5_sl10_1.3s"][0]
GUARDS = (1.05, 1.10, 1.15, 1.20); EXTRA = 0.0025; FAIL = 0.0005
def pnl_at(tr, k, ke, s_land):
    t = tr[k]; fr = ((t["fbps"] or 95) + (t["cbps"] or 30)) / 1e4
    s_in, S_, K_, VAL, CHK, PNL = X.rt_path(tr, ke, fr, s_land)
    nm, tp, sl, cap, mh = EXI; n = len(K_)
    co = s_in + cap; win = (S_ + 1 < co) & (S_ + 1 >= s_in + mh)
    ti = np.flatnonzero(CHK & (VAL >= 1 + tp) & win); si = np.flatnonzero(CHK & (VAL <= 1 - sl) & win)
    a = int(ti[0]) if len(ti) else None; b = int(si[0]) if len(si) else None
    if a is None and b is None: s_out, why = co, "time"
    elif b is None or (a is not None and a <= b): s_out, why = int(S_[a]) + 1, "TP"
    else: s_out, why = int(S_[b]) + 1, "SL"
    j = min(int(np.searchsorted(K_, 2 * s_out + 1, side="left")), n)
    return float(PNL[j]), why
rows = []
for run in sys.argv[1:]:
    ev = [json.loads(l) for l in open(run)]
    for f in [e for e in ev if e["ev"] == "fire"]:
        cl = next((e for e in ev if e["ev"] == "close" and e.get("buy_sig") == f["buy_sig"]), {})
        if "6042" not in json.dumps(cl.get("err") or ""): continue          # only the guard-blocked buys
        lp = next((e for e in ev if e["ev"] == "land_poll" and e.get("sig") == f["buy_sig"]), {})
        bf = next((e for e in ev if e["ev"] == "buy_failed" and e.get("sig") == f["buy_sig"]), {})
        slot = lp.get("land_slot") or bf.get("slot")
        m = f["mint"]; L = X.L.get(m)
        tr = X.rp.read_bucket(L["run"], X.rp.bucket(m), {m}).get(m) if L else None
        pos = S.pos(slot, f["buy_sig"]) if slot else None
        if not tr or not pos: print(f"{m[:6]}: {'no tape' if not tr else 'no block position'}"); continue
        k = next((j for j, t in enumerate(tr) if t.get("sig") == f["dump_sig"]), None)
        if k is None: print(f"{m[:6]}: dump not on the tape"); continue
        ke = next((j for j in range(k + 1, len(tr)) if (tr[j]["s"], tr[j]["i"]) > (slot, pos[0])), len(tr))
        if ke >= len(tr): print(f"{m[:6]}: tape ends"); continue
        p_after = tr[k]["vsol"] / tr[k]["vtok"]; ratio = (tr[ke - 1]["vsol"] / tr[ke - 1]["vtok"]) / p_after
        pnl, why = pnl_at(tr, k, ke, slot)
        ahead = [t for t in tr[k + 1:ke] if t["buy"]]
        rows.append(dict(run=run.split("/")[-1].split(".")[0], mint=m, ratio=ratio, pnl=pnl, why=why, n_ahead=len(ahead), sol_ahead=sum(t["sol"] for t in ahead) / 1e9,
                         dslot=slot - f["slot"], score=None))
print(f"{'run':7s} {'token':8s} price when we executed  buyers ahead      P&L if bought (model / real)  exit")
for r in rows:
    print(f"{r['run']:7s} {r['mint'][:6]:8s} {100 * (r['ratio'] - 1):+6.1f}%              {r['n_ahead']:2d} ({r['sol_ahead']:5.2f} SOL)   {r['pnl']:+.4f} / {r['pnl'] - EXTRA:+.4f}          {r['why']}")
print()
for g in GUARDS:
    fills = [r for r in rows if r["ratio"] <= g]; blocked = len(rows) - len(fills)
    model = sum(r["pnl"] for r in fills) - FAIL * blocked; real = sum(r["pnl"] - EXTRA for r in fills) - FAIL * blocked
    print(f"guard {100 * (g - 1):3.0f}%: would fill {len(fills):2d} of {len(rows)} | P&L model {model:+.4f} SOL, real costs {real:+.4f} SOL | wins {sum(1 for r in fills if r['pnl'] - EXTRA > 0)}")
