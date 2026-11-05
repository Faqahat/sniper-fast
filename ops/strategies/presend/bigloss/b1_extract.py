#!/usr/bin/env python3
"""BIGLOSS b1: one row per LIVE position (w, mint) of one run: arm, fill (+ann), filled attempt (signing state), its landing
record (crossing dump d + trades between), close, realized P&L, fam, the run's presend_live_tape trades of that mint and the obs
hold_tape (3 s of trades after the fill, 8-char wallet prefixes).  Read-only on inputs.
usage: b1_extract.py RUN_JSONL OBS_GLOB_PREFIX OUT.jsonl RUN"""
import sys, json, collections, glob
src, obsp, dst, run = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
arm, fill, close, real, nreal, tape, fam, disarm = {}, {}, {}, collections.defaultdict(float), collections.Counter(), collections.defaultdict(list), {}, {}
LIVE = '"ev":"presend_live_'
for line in open(src, errors="replace"):
    if LIVE not in line: continue
    try: d = json.loads(line)
    except Exception: continue
    e = d["ev"]
    m = d.get("mint") or (d.get("trig") or {}).get("mint")
    k = (d.get("w"), m)
    if e == "presend_live_arm": arm[k] = d
    elif e == "presend_live_fill": fill.setdefault(k, d)
    elif e == "presend_live_close": close[k] = d
    elif e == "presend_live_realized": real[k] += d["pnl"]; nreal[k] += 1
    elif e == "presend_live_tape": tape[m].append(d)
    elif e == "presend_live_fam": fam[k] = d
    elif e == "presend_live_disarm": disarm[k] = d
sigs = {f["sig"]: k for k, f in fill.items()}
att, land = {}, {}
for line in open(src, errors="replace"):
    if '"ev":"presend_attempt' not in line: continue
    i = line.find('"sig":"')
    if i < 0: continue
    s = line[i + 7:line.find('"', i + 7)]
    if s not in sigs: continue
    d = json.loads(line)
    if d["ev"] == "presend_attempt": att[s] = d
    elif d["ev"] == "presend_attempt_land": land[s] = d
ht = {}
for fn in sorted(glob.glob(obsp + "*")):
    for line in open(fn, errors="replace"):
        if '"ev":"hold_tape"' not in line: continue
        try: d = json.loads(line)
        except Exception: continue
        s = (d.get("fill") or {}).get("sig")
        if s in sigs: ht[s] = d
n = 0
with open(dst, "w") as o:
    for k, f in fill.items():
        if k not in real: continue
        c = close.get(k, {})
        a = att.get(f["sig"], {}); L = land.get(f["sig"], {})
        h = ht.get(f["sig"])
        tp = sorted(tape.get(k[1], []), key=lambda x: (x["slot"], x.get("idx", 0)))
        o.write(json.dumps({"run": run, "w": k[0], "mint": k[1], "pnl": real[k] / 1e9, "nreal": nreal[k], "t": f["t"],
            "arm": arm.get(k), "fill": f, "fam": fam.get(k),
            "att": {x: a.get(x) for x in ("pos", "slot", "t", "p", "vsol", "vtok", "lim", "spend")},
            "land": {x: L.get(x) for x in ("d", "between", "after", "n_between", "kind")},
            "close": {x: c.get(x) for x in ("exit_why", "exit_slot", "sell_land", "sell_lands", "held_s", "rounds", "merged", "spend", "sol_in_curve", "sol_out_curve", "tips", "result")},
            "tape": tp,
            "ht": None if not h else {x: h.get(x) for x in ("trades", "dump", "exit", "sells", "first_big_sell", "first_1sol_sell", "followers")}}) + "\n")
        n += 1
print(run, "positions", n, "att", len(att), "land", len(land), "hold_tape", len(ht), "arms", len(arm), file=sys.stderr)
