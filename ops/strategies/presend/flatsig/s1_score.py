#!/usr/bin/env python3
"""FLATSIG scorer [MEASURED live P&L; paper where labelled]: applies the FROZEN skip rules (FROZEN.json) to every live T2 position with
chain features, per period (DEV / VAL / HOLD) and per run, ON TOP of current live (QUIET + QUIET3-A: positions QUIET3-A would block
are removed first; QUIET3-A was live only in r49/r50/r51/r55, elsewhere simulated from the arm record).
Saved = -sum(realized P&L of blocked positions). w/o top5 = saved without its 5 biggest saves.
f20 = ESTIMATE with followers 20% weaker: a blocked trade's gain above the ~17 mSOL fixed round-trip cost shrinks by 20%.
Also prints the current-live reference on the same windows: QUIET3-A (simulated blocks = realized; live skips = shadow row c PAPER)
and QUIET skips (shadow row c PAPER).
usage: s1_score.py [--periods DEV,VAL,HOLD]"""
import json, sys, os, collections, hashlib
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flib as L, fpos, fmodel as FM
HERE = os.path.dirname(os.path.abspath(__file__))
FR = json.load(open(f"{HERE}/FROZEN.json"))
pers = (sys.argv[sys.argv.index("--periods") + 1] if "--periods" in sys.argv else "DEV,VAL,HOLD").split(",")
COST = 0.017


def cond(p, c):
    v = p["f"][c["feat"]]
    if c.get("nohist_true") and v < 0: return True
    if c["op"] == "<=": return (v >= 0 or not c.get("hist_only")) and v <= c["t"]
    if c["op"] == ">=": return v >= c["t"]
    raise ValueError(c)


MODELS = {}
def rule_hits(rule, Q):
    if rule["type"] == "and":
        return [all(cond(p, c) for c in rule["conds"]) for p in Q]
    if rule["type"] == "model":
        m = MODELS.setdefault(rule["model"], json.load(open(rule["model"])))
        if not Q: return []
        s = FM.score(m, FM.transform([p["f"] for p in Q]))
        return list(s < rule["t"])
    raise ValueError(rule)


def f20(x):
    g = x + COST
    return 0.8 * g - COST if g > 0 else x


def summ(b):
    v = [p["pnl"] for p in b]
    c = collections.Counter(p["cls"] for p in b)
    return {"n": len(b), "flat": c["flat"], "small": c["small"], "win": c["win"], "big": c["bigloss"],
            "flat_sol": round(sum(p["pnl"] for p in b if p["cls"] == "flat"), 3),
            "winners_lost_sol": round(sum(x for x in v if x > 0), 3), "saved": round(-sum(v), 3),
            "wo5": round(-sum(sorted(v)[5:]), 3), "f20": round(-sum(f20(x) for x in v), 3)}


def main():
    P = fpos.positions()
    H = L.run_hours()
    hours = collections.Counter()
    for (per, run), h in H.items(): hours[per] += h
    T2 = [p for p in P if p["kind"] == "T2"]
    out = {"frozen_sha": hashlib.sha256(open(f"{HERE}/FROZEN.json", "rb").read()).hexdigest(), "hours": dict(hours), "rules": {}}
    # coverage
    for per in pers:
        a = [p for p in T2 if p["per"] == per]; cov = [p for p in a if "f" in p]
        print(f"{per}: T2 positions {len(a)} ({sum(p['pnl'] for p in a):+.3f}), with chain features {len(cov)} ({sum(p['pnl'] for p in cov):+.3f}), "
              f"QUIET3-A would block {sum(1 for p in cov if p['q3a'])}; hours {hours[per]:.1f}")
    for rule in FR["rules"]:
        print(f"\n=== {rule['name']}: {rule['text']}")
        out["rules"][rule["name"]] = {}
        for per in pers:
            Q = [p for p in T2 if p["per"] == per and "f" in p and not p["q3a"]]
            hit = rule_hits(rule, Q)
            b = [p for p, h in zip(Q, hit) if h]
            s = summ(b); kept = [p for p, h in zip(Q, hit) if not h]
            s["base_n"] = len(Q); s["base_sol"] = round(sum(p["pnl"] for p in Q), 3); s["kept_sol"] = round(sum(p["pnl"] for p in kept), 3)
            s["base_flats"] = sum(1 for p in Q if p["cls"] == "flat")
            s["per_day"] = round(s["saved"] / hours[per] * 24, 3) if hours[per] else None
            s["wo5_day"] = round(s["wo5"] / hours[per] * 24, 3) if hours[per] else None
            runs = collections.defaultdict(float)
            for p in b: runs[p["run"]] -= p["pnl"]
            s["per_run"] = {r: round(v, 3) for r, v in sorted(runs.items(), key=lambda x: int(x[0][1:]))}
            out["rules"][rule["name"]][per] = s
            print(f"{per:4s} base n{s['base_n']} ({s['base_sol']:+.3f}, flats {s['base_flats']}) | blocked n{s['n']} flats {s['flat']} ({s['flat_sol']:+.3f}) "
                  f"small {s['small']} win {s['win']} big {s['big']} winners_lost {s['winners_lost_sol']:+.3f} | SAVED {s['saved']:+.3f} "
                  f"({s['per_day']:+.2f}/day) w/o top5 {s['wo5']:+.3f} ({s['wo5_day']:+.2f}/day) f20(EST) {s['f20']:+.3f}")
            print(f"      per run saved: {s['per_run']}")
            if "--list" in sys.argv:
                for p in b: print(f"        {L.pkt(p['t0'])} {p['run']} {p['mint'][:10]} {p['pnl']:+.4f} {p['cls']}")
    # current live reference on the same windows
    print("\n=== current live reference (same periods) ===")
    out["live_ref"] = {}
    for per in pers:
        cov = [p for p in T2 if p["per"] == per and "f" in p]
        sim = [p for p in cov if p["q3a"] and not p["q3a_live"]]
        q3 = summ(sim)
        # QUIET3-A live skips and QUIET skips -> shadow row c paper (all runs of the period, chain coverage not required)
        paper = collections.defaultdict(lambda: [0, 0, 0.0, 0])
        for r in L.RUNS:
            ex = L.load(r); sh = {(x["mint"], x["t"]): x for x in ex["sh"]}
            for sk in ex["skips"]:
                if sk["kind"] != "T2" or sk["why"] not in ("quiet", "quiet3_a") or not sk["t"]: continue
                if L.period(r, sk["t"]) != per: continue
                x = sh.get((sk["mint"], sk["t"]))
                paper[sk["why"]][0] += 1
                if x: paper[sk["why"]][3] += 1
                if x and x["c"] is not None: paper[sk["why"]][1] += 1; paper[sk["why"]][2] += x["c"]
        out["live_ref"][per] = {"q3a_sim_realized": q3, "paper": {k: v for k, v in paper.items()}}
        print(f"{per:4s} QUIET3-A simulated (realized, runs where not live): blocked n{q3['n']} flats {q3['flat']} win {q3['win']} saved {q3['saved']:+.3f} w/o5 {q3['wo5']:+.3f}")
        for k, v in paper.items():
            print(f"      live skips '{k}': {v[0]} skips ({v[3]} matched to shadow), {v[1]} shadow-filled, shadow row c net {v[2]:+.3f} PAPER (saved = {-v[2]:+.3f})")
    json.dump(out, open(f"{L.D}/score_{'_'.join(pers)}.json", "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
