#!/usr/bin/env python3
# Pooled TEST (R3 + R4 + R1, chosen on R2) per key: SOL per 24 h, hour-block bootstrap 90% interval, without the top 1% of
# fills, share of positive hours, falling knife, send load (attempts per second: mean and the 99th percentile over 1-second
# bins; concurrent armed windows: mean / max). Cheap fees, k per queue row.
import sys, json, collections
import numpy as np
import ps5_lib as E, ps7_test as T
best = json.load(open(f"{E.C.OUT}/ps6_select.json"))["best"]
keys = sys.argv[1:] or ["T2|c", "T2|r20", "T2|r4", "T2|b", "T2|a", "T1t|r4", "T1t|c", "T3|r4", "T3|a"]
acc = {k: dict(hour=collections.defaultdict(float), pn=[], knife=[], h=0.0, rate=[], conc=[], fills=0, att=0.0) for k in keys}
for day in ("R3", "R4", "R1"):
    D = E.load(day); h = D["hours"]
    for key in keys:
        b = best[key]; o = T.one(D, b); a = acc[key]; a["h"] += h; a["fills"] += o["fill"]; a["att"] += o["att"]
        hr = lambda t: ((np.asarray(t) + 5 * 3600) // 3600).astype(np.int64)
        for t, v in zip(hr(o["acc_t"]).tolist(), o["acc_pnl"].tolist()): a["hour"][(day, t)] += v
        for t, sl in zip(hr(o["arm_t"]).tolist(), o["arm_slots"].tolist()): a["hour"][(day, t)] -= o["k"] * sl * o["fee_att"]
        for t in hr(o["acc_t"]).tolist(): a["hour"][(day, t)] += o["fee_att"]
        a["pn"] += o["acc_pnl"].tolist(); ci = T.capi(b["ex"]); a["knife"] += (o["acc_pmin"][:, ci] <= 0.90).tolist()
        # send load: armed intervals -> attempts per 1 s bin
        st = D["w_start"][o["arm_rows"]]; en = st + o["arm_slots"] * E.SMS
        if len(st):
            t0 = st.min(); nb = int((en.max() - t0) // 1000) + 2; att = np.zeros(nb); conc = np.zeros(nb)
            for s_, e_ in zip(st.tolist(), en.tolist()):
                i0 = int((s_ - t0) // 1000); i1 = int((e_ - t0) // 1000)
                conc[i0:i1 + 1] += 1; att[i0:i1 + 1] += o["k"] * (e_ - s_) / E.SMS / (i1 - i0 + 1)
            a["rate"].append((att.mean(), np.percentile(att, 99), att.max())); a["conc"].append((conc.mean(), conc.max()))
    del D
out = {}
print("POOLED TEST R3 + R4 + R1 (39.3 h), configs chosen on R2 only; cheap fees; SOL per 24 h")
for key in keys:
    a = acc[key]; v = np.array(list(a["hour"].values())); tot = v.sum(); h = a["h"]
    rng = np.random.default_rng(11); bs = v[rng.integers(0, len(v), (4000, len(v)))].sum(1)
    pn = np.sort(np.array(a["pn"])); ntop = max(1, int(round(0.01 * len(pn)))); notop = tot - pn[-ntop:].sum()
    r = np.array(a["rate"]); c = np.array(a["conc"])
    out[key] = dict(per24=tot / h * 24, boot90=[float(np.percentile(bs, 5) / h * 24), float(np.percentile(bs, 95) / h * 24)], no_top1_24=notop / h * 24,
                    pos_hours=float((v > 0).mean()), knife=float(np.mean(a["knife"])) if a["knife"] else None, fills_24=a["fills"] / h * 24,
                    att_per_fill=a["att"] / max(a["fills"], 1), att_s_mean=float(r[:, 0].mean()), att_s_p99=float(r[:, 1].max()), att_s_max=float(r[:, 2].max()),
                    conc_mean=float(c[:, 0].mean()), conc_max=float(c[:, 1].max()))
    o = out[key]
    print(f"  {key:7s} {o['per24']:+6.2f}/24h  boot90 [{o['boot90'][0]:+6.2f}, {o['boot90'][1]:+6.2f}]  w/o top1% {o['no_top1_24']:+6.2f}  +hours {100 * o['pos_hours']:3.0f}%  "
          f"knife {100 * o['knife']:3.0f}%  fills {o['fills_24']:5.0f}/24h  att/fill {o['att_per_fill']:5.0f}  sends {o['att_s_mean']:5.1f}/s (p99 {o['att_s_p99']:5.0f}, max {o['att_s_max']:5.0f})  "
          f"armed windows mean {o['conc_mean']:.2f} max {o['conc_max']:.0f}")
json.dump(out, open(f"{E.C.OUT}/ps7d_pooled.json", "w"), indent=1)
