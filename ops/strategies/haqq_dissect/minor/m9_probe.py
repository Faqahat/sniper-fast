#!/usr/bin/env python3
"""MINOR step 9 (read-only): what are the 0.01-SOL lots for? (codes 249, 252 and 244's 0.01 tier). MEASURED tests:
 (1) warm-up / scout: after a probe on a mint, how often does a NON-probe haqq lot (any code) follow on that mint within 2 / 10 / 60 s,
     vs after a non-probe first lot; and does the probe's own result (value at its sell) change that rate (= price discovery)?
 (2) paper trading: per-SOL return of the same code at 0.01 vs at full size, per day (same entry/exit logic?);
     timeline of sizes per code and day (a strategy tested at 0.01 and then scaled up, or switched off).
 (3) landing test: paths/tips/CU of probes vs full-size lots of the same code.
Out: minor/m9.txt"""
import pickle, sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos")
from plib import Out, boot_mean
OUT = "/home/moiz/sniper-data/haqq_dissect/minor"


def main():
    P = Out(f"{OUT}/m9.txt")
    lots = pickle.load(open(f"{OUT}/m2_lots.pkl", "rb"))
    bym = collections.defaultdict(list)
    for l in lots: bym[l["ms"]].append(l)
    for v in bym.values(): v.sort(key=lambda l: l["cc"])
    def follow(l, win_ms):
        for x in bym[l["ms"]]:
            if x["cc"] <= l["cc"]: continue
            if x["cc"] - l["cc"] > win_ms: break
            if x["spend"] > 0.05: return x
        return None
    P("# What are the 0.01-SOL lots for? (MEASURED)")
    groups = {"249 @0.01": lambda l: l["code"] == 249 and l["spend"] <= 0.011, "249 full": lambda l: l["code"] == 249 and l["spend"] > 0.05,
              "252 @0.01": lambda l: l["code"] == 252 and l["spend"] <= 0.011, "244 @0.01": lambda l: l["code"] == 244 and l["spend"] <= 0.011,
              "244 @0.247": lambda l: l["code"] == 244 and abs(l["spend"] - 0.247) < 0.002, "247 all": lambda l: l["code"] == 247,
              "248 all": lambda l: l["code"] == 248}
    P("\n## (1) does a full-size haqq lot follow on the same mint after the lot? (scout / warm-up test)")
    P("| group | lots | first haqq lot on mint | full-size lot follows <= 2 s | <= 10 s | <= 60 s | follow rate if this lot's value at sell > 0 | if <= 0 |")
    P("|---|---|---|---|---|---|---|---|")
    for g, f in groups.items():
        v = [l for l in lots if f(l) and not l["mayhem"]]
        first = [l for l in v if bym[l["ms"]][0] is l]
        r = {w: np.mean([follow(l, w) is not None for l in v]) for w in (2000, 10000, 60000)}
        win = [l for l in v if (l["out"] - l["cost"]) > 0]; los = [l for l in v if (l["out"] - l["cost"]) <= 0]
        fw = np.mean([follow(l, 60000) is not None for l in win]) if win else 0; fl = np.mean([follow(l, 60000) is not None for l in los]) if los else 0
        P(f"| {g} | {len(v):,} | {100 * len(first) / max(len(v), 1):.0f}% | {100 * r[2000]:.0f}% | {100 * r[10000]:.0f}% | {100 * r[60000]:.0f}% | {100 * fw:.0f}% ({len(win)}) | {100 * fl:.0f}% ({len(los)}) |")
    P("\n## (2) same code, per-SOL return (gross of tx cost, code-matched) at 0.01 vs full size, per day")
    for c in (249, 252, 244, 251):
        v = [l for l in lots if l["code"] == c and not l["mayhem"]]
        for d in range(7):
            w = [l for l in v if l["day"] == d]
            if not w: continue
            sm = [l for l in w if l["spend"] <= 0.011]; bg = [l for l in w if l["spend"] > 0.05]
            def rr(x):
                if not x: return "-"
                g = [(l["out"] + l.get("mark", 0) - l["cost"]) / l["cost"] for l in x]
                lo, hi = boot_mean(g)
                return f"{100 * np.mean(g):+.1f}% [{100 * lo:+.1f}..{100 * hi:+.1f}] n {len(x)}"
            P(f"- {c} D{d}: 0.01 lots {rr(sm)} | full-size {rr(bg)}")
    P("\n## (3) tx shape of probes vs full-size lots (buy tx)")
    for g, f in groups.items():
        v = [l for l in lots if f(l)]
        pa = collections.Counter(l["path"] for l in v)
        P(f"- {g}: paths " + ", ".join(f"{k} {100 * n / len(v):.0f}%" for k, n in pa.most_common(4)) + f"; tip p50 {np.median([l['tip'] or 0 for l in v]) / 1e6:.3f} mSOL; fee p50 {np.median([l['fee'] or 0 for l in v]) / 1e6:.3f}; CU price p50 {np.median([l['cup'] or 0 for l in v]):.0f}")
    P("\n## (4) 0.01 lots of 244: same entry features as its 0.247 lots? (median)")
    for g in ("244 @0.01", "244 @0.247"):
        v = [l for l in lots if groups[g](l) and l["ctx"]]
        cx = [l["ctx"] for l in v]
        P(f"- {g}: d_drop {np.median([x.get('d_drop') or 0 for x in cx]):.3f}, age {np.median([l['age'] for l in v if l['age'] is not None]):.0f} slots, curve {np.median([l['vsol_pre'] for l in v]):.1f}, "
          f"bo3 {np.median([x.get('bo3') or 0 for x in cx]):.2f}, ch10 {np.median([x.get('ch10') or 0 for x in cx]):.2f}, others holding {100 * np.mean([bool(l['others']) for l in v]):.0f}%, "
          f"partial {100 * np.mean([l['f1'] is not None and 0.45 <= l['f1'] <= 0.55 for l in v]):.0f}%, hold p50 {np.median([l['hold_sl'] for l in v if l['hold_sl'] is not None]):.0f} slots")
    P.save()


if __name__ == "__main__":
    main()
