#!/usr/bin/env python3
"""vs248 step 6 (read-only): the bridge (waterfall) from OUR wallet P&L per day to BOT 248's P&L per day, D2-D5, every SOL assigned.
Our side MEASURED (wallet = every FRA/AMS tx's SOL delta; lots = tape). 248 side MEASURED (code-matched tape lots + its tx costs).
The shared-dump steps (size / exit / entry / costs) are an exact-replay chain on the clean pairs (one our lot <-> one 248 lot);
residuals R1, R2 = replay vs measured (both ~0). Any day-boundary mismatch of a pair is its own line. Sum is exact by construction.
Out: vs248/v6_bridge.txt"""
import pickle, sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/vs248"
DAYS = (2, 3, 4, 5)


def main():
    Z = pickle.load(open(f"{OUT}/v2.pkl", "rb")); H, O, F, WAL = Z["H"], Z["O"], Z["ofail"], Z["wal"]
    PP = pickle.load(open(f"{OUT}/v3.pkl", "rb"))["P"]
    hk = {(h["slot"], h["idx"]): h for h in H}; ok = {(x["slot"], x["idx"]): x for x in O}
    hn = collections.Counter(r["h"] for r in PP); on = collections.Counter(r["o"] for r in PP)
    clean = [r for r in PP if hn[r["h"]] == 1 and on[r["o"]] == 1]
    cl_h = set(r["h"] for r in clean); cl_o = set(r["o"] for r in clean)
    lines = collections.OrderedDict()
    def add(name, d, v): lines.setdefault(name, collections.Counter())[d] += v
    for d in DAYS:
        add("OUR WALLET (MEASURED)", d, WAL.get(d, 0.0))
    for x in O:
        d = x["day"]
        if d not in DAYS: continue
        if x["bucket"] == "OWN": add(f"1. minus our fills on dumps 248 did not buy ({x['path']})", d, -x["net"])
        elif x["bucket"] == "NEAR": add("2. minus our fills near a 248 buy but on another trigger row", d, -x["net"])
        elif (x["slot"], x["idx"]) not in cl_o: add("5. shared events with 2 lots on one side: minus ours", d, -x["net"])
    for f in F:
        if f["day"] in DAYS: add(f"3. minus our failed buy attempts' fees+tips ({f['path']})", f["day"], f["cost"])
    lot_sum = collections.Counter(); fail_sum = collections.Counter()
    for x in O: lot_sum[x["day"]] += x["net"]
    for f in F: fail_sum[f["day"]] -= f["cost"]
    for d in DAYS: add("4. minus wallet residual (rent, ATA closes, other txs)", d, -(WAL.get(d, 0.0) - lot_sum[d] - fail_sum[d]))
    for r in clean:
        x = ok[r["o"]]; d = x["day"]
        if d not in DAYS: continue
        add("= our fills on the same dumps 248 bought (clean pairs)", d, 0.0)
        add("6a. replay residual ours (R1)", d, r["A"] - r["Ap"])
        add("6b. SIZE: our entry+exit at 248's size", d, r["S1"] - r["Ap"])
        add("6c. EXIT: our entry, 248's sell time(s)", d, r["S2"] - r["S1"])
        add("6d. ENTRY: 248's own landing (later, after more buys)", d, r["S3"] - r["S2"])
        add("6e. COSTS: 248's tx costs instead of ours", d, r["S4"] - r["S3"])
        add("6f. replay residual 248 (R2)", d, r["Hh"] - r["S4"])
        hd = hk[r["h"]]["day"]
        if hd != d:
            add("6g. day boundary (pair split across days)", d, -r["Hh"])
            if hd in DAYS: add("6g. day boundary (pair split across days)", hd, r["Hh"])
    for h in H:
        d = h["day"]
        if d not in DAYS: continue
        b = h["bucket"]
        if b == "S_FILL":
            if (h["slot"], h["idx"]) not in cl_h: add("5. shared events with 2 lots on one side: plus 248", d, h["net"])
            continue
        nm = {"S_NEAR": "7. 248 near our fill, other trigger row", "S_FAIL": "8. LIMIT/FILL: we fired and failed (guard), 248 filled",
              "NODUMP": "10. 248 lots with no >=5% dump within 2 slots (type we never trade)", "NOENG": "11. no engine of ours running (run gaps)",
              "NOCOV": "12. tape hour not usable"}.get(b)
        if nm is None: nm = "9. SELECTION refused: " + b[4:]
        add(nm, d, h["net"])
    for d in DAYS: add("= BOT 248 (MEASURED)", d, sum(h["net"] for h in H if h["day"] == d))
    out = []
    def P(*a):
        s = " ".join(str(x) for x in a); print(s); out.append(s)
    P("# Bridge: our wallet -> bot 248, SOL per day (D2 10-24 .. D5 10-27, days end 23:15 PKT)")
    P("| step | " + " | ".join(L.day_name(d)[:9] for d in DAYS) + " | mean/day |"); P("|---|" + "---|" * (len(DAYS) + 1))
    run = collections.Counter()
    import re
    def key(k):
        if k.startswith("OUR WALLET"): return (0, "")
        if k.startswith("= our fills"): return (5.5, "")
        if k.startswith("= BOT"): return (99, "")
        m = re.match(r"(\d+)([a-z]?)\.", k)
        return (int(m.group(1)), m.group(2) + k)
    order2 = sorted([k for k in lines if not k.startswith("= BOT")], key=key)
    for k in order2:
        v = lines[k]
        if k.startswith("="):
            P(f"| **{k}** | " + " | ".join(f"{run[d]:+.3f}" for d in DAYS) + f" | **{np.mean([run[d] for d in DAYS]):+.3f}** |"); continue
        for d in DAYS: run[d] += v[d]
        P(f"| {k} | " + " | ".join(f"{v[d]:+.3f}" for d in DAYS) + f" | {np.mean([v[d] for d in DAYS]):+.3f} |")
    tgt = lines["= BOT 248 (MEASURED)"]
    P(f"| **= BOT 248 (MEASURED)** | " + " | ".join(f"{tgt[d]:+.3f}" for d in DAYS) + f" | **{np.mean([tgt[d] for d in DAYS]):+.3f}** |")
    P("| check: running sum - 248 | " + " | ".join(f"{run[d] - tgt[d]:+.6f}" for d in DAYS) + " | |")
    open(f"{OUT}/v6_bridge.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
