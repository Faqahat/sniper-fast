#!/usr/bin/env python3
# LANDING2 step 5 (read-only): the SEND LEG measured on thousands of real pre-sent buy attempts (AMS r16 08:48-10:18 and r17 15:30-17:44 PKT).
# Each attempt is a real tx (helius-ps, 0.0002 tip, 1000 uL/CU, 120k CU) sent at a known wall time, independent of any dump; its
# landing (slot, idx) and its first sighting on our feeds are logged. send -> first seen = relay -> leader -> block -> shreds -> us.
# Output: tables on stdout + OUT/presend_rows.json
import json, collections, sys
import numpy as np

OUT = "/home/moiz/sniper-data/landing2"
RUNS = "/home/moiz/sniper-data/runs/ams/runs"
sys.path.insert(0, "/home/moiz/sniper/ops/dip/speed/landing2")
from l3_timeline import client_class, front

tg = json.load(open(f"{OUT}/targets.json"))["leaders"]
sch = json.load(open("/home/moiz/sniper-data/competitors2/schedule_1067.json"))
ids, sl0, sl = sch["ids"], sch["start"], sch["slot_leader"]
lead = lambda s: ids[sl[s - sl0]] if 0 <= s - sl0 < len(sl) and sl[s - sl0] is not None else None


def q(v, ps=(10, 25, 50, 75, 90)):
    v = [x for x in v if x is not None]
    return ("n=%d " % len(v) + " / ".join("%.1f" % x for x in np.percentile(v, ps))) if v else "-"


rows = []; unseen = collections.Counter()
for run in (16, 17):
    att = {}
    for l in open(f"{RUNS}/dip_ams_r{run}.jsonl"):
        if '"presend_attempt' not in l: continue
        r = json.loads(l)
        if r["ev"] == "presend_attempt": att[r["sig"]] = r
        elif r["ev"] == "presend_attempt_land":
            a = att.get(r["sig"], {})
            if "slot" not in r:          # never landed ("unseen") or no slot: counted separately
                unseen[r.get("res")] += 1; continue
            ld = lead(r["send_slot"]); ldl = lead(r["slot"])
            k = 0
            while k < 8 and lead(r["send_slot"] - k - 1) == ld: k += 1
            rows.append(dict(run=run, client=r.get("client"), cls=client_class(r.get("client")), front=front(tg.get(ld)), path=r.get("path"),
                             send_slot=r["send_slot"], slot=r["slot"], idx=r["idx"], dslots=r["slots_after_send"], s2seen=r.get("ms_send_to_first_rx"),
                             ack_ms=r.get("ack_ms"), ack=r.get("ack"), res=r.get("res"), window_slot=k + 1, same_leader=(ld == ldl),
                             build_us=a.get("build_us"), write_us=a.get("write_us"), bh_age=a.get("bh_age_ms"), cu_price=a.get("cu_price"), tip=a.get("tip")))
json.dump(rows, open(f"{OUT}/presend_rows.json", "w"))
print("pre-sent attempts with a landing record:", len(rows), "| paths", collections.Counter(r["path"] for r in rows),
      "| cu_price", collections.Counter(r["cu_price"] for r in rows).most_common(3), "| tip", collections.Counter(r["tip"] for r in rows).most_common(3))
print("attempts with no landing slot:", dict(unseen))
print("result codes:", collections.Counter(r["res"] for r in rows).most_common(6))
print("\nsend -> our tx first seen (ms; p10/p25/p50/p75/p90), by leader client, all / landed in the send slot / later")
print(f"{'client':12s} {'n':>5s} {'same slot':>9s} | {'all':42s} | {'same slot':42s} | next slot+")
for c in ("bam", "firebam", "harmonic", "jito", "fd", "agave", "rakurai", "ALL"):
    g = [r for r in rows if c == "ALL" or r["cls"] == c]
    if not g: continue
    ss = [r for r in g if r["dslots"] == 0]
    print(f"{c:12s} {len(g):5d} {len(ss) / len(g):9.0%} | {q([r['s2seen'] for r in g]):42s} | {q([r['s2seen'] for r in ss]):42s} | "
          f"{q([r['s2seen'] for r in g if r['dslots'] > 0], (50,))}")
print("\nJito by TPU front (relayer :11228 vs own TPU), same slot as the send:")
for fr in ("own", "relayer", "other-host"):
    g = [r for r in rows if r["cls"] == "jito" and r["front"] == fr]
    if g: print(f"  {fr:10s} n={len(g):4d} same-slot {sum(r['dslots'] == 0 for r in g) / len(g):.0%} send->seen all {q([r['s2seen'] for r in g], (25, 50, 75))} | same slot {q([r['s2seen'] for r in g if r['dslots'] == 0], (25, 50, 75))}")
print("\nBy window slot (1 = first slot of the leader's 4-slot window), share landing in the send slot:")
for c in ("bam", "harmonic", "jito", "fd"):
    print(f"  {c:9s}", "  ".join(f"w{k}: {sum(r['dslots'] == 0 for r in rows if r['cls'] == c and r['window_slot'] == k) / max(1, sum(1 for r in rows if r['cls'] == c and r['window_slot'] == k)):.0%} (n={sum(1 for r in rows if r['cls'] == c and r['window_slot'] == k)})" for k in (1, 2, 3, 4)))
print("\nrelay HTTP ack (ms):", q([r["ack_ms"] for r in rows]), "| statuses", collections.Counter(r["ack"] for r in rows).most_common(4))
print("build us:", q([r["build_us"] for r in rows], (50, 90)), "| write us:", q([r["write_us"] for r in rows], (50, 90)))
print("lowest send->seen seen (ms):", sorted(r["s2seen"] for r in rows if r["s2seen"] is not None)[:10])
