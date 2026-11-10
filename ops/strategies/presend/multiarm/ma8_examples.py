#!/usr/bin/env python3
"""MULTIARM step 8: per-token reality checks. For a variant (rep 0) vs the base (R0): tokens where the variant traded MORE; 5 of them
(the 2 best and 2 worst by the extra trades' cash, and the one with the most extra trades), every window on the token in time order:
kind, n-th re-arm on the token, chained or not, armed (PKT), the dump that triggered it (% of supply, SOL, token age, seller), holders
left, filled or not, the exit and the cash (slip basis, mSOL); extra = not in the base. GMGN link per token.
usage: ma8_examples.py RUNDIR TAB OUT.md VARIANT [VARIANT ...] [--base R0]"""
import sys, json, pickle, collections, datetime
import numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/multiarm")
import ma_lib as M


def pkt(t_ms): return (datetime.datetime.fromtimestamp(t_ms / 1e3, datetime.UTC) + datetime.timedelta(hours=5)).strftime("%m-%d %H:%M:%S")


def kstr(k): return tuple(k) if isinstance(k, (list, tuple)) else (k,)


def main(rundir, tab, outp, variants, base="R0"):
    tape = M.Tape(tab)
    B = pickle.load(open(f"{rundir}/{base}__0.pkl", "rb"))["rows"]
    bk = {kstr(r["key"]): r for r in B}
    lines = []
    for v in variants:
        try: A = pickle.load(open(f"{rundir}/{v}__0.pkl", "rb"))["rows"]
        except FileNotFoundError: continue
        by = collections.defaultdict(list)
        for r in A: by[r["mint"]].append(r)
        cand = []
        for m, rows in by.items():
            ex = [r for r in rows if kstr(r["key"]) not in bk and r["filled"]]
            if not ex: continue
            cand.append((m, sum(r["cash"] for r in ex), len(ex)))
        if not cand: continue
        cand.sort(key=lambda x: x[1])
        pick = []
        for x in cand[-2:][::-1] + cand[:2] + sorted(cand, key=lambda x: -x[2])[:3]:
            if x[0] not in [p[0] for p in pick]: pick.append(x)
            if len(pick) >= 5: break
        lines.append(f"\n#### {v}: {len(cand)} tokens with extra trades (rep 0); 5 shown\n")
        for m, cs, n in pick:
            rows = sorted(by[m], key=lambda r: r["t_arm"])
            tl = tape.tok(m)
            lines.append(f"- **{m[:8]}…** https://gmgn.ai/sol/token/{m} — extra trades {n}, their cash {cs * 1e3:+.1f} mSOL")
            for r in rows:
                k = kstr(r["key"]); extra = k not in bk
                trig = ""
                if r["kind"] == "rearm" and len(k) == 4 and k[1] != "chain":
                    s, i, j = k[1], k[2], k[3]
                    q = next((q for q in range(tl.n) if (tl.s[q], tl.i[q], tl.j[q]) == (s, i, j)), None)
                    if q is not None:
                        trig = f"dump {tl.tok[q] / 1e13:.1f}% / {tl.sol[q] / 1e9:.2f} SOL by {tape.ids[int(tl.user[q])][:6]}, age {int(tl.s[q] - tl.s0)} slots"
                elif r["kind"] == "rearm": trig = "chained after our sell"
                else: trig = "T2 whale buy"
                res = "no fill"
                if r["filled"]:
                    res = f"FILL, exit {r['why']}, {r['cash'] * 1e3:+.1f} mSOL (-20%: {r['cash_cut'] * 1e3:+.1f})"
                elif r["fails"]: res = f"no fill ({r['fails']} failed tries, {r['cash'] * 1e3:+.2f} mSOL)"
                hold = "" if r["n_hold"] is None else ", holders left " + str(r["n_hold"])
                nth = (" #" + str(r["nth"])) if r["kind"] == "rearm" else ""
                lines.append(f"  - {pkt(r['t_arm'])} {r['kind']}{nth}{' EXTRA' if extra else ''}: {trig}{hold} -> {res} (ended {r['end_why']})")
    open(outp, "w").write("\n".join(lines) + "\n")
    print("\n".join(lines)[:8000])


if __name__ == "__main__":
    a = sys.argv[1:]
    base = "R0"
    if "--base" in a: k = a.index("--base"); base = a[k + 1]; del a[k:k + 2]
    main(a[0], a[1], a[2], a[3:], base)
