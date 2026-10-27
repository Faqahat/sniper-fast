#!/usr/bin/env python3
# r02: every live fire (FRA runs 10-15, AMS runs 9-14) joined with its landed tx in the raw recording (any copy, fill or failed)
# and the sell txs -> WORK/fires.json (one row per fire) + a coverage summary. MEASURED (chain = the recording's tx records).
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib as R

if __name__ == "__main__":
    runs = R.load_runs(); ours = R.load_ours()
    rows = []; used = set()
    for ru in runs:
        for f in ru["fires"]:
            fo = f["fire"]; cl = f.get("close", {}); bl = f.get("buy_land"); bf = f.get("buy_failed")
            # which copy landed: any of the fire's signatures found in the recording
            hits = [ours[s] for s in f["sigs"] if s in ours]
            okh = [h for h in hits if not h.get("err")]; erh = [h for h in hits if h.get("err")]
            land = (okh or erh or [None])[0]
            row = dict(srv=f["srv"], run=f["run"], mint=f["mint"], dump_sig=f["dump_sig"], t_fire=fo["t_fire"] / 1e9,
                       t_dump_rx=fo["t_dump_rx"] / 1e9, dump_slot=fo["slot"], leader=fo.get("leader"), client=fo.get("client"),
                       route=fo.get("route"), dev=fo.get("dev"), spend=fo["spend"], min_out=fo.get("min_out"), tips_fire=fo.get("tips"),
                       n_sigs=len(f["sigs"]), n_hits=len(hits), n_ok=len(okh), n_err=len(erh),
                       live_result=cl.get("result"), live_err=cl.get("err"), dump_idx=cl.get("dump_idx"),
                       dump_vsol=cl.get("dump_vsol"), dump_vtok=cl.get("dump_vtok"),
                       bl_slot=(bl or {}).get("slot"), bl_idx=(bl or {}).get("idx"), bl_tokens=(bl or {}).get("tokens"), bl_sol=(bl or {}).get("sol"),
                       bl_rx_ms=(bl or {}).get("rx_ms_after_dump"), bl_fee=(bl or {}).get("fee"),
                       bf_slot=(bf or {}).get("slot"),
                       exit_why=(f.get("exit") or {}).get("why"), exit_slot=(f.get("exit") or {}).get("slot"),
                       exit_slots_held=(f.get("exit") or {}).get("slots_held"),
                       sl_slot=(f.get("sell_land") or {}).get("slot"), sl_idx=(f.get("sell_land") or {}).get("idx"),
                       sl_sol=(f.get("sell_land") or {}).get("sol"), sl_fee=(f.get("sell_land") or {}).get("fee"),
                       curve_pnl=cl.get("curve_pnl"), sol_in_curve=cl.get("sol_in_curve"), sol_out_curve=cl.get("sol_out_curve"),
                       close_tips=cl.get("tips"), sell_sigs=cl.get("sell_sigs"), realized=f.get("realized"),
                       timing={k: (f.get("timing") or {}).get(k) for k in ("fire_to_seen_ms", "reaction_ms", "land_ms_poh", "dump_first_rx",
                                                                        "dump_exec_rx", "buy_first_rx", "exec_lag_ms", "buy_poh", "dump_poh")})
            if land is not None:
                used.add(land["sig"])
                tev = [e for e in R.trade_events(land) if e["mint"] == f["mint"]]
                row.update(rec=land["_rec"], land_sig=land["sig"], land_slot=land["s"], land_idx=land["i"], land_err=land.get("err"),
                           land_fee=land.get("fee"), land_cup=land.get("cup"), land_cul=land.get("cul"), land_cu=land.get("cu"),
                           land_tips=sum(v for _, v in land.get("tips") or []), land_delta=R.our_delta(land),
                           land_tok=sum(e["tok"] for e in tev if e["buy"]), land_sol=sum(e["sol"] for e in tev if e["buy"]),
                           land_fee_bps=(tev[0]["fee_bps"] + tev[0]["cfee_bps"]) if tev else None,
                           land_vsol=tev[-1]["vsol"] if tev else None, land_vtok=tev[-1]["vtok"] if tev else None)
                if len(okh) + len(erh) > 1:
                    row["other_hits"] = [(h["sig"], h["s"], h["i"], h.get("err")) for h in hits if h["sig"] != land["sig"]]
            # sells
            sells = []
            for s in (cl.get("sell_sigs") or []):
                sg = s[0] if isinstance(s, list) else s
                h = ours.get(sg)
                if h is not None:
                    used.add(sg)
                    tev = [e for e in R.trade_events(h) if e["mint"] == f["mint"]]
                    sells.append(dict(sig=sg, slot=h["s"], idx=h["i"], err=h.get("err"), fee=h.get("fee"), delta=R.our_delta(h),
                                      tips=sum(v for _, v in h.get("tips") or []), tok=sum(e["tok"] for e in tev if not e["buy"]),
                                      sol=sum(e["sol"] for e in tev if not e["buy"]),
                                      fee_bps=(tev[0]["fee_bps"] + tev[0]["cfee_bps"]) if tev else None,
                                      vsol=tev[-1]["vsol"] if tev else None, vtok=tev[-1]["vtok"] if tev else None))
                else:
                    sells.append(dict(sig=sg, missing=True))
            row["sells"] = sells
            rows.append(row)
    # our txs in the recording that no fire claims (sells retried, other activity)
    extra = [r for s, r in ours.items() if s not in used]
    json.dump(dict(rows=rows, extra=[dict(sig=r["sig"], slot=r["s"], idx=r["i"], err=r.get("err"), ixn=r.get("ixn"), mints=r.get("mints"),
                                         delta=R.our_delta(r), rec=r["_rec"], bt=r.get("bt")) for r in extra],
                   runs=[dict(srv=ru["srv"], run=ru["run"], start=ru["start"], end=ru["end"], n_fires=len(ru["fires"]),
                              realized_unmatched=ru["realized_unmatched"],
                              cfg={k: ru["cfg"].get(k) for k in ("spend", "dev_spend", "hold_slots", "sl", "tp", "thr", "thr_dev", "tier",
                                                                  "model", "guard", "max_inflight")} | {"m2_mode": (ru["cfg"].get("m2") or {}).get("mode")})
                         for ru in runs]),
              open(f"{R.WORK}/fires.json", "w"), default=str)
    # ---- coverage summary
    c = collections.Counter()
    for r in rows:
        c[(r["srv"], r["run"], r["live_result"], "found" if r.get("land_sig") else "NOT FOUND", r.get("rec"))] += 1
    for k in sorted(c, key=str): print(k, c[k])
    print("extra our txs not claimed by a fire:", len(extra))
    ce = collections.Counter((tuple(x for x in (r.get("ixn") or []) if "Buy" in x or "Sell" in x), bool(r.get("err")), r["_rec"]) for r in extra)
    for k, v in ce.most_common(): print("  ", k, v)
    multi = [r for r in rows if r["n_ok"] + r["n_err"] > 1]
    print("fires with more than one landed copy:", len(multi))
    for r in multi[:10]: print("   ", r["srv"], r["run"], r["mint"][:8], r["land_sig"][:10], r.get("other_hits"))
    for ru in runs:
        if ru["realized_unmatched"]: print("REALIZED not matched", ru["srv"], ru["run"], ru["realized_unmatched"])
