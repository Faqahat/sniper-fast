#!/usr/bin/env python3
# SPEED TRUTH step 6 (read-only): per-client comparison with rivals and the cause-specific what-ifs used in the ranking.
import json, sys, os, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tl
import importlib.util
spec = importlib.util.spec_from_file_location("a4", os.path.join(os.path.dirname(os.path.abspath(__file__)), "a4_analysis.py"))
R = json.load(open(f"{tl.OUT}/timeline.json"))
SS = {int(k): v for k, v in json.load(open(f"{tl.OUT}/slot_stats.json")).items()}
def size(s): v = SS.get(s); return v[1] + 1 if v else None
def B400(s, i): return s * tl.SMS + i / max(400, i + 1) * tl.SMS
def Bmix(s, i): return s * tl.SMS + i / max(400, size(s) or 400, i + 1) * tl.SMS
K = {"B400": B400, "Bmix": Bmix}
def our_ms(r, k): c = r["C"]; return k(c["our_slot"], c["our_idx"]) - k(c["dump_slot"], c["dump_idx"])
def g_at(r, t, k):
    c = r["C"]; d0 = k(c["dump_slot"], c["dump_idx"]); ok = True
    for s, i, j, ps, *_ in c["gseq"]:
        if k(s, i) - d0 < t or (s, i) == (c["dump_slot"], c["dump_idx"]): ok = ps
        else: break
    return ok
cls = lambda r: r["L"]["dump_class"]
F = [r for r in R if not r["filled"]]
print("PER CLIENT: us vs rivals (median ms after the dump; B400 | Bmix), fill rate, spill rate")
for c in ("bam", "harmonic", "jito", "fd", "firebam", "rakurai"):
    v = [r for r in R if cls(r) == c]
    if not v: continue
    out = []
    for kn, k in K.items():
        us = np.median([our_ms(r, k) for r in v])
        fr_ = []; hk = []; hq = []
        for r in v:
            d0 = k(r["C"]["dump_slot"], r["C"]["dump_idx"])
            ok = [x for x in r["C"]["rivals"] if x["ok"] and x["user"] != r["C"].get("dump_user") and not (x["ds"] == 0 and x["di"] <= 3)]
            if ok: fr_.append(k(ok[0]["s"], ok[0]["i"]) - d0)
            for w, L in ((tl.HKQ7, hk), (tl.HAQQ, hq)):
                x = next((x for x in r["C"]["rivals"] if x["user"] == w), None)
                if x: L.append(k(x["s"], x["i"]) - d0)
        out.append(f"{kn}: us {us:5.1f} | first reacting rival {np.median(fr_):5.1f} | HkQ7 {np.median(hk) if hk else float('nan'):5.1f} (n={len(hk)}) | haqq {np.median(hq) if hq else float('nan'):5.1f} (n={len(hq)})")
    print(f"  {c:9s} n={len(v):3d} fill {sum(r['filled'] for r in v)/len(v):4.0%} spill {sum(r['C']['slot_delta'] > 0 for r in v)/len(v):4.0%}\n      " + "\n      ".join(out))
print("\nWHAT-IFS on the measured chain guard (failed buys rescued; INFERRED shift)")
for kn, k in K.items():
    bam_med = np.median([our_ms(r, k) for r in R if cls(r) == "bam"])
    for c in ("jito", "harmonic", "rakurai", "fd"):
        fv = [r for r in F if cls(r) == c]
        n = sum(1 for r in fv if g_at(r, min(our_ms(r, k), bam_med), k))
        print(f"  [{kn}] {c:9s} failed {len(fv):3d}: landing at our BAM median ({bam_med:.1f} ms) or earlier would rescue {n}")
    # Jito first slot of the turn
    jt = [r for r in R if cls(r) == "jito" and r["L"]["turn_pos"] == 0]
    print(f"  [{kn}] Jito first slot of the turn: attempts {len(jt)}, spills {sum(r['C']['slot_delta'] > 0 for r in jt)}, fails {sum(not r['filled'] for r in jt)}")
# expected fills under scenarios (each attempt's landing replaced; fills stay fills when the new landing passes)
print("\nSCENARIOS (INFERRED): fills out of 309 if ...")
def scen(name, fn):
    for kn, k in K.items():
        n = sum(1 for r in R if g_at(r, fn(r, k), k))
        print(f"  [{kn}] {name:78s} {n:3d} ({n/len(R):.0%})")
end_of_slot = lambda r, k: (r["C"]["dump_slot"] + 1) * tl.SMS - k(r["C"]["dump_slot"], r["C"]["dump_idx"]) - 0.01
eng = lambda r: max(0.0, r["W"]["first_write"] - 0.2)
scen("as measured (our real landing)", lambda r, k: our_ms(r, k) - 1e-6)
scen("engine fix only (fire on shreds, 0.2 ms to first write)", lambda r, k: our_ms(r, k) - eng(r) if r["C"]["slot_delta"] == 0 else our_ms(r, k))
scen("engine fix + every spill lands at the end of the dump's slot", lambda r, k: (our_ms(r, k) - eng(r)) if r["C"]["slot_delta"] == 0 else end_of_slot(r, k))
bam = {kn: np.median([our_ms(r, k) for r in R if cls(r) == "bam"]) for kn, k in K.items()}
scen("engine fix + Jito/Rakurai attempts land like our BAM median", lambda r, k: (min(our_ms(r, k), bam["B400" if k is B400 else "Bmix"]) if cls(r) in ("jito", "rakurai") else our_ms(r, k)) - (eng(r) if r["C"]["slot_delta"] == 0 else 0))
for dt in (10, 20):
    scen(f"engine fix + same-slot send leg {dt} ms faster + spills at end of slot", lambda r, k, dt=dt: max(0.0, our_ms(r, k) - eng(r) - dt) if r["C"]["slot_delta"] == 0 else end_of_slot(r, k))
for d in (20, 30, 35):
    scen(f"every buy lands {d} ms after the dump", lambda r, k, d=d: float(d))
