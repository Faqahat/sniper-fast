#!/usr/bin/env python3
"""HAQQ_STRAT step 2 (read-only): our live engine records in the haqq window, trimmed to what the speed / skip study needs.
Runs: AMS r24-r33 (EgxfYgEb), FRA r23-r25 (2g7rYv7y). Copies of r29-r33 were read with `sudo cat` from the AMS edge.
Out: /home/moiz/sniper-data/haqq_strat/live.pkl  {run: {"start","end","regular":[...],"presend":[...],"dumps":{sig:..},
      "picks":{sig:..}, "pick_skip":{sig:why}, "arms":[...], "arm_skips":[...]}}"""
import json, pickle, glob, os
D = "/home/moiz/sniper-data"
RUNS = {f"AMS{n}": f"{D}/runs/ams/runs/dip_ams_r{n}.jsonl" for n in (24, 25, 26, 27)}
RUNS["AMS28"] = f"{D}/presend_filter/live28/dip_ams_r28.jsonl"
RUNS.update({f"AMS{n}": f"{D}/haqq_strat/live/dip_ams_r{n}.jsonl" for n in (29, 30, 31, 32, 33)})
RUNS.update({f"FRA{n}": f"{D}/runs/fra/runs/dip_r{n}.jsonl" for n in (23, 24, 25)})


def tsec(t): return t / 1e9 if t and t > 1e15 else t


def main():
    out = {}
    for run, f in RUNS.items():
        R = dict(start=None, end=None, cfg=None, dumps={}, picks={}, pick_skip={}, fires={}, land={}, failed={}, poll={}, timing={},
                 closes={}, exits={}, sell_land={}, pattempts=[], pfills={}, pcloses={}, prealized={}, arms=[], arm_skips=[], pdisarm=[])
        for l in open(f):
            try: d = json.loads(l)
            except Exception: continue
            e = d.get("ev"); t = tsec(d.get("t"))
            if t and t > 1.7e9:
                R["start"] = R["start"] or t; R["end"] = t
            if e == "run_start": R["cfg"] = {k: d.get(k) for k in ("spend", "guard", "hold_slots", "sl", "tp", "presend_live", "max_inflight", "wallet")}
            elif e == "dump": R["dumps"][d["sig"]] = dict(mint=d["mint"], slot=d["slot"], idx=d["idx"], drop=d.get("drop_pct"), m2=d.get("m2"),
                                                          m2_pick=d.get("m2_pick"), pass_=d.get("pass"), imit=d.get("imit_pass"), dev=d.get("dev"),
                                                          age=d.get("age"), sell=d.get("sell"), t=t, launch_ok=d.get("launch_ok"))
            elif e == "pick": R["picks"][d["sig"]] = dict(mint=d["mint"], client=d.get("client"), route=d.get("route"), t=t)
            elif e == "pick_skip": R["pick_skip"][d["sig"]] = d.get("why")
            elif e == "fire":
                sigs = [d["buy_sig"]] + [p["sig"] for p in (d.get("nonce") or {}).get("per_path", [])] + [v["sig"] for v in d.get("variants", [])]
                R["fires"][d["buy_sig"]] = dict(mint=d["mint"], dump_sig=d.get("dump_sig"), client=d.get("client"), dev=d.get("dev"),
                                                 sigs=list(dict.fromkeys(sigs)), t=t, decision_us=d.get("decision_us"))
            elif e == "buy_land": R["land"][d["sig"]] = dict(mint=d["mint"], slot=d["slot"], idx=d["idx"], rx_ms=d.get("rx_ms_after_dump"),
                                                             slots_after=d.get("slots_after_dump"), fee=d.get("fee"), sol=d.get("sol"),
                                                             tip=(d.get("variant") or {}).get("tip"), path=(d.get("variant") or {}).get("paths"), t=t)
            elif e == "buy_failed": R["failed"][d["sig"]] = dict(mint=d["mint"], slot=d.get("slot"), path=(d.get("variant") or {}).get("paths"))
            elif e == "land_poll": R["poll"][d["sig"]] = dict(ok=d.get("ok"), err=d.get("err"), slot=d.get("land_slot"))
            elif e == "timing" and d.get("kind") == "fire":
                c2 = d.get("clock2") or {}
                R["timing"][d.get("buy_sig")] = dict(seen=d.get("buy_sig_seen"), dslot=c2.get("dump_slot"), didx=c2.get("dump_idx"),
                                                     bslot=c2.get("buy_slot"), bidx=c2.get("buy_idx"), land_ms=c2.get("land_ms_bmix"),
                                                     fire_to_seen=d.get("fire_to_seen_ms"), reaction=d.get("reaction_ms"))
            elif e == "close": R["closes"][d.get("buy_sig")] = dict(result=d.get("result"), mint=d["mint"], client=d.get("client"),
                                                                     dump_sig=d.get("dump_sig"), err=d.get("err"), route=d.get("route"))
            elif e == "sell_land": R["sell_land"][d["mint"] + str(d["slot"])] = dict(mint=d["mint"], sol=d.get("sol"), fee=d.get("fee"), slot=d["slot"])
            elif e == "presend_attempt_land":
                dd = d.get("d") or {}
                R["pattempts"].append(dict(mint=d["mint"], sig=d["sig"], slot=d.get("slot"), idx=d.get("idx"), res=d.get("res"), err=d.get("err"),
                                           ms_a=d.get("ms_after_d_a"), ms_rx=d.get("ms_after_d_rx"), n_between=d.get("n_between"),
                                           client=d.get("client"), path=d.get("path"), fee=d.get("fee"), sas=d.get("slots_after_send"),
                                           dslot=dd.get("slot"), didx=dd.get("idx"), dsig8=dd.get("sig8"), ddrop=dd.get("drop_pct"), dsol=dd.get("sol"),
                                           n=d.get("n"), t=t))
            elif e == "presend_live_fill": R["pfills"][d["sig"]] = dict(mint=d["mint"], slot=d["slot"], idx=d["idx"], client=d.get("client"),
                                                                        ms_send_to_rx=d.get("ms_send_to_rx"), sat=d.get("slots_after_trigger"),
                                                                        tip=d.get("tip"), fee=d.get("fee"), sol=d.get("sol_in"), t=t)
            elif e == "presend_live_close": R["pcloses"][d.get("buy_sig")] = dict(mint=d["mint"], tips=d.get("tips"), fee=d.get("fee"),
                                                                                   exit_why=d.get("exit_why"), held_s=d.get("held_s"))
            elif e == "presend_live_realized": R["prealized"][d["mint"] + str(d.get("pid"))] = dict(mint=d["mint"], pnl=d.get("pnl"))
            elif e == "presend_live_arm": R["arms"].append(dict(mint=d["trig"]["mint"], slot=d["trig"]["slot"], en=d.get("en_slot"), t=t,
                                                                 pct=d["trig"].get("pct")))
            elif e == "presend_live_skip": R["arm_skips"].append(dict(mint=d["trig"]["mint"], slot=d["trig"]["slot"], why=d.get("why"), t=t,
                                                                       pct=d["trig"].get("pct")))
            elif e == "presend_live_disarm": R["pdisarm"].append(dict(mint=d["mint"], why=d.get("why"), filled=d.get("filled"), slot=d.get("slot")))
        out[run] = R
        print(run, R["start"] and int(R["start"]), R["end"] and int(R["end"]), "dumps", len(R["dumps"]), "fires", len(R["fires"]),
              "land", len(R["land"]), "pattempts", len(R["pattempts"]), "pfills", len(R["pfills"]), "arms", len(R["arms"]), flush=True)
    pickle.dump(out, open(f"{D}/haqq_strat/live.pkl", "wb"))


if __name__ == "__main__":
    main()
