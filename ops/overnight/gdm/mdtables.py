#!/usr/bin/env python3
# markdown tables for RESULTS.md from gsum JSON outputs (fin_*.json)
import sys, json
VN = {"slip": "slip", "proafter_slip": "pro-after", "nosnip": "no-snipers"}
def full(fn, lists, ex, title):
    S = json.load(open(fn)); out = [f"**{title}** (exit {ex}; PRO = pro costs; w/o top5, halves at PRO costs)", "",
        "| List | Landing | Variant | Fills/tries | Today SOL | PRO SOL | Median/fill | Win | PRO w/o top 5 | PRO halves |", "|---|---|---|---|---|---|---|---|---|---|"]
    for nm, lab in lists:
        for L in ("75", "45", "30"):
            for v in ("slip", "proafter_slip", "nosnip"):
                r = next(x for x in S[nm] if x["L"] == L and x["var"] == v and x["ex"] == ex)
                out.append(f"| {lab} | {L} ms | {VN[v]} | {r['fills']}/{r['att']} | {r['cur']:+.2f} | **{r['pro']:+.2f}** | {r['med']:+.3f} | {r['win']:.0%} | {r['wo5']:+.2f} | {r['h1']:+.2f} / {r['h2']:+.2f} |")
    return "\n".join(out)
def compact(fn, lists, title):
    S = json.load(open(fn)); out = [f"**{title}** (PRO-cost totals, SOL; fills/tries at the 45 ms landing)", "",
        "| List | Tries | 75 ms 8 s: slip / pro-after / no-snipers | 45 ms 8 s | 30 ms 8 s | 75 ms 10 s | 45 ms 10 s | 30 ms 10 s |", "|---|---|---|---|---|---|---|---|"]
    for nm, lab in lists:
        cells = []
        for ex in ("t8", "t10"):
            for L in ("75", "45", "30"):
                r = {x["var"]: x for x in S[nm] if x["L"] == L and x["ex"] == ex}
                cells.append(f"{r['slip']['pro']:+.2f} / {r['proafter_slip']['pro']:+.2f} / {r['nosnip']['pro']:+.2f}")
        r45 = next(x for x in S[nm] if x["L"] == "45" and x["ex"] == "t8" and x["var"] == "slip")
        out.append(f"| {lab} | {r45['fills']}/{r45['att']} | " + " | ".join(cells) + " |")
    return "\n".join(out)
if __name__ == "__main__":
    L2 = [("FINAL2_off", "FINAL-2 (offline picks)"), ("GDM_bag", "GDM alone (frozen recipe, trained R1)"), ("UNION_bag", "UNION FINAL-2 + GDM")]
    L1 = [("FINAL2_off", "FINAL-2 (offline; in-sample < 14:58)"), ("GDM_bag", "GDM alone (frozen recipe, trained R2)"), ("UNION_bag", "UNION FINAL-2 + GDM")]
    parts = {
      "R2c": compact("fin_R2.json", [("FINAL2_off", "FINAL-2 offline"), ("GDM_valpick", "GDM, validation-chosen (yc 2%)"), ("GDM_bag", "GDM bag (yc 3%)"), ("GDM_bag_R1snp", "GDM bag, R1-only sniper list"),
                                      ("UNION_valpick", "UNION F2 + GDM val-chosen"), ("UNION_bag", "UNION F2 + GDM bag"), ("UNION_bag_R1snp", "UNION F2 + GDM bag, R1-only snipers"), ("F2_and_GDMtop50", "FINAL-2 minus GDM bottom half")],
                     "R2 = 10-22 22:09 -> 10-23 05:34 PKT, fully out of sample for every list"),
      "R2l": compact("fin_R2live.json", [("FINAL2_live", "FINAL-2 LIVE picks"), ("FINAL2_off", "FINAL-2 offline"), ("GDM_bag", "GDM bag"), ("UNION_live_bag", "UNION F2 live + GDM bag")],
                     "R2 live-pick window 23:36 -> 05:34 PKT"),
      "R1c": compact("fin_R1.json", [("FINAL2_off", "FINAL-2 offline (in-sample < 14:58)"), ("GDM_valpick", "GDM, validation-chosen (E3 7.5%)"), ("GDM_bag", "GDM bag (yc 3%)"),
                                      ("UNION_valpick", "UNION F2 + GDM val-chosen"), ("UNION_bag", "UNION F2 + GDM bag"), ("F2_and_GDMtop50", "FINAL-2 minus GDM bottom half")],
                     "R1 = 10-22 03:07 -> 18:00 PKT (models trained on R2)"),
      "R1h": compact("fin_R1h.json", [("FINAL2_off", "FINAL-2 offline"), ("GDM_valpick", "GDM val-chosen"), ("GDM_bag", "GDM bag"), ("UNION_valpick", "UNION val-chosen"), ("UNION_bag", "UNION bag")],
                     "R1 14:58 -> 18:00 PKT only (FINAL-2's early-stop holdout: the only R1 slice unseen by its training)"),
      "R2f": full("fin_R2.json", L2, "t8", "R2 full detail"), "R1f": full("fin_R1.json", L1, "t8", "R1 full detail")}
    json.dump(parts, open("md_parts.json", "w")); print("\n\n".join(parts.values()))
