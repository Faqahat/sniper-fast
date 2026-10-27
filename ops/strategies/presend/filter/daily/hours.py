import json, sys, datetime as dt
PKT = dt.timezone(dt.timedelta(hours=5))
def fmt(ns): return dt.datetime.fromtimestamp(ns/1e9, PKT).strftime("%m-%d %H:%M")
for path in sys.argv[1:]:
    ts = []; stops = []; fills = 0; arms = 0; spend = set(); starts = []
    for line in open(path, errors="ignore"):
        if '"presend_live' not in line and '"start' not in line: continue
        try: d = json.loads(line)
        except Exception: continue
        ev = d.get("ev", "")
        t = d.get("t") or d.get("ts")
        if not ev.startswith("presend_live"): continue
        if t: ts.append(t)
        if ev == "presend_live_stop": stops.append((t, {k: v for k, v in d.items() if k not in ("ev",)}))
        if ev == "presend_live_fill": fills += 1
        if ev == "presend_live_arm": arms += 1; spend.add(d.get("spend"))
    ts.sort()
    # gaps > 20 min between consecutive pre-send events = pre-send off (cap reached / restart)
    gaps = [(a, b) for a, b in zip(ts, ts[1:]) if b - a > 20*60e9]
    act = (ts[-1] - ts[0])/3.6e12 - sum((b - a) for a, b in gaps)/3.6e12 if ts else 0
    print(path.split("/")[-1], "| fills", fills, "arms", arms, "size", sorted(s/1e9 for s in spend if s), "| first", fmt(ts[0]) if ts else "-", "last", fmt(ts[-1]) if ts else "-", f"| active {act:.2f} h", "| gaps", [(fmt(a), fmt(b)) for a, b in gaps])
    for t, s in stops: print("   stop", fmt(t) if t else "?", str(s)[:200])
