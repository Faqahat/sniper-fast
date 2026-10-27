#!/usr/bin/env python3
"""DENSITY step 1 (read-only): landing per send path x leader client, MEASURED from the AMS run records.
  regular buys (nonce fan-out: one copy per path, the first to land wins; the others die on the nonce): per fire the leader
    client at send, the copy that landed (buy_land / buy_failed variant paths), send -> seen on our feed (timing.fire_to_seen_ms)
    and slots after send (landing slot - fire slot);
  pre-send tries (one path, helius-ps): per try the client, send -> seen (ms_send_to_rx), slots after send.
Writes /home/moiz/sniper-data/presend_density/paths.json"""
import json, collections, sys
import numpy as np

RUNS = {r: f"/home/moiz/sniper-data/runs/ams/runs/dip_ams_r{r}.jsonl" for r in (22, 23, 24, 25, 26, 27)}
RUNS[28] = "/home/moiz/sniper-data/presend_filter/live28/dip_ams_r28.jsonl"
OUT = "/home/moiz/sniper-data/presend_density/paths.json"


def q(a):
    a = np.array(a, float)
    if len(a) == 0: return None
    return dict(n=int(len(a)), p10=float(np.percentile(a, 10)), p25=float(np.percentile(a, 25)), p50=float(np.median(a)),
                p75=float(np.percentile(a, 75)), p90=float(np.percentile(a, 90)), grid=[float(np.percentile(a, x)) for x in range(0, 101, 5)])


NEAR = set(l.split()[0] for l in open("/home/moiz/sniper/ops/region/near_leaders_ams.txt") if l.strip() and not l.startswith("#"))
NEAR8 = set(k[:8] for k in NEAR)
reg = []; ps = collections.defaultdict(list); ps_sas = collections.defaultdict(list)
for r, fn in RUNS.items():
    fires = {}; tim = {}; land = {}; lead = {}
    for l in open(fn, errors="ignore"):
        if '"ev":"presend_attempt"' in l and r >= 24:
            x = json.loads(l); lead[x["sig"]] = x.get("leader"); continue
        if '"ev":"fire"' in l or '"ev":"timing"' in l or '"ev":"buy_land"' in l or '"ev":"buy_failed"' in l or ('"presend_attempt_land"' in l and r >= 24):
            try: x = json.loads(l)
            except Exception: continue
            ev = x["ev"]
            if ev == "fire": fires[x["buy_sig"]] = x
            elif ev == "timing" and x.get("kind") == "fire": tim[x["buy_sig"]] = x
            elif ev in ("buy_land", "buy_failed"):
                v = x.get("variant") or {}
                land[x["sig"]] = dict(ok=(ev == "buy_land"), paths=v.get("paths"), slot=x.get("slot"), t=x.get("t"))
            elif ev == "presend_attempt_land":
                c = x.get("client") or "?"
                nf = "near" if (lead.get(x["sig"]) or "")[:8] in NEAR8 else "far"
                if x.get("ms_send_to_rx") is not None and x.get("res") not in (None, "unseen"):
                    ps[c + ":" + nf].append(x["ms_send_to_rx"]); ps["ALL:" + nf].append(x["ms_send_to_rx"])
                    ps_sas[c + ":" + nf].append(x.get("slots_after_send")); ps_sas["ALL:" + nf].append(x.get("slots_after_send"))
                if x.get("ms_send_to_rx") is not None and x.get("res") not in (None, "unseen"):
                    ps[c].append(x["ms_send_to_rx"]); ps["ALL"].append(x["ms_send_to_rx"])
                    ps_sas[c].append(x.get("slots_after_send")); ps_sas["ALL"].append(x.get("slots_after_send"))
    # map each fire's landed copy
    sig2fire = {}
    for bs, f in fires.items():
        for v in ((f.get("nonce") or {}).get("variants") or []):
            sig2fire[v["sig"]] = (bs, v["paths"])
        sig2fire.setdefault(bs, (bs, None))
    for sig, L in land.items():
        if sig not in sig2fire: continue
        bs, paths = sig2fire[sig]; f = fires[bs]; tm = tim.get(bs) or {}
        paths = L["paths"] or paths
        sent = (f.get("t_fire") or 0)
        ms = (L["t"] - sent) / 1e6 if (L.get("t") and sent) else tm.get("fire_to_seen_ms")
        reg.append(dict(run=r, client=f.get("client") or "?", near=(f.get("leader") in NEAR), path="+".join(paths or ["?"]), ok=L["ok"], ms=ms, ms_timing=tm.get("fire_to_seen_ms"),
                        sas=(L["slot"] - f["slot"]) if (L.get("slot") is not None and f.get("slot") is not None) else None,
                        npaths=len(f.get("writes") or [])))

out = dict(reg_rows=reg, ps={c: q(v) for c, v in ps.items()}, ps_sas={c: dict(collections.Counter(min(s, 3) for s in v if s is not None)) for c, v in ps_sas.items()})
by = collections.defaultdict(list); byc = collections.defaultdict(list); sasc = collections.defaultdict(list)
for x in reg:
    if x["ms"] is None: continue
    by[(x["path"], x["client"])].append(x["ms"]); byc[x["client"]].append(x["ms"]); byc["ALL"].append(x["ms"])
    if x["sas"] is not None: sasc[x["client"]].append(x["sas"]); sasc["ALL"].append(x["sas"])
out["reg_path_client"] = {f"{p}|{c}": q(v) for (p, c), v in by.items()}
out["reg_client"] = {c: q(v) for c, v in byc.items()}
out["reg_sas"] = {c: dict(collections.Counter(min(s, 3) for s in v)) for c, v in sasc.items()}
json.dump(out, open(OUT, "w"))
print(f"regular landed copies {len(reg)} (runs {sorted(RUNS)})")
print("\nPRE-SEND helius-ps send->seen ms by client (MEASURED, runs 24-28):")
for c, v in sorted(out["ps"].items(), key=lambda z: -z[1]["n"]):
    s = out["ps_sas"][c]; n = sum(s.values())
    print(f"  {c:16s} n {v['n']:6d} p10 {v['p10']:6.1f} p50 {v['p50']:6.1f} p90 {v['p90']:6.1f} | same slot {s.get(0, 0) / n * 100:4.0f}% +1 {s.get(1, 0) / n * 100:4.0f}% +2.. {(n - s.get(0, 0) - s.get(1, 0)) / n * 100:4.0f}%")
print("\nREGULAR fan-out: first copy to land, send->seen ms by client (MEASURED, min over ~6-8 paths):")
for c, v in sorted(out["reg_client"].items(), key=lambda z: -z[1]["n"]):
    s = out["reg_sas"].get(c, {}); n = max(sum(s.values()), 1)
    print(f"  {c:16s} n {v['n']:5d} p10 {v['p10']:6.1f} p50 {v['p50']:6.1f} p90 {v['p90']:6.1f} | same slot {s.get(0, 0) / n * 100:4.0f}% +1 {s.get(1, 0) / n * 100:4.0f}%")
print("\nREGULAR: which copy landed, per client (n wins, median send->seen when it won):")
cl = collections.defaultdict(list)
for k, v in out["reg_path_client"].items():
    p, c = k.split("|"); cl[c].append((v["n"], p, v["p50"], v["p90"]))
for c in sorted(cl, key=lambda c: -sum(z[0] for z in cl[c])):
    tot = sum(z[0] for z in cl[c])
    print(f"  {c:16s} ({tot}): " + ", ".join(f"{p} {n} ({n / tot * 100:.0f}%, p50 {m:.0f}, p90 {m9:.0f})" for n, p, m, m9 in sorted(cl[c], reverse=True)))
