#!/usr/bin/env python3
"""SIZE_48H step 1b (read-only): the MEASURED per-try landing of probe 3 (AMS run 19) next to probes 1-2, from the engine's own
records (presend_attempt_land: slots_after_send, ms_send_to_rx, client, path) and the donor table (lam = landing chain clock -
trigger chain clock - send offset, i.e. send -> land incl. the trigger's view delay). Also the live fills' rows."""
import sys, os, pickle, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s48lib
import probes as PR

def q3(a): return "/".join("%.0f" % x for x in np.percentile(a, [25, 50, 75])) if len(a) else "-"

if __name__ == "__main__":
    D = pickle.load(open(f"{s48lib.S48}/donors123.pkl", "rb"))
    for name in ("P1", "P2", "P3"):
        P = PR.load(name)
        L = [a["land"] for W in P["W"].values() for a in W["atts"] if a["land"] and a["land"].get("res") not in (None, "unseen")]
        sas = collections.Counter(min(int(x.get("slots_after_send") if x.get("slots_after_send") is not None else x["slot"] - x["send_slot"]), 2) for x in L)
        ms = [x["ms_send_to_rx"] for x in L if x.get("ms_send_to_rx") is not None]
        lam = [t["lam"] for W in D[name]["wins"] for t in W["tries"] if t["lam"] is not None]
        n = sum(sas.values())
        print(f"\n== {name}: tries {sum(len(W['atts']) for W in P['W'].values())}, landed with a feed record {n}; slot after send +0 {sas[0] / n * 100:.0f}% / +1 {sas[1] / n * 100:.0f}% / +2+ {sas[2] / n * 100:.0f}%; "
              f"send->seen ms p25/50/75 {q3(ms)}; send->land incl. trigger view (lam) {q3(lam)}")
        if name == "P3":
            byc = collections.defaultdict(list)
            for x in L: byc[x.get("client")].append(x)
            print("| Leader client | Landed tries | send->seen ms p25/50/75 | same slot / +1 / later |")
            print("|---|---|---|---|")
            for c, xs in sorted(byc.items(), key=lambda kv: -len(kv[1])):
                s = collections.Counter(min(int(x.get("slots_after_send") if x.get("slots_after_send") is not None else x["slot"] - x["send_slot"]), 2) for x in xs)
                m = len(xs)
                print(f"| {c} | {m} | {q3([x['ms_send_to_rx'] for x in xs if x.get('ms_send_to_rx') is not None])} | {s[0] / m * 100:.0f}% / {s[1] / m * 100:.0f}% / {s[2] / m * 100:.0f}% |")
        F = [W["fill"] for W in P["W"].values() if W["fill"]]
        fs = collections.Counter(f.get("slots_after_send") for f in F)
        print(f"   live fills {len(F)}: slots after send {dict(sorted(fs.items(), key=lambda kv: (kv[0] is None, kv[0] or 0)))}; send->seen ms {q3([f['ms_send_to_rx'] for f in F if f.get('ms_send_to_rx') is not None])}; "
              f"paths {dict(collections.Counter(f.get('path') for f in F))}; clients {dict(collections.Counter(f.get('client') for f in F))}")
        full = [W for W in D[name]["wins"] if (W["disarm"] or {}).get("why") == "expired" and sum(1 for t in W["tries"] if t["res"] != "unknown") >= 8]
        print(f"   donor windows (full length, >= 8 tries): {len(full)} of {len(D[name]['wins'])}; disarms {dict(collections.Counter((W['disarm'] or {}).get('why') for W in D[name]['wins']))}")
