#!/usr/bin/env python3
"""STATE step 1 [MEASURED, read-only]: every live pre-send window (T2 + re-arm) of every live run, and the engine shadow (paper) T2 arms
of the shadow-only runs, from the run jsonl files.
  live window = presend_live_arm (+ attempt_land per try: send slot, landed result; fill with its try's send slot; realized; disarm)
  value (SOL at 0.696) = realized x 0.696 / window spend  -  5120 lamports x landed failed tries   [size scaling INFERRED, linear]
  paper (shadow-only runs) = presend_arm + presend_exit rows a/b/c (pnl per row, the engine's own paper; scaled to 0.696 by the run's
  shadow spend if logged, else as logged)  [PAPER]
Out: /home/it/sniper-data/prevent/state/windows.pkl"""
import json, pickle, collections, sys, os, time
OUT = "/home/it/sniper-data/prevent/state"
L = "/home/it/sniper-data/runs"; V = "/home/it/sniper-data/presend_losses/verify/raw"
LIVE = [("FRA", n, f"{L}/fra/runs/dip_r{n}.jsonl") for n in (21, 22, 23, 24, 26, 27, 28)]
LIVE += [("AMS", n, f"{L}/ams/runs/dip_ams_r{n}.jsonl") for n in (16, 17, 19, 20, 24, 25, 26, 27, 34, 35, 36, 37, 38)]
LIVE += [("AMS", n, f"{V}/dip_ams_r{n}.jsonl") for n in (28, 29, 30, 31, 32, 33)]          # live too (QUIET4's 24-run set)
SHADOW = [("AMS", n, f"{L}/ams/runs/dip_ams_r{n}.jsonl") for n in (14, 15, 21, 22, 23)] + [("FRA", n, f"{L}/fra/runs/dip_r{n}.jsonl") for n in (15, 16, 20, 25)]
SIZE = 0.696; FAIL = 5120e-9
OKRES = (None, "unseen", "ok")


def parse(reg, n, path, live=True):
    seg = 0; W = {}; land = {}; att = {}; skips = []; spans = []; seg_t0 = None; last_t = None
    SH = {}; cfg_spend = None
    for line in open(path, errors="ignore"):
        if '"ev":"presend' not in line and '"ev":"run_start"' not in line: continue
        try: d = json.loads(line)
        except Exception: continue
        ev = d.get("ev"); t = d.get("t")
        if isinstance(t, (int, float)) and t > 1e18:
            last_t = t if last_t is None else max(last_t, t)
        if ev == "run_start":
            if seg_t0 is not None and last_t is not None: spans.append((seg_t0, last_t))
            seg += 1; seg_t0 = t if isinstance(t, (int, float)) and t > 1e18 else None
            ps = d.get("presend") or {}
            if isinstance(ps, dict): cfg_spend = ps.get("spend_sol") or ps.get("spend") or cfg_spend
            continue
        if seg == 0: seg = 1
        k = (seg, d.get("w"))
        if ev == "presend_live_arm":
            kind = d.get("kind") or "t2"
            x = dict(reg=reg, run=n, seg=seg, w=d["w"], kind=kind, spend=d.get("spend", 696000000) / 1e9, en_slot=d.get("en_slot"), quiet=d.get("quiet"), v2=d.get("v2"),
                     fills=[], pnl=None, dis=None, tries=[])
            if kind == "rearm":
                dm = d["dump"]; x.update(mint=d["mint"], who=dm["seller"], slot=dm["slot"], idx=dm["idx"], j=dm.get("j", 0), t=dm["t"], age=dm.get("age_slots"),
                                        pct=dm.get("pct"), wsol=dm.get("sol", 0) / 1e9, arm_slot=d.get("arm_slot"), holders=d.get("holders"), dump=dm)
            else:
                tg = d["trig"]; x.update(mint=tg["mint"], who=tg["wallet"], slot=tg["slot"], idx=tg["idx"], j=tg.get("j", 0), t=tg["t"], age=tg.get("age_slots"),
                                        pct=tg.get("pct"), wsol=tg.get("sol", 0) / 1e9, arm_slot=tg["slot"])
            W[k] = x
        elif ev == "presend_attempt":
            if d["sig"] not in att: att[d["sig"]] = (k, d.get("slot"))
        elif ev == "presend_attempt_land":
            o = land.get(d["sig"])
            if o is None or (o[0] == "unseen" and d.get("res") != "unseen"): land[d["sig"]] = (d.get("res"), d.get("send_slot"), k)
        elif ev == "presend_live_fill" and k in W:
            W[k]["fills"].append(dict(slot=d.get("slot"), idx=d.get("idx"), sig=d.get("sig"), sat=d.get("slots_after_trigger"), sas=d.get("slots_after_send"),
                                      p_sign=d.get("p_sign"), pre=d.get("p_entry_pre"), post=d.get("p_entry_post"), lim=d.get("lim"), t=d.get("t"),
                                      after_exit=d.get("after_exit"), sol_in=d.get("sol_in")))
        elif ev == "presend_live_realized" and k in W:
            W[k]["pnl"] = (W[k]["pnl"] or 0) + d["pnl"] / 1e9
        elif ev == "presend_live_disarm" and k in W:
            W[k]["dis"] = dict(why=d.get("why"), slot=d.get("slot"), att=d.get("attempts"), filled=d.get("filled"), qstop=d.get("quiet_stop"))
        elif ev == "presend_live_skip":
            x = dict(seg=seg, why=d.get("why"), kind=d.get("kind") or "t2")
            tg = d.get("trig"); dm = d.get("dump")
            if tg: x.update(mint=tg["mint"], who=tg["wallet"], slot=tg["slot"], idx=tg["idx"], t=tg.get("t"), age=tg.get("age_slots"), pct=tg.get("pct"))
            elif dm: x.update(mint=d.get("mint"), who=dm.get("seller"), slot=dm.get("slot"), idx=dm.get("idx"), t=dm.get("t"), age=dm.get("age_slots"), pct=dm.get("pct"))
            skips.append(x)
        elif ev == "presend_arm":
            SH[k] = dict(reg=reg, run=n, seg=seg, w=d["w"], mint=d["mint"], who=d.get("wallet"), slot=d["slot"], idx=d["idx"], j=d.get("j", 0), t=d.get("t"),
                         age=d.get("age_slots"), pct=d.get("pct"), wsol=d.get("sol", 0) / 1e9, quiet=d.get("quiet"), rows=d.get("rows"), ex={}, fi={})
        elif ev == "presend_fill" and k in SH:
            SH[k]["fi"][d.get("row")] = dict(s_in=d.get("s_in"), sat=d.get("slots_after_trigger"), drop=d.get("drop_pct"))
        elif ev == "presend_exit" and k in SH:
            SH[k]["ex"][d.get("row")] = dict(pnl=d.get("pnl"), net=d.get("net_cheap"), why=d.get("why"))
    if seg_t0 is not None and last_t is not None: spans.append((seg_t0, last_t))
    # tries -> windows
    for sig, (res, ss, kk) in land.items():
        if kk not in W:
            a = att.get(sig)
            if a is None or a[0] not in W: continue
            kk = a[0]
        if ss is None:
            a = att.get(sig); ss = a[1] if a else None
        W[kk]["tries"].append((ss, res))
    fsend = {}
    for sig, (kk, ss) in att.items(): fsend[sig] = ss
    for x in W.values():
        x["n_fail"] = sum(1 for ss, res in x["tries"] if res not in OKRES)
        for f in x["fills"]:
            f["send_slot"] = fsend.get(f["sig"])
            if f["send_slot"] is None and f.get("sas") is not None and f.get("slot") is not None: f["send_slot"] = f["slot"] - f["sas"]
        x["filled"] = bool(x["fills"])
        x["v"] = ((x["pnl"] or 0.0) * SIZE / x["spend"]) - x["n_fail"] * FAIL
    hours = sum((b - a) for a, b in spans) / 3.6e12
    return dict(reg=reg, run=n, live=live, hours=hours, spans=spans, wins=list(W.values()), skips=skips, shadow=list(SH.values()), cfg_spend=cfg_spend)


def main():
    t0 = time.time(); R = {}
    for reg, n, p in LIVE:
        r = parse(reg, n, p, True); R[f"{reg}{n}"] = r
        A = r["wins"]; F = [x for x in A if x["filled"]]
        print(f"{reg} r{n} {r['hours']:.2f}h arms {len(A)} (t2 {sum(1 for x in A if x['kind']=='t2')}, rearm {sum(1 for x in A if x['kind']=='rearm')}) fills {len(F)} "
              f"realized {sum((x['pnl'] or 0) for x in A):+.3f} value@0.696 {sum(x['v'] for x in A):+.3f} shadow {len(r['shadow'])} {time.time()-t0:.0f}s", flush=True)
        for x in r["shadow"]: x.pop("ex", None) if False else None
    for reg, n, p in SHADOW:
        r = parse(reg, n, p, False); R[f"{reg}{n}"] = r
        print(f"SHADOW {reg} r{n} {r['hours']:.2f}h shadow arms {len(r['shadow'])} live arms {len(r['wins'])} spend {r['cfg_spend']} {time.time()-t0:.0f}s", flush=True)
    pickle.dump(R, open(f"{OUT}/windows.pkl", "wb"))


if __name__ == "__main__":
    main()
