#!/usr/bin/env python3
"""ASTRA A/B: which pre-send path lands our tries faster, and what that is worth (AMS run 38: helius-ps vs astralane-ps).

The engine alternates the tries of every armed window between the paths of its route (pslive.rs sender:
ri = (w.n + w.id) % len(route)), so with --presend-live-routes default=helius-ps+astralane-ps consecutive tries of the same
window go to different paths: a paired, within-run A/B. This tool reads a run's .jsonl (and optionally its .log) and prints:
  1. per path and per path x leader client: tries, skipped ticks, landed share, same-slot share, send->land p50/p75/p90 (ms and
     slots), ack failures, error classes; plus the "records" view that the hourly checks used so far (run 37 baseline);
  2. the fill race (fills by path vs each path's share of tries in the same windows);
  3. the first of our tries to land after each dump, when both paths had a try in flight (which path got there first, by how much);
  4. P&L of positions by the path of the filling try;
  5. paired per-window differences and cluster-bootstrap CIs (resampling whole windows) for the main metrics;
  6. a conversion to SOL (INFERRED): each path's measured send->land distribution fed into the calibrated landing-speed replay
     (ops/strategies/presend/speed35: s3_scen / s4_replay / s_sim). Two modes:
       base (default): the 911 calibrated r36+r37 windows (tapes on disk); every try's latency is mapped, per leader client, onto
                       the path's distribution (quantile mapping) -> "if ALL tries had path X's landing" vs the run's real mix.
       own  (--tab DIR): the analysed run's OWN windows on a tape decoded from the recorder chunks (--build-tab makes it).
MEASURED = counted from the records; INFERRED = model / replay.

Usage (read-only on the run files; never touches a server):
  astra_ab.py RUN.jsonl [--log RUN.log] [--last-hours H | --from 'YYYY-MM-DD HH:MM' --to ...  (PKT)] [--boot 2000] [--ci 0.90]
              [--sol base|own|off] [--tab DIR] [--procs 4] [--json OUT.json] [--no-clients]
  astra_ab.py --make-fake IN.jsonl OUT.jsonl [--fake-name fake-ps]   # test file: alternate tries of a one-path run relabelled
  astra_ab.py --build-tab RUN.jsonl OUTDIR [--procs 4]                # decode the recorder chunks of the run's span for --tab
Hourly check (owner's checks; copy the live file read-only first, never write on the server):
  ssh -p 1996 it@84.32.104.202 'sudo cat /root/prod/runs/dip_ams_r38.jsonl' > /home/moiz/sniper-data/lanes/r38.jsonl
  ssh -p 1996 it@84.32.104.202 'sudo cat /root/prod/runs/dip_ams_r38.log' > /home/moiz/sniper-data/lanes/r38.log
  python3 /home/moiz/sniper/ops/lanes/astra_ab.py /home/moiz/sniper-data/lanes/r38.jsonl --log /home/moiz/sniper-data/lanes/r38.log
  (add --last-hours 1 for the last hour only; --sol off for a 10-second read)"""
import sys, os, json, re, argparse, collections, datetime, math, pickle, subprocess, glob, time
import numpy as np

SMS = 213.0                       # ms per slot on the replay's chain clock (speed35 s3_scen, MEASURED)
SMS_A = 212.0                     # dip_model::arrival's slot length (block-position clock of the land records)
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
OURS8 = {o[:8] for o in OURS}
SPEED35 = "/home/moiz/sniper/ops/strategies/presend/speed35"
YOUNG = "/home/moiz/sniper/ops/strategies/presend/young"
REALD = "/home/moiz/sniper/ops/strategies/presend/real"
S35 = "/home/moiz/sniper-data/speed35"
BASE_RUNS = {"r36": "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r36.jsonl", "r37": f"{S35}/dip_ams_r37.jsonl"}
BASE_TPSL = {"r36": (0.20, 0.20), "r37": (0.15, 0.20)}   # speed35 s4_replay's values (kept so 'cur' equals its calibration)
SIZE = 0.696; COST_RT = 0.00352; SEEDS = 5
COLLECT = "/home/moiz/sniper-data/collect"
RES_ORDER = ["ok", "6042", "deadline", "ata_exists", "other", "unseen"]


def pkt(ns): return (datetime.datetime.fromtimestamp(ns / 1e9, datetime.UTC) + datetime.timedelta(hours=5)).strftime("%m-%d %H:%M")
def pkt_ns(s):
    d = datetime.datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=datetime.UTC) - datetime.timedelta(hours=5)
    return int(d.timestamp() * 1e9)
def arrival(s, i): return s * SMS_A + (i / max(400, i + 1)) * SMS_A
def lat_class(c):
    if c in ("AgaveBam", "FireBAM"): return "bam"
    if c.startswith("Harmonic"): return "harmonic"
    return {"JitoLabs": "jito", "Firedancer": "fd", "Frankendancer": "fd", "Agave": "agave", "": "unknown"}.get(c, "other")
def res_class(r): return r if r in RES_ORDER else "other"
def pq(a, ps=(50, 75, 90)):
    a = np.asarray([x for x in a if x is not None and x == x], float)
    return [float(np.percentile(a, p)) if len(a) else float("nan") for p in ps]
def fq(v, d=0): return "/".join(("-" if x != x else f"{x:.{d}f}") for x in v)
def fp(x, d=1): return "-" if x is None or x != x else f"{100 * x:.{d}f}%"
def wq(vals, wts, p):
    """weighted percentile (vals sorted ascending)"""
    cw = np.cumsum(wts)
    if len(cw) == 0 or cw[-1] <= 0: return float("nan")
    return float(vals[min(np.searchsorted(cw, p / 100.0 * cw[-1]), len(vals) - 1)])


# ------------------------------------------------------------------------------------------------------------------ loading
WANT = ('"ev":"presend_', '"ev":"dump"', '"ev":"run_start"', '"ev":"run_end"')

def parse_routes(spec):
    out = {}
    for part in (spec or "default=?").split(";"):
        part = part.strip()
        if not part or "=" not in part: continue
        c, lst = part.split("=", 1)
        out[c.strip()] = [x.strip() for x in re.split(r"[+,]", lst) if x.strip()]
    return out

def load(fn):
    """every record the A/B needs, keyed by engine segment (a new run_start = a new segment: window ids restart)"""
    R = {"starts": [], "att": [], "land": [], "arm": {}, "disarm": {}, "fill": [], "close": [], "real": [], "dumps": [], "skip": [], "bad": 0, "end": None}
    seg = -1
    with open(fn, errors="replace") as f:
        for line in f:
            if not any(k in line for k in WANT): continue
            try: r = json.loads(line)
            except Exception: R["bad"] += 1; continue
            ev = r.get("ev")
            if ev == "run_start": seg += 1; r["_seg"] = seg; R["starts"].append(r); continue
            if ev == "run_end": R["end"] = r; continue
            sg = max(seg, 0)
            if ev == "presend_attempt":
                R["att"].append({"seg": sg, "w": r.get("w"), "n": r.get("n"), "sig": r["sig"], "mint": r.get("mint"), "path": r.get("path"), "client": r.get("client") or "",
                                 "slot": r.get("slot"), "t": r.get("t"), "tip": r.get("tip"), "kind": r.get("kind", "t2"), "wst": r.get("w_status")})
            elif ev == "presend_attempt_land":
                d = r.get("d") or {}; x = r.get("x") or {}
                R["land"].append({"seg": sg, "w": r.get("w"), "n": r.get("n"), "sig": r["sig"], "mint": r.get("mint"), "path": r.get("path"), "client": r.get("client") or "",
                                  "res": r.get("res"), "err": r.get("err") or "", "fee": r.get("fee"), "send_slot": r.get("send_slot"), "t_send": r.get("t_send"),
                                  "ack": r.get("ack"), "ack_ms": r.get("ack_ms"), "first_rx": r.get("first_rx"), "msf": r.get("ms_send_to_first_rx"),
                                  "slot": r.get("slot"), "idx": r.get("idx"), "rx": r.get("t"), "sas": r.get("slots_after_send"), "ms": r.get("ms_send_to_rx"),
                                  "nb": r.get("n_between"),
                                  "d": ({k: d.get(k) for k in ("slot", "idx", "j", "t", "user", "sol", "drop_pct", "sig8", "p_rel")} if d and not d.get("buy") else None),
                                  "x": ({k: x.get(k) for k in ("slot", "idx", "j", "t", "user", "sol", "sig8", "p_rel")} if x and not x.get("buy") else None)})
            elif ev == "presend_live_arm":
                tr = r.get("trig") or {}
                k = (sg, r.get("w"))
                R["arm"][k] = {"mint": r.get("mint") or tr.get("mint"), "t": tr.get("t") or (r.get("dump") or {}).get("t") or r.get("t"), "slot": tr.get("slot") or (r.get("dump") or {}).get("slot"),
                               "kind": r.get("kind", "t2"), "en_slot": r.get("en_slot"), "trig_sig": tr.get("sig")}
            elif ev == "presend_live_disarm":
                R["disarm"][(sg, r.get("w"))] = {"t": r.get("t"), "why": r.get("why"), "attempts": r.get("attempts"), "filled": r.get("filled"), "slot": r.get("slot"), "kind": r.get("kind", "t2")}
            elif ev == "presend_live_fill":
                R["fill"].append({"seg": sg, "w": r.get("w"), "n": r.get("n"), "sig": r.get("sig"), "mint": r.get("mint"), "path": r.get("path"), "client": r.get("client") or "",
                                  "t": r.get("t"), "slot": r.get("slot"), "idx": r.get("idx"), "tip": r.get("tip"), "after_exit": r.get("after_exit"),
                                  "window_open": r.get("window_open"), "kind": r.get("kind", "t2"), "sat": r.get("slots_after_trigger"),
                                  "p_pre": r.get("p_entry_pre"), "p_sign": r.get("p_sign"), "ms": r.get("ms_send_to_rx")})
            elif ev == "presend_live_realized":
                R["real"].append({"seg": sg, "w": r.get("w"), "mint": r.get("mint"), "pid": r.get("pid"), "pnl": r.get("pnl"), "sigs": [b.get("sig") for b in r.get("buys") or []],
                                  "kind": r.get("kind", "t2")})
            elif ev == "presend_live_close":
                R["close"].append({"seg": sg, "w": r.get("w"), "mint": r.get("mint"), "path": r.get("path"), "buy_sigs": r.get("buy_sigs") or []})
            elif ev == "presend_live_skip":
                R["skip"].append({"seg": sg, "why": r.get("why"), "t": (r.get("trig") or {}).get("t")})
            elif ev == "dump":
                R["dumps"].append({"mint": r.get("mint"), "slot": r.get("slot"), "idx": r.get("idx"), "j": 0, "t": r.get("t"), "sol": int((r.get("sell") or 0) * 1e9),
                                   "drop_pct": r.get("drop_pct"), "user": None, "src": "dump"})
    return R

def run_cfg(R):
    """the active engine config (the last run_start that has a presend_live block)"""
    for r in reversed(R["starts"]):
        if r.get("presend_live"): return r["presend_live"], r
    return {}, (R["starts"][-1] if R["starts"] else {})

def time_cut(R, t_from, t_to):
    """keep the windows armed inside [t_from, t_to) and every record of those windows (by segment + window id)"""
    keep = {k for k, a in R["arm"].items() if a.get("t") and (t_from is None or a["t"] >= t_from) and (t_to is None or a["t"] < t_to)}
    # windows without an arm record (file cut at the start): keep by their first attempt time
    first = {}
    for a in R["att"]:
        k = (a["seg"], a["w"]); first[k] = min(first.get(k, a["t"]), a["t"])
    for k, t in first.items():
        if k not in R["arm"] and (t_from is None or t >= t_from) and (t_to is None or t < t_to): keep.add(k)
    S = dict(R)
    for key in ("att", "land", "fill", "real", "close"): S[key] = [x for x in R[key] if (x["seg"], x["w"]) in keep]
    S["arm"] = {k: v for k, v in R["arm"].items() if k in keep}; S["disarm"] = {k: v for k, v in R["disarm"].items() if k in keep}
    lo = t_from or 0; hi = t_to or 1 << 62
    S["dumps"] = [d for d in R["dumps"] if d["t"] and lo - 5e9 <= d["t"] < hi + 5e9]
    S["skip"] = [x for x in R["skip"] if x["t"] and lo <= x["t"] < hi]
    return S


# ------------------------------------------------------------------------------------------------------------------ status lines
def parse_status(logfn):
    """the 60 s status lines' pre-send part (cumulative): slot, sent, not-sent {reason: n}, trigger skips, per path counters, acks"""
    out = []
    if not logfn or not os.path.exists(logfn): return out
    with open(logfn, errors="replace") as f:
        for line in f:
            if "PRESEND LIVE" not in line or "not-sent {" not in line: continue
            m = re.search(r"DIP status:.*? slot (\d+)", line)
            s = {"slot": int(m.group(1)) if m else None}
            m = re.search(r"attempts sent (\d+)", line); s["sent"] = int(m.group(1)) if m else None
            m = re.search(r"not-sent (\{[^}]*\})", line)
            try: s["not_sent"] = json.loads(m.group(1)) if m else {}
            except Exception: s["not_sent"] = {}
            m = re.search(r"PRESEND LIVE[^:]*: triggers \d+ armed \d+ \(now \d+\) skips (\{[^}]*\})", line)
            try: s["trig_skips"] = json.loads(m.group(1)) if m else {}
            except Exception: s["trig_skips"] = {}
            m = re.search(r"per path sent/ok/6042/deadline/ata/other/unseen ([^|]*)\|", line); pp = {}
            if m:
                for part in m.group(1).split(","):
                    mm = re.match(r"\s*(\S+) (\d+)/(\d+)/(\d+)/(\d+)/(\d+)/(\d+)/(\d+)", part)
                    if mm: pp[mm.group(1)] = [int(mm.group(i)) for i in range(2, 9)]
            s["per_path"] = pp
            m = re.search(r"acks \{([^}]*)\}", line); ak = {}
            if m:
                for kv in m.group(1).split(","):
                    if ":" in kv: k, v = kv.split(":"); ak[k.strip()] = int(v)
            s["acks"] = ak
            out.append(s)
    return out

def status_delta(stats, slot_lo, slot_hi):
    """counts between the last status line at or before slot_lo and the last one at or before slot_hi (cumulative lines)"""
    st = [s for s in stats if s["slot"] is not None]
    if not st: return None
    hi = [s for s in st if s["slot"] <= slot_hi]; lo = [s for s in st if s["slot"] <= slot_lo]
    if not hi: return None
    h = hi[-1]; l = lo[-1] if lo else None
    def sub(a, b): return {k: v - (b or {}).get(k, 0) for k, v in a.items()}
    return {"slot_lo": l["slot"] if l else None, "slot_hi": h["slot"], "sent": h["sent"] - (l["sent"] if l else 0), "not_sent": sub(h["not_sent"], l["not_sent"] if l else {}),
            "trig_skips": sub(h["trig_skips"], l["trig_skips"] if l else {}), "acks": sub(h["acks"], l["acks"] if l else {}),
            "per_path": {p: [v[i] - (l["per_path"].get(p, [0] * 7)[i] if l else 0) for i in range(7)] for p, v in h["per_path"].items()}}


# ------------------------------------------------------------------------------------------------------------------ core tables
def unique_tries(R):
    """one row per signature (identical bytes sent twice = one tx): its first copy, its landing, whether its latency is unambiguous"""
    copies = collections.defaultdict(list)
    for a in R["att"]: copies[a["sig"]].append(a)
    lands = collections.defaultdict(list)
    for l in R["land"]: lands[l["sig"]].append(l)
    T = []
    for sig, cs in copies.items():
        cs.sort(key=lambda a: a["t"] or 0); a0 = cs[0]
        L = lands.get(sig, [])
        landed = [l for l in L if l["res"] != "unseen"]
        l = landed[0] if landed else (L[0] if L else None)
        amb = False
        if len(cs) > 1 and l is not None and l["res"] != "unseen" and l.get("t_send") != a0["t"]: amb = True
        row = {"sig": sig, "seg": a0["seg"], "w": a0["w"], "n": a0["n"], "mint": a0["mint"], "path": a0["path"], "client": a0["client"], "kind": a0["kind"],
               "t": a0["t"], "send_slot": a0["slot"], "copies": len(cs), "paths": {c["path"] for c in cs}, "has_land": l is not None, "amb": amb,
               "res": res_class(l["res"]) if l else "norec", "err": l["err"] if l else "", "landed": bool(landed), "slot": None, "idx": None, "rx": None,
               "ms": None, "msf": None, "sas": None, "ack": (l or {}).get("ack"), "ack_ms": (l or {}).get("ack_ms"), "d": None, "x": None, "fee": (l or {}).get("fee")}
        if landed:
            row.update(slot=l["slot"], idx=l["idx"], rx=l["rx"], d=l["d"], x=l["x"], nb=l.get("nb"))
            if not amb:
                row["ms"] = l["ms"]; row["msf"] = l["msf"]
                row["sas"] = l["sas"] if l["sas"] is not None else (l["slot"] - a0["slot"] if l["slot"] and a0["slot"] else None)
        T.append(row)
    return T

def baseline_view(R, p=print):
    """the records view used for the run 37 baseline: tries = attempt lines, landed = land records / tries, same-slot = same-slot
    land records / all land records, p50/p90 of ms_send_to_rx over non-unseen land records"""
    byp = collections.defaultdict(lambda: {"att": 0, "land": 0, "same": 0, "ms": []}); byc = collections.defaultdict(lambda: {"att": 0, "land": 0, "same": 0, "ms": []})
    for a in R["att"]: byp[a["path"]]["att"] += 1; byc[(a["path"], a["client"])]["att"] += 1
    for l in R["land"]:
        for d in (byp[l["path"]], byc[(l["path"], l["client"])]):
            d["land"] += 1
            if l["res"] != "unseen":
                if l["sas"] == 0: d["same"] += 1
                if l["ms"] is not None: d["ms"].append(l["ms"])
    p("  RECORDS VIEW (as the r37 baseline was computed: duplicate sends and 'unseen' land records counted as records) [MEASURED]")
    for path, d in sorted(byp.items()):
        p(f"    {path:14s} tries {d['att']:6d} | land records / tries {fp(d['land'] / max(d['att'], 1))} | same-slot {fp(d['same'] / max(d['land'], 1))} | "
          f"send->land p50/p90 {fq(pq(d['ms'], (50, 90)))} ms")
    rows = sorted(byc.items(), key=lambda kv: (kv[0][0], -kv[1]["att"]))
    p(f"    {'path':14s} {'client':19s} {'tries':>6s} {'same-slot':>9s} {'p50/p90 ms':>11s}")
    for (path, c), d in rows:
        if d["att"] < 100: continue
        p(f"    {path:14s} {c or '?':19s} {d['att']:6d} {fp(d['same'] / max(d['land'], 1), 0):>9s} {fq(pq(d['ms'], (50, 90))):>11s}")

def tick_skips(R, routes):
    """INFERRED skipped ticks per path: a window's ticks are numbered n = 1, 2, ... (the sender numbers a tick BEFORE its skip
    checks), so a missing n is a tick that sent nothing; its path = route[(n + w) % len] (default class). Ticks after a window's
    last sent try are not visible."""
    rt = routes.get("default") or next(iter(routes.values()), ["?"])
    have = collections.defaultdict(set)
    for a in R["att"]: have[(a["seg"], a["w"])].add(a["n"])
    out = collections.Counter(); tot = 0
    for k, ns in have.items():
        mx = max(ns)
        for n in range(1, mx + 1):
            if n not in ns: out[rt[(n + k[1]) % len(rt)]] += 1; tot += 1
    return out, tot

def route_check(T, routes):
    """does every distinct try's path equal the engine's rule route[(n + w) % len]? (the alternation the A/B relies on; first copy)"""
    ok = bad = 0
    for a in T:
        rt = routes.get(lat_class(a["client"])) or routes.get("default")
        if not rt: continue
        if rt[(a["n"] + a["w"]) % len(rt)] == a["path"]: ok += 1
        else: bad += 1
    return ok, bad


# ------------------------------------------------------------------------------------------------------------------ races
def window_index(T):
    W = collections.defaultdict(list)
    for t in T: W[(t["seg"], t["w"])].append(t)
    return W

def dumps_by_window(R, T, W):
    """outside sells around each window: the land records' d (largest >= 2% drop in the 2 slots before a try) and x (the crossing
    trade), plus the engine's dump events of the mint between the arm and the disarm (+1 s). Our own wallets excluded."""
    out = {}
    dm = collections.defaultdict(list)
    for d in R["dumps"]: dm[d["mint"]].append(d)
    for k, ts in W.items():
        arm = R["arm"].get(k) or {}; dis = R["disarm"].get(k) or {}
        mint = ts[0]["mint"]
        t0 = min(t["t"] for t in ts); t1 = max((t["rx"] or t["t"]) for t in ts)
        if arm.get("t"): t0 = min(t0, arm["t"])
        if dis.get("t"): t1 = max(t1, dis["t"])
        D = {}
        for t in ts:
            for src in ("d", "x"):
                x = t.get(src)
                if x and x.get("slot") is not None and (x.get("user") or "")[:8] not in OURS8:
                    e = D.setdefault((x["slot"], x["idx"], x.get("j") or 0), {**x, "src": src})
                    if src == "x": e["cross"] = True
        for d in dm.get(mint, []):
            if d["t"] and t0 - 1e9 <= d["t"] <= t1 + 1e9 and d["slot"] is not None:
                D.setdefault((d["slot"], d["idx"], 0), d)
        out[k] = sorted(D.values(), key=lambda d: (d["slot"], d["idx"], d.get("j") or 0))
    return out

def first_after_dump(R, T, W, paths):
    """per dump: the first of our landed tries after it in chain order (slot, idx), when every path had a try IN FLIGHT at the dump
    (sent before we saw the dump, landing after it). -> list of dicts (window, winner path, each path's first position)"""
    DW = dumps_by_window(R, T, W)
    out = []
    for k, ts in W.items():
        lt = sorted([t for t in ts if t["landed"] and t["slot"] is not None and t["idx"] is not None], key=lambda t: (t["slot"], t["idx"]))
        if not lt: continue
        for D in DW.get(k, []):
            dpos = (D["slot"], D["idx"])
            after = [t for t in lt if (t["slot"], t["idx"]) > dpos]
            if not after: continue
            # in flight: sent before the dump reached our feed (its t), landed after it
            fl = {p: any(t["path"] == p and t["t"] <= (D.get("t") or 0) for t in after) for p in paths}
            firsts = {}
            for p in paths:
                f = next((t for t in after if t["path"] == p), None)
                if f is not None:
                    firsts[p] = {"slot": f["slot"], "idx": f["idx"], "dslot": f["slot"] - D["slot"], "gap": (f["idx"] - D["idx"]) if f["slot"] == D["slot"] else None,
                                 "a": arrival(f["slot"], f["idx"]), "ms_after_d": ((f["rx"] - D["t"]) / 1e6) if (f["rx"] and D.get("t")) else None}
            w = after[0]
            out.append({"k": k, "win": w["path"], "inflight": fl, "all_inflight": all(fl.values()), "firsts": firsts, "src": D.get("src"), "cross": bool(D.get("cross")),
                        "d_a": arrival(D["slot"], D["idx"]), "same_slot_win": w["slot"] == D["slot"], "sol": D.get("sol")})
    return out


# ------------------------------------------------------------------------------------------------------------------ bootstrap
class Boot:
    """cluster bootstrap over windows: every replicate draws whole windows with replacement (fixed seed)"""
    def __init__(self, keys, n, seed=7):
        self.keys = list(keys); self.ix = {k: i for i, k in enumerate(self.keys)}; self.n = n
        rng = np.random.default_rng(seed)
        self.C = np.stack([np.bincount(rng.integers(0, len(self.keys), len(self.keys)), minlength=len(self.keys)) for _ in range(n)]) if self.keys else np.zeros((0, 0))
    def ratio(self, num, den):
        """num/den per window (dicts window -> value) -> replicate ratios"""
        a = np.array([num.get(k, 0.0) for k in self.keys], float); b = np.array([den.get(k, 0.0) for k in self.keys], float)
        with np.errstate(invalid="ignore", divide="ignore"): return (self.C @ a) / (self.C @ b)
    def quant(self, vals_by_win, p):
        """pooled percentile of per-window value lists"""
        v, wi = [], []
        for k, vs in vals_by_win.items():
            if k in self.ix: v += vs; wi += [self.ix[k]] * len(vs)
        v = np.asarray(v, float); wi = np.asarray(wi, int)
        o = np.argsort(v); v = v[o]; wi = wi[o]
        return np.array([wq(v, self.C[r][wi], p) for r in range(self.n)])

def ci(arr, level):
    a = np.asarray(arr, float); a = a[~np.isnan(a)]
    if len(a) == 0: return (float("nan"), float("nan"))
    lo = (1 - level) / 2 * 100; return (float(np.percentile(a, lo)), float(np.percentile(a, 100 - lo)))


# ------------------------------------------------------------------------------------------------------------------ report
def report(R, args, p=print):
    cfg, start = run_cfg(R)
    routes = parse_routes(cfg.get("routes"))
    T = unique_tries(R)
    if not T: p("no pre-send tries in this file / time range"); return {}
    paths = sorted({t["path"] for t in T}, key=lambda x: (x != "helius-ps", x))
    ref = paths[0]
    W = window_index(T)
    t0 = min(t["t"] for t in T); t1 = max(t["t"] for t in T); hours = (t1 - t0) / 3.6e12
    out = {"file": args.run, "from_pkt": pkt(t0), "to_pkt": pkt(t1), "hours": hours, "paths": paths, "routes": cfg.get("routes")}
    p(f"ASTRA A/B  {os.path.basename(args.run)}  {pkt(t0)} -> {pkt(t1)} PKT ({hours:.1f} h of tries)  routes {cfg.get('routes')}  caps: global {cfg.get('max_per_sec')}/s, "
      f"per path {cfg.get('path_max_per_sec')}/s, k {cfg.get('k')}/slot, tip override {cfg.get('tip')}")
    kinds = collections.Counter(R["arm"][k]["kind"] for k in W if k in R["arm"])
    p(f"  windows with tries {len(W)} ({', '.join(f'{k} {v}' for k, v in kinds.items()) or 'arm records not in range'}) | tries (attempt records) {len(R['att'])}, "
      f"distinct txs {len(T)} | fills {len(R['fill'])} | positions realized {len(R['real'])}")
    ok, bad = route_check(T, routes)
    p(f"  alternation check (path == route[(n + w) % len]): {ok} match, {bad} differ{'  <-- the A/B assumption is broken: check the routes' if bad else ''}")
    dups = [t for t in T if t["copies"] > 1]
    if dups:
        p(f"  NOTE: {len(dups)} txs were sent twice with identical bytes (same blockhash, deadline, limit and tip account; ~10 ticks apart): one tx, "
          f"one landing; {sum(t['amb'] for t in T)} of them have an ambiguous send time (left out of the latency numbers)")
    p("")
    # ---- 1. per path
    p("1. PER PATH [MEASURED]  (one row per distinct tx; landed = seen on chain, filled or failed; same-slot = landed in its send slot)")
    sk, sk_tot = tick_skips(R, routes)
    hdr = (f"  {'path':14s} {'tries':>6s} {'skip':>5s} {'landed':>7s} {'unseen':>6s} {'same-slot':>9s} {'+1':>5s} {'+2+':>5s} {'slots p50/75/90':>15s} {'p50/p75/p90 ms':>15s} "
           f"{'first-rx p50/p90':>16s} {'ack!=200':>8s} {'ack p50/p99 ms':>14s}")
    p(hdr)
    per = {}
    for path in paths:
        X = [t for t in T if t["path"] == path]; L = [t for t in X if t["landed"]]
        sas = [t["sas"] for t in L if t["sas"] is not None]
        ms = [t["ms"] for t in L if t["ms"] is not None]; msf = [t["msf"] for t in L if t["msf"] is not None]
        acks = [t["ack"] for t in X if t["has_land"]]; nack = sum(1 for a in acks if a != 200)
        ackms = [t["ack_ms"] for t in X if t["ack_ms"] is not None]
        unseen = sum(1 for t in X if t["res"] == "unseen")
        d = {"tries": len(X), "skipped_ticks": sk.get(path, 0), "landed": len(L) / max(len(X), 1), "unseen": unseen / max(len(X), 1),
             "same": np.mean([s == 0 for s in sas]) if sas else float("nan"), "s1": np.mean([s == 1 for s in sas]) if sas else float("nan"),
             "s2": np.mean([s >= 2 for s in sas]) if sas else float("nan"), "ms_q": pq(ms, (50, 75, 90)), "msf_q": pq(msf, (50, 90)),
             "ack_bad": nack / max(len(acks), 1), "ack_ms_q": pq(ackms, (50, 99)), "res": collections.Counter(t["res"] for t in X),
             "acks": collections.Counter(str(a) for a in acks), "errs": collections.Counter(t["err"] for t in X if t["err"])}
        per[path] = d
        d["slots_q"] = pq(sas, (50, 75, 90))
        p(f"  {path:14s} {d['tries']:6d} {d['skipped_ticks']:5d} {fp(d['landed']):>7s} {fp(d['unseen']):>6s} {fp(d['same']):>9s} {fp(d['s1'], 0):>5s} {fp(d['s2'], 0):>5s} "
          f"{fq(d['slots_q']):>15s} {fq(d['ms_q']):>15s} {fq(d['msf_q']):>16s} {fp(d['ack_bad']):>8s} {fq(d['ack_ms_q'], 1):>14s}")
    tips = collections.defaultdict(collections.Counter)
    for a in R["att"]: tips[a["path"]][a["tip"]] += 1
    for path in paths:
        d = per[path]
        p(f"    {path}: tip {', '.join(f'{k} lamports x{v}' for k, v in tips[path].most_common(3))} | results " + ", ".join(f"{k} {d['res'].get(k, 0)}" for k in RES_ORDER + ["norec"] if d["res"].get(k)) +
          f" | acks {dict(d['acks'])} | top errors " + "; ".join(f"{e} x{n}" for e, n in d["errs"].most_common(4)))
    kinds_t = sorted({t["kind"] for t in T})
    if len(kinds_t) > 1:
        for kd in kinds_t:
            for path in paths:
                X = [t for t in T if t["path"] == path and t["kind"] == kd]; L = [t for t in X if t["landed"]]
                sas = [t["sas"] for t in L if t["sas"] is not None]; ms = [t["ms"] for t in L if t["ms"] is not None]
                if X: p(f"    windows {kd:6s} {path:14s} tries {len(X):6d} landed {fp(len(L) / len(X))} same-slot {fp(np.mean([x == 0 for x in sas]) if sas else float('nan'))} p50/p90 {fq(pq(ms, (50, 90)))} ms")
    p(f"  skipped ticks (INFERRED from gaps in each window's tick numbers n; their path = the route's rule): {sk_tot} in all"
      + (f" = {fp(sk_tot / (sk_tot + len(R['att'])))} of ticks" if sk_tot else ""))
    st = parse_status(args.log) if args.log else []
    if args.log:
        if st:
            sl = [t["send_slot"] for t in T if t["send_slot"]]
            dlt = status_delta(st, min(sl) - 1, max(sl) + 400)
            if dlt:
                p(f"  status lines (.log, cumulative, slots {dlt['slot_lo']}..{dlt['slot_hi']}) [MEASURED]: sent {dlt['sent']} | not sent (sender skips, all paths) {dlt['not_sent']} | "
                  f"trigger skips {dlt['trig_skips']} | acks {dlt['acks']}")
                for path, v in sorted(dlt["per_path"].items()):
                    p(f"    engine per path {path}: sent {v[0]} ok {v[1]} 6042 {v[2]} deadline {v[3]} ata {v[4]} other {v[5]} unseen {v[6]}")
                out["status"] = dlt
        else: p("  status lines: none found in the .log")
    out["per_path"] = {k: {kk: (vv if not isinstance(vv, collections.Counter) else dict(vv)) for kk, vv in v.items()} for k, v in per.items()}
    p("")
    baseline_view(R, p)
    # ---- per path x client
    if not args.no_clients:
        p("")
        p("  PER PATH x LEADER CLIENT [MEASURED]")
        p(f"  {'client':19s} " + " ".join(f"{x[:14]:>44s}" for x in paths))
        p(f"  {'':19s} " + " ".join(f"{'tries landed same p50/p75/p90':>44s}" for _ in paths))
        clients = collections.Counter(t["client"] for t in T)
        for c, n in clients.most_common():
            if n < 100: continue
            cells = []
            for path in paths:
                X = [t for t in T if t["path"] == path and t["client"] == c]; L = [t for t in X if t["landed"]]
                sas = [t["sas"] for t in L if t["sas"] is not None]; ms = [t["ms"] for t in L if t["ms"] is not None]
                cells.append(f"{len(X):6d} {fp(len(L) / max(len(X), 1), 0):>5s} {fp(np.mean([s == 0 for s in sas]) if sas else float('nan'), 0):>5s} {fq(pq(ms)):>15s}".rjust(44))
            p(f"  {c or '?':19s} " + " ".join(cells))
    if len(paths) < 2:
        p("")
        p(f"  (one path only ({ref}): the race, P&L-by-path and paired sections compare paths and are skipped; the SOL section still runs)")
        races = None
    else:
        races = race_sections(R, T, W, paths, ref, args, p, out)
    # ---- SOL
    if args.sol != "off":
        p("")
        try: out["sol"] = sol_section(R, T, paths, args, p)
        except Exception as e:
            import traceback; traceback.print_exc()
            p(f"  SOL conversion failed: {e!r}")
    summary(out, paths, args, p)
    return out

def summary(out, paths, args, p):
    """the plain headline (phone-sized)"""
    p("")
    p(f"SUMMARY {out['from_pkt']} -> {out['to_pkt']} PKT ({out['hours']:.1f} h)")
    for x in paths:
        d = out["per_path"][x]
        p(f"  {x}: {d['tries']} tries, landed {fp(d['landed'])}, same slot {fp(d['same'])}, send->land p50/p90 {fq([d['ms_q'][0], d['ms_q'][2]])} ms, "
          f"acks not 200 {fp(d['ack_bad'])}" + (f", fills {out['fill_race'][x]['fills']:.0f} (expected {out['fill_race'][x]['expected']:.1f})" if out.get("fill_race") else "")
          + (f", first after a dump {fp(out['first_after_dump'][x]['share'])}" if out.get("first_after_dump") else ""))
    for x, rows in (out.get("paired") or {}).items():
        r = {q["metric"]: q for q in rows}
        if "send->land p50 ms" in r:
            a, b = r["send->land p50 ms"], r["send->land p90 ms"]; c = r["same-slot share"]
            p(f"  {x} vs {paths[0]}: p50 {a['diff']:+.1f} ms [{a['ci'][0]:+.1f}, {a['ci'][1]:+.1f}], p90 {b['diff']:+.1f} ms [{b['ci'][0]:+.1f}, {b['ci'][1]:+.1f}], "
              f"same slot {100 * c['diff']:+.1f} pt [{100 * c['ci'][0]:+.1f}, {100 * c['ci'][1]:+.1f}] (negative ms = {x} faster; {int(args.ci * 100)}% CIs)")
    sol = out.get("sol") or {}
    for k, v in sol.items():
        if k.endswith(f"_minus_{paths[0]}") and isinstance(v, dict):
            ci_ = sol.get(f"{k}_ci_day")
            p(f"  SOL (INFERRED): {k.replace('_minus_', ' instead of ')} for ALL tries: {v['per_day']:+.2f} SOL/day" + (f" [{ci_[0]:+.2f}, {ci_[1]:+.2f}]" if ci_ else ""))


def race_sections(R, T, W, paths, ref, args, p, out):
    lvl = args.ci; B = Boot(W.keys(), args.boot)
    others = [x for x in paths if x != ref]
    # ---- 2. fill race
    p("")
    p("2. FILL RACE [MEASURED]: who filled, against each path's share of the window's tries sent before the fill (expected if the paths were equal)")
    fills = [f for f in R["fill"]]
    obs = {x: {} for x in paths}; exp = {x: {} for x in paths}
    for f in fills:
        k = (f["seg"], f["w"]); ts = W.get(k, [])
        before = [t for t in ts if t["t"] <= (f["t"] or 0)]
        if not before: continue
        for x in paths:
            exp[x][k] = exp[x].get(k, 0.0) + sum(t["path"] == x for t in before) / len(before)
            obs[x][k] = obs[x].get(k, 0.0) + (f["path"] == x)
    nf = sum(sum(v.values()) for v in obs.values())
    p(f"  fills {len(fills)} (in windows with tries: {nf:.0f}; after an exit {sum(1 for f in fills if f['after_exit'])}, window already closed {sum(1 for f in fills if f['window_open'] is False)})")
    rr = {}
    for x in paths:
        o = sum(obs[x].values()); e = sum(exp[x].values())
        one = {k: 1.0 for k in set(obs[x]) | set(exp[x])}
        bo = B.ratio(obs[x], one); be = B.ratio(exp[x], one)
        lo, hi = ci(bo - be, lvl)
        rr[x] = {"fills": o, "expected": e, "excess_share": (o - e) / max(nf, 1), "ci": (lo, hi)}
        p(f"  {x:14s} fills {o:4.0f}  expected {e:6.1f}  -> {o - e:+5.1f} fills ({fp((o - e) / max(nf, 1))} of all fills), {int(lvl * 100)}% CI [{fp(lo)}, {fp(hi)}]")
    byc = collections.defaultdict(collections.Counter)
    for f in fills: byc[f["client"]][f["path"]] += 1
    p("  fills by leader client: " + "; ".join(f"{c or '?'} " + "/".join(f"{x.split('-')[0]} {v.get(x, 0)}" for x in paths) for c, v in sorted(byc.items(), key=lambda kv: -sum(kv[1].values()))))
    out["fill_race"] = rr
    # ---- 3. first after dump
    p("")
    p("3. FIRST TO LAND AFTER EACH DUMP [MEASURED positions; ms leads INFERRED from the block-position clock]")
    p("   dumps = outside sells in each window (the try records' 'd' (>= 2% drop) and 'x' (the limit-crossing trade) + the engine's dump events);")
    p("   counted when every path had a try in flight (sent before we saw the dump, landing after it)")
    FA = first_after_dump(R, T, W, paths)
    FB = [x for x in FA if x["all_inflight"]]
    xs = [x for x in FB if x["cross"]]
    p(f"  dumps with a landed try after them {len(FA)}; with every path in flight {len(FB)} (of them limit-crossing 'x' trades: {len(xs)})")
    won = {x: collections.Counter() for x in paths}; tot = collections.Counter()
    for r in FB: won[r["win"]][r["k"]] += 1; tot[r["k"]] += 1
    fa = {}
    for x in paths:
        share = sum(won[x].values()) / max(len(FB), 1)
        bs = B.ratio(dict(won[x]), dict(tot)); lo, hi = ci(bs, lvl)
        sub = [r for r in xs]; sx = sum(r["win"] == x for r in sub) / max(len(sub), 1)
        fs = [r["firsts"][x] for r in FB if x in r["firsts"]]
        same = np.mean([f["dslot"] == 0 for f in fs]) if fs else float("nan")
        gaps = [f["gap"] for f in fs if f["gap"] is not None]
        mad = [f["ms_after_d"] for f in fs if f["ms_after_d"] is not None]
        fa[x] = {"share": share, "ci": (lo, hi), "share_x": sx, "same_slot": same, "ms_after_dump_q": pq(mad, (25, 50, 75))}
        p(f"  {x:14s} first {sum(won[x].values()):5d} of {len(FB)} = {fp(share)} {int(lvl * 100)}% CI [{fp(lo)}, {fp(hi)}] | on limit-crossing trades {fp(sx)} | "
          f"its first try after the dump: same slot {fp(same)}, idx gap q25/50/75 {fq(pq(gaps, (25, 50, 75)))}, seen {fq(pq(mad, (25, 50, 75)))} ms after the dump")
    for x in others:
        lead = [r["firsts"][ref]["a"] - r["firsts"][x]["a"] for r in FB if x in r["firsts"] and ref in r["firsts"]]
        if lead:
            p(f"  paired: {x} first try lands {np.median(lead):+.1f} ms (median; block clock) vs {ref}'s first try; ahead in {fp(np.mean([l > 0 for l in lead]))}, "
              f"behind in {fp(np.mean([l < 0 for l in lead]))} of {len(lead)} dumps (positive = {x} earlier)")
            fa[x]["lead_ms_median"] = float(np.median(lead))
    out["first_after_dump"] = fa
    # ---- 4. P&L by fill path
    p("")
    p("4. POSITIONS BY THE PATH OF THE FILLING TRY [MEASURED; realized P&L in SOL]")
    pmap = {t["sig"]: t["path"] for t in T}
    for f in R["fill"]: pmap.setdefault(f["sig"], f["path"])
    pos = collections.defaultdict(list)
    for r in R["real"]:
        ps = [pmap.get(s) for s in r["sigs"] if pmap.get(s)]
        if not ps or r["pnl"] is None: continue
        pos[ps[0]].append(r["pnl"] / 1e9)
    # entry quality per fill (luck-free-ish): outside trades between the dump and our fill, and the price move from the dump's
    # post-trade price to our entry (both from the filling try's land record / the fill record)
    tsig = {t["sig"]: t for t in T}
    eq = collections.defaultdict(lambda: {"nb": [], "reb": []})
    for f in R["fill"]:
        t = tsig.get(f["sig"])
        if not t: continue
        if t.get("nb") is not None: eq[f["path"]]["nb"].append(t["nb"])
        d = t.get("d")
        if d and d.get("p_rel") and f.get("p_pre") and f.get("p_sign"):
            eq[f["path"]]["reb"].append(100.0 * ((f["p_pre"] / f["p_sign"]) / d["p_rel"] - 1.0))
    pl = {}
    rng = np.random.default_rng(11)
    for x in paths:
        v = np.array(pos.get(x, []))
        e = eq[x]
        eqs = (f" | entry: 0 outside trades between dump and fill {fp(np.mean([n == 0 for n in e['nb']]) if e['nb'] else float('nan'), 0)}, "
               f"price above the dump's {fq(pq(e['reb'], (25, 50, 75)), 2)}% (q25/50/75)")
        if len(v) == 0: p(f"  {x:14s} no positions{eqs}"); continue
        bs = [v[rng.integers(0, len(v), len(v))].mean() for _ in range(args.boot)]; lo, hi = ci(bs, lvl)
        tipx = max([(f["tip"] or 0) for f in R["fill"] if f["path"] == x] or [0]) / 1e9
        pl[x] = {"n": len(v), "sum": float(v.sum()), "mean_msol": float(v.mean() * 1e3), "ci_msol": (lo * 1e3, hi * 1e3),
                 "entry_zero_between": float(np.mean([n == 0 for n in e["nb"]])) if e["nb"] else None, "entry_rebound_pct_q": pq(e["reb"], (25, 50, 75))}
        p(f"  {x:14s} positions {len(v):4d}  total {v.sum():+8.3f}  mean {v.mean() * 1e3:+6.2f} mSOL [{lo * 1e3:+.2f}, {hi * 1e3:+.2f}]  median {np.median(v) * 1e3:+6.2f}  "
          f"win {fp(np.mean(v > 0), 0)}  tip/fill {tipx:.4f}{eqs}")
    for x in others:
        if x in pl and ref in pl:
            a_ = np.array(pos[x]); b_ = np.array(pos[ref]); obsd = a_.mean() - b_.mean()
            allv = np.concatenate([a_, b_]); na = len(a_); prng = np.random.default_rng(13); cnt = 0; NP = 10000
            for _ in range(NP):
                prng.shuffle(allv)
                if abs(allv[:na].mean() - allv[na:].mean()) >= abs(obsd): cnt += 1
            p(f"  mean per position {x} - {ref}: {obsd * 1e3:+.2f} mSOL; label-shuffle p = {cnt / NP:.2f} (two-sided). Token luck dominates position P&L: "
              f"the r37 fake split (same path, labels by tick parity) gave +20.6 mSOL with a 90% CI excluding 0. Decide on sections 1-3 and 6.")
            pl[f"{x}_minus_{ref}"] = {"mean_msol": obsd * 1e3, "perm_p": cnt / NP}
    out["pnl_by_path"] = pl
    # ---- 5. paired per window
    p("")
    p(f"5. PAIRED, PER WINDOW [MEASURED; CIs = cluster bootstrap over whole windows, {args.boot} draws, {int(lvl * 100)}%]")
    both = [k for k, ts in W.items() if len({t["path"] for t in ts}) >= 2]
    p(f"  windows with tries on 2+ paths: {len(both)} of {len(W)}")
    def per_win(x, f):
        return {k: f([t for t in W[k] if t["path"] == x]) for k in W}
    pr = {}
    for x in others:
        rows = []
        for name, num, den in (("landed share", lambda ts: sum(t["landed"] for t in ts), lambda ts: len(ts)),
                               ("same-slot share", lambda ts: sum(1 for t in ts if t["landed"] and t["sas"] == 0), lambda ts: sum(1 for t in ts if t["landed"] and t["sas"] is not None)),
                               ("unseen share", lambda ts: sum(1 for t in ts if t["res"] == "unseen"), lambda ts: len(ts))):
            a = B.ratio(per_win(x, num), per_win(x, den)); b = B.ratio(per_win(ref, num), per_win(ref, den))
            pa = sum(per_win(x, num).values()) / max(sum(per_win(x, den).values()), 1); pb = sum(per_win(ref, num).values()) / max(sum(per_win(ref, den).values()), 1)
            lo, hi = ci(a - b, lvl); rows.append((name, pa, pb, pa - pb, lo, hi, "%"))
        for name, qv in (("send->land p50 ms", 50), ("send->land p75 ms", 75), ("send->land p90 ms", 90)):
            va = {k: [t["ms"] for t in W[k] if t["path"] == x and t["ms"] is not None] for k in W}
            vb = {k: [t["ms"] for t in W[k] if t["path"] == ref and t["ms"] is not None] for k in W}
            a = B.quant(va, qv); b = B.quant(vb, qv)
            pa = pq(sum(va.values(), []), (qv,))[0]; pb = pq(sum(vb.values(), []), (qv,))[0]
            lo, hi = ci(a - b, lvl); rows.append((name, pa, pb, pa - pb, lo, hi, "ms"))
        # mean of per-window paired differences (windows with >= 3 landed tries on both)
        dd = []
        for k in both:
            a = [t["ms"] for t in W[k] if t["path"] == x and t["ms"] is not None]; b = [t["ms"] for t in W[k] if t["path"] == ref and t["ms"] is not None]
            if len(a) >= 3 and len(b) >= 3: dd.append(np.median(a) - np.median(b))
        p(f"  {x} vs {ref}:")
        p(f"    {'metric':22s} {x[:12]:>12s} {ref[:12]:>12s} {'difference':>11s} {'CI':>20s}")
        for name, pa, pb, df, lo, hi, u in rows:
            if u == "%": p(f"    {name:22s} {fp(pa):>12s} {fp(pb):>12s} {(100 * df):+10.1f}pt [{100 * lo:+6.1f}, {100 * hi:+6.1f}]pt")
            else: p(f"    {name:22s} {pa:12.1f} {pb:12.1f} {df:+10.1f}ms [{lo:+6.1f}, {hi:+6.1f}]ms")
        if dd:
            rng = np.random.default_rng(5); dd = np.array(dd)
            bs = [dd[rng.integers(0, len(dd), len(dd))].mean() for _ in range(args.boot)]; lo, hi = ci(bs, lvl)
            p(f"    per-window median send->land, {x} - {ref}: mean {dd.mean():+.1f} ms [{lo:+.1f}, {hi:+.1f}] over {len(dd)} windows (>= 3 landed tries on each); "
              f"{x} faster in {fp(np.mean(dd < 0), 0)} of them")
        pr[x] = [{"metric": r[0], x: r[1], ref: r[2], "diff": r[3], "ci": (r[4], r[5])} for r in rows]
    out["paired"] = pr
    return out


# ------------------------------------------------------------------------------------------------------------------ SOL (INFERRED)
def _cc(s, i, MAXI):
    return s * SMS + (i + 0.5) / (MAXI.get(s, 400) + 1.0) * SMS
def _pos(c, MAXI):
    s = int(c // SMS); return s, int((c - s * SMS) / SMS * (MAXI.get(s, 400) + 1))

def scen_from(samples):
    """speed35 s3_scen.scen_from: (slot offset, idx) quantiles, weights"""
    by = collections.defaultdict(list)
    for d, i in samples: by[min(d, 3)].append(i)
    n = len(samples); out = []
    for d, v in sorted(by.items()):
        for q in np.percentile(v, np.arange(5, 100, 10)): out.append(((d, int(round(q))), len(v) / n / 10))
    return out

def load_tries(fn):
    """s3_scen.load + each try's path and client: sends, lands (slot, idx, first_rx), windows, exits, sells, fills"""
    sends = {}; lands = {}; wins = []; cur = {}; exits = {}; sells = []; fills = {}
    for l in open(fn, errors="replace"):
        if '"ev":"presend_' not in l: continue
        try: r = json.loads(l)
        except Exception: continue
        e = r["ev"]
        if e == "presend_attempt": sends[r["sig"]] = (r["t"], r["mint"], r.get("path"), r.get("client") or "")   # last copy, as s3_scen
        elif e == "presend_attempt_land" and r.get("first_rx") and r.get("slot") and r.get("idx") is not None: lands[r["sig"]] = (r["slot"], r["idx"], r["first_rx"])
        elif e == "presend_live_arm":
            tr = r.get("trig") or {}
            if tr: cur[tr["mint"]] = {"sig": tr["sig"], "t0": tr["t"], "mint": tr["mint"]}
        elif e == "presend_live_disarm":
            w = cur.pop(r["mint"], None)
            if w: w["t1"] = r["t"]; w["slot1"] = r["slot"]; wins.append(w)
        elif e == "presend_live_fill": fills[(r["mint"], 1)] = r
        elif e == "presend_live_exit": exits[(r["mint"], r.get("pid"), r.get("round"))] = r
        elif e == "presend_live_sell_land": sells.append(r)
    return sends, lands, wins, exits, sells, fills

MIN_MAP = 40     # a client needs this many landed tries on both sides of a mapping, else the all-client distributions are used

def mid_rank(sample, values):
    s = np.sort(np.asarray(sample, float)); v = np.asarray(values, float)
    return (np.searchsorted(s, v, "left") + np.searchsorted(s, v, "right")) / 2.0 / max(len(s), 1)

class Src:
    """the tries whose latency gets mapped: per try its group (base run: the client; own run: (path, client)), its latency L and
    its rank inside its group and inside its path's all-client sample. mapped(D) -> {sig: the target's latency at that rank}"""
    def __init__(self, items):
        self.sig = list(items.keys())
        self.g = [items[s][0] for s in self.sig]; self.c = np.array([items[s][1] for s in self.sig]); self.p = np.array([items[s][2] for s in self.sig])
        self.L = np.array([items[s][3] for s in self.sig], float)
        self.u_g = np.zeros(len(self.L)); self.u_p = np.zeros(len(self.L)); self.n_g = {}
        ga = np.array([f"{x}" for x in self.g])
        self.ga = ga
        for k in set(ga.tolist()):
            m = ga == k; self.n_g[k] = int(m.sum()); self.u_g[m] = mid_rank(self.L[m], self.L[m])
        for k in set(self.p.tolist()):
            m = self.p == k; self.u_p[m] = mid_rank(self.L[m], self.L[m])
    def mapped(self, D):
        out = np.empty(len(self.L)); done = np.zeros(len(self.L), bool)
        allv = np.concatenate([np.asarray(v, float) for v in D.values() if len(v)]) if D else np.zeros(0)
        for k in set(self.ga.tolist()):
            m = self.ga == k; c = self.c[m][0]; tv = D.get(c)
            if tv is not None and len(tv) >= MIN_MAP and self.n_g[k] >= MIN_MAP:
                out[m] = np.quantile(np.asarray(tv, float), np.clip(self.u_g[m], 0, 1), method="inverted_cdf"); done[m] = True
        if (~done).any(): out[~done] = np.quantile(allv, np.clip(self.u_p[~done], 0, 1), method="inverted_cdf")
        return dict(zip(self.sig, out.tolist()))

def prep(sends, lands, wins, TAPES, MAXI):
    """speed35 s3_scen's per-window inputs, computed once: each window's landed tries (chain coordinate c, latency L, sig) and its
    outside sells inside the try stream (chain coordinate; s3's clock filter)"""
    A = sorted((_cc(s, i, MAXI), rx / 1e6) for s, i, rx in lands.values())
    Ac = np.array([a[0] for a in A]); Ao = np.array([a[1] - a[0] for a in A])
    def off(c):
        k = np.searchsorted(Ac, c); lo, hi = max(0, k - 3), min(len(Ac), k + 3); return float(np.median(Ao[lo:hi]))
    bym = collections.defaultdict(list)
    for s, v in sends.items():
        if s in lands: bym[v[1]].append((v[0] / 1e6, lands[s][2] / 1e6, _cc(lands[s][0], lands[s][1], MAXI), s))
    P = []
    for w in wins:
        tape = TAPES.get(w["sig"])
        if not tape: continue
        tr = [x for x in tape if x[8] not in OURS]
        tries = [x for x in bym[w["mint"]] if w["t0"] / 1e6 - 1 <= x[0] <= w["t1"] / 1e6]
        if not tries: continue
        dm = []
        for x in tr:
            if x[3] or x[0] > w["slot1"]: continue
            cd = _cc(x[0], x[1], MAXI); td = cd + off(cd)
            if td < tries[0][1] or td > tries[-1][1] - 30: continue
            dm.append((cd, x[0], x[1]))
        if not dm: continue
        P.append({"c": np.array([t[2] for t in tries]), "L": np.array([t[1] - t[0] for t in tries]), "sig": [t[3] for t in tries], "dumps": dm})
    return P

def scen_samples(P, MAXI, Lmap=None):
    """first try after each outside sell, every try keeping its real send time and chain place, moved earlier by the time it saves
    (Lmap: sig -> new latency; None = today's landing)"""
    samp = []
    for w in P:
        if Lmap is None: arr = np.sort(w["c"])
        else:
            L2 = np.array([Lmap.get(s, l) for s, l in zip(w["sig"], w["L"])])
            arr = np.sort(w["c"] - (w["L"] - L2))
        for cd, s0, i0 in w["dumps"]:
            k = np.searchsorted(arr, cd, "right")
            if k >= len(arr): continue
            s1, i1 = _pos(float(arr[k]), MAXI); d = s1 - s0
            samp.append((d, max(i1 - i0, 1) if d == 0 else i1))
    return samp

def sell_mix(sends, lands, exits, sells, fills, MAXI):
    S = []
    for sl in sells:
        ex = exits.get((sl["mint"], sl.get("pid"), sl.get("round"))); fl = fills.get((sl["mint"], 1))
        if not ex or not fl: continue
        s1, i1 = _pos(_cc(sl["slot"], sl["idx"], MAXI), MAXI); S.append((s1 - fl["slot"], i1 / (MAXI.get(s1, 400) + 1)))
    g = collections.defaultdict(list)
    for h, pp in S: g[max(h, 1)].append(pp if h >= 1 else 0.0)
    return [(h, float(np.mean(v)), len(v) / len(S)) for h, v in sorted(g.items())] if S else None

_G = {}
def _sim_row(r, tp, scens_row, M, tpv, slv, size, cut):
    sim = _G["sim"]; res = {}
    for name, S in scens_row.items():
        acc = [0.0, 0.0, 0.0]
        for sc, w in S:
            kw = dict(size=size, lim_mult=0.88, tp=tpv, sl=slv, cost_rt=COST_RT, scen=sc, mix=M)
            x = sim(r, tp, **kw)
            acc[0] += w * x["pnl"]; acc[1] += w * x["filled"]
            if cut and x["filled"]: acc[2] += w * np.mean([sim(r, tp, cut=0.2, seed=k, **kw)["pnl"] for k in range(SEEDS)])
        res[name] = acc
    return res

def _replay_one(i):
    r = _G["rows"][i]; tp = _G["tapes"].get(r["sig"])
    if not tp: return None
    tpv, slv = _G["tpsl"][r["run"]]
    res = _sim_row(r, tp, {n: s[r["run"]] for n, s in _G["scens"].items()}, _G["mix"][r["run"]], tpv, slv, _G["size"], True)
    return {"sig": r["sig"], "run": r["run"], "t": r["t"], "lp": sum(x for x in r["real"] if x is not None) / 1e9, "lf": len(r["lfill"]), "res": res}

def _make_scens(D):
    """target name -> run -> scenario, for target latency distributions D (name -> client -> [ms])"""
    out = {}
    for name, Dt in D.items():
        out[name] = {}
        for rn, pr in _G["prep"].items():
            out[name][rn] = scen_from(scen_samples(pr, _G["maxi"], _G["src"][rn].mapped(Dt)))
    return out

def _boot_one(b):
    """one replicate: whole windows of the analysed run resampled -> each target's latency distributions -> scenarios -> the replay
    (no follower cut) -> the replay windows resampled. -> {target: P&L sum}"""
    rng = np.random.default_rng(1000 + b)
    keys = _G["akeys"]; cnt = np.bincount(rng.integers(0, len(keys), len(keys)), minlength=len(keys))
    D = {x: collections.defaultdict(list) for x in set(_G["targets"]) | {"mix"}}
    for i in np.nonzero(cnt)[0]:
        for path, client, L in _G["awin"][keys[i]]:
            D[path][client].extend([L] * int(cnt[i])); D["mix"][client].extend([L] * int(cnt[i]))
    scens = _make_scens({k: v for k, v in D.items() if k in _G["targets"]})
    rows = _G["rows"]; names = _G["targets"]
    per = np.zeros((len(rows), len(names)))
    for j, r in enumerate(rows):
        tpv, slv = _G["tpsl"][r["run"]]
        res = _sim_row(r, _G["tapes"][r["sig"]], {n: scens[n][r["run"]] for n in names}, _G["mix"][r["run"]], tpv, slv, _G["size"], False)
        per[j] = [res[n][0] for n in names]
    rw = np.bincount(rng.integers(0, len(rows), len(rows)), minlength=len(rows))
    return (rw[:, None] * per).sum(0)

def run_pool(fn, items, procs):
    if procs > 1:
        from multiprocessing import get_context
        with get_context("fork").Pool(procs) as pool: return pool.map(fn, items, chunksize=max(1, min(8, len(items) // (procs * 4) or 1)))
    return list(map(fn, items))

def target_dists(T, paths):
    """per path (and 'mix' = all paths pooled, the run's real mix): per client lists of send -> first feed sighting (ms), the
    replay's latency measure (s3_scen: first_rx - send); plus the same per window (for the bootstrap)"""
    D = {x: collections.defaultdict(list) for x in paths}; D["mix"] = collections.defaultdict(list)
    per_w = collections.defaultdict(list)
    for t in T:
        if t["landed"] and t["msf"] is not None and t["msf"] > 0:
            D[t["path"]][t["client"]].append(t["msf"]); D["mix"][t["client"]].append(t["msf"])
            per_w[(t["seg"], t["w"])].append((t["path"], t["client"], t["msf"]))
    return D, per_w

def sol_section(R, T, paths, args, p):
    p(f"6. SOL CONVERSION [INFERRED: a replay, not money made] mode {args.sol}")
    D, per_w = target_dists(T, paths)
    for x in list(paths) + ["mix"]:
        allv = sum(D[x].values(), [])
        p(f"  {x:14s} send->first sighting (the replay's latency) p50/p75/p90 {fq(pq(allv))} ms, n {len(allv)}")
    sys.path.insert(0, SPEED35)
    from s_sim import sim
    _G.update(sim=sim, akeys=list(per_w.keys()), awin=per_w)
    if args.sol == "own": return sol_own(R, T, paths, D, args, p)
    return sol_base(paths, D, args, p)

def sol_report(RR, names, ref_name, hrs, args, p, boots, paths):
    """the point table (vs the reference) and the A-B lines with the bootstrap CI"""
    lvl = args.ci
    p(f"  {'if ALL tries had':18s} {'P&L SOL':>8s} {'fills':>6s} {'vs ' + ref_name:>9s} {'SOL/day':>8s} {'-20% fol.':>9s}" + (f"  {int(lvl * 100)}% CI SOL/day ({len(boots)} draws)" if len(boots) else ""))
    base = np.array([r["res"][ref_name][0] for r in RR]); basec = np.array([r["res"][ref_name][2] for r in RR]); out = {}
    for nm in names:
        v = np.array([r["res"][nm][0] for r in RR]); f = sum(r["res"][nm][1] for r in RR); vc = np.array([r["res"][nm][2] for r in RR])
        d = v.sum() - base.sum()
        cis = ""
        if len(boots) and nm in _G.get("targets", []) and ref_name in _G.get("targets", []):
            ix = _G["targets"]; bd = boots[:, ix.index(nm)] - boots[:, ix.index(ref_name)]
            lo, hi = ci(bd, lvl); cis = f"  [{lo / hrs * 24:+.2f}, {hi / hrs * 24:+.2f}]"
        out[nm] = {"pnl": float(v.sum()), "fills": float(f), "delta": float(d), "per_day": float(d / hrs * 24) if hrs else None, "delta_cut20": float((vc - basec).sum())}
        p(f"  {nm:18s} {v.sum():+8.3f} {f:6.1f} {d:+9.3f} {d / hrs * 24 if hrs else float('nan'):+8.2f} {(vc - basec).sum():+9.3f}{cis}")
    for x in [q for q in paths if q != paths[0]]:
        v = sum(r["res"][x][0] for r in RR) - sum(r["res"][paths[0]][0] for r in RR)
        cis = ""
        if len(boots):
            ix = _G["targets"]; bd = boots[:, ix.index(x)] - boots[:, ix.index(paths[0])]; lo, hi = ci(bd, lvl)
            cis = f", {int(lvl * 100)}% CI [{lo / hrs * 24:+.2f}, {hi / hrs * 24:+.2f}] SOL/day (bootstrap median {np.median(bd) / hrs * 24:+.2f})"
            out[f"{x}_minus_{paths[0]}_ci_day"] = (lo / hrs * 24, hi / hrs * 24)
        p(f"  => ALL tries on {x} instead of ALL on {paths[0]}: {v:+.3f} SOL over {hrs:.1f} h = {v / hrs * 24:+.2f} SOL/day{cis} (INFERRED)")
        out[f"{x}_minus_{paths[0]}"] = {"sol": float(v), "per_day": float(v / hrs * 24)}
    if len(boots): p(f"  CIs: cluster bootstrap that re-measures each path's latency on resampled windows of THIS run and resamples the replay's windows")
    else: p("  (no CI: --sol-boot 0; the paths' own measurement noise is NOT in these numbers: the r37 fake split, same path twice, read -0.10 SOL/day)")
    return out

def sol_base(paths, D, args, p):
    """the 911 calibrated r36+r37 windows; every try's latency mapped per client onto each target distribution"""
    B = pickle.load(open(f"{S35}/rows.pkl", "rb")); SC = pickle.load(open(f"{S35}/scen.pkl", "rb"))
    TAPES = B["tapes"]; MAXI = B["maxi"]
    pre = {}; srcs = {}; chk = []
    for rn, fn in BASE_RUNS.items():
        sends, lands, wins, exits, sells, fills = load_tries(fn)
        items = {s: (v[3], v[3], "base", lands[s][2] / 1e6 - v[0] / 1e6) for s, v in sends.items() if s in lands}
        srcs[rn] = Src(items); pre[rn] = prep(sends, lands, wins, TAPES, MAXI)
        sc = scen_from(scen_samples(pre[rn], MAXI)); ref = SC[rn]["cur"]["scen"]
        chk.append((rn, max(abs(a[0][1] - b[0][1]) + abs(a[1] - b[1]) for a, b in zip(sc, ref)) if len(sc) == len(ref) else "length differs"))
    rows = [r for r in B["rows"] if r["live"] == "armed" and TAPES.get(r["sig"])]
    targets = ["mix"] + list(paths)
    _G.update(prep=pre, src=srcs, maxi=MAXI, tapes=TAPES, rows=rows, mix={rn: SC[rn]["cur"]["mix"] for rn in BASE_RUNS}, tpsl=BASE_TPSL, size=SIZE, targets=targets)
    scens = {"cur": {rn: scen_from(scen_samples(pre[rn], MAXI)) for rn in BASE_RUNS}}
    scens.update(_make_scens({x: D[x] for x in targets}))
    _G["scens"] = scens
    p("  base: the speed35 r36 + r37 windows (911 live-armed windows with tapes); each base try's send->sighting latency is replaced by the")
    p("        target's latency at the same rank, per leader client (the try keeps its real send time, chain place and order)")
    p("  check vs speed35 scen.pkl ('cur' scenario, max difference): " + ", ".join(f"{rn} {d}" for rn, d in chk))
    t0 = time.time()
    RR = [x for x in run_pool(_replay_one, list(range(len(rows))), args.procs) if x]
    hrs = sum((max(t) - min(t)) / 3.6e12 for t in ([r["t"] for r in RR if r["run"] == rn] for rn in BASE_RUNS) if t)
    p(f"  replayed {len(RR)} windows ({time.time() - t0:.0f} s); calibration, today's landing: sim P&L {sum(r['res']['cur'][0] for r in RR):+.3f} SOL, "
      f"fills {sum(r['res']['cur'][1] for r in RR):.1f} | live {sum(r['lp'] for r in RR):+.3f} SOL, {sum(r['lf'] > 0 for r in RR)} fills (speed35: sim +3.280 / 224.6)")
    boots = np.zeros((0, len(targets)))
    if args.sol_boot > 0:
        t0 = time.time(); boots = np.array(run_pool(_boot_one, list(range(args.sol_boot)), args.procs))
        p(f"  bootstrap {args.sol_boot} draws ({time.time() - t0:.0f} s)")
    p(f"  P&L over these windows ({hrs:.1f} h; per day = x 24 / {hrs:.1f}); reference 'mix' = this run's real mix of paths; 'cur' = r36/r37 as they landed:")
    return sol_report(RR, ["cur", "mix"] + list(paths), "mix", hrs, args, p, boots, paths)

def sol_own(R, T, paths, D, args, p):
    """the analysed run's own live-armed T2 windows on a recorder tape (--tab, built by --build-tab)"""
    sys.path.insert(0, YOUNG)
    import y1_extract
    tab = args.tab
    tr = np.load(f"{tab}/trades.npy"); ids = json.load(open(f"{tab}/ids.json")); gid = {k: i for i, k in enumerate(ids)}
    smax = int(tr["slot"][-1]); order = np.argsort(tr["mint"], kind="stable"); ms = tr["mint"][order]
    MAXI = {}
    sl = np.load(f"{tab}/slots.npy")
    for s_, i_ in zip(sl["slot"].tolist(), sl["maxi"].tolist()): MAXI[s_] = max(i_, MAXI.get(s_, 0))
    rn = "own"
    # y1_extract reads T2 windows only and expects every arm / skip record to carry "trig": dip26 re-arm records (kind "rearm") are
    # left out of a filtered copy next to the tab (the replay rows are the T2 windows; re-arm tries still count in sections 1-5)
    src_run = args.run
    with open(args.run, errors="replace") as f_:
        if any('"kind":"rearm"' in l_ for l_ in f_):
            src_run = os.path.join(os.path.dirname(os.path.abspath(tab)), os.path.basename(args.run) + ".t2only.jsonl")
            with open(args.run, errors="replace") as fi, open(src_run, "w") as fo:
                for l_ in fi:
                    if '"kind":"rearm"' in l_ and ('"ev":"presend_live_arm"' in l_ or '"ev":"presend_live_skip"' in l_ or '"ev":"presend_live_disarm"' in l_): continue
                    fo.write(l_)
            p(f"  (dip26 re-arm records left out of the replay rows: {src_run})")
    _, rows0 = y1_extract.run("AMS", rn, src_run)
    rows = []; TAPES = {}
    for r in rows0:
        if r["live"] != "armed" or r["slot"] + 60 > smax or r["mint"] not in gid: continue
        g = gid[r["mint"]]; a, b = np.searchsorted(ms, g), np.searchsorted(ms, g, side="right")
        t = tr[np.sort(order[a:b])]; t = t[t["slot"] <= r["slot"] + 60]
        TAPES[r["sig"]] = [(int(x["slot"]), int(x["idx"]), int(x["j"]), int(x["buy"]), int(x["sol"]), int(x["tok"]), int(x["vsol"]), int(x["vtok"]), ids[int(x["user"])]) for x in t]
        r["run"] = rn; rows.append(r)
    sends, lands, wins, exits, sells, fills = load_tries(args.run)
    items = {s: ((v[2], v[3]), v[3], v[2], lands[s][2] / 1e6 - v[0] / 1e6) for s, v in sends.items() if s in lands and v[2] in paths}
    # the targets from the same samples as the ranks (a path mapped onto itself is then exactly today's landing); windows for the bootstrap
    wk = {t["sig"]: (t["seg"], t["w"]) for t in T}
    D = {x: collections.defaultdict(list) for x in paths}; D["mix"] = collections.defaultdict(list); per_w = collections.defaultdict(list)
    for s_, (g_, c_, p_, L_) in items.items():
        D[p_][c_].append(L_); D["mix"][c_].append(L_)
        if s_ in wk: per_w[wk[s_]].append((p_, c_, L_))
    _G.update(akeys=list(per_w.keys()), awin=per_w)
    pre = {rn: prep(sends, lands, wins, TAPES, MAXI)}
    mx = sell_mix(sends, lands, exits, sells, fills, MAXI)
    cfg, _ = run_cfg(R)
    tpsl = {rn: (cfg.get("tp", 0.2), cfg.get("sl", 0.2))}; size = (cfg.get("spend") or SIZE * 1e9) / 1e9
    targets = list(paths)
    _G.update(prep=pre, src={rn: Src(items)}, maxi=MAXI, tapes=TAPES, rows=rows, mix={rn: mx}, tpsl=tpsl, size=size, targets=targets)
    scens = {"cur": {rn: scen_from(scen_samples(pre[rn], MAXI))}}
    scens.update(_make_scens({x: D[x] for x in targets}))
    _G["scens"] = scens
    t0 = time.time()
    RR = [x for x in run_pool(_replay_one, list(range(len(rows))), args.procs) if x]
    t = [r["t"] for r in RR]; hrs = (max(t) - min(t)) / 3.6e12 if t else 0
    p(f"  own: {len(RR)} live-armed T2 windows of this run on the tape {tab} (to slot {smax}); TP/SL {tpsl[rn]}, size {size:.3f}; sell landing mix "
      + " ".join(f"+{h}:{w:.0%}@{q:.2f}" for h, q, w in (mx or [])))
    p(f"  calibration (sim 'cur' vs live, same windows): sim P&L {sum(r['res']['cur'][0] for r in RR):+.3f} SOL, fills {sum(r['res']['cur'][1] for r in RR):.1f} | "
      f"live {sum(r['lp'] for r in RR):+.3f} SOL, {sum(r['lf'] > 0 for r in RR)} fills ({time.time() - t0:.0f} s)")
    boots = np.zeros((0, len(targets)))
    if args.sol_boot > 0:
        t0 = time.time(); boots = np.array(run_pool(_boot_one, list(range(args.sol_boot)), args.procs))
        p(f"  bootstrap {args.sol_boot} draws ({time.time() - t0:.0f} s)")
    p(f"  P&L over these windows ({hrs:.1f} h); reference 'cur' = this run as it landed (its real mix):")
    return sol_report(RR, ["cur"] + list(paths), "cur", hrs, args, p, boots, paths)


# ------------------------------------------------------------------------------------------------------------------ tools
def make_fake(src, dst, name):
    """a synthetic two-path file: every try whose (n + w) is odd (the engine's rule for the 2nd path of a 2-path route) is relabelled
    `name` in its attempt / land / fill / close records; run_start's routes become default=<path>+<name>"""
    sigpath = {}; first = {}
    with open(src) as f:
        for line in f:
            if '"ev":"presend_attempt"' in line:
                try: r = json.loads(line)
                except Exception: continue
                if r["sig"] in first: continue
                first[r["sig"]] = 1
                if (r["n"] + r["w"]) % 2 == 1: sigpath[r["sig"]] = name
    n = 0
    with open(src) as f, open(dst, "w") as g:
        for line in f:
            if '"ev":"presend_attempt' in line or '"ev":"presend_live_fill"' in line or '"ev":"presend_live_close"' in line or '"ev":"run_start"' in line:
                try: r = json.loads(line)
                except Exception: g.write(line); continue
                if r["ev"] == "run_start":
                    if r.get("presend_live"): r["presend_live"]["routes"] = f"{r['presend_live'].get('routes', 'default=helius-ps')}+{name}"
                elif r["ev"] == "presend_live_close":
                    if any(s in sigpath for s in r.get("buy_sigs") or []): r["path"] = name; n += 1
                elif r.get("sig") in sigpath: r["path"] = name; n += 1
                line = json.dumps(r, separators=(",", ":")) + "\n"
            g.write(line)
    print(f"wrote {dst}: {len(sigpath)} txs relabelled {name} ({n} records)")

def build_tab(run, out, procs):
    """the recorder chunks overlapping the run's tries (+-10 min), decoded (ops/strategies/presend/real/decode.py) and merged
    (build.py) into OUT/tab for --sol own --tab OUT/tab. Read-only on the raw chunks (symlinks)."""
    t = [json.loads(l)["t"] for l in open(run) if '"ev":"presend_attempt"' in l]
    lo, hi = min(t) / 1e9 - 600, max(t) / 1e9 + 600
    fs = []
    for f in sorted(glob.glob(f"{COLLECT}/run_*/txs/txs_*.jsonl.gz")):
        ts = int(os.path.basename(f)[4:-9])
        if lo - 300 <= ts <= hi: fs.append(f)
    rec = f"{out}/rec/txs"; os.makedirs(rec, exist_ok=True)
    for f in fs:
        d = f"{rec}/{os.path.basename(f)}"
        if not os.path.exists(d): os.symlink(f, d)
    print(f"{len(fs)} chunks {datetime.datetime.fromtimestamp(lo, datetime.UTC):%m-%d %H:%M} .. {datetime.datetime.fromtimestamp(hi, datetime.UTC):%m-%d %H:%M} UTC", flush=True)
    subprocess.run([sys.executable, f"{REALD}/decode.py", f"{out}/dec", f"{out}/rec", "--procs", str(procs)], check=True)
    subprocess.run([sys.executable, f"{REALD}/build.py", f"{out}/dec", f"{out}/tab"], check=True)
    print(f"tab: {out}/tab  (use: --sol own --tab {out}/tab)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", nargs="?"); ap.add_argument("--log"); ap.add_argument("--from", dest="t_from"); ap.add_argument("--to", dest="t_to")
    ap.add_argument("--last-hours", type=float); ap.add_argument("--boot", type=int, default=2000); ap.add_argument("--ci", type=float, default=0.90)
    ap.add_argument("--sol", choices=["base", "own", "off"], default="base"); ap.add_argument("--tab"); ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--sol-boot", type=int, default=40, help="bootstrap draws for the SOL CI (0 = none; ~3 s each / procs)")
    ap.add_argument("--json"); ap.add_argument("--no-clients", action="store_true")
    ap.add_argument("--make-fake", nargs=2, metavar=("IN", "OUT")); ap.add_argument("--fake-name", default="fake-ps")
    ap.add_argument("--build-tab", nargs=2, metavar=("RUN", "OUTDIR"))
    args = ap.parse_args()
    if args.make_fake: return make_fake(args.make_fake[0], args.make_fake[1], args.fake_name)
    if args.build_tab: return build_tab(args.build_tab[0], args.build_tab[1], args.procs)
    if not args.run: ap.error("RUN.jsonl needed")
    if args.sol == "own" and not args.tab: ap.error("--sol own needs --tab DIR (make it with --build-tab RUN OUTDIR)")
    R = load(args.run)
    t_from = pkt_ns(args.t_from) if args.t_from else None; t_to = pkt_ns(args.t_to) if args.t_to else None
    if args.last_hours:
        tl = max(a["t"] for a in R["att"]); t_from = int(tl - args.last_hours * 3.6e12)
    if t_from or t_to: R = time_cut(R, t_from, t_to)
    out = report(R, args)
    if args.json:
        def conv(o):
            if isinstance(o, (np.floating, np.integer)): return o.item()
            if isinstance(o, (set, tuple)): return list(o)
            return str(o)
        json.dump(out, open(args.json, "w"), default=conv, indent=1)

if __name__ == "__main__":
    main()
