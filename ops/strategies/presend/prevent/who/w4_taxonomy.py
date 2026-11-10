#!/usr/bin/env python3
"""WHO step 4 [MEASURED]: who sold inside our hold, by role at arm time; big losses (P&L < -0.05 SOL raw) vs other fills.
Out: taxonomy.json + printed tables"""
import pickle, json, collections
import numpy as np

D = "/home/it/sniper-data/prevent/who"
ROLES = ["trigger", "creator", "holder6", "holder3", "bundle", "holder<3", "new_window", "new_hold"]


def grp(p):
    return "big_loss" if p < -0.05 else ("loss" if p < 0 else "win")


def main():
    W = pickle.load(open(f"{D}/windows.pkl", "rb")); F = pickle.load(open(f"{D}/feats.pkl", "rb"))
    fl = [(w, f) for w, f in zip(W, F) if w["mode"] == "live" and w.get("filled") and "sellers" in f]
    out = {}
    # T1: in-hold sell SOL by role per group
    t1 = collections.defaultdict(lambda: collections.defaultdict(float)); nfills = collections.Counter(); pnl = collections.defaultdict(float)
    botsol = collections.defaultdict(float)
    for w, f in fl:
        g = grp(w["pnl"]); nfills[g] += 1; pnl[g] += w["pnl"]
        for u, x in f["sellers"].items():
            t1[g][x["role"]] += x["sol"]
            if x["bot"]: botsol[g] += x["sol"]
    print("T1 in-hold sell SOL by role at arm (share of the group's in-hold sell SOL)")
    print("group     fills  pnl     sellSOL/fill " + " ".join(f"{r:>10s}" for r in ROLES) + "   knownbot")
    for g in ("big_loss", "loss", "win"):
        tot = sum(t1[g].values())
        print(f"{g:9s} {nfills[g]:5d} {pnl[g]:7.2f} {tot / max(nfills[g], 1):8.2f}     " + " ".join(f"{t1[g][r] / tot * 100:9.1f}%" for r in ROLES) + f"   {botsol[g] / tot * 100:6.1f}%")
    out["t1"] = {g: {"fills": nfills[g], "pnl": pnl[g], "sell_sol": dict(t1[g]), "bot_sol": botsol[g]} for g in t1}
    # T2: big losses by main seller (largest in-hold seller) role; loss SOL; visibility
    t2 = collections.defaultdict(lambda: [0, 0.0]); vis = collections.defaultdict(lambda: [0, 0.0]); clus = collections.defaultdict(lambda: [0, 0.0])
    t2w = collections.defaultdict(lambda: [0, 0.0])
    rows = []
    for w, f in fl:
        s = f["sellers"]
        if not s: main_r, mx = "none", None
        else:
            u = max(s, key=lambda k: s[k]["sol"]); mx = s[u]; main_r = mx["role"]
        tgt = t2 if w["pnl"] < -0.05 else (t2w if w["pnl"] > 0 else None)
        if tgt is not None:
            tgt[main_r][0] += 1; tgt[main_r][1] += w["pnl"]
        if w["pnl"] < -0.05:
            v = "none" if mx is None else ("held>=6%" if mx["pct_arm"] >= 6 else ("held3-6%" if mx["pct_arm"] >= 3 else ("held<3%" if mx["pct_arm"] > 0 else "not holding")))
            vis[v][0] += 1; vis[v][1] += w["pnl"]
            c = "none" if mx is None else ("same-slot cluster" if mx["cluster"] > 0 else "no cluster")
            clus[c][0] += 1; clus[c][1] += w["pnl"]
            rows.append({"run": w["run"], "kind": w["kind"], "mint": w["mint"], "pnl": w["pnl"], "t": w["fill_t"],
                         "sellers": sorted([(u, round(x["sol"], 2), x["role"], round(x["pct_arm"], 1), x["bot"], x["cluster"]) for u, x in s.items()], key=lambda z: -z[1])[:6]})
    print("\nT2 main in-hold seller (largest) role: big losses vs winners")
    print("role         bigloss_n  bigloss_SOL   win_n  win_SOL")
    for r in ROLES + ["none"]:
        print(f"{r:12s} {t2[r][0]:9d} {t2[r][1]:11.2f} {t2w[r][0]:7d} {t2w[r][1]:8.2f}")
    print("\nT3 visibility at arm of the main seller (big losses)")
    for k, v in vis.items(): print(f"  {k:12s} n={v[0]:4d} SOL={v[1]:7.2f}")
    print("T4 main seller first-bought in the same slot as >=1 other holder >=1% at arm (big losses)")
    for k, v in clus.items(): print(f"  {k:18s} n={v[0]:4d} SOL={v[1]:7.2f}")
    out["t2_bigloss"] = {k: v for k, v in t2.items()}; out["t2_win"] = {k: v for k, v in t2w.items()}
    out["t3_vis"] = dict(vis); out["t4_cluster"] = dict(clus)
    # T5: any visible other holder >=3% at arm (besides the trigger): rate of big losses / pnl
    t5 = collections.defaultdict(lambda: [0, 0.0, 0])
    for w, f in fl:
        oth = [p for u, p in f["hold"].items() if u != w["wallet"] and p >= 3]
        k = f"{w['kind']}:other3={min(len(oth), 2)}"
        t5[k][0] += 1; t5[k][1] += w["pnl"] * 0.696 / (w["spend"] / 1e9); t5[k][2] += w["pnl"] < -0.05
    print("\nT5 fills by # other holders >=3% at arm (pnl @0.696)")
    for k in sorted(t5): print(f"  {k:22s} fills={t5[k][0]:5d} pnl={t5[k][1]:7.2f} bigloss={t5[k][2]}")
    out["t5"] = dict(t5)
    # who are the repeated big-loss sellers (>= 1 SOL in hold)?
    rep = collections.defaultdict(lambda: [0, 0.0, set(), collections.Counter()])
    for w, f in fl:
        if w["pnl"] >= -0.05: continue
        for u, x in f["sellers"].items():
            if x["sol"] >= 1:
                rep[u][0] += 1; rep[u][1] += w["pnl"]; rep[u][2].add(w["run"]); rep[u][3][x["role"]] += 1
    print("\nT6 wallets that sold >= 1 SOL into >= 2 big losses")
    for u, v in sorted(rep.items(), key=lambda z: z[1][1]):
        if v[0] >= 2: print(f"  {u[:8]} n={v[0]} lossSOL={v[1]:.2f} runs={sorted(v[2])} roles={dict(v[3])}")
    out["rows"] = rows
    json.dump(out, open(f"{D}/taxonomy.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
