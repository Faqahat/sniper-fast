#!/usr/bin/env python3
"""Where do our ~150 ms go? For every landed trade, split "trigger executed -> our transaction executed" into
  seen:  trigger executed -> the trigger reached us (first feed)
  ours:  reached us -> our copies sent (engine + build + sign + send)
  land:  sent -> our transaction executed at the leader
Anchor: per slot, offset = min over its transactions of (first arrival wall-clock - PoH ms in slot), i.e. the slot's
start on the wall clock plus the smallest delivery delay we saw. Execution wall time of a transaction ~ offset + its
PoH ms (so "seen" is the trigger's delay beyond the slot's best-delivered transaction). usage: latency.py <segs..>"""
import json, sys, os, subprocess, collections

HERE = os.path.dirname(os.path.abspath(__file__))
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n = 0
    for c in s: n = n * 58 + B58.index(c)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + raw
sig8 = lambda s: b58d(s)[:8].hex()
q = lambda v, p: (round(sorted(v)[min(len(v) - 1, int(len(v) * p))], 1) if v else None)
def lines(seg, name):
    p = os.path.join(seg, name)
    if os.path.exists(p):
        with open(p) as f: yield from f
    elif os.path.exists(p + ".zst"):
        pr = subprocess.Popen(["bun", os.path.join(HERE, "unzst.js"), p + ".zst"], stdout=subprocess.PIPE, text=True, bufsize=1 << 20)
        yield from pr.stdout
        pr.wait()

rows = []
for seg in sys.argv[1:]:
    A = {x["attempt"]: x for x in map(json.loads, lines(seg, "attempts.jsonl"))}
    O = {x["attempt"]: x for x in map(json.loads, lines(seg, "outcomes.jsonl"))}
    C = collections.defaultdict(list)
    for x in map(json.loads, lines(seg, "copies.jsonl")): C[x["attempt"]].append(x)
    slots = set()
    for i, a in A.items():
        o = O.get(i, {})
        if o.get("poh") and o["poh"].get("trigger"): slots.add(o["poh"]["trigger"]["slot"])
        if o.get("poh") and o["poh"].get("ours"): slots.add(o["poh"]["ours"]["slot"])
    # PoH ms of every transaction in those slots, then the min (first arrival - PoH ms) per slot
    pohms = {}
    for l in lines(seg, "poh.log"):
        p = l.split()
        if len(p) == 3 and int(p[1]) in slots and p[0] not in pohms: pohms[p[0]] = (int(p[1]), float(p[2]))
    off = {}
    for l in lines(seg, "txarr.log"):
        p = l.split(maxsplit=3)
        if len(p) < 3 or p[0] not in pohms: continue
        slot, ms = pohms[p[0]]
        v = int(p[2]) / 1e6 - ms
        if slot not in off or v < off[slot]: off[slot] = v
    for i, a in A.items():
        o = O.get(i, {})
        po = o.get("poh") or {}
        if not (po.get("trigger") and po.get("ours")): continue
        ts, tm = po["trigger"]["slot"], po["trigger"]["ms_in_slot"]
        us, um = po["ours"]["slot"], po["ours"]["ms_in_slot"]
        if ts not in off or us not in off: continue
        trig_exec = off[ts] + tm            # ms, wall clock (plus the slot's smallest delivery delay)
        ours_exec = off[us] + um
        rx = a["st"]["rx"] / 1e6
        sent = min((c["t_sent"] for c in C[i] if c.get("t_sent")), default=a["st"]["signed"]) / 1e6
        landed = o.get("landed")
        rows.append({"seg": seg, "attempt": i, "path": landed, "path_arm": a.get("path_arm"), "seen": rx - trig_exec, "ours": sent - rx,
                     "land": ours_exec - sent, "total": po.get("ours_ms_after_trigger"), "slots_after": us - ts, "trig_ms_in_slot": tm,
                     "trigger_feed": a.get("trigger_feed"), "ok": o.get("ok")})
json.dump(rows, open("latency.json", "w"))
print(f"{len(rows)} landed trades with both positions anchored")
for k in ("seen", "ours", "land", "total"):
    v = [r[k] for r in rows if r[k] is not None]
    print(f"  {k:6} p10/p25/p50/p75/p90 {q(v,.1)} / {q(v,.25)} / {q(v,.5)} / {q(v,.75)} / {q(v,.9)} ms")
print("  slots after the trigger:", dict(collections.Counter(r["slots_after"] for r in rows)))
print("  land by slots_after:", {k: q([r["land"] for r in rows if r["slots_after"] == k], .5) for k in sorted({r["slots_after"] for r in rows})})
print("  land p50 by path:", {p: (sum(1 for r in rows if r["path"] == p), q([r["land"] for r in rows if r["path"] == p], .5)) for p in sorted({r["path"] for r in rows if r["path"]})})
print("  seen p50 by trigger feed:", {f: (sum(1 for r in rows if r["trigger_feed"] == f), q([r["seen"] for r in rows if r["trigger_feed"] == f], .5)) for f in sorted({r["trigger_feed"] for r in rows if r["trigger_feed"]})})
# where in the slot was the trigger, and did we make the same slot?
for lo, hi in ((0, 100), (100, 200), (200, 300), (300, 400)):
    sub = [r for r in rows if lo <= r["trig_ms_in_slot"] < hi]
    if sub: print(f"  trigger at {lo}-{hi} ms of its slot: n={len(sub)}, same slot {sum(1 for r in sub if r['slots_after'] == 0)}, land p50 {q([r['land'] for r in sub], .5)}")
