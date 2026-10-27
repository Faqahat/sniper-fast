#!/usr/bin/env python3
"""DENSITY: real/sim.py's run() (via filter/live28/sim28.run28: common random numbers per window, the live QUIET stop, no fill
before a live stop, dynamic arm checks) with four execution levers added. Everything else (landing donor transplant, view,
exit, follower and cost models) is sim.py's, imported unchanged. INFERRED outputs.
  1. k tries per pace slot, evenly spaced (sim.py already: next try at t + slot_ms / k).
  2. Send paths and the rate caps as the engine has them (pslive.rs): a try's route list is chosen by the leader class
     (cfg.routes: class -> [paths], 'default' otherwise); within it path (n + window id) % len; refused (never queued) when the
     path's token bucket (rate, burst rate/4), the global bucket, or the path's 1-second budget is empty.
  3. Path landing (INFERRED: pre-send never used these paths): a try's landing delay is the donor try's (helius-ps, MEASURED)
     plus delta(path, client, near/far, u) = Q_path(u) - Q_hps(u): quantile maps of send -> seen ms per leader client
     (helius-ps: pre-send tries r24-r28; other paths: regular buys' landed copies r22-r28, near leaders only). u = the donor
     try's own rank in helius-ps's distribution for its client. No regular-buy data on far leaders: delta 0 there (cfg.far_too
     applies the near delta to far leaders as well). A fill pays its path's tip.
  4. cfg.max_pos open pre-send positions (1 = live): tries pause only while max_pos positions are open."""
import math, heapq, collections, hashlib, json, bisect
import numpy as np
import sys
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real")
import sim, rlib
from sim import Win, exit_path, SMS

TIPS = {"helius-ps": 200_000, "nozomi": 1_000_000, "glaive": 100_000, "falcon+falcon-udp": 1_000_000, "0slot": 1_000_000,
        "landx-fra3": 1_000_000, "soyas": 1_000_000, "solami": 100_000, "helius-swqos": 200_000, "bolt": 1_000_000}
CLASS = {"AgaveBam": "bam", "FireBAM": "bam", "HarmonicAgave": "harmonic", "HarmonicFiredancer": "harmonic", "JitoLabs": "jito",
         "Firedancer": "fd"}
GRID = np.arange(0, 101, 5) / 100.0


def wkey(x):
    return int.from_bytes(hashlib.blake2b(f"{x['mint']}:{x['slot']}:{x['idx']}:{x.get('j', 0)}".encode(), digest_size=8).digest(), "little")


class PathModel:
    """send -> seen quantile functions (ms) per path x client x near/far (MEASURED inputs, see d1_paths.py)"""
    def __init__(self, path="/home/moiz/sniper-data/presend_density/paths.json", min_n=15, min_share=0.25):
        J = json.load(open(path))
        self.hps = {}
        for k, v in J["ps"].items():
            if ":" in k and v and v["n"] >= 200: self.hps[tuple(k.split(":"))] = np.array(v["grid"])
        tot = collections.Counter()
        for k, v in J["reg_path_client"].items():
            p, c = k.split("|"); tot[c] += v["n"]
        self.lane = {}
        for k, v in J["reg_path_client"].items():
            p, c = k.split("|")
            share = v["n"] / tot[c]
            if (v["n"] >= min_n and share >= min_share) or (v["n"] >= 10 and share >= 0.5):
                self.lane[(p, c)] = np.array(v["grid"])
        self.used = sorted(self.lane)

    def u_of(self, client, near, ms):
        g = self.hps.get((client, "near" if near else "far"))
        if g is None or ms is None or not np.isfinite(ms): return 0.5
        return float(np.interp(ms, g, GRID))

    def delta(self, path, client, near, u, scale=1.0, far_too=False):
        if path == "helius-ps": return 0.0
        if not near and not far_too: return 0.0
        q = self.lane.get((path, client))
        h = self.hps.get((client, "near"))
        if q is None or h is None: return 0.0
        return scale * (float(np.interp(u, GRID, q)) - float(np.interp(u, GRID, h)))


class LandingX(sim.Landing):
    """sim.Landing plus, per donor try: leader client, near/far, and its rank u in helius-ps's send->seen distribution"""
    def __init__(self, D, pm, near8, full_only=True, fband=0.15, probes=("P3",), mode="interp"):
        self.L = []; self.mode = mode; self.fband = fband
        for name in probes:
            for W in D[name]["wins"]:
                if full_only and (W["disarm"] or {}).get("why") != "expired": continue
                tr = [t for t in W["tries"] if t["res"] != "unknown"]
                if len(tr) < 8: continue
                tr.sort(key=lambda t: t["d"])
                d = np.array([t["d"] for t in tr])
                lam = np.array([t["lam"] if t["lam"] is not None else np.nan for t in tr])
                g = np.array([t["g"] for t in tr])
                cl = [t.get("client") or "?" for t in tr]
                nr = [(near8.get(t.get("sig")) or "")[:8] in near8["__set__"] for t in tr]
                u = [pm.u_of(c, n, t.get("ms_rx")) for c, n, t in zip(cl, nr, tr)]
                self.L.append(dict(key=(name, W["w"]), mint=W["mint"], f=(W["ct"] / SMS) % 1.0, d=d, lam=lam, g=g, drop=np.isnan(lam),
                                   n=len(tr), dmax=float(d[-1]), q=W.get("q_view", 0.5), cl=cl, near=nr, u=u))

    def nearest(self, x, d):
        D = x["d"]; n = x["n"]; k = int(np.searchsorted(D, d))
        j0 = min(max(k - 1, 0), n - 1); j1 = min(k, n - 1)
        if k <= 0: j0 = j1 = 0
        return j0 if abs(D[j0] - d) <= abs(D[j1] - d) else j1


def run_d(ck, store, wins_in, cfg, landing, model, view, seed, pm, exclude_self=True, our_id=None, whale_ids=None):
    pnames = sorted({p for v in cfg.routes.values() for p in v})
    buckets = {p: (sim.Bucket(cfg.path_rate), sim.Budget(cfg.path_rate)) for p in pnames}
    glob = sim.Bucket(cfg.global_rate)
    W = []
    for x in wins_in:
        w = Win(); w.trig = x; w.mint = x["mint"]; w.st = x["slot"]; w.ct = ck.cc(x["slot"], x["idx"])
        w.tok = None; w.done = False; w.why = None; w.tries = []; w.fill = None; w.fill_seen_d = math.inf; w.ext = None
        w.rate_skips = collections.Counter(); w.paused = 0; w.armed = False; w.n = 0; w.donor = None
        w.meta = dict(rng=np.random.default_rng([seed, wkey(x)]), path=None)
        W.append(w)
    W.sort(key=lambda w: (w.ct, w.trig.get("j", 0)))
    for q, w in enumerate(W): w.ix = q
    heap = []; pause = {}; tok_free = {}; armed_tok = {}; nxt = 0
    max_pos = getattr(cfg, "max_pos", 1)

    def paused_at(t):
        for k_ in [k_ for k_, (a, b) in pause.items() if b <= t]: del pause[k_]
        return sum(1 for a, b in pause.values() if a <= t < b) >= max_pos

    def end(w, why):
        w.done = True; w.why = why
        if armed_tok.get(w.mint) == w.ix: del armed_tok[w.mint]

    while nxt < len(W) or heap:
        t_arm = W[nxt].ct + 0.6 if nxt < len(W) else math.inf
        if heap and heap[0][0] < t_arm:
            t, ix = heapq.heappop(heap)
            w = W[ix]
            if w.done: continue
            d = t - w.ct
            lam, _g = landing.at(w.donor, d)
            a_now = w.ct + d
            E = int((a_now - view.eps(int(a_now // SMS) - w.st, w.q) - cfg.slot_lag_ms) // SMS)
            if E > w.en_slot: end(w, "expired"); continue
            if d >= w.stop_d: end(w, "whale_sold"); continue
            if d >= w.fill_seen_d: end(w, "filled"); continue
            x = w.trig
            if x.get("stop_at_d") is not None and d >= x["stop_at_d"]: end(w, "quiet"); continue
            k = cfg.k
            heapq.heappush(heap, (t + cfg.slot_ms / max(k, 1), ix))
            w.n += 1
            if cfg.one_position and paused_at(t): w.paused += 1; continue
            jn = landing.nearest(w.donor, d)
            client = w.donor["cl"][jn]; near = w.donor["near"][jn]
            rs = cfg.routes.get(CLASS.get(client, "default")) or cfg.routes["default"]
            path = rs[(w.n + w.ix) % len(rs)]
            pb, pc = buckets[path]
            if not pb.peek(t): w.rate_skips["rate_path"] += 1; continue
            if not glob.peek(t): w.rate_skips["rate_global"] += 1; continue
            if not pc.try_take(t): w.rate_skips["rate_path_config"] += 1; continue
            pb.take(t); glob.take(t)
            deadline = min(E + cfg.deadline_slots, w.en_slot)
            tk = w.tok
            ks = w.kt + int(np.searchsorted(w.seen, d, side="right"))
            psign = tk.vsol[ks] / tk.vtok[ks]
            lim = psign * (1.0 - cfg.drop)
            tr = dict(n=w.n, d=d, E=E, deadline=deadline, lim=lim, psign=psign, path=path)
            if lam is None:
                tr["res"] = "drop"; w.tries.append(tr); continue
            lam = lam + pm.delta(path, client, near, w.donor["u"][jn], cfg.path_scale, cfg.far_too)
            a = max(w.ct + d + lam + cfg.extra_lag_ms, tk.cc[ks] + 1e-3, E * SMS)
            S, I = ck.cc_inv(a)
            tr["S"] = S; tr["I"] = I
            if S > deadline: tr["res"] = "deadline"; w.tries.append(tr); continue
            kb = tk.before(S, I)
            nofill = x.get("nofill_before_d") is not None and d < x["nofill_before_d"]
            if (not nofill) and kb >= 0 and tk.vsol[kb] > 0 and tk.vtok[kb] > 0 and tk.vsol[kb] / tk.vtok[kb] <= lim and tk.vsol[kb] < rlib.UNTRADE_V:
                tr["res"] = "cand"
                if w.fill is None or (S, I) < (w.fill["S"], w.fill["I"]):
                    xk = next((j for j in range(ks + 1, kb + 1) if tk.vsol[j] / tk.vtok[j] <= lim), kb)
                    w.fill = dict(S=S, I=I, kb=kb, n=w.n, d=d, lim=lim, psign=psign, xgap=ck.cc(S, I) - tk.cc[xk], path=path)
                    w.fill_seen_d = max(d + 20.0, (ck.cc(S, I) - w.ct) + view.eps(S - w.st, w.q))
                    w.ext = exit_path(ck, tk, w, cfg, model, w.meta["rng"])
                    w.ext["pnl"] -= TIPS.get(path.split("#")[0], 1_000_000) - cfg.cost.tip          # the fill's path's tip (sim.Cost books helius-ps's)
                    pause[w.ix] = (w.ct + w.fill_seen_d, w.ext["t_sell"] + 60.0)
                    tok_free[w.mint] = w.ext["t_sell"] + 60.0 + cfg.margin_ms
            else:
                tr["res"] = "6042"
            w.tries.append(tr)
        else:
            w = W[nxt]; nxt += 1
            x = w.trig
            why = None
            if not x.get("force_arm"):
                if w.mint in armed_tok: why = "blocked_armed"
                elif tok_free.get(w.mint, -1.0) > w.ct: why = "blocked_position"
            if why:
                w.done = True; w.why = "skip:" + why; continue
            w.armed = True
            armed_tok[w.mint] = w.ix
            w.tok = store[w.mint]
            rng = w.meta["rng"]
            w.en_slot = int(math.floor((rlib.arr(x["slot"], x["idx"]) + cfg.live_ms + cfg.window_slots * SMS) / SMS))
            if exclude_self:
                w.donor = landing.pick(rng, (w.ct / SMS) % 1.0, exclude_keys={(x.get("probe"), x.get("w"))}, exclude_mint=x["mint"])
            else:
                w.donor = landing.pick(rng, (w.ct / SMS) % 1.0, exclude_mint=x["mint"])
            tk = w.tok
            w.kt = max(tk.before(x["slot"], x["idx"] + 0.5), 0)
            w.q = w.donor["q"]
            w.seen = view.seen_times(tk, w.kt, w.st, w.ct, w.q)
            ws = x.get("whale_sell")
            if ws is not None:
                kw = tk.before(ws[0], ws[1] + 0.5)
                if kw > w.kt and tk.pos[kw] == (ws[0], ws[1]): sd = w.seen[kw - w.kt - 1]
                else: sd = max(ck.cc(ws[0], ws[1]) - w.ct + view.eps(ws[0] - w.st, w.q), 0.0)
                w.stop_d = sd + cfg.whale_sell_ms
            else: w.stop_d = math.inf
            heapq.heappush(heap, (w.ct + cfg.live_ms + 0.5 + float(rng.random()) * 0.5, w.ix))
    return [finish_d(w, cfg) for w in W]


def finish_d(w, cfg):
    r = sim.finish(w, cfg)
    if w.armed:
        r["fill_path"] = (w.fill or {}).get("path")
        r["sent_by_path"] = dict(collections.Counter(t["path"] for t in w.tries))
    return r
