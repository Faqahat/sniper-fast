#!/usr/bin/env python3
"""FLAT study, step 2 (read-only): every live pre-send window of one run from the engine records (MEASURED).
Per window (seg, w): the trigger, the arm's QUIET record (dip20+), the disarm, every try (send slot, pos, landing result, fee),
the fill(s), the exit(s), our sell landing(s), the close, the realized P&L, the token-account rent back (ATA close), and the
position's tape (presend_live_tape: every trade the engine received on the token while the position was open, with its
receive time). Also the regular (reactive) fires' decision times and the run's segments (live size per segment).
Writes /home/moiz/sniper-data/presend_flat/live_<run>.pkl
usage: f2_live.py r24 [r25 ...] [--file PATH (for r28's snapshot)]"""
import sys, json, pickle, collections, argparse

RUNS = "/home/moiz/sniper-data/runs/ams/runs"
OUT = "/home/moiz/sniper-data/presend_flat"
WALLET = "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"
EVS = ("presend_live_", "presend_attempt", "run_start", "run_end", '"ev":"fire"')


def parse(fn):
    seg = 0; segs = {}
    W = collections.OrderedDict(); att = {}; land = {}; ata = []; tape = collections.defaultdict(list); fires = []; skips = []
    for line in open(fn, errors="ignore"):
        if not any(e in line for e in EVS): continue
        try: r = json.loads(line)
        except Exception: continue
        ev = r.get("ev")
        if ev == "run_start":
            seg += 1; pl = r.get("presend_live") or {}
            segs[seg] = dict(t=r["t"], spend=pl.get("spend"), k=pl.get("k"), exit_slots=pl.get("exit_slots"), tp=pl.get("tp"), sl=pl.get("sl"),
                             window_slots=pl.get("window_slots"), quiet=pl.get("quiet"), one_position=pl.get("one_position"), fail_fee=pl.get("fail_fee"))
            continue
        if ev == "run_end":
            if seg in segs: segs[seg]["t_end"] = r.get("t")
            continue
        if ev == "fire":
            fires.append(dict(seg=seg, t=r.get("t_fire"), mint=r.get("mint"), slot=r.get("slot"))); continue
        if not ev or not ev.startswith("presend_"): continue
        r["seg"] = seg
        if ev == "presend_live_arm":
            W[(seg, r["w"])] = dict(seg=seg, w=r["w"], arm=r, disarm=None, tries=[], fills=[], exits=[], sells=[], close=None, realized=None)
        elif ev == "presend_live_skip": skips.append(r)
        elif ev == "presend_attempt": att[r["sig"]] = r
        elif ev == "presend_attempt_land": land[r["sig"]] = r
        elif ev == "presend_live_disarm" and (seg, r["w"]) in W: W[(seg, r["w"])]["disarm"] = r
        elif ev == "presend_live_fill" and (seg, r["w"]) in W: W[(seg, r["w"])]["fills"].append(r)
        elif ev == "presend_live_exit" and (seg, r.get("w")) in W: W[(seg, r["w"])]["exits"].append(r)
        elif ev == "presend_live_sell_land" and (seg, r.get("w")) in W: W[(seg, r["w"])]["sells"].append(r)
        elif ev == "presend_live_close" and (seg, r.get("w")) in W: W[(seg, r["w"])]["close"] = r
        elif ev == "presend_live_realized" and (seg, r.get("w")) in W: W[(seg, r["w"])]["realized"] = r
        elif ev == "presend_live_ata_close": ata.append(r)
        elif ev == "presend_live_tape": tape[(seg, r["mint"])].append(r)
    for sig, a in att.items():
        key = (a["seg"], a["w"])
        if key not in W: continue
        a = dict(a); a["land"] = land.get(sig)
        W[key]["tries"].append(a)
    used = set()
    for key, X in W.items():
        X["tries"].sort(key=lambda a: a["t"])
        X["spend"] = (X["arm"].get("spend") or segs[X["seg"]]["spend"])
        X["k"] = X["arm"].get("k") or segs[X["seg"]]["k"]
        X["mint"] = X["arm"]["trig"]["mint"]
        rb = 0; rb_rec = None
        if X["fills"]:
            f = X["fills"][0]
            for q, z in enumerate(ata):
                if q in used: continue
                if z["seg"] == X["seg"] and z["mint"] == X["mint"] and z.get("slot", 0) >= f["slot"]:
                    rb = z.get("delta") or 0; rb_rec = z; used.add(q); break
            # the position's tape: trades received from the fill to the close (receive time order)
            cl = X["close"] or {}
            t_end = max([s[2] for s in (cl.get("sell_lands") or [])] + [s["t"] for s in X["sells"]] + [f["t"]])
            X["tape"] = [r for r in tape.get((X["seg"], X["mint"]), []) if f["t"] <= r["t"] <= t_end]
        else:
            X["tape"] = []
        X["rb"] = rb; X["rb_rec"] = rb_rec
        X["pnl"] = (X["realized"] or {}).get("pnl", 0) if X["fills"] else 0
    return dict(segs=segs, W=W, fires=fires, skips=skips, n_att=len(att), n_land=len(land))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("runs", nargs="+"); ap.add_argument("--file")
    A = ap.parse_args()
    for run in A.runs:
        import flatlib as FL
        fn = A.file or FL.RUNS[run]["file"]
        D = parse(fn)
        D["run"] = run; D["file"] = fn
        pickle.dump(D, open(f"{OUT}/live_{run}.pkl", "wb"))
        nf = sum(1 for X in D["W"].values() if X["fills"])
        multi = sum(1 for X in D["W"].values() if len(X["fills"]) > 1)
        msell = sum(1 for X in D["W"].values() if len(X["sells"]) > 1)
        nrz = sum(1 for X in D["W"].values() if X["fills"] and X["realized"] is None)
        print(f"{run}: segments {len(D['segs'])}, windows {len(D['W'])}, fills {nf} (multi-fill {multi}, multi-sell {msell}, no realized {nrz}), "
              f"tries {D['n_att']}, skips {len(D['skips'])}, fires {len(D['fires'])}")


if __name__ == "__main__":
    main()
