#!/usr/bin/env python3
"""BOTREG step 4 [MEASURED replay]: hour-by-hour registry updates over all recorded hours, as if live
(update at the end of each covered hour, using only hours before it). Starts EMPTY (no seed list).
Out: /home/it/sniper-data/botreg/backtest/{transitions.jsonl, members.npz (t, u64, state code), snap_<day>.json, final.json}
     and the newest registry.json / engine_view.json / engine_view.txt in /home/it/sniper-data/botreg/"""
import sys, os, json, pickle, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C, hourly_table as HT, reg as R

OUT = f"{C.DATA}/backtest"
SC = {"probation": 1, "active": 2, "dormant": 3}
if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    T = HT.load()
    cov = sorted(set(int(x) for x in T["_G"]["h"]))
    reg = R.Registry(); fp = R.FPStore()
    mt, mu, ms = [], [], []
    st_t, st_u, st_s = [], [], []
    t0 = time.time()
    for h in cov:
        reg.add_hour(T, h)
        p = f"{C.DATA}/fprint/{h}.pkl"
        if os.path.exists(p): fp.add_hour(h, pickle.load(open(p, "rb")))
        po = f"{C.DATA}/hourly/{h}.ours.pkl"
        if os.path.exists(po): reg.add_positions(sorted(pickle.load(open(po, "rb")), key=lambda p: p["bt"]))
        t = h + C.H
        reg.update(T, t, cov, fp)
        reg.update_sellers(t, [x for x in cov if x < t], fp)
        for u, s in reg.seller_view().items(): st_t.append(t); st_u.append(u); st_s.append(1 if s == "active" else 3)
        es = reg.engine_states()
        for u, s in es.items(): mt.append(t); mu.append(u); ms.append(SC[s])
        if C.pkt(h).endswith("23:00") or h == cov[-1]:
            j = reg.to_json(fp, t)
            json.dump(j, open(f"{OUT}/snap_{C.pkt(h)[:5].replace('-', '')}.json", "w"), indent=1)
        n = {}
        for r in reg.W.values(): n[r["state"]] = n.get(r["state"], 0) + 1
        print(C.pkt(t), n, "sellers", len(reg.seller_view()), round(time.time() - t0), flush=True)
    with open(f"{OUT}/transitions.jsonl", "w") as f:
        for e in reg.log:
            f.write(json.dumps({"t": e["t"], "t_pkt": C.pkt(e["t"]), "wallet": fp.b58.get(e["u"], str(e["u"])), "u64": str(e["u"]),
                                "from": e["from"], "to": e["to"], "why": e["why"]}) + "\n")
    np.savez(f"{OUT}/members.npz", t=np.array(mt, np.int64), u=np.array(mu, np.uint64), s=np.array(ms, np.int8))
    np.savez(f"{OUT}/sellers.npz", t=np.array(st_t, np.int64), u=np.array(st_u, np.uint64), s=np.array(st_s, np.int8))
    pickle.dump(reg, open(f"{OUT}/registry_state.pkl", "wb"))
    pickle.dump({"reg": reg, "fp": fp, "last_hour": cov[-1]}, open(f"{C.DATA}/state.pkl.tmp", "wb"))
    os.replace(f"{C.DATA}/state.pkl.tmp", f"{C.DATA}/state.pkl")
    t = cov[-1] + C.H
    reg.resolve_names(fp, 2500)
    R.write_atomic(f"{C.DATA}/registry.json", reg.to_json(fp, t))
    ev = reg.engine_view(fp, t)
    R.write_atomic(f"{C.DATA}/engine_view.json", ev)
    R.write_atomic(f"{C.DATA}/engine_view.txt", "".join(w["w"] + "\n" for w in ev["wallets"]), text=True)
    R.write_atomic(f"{C.DATA}/engine_sellers.txt", "".join(w["w"] + "\n" for w in ev["sellers"]), text=True)
    print("done", len(reg.W), "engine view", ev["n"], flush=True)
