#!/usr/bin/env python3
"""DENSITY (read-only, offline): shared pieces for the 'more tries per block / more send paths / 2 positions' replay of AMS
pre-send runs 24-28. Generalises filter/live28/lib28.py (run 28's QUIET study) to every run:
  * a run's records per live window (MEASURED: arm, disarm incl. QUIET stops, tries and their landing, fill, exit, realized,
    rent back), its settings (run_start) and its pace slot (measured on its tries);
  * the run's chain tape (FRA's recording decoded with the unchanged real/decode.py + build.py) with OUR pre-send fills and sells
    removed (the replay puts its own buy in; every other trade stays as the market);
  * the window list (live armed windows; QUIET's live stops for r27/r28) and a 'dumped' flag per window (the tape's price fell
    >= 12% below the trigger price before the window's last slot: an opportunity, MEASURED on the tape).
Nothing here sends, starts or stops anything."""
import sys, os, json, collections, hashlib, math
import numpy as np

REAL = "/home/moiz/sniper/ops/strategies/presend/real"
sys.path.insert(0, REAL)
import rlib, sim, variants, donors as DN

DATA = "/home/moiz/sniper-data/presend_density"
WALLET = "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"          # AMS live wallet (public key)
RUNS = {
    24: dict(rec="/home/moiz/sniper-data/runs/ams/runs/dip_ams_r24.jsonl", tab=f"{DATA}/tab_r24"),
    25: dict(rec="/home/moiz/sniper-data/runs/ams/runs/dip_ams_r25.jsonl", tab=f"{DATA}/tab_r25"),
    26: dict(rec="/home/moiz/sniper-data/runs/ams/runs/dip_ams_r26.jsonl", tab=f"{DATA}/tab_r26"),
    27: dict(rec="/home/moiz/sniper-data/runs/ams/runs/dip_ams_r27.jsonl", tab="/home/moiz/sniper-data/presend_filter/live27/tab"),
    28: dict(rec="/home/moiz/sniper-data/presend_filter/live28/dip_ams_r28.jsonl", tab="/home/moiz/sniper-data/presend_filter/live28/tab"),
}
PKT = 18000


def sh(s): return int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "little")


def hm(ns, f="%H:%M"):
    import time
    return time.strftime(f, time.gmtime(int(ns / 1e9) + PKT))


def load_run(path):
    """lib28.load_run without the cut (MEASURED). net = realized + rent back - failed-try fees (engine-logged, as eval_live.py)"""
    W = collections.OrderedDict(); atts = {}; lands = {}; skips = []
    fills = {}; exits = {}; sells = {}; closes = {}; realized = {}; ata = collections.defaultdict(list); start = stop = None
    seg = 0; segs = []                                   # r24 restarted its engine 3 times: window ids restart, so key them per segment
    for line in open(path, errors="ignore"):
        if '"presend_live' not in line and '"presend_attempt' not in line and '"run_start"' not in line: continue
        try: r = json.loads(line)
        except Exception: continue
        ev = r.get("ev")
        if ev == "run_start":
            seg += 1; segs.append([int(r["t"]), None])
            if start is None or (r.get("presend_live") and not (start.get("presend_live"))): start = r
            continue
        if "w" in r and seg > 1: r["w"] = seg * 10000 + r["w"]
        if ev == "presend_live_disarm" and segs: segs[-1][1] = int(r["t"])
        if ev == "presend_live_arm": W[r["w"]] = dict(arm=r, disarm=None, atts=[], fill=None)
        elif ev == "presend_live_disarm":
            if r["w"] in W: W[r["w"]]["disarm"] = r
        elif ev == "presend_live_skip": skips.append(r)
        elif ev == "presend_attempt": atts[r["sig"]] = r
        elif ev == "presend_attempt_land": lands[r["sig"]] = r
        elif ev == "presend_live_fill": fills[r["w"]] = r
        elif ev == "presend_live_exit": exits[r["w"]] = r
        elif ev == "presend_live_sell_land": sells[r["w"]] = r
        elif ev == "presend_live_close": closes[r["w"]] = r
        elif ev == "presend_live_realized": realized[r["w"]] = r
        elif ev == "presend_live_ata_close": ata[r["mint"]].append(r)
        elif ev == "presend_live_stop": stop = r
    for sig, a in atts.items():
        a = dict(a); a["land"] = lands.get(sig)
        if a["w"] in W: W[a["w"]]["atts"].append(a)
    used = set()
    for w, x in W.items():
        x["atts"].sort(key=lambda a: a["t"])
        x["fill"] = fills.get(w); x["exit"] = exits.get(w); x["sell"] = sells.get(w); x["close"] = closes.get(w); x["realized"] = realized.get(w)
        rb = 0
        if x["fill"]:
            for q, z in enumerate(ata.get(x["fill"]["mint"], [])):
                if (x["fill"]["mint"], q) in used: continue
                if z.get("slot", 0) >= x["fill"]["slot"]: rb = z.get("delta", 0); used.add((x["fill"]["mint"], q)); break
        x["rb"] = rb
        x["pnl"] = (x["realized"] or {}).get("pnl", 0) if x["fill"] else 0
        x["fee_eng"] = sum((a["land"] or {}).get("fee") or 5120 for a in x["atts"]
                           if a["land"] and a["land"].get("err") and a["land"].get("res") != "unseen")
        x["net"] = x["pnl"] + x["rb"] - x["fee_eng"]
    W = collections.OrderedDict((w, x) for w, x in W.items() if x["disarm"] is not None)
    hours = sum((b - a) / 3.6e12 for a, b in segs if b)
    return dict(start=start, stop=stop, W=W, skips=skips, hours=hours, nseg=seg)


class TapeR(rlib.Tape):
    """a run's tape; our pre-send fills and sells (and any landed buy of a try) removed"""
    def __init__(self, tab, R):
        super().__init__(tab=tab, with_ours=False)
        self.skip_sigh = set()
        for x in R["W"].values():
            if x["fill"]: self.skip_sigh.add(sh(x["fill"]["sig"]))
            if x["sell"]: self.skip_sigh.add(sh(x["sell"]["sig"]))
            for a in x["atts"]:
                if (a["land"] or {}).get("res") == "ok": self.skip_sigh.add(sh(a["sig"]))
            for s in ((x["close"] or {}).get("sell_sigs") or []):
                self.skip_sigh.add(sh(s[0]))
        self.our_id = self.id_map().get(WALLET)


def pace_slot(R):
    """the engine's pace slot (ms): k x the modal gap between a window's consecutive tries (MEASURED, as lib28.pace_slot)"""
    k = R["start"]["presend_live"]["k"]; gaps = []
    for x in R["W"].values():
        d = sorted(a["t"] / 1e6 for a in x["atts"])
        gaps += list(np.diff(d))
    g = np.array(gaps); lo, hi = 212.0 / k * 0.6, 212.0 / k * 1.4
    g = g[(g > lo) & (g < hi)]
    h, e = np.histogram(g, bins=np.arange(lo, hi, 0.1))
    mode = e[np.argmax(h)] + 0.05
    sel = g[np.abs(g - mode) < 0.6]
    return float(np.median(sel) * k), len(sel)


def live_spend(R):
    """the size the run's tries really used (MEASURED: the attempts' spend; r24's run_start says 0.40, its tries 0.34)"""
    c = collections.Counter(a.get("spend") for x in R["W"].values() for a in x["atts"] if a.get("spend"))
    return c.most_common(1)[0][0] if c else R["start"]["presend_live"]["spend"]


def whale_sell(tp, mint, slot, idx, j, whale_b58):
    idm = tp.id_map(); mid = idm.get(mint); wid = idm.get(whale_b58)
    if mid is None or mid not in tp.span or wid is None: return None
    a, e = tp.span[mid]
    for k in range(a, e):
        if (tp.s[k], tp.i[k], tp.j[k]) <= (slot, idx, j): continue
        if tp.user[k] == wid and not tp.buy[k]: return (int(tp.s[k]), int(tp.i[k]))
    return None


def trig_dict(tp, tr, **kw):
    d = dict(mint=tr["mint"], slot=tr["slot"], idx=tr["idx"], j=tr.get("j", 0), age_slots=tr["age_slots"], v2=True, cashback=False,
             whale_b58=tr["wallet"], whale_sell=whale_sell(tp, tr["mint"], tr["slot"], tr["idx"], tr.get("j", 0), tr["wallet"]),
             t_ns=tr["t"], pct=tr["pct"], sig=tr["sig"])
    d.update(kw)
    return d


def dumped(tk, x, cfg):
    """MEASURED on the tape: an opportunity for a pre-send fill: before the window's last slot ends, the price fell >= drop below
    an earlier price of the window (a try's limit is the latest seen price x (1 - drop), so a fill needs such a fall)"""
    kt = max(tk.before(x["slot"], x["idx"] + 0.5), 0)
    hi = tk.vsol[kt] / tk.vtok[kt]
    en = int(math.floor((rlib.arr(x["slot"], x["idx"]) + cfg.live_ms + cfg.window_slots * rlib.SMS) / rlib.SMS))
    for k in range(kt + 1, tk.n):
        if tk.s[k] > en: break
        if tk.vtok[k] <= 0: continue
        p = tk.vsol[k] / tk.vtok[k]
        if p <= hi * (1.0 - cfg.drop): return True
        hi = max(hi, p)
    return False


def setup_run(run):
    """-> dict with the records, tape store, clock, cfg (live settings), window list"""
    spec = RUNS[run]
    R = load_run(spec["rec"])
    tp = TapeR(spec["tab"], R)
    c = R["start"]["presend_live"]
    slot_ms, _ = pace_slot(R)
    rate = c["path_max_per_sec"]
    cfg = sim.Cfg(slot_ms=slot_ms, size=live_spend(R), k=c["k"], drop=c["drop"], deadline_slots=c["deadline_slots"], window_slots=c["window_slots"],
                  live_ms=c["live_ms"], whale_sell_ms=c["whale_sell_ms"], paths=[(rate, rate)], global_rate=c["max_per_sec"], exit_slots=c["exit_slots"],
                  tp=c["tp"], sl=c["sl"], whale_pct=c["whale_pct"], create_slot=c["create_slot"], one_position=c["one_position"])
    cfg.cost = sim.Cost(fail_fee=c["fail_fee"])
    live = []
    for w, x in R["W"].items():
        tr = x["arm"]["trig"]; dz = x["disarm"]
        d_stop = (dz["t"] - tr["t"]) / 1e6 if dz.get("quiet_stop") else None
        live.append(trig_dict(tp, tr, probe=f"R{run}", w=w, run=run, d_stop=d_stop, stop_filled=(d_stop is not None and x["fill"] is not None),
                              live=dict(filled=x["fill"] is not None, pnl=x["pnl"], rb=x["rb"], fee=x["fee_eng"], net=x["net"], why=dz["why"],
                                        n_att=len(x["atts"]), fill_path=(x["fill"] or {}).get("path"))))
    idm = tp.id_map()
    whale_ids = {x["whale_b58"]: idm.get(x["whale_b58"], -1) for x in live}
    store = sim.build_store(tp, variants.spans_for(live))
    for x in live:
        x["dumped"] = dumped(store[x["mint"]], x, cfg)
    t1 = max(x["disarm"]["t"] for x in R["W"].values())
    return dict(run=run, R=R, ck=tp.clock(), store=store, cfg=cfg, slot_ms=slot_ms, live=live, whale_ids=whale_ids, our_id=tp.our_id,
                hours=R["hours"], start_ns=int(R["start"]["t"]), end_ns=t1, skips=len(R["skips"]))
