# REGIME step 1: compact per-run extract of live pre-send trades, windows, try fees, shadow rows and market-wide dump events.
# usage: rg1_extract.py OUT_DIR  (reads /home/it/sniper-data/runs/{ams,fra}/runs/*.jsonl read-only)
import json, sys, os, pickle, collections
from multiprocessing import Pool

R = "/home/it/sniper-data/runs"
LIVE = [("ams", f"dip_ams_r{n}") for n in (16, 17, 19, 20, 24, 25, 26, 27, 34, 35, 36, 37, 38)] + \
       [("fra", f"dip_r{n}") for n in (21, 22, 23, 24, 26, 27, 28)]
SHADOW = [("ams", f"dip_ams_r{n}") for n in (14, 15, 21, 22, 23)] + [("fra", f"dip_r{n}") for n in (15, 16, 20, 25)]
WANT = (b'"ev":"presend_live_', b'"ev":"presend_attempt_land"', b'"ev":"presend_arm"', b'"ev":"presend_exit"',
        b'"ev":"dump"', b'"ev":"run_start"', b'"ev":"run_end"', b'"ev":"presend_skip"')


def one(arg):
    region, name = arg
    path = f"{R}/{region}/runs/{name}.jsonl"
    o = dict(region=region, name=name, sessions=[], arms=[], disarms=[], fills=[], closes=[], realized=[], lexits=[],
             ata=[], fees=collections.defaultdict(lambda: [0, 0, None]), sh_arms=[], sh_exits=[], dumps=[], skips=collections.Counter(),
             live_skips=[], stops=[], first_t=None, last_t=None, cfg=None)
    off = None
    sess = 0
    with open(path, "rb") as fh:
        for raw in fh:
            if not any(w in raw for w in WANT):
                continue
            try:
                d = json.loads(raw)
            except Exception:
                continue
            e = d.get("ev"); t = d.get("t")
            if e == "run_start":
                sess += 1
            if "w" in d and e.startswith("presend_live_") or e == "presend_attempt_land":
                d["w"] = (sess, d.get("w"))
            if isinstance(t, (int, float)) and t > 1e18:
                o["first_t"] = t if o["first_t"] is None else min(o["first_t"], t)
                o["last_t"] = t if o["last_t"] is None else max(o["last_t"], t)
            if e == "run_start":
                pl = d.get("presend_live") or {}
                o["sessions"].append([t, None])
                if o["cfg"] is None:
                    o["cfg"] = dict(spend=pl.get("spend"), sl=pl.get("sl"), tp=pl.get("tp"), exit_ms=pl.get("exit_ms"), k=pl.get("k"),
                                    lock=(d.get("limits") or {}).get("profit_lock"), kill=(d.get("limits") or {}).get("kill_switch"),
                                    rearm=(pl.get("rearm") or {}).get("on"), min_age=pl.get("min_age_slots"), live=d.get("live"),
                                    presend_sz=(d.get("presend") or {}).get("size_sol"))
            elif e == "run_end":
                if o["sessions"]:
                    o["sessions"][-1][1] = t
            elif e == "presend_live_arm":
                tr = d.get("trig") or d.get("dump") or {}
                o["arms"].append(dict(t=d.get("t") or tr.get("t"), w=d.get("w"), kind=d.get("kind", "t2"), mint=tr.get("mint") or d.get("mint"),
                                      spend=d.get("spend"), qskip=d.get("quiet_skip"), age=tr.get("age_slots"), pct=tr.get("pct")))
            elif e == "presend_live_disarm":
                o["disarms"].append(dict(t=t, w=d.get("w"), mint=d.get("mint"), filled=d.get("filled"), why=d.get("why"), att=d.get("attempts"), kind=d.get("kind", "t2")))
            elif e == "presend_live_fill":
                o["fills"].append(dict(t=t, w=d.get("w"), kind=d.get("kind", "t2"), mint=d.get("mint"), slot=d.get("slot"), spend=d.get("spend"),
                                       sol_in=d.get("sol_in"), path=d.get("path")))
            elif e == "presend_live_close":
                sl = d.get("sell_land") or [None, None, None, None]
                o["closes"].append(dict(w=d.get("w"), kind=d.get("kind", "t2"), mint=d.get("mint"), why=d.get("exit_why"), sell_t=sl[2] if len(sl) > 2 else None,
                                        held=d.get("held_s"), spend=d.get("spend"), result=d.get("result"), pid=d.get("pid")))
            elif e == "presend_live_realized":
                o["realized"].append(dict(w=d.get("w"), kind=d.get("kind", "t2"), mint=d.get("mint"), pnl=d.get("pnl"), pid=d.get("pid")))
            elif e == "presend_live_exit":
                o["lexits"].append(dict(t=t, w=d.get("w"), kind=d.get("kind", "t2"), mint=d.get("mint"), why=d.get("why")))
            elif e == "presend_live_ata_close":
                o["ata"].append(dict(mint=d.get("mint"), delta=d.get("delta"), ok=d.get("ok"), slot=d.get("slot")))
            elif e == "presend_attempt_land":
                if d.get("res") != "ok":
                    f = o["fees"][d.get("w")]
                    f[0] += d.get("fee") or 0; f[1] += 1
                    ts = d.get("t_send")
                    if ts and (f[2] is None or ts < f[2]):
                        f[2] = ts
            elif e == "presend_live_stop":
                o["stops"].append(dict(t=t, why=d.get("why"), fees=d.get("fees"), fills=d.get("fills")))
            elif e == "presend_live_skip":
                dd = d.get("dump") or d.get("trig") or {}
                o["live_skips"].append(dict(t=d.get("t") or dd.get("t"), kind=d.get("kind", "t2"), why=d.get("why"), mint=d.get("mint")))
            elif e == "presend_arm":
                if off is None and d.get("a") and t:
                    off = t / 1e6 - d["a"]
                q = d.get("quiet") or {}
                o["sh_arms"].append(dict(t=t, w=d.get("w"), mint=d.get("mint"), age=d.get("age_slots"), pct=d.get("pct"), sol=d.get("sol"),
                                         rows=d.get("rows"), qall4=q.get("all4")))
            elif e == "presend_exit":
                o["sh_exits"].append(dict(row=d.get("row"), w=d.get("w"), mint=d.get("mint"), pnl=d.get("pnl"), why=d.get("why"), xt=d.get("xt"),
                                          s_in=d.get("s_in"), free_at=d.get("free_at")))
            elif e == "presend_skip":
                o["skips"][d.get("why")] += 1
            elif e == "dump":
                o["dumps"].append((t, d.get("mint"), d.get("slot"), d.get("drop_pct"), d.get("sell"), d.get("age"), d.get("vsol")))
    o["off_ms"] = off
    if off is not None:
        for x in o["sh_exits"]:
            if x["xt"] is not None:
                x["t"] = (x["xt"] + off) * 1e6
    o["fees"] = dict(o["fees"])
    os.makedirs(sys.argv[1], exist_ok=True)
    pickle.dump(o, open(f"{sys.argv[1]}/{name}.pkl", "wb"))
    return f"{name}: arms {len(o['arms'])} fills {len(o['fills'])} realized {len(o['realized'])} sh_arms {len(o['sh_arms'])} sh_exits {len(o['sh_exits'])} dumps {len(o['dumps'])} fees {sum(v[0] for v in o['fees'].values())/1e9:.3f}"


if __name__ == "__main__":
    jobs = sorted(LIVE + SHADOW, key=lambda a: -os.path.getsize(f"{R}/{a[0]}/runs/{a[1]}.jsonl"))
    with Pool(6) as p:
        for line in p.imap_unordered(one, jobs):
            print(line, flush=True)
