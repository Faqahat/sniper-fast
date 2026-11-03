#!/usr/bin/env python3
"""GUARDS step 1 [MEASURED, read-only]: every LIVE pre-send fill of the 20 live runs (T2 and dip26 re-arm) with what a guard needs:
the window's trigger (T2: the whale = trigger wallet, its balance at the trigger; re-arm: the dump seller + the holders the engine saw),
the filled try's SIGNING position (presend_attempt "pos" = the newest trade the engine had seen when it signed) and its LANDING
position (presend_live_fill slot, idx), the realized wallet P&L (presend_live_realized), the exit and the sell landing.
Out: /home/moiz/sniper-data/prevent/guards/fills.pkl  (list of dicts) + per-run window counts.
usage: g1_fills.py"""
import json, pickle, collections, os
A = "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r{}.jsonl"
F = "/home/moiz/sniper-data/runs/fra/runs/dip_r{}.jsonl"
RUNS = [("AMS", r, A.format(r)) for r in (16, 17, 19, 20, 24, 25, 26, 27, 34, 35, 36, 37, 38)] + [("FRA", r, F.format(r)) for r in (21, 22, 23, 24, 26, 27, 28)]
OUT = "/home/moiz/sniper-data/prevent/guards"


def scan(reg, run, fn):
    ses = -1; cfg = []; arms = {}; atts = {}; fills = {}; real = collections.defaultdict(list); close = {}; sells = collections.defaultdict(list); nwin = collections.Counter()
    with open(fn, "rb") as f:
        for raw in f:
            if b'"ev":"presend_' not in raw and b'"ev":"run_start"' not in raw: continue
            try: r = json.loads(raw)
            except Exception: continue
            e = r.get("ev"); kind = r.get("kind") or "t2"
            if e == "run_start":
                ses += 1; cfg.append(r.get("presend_live")); continue
            if ses < 0: ses = 0
            if e == "presend_attempt":
                atts[r["sig"]] = {k: r.get(k) for k in ("pos", "t", "slot", "n", "vsol", "vtok", "lim", "min_out", "spend", "w", "path", "deadline")} | {"kind": kind, "ses": ses}
            elif e == "presend_live_arm":
                k = (ses, kind, r["w"]); nwin[kind] += 1
                arms[k] = {"mint": r.get("mint") or r["trig"]["mint"], "trig": r.get("trig"), "dump": r.get("dump"), "holders": r.get("holders"), "en_slot": r.get("en_slot"),
                           "spend": r.get("spend"), "check_slot": r.get("check_slot"), "arm_slot": r.get("arm_slot"), "quiet": r.get("quiet")}
            elif e == "presend_live_fill":
                k = (ses, kind, r.get("w"))
                fills.setdefault(k, r)
            elif e == "presend_live_realized":
                real[(ses, kind, r.get("w"))].append(r.get("pnl") or 0)
            elif e == "presend_live_close":
                close[(ses, kind, r.get("w"))] = {x: r.get(x) for x in ("exit_why", "sell_land", "sell_lands", "held_s", "curve_pnl", "rounds", "merged", "land")}
            elif e == "presend_live_sell_land":
                sells[(ses, kind, r.get("w"))].append((r.get("slot"), r.get("idx"), r.get("t"), r.get("sol")))
    out = []
    for k, fl in fills.items():
        a = arms.get(k)
        if a is None: continue
        at = atts.get(fl["sig"], {})
        tg = a["trig"] or {}; dp = a["dump"] or {}
        whale = tg.get("wallet") if k[1] == "t2" else dp.get("seller")
        out.append({"reg": reg, "run": f"{reg[0]}{run}", "ses": k[0], "kind": k[1], "w": k[2], "mint": a["mint"], "whale": whale,
                    "trig_slot": tg.get("slot") if k[1] == "t2" else dp.get("slot"), "trig_idx": tg.get("idx") if k[1] == "t2" else dp.get("idx"),
                    "trig_j": (tg.get("j") if k[1] == "t2" else dp.get("j")) or 0, "trig_bal": tg.get("bal"), "trig_pct": tg.get("pct") if k[1] == "t2" else dp.get("pct"),
                    "age": tg.get("age_slots") if k[1] == "t2" else dp.get("age_slots"), "trig_t": tg.get("t") if k[1] == "t2" else dp.get("t"),
                    "holders_arm": a["holders"], "en_slot": a["en_slot"], "check_slot": a["check_slot"],
                    "sig": fl["sig"], "slot": fl["slot"], "idx": fl["idx"], "t": fl["t"], "n": fl.get("n"), "p_sign": fl.get("p_sign"), "lim": fl.get("lim"),
                    "p_pre": fl.get("p_entry_pre"), "sat": fl.get("slots_after_trigger"), "path": fl.get("path"), "client": fl.get("client"),
                    "spend": fl.get("spend") or at.get("spend") or a["spend"], "sol_in": fl.get("sol_in"), "tokens": fl.get("tokens"),
                    "sign_pos": at.get("pos"), "sign_t": at.get("t"), "sign_slot": at.get("slot"), "sign_v": at.get("vsol"), "sign_tok": at.get("vtok"),
                    "pnl": sum(real.get(k, [])) / 1e9 if k in real else None, "close": close.get(k), "sells": sells.get(k, [])})
    return out, nwin, cfg


if __name__ == "__main__":
    allf = []; meta = {}
    for reg, run, fn in RUNS:
        if not os.path.exists(fn): print("MISSING", fn); continue
        o, nwin, cfg = scan(reg, run, fn)
        allf += o
        c = cfg[-1] or {}
        meta[f"{reg[0]}{run}"] = {"windows": dict(nwin), "fills": len(o), "fills_with_pnl": sum(1 for x in o if x["pnl"] is not None),
                                  "pnl": round(sum(x["pnl"] or 0 for x in o), 4), "no_sign_pos": sum(1 for x in o if not x["sign_pos"]),
                                  "cfg": {k: c.get(k) for k in ("spend", "k", "drop", "tp", "sl", "exit_ms", "window_slots")}}
        print(f"{reg[0]}{run}", meta[f"{reg[0]}{run}"], flush=True)
    pickle.dump(allf, open(f"{OUT}/fills.pkl", "wb"))
    json.dump(meta, open(f"{OUT}/fills_meta.json", "w"), indent=1)
    print("total fills", len(allf))
