#!/usr/bin/env python3
# PRE-SEND V2 (agent 10-25 PKT) step c1: what the live probe (AMS r16, 10-25 08:49-09:49 PKT) MEASURED about where cheap
# pre-sent attempts land, as inputs for a landing model that can be moved to other attempt rates. Read-only on the run log.
#  1. clocks: the block-position clock a (slot x 212 ms + index share, the replay's clock) vs our server clock (send / rx ns):
#     a robust linear map from every trade seen with both (the x / d / between / after trades in presend_attempt_land);
#  2. per landed attempt: tau = landing on the block clock - send time mapped to the block clock (transit + leader scheduling),
#     by leader client and by send phase; the slots after the send; deadline failures;
#  3. feed delay f = our rx of a trade - its block-clock time (how long after a crossing our signer still uses the old price);
#  4. send pacing: gaps between consecutive attempts of a window (k per slot -> 212/k ms);
#  5. per dump inside an armed window (every >= 2% one-trade drop the land records name as d): the first attempt landing after
#     it that was signed before we saw it (= the first one that could fill), D = its landing - the dump (block clock);
#     and the fills' own D (the crossing trade = x).
# -> /home/moiz/sniper-data/presend_v2/c1_landing.json (+ .txt)
import sys, json, collections, math
import numpy as np
F = sys.argv[1] if len(sys.argv) > 1 else "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r16.jsonl"
OUT = "/home/moiz/sniper-data/presend_v2/c1_landing"
LOG = []
def say(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); LOG.append(s)
def q(v, ps=(10, 25, 50, 75, 90)):
    v = np.asarray([x for x in v if x is not None], float)
    if len(v) == 0: return "n 0"
    return f"n {len(v)}: " + " | ".join(f"p{p} {np.percentile(v, p):.1f}" for p in ps) + f" | mean {v.mean():.1f}"

att = {}; land = {}; arms = {}; dis = {}; fills = {}
for l in open(F):
    if '"presend_' not in l: continue
    o = json.loads(l); ev = o["ev"]
    if ev == "presend_attempt": att[o["sig"]] = o
    elif ev == "presend_attempt_land": land[o["sig"]] = o
    elif ev == "presend_live_arm": arms[o["w"]] = o
    elif ev == "presend_live_disarm": dis[o["w"]] = o
    elif ev == "presend_live_fill": fills[o["w"]] = o
say(f"probe file {F}: attempts {len(att)}, land records {len(land)}, armed windows {len(arms)}, fills {len(fills)}")

# ---- 1. clock map from trades seen with both clocks
pairs = {}
for l in land.values():
    for k in ("x", "d"):
        z = l.get(k)
        if z and z.get("a") and z.get("t"): pairs[(z["slot"], z["idx"], z.get("j", 0))] = (z["a"], z["t"] / 1e6, z.get("first_rx", z["t"]) / 1e6)
    for z in (l.get("between") or []) + (l.get("after") or []):
        if z.get("a") and z.get("t"): pairs[(z["slot"], z["idx"], z.get("j", 0))] = (z["a"], z["t"] / 1e6, z.get("first_rx", z["t"]) / 1e6)
P = np.array(list(pairs.values()))
a_, t_, f_ = P[:, 0], P[:, 1], P[:, 2]
# rx - a = offset + feed delay; the offset can drift (real slot time != 212 ms): fit the LOWER envelope (p5 per 5-min bin)
bins = np.floor((t_ - t_.min()) / 300e3).astype(int)
bx, by = [], []
for b in np.unique(bins):
    m = bins == b
    if m.sum() < 30: continue
    bx.append(np.median(t_[m])); by.append(np.percentile(f_[m] - a_[m], 5))
co = np.polyfit(np.array(bx), np.array(by), 1)
off = lambda t: np.polyval(co, t)       # rx(server ms) ~ a + off(t) + feed delay
fd = f_ - a_ - off(f_)
say(f"(1) clock map from {len(P)} trades: rx - a lower envelope drifts {co[0] * 3600e3:+.1f} ms per hour (real slot time ~{212 * (1 + co[0]):.2f} ms if the drift is the slot clock); "
    f"feed delay above the envelope (first sighting): {q(fd)}")

# ---- 2. tau per landed attempt
rows = []
for s, a in att.items():
    l = land.get(s)
    if not l or l.get("res") == "unseen" or l.get("a") is None: continue
    ts = a["t"] / 1e6
    tau = l["a"] - (ts - off(ts))           # landing (block clock) - send mapped to the block clock
    rows.append(dict(sig=s, w=a["w"], n=a["n"], ts=ts, a=l["a"], tau=tau, res=l["res"], client=a.get("client") or "?", slot=l.get("slot"),
                     send_slot=a.get("slot"), deadline=a.get("deadline"), s2rx=l.get("ms_send_to_rx"), lim=a.get("lim"), p=a.get("p")))
tau = np.array([r["tau"] for r in rows])
say(f"(2) tau (send -> landing, block clock, incl. leader scheduling) all landed attempts {q(tau)}")
for res in ("6042", "ok", "deadline", "ata_exists"):
    say(f"     res {res:10s} {q([r['tau'] for r in rows if r['res'] == res])}")
for c in sorted(set(r["client"] for r in rows)):
    v = [r["tau"] for r in rows if r["client"] == c]
    if len(v) >= 20: say(f"     client {c:18s} {q(v)}")
say(f"     send -> rx on the feed (server clock, as ps13): {q([r['s2rx'] for r in rows])}")
dl = collections.Counter((r["slot"] - r["send_slot"]) if r["slot"] is not None and r["send_slot"] is not None else None for r in rows)
say(f"     landing slot - the send's slot: {dict(sorted(dl.items(), key=lambda kv: (kv[0] is None, kv[0])))}")
dd = [r for r in rows if r["res"] == "deadline"]
say(f"     deadline failures {len(dd)} ({100 * len(dd) / len(rows):.1f}%), their tau {q([r['tau'] for r in dd])}")
# phase of the send inside the slot (does the leader-slot position matter?)
ph = np.array([((r["ts"] - off(r["ts"])) % 212.0) for r in rows])
for lo in range(0, 212, 53):
    m = (ph >= lo) & (ph < lo + 53)
    say(f"     send phase {lo:3d}-{lo + 53:3d} ms of the slot: {q(tau[m], (25, 50, 75))}")

# ---- 4. pacing
gaps = []
byw = collections.defaultdict(list)
for a in att.values(): byw[a["w"]].append(a["t"] / 1e6)
for w, v in byw.items():
    v.sort(); gaps += list(np.diff(v))
armed_ms = sum(d.get("armed_ms") or 0 for d in dis.values())
say(f"(4) pacing: gaps between a window's attempts {q(gaps)}; attempts per armed slot {len(att) / max(armed_ms / 212.0, 1):.2f} "
    f"({len(att)} attempts over {armed_ms / 1000:.0f} s armed)")

# ---- 3 + 5. per dump in an armed window: first VALID landing after it
R_by_w = collections.defaultdict(list)
for r in rows: R_by_w[r["w"]].append(r)
dumps = {}
for l in land.values():
    d = l.get("d")
    if not d or not d.get("a"): continue
    key = (l["w"], d["slot"], d["idx"], d.get("j", 0))
    dumps[key] = d
D_rows = []
for (w, s, i, j), d in dumps.items():
    X = d["a"]; seen = d.get("first_rx", d["t"]) / 1e6       # when we first saw the dump (server ms)
    cand = sorted((r for r in R_by_w[w] if r["a"] > X), key=lambda r: r["a"])
    valid = [r for r in cand if r["ts"] < seen]
    first_any = cand[0]["a"] - X if cand else None
    first_valid = valid[0]["a"] - X if valid else None
    D_rows.append(dict(w=w, X=X, drop=d.get("drop_pct"), f=seen - X - off(seen), any=first_any, valid=first_valid,
                       valid_res=valid[0]["res"] if valid else None, valid_slot_gap=(valid[0]["slot"] - s) if valid else None,
                       n_inflight=sum(1 for r in R_by_w[w] if r["ts"] < seen and r["a"] > X)))
say(f"(3) feed delay of the dumps we saw (first sighting - block clock - envelope): {q([r['f'] for r in D_rows])}")
say(f"(5) {len(D_rows)} dumps (>= 2% one-trade drops) inside armed windows, first landing after the dump (block clock):")
say(f"     any attempt          {q([r['any'] for r in D_rows])}")
say(f"     signed before we saw it (could fill) {q([r['valid'] for r in D_rows])}; none landed after it: {sum(1 for r in D_rows if r['valid'] is None)}")
big = [r for r in D_rows if (r["drop"] or 0) >= 10]
say(f"     dumps >= 10%: {q([r['valid'] for r in big])}")
say(f"     attempts in flight at the dump (signed before we saw it, landing after it): {q([r['n_inflight'] for r in D_rows], (10, 50, 90))}")
# fills
Dx = []
for w, fl in fills.items():
    l = land.get(fl["sig"])
    if l and l.get("ms_after_x_a") is not None: Dx.append(l["ms_after_x_a"])
say(f"     the 20 fills, after their crossing trade: {q(Dx)}")
json.dump(dict(co=list(co), tau=[(r["tau"], r["client"], r["res"], r["slot"] - r["send_slot"] if r["slot"] is not None and r["send_slot"] is not None else None) for r in rows],
               fd=list(fd), gaps=list(gaps), D=D_rows, Dx=Dx, att_per_slot=len(att) / max(armed_ms / 212.0, 1)),
          open(OUT + ".json", "w"), default=float)
open(OUT + ".txt", "w").write("\n".join(LOG) + "\n")
