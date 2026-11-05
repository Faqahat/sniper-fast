import sys, json, glob
import nlib as L
w = sys.argv[1]; flt = sys.argv[2] if len(sys.argv) > 2 else ""
runs = [r for r in L.RUNS if glob.glob(f"{L.OUT}/n9_{w}_{r}.json")]
tab = {}
for r in runs:
    for x in json.load(open(f"{L.OUT}/n9_{w}_{r}.json"))["rows"]:
        tab.setdefault((x["idea"], x["mode"], x["exit"]), {})[L.DAY[r]] = x
fit = ["10-28", "10-29", "10-30"]
rows = sorted(tab.items(), key=lambda kv: -sum(kv[1].get(d, {}).get("per_day", -99) for d in fit))
for k, v in rows[:int(sys.argv[3]) if len(sys.argv) > 3 else 15]:
    if flt and flt not in " ".join(k): continue
    print(k, " | ".join(f"{d} {x['per_day']:+.1f}/d fills {x['fills']} {x['mSOL_fill']:+.1f} win {x['win_fill']:.0f} wo5 {x['wo5_day']:+.1f} f20 {x['f20_day']:+.1f}" for d, x in v.items()))
