#!/usr/bin/env python3
"""REPLAY_065 step 1 (read-only, offline): parse AMS runs 24 and 25 (engine dip19) into per-trade structures.
Inputs: local copies of /root/prod/runs/dip_ams_r{24,25}.{log,jsonl} (pulled with sudo cat, md5 checked).
Every number here is MEASURED (the engine's own records). Window / attempt ids restart at each engine start, so every
key carries the segment number (one segment = one run_start).
Writes /home/moiz/sniper-data/replay065/live.pkl"""
import json, re, collections, pickle, sys

LIVE = "/home/moiz/sniper-data/replay065/live"
OUT = "/home/moiz/sniper-data/replay065/live.pkl"
RUNS = ("r24", "r25")


def load(run):
    seg = 0
    R = dict(run=run, segs=[], ps=collections.OrderedDict(), att={}, land={}, skips=[], tape=collections.defaultdict(list),
             sh_arm={}, sh_fill=[], sh_exit=[], sh_disarm={}, sh_skip=[], fires=[], reg_tape=collections.defaultdict(list),
             buy_land={}, buy_failed={}, land_poll={}, reg_exit={}, reg_sell={}, reg_close={}, stops=[], run_end=[], dumps={})
    for line in open(f"{LIVE}/dip_ams_{run}.jsonl"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        ev = r.get("ev")
        if ev == "run_start":
            seg += 1
            R["segs"].append(dict(seg=seg, t=r["t"], ps_spend=(r.get("presend_live") or {}).get("spend"), ps_cfg=r.get("presend_live"),
                                  sh_cfg=r.get("presend"), spend=r.get("spend"), guard=r.get("guard"), hold=r.get("hold_slots"), tp=r.get("tp"),
                                  sl=r.get("sl"), dev_spend=r.get("dev_spend")))
            continue
        r["seg"] = seg
        if ev == "presend_live_arm":
            R["ps"][(seg, r["w"])] = dict(seg=seg, w=r["w"], arm=r, disarm=None, fills=[], exits=[], sells=[], close=None, realized=None, ata_close=None)
        elif ev == "presend_live_disarm":
            R["ps"][(seg, r["w"])]["disarm"] = r
        elif ev == "presend_live_skip":
            R["skips"].append(r)
        elif ev == "presend_attempt":
            R["att"][r["sig"]] = r
        elif ev == "presend_attempt_land":
            R["land"][r["sig"]] = r
        elif ev == "presend_live_fill":
            R["ps"][(seg, r["w"])]["fills"].append(r)
        elif ev == "presend_live_exit":
            R["ps"][(seg, r["w"])]["exits"].append(r)
        elif ev == "presend_live_sell_land":
            R["ps"][(seg, r["w"])]["sells"].append(r)
        elif ev == "presend_live_close":
            R["ps"][(seg, r["w"])]["close"] = r
        elif ev == "presend_live_realized":
            R["ps"][(seg, r["w"])]["realized"] = r
        elif ev == "presend_live_ata_close":
            # keyed by mint: the close of the pre-send token account (rent back)
            R.setdefault("ata_close", []).append(r)
        elif ev == "presend_live_tape":
            R["tape"][(seg, r["mint"])].append(r)
        elif ev == "presend_live_stop":
            R["stops"].append(r)
        elif ev == "presend_arm":
            R["sh_arm"][(seg, r["w"])] = r
        elif ev == "presend_fill":
            R["sh_fill"].append(r)
        elif ev == "presend_exit":
            R["sh_exit"].append(r)
        elif ev == "presend_disarm":
            R["sh_disarm"][(seg, r["w"])] = r
        elif ev == "presend_skip":
            R["sh_skip"].append(r)
        elif ev == "fire":
            R["fires"].append(r)
        elif ev == "buy_land":
            R["buy_land"][(seg, r["mint"], r["sig"])] = r
        elif ev == "buy_failed":
            R["buy_failed"][(seg, r["mint"], r["sig"])] = r
        elif ev == "land_poll":
            R["land_poll"][(seg, r["mint"], r["sig"])] = r
        elif ev == "exit":
            R["reg_exit"].setdefault((seg, r["mint"]), []).append(r)
        elif ev == "sell_land":
            R["reg_sell"].setdefault((seg, r["mint"]), []).append(r)
        elif ev == "close":
            R["reg_close"].setdefault((seg, r["mint"]), []).append(r)
        elif ev == "tape":
            R["reg_tape"][(seg, r["mint"])].append(r)
        elif ev == "run_end":
            R["run_end"].append(r)
        elif ev == "dump":
            if r.get("sig"):
                R["dumps"][r["sig"]] = dict(slot=r.get("slot"), idx=r.get("idx"), mint=r.get("mint"))
    # the log: realized lines (in order), start balances, shadow status lines
    R["log_ps_real"] = []; R["log_reg_real"] = []; R["start_bal"] = []; R["sh_line"] = []
    seg = 0
    for line in open(f"{LIVE}/dip_ams_{run}.log", errors="replace"):
        if line.startswith("snipe_engine: payer"):
            seg += 1
        m = re.search(r"PRESEND LIVE REALIZED (\S+) ([+-][0-9.]+) SOL", line)
        if m: R["log_ps_real"].append((seg, m.group(1), float(m.group(2))))
        m = re.search(r"REALIZED mint=(\S+) pnl=([+-][0-9.]+) SOL", line)
        if m: R["log_reg_real"].append((seg, m.group(1), float(m.group(2))))
        m = re.search(r"START BALANCE ([0-9.]+) SOL", line)
        if m: R["start_bal"].append((seg, float(m.group(1))))
        if line.startswith("=== DIP PRESEND:"):
            m = re.search(r"fills (\d+)/(\d+)/(\d+) exits (\d+)/(\d+)/(\d+) gross ([+-][0-9.]+)/([+-][0-9.]+)/([+-][0-9.]+) SOL net\(cheap, 20/slot\) ([+-][0-9.]+)/([+-][0-9.]+)/([+-][0-9.]+)", line)
            if m: R["sh_line"].append((seg, [int(x) for x in m.groups()[:6]], [float(x) for x in m.groups()[6:]]))
    return R


def presend_fills(R):
    """one row per pre-send position (MEASURED)"""
    out = []
    for key, W in R["ps"].items():
        if not W["fills"]:
            continue
        seg, w = key
        f = W["fills"][0]
        rz = W["realized"] or {}
        cl = W["close"] or {}
        ac = next((a for a in R.get("ata_close", []) if a["seg"] == seg and a["mint"] == f["mint"] and a.get("slot", 0) >= f["slot"]), None)
        out.append(dict(run=R["run"], seg=seg, w=w, mint=f["mint"], n_fills=len(W["fills"]), fill=f, fills=W["fills"], exits=W["exits"], sells=W["sells"],
                        close=cl, realized=rz.get("pnl"), real_rec=rz, ata_close=ac, arm=W["arm"], disarm=W["disarm"]))
    return out


if __name__ == "__main__":
    D = {}
    for run in RUNS:
        R = load(run)
        D[run] = R
        F = presend_fills(R)
        n_multi = sum(1 for x in F if x["n_fills"] > 1)
        print(run, "segments", [(s["seg"], s["ps_spend"], s["spend"], s["guard"], s["hold"]) for s in R["segs"]], "start balances", R["start_bal"])
        print("   pre-send positions", len(F), "multi-fill", n_multi, "realized sum %+.4f" % (sum(x["realized"] or 0 for x in F) / 1e9),
              "log realized n", len(R["log_ps_real"]), "sum %+.4f" % sum(p for _, _, p in R["log_ps_real"]))
        print("   regular fires", len(R["fires"]), "buy_land", len(R["buy_land"]), "log REALIZED n", len(R["log_reg_real"]), "sum %+.4f" % sum(p for _, _, p in R["log_reg_real"]))
        print("   shadow: arms", len(R["sh_arm"]), "fills", len(R["sh_fill"]), "exits", len(R["sh_exit"]), "status-end lines", R["sh_line"])
    pickle.dump(D, open(OUT, "wb"))
    print("wrote", OUT)
