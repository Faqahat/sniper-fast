#!/usr/bin/env python3
# READ-ONLY, offline: summarize q6_res.json -> q6_summary.json + q6_summary.txt
import json, collections, statistics as stt, sys
D = json.load(open("q6_res.json")); RES = D["res"]; SETS = json.load(open("sets.json"))["sets"]
MODES = ["L45", "L75", "D0.15", "D1", "D2", "D5"]; EXITS = ["eos1", "t1", "t2", "t5", "t10"]
VN = {"v0": "no slip", "v1": "slip", "v2": "slip, FiFawH after us removed", "v3": "slip, ALL fast snipers after us removed",
      "v4": "slip, top-10 after-us buyers removed", "v5": "slip, fast snipers + top-10 removed"}
print("errors:", sum(1 for r in RES.values() if r.get("error")), collections.Counter(r.get("error", "")[:40] for r in RES.values() if r.get("error")).most_common(3))
out = {}; lines = []
def agg(sn, mode, vkey, ex):
    tot = {"R1": 0.0, "R2": 0.0}; n = {"R1": 0, "R2": 0}; fills = {"R1": 0, "R2": 0}; pn = []; zero = 0; nf = 0
    for m in SETS[sn]:
        r = RES.get(m)
        if not r or mode not in r["modes"]: continue
        d = r["modes"][mode]; run = r["run"]
        if not d["ok"]:
            n[run] += 1; tot[run] -= 0.005; continue
        v = d.get("v", {}).get(vkey)
        if v is None: continue
        n[run] += 1; fills[run] += 1; tot[run] += v[ex][0]; pn.append(v[ex][0]); nf += 1; zero += v[ex][1] <= 0
    return dict(n=n, fills=fills, tot={k: round(v, 3) for k, v in tot.items()}, total=round(tot["R1"] + tot["R2"], 3),
                mean=round(stt.mean(pn), 4) if pn else None, win=round(sum(x > 0 for x in pn) / len(pn), 3) if pn else None,
                zero_share=round(zero / nf, 3) if nf else None)
for sn in SETS:
    out[sn] = {}
    lines.append(f"\n=== {sn} ({len(SETS[sn])} launches in set) ===")
    for mode in MODES:
        out[sn][mode] = {}
        for vk in ("v0", "v1", "v2", "v3", "v4", "v5"):
            key = vk if vk in ("v0", "v1", "v2", "v3") else f"{vk}|{sn}"
            out[sn][mode][vk] = {ex: agg(sn, mode, key, ex) for ex in EXITS}
        a = out[sn][mode]["v0"]["eos1"]
        lines.append(f"  {mode}: simulated R1 {a['n']['R1']} / R2 {a['n']['R2']}, fills R1 {a['fills']['R1']} / R2 {a['fills']['R2']}")
        for vk in ("v0", "v1", "v2", "v3", "v4", "v5"):
            cells = []
            for ex in EXITS:
                x = out[sn][mode][vk][ex]
                cells.append(f"{ex}: {x['total']:+6.2f} (R1 {x['tot']['R1']:+.2f}/R2 {x['tot']['R2']:+.2f}) z{x['zero_share'] if x['zero_share'] is not None else '-'}")
            lines.append(f"     {vk:3} {VN[vk][:34]:34} " + " | ".join(cells))
open("q6_summary.txt", "w").write("\n".join(lines)); json.dump(out, open("q6_summary.json", "w"))
print("\n".join(lines))
