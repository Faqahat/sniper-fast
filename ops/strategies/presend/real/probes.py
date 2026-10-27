#!/usr/bin/env python3
"""REAL replay (10-25, read-only): load the two live pre-send probes into per-window structures.
Probe 1 = AMS run 16 (10-25 08:48-10:18 PKT, 0.2 SOL, whale >= 5%, k 4, 20/s caps).
Probe 2 = AMS run 17 (10-25 15:30-17:30 PKT, 0.35 SOL, whale >= 6%, k 8, 30/s caps).
Every number here is MEASURED from the engine's own records (presend_live_* / presend_attempt*)."""
import json, collections, os
RUNS = "/home/moiz/sniper-data/runs/ams/runs"
PROBES = {"P1": f"{RUNS}/dip_ams_r16.jsonl", "P2": f"{RUNS}/dip_ams_r17.jsonl"}
WALLET = "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"     # AMS live wallet (public key, not a secret)
SMS = 212.0

def arrival(s, i):
    """the engine's block-position clock (dip_model::arrival): slot x 212 + idx / max(400, idx + 1) x 212"""
    return s * SMS + i / max(400.0, i + 1.0) * SMS

def load(name):
    W = collections.OrderedDict(); atts = {}; lands = {}; skips = []; shadow = collections.defaultdict(dict)
    dumps = []; start = None; stop = None; fills = {}; exits = {}; sells = {}; closes = {}; realized = {}; tapes = collections.defaultdict(list)
    for line in open(PROBES[name]):
        try: r = json.loads(line)
        except Exception: continue
        ev = r.get("ev")
        if ev == "run_start": start = r
        elif ev == "presend_live_arm": W[r["w"]] = dict(arm=r, disarm=None, atts=[], fill=None)
        elif ev == "presend_live_disarm": W[r["w"]]["disarm"] = r
        elif ev == "presend_live_skip": skips.append(r)
        elif ev == "presend_attempt": atts[r["sig"]] = r
        elif ev == "presend_attempt_land": lands[r["sig"]] = r
        elif ev == "presend_live_fill": fills[r["w"]] = r
        elif ev == "presend_live_exit": exits[r["w"]] = r
        elif ev == "presend_live_sell_land": sells[r["w"]] = r
        elif ev == "presend_live_close": closes[r["w"]] = r
        elif ev == "presend_live_realized": realized[r["w"]] = r
        elif ev == "presend_live_tape": tapes[r["mint"]].append(r)
        elif ev == "presend_live_stop": stop = r
        elif ev == "dump": dumps.append(r)
        elif ev in ("presend_arm", "presend_fill", "presend_exit", "presend_disarm"):
            shadow[ev][(r["mint"], r["w"], r.get("row"))] = r
    for sig, a in atts.items():
        a = dict(a); a["land"] = lands.get(sig)
        W[a["w"]]["atts"].append(a)
    for w, x in W.items():
        x["atts"].sort(key=lambda a: a["t"])
        x["fill"] = fills.get(w); x["exit"] = exits.get(w); x["sell"] = sells.get(w); x["close"] = closes.get(w); x["realized"] = realized.get(w)
    return dict(name=name, start=start, stop=stop, W=W, skips=skips, shadow=shadow, dumps=dumps, tapes=tapes, n_att=len(atts), n_land=len(lands))

if __name__ == "__main__":
    for n in PROBES:
        P = load(n)
        W = P["W"]
        nf = sum(1 for x in W.values() if x["fill"])
        print(n, "windows", len(W), "fills", nf, "attempts", P["n_att"], "landed recs", P["n_land"], "skips", collections.Counter(s["why"] for s in P["skips"]),
              "disarms", collections.Counter((x["disarm"] or {}).get("why") for x in W.values()))
