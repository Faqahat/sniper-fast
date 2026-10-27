#!/usr/bin/env python3
# M2 shadow progress (owner 10-25 01:45 PKT: "keep me updated with the shadow progress, 15 min and then every 30 min").
# Pulls the M2 / IMIT1 records of the live shadow runs from both servers (read-only), maps each dump's slot to its leader
# (epoch-1067 schedule) and keeps a dump only on the server whose near list holds that leader (where it could be traded),
# then counts: M2 would-buys, IMIT1 picks, overlap, real fills and P&L, M2 timing. Usage: m2_progress.py [fra_run ams_run]
import json, subprocess, sys, time, statistics as st, collections
RUNS = {"fra": ("84.32.100.36", f"dip_r{sys.argv[1] if len(sys.argv) > 1 else 14}"), "ams": ("84.32.104.202", f"dip_ams_r{sys.argv[2] if len(sys.argv) > 2 else 13}")}
SCH = json.load(open("/home/moiz/sniper-data/competitors2/schedule_1067.json"))
NEAR = {r: {l.strip() for l in open(f"/home/moiz/sniper/ops/region/near_leaders_{r}.txt") if l.strip()} for r in ("fra", "ams")}
def leader(s):
    i = s - SCH["start"]
    return SCH["ids"][SCH["slot_leader"][i]] if 0 <= i < len(SCH["slot_leader"]) else None
def realized(ip, tag):
    cmd = f"sudo grep -h 'REALIZED mint=' /root/prod/runs/{tag}.log"
    out = subprocess.run(["ssh", "-p", "1996", "-o", "ConnectTimeout=15", f"it@{ip}", cmd], capture_output=True, text=True, timeout=120).stdout
    r = collections.defaultdict(list)
    for l in out.splitlines():
        try: m = l.split("mint=")[1].split()[0]; v = float(l.split("pnl=")[1].split()[0]); r[m].append(v)
        except Exception: pass
    return r
def pull(ip, tag):
    cmd = f"sudo grep -hE '\"ev\": *\"(run_start|pick|fire|close|buy_land|buy_failed)\"|\"m2\": *[-0-9]' /root/prod/runs/{tag}.jsonl"
    out = subprocess.run(["ssh", "-p", "1996", "-o", "ConnectTimeout=15", f"it@{ip}", cmd], capture_output=True, text=True, timeout=120).stdout
    ev = []
    for l in out.splitlines():
        try: o = json.loads(l)
        except Exception: continue
        if o.get("ev") == "run_start": ev = []
        ev.append(o)
    return ev
pk = lambda ns: time.strftime("%H:%M", time.gmtime(ns / 1e9 + 5 * 3600))
res = {}
for reg, (ip, tag) in RUNS.items():
    ev = pull(ip, tag)
    start = next((o["t"] for o in ev if o.get("ev") == "run_start"), None)
    dumps = [o for o in ev if o.get("ev") == "dump" and o.get("m2") is not None]
    picks = {o["sig"]: o for o in ev if o.get("ev") == "pick"}
    fires = {o["dump_sig"]: o for o in ev if o.get("ev") == "fire"}
    closes = [o for o in ev if o.get("ev") == "close"]
    near = [o for o in dumps if leader(o["slot"]) in NEAR[reg]]
    m2p = [o for o in near if o.get("m2_pick")]
    imit_near = [s for s, p in picks.items() if p.get("leader") in NEAR[reg]]
    rz = realized(ip, tag)
    res[reg] = dict(rz=rz, start=start, scored=len(dumps), near=len(near), m2p=m2p, imit=imit_near, picks=picks, fires=fires, closes=closes,
                    us=[o.get("m2_us") or 0 for o in dumps])
for reg, r in res.items():
    mins = (time.time() - r["start"] / 1e9) / 60 if r["start"] else 0
    m2s = {o["sig"] for o in r["m2p"]}; im = set(r["imit"])
    both = m2s & im; only_m2 = m2s - im; only_im = im - m2s
    fills = [c for c in r["closes"] if c.get("result") == "sold"]
    us = sorted(r["us"]); p50 = us[len(us) // 2] if us else 0; p99 = us[int(0.99 * (len(us) - 1))] if us else 0
    print(f"{reg.upper()} ({mins:.0f} min): scored {r['scored']} dumps ({r['near']} on its own leaders) | would-buy: M2 {len(m2s)} vs IMIT1 {len(im)} "
          f"(both {len(both)}, M2-only {len(only_m2)}, IMIT1-only {len(only_im)}) | real buys sent {len(r['fires'])}, fills {len(fills)} | M2 time p50 {p50:.0f} / p99 {p99:.0f} µs")
    # real fills split by whether M2 also picked that dump (only when this run's records start after the log's run start)
    rz = {k: list(v) for k, v in r["rz"].items()}; agree = []; disagree = []
    for c in r["closes"]:
        if c.get("result") != "sold": continue
        v = rz.get(c["mint"], []); p_ = v.pop(0) if v else None
        if p_ is None: continue
        (agree if c.get("dump_sig") in m2s or any(o["sig"] == c.get("dump_sig") for o in r["m2p"]) else disagree).append(p_)
    print(f"   real fills where M2 also picked: {len(agree)} = {sum(agree):+.4f} SOL | fills M2 would have SKIPPED: {len(disagree)} = {sum(disagree):+.4f} SOL")
    if "--list" not in sys.argv: continue
    for o in sorted(r["m2p"], key=lambda o: o["t"]):
        tag = "both" if o["sig"] in im else ("M2 only" + (" (later big sell)" if o.get("m2_extra") else ""))
        fired = " — we bought it" if o["sig"] in r["fires"] else ""
        print(f"   {pk(o['t'])} {o['mint'][:8]} M2 {o['m2']:+.4f} IMIT1 {o.get('score', 0):+.2f} dump {o.get('sell', 0):.2f} SOL −{o.get('drop_pct', 0):.0f}% [{tag}]{fired}")
