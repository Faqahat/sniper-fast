#!/usr/bin/env python3
"""MINOR step 2 (read-only): descriptive profile of every haqq bot code (MEASURED from m1.pkl + pos/p1.pkl context).
Out: minor/m2.txt"""
import pickle, sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
from plib import load, Out, boot_sum
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/minor"
CODES = (244, 226, 231, 234, 249, 251, 252, 247, 248)


def q(v, ps=(10, 25, 50, 75, 90)):
    v = np.asarray([x for x in v if x is not None], float)
    return " / ".join(f"{np.percentile(v, p):.3g}" for p in ps) if len(v) else "-"


def share(v, cond):
    v = list(v); return f"{100 * sum(1 for x in v if cond(x)) / max(len(v), 1):.0f}%"


def main():
    P = Out(f"{OUT}/m2.txt")
    Z = pickle.load(open(f"{OUT}/m1.pkl", "rb")); lots = Z["lots"]; fails = Z["fails"]
    B, LO, T = load()
    for l in lots:
        b = B[l["b"]] if l["b"] is not None else {}
        l["ctx"] = b
        pl = LO[l["plot"]] if l["plot"] is not None else None
        l["net"] = pl["cnet"] if pl is not None else (l["out"] + l.get("mark", 0) - l["cost"] - 0.00079)
        l["day"] = L.day_of(l["bt"])
        l["hold_sl"] = max(s[0] for s in l["sells"]) if l["sells"] else None
        l["hold_ms"] = max(s[1] for s in l["sells"]) if l["sells"] else None
        l["first_sl"] = l["sells"][0][0] if l["sells"] else None
        l["nsell"] = len(l["sells"])
        l["f1"] = l["sells"][0][2] if l["sells"] else None
        l["spend"] = round(l["cost"] / 1.0125, 3)
    pickle.dump(lots, open(f"{OUT}/m2_lots.pkl", "wb"))
    fc = collections.Counter((f["code"], f["kind"]) for f in fails if f["kind"] == "buy")
    P("# haqq bots: profile per code (MEASURED, exit tape 10-22 03:07 -> 10-28 01:12 PKT; code-matched lots)")
    for c in CODES:
        v = [l for l in lots if l["code"] == c and not l["mayhem"]]
        vm = [l for l in lots if l["code"] == c and l["mayhem"]]
        P(f"\n## code {c}: {len(v):,} lots (+{len(vm)} on mayhem tokens), failed buys {fc.get((c, 'buy'), 0):,} "
          f"(fail rate {100 * fc.get((c, 'buy'), 0) / max(len(v) + len(vm) + fc.get((c, 'buy'), 0), 1):.0f}%)")
        net = [l["net"] for l in v]
        lo, hi = boot_sum(net)
        P(f"- net {sum(net):+.2f} SOL [{lo:+.2f}..{hi:+.2f}], mSOL/lot {1000 * np.mean(net):+.2f}, win {share(net, lambda x: x > 0)}; per day D0..D6: "
          + " ".join(f"{sum(l['net'] for l in v if l['day'] == d):+.2f}({sum(1 for l in v if l['day'] == d)})" for d in range(7)))
        sp = collections.Counter(l["spend"] for l in v)
        P(f"- spend (SOL) top: " + ", ".join(f"{k}:{n}" for k, n in sp.most_common(8)))
        cul = collections.Counter(l["cul"] for l in v); cup = collections.Counter(l["cup"] for l in v)
        P(f"- buy CU limit top: " + ", ".join(f"{k}:{n}" for k, n in cul.most_common(4)) + " | CU price top: " + ", ".join(f"{k}:{n}" for k, n in cup.most_common(5)))
        pa = collections.Counter(l["path"] for l in v)
        P(f"- buy path: " + ", ".join(f"{k}:{n}" for k, n in pa.most_common(5)) + f" | tip mSOL p50 {np.median([l['tip'] or 0 for l in v]) / 1e6:.3f}, fee p50 {np.median([l['fee'] or 0 for l in v]) / 1e6:.3f}")
        cx = [l["ctx"] for l in v if l["ctx"]]
        P(f"- trigger: biggest outside sell drop in 5 slots before (d_drop) p10..p90 {q([x.get('d_drop') for x in cx])}; >=5% & <=2 slots {share(cx, lambda x: (x.get('d_drop') or 0) >= .05 and (x.get('d_slots') if x.get('d_slots') is not None else 99) <= 2)}; "
          f">=10% {share(cx, lambda x: (x.get('d_drop') or 0) >= .10)}; d_slots p10..p90 {q([x.get('d_slots') for x in cx])}")
        dt = collections.Counter(x.get("d_type") for x in cx)
        P(f"- dumper type: " + ", ".join(f"{k}:{100 * n / len(cx):.0f}%" for k, n in dt.most_common()))
        P(f"- age slots p10..p90 {q([l['age'] for l in v])}; age<=5 {share(v, lambda l: l['age'] is not None and l['age'] <= 5)}; curve SOL before p10..p90 {q([l['vsol_pre'] for l in v])}; "
          f"curve<=30.6 {share(v, lambda l: l['vsol_pre'] <= 30.6)}; curve<=32 {share(v, lambda l: l['vsol_pre'] <= 32)}")
        P(f"- outside buy SOL last 3 slots p10..p90 {q([x.get('bo3') for x in cx])}; sell SOL {q([x.get('so3') for x in cx])}; dd10 {q([x.get('dd10') for x in cx])}; ch10 {q([x.get('ch10') for x in cx])}")
        P(f"- new trip {share(cx, lambda x: x.get('new_trip'))}; other codes open at buy: none {share(v, lambda l: not l['others'])}, "
          + ", ".join(f"{oc}:{share(v, lambda l, oc=oc: oc in l['others'])}" for oc in (247, 248, 244, 226, 234)))
        pc = collections.Counter(l["po_code"] for l in v if l["po_ms"] is not None and l["po_ms"] <= 2000)
        P(f"- an other-code haqq buy on the mint within 2 s before: {share(v, lambda l: l['po_ms'] is not None and l['po_ms'] <= 2000)} (by code: "
          + ", ".join(f"{k}:{n}" for k, n in pc.most_common(5)) + f"); within 500 ms {share(v, lambda l: l['po_ms'] is not None and l['po_ms'] <= 500)}; po_ms p10..p90 (when <=10 s) {q([l['po_ms'] for l in v if l['po_ms'] is not None and l['po_ms'] <= 10000])}")
        P(f"- same code bought this mint before: {share(v, lambda l: l['ps_ms'] is not None)}; same code lot still open {share(v, lambda l: l['same_open'] > 0)}")
        P(f"- exit: sells/lot p50 {np.median([l['nsell'] for l in v]):.0f}, 1 sell {share(v, lambda l: l['nsell'] == 1)}, 2 sells {share(v, lambda l: l['nsell'] == 2)}, 3+ {share(v, lambda l: l['nsell'] >= 3)}, "
          f"never sold {share(v, lambda l: l['nsell'] == 0)}; first-sell fraction ~0.5 {share(v, lambda l: l['f1'] is not None and 0.45 <= l['f1'] <= 0.55)}")
        P(f"- hold (last sell) slots p10..p90 {q([l['hold_sl'] for l in v])}; first sell slots {q([l['first_sl'] for l in v])}; hold s {q([l['hold_ms'] / 1000 if l['hold_ms'] else None for l in v])}")
        hs = collections.Counter(l["first_sl"] for l in v if l["first_sl"] is not None)
        P(f"- first-sell slot offset top: " + ", ".join(f"{k}:{n}" for k, n in hs.most_common(12)))
        sc = collections.Counter(s[5] for l in v for s in l["sells"])
        P(f"- sell codes on these lots: " + ", ".join(f"{k}:{n}" for k, n in sc.most_common(4)) + f"; fallback (other-code sell) {sum(1 for l in v for s in l['sells'] if s[6] == 1)}")
    P.save()


if __name__ == "__main__":
    main()
