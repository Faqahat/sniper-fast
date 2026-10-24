#!/usr/bin/env python3
# matrix view of the v2 forward replay: selection x exit rule -> total PnL (SOL) per landing/sell-delay/size config
import sys, json, gzip, collections, statistics, datetime
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
F = sys.argv[1] if len(sys.argv) > 1 else "fwd2.jsonl.gz"
rows = []
with gzip.open(F, "rt") as f:
    meta = json.loads(f.readline()); NAMES = meta["rules"]
    for l in f: rows.append(json.loads(l))
rows.sort(key=lambda r: r["bt"] or 0)
LS = json.load(open("lists_cut1709.json"))
CF = ["L0", "L25", "L35", "L45", "L60", "L75", "L90", "L35_d1", "L60_d1", "L35_drop", "L60_drop", "L35_B025", "L35_B1"]
def wf_select(cfg, rule, K=3, THR=0.02, GAP=60):
    i = NAMES.index(rule); past = collections.defaultdict(list); pend = []; sel = set()
    for r in rows:
        if cfg not in r["cfg"]: continue
        t = r["bt"] or 0
        while pend and pend[0][0] <= t: _, d, v = pend.pop(0); past[d].append(v)
        h = past[r["signer"]]
        if len(h) >= K and statistics.mean(h) >= THR: sel.add(r["mint"])
        pend.append((t + GAP, r["signer"], r["cfg"][cfg]["pnl"][i] / 0.5)); pend.sort(key=lambda x: x[0])
    return sel
SEL = {
    "ALL": lambda r: True,
    "COPY-LIST union(9Sh2fd,DGmspi) pre-window": lambda r: any(LS.get(w, {}).get(r["signer"], 0) >= 1 for w in ("9Sh2fd", "DGmspi")),
    "COPY-LIST 3 wallets": lambda r: any(LS.get(w, {}).get(r["signer"], 0) >= 1 for w in ("9Sh2fd", "DGmspi", "D24ipY")),
    "ORACLE their attempts (9Sh2fd|DGmspi)": lambda r: "9Sh2fd" in r["att"] or "DGmspi" in r["att"],
}
wf = wf_select("L35", "eos1")
SEL["WALKFWD own-history (L35 eos1, K3, >=2%)"] = lambda r: r["mint"] in wf
SEL["COPY-LIST union OR WALKFWD"] = lambda r: SEL["COPY-LIST union(9Sh2fd,DGmspi) pre-window"](r) or r["mint"] in wf
RULESHOW = ["eos0", "eos1", "eos2", "hold1s", "fsell_any_c2", "fsell_any", "tp1.1_sl0.9_c2", "tp1.1_eos2", "tp1.15_sl0.8_c20", "hold5s", "hold10s", "hold30s",
            "pA_50eos1_50@2x_c30", "pB_50fsell_50trail1.3_.2_c60", "pC_33@1.2_33@1.5_34@2_sl.85_c30", "pD_25at_slots1_3_6_10", "pH_77@1.3_rest_trail.3_c300",
            "pI_50eos0_50hold10s", "pJ_50eos1_25@1.5_25trail.25_c60", "pK_20pct_each_new_high_10pct", "lad_33@1.3_33@1.6_trail", "twap_10pct_every2s_20s", "trail1.5_0.25"]
for sn, sf in SEL.items():
    R = [r for r in rows if sf(r)]
    print(f"\n== {sn}: {len(R)} launches   (cells = total SOL at 0.5 SOL/trade unless B; n per cell ~ launches)")
    print(f"   {'rule':34}" + "".join(f"{c:>9}" for c in CF))
    for rn in RULESHOW:
        i = NAMES.index(rn); cells = []
        for c in CF:
            v = [r["cfg"][c]["pnl"][i] for r in R if c in r["cfg"]]
            cells.append(f"{sum(v):+9.2f}" if v else f"{'-':>9}")
        print(f"   {rn:34}" + "".join(cells))
