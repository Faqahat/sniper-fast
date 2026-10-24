#!/usr/bin/env python3
# Estimated trades per hour for the dip strategy, from out-of-fold six-block picks (top 5%, spacing 5):
#   attempts/h = model picks per hour; fills/h = picks whose 2% guard passes (the price when we land is <= 1.02 x the dump price)
#   direct-only (shreds), routed (executed feed), and both (the hybrid design), at "35 / 50 / 75 ms"; plus the spread over hours
#   of the day (PKT) and the average SOL per filled trade.
# usage: python3 -I trades_per_hour.py SEL_none.jsonl DIRECT_FLAGS.json EV_FILE
import sys, json, gzip, time, collections, statistics
SEL, FLAGS, EVF = sys.argv[1], sys.argv[2], sys.argv[3]
F = json.load(open(FLAGS))
EV = {}
for l in gzip.open(EVF, "rt"):
    r = json.loads(l); EV[(r["m"], r["age"])] = r
P = [json.loads(l) for l in open(SEL)]
ts = [EV[(p["m"], p["age"])]["bt"] + p["age"] for p in P if (p["m"], p["age"]) in EV]
span_h = (max(ts) - min(ts)) / 3600 if ts else 1
print(f"data span {span_h:.1f} h ({time.strftime('%m-%d %H:%M', time.gmtime(min(ts) + 18000))} -> {time.strftime('%m-%d %H:%M', time.gmtime(max(ts) + 18000))} PKT)")
for L in ("35", "50", "75"):
    rows = [p for p in P if p["LAT"] == L]
    for kind, want in (("direct (shreds)", {1}), ("routed (executed feed)", {0}), ("both (hybrid design)", {0, 1})):
        v = [p for p in rows if F.get(f'{p["m"]}|{p["age"]}') in want]
        if not v: continue
        fills = [p for p in v if (p.get("px") or 1.0) <= 1.02]
        hrs = collections.Counter(time.gmtime(EV[(p["m"], p["age"])]["bt"] + p["age"] + 18000).tm_hour for p in v if (p["m"], p["age"]) in EV)
        days = collections.Counter((time.gmtime(EV[(p["m"], p["age"])]["bt"] + p["age"] + 18000).tm_mday, time.gmtime(EV[(p["m"], p["age"])]["bt"] + p["age"] + 18000).tm_hour) for p in v if (p["m"], p["age"]) in EV)
        per_clock_hour = sorted(days.values())
        lo, hi = (per_clock_hour[len(per_clock_hour) // 10], per_clock_hour[9 * len(per_clock_hour) // 10]) if per_clock_hour else (0, 0)
        g = sum(p["pnl"] for p in fills) - 0.0002 * (len(v) - len(fills))
        print(f'"{L} ms" {kind:24s}: attempts {len(v) / span_h:5.1f}/h, guarded fills {len(fills) / span_h:5.1f}/h ({len(fills) / len(v):.0%}) | '
              f'busiest-10% hours >= {hi}/h, quietest-10% <= {lo}/h | SOL per fill {sum(p["pnl"] for p in fills) / max(len(fills), 1):+.4f} | guarded total {g:+.2f} over {span_h:.1f} h')
