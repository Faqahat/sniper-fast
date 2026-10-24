#!/usr/bin/env python3
# Per forced send path (dip8 --dip-probe-paths): landed share, landing delay after the dump on the LEADER'S clock (PoH, the
# "timing" records), same-slot share, fire -> our tx seen back on a feed; plus the trigger feed lag and our reaction.
# Block-position ms (our_speed.py scale) as a cross-check. usage: python3 -I probe_timing.py <probe.jsonl> [...]
import sys, json, statistics, collections, importlib.util
spec = importlib.util.spec_from_file_location("osp", "/home/moiz/sniper/ops/speedcheck/our_speed.py"); S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
med = lambda v: statistics.median(v) if v else float("nan")
rows = []
for f in sys.argv[1:]:
    ev = [json.loads(l) for l in open(f)]
    lands = {e["sig"]: e for e in ev if e["ev"] == "probe_land"}
    tim = {e["buy_sig"]: e for e in ev if e["ev"] == "timing"}
    for p in [e for e in ev if e["ev"] == "probe"]:
        path = "+".join(w["path"] for w in p["writes"]); l = lands.get(p["buy_sig"]); t = tim.get(p["buy_sig"], {})
        bp = None
        if l:
            pb = S.pos(l["slot"], p["buy_sig"]); pd = S.pos(p["slot"], p["dump_sig"])
            if pb and pd: bp = (l["slot"] - p["slot"]) * S.SLOT_MS + (pb[0] / pb[1] - pd[0] / pd[1]) * S.SLOT_MS
        same = None
        if t.get("dump_poh") and t.get("buy_poh"): same = t["dump_poh"][0] == t["buy_poh"][0]
        elif l: same = l["slot"] == p["slot"]
        rows.append(dict(path=path, client=p["client"], landed=l is not None, poh=t.get("land_ms_poh"), bp=bp, seen=t.get("fire_to_seen_ms"),
                         lag=t.get("exec_lag_ms"), react=t.get("reaction_ms"), same=same, feed=t.get("dump_first_feed")))
print(f"{'path':12s}  n  landed  same-slot  leader-clock ms (median, all)                block-pos ms  fire->seen ms")
for path in sorted({r["path"] for r in rows}):
    v = [r for r in rows if r["path"] == path]
    poh = sorted(round(r["poh"], 1) for r in v if r["poh"] is not None)
    bp = [r["bp"] for r in v if r["bp"] is not None]; seen = [r["seen"] for r in v if r["seen"] is not None]
    print(f"{path:12s} {len(v):2d}  {sum(r['landed'] for r in v):2d}      {sum(1 for r in v if r['same']):2d}       {med(poh):6.1f}  {poh[:12]}   {med(bp):6.1f}        {med(seen):6.1f}")
lag = [r["lag"] for r in rows if r["lag"] is not None]; react = [r["react"] for r in rows if r["react"] is not None]
feeds = collections.Counter(r["feed"] for r in rows if r["feed"])
print(f"\ntrigger: executed-feed lag behind the first sighting median {med(lag):.2f} ms (p90 {sorted(lag)[int(0.9 * (len(lag) - 1))] if lag else float('nan'):.2f}); "
      f"our reaction (first sighting -> fire) median {med(react):.2f} ms; first sighting by feed {dict(feeds)}")
