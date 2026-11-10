#!/usr/bin/env python3
"""T2-WINDOWS step 1 [MEASURED, read-only]: one pass over a run's records -> compact pickle.
  live windows (T2 + re-arm, armed): arm record, every try (presend_attempt + _land), fill, close, realized (THE money), disarm
  skips: every presend_live_skip (T2 and re-arm, with why / trig / dump / holders / r5 / quiet / f3 / nb / ann) + re-arm defers
  wide shadow (3-6 % whales, r41+): arm, fills / exits per row, disarm
  shadow T2 (presend_arm / presend_fill / presend_exit row c) for calibration
  landing pool: (res, ms send -> first_rx) of every try
Out: /home/it/sniper-data/filters3/t2windows/rec_<run>.pkl     usage: e1_extract.py RUN SRC"""
import sys, json, pickle, collections
OUT = "/home/it/sniper-data/filters3/t2windows"
AK = ("t", "slot", "pos", "deadline", "lim", "min_out", "vsol", "vtok", "spend", "n", "path", "client")
LK = ("res", "slot", "idx", "first_rx", "t_send", "fee", "err", "send_slot", "deadline")
SKEEP = ("why", "kind", "mint", "trig", "dump", "holders", "r5", "quiet", "f3", "nb", "check_slot", "en_slot", "cr", "tags", "deferred", "ended")


def ann_cr(r):
    a = r.get("ann") or {}
    return a.get("creator"), a.get("nb50")


def main(run, src):
    ses = -1; cfgs = []; t_first = None; t_last = None
    arms, atts, lands, fills, real, nreal, close, disarm, exits, sland = {}, collections.defaultdict(list), {}, {}, collections.defaultdict(int), collections.Counter(), {}, {}, {}, {}
    skips, defers = [], []
    warm, wfill, wexit, wdis = {}, collections.defaultdict(dict), collections.defaultdict(dict), {}
    sarm, sfill, sexit, sdis = {}, {}, {}, {}
    with open(src, "rb") as f:
        for raw in f:
            if b'"ev":"presend_' not in raw and b'"ev":"run_start"' not in raw and b'"ev":"run_end"' not in raw: continue
            if b'"ev":"presend_live_tape"' in raw or b'"ev":"presend_live_ata' in raw: continue
            try: r = json.loads(raw)
            except Exception: continue
            e = r.get("ev"); t = r.get("t")
            if e == "run_start":
                ses += 1; cfgs.append({"t": t, "pl": r.get("presend_live")}); continue
            if e == "run_end": cfgs[-1]["t_end"] = t if cfgs else None; continue
            if ses < 0: ses = 0; cfgs.append({"t": None, "pl": None})
            if isinstance(t, (int, float)) and t > 1.7e18:
                t_first = t if t_first is None else min(t_first, t); t_last = t if t_last is None else max(t_last, t)
            k = (ses, r.get("w"))
            if e == "presend_live_arm":
                a = {x: r.get(x) for x in ("mint", "trig", "dump", "holders", "en_slot", "arm_slot", "check_slot", "spend", "lim0", "drop", "k", "quiet", "gap", "r5", "f3",
                                           "nb", "deferred_ms", "arm_ms_after_dump", "tags")}
                a["kind"] = r.get("kind") or "t2"
                a["creator"], a["nb50"] = ann_cr(r)
                a["t_arm"] = (r.get("trig") or r.get("dump") or {}).get("t")
                a["mint"] = r.get("mint") or (r.get("trig") or {}).get("mint") or (r.get("dump") or {}).get("mint")
                arms[k] = a
            elif e == "presend_attempt":
                atts[k].append(dict({x: r.get(x) for x in AK}, sig=r["sig"]))
            elif e == "presend_attempt_land":
                lands[r["sig"]] = {x: r.get(x) for x in LK}
            elif e == "presend_live_fill":
                fills[k] = {x: r.get(x) for x in ("sig", "slot", "idx", "t", "lim", "min_out", "p_sign", "p_entry_pre", "sol_in", "tokens", "spend", "slots_after_trigger", "mint")}
            elif e == "presend_live_realized":
                real[k] += r.get("pnl") or 0; nreal[k] += 1
            elif e == "presend_live_close":
                close[k] = {x: r.get(x) for x in ("exit_why", "sell_land", "sell_lands", "held_s", "curve_pnl", "rounds", "merged", "land", "sol_in_curve", "sol_out_curve",
                                                   "tokens", "spend", "result", "mint")}
            elif e == "presend_live_exit":
                exits[k] = {x: r.get(x) for x in ("why", "t", "slot", "v", "mint")}
            elif e == "presend_live_disarm":
                disarm[k] = {x: r.get(x) for x in ("why", "slot", "t", "filled", "attempts", "armed_ms", "rearm", "trig_slot", "quiet_stop")}
            elif e == "presend_live_skip":
                s = {x: r.get(x) for x in SKEEP if r.get(x) is not None}
                s["kind"] = r.get("kind") or "t2"; s["ses"] = ses
                s["creator"], s["nb50"] = ann_cr(r)
                s["mint"] = r.get("mint") or (r.get("trig") or {}).get("mint")
                skips.append(s)
            elif e == "presend_live_rearm_defer":
                defers.append({x: r.get(x) for x in ("mint", "dump", "holders", "r5", "why", "check_slot", "en_slot")})
            elif e == "presend_wide_arm":
                warm[k] = {x: r.get(x) for x in ("mint", "wallet", "pct", "bal", "slot", "idx", "sig", "t", "age_slots", "vsol", "vtok", "sol", "tok", "a", "en0", "rows")}
            elif e == "presend_wide_fill":
                wfill[k][r.get("row")] = {x: r.get(x) for x in ("ft", "s_in", "slots_after_trigger", "drop_pct", "n_ahead", "seller_is_whale")}
            elif e == "presend_wide_exit":
                wexit[k][r.get("row")] = {x: r.get(x) for x in ("net_cheap", "pnl", "why", "xt")}
            elif e == "presend_wide_disarm":
                wdis[k] = {"why": r.get("why"), "whale_sell": (r.get("whale_sell") or {}).get("slot")}
            elif e == "presend_arm":
                sarm[k] = {x: r.get(x) for x in ("mint", "wallet", "pct", "slot", "idx", "sig", "t", "age_slots", "quiet")}
            elif e == "presend_fill" and r.get("row") == "c":
                sfill[k] = {x: r.get(x) for x in ("ft", "s_in", "drop_pct")}
            elif e == "presend_exit" and r.get("row") == "c":
                sexit[k] = {x: r.get(x) for x in ("net_cheap", "pnl", "why")}
            elif e == "presend_disarm":
                sdis[k] = r.get("why")
    pool = []; wins = []
    for key, tries in atts.items():
        for a in tries:
            L = lands.get(a["sig"])
            if L and L.get("first_rx") and a.get("t"): pool.append((L["res"], (L["first_rx"] - a["t"]) / 1e6))
            elif L and L.get("res") == "unseen": pool.append(("unseen", None))
    for key, a in arms.items():
        tries = []
        for x in atts.get(key, []):
            x = dict(x); x["land"] = lands.get(x["sig"]); tries.append(x)
        tries.sort(key=lambda x: x["t"] or 0)
        wins.append({"ses": key[0], "w": key[1], **a, "tries": tries, "fill": fills.get(key), "pnl": (real[key] / 1e9) if key in nreal else None,
                     "n_real": nreal[key], "close": close.get(key), "exit": exits.get(key), "disarm": disarm.get(key)})
    # orphan fills (fill without an arm record: should not happen)
    orphan = [k for k in fills if k not in arms]
    wide = []
    for key, a in warm.items():
        wide.append({"ses": key[0], "w": key[1], **a, "fill": dict(wfill.get(key, {})), "exit": dict(wexit.get(key, {})), "dis": wdis.get(key)})
    shadow = []
    for key, a in sarm.items():
        shadow.append({"ses": key[0], "w": key[1], **a, "fill": sfill.get(key), "exit": sexit.get(key), "dis": sdis.get(key)})
    out = {"run": run, "cfgs": cfgs, "t_first": t_first, "t_last": t_last, "wins": wins, "pool": pool, "skips": skips, "defers": defers, "wide": wide,
           "shadow": shadow, "orphan_fills": orphan}
    pickle.dump(out, open(f"{OUT}/rec_{run}.pkl", "wb"))
    kc = collections.Counter(w["kind"] for w in wins)
    print(f"r{run}: wins {dict(kc)} filled {sum(1 for w in wins if w['fill'])} realized {sum(w['pnl'] or 0 for w in wins):+.4f} skips {len(skips)} "
          f"({collections.Counter((s['kind'], s.get('why')) for s in skips).most_common(6)}) wide {len(wide)} shadow {len(shadow)} pool {len(pool)} "
          f"orphan {len(orphan)} sessions {len(cfgs)}", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2])
