#!/usr/bin/env python3
"""TUNE t5: creator ledgers, checked at the ARM (T2 and re-arm), learned online from OUR KEPT positions only (a blocked position never
enters the ledger), a position counts once its presend_live_realized record was written before the arm record (record order = what the
engine knew). Variants: run-only vs carried across runs (state file), creator still holding >= 3% or any, min positions, P&L sum
threshold, 24 h window; plus QUIET3-B (last <= 3 positions all not followed, 24 h) alone / OR'd with the ledger.
Scored on realized P&L: DEV / VALx / VAL / HOLD, w/o top 5."""
import sys, pickle, json, collections, itertools
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/tune")
import tlib as T
P = pickle.load(open("/home/moiz/sniper-data/filters3/tune/pos_all.pkl", "rb"))
A0, A1 = 1793590164e9 - 60e9, 1793590555e9 + 60e9
for r in P: r["attk"] = r["run"] == "r42" and A0 <= r["t"] <= A1
# arm seq per position
for r in P:
    a = T.load(r["run"])["arms"].get(r["k"], {}); r["arm_seq"] = a.get("_seq", r["seq"]); r["arm_t"] = (a.get("trig") or a.get("dump") or {}).get("t") or r["t"]
    r["creator"] = (a.get("ann") or {}).get("creator"); r["cr_pct"] = (a.get("ann") or {}).get("cr_pct") or 0
RUNORD = T.RUNS
def sim(rule, persist=True):
    """rule(hist, r) -> block?; hist = list of (t_known, pnl, followed) of kept positions of r's creator. Returns set of blocked keys."""
    blocked = set(); led = collections.defaultdict(list)
    for run in RUNORD:
        if not persist: led = collections.defaultdict(list)
        R = [r for r in P if r["run"] == run]
        evs = sorted([(r["arm_seq"], 0, i) for i, r in enumerate(R)] + [(r["seq"], 1, i) for i, r in enumerate(R)])
        for s, typ, i in evs:
            r = R[i]
            if typ == 0:
                c = r["creator"]
                if c and rule(led[c], r): blocked.add((run, r["k"]))
            else:
                if (run, r["k"]) in blocked: continue
                if r["creator"]: led[r["creator"]].append((r["t"], r["pnl"], r["followed"]))
    return blocked
SEG = {"DEV": lambda r: r["per"] == "DEV" and r["run"] not in ("r37", "r38"), "VALx": lambda r: r["per"] == "VAL" and not r["attk"],
       "VAL": lambda r: r["per"] == "VAL", "HOLD": lambda r: r["per"] == "HOLD"}
H = {"DEV": 3.14 + 17.29 + 1.32 + 32.12, "VALx": 19.93, "VAL": 20.6, "HOLD": 14.23}
def score(B):
    out = {}
    for sn, sf in SEG.items():
        v = [r["pnl"] for r in P if sf(r) and (r["run"], r["k"]) in B]
        d = T.summ(v); d["wo5"] = T.wo_top(v); d["day"] = round(d["saved"] / H[sn] * 24, 2); out[sn] = d
    return out
def fmt(name, d):
    return f"{name:58s}" + "".join(f" | {sn} {d[sn]['n']:3d} p{(d[sn]['prec'] or 0):.2f} {d[sn]['saved']:+6.3f} w5 {d[sn]['wo5']:+6.3f} {d[sn]['day']:+5.2f}/d" for sn in SEG)
def ledger(nmin, smax, crmin, win_h=None):
    def f(h, r):
        if r["cr_pct"] < crmin: return False
        hh = [x for x in h if win_h is None or x[0] >= r["arm_t"] - win_h * 3.6e12]
        return len(hh) >= nmin and sum(x[1] for x in hh) <= smax
    return f
def qb(h, r):
    hh = [x for x in h if x[0] >= r["arm_t"] - 24 * 3.6e12][-3:]
    return bool(hh) and not any(x[2] for x in hh)
res = {}
print("CREATOR LEDGERS at ARM (kept positions only; DEV = r39..r42-DEV, the runs that log the creator)")
B0 = {(r["run"], r["k"]) for r in P if r["gcr"]}
print(fmt("dashboard gcr (cr>=3%, n>=2, sum<=-0.05, run-only, as logged)", score(B0))); res["gcr_logged"] = score(B0)
rows = []
for persist, crmin, nmin, smax, wh in itertools.product((False, True), (0, 3), (1, 2, 3), (-0.03, -0.05, -0.10, -0.15), (None, 24)):
    B = sim(ledger(nmin, smax, crmin, wh), persist); sc = score(B)
    name = f"{'carry' if persist else 'run  '} cr>={crmin} n>={nmin} sum<={smax} win {wh or 'all'}"
    rows.append((name, sc)); res[name] = sc
rows.sort(key=lambda x: -x[1]["DEV"]["saved"])
for name, sc in rows:
    ok = all(sc[s]["saved"] > 0 and sc[s]["wo5"] > 0 for s in SEG)
    print(fmt(("ALL+ " if ok else "     ") + name, sc))
print("\nQUIET3-B and its union with ledgers (sequential, kept-only)")
for name, rule in (("QUIET3-B (last<=3 in 24h all not followed)", qb),
                   ("G1 = carry cr>=0 n>=1 sum<=-0.10", ledger(1, -0.10, 0)),
                   ("B or G1", lambda h, r: qb(h, r) or ledger(1, -0.10, 0)(h, r)),
                   ("B or carry cr>=3 n>=2 sum<=-0.05", lambda h, r: qb(h, r) or ledger(2, -0.05, 3)(h, r)),
                   ("B or carry cr>=0 n>=2 sum<=-0.05", lambda h, r: qb(h, r) or ledger(2, -0.05, 0)(h, r))):
    B = sim(rule, True); sc = score(B); res[name] = sc; print(fmt(name, sc))
json.dump(res, open("/home/moiz/sniper-data/filters3/tune/t5_creator.json", "w"))
