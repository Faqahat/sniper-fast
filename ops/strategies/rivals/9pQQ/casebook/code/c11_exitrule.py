#!/usr/bin/env python3
"""teacher-forced exit-rule check on case tokens: per trip, first outside trade in the hold where rule fires vs its real sell trigger.
usage: c11_exitrule.py RULE RUN:MINT8 ...   rules defined below."""
import sys, json, gzip, glob, collections
D = "/home/moiz/sniper-data/rivals/9pQQ/casebook"
def peakinfo(rows, emc):
    pk = emc; out = []
    for r in rows:
        pk = max(pk, r["mc"]); out.append(pk)
    return out
RULES = {
 "stale5": lambda r, st: (not r["buy"]) and (r["since_ob"] or 0) >= 5,
 "stale30": lambda r, st: (not r["buy"]) and (r["since_ob"] or 0) >= 30,
 "stale60": lambda r, st: (not r["buy"]) and (r["since_ob"] or 0) >= 60,
 "stale100": lambda r, st: (not r["buy"]) and (r["since_ob"] or 0) >= 100,
 "stale15": lambda r, st: (not r["buy"]) and (r["since_ob"] or 0) >= 15,
 "stale8": lambda r, st: (not r["buy"]) and (r["since_ob"] or 0) >= 8,
 "stale5any": lambda r, st: (r["since_ob"] or 0) >= 5,
 "dd3": lambda r, st: r["mc"] <= st["pk"] * 0.97 and not r["buy"],
 "burst": lambda r, st: st["b3"] >= 2.0 and r["mc"] > st["emc"],
 "stale5|burst": lambda r, st: ((not r["buy"]) and (r["since_ob"] or 0) >= 5) or (st["b3"] >= 2.0 and r["mc"] > st["emc"]),
}
rule = sys.argv[1]; f = RULES[rule]
tot = collections.Counter()
for spec in sys.argv[2:]:
    run, m8 = spec.split(":")
    fn = glob.glob(f"{D}/tapes/{run}/{m8}*.ev.jsonl.gz")[0]
    R = [json.loads(l) for l in gzip.open(fn, "rt")]
    own = [k for k, r in enumerate(R) if r["own"]]
    res = collections.Counter()
    for a, b in zip(own[::2], own[1::2]):
        cap = R[b]["bt"] - R[a]["bt"] >= 295
        emc = R[a]["mc"]; pk = emc; fired = None; trig = None
        j = b - 1
        while R[j]["own"]: j -= 1
        trig = j
        for k in range(a + 1, b):
            r = R[k]
            if r["own"]: continue
            b3 = sum(x["sol"] for x in R[max(a + 1, k - 30):k + 1] if not x["own"] and x["buy"] and x["s"] >= r["s"] - 2)
            pk = max(pk, r["mc"])
            if r["s"] - R[a]["s"] < 2: continue
            if f(r, dict(pk=pk, emc=emc, b3=b3)): fired = k; break
        if cap: res["cap_fired" if fired is not None else "cap_clean"] += 1
        elif fired is None: res["never"] += 1
        elif fired == trig: res["exact"] += 1
        elif fired < trig: res["early" if R[trig]["s"] - R[fired]["s"] > 1 else "early<=1sl"] += 1
    print(spec, rule, dict(res)); tot.update(res)
print("TOTAL", rule, dict(tot), "exact%", round(100 * tot["exact"] / max(1, sum(v for k, v in tot.items() if not k.startswith("cap"))), 1))
