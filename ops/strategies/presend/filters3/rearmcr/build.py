#!/usr/bin/env python3
"""REARM-CREATOR step 3: one row per live re-arm window (arm) + every live fill's realized P&L, per run.
out: /home/it/sniper-data/filters3/rearmcr/rows.json  {"rearm": [...], "fills": [...], "spans": {...}, "shadow": [...], "wins": [...]}"""
import json
D = "/home/it/sniper-data/filters3/rearmcr"
CUT = 1793516400 * 10**9          # 2026-11-01 12:00 PKT = 07:00 UTC
recon = json.load(open(f"{D}/recon.json"))["pct"]
def period(r, t):
    if r <= 41: return "DEV"
    if r == 42: return "DEV" if t < CUT else "VAL"
    return "HOLD"
out = {"rearm": [], "fills": [], "spans": {}, "shadow": [], "wins": []}
for r in range(38, 52):
    arms, real, fill, close, disarm = {}, {}, {}, {}, {}
    sh_fill, sh_exit = {}, {}
    ts = []
    for l in open(f"{D}/ext/r{r}.jsonl"):
        d = json.loads(l); ev = d["ev"]
        if "t" in d and isinstance(d["t"], int): ts.append(d["t"])
        if ev == "presend_live_arm":
            arms[d["w"]] = d
        elif ev == "presend_live_realized":
            real.setdefault(d.get("w"), []).append(d)
        elif ev == "presend_live_fill":
            fill.setdefault(d["w"], d)
        elif ev == "presend_live_close":
            close.setdefault(d.get("w"), d)
        elif ev == "presend_live_disarm":
            disarm[d["w"]] = d
        elif ev == "presend_fill" and d.get("row") == "c":
            sh_fill[(d["mint"], d["w"])] = d
        elif ev == "presend_exit" and d.get("row") == "c":
            sh_exit[(d["mint"], d["w"])] = d
    t0, t1 = min(ts), max(ts)
    if r == 42:
        out["spans"]["r42DEV"] = (t0, CUT); out["spans"]["r42VAL"] = (CUT, t1)
    else:
        out["spans"][f"r{r}"] = (t0, t1)
    for w, a in arms.items():
        rearm = a.get("kind") == "rearm"
        if rearm:
            ta = a["dump"]["t"] + int(a.get("arm_ms_after_dump", 0) * 1e6)
        else:
            ta = a["trig"]["t"]; a["mint"] = a["trig"]["mint"]
        dd = disarm.get(w)
        tend = dd["t"] if dd and "t" in dd else None
        out["wins"].append({"r": r, "w": w, "rearm": rearm, "mint": a["mint"], "ta": ta, "tend": tend, "filled": w in fill})
        if not rearm: continue
        ann = a.get("ann") or {}
        cp = ann.get("cr_pct"); src = "ann"
        if cp is None: cp = recon.get(f"r{r}:{w}"); src = "recon"
        cr = ann.get("creator")
        hold = a.get("holders") or []
        hold_arm = a.get("holders_arm")
        rl = real.get(w, [])
        f = fill.get(w); c = close.get(w)
        pnl = sum(x["pnl"] for x in rl) / 1e9 if rl else None
        tf = f["t"] if f else None
        tx = None
        if c and c.get("sell_land"): tx = c["sell_land"][2]
        out["rearm"].append({"r": r, "w": w, "mint": a["mint"], "ta": ta, "per": period(r, ta), "cr_pct": cp, "src": src, "creator": cr,
            "holders": [(h["w"], h["pct"]) for h in hold], "holders_arm": [(h["w"], h["pct"]) for h in hold_arm] if hold_arm else None,
            "dumper": a["dump"]["seller"], "dump_pct": a["dump"]["pct"], "filled": f is not None, "pnl": pnl, "n_real": len(rl),
            "tf": tf, "tx": tx, "deferred": a.get("deferred")})
    for w, rl in real.items():
        k = "rearm" if (arms.get(w, {}).get("kind") == "rearm") else "t2"
        f = fill.get(w)
        t = f["t"] if f else (arms[w]["dump"]["t"] if k == "rearm" else None)
        out["fills"].append({"r": r, "w": w, "kind": k, "t": t, "pnl": sum(x["pnl"] for x in rl) / 1e9, "mint": rl[0]["mint"]})
    for (m, w), f in sh_fill.items():
        e = sh_exit.get((m, w))
        if e is None: continue
        out["shadow"].append({"r": r, "mint": m, "t": f["m"]["t"], "net": e.get("net_cheap")})
    print(r, "arms", len(arms), "rearm", sum(1 for a in arms.values() if a.get("kind") == "rearm"), "real", len(real), "shadow_c", len(sh_fill), flush=True)
json.dump(out, open(f"{D}/rows.json", "w"))
