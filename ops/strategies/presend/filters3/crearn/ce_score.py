#!/usr/bin/env python3
"""CR-EARNBACK: score the variants vs the baseline (the current rule) on DEV / VAL / HOLD (r43–r46 gate-off replay + r47–r50 live gate)."""
import sys, pickle, collections, json, itertools
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/filters3/crearn")
import ce_lib as L, ce_sim as S
W = pickle.load(open(f"{L.D0}/windows.pkl", "rb"))          # creators of re-arm skips resolved by ce_validate.py
SF = S.seed_full()
DT, G3 = "dtrzJPj7yDdvm6eRqBAgxsK2sMJeD9HhBEBB3XMedXy", None
for w in W:
    if w["creator"] and w["creator"].startswith("G3eWaBWu"): G3 = w["creator"]
V = {"BASE": {}, "OFF (no gate)": {"on": False}}
for k in (0.3, 0.5, 1.0, "cal"): V[f"A k={k}"] = {"credit": k}
for h in (24, 48, 72, 168): V[f"B win {h}h"] = {"win_h": h}
for h in (24, 72): V[f"B half-life {h}h"] = {"hl": h}
for k, h in itertools.product((0.3, 0.5, "cal"), (48, 72, 168)): V[f"C k={k} win {h}h"] = {"credit": k, "win_h": h}
for x, f in itertools.product((6, 12, 24), (0.5, 0.25)): V[f"D probation {x}h f={f}"] = {"prob": (x, f)}
for kk, k in itertools.product((5, 10), (None, 0.5, "cal")): V[f"L last {kk}" + (f" k={k}" if k else "")] = {"lastk": kk, "credit": k}
SEGS = {"DEV": lambda w: w["per"] == "DEV", "VAL": lambda w: w["per"] == "VAL", "HOLD": lambda w: w["per"] == "HOLD",
        "H43-46": lambda w: w["per"] == "HOLD" and w["run"] not in L.GATE_RUNS, "H47-50": lambda w: w["run"] in L.GATE_RUNS}
NORESET = "--noreset" in sys.argv
if NORESET:
    for v in V.values(): v["noreset"] = True
base, _ = S.run(W, V["BASE"], SF)
res = {}
def score(name, out):
    d = {}
    for sn, sf in SEGS.items():
        diffs = [(o[2] - b[2], o, b) for o, b in zip(out, base) if sf(o[0]) and (o[1] != b[1] or o[2] != b[2])]
        v = sorted(x[0] for x in diffs)
        tot = sum(v); top = sum(x for x in sorted(v, reverse=True)[:5] if x > 0)
        unb = [x for x in diffs if x[2][1] == "block" and x[1][1] != "block"]
        blk = [x for x in diffs if x[2][1] != "block" and x[1][1] == "block"]
        d[sn] = {"net": round(tot, 3), "wo5": round(tot - top, 3), "unblocked_w": len(unb), "blocked_w": len(blk),
                 "unb_cr": len({x[1][0]["creator"] for x in unb}), "unb_rearm_skip": sum(1 for x in unb if x[1][0]["live"] is None and x[1][0]["kind"] == "rearm"),
                 "unb_paper": sum(1 for x in unb if x[1][0]["live"] is None and x[1][0]["kind"] == "t2")}
    for tag, c in (("dtrz", DT), ("G3eW", G3)):
        ws = [(o, b) for o, b in zip(out, base) if o[0]["creator"] == c]
        d[tag] = {"traded": sum(1 for o, b in ws if o[1] != "block"), "base_traded": sum(1 for o, b in ws if b[1] != "block"),
                  "val": round(sum(o[2] for o, b in ws), 3), "base_val": round(sum(b[2] for o, b in ws), 3),
                  "h_traded": sum(1 for o, b in ws if o[1] != "block" and o[0]["per"] == "HOLD"),
                  "h_base": sum(1 for o, b in ws if b[1] != "block" and o[0]["per"] == "HOLD"),
                  "end": next((o[1] for o, b in reversed(ws)), None)}
    return d
lines = []
hdr = f"{'variant':26s} | {'DEV net':>8s} {'w/o5':>7s} | {'VAL net':>8s} {'w/o5':>7s} | {'HOLD net':>8s} {'w/o5':>7s} unb(w/cr/rs) | H47-50 net (paper w) | dtrz traded/base val | G3eW traded/base val"
print(hdr); lines.append(hdr)
for name, v in V.items():
    out, led = S.run(W, v, SF)
    d = score(name, out); res[name] = d
    ok = all(d[s]["net"] > 0 and d[s]["wo5"] > 0 for s in ("DEV", "VAL", "HOLD"))
    ln = (f"{('PASS ' if ok else '     ') + name:26s} | {d['DEV']['net']:+8.3f} {d['DEV']['wo5']:+7.3f} | {d['VAL']['net']:+8.3f} {d['VAL']['wo5']:+7.3f} | "
          f"{d['HOLD']['net']:+8.3f} {d['HOLD']['wo5']:+7.3f} {d['HOLD']['unblocked_w']:3d}/{d['HOLD']['unb_cr']:2d}/{d['HOLD']['unb_rearm_skip']:2d} b{d['HOLD']['blocked_w']:3d} | "
          f"{d['H47-50']['net']:+7.3f} ({d['H47-50']['unb_paper']:2d}) | {d['dtrz']['traded']:3d}/{d['dtrz']['base_traded']:3d} {d['dtrz']['val']:+.3f}/{d['dtrz']['base_val']:+.3f} {d['dtrz']['end']} | "
          f"{d['G3eW']['traded']:2d}/{d['G3eW']['base_traded']:2d} {d['G3eW']['val']:+.3f}/{d['G3eW']['base_val']:+.3f} {d['G3eW']['end']}")
    print(ln); lines.append(ln)
sfx = "_noreset" if NORESET else ""
json.dump(res, open(f"{L.D0}/ce_score{sfx}.json", "w"), indent=1)
open(f"{L.D0}/ce_score{sfx}.txt", "w").write("\n".join(lines) + "\n")
