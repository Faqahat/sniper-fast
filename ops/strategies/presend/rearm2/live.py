#!/usr/bin/env python3
"""MEASURED live pre-send per run: windows (arm / skip / disarm), fills with realized P&L, rent back, exit kind, sell landing,
failed landed tries (fee). Out: live_<name>.pkl"""
import sys, json, pickle, collections
RUNS = {"f28": "/home/moiz/sniper-data/runs/fra/runs/dip_r28.jsonl", "a34": "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r34.jsonl",
        "a35": "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/rearm2/live/dip_ams_r35.jsonl"}
EVS = ("run_start", "presend_live_arm", "presend_live_skip", "presend_live_disarm", "presend_live_fill", "presend_live_realized",
       "presend_live_close", "presend_live_ata_close", "presend_attempt_land", "run_end")

def parse(fn):
    R = dict(arms={}, skips=[], dis={}, fills=collections.defaultdict(list), real={}, close={}, ata=[], tries=[], t0=None, t1=None, cfg=None)
    for l in open(fn, errors="ignore"):
        if '"ev":"' not in l: continue
        ev = l.split('"ev":"', 1)[1].split('"', 1)[0]
        if ev not in EVS: continue
        r = json.loads(l)
        t = r.get("t")
        if ev == "run_start": R["t0"] = t; R["cfg"] = r.get("presend_live"); continue
        if t: R["t1"] = t if R["t1"] is None else max(R["t1"], t)
        if ev == "presend_live_arm": R["arms"][r["w"]] = r
        elif ev == "presend_live_skip": R["skips"].append(r)
        elif ev == "presend_live_disarm": R["dis"][r["w"]] = r
        elif ev == "presend_live_fill": R["fills"][r["w"]].append(r)
        elif ev == "presend_live_realized": R["real"][r["w"]] = r
        elif ev == "presend_live_close": R["close"][r["w"]] = r
        elif ev == "presend_live_ata_close": R["ata"].append(r)
        elif ev == "presend_attempt_land": R["tries"].append((r.get("w"), r.get("res"), r.get("fee"), r.get("slot"), r.get("t_send")))
    return R

def summary(R):
    fills = []
    used = set()
    for w, fl in R["fills"].items():
        f = fl[0]; rz = R["real"].get(w) or {}; cl = R["close"].get(w) or {}
        rb = 0
        for q, z in enumerate(R["ata"]):
            if q in used: continue
            if z["mint"] == f["mint"] and z.get("slot", 0) >= f["slot"]: rb = z.get("delta") or 0; used.add(q); break
        sl = cl.get("sell_lands") or []
        fills.append(dict(w=w, mint=f["mint"], slot=f["slot"], idx=f["idx"], t=f["t"], pnl=rz.get("pnl"), rent=rb, curve=cl.get("curve_pnl"),
                          why=cl.get("exit_why"), sell=(sl[-1][0], sl[-1][1]) if sl else None, spend=cl.get("spend"), client=f.get("client"),
                          trig=(R["arms"].get(w) or {}).get("trig"), merged=cl.get("merged")))
    nfail = sum(1 for x in R["tries"] if x[1] not in ("ok", "unseen", None))
    ffee = sum((x[2] or 5120) for x in R["tries"] if x[1] not in ("ok", "unseen", None))
    return fills, nfail, ffee

if __name__ == "__main__":
    for name in sys.argv[1:]:
        R = parse(RUNS[name]); fills, nfail, ffee = summary(R)
        pnl = sum(f["pnl"] or 0 for f in fills); rent = sum(f["rent"] for f in fills); cur = sum(f["curve"] or 0 for f in fills)
        tries = len(R["tries"])
        print(f"{name}: arms {len(R['arms'])} skips {len(R['skips'])} (quiet {sum(1 for s in R['skips'] if s.get('why') == 'quiet')}) fills {len(fills)} "
              f"realized {pnl/1e9:+.3f} rent {rent/1e9:+.3f} failed tries {nfail}/{tries} fee {ffee/1e9:.3f} NET {(pnl+rent-ffee)/1e9:+.3f} | curve {cur/1e9:+.3f} "
              f"| per-fill non-curve cost {(cur-pnl-rent)/1e6/max(len(fills),1):.2f} mSOL | exits {collections.Counter(f['why'] for f in fills)}")
        pickle.dump(dict(R=R, fills=fills, nfail=nfail, ffee=ffee), open(f"/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/rearm2/live_{name}.pkl", "wb"))
