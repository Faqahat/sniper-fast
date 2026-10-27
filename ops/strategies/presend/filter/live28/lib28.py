#!/usr/bin/env python3
"""LIVE28 (read-only, offline): shared pieces for the QUIET counterfactual of AMS run 28 (dip21, QUIET on from the start via the host's whale book).
  * the run's records per live window (MEASURED: arm, disarm incl. QUIET's decided / others, tries and their landing, fill, exit,
    sell, realized, token-account rent back) and the QUIET skips;
  * the chain tape of the run (live28/tab: decode.py + build.py of FRA's recording, 18:17 -> 22:05+ PKT) with OUR pre-send fills and
    sells removed (the replay puts its own buy in; every other trade, our regular M2 trades included, stays as the market);
  * run 28's own live tries as landing donors (built exactly as real/p3donors.py builds probe 3's);
  * the settings from run 28's run_start, the pace slot measured on its tries.
Nothing here sends, starts or stops anything."""
import sys, os, json, pickle, collections, hashlib
import numpy as np

REAL = "/home/moiz/sniper/ops/strategies/presend/real"
sys.path.insert(0, REAL)
import rlib
DATA = "/home/moiz/sniper-data/presend_filter/live28"
TAB = f"{DATA}/tab"
rlib.TAB = TAB                    # donors.build / variants read rlib.TAB
import sim, s48lib, donors as DN

R28 = "/home/moiz/sniper-data/presend_filter/live28/dip_ams_r28.jsonl"     # FINAL snapshot (sudo cat) after the run ended 22:03:02 PKT; md5 e7cacd3d96d3e08491a28d64cf199c02 (= server)
CUT_NS = (int(os.environ['LIVE28_CUT']) * 10**9) if os.environ.get('LIVE28_CUT') else None   # trial runs only; final: no cut: the tape covers the whole run (the mid-run 21:23 cut version is in DATA/mid2123/)
WALLET = "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"          # AMS live wallet (public key)
RULE_ON_NS = None                                                   # filled by load_run (first armed window with rule_on)
PKT = 18000


def sh(s): return int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "little")


def hm(ns, f="%H:%M:%S"):
    import time
    return time.strftime(f, time.gmtime(int(ns / 1e9) + PKT))


# ---------------------------------------------------------------------------------------------------------------------------
def load_run(path=R28, cut_ns=CUT_NS):
    """run 28's pre-send records per live window (MEASURED). net = realized + rent back - failed-try fees (engine-logged, as
    eval_live.py); fee_chain = the same tries' fees as found on chain (incl. tries the engine logged unseen)."""
    W = collections.OrderedDict(); atts = {}; lands = {}; skips = []; shadow = collections.defaultdict(dict)
    fills = {}; exits = {}; sells = {}; closes = {}; realized = {}; ata = collections.defaultdict(list); start = stop = None; dumps = []
    for line in open(path, errors="ignore"):
        if '"presend' not in line and '"run_start"' not in line and '"dump"' not in line: continue
        try: r = json.loads(line)
        except Exception: continue                       # the live file's last line may be cut
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
        elif ev == "presend_live_ata_close": ata[r["mint"]].append(r)
        elif ev == "presend_live_stop": stop = r
        elif ev == "dump": dumps.append(r)
        elif ev in ("presend_arm", "presend_fill", "presend_exit", "presend_disarm"):
            shadow[ev][(r["mint"], r["w"], r.get("row"))] = r
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
    global RULE_ON_NS
    on = [x["arm"]["trig"]["t"] for x in W.values() if (x["arm"].get("quiet") or {}).get("rule_on")]
    RULE_ON_NS = min(on) if on else None
    W_all = W
    if cut_ns is not None:
        W = collections.OrderedDict((w, x) for w, x in W_all.items() if x["arm"]["trig"]["t"] < cut_ns)
        skips = [s_ for s_ in skips if s_["trig"]["t"] < cut_ns]
    return dict(start=start, stop=stop, W=W, W_all=W_all, skips=skips, shadow=shadow, dumps=dumps, cut_ns=cut_ns)


def chain_fees(R, ours):
    """per window: failed-try fees as found on chain (every try of ours that landed with an error; MEASURED)"""
    for w, x in R["W"].items():
        f = 0
        for a in x["atts"]:
            o = ours.get(a["sig"])
            if o is not None and o.get("err") is not None: f += o.get("fee") or 5120
        x["fee_chain"] = f


def load_ours():
    ours = {}
    for l in open(f"{TAB}/ours.jsonl"):
        r = json.loads(l); ours[r["sig"]] = r
    return ours


# ---------------------------------------------------------------------------------------------------------------------------
class Tape28(rlib.Tape):
    """the run-28 tape (to the cut); our pre-send fills and sells (and any landed buy of a try) removed"""
    def __init__(self, R):
        super().__init__(tab=TAB, with_ours=False)
        self.skip_sigh = set(); n = 0
        for x in R["W_all"].values():
            if x["fill"]: self.skip_sigh.add(sh(x["fill"]["sig"])); n += 1
            if x["sell"]: self.skip_sigh.add(sh(x["sell"]["sig"])); n += 1
            for a in x["atts"]:
                if (a["land"] or {}).get("res") == "ok": self.skip_sigh.add(sh(a["sig"]))
        # every sell signature of every round (presend_live_close sell_sigs)
        for x in R["W_all"].values():
            for s in ((x["close"] or {}).get("sell_sigs") or []):
                self.skip_sigh.add(sh(s[0]))
        self.n_skip = len(self.skip_sigh)
        self.our_id = self.id_map().get(WALLET)


def cfg28(R, slot_ms):
    c = R["start"]["presend_live"]; rate = c["path_max_per_sec"]
    cfg = sim.Cfg(slot_ms=slot_ms, size=c["spend"], k=c["k"], drop=c["drop"], deadline_slots=c["deadline_slots"], window_slots=c["window_slots"],
                  live_ms=c["live_ms"], whale_sell_ms=c["whale_sell_ms"], paths=[(rate, rate)], global_rate=c["max_per_sec"], exit_slots=c["exit_slots"],
                  tp=c["tp"], sl=c["sl"], whale_pct=c["whale_pct"], create_slot=c["create_slot"], one_position=c["one_position"])
    cfg.cost = sim.Cost(fail_fee=c["fail_fee"])
    return cfg


def pace_slot(R):
    """the engine's pace slot (ms): k x the modal gap between a window's consecutive tries (MEASURED, as p3check.pace_slot)"""
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


# ---------------------------------------------------------------------------------------------------------------------------
def build_donors(tp, R, ours):
    """run 28's live tries as landing donors (exactly p3donors.build_p3's fields)"""
    cfg = R["start"]["presend_live"]
    wins = []
    for w, x in R["W"].items():
        tr = x["arm"]["trig"]; ct = tp.cc(tr["slot"], tr["idx"]); t0 = tr["t"]
        tries = []
        for a in x["atts"]:
            L = a["land"] or {}
            d = (a["t"] - t0) / 1e6
            o = ours.get(a["sig"])
            res = L.get("res"); slot = L.get("slot"); idx = L.get("idx"); src = "live"
            if res in (None, "unseen") or slot is None:
                if o is not None:
                    res = DN.classify(o.get("err")); slot = o["s"]; idx = o["i"]; src = "chain"
                else:
                    covered = all(tp.nblk(s) > 0 for s in range(a["slot"], a["deadline"] + 4))
                    res = "drop" if covered else "unknown"; slot = None; idx = None; src = "none"
            lam = (tp.cc(slot, idx) - ct - d) if slot is not None else None
            g = ct + d - (a["slot"] + 0.5) * rlib.SMS
            tries.append(dict(n=a["n"], d=d, send_slot=a["slot"], deadline=a["deadline"], en_slot=a["en_slot"], lim=a["lim"], p=a["p"], pos=a["pos"],
                              slot=slot, idx=idx, res=res, src=src, lam=lam, g=g, client=a["client"], sig=a["sig"], path=a.get("path"),
                              t_send=a["t"], ms_rx=L.get("ms_send_to_rx"), sas=L.get("slots_after_send"),
                              fee=(L.get("fee") if L.get("fee") is not None else (o or {}).get("fee"))))
        wins.append(dict(probe="R28", w=w, mint=tr["mint"], trig=tr, ct=ct, en_slot=x["arm"]["en_slot"], tries=tries, disarm=x["disarm"], fill=x["fill"],
                         exit=x["exit"], sell=x["sell"], close=x["close"], realized=x["realized"]))
    D = {"R28": dict(cfg=cfg, wins=wins, start=R["start"], stop=R["stop"], shadow=R["shadow"], dumps=R["dumps"], skips=R["skips"])}
    DN.view_quantile(D, tp, sim.View())
    return D


# ---------------------------------------------------------------------------------------------------------------------------
def whale_sell(tp, mint, slot, idx, j, whale_b58):
    """the whale's first sell after the trigger on the tape (chain order) -> (slot, idx) or None"""
    idm = tp.id_map(); mid = idm.get(mint); wid = idm.get(whale_b58)
    if mid is None or mid not in tp.span or wid is None: return None
    a, e = tp.span[mid]
    for k in range(a, e):
        if (tp.s[k], tp.i[k], tp.j[k]) <= (slot, idx, j): continue
        if tp.user[k] == wid and not tp.buy[k]: return (int(tp.s[k]), int(tp.i[k]))
    return None


def trig_dict(tp, tr, **kw):
    """a trigger record (presend_live_arm / _skip 'trig') -> the simulator's window dict"""
    d = dict(mint=tr["mint"], slot=tr["slot"], idx=tr["idx"], j=tr.get("j", 0), age_slots=tr["age_slots"], v2=True, cashback=False,
             whale_b58=tr["wallet"], whale_sell=whale_sell(tp, tr["mint"], tr["slot"], tr["idx"], tr.get("j", 0), tr["wallet"]),
             t_ns=tr["t"], pct=tr["pct"], sig=tr["sig"])
    d.update(kw)
    return d


PERIODS = ((1793106000, "18-19"), (1793109600, "19-20"), (1793113200, "20-21"), (1793116800, "21-22"))   # PKT hour blocks; 21-22 includes 22:00-22:03


def period(t_ns):
    """the hour block of a trigger (reporting only; nothing is chosen on it)"""
    t = t_ns / 1e9; lab = PERIODS[0][1]
    for t0, name in PERIODS:
        if t >= t0: lab = name
    return lab

# windows next to the recording hole at 19:06-19:08 PKT (slots 462098144-462098147 and 462098631 not recorded although the engine
# saw dumps there): w94 (trigger slot 462098148) and w98 (trigger 462098619; its exit could reach 462098631). Sensitivity only.
HOLE_WINDOWS = (94, 98)
HOLE_SLOTS = (462098144, 462098145, 462098146, 462098147, 462098631)
