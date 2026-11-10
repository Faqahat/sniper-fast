# rebuild testdata/dip26_r38_slice.jsonl from AMS run 38 (lost 11-09): run_start; every record of re-arm windows 90 and 117
# and T2 window 118; one deferred re-arm window armed after waiting that expired (arm + defer + disarm); one T2 window
# QUIET-stopped (arm + disarm); one T2 skip create_slot, one T2 skip quiet, one re-arm skip rearm_no_holder, one rearm_age.
import json, sys
src, out = sys.argv[1], sys.argv[2]
lines = open(src, errors="replace").read().split("\n")
recs = []
for i, l in enumerate(lines):
    try: recs.append((i, json.loads(l), l))
    except Exception: pass
keep = set()
for i, o, l in recs:
    ev = o.get("ev", "")
    if ev == "run_start": keep.add(i)
    if o.get("w") in (90, 117, 118) and (ev.startswith("presend_live") or ev in ("presend_attempt", "presend_attempt_land")): keep.add(i)
byw = {}
for i, o, l in recs:
    if o.get("ev", "").startswith("presend_live") and "w" in o: byw.setdefault(o["w"], []).append((i, o))
def pick(pred):
    for w, L in sorted(byw.items()):
        if w in (90, 117, 118): continue
        if pred(L): return w, L
    return None, None
w, L = pick(lambda L: any(o["ev"] == "presend_live_arm" and o.get("kind") == "rearm" and o.get("deferred") for i, o in L) and any(o["ev"] == "presend_live_disarm" and o.get("why") == "expired" for i, o in L) and not any(o["ev"] == "presend_live_fill" for i, o in L))
for i, o in L:
    if o["ev"] in ("presend_live_arm", "presend_live_disarm", "presend_live_rearm_defer"): keep.add(i)
print("re-arm expired", w, file=sys.stderr)
w, L = pick(lambda L: any(o["ev"] == "presend_live_arm" and o.get("kind") != "rearm" for i, o in L) and any(o["ev"] == "presend_live_disarm" and o.get("why") == "quiet" for i, o in L))
for i, o in L:
    if o["ev"] in ("presend_live_arm", "presend_live_disarm"): keep.add(i)
print("T2 quiet", w, file=sys.stderr)
need = {("t2", "create_slot"): 1, ("t2", "quiet"): 1, ("rearm", "rearm_no_holder"): 1, ("rearm", "rearm_age"): 1, ("defer", None): 1}
for i, o, l in recs:
    ev = o.get("ev")
    if ev == "presend_live_skip":
        k = ("rearm" if o.get("kind") == "rearm" else "t2", o.get("why"))
    elif ev == "presend_live_rearm_defer" and "w" not in o:
        k = ("defer", None)
    else:
        continue
    if need.get(k, 0) > 0:
        need[k] -= 1; keep.add(i)
mints = {o.get("mint") for i, o, l in recs if i in keep and o.get("w") in (90, 117, 118)}
for i, o, l in recs:  # the position records keyed by mint only (account close, end check)
    if o.get("ev", "").startswith("presend_live") and "w" not in o and o.get("mint") in mints and o.get("ev") == "presend_live_ata_close":
        keep.add(i)
with open(out, "w") as f:
    for i in sorted(keep):
        f.write(lines[i] + "\n")
