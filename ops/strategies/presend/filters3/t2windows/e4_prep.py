#!/usr/bin/env python3
"""T2-WINDOWS step 4a: per run calibration (from the live records + block clock) and the candidate list grouped by mint bucket.
Calibration per run [MEASURED]:
  d_t2  = median over live T2 windows of (first try send - trigger feed arrival) ms   -> sim window opens at cc(trigger) + d_t2
  d_re  = median over live re-arm windows of (first try send - dump feed arrival) ms + cc(dump) - (dump slot + 3) x 212
          -> sim window opens at (dump slot + 3) x 212 + d_re  (the engine arms at the first executed tx of slot >= dump + 3)
  H     = median fill -> sell landing on the block clock (time-ms exits) per run; H_cur = r48 + r49 (the 125 ms exit)
  fixed = median (live realized - live curve P&L) per run and kind, rounds == 1 (pump fees both ways, tips, tx fees)
  pool  = every try's (send -> first seen) ms + unseen share
Candidates: LIVE windows (validation), RE-ARM candidates (every >= 6 % sell record: armed / skipped / deferred), WIDE triggers >= 3.9 %,
live T2 triggers (armed + skipped; QUIET-proxy validation).
Out: /home/moiz/sniper-data/filters3/t2windows/prep.pkl"""
import sys, pickle, statistics, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/t2windows")
import t2lib as L

RUNS = [39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49]


def med(v, d=None): return statistics.median(v) if v else d


if __name__ == "__main__":
    maxi = pickle.load(open(f"{L.D}/maxi.pkl", "rb")); clk = L.Clock(maxi)
    cal = {}; cands = collections.defaultdict(list); live_pos = []; live_arm = []
    for r in RUNS:
        R = pickle.load(open(f"{L.D}/rec_{r}.pkl", "rb"))
        dt2, dre, Hs, fx, offs = [], [], [], collections.defaultdict(list), []
        for w in R["wins"]:
            anc = w.get("trig") if w["kind"] == "t2" else w.get("dump")
            if not anc or not w["tries"]: continue
            t0 = w["tries"][0]["t"]
            if anc["slot"] in maxi:
                c = clk.cc(anc["slot"], anc["idx"]); offs.append(anc["t"] / 1e6 - c)
                if w["kind"] == "t2": dt2.append((t0 - anc["t"]) / 1e6)
                elif not w.get("deferred_ms"): dre.append((t0 - anc["t"]) / 1e6 + c - (anc["slot"] + 3) * L.SMS)
            cl = w.get("close") or {}; fl = w.get("fill")
            if fl and w["pnl"] is not None and cl.get("curve_pnl") is not None and cl.get("rounds") == 1:
                fx[w["kind"]].append((w["pnl"] * 1e9 - cl["curve_pnl"], cl.get("spend") or w.get("spend")))
                sl = cl.get("sell_land")
                if sl and cl.get("exit_why") == "time-ms" and sl[0] in maxi and fl["slot"] in maxi and fl.get("idx") is not None:
                    Hs.append(clk.cc(sl[0], sl[1]) - clk.cc(fl["slot"], fl["idx"]))
            # live intervals (one-position rule / one window per token)
            dis = w.get("disarm") or {}
            live_arm.append((r, w["ses"], w["w"], w["mint"], t0, dis.get("t") or t0, w["kind"]))
            if fl:
                sl = cl.get("sell_land") or []
                tend = (sl[2] if len(sl) > 2 and sl[2] else (fl["t"] + int(((cl.get("held_s") or 1.0)) * 1e9)))
                live_pos.append((r, w["ses"], w["w"], w["mint"], fl["t"], tend + 300_000_000, w["pnl"] or 0.0, w["kind"]))
        pool_ms, unseen = L.make_pool(R["pool"])
        cfg = R["cfgs"][-1]["pl"] or {}
        rcfg = cfg.get("rearm") or {}
        cal[r] = {"d_t2": med(dt2, 60.0), "d_re": med(dre, 30.0), "n_t2": len(dt2), "n_re": len(dre), "dre_iqr": (sorted(dre)[len(dre) // 4], sorted(dre)[3 * len(dre) // 4]) if len(dre) > 8 else None,
                  "H": med(Hs, 400.0), "nH": len(Hs), "fixed": {k: med([a for a, b in v]) for k, v in fx.items()}, "fixed_spend": {k: med([b for a, b in v]) for k, v in fx.items()},
                  "pool": pool_ms, "unseen": unseen, "spend": cfg.get("spend"), "re_spend": rcfg.get("spend"), "exit_ms": cfg.get("exit_ms"),
                  "t_first": R["t_first"], "t_last": R["t_last"], "off_med": med(offs)}
        # candidates
        seen = set()
        for w in R["wins"]:
            if w["kind"] == "rearm":
                d = w["dump"]; seen.add(d["sig"])
                cands[L.bucket(w["mint"])].append({"c": "re", "run": r, "mint": w["mint"], "anc": d, "why": "armed", "rec": {k: w.get(k) for k in ("holders", "r5", "check_slot", "en_slot", "creator", "deferred_ms")},
                                                   "live": (w["ses"], w["w"]), "live_pnl": w["pnl"], "live_fill": bool(w["fill"])})
            else:
                cands[L.bucket(w["mint"])].append({"c": "t2", "run": r, "mint": w["mint"], "anc": w["trig"], "why": "armed", "rec": {k: w.get(k) for k in ("quiet", "f3", "nb", "creator", "nb50")},
                                                   "live": (w["ses"], w["w"]), "live_pnl": w["pnl"], "live_fill": bool(w["fill"])})
        for s in R["skips"]:
            if s["kind"] == "rearm":
                d = s.get("dump") or {}
                if not d.get("sig") or d["sig"] in seen: continue
                seen.add(d["sig"])
                cands[L.bucket(s["mint"])].append({"c": "re", "run": r, "mint": s["mint"], "anc": d, "why": s["why"], "rec": {k: s.get(k) for k in ("holders", "r5", "check_slot", "en_slot", "creator", "cr")},
                                                   "live": None})
            else:
                tg = s.get("trig") or {}
                if not tg.get("sig"): continue
                cands[L.bucket(tg["mint"])].append({"c": "t2", "run": r, "mint": tg["mint"], "anc": tg, "why": s["why"], "rec": {k: s.get(k) for k in ("quiet", "f3", "nb", "creator", "nb50")},
                                                    "live": None})
        for w in R["wide"]:
            if (w.get("pct") or 0) < 3.9: continue
            anc = {k: w.get(k) for k in ("mint", "wallet", "pct", "bal", "slot", "idx", "sig", "t", "age_slots", "vsol", "vtok", "sol", "tok")}
            cands[L.bucket(w["mint"])].append({"c": "wide", "run": r, "mint": w["mint"], "anc": anc, "why": (w.get("dis") or {}).get("why"),
                                               "rec": {"rows": w.get("rows"), "fill_c": (w["fill"] or {}).get("c"), "exit_c": (w["exit"] or {}).get("c")}, "live": None})
        c = cal[r]
        print(f"r{r}: d_t2 {c['d_t2']:.1f} ({c['n_t2']}) d_re {c['d_re']:.1f} ({c['n_re']}, iqr {c['dre_iqr']}) H {c['H']:.0f} ({c['nH']}) fixed "
              f"{ {k: round(v / 1e6, 2) for k, v in c['fixed'].items()} } pool {len(c['pool'])} unseen {c['unseen']:.3f} spend {c['spend']} re {c['re_spend']} exit {c['exit_ms']}", flush=True)
    Hc = [cal[r]["H"] for r in (48, 49)]
    pickle.dump({"cal": cal, "H_cur": statistics.mean(Hc), "cands": dict(cands), "live_pos": live_pos, "live_arm": live_arm}, open(f"{L.D}/prep.pkl", "wb"))
    print("H_cur", statistics.mean(Hc), "cands", sum(len(v) for v in cands.values()), collections.Counter(x["c"] for v in cands.values() for x in v))
