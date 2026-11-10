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
dip37: the WHALE / DUMPER LOSS LEDGER verdict at the arm (the arm wallet's [n, sum] before this position): the engine's own wh_n / wh_sum /
wh_sum_hit / wh_mean_hit on the arm record when the ledger ran live, else replayed here from --whale-seed (a state file built BEFORE this run;
default none) plus this run's earlier positions, under --wh N:SOL (default 2:0.05; sum and mean both shown).
dip38 (log-only anti-bait, presend_live_insider / presend_live_shape): the launcher (create-tx payer, its holding / sold %), INSIDER (a >= 3% holder
or the whale funded by the launcher / creator: wallet, hop, chain walk), FAMILY (its chain holds a blocklisted wallet), the FAMILY LEDGER (the
launcher's INSIDER fills over 24 h) at the arm and at the fill (the deciding view), INSIDER again with the chains known at the realize, and the
SHAPE ledger (exact holder sizes); the fill's would-blocks join the list as "family ledger (log)", "insider flag (log)", "family chain (log)",
"shape ledger (log)".
dip38 PSM12-S1 (--presend-live-s1-log): the arm record's "s1" verdict (nd M2-scored dumps before the trigger, T2 age, the whale's / dumper's
REAL positions with us, cold = none) -> keep or WOULD SKIP (first failing reason: nd < 2, T2 age < 50, whale n >= 1 and sum <= -0.02, cold
n == 0 and nd < 8); an older run without "s1" is replayed from the arm's nd / age / wh_n / wh_sum (labelled "replayed"). A would-skip joins
the list as "S1 <reason> (log)" ("S1 <reason> (LIVE)" when the gate was live: then the arm was not skipped by the live parts).
usage: loss_brief.py RUN.jsonl MINT_PREFIX [--all] [--seed gcr_seed.json] [--whale-seed whale_state.json] [--wh 2:0.05]"""
import sys, json, collections, os

path, pre = sys.argv[1], sys.argv[2]
seed_p = sys.argv[sys.argv.index("--seed") + 1] if "--seed" in sys.argv else "/home/it/sniper-data/prevent/forward/gcr_seed.json"
led = collections.defaultdict(lambda: [0, 0.0])
if os.path.exists(seed_p):
    for c, d in json.load(open(seed_p)).items(): led[c] = [d["n"], d["sum"]]
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
# dip37 the whale / dumper ledger (wallet -> [n, sum lamports]) and its rule
wled = collections.defaultdict(lambda: [0, 0])
if "--whale-seed" in sys.argv:
    for w, v in json.load(open(sys.argv[sys.argv.index("--whale-seed") + 1]))["w"].items(): wled[w] = [v[0], v[1]]
WH_N, WH_S = (lambda x: (int(x[0]), float(x[1])))((sys.argv[sys.argv.index("--wh") + 1] if "--wh" in sys.argv else "2:0.05").split(":"))
warm = {}   # (w, mint) -> (wallet, n, sum lamports) before the position
arm, fill, close, tape, out, famr = {}, {}, {}, collections.defaultdict(list), [], {}
fpnb = collections.defaultdict(dict)   # dip36: (w, mint) -> {"arm": rec, "fill": the first fill's rec}
ins38 = collections.defaultdict(dict)  # dip38: (w, mint) -> {"arm" / "fill": the first rec, "realize": the last, "send_flags": n sends flagged}
shp38 = collections.defaultdict(dict)
for line in open(path, errors="replace"):
    if '"ev":"presend_live_' not in line: continue
    d = json.loads(line); e = d["ev"]
    mint = d.get("mint") or (d.get("trig") or {}).get("mint") or ""
    k = (d.get("w"), mint)
    if e == "presend_live_arm":
        a = d.get("ann") or {}; c = a.get("creator")
        n, s = led[c] if c else (0, 0.0)
        arm[k] = (d, bool(c and a.get("cr_pct", 0) >= 3 and n >= 2 and s <= -0.05), (n, s))
        ww = (d.get("trig") or {}).get("wallet") or (d.get("dump") or {}).get("seller")
        if ww: warm[k] = (ww, *wled[ww])
    elif e == "presend_live_fill": fill.setdefault(k, d)
    elif e == "presend_live_close": close[k] = d
    elif e == "presend_live_tape": tape[mint].append(d)
    elif e == "presend_live_fam": famr[k] = d
    elif e == "presend_live_fpnb" and d.get("stage") in ("arm", "fill"): fpnb[k].setdefault(d["stage"], d)
    elif e in ("presend_live_insider", "presend_live_shape"):
        m38 = ins38 if e == "presend_live_insider" else shp38
        st = d.get("stage")
        if st in ("arm", "fill"): m38[k].setdefault(st, d)
        elif st == "realize": m38[k]["realize"] = d
        elif st == "send":
            m38[k]["sends"] = m38[k].get("sends", 0) + 1
            if d.get("insider") or d.get("would"): m38[k]["send_flags"] = m38[k].get("send_flags", 0) + 1
    elif e == "presend_live_realized":
        a = arm.get(k)
        if a and (a[0].get("ann") or {}).get("creator") and (a[0].get("ann") or {}).get("cr_pct", 0) >= 3:
            c = a[0]["ann"]["creator"]; led[c][0] += 1; led[c][1] += d["pnl"] / 1e9
        if k in warm: wled[warm[k][0]][0] += 1; wled[warm[k][0]][1] += d["pnl"]
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
    # dip37 LIVE: the whale / dumper loss ledger at the arm (the engine's own view when it ran, else replayed here)
    if a.get("wh_n") is not None:
        lines.append(f"  whale ledger (live): {'dumper' if kind == 'rearm' else 'whale'} {str(a.get('wh_wallet'))[:8]} had {a['wh_n']} positions / {a.get('wh_sum', 0):+.3f} SOL "
                     f"-> sum rule {'HIT' if a.get('wh_sum_hit') else 'no'}, mean rule {'HIT' if a.get('wh_mean_hit') else 'no'} (armed: the live rule did not block)")
        if a.get("wh_sum_hit") or a.get("wh_mean_hit"): caught.append("whale ledger (other rule)")
    elif k in warm:
        ww, wn, ws = warm[k]
        sh, mh = wn >= WH_N and ws <= -WH_S * 1e9, wn >= max(WH_N, 1) and ws <= -WH_S * 1e9 * wn
        lines.append(f"  whale ledger (replayed {WH_N}:{WH_S}{', seed ' + os.path.basename(sys.argv[sys.argv.index('--whale-seed') + 1]) if '--whale-seed' in sys.argv else ', this run only'}): "
                     f"{'dumper' if kind == 'rearm' else 'whale'} {ww[:8]} had {wn} positions / {ws / 1e9:+.3f} SOL -> sum rule {'WOULD SKIP' if sh else 'no'}, mean rule {'WOULD SKIP' if mh else 'no'}")
        if sh: caught.append("whale ledger sum")
        elif mh: caught.append("whale ledger mean")
    # dip37 holder ledger (live / log mode): the arm record's first blocking holder (only present when one blocked: hl_would = log mode)
    if a.get("hl_wallet") is not None:
        lines.append(f"  holder ledger: holder {a['hl_wallet'][:8]} {a.get('hl_pct', 0):.1f}% had {a.get('hl_n')} positions / {a.get('hl_sum', 0):+.3f} SOL, no win -> "
                     + ("WOULD SKIP (log mode)" if a.get("hl_would") else "skip"))
        caught.append("holder ledger (log mode)")
    elif kind in ("t2", "rearm") and any(k in a for k in ("wh_n", "nd")):
        lines.append("  holder ledger: no blocking holder at the arm (or the ledger off)")
    # dip37 creator ledger at the arm (cr on the arm record)
    if a.get("cr"):
        cr = a["cr"]
        lines.append(f"  creator ledger: {cr.get('n')} positions / {cr.get('sum', 0):+.3f} SOL" + (f" -> would {cr['would']} (log)" if cr.get("would") else ""))
    # dip37 HYBRID-2 (log only): the arm rule on the arm record (nd M2-scored dumps before the trigger, m2max, T2 age >= 30)
    if a.get("h2_keep") is not None:
        lines.append(f"  HYBRID-2 (log): nd {a.get('nd')} m2max {a.get('m2max', -1):.3f} -> h2_keep {a['h2_keep']} (size {a.get('h2_size')} SOL)")
        if not a["h2_keep"]: caught.append("HYBRID-2 (log)")
    # dip38 PSM12-S1 (log only unless its gate was live): the engine's verdict on the arm, else replayed from the arm's nd / age / wh_n / wh_sum
    s1 = a.get("s1")
    if s1 is None and a.get("nd") is not None and a.get("wh_n") is not None:
        nd_, age_, wn_, ws_ = a["nd"], (age or 0), a["wh_n"] - a.get("wh_pn", 0), a.get("wh_sum", 0) - a.get("wh_ps", 0)
        why_ = ("nd" if nd_ < 2 else "age" if kind != "rearm" and age_ < 50 else "whale" if wn_ >= 1 and ws_ <= -0.02 + 1e-12 else "cold" if wn_ == 0 and nd_ < 8 else None)
        s1 = {"nd": nd_, "age": age_, "wh_n": wn_, "wh_s": ws_, "cold": wn_ == 0, "keep": why_ is None, "why": why_, "replayed": True}
    if s1:
        lines.append(f"  S1 gate PSM12-S1 ({'replayed from the arm' if s1.get('replayed') else 'LIVE' if s1.get('live') else 'log'}): nd {s1.get('nd')}, age {s1.get('age')}, "
                     f"{'dumper' if kind == 'rearm' else 'whale'} {s1.get('wh_n')} positions {s1.get('wh_s', 0):+.3f} SOL{' (cold)' if s1.get('cold') else ''} -> "
                     + ("keep" if s1.get("keep") else f"WOULD SKIP ({s1.get('why')})") + (f" | live parts {s1['parts']}: {s1.get('pwhy') or 'keep'}" if s1.get("parts") else ""))
        if not s1.get("keep"): caught.append(f"S1 {s1.get('why')} ({'LIVE' if s1.get('live') else 'log'})")
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
    # LOG (dip38): launcher, INSIDER / FAMILY / FAMILY LEDGER at the arm and the fill, INSIDER with the chains known at the realize; SHAPE
    i38 = ins38.get(k) or {}
    if i38:
        def ins_s(r):
            if not r: return "n/a"
            cv = r.get("cov") or {}
            s_ = (f"INSIDER {r['ins']['role']} {r['ins']['wallet'][:8]} {r['ins'].get('pct', 0):.1f}% funded by the {r['ins']['via']} ({r['ins']['hops']} hop: {r['ins']['chain']})"
                  if r.get("insider") else f"insider no (chains ok {cv.get('ok', 0)} / deep {cv.get('deep', 0)} / pending {cv.get('pending', 0)} / fail {cv.get('fail', 0)} of {r.get('cands')})")
            if r.get("family"): s_ += f"; FAMILY {r['fam']['wallet'][:8]} chain has listed {r['fam']['link'][:8]}"
            fl_ = r.get("fl")
            if fl_ is not None: s_ += f"; family ledger {fl_.get('n')} fills {fl_.get('sum', 0):+.3f}" + (" -> WOULD BLOCK" if r.get("would") else "")
            return s_
        a38, f38, z38 = i38.get("arm"), i38.get("fill"), i38.get("realize")
        r0 = f38 or a38 or {}
        lines.append(f"  launcher (dip38): {str(r0.get('launcher'))[:8]}" + (" (pays the create; creator field " + str(r0.get('creator'))[:8] + ")" if r0.get("payer_ne_creator") else "")
                     + f", holds {r0.get('launcher_pct') or 0:.1f}% at the fill, sold {r0.get('launcher_sold_pct') or 0:.1f}% so far")
        lines.append(f"  insider / family (log): arm {ins_s(a38)} | fill {ins_s(f38)}" + (f" | {i38['send_flags']} of {i38.get('sends', 0)} sends flagged" if i38.get("send_flags") else ""))
        if z38:
            lines.append(f"  insider at the realize (late chains, log): " + (f"INSIDER {z38['late']['wallet'][:8]} ({z38['late']['chain']})" if z38.get("insider_late") else "no")
                         + (f" | learned into the launcher's ledger -> {z38['fl_after'].get('n')} fills {z38['fl_after'].get('sum', 0):+.3f}" if z38.get("learned") and z38.get("fl_after") else ""))
        if f38 and f38.get("would"): caught.append("family ledger (log)")
        if f38 and f38.get("insider"): caught.append("insider flag (log)")
        if f38 and f38.get("family"): caught.append("family chain (log)")
    s38 = shp38.get(k) or {}
    if s38:
        fs = s38.get("fill") or s38.get("arm") or {}
        h_ = fs.get("hit")
        lines.append(f"  shape ledger (log): holder sizes {', '.join(format(x, '.3f') + '%' for x in fs.get('els') or []) or 'none'}"
                     + (f" -> {h_['el']:.3f}% had {h_['n']} fills {h_['sum']:+.3f} in 6 h, no win: WOULD BLOCK" if h_ else " -> no"))
        if (s38.get("fill") or {}).get("would"): caught.append("shape ledger (log)")
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
