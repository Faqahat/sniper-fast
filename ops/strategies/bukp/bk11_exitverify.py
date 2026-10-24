#!/usr/bin/env python3
# Verify Haiku's exit rules (llm/answers_exit.jsonl) on BUkpShoE's entries re-timed to 35 ms (0.6 SOL): P&L on R2/R3/R1,
# all entries and curve<50, plus how close the rule's exit lands to ITS exit (median |slot difference|).
import sys, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/patterns"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/bukp")
import p4_eval as E
import bk8_replica as B8
OUT = "/home/moiz/sniper-data/strategies/bukp"
OPS = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b, ">": lambda a, b: a > b, "<": lambda a, b: a < b, "==": lambda a, b: a == b, "!=": lambda a, b: a != b}
WIN = ("bsol3", "ssol3", "nb3", "ns3", "maxs3", "maxb3", "net3", "net10", "ret1", "ret3", "ret10", "curve", "nbot_hold", "fam_hold", "sol", "wt")
def run(day, rules, lat=35):
    d = E.DAYS[day]; FI = d["FI"]; T = [t for t in json.load(open(f"{OUT}/trips_{day}.json")) if t["closed"] and t["sells"]]
    ents = [(B8.entry(d, t, lat, "0.6"), t) for t in T]
    out = {}
    for ri, R in enumerate(rules):
        pa = []; ps = []; dev = []
        for e, t in ents:
            if e is None: continue
            if e["fail"]: pa.append(e["pnl"]); continue
            path, Vs, Ts, rows = e["path"], e["Vs"], e["Ts"], e["rows"]
            if not path: continue
            mn = R.get("min_hold") or 0; mx = R.get("max_hold") or 1417; tp = R.get("tp"); sl = R.get("sl"); tr = R.get("trail")
            hit = None; botsells = []
            for n, m in enumerate(path):
                r = rows[n]; held = r[3]
                if not d["buy"][m] and d["bid"][m]: botsells.append(d["s"][m])
                if held < mn: continue
                if held > mx: break
                f = dict(mult=r[1], peak=r[2], dd_peak=r[4], held=held, sell_since=r[5], buy_since=r[6], side=int(d["buy"][m]),
                         bot_s10=sum(1 for x in botsells if x >= d["s"][m] - 10))
                for k in WIN: f[k] = float(d["F"][m, FI[k]]) if k != "sol" else float(d["sol"][m]) / 1e9
                if (tp and r[1] >= tp) or (sl and r[1] <= sl) or (tr and r[2] >= tr[0] and r[4] >= tr[1]): hit = n; break
                ok = False
                for grp in R.get("when_any") or []:
                    try:
                        if all(OPS[op](f[fe], float(v)) for fe, op, v in grp): ok = True; break
                    except (KeyError, TypeError, ValueError): pass
                if ok: hit = n; break
            if hit is not None:
                ta2 = d["arr"][path[hit]] + lat; nn = hit
                while nn + 1 < len(path) and d["arr"][path[nn + 1]] < ta2: nn += 1
                hs = int(d["s"][path[hit]] - e["s_land"])
            else:
                nn = len(path) - 1
                while nn > 0 and d["s"][path[nn]] > e["s_land"] + mx: nn -= 1
                hs = mx
            got = Vs[nn] * e["qt"] / (Ts[nn] + e["qt"]) * (1 - e["fr"]) / 1e9; pnl = got - e["B"] - B8.FIX
            pa.append(pnl); dev.append(abs(hs - t["hold"]))
            if t["buys"][0]["sol"] < 1.0: ps.append(pnl)
        out[ri] = (len(pa), round(sum(pa), 2), round(float(np.mean(pa)), 4), round(sum(ps), 2), int(np.median(dev)) if dev else None)
    return out
if __name__ == "__main__":
    rules = []
    for l in open(f"{OUT}/llm/answers_exit.jsonl"):
        for r in json.loads(l).get("exit_rules") or []: rules.append(r)
    E.load(["R2", "R3", "R1"])
    res = {day: run(day, rules) for day in ("R2", "R3", "R1")}
    print("Haiku exit rules on its entries at 35 ms, 0.6 SOL: (n, P&L all, mean, P&L curve<50, median |exit slot - its exit slot|)")
    for i, R in sorted(enumerate(rules), key=lambda x: -res["R2"][x[0]][1]):
        print(f"  {R.get('name', '')[:40]:<40} R2 {res['R2'][i]} | R3 {res['R3'][i]} | R1 {res['R1'][i]}")
    json.dump(dict(rules=rules, res=res), open(f"{OUT}/exit_verify.json", "w"))
