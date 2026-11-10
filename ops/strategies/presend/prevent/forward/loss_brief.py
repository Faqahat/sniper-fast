#!/usr/bin/env python3
"""LOSS BRIEF for one live position (owner 10-30 ~09:05 PKT: "with every big loss (more than 0.04) send me: would it have been caught by
any filter"). Read-only on a local copy of the run's records. For the mint's LAST realized position (or every one with --all):
kind (T2 / re-arm), P&L, exit, token age, the trigger (whale or re-arm dump + holders), what the LIVE filters saw (10-sec skip buyers,
deeper limit: drop used / other holder / depth) and what the LOG-ONLY rules say (bad creator via the ledger seed + this run's fills
before it, the safe sell timer's would-block with each holder's hazard, the holder clock), then who sold inside our hold.
dip34/35: the arm record's log-only fields (eqgrp, f3 fresh, q4 wh_l10) and the presend_live_fam record (fam %, hit) are printed when
present and join the "WOULD HAVE BLOCKED IT" list as "(log)" entries (eqgrp flag, fresh >= 35%, fam hit).
dip36: FP-NOBOT (presend_live_fpnb): the score at the arm and at the send that decided the fill (stage "fill"), its threshold and
would_block; a would_block at the fill joins the list as "fpnb (log)".
usage: loss_brief.py RUN.jsonl MINT_PREFIX [--all] [--seed gcr_seed.json]"""
import sys, json, collections, os

path, pre = sys.argv[1], sys.argv[2]
seed_p = sys.argv[sys.argv.index("--seed") + 1] if "--seed" in sys.argv else "/home/it/sniper-data/prevent/forward/gcr_seed.json"
led = collections.defaultdict(lambda: [0, 0.0])
if os.path.exists(seed_p):
    for c, d in json.load(open(seed_p)).items(): led[c] = [d["n"], d["sum"]]
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
arm, fill, close, tape, out, famr = {}, {}, {}, collections.defaultdict(list), [], {}
fpnb = collections.defaultdict(dict)   # dip36: (w, mint) -> {"arm": rec, "fill": the first fill's rec}
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
    elif e == "presend_live_fam": famr[k] = d
    elif e == "presend_live_fpnb" and d.get("stage") in ("arm", "fill"): fpnb[k].setdefault(d["stage"], d)
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
    # LOG (dip34): equal-size holder group, fresh holders (f3), QUIET4 (q4) on the arm record
    eq = a.get("eqgrp")
    if eq is not None:
        lines.append(f"  equal-size group (log): {eq.get('n', 0)} holders" + (f" ~{eq.get('pct', 0):.2f}% each (sum {eq.get('sum', 0):.1f}%)" if eq.get("n") else "")
                     + " -> " + ("FLAGGED" if eq.get("flag") else "no"))
        if eq.get("flag"): caught.append("eqgrp flag (log)")
    f3 = a.get("f3")
    if f3 is not None:
        fr = f3.get("fresh") or 0
        lines.append(f"  fresh holders (log): {fr:.1f}% in {f3.get('fresh_n')} wallets, whale dumps {f3.get('wh_dumps')}, QUIET3-A {f3.get('q3a')} -> "
                     + ("FLAGGED (fresh >= 35%)" if fr >= 35 else "no"))
        if fr >= 35: caught.append("fresh>=35 (log)")
    q4 = a.get("q4")
    if q4 is not None:
        lines.append(f"  QUIET4 (log): whale's last dumps wh_l10 {q4.get('wh_l10')} [n, mean followers], repeat hold-sellers {q4.get('hs_n', 0)}, whale unfollowed 1 h {q4.get('wh_unf1h')}")
    # LOG (dip35): the bundle family (create-slot owners + transfer recipients) from the holders read at the arm
    fm = famr.get(k)
    if fm is not None:
        if fm.get("err"): lines.append(f"  bundle family (log): no read ({fm['err']})")
        else:
            lines.append(f"  bundle family (log): fam {fm.get('fam', 0):.1f}% (create-slot {fm.get('cs_pct', 0):.1f}%, recipients {fm.get('recv_n')} / {fm.get('recv_pct', 0):.1f}%, "
                         f"{fm.get('n_holders')} holders, hist {fm.get('hist')}, read {(fm.get('read_slot') or 0) - (fm.get('arm_slot') or 0)} slots after the arm) -> "
                         + ("FLAGGED (>= %.1f%%)" % fm.get("thr", 26.825) if fm.get("hit") else "no"))
            if fm.get("hit"): caught.append("fam hit (log)")
    # LOG (dip36): FP-NOBOT (no follower bot within 2 slots), at the arm and at the send that decided the fill
    fp = fpnb.get(k) or {}
    if fp:
        def fps(r):
            if not r or r.get("score") is None: return "n/a" + (f" ({r.get('nc')})" if r and r.get("nc") else "")
            return (f"{r['score']:.3f} vs {r.get('thr', 0):.3f}" + ("" if r.get("covered", True) else f" [not covered: {r.get('nc')}]")
                    + ("" if r.get("warm", True) else " [warm-up]") + (" -> WOULD BLOCK" if r.get("block") else " -> pass"))
        fl = fp.get("fill")
        lines.append(f"  no-bot filter FP-NOBOT (log): arm {fps(fp.get('arm'))} | deciding send (slot {fl.get('slot') if fl else '?'}) {fps(fl)}"
                     + (f" | whale history {fl.get('hist_h')} h" if fl else "")
                     + (f" | live gate withheld {fl['withheld']} sends of this window first" if fl and fl.get("withheld") else ""))
        if fl and fl.get("block"): caught.append("fpnb (log)")
        s2 = (fl or {}).get("skip2")
        if s2:
            lines.append(f"  skip2 per-send (log): score {s2.get('score', 0):.3f} vs {s2.get('thr', 0):.3f} (without failed txs {s2.get('score_nf', 0):.3f})"
                         + (" -> WOULD SKIP" if s2.get("skip") else " -> pass"))
            if s2.get("skip"): caught.append("skip2 (log)")
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
