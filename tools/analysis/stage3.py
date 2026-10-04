#!/usr/bin/env python3
"""Long run, stage 3: leaders. Joins every clean win (wins.jsonl.gz), every bot (bots.json) and every slot's feed
statistics (<seg>/feedslots.json) with the slot's leader (leaders.json from leaders.py). Answers:
  - where wins happen: leader distance from Cherry, client, Jito/BAM, DoubleZero, country -- against how often such
    leaders lead at all (base rate), overall and per top bot (location / private-deal hints);
  - how fast winners react on each kind of leader;
  - which feed shows each kind of leader's transactions first, and by how much (DoubleZero vs the rest).
usage: stage3.py <leaders.json> <segment dir> [...] -> leaders-report.json"""
import json, sys, gzip, collections

L = json.load(open(sys.argv[1])); first = L["first_slot"]; LEAD = L["leaders"]; INFO = L["info"]
leader = lambda s: LEAD[s - first] if 0 <= s - first < len(LEAD) else None
q = lambda v, p: (round(sorted(v)[min(len(v) - 1, int(len(v) * p))], 2) if v else None)

def rtt_b(r):
    if r is None: return "no ping"
    return "<1ms (same DC)" if r < 1 else "1-5ms (Frankfurt/near)" if r < 5 else "5-20ms (EU)" if r < 20 else "20-100ms (US east, far EU)" if r < 100 else ">100ms (US west, Asia)"
def client(v):
    if not v: return "?"
    if v.startswith("0."): return "firedancer"
    if v.startswith("26."): return "26.x (unknown)"
    return "agave " + v.split(".")[0] + ".x"
def cats(k):
    i = INFO.get(k) or {}
    return {"rtt": rtt_b(i.get("rtt_ms")), "client": client(i.get("version")), "jito": "bam" if i.get("bam") else "jito" if i.get("jito") else "no jito",
            "dz": "on DZ" if i.get("dz") else "not DZ", "country": i.get("country") or "?", "relayer": "tpu elsewhere" if i.get("tpu_same_host") is False else "tpu on host"}

slots = set()
for seg in sys.argv[2:]:
    slots |= {int(s) for s in json.load(open(f"{seg.rstrip('/')}/feedslots.json"))["slots"]}
base = collections.defaultdict(collections.Counter)
for s in slots:
    k = leader(s)
    if k:
        for d, v in cats(k).items(): base[d][v] += 1
n_base = len(slots)

wins = [json.loads(l) for l in gzip.open("wins.jsonl.gz", "rt")]
bots = json.load(open("bots.json"))
top = [b["signer"] for b in sorted(bots.values(), key=lambda b: -b["wins"])[:15]]
by = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
ms_by = collections.defaultdict(lambda: collections.defaultdict(list))
per_leader = collections.defaultdict(collections.Counter)
for w in wins:
    k = leader(w["slot"])
    if not k: continue
    c = cats(k)
    for d, v in c.items():
        by["ALL"][d][v] += 1
        if w["signer"] in top: by[w["signer"]][d][v] += 1
        if w["trig"]: ms_by[d][v].append(w["trig"]["ms"])
    per_leader[w["signer"]][k] += 1

def lift(cnt):
    n = sum(cnt.values()) or 1
    return {v: {"wins_pct": round(100 * x / n, 1), "base_pct": round(100 * base_d.get(v, 0) / n_base, 1)} for v, x in cnt.most_common()}
out = {"slots": n_base, "base": {d: {v: round(100 * x / n_base, 1) for v, x in c.most_common()} for d, c in base.items()}, "wins_by": {}, "win_ms_by": {}, "bot_leader_affinity": {}}
for who, dims in by.items():
    out["wins_by"][who] = {}
    for d, cnt in dims.items():
        base_d = base[d]
        out["wins_by"][who][d] = lift(cnt)
for d, vs in ms_by.items():
    out["win_ms_by"][d] = {v: {"n": len(x), "p10": q(x, .1), "p50": q(x, .5), "p90": q(x, .9)} for v, x in vs.items()}
# leaders a bot wins on far more than chance (the share of the run's slots that leader had)
lead_share = collections.Counter(leader(s) for s in slots)
for b in top:
    c = per_leader[b]; n = sum(c.values())
    if n < 10: continue
    out["bot_leader_affinity"][b] = [{"leader": k, "wins": x, "wins_pct": round(100 * x / n, 1), "slots_pct": round(100 * lead_share[k] / n_base, 2),
        "info": INFO.get(k)} for k, x in c.most_common(5)]

# feeds by kind of leader: share first and mean lag (µs) of each feed, from every forwarded transaction
F = None
agg = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0, 0]))
for seg in sys.argv[2:]:
    fsj = json.load(open(f"{seg.rstrip('/')}/feedslots.json"))
    F = fsj["feeds"]
    for s, per in fsj["slots"].items():
        k = leader(int(s))
        if not k: continue
        c = cats(k)
        for d in ("dz", "rtt", "client", "jito", "country"):
            a = agg[d + ":" + c[d]]
            for i, (seen, firsts, lag) in enumerate(per):
                x = a[F[i]]; x[0] += seen; x[1] += firsts; x[2] += lag
        a = agg["ALL"]
        for i, (seen, firsts, lag) in enumerate(per):
            x = a[F[i]]; x[0] += seen; x[1] += firsts; x[2] += lag
out["feeds_by"] = {g: {f: {"seen": v[0], "first_pct": round(100 * v[1] / max(1, sum(w[1] for w in fe.values())), 1), "mean_lag_ms": round(v[2] / max(1, v[0]) / 1000, 2)}
    for f, v in fe.items() if v[0]} for g, fe in agg.items()}
json.dump(out, open("leaders-report.json", "w"), indent=1)
print(json.dumps({"base": out["base"], "ALL wins": out["wins_by"].get("ALL"), "win_ms_by": out["win_ms_by"]}, indent=1)[:4000])
print(json.dumps({g: out["feeds_by"][g] for g in out["feeds_by"] if g.startswith("dz") or g == "ALL"}, indent=1)[:3000])
