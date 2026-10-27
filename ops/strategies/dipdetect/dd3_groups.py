#!/usr/bin/env python3
# What the non-qualifying dumps look like: every dump of the universe "taken alone" (no engine limits), near leaders (FRA or AMS),
# 35 ms landing, 0.55 SOL, P&L per attempt incl. fixed costs (fill -0.0051, blocked buy -0.0005). Groups by envelope status / each
# envelope criterion / seller / time / crowding. MEASURED replay numbers.
import numpy as np
import dd_lib as L
EXS = [("1.3s/SL10", L.E_13), ("4s/SL20", L.E_4S), ("0.85s", L.EXI["c4_tpnone_slnone"]), ("2s/SL10", L.EXI["c9_tpnone_sl10"]), ("8s/SL30", L.EXI["c38_tpnone_sl30"])]
def per_att(d, m, lat=0):
    st = d["st"][m, lat]; ok = st == 0; fl = st == 1
    res = []
    for _, e in EXS:
        p = np.where(ok, d["pnl"][m, lat, e] - L.FIX, np.where(fl, -L.FAIL, 0.0))
        res.append(p[st != 2].mean() if (st != 2).any() else np.nan)
    return (st != 2).sum(), ok.sum() / max(1, (st != 2).sum()), res
def show(name, D, mk):
    cells = []
    for day in ("R2", "R3", "R1", "R4"):
        d = D[day]; m = mk(d) & (d["near_f"] | d["near_a"])
        n, fr, res = per_att(d, m)
        cells.append(f"{n:6d} {100 * fr:3.0f}% " + " ".join(f"{1000 * x:+6.1f}" for x in res[:2]))
    print(f"{name:42s} | " + " | ".join(cells))
if __name__ == "__main__":
    D = {day: L.load(day) for day in ("R1", "R2", "R3", "R4")}
    print("per-attempt P&L in mSOL (1.3s/SL10, 4s/SL20), n attempts, fill rate @35ms; near leaders; columns R2 | R3 | R1 | R4")
    f = L.feat
    sc = lambda d: np.isfinite(d["f1"])
    G = [
        ("ALL dumps (drop>=2%)", lambda d: np.ones(len(d["k"]), bool)),
        ("env & IMIT1 >= top2", lambda d: sc(d) & (d["f1"] >= L.THR["top2"])),
        ("env & IMIT1 top4..top2", lambda d: sc(d) & (d["f1"] >= L.THR["top4"]) & (d["f1"] < L.THR["top2"])),
        ("env & IMIT1 top8..top4", lambda d: sc(d) & (d["f1"] >= L.THR["top8"]) & (d["f1"] < L.THR["top4"])),
        ("env & IMIT1 -1..top8", lambda d: sc(d) & (d["f1"] >= -1) & (d["f1"] < L.THR["top8"])),
        ("env & IMIT1 < -1", lambda d: sc(d) & (d["f1"] < -1)),
        ("env (mine) & unscored", lambda d: d["env"] & ~sc(d)),
        ("OUT of env", lambda d: ~d["env"] & ~sc(d)),
        (" out: only age > 343 s", lambda d: ~sc(d) & (f(d, "age_s") > 343.67) & (f(d, "drop_pct") >= 4.65) & (f(d, "since_buy_s") <= 3.869) & (f(d, "sol") >= 1.08)),
        (" out: only drop 2-4.65%", lambda d: ~sc(d) & (f(d, "age_s") <= 343.67) & (f(d, "drop_pct") < 4.65) & (f(d, "since_buy_s") <= 3.869) & (f(d, "sol") >= 1.08)),
        (" out: only since_buy > 3.87 s", lambda d: ~sc(d) & (f(d, "age_s") <= 343.67) & (f(d, "drop_pct") >= 4.65) & (f(d, "since_buy_s") > 3.869) & (f(d, "sol") >= 1.08)),
        (" out: only sell < 1.08", lambda d: ~sc(d) & (f(d, "age_s") <= 343.67) & (f(d, "drop_pct") >= 4.65) & (f(d, "since_buy_s") <= 3.869) & (f(d, "sol") < 1.08)),
        (" out: age 343-900 s, drop>=4.65", lambda d: (f(d, "age_s") > 343.67) & (f(d, "age_s") <= 900) & (f(d, "drop_pct") >= 4.65)),
        (" out: age > 900 s, drop>=4.65", lambda d: (f(d, "age_s") > 900) & (f(d, "drop_pct") >= 4.65)),
        ("drop >= 15%", lambda d: f(d, "drop_pct") >= 15),
        ("drop 10-15%", lambda d: (f(d, "drop_pct") >= 10) & (f(d, "drop_pct") < 15)),
        ("drop 6-10%", lambda d: (f(d, "drop_pct") >= 6) & (f(d, "drop_pct") < 10)),
        ("drop 4.65-6%", lambda d: (f(d, "drop_pct") >= 4.65) & (f(d, "drop_pct") < 6)),
        ("drop 2-4.65%", lambda d: (f(d, "drop_pct") < 4.65)),
        ("age <= 10 s", lambda d: f(d, "age_s") <= 10),
        ("age 10-60 s", lambda d: (f(d, "age_s") > 10) & (f(d, "age_s") <= 60)),
        ("age 60-343 s", lambda d: (f(d, "age_s") > 60) & (f(d, "age_s") <= 343.67)),
        ("seller creator", lambda d: d["wt"] == 1),
        ("seller insider(create-slot)", lambda d: d["wt"] == 2),
        ("seller fresh", lambda d: d["wt"] == 3),
        ("seller bot(R2 list)", lambda d: d["wt"] == 4),
        ("seller family F1-F10", lambda d: d["wt"] >= 11),
        ("seller is pro (cohort/dip bots)", lambda d: f(d, "s_is_pro") == 1),
        ("dev-list token", lambda d: f(d, "dev_tok") == 1),
        ("env & dev-list token", lambda d: d["env"] & (f(d, "dev_tok") == 1)),
    ]
    for nm, mk in G: show(nm, D, mk)
    print("\nby hour PKT, env & IMIT1 >= top4 vs env & IMIT1 < top8 (per-attempt mSOL 1.3s/SL10, all days pooled)")
    for h in range(24):
        a = []; b = []
        for day in ("R1", "R2", "R3", "R4"):
            d = D[day]; nr = (d["near_f"] | d["near_a"]) & (d["hour"] == h)
            for lst, m in ((a, sc(d) & (d["f1"] >= L.THR["top4"])), (b, sc(d) & (d["f1"] < L.THR["top8"]))):
                mm = m & nr; st = d["st"][mm, 0]
                lst += list(np.where(st == 0, d["pnl"][mm, 0, L.E_13] - L.FIX, np.where(st == 1, -L.FAIL, 0.0))[st != 2])
        print(f"  {h:02d}h top4 n {len(a):4d} {1000 * np.mean(a) if a else 0:+6.1f} | below top8 n {len(b):5d} {1000 * np.mean(b) if b else 0:+6.1f}")
