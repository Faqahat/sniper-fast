#!/usr/bin/env python3
"""LIVE28: the replay's inputs, built once (read-only): run 28's records, the tape, the clock, landing pools (P3 = the validated
LAST_HOUR model; R28 = run 28's own full live windows), the exit model (s48lib.ModelN over probes 1-3, as LAST_HOUR), the view
model, the settings (run 28's run_start, pace slot measured on its tries), the window lists:
  live : the armed live windows before the cut (phase, QUIET signals, live stop time, live outcome MEASURED)
  skip : the triggers QUIET skipped before the cut"""
import sys, os, json, pickle, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib28 as L
import rlib, sim, s48lib, variants

SMS = rlib.SMS


def s48_clock():
    """the chain clock of the s48 tape (covers probes 1-3): ModelN measures the probes' view jitter on it (as lasthour.py)"""
    S = np.load(f"{s48lib.TAB48}/slots.npy")
    slot0 = int(S["slot"][0]); n = int(S["slot"][-1]) - slot0 + 1
    bs = np.zeros(n, np.int32); bs[S["slot"].astype(np.int64) - slot0] = S["maxi"].astype(np.int32) + 1
    return rlib.Clock(slot0, bs)


def setup():
    G = {}
    R = L.load_run(); ours = L.load_ours(); L.chain_fees(R, ours)
    tp = L.Tape28(R)
    G["R"] = R; G["tp"] = tp; G["ck"] = tp.clock()
    D27 = pickle.load(open(f"{L.DATA}/donors28.pkl", "rb"))
    D3 = pickle.load(open(f"{s48lib.S48}/donors123.pkl", "rb"))
    G["land"] = {"P3": sim.Landing(D3, probes=("P3",)), "R28": sim.Landing(D27, probes=("R28",))}
    G["model"] = s48lib.ModelN(D3, s48_clock(), ("P1", "P2", "P3"))
    G["view"] = sim.View()
    slot_ms, ngap = L.pace_slot(R)
    G["slot_ms"] = slot_ms
    G["cfg"] = L.cfg28(R, slot_ms)
    Q = json.load(open(f"{L.DATA}/qcheck.json"))
    G["qdelta_pool"] = np.array([s["d"] - s["t6"] for s in Q["stops"]])
    idm = tp.id_map()
    live = []
    for w, x in R["W"].items():
        tr = x["arm"]["trig"]; dz = x["disarm"]; q = x["arm"].get("quiet") or {}
        d_stop = (dz["t"] - tr["t"]) / 1e6 if dz.get("quiet_stop") else None
        live.append(L.trig_dict(tp, tr, probe="R28", w=w, phase=L.period(tr["t"]), all4=bool(q.get("all4")),
                                d_stop=d_stop, stop_filled=(d_stop is not None and x["fill"] is not None), live=dict(filled=x["fill"] is not None, pnl=x["pnl"], rb=x["rb"], fee=x["fee_eng"], fee_chain=x["fee_chain"],
                                                         net=x["net"], why=dz["why"], exit=(x["close"] or {}).get("exit_why"))))
    skip = []
    for s in R["skips"]:
        if s.get("why") != "quiet": continue
        skip.append(L.trig_dict(tp, s["trig"], probe="SKIP", w=None, phase=L.period(s["trig"]["t"]), all4=True, d_stop=None, live=None))
    G["live"] = live; G["skip"] = skip
    G["whale_ids"] = {x["whale_b58"]: idm.get(x["whale_b58"], -1) for x in live + skip}
    G["our_id"] = tp.our_id
    spans = variants.spans_for(live + skip)
    G["store"] = sim.build_store(tp, spans)
    return G
