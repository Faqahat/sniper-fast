#!/usr/bin/env python3
"""STEP 1 — his ground-truth tape. Join snipe_study50 (create/creator/dev) + exit_study (fill/sells/PnL/path)."""
import json, statistics as st
from collections import Counter

REC = json.load(open("/root/snipe_study50/enriched200.json"))["records"]
ROWS = {r["mint"]: r for r in json.load(open("/root/exit_study/rows2.json"))}
PATHS = json.load(open("/root/exit_study/paths.json"))

by_mint_rec = {r["mint"]: r for r in REC}
tape = []
for mint, rr in ROWS.items():
    rc = by_mint_rec.get(mint, {})
    path = PATHS.get(mint, {}).get("pts", [])
    # floor px = earliest path point (create-slot anchored); fallback to his fill
    floor_px = None
    if path:
        p0 = min(path, key=lambda x: x[0])
        floor_px = p0[1]
    his_fill = rr["px_entry"]
    fill_vs_floor = (his_fill / floor_px) if (floor_px and floor_px > 0) else None
    dev_buy = rc.get("curve_delta")
    dev_sol = (dev_buy / 1e9) if dev_buy else None
    tape.append({
        "mint": mint,
        "creator": rc.get("creator"),
        "create_slot": rc.get("create_slot"),
        "buy_slot": rr["bslot"],
        "delta": rc.get("delta"),
        "vanilla": rc.get("vanilla"),
        "dev_buy_sol": dev_sol,
        "wire_dev_sol": (rc.get("wire_dev")/1e9) if rc.get("wire_dev") else None,
        "his_fill_px": his_fill,
        "floor_px": floor_px,
        "fill_vs_floor": fill_vs_floor,
        "sol_in": rr["sol_in"],
        "nsells": rr["nsells"],
        "sells": [{"dslot": s["dslot"], "frac": s["frac"], "r": s["r"]} for s in rr["sells"]],
        "realized_sol": rr["realized"],
        "realized_R": rr["realized"]/rr["sol_in"] if rr["sol_in"] else None,
        "peak_r": rr["peak_r"],
        "r5": rr.get("r5"), "r10": rr.get("r10"), "r20": rr.get("r20"),
        "path": path,
        "has_path": bool(path),
    })

json.dump(tape, open("/root/mirror/his_tape.json","w"))

# ---- aggregate reproduction ----
realized = [t["realized_sol"] for t in tape]
n=len(tape); tot=sum(realized); win=sum(1 for x in realized if x>0)/n
print(f"HIS TAPE: n={n}  total={tot:+.3f} SOL  mean={tot/n:+.4f}  win={win:.3f}")
# fill-vs-floor distribution
fvf=[t["fill_vs_floor"] for t in tape if t["fill_vs_floor"]]
def pct(xs,p):
    xs=sorted(xs); return xs[min(len(xs)-1,int(round(p*(len(xs)-1))))]
print(f"his fill_vs_floor: n={len(fvf)} p25={pct(fvf,.25):.3f} med={st.median(fvf):.3f} p75={pct(fvf,.75):.3f}  mean={sum(fvf)/len(fvf):.3f}")
print(f"  at-floor (<=1.03): {sum(1 for x in fvf if x<=1.03)}/{len(fvf)}  above 1.2x: {sum(1 for x in fvf if x>1.2)}")
# delta (buy-create slot) dist
dd=Counter(t["delta"] for t in tape if t["delta"] is not None)
print("delta(buy-create):",dict(sorted(dd.items())))
# peak dist
pk=[t["peak_r"] for t in tape if t["peak_r"]]
print(f"peak_r: med={st.median(pk):.3f} >=1.2x:{sum(1 for x in pk if x>=1.2)} >=2x:{sum(1 for x in pk if x>=2)}")

# ---- creator recurrence split ----
crc=Counter(t["creator"] for t in tape if t["creator"])
repeat_creators={c for c,k in crc.items() if k>=2}
rep=[t for t in tape if t["creator"] in repeat_creators]
one=[t for t in tape if t["creator"] and t["creator"] not in repeat_creators]
def grp(ts):
    r=[t["realized_sol"] for t in ts]
    return f"n={len(ts)} total={sum(r):+.3f} mean={sum(r)/len(r):+.4f} win={sum(1 for x in r if x>0)/len(r):.3f} med_peak={st.median([t['peak_r'] for t in ts if t['peak_r']]):.3f}"
print(f"\nCREATOR SPLIT (repeat = creator with >=2 of his positions, {len(repeat_creators)} creators):")
print(f"  REPEAT-creator positions:   {grp(rep)}")
print(f"  ONE-SHOT-creator positions: {grp(one)}")
print(f"  => recurrence covers {len(rep)}/{len([t for t in tape if t['creator']])} of his positions = recall ceiling for any creator-recurrence rule")
json.dump({"repeat_creators":sorted(repeat_creators)}, open("/root/mirror/his_creators.json","w"))
