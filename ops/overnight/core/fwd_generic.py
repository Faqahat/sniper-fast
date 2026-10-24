#!/usr/bin/env python3
# FORWARD TEST (read-only, nothing traded) of dryrun/frozen_generic.json on launches created after the freeze.
#  1. stage-1 summaries for R2 launches after the static snapshot (deployer track records need them)
#  2. decision points for launches after the freeze (same code as the search: gf_build.py) -> track-B rules
#  3. FINAL-2 live picks after the freeze -> track A (become_eval.py: base / slip / pro-buys-after-us removed /
#     pros removed / all sniper buys after us removed); follower slippage limits fetched for the forward fills first
#  4. report -> dryrun/forward_generic.txt (+ .json)
# Skips if a dry-run cycle is extracting into phaseA_dry right now. usage: python3 -I fwd_generic.py
import os, sys, json, gzip, time, subprocess, statistics, datetime
CORE = "/home/moiz/sniper/ops/overnight/core"; DRY = "/home/moiz/sniper/ops/overnight/dryrun"
PKT = datetime.timezone(datetime.timedelta(hours=5))
F = json.load(open(f"{DRY}/frozen_generic.json")); T0 = F["frozen_at_unix"]
busy = subprocess.run("ps -eo args | grep -E 'a_extract|cycle.sh' | grep -v grep", shell=True, capture_output=True, text=True).stdout.strip()
if busy: print("dry-run cycle running; try again in a few minutes"); sys.exit(0)
env = dict(os.environ, RP_PHASEA_R2="phaseA_dry")
SNAP_END = max(v["bt"] for v in json.load(open(f"{CORE}/gf_launches.json")).values())
def sh(cmd, extra):
    r = subprocess.run(cmd, shell=True, env=dict(env, **extra), capture_output=True, text=True, cwd=CORE)
    if r.returncode: print(r.stdout[-2000:], r.stderr[-2000:]); raise SystemExit(f"failed: {cmd}")
    return r.stdout
# 1 + 2
sh("python3 -I gf_stage1.py", dict(GF_SINCE=str(SNAP_END - 600), GF_LS_OUT=f"{CORE}/gf_launches_fwd.json", GF_W_OUT=f"{CORE}/gf_wallets_fwd_unused.json"))
LS = json.load(open(f"{CORE}/gf_launches.json")); LS.update(json.load(open(f"{CORE}/gf_launches_fwd.json")))
json.dump(LS, open(f"{CORE}/gf_launches_all.json", "w"))
sh("python3 -I gf_build.py", dict(GF_LS=f"{CORE}/gf_launches_all.json", GF_SINCE=str(T0), GF_OUT=f"{CORE}/gf_points_fwd.jsonl.gz"))
now = time.time()
P = [json.loads(l) for l in gzip.open(f"{CORE}/gf_points_fwd.jsonl.gz", "rt")]
P = [p for p in P if LS[p["m"]]["bt"] <= now - 330]                       # every exit (<= 300 s) complete
FN = list(P[0]["f"].keys()) if P else []
def val(p, k):
    if k in p["f"]: return p["f"][k]
    if k.startswith("rec_"): return p["rec"][["rec_n", "rec_nb60", "rec_pk", "rec_f2x", "rec_m60", "rec_sb60"].index(k)]
    return p[k]
def match(p, rule):
    for c in rule:
        k, op, th = c.split(); v = val(p, k); th = float(th)
        if not (v >= th if op == ">=" else v <= th): return False
    return True
out = dict(frozen_at=F["frozen_at_pkt"], evaluated_at=datetime.datetime.fromtimestamp(now, PKT).strftime("%Y-%m-%d %H:%M PKT"),
           forward_launches=len({p["m"] for p in P}), trackB={}, trackA={})
lines = [f"FORWARD TEST of frozen_generic.json (frozen {F['frozen_at_pkt']}), evaluated {out['evaluated_at']}",
         f"forward launches with decision points: {out['forward_launches']} (created after the freeze, >= 5.5 min old)", "",
         "TRACK B (later entries, 0.5 SOL, cheap send): trades | total SOL | mean % | median % | win | no-sniper-buys-after-us total"]
for b in F["trackB"]:
    tr = [p for p in P if p["T"] == b["T"] and match(p, b["rule"]) and not p["o"][b["exit"]][2]]
    r = [p["o"][b["exit"]][0] for p in tr]; r2 = [p["o"][b["exit"]][1] if p["o"][b["exit"]][1] is not None else p["o"][b["exit"]][0] for p in tr]
    d = dict(n=len(r), tot=round(sum(r) * 0.5, 3), mean=round(statistics.mean(r) * 100, 2) if r else None, med=round(statistics.median(r) * 100, 2) if r else None,
             win=sum(1 for x in r if x > 0), tot_nosnip=round(sum(r2) * 0.5, 3), mints=[p["m"] for p in tr])
    out["trackB"][b["id"]] = d
    lines.append(f"  {b['id']:4s} T={b['T']:3d} {b['exit']:16s} {' & '.join(b['rule']):40s} | {d['n']:3d} | {d['tot']:+6.3f} | "
                 f"{(d['mean'] if d['mean'] is not None else 0):+6.2f} | {(d['med'] if d['med'] is not None else 0):+6.2f} | {d['win']}/{d['n']} | {d['tot_nosnip']:+6.3f}")
# 3: track A
picks = []
for l in open("/home/moiz/sniper-data/collect/shadow/scores_v3.jsonl"):
    try: r = json.loads(l)
    except Exception: continue
    if r.get("type") == "decide" and r.get("final_pick") and r.get("t", 0) >= T0 and r["t"] <= now - 90: picks.append(r["mint"])
json.dump(picks, open(f"{CORE}/fwd_f2_picks.json", "w"))
lines += ["", f"TRACK A (FINAL-2 live picks after the freeze: {len(picks)}; 0.5 SOL, price guard 0.5%; A1 = fast exit if <=1 buyer else 10 s, A2 = 10 s, A4 = 8 s [frozen_generic2]; failed guarded buy -0.005):"]
if picks:
    sh("python3 -I slip_collect_picks.py fwd_f2_picks.json", {})
    sh("python3 -I slip_fetch.py slip_sigs_picks.json", {})
    sh("python3 -I become_eval.py fwd_f2_picks.json 0.5 1.005", dict(LANDS="20,30,35,45,60,75"))
    R = json.load(open(f"{CORE}/fwd_f2_picks_become_B0.5.json"))
    for Lm in ("75", "60", "45", "35", "30", "20"):
        for var in ("slip", "proafter_slip", "nosnip"):
            v = [r[Lm][var] for r in R if r.get(Lm, {}).get(var)]
            fills = [x for x in v if x["fill"]]; nf = len(v) - len(fills)
            A1 = sum((x["pnl"]["eos1"] if x["nb"] <= 1 else x["pnl"]["t10"]) for x in fills) - 0.005 * nf
            A2 = sum(x["pnl"]["t10"] for x in fills) - 0.005 * nf; A4 = sum(x["pnl"]["t8"] for x in fills) - 0.005 * nf
            A5 = sum(x["pnl"]["idle3.0_c30"] for x in fills) - 0.005 * nf; A6 = sum(x["pnl"]["idle2.0_c15"] for x in fills) - 0.005 * nf
            A7 = sum((x["pnl"]["eos1"] if x["nb"] <= 1 else x["pnl"]["t8"]) for x in fills) - 0.005 * nf
            p8 = sorted(x["pnl"]["t8"] for x in fills); med8 = statistics.median(p8) if p8 else 0
            out["trackA"][f"L{Lm}_{var}"] = dict(fills=len(fills), attempts=len(v), A1=round(A1, 3), A2=round(A2, 3), A4=round(A4, 3), A4_med=round(med8, 4), A4_wo_top5=round(A4 - sum(p8[-5:]), 3), A5=round(A5, 3), A6=round(A6, 3), A7=round(A7, 3))
            lines.append(f"  L{Lm} {var:13s} fills {len(fills):3d}/{len(v):3d} | A1 {A1:+6.3f} | A2 (10 s) {A2:+6.3f} | A4 (8 s) {A4:+6.3f} med {med8:+.4f} w/o top5 {A4 - sum(p8[-5:]):+6.3f} | A5 (wave stop 3 s, max 30) {A5:+6.3f} | A6 (2 s, max 15) {A6:+6.3f} | A7 (activity check, 8 s) {A7:+6.3f}")
    # per PKT hour (the daytime question): 75 and 45 ms, pros' later buys removed, 8 s (A4) and activity check (A7), today's costs
    lines += ["", "TRACK A by PKT hour (pros' later buys removed + slippage, today's costs): hour | L75 fills/attempts A4 A7 | L45 fills/attempts A4 A7"]
    byh = {}
    for r in R:
        h = datetime.datetime.fromtimestamp(r["bt"], PKT).hour
        for Lm in ("75", "45"):
            x = r.get(Lm, {}).get("proafter_slip")
            if not x: continue
            e_ = byh.setdefault(h, {}).setdefault(Lm, [0, 0, 0.0, 0.0])
            e_[1] += 1
            if x["fill"]:
                e_[0] += 1; e_[2] += x["pnl"]["t8"]; e_[3] += x["pnl"]["eos1"] if x["nb"] <= 1 else x["pnl"]["t8"]
            else: e_[2] -= 0.005; e_[3] -= 0.005
    for h in sorted(byh):
        c = byh[h]; f = lambda Lm: (f"{c[Lm][0]:3d}/{c[Lm][1]:3d} {c[Lm][2]:+6.3f} {c[Lm][3]:+6.3f}" if Lm in c else "-")
        lines.append(f"  {h:02d}h | {f('75')} | {f('45')}")
    out["trackA_by_hour"] = {str(h): v for h, v in byh.items()}
json.dump(out, open(f"{DRY}/forward_generic.json", "w"))
open(f"{DRY}/forward_generic.txt", "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
