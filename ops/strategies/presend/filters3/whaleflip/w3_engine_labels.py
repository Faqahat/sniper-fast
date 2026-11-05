#!/usr/bin/env python3
"""WHALEFLIP step 3 [MEASURED]: the ENGINE's own crossing trade for every live fill (presend_attempt_land res "ok" of the filling try:
"x" = the trade that pushed the price through our limit, "d" = the dump; user = 8-char signer prefix) -> who dumped into our buy.
T2: x.user == the trigger whale's prefix -> FLIP (the whale's own dump) else OTHER. Re-arm: x.user == the trigger dump seller -> SAME
(the trigger holder kept selling), in the arm's holder list (another >= 6% holder) -> HOLDER, else OTHER.
Agreement with the paper shadow's label (grp/whale_flip.py: shadow row-c presend_fill seller_is_whale on the same trigger).
Out: whaleflip/engine_labels.json (per fill) + printed tables.  usage: w3_engine_labels.py"""
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/whaleflip")
import wlib as W

F = W.load()
h, hp, P = W.hours(F)
rows = []
for f in F:
    fl = f["fills"][0]
    tr = next((t for t in f["tries"] if t["sig"] == fl["sig"]), None)
    L = (tr or {}).get("land") or {}
    x = L.get("x") or {}; d = L.get("d") or {}
    xu = x.get("user"); du = d.get("user")
    if f["kind"] == "t2":
        wh = (f.get("trig") or {}).get("wallet") or ""
        lab = None if not xu else ("FLIP" if wh.startswith(xu) else "OTHER")
        dl = None if not du else ("FLIP" if wh.startswith(du) else "OTHER")
        sh = f.get("shadow")
        shl = "noshadow" if sh is None else ("nofill" if sh == "nofill" else ("FLIP" if sh.get("seller_is_whale") else "OTHER"))
    else:
        wh = (f.get("dump") or {}).get("seller") or ""
        hs = [z["w"] for z in (f.get("holders") or [])]
        lab = None if not xu else ("SAME" if wh.startswith(xu) else ("HOLDER" if any(z.startswith(xu) for z in hs) else "OTHER"))
        dl = None if not du else ("SAME" if wh.startswith(du) else ("HOLDER" if any(z.startswith(du) for z in hs) else "OTHER"))
        shl = None
    rows.append({"run": f["run"], "seg": f["seg"], "period": f["period"], "kind": f["kind"], "w": f["w"], "ses": f["ses"], "mint": f["mint"], "pnl": f["pnl"],
                 "elab": lab, "dlab": dl, "slab": shl, "x_user": xu, "x_sol": x.get("sol"), "x_drop": d.get("drop_pct"), "n_between": L.get("n_between"),
                 "x_slot": x.get("slot"), "x_idx": x.get("idx"), "fill_slot": fl["slot"], "fill_idx": fl["idx"], "t": fl["t"]})
json.dump(rows, open(f"{W.D}/engine_labels.json", "w"))

print("hours per segment:", {k: round(v, 2) for k, v in sorted(h.items())}, "per period:", {k: round(v, 2) for k, v in hp.items()})
for kind in ("t2", "rearm"):
    print(f"\n==== {kind}: ENGINE label (crossing trade x) ====")
    for per in ("DEV", "VAL", "HOLD", None):
        rr = [r for r in rows if r["kind"] == kind and (per is None or r["period"] == per)]
        g = collections.defaultdict(list)
        for r in rr: g[r["elab"]].append(r["pnl"])
        hrs = hp[per] if per else sum(hp.values())
        print(f"  {per or 'ALL'}: " + " | ".join(f"{k}: {W.fmt(W.st(v, hrs))}" for k, v in sorted(g.items(), key=lambda kv: str(kv[0]))))
    print("  per segment:")
    for s in ["r39", "r40", "r41", "r42a", "r42b", "r43", "r44", "r45", "r46", "r47", "r48"]:
        rr = [r for r in rows if r["kind"] == kind and r["seg"] == s]
        g = collections.defaultdict(list)
        for r in rr: g[r["elab"]].append(r["pnl"])
        print(f"    {s:5s} " + " | ".join(f"{k}: n {len(v)} {sum(v):+.3f}" for k, v in sorted(g.items(), key=lambda kv: str(kv[0]))))
    c = collections.Counter((r["elab"], r["dlab"]) for r in rows if r["kind"] == kind)
    print("  x-label vs d-label:", dict(c))
print("\n==== T2: shadow label vs engine label (all runs) ====")
c = collections.Counter((r["slab"], r["elab"]) for r in rows if r["kind"] == "t2")
for k, v in sorted(c.items(), key=lambda kv: str(kv)): print("  shadow", k[0], "-> engine", k[1], v)
both = [r for r in rows if r["kind"] == "t2" and r["slab"] in ("FLIP", "OTHER") and r["elab"]]
print(f"  agreement where both exist: {sum(r['slab'] == r['elab'] for r in both)}/{len(both)}")
print("\n==== T2 by shadow label (the parent's table, same fills) ====")
g = collections.defaultdict(list)
for r in rows:
    if r["kind"] == "t2": g[r["slab"]].append(r["pnl"])
for k, v in g.items(): print(f"  {k}: {W.fmt(W.st(v))}")
