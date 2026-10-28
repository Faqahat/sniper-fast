#!/usr/bin/env python3
"""FRONT step 3 (read-only): our live engine's view of every dump, from the run records (AMS r9-r33, FRA r1-r26).
Per run: time span; per dump the engine logged: gate result; regular pick/skip(why)/fire (+ per-path copies, route); pre-send live
arm windows (mint, arm slot, disarm slot, why) and skips (why); every pre-send try (send slot, landed slot/idx, result, path).
Out: sniper-data/haqq_dissect/front/f3_ours.pkl"""
import json, glob, os, hashlib, collections, pickle, time
OUT = "/home/moiz/sniper-data/haqq_dissect/front"
D = "/home/moiz/sniper-data"


def sigh(sig): return int.from_bytes(hashlib.blake2b(sig.encode(), digest_size=8).digest(), "little")


def files():
    F = {}
    for f in glob.glob(f"{D}/runs/ams/runs/dip_ams_r*.jsonl") + [f"{D}/presend_filter/live28/dip_ams_r28.jsonl"] + glob.glob(f"{D}/haqq_strat/live/dip_ams_r*.jsonl"):
        r = "AMS%02d" % int(os.path.basename(f).split("_r")[1].split(".")[0]); F.setdefault(r, []).append(f)
    for f in glob.glob(f"{D}/runs/fra/runs/dip_r*.jsonl") + [f"{D}/dv8/live/dip_r26.jsonl"]:
        r = "FRA%02d" % int(os.path.basename(f).split("_r")[1].split(".")[0]); F.setdefault(r, []).append(f)
    return {r: max(v, key=os.path.getsize) for r, v in F.items()}


def main():
    t0 = time.time()
    runs = {}; dumps = {}; skips = {}; picks = {}; fires = {}; blands = {}; arms = []; pskips = []; tries = {}; timing = {}
    for run, f in sorted(files().items()):
        tmin = tmax = None; srv = run[:3]; openarm = {}
        for l in open(f, errors="ignore"):
            try: d = json.loads(l)
            except Exception: continue
            e = d.get("ev"); t = d.get("t")
            if isinstance(t, (int, float)) and t > 1e15:
                t = t / 1e9
                tmin = t if tmin is None else min(tmin, t); tmax = t if tmax is None else max(tmax, t)
            if e == "dump":
                dumps[(srv, sigh(d["sig"]))] = dict(run=run, t=t, gate=d.get("pass"), m2=d.get("m2_pick"), imit=d.get("imit_pass"), launch_ok=d.get("launch_ok"),
                                                   mint=d.get("mint"), slot=d.get("slot"), idx=d.get("idx"))
            elif e == "pick_skip":
                skips[(srv, sigh(d["sig"]))] = d.get("why")
            elif e == "pick":
                picks[(srv, sigh(d["sig"]))] = dict(route=d.get("route"), paths=d.get("paths"), client=d.get("client"))
            elif e == "fire":
                fires[(srv, sigh(d["dump_sig"]))] = dict(run=run, buy_sig=d.get("buy_sig"), client=d.get("client"), leader=d.get("leader"),
                                                        copies=[(p.get("path"), p.get("sig"), p.get("tip")) for p in (d.get("nonce") or {}).get("per_path", [])],
                                                        decision_us=d.get("decision_us"))
            elif e in ("buy_land", "buy_failed"):
                blands[d.get("sig")] = dict(ev=e, slot=d.get("slot"), idx=d.get("idx"), ms=d.get("rx_ms_after_dump"), dsl=d.get("slots_after_dump"),
                                            variant=(d.get("variant") or {}).get("paths"), err=d.get("err"))
            elif e == "timing":
                timing[d.get("buy_sig")] = dict(acks=d.get("acks"), clock2=d.get("clock2"), first_feed=d.get("buy_first_feed"), sig_seen=d.get("buy_sig_seen"))
            elif e == "presend_live_arm":
                tr = d.get("trig") or {}
                openarm[(d.get("w"), tr.get("mint"))] = dict(run=run, srv=srv, mint=tr.get("mint"), w=d.get("w"), arm_slot=tr.get("slot"), t=t, k=d.get("k"),
                                                            spend=d.get("spend"), drop=d.get("drop"), trig_pct=tr.get("pct"), trig_wallet=tr.get("wallet"),
                                                            trig_age=tr.get("age_slots"))
            elif e == "presend_live_disarm":
                a = openarm.pop((d.get("w"), d.get("mint")), None)
                if a: a.update(end_slot=d.get("slot"), why=d.get("why"), attempts=d.get("attempts"), filled=d.get("filled")); arms.append(a)
            elif e == "presend_live_skip":
                tr = d.get("trig") or {}
                pskips.append(dict(run=run, srv=srv, mint=tr.get("mint"), slot=tr.get("slot"), why=d.get("why"), pct=tr.get("pct"), wallet=tr.get("wallet")))
            elif e == "presend_attempt":
                if d.get("dry"): continue
                tries[d["sig"]] = dict(run=run, srv=srv, mint=d.get("mint"), send_slot=d.get("slot"), path=d.get("path"), client=d.get("client"),
                                       leader=d.get("leader"), w=d.get("w"), t_send=t, pos=d.get("pos"), cu_price=d.get("cu_price"))
            elif e == "presend_attempt_land":
                x = tries.get(d.get("sig"))
                if x is not None: x.update(slot=d.get("slot"), idx=d.get("idx"), res=d.get("res"), sas=d.get("slots_after_send"), ms_rx=d.get("ms_send_to_rx"))
        for a in openarm.values(): a.update(end_slot=None, why="open_at_end"); arms.append(a)
        runs[run] = (tmin, tmax)
        print(f"{run} {f.split('/')[-1]} {len(dumps):,} dumps, {len(arms):,} arms, {len(tries):,} tries ({time.time()-t0:.0f}s)", flush=True)
    pickle.dump(dict(runs=runs, dumps=dumps, skips=skips, picks=picks, fires=fires, blands=blands, timing=timing, arms=arms, pskips=pskips,
                     tries=list(tries.values())), open(f"{OUT}/f3_ours.pkl", "wb"))


if __name__ == "__main__":
    main()
