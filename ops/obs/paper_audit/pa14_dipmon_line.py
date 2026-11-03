#!/usr/bin/env python3
"""PAPER AUDIT: a reference for the proposed dipmon paper lines (records only, read-only; NOT wired into dipmon).
Prints, for one run's --dip-log:
  now   : what dipmon shows today (the engine's last 60 s line, row c: all T2 triggers, 0.55 SOL, 20 tries/slot fee model)
  live  : pre-send live fills and cash (realized + ATA rent back - failed-try fees), as today
  parity: the shadow ONLY on the T2 triggers live armed: per row fills vs live fills on the same windows, agreement (counts only:
          the shadow's P&L there is not comparable while its tape holds our own trades and its exit is 2 slots)
  skipped: the shadow on the triggers live skipped, by reason: windows, row c fills, row c gross at the shadow size (a paper P&L,
          no costs; the calibrated value is the offline try-level replay, ops/obs/paper_audit)
usage: pa14_dipmon_line.py RUN.jsonl"""
import sys, json, collections


def main(fn):
    sh_arm, sh_fill, sh_exit, sh_dis = {}, {}, {}, {}
    lv_arm, lv_skip, lv_fill, lv_real, ata, tries_fail = {}, [], collections.Counter(), 0.0, 0.0, 0.0
    status = None; ses = -1
    for line in open(fn, errors="replace"):
        if '"ev":"run_start"' in line: ses += 1; continue
        if '"ev":"presend' not in line: continue
        r = json.loads(line); e = r["ev"]
        if e == "presend_arm": sh_arm[(ses, r["w"])] = r
        elif e == "presend_fill": sh_fill[(ses, r["w"], r["row"])] = r
        elif e == "presend_exit": sh_exit[(ses, r["w"], r["row"])] = r
        elif e == "presend_disarm": sh_dis[(ses, r["w"])] = r
        elif e == "presend_live_arm" and r.get("kind") != "rearm": lv_arm[(ses, r["w"])] = r
        elif e == "presend_live_skip" and r.get("trig"): r["ses"] = ses; lv_skip.append(r)
        elif e == "presend_live_fill": lv_fill[(ses, r["w"])] += 1
        elif e == "presend_live_realized": lv_real += (r.get("pnl") or 0) / 1e9
        elif e == "presend_live_ata_close" and r.get("ok"): ata += (r.get("delta") or 0) / 1e9
        elif e == "presend_attempt_land" and r.get("res") not in (None, "unseen", "ok"): tries_fail += (r.get("fee") or 0) / 1e9
    dec = {}
    for k, a in lv_arm.items(): dec[(k[0], a["trig"]["sig"], a["trig"].get("j", 0))] = ("armed", k)
    for s in lv_skip: dec.setdefault((s["ses"], s["trig"]["sig"], s["trig"].get("j", 0)), (s["why"], None))
    nf = sum(lv_fill.values())
    print(f"live      {nf} fills, cash {lv_real + ata - tries_fail:+.3f} SOL (realized {lv_real:+.3f}, rent back {ata:+.3f}, failed tries -{tries_fail:.3f})")
    par = {r: collections.Counter() for r in "abc"}; skip = collections.defaultdict(lambda: [0, 0, 0.0])
    for k, a in sh_arm.items():
        d, lk = dec.get((k[0], a["sig"], a.get("j", 0)), ("no_live_record", None))
        if d == "armed":
            lf = lv_fill.get(lk, 0) > 0
            dd = sh_dis.get(k)
            for r in "abc":
                if not dd or dd["rows"][r]["armed"] is not True: continue
                sf = (k[0], k[1], r) in sh_fill
                par[r]["both" if sf and lf else "shadow_only" if sf else "live_only" if lf else "neither"] += 1
        else:
            S = skip[d]; S[0] += 1
            e = sh_exit.get((k[0], k[1], "c"))
            if e: S[1] += 1; S[2] += e["pnl"]
    for r in "abc":
        c = par[r]; n = sum(c.values())
        print(f"parity {r}  live-armed T2 windows {n}: shadow fills {c['both'] + c['shadow_only']} vs live {c['both'] + c['live_only']} | both {c['both']}, shadow only {c['shadow_only']}, "
              f"live only {c['live_only']} | agree {100 * (c['both'] + c['neither']) / max(1, n):.1f}%")
    print("skipped   " + " | ".join(f"{w} {v[0]} (row c fills {v[1]}, gross {v[2]:+.3f} @0.55)" for w, v in sorted(skip.items(), key=lambda kv: -kv[1][0])))


if __name__ == "__main__":
    main(sys.argv[1])
