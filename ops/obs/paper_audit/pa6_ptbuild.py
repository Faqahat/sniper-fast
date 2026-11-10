#!/usr/bin/env python3
"""PAPER AUDIT step 6 [MEASURED inputs, read-only]: the try-level replay's inputs (custom37 format) for the FULL r37 run.
Live windows = custom37's c1_extract on the fresh r37 records (every real try with its landing); SKIPPED T2 triggers (presend_live_skip:
create_slot, quiet, young_age, ...) become windows with no tries ("synthetic"), so the same replay can put phantom tries on them.
RE-ARM windows (observatory rearm_window records, --rearm OBS ...) become windows too, armed at the record's arm time and stopped at its end.
Tapes: custom37's c2_tape.from_tab on the paper-audit tape (pa_decode + build: the recorder chunks of the whole run).
Out: OUTDIR/win_r37f.pkl, OUTDIR/tape_r37f.pkl  (c37lib reads them with c37lib.D = OUTDIR)
usage: pa6_ptbuild.py RUN.jsonl TAB OUTDIR [--rearm OBS.jsonl ...]"""
import sys, json, pickle, collections
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/custom37")
import c1_extract as E
import c2_tape as T


def rearm_windows(paths, ses):
    out = []
    seen = set()
    for p in paths:
        for line in open(p, errors="replace"):
            if '"ev":"rearm_window"' not in line: continue
            try: r = json.loads(line)
            except Exception: continue
            key = (r["mint"], r["dump"]["sig"])
            if key in seen: continue
            seen.add(key)
            out.append(r)
    return out


def main(run_jsonl, tab, outdir, rearm_paths):
    E.RUNS["r37f"] = ("AMS", run_jsonl)
    X = E.extract("r37f")
    ses = max(W["ses"] for W in X["wins"])
    n0 = len(X["wins"])
    syn = collections.Counter()
    for i, s in enumerate(X["skips"]):
        if s["ses"] != ses or "trig" not in s or not s["trig"]: continue
        tg = s["trig"]
        W = {"run": "r37f", "reg": "AMS", "ses": ses, "w": 1_000_000 + i, "mint": tg["mint"], "trig": tg, "en_slot": tg["slot"] + 10, "k": 8, "spend": 696_000_000,
             "drop": 0.12, "lim0": None, "quiet": s.get("quiet"), "v2": s.get("v2"), "dis": None, "tries": [], "fills": [], "exit": None, "sells": [], "close": None,
             "real": [], "late": [], "ptape": [], "synthetic": s["why"]}
        X["wins"].append(W); syn[s["why"]] += 1
    nre = 0
    for i, r in enumerate(rearm_windows(rearm_paths, ses)):
        d = r["dump"]
        tg = {"sig": d["sig"], "slot": d["slot"], "idx": d["idx"], "j": d.get("j", 0), "t": d["t"], "a": None, "wallet": d["seller"], "bal": 0, "vsol": d["vsol"], "vtok": d["vtok"],
              "age_slots": d.get("age_slots"), "mint": r["mint"], "sol": d["sol"], "tok": d["tok"], "pct": d["pct"]}
        W = {"run": "r37f", "reg": "AMS", "ses": ses, "w": 2_000_000 + i, "mint": r["mint"], "trig": tg, "en_slot": r["en_slot"], "k": 8, "spend": 650_000_000, "drop": 0.12,
             "lim0": None, "quiet": {"stop": "6:2"}, "v2": None, "dis": None, "tries": [], "fills": [], "exit": None, "sells": [], "close": None, "real": [], "late": [], "ptape": [],
             "synthetic": "rearm", "rearm": {"arm": r["arm"], "end": r["end"], "end_r2": r.get("end_r2"), "en_slot_r2": r.get("en_slot_r2"), "r5_skip": r.get("r5_skip"),
                                             "quiet_stop": r.get("quiet_stop"), "superseded": r.get("superseded"), "rows": {k: (v or {}).get("hit") for k, v in (r.get("rows") or {}).items()},
                                             "rows_full": r.get("rows"), "tries": r.get("tries"), "holders": r.get("holders")}}
        X["wins"].append(W); nre += 1
    X["wins"].sort(key=lambda W: W["trig"]["t"])
    pickle.dump(X, open(f"{outdir}/win_r37f.pkl", "wb"))
    tapes, maxi, end = T.from_tab(X, tab)
    pickle.dump({"tapes": tapes, "maxi": maxi, "end_slot": end}, open(f"{outdir}/tape_r37f.pkl", "wb"))
    print("live windows", n0, "synthetic skips", dict(syn), "rearm windows", nre, "with tape", sum(1 for W in X["wins"] if tapes.get((W["ses"], W["w"]))), "end slot", end)


if __name__ == "__main__":
    a = sys.argv[1:]
    rp = []
    if "--rearm" in a:
        k = a.index("--rearm"); rp = a[k + 1:]; a = a[:k]
    main(a[0], a[1], a[2], rp)
