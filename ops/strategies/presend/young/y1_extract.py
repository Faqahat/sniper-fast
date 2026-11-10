#!/usr/bin/env python3
"""YOUNG step 1: per-trigger table from run .jsonl (read-only copies).
One row per shadow presend_arm (every trigger the engine saw, incl. age-0 skips), joined with the live arm/skip,
live attempts (landing positions), live fill, live sell, live realized P&L and the shadow row-a fill/exit.
Out: /home/it/sniper-data/presend_young/trig.json"""
import json, glob, os, sys, collections
OUT = "/home/it/sniper-data/presend_young"
RUNS = []
for f in sorted(glob.glob("/home/it/sniper-data/runs/fra/runs/dip_r*.jsonl")):
    n = int(os.path.basename(f)[5:-6])
    if 21 <= n <= 28: RUNS.append(("FRA", f"r{n}", f))
amsdir = "/home/it/sniper-data/runs/ams/runs"
for n in range(16, 38):
    f = f"{amsdir}/dip_ams_r{n}.jsonl"
    for alt in (f"/home/it/sniper-data/presend_losses/verify/raw/dip_ams_r{n}.jsonl", f"{OUT}/dip_ams_r{n}.jsonl"):
        if not os.path.exists(f) and os.path.exists(alt): f = alt
    if os.path.exists(f): RUNS.append(("AMS", f"r{n}", f))


def run(reg, rn, fn):
    arms = []; live = {}; byk = collections.defaultdict(list)
    size = None; t0 = t1 = None
    cur_live = {}  # mint -> live arm key (trig sig)
    att = collections.defaultdict(list)
    fills = collections.defaultdict(list); sells = collections.defaultdict(list); real = collections.defaultdict(list)
    sh_fill = {}; sh_exit = {}; cur_sh = {}
    closes = collections.defaultdict(list)
    for line in open(fn):
        if '"ev":"presend' not in line and '"ev":"run_' not in line: continue
        try: r = json.loads(line)
        except Exception: continue
        ev = r.get("ev"); t = r.get("t")
        if t: t0 = t if t0 is None else min(t0, t); t1 = t if t1 is None else max(t1, t)
        if ev == "presend_arm":
            r["_k"] = r["sig"]; arms.append(r); cur_sh[r["mint"]] = r["sig"]
        elif ev == "presend_fill" and r.get("row") == "a":
            k = cur_sh.get(r["mint"]); sh_fill.setdefault(k, r)
        elif ev == "presend_exit" and r.get("row") == "a":
            k = cur_sh.get(r["mint"]); sh_exit.setdefault(k, r)
        elif ev in ("presend_live_arm", "presend_live_skip"):
            tr = r["trig"]; live[tr["sig"]] = {"st": "armed" if ev == "presend_live_arm" else r["why"], "quiet_skip": r.get("quiet_skip"),
                                               "spend": r.get("spend"), "lim0": r.get("lim0")}
            if ev == "presend_live_arm":
                cur_live[tr["mint"]] = tr["sig"]
                if r.get("spend"): size = r["spend"] / 1e9
        elif ev == "presend_attempt_land":
            k = cur_live.get(r["mint"])
            if k: att[k].append((r.get("slot"), r.get("idx"), r.get("err") or "", r.get("fee") or 0, r.get("send_slot")))
        elif ev == "presend_live_disarm":
            k = cur_live.get(r["mint"])
            if k and k in live: live[k]["n_att"] = r.get("attempts"); live[k]["filled"] = r.get("filled"); live[k]["dis_why"] = r.get("why")
        elif ev == "presend_live_fill":
            k = cur_live.get(r["mint"]); fills[k].append({x: r.get(x) for x in ("slot", "idx", "sol_in", "tokens", "t", "tip", "fee", "client", "lim", "n", "after_exit")})
        elif ev == "presend_live_close":
            k = cur_live.get(r["mint"]); closes[k].append({x: r.get(x) for x in ("buys", "sell_lands", "exit_why", "exit_slot", "result", "rounds", "merged", "held_s", "fee")})
        elif ev == "presend_live_realized":
            k = cur_live.get(r["mint"]); real[k].append(r.get("pnl"))
    rows = []
    for a in arms:
        k = a["_k"]; L = live.get(k, {})
        rows.append({"reg": reg, "run": rn, "sig": k, "mint": a["mint"], "wallet": a["wallet"], "slot": a["slot"], "idx": a["idx"], "j": a.get("j", 0),
                     "t": a["t"], "age": a["age_slots"], "pct": a["pct"], "sol": a["sol"], "tok": a["tok"], "vsol": a["vsol"], "vtok": a["vtok"],
                     "q_all4": (a.get("quiet") or {}).get("all4"), "quiet": a.get("quiet"), "live": L.get("st"), "quiet_skip": L.get("quiet_skip"),
                     "lim0": L.get("lim0"), "spend": L.get("spend"), "n_att": L.get("n_att"), "att": att.get(k, []),
                     "lfill": fills.get(k, []), "close": closes.get(k, []), "real": real.get(k, []),
                     "sh_fill": sh_fill.get(k), "sh_exit": sh_exit.get(k)})
    return {"reg": reg, "run": rn, "t0": t0, "t1": t1, "size": size}, rows


if __name__ == "__main__":
    allrows = []; meta = []
    for reg, rn, fn in RUNS:
        m, rows = run(reg, rn, fn)
        nl = sum(1 for r in rows if r["live"] == "armed")
        if nl == 0: continue
        meta.append(m); allrows += rows
        print(reg, rn, len(rows), "live armed", nl, "fills", sum(len(r["lfill"]) for r in rows), "real", round(sum(sum(x for x in r["real"] if x) for r in rows) / 1e9, 3), flush=True)
    for r in allrows:
        for x in ("sh_fill",):
            if r[x]: r[x] = {k: r[x].get(k) for k in ("entry", "m", "lim", "ref", "s_in", "seller_is_whale", "slots_after_trigger", "drop_pct")}
    json.dump({"meta": meta, "rows": allrows}, open(f"{OUT}/trig.json", "w"))
