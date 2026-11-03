#!/usr/bin/env python3
"""VERIFY step 1 [MEASURED]: own extraction of every live pre-send window / try / fill / realized P&L from the live run jsonl files.
Independent of the agents' code. Out: /home/moiz/sniper-data/prevent/verify/live.pkl
 per run: cfg (run_start), arms {w: arm rec}, disarm {w: rec}, fills [rec], closes [rec], realized [rec], ata [rec], att_land fee per w,
 attempts per w (send slot, n, lim, p, pos, t), skips counter, stop rec, start/end t."""
import json, sys, os, pickle, collections, glob
from multiprocessing import Pool
OUT = "/home/moiz/sniper-data/prevent/verify"
RUNS = {}
for r in (16, 17, 19, 20, 24, 25, 26, 27, 34, 35, 36, 37, 38):
    RUNS[f"A{r}"] = f"/home/moiz/sniper-data/runs/ams/runs/dip_ams_r{r}.jsonl"
for r in (21, 22, 23, 24, 26, 27, 28):
    RUNS[f"F{r}"] = f"/home/moiz/sniper-data/runs/fra/runs/dip_r{r}.jsonl"
EXTRA = {"A28": "/home/moiz/sniper-data/presend_filter/live28/dip_ams_r28.jsonl"}
for r in (29, 30, 31, 32, 33):
    for p in (f"/home/moiz/sniper-data/haqq_strat/live/dip_ams_r{r}.jsonl",):
        if os.path.exists(p): EXTRA[f"A{r}"] = p
KEEP = (b'"ev":"run_start"', b'"ev":"run_end"', b'"ev":"presend_live_arm"', b'"ev":"presend_live_disarm"', b'"ev":"presend_live_fill"',
        b'"ev":"presend_live_close"', b'"ev":"presend_live_realized"', b'"ev":"presend_live_ata_close"', b'"ev":"presend_live_exit"',
        b'"ev":"presend_live_sell_land"', b'"ev":"presend_live_stop"', b'"ev":"presend_live_skip"', b'"ev":"presend_live_rearm_defer"',
        b'"ev":"presend_attempt_land"', b'"ev":"presend_attempt"', b'"ev":"presend_live_lock"', b'"ev":"presend_live_profit_lock"',
        b'"ev":"presend_live_quiet_stop"', b'"ev":"presend_live_end_check"')


def one(item):
    run, path = item
    D = dict(run=run, path=path, cfg=None, end=None, arms={}, disarm={}, fills=[], closes=[], realized=[], ata=[], exits=[], sells=[],
             stop=[], skips=collections.Counter(), defer=0, att={}, land_fee=collections.Counter(), land_res=collections.Counter(),
             other=collections.Counter(), t_first=None, t_last=None, endchk=[])
    att = collections.defaultdict(list)
    sess = 0
    with open(path, "rb") as fh:
        for raw in fh:
            if not raw.startswith(b"{"): continue
            hit = None
            for k in KEEP:
                if k in raw: hit = k; break
            if hit is None:
                continue
            try: d = json.loads(raw)
            except Exception: D["other"]["bad"] += 1; continue
            ev = d.get("ev"); t = d.get("t")
            if ev == "run_start": sess += 1
            d["_s"] = sess
            if "w" in d: d["w"] = (sess, d["w"])
            if t:
                if D["t_first"] is None: D["t_first"] = t
                D["t_last"] = t
            if ev == "run_start":
                D.setdefault("cfgs", []).append(d)
                if D["cfg"] is None: D["cfg"] = d
            elif ev == "run_end": D["end"] = d
            elif ev == "presend_live_arm": D["arms"][d["w"]] = d
            elif ev == "presend_live_disarm": D["disarm"][d["w"]] = d
            elif ev == "presend_live_fill": D["fills"].append(d)
            elif ev == "presend_live_close": D["closes"].append(d)
            elif ev == "presend_live_realized": D["realized"].append(d)
            elif ev == "presend_live_ata_close": D["ata"].append(d)
            elif ev == "presend_live_exit": D["exits"].append(d)
            elif ev == "presend_live_sell_land": D["sells"].append(d)
            elif ev == "presend_live_stop": D["stop"].append(d)
            elif ev == "presend_live_skip": D["skips"][(d.get("kind", "t2"), d.get("why"))] += 1
            elif ev == "presend_live_rearm_defer": D["defer"] += 1
            elif ev == "presend_live_end_check": D["endchk"].append(d)
            elif ev == "presend_attempt_land":
                w = d.get("w"); fee = d.get("fee") or 0
                D["land_fee"][w] += fee; D["land_res"][(d.get("res"), (d.get("err") or "")[:40])] += 1
                if d.get("sig"): att[w].append(("L", d.get("n"), d.get("res"), fee, d.get("send_slot"), d.get("sig")[:16], d.get("err", "")[:60]))
            elif ev == "presend_attempt":
                w = d.get("w")
                att[w].append(("A", d.get("n"), d.get("slot"), d.get("lim"), d.get("p"), d.get("pos"), d.get("t"), d.get("sig", "")[:16], d.get("min_out"), d.get("vsol"), d.get("vtok"), d.get("path"), d.get("spend")))
            else: D["other"][ev] += 1
    D["att"] = dict(att)
    return run, D


if __name__ == "__main__":
    items = list(RUNS.items()) + list(EXTRA.items())
    with Pool(6) as p:
        res = dict(p.map(one, items))
    pickle.dump(res, open(f"{OUT}/live.pkl", "wb"))
    for run, D in res.items():
        c = D["cfg"] or {}
        pl = (c.get("presend_live") or {})
        lim = c.get("limits") or {}
        print(run, "arms", len(D["arms"]), "fills", len(D["fills"]), "real", len(D["realized"]), "ata", len(D["ata"]), "closes", len(D["closes"]),
              "spend", pl.get("spend"), "rearm", (pl.get("rearm") or {}).get("spend") if (pl.get("rearm") or {}).get("on") else None,
              "lock", lim.get("profit_lock"), "kill", lim.get("kill_switch"), "stop", [s.get("why") for s in D["stop"]], dict(D["other"]))
