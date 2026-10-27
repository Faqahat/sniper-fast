#!/usr/bin/env python3
# Do we match the rivals' speed? Our live fires (runs 1-13, FRA + AMS). Same clock/feed for every tx (tape t = executed-feed rx).
# Per fire: our buy and every rival buy on the token from the dump to dump_slot+1: ms after the dump, and chain order (slot, idx).
import json, collections, statistics, os
D = os.path.dirname(os.path.abspath(__file__)) + "/.."
OURS = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
FILES = [f"dip_r{i}.jsonl" for i in range(1, 11)] + ["dip_ams_r9.jsonl", "dip_ams_r10.jsonl", "r11/dip_r11.jsonl", "r11/dip_r13.jsonl", "r11/dip_ams_r11.jsonl"]
rows = []
for fn in FILES:
    fires = {}; tim = {}; tape = collections.defaultdict(list)
    for l in open(f"{D}/{fn}"):
        try: r = json.loads(l)
        except Exception: continue
        e = r.get("ev")
        if e == "fire": fires[r["buy_sig"]] = r
        elif e == "timing" and r.get("kind") == "fire": tim[r["buy_sig"]] = r
        elif e == "tape": tape[r["mint"]].append(r)
    for sig, f in fires.items():
        t0 = f["t_dump_rx"]; S = f["slot"]; tm = tim.get(sig, {})
        tp = sorted([x for x in tape[f["mint"]] if S <= x["slot"] <= S + 1 and x["t"] >= t0 - 5e6], key=lambda x: (x["slot"], x["idx"]))
        ours = next((x for x in tp if x["user"] in OURS and x["buy"]), None)
        riv = [x for x in tp if x["buy"] and x["user"] not in OURS]
        rows.append(dict(run=fn, region="AMS" if "ams" in fn else "FRA", t_ours_all=(tm["reaction_ms"] + tm["fire_to_seen_ms"]) if tm.get("fire_to_seen_ms") and tm.get("reaction_ms") else None,
                         ours=((ours["t"] - t0) / 1e6, ours["slot"] - S, ours["idx"]) if ours else None,
                         riv=[(x["user"], (x["t"] - t0) / 1e6, x["slot"] - S, x["idx"]) for x in riv]))
med = lambda v: round(statistics.median(v), 1) if v else None
q = lambda v, p: round(sorted(v)[min(int(len(v) * p), len(v) - 1)], 1) if v else None
print(f"fires {len(rows)} | our buy filled (on tape) {sum(1 for r in rows if r['ours'])}")
oa = [r["t_ours_all"] for r in rows if r["t_ours_all"]]
print(f"OUR buy seen after the dump (ALL fires incl. failed): median {med(oa)} | p25 {q(oa,.25)} | p75 {q(oa,.75)} | p90 {q(oa,.9)}")
of = [r["ours"][0] for r in rows if r["ours"]]
print(f"OUR buy seen after the dump (filled only):            median {med(of)} | p25 {q(of,.25)} | p75 {q(of,.75)}")
# fastest reacting rival per fire (> 3 ms after the dump = not in the dump's own burst)
fx = [min(x[1] for x in r["riv"] if x[1] > 3) for r in rows if any(x[1] > 3 for x in r["riv"])]
print(f"FASTEST reacting rival per fire: median {med(fx)} | p25 {q(fx,.25)} | p75 {q(fx,.75)} | fires with one: {len(fx)}")
# per wallet: their landing on these same dumps, and head-to-head vs our filled buy (chain order)
W = collections.defaultdict(lambda: dict(t=[], same=0, n=0, win=0, lose=0, dms=[]))
for r in rows:
    seen = set()
    for u, t, ds, i in r["riv"]:
        if u in seen: continue
        seen.add(u); w = W[u]; w["n"] += 1; w["t"].append(t); w["same"] += ds == 0
        if r["ours"]:
            if (ds, i) < (r["ours"][1], r["ours"][2]): w["lose"] += 1; w["dms"].append(r["ours"][0] - t)
            else: w["win"] += 1
print("\nrival wallet (>=8 dumps)   dumps | their landing ms: median p25 | same slot as dump | vs our FILLED buys: they first / we first | they ahead by median ms")
for u, w in sorted(W.items(), key=lambda kv: -kv[1]["n"]):
    if w["n"] < 8: continue
    print(f"  {u[:8]}  {w['n']:4d} | {med(w['t']):6.1f} {q(w['t'],.25):6.1f} | {w['same']/w['n']:4.0%} | {w['lose']:3d} / {w['win']:3d} | {med(w['dms'])}")

# ---- all fires (incl. failed buys): our seen time measured from the same executed-feed dump time as the rivals
print("\n== ALL fires, our buy (incl. failed) vs the fastest reacting pros on the same dump")
PROS = ["HkQ7hMjy", "G9G3dCBG", "5w8xtjc6", "6n2cCJrr", "haqqiUUX", "8PgC4ngp", "9k78QZyw"]
allr = []
for fn in FILES:
    fires = {}; tim = {}
    for l in open(f"{D}/{fn}"):
        try: r = json.loads(l)
        except Exception: continue
        if r.get("ev") == "fire": fires[r["buy_sig"]] = r
        elif r.get("ev") == "timing" and r.get("kind") == "fire": tim[r["buy_sig"]] = r
    for sig, f in fires.items():
        tm = tim.get(sig)
        if tm and tm.get("fire_to_seen_ms"): allr.append(((f["t_fire"] - f["t_dump_rx"]) / 1e6 + tm["fire_to_seen_ms"], fn))
for tag, sel in (("runs 1-10 (before nonce)", lambda fn: "r11/" not in fn), ("runs 11-13 (nonce fan-out)", lambda fn: "r11/" in fn)):
    v = [t for t, fn in allr if sel(fn)]
    if v: print(f"  OUR buy, {tag}: n={len(v)} median {med(v)} | p25 {q(v,.25)} | p75 {q(v,.75)} | p90 {q(v,.9)} | over 100 ms: {sum(1 for x in v if x > 100)/len(v):.0%}")
pt = [t for u, w in W.items() if u[:8] in PROS for t in w["t"]]
print(f"  top reacting pros {PROS}: n={len(pt)} median {med(pt)} | p25 {q(pt,.25)} | p75 {q(pt,.75)} | p90 {q(pt,.9)} | over 100 ms: {sum(1 for x in pt if x > 100)/len(pt):.0%}")
ss = [r["ours"][1] == 0 for r in rows if r["ours"]]; print(f"  our filled buys in the dump's own slot: {sum(ss)/len(ss):.0%} (n={len(ss)})")
