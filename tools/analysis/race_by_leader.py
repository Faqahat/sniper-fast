#!/usr/bin/env python3
"""Long run: our path race by kind of leader. For every landed trade (ours.jsonl from stage 4): the leader of the slot
it landed in, and which path's copy landed (race arm: all paths fired at once, so the landed path is the one that
reached that leader first) and how many ms after the trigger. Tells which path to use for which leader.
usage: race_by_leader.py <leaders.json> -> race-by-leader.json"""
import json, sys, os, collections

L = json.load(open(sys.argv[1])); first = L["first_slot"]; LEAD = L["leaders"]; INFO = L["info"]
lead = lambda s: LEAD[s - first] if 0 <= s - first < len(LEAD) else None
q = lambda v, p: (round(sorted(v)[min(len(v) - 1, int(len(v) * p))], 1) if v else None)
R = [json.loads(l) for l in open("ours.jsonl")]
# landed slot per attempt: from each segment's outcomes
slot = {}
for seg in {r["seg"] for r in R}:
    for l in open(os.path.join(seg, "outcomes.jsonl")):
        o = json.loads(l)
        if o.get("slot"): slot[(seg, o["attempt"])] = o["slot"]
def cats(k):
    i = INFO.get(k) or {}; v = i.get("version") or ""; r = i.get("rtt_ms")
    return {"jito": "bam" if i.get("bam") else "jito" if i.get("jito") else "no jito", "dz": "DZ" if i.get("dz") else "not DZ",
            "client": "firedancer" if v.startswith("0.") else "26.x" if v.startswith("26.") else "agave",
            "rtt": "?" if r is None else "<1ms" if r < 1 else "1-20ms" if r < 20 else "20-100ms" if r < 100 else ">100ms",
            "tpu": "relayer/elsewhere" if i.get("tpu_same_host") is False else "on host"}
out = {}
for dim in ("jito", "dz", "client", "rtt", "tpu"):
    first_by = collections.defaultdict(collections.Counter); ms_by = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in R:
        if r["path_arm"] != "race" or not r["landed"]: continue
        k = lead(slot.get((r["seg"], r["attempt"]), 0))
        if not k: continue
        c = cats(k)[dim]
        first_by[c][r["landed"]] += 1
        if r["ours_ms"] is not None: ms_by[c][r["landed"]].append(r["ours_ms"])
    out[dim] = {c: {"n": sum(cnt.values()), "first": dict(cnt.most_common()), "ms_p50": {p: q(v, .5) for p, v in ms_by[c].items()}} for c, cnt in first_by.items()}
    for c, x in out[dim].items(): print(f"{dim:6} {c:18} n={x['n']:3}  first: {x['first']}  ms p50: {x['ms_p50']}")
json.dump(out, open("race-by-leader.json", "w"), indent=1)
