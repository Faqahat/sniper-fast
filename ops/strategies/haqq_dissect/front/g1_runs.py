#!/usr/bin/env python3
"""FRONT addendum step 1 (read-only): every live pre-send run's tries, arms, realized P&L and rate-cap refusals (run_end not_sent),
AMS16-33 + FRA21-26 + FRA27 (live copy pulled read-only into scratch). Out: sniper-data/haqq_dissect/front/g1_runs.pkl"""
import json, glob, os, pickle, sys, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/front")
from f3_ours import files
OUT = "/home/moiz/sniper-data/haqq_dissect/front"
R27 = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/hd_front/dip_r27.jsonl"


def main():
    F = files(); F["FRA27"] = R27
    runs = {}
    for run, f in sorted(F.items()):
        cfg = None; t0 = t1 = None; tries = {}; arms = {}; done = []; real = collections.defaultdict(int); fills = []; rend = None
        for l in open(f, errors="ignore"):
            if '"presend' not in l and '"run_start"' not in l and '"run_end"' not in l: continue
            try: d = json.loads(l)
            except Exception: continue
            e = d.get("ev"); t = d.get("t")
            if isinstance(t, (int, float)) and t > 1e15:
                t /= 1e9; t0 = t if t0 is None else min(t0, t); t1 = t if t1 is None else max(t1, t)
            if e == "run_start": cfg = d.get("presend_live")
            elif e == "run_end": rend = d.get("presend_live")
            elif e == "presend_live_arm":
                tr = d.get("trig") or {}
                arms[(d.get("w"), tr.get("mint"))] = dict(w=d.get("w"), mint=tr.get("mint"), arm_slot=tr.get("slot"), t_arm=t, k=d.get("k"))
            elif e == "presend_live_disarm":
                a = arms.pop((d.get("w"), d.get("mint")), None)
                if a: a.update(end_slot=d.get("slot"), t_end=t, why=d.get("why"), attempts=d.get("attempts"), filled=d.get("filled")); done.append(a)
            elif e == "presend_attempt" and not d.get("dry"):
                tries[d["sig"]] = dict(w=d.get("w"), n=d.get("n"), mint=d.get("mint"), send_slot=d.get("slot"), t_send=t, client=d.get("client"), path=d.get("path"),
                                       deadline=d.get("deadline"), pos=d.get("pos"))
            elif e == "presend_attempt_land":
                x = tries.get(d.get("sig"))
                if x is not None: x.update(slot=d.get("slot"), idx=d.get("idx"), res=d.get("res"), ms_rx=d.get("ms_send_to_rx"), sas=d.get("slots_after_send"))
            elif e == "presend_live_fill":
                fills.append(dict(w=d.get("w"), mint=d.get("mint"), slot=d.get("slot"), idx=d.get("idx"), sig=d.get("sig"), client=d.get("client")))
            elif e == "presend_live_realized":
                real[(d.get("w"), d.get("mint"))] += int(d.get("pnl") or 0)
        for a in arms.values(): a.update(end_slot=None, t_end=t1, why="open_at_end"); done.append(a)
        if cfg is None or not tries: continue
        runs[run] = dict(cfg=cfg, t0=t0, t1=t1, tries=list(tries.values()), arms=done, real=dict(real), fills=fills, rend=rend)
        print(run, cfg.get("k"), cfg.get("max_per_sec"), len(tries), len(done), (rend or {}).get("not_sent"), flush=True)
    pickle.dump(runs, open(f"{OUT}/g1_runs.pkl", "wb"))


if __name__ == "__main__":
    main()
