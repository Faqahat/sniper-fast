#!/usr/bin/env python3
"""VM1 independent check, step 8: all tables (claim reproduction, live-reality matrix, halves, hours, null check,
head-to-head). Reads dumps.npz, expect_0.3.npz, h2h_picks.npz, livecal bias. Prints and writes report.json."""
import json, sys
import numpy as np
import core, sim

Z = np.load(core.D + "/dumps.npz")
X = np.load(core.D + "/expect_0.3.npz")
H = np.load(core.D + "/h2h_picks.npz")
M = core.Model()
EL = X["elig_idx"]                                  # eligible dumps (no hole, full history), index into Z
lab = Z["lab"][EL]; slot = Z["slot"][EL].astype(np.int64); mint = Z["mint"][EL]
near = {"all": np.ones(len(EL), bool), "FRA": Z["near_fra"][EL], "AMS": Z["near_ams"][EL]}
VM1 = Z["sm"][EL] >= M.cut; VM1p = Z["sp"][EL] >= M.cut
M2 = H["m2"][EL]; IM = H["imit"][EL]; COV = H["cov"][EL]
ROWS = ["Llive", "F40", "F80", "F150"]
E = {r: {k: X[f"{r}_{k}"] for k in ("p_fill", "e_pos", "e_neg", "p_spill")} for r in ROWS}
BIAS = {0.2: 0.00527, 0.35: 0.00316}               # livecal: sim (L-live) minus realized per fire, 370 fires r10+ (pre-registered rule C)
UNSEEN = ("U1", "U2", "U3", "U4")
holes = json.load(open(core.D + "/holes.json"))

def hours(mask_lab):
    """scored hours of a set of blocks: span of each block minus recording holes"""
    h = 0.0
    for L in mask_lab:
        s = slot[lab == L]
        if not len(s): continue
        lo, hi = s.min(), s.max(); n = hi - lo + 1
        for a, b in holes: n -= max(0, min(b, hi) - max(a, lo) + 1)
        h += n * core.SLOT_SEC / 3600
    return h

HRS = {L: hours([L]) for L in UNSEEN + ("T1", "T2")}

def run(pick, blocks, row="Llive", C=0.0045, R=0.0006, cut=0.2, max_open=1, lead="FRA", bias=False, busy=6):
    m = pick & np.isin(lab, blocks) & near[lead]
    idx = np.where(m)[0]
    took = sim.take(slot[idx], mint[idx], max_open, busy) if max_open else np.ones(len(idx), bool)
    t = idx[took]
    v = sim.value({k: a[t] for k, a in E[row].items()}, C, R, cut)
    if bias: v = v - BIAS[cut]
    hrs = sum(HRS[b] for b in blocks)
    return {"n": int(len(t)), "n_raw": int(m.sum()), "total": float(v.sum()), "per": float(v.mean()) if len(t) else 0.0,
            "day": float(v.sum() / hrs * 24) if hrs else 0.0, "ph": len(t) / hrs if hrs else 0.0, "fill": float(E[row]["p_fill"][t].mean()) if len(t) else 0.0,
            "idx": t, "v": v, "hrs": hrs}

def fmt(o):
    return f"{o['day']:+6.2f}/day ({o['per'] * 1e3:+6.2f} mSOL/trade, {o['ph']:4.1f} trades/h, fill {o['fill']:.2f})"

def main():
    out = {}
    print("hours:", {k: round(v, 2) for k, v in HRS.items()})
    # ---------------- 1. claim reproduction (the copy's rule, my data and my code) ----------------
    print("\n== 1. CLAIM reproduction: +80 txs never leaving the dump's slot, exit end of dump slot + 6, 0.3 SOL, cut 20% on positive NET, no position limit, all leaders")
    cf = X["CLAIM_fill"]; cp = X["CLAIM_pnl"]
    fwd = (lab == "U4") & (slot <= 461_092_744)            # the copy's 5.3 h forward window (its rows_fwd.json end)
    for name, blk in (("copy's forward window (U4 first 5.3 h)", fwd), ("U4 all", lab == "U4"), ("U3", lab == "U3"), ("U2", lab == "U2"), ("U1", lab == "U1"),
                      ("ALL unseen U1-U4", np.isin(lab, UNSEEN)), ("training T1+T2 (in-sample)", np.isin(lab, ("T1", "T2")))):
        for C, Rv in ((0.002, 0.0005), (0.0006, 0.00015)):
            v = sim.claim_value(cf, cp, C, Rv)
            pv = VM1 & blk; av = blk
            hrs = (slot[blk].max() - slot[blk].min()) * core.SLOT_SEC / 3600 if name.startswith("copy") else (sum(HRS[b] for b in UNSEEN) if name.startswith("ALL") else
                   (HRS["T1"] + HRS["T2"] if name.startswith("train") else HRS[name.split()[0]]))
            print(f"  {name:40s} cost {C * 1e3:.1f}: VM1 picks {pv.sum():4d} ({pv.sum() / hrs:4.1f}/h) per trade {v[pv].mean() * 1e3:+6.2f} mSOL = {v[pv].sum() / hrs * 24:+6.2f} SOL/day"
                  f" | all dumps per trade {v[av].mean() * 1e3:+6.2f} | VM1 fill {cf[pv].mean():.2f}")
    out["claim"] = True
    # ---------------- 2. live-reality matrix ----------------
    print("\n== 2. LIVE-REALITY rows, all unseen hours U1-U4, VM1 picks (model features), 1 open position, FRA near leaders, cut 20%")
    print("   landing \\ cost   " + "   ".join(f"{c:>34s}" for c in ("4.5 mSOL (pre-reg)", "3.8 mSOL (measured r10+)", "2.0 mSOL", "0.6 mSOL")))
    for row in ROWS:
        cells = []
        for C in (0.0045, 0.0038, 0.002, 0.0006):
            o = run(VM1, UNSEEN, row, C, 0.0006 * C / 0.0045 if C != 0.0038 else 0.0006, 0.2)
            cells.append(fmt(o))
        print(f"   {row:8s} " + " | ".join(cells))
    print("   same, after the pre-registered live-calibration correction (-5.27 mSOL per trade):")
    for row in ROWS:
        cells = []
        for C in (0.0045, 0.0038, 0.002, 0.0006):
            o = run(VM1, UNSEEN, row, C, 0.0006 * C / 0.0045 if C != 0.0038 else 0.0006, 0.2, bias=True)
            cells.append(f"{o['day']:+6.2f}/day ({o['per'] * 1e3:+6.2f})")
        print(f"   {row:8s} " + " | ".join(cells))
    print("\n== 3. leaders x positions x follower cut (L-live, 4.5 mSOL, all unseen)")
    for lead in ("all", "FRA", "AMS"):
        for mo in (1, 3):
            for cut in (0.2, 0.35):
                o = run(VM1, UNSEEN, "Llive", 0.0045, 0.0006, cut, mo, lead); ob = run(VM1, UNSEEN, "Llive", 0.0045, 0.0006, cut, mo, lead, bias=True)
                print(f"   leaders {lead:3s} open {mo} cut {int(cut * 100)}%: {fmt(o)} | corrected {ob['day']:+6.2f}/day ({ob['per'] * 1e3:+.2f})")
    # ---------------- 4. per block, halves, hours (MAIN ROW) ----------------
    print("\n== 4. MAIN ROW (L-live, 4.5 mSOL, revert 0.6, cut 20%, 1 open, FRA near) per block / halves / hours")
    for L in UNSEEN + ("T1", "T2"):
        o = run(VM1, (L,)); ob = run(VM1, (L,), bias=True)
        print(f"   {L:3s} {HRS[L]:5.1f} h: total {o['total']:+.3f} SOL {fmt(o)} | corrected {ob['total']:+.3f} ({ob['day']:+.2f}/day)")
    o = run(VM1, UNSEEN); t = o["idx"]; v = o["v"]; med = np.median(slot[t])
    h1 = v[slot[t] < med].sum(); h2 = v[slot[t] >= med].sum()
    ob = run(VM1, UNSEEN, bias=True); vb = ob["v"]
    print(f"   pooled unseen: total {o['total']:+.3f} SOL ({o['n']} trades) | halves (split at median trade slot) {h1:+.3f} / {h2:+.3f} | corrected halves {vb[slot[t] < med].sum():+.3f} / {vb[slot[t] >= med].sum():+.3f}")
    hb = (slot[t] - slot[t].min()) // int(3600 / core.SLOT_SEC)
    hourly = np.bincount(hb, weights=v); hn = np.bincount(hb)
    print(f"   per-hour (hours with >=1 trade): {int((hn > 0).sum())} hours, positive {int(((hourly > 0) & (hn > 0)).sum())}, median hour {np.median(hourly[hn > 0]):+.4f} SOL")
    out["main"] = {"total": o["total"], "day": o["day"], "per": o["per"], "n": o["n"], "h1": float(h1), "h2": float(h2)}
    # ---------------- 5. null check ----------------
    print("\n== 5. NULL check (main row): 200 random pick sets, same picks per hour, same envelope/leaders/hours, same simulator + position limit")
    rng = np.random.default_rng(42)
    base = np.isin(lab, UNSEEN) & near["FRA"]
    hrb = (slot - slot.min()) // int(3600 / core.SLOT_SEC)
    vm_idx = np.where(VM1 & base)[0]; need = np.bincount(hrb[vm_idx], minlength=hrb.max() + 1)
    pool = {h: np.where(base & (hrb == h))[0] for h in np.where(need > 0)[0]}
    vm_per = o["per"]; nulls = []
    for _ in range(200):
        pk = np.zeros(len(EL), bool)
        for h, c in enumerate(need):
            if c: pk[rng.choice(pool[h], min(c, len(pool[h])), replace=False)] = True
        nulls.append(run(pk, UNSEEN)["per"])
    nulls = np.array(nulls)
    allv = sim.value({k: a[base] for k, a in E["Llive"].items()}, 0.0045, 0.0006, 0.2)
    print(f"   VM1 per trade {vm_per * 1e3:+.2f} mSOL | random sets: median {np.median(nulls) * 1e3:+.2f}, 95th pct {np.percentile(nulls, 95) * 1e3:+.2f}, "
          f"VM1 beats {100 * (nulls < vm_per).mean():.1f}% | all-dumps baseline {allv.mean() * 1e3:+.2f} mSOL/trade ({base.sum()} dumps)")
    out["null"] = {"vm": vm_per, "p95": float(np.percentile(nulls, 95)), "beat": float((nulls < vm_per).mean()), "all": float(allv.mean())}
    # plain-reading features
    op = run(VM1p, UNSEEN)
    print(f"   VM1 on MY plain-reading features (ch15/ch60 vs the price at the window start): {fmt(op)} total {op['total']:+.3f}")
    # ---------------- 6. head-to-head ----------------
    print("\n== 6. HEAD-TO-HEAD on U3+U4 hours where M2 and IMIT1 are known (all three unseen), same simulator, MAIN ROW")
    for L in ("U3", "U4", "U3+U4"):
        bl = ("U3", "U4") if L == "U3+U4" else (L,)
        cov = COV & np.isin(lab, bl)
        hrs_cov = None
        line = []
        for name, pk in (("VM1", VM1), ("M2", M2), ("IMIT1", IM), ("VM1|M2", VM1 | M2)):
            o2 = run(pk & cov, bl); ob2 = run(pk & cov, bl, bias=True)
            line.append(f"{name} {o2['total']:+.3f} ({o2['n']} tr, {o2['per'] * 1e3:+.2f}/tr; corr {ob2['total']:+.3f})")
        print(f"   {L:6s} " + " | ".join(line))
    cov = COV & np.isin(lab, ("U3", "U4")) & near["FRA"]
    a, b, c = VM1 & cov, M2 & cov, IM & cov
    print(f"   overlap (FRA-near, covered): VM1 {a.sum()}, M2 {b.sum()}, IMIT1 {c.sum()}, VM1&M2 {(a & b).sum()}, VM1&IMIT1 {(a & c).sum()}, M2&IMIT1 {(b & c).sum()}")
    for name, pk in (("VM1 only (not M2)", a & ~b), ("M2 only (not VM1)", b & ~a), ("both", a & b)):
        o3 = run(pk, ("U3", "U4"), max_open=0)
        print(f"   {name:20s} n={o3['n']:4d} per trade {o3['per'] * 1e3:+.2f} mSOL (no position limit)")
    json.dump(out, open(core.D + "/report.json", "w"), default=float)

if __name__ == "__main__":
    main()
