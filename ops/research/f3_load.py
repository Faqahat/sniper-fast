# READ-ONLY (host): one joined table for FILTERS3.md ("creator dev"-style create-time signals).
# Rows = FILTERS2's priced launches A-D (filters2_rows.json) + the live paper launches after D (group E, f3_rows_e.py),
# joined with the block recording of each launch (bundle members, trades S..S+2), the feed's RACE obs outs, and the
# creator's on-chain transactions (creator_creates.py). Every HISTORY feature uses only launches whose create is >= LAG
# slots (~2 min) before this one (time to settle + price) and on-chain transactions with slot < S: no look-ahead.
import os, json, collections

HERE = os.path.dirname(os.path.abspath(__file__))
SP = os.environ.get("F3_WORK", "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad")
F3 = os.path.join(SP, "f3")
REC_DIRS = ["/home/moiz/sniper-data/research/rec", os.path.join(SP, "f2", "paper", "rec"), os.path.join(F3, "paper", "rec")]
LAG = 550
PROS = {"dKMjeG": "dKMjeG", "4yFAz7": "4yFAz7", "9XPMCa": "9XPMCa", "3yrJE1": "3yrJE1", "AHwJSn": "AHwJSn", "2EsRia": "2EsRia", "9qz7cW": "9qz7cW"}
OURS6 = ("FRZh63", "2g7rYv")


def rec_of(r):
    for d in REC_DIRS:
        p = os.path.join(d, r["mint"] + ".json")
        if os.path.exists(p):
            x = json.load(open(p))
            if x["S"] == r["S"]: return x
    return None


def load():
    from f2_load import market
    R = json.load(open(os.path.join(HERE, "filters2_rows.json")))
    rows = R["rows"]; hours = dict(R.get("hours") or {})
    if not hours:
        hours = dict(json.load(open(os.path.join(HERE, "filters_rows.json")))["hours"])
        hours["D"] = json.load(open(os.path.join(SP, "f2", "paper", "paper_rows.json")))["hours"]["D"]
    E = json.load(open(os.path.join(F3, "paper", "paper_rows_e.json")))
    hours.update(E["hours"])
    LE = {(x["S"], x["mint"]): x for x in json.load(open(os.path.join(F3, "paper", "launches_ready.json")))["launches"]}
    for r in E["rows"]:
        x = LE[(r["S"], r["mint"])]
        for f in ("creator", "name", "sym", "uri", "dev_sized", "dev_cap", "tip", "tip_to"): r[f] = x.get(f)
    rows = rows + E["rows"]
    # feed outs (RACE obs) per launch
    OB = {}
    for p in (os.path.join(SP, "filt", "launches2.json"), os.path.join(SP, "f2", "paper", "launches_ready.json"), os.path.join(F3, "paper", "launches_ready.json")):
        for x in json.load(open(p))["launches"]:
            OB[(x["S"], x["mint"])] = x
    for r in rows:
        x = OB.get((r["S"], r["mint"])) or {}
        r["outs"] = (x.get("obs") or {}).get("outs") or []
        r["dev_lam"] = x.get("dev"); r["dev_sized_l"] = x.get("dev_sized"); r["dev_cap_l"] = x.get("dev_cap")
        rec = rec_of(r)
        r["_has_rec"] = rec is not None
        if rec:
            r["bmem"] = sorted(set(rec.get("bundle_members") or []) - {r["mint"], r["creator"]})
            if r["grp"] == "E": r.update(market(rec))
            S = r["S"]; mem = set(rec.get("bundle_members") or []) | {r["creator"]}
            r["pro_in"] = sorted({PROS[k] for t in rec["trades"] if t["buy"] and t["slot"] <= S + 2 for k in PROS if t["user"].startswith(k)})
        else:
            r["bmem"] = []; r["pro_in"] = []
        b6 = {w[:6] for w in r["bmem"]} | {r["creator"][:6]}
        early = [(ms, sol, w) for ms, sol, f, w in r["outs"] if ms <= 5.0 and f == "1" and w not in b6 and not w.startswith(OURS6)]
        r["early_n"] = len(early); r["early_sol"] = sum(s for _, s, _ in early)
        r["early_n3"] = sum(1 for ms, _, _ in early if ms <= 3.0)
    rows.sort(key=lambda r: r["S"])
    return rows, hours
