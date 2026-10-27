#!/usr/bin/env python3
# PRE-SEND V2 step c5 (g): interaction with the normal (reactive IMIT1) dip bot, MEASURED from the live run logs that ran the
# pre-send SHADOW next to the live reactive bot: FRA r15 (local copy, 10-25 06:08 -> ~07:50 PKT), AMS r14 / r16.
#  - the reactive bot's fires per hour and how long each position blocks the server (fire -> sell landed);
#  - the shadow's row-c fills per hour and how many sat on a dump the reactive bot also acted on (imit marks on the crossing:
#    dump event / in its envelope / picked / fired live), and the reactive bot's realized curve P&L on those shared dumps;
#  - time the server would be blocked by each side (one position per server).
import sys, json, collections, os
import numpy as np
FILES = ["/home/moiz/sniper-data/recon/live/dip_r15.jsonl", "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r14.jsonl",
         "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r16.jsonl"]
OUT = "/home/moiz/sniper-data/presend_v2/c5_interact"
LOG = []
def say(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); LOG.append(s)
import time
pkt = lambda t: time.strftime("%m-%d %H:%M", time.gmtime(t / 1e9 + 18000))
RES = {}
for f in FILES:
    fires = {}; closes = {}; pf = []; pe = {}; ts = []
    for l in open(f):
        if '"ev"' not in l: continue
        if not any(x in l for x in ('"fire"', '"close"', '"presend_fill"', '"presend_exit"', '"run_start"', '"run_end"', '"dump"')): continue
        o = json.loads(l); ev = o.get("ev"); t = o.get("t")
        if isinstance(t, (int, float)) and t > 1e15: ts.append(t)
        if ev == "fire": fires[o.get("dump_sig")] = o
        elif ev == "close": closes[o.get("dump_sig")] = o
        elif ev == "presend_fill" and o.get("row") == "c": pf.append(o)
        elif ev == "presend_exit" and o.get("row") == "c": pe[o["w"]] = o
    if not ts: continue
    h = (max(ts) - min(ts)) / 3.6e12
    held = []
    for s, fo in fires.items():
        c = closes.get(s)
        if c and c.get("held_s") is not None: held.append(float(c["held_s"]) + 0.3)      # buy landed -> sell landed, + the 300 ms margin
    im = collections.Counter()
    shared = []
    for o in pf:
        m = o.get("imit") or {}
        for k, v in m.items():
            if v: im[k] += 1
        if m.get("fired") or m.get("pick"):
            c = closes.get(o["x"]["sig"])
            shared.append(dict(w=o["w"], pick=m.get("pick"), fired=m.get("fired"), reactive_curve=(c or {}).get("curve_pnl"), reactive_spend=(c or {}).get("spend"),
                               presend=pe.get(o["w"], {}).get("pnl")))
    n = len(pf)
    say(f"{os.path.basename(f)}: {pkt(min(ts))} -> {pkt(max(ts))} PKT ({h:.2f} h)")
    say(f"  reactive: fires {len(fires)} ({len(fires) / h:.1f}/h), server blocked per position (fire -> sell landed) "
        + (f"p50 {np.median(held):.2f} s, mean {np.mean(held):.2f} s -> {100 * len(fires) * np.mean(held) / (h * 3600):.2f}% of the time" if held else "n/a"))
    say(f"  pre-send shadow row c: fills {n} ({n / h:.1f}/h); on the crossing the reactive bot saw a dump event {im['dump']} ({100 * im['dump'] / max(n, 1):.0f}%), "
        f"in envelope {im['env']}, picked {im['pick']} ({100 * im['pick'] / max(n, 1):.1f}%), fired live {im['fired']}, M2 {im['m2']}")
    for s in shared: say(f"    shared dump w{s['w']}: pick {s['pick']} fired {s['fired']} reactive curve P&L {s['reactive_curve']} on {s['reactive_spend']} | pre-send shadow P&L (0.55) {s['presend']}")
    RES[os.path.basename(f)] = dict(hours=h, fires=len(fires), held=held, fills=n, imit=dict(im), shared=shared)
json.dump(RES, open(OUT + ".json", "w"), default=float)
open(OUT + ".txt", "w").write("\n".join(LOG) + "\n")
