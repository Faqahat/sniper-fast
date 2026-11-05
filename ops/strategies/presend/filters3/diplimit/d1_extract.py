#!/usr/bin/env python3
"""DIPLIMIT step 1 [MEASURED, read-only]: every LIVE pre-send window that was ARMED (T2 and re-arm; filled or not) in one run, with all
its tries (presend_attempt + presend_attempt_land), its fill, close, realized P&L, disarm; plus the run's landing-delay pool.
Out: /home/moiz/sniper-data/filters3/diplimit/win_<tag>.pkl
usage: d1_extract.py TAG SRC [T_FROM_PKT T_TO_PKT]   (time cut on the arm time, 'MM-DD HH:MM' PKT, optional)"""
import sys, json, pickle, collections, datetime
OUT = "/home/moiz/sniper-data/filters3/diplimit"
AKEYS = ("t", "slot", "pos", "deadline", "lim", "min_out", "vsol", "vtok", "spend", "n", "path", "client", "p")
LKEYS = ("res", "slot", "idx", "first_rx", "t_send", "fee", "err", "ms_send_to_first_rx", "send_slot", "deadline")


def pkt(s):
    d = datetime.datetime.strptime("2026-" + s, "%Y-%m-%d %H:%M") - datetime.timedelta(hours=5)
    return int(d.replace(tzinfo=datetime.timezone.utc).timestamp() * 1e9)


def scan(src, lo=None, hi=None):
    ses = -1
    arms, atts, lands, fills, real, close, disarm = {}, collections.defaultdict(list), {}, {}, collections.defaultdict(int), {}, {}
    nreal = collections.Counter(); cfg = []
    with open(src, "rb") as f:
        for raw in f:
            if b'"ev":"presend_live_' not in raw and b'"ev":"presend_attempt' not in raw and b'"ev":"run_start"' not in raw: continue
            try: r = json.loads(raw)
            except Exception: continue
            e = r.get("ev")
            if e == "run_start":
                ses += 1; cfg.append((r.get("presend_live") or {}).get("drop")); continue
            if ses < 0: ses = 0
            k = (ses, r.get("w"))
            if e == "presend_live_arm":
                t = (r.get("trig") or r.get("dump") or {}).get("t")
                arms[k] = {x: r.get(x) for x in ("mint", "trig", "dump", "holders", "en_slot", "arm_slot", "check_slot", "spend", "lim0", "drop", "k", "quiet", "gap")}
                arms[k]["kind"] = r.get("kind") or "t2"; arms[k]["t_arm"] = t
                arms[k]["mint"] = r.get("mint") or (r.get("trig") or {}).get("mint") or (r.get("dump") or {}).get("mint")
            elif e == "presend_attempt":
                atts[k].append(dict({x: r.get(x) for x in AKEYS}, sig=r["sig"]))
            elif e == "presend_attempt_land":
                lands[r["sig"]] = {x: r.get(x) for x in LKEYS}
            elif e == "presend_live_fill":
                fills[k] = {x: r.get(x) for x in ("sig", "slot", "idx", "t", "lim", "min_out", "p_sign", "p_entry_pre", "sol_in", "tokens", "spend", "slots_after_trigger")}
            elif e == "presend_live_realized":
                real[k] += r.get("pnl") or 0; nreal[k] += 1
            elif e == "presend_live_close":
                close[k] = {x: r.get(x) for x in ("exit_why", "sell_land", "sell_lands", "held_s", "curve_pnl", "rounds", "merged", "land", "buys",
                                                   "sol_in_curve", "sol_out_curve", "tokens", "spend", "result")}
            elif e == "presend_live_disarm":
                disarm[k] = {x: r.get(x) for x in ("why", "slot", "t", "filled", "attempts", "armed_ms", "rearm", "trig_slot")}
    out = []; pool = []
    for key, tries in atts.items():
        for a in tries:
            L = lands.get(a["sig"])
            if L and L.get("first_rx") and a.get("t"): pool.append((L["res"], (L["first_rx"] - a["t"]) / 1e6))
            elif L and L.get("res") == "unseen": pool.append(("unseen", None))
    for key, a in arms.items():
        if lo and (a["t_arm"] or 0) < lo: continue
        if hi and (a["t_arm"] or 0) > hi: continue
        tries = []
        for x in atts.get(key, []):
            x = dict(x); x["land"] = lands.get(x["sig"]); tries.append(x)
        tries.sort(key=lambda x: x["t"] or 0)
        out.append({"ses": key[0], "w": key[1], **a, "tries": tries, "fill": fills.get(key), "pnl": (real[key] / 1e9) if key in nreal else None,
                    "n_real": nreal[key], "close": close.get(key), "disarm": disarm.get(key)})
    return out, pool, cfg


if __name__ == "__main__":
    tag, src = sys.argv[1], sys.argv[2]
    lo = pkt(sys.argv[3]) if len(sys.argv) > 3 else None
    hi = pkt(sys.argv[4]) if len(sys.argv) > 4 else None
    o, pool, cfg = scan(src, lo, hi)
    pickle.dump({"wins": o, "pool": pool, "cfg": cfg}, open(f"{OUT}/win_{tag}.pkl", "wb"))
    k = collections.Counter(x["kind"] for x in o)
    nf = sum(1 for x in o if x["fill"])
    print(f"{tag}: armed {len(o)} {dict(k)} filled {nf} realized {sum(x['pnl'] or 0 for x in o):+.4f} tries {sum(len(x['tries']) for x in o)} "
          f"pool {len(pool)} sessions {len(cfg)} drops {cfg}", flush=True)
