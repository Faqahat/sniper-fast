#!/usr/bin/env python3
"""verify2 / v3: my own replay of the FINAL-2 claim. For every pick: placement at L ms from the engine's arrival timeline,
0.5% guard vs the post-bundle price, 0.5 SOL buy (1.5% fewer tokens, 2% overhead), sell all ~8 s after our buy's slot,
variants: base / slip (follower limits) / proafter_slip / nosnip (claim def: SNIPER|PRO buys after us dropped, no slip) /
nosnip_slip.  Tapes: raw (collector events as recorded) and repaired (missing events / slots filled from the curve state).
Placements: opt (after the last tx seen before L) and pess (also every unseen tx before the first tx seen at/after L).
Writes work/v3_res.json (per pick) and prints the totals table."""
import sys, os, json, gzip, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v2core as V

LANDS = [int(x) for x in os.environ.get("LANDS", "75,45").split(",")]
P = V.load_picks(); L = V.load_launches(P); D, O = V.load_scores(P); X = V.load_x1()
SLIP, kinds = V.load_slip(); PRO, SNIPER = V.load_wallet_sets()
slots = {int(k): v for k, v in json.load(gzip.open(os.path.join(V.WORK, "x1_slots.json.gz"), "rt")).items()}
lo, hi = min(slots), max(slots); EMPTY = {s for s in range(lo, hi + 1) if slots.get(s, 0) == 0}
CLAIM = {r["m"]: r for r in json.load(open("/home/moiz/sniper/ops/overnight/core/final2_picks_v3_become_B0.5_tu.json"))}
ENG = json.load(open(os.path.join(V.WORK, "a6_engine.json")))
PMODES = ("opt", "pess", "abs", "abs_pess")
VARS = dict(base=(None, None), slip=("S", None), proafter_slip=("S", "PRO"), nosnip=(None, "SNP"), nosnip_slip=("S", "SNP"))
def dset(k): return None if k is None else (PRO if k == "PRO" else (SNIPER | PRO))
res = []
for m in P:
    c = L[m]; outs = V.parse_outs(O[m]["outs"]) if m in O else []
    r = dict(m=m, name=c.get("name"), bt=c["bt"], slot=c["slot"], in_claim=m in CLAIM)
    for tape in ("raw", "rep"):
        M = V.Mint(m, c, X.get(m, []), repair=(tape == "rep"), empty_slots=EMPTY)
        seen, miss, how = V.match_anchors(M, outs)
        ab = V.absorbed_units(M, ENG.get(m), seen)
        if tape == "raw": r.update(n_outs=len(outs), n_seen=len(seen), n_miss=len(miss), match=dict(how), glued_n=len(M.glued_units), n_absorbed=len(ab))
        else: r.update(n_gap=M.n_gap, n_resid=M.n_resid, gap_sol=round(M.gap_sol, 4))
        for Lm in LANDS:
            for pm in PMODES:
                ins = V.place2(M, seen, Lm, pm.replace("abs_", "").replace("abs", "opt"), ab if pm.startswith("abs") else ())
                key = f"{tape}|{Lm}|{pm}"
                r[key] = {}
                for var, (sk, dk) in VARS.items():
                    o = V.replay(M, ins, slip=SLIP if sk else None, drop_buy=dset(dk))
                    r[key][var] = {k: (round(v, 6) if isinstance(v, float) else v) for k, v in o.items() if k not in ("Vend", "Tend")}
    res.append(r)
json.dump(res, open(os.path.join(V.WORK, "v3_res.json"), "w"))
def tot(rows, key, var):
    v = [x[key][var] for x in rows if x[key][var].get("fill") is not None]
    f = [x for x in v if x["fill"]]
    return sum(x["pnl"] for x in v), len(f), len(v)
print("slip_args kinds:", dict(kinds))
for subset, rows in (("claim's 235", [x for x in res if x["in_claim"]]), ("all 238", res)):
    print(f"\n=== {subset} picks")
    for Lm in LANDS:
        for tape in ("raw", "rep"):
            for pm in PMODES:
                key = f"{tape}|{Lm}|{pm}"
                cells = []
                for var in VARS:
                    s, nf, nv = tot(rows, key, var); cells.append(f"{var} {s:+.2f}")
                s, nf, nv = tot(rows, key, "slip")
                print(f"  L{Lm} {tape:3s} {pm:4s} fills {nf:3d}/{nv:3d} | " + " | ".join(cells))
# claim comparison (raw|opt is the closest to the claim's method)
print("\n=== claim per-variant (file) vs mine, t8")
cl = {}
for Lm in ("75", "45"):
    for var in ("base", "slip", "proafter_slip", "nosnip"):
        v = [x[Lm][var] for x in CLAIM.values() if x[Lm].get(var) is not None]
        cl[(Lm, var)] = (sum(x["pnl"]["t8"] for x in v if x["fill"]) - 0.005 * sum(1 for x in v if not x["fill"]), sum(1 for x in v if x["fill"]))
for Lm in LANDS:
    for var in ("base", "slip", "proafter_slip", "nosnip"):
        rows = [x for x in res if x["in_claim"]]
        a = tot(rows, f"raw|{Lm}|opt", var); b = tot(rows, f"rep|{Lm}|opt", var); c = tot(rows, f"rep|{Lm}|abs", var); d = tot(rows, f"rep|{Lm}|abs_pess", var)
        print(f"  L{Lm} {var:14s} claim {cl[(str(Lm), var)][0]:+.3f} ({cl[(str(Lm), var)][1]}) | mine raw/opt {a[0]:+.3f} ({a[1]}) | rep/opt {b[0]:+.3f} ({b[1]}) | rep/abs {c[0]:+.3f} ({c[1]}) | rep/abs_pess {d[0]:+.3f} ({d[1]})")
