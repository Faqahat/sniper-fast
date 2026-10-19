#!/usr/bin/env python3
# READ-ONLY. FORWARD PROOF on a fresh paper run (only launches after its start), under evidence-based landing models:
#   (a) OURS   : 39% of fires land in S at a position drawn from our 18 measured same-slot positions (median ~104),
#                61% land in S+1 (behind all of S) — today's live measurement
#   (b) JITO   : in-S position drawn from Jito-tipped outside buyers' empirical positions for that leader client
#                (landing_dist.json; d<=5 bundle-rider wallets excluded); assumes we land in S
#   (c) LANDX  : same with LandX-tipped outside buyers
#   (d) d<=25  : ceiling, land behind the first 25 txs
# Rules (frozen; no refit): Gate B, Gate B no-name, FIX base, PREREG_v2 #1-#5 (their EXIT_FREEZE exit and 1 s),
# racedeep whale rule (first outside buy >= 5 SOL in slot S triggers; we land L txs after it; sell +3 s).
# Output: per rule x model: n, fires/day, contested rate (on chain), mean/median/ex-top3/win, SOL/day @1/@2 SOL with 90% CI.
# usage: forward_proof.py <tag>
import sys, json, random, statistics as st, os
sys.path.insert(0, "/root/race")
from hc_search import sim, EXITS, hostbad, C, stats
from fwdrows import build
sys.path.insert(0, "/root/nob")

tag = sys.argv[1] if len(sys.argv) > 1 else "fresh"
F = [o for o in build(f"/root/race/paper_{tag}.log", f"/root/race/{tag}_onchain.jsonl", f"/root/race/paths_{tag}.jsonl", verbose=False)
     if not hostbad(o["uri_host"]) and 0.5 <= o["dev_sol"] <= 8]
if len(F) < 20:
    sys.exit(f"too few scored launches yet ({len(F)})")
days = (F[-1]["slot"] - F[0]["slot"]) * 0.217 / 86400
# leader clients for the fresh slots
nodes = {x["pubkey"]: x for x in json.load(open("/root/stakepaths/clusternodes.json"))["result"]}
cache_f = "/root/race/leaders_cache.json"
cache = json.load(open(cache_f)) if os.path.exists(cache_f) else {}
need = sorted({o["slot"] for o in F if str(o["slot"]) not in cache})
if need:
    from nrpc import rpc
    i = 0
    while i < len(need):
        lo = need[i]
        r = rpc("getSlotLeaders", [lo, 5000])
        if isinstance(r, list):
            for k, l in enumerate(r):
                cache[str(lo + k)] = l
        while i < len(need) and need[i] < lo + 5000:
            i += 1
    json.dump(cache, open(cache_f, "w"))
for o in F:
    o["client"] = (nodes.get(cache.get(str(o["slot"]))) or {}).get("clientId", "?")
D = json.load(open("/root/race/landing_dist.json"))


def qs(v, k=9):
    v = sorted(v)
    return [v[int((i + 0.5) / k * len(v))] for i in range(k)] if v else []


OURS_D = D["ours"]["ALL"]          # 18 measured same-slot positions
P_S = 16 / 42                      # measured share of our fires that landed in S


def dist_for(sender, client):
    v = [d for d in D[sender].get(client, []) if d > 5]
    if len(v) < 15:
        v = [d for d in D[sender]["ALL"] if d > 5]
    return qs(v)


MODELS = ["a OURS", "b JITO", "c LANDX", "d <=25"]


def ev(o, ex, model, offset=0):
    """expected realistic PnL (2 SOL default) of one launch under a landing model; offset = trigger position (whale rule)"""
    def s(d=None, s1=False, size=2.0):
        return sim(o, ex, d_land=offset + d if d is not None else 100, land_s1=s1, size=size)
    if model == "a OURS":
        return lambda size: P_S * st.mean(s(d, size=size) for d in qs(OURS_D, 6)) + (1 - P_S) * s(s1=True, size=size)
    if model == "b JITO":
        ds = dist_for("jito", o["client"])
        return lambda size: st.mean(s(d, size=size) for d in ds)
    if model == "c LANDX":
        ds = dist_for("landx", o["client"])
        return lambda size: st.mean(s(d, size=size) for d in ds)
    return lambda size: s(25, size=size)


fz = json.load(open("/root/race/EXIT_FREEZE.json"))["gates"]
pre = json.load(open("/root/race/PREREG_v2.json"))["prereg"]
RULES = [("Gate B", lambda o: o["dev_sol"] >= 3 and o["glued"] >= 2 and o["n_len"] <= 12, "time 1s"),
         ("Gate B no-name", lambda o: o["dev_sol"] >= 3 and o["glued"] >= 2, "time 1s"),
         ("FIX base filter", lambda o: True, "time 1s")]
for k, p in enumerate(pre):
    RULES.append((f"PREREG_v2 #{k + 1} [{' & '.join(p['rule'])}]", (lambda o, rule=p["rule"]: all(C[c](o) for c in rule)), "time 1s"))
    if fz[f"PREREG_v2 #{k + 1}"]["exit"] != "time 1s":
        RULES.append((f"PREREG_v2 #{k + 1} (frozen exit)", (lambda o, rule=p["rule"]: all(C[c](o) for c in rule)), fz[f"PREREG_v2 #{k + 1}"]["exit"]))


def whale_pos(o):
    for d, v in zip(o["outS_d"], o["outS_sv"]):
        if v >= 5.0:
            return d
    return None


RULES.append(("racedeep whale (>=5 SOL outside buy in S, +3 s)", lambda o: whale_pos(o) is not None, "time 3s"))
RACE = lambda o: o["out2s_nx"] >= 3 and o["out2s_solx"] >= 3


def boot(v, n=2000):
    rnd = random.Random(5)
    m = sorted(st.mean(rnd.choices(v, k=len(v))) for _ in range(n))
    return m[int(.05 * n)], m[int(.95 * n)]


out = []
for rn, fn, xn in RULES:
    g = [o for o in F if fn(o)]
    if len(g) < 5:
        out.append((rn, xn, None))
        continue
    fpd = len(g) / days
    race = sum(RACE(o) for o in g) / len(g)
    for m in MODELS:
        off = (lambda o: whale_pos(o)) if rn.startswith("racedeep") else (lambda o: 0)
        v2 = [ev(o, EXITS[xn], m, off(o))(2.0) for o in g]
        v1 = [ev(o, EXITS[xn], m, off(o))(1.0) for o in g]
        lo, hi = boot(v2)
        s2 = stats(v2)
        out.append((rn, xn, (m, len(g), fpd, race, s2, st.mean(v1) * fpd, st.mean(v2) * fpd * 2, lo * fpd * 2, hi * fpd * 2)))
hours = days * 24
print(f"FORWARD PROOF run '{tag}': {len(F)} scored base launches over {hours:.2f} h (only launches after the run start).")
print("Landing models: a OURS (39% in S at our measured positions, 61% S+1) | b JITO / c LANDX (empirical in-S positions of those senders' buyers on the same leader client, d<=5 riders excluded; assumes we land in S) | d <=25 ceiling.")
print(f"\n{'rule':62} {'exit':10} {'model':8} | {'n':>4} {'fires/d':>7} {'race':>4} | {'mean':>6} {'med':>6} {'ex3':>6} {'win':>4} | SOL/day @1 | SOL/day @2 [90% CI]")
verdict = []
for rn, xn, r in out:
    if r is None:
        print(f"{rn[:62]:62} {xn[:10]:10} n<5")
        continue
    m, n, fpd, race, s2, sd1, sd2, lo, hi = r
    print(f"{rn[:62]:62} {xn.replace('time ', '')[:10]:10} {m:8} | {n:4} {fpd:7.0f} {race:4.0%} | {s2['avg']:+6.1%} {s2['med']:+6.1%} {s2['ex3']:+6.1%} {s2['win']:4.0%} | {sd1:+9.1f} | {sd2:+8.1f} [{lo:+.0f},{hi:+.0f}]")
    if lo > 0 and n >= 100:
        verdict.append(f"{rn.split(' [')[0]} ({xn}) under {m}: +{sd2:.0f} SOL/day @2 SOL (90% CI {lo:+.0f}..{hi:+.0f})")
print("\nVERDICT (n>=100 fires and 90% CI of SOL/day above zero): " + ("; ".join(verdict) if verdict else f"nothing proven yet (no rule with >= 100 fires and a CI above zero; {len(F)} launches scored so far)"))
