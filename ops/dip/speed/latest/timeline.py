#!/usr/bin/env python3
# Per-fire timeline from all live runs (r1–r10 FRA, r9–r10 AMS). Local clock (one machine per region, same feed for every tx):
# dump seen -> we fire (reaction) -> our tx seen back (fire_to_seen) ; rivals' buys on the same token seen at t (ms after the dump was seen).
import json, glob, collections, statistics
OURS = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
FILES = [f"dip_r{i}.jsonl" for i in range(1, 10)] + ["latest/dip_r10.jsonl", "dip_ams_r9.jsonl", "latest/dip_ams_r10.jsonl"]
rows = []
for fn in FILES:
    region = "AMS" if "ams" in fn else "FRA"; fires = {}; tim = {}; tape = collections.defaultdict(list); res = {}; picks = {}
    for l in open(fn):
        try: r = json.loads(l)
        except Exception: continue
        e = r.get("ev")
        if e == "fire": fires[r["buy_sig"]] = r
        elif e == "pick": picks[r.get("mint"), r.get("idx")] = r
        elif e == "timing" and r.get("kind") == "fire": tim[r["buy_sig"]] = r
        elif e == "tape": tape[r["mint"]].append(r)
        elif e == "close": res[r["buy_sig"]] = r
    for sig, f in fires.items():
        t0 = f["t_dump_rx"]; tm = tim.get(sig, {}); c = res.get(sig, {})
        tp = sorted([x for x in tape[f["mint"]] if x["slot"] >= f["slot"]], key=lambda x: (x["slot"], x["idx"]))
        ours = next((x for x in tp if x["user"] in OURS and x["buy"]), None)
        rivals = [x for x in tp if x["buy"] and x["user"] not in OURS and x["slot"] <= f["slot"] + 1]
        before = [x for x in rivals if ours is None or (x["slot"], x["idx"]) < (ours["slot"], ours["idx"])]
        pk = picks.get((f["mint"], c.get("dump_idx")), {})
        rows.append(dict(region=region, run=fn.split("/")[-1], sig=sig, mint=f["mint"], client=f.get("client"), leader=f.get("leader"), route=f.get("route"), paths=pk.get("paths"),
                         dump_slot=f["slot"], t0=t0, reaction=(f["t_fire"] - t0) / 1e6, fire_to_seen=tm.get("fire_to_seen_ms"),
                         ours_ms=(ours["t"] - t0) / 1e6 if ours else None, ours_slot=(ours["slot"] - f["slot"]) if ours else None, ours_idx=ours["idx"] if ours else None,
                         first_rival_ms=(rivals[0]["t"] - t0) / 1e6 if rivals else None, n_before=len(before),
                         before_ms=[round((x["t"] - t0) / 1e6, 1) for x in before[:6]], before_users=[x["user"][:8] for x in before[:6]],
                         result=c.get("result"), lat_us=f.get("lat_us")))
json.dump(rows, open("latest/timeline.json", "w"))
med = lambda v: statistics.median(v) if v else float("nan")
q = lambda v, p: sorted(v)[int(len(v) * p)] if v else float("nan")
print(f"fires: {len(rows)} | results: {collections.Counter(r['result'] for r in rows).most_common()}")
for reg in ("FRA", "AMS"):
    v = [r for r in rows if r["region"] == reg]
    if not v: continue
    rx = [r["reaction"] for r in v]; fs = [r["fire_to_seen"] for r in v if r["fire_to_seen"]]; om = [r["ours_ms"] for r in v if r["ours_ms"] is not None]
    fr = [r["first_rival_ms"] for r in v if r["first_rival_ms"] is not None]
    print(f"\n== {reg}: {len(v)} fires")
    print(f"   our reaction (dump seen -> fire): median {med(rx):.2f} ms, p90 {q(rx, .9):.2f}")
    print(f"   our fire -> our tx seen back: median {med(fs):.1f} ms, p10 {q(fs, .1):.1f}, p90 {q(fs, .9):.1f}  (n={len(fs)})")
    print(f"   our tx seen after dump seen: median {med(om):.1f} ms, p10 {q(om, .1):.1f}, p90 {q(om, .9):.1f}")
    print(f"   FIRST rival buy seen after dump seen: median {med(fr):.1f} ms, p10 {q(fr, .1):.1f}, p90 {q(fr, .9):.1f}")
    print(f"   share of fires where a rival buy was seen within 5 ms of the dump: {sum(1 for x in fr if x <= 5) / max(len(fr),1):.0%} | within 2 ms: {sum(1 for x in fr if x <= 2)/max(len(fr),1):.0%}")
    print(f"   rival buys landing before ours: median {med([r['n_before'] for r in v]):.0f}")
    for cl in sorted({r["client"] for r in v if r["client"]}):
        w = [r for r in v if r["client"] == cl]; fs2 = [r["fire_to_seen"] for r in w if r["fire_to_seen"]]; fr2 = [r["first_rival_ms"] for r in w if r["first_rival_ms"] is not None]
        print(f"     {cl:18s} n={len(w):3d} | fire->seen med {med(fs2):5.1f} | ours after dump med {med([r['ours_ms'] for r in w if r['ours_ms'] is not None]):5.1f} | first rival med {med(fr2):5.1f}")
