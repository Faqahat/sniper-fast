#!/usr/bin/env python3
# e01: the dump table for the 24 h window (10-24 09:45 -> 10-25 09:45 PKT) from the two builds (A = run_20261023_1426 tokens
# created before the NEW run started 19:25:11 PKT; B = run_20261024_1425). Envelope, M2 score (engine bundle), IMIT1 top4 flag,
# slot leader client group and near flags (FRA / AMS / AMS no-BAM), from the epoch schedules 1066 + 1067.
# -> /home/moiz/sniper-data/exits/dumps.npz
import sys, os, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import exit_lib as E
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect")
import dd_lib as DL

W0, W1 = E.pk("10-24 09:45"), E.pk("10-25 09:45")
NEW_START = 1792851911

def load(tag):
    z = np.load(f"{E.DATA}/{tag}/dd1_{tag}.npz"); d = {k: z[k] for k in ("k", "tok", "s", "arr", "bt", "F", "X", "f1", "f1src", "uid")}
    bt = d["bt"].astype(np.int64); ok = bt > 0
    if (~ok).any():
        a = np.polyfit(d["s"][ok].astype(float), bt[ok].astype(float), 1); bt = np.where(ok, bt, np.round(np.polyval(a, d["s"].astype(float))).astype(np.int64))
    d["t"] = bt
    meta = json.load(open(f"{E.DATA}/{tag}/day_{tag}_meta.json"))["meta"]
    cbt = np.array([(m.get("cbt") or 0) for m in meta], np.int64)
    d["cbt"] = cbt[d["tok"]]
    return d

if __name__ == "__main__":
    out = {}
    parts = []
    for ti, tag in enumerate(("A", "B")):
        d = load(tag)
        m = (d["t"] >= W0) & (d["t"] < W1)
        if tag == "A": m &= (d["cbt"] > 0) & (d["cbt"] < NEW_START)
        else: m &= d["cbt"] >= NEW_START - 5
        d = {k: v[m] for k, v in d.items()}
        d["tag"] = np.full(m.sum(), ti, np.int8)
        parts.append(d)
        print(f"{tag}: {m.sum()} dump rows in the window")
    D = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    Xall = np.concatenate([D["F"], D["X"], D["f1"][:, None]], 1).astype(np.float32)
    f = lambda k: Xall[:, DL.FNI[k]]
    env = (f("age_s") <= 343.67) & (f("drop_pct") >= 4.65) & (f("since_buy_s") <= 3.869) & (f("sol") >= 1.08)
    P = E.m2_scores(Xall)
    LD = E.Leaders()
    g, nf, na, nb, known = LD.arrays(D["s"])
    pick_m2 = env & (P >= E.M2_THR)
    pick_im = env & np.isfinite(D["f1"]) & (D["f1"] >= E.IMIT_THR4)
    o = np.argsort(D["arr"] + D["tag"] * 0, kind="stable")
    res = dict(tag=D["tag"], k=D["k"], tok=D["tok"], s=D["s"], arr=D["arr"], t=D["t"], uid=D["uid"], env=env, m2=P.astype(np.float32), f1=D["f1"],
               f1src=D["f1src"], pick_m2=pick_m2, pick_im=pick_im, grp=g, near_f=nf, near_a=na, near_nb=nb, lead_known=known,
               drop=f("drop_pct"), sol=f("sol"), age_s=f("age_s"), curve=f("curve"), since_buy=f("since_buy_s"), coh_n=f("coh_n"),
               hour=((D["t"] + 5 * 3600) // 3600) % 24)
    res = {k: v[o] for k, v in res.items()}
    np.savez(f"{E.DATA}/dumps.npz", **res)
    n = len(res["t"])
    print(f"window {E.pkt(W0)} -> {E.pkt(W1)} PKT: {n} dumps, env {res['env'].sum()}, leader known {res['lead_known'].mean():.3f}")
    for nm in ("pick_m2", "pick_im"):
        p = res[nm]
        print(f"  {nm}: {p.sum()} ({p.sum() / 24:.0f}/h); near FRA {(p & res['near_f']).sum()}, near AMS {(p & res['near_a']).sum()}, "
              f"near AMS no-BAM {(p & res['near_nb']).sum()}; both pick sets {(res['pick_m2'] & res['pick_im']).sum()}")
    im_cov = np.isfinite(res["f1"]) & res["env"]
    print(f"  IMIT1 score coverage of env dumps: {im_cov.sum()} / {res['env'].sum()} ({100 * im_cov.sum() / max(1, res['env'].sum()):.0f}%)")
    for h0 in range(0, 24, 2):
        hh = (res["hour"] >= h0) & (res["hour"] < h0 + 2)
        print(f"   PKT {h0:02d}-{h0 + 2:02d}: env {(res['env'] & hh).sum():6d}  M2 picks {(res['pick_m2'] & hh).sum():5d}  IMIT1 picks {(res['pick_im'] & hh).sum():5d}"
              f"  IMIT1 coverage {100 * (im_cov & hh).sum() / max(1, (res['env'] & hh).sum()):3.0f}%")
    gname = {v: k for k, v in E.GI.items()}
    for nm in ("pick_m2",):
        p = res[nm] & (res["near_f"] | res["near_a"])
        print("  near M2 picks by leader group:", {gname[x]: int((res["grp"][p] == x).sum()) for x in np.unique(res["grp"][p])})
