#!/usr/bin/env python3
"""FRONT step 4 (read-only): our side on every paying dump (S) and the control sample (C).
Per dump: leader (pubkey, client class, region by IP geo, FRA/AMS near flags); which of our engines was running; pre-send: armed
window covering the dump? skip reason? our tries sent in [dump-3, dump] and where they landed (before/after the dump, same/next
slot, outside buys ahead, result); regular: did the engine log the dump, gate result, skip reason, fire, our landed copy and result.
Out: sniper-data/haqq_dissect/front/f4.pkl (list of dicts aligned with f2_sets S then C)"""
import sys, pickle, json, collections, math, bisect
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/front"
SCR = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/main"
exec(open(f"{SCR}/regions.py").read().split("# our pre-send stats")[0])   # HUBS, hub(), geo
REG = {"Amsterdam": "EU", "Frankfurt": "EU", "London": "EU", "Paris": "EU", "Warsaw/East EU": "EU", "New York/NJ": "US-East", "Ashburn VA": "US-East",
       "Toronto/Montreal": "US-East", "Chicago": "US-Central", "Dallas": "US-Central", "Salt Lake/Denver": "US-West", "Los Angeles/West": "US-West",
       "Tokyo": "Asia", "Singapore": "Asia", "Hong Kong": "Asia", "Seoul": "Asia", "Sydney": "Other", "Sao Paulo": "Other", "Mumbai/Middle East": "Other",
       "Johannesburg": "Other"}


def region_of(ld):
    v = geo.get(ld) if ld else None
    if not v or v.get("lat") is None: return "unknown"
    return REG[hub(v)[0]]


def main():
    R = pickle.load(open(f"{OUT}/f1.pkl", "rb")); SE = pickle.load(open(f"{OUT}/f2_sets.pkl", "rb"))
    O = pickle.load(open(f"{OUT}/f3_ours.pkl", "rb"))
    ids, idm = L.ids_map()
    _, CL, _ = L._sched()
    FT = pickle.load(open(f"{L.D}/fires_tape.pkl", "rb"))
    ftk = {(f["mint"], f["ds"], f["di"]): f for f in FT if f.get("ds") is not None}
    runs = O["runs"]
    run_iv = collections.defaultdict(list)
    for r, (a, b) in runs.items():
        if a: run_iv[r[:3]].append((a, b, r))
    arms = collections.defaultdict(list)
    for a in O["arms"]:
        arms[(a["srv"], a["mint"])].append(a)
    psk = collections.defaultdict(list)
    for s in O["pskips"]: psk[s["mint"]].append(s)
    tries = collections.defaultdict(list)
    for t in O["tries"]:
        if t.get("send_slot") is not None: tries[t["mint"]].append(t)
    # tape: our landed rows are in f1 front lists; outside buys after the dump come from front lists (first 6)
    rows = []
    for setname in ("S", "C"):
        for i in SE[setname]:
            r = R[i]; mint = ids[r["mint"]]; ds, di = r["ds"], r["di"]
            ld = L.leader_of(ds); ccl = L.client_class(CL.get(ld, "")) if ld else "?"
            raw_client = CL.get(ld, "") if ld else ""
            reg = region_of(ld)
            nearF = L.leader_info(ds, "FRA")[2]; nearA = L.leader_info(ds, "AMS")[2]
            up = {s: any(a <= r["bt"] <= b for a, b, _ in run_iv[s]) for s in ("AMS", "FRA")}
            upr = {s: next((rr for a, b, rr in run_iv[s] if a <= r["bt"] <= b), None) for s in ("AMS", "FRA")}
            # pre-send
            armed = {}
            for s in ("AMS", "FRA"):
                for a in arms.get((s, mint), []):
                    e = a["end_slot"] if a["end_slot"] is not None else a["arm_slot"] + 2000
                    if a["arm_slot"] is not None and a["arm_slot"] <= ds <= e: armed[s] = a
            skip = [x for x in psk.get(mint, []) if x["slot"] is not None and ds - 3000 <= x["slot"] <= ds]
            tr = [t for t in tries.get(mint, []) if ds - 3 <= t["send_slot"] <= ds]
            trl = []
            for t in tr:
                if t.get("slot") is None or t.get("idx") is None: trl.append(dict(t, rel="unlanded")); continue
                rel = "before" if (t["slot"], t["idx"]) < (ds, di) else ("same" if t["slot"] == ds else ("next" if t["slot"] == ds + 1 else "later"))
                trl.append(dict(t, rel=rel))
            # outside buys ahead of a position (from the front list; >= 6 if beyond it)
            def ahead(slot, idx):
                n = 0
                for f in r["front"]:
                    if f["ours"]: continue
                    if (f["slot"], f["idx"]) < (slot, idx): n += 1
                return n
            for t in trl:
                if t["rel"] in ("same", "next", "later"): t["ahead"] = ahead(t["slot"], t["idx"]); t["ms"] = float(L.cc(t["slot"], t["idx"]) - r["cc"])
            # regular
            reg_ = {}
            for s in ("AMS", "FRA"):
                d = O["dumps"].get((s, r["dsigh"]))
                if d is None: continue
                k = (s, r["dsigh"])
                reg_[s] = dict(seen=True, gate=d["gate"], m2=d["m2"], imit=d["imit"], launch_ok=d["launch_ok"], skip=O["skips"].get(k),
                               pick=O["picks"].get(k), fire=O["fires"].get(k))
            # dsigh matching may miss when the engine's dump sig differs; fall back to fires_tape by (mint, ds, di)
            ft = ftk.get((mint, ds, di))
            if ft is not None:
                ft = dict(out=ft["out"], us=ft["us"], n_ahead=ft.get("n_ahead"), d_ms=ft.get("d_ms"), d_slots=ft.get("d_slots"), srv=ft["srv"],
                          land_client=ft.get("land_client"), ncopies=ft.get("ncopies"), run=ft["run"])
                if ft["us"]: ft["ahead"] = ahead(ft["us"][0], ft["us"][1]); ft["ms"] = float(L.cc(ft["us"][0], ft["us"][1]) - r["cc"])
            ours_front = [k for k, f in enumerate(r["front"]) if f["ours"]]
            rows.append(dict(set=setname, i=i, mint=mint, ds=ds, di=di, bt=r["bt"], day=L.day_of(r["bt"]), leader=ld, client=ccl, raw_client=raw_client,
                             region=reg, nearF=nearF, nearA=nearA, up=up, upr=upr, armed={s: dict(arm_slot=a["arm_slot"], end_slot=a["end_slot"], why=a["why"],
                             trig_pct=a.get("trig_pct"), trig_age=a.get("trig_age"), k=a.get("k"), run=a["run"]) for s, a in armed.items()},
                             pskip=[(x["srv"], x["slot"], x["why"]) for x in skip][-3:], tries=trl, reg=reg_, ft=ft, ours_front=ours_front))
    pickle.dump(rows, open(f"{OUT}/f4.pkl", "wb"))
    S = [x for x in rows if x["set"] == "S"]
    print(f"S {len(S):,}: running any {sum(x['up']['AMS'] or x['up']['FRA'] for x in S):,}; armed {sum(bool(x['armed']) for x in S):,}; "
          f"tries after dump {sum(any(t['rel'] in ('same','next') for t in x['tries']) for x in S):,}; reg seen {sum(bool(x['reg']) for x in S):,}; "
          f"fired {sum(x['ft'] is not None for x in S):,}; ours in front6 {sum(bool(x['ours_front']) for x in S):,}")
    print(collections.Counter(x["region"] for x in S)); print(collections.Counter(x["client"] for x in S))


if __name__ == "__main__":
    main()
