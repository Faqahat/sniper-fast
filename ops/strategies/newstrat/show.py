import sys, json, glob
import nlib as L
# usage: show.py PREFIX [D]  -> table idea/exit rows across available runs (per_day; n; per; win; wo5; f20)
pre = sys.argv[1]; Dsel = int(sys.argv[2]) if len(sys.argv) > 2 else 70
runs = [r for r in L.RUNS if glob.glob(f"{L.OUT}/{pre}_{r}.json")]
tab = {}
for r in runs:
    d = json.load(open(f"{L.OUT}/{pre}_{r}.json"))
    for x in d["rows"]:
        if x["D"] != Dsel: continue
        tab.setdefault((x["idea"], x["exit"]), {})[r] = x
print("D", Dsel, "| idea exit | " + " | ".join(L.DAY[r] + " /day (n, mSOL/trip, win%, w/o5 SOL, f20/day)" for r in runs))
for k in sorted(tab):
    cells = []
    for r in runs:
        x = tab[k].get(r)
        cells.append("-" if x is None else f"{x['per_day']:+.1f} ({x['n']}, {x['per']:+.1f}, {x['win']:.0f}, {x['wo5']:+.2f}, {x.get('f20_day', 0):+.1f})")
    print(k[0], k[1], "|", " | ".join(cells))
