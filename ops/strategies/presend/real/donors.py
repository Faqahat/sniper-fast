#!/usr/bin/env python3
"""REAL replay: the live tries of both probes as 'donor' sequences for the landing model (MEASURED, read-only).
Per live window: the trigger's chain clock (recorded block sizes), and per try:
  d    = send time after the engine saw the trigger (ms; t_send - trigger rx)
  lam  = landing chain clock - trigger chain clock - d   (= the trigger's feed delay + the try's send->land delay)
  g    = trigger chain clock + d - (send slot + 0.5) x 212 (how far the engine's slot view lags the chain clock)
  res  = ok / 6042 / deadline / ata_exists / drop (never on chain)
Unseen tries (the engine's feed missed them) are looked up in the chain recording: most did land.
Writes /home/moiz/sniper-data/presend_real/donors.pkl"""
import sys, os, json, pickle, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib, probes as PR

OUT = "/home/moiz/sniper-data/presend_real/donors.pkl"

def classify(err):
    """our attempt's error in the recording (InstructionError index) -> result class (roles: guard 2, ata 3, buy 5)"""
    if err is None: return "ok"
    try:
        ie = err.get("InstructionError")
        if ie:
            n = ie[0]; c = ie[1]
            if n == 2: return "deadline"
            if n == 3: return "ata_exists"
            if n == 5 and isinstance(c, dict) and c.get("Custom") == 6042: return "6042"
            return "other"
    except Exception: pass
    return "other"

def build(tp):
    ours = {}
    for l in open(f"{rlib.TAB}/ours.jsonl"):
        r = json.loads(l); ours[r["sig"]] = r
    D = {}
    for name in ("P1", "P2"):
        P = PR.load(name)
        cfg = P["start"]["presend_live"]
        wins = []
        for w, x in P["W"].items():
            tr = x["arm"]["trig"]
            ct = tp.cc(tr["slot"], tr["idx"])
            t0 = tr["t"]
            tries = []
            for a in x["atts"]:
                L = a["land"] or {}
                d = (a["t"] - t0) / 1e6
                o = ours.get(a["sig"])
                res = L.get("res"); slot = L.get("slot"); idx = L.get("idx")
                src = "live"
                if res in (None, "unseen") or slot is None:
                    if o is not None:
                        res = classify(o.get("err")); slot = o["s"]; idx = o["i"]; src = "chain"
                    else:
                        s_lo = a["slot"]; covered = all(tp.nblk(s) > 0 for s in range(s_lo, a["deadline"] + 4))
                        res = "drop" if covered else "unknown"; slot = None; idx = None; src = "none"
                lam = (tp.cc(slot, idx) - ct - d) if slot is not None else None
                g = ct + d - (a["slot"] + 0.5) * rlib.SMS
                tries.append(dict(n=a["n"], d=d, send_slot=a["slot"], deadline=a["deadline"], en_slot=a["en_slot"], lim=a["lim"], p=a["p"],
                                  pos=a["pos"], slot=slot, idx=idx, res=res, src=src, lam=lam, g=g, client=a["client"], sig=a["sig"],
                                  fee=(L.get("fee") if L.get("fee") is not None else (o or {}).get("fee"))))
            wins.append(dict(probe=name, w=w, mint=tr["mint"], trig=tr, ct=ct, en_slot=x["arm"]["en_slot"], tries=tries,
                             disarm=x["disarm"], fill=x["fill"], exit=x["exit"], sell=x["sell"], close=x["close"], realized=x["realized"]))
        D[name] = dict(cfg=cfg, wins=wins, start=P["start"], stop=P["stop"], shadow=P["shadow"], dumps=P["dumps"])
    return D

# ---- the engine's view of later trades (MEASURED from the live tries' signing prices; used by sim.View) ----------------
def view_quantile(D, tp, view):
    """per donor window: the view-speed quantile q (0.05..0.95) that best explains its tries' signing prices"""
    import sim
    for name in D:
        for W in D[name]["wins"]:
            tr = W["trig"]; s0 = tr["slot"]; ct = W["ct"]
            tk = sim.Tok(tp, W["mint"], s0 - 3, s0 + 14)
            kt = tk.before(tr["slot"], tr["idx"] + 0.5)
            obs = []
            for t in W["tries"]:
                pos = tuple(t["pos"][:2]); ks = tk.before(pos[0], pos[1] + 0.5)
                if ks < 0 or tk.pos[ks] != pos: continue
                obs.append((t["d"], ks))
            best = (-1, 0.5)
            for q in np.arange(0.05, 0.96, 0.05):
                seen = view.seen_times(tk, kt, s0, ct, q)
                ok = 0
                for d, ks in obs:
                    k2 = int(np.searchsorted(seen, d, side="right")) - 1 + (kt + 1)
                    ok += (max(k2, kt) == ks)
                score = ok + 1e-3 * (1 - abs(q - 0.5))
                if score > best[0]: best = (score, float(q))
            W["q_view"] = best[1]; W["q_fit"] = best[0] / max(len(obs), 1)

if __name__ == "__main__":
    tp = rlib.Tape()
    D = build(tp)
    import sim
    view_quantile(D, tp, sim.View())
    pickle.dump(D, open(OUT, "wb"))
    for name in D:
        T = [t for w in D[name]["wins"] for t in w["tries"]]
        print(name, "tries", len(T), "results", collections.Counter(t["res"] for t in T).most_common(), "sources", collections.Counter(t["src"] for t in T))
        lam = np.array([t["lam"] for t in T if t["lam"] is not None]); g = np.array([t["g"] for t in T])
        print("  lam pcts", np.percentile(lam, [5, 10, 25, 50, 75, 90, 95]).round(1))
        print("  g pcts", np.percentile(g, [5, 10, 25, 50, 75, 90, 95]).round(1))
        q = np.array([w["q_view"] for w in D[name]["wins"]]); fit = np.array([w["q_fit"] for w in D[name]["wins"]])
        print("  view speed q pcts", np.percentile(q, [10, 25, 50, 75, 90]).round(2), "signing-price fit p50 %.2f mean %.2f" % (np.median(fit), fit.mean()))
