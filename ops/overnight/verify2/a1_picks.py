#!/usr/bin/env python3
# a1: compare the claimed pick list with the shadow scorer's final_pick records; timing of decisions (look-ahead audit a)
import json, collections, statistics, datetime
SC = "/home/moiz/sniper-data/collect/shadow/scores_v3.jsonl"
PK = "/home/moiz/sniper/ops/overnight/core/final2_picks_v3.json"
PKT = datetime.timezone(datetime.timedelta(hours=5))
def ts(t): return datetime.datetime.fromtimestamp(t, PKT).strftime("%m-%d %H:%M:%S")
dec = {}; obs = {}; dup = collections.Counter()
for l in open(SC):
    try: r = json.loads(l)
    except Exception: continue
    if r.get("type") == "decide":
        if r["mint"] in dec: dup[r["mint"]] += 1
        dec.setdefault(r["mint"], r)
    elif r.get("type") == "obs": obs.setdefault(r["mint"], r)
picks = json.load(open(PK))
fp = [r for r in dec.values() if r.get("final_pick")]
fp.sort(key=lambda r: r["t"])
print("decide records", len(dec), "dup decide", sum(dup.values()), "final_pick records", len(fp), "obs", len(obs))
print("final_pick time range", ts(fp[0]["t"]), "->", ts(fp[-1]["t"]))
sp = set(picks); sf = {r["mint"] for r in fp}
print("pick list", len(picks), "unique", len(sp), "| in final_pick", len(sp & sf), "| list not final_pick", len(sp - sf), "| final_pick not in list", len(sf - sp))
for m in sorted(sf - sp, key=lambda m: dec[m]["t"]): print("   final_pick NOT in list:", m, ts(dec[m]["t"]), "quote", dec[m].get("quote"))
for m in sorted(sp - sf): print("   list NOT final_pick:", m, (ts(dec[m]["t"]) if m in dec else "no decide record"))
lag = [r["t_scored"] - r["t"] for r in fp if r["mint"] in sp]
lag_all = [r["t_scored"] - r["t"] for r in dec.values()]
q = lambda v, p: sorted(v)[min(len(v) - 1, int(p * len(v)))]
print("t_scored - t (s), picks: min %.3f p50 %.3f p90 %.3f p99 %.3f max %.3f" % (min(lag), q(lag, .5), q(lag, .9), q(lag, .99), max(lag)))
print("t_scored - t (s), all  : min %.3f p50 %.3f p90 %.3f p99 %.3f max %.3f" % (min(lag_all), q(lag_all, .5), q(lag_all, .9), q(lag_all, .99), max(lag_all)))
big = sorted([(r["t_scored"] - r["t"], r["mint"], ts(r["t"])) for r in fp if r["mint"] in sp], reverse=True)[:12]
print("largest scoring lags among picks:"); [print("   %.2f s %s %s" % b) for b in big]
at = [r["at_ms"] for r in fp if r["mint"] in sp]
print("at_ms picks: min %.1f p50 %.1f p90 %.1f max %.1f" % (min(at), q(at, .5), q(at, .9), max(at)))
print("glued_closed among picks:", collections.Counter(r.get("glued_closed") for r in fp if r["mint"] in sp), "glued_unknown:", collections.Counter(r.get("glued_unknown") for r in fp if r["mint"] in sp))
print("quote among picks:", collections.Counter(r.get("quote") for r in fp if r["mint"] in sp), " mayhem feature:", collections.Counter(r["features"].get("mayhem") for r in fp if r["mint"] in sp))
print("final names:", collections.Counter(r.get("final") for r in dec.values()))
print("obs present for picks:", sum(1 for m in sp if m in obs))
neg = [(r["mint"], r["features"].get("cr_min_since_prev_create")) for r in fp if r["mint"] in sp and (r["features"].get("cr_min_since_prev_create") or 1) < 0.02]
print("picks with cr_min_since_prev_create < 0.02 min (self-in-history symptom):", len(neg), neg[:5])
# guards (final_config2 'guards', added 19:18 UTC 10-22): are picks consistent with them?
g = [r for r in fp if r["mint"] in sp and not (r["features"].get("payer_is_creator") == 1 and not ((r["features"].get("glued_n") or 0) == 0 and (r["features"].get("dev_buy") or 0) < 1))]
print("picks failing final_config2 guards:", len(g))
json.dump(dict(fp=[r["mint"] for r in fp]), open("/home/moiz/sniper/ops/overnight/verify2/a1_out.json", "w"))
