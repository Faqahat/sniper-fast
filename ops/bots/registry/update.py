#!/usr/bin/env python3
"""BOTREG live update (incremental; proposed schedule: every hour at HH:05 PKT, after the hour's chunks + 60 s are recorded).
Steps: (1) decode new recording chunks  (2) hourly counters + our positions for newly completed hours
       (3) widen the fingerprint watch set with new loose-bar wallets (back-fill their last 72 h)  (4) fingerprints of new hours
       (5) registry update per new hour (discovery, linking, lifecycle, sellers) from state.pkl  (6) atomic writes:
   /home/moiz/sniper-data/botreg/registry.json      full registry (wallets, operators, sellers, evidence, history)
   /home/moiz/sniper-data/botreg/engine_view.json   flat lists for the engine: wallets (follower/dip bots) + sellers
   /home/moiz/sniper-data/botreg/engine_view.txt / engine_sellers.txt   one base58 per line
Local only: reads sniper-data/collect, writes sniper-data/botreg. No server, no engine change.
usage: update.py [--dry]"""
import sys, os, json, pickle, time, glob, subprocess, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C, hourly_table as HT, reg as R
HERE = os.path.dirname(os.path.abspath(__file__))
D = C.DATA


def sh(*a):
    r = subprocess.run([sys.executable, *a], cwd=D, capture_output=True, text=True, env=dict(os.environ, NW=os.environ.get("NW", "4")))
    if r.returncode: raise SystemExit(f"step failed: {a}\n{r.stderr[-2000:]}")
    return r.stdout


def main():
    t0 = time.time()
    st = pickle.load(open(f"{D}/state.pkl", "rb"))
    reg, fp, last = st["reg"], st["fp"], st["last_hour"]
    sh(f"{HERE}/x0_extract.py")
    sh(f"{HERE}/x1_hourly.py")
    T = HT.load()
    cov = sorted(set(int(x) for x in T["_G"]["h"]))
    new = [h for h in cov if h > last]
    if not new:
        print("no new complete hour; registry unchanged (data through", C.pkt(last + C.H), ")"); return
    # (3) watch set: loose-bar-ish wallets of the last 24 h not yet watched -> back-fill their fingerprints over 72 h
    W = {int(x) for x in open(f"{D}/watch.txt").read().split()}
    w24 = R.Window(T, cov[-24:])
    add = set(w24.mask(lambda S, d: ((S["n_dip"] >= 5) & (S["n_trip"] >= 8)) | (S["n_fol_fills"] >= 3))) | set(reg.S)
    add -= W | set(C.OURS64)
    if add:
        tag = f"bf{int(time.time())}"
        open(f"{D}/watch_{tag}.txt", "w").write("\n".join(map(str, sorted(add))) + "\n")
        hrs = [h for h in cov if h > last - R.CFG["LINK"]["fp_hours"] * C.H]
        sh(f"{HERE}/x2_fprint.py", f"{D}/watch_{tag}.txt", "--hours", str(hrs[0]), str(hrs[-1] + C.H), "--tag", tag)
        for h in hrs:
            for p in glob.glob(f"{D}/fprint/{h}.{tag}.pkl"):
                if h <= last: fp.backfill(h, pickle.load(open(p, "rb")))
        W |= add
        open(f"{D}/watch.txt.tmp", "w").write("\n".join(map(str, sorted(W))) + "\n"); os.replace(f"{D}/watch.txt.tmp", f"{D}/watch.txt")
    sh(f"{HERE}/x2_fprint.py", f"{D}/watch.txt", "--hours", str(new[0]), str(new[-1] + C.H))
    for h in new:
        reg.add_hour(T, h)
        recs = {}
        for p in sorted(glob.glob(f"{D}/fprint/{h}.pkl")) + sorted(glob.glob(f"{D}/fprint/{h}.bf*.pkl")):
            for u, r in pickle.load(open(p, "rb")).items(): recs.setdefault(u, r)
        fp.add_hour(h, recs)
        po = f"{D}/hourly/{h}.ours.pkl"
        if os.path.exists(po): reg.add_positions(sorted(pickle.load(open(po, "rb")), key=lambda p: p["bt"]))
        t = h + C.H
        reg.update(T, t, cov, fp)
        reg.update_sellers(t, [x for x in cov if x < t], fp)
    t = new[-1] + C.H
    reg.resolve_names(fp, 60)
    if "--dry" in sys.argv:
        print("dry run: would write version", reg.version); return
    R.write_atomic(f"{D}/registry.json", reg.to_json(fp, t))
    ev = reg.engine_view(fp, t)
    R.write_atomic(f"{D}/engine_view.json", ev)
    R.write_atomic(f"{D}/engine_view.txt", "".join(w["w"] + "\n" for w in ev["wallets"]), text=True)
    R.write_atomic(f"{D}/engine_sellers.txt", "".join(w["w"] + "\n" for w in ev["sellers"]), text=True)
    pickle.dump({"reg": reg, "fp": fp, "last_hour": new[-1]}, open(f"{D}/state.pkl.tmp", "wb")); os.replace(f"{D}/state.pkl.tmp", f"{D}/state.pkl")
    print(f"registry v{reg.version} data through {C.pkt(t)} | hours added {len(new)} | engine view {ev['n']} | sellers {len(ev['sellers'])} | "
          f"watch +{len(add)} | {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
