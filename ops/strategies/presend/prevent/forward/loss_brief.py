#!/usr/bin/env python3
"""LOSS BRIEF for one live position (owner 10-30 ~09:05 PKT: "with every big loss (more than 0.04) send me: would it have been caught by
any filter"). Read-only on a local copy of the run's records. For the mint's LAST realized position (or every one with --all):
kind (T2 / re-arm), P&L, exit, token age, the trigger (whale or re-arm dump + holders), what the LIVE filters saw (10-sec skip buyers,
deeper limit: drop used / other holder / depth) and what the LOG-ONLY rules say (bad creator via the ledger seed + this run's fills
before it, the safe sell timer's would-block with each holder's hazard, the holder clock), then who sold inside our hold.
usage: loss_brief.py RUN.jsonl MINT_PREFIX [--all] [--seed gcr_seed.json]"""
import sys, json, collections, os

path, pre = sys.argv[1], sys.argv[2]
seed_p = sys.argv[sys.argv.index("--seed") + 1] if "--seed" in sys.argv else "/home/moiz/sniper-data/prevent/forward/gcr_seed.json"
led = collections.defaultdict(lambda: [0, 0.0])
if os.path.exists(seed_p):
    for c, d in json.load(open(seed_p)).items(): led[c] = [d["n"], d["sum"]]
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
arm, fill, close, tape, out = {}, {}, {}, collections.defaultdict(list), []
for line in open(path, errors="replace"):
    if '"ev":"presend_live_' not in line: continue
    d = json.loads(line); e = d["ev"]
    mint = d.get("mint") or (d.get("trig") or {}).get("mint") or ""
    k = (d.get("w"), mint)
    if e == "presend_live_arm":
        a = d.get("ann") or {}; c = a.get("creator")
        n, s = led[c] if c else (0, 0.0)
        arm[k] = (d, bool(c and a.get("cr_pct", 0) >= 3 and n >= 2 and s <= -0.05), (n, s))
    elif e == "presend_live_fill": fill.setdefault(k, d)
    elif e == "presend_live_close": close[k] = d
    elif e == "presend_live_tape": tape[mint].append(d)
    elif e == "presend_live_realized":
        a = arm.get(k)
        if a and (a[0].get("ann") or {}).get("creator") and (a[0].get("ann") or {}).get("cr_pct", 0) >= 3:
            c = a[0]["ann"]["creator"]; led[c][0] += 1; led[c][1] += d["pnl"] / 1e9
        if mint.startswith(pre): out.append((k, d["pnl"] / 1e9))
if not out: sys.exit(f"no realized position on {pre}")
for k, pnl in (out if "--all" in sys.argv else out[-1:]):
    a, gcr, (gn, gs) = arm.get(k, ({}, False, (0, 0.0)))
    f = fill.get(k, {}); c = close.get(k, {}); fa = f.get("ann") or {}; aa = a.get("ann") or {}
    kind = a.get("kind", "t2")
    if kind == "rearm":
        du = a.get("dump") or {}
        trig = f"re-arm after {du.get('seller','?')[:8]} sold {du.get('pct',0):.1f}% at token age {du.get('age_slots')} slots; holders " + ", ".join(f"{h['w'][:8]} {h['pct']:.1f}%" for h in a.get("holders") or [])
        age = du.get("age_slots")
    else:
        t = a.get("trig") or {}
        trig = f"whale {t.get('wallet','?')[:8]} bought {t.get('pct',0):.1f}% at token age {t.get('age_slots')} slots"
        age = t.get("age_slots")
    lines = [f"{k[1]} ({kind}) {pnl:+.4f} SOL, exit {c.get('exit_why')}, {trig}"]
    caught = []
    # LIVE: deeper limit
    deep = f.get("deep")
    lines.append(f"  deeper limit (live): other big holder at signing {fa.get('ob6', 0):.1f}%, dip {100*fa.get('depth', 0):.1f}% -> "
                 + ("the try already used the 0.85x limit (deep dip; it can't block deeper dips)" if deep else ("not applied (no other holder >= 6% at signing)" if fa.get('ob6', 0) < 6 else "applied")))
    # LIVE: 10-sec skip (T2 only)
    if kind == "t2": lines.append(f"  10-sec skip (live): {aa.get('nb50')} buyers in the last 50 slots -> {'would skip' if (aa.get('nb50') or 9) <= 1 else 'not a lone whale'}")
    # LOG: bad creator
    lines.append(f"  bad creator (log): creator {str(aa.get('creator'))[:8]} holds {aa.get('cr_pct', 0):.1f}%, its past fills {gn} / {gs:+.2f} -> {'FLAGGED' if gcr else 'no'}")
    if gcr: caught.append("bad creator (log)")
    # LOG: safe sell timer
    st = fa.get("st_block")
    hs = fa.get("holders") or []
    lines.append(f"  safe sell timer (log): " + ("FLAGGED" if st else "no") + " | holders at landing: " + ", ".join(
        f"{h['w'][:8]} {h['pct']:.1f}% age {h['age']} holds {h.get('n')} risk {h.get('risk')} hz3 {h.get('hz3', 0):.2f}" for h in hs[:4]))
    if st: caught.append("safe sell timer (log)")
    # LOG: holder clock (approx, same rule as filters_report.py)
    hc = [h for h in hs if h.get("pct", 0) >= 6 and h.get("n", 0) >= 5 and (h.get("h3") or 0) >= 0.3]
    lines.append("  holder clock (log): " + ("FLAGGED by " + ", ".join(f"{h['w'][:8]} {h['pct']:.1f}% h3 {h['h3']:.2f}" for h in hc) if hc else "no"))
    if hc: caught.append("holder clock (log)")
    # LOG: group risk (risky holders of any size, the safe timer's per-holder test, summed >= 6%)
    grp = [h for h in hs if (h.get("risk") or 0) >= 5 and (h.get("hz3") or 0) >= 0.3]
    gsum = sum(h.get("pct", 0) for h in grp)
    lines.append(f"  group risk (log): risky holders {', '.join(h['w'][:8] + ' ' + format(h['pct'], '.1f') + '%' for h in grp) or 'none'} = {gsum:.1f}% -> " + ("FLAGGED" if gsum >= 6.0 else "no"))
    if gsum >= 6.0: caught.append("group risk (log)")
    # who sold inside our hold
    sl = (c.get("sell_land") or [None])[0]
    holders = {h["w"] for h in hs}
    sold = collections.Counter()
    for x in tape.get(k[1], []):
        if x["user"] in OURS or x["buy"] or x["slot"] < f.get("slot", 0) or (sl and x["slot"] > sl): continue
        sold[x["user"]] += x["sol"] / 1e9
    lines.append("  sold into our hold: " + (", ".join(f"{u[:8]} {v:.2f} SOL{' (holder at landing)' if u in holders else ''}" for u, v in sold.most_common(4)) or "nobody (a flat or slow loss)"))
    lines.append("  " + ("WOULD HAVE BLOCKED IT: " if pnl > 0 else "CAUGHT BY: ") + (", ".join(caught) if caught else "none of the filters"))
    print("\n".join(lines))
