#!/usr/bin/env python3
"""INSIDER step 1: rebuild the observatory selection census (select_cand records, src/obs/select.rs) per run.
Collects every select_cand record of the given obs files (deduped on mint/wallet/slot/idx), flattens the fields we need and saves
one pickle per run.  usage: in1_census.py RUN OUT.pkl FILE [FILE...]"""
import sys, json, pickle
run, outp, files = sys.argv[1], sys.argv[2], sys.argv[3:]
rows = {}; nlines = 0
for f in files:
    with open(f, "rb") as fh:
        for line in fh:
            if b'"select_cand"' not in line: continue
            try: r = json.loads(line)
            except Exception: continue
            if r.get("ev") != "select_cand": continue
            nlines += 1
            o = r.get("outcome") or {}; d = o.get("dump") or {}
            q = r.get("quiet") or {}
            k = (r["mint"], r["w"], r["slot"], r["idx"])
            rows[k] = {"run": run, "mint": r["mint"], "w": r["w"], "slot": r["slot"], "idx": r["idx"], "t": r["t"], "class": r["class"], "live": r["live_arms"],
                       "why_not": r.get("why_not"), "pct": r["pct_after"], "buy_sol": r.get("buy_sol"), "age": r.get("age_slots"), "age_ms": r.get("age_ms"), "vsol": r.get("vsol"),
                       "n60": r.get("n60"), "b60": r.get("b60"), "n120": r.get("n120"), "b120": r.get("b120"), "q_all4": q.get("all4"), "q_since": q.get("since_last"),
                       "q_coh": q.get("coh_hold"), "q_fb": q.get("fb_n"), "q_whfol": q.get("wh_fol"), "q_whd": q.get("wh_dumps"),
                       "dump": bool(d), "gap": d.get("slot_gap"), "dms": d.get("ms"), "psold": d.get("pct_sold"), "drop": d.get("drop_pct"),
                       "reb": o.get("rebound_15"), "fol_n": (o.get("followers") or [None, None])[0], "fol_sol": (o.get("followers") or [None, None])[1],
                       "paper": o.get("paper_065_msol"), "inwin": o.get("in_window")}
pickle.dump(list(rows.values()), open(outp, "wb"))
print(run, "records", nlines, "unique", len(rows))
