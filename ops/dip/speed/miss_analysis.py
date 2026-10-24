#!/usr/bin/env python3
# Owner 10-24 03:55 PKT: "check our failed txns, see how we are lagging behind, anything we can do to fix that".
# For every buy of ours (PROD runs + FRZ tests): block-position ms (x 212 ms) of the dump, of every trade after it (tape), of
# OUR tx; the moment the price first went over our guard (post-dump price x guard) = cross_ms, who did it; lag = our_ms -
# cross_ms -> "how much faster we had to be". Plus run 2's timing records (feed lag, decision, send -> seen). READ-ONLY RPC.
# usage: python3 -I miss_analysis.py <label>=<run.jsonl>:<guard> ...
import sys, json, statistics, collections, importlib.util
spec = importlib.util.spec_from_file_location("osp", "/home/moiz/sniper/ops/speedcheck/our_speed.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
OURS = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS"}
TGT = {"HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ": "HkQ7hMjy", "DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw": "DYXDDrZC", "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq": "haqqiUUX"}
size_cache = {}
def bsize(slot):
    if slot not in size_cache:
        b = S.block(slot); size_cache[slot] = len(b) if b else None
    return size_cache[slot]
def bp_ms(slot, idx, d_slot, d_idx, d_size):
    sz = bsize(slot)
    return None if not sz else (slot - d_slot) * S.SLOT_MS + (idx / sz - d_idx / d_size) * S.SLOT_MS
rows = []
for arg in sys.argv[1:]:
    lab, rest = arg.split("=", 1); path, g = rest.rsplit(":", 1); guard = float(g)
    ev = [json.loads(l) for l in open(path)]
    tim = {e["buy_sig"]: e for e in ev if e["ev"] == "timing"}
    for f in [e for e in ev if e["ev"] == "fire"]:
        sig = f["buy_sig"]
        bl = next((e for e in ev if e["ev"] == "buy_land" and e.get("sig") == sig), None)
        lp = next((e for e in ev if e["ev"] == "land_poll" and e.get("sig") == sig), {})
        bf = next((e for e in ev if e["ev"] == "buy_failed" and e.get("sig") == sig), None)
        cl = next((e for e in ev if e["ev"] == "close" and e.get("buy_sig") == sig), {})
        pk = next((e for e in ev if e["ev"] == "pick" and e["mint"] == f["mint"] and e["sig"] == f["dump_sig"]), {})
        dmp = next((e for e in ev if e["ev"] == "dump" and e["sig"] == f["dump_sig"]), {})
        land_slot = (bl or {}).get("slot") or lp.get("land_slot") or (bf or {}).get("slot")
        dpos = S.pos(f["slot"], f["dump_sig"]); opos = S.pos(land_slot, sig) if land_slot else None
        if not dpos or not opos or not dmp: continue
        d_idx, d_size = dpos
        our_ms = bp_ms(land_slot, opos[0], f["slot"], d_idx, d_size)
        p0 = dmp["vsol"] / dmp["vtok"]
        tape = sorted([e for e in ev if e["ev"] == "tape" and e["mint"] == f["mint"] and e["user"] not in OURS and (e["slot"], e["idx"]) > (f["slot"], d_idx)],
                      key=lambda e: (e["slot"], e["idx"], e["j"]))
        ahead = [e for e in tape if (e["slot"], e["idx"]) < (land_slot, opos[0])]
        cross = next((e for e in ahead if (e["vsol"] / e["vtok"]) / p0 > guard), None)
        ratio = (ahead[-1]["vsol"] / ahead[-1]["vtok"]) / p0 if ahead else 1.0
        cross_ms = bp_ms(cross["slot"], cross["idx"], f["slot"], d_idx, d_size) if cross else None
        first_ms = bp_ms(ahead[0]["slot"], ahead[0]["idx"], f["slot"], d_idx, d_size) if ahead else None
        err = json.dumps(cl.get("err") or lp.get("err") or "")
        res = "FILL" if bl else "guard" if "6042" in err else "deadline" if "6001" in err else "?"
        t = tim.get(sig, {})
        rows.append(dict(lab=lab, mint=f["mint"][:6], res=res, client=f["client"], our_ms=our_ms, dslot=land_slot - f["slot"], ratio=ratio, cross_ms=cross_ms,
                         cross_who=(TGT.get(cross["user"], cross["user"][:6]) if cross else None), cross_sig=cross["sig"] if cross else None, first_ms=first_ms,
                         n_ahead=len(ahead), sol_ahead=sum(e["sol"] for e in ahead if e["buy"]) / 1e9, dump_sol=dmp.get("sell", 0) if False else (pk.get("feats") or [0, 0])[1],
                         decision_us=f["decision_us"], exec_lag=t.get("exec_lag_ms"), react=t.get("reaction_ms"), seen=t.get("fire_to_seen_ms"),
                         paths="+".join(w["path"] for w in f["writes"])))
json.dump(rows, open("/home/moiz/sniper/ops/dip/speed/miss_analysis.json", "w"), indent=1)
print(f"{'run':6s} {'token':7s} {'result':8s} {'leader':18s} {'paths':16s} {'we landed':>10s} {'+5% crossed':>12s} {'late by':>8s} {'price at us':>11s} {'first buyer':>11s} ahead (SOL)  who crossed")
for r in rows:
    late = (r["our_ms"] - r["cross_ms"]) if r["cross_ms"] is not None else None
    print(f"{r['lab']:6s} {r['mint']:7s} {r['res']:8s} {r['client'][:18]:18s} {r['paths'][:16]:16s} {r['our_ms']:8.0f}ms {('%.0fms' % r['cross_ms']) if r['cross_ms'] is not None else '-':>12s} "
          f"{('%.0fms' % late) if late is not None else '-':>8s} {100 * (r['ratio'] - 1):+9.1f}% {('%.0fms' % r['first_ms']) if r['first_ms'] is not None else '-':>11s} {r['n_ahead']:3d} ({r['sol_ahead']:4.2f})  {r['cross_who'] or ''}")
miss = [r for r in rows if r["res"] == "guard" and r["cross_ms"] is not None]
lates = sorted(r["our_ms"] - r["cross_ms"] for r in miss)
print(f"\nguard misses with a crossing seen: {len(miss)}; how much earlier we had to land (ms): median {statistics.median(lates):.0f}, all {[round(x) for x in lates]}")
for x in (5, 10, 20, 30, 50):
    print(f"  {x:3d} ms faster -> {sum(1 for l in lates if l < x)} of {len(miss)} misses would have filled")
cm = sorted(r["cross_ms"] for r in miss); print(f"the price crossed +5% at (ms after the dump): median {statistics.median(cm):.0f}, p25 {cm[len(cm) // 4]:.0f}, p75 {cm[3 * len(cm) // 4]:.0f}")
fills = [r for r in rows if r["res"] == "FILL"]; print(f"fills: we landed at median {statistics.median([r['our_ms'] for r in fills]):.0f} ms; misses: median {statistics.median([r['our_ms'] for r in miss]):.0f} ms")
who = collections.Counter(r["cross_who"] for r in miss); print("who pushed the price over +5% first:", dict(who.most_common(12)))
t2 = [r for r in rows if r["seen"] is not None]
if t2: print(f"run 2 time split (n {len(t2)}): exec-feed lag median {statistics.median([r['exec_lag'] for r in t2 if r['exec_lag'] is not None]):.1f} ms, first sighting -> fire median {statistics.median([r['react'] for r in t2 if r['react'] is not None]):.2f} ms, fire -> our tx seen median {statistics.median([r['seen'] for r in t2]):.0f} ms")
