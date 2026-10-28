#!/usr/bin/env python3
"""vs248 step 2 (read-only): put every bot-248 lot and every one of OUR lots / failed attempts in exactly one bucket.

248 lot buckets (in this order):
  S_FILL  we filled a lot on the SAME dump row (same mint, same biggest-outside-drop row; identical definition both sides)
  S_NEAR  no same-dump fill, but we filled on the same mint within 248's buy slot -5 .. +2 (same burst, different trigger row)
  S_FAIL  no fill, but at least one of our buy attempts landed after the dump and <= 248's buy slot + 2 and failed (guard etc.)
  NOCOV   tape hour not usable (dv8 hours.json)
  NOENG   no trading engine running (run gaps, probe-only runs)  [g2_engine.pkl windows]
  NODUMP  248's buy has no >= 5 % outside drop within 2 slots (a lot type our engine never trades)
  REF:<reason>  dump-reactive, engine running, we did not attempt: the engine's reason from the run records
          (gap/g3_ledger.classify: gate refused / near-only / one-position busy / QUIET / pre-send not armed / thresholds / old / cooldown / other)
our lots: H2H (paired to a 248 S_FILL lot) / NEAR (same burst) / OWN (no 248 lot)
our failed attempts: on an S_FAIL / S_FILL / S_NEAR event, or alone (no 248 lot)
our wallet per day = every FRA/AMS tx's SOL delta (ours.jsonl sd; fees, tips, rent) (MEASURED)
Out: vs248/v2.pkl"""
import json, pickle, sys, collections, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/gap")
import dv8lib as L
from g3_ledger import classify, grp
OUT = "/home/moiz/sniper-data/haqq_dissect/vs248"
G = "/home/moiz/sniper-data/haqq_dissect/gap"


def main():
    t0 = time.time()
    Z = pickle.load(open(f"{OUT}/v1.pkl", "rb")); LOTS = Z["lots"]; ofail = Z["ofail"]
    H = [x for x in LOTS if x["who"] == "248"]; O = [x for x in LOTS if x["who"] != "248"]
    ids, idm = L.ids_map()
    g3 = pickle.load(open(f"{G}/g3_rows.pkl", "rb"))
    g3b = {(r["b"]["slot"], r["b"]["idx"]): r for r in g3["rows"]}
    RUNS = pickle.load(open(f"{G}/g2_engine.pkl", "rb"))
    runs = []
    for rn, X in RUNS.items():
        if not X["start"]: continue
        live_arms = [a for a in X["arms"] if not a[9]]
        X["ps_on"] = len(live_arms) > 0 or len(X["patt"]) > 0
        X["arms_by"] = collections.defaultdict(list); X["sk_by"] = collections.defaultdict(list)
        for a in live_arms: X["arms_by"][(a[0], a[1])].append(a)
        for s in X["pskips"]: X["sk_by"][(s[0], s[1])].append(s)
        runs.append((X["start"], X["end"], rn, X))
    runs.sort()
    HR = json.load(open(f"{L.D}/hours.json"))["rows"]; usable = {r["h"]: r["usable"] for r in HR}
    def hour_ok(t): return usable.get(int((t + 18000) // 3600 * 3600 - 18000), False)
    # our lots per mint, failed attempts per mint
    obym = collections.defaultdict(list)
    for x in O: obym[x["mint"]].append(x)
    fbym = collections.defaultdict(list)
    for f in ofail:
        if f["mint"]: fbym[f["mint"]].append(f)
    od = {(x["mint"], x["d_row"]): x for x in O if x["d_row"] is not None}
    odl = collections.defaultdict(list)
    for x in O:
        if x["d_row"] is not None: odl[(x["mint"], x["d_row"])].append(x)
    for x in O: x["bucket"] = "OWN"; x["pair"] = []
    for f in ofail: f["ev"] = None
    nh = 0
    for h in H:
        h["pair"] = []; h["fails"] = []
        r = g3b.get((h["slot"], h["idx"]))
        h["g3"] = (r["bucket"], r["reason"], r["type"]) if r else None
        act = [(rn, X) for s, e, rn, X in runs if s <= h["bt"] <= e]
        trading = [(rn, X) for rn, X in act if not X["probe_run"]]
        h["servers"] = sorted(set(X["srv"] for rn, X in trading)); h["ps_live"] = any(X["ps_on"] for rn, X in trading)
        same = odl.get((h["mint"], h["d_row"]), []) if h["d_row"] is not None else []
        sid = set(id(y) for y in same)
        near = [x for x in obym.get(h["mint"], []) if h["slot"] - 5 <= x["slot"] <= h["slot"] + 2 and id(x) not in sid]
        lo = (h["d_slot"], h["d_idx"]) if h["d_row"] is not None and h["d_slots"] <= 5 else (h["slot"] - 2, 0)
        fl = [f for f in fbym.get(h["mint"], []) if (f["s"], f["i"]) > lo and f["s"] <= h["slot"] + 2]
        h["fails"] = fl
        if same:
            h["bucket"] = "S_FILL"; h["pair"] = same
            for x in same: x["bucket"] = "H2H"; x["pair"].append(h)
        elif near:
            h["bucket"] = "S_NEAR"; h["pair"] = near
            for x in near:
                if x["bucket"] == "OWN": x["bucket"] = "NEAR"
                x["pair"].append(h)
        elif fl: h["bucket"] = "S_FAIL"
        elif not hour_ok(h["bt"]): h["bucket"] = "NOCOV"
        elif not trading: h["bucket"] = "NOENG"
        elif not h["dumpre"]: h["bucket"] = "NODUMP"
        else:
            b = r["b"] if r else None
            if b is None or b.get("d_slot") is None:
                h["bucket"] = "REF:other"; h["reason"] = "no g1 record"
            else:
                c = classify(b, trading, ids)
                h["bucket"] = "REF:" + grp(c["reason"]); h["reason"] = c["reason"]; h["reg_reason"] = c["reg_reason"]; h["ps_reason"] = c["ps_reason"]
        for f in fl:
            if f["ev"] is None: f["ev"] = (h["bucket"], h["slot"], h["idx"])
        nh += 1
        if nh % 2000 == 0: print(f"  {nh:,} ({time.time() - t0:.0f}s)", flush=True)
    # failed attempts on our own fills' events (same mint, within our fill's dump .. fill slot + 2)
    for x in O:
        lo = (x["d_slot"], x["d_idx"]) if x["d_row"] is not None and x["d_slots"] <= 5 else (x["slot"] - 2, 0)
        for f in fbym.get(x["mint"], []):
            if f["ev"] is None and (f["s"], f["i"]) > lo and f["s"] <= x["slot"] + 2: f["ev"] = ("OURFILL:" + x["bucket"], x["slot"], x["idx"])
    for f in ofail:
        if f["ev"] is None: f["ev"] = ("ALONE", None, None)
        f["day"] = L.day_of(f["bt"]); f["path"] = "ps" if f["cul"] == 120000 else "reg" if f["cul"] == 100000 else "other"
    # wallet per day
    wal = collections.Counter(); W2 = set(L.WAL.values())
    for l in open(f"{L.TAB}/ours.jsonl"):
        d = json.loads(l); w = d["signers"][0]
        if w not in W2: continue
        sd = d["sd"]; sd = json.loads(sd.replace("'", '"')) if isinstance(sd, str) else sd
        wal[L.day_of(d["bt"])] += sum(v for a, v in sd if a == w) / 1e9
    pickle.dump(dict(H=H, O=O, ofail=ofail, wal=dict(wal)), open(f"{OUT}/v2.pkl", "wb"))
    print("248 buckets", collections.Counter(h["bucket"] for h in H))
    print("our buckets", collections.Counter((x["bucket"], x["path"]) for x in O))
    print("fails", collections.Counter((f["ev"][0], f["path"]) for f in ofail))
    print("wallet", {k: round(v, 3) for k, v in sorted(wal.items())})
    # main-session window reproduction: our fills with a 248 buy on the mint in [our slot-2, our slot+5]
    hb = collections.defaultdict(list)
    for h in H: hb[h["mint"]].append(h)
    c = collections.Counter(); n = collections.Counter(); order = collections.Counter()
    for x in O:
        n[x["path"]] += 1
        w = [h for h in hb.get(x["mint"], []) if x["slot"] - 2 <= h["slot"] <= x["slot"] + 5]
        if w: c[x["path"]] += 1
        for h in w: order[(x["path"], "after" if (h["slot"], h["idx"]) > (x["slot"], x["idx"]) else "before")] += 1
    print("window match (main session def):", {k: f"{c[k]}/{n[k]}" for k in n}, dict(order))
    print(f"done ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
