#!/usr/bin/env python3
"""QUIET (dip20) PARITY, the comparison: per live armed window, the research replay's decision (quiet_parity_export.py, from
apply_filter.py) vs THE ENGINE'S (the probe's own code fed the same raw recording in chain order: dip20_tests::dip20_recorded_parity).

  python3 quiet_parity_compare.py --replay replay_ams_r24.json --engine engine_ams_r24_full.json [--engine-seg engine_ams_r24_seg.json] [--list]

Compared per window:
  signals   since_last, coh_hold, fb_n (exact), wh_dump_fol vs the engine's wh_fol (to 1e-9)
  skip      the replay's quiet arm rule vs the engine's (all four signals; the rule on: full history)
  stop      the replay: a try at slot >= trigger + 6 whose 'others' (chain rows up to the try's pos) is < 2 -> stop at that try's slot.
            the engine: at the first tick with slot >= trigger + 6, others < 2 -> disarm at that slot; it STOPS a live try only if the
            live window still sent one at or after that slot. Compared: stop yes/no (as effective on the live tries) and the stop slot.
Leftover stop mismatches are classified: 'two wallets' (the replay also excludes the other region's wallet; the engine knows only
its own), 'decision moment' (the replay's count is at each try's own pos, the engine's at the first tx of slot trigger + 6), other."""
import json, argparse, collections


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", required=True); ap.add_argument("--engine", required=True); ap.add_argument("--engine-seg"); ap.add_argument("--list", action="store_true")
    ap.add_argument("--engine-state", action="append", default=[], help="dip21 restarts harness output(s) (dip21_tests::dip21_recorded_restarts)")
    ap.add_argument("--after", type=int, default=0, help="--engine-state: also count the windows triggered at or after this unix time (s) (a restart)")
    A = ap.parse_args()
    R = json.load(open(A.replay)); E = json.load(open(A.engine))
    eng = {(w["seg"], w["w"]): w for w in E["windows"]}
    c = collections.Counter(); bad = collections.defaultdict(list)
    for w in R["windows"]:
        k = (w["seg"], w["w"]); r = w["replay"]; e = eng.get(k)
        c["windows"] += 1
        if e is None: c["engine_missing"] += 1; bad["engine_missing"].append(k); continue
        if not r["found"]:
            c["replay_not_found"] += 1
            if e["found"]: c["replay_not_found_engine_found"] += 1
            continue
        if not e["found"]: c["engine_no_trigger"] += 1; bad["engine_no_trigger"].append(k); continue
        c["compared"] += 1
        a = e["arm"]
        sig_ok = (a["since_last"] == r["since_last"] and a["coh_hold"] == r["coh_hold"] and a["fb_n"] == r["fb_n"] and abs(a["wh_fol"] - r["wh_dump_fol"]) < 1e-9)
        if not sig_ok:
            c["signal_mismatch"] += 1
            bad["signal"].append((k, {x: (a[x], r[y]) for x, y in (("since_last", "since_last"), ("coh_hold", "coh_hold"), ("fb_n", "fb_n"), ("wh_fol", "wh_dump_fol")) if a[x] != r[y]}))
        for n, (x, y) in enumerate((("since_last", "since_last"), ("coh_hold", "coh_hold"), ("fb_n", "fb_n"), ("wh_fol", "wh_dump_fol"))):
            if (a[x] != r[y]) if x != "wh_fol" else abs(a[x] - r[y]) >= 1e-9: c[f"diff_{x}"] += 1
        eskip = bool(a["all4"])
        if eskip != r["skip"]: c["skip_mismatch"] += 1; bad["skip"].append((k, eskip, r["skip"]))
        if r["skip"]: c["skip_replay"] += 1
        if eskip: c["skip_engine"] += 1
        # the stop, as it acts on the live tries
        tries = [t[0] for t in w["tries"]]
        e_stop = bool(e["stop"]) and any(s >= e["stop_slot"] for s in tries)
        r_stop = bool(r["stop"])
        if r_stop: c["stop_replay"] += 1
        if e_stop: c["stop_engine"] += 1
        if e["stop"] is None: c["engine_undecided"] += 1
        if e_stop != r_stop:
            c["stop_mismatch"] += 1
            why = "other"
            if r.get("first6_slot") is not None and r["first6_others"] != r["first6_others_own"]: why = "two wallets"
            elif r.get("first6_slot") is not None and e["others"] is not None and e["others"] != r["first6_others_own"]: why = "decision moment"
            c[f"stop_mismatch_{why}"] += 1
            bad["stop"].append((k, why, dict(engine=(e["stop"], e["stop_slot"], e["others"]), replay=(r["stop"], r["stop_slot"], r["first6_slot"], r["first6_others"], r["first6_others_own"]),
                                             trig=w["slot"], last_try=max(tries) if tries else None, disarm=w.get("disarm"))))
        elif e_stop and r_stop:
            if e["stop_slot"] == r["stop_slot"]: c["stop_slot_same"] += 1
            else: c["stop_slot_diff"] += 1; bad["stop_slot"].append((k, e["stop_slot"], r["stop_slot"], w["slot"]))
    print(f"=== {R['run']}: {c['windows']} windows | compared {c['compared']} (replay: trigger not on the recording {c['replay_not_found']}; engine: no trigger at that trade {c['engine_no_trigger']}, "
          f"missing {c['engine_missing']})")
    print(f"  signals: mismatched windows {c['signal_mismatch']} (since_last {c['diff_since_last']}, coh_hold {c['diff_coh_hold']}, fb_n {c['diff_fb_n']}, wh_fol {c['diff_wh_fol']})")
    print(f"  SKIP: replay {c['skip_replay']} engine {c['skip_engine']} -> mismatches {c['skip_mismatch']}")
    print(f"  STOP: replay {c['stop_replay']} engine {c['stop_engine']} -> mismatches {c['stop_mismatch']} (two wallets {c['stop_mismatch_two wallets']}, decision moment "
          f"{c['stop_mismatch_decision moment']}, other {c['stop_mismatch_other']}) | stop slot: same {c['stop_slot_same']}, different {c['stop_slot_diff']} | engine undecided {c['engine_undecided']}")
    if A.list:
        for kind, v in bad.items():
            for x in v[:40]: print(f"    {kind}: {x}")
    out = dict(run=R["run"], counts=dict(c), mismatches={k: v for k, v in bad.items()})
    if A.engine_seg:
        S = json.load(open(A.engine_seg)); seg = {(w["seg"], w["w"]): w for w in S["windows"]}
        d = collections.Counter()
        for w in R["windows"]:
            r = w["replay"]; e = seg.get((w["seg"], w["w"]))
            if not r["found"] or e is None or not e["found"]: continue
            a = e["arm"]; d["n"] += 1
            on = bool(a.get("rule_on")); eskip = bool(a["all4"]) and on
            if not on: d["warmup"] += 1; d["warmup_replay_skip"] += int(r["skip"]); d["warmup_would"] += int(bool(a["all4"]))
            if eskip != r["skip"]: d["differ"] += 1
            if on and bool(a["all4"]) != r["skip"]: d["differ_after_warmup"] += 1
            if abs(a["wh_fol"] - r["wh_dump_fol"]) >= 1e-9: d["wh_fol_differs"] += 1
        print(f"  WITHOUT A PRELOAD (each segment from its own start, 60-min warm-up): {d['n']} windows, {d['warmup']} in the warm-up (replay skips {d['warmup_replay_skip']} of them; "
              f"all four held on {d['warmup_would']}); skip decisions differing from the replay: {d['differ']} ({d['differ_after_warmup']} after the warm-up; whale history differs on {d['wh_fol_differs']})")
        out["no_preload"] = dict(d)
    # dip21: the state journal's restarts: each session a fresh engine whose whale history is the journal (+ its own feed)
    for fn in A.engine_state:
        X = json.load(open(fn)); st = {(w["seg"], w["w"]): w for w in X["windows"]}
        for part, lo in (("all sessions", 0), (f"after {A.after}", A.after)) if A.after else (("all sessions", 0),):
            d = collections.Counter(); bad2 = []
            for w in R["windows"]:
                r = w["replay"]; e = st.get((w["seg"], w["w"]))
                if e is None or w["t"] / 1e9 < lo: continue
                d["n"] += 1
                if not r["found"]: d["replay_not_found"] += 1; continue
                if not e["found"]: d["engine_no_trigger"] += 1; continue
                a = e["arm"]; on = bool(a.get("rule_on")); eskip = bool(a["all4"]) and on
                d["compared"] += 1
                if not on: d["rule_off"] += 1; d["rule_off_replay_skip"] += int(r["skip"])
                if r["skip"]: d["replay_skip"] += 1
                if eskip: d["engine_skip"] += 1
                sig_ok = a["since_last"] == r["since_last"] and a["coh_hold"] == r["coh_hold"] and a["fb_n"] == r["fb_n"]
                fol_ok = abs(a["wh_fol"] - r["wh_dump_fol"]) < 1e-9
                if not sig_ok: d["sig_abc_differs"] += 1
                if not fol_ok: d["wh_fol_differs"] += 1
                if eskip != r["skip"]:
                    d["skip_mismatch"] += 1
                    why = "rule off (warm-up)" if not on else ("whale history differs" if not fol_ok else ("token signals differ" if not sig_ok else "other"))
                    d[f"mm_{why}"] += 1
                    bad2.append((w["seg"], w["w"], why, dict(engine=(a["since_last"], a["coh_hold"], a["fb_n"], a["wh_fol"], a["wh_dumps"], on), replay=(r["since_last"], r["coh_hold"], r["fb_n"], r["wh_dump_fol"]))))
            print(f"  WITH THE STATE FILE [{X['mode']}{' + 24 h prior history' if X.get('prehist') else ''}] {part}: {d['n']} windows, compared {d['compared']} (engine had no trigger there: "
                  f"{d['engine_no_trigger']}), arm rule off at {d['rule_off']} (replay skips {d['rule_off_replay_skip']} of them) | SKIP replay {d['replay_skip']} engine {d['engine_skip']} -> "
                  f"mismatches {d['skip_mismatch']} (rule off {d['mm_rule off (warm-up)']}, whale history {d['mm_whale history differs']}, token signals {d['mm_token signals differ']}, "
                  f"other {d['mm_other']}) | whale history differs on {d['wh_fol_differs']}, token signals on {d['sig_abc_differs']}")
            if A.list:
                for x in bad2[:30]: print(f"      {x}")
            out.setdefault("state", {})[f"{fn}|{part}"] = dict(d)
    return out


if __name__ == "__main__":
    main()
