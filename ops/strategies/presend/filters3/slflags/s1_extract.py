#!/usr/bin/env python3
"""SL-REDFLAGS s1 (copy of TAIL t1 + tolerant json for partial live logs): one row per LIVE position of a run file.
landing record (the crossing dump d, trades between), close, realized P&L (sum over the position's realized records), tape.
usage: t1_extract.py RUN.presend.jsonl OUT.jsonl"""
import sys, json, collections
src, dst = sys.argv[1], sys.argv[2]
arm, fill, close, real, tape, disarm = {}, {}, {}, collections.defaultdict(float), collections.defaultdict(list), {}
start = None
LIVE = '"ev":"presend_live_'
for line in open(src, errors="replace"):
    if LIVE not in line:
        if '"ev":"run_start"' in line: start = json.loads(line)
        continue
    try: d = json.loads(line)
    except Exception: continue
    e = d["ev"]
    m = d.get("mint") or (d.get("trig") or {}).get("mint")
    k = (d.get("w"), m)
    if e == "presend_live_arm": arm[k] = d
    elif e == "presend_live_fill": fill.setdefault(k, d)
    elif e == "presend_live_close": close[k] = d
    elif e == "presend_live_realized": real[k] += d["pnl"]
    elif e == "presend_live_tape": tape[m].append(d)
sigs = {f["sig"]: k for k, f in fill.items()}
att, land = {}, {}
for line in open(src, errors="replace"):
    if '"ev":"presend_attempt' not in line: continue
    i = line.find('"sig":"')
    s = line[i + 7:line.find('"', i + 7)]
    if s not in sigs: continue
    try: d = json.loads(line)
    except Exception: continue
    if d["ev"] == "presend_attempt": att[s] = d
    elif d["ev"] == "presend_attempt_land": land[s] = d
with open(dst, "w") as o:
    for k, f in fill.items():
        if k not in real: continue
        c = close.get(k, {})
        sl = (c.get("sell_land") or [None])[0]
        tp = [x for x in tape.get(k[1], []) if x["slot"] >= f["slot"] and (sl is None or x["slot"] <= sl + 2)]
        a = att.get(f["sig"], {}); L = land.get(f["sig"], {})
        o.write(json.dumps({"w": k[0], "mint": k[1], "pnl": real[k] / 1e9, "t": f["t"], "arm": arm.get(k), "fill": f,
            "att": {x: a.get(x) for x in ("pos", "slot", "t", "p", "vsol", "vtok", "lim")},
            "land": {x: L.get(x) for x in ("d", "between", "after", "n_between", "kind")},
            "close": {x: c.get(x) for x in ("exit_why", "exit_slot", "sell_land", "held_s", "rounds", "merged")},
            "tape": tp}) + "\n")
print(src, "positions", sum(1 for k in fill if k in real), "att found", len(att), "land found", len(land), "start", bool(start))
