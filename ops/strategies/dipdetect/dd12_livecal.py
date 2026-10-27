#!/usr/bin/env python3
# Live calibration of the replay (run 10, both servers, fresh logs in dipdetect/live/): every live fire inside the R4 data window
# matched to its dd1_R4 row -> replay guard outcome at 35 / 50 / 75 ms vs the live buy result, and replay P&L (the live exit of that
# server, scaled to the live size; after pump fees, before fixed costs) vs the live curve P&L minus 2 x 1.25% pump fee. MEASURED.
import json, glob
import numpy as np
import dd_lib as L
if __name__ == "__main__":
    d = L.load("R4", window=False)
    meta = json.load(open(f"{L.OUT}/day_R4_meta.json"))["meta"]
    key = {}
    for i in range(len(d["k"])): key.setdefault((meta[d["tok"][i]]["m"], int(d["s"][i])), []).append(i)
    rows = []
    for f, ex, srv in ((f"{L.OUT}/live/dip_r10.jsonl", "c19_tpnone_sl20", "FRA"), (f"{L.OUT}/live/dip_ams_r10.jsonl", "c6_tpnone_sl10", "AMS")):
        fires = {}; closes = {}
        for l in open(f):
            o = json.loads(l)
            if o.get("ev") == "fire": fires[o["buy_sig"]] = o
            if o.get("ev") == "close": closes[o["buy_sig"]] = o
        for sig, fo in fires.items():
            c = closes.get(sig)
            if c is None: continue
            ii = key.get((fo["mint"], c.get("dump_slot") or fo["slot"]))
            if not ii: continue
            # the dump row: same slot, closest drop to the live dump (several sells per slot are rare)
            i = ii[0]
            size = fo["spend"] / 1e9
            live_fill = c.get("result") == "sold"
            rp = [(int(d["st"][i, li]), float(d["pnl"][i, li, L.EXI[ex]]) * size / 0.55 if d["st"][i, li] == 0 else None) for li in range(3)]
            rows.append(dict(srv=srv, mint=fo["mint"][:6], size=size, live_fill=live_fill, live_pnl=((c.get("curve_pnl") or 0) / 1e9 - 0.025 * size) if live_fill else None, rp=rp))
    print(f"live fires matched to the R4 replay: {len(rows)}")
    for li, lat in enumerate((35, 50, 75)):
        agree = np.mean([(r["rp"][li][0] == 0) == r["live_fill"] for r in rows])
        rf = np.mean([r["rp"][li][0] == 0 for r in rows]); lf = np.mean([r["live_fill"] for r in rows])
        both = [r for r in rows if r["live_fill"] and r["rp"][li][0] == 0]
        lp = np.array([r["live_pnl"] for r in both]); pp = np.array([r["rp"][li][1] for r in both])
        print(f"  {lat} ms: replay fill rate {rf:.2f} vs live {lf:.2f}, same outcome {agree:.2f}; both filled {len(both)}: live curve P&L {lp.sum():+.3f} "
              f"(mean {lp.mean():+.4f}) vs replay {pp.sum():+.3f} (mean {pp.mean():+.4f}), corr {np.corrcoef(lp, pp)[0, 1]:.2f}")
    for r in rows[:60]:
        print(f"   {r['srv']} {r['mint']} size {r['size']:.2f} live {'FILL ' + format(r['live_pnl'], '+.4f') if r['live_fill'] else 'fail'} | replay " +
              " ".join(f"{('fill ' + format(p, '+.4f')) if s == 0 else ('guard' if s == 1 else 'n/a')}" for s, p in r["rp"]))
