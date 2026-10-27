#!/usr/bin/env python3
"""SIZE_48H step 1a (read-only): probe 3's (AMS run 19) live tries as landing donors, the same way donors.py made them for
probes 1-2 (d, lam, g, result; unseen tries looked up in the chain recording; each window's view speed q fitted on its tries'
signing prices). Writes s48/donors123.pkl = {P1, P2 (unchanged, from donors.pkl), P3}."""
import sys, os, json, pickle, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s48lib
s48lib.use_tab48()
import rlib, sim, donors, probes as PR

def build_p3(tp):
    ours = {}
    for l in open(f"{rlib.TAB}/ours.jsonl"):
        r = json.loads(l); ours[r["sig"]] = r
    P = PR.load("P3")
    cfg = P["start"]["presend_live"]
    wins = []
    for w, x in P["W"].items():
        tr = x["arm"]["trig"]; ct = tp.cc(tr["slot"], tr["idx"]); t0 = tr["t"]
        tries = []
        for a in x["atts"]:
            L = a["land"] or {}
            d = (a["t"] - t0) / 1e6
            o = ours.get(a["sig"])
            res = L.get("res"); slot = L.get("slot"); idx = L.get("idx"); src = "live"
            if res in (None, "unseen") or slot is None:
                if o is not None:
                    res = donors.classify(o.get("err")); slot = o["s"]; idx = o["i"]; src = "chain"
                else:
                    covered = all(tp.nblk(s) > 0 for s in range(a["slot"], a["deadline"] + 4))
                    res = "drop" if covered else "unknown"; slot = None; idx = None; src = "none"
            lam = (tp.cc(slot, idx) - ct - d) if slot is not None else None
            g = ct + d - (a["slot"] + 0.5) * rlib.SMS
            tries.append(dict(n=a["n"], d=d, send_slot=a["slot"], deadline=a["deadline"], en_slot=a["en_slot"], lim=a["lim"], p=a["p"], pos=a["pos"],
                              slot=slot, idx=idx, res=res, src=src, lam=lam, g=g, client=a["client"], sig=a["sig"], path=a.get("path"),
                              t_send=a["t"], ms_rx=L.get("ms_send_to_rx"), sas=L.get("slots_after_send"),
                              fee=(L.get("fee") if L.get("fee") is not None else (o or {}).get("fee"))))
        wins.append(dict(probe="P3", w=w, mint=tr["mint"], trig=tr, ct=ct, en_slot=x["arm"]["en_slot"], tries=tries, disarm=x["disarm"], fill=x["fill"],
                         exit=x["exit"], sell=x["sell"], close=x["close"], realized=x["realized"]))
    return dict(cfg=cfg, wins=wins, start=P["start"], stop=P["stop"], shadow=P["shadow"], dumps=P["dumps"], skips=P["skips"])

if __name__ == "__main__":
    tp = s48lib.Tape48()
    D3 = {"P3": build_p3(tp)}
    donors.view_quantile(D3, tp, sim.View())
    D = pickle.load(open(f"{s48lib.BASE}/donors.pkl", "rb"))
    D["P3"] = D3["P3"]
    pickle.dump(D, open(f"{s48lib.S48}/donors123.pkl", "wb"))
    T = [t for w in D["P3"]["wins"] for t in w["tries"]]
    print("P3 windows", len(D["P3"]["wins"]), "tries", len(T), "results", collections.Counter(t["res"] for t in T).most_common(),
          "sources", collections.Counter(t["src"] for t in T))
    lam = np.array([t["lam"] for t in T if t["lam"] is not None])
    print("  lam pcts", np.percentile(lam, [5, 10, 25, 50, 75, 90, 95]).round(1))
    q = np.array([w["q_view"] for w in D["P3"]["wins"]]); fit = np.array([w["q_fit"] for w in D["P3"]["wins"]])
    print("  view q pcts", np.percentile(q, [10, 25, 50, 75, 90]).round(2), "fit p50 %.2f mean %.2f" % (np.median(fit), fit.mean()))
    print("  cfg", D["P3"]["cfg"])
    print("  disarms", collections.Counter((W["disarm"] or {}).get("why") for W in D["P3"]["wins"]))
