#!/usr/bin/env python3
"""GUARDS step 12 [MEASURED live fills; creator = create record where a local table has it, else the HEURISTIC 'user of the mint's first
tape trade if it is in the create slot' (accuracy measured on the r37/r38 fills that have create records)]: post-hoc guard idea from the
STATE agent - the creator's remaining balance at our landing must be < Z% of supply. DIRECT effect per run, all 20 live runs.
NOT pre-registered (added after PREREG; r37 was looked at first via g11) -> at best a LEAD.
usage: g12_creator.py"""
import pickle, json, collections, sys
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/prevent/guards")
import glib as G
OUT = "/home/moiz/sniper-data/prevent/guards"
R = pickle.load(open(f"{OUT}/feats.pkl", "rb"))
tapes = pickle.load(open(f"{OUT}/tapes_fills.pkl", "rb"))
cre = {}
for tab in ("/home/moiz/sniper-data/presend_quiet4/tab37", "/home/moiz/sniper-data/prevent/guards/tab_tail", "/home/moiz/sniper-data/multiarm/tab38", "/home/moiz/sniper-data/prevent/guards/tab_t38",
            "/home/moiz/sniper-data/paper_audit/tab36", "/home/moiz/sniper-data/paper_audit/tab"):
    try:
        for m, c in json.load(open(f"{tab}/creates.json")).items(): cre[m] = c.get("creator")
    except Exception as e: print("skip", tab, e)
ORDER = ["F21", "F22", "F23", "F24", "F26", "F27", "F28", "A16", "A17", "A19", "A20", "A24", "A25", "A26", "A27", "A34", "A35", "A36", "A37", "A38"]
FIXC = 0.003524
def sc(o): return (o["pnl"] + FIXC) * 0.696 / (o["spend"] / 1e9) - FIXC
def heur(o):
    rows = tapes[o["mint"]]
    if not rows: return None
    cs = (o["trig_slot"] - o["age"]) if o["age"] is not None and o["trig_slot"] else None
    r0 = rows[0]
    return r0[8] if (cs is not None and r0[0] == cs and r0[3]) else None
ok = n = 0
for o in R:
    c = cre.get(o["mint"])
    if c: n += 1; ok += (heur(o) == c)
print(f"heuristic creator == create record on {ok}/{n} fills with a record")
lines = [f"creator heuristic accuracy {ok}/{n}", f"{'run':4s} {'fills':>5s} {'known':>5s} | " + " | ".join(f"Z{Z}% blk  gain@0.696" for Z in (1, 3))]
res = {}
for run in ORDER:
    v = [o for o in R if o["run"] == run]
    row = [run, len(v)]
    known = 0; out = {}
    for Z in (1.0, 3.0):
        blk = []
        for o in v:
            c = cre.get(o["mint"]) or heur(o)
            if not c: continue
            if Z == 1.0: known += 1
            H = G.Hold(tapes[o["mint"]])
            if H.bal_before(c, H.key(o["slot"], o["idx"], 0)) >= Z / 100 * G.SUP: blk.append(o)
        out[Z] = (len(blk), -sum(sc(o) for o in blk))
    res[run] = {"fills": len(v), "known": known, "Z1": out[1.0], "Z3": out[3.0]}
    lines.append(f"{run:4s} {len(v):5d} {known:5d} | " + " | ".join(f"{out[Z][0]:6d} {out[Z][1]:+9.3f}" for Z in (1.0, 3.0)))
pk = [r for r in ORDER if r not in ("A37", "A38")]
for Z in ("Z1", "Z3"):
    g = sum(res[r][Z][1] for r in pk); p = sum(1 for r in pk if res[r][Z][1] > 1e-9); m = sum(1 for r in pk if res[r][Z][1] < -1e-9)
    lines.append(f"creator {Z}: PICK gain {g:+.3f} (runs +{p}/-{m}), r37 {res['A37'][Z][1]:+.3f}, r38 {res['A38'][Z][1]:+.3f}")
open(f"{OUT}/creator.txt", "w").write("\n".join(lines) + "\n"); json.dump(res, open(f"{OUT}/creator.json", "w"), indent=1)
print("\n".join(lines))
