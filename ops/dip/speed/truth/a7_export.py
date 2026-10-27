#!/usr/bin/env python3
# SPEED TRUTH step 7: one CSV row per live attempt (fills and failed buys) with every stage, for spreadsheets / phone.
import json, csv, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tl
R = json.load(open(f"{tl.OUT}/timeline.json"))
SS = {int(k): v for k, v in json.load(open(f"{tl.OUT}/slot_stats.json")).items()}
def size(s): v = SS.get(s); return v[1] + 1 if v else None
B400 = lambda s, i: s * tl.SMS + i / max(400, i + 1) * tl.SMS
Bmix = lambda s, i: s * tl.SMS + i / max(400, size(s) or 400, i + 1) * tl.SMS
def fx(v, n=1): return "" if v is None else round(v, n)
cols = ["time_pkt", "server", "run", "mint", "dump_sig", "our_sig", "result", "err", "leader", "client", "turn_slot", "route", "landed_path",
        "exec_wait_ms", "decision_ms", "first_write_ms", "our_tx_seen_ms", "send_to_seen_ms", "dump_slot", "dump_idx", "dump_block_n", "our_slot", "our_idx",
        "slot_delta", "land_B400_ms", "land_Bmix_ms", "land_feed_ms", "first_cross_B400_ms", "late_by_B400_ms", "crossing_wallet", "rival_buys_ahead",
        "first_rival_B400_ms", "first_reacting_rival_B400_ms", "hkq7_B400_ms", "haqq_B400_ms", "helius_429", "min_out", "spend"]
with open(f"{tl.OUT}/attempts.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(cols)
    for r in sorted(R, key=lambda r: r["t_fire"]):
        c = r["C"]; d0 = B400(c["dump_slot"], c["dump_idx"]); d1 = Bmix(c["dump_slot"], c["dump_idx"])
        fc = next((B400(s, i) - d0 for s, i, j, ps, *_ in c["gseq"] if not ps), None)
        land = B400(c["our_slot"], c["our_idx"]) - d0
        riv = [x for x in c["rivals"] if x["ok"] and x["user"] != c.get("dump_user")]
        react = [x for x in riv if not (x["ds"] == 0 and x["di"] <= 3)]
        def wms(u):
            x = next((x for x in c["rivals"] if x["user"] == u), None)
            return fx(B400(x["s"], x["i"]) - d0) if x else ""
        tfeed = (r["land"]["t"] if r["land"] else r["fail"]["t"]) if (r["land"] or r["fail"]) else None
        w.writerow([tl.pkt(r["t_fire"] / 1e9), r["srv"], r["run"], r["mint"], r["dump_sig"], c.get("our_sig"), "FILL" if r["filled"] else "fail",
                    "" if c["our_err"] is None else json.dumps(c["our_err"]), r["leader"], r["client"], r["L"]["turn_pos"] + 1, r["route"], c.get("our_path"),
                    fx(r["W"]["exec_wait"], 2), fx(r["W"]["decision"], 2), fx(r["W"]["first_write"], 2), fx(r["W"]["seen"]), fx(r["W"]["send_to_seen"]),
                    c["dump_slot"], c["dump_idx"], size(c["dump_slot"]), c["our_slot"], c["our_idx"], c["slot_delta"], fx(land),
                    fx(Bmix(c["our_slot"], c["our_idx"]) - d1), fx((tfeed - r["t_dump_rx"]) / 1e6 if tfeed else None), fx(fc),
                    fx(land - fc) if (fc is not None and not r["filled"]) else "", (tl.NAMED.get(c["cross_user"]) or c["cross_user"][:8]) if c.get("cross_user") else "",
                    sum(1 for x in riv if x["ahead"]), fx(B400(riv[0]["s"], riv[0]["i"]) - d0) if riv else "", fx(B400(react[0]["s"], react[0]["i"]) - d0) if react else "",
                    wms(tl.HKQ7), wms(tl.HAQQ), int(any(a["status"] == 429 for a in r["W"]["acks"].values())), r["min_out"], r["spend"]])
print("wrote", f"{tl.OUT}/attempts.csv", len(R), "rows")
