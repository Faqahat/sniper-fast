#!/usr/bin/env python3
# PRE-SEND V2: append the FRESH-HOURS check (r5_eval.json, built after every choice was made) to V2_OPTIONS.md. Append-only.
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import v2data as V
R = json.load(open(f"{V.OUT}/r5_eval.json"))
w = V.WIN["R5"]
h = (V.pk(w[1]) - V.pk(w[0])) / 3600
rows = [("B6_k8_0.55", "B6: whale ≥ 6%, 8/slot, 0.55"), ("A6_k4_0.55", "A6: whale ≥ 6%, 4/slot, 0.55"), ("C6_k8_1.0", "C6: whale ≥ 6%, 8/slot, 1.0"),
        ("D6_k12_1.0", "D6: whale ≥ 6%, 12/slot, 1.0"), ("B6_k8_0.55_pess", "B6, pessimistic landing"), ("A6_k4_0.55_pess", "A6, pessimistic landing"),
        ("B_k8_0.55", "B: whale ≥ 5%, 8/slot, 0.55"), ("A_k4_0.55", "A: whale ≥ 5%, 4/slot, 0.55"), ("P1_as_run_0.2_k4", "probe 1 as run (0.2 SOL)")]
L = [f"\n## Fresh hours check (auto-appended by `v2/r5_append.py`)",
     f"- **R5:** {w[0]} → {w[1]} PKT ({h:.1f} h). The tape was built after every choice above was made, so no number here was used to choose anything.",
     "- Same engine and real costs as the test days. Each line: SOL in R5, per 24 h, fills, net per fill, then the clock hours.", ""]
for k, nm in rows:
    r = R.get(k)
    if not r: continue
    hrs = " / ".join(f"{x:+.2f}" for x in r["hourly"])
    L.append(f"- {nm}: **{r['pnl']:+.3f} SOL** ({r['per24']:+.1f}/24h), {r['fills']} fills, net {r['per_fill']:+.4f}/fill; hours {hrs}")
b6 = R.get("B6_k8_0.55", {}); a6 = R.get("A6_k4_0.55", {})
L.append("")
L.append(f"- Reading: B6 {'held up' if b6.get('pnl', 0) > 0 else 'did NOT hold up'} on the fresh hours "
         f"({b6.get('per24', 0):+.1f}/24h vs +7.8 on test), and A6 {'held up' if a6.get('pnl', 0) > 0 else 'did NOT hold up'} "
         f"({a6.get('per24', 0):+.1f}/24h vs +5.4).")
L.append("  - Only a few hours, and test hours were negative 13–20% of the time, so this is a sanity check, not proof.")
open("/home/moiz/sniper/ops/strategies/presend/V2_OPTIONS.md", "a").write("\n".join(L) + "\n")
print("\n".join(L))
