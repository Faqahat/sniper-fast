#!/usr/bin/env python3
"""dip47 GRPSIGN parity on a real run log (no engine replay needed for the members' balances):
signing-time group = the fill's ann.guard.set "sign_pct" (dip30 LANDING GUARD set: the SAME risky-holder test, >= 2%, risk >= 5, hz3 >= 0.3,
chosen by the main loop after the last trade before the try was signed, i.e. the SWin state the sender signed with; capped at the top
GRD_K = 4 risky holders) vs landing-time group = ann.grp_pct (up to 12 holders). Rows where the signing set is full (4) are a lower bound.
With dip47 running, presend_live_fill.grpsign.pct replaces the proxy (no cap) and the same report runs on it.
usage: parity_r82.py RUN.jsonl"""
import json, sys, math

def main(path):
    rows = []
    with open(path) as f:
        for l in f:
            if '"presend_live_fill"' not in l: continue
            r = json.loads(l)
            if r.get("ev") != "presend_live_fill": continue
            ann = r.get("ann") or {}
            if "grp_pct" not in ann: continue
            land = ann["grp_pct"] or 0.0
            if "grpsign" in r and r["grpsign"].get("pct") is not None:
                sign, src, full = r["grpsign"]["pct"], "grpsign", False
            else:
                st = ann.get("guard", {}).get("set", [])
                sign, src, full = sum(m["sign_pct"] for m in st), "guard_sign_pct", len(st) >= 4
            rows.append((r.get("kind", "t2"), land, sign, full, r["w"], src))
    n = len(rows)
    if n == 0: print("no fills with ann"); return
    xs = [r[2] for r in rows]; ys = [r[1] for r in rows]
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys)); sx = math.sqrt(sum((a - mx) ** 2 for a in xs)); sy = math.sqrt(sum((b - my) ** 2 for b in ys))
    corr = sxy / (sx * sy) if sx > 0 and sy > 0 else float("nan")
    def rep(sub, name):
        k = len(sub)
        if k == 0: print(f"{name}: none"); return
        ls = sum(1 for r in sub if r[1] >= 3 and r[2] < 3); sl = sum(1 for r in sub if r[2] >= 3 and r[1] < 3)
        both = sum(1 for r in sub if r[1] >= 3 and r[2] >= 3); eq = sum(1 for r in sub if abs(r[1] - r[2]) < 0.01)
        print(f"{name}: fills {k} | equal (±0.01) {eq} ({eq/k:.0%}) | both >=3 {both} | landing>=3 & signing<3: {ls} ({ls/k:.1%}) | signing>=3 & landing<3: {sl} ({sl/k:.1%})")
    print(f"{path}: {n} fills with the landing annotation; signing source: {rows[0][5]}; signing set full (cap 4, lower bound): {sum(r[3] for r in rows)}")
    print(f"correlation(signing, landing) = {corr:.3f}; mean signing {mx:.2f}% landing {my:.2f}%")
    rep(rows, "ALL"); rep([r for r in rows if r[0] == "t2"], "T2"); rep([r for r in rows if r[0] == "rearm"], "REARM")
    for r in rows:
        if (r[1] >= 3) != (r[2] >= 3): print(f"  disagree w{r[4]} {r[0]}: signing {r[2]:.2f}% landing {r[1]:.2f}%")

if __name__ == "__main__": main(sys.argv[1])
