#!/usr/bin/env python3
"""SPEED35 step 1 [MEASURED]: our CURRENT landing on AMS r37 live data.
(a) every landed pre-send try: send -> first feed rx (ms), same slot as send; per path.
(b) every live fill: the outside dump just before it (presend_live_tape, same feed clock) -> our fill rx (ms), block-index gap, same slot.
(c) every live sell: exit decision (presend_live_exit t) -> sell land rx (ms), slots.
Usage: s1_measure.py RUN.jsonl  -> prints; writes /home/it/sniper-data/speed35/s1_measure.json"""
import json, sys, collections, numpy as np
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
fn = sys.argv[1]
att = []; fills = []; tape = collections.defaultdict(list); exits = {}; sells = []; sent = {}; dumps = {}
for l in open(fn):
    if '"ev":"dump"' in l:
        r = json.loads(l); dumps[(r["mint"], r["slot"], r["idx"])] = r["t"]; continue
    if '"ev":"presend_' not in l: continue
    r = json.loads(l); e = r["ev"]
    if e == "presend_attempt": sent[r["sig"]] = r
    elif e == "presend_attempt_land": att.append(r)
    elif e == "presend_live_tape": tape[r["mint"]].append(r)
    elif e == "presend_fill" and r.get("row") == "a" and r.get("m"): dumps[(r["mint"], r["m"]["slot"], r["m"]["idx"])] = r["m"]["t"]
    elif e == "presend_live_fill": fills.append(r)
    elif e == "presend_live_exit": exits[(r["mint"], r.get("pid"), r.get("round"))] = r
    elif e == "presend_live_sell_land": sells.append(r)
q = lambda a, ps=(10, 25, 50, 75, 90): [round(float(np.percentile(a, p)), 1) for p in ps] if len(a) else []
out = {}
ms = [a["ms_send_to_first_rx"] for a in att if a.get("ms_send_to_first_rx") is not None]
ss = [a.get("slots_after_send") for a in att]
print(f"(a) landed tries {len(att)}: send->first rx ms q10/25/50/75/90 {q(ms)}; same slot as send {np.mean([s == 0 for s in ss]):.0%}, +1 {np.mean([s == 1 for s in ss]):.0%}, +2+ {np.mean([(s or 0) >= 2 for s in ss]):.0%}")
byp = collections.defaultdict(list)
for a in att:
    if a.get("ms_send_to_first_rx") is not None: byp[a.get("path")].append(a["ms_send_to_first_rx"])
for p, v in sorted(byp.items(), key=lambda x: -len(x[1])): print(f"    path {p:12s} n {len(v):6d} ms q10/25/50/75/90 {q(v)}")
out["try_ms"] = ms
# cadence: gap between consecutive sends per mint window
TB = "/home/it/sniper-data/speed35/tab"
T = np.load(TB + "/trades.npy", mmap_mode="r"); IDS = json.load(open(TB + "/ids.json")); GID = {k: i for i, k in enumerate(IDS)}
OG = {GID[o] for o in OURS if o in GID}
Tm = np.asarray(T["mint"]); F = []
for f in fills:
    if f["mint"] not in GID: continue
    t = T[Tm == GID[f["mint"]]]
    pre = [x for x in t if (int(x["slot"]), int(x["idx"])) < (f["slot"], f["idx"]) and int(x["user"]) not in OG and int(x["slot"]) >= f["slot"] - 12]
    d = next((x for x in reversed(pre) if not x["buy"]), None)
    if d is None: continue
    d = {"slot": int(d["slot"]), "idx": int(d["idx"]), "t": dumps.get((f["mint"], int(d["slot"]), int(d["idx"])))}
    between = [x for x in pre if (int(x["slot"]), int(x["idx"])) > (d["slot"], d["idx"])]
    F.append({"dms": (f["t"] - d["t"]) / 1e6 if d["t"] else None, "same": d["slot"] == f["slot"], "gap": f["idx"] - d["idx"] if d["slot"] == f["slot"] else None,
              "between": len(between), "try_ms": f.get("ms_send_to_rx"), "d_slot": f["slot"] - d["slot"], "path": f.get("path")})
dms = [x["dms"] for x in F if x["dms"] is not None]
print("    dump rx time known for", len(dms))
print(f"(b) fills {len(fills)} with dump found {len(F)}: dump rx -> our fill rx ms q10/25/50/75/90 {q(dms)}")
for k in (0, 1, 2): print(f"    fill slot = dump slot + {k}: {np.mean([x['d_slot'] == k for x in F]):.0%}")
print(f"    same slot as dump {np.mean([x['same'] for x in F]):.0%}; block-index gap (same slot) q10/25/50/75/90 {q([x['gap'] for x in F if x['same']])}; "
      f"0 outside trades between {np.mean([x['between'] == 0 for x in F]):.0%}")
print(f"    filling try send->rx ms q10/50/90 {q([x['try_ms'] for x in F if x['try_ms']], (10, 50, 90))} (tries are pre-sent, so this includes waiting for the dump)")
out["fill"] = F
S = []
for s in sells:
    x = exits.get((s["mint"], s.get("pid"), s.get("round")))
    if x: S.append({"ms": (s["t"] - x["t"]) / 1e6, "slots": s["slot"] - x["slot"]})
print(f"(c) sells {len(sells)} matched {len(S)}: decision -> sell land rx ms q10/25/50/75/90 {q([x['ms'] for x in S])}; slots after decision slot "
      f"{dict(collections.Counter(x['slots'] for x in S))}")
out["sell"] = S
json.dump(out, open("/home/it/sniper-data/speed35/s1_measure.json", "w"))
