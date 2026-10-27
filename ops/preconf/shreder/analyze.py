#!/usr/bin/env python3
"""SHREDER PRECONF TRIAL ANALYSIS (read-only; Python stdlib only). Owner trial 2026-10-28 ~00:30-01:30 PKT.

Inputs (everything optional except one recorder dir):
  <run-dir>/fra/ (and optional ams/):
     <stream>_YYYYMMDD_HH.jsonl          pump VIEW of a stream (txs whose static keys hold the pump/pump-AMM program id)
     <stream>_YYYYMMDD_HH_<part>.rec.gz  full DATASET of a stream (all txs; binary records, gzip members) -- used for
                                         coverage / landed checks / ALT-CPI pump txs the view misses
     events.jsonl                        recorder connection events (connected windows)
     clock_start.json / clock_end.json   FRA<->AMS clock bracket (for an AMS engine)
  <collect-root>/run_*/txs/*.jsonl.gz    chain truth (FRA getBlock recording: slot, index, err, events; NO receive times)
  <run-dir>/engine/*.jsonl or --engine   live engine log (dip_*_rNN.jsonl); --engine-host fra|ams (default ams)
  --leaders-rpc                          slot leaders + clientId via getLeaderSchedule/getClusterNodes on the URL in
                                         ~/.config/sniper/ck_rpc_url (never printed); cached in <out>/leaders_cache.json
Outputs (<run-dir>/analysis/): report.md, summary.json, leaders.csv, engine_events.csv, never_landed_<m>.csv,
whatif_events.json; a short summary on stdout. All times PKT (UTC+5). Numbers are labelled MEASURED / MODELLED / INFERRED.
Run (right after the hour):
  python3 analyze.py --run-dir /home/moiz/sniper-data/preconf/<YYYYMMDD> [--engine-host fra|ams] [--leaders-rpc]
     [--engine FILE] [--from HH:MM --to HH:MM --date YYYY-MM-DD] [--streams pre,bin|fpre,fbin] [--quick] [--no-dataset]
Test: test_analyze.sh (make_synth.py builds a synthetic run with known injected values and checks recovery)."""
import argparse, base64, binascii, bisect, collections, datetime, glob, gzip, json, math, os, re, statistics, struct, sys, time, zlib

PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMPAMM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
TRADE_DISC = bytes([189, 219, 127, 211, 78, 230, 97, 238])
PKT_S = 5 * 3600
NS = 1_000_000_000
DUMP_MIN = 300_000_000          # dump = sell >= 0.3 SOL
TRIG_PROXY = 2_000_000_000      # without an engine log: "whale buy" proxy = buy >= 2 SOL
LAT_ROWS = [30, 40, 50, 60, 75, 100]   # landing latency rows (ms after the engine saw the dump); never one fixed value
HOLD_SLOTS = 5
FEE_RATE = 0.0125               # pump curve fee approximation, only inside MODELLED replays
HDR = struct.Struct("<IQqqQBBHI")      # dataset record header (44 bytes incl. rec_len)
T0 = time.time()
TYPES = ["trigger", "dump>=0.3", "buy>=0.3", "small<0.3", "other", "failed"]
TCODE = {k: i for i, k in enumerate(TYPES)}

def pkt(tns, ms=True):
    if tns is None: return "-"
    s = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(tns / NS + PKT_S))
    return s + (".%03d" % int((tns % NS) / 1e6) if ms else "")

def log(msg): print(f"[{time.time() - T0:6.1f}s] {msg}", file=sys.stderr, flush=True)

def pctl(v, q):
    k = (len(v) - 1) * q; f = math.floor(k); c = min(f + 1, len(v) - 1)
    return v[f] + (v[c] - v[f]) * (k - f)

def dist(vals):
    """{n, p10, p50, p90, mean, share_pre_earlier} of a list of ms values (positive = pre earlier)"""
    if not vals: return {"n": 0}
    v = sorted(vals); n = len(v)
    return {"n": n, "p10": round(pctl(v, .1), 3), "p50": round(pctl(v, .5), 3), "p90": round(pctl(v, .9), 3),
            "mean": round(sum(v) / n, 3), "share_pre_earlier": round(sum(1 for x in v if x > 0) / n, 4)}

def fmt_dist(d, unit="ms", lead=True):
    if not d or not d.get("n"): return "n=0"
    return (f"n={d['n']}  P10 {d['p10']:.2f} / P50 {d['p50']:.2f} / P90 {d['p90']:.2f} {unit}"
            + (f" (pre earlier {100 * d['share_pre_earlier']:.1f}%)" if lead else ""))

def fmtp(x): return "-" if x is None else f"{100 * x:.1f}%"

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
B58I = {c: i for i, c in enumerate(B58)}
_B58I3 = None
def key_of(sig):
    """first 8 bytes (big-endian int) of a base58 signature -- the join key with the binary dataset"""
    global _B58I3
    if _B58I3 is None:
        _B58I3 = {a + b + c: (B58I[a] * 58 + B58I[b]) * 58 + B58I[c] for a in B58 for b in B58 for c in B58}
    n = 0; L = len(sig); r = L % 3
    try:
        for ch in sig[:r]: n = n * 58 + B58I[ch]
        I3 = _B58I3
        for k in range(r, L, 3): n = n * 195112 + I3[sig[k:k + 3]]
    except KeyError: return None
    return n >> 448 if n < (1 << 512) else None

def b58enc(b):
    n = int.from_bytes(b, "big"); out = []
    while n: n, r = divmod(n, 58); out.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(out))

def b64d(s):
    try: return base64.b64decode(s + "=" * (-len(s) % 4))
    except (binascii.Error, ValueError): return None

def cu16(b, o):
    v = 0; sh = 0
    while True:
        x = b[o]; o += 1; v |= (x & 0x7F) << sh
        if not x & 0x80: return v, o
        sh += 7

def static_keys(raw):
    """static account keys of a VersionedTransaction (legacy or v0); [] on a parse problem"""
    try:
        n, o = cu16(raw, 0); o += 64 * n
        if raw[o] & 0x80: o += 1
        o += 3
        k, o = cu16(raw, o)
        return [b58enc(raw[o + 32 * j:o + 32 * (j + 1)]) for j in range(k)]
    except Exception:
        return []

def trade_events(evs):
    """pump TradeEvents of a chain record: [(mint, sol, tok, buy, user, vsol, vtok)]"""
    out = []
    for e in evs or ():
        raw = b64d(e)
        if not raw or raw[:8] != TRADE_DISC or len(raw) < 113: continue
        u = lambda o: int.from_bytes(raw[o:o + 8], "little")
        out.append((b58enc(raw[8:40]), u(40), u(48), raw[56] == 1, b58enc(raw[57:89]), u(97), u(105)))
    return out

def classify(tr, err, sig, trig_sigs, have_engine):
    if err is not None: return "failed"
    if sig in trig_sigs: return "trigger"
    if not tr: return "other"
    m = max(tr, key=lambda x: x[1]); buy, sol = m[3], m[1]
    if not buy and sol >= DUMP_MIN: return "dump>=0.3"
    if buy and not have_engine and sol >= TRIG_PROXY: return "trigger"
    if buy and sol >= DUMP_MIN: return "buy>=0.3"
    return "small<0.3"

def classify_p(p, sig, trig_sigs):
    """type of an unjoined view record from its decoded top-level pump instructions (max-cost / min-out bounds)"""
    if sig in trig_sigs: return "trigger"
    best = None
    for ins in p or ():
        k = ins[0]
        if k in ("sell", "amm_sell") and (ins[4] or 0) >= DUMP_MIN: return "dump>=0.3"
        if k in ("buy", "bxs", "amm_buy"):
            best = max(best or 0, (ins[4] if k != "bxs" else ins[3]) or 0)
    if best is None: return "other"
    return "buy>=0.3" if best >= DUMP_MIN else "small<0.3"

# --------------------------------------------------------------------------------------------------------------------------
class Stream:
    def __init__(self, mach, name):
        self.mach = mach; self.name = name
        self.t = {}; self.s = {}; self.p = {}; self.q = {}; self.c = {}
        self.st = collections.Counter(); self.ca_delay = []; self.win = []; self.win_info = {}; self.files = []
        self.tmin = None; self.tmax = None; self.silent_gaps = []
        # dataset (binary, all txs)
        self.ds_files = []; self.ds = collections.Counter(); self.slot_msgs = collections.Counter()
        self.rx_chain = {}      # chain pump key -> earliest rx (dataset; else view)
        self.rx_extra = {}      # other wanted keys (engine sigs, never-landed candidates) -> (rx, slot)
        self.cand_keys = {}     # never-landed candidate key -> static keys (from dataset bytes)

def load_view(mach, d, name, t_lo, t_hi, full=True):
    S = Stream(mach, name)
    files = sorted(f for f in glob.glob(os.path.join(d, f"{name}_*.jsonl")) if re.search(rf"/{name}_\d{{8}}_\d\d\.jsonl$", f))
    S.files = [os.path.basename(f) for f in files]
    T, Sl, Pp, Q, C, st, cad = S.t, S.s, S.p, S.q, S.c, S.st, S.ca_delay
    for fn in files:
        with open(fn, "rb") as f:
            for line in f:
                st["lines"] += 1
                if not line.endswith(b"\n"): st["no_newline_last_line"] += 1
                try: o = json.loads(line)
                except ValueError: st["bad_json"] += 1; continue
                t = o.get("t"); sig = o.get("sig")
                if not isinstance(t, int) or not sig: st["no_t_or_sig"] += 1; continue
                if (t_lo is not None and t < t_lo) or (t_hi is not None and t > t_hi): st["out_of_window"] += 1; continue
                if o.get("pe"): st["tx_parse_err"] += 1
                old = T.get(sig)
                if old is not None:
                    st["dups"] += 1
                    if t >= old: continue
                    st["dup_earlier_replaced"] += 1
                else: st["records"] += 1
                T[sig] = t; Sl[sig] = o.get("s")
                if full:
                    Q[sig] = o.get("q") or 0; C[sig] = o.get("c")
                    if o.get("p"): Pp[sig] = o["p"]
                ca = o.get("ca") or 0
                if ca and len(cad) < 400000: cad.append((t - ca) / 1e6)
                if S.tmin is None or t < S.tmin: S.tmin = t
                if S.tmax is None or t > S.tmax: S.tmax = t
    return S

def ds_files_of(d, name):
    return sorted(f for f in glob.glob(os.path.join(d, f"{name}_*.rec.gz")) if re.search(rf"/{name}_\d{{8}}_\d\d_[^/]*\.rec\.gz$", f))

def iter_dataset(path, stats):
    """(rx_ns, ca_ns, slot, flags, key, buf, tx_off, tx_len) per record; tolerates a truncated last gzip member"""
    with open(path, "rb") as raw:
        f = gzip.GzipFile(fileobj=raw)
        buf = b""; o = 0
        while True:
            try: chunk = f.read(1 << 22)
            except (EOFError, OSError, zlib.error):
                stats["truncated_member"] += 1; chunk = b""
                done = True
            else: done = not chunk
            if chunk:
                buf = buf[o:] + chunk; o = 0
            n = len(buf)
            while o + 44 <= n:
                rl, seq, rx, ca, slot, fl, nps, _r, tl = HDR.unpack_from(buf, o)
                end = o + 4 + rl
                if end > n: break
                to = o + 44
                if to + tl > end: stats["bad_record"] += 1; o = end; continue
                if tl < 65: stats["short_or_empty_tx"] += 1; o = end; continue
                c0 = buf[to]
                key = int.from_bytes(buf[to + 1:to + 9], "big") if 0 < c0 < 0x80 else None
                yield seq, rx, ca, slot, fl, key, buf, to, tl
                o = end
            if done:
                if o < n: stats["trailing_bytes"] += n - o
                return

def load_events(d):
    fn = os.path.join(d, "events.jsonl")
    if not os.path.exists(fn): return None
    out = []
    with open(fn, "rb") as f:
        for line in f:
            try: out.append(json.loads(line))
            except ValueError: pass
    out.sort(key=lambda e: e.get("t", 0) if isinstance(e.get("t"), int) else 0)
    return out

def connected_windows(events, name, t_lo, t_hi, rec_tmin, rec_tmax):
    info = collections.Counter()
    if events is None:
        if rec_tmin is None: return [], {"source": "none"}
        return [(rec_tmin, rec_tmax)], {"source": "record span (no events.jsonl)"}
    wins = []; open_t = None; last_t = None
    for e in events:
        if e.get("st") not in (name, "all"): continue
        ev = e.get("ev"); t = e.get("t")
        if not isinstance(t, int): continue
        info[ev] += 1; last_t = t
        if ev == "dropped": info["dropped_msgs"] += int(e.get("n") or 0)
        if ev in ("subscribed", "first_msg"):
            if open_t is None: open_t = t
        elif ev in ("stream_end", "error", "stop"):
            if open_t is not None: wins.append((open_t, t)); open_t = None
        elif ev == "status" and open_t is None and e.get("st") == name and (e.get("rate") or 0) > 0:
            open_t = t; info["opened_by_status"] += 1
    if open_t is not None: wins.append((open_t, max(last_t or open_t, rec_tmax or open_t)))
    if not wins and rec_tmin is not None:
        return [(rec_tmin, rec_tmax)], dict(info, source="record span (events had no subscribe)")
    lo = t_lo if t_lo is not None else -1; hi = t_hi if t_hi is not None else 1 << 62
    return [(max(a, lo), min(b, hi)) for a, b in wins if b > lo and a < hi], dict(info, source="events.jsonl")

def order_counts(L):
    """L = [(t_rx, q, chain_idx)] of one slot -> (concordant, discordant, tied-in-t) pairs, O(n log n) (Fenwick tree)"""
    L.sort(); n = len(L)
    rank = {v: j + 1 for j, v in enumerate(sorted(x[2] for x in L))}
    bit = [0] * (n + 1); conc = disc = ties = 0; ins = 0; j = 0
    while j < n:
        k = j
        while k < n and L[k][0] == L[j][0]: k += 1
        ties += (k - j) * (k - j - 1) // 2
        for x in range(j, k):
            r = rank[L[x][2]] - 1; less = 0
            while r > 0: less += bit[r]; r -= r & -r
            conc += less; disc += ins - less
        for x in range(j, k):
            r = rank[L[x][2]]
            while r <= n: bit[r] += 1; r += r & -r
            ins += 1
        j = k
    return conc, disc, ties

def in_wins(t, wins, margin=0):
    if t is None: return False
    for a, b in wins:
        if a + margin <= t <= b - margin: return True
    return False

def wins_len(wins): return sum(b - a for a, b in wins)

def cut_gaps(wins, gaps):
    out = []
    for wa, wb in wins:
        cur = wa
        for ga, gb in gaps:
            if gb <= cur or ga >= wb: continue
            if ga > cur: out.append((cur, ga))
            cur = max(cur, gb)
        if cur < wb: out.append((cur, wb))
    return out

class SlotClock:
    """slot -> local receive time (ns): median per slot of a stream, linear between slots"""
    def __init__(self): self.sl = []; self.tt = []
    def build(self, per):
        sl, tt = [], []
        for s in sorted(per):
            v = sorted(per[s]); t = v[len(v) // 2]
            if tt and t < tt[-1]: continue
            sl.append(s); tt.append(t)
        self.sl, self.tt = sl, tt
    def t_of(self, s):
        if not self.sl or s is None: return None
        j = bisect.bisect_left(self.sl, s)
        if j < len(self.sl) and self.sl[j] == s: return self.tt[j]
        a, b = (0, 1) if j == 0 else ((len(self.sl) - 2, len(self.sl) - 1) if j >= len(self.sl) else (j - 1, j))
        if a < 0 or b >= len(self.sl) or self.sl[b] == self.sl[a]: return self.tt[min(j, len(self.tt) - 1)]
        return int(self.tt[a] + (self.tt[b] - self.tt[a]) * (s - self.sl[a]) / (self.sl[b] - self.sl[a]))

# --------------------------------------------------------------------------------------------------------------------------
def chain_files(root, t_lo, t_hi):
    out = []
    for rd in sorted(glob.glob(os.path.join(root, "run_*"))):
        for fn in glob.glob(os.path.join(rd, "txs", "txs_*.jsonl.gz")):
            try: ep = int(os.path.basename(fn)[4:-9])
            except ValueError: continue
            if ep + 330 >= t_lo / NS - 5 and ep <= t_hi / NS + 900: out.append((ep, fn, rd))
    return sorted(out)

def load_gaps(run_dirs):
    sk = set()
    for rd in run_dirs:
        fn = os.path.join(rd, "gaps.jsonl")
        if not os.path.exists(fn): continue
        with open(fn) as f:
            for line in f:
                try: o = json.loads(line)
                except ValueError: continue
                if isinstance(o.get("slot"), int): sk.add(o["slot"])
    return sk

def load_tracked(run_dirs):
    m = set(); starts = []
    for rd in run_dirs:
        try: starts.append(json.load(open(os.path.join(rd, "run.json"))).get("start_time"))
        except Exception: pass
        fn = os.path.join(rd, "launches.jsonl")
        if not os.path.exists(fn): continue
        with open(fn, "rb") as f:
            for line in f:
                j = line.find(b'"mint":"')
                if j >= 0: m.add(line[j + 8:line.index(b'"', j + 8)].decode())
    return m, [s for s in starts if s]

# --------------------------------------------------------------------------------------------------------------------------
class Clock:
    """engine clock -> recorder clock. host fra (or an AMS recorder): identity. AMS engine + FRA recorder: subtract the
    bracketed AMS-FRA offset (interpolated between clock_start/clock_end); uncertainty +-best_rtt/2 + start/end drift."""
    def __init__(self, engine_host, rec_mach, fra_dir):
        self.same = (engine_host == rec_mach); self.note = ""; self.unc_ms = 0.0; self.pts = []; self.raw = {}
        if self.same:
            self.note = f"engine and recorder on the same machine ({rec_mach}): direct comparison"; return
        for nm in ("clock_start", "clock_end"):
            fn = os.path.join(fra_dir or "", nm + ".json")
            try: c = json.load(open(fn))
            except Exception: continue
            br = c.get("bracket") or {}
            if isinstance(br.get("offset_ms"), (int, float)) and isinstance(c.get("t"), int):
                self.pts.append((c["t"], float(br["offset_ms"]), float(br.get("best_rtt_ms") or 0)))
                self.raw[nm] = c
        self.pts.sort()
        if not self.pts:
            self.note = "AMS engine vs FRA recorder WITHOUT clock_start/end.json: raw cross-machine difference only (offset unknown)"
            self.unc_ms = None; return
        rtt = max(p[2] for p in self.pts)
        drift = abs(self.pts[-1][1] - self.pts[0][1]) if len(self.pts) > 1 else 0.0
        self.unc_ms = rtt / 2 + drift
        self.note = (f"AMS engine vs FRA recorder: offset (AMS−FRA) {', '.join('%.3f ms' % p[1] for p in self.pts)} at "
                     f"{', '.join(pkt(p[0]) for p in self.pts)}; corrected linearly; uncertainty ±{self.unc_ms:.3f} ms "
                     f"(best RTT/2 {rtt / 2:.3f} + drift {drift:.3f})")
    def off_ms(self, t):
        if self.same or not self.pts: return 0.0
        if len(self.pts) == 1 or t <= self.pts[0][0]: return self.pts[0][1]
        if t >= self.pts[-1][0]: return self.pts[-1][1]
        (ta, oa, _), (tb, ob, _) = self.pts[0], self.pts[-1]
        return oa + (ob - oa) * (t - ta) / (tb - ta)
    def __call__(self, t):
        if t is None: return None
        return t if self.same else int(t - self.off_ms(t) * 1e6)

def ev_time(o):
    """an engine record's own time: t, else t_fire / trig.t / land[2] / dump_first_rx; None for keyed records without a time"""
    t = o.get("t")
    if isinstance(t, int): return t
    land = o.get("land")
    for v in (o.get("t_fire"), (o.get("trig") or {}).get("t") if isinstance(o.get("trig"), dict) else None,
              land[2] if isinstance(land, list) and len(land) > 2 else None, o.get("dump_first_rx")):
        if isinstance(v, int): return v
    return None

def load_engine(path, t_lo, t_hi, pad_ns=120 * NS):
    E = dict(path=path, first_rx={}, kind={}, dumps={}, trig={}, tape=collections.defaultdict(list), fires=[], timing={},
             closes={}, arms=[], fills=[], exits=[], pcloses=[], realized=[], attempts=collections.defaultdict(list),
             run_start=None, our_sigs=set(), leader_client={}, n=collections.Counter())
    lo = (t_lo or 0) - pad_ns; hi = (t_hi or 1 << 62) + pad_ns
    fr = E["first_rx"]; kind = E["kind"]
    def seen(sig, t, k):
        if not sig or not isinstance(t, int) or t <= 0: return
        if sig not in fr or t < fr[sig]: fr[sig] = t
        if k == "trigger" or sig not in kind: kind[sig] = k
    with open(path, "rb") as f:
        for line in f:
            try: o = json.loads(line)
            except ValueError: E["n"]["bad"] += 1; continue
            ev = o.get("ev"); t = o.get("t")
            if ev == "run_start": E["run_start"] = o; continue
            if isinstance(o.get("leader"), str) and len(o["leader"]) > 30 and o.get("client"): E["leader_client"][o["leader"]] = o["client"]
            tt = ev_time(o)
            if tt is not None and not (lo <= tt <= hi): continue
            if tt is None and ev not in ("close", "presend_live_close", "presend_live_realized", "timing", "presend_attempt_land"): continue
            E["n"][ev] += 1
            if ev == "dump": E["dumps"][o["sig"]] = o; seen(o["sig"], t, "dump")
            elif ev in ("presend_live_arm", "presend_live_skip"):
                tr = o.get("trig") or {}
                seen(tr.get("sig"), tr.get("t"), "trigger")
                if ev == "presend_live_arm": E["arms"].append(o); E["trig"][tr.get("sig")] = tr
            elif ev == "presend_arm": seen(o.get("sig"), o.get("t"), "trigger"); E["trig"].setdefault(o.get("sig"), o)
            elif ev in ("presend_live_tape", "tape"): seen(o.get("sig"), t, "tape"); E["tape"][o.get("mint")].append(o)
            elif ev == "fire": E["fires"].append(o); seen(o.get("dump_sig"), o.get("t_dump_rx"), "dump")
            elif ev == "timing":
                if o.get("buy_sig"): E["timing"][o["buy_sig"]] = o
            elif ev == "close":
                for k_ in [o.get("buy_sig"), o.get("dump_sig"), (o.get("variant") or {}).get("sig") if isinstance(o.get("variant"), dict) else None]:
                    if k_: E["closes"][k_] = o
            elif ev == "presend_live_fill": E["fills"].append(o); E["our_sigs"].add(o.get("sig"))
            elif ev == "presend_live_exit": E["exits"].append(o)
            elif ev == "presend_live_close":
                E["pcloses"].append(o)
                for s in o.get("buy_sigs") or []: E["our_sigs"].add(s)
                for x in o.get("sell_sigs") or []: E["our_sigs"].add(x[0])
            elif ev == "presend_live_realized": E["realized"].append(o)
            elif ev == "presend_attempt": E["attempts"][(o.get("mint"), o.get("w"))].append(o)
            elif ev in ("buy_land", "sell_land"): E["our_sigs"].add(o.get("sig"))
    for f in E["fires"]:
        tm = E["timing"].get(f.get("buy_sig"))
        if tm: seen(f.get("dump_sig"), tm.get("dump_first_rx"), "dump")
        for s in [f.get("buy_sig")] + [v.get("sig") for v in (f.get("variants") or []) if isinstance(v, dict)]:
            if s: E["our_sigs"].add(s)
        cl = E["closes"].get(f.get("buy_sig"))
        if cl:
            for x in cl.get("sell_sigs") or []: E["our_sigs"].add(x[0])
    E["hold_slots"] = (E["run_start"] or {}).get("hold_slots") or HOLD_SLOTS
    return E

# --------------------------------------------------------------------------------------------------------------------------
def rpc_call(url, method, params, timeout=90, tries=3):
    import urllib.request
    req = urllib.request.Request(url, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
                                 headers={"Content-Type": "application/json"})
    for k in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r: j = json.loads(r.read())
            if "error" in j: raise RuntimeError(f"{method}: rpc error code {j['error'].get('code')}")
            return j["result"]
        except Exception:
            if k == tries - 1: raise
            time.sleep(2 * (k + 1))

def get_leaders(cache_fn, s_lo, s_hi, use_rpc):
    """({slot: leader}, {leader: clientId}, note); the URL is never printed or logged"""
    if os.path.exists(cache_fn):
        try:
            c = json.load(open(cache_fn)); sl = {int(k): v for k, v in c["slot_leader"].items()}
            if sl and min(sl) <= s_lo and max(sl) >= s_hi: return sl, c.get("client", {}), "cache " + os.path.basename(cache_fn)
        except Exception: pass
    if not use_rpc: return {}, {}, "no leader identities (run once with --leaders-rpc)"
    try: url = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
    except Exception: return {}, {}, "rpc url file missing"
    try:
        sl = {}
        ep = rpc_call(url, "getEpochInfo", [])
        start = ep["absoluteSlot"] - ep["slotIndex"]; L = ep["slotsInEpoch"]
        for base in sorted({start + ((s - start) // L) * L for s in (s_lo, s_hi)}):
            ls = rpc_call(url, "getLeaderSchedule", [base])
            for leader, idxs in (ls or {}).items():
                for i in idxs:
                    if s_lo - 8 <= base + i <= s_hi + 8: sl[base + i] = leader
        cl = {n["pubkey"]: n["clientId"] for n in (rpc_call(url, "getClusterNodes", []) or []) if n.get("pubkey") and n.get("clientId")}
        os.makedirs(os.path.dirname(cache_fn), exist_ok=True)
        json.dump({"slot_leader": sl, "client": cl, "fetched": time.time()}, open(cache_fn, "w"))
        return sl, cl, f"rpc getLeaderSchedule/getClusterNodes (cached {os.path.basename(cache_fn)})"
    except Exception as e:
        return {}, {}, "rpc failed (" + type(e).__name__ + ": " + re.sub(r"\S*://\S+", "<url>", str(e))[:100] + ")"

# --------------------------------------------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--engine", default=None)
    ap.add_argument("--engine-host", default="ams", choices=["ams", "fra"])
    ap.add_argument("--collect-root", default="/home/moiz/sniper-data/collect")
    ap.add_argument("--streams", default="pre,bin", help="preconf,binary stream names (pre,bin or fpre,fbin)")
    ap.add_argument("--from", dest="t_from", default=None, help="HH:MM PKT")
    ap.add_argument("--to", dest="t_to", default=None, help="HH:MM PKT")
    ap.add_argument("--date", default=None, help="PKT date of --from (YYYY-MM-DD)")
    ap.add_argument("--leaders-rpc", action="store_true")
    ap.add_argument("--no-dataset", action="store_true", help="ignore *.rec.gz (view-only coverage)")
    ap.add_argument("--quick", action="store_true", help="skip in-slot order analysis and what-if replays")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    RD = a.run_dir; OUT = a.out or os.path.join(RD, "analysis"); os.makedirs(OUT, exist_ok=True)
    PRE, BIN = [x.strip() for x in a.streams.split(",")][:2]
    notes, skipped = [], []

    # ---------------- window
    t_lo = t_hi = None
    if a.t_from or a.t_to:
        if a.date: d0 = datetime.date.fromisoformat(a.date)
        else:
            fs = sorted(glob.glob(os.path.join(RD, "*", f"{PRE}_*.jsonl")) + glob.glob(os.path.join(RD, "*", f"{BIN}_*.jsonl")))
            m = re.search(r"_(\d{8})_\d\d\.jsonl$", fs[0]) if fs else None
            d0 = datetime.datetime.strptime(m.group(1), "%Y%m%d").date() if m else datetime.datetime.utcfromtimestamp(time.time() + PKT_S).date()
        def at(hm, day):
            hh, mm = map(int, hm.split(":"))
            return int((datetime.datetime(day.year, day.month, day.day, hh, mm, tzinfo=datetime.timezone.utc).timestamp() - PKT_S) * NS)
        if a.t_from: t_lo = at(a.t_from, d0)
        if a.t_to:
            t_hi = at(a.t_to, d0)
            if t_lo is not None and t_hi <= t_lo: t_hi += 86400 * NS
    # ---------------- recorder views
    machines = {}
    for mach in ("fra", "ams"):
        d = os.path.join(RD, mach)
        if not os.path.isdir(d): skipped.append(f"{mach}/ missing"); continue
        evs = load_events(d)
        M = dict(dir=d, events=evs)
        for role, nm in (("pre", PRE), ("bin", BIN)):
            S = load_view(mach, d, nm, t_lo, t_hi, full=(role == "pre")); S.ds_files = [] if a.no_dataset else ds_files_of(d, nm); M[role] = S
        machines[mach] = M
        log(f"{mach}: {PRE} view {M['pre'].st['records']} ({M['pre'].st['dups']} dups, {len(M['pre'].ds_files)} dataset files); "
            f"{BIN} view {M['bin'].st['records']} ({M['bin'].st['dups']} dups, {len(M['bin'].ds_files)} dataset files)")
    if not machines: print("no recorder dirs (fra/ or ams/) in", RD); sys.exit(2)
    tm = [x for M in machines.values() for r in ("pre", "bin") for x in (M[r].tmin, M[r].tmax) if x]
    if not tm:
        # views empty: fall back to the dataset index span
        for M in machines.values():
            for r in ("pre", "bin"):
                for fn in M[r].ds_files:
                    try:
                        for line in open(fn[:-7] + ".idx.jsonl"):
                            j = json.loads(line); tm += [j.get("t0"), j.get("t1")]
                    except Exception: pass
        tm = [x for x in tm if isinstance(x, int)]
    if not tm: print("recorder dirs have no records"); sys.exit(2)
    if t_lo is None: t_lo = min(tm)
    if t_hi is None: t_hi = max(tm)
    log(f"window {pkt(t_lo)} .. {pkt(t_hi)} PKT")
    rec_mach = "ams" if (a.engine_host == "ams" and "ams" in machines and machines["ams"]["pre"].t) else ("fra" if "fra" in machines else "ams")
    for mach, M in machines.items():
        for r in ("pre", "bin"):
            S = M[r]
            S.win, S.win_info = connected_windows(M["events"], S.name, t_lo, t_hi, S.tmin, S.tmax)
    # ---------------- engine
    epath = a.engine
    if not epath:
        c = sorted(glob.glob(os.path.join(RD, "engine", "*.jsonl")))
        epath = c[-1] if c else None
    E = None
    clk = Clock(a.engine_host, rec_mach, machines.get("fra", {}).get("dir"))
    if epath and os.path.exists(epath):
        E = load_engine(epath, t_lo, t_hi)
        log(f"engine: {sum(E['n'].values())} events near the window ({os.path.basename(epath)}); clock: {clk.note}")
        if not E["fires"] and not E["arms"] and not E["dumps"]: notes.append("engine log has no dumps/fires/arms inside the window")
    else: skipped.append("engine log (none given / none in <run-dir>/engine/): engine joins + what-if skipped")
    trig_sigs = set(E["trig"]) if E else set()

    # ---------------- chain truth pass
    files = chain_files(a.collect_root, t_lo, t_hi)
    run_dirs = sorted({rd for _, _, rd in files})
    gaps = load_gaps(run_dirs); tracked, run_starts = load_tracked(run_dirs)
    bt_lo = t_lo // NS - 1; bt_hi = t_hi // NS + 1
    per_slot = {}                      # slot -> [n_all, n_ok]
    chain_pump = {}                    # key -> slot*8 + type code (pump.fun txs in window)
    joined = {m: {} for m in machines} # pre-view sig -> (slot, idx, err, trades, mints)
    chain_type = {}
    tapes = collections.defaultdict(list)
    want_tape = set()
    if E:
        for o in E["dumps"].values(): want_tape.add(o.get("mint"))
        for o in E["fires"]: want_tape.add(o.get("mint"))
        for o in E["arms"]: want_tape.add((o.get("trig") or {}).get("mint"))
        for o in E["fills"]: want_tape.add(o.get("mint"))
        want_tape.discard(None)
    pre_views = [(m, machines[m]["pre"].t) for m in machines]
    eng_sigs = E["first_rx"] if E else {}
    ch_s_min = ch_s_max = None; nlines = 0; npump = 0; seen_sigs = set(); tch = time.time()
    for ep, fn, rd in files:
        try:
            with gzip.open(fn, "rt") as f:
                for line in f:
                    nlines += 1
                    j = line.find('"sig":"')
                    if j < 0: continue
                    sig = line[j + 7:line.find('"', j + 7)]
                    haspump = PUMP in line
                    inpre = [m for m, pt in pre_views if sig in pt]
                    if not haspump and not inpre: continue
                    try: o = json.loads(line)
                    except ValueError: continue
                    bt = o.get("bt") or 0
                    if bt < bt_lo or bt > bt_hi: continue
                    if sig in seen_sigs: continue
                    seen_sigs.add(sig)
                    s = o["s"]; err = o.get("err"); mints = o.get("mints") or []
                    tr = None; ty = None
                    if inpre:
                        tr = trade_events(o.get("ev")) if err is None else []
                        for m in inpre: joined[m][sig] = (s, o["i"], err, tr, mints)
                    if PUMP in o.get("progs", ()):
                        npump += 1
                        ps = per_slot.get(s)
                        if ps is None: ps = per_slot[s] = [0, 0]
                        ps[0] += 1
                        if err is None: ps[1] += 1
                        if ch_s_min is None or s < ch_s_min: ch_s_min = s
                        if ch_s_max is None or s > ch_s_max: ch_s_max = s
                        if err is None:
                            if tr is None: tr = trade_events(o.get("ev"))
                            ty = classify(tr, err, sig, trig_sigs, E is not None)
                        else: ty = "failed"
                        k = key_of(sig)
                        if k is not None: chain_pump[k] = s * 8 + TCODE[ty]
                        if inpre or sig in eng_sigs: chain_type[sig] = ty
                    if err is None and want_tape and any(mm in want_tape for mm in mints):
                        if tr is None: tr = trade_events(o.get("ev"))
                        for (mint, sol, tok, buy, user, vsol, vtok) in tr:
                            if mint in want_tape: tapes[mint].append((s, o["i"], sig, buy, sol, tok, vsol, vtok, user))
        except (EOFError, OSError, zlib.error) as e:
            notes.append(f"chain file {os.path.basename(fn)} truncated/unreadable ({type(e).__name__}); used the readable part")
    seen_sigs = None
    for k in tapes: tapes[k].sort()
    log(f"chain: {len(files)} files, {nlines} lines, {npump} pump txs in window ({time.time() - tch:.1f}s)")
    chain_ok = npump > 0
    if not files: skipped.append("chain recording: no txs files overlap the window (coverage/accuracy vs chain skipped)")
    ch_complete_hi = (ch_s_max - 2) if ch_s_max else None
    def slot_in_chain(s): return chain_ok and s is not None and ch_s_min <= s <= ch_complete_hi and s not in gaps

    # ---------------- dataset pass (all txs) or view fallback
    eng_keys = {}
    if E:
        for sig in E["first_rx"]:
            k = key_of(sig)
            if k is not None: eng_keys[k] = sig
    for mach, M in machines.items():
        # never-landed candidates (pre view sigs absent from the chain), resolved later; collect their keys now
        pre = M["pre"]; J = joined[mach]
        M["cand"] = {}
        for sig, t in pre.t.items():
            if sig not in J:
                k = key_of(sig)
                if k is not None: M["cand"][k] = sig
        for r in ("pre", "bin"):
            S = M[r]; cand = M["cand"] if r == "pre" else {}
            if S.ds_files:
                td = time.time(); rx_chain = S.rx_chain; rx_extra = S.rx_extra; sm = S.slot_msgs; st = S.ds; prev = None
                for fn in sorted(S.ds_files, key=lambda x: (re.findall(r"_(\d{8}_\d\d)_", x)[-1:], int((re.findall(r"_(\d+)\.rec\.gz$", x) or ["0"])[0]))):
                    for seq, rx, ca, slot, fl, key, buf, to, tl in iter_dataset(fn, st):
                        if prev is not None and seq > prev + 1: st["seq_gaps"] += 1; st["seq_missing"] += seq - prev - 1
                        prev = seq
                        if rx < t_lo or rx > t_hi: st["out_of_window"] += 1; continue
                        st["records"] += 1; sm[slot] += 1
                        if fl & 2: st["parse_err_flag"] += 1
                        if key is None: st["no_sig"] += 1; continue
                        if key in chain_pump:
                            old = rx_chain.get(key)
                            if old is None or rx < old: rx_chain[key] = rx
                            if old is not None: st["dup_chain_sig"] += 1
                        if key in eng_keys or key in cand:
                            old = rx_extra.get(key)
                            if old is None or rx < old[0]: rx_extra[key] = (rx, slot)
                            if key in cand and key not in S.cand_keys:
                                S.cand_keys[key] = static_keys(bytes(buf[to:to + tl]))
                log(f"{mach} {S.name} dataset: {st['records']} recs, {len(rx_chain)} chain pump txs matched ({time.time() - td:.1f}s)")
            else:
                for sig, t in S.t.items():
                    k = key_of(sig)
                    if k is None: continue
                    if k in chain_pump: S.rx_chain[k] = t
                    if k in eng_keys or k in cand: S.rx_extra[k] = (t, S.s.get(sig))
                    S.slot_msgs[S.s.get(sig)] += 1
                if S.t: notes.append(f"{mach} {S.name}: no dataset files, coverage from the pump VIEW only (misses pump txs reached via lookup-table CPI)")
            # bin: silent gaps > 5 s are disconnections even if events.jsonl says connected
            if r == "bin":
                ts = sorted(set(S.t.values()))
                g = [(x, y) for x, y in zip(ts, ts[1:]) if y - x > 5 * NS]
                S.silent_gaps = g
                if g: S.win = cut_gaps(S.win, g)

    # ---------------- slot clock (bin view of the recorder machine, else any)
    clock = SlotClock(); clock_src = "none"
    for mach in [rec_mach] + [m for m in machines if m != rec_mach]:
        for r in ("bin", "pre"):
            S = machines[mach][r] if mach in machines else None
            if S and S.t:
                per = collections.defaultdict(list)
                for sig, t in S.t.items():
                    s = S.s.get(sig)
                    if s is not None and len(per[s]) < 64: per[s].append(t)
                clock.build(per); clock_src = f"{mach} {S.name} view"; break
        if clock.sl: break
    log(f"slot clock: {len(clock.sl)} slots from {clock_src}")
    ch_cover_end_t = clock.t_of(ch_complete_hi) if ch_complete_hi else None
    chain_cov_frac = max(0.0, min(1.0, (min(ch_cover_end_t, t_hi) - t_lo) / max(1, t_hi - t_lo))) if ch_cover_end_t else None

    # ---------------- leaders
    s_lo_w = min(per_slot) if per_slot else (clock.sl[0] if clock.sl else None)
    s_hi_w = max(per_slot) if per_slot else (clock.sl[-1] if clock.sl else None)
    if s_lo_w is not None: slot_leader, leader_client, lnote = get_leaders(os.path.join(OUT, "leaders_cache.json"), s_lo_w, s_hi_w, a.leaders_rpc)
    else: slot_leader, leader_client, lnote = {}, {}, "no slots"
    if E:
        for k, v in E["leader_client"].items(): leader_client.setdefault(k, v)
    log(f"leaders: {lnote}")
    def leader_of(s): return slot_leader.get(s) or f"win{s // 4 * 4}"
    def client_of(s):
        l = slot_leader.get(s)
        return leader_client.get(l, "unknown") if l else "unknown"

    R = {"window": {"from_pkt": pkt(t_lo), "to_pkt": pkt(t_hi), "minutes": round((t_hi - t_lo) / 6e10, 2)},
         "streams": [PRE, BIN], "recorder_machine_for_engine": rec_mach, "engine_host": a.engine_host, "clock": clk.note,
         "clock_unc_ms": clk.unc_ms, "skipped": skipped, "notes": notes, "leaders_source": lnote}
    md = []; P = md.append
    P("# Shreder preconf trial analysis\n")
    P(f"Window **{pkt(t_lo)} → {pkt(t_hi)} PKT** ({R['window']['minutes']} min). Recorder: {', '.join(machines)}; streams {PRE} (preconf) / {BIN} (shreds). "
      f"Engine log: {os.path.basename(epath) if E else 'none'} (host {a.engine_host}). Leaders: {lnote}. Generated {pkt(int(time.time() * NS), False)} PKT.\n")
    P("Labels: **MEASURED** = counted from recorded data; **MODELLED** = replay with stated assumptions; **INFERRED** = reasoning or cross-machine clock correction.\n")

    # ================= 1. coverage
    P("## 1. Coverage (MEASURED)\n")
    P(f"Chain truth = FRA getBlock recording: pump.fun txs (incl. failed) on mints created after the collector run started "
      f"({', '.join(pkt(int(x * NS), False) for x in run_starts) or '-'} PKT); older mints are not in it. Chain covers "
      f"{fmtp(chain_cov_frac)} of the window{' — LAGGING, last complete slot ' + str(ch_complete_hi) + ' ≈ ' + pkt(ch_cover_end_t) if chain_cov_frac is not None and chain_cov_frac < 0.999 else ''}; "
      f"{sum(1 for g in gaps if ch_s_min and ch_s_min <= g <= (ch_s_max or 0))} collector-skipped slots excluded. "
      f"Matching uses the full dataset (all txs) when present, else the pump view.\n")
    R["coverage"] = {}; leader_rows = []
    by_slot_chain = collections.defaultdict(list)  # slot -> [keys]
    for k, v in chain_pump.items(): by_slot_chain[v >> 3].append(k)
    for mach, M in machines.items():
        rc = {}
        for r in ("pre", "bin"):
            S = M[r]
            if not S.t and not S.ds.get("records"): rc[r] = {"records": 0}; continue
            tot = [0, 0]; got = [0, 0]; slots_tot = slots_got = 0
            per_leader = collections.defaultdict(lambda: [0, 0, 0, 0, 0])   # slots, covered slots, txs, txs_cov, txs_in_cov_slots
            rxc = S.rx_chain; share_hist = collections.Counter(); stray = [0, 0, 0]
            for s, (n_all, n_ok) in per_slot.items():
                if not slot_in_chain(s): continue
                ts = clock.t_of(s)
                if ts is None or not in_wins(ts, S.win, margin=NS): continue
                ks = by_slot_chain.get(s, ())
                c_all = sum(1 for k in ks if k in rxc); c_ok = sum(1 for k in ks if k in rxc and (chain_pump[k] & 7) != TCODE["failed"])
                tot[0] += n_all; tot[1] += n_ok; got[0] += c_all; got[1] += c_ok
                slots_tot += 1
                sh = c_all / n_all if n_all else 0
                share_hist["0" if sh == 0 else "(0,10%)" if sh < 0.1 else "[10,50%)" if sh < 0.5 else "[50,90%)" if sh < 0.9 else ">=90%"] += 1
                has = sh >= 0.1
                if 0 < sh < 0.1: stray[0] += 1; stray[1] += c_all; stray[2] += n_all
                slots_got += 1 if has else 0
                L = per_leader[leader_of(s)]; L[0] += 1; L[2] += n_all
                if has: L[1] += 1; L[3] += c_all; L[4] += n_all
            x = {"records": S.st["records"], "dataset_records": S.ds.get("records", 0), "connected_min": round(wins_len(S.win) / 6e10, 2),
                 "chain_txs": tot[0], "chain_txs_ok": tot[1], "covered_txs": got[0], "covered_txs_ok": got[1],
                 "tx_share": round(got[0] / tot[0], 4) if tot[0] else None, "tx_share_ok": round(got[1] / tot[1], 4) if tot[1] else None,
                 "chain_slots": slots_tot, "slots_with_any": slots_got, "slot_share": round(slots_got / slots_tot, 4) if slots_tot else None,
                 "slot_match_share_hist": dict(share_hist), "stray_slots(<10%)": stray[0], "stray_matched_txs": stray[1],
                 "slots_with_any_msg_by_shreder_slot": sum(1 for s_ in per_slot if slot_in_chain(s_) and S.slot_msgs.get(s_, 0) > 0 and in_wins(clock.t_of(s_), S.win, margin=NS))}
            if r == "pre":
                conn = 0; hist = collections.Counter(); byc = collections.defaultdict(lambda: [0, 0, 0, 0, 0])
                for l, v in per_leader.items():
                    fr_ = v[1] / v[0] if v[0] else 0
                    cl = leader_client.get(l, "unknown") if not l.startswith("win") else "n/a"
                    leader_rows.append(dict(machine=mach, leader=l, client=cl, slots=v[0], slots_with_pre=v[1], slot_frac=round(fr_, 3),
                                            txs=v[2], txs_in_covered_slots=v[4], covered_txs=v[3],
                                            tx_frac_in_covered_slots=round(v[3] / v[4], 3) if v[4] else None))
                    conn += fr_ >= 0.5
                    hist["0" if fr_ == 0 else "(0,0.5)" if fr_ < 0.5 else "[0.5,0.9)" if fr_ < 0.9 else ">=0.9"] += 1
                    for j in range(5): byc[cl][j] += v[j]
                in_cov = sum(v[4] for v in per_leader.values()); cov_n = sum(v[3] for v in per_leader.values())
                x.update({"leaders_seen": len(per_leader), "leaders_connected": conn, "leader_slot_frac_hist": dict(hist),
                          "tx_share_within_covered_slots": round(cov_n / in_cov, 4) if in_cov else None,
                          "by_client": {k: {"slots": v[0], "slot_frac": round(v[1] / v[0], 3) if v[0] else None,
                                            "tx_share": round(v[3] / v[2], 3) if v[2] else None,
                                            "tx_share_in_covered_slots": round(v[3] / v[4], 3) if v[4] else None} for k, v in sorted(byc.items())}})
            rc[r] = x
        R["coverage"][mach] = rc
        P(f"### {mach.upper()}\n")
        P("A slot counts as covered when ≥10% of its landed pump txs (by CHAIN slot) are in the stream; slots with a few stray matches (<10%: "
          "re-included txs / slot mismatch) are listed separately.\n")
        P("| stream | view recs | dataset recs | connected min | chain pump txs (ok) | matched | tx share | tx share ok-only | slots | covered slots | slot share |")
        P("|---|---|---|---|---|---|---|---|---|---|---|")
        for r in ("pre", "bin"):
            x = rc.get(r) or {}
            if "chain_txs" not in x: P(f"| {M[r].name} | 0 | | | | | | | | | |"); continue
            P(f"| {M[r].name} | {x['records']} | {x['dataset_records']} | {x['connected_min']} | {x['chain_txs']} ({x['chain_txs_ok']}) | {x['covered_txs']} | "
              f"{fmtp(x['tx_share'])} | {fmtp(x['tx_share_ok'])} | {x['chain_slots']} | {x['slots_with_any']} | {fmtp(x['slot_share'])} |")
        for r in ("pre", "bin"):
            x = rc.get(r) or {}
            if x.get("slot_match_share_hist"):
                P(f"\n{M[r].name}: per-slot matched-share histogram {x['slot_match_share_hist']}; stray slots {x['stray_slots(<10%)']} "
                  f"({x['stray_matched_txs']} txs); slots with ≥1 msg by the stream's own slot number: {x['slots_with_any_msg_by_shreder_slot']}")
        x = rc.get("pre") or {}
        if "leaders_seen" in x:
            P(f"\n{M['pre'].name} by slot leader ({'identities' if slot_leader else '4-slot leader windows (no identities)'}): {x['leaders_seen']} leaders, "
              f"{x['leaders_connected']} with ≥50% of their slots carrying preconf msgs; per-leader covered-slot fraction histogram {x['leader_slot_frac_hist']}. "
              f"Inside covered slots, preconf has **{fmtp(x['tx_share_within_covered_slots'])}** of the landed pump txs.\n")
            if slot_leader:
                P("| leader client | slots | share of slots with preconf | pump-tx share | pump-tx share in covered slots |"); P("|---|---|---|---|---|")
                for k, v in x["by_client"].items(): P(f"| {k} | {v['slots']} | {fmtp(v['slot_frac'])} | {fmtp(v['tx_share'])} | {fmtp(v['tx_share_in_covered_slots'])} |")
                P("")
    if leader_rows:
        with open(os.path.join(OUT, "leaders.csv"), "w") as f:
            ks = list(leader_rows[0]); f.write(",".join(ks) + "\n")
            for r in sorted(leader_rows, key=lambda r: (r["machine"], -r["slots"])): f.write(",".join(str(r[k]) for k in ks) + "\n")

    # ================= 2. lead times
    P("## 2. Lead times (MEASURED; positive = preconf earlier)\n")
    R["lead"] = {}
    for mach, M in machines.items():
        pre, bn = M["pre"], M["bin"]
        bytype = collections.defaultdict(list); byclient = collections.defaultdict(list); allv = []
        for k, tp in pre.rx_chain.items():
            tb = bn.rx_chain.get(k)
            if tb is None: continue
            v = (tb - tp) / 1e6; code = chain_pump[k]
            allv.append(v); bytype[TYPES[code & 7]].append(v); byclient[client_of(code >> 3)].append(v)
        vv = [(bn.t[s_] - t) / 1e6 for s_, t in pre.t.items() if s_ in bn.t]
        res = {"pre_vs_bin_chain_pump": {"all": dist(allv), "by_type": {k: dist(bytype[k]) for k in TYPES if bytype.get(k)},
                                         "by_client": {k: dist(v) for k, v in sorted(byclient.items())}},
               "pre_vs_bin_view_all": dist(vv), "ca_delay_ms": {"pre": dist(pre.ca_delay), "bin": dist(bn.ca_delay)}}
        R["lead"][mach] = res
        P(f"### {mach.upper()}: {pre.name} vs {bn.name}, same machine\n")
        P(f"- chain-truth pump txs, all: {fmt_dist(res['pre_vs_bin_chain_pump']['all'])}")
        for k, d in res["pre_vs_bin_chain_pump"]["by_type"].items(): P(f"  - {k}: {fmt_dist(d)}")
        P(f"- every pump-view tx in both views (incl. untracked mints): {fmt_dist(res['pre_vs_bin_view_all'])}")
        if slot_leader:
            P("- by leader client: " + "; ".join(f"{k}: {fmt_dist(d)}" for k, d in res["pre_vs_bin_chain_pump"]["by_client"].items()))
        P(f"- server created_at → local receive (t − ca, includes the Shreder−local clock offset): {pre.name} {fmt_dist(res['ca_delay_ms']['pre'], lead=False)}; {bn.name} {fmt_dist(res['ca_delay_ms']['bin'], lead=False)}\n")
    if "fra" in machines and "ams" in machines:
        fb, ab = machines["fra"]["bin"].t, machines["ams"]["bin"].t
        dd = [(fb[s] - ab[s]) / 1e6 for s in fb if s in ab]
        R["fra_minus_ams_bin_ms"] = dist(dd)
        P(f"FRA − AMS receive time, same sig ({BIN}): {fmt_dist(dist(dd), lead=False)} (INFERRED: clock offset + path difference, not separable).\n")
    eng_rows = []
    if E and rec_mach in machines:
        M = machines[rec_mach]; pre, bn = M["pre"], M["bin"]
        def rx_pre(sig):
            t = pre.t.get(sig)
            if t is None:
                k = key_of(sig); x = pre.rx_extra.get(k) if k is not None else None
                t = x[0] if x else None
            return t
        def rx_bin(sig):
            t = bn.t.get(sig)
            if t is None:
                k = key_of(sig); x = bn.rx_extra.get(k) if k is not None else None
                t = x[0] if x else None
            return t
        bk = collections.defaultdict(list); bk_raw = collections.defaultdict(list); bk_bin = collections.defaultdict(list)
        have = collections.Counter(); tot = collections.Counter(); byclient = collections.defaultdict(list)
        for sig, te_raw in E["first_rx"].items():
            te = clk(te_raw)
            if not (t_lo <= te <= t_hi) or not in_wins(te, pre.win): continue
            k = "trigger" if E["kind"].get(sig) == "trigger" else ("dump>=0.3" if E["kind"].get(sig) == "dump" else (chain_type.get(sig) or "other"))
            tot[k] += 1
            tp = rx_pre(sig)
            if tp is not None:
                have[k] += 1; bk[k].append((te - tp) / 1e6); bk_raw[k].append((te_raw - tp) / 1e6)
                s = pre.s.get(sig)
                if s is not None and slot_leader: byclient[client_of(s)].append((te - tp) / 1e6)
            tb = rx_bin(sig)
            if tb is not None: bk_bin[k].append((te - tb) / 1e6)
        R["lead"]["pre_vs_engine"] = {"recorder": rec_mach, "engine_host": a.engine_host, "clock": clk.note, "unc_ms": clk.unc_ms,
                                      "all": dict(dist([v for L in bk.values() for v in L]), events=sum(tot.values()), with_pre=sum(have.values())),
                                      "by_type": {k: dict(dist(bk[k]), events=tot[k], with_pre=have[k]) for k in tot},
                                      "raw_uncorrected": {k: dist(v) for k, v in bk_raw.items()},
                                      "engine_minus_bin": {k: dist(v) for k, v in bk_bin.items()}, "by_client": {k: dist(v) for k, v in byclient.items()}}
        lab = "MEASURED" if clk.same else "INFERRED (cross-machine, offset-corrected" + (f", ±{clk.unc_ms:.2f} ms)" if clk.unc_ms is not None else ", offset UNKNOWN)")
        P(f"### {pre.name} vs engine first receive — {lab}\n")
        P(f"Clock: {clk.note}. Engine first receive = earliest engine record of that sig (dump t / timing.dump_first_rx / t_dump_rx; trigger t; tape t). "
          f"Only events while {pre.name} was connected.\n")
        P("| type | engine events | with a preconf copy | lead P10 | P50 | P90 ms | pre earlier | raw (uncorrected) P50 |"); P("|---|---|---|---|---|---|---|---|")
        for k in sorted(tot, key=lambda x: -tot[x]):
            d = dist(bk[k]); dr = dist(bk_raw[k])
            P(f"| {k} | {tot[k]} | {have[k]} ({100 * have[k] / tot[k]:.0f}%) | {d.get('p10', '-')} | {d.get('p50', '-')} | {d.get('p90', '-')} | "
              f"{fmtp(d.get('share_pre_earlier')) if d.get('n') else '-'} | {dr.get('p50', '-')} |")
        P("")
        if bk_bin: P(f"Sanity (engine first receive − {bn.name} receive, corrected; ≈ path difference): " + "; ".join(f"{k} {fmt_dist(dist(v), lead=False)}" for k, v in bk_bin.items()) + "\n")
        if len(byclient) > 1: P("By leader client: " + "; ".join(f"{k}: {fmt_dist(dist(v))}" for k, v in sorted(byclient.items())) + "\n")
    P("Preconf vs FRA chain-recording receive time: **not available** — the collector is getBlock-based (block time `bt`, 1 s resolution; no per-tx receive time).\n")

    # ================= 3. accuracy
    P("## 3. Accuracy (MEASURED)\n")
    R["accuracy"] = {}
    for mach, M in machines.items():
        pre = M["pre"]
        if not pre.t or not chain_ok: continue
        J = joined[mach]
        elig = lok = lerr = absent = unknown = outside = same = 0; sdiff = collections.Counter(); nl_rows = []
        for sig, tp in pre.t.items():
            s = pre.s.get(sig)
            if s is None or not slot_in_chain(s) or not slot_in_chain(s + 2): outside += 1; continue
            j = J.get(sig)
            if j:
                elig += 1
                if j[2] is None: lok += 1
                else: lerr += 1
                d = j[0] - s; sdiff[d] += 1; same += d == 0
                continue
            mints = {ins[1] for ins in pre.p.get(sig, ()) if len(ins) > 1 and ins[1]}
            if not (mints & tracked):
                k = key_of(sig); keys = pre.cand_keys.get(k) if k is not None else None
                if keys: mints |= set(keys)
            hit = mints & tracked
            if not hit: unknown += 1; continue
            elig += 1; absent += 1
            if len(nl_rows) < 20000: nl_rows.append((pkt(tp), s, sig, ";".join(sorted(hit)), "|".join(str(i[0]) for i in pre.p.get(sig, ()))))
        x = {"pre_records": len(pre.t), "outside_complete_chain": outside, "untracked_or_unknown_mint": unknown, "judged": elig,
             "landed_ok": lok, "landed_failed": lerr, "never_landed": absent,
             "land_share": round((lok + lerr) / elig, 4) if elig else None, "never_landed_share": round(absent / elig, 4) if elig else None,
             "failed_share": round(lerr / elig, 4) if elig else None, "same_slot_share": round(same / (lok + lerr), 4) if lok + lerr else None,
             "slot_diff_hist": {str(k): v for k, v in sorted(sdiff.items())}}
        if not a.quick:
            byslot = collections.defaultdict(list)
            for sig, jj in J.items(): byslot[jj[0]].append((pre.t[sig], pre.q.get(sig, 0), jj[1]))
            conc = disc = ties = 0; taus = []
            for s, L in byslot.items():
                if len(L) < 2: continue
                c_, d_, t_ = order_counts(L)
                conc += c_; disc += d_; ties += t_
                if c_ + d_: taus.append((c_ - d_) / (c_ + d_))
            x["order"] = {"slots": len(taus), "pairs": conc + disc, "pair_agreement": round(conc / (conc + disc), 4) if conc + disc else None,
                          "tied_pairs_same_t": ties, "kendall_tau_median_per_slot": round(statistics.median(taus), 4) if taus else None}
        R["accuracy"][mach] = x
        if nl_rows:
            with open(os.path.join(OUT, f"never_landed_{mach}.csv"), "w") as f:
                f.write("t_pkt,pre_slot,sig,tracked_mints,pre_ix_kinds\n")
                for row in nl_rows: f.write(",".join(str(v) for v in row) + "\n")
        P(f"### {mach.upper()} ({pre.name} view)\n")
        P(f"- {x['pre_records']} preconf pump-view txs; {outside} outside the complete chain range and {unknown} on untracked/unknown mints (not judged)")
        P(f"- judged {elig}: landed OK {lok}, landed FAILED (err ≠ null) {lerr}, never landed {absent} → land {fmtp(x['land_share'])}, "
          f"**never landed {fmtp(x['never_landed_share'])}**, failed {fmtp(x['failed_share'])}")
        P(f"- same slot as chain: {fmtp(x['same_slot_share'])} (chain − preconf slot: {x['slot_diff_hist']})")
        if x.get("order"):
            o = x["order"]
            P(f"- order inside a slot: arrival order agrees with chain index on **{fmtp(o['pair_agreement'])}** of {o['pairs']} pairs in {o['slots']} slots "
              f"(median per-slot Kendall tau {o['kendall_tau_median_per_slot']}); {o['tied_pairs_same_t']} pairs had identical receive times (batched, not judged)")
        P("")

    # ================= 4. what-if
    if E and not a.quick and rec_mach in machines:
        whatif(E, machines[rec_mach], clk, tapes, clock, joined.get(rec_mach, {}), t_lo, t_hi, R, P, OUT)
    else: P("## 4. What-if\n\nskipped (" + ("--quick" if E else "no engine log") + ")\n")

    # ================= 5. data quality
    P("## 5. Data quality\n")
    R["quality"] = {}
    for mach, M in machines.items():
        q = {}; P(f"### {mach.upper()}")
        for r in ("pre", "bin"):
            S = M[r]; st = S.st
            q[r] = {"stream": S.name, "view_files": S.files, "view_stats": dict(st), "dataset_files": [os.path.basename(f) for f in S.ds_files],
                    "dataset_stats": dict(S.ds), "connected_windows": [[pkt(x), pkt(y)] for x, y in S.win], "connected_min": round(wins_len(S.win) / 6e10, 2),
                    "events": {k: v for k, v in S.win_info.items() if k != "source"}, "windows_source": S.win_info.get("source"),
                    "silent_gaps_over_5s": [[pkt(x), round((y - x) / 1e9, 1)] for x, y in S.silent_gaps][:50],
                    "connection_epochs": sorted({c for c in S.c.values() if c is not None}) if S.c else "not stored for this stream"}
            v = q[r]
            P(f"- {S.name}: view {', '.join(v['view_files']) or 'none'} — {st.get('records', 0)} recs, {st.get('dups', 0)} duplicates, "
              f"{st.get('bad_json', 0)} bad/truncated lines, {st.get('tx_parse_err', 0)} tx parse errors; dataset {len(v['dataset_files'])} files "
              f"{dict(S.ds) if S.ds else ''}; connected {v['connected_min']} min in {len(v['connected_windows'])} window(s) [{v['windows_source']}] "
              f"{'; '.join(x_ + ' → ' + y_[11:] for x_, y_ in v['connected_windows'][:6])}; events {v['events']}; connection epochs {v['connection_epochs']}"
              + (f"; silent gaps >5 s (excluded): {v['silent_gaps_over_5s'][:5]}" if v['silent_gaps_over_5s'] else ""))
        R["quality"][mach] = q
        P("")
    P(f"- chain recording: {len(files)} files ({', '.join(os.path.basename(r) for r in run_dirs) or 'none'}), {npump} pump txs in window, "
      f"window coverage {fmtp(chain_cov_frac)}, slots {ch_s_min}..{ch_complete_hi}, {len(tracked)} tracked mints")
    P(f"- clocks: recorder/engine `t` are CLOCK_REALTIME ns of their own machine. {clk.note}.")
    if clk.raw:
        for nm, c in clk.raw.items():
            P(f"  - {nm}: fra_sync {c.get('fra_sync', {}).get('tool')} offset {c.get('fra_sync', {}).get('offset_ms')} ms; ams_sync {c.get('ams_sync', {}).get('tool')} "
              f"offset {c.get('ams_sync', {}).get('offset_ms')} ms; bracket n={c.get('bracket', {}).get('n')} best_rtt {c.get('bracket', {}).get('best_rtt_ms')} ms "
              f"offset {c.get('bracket', {}).get('offset_ms')} (p50 {c.get('bracket', {}).get('offset_ms_p50')}); ping {c.get('ping')}")
    P(f"- slot clock from {clock_src}; leaders: {lnote}")
    if skipped: P("- skipped: " + "; ".join(skipped))
    if notes: P("- notes: " + "; ".join(notes))
    R["quality"]["chain"] = {"files": len(files), "pump_txs": npump, "coverage_frac": chain_cov_frac, "slot_lo": ch_s_min,
                             "slot_hi_complete": ch_complete_hi, "tracked_mints": len(tracked)}
    R["runtime_s"] = round(time.time() - T0, 1)
    try:
        import resource; R["peak_rss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
    except Exception: R["peak_rss_mb"] = None
    P(f"\n_runtime {R['runtime_s']} s, peak memory {R['peak_rss_mb']} MB_\n")
    with open(os.path.join(OUT, "report.md"), "w") as f: f.write("\n".join(md) + "\n")
    with open(os.path.join(OUT, "summary.json"), "w") as f: json.dump(R, f, indent=1, default=str)
    short(R, OUT)

# --------------------------------------------------------------------------------------------------------------------------
def curve_buy(vsol, vtok, sol_in):
    net = sol_in * (1 - FEE_RATE)
    return vtok - vsol * vtok / (vsol + net)

def curve_sell(vsol, vtok, tok):
    return (vsol - vsol * vtok / (vtok + tok)) * (1 - FEE_RATE)

def exit_curve(vsol, vtok, net_in, tok):
    """curve SOL out (before fee) for selling `tok` at a recorded state (vsol, vtok) that does NOT contain our own buy of net_in:
    our buy is put back in (same k = vsol*vtok, vsol + net_in), then our tokens are sold"""
    vs = vsol + net_in; kk = vsol * vtok; vt = kk / vs
    return vs - kk / (vt + tok)

class TapeView:
    """one mint's chain trades (ours removed) with an arrival time each on the recorder clock (bin view; else the engine's
    tape time, clock-corrected; else the slot clock). k_at(T) = trades that arrived by T -> our buy lands after them."""
    def __init__(self, rows, our, rx_of, clock):
        self.rows = [r for r in rows if r[2] not in our and r[8] not in our]
        self.arr = []; m = 0
        for r in self.rows:
            t = rx_of(r[2])
            if t is None: t = (clock.t_of(r[0]) or 0) + 100_000 * min(r[1], 3000)
            m = max(m, t); self.arr.append(m)
        self.slots = [r[0] for r in self.rows]
    def state_at(self, k):
        if not self.rows: return None
        if k <= 0:
            r = self.rows[0]
            return (r[6] - r[4], r[7] + r[5]) if r[3] else (r[6] + r[4], r[7] - r[5])
        r = self.rows[min(k, len(self.rows)) - 1]
        return (r[6], r[7])
    def k_at(self, T): return bisect.bisect_right(self.arr, T)
    def k_after_slot(self, s): return bisect.bisect_right(self.slots, s)

def ps_sim(tv, k0, lim, spend, en_slot):
    """pre-send fill on the tape from position k0: (k, pnl_lamports) or None"""
    net = spend / (1 + FEE_RATE); n = len(tv.rows)
    for k in range(max(k0, 1), n + 1):
        r = tv.rows[k - 1]
        if r[0] > en_slot: return None
        if r[7] and r[6] / r[7] <= lim:
            tok = r[7] - r[6] * r[7] / (r[6] + net); s_in = r[0]; val = None
            for k2 in range(k + 1, n + 1):
                r2 = tv.rows[k2 - 1]
                if r2[0] > s_in + 2: break
                v = exit_curve(r2[6], r2[7], net, tok) * (1 - FEE_RATE)
                if v >= spend * 1.10 or v <= spend * 0.80: val = v; break
            if val is None:
                st2 = tv.state_at(tv.k_after_slot(s_in + 2)); val = exit_curve(st2[0], st2[1], net, tok) * (1 - FEE_RATE)
            return (k, val - spend)
    return None

def ps_sim_tries(tv, tries, L, lead, spend, en_slot):
    """pre-send window with discrete tries [(send_t recorder clock, limit)]: (k, pnl_lamports) of the first try that fills, or None"""
    net = spend / (1 + FEE_RATE); n = len(tv.rows)
    for t_send, lim in tries:
        k = tv.k_at(t_send - int(lead * 1e6) + int(L * 1e6))
        if k < 1: continue
        r = tv.rows[k - 1]
        if r[0] > en_slot: return None
        if not r[7] or r[6] / r[7] > lim: continue
        tok = r[7] - r[6] * r[7] / (r[6] + net); s_in = r[0]; val = None
        for k2 in range(k + 1, n + 1):
            r2 = tv.rows[k2 - 1]
            if r2[0] > s_in + 2: break
            v = exit_curve(r2[6], r2[7], net, tok) * (1 - FEE_RATE)
            if v >= spend * 1.10 or v <= spend * 0.80: val = v; break
        if val is None:
            st2 = tv.state_at(tv.k_after_slot(s_in + 2)); val = exit_curve(st2[0], st2[1], net, tok) * (1 - FEE_RATE)
        return (k, val - spend)
    return None

def whatif(E, M, clk, tapes, clock, J, t_lo, t_hi, R, P, OUT):
    P("## 4. What-if\n")
    pre, bn = M["pre"], M["bin"]
    def rx_pre(sig):
        t = pre.t.get(sig)
        if t is None:
            k = key_of(sig); x = pre.rx_extra.get(k) if k is not None else None
            t = x[0] if x else None
        return t
    fr = E["first_rx"]
    tape_t = {}
    for mint, L in E["tape"].items():
        for o in L:
            if o.get("sig") and isinstance(o.get("t"), int): tape_t.setdefault(o["sig"], clk(o["t"]))
    def rx_of(sig): return bn.t.get(sig) or tape_t.get(sig) or (clk(fr[sig]) if sig in fr else None)
    our = set(E["our_sigs"]); ourw = set()
    for rows_ in tapes.values():
        for r in rows_:
            if r[2] in our: ourw.add(r[8])
    our |= ourw
    lab = "MEASURED" if clk.same else "INFERRED (cross-machine clock correction" + (f" ±{clk.unc_ms:.2f} ms)" if clk.unc_ms is not None else ", offset unknown)")
    W = {}
    rows = []
    for f in E["fires"]:
        tf = clk(f.get("t_fire") or f.get("t"))
        if tf is None or not (t_lo <= tf <= t_hi): continue
        ds = f.get("dump_sig"); te_raw = fr.get(ds) or f.get("t_dump_rx"); te = clk(te_raw); tp = rx_pre(ds)
        lead = (te - tp) / 1e6 if (te and tp) else None
        cl = E["closes"].get(f.get("buy_sig")) or E["closes"].get(ds) or next((E["closes"][v.get("sig")] for v in (f.get("variants") or [])
                                                                                if isinstance(v, dict) and v.get("sig") in E["closes"]), {})
        tm = E["timing"].get(f.get("buy_sig")) or {}
        res = cl.get("result"); pnl = cl.get("curve_pnl") if res == "sold" else (0 if res else None)
        land_ms = ((tm["buy_first_rx"] - te_raw) / 1e6) if (tm.get("buy_first_rx") and te_raw) else None
        row = dict(kind="fire", t_pkt=pkt(tf), mint=f.get("mint"), dump_sig=ds, buy_sig=f.get("buy_sig"), client=f.get("client"),
                   connected=in_wins(te, pre.win), has_pre=tp is not None, lead_ms=round(lead, 3) if lead is not None else None, result=res,
                   curve_pnl_sol=(pnl / 1e9 if isinstance(pnl, (int, float)) else None), land_ms_after_dump=round(land_ms, 2) if land_ms else None)
        rws = tapes.get(f.get("mint"))
        if rws and te:
            tv = TapeView(rws, our, rx_of, clock)
            spend = f.get("spend") or 550_000_000; min_out = f.get("min_out") or 0; hold = E["hold_slots"]
            def sim(T, k=None):
                if not tv.rows: return None
                if k is None: k = tv.k_at(T)
                stt = tv.state_at(k)
                net = spend / (1 + FEE_RATE); tok = stt[1] - stt[0] * stt[1] / (stt[0] + net)
                if tok < min_out: return ["nofill", 0.0]
                s_in = tv.rows[k - 1][0] if k else tv.rows[0][0]
                st2 = tv.state_at(tv.k_after_slot(s_in + hold))
                return ["fill", (exit_curve(st2[0], st2[1], net, tok) * (1 - FEE_RATE) - spend) / 1e9]
            mrows = {}
            land = cl.get("land") if isinstance(cl.get("land"), list) and len(cl.get("land")) >= 2 else None
            for L in LAT_ROWS + (["live"] if (land_ms or land) else []):
                if L == "live" and land:
                    # base = our REAL chain position; preconf = the position reached `lead` ms before the arrival of the trade before us
                    k0 = bisect.bisect_left([(r[0], r[1]) for r in tv.rows], (land[0], land[1]))
                    b = sim(None, k0)
                    if lead is not None and lead > 0 and k0 > 0: w_ = sim(None, min(k0, tv.k_at(tv.arr[k0 - 1] - int(lead * 1e6))))
                    else: w_ = b
                else:
                    Lm = land_ms if L == "live" else L
                    b = sim(te + int(Lm * 1e6))
                    w_ = sim(te - int(lead * 1e6) + int(Lm * 1e6)) if (lead is not None and lead > 0) else b
                mrows[str(L)] = [b, w_]
            row["model"] = mrows
        rows.append(row)
    n = len(rows); nconn = sum(r["connected"] for r in rows); npre = sum(r["has_pre"] for r in rows)
    leads = [r["lead_ms"] for r in rows if r["lead_ms"] is not None]
    P("### A. Speed: seeing the dump / trigger earlier via preconf\n")
    P(f"**Regular fires** ({lab}): {n} fires in the window, {nconn} while preconf was connected, {npre} with a preconf copy of the dump "
      f"({fmtp(npre / nconn if nconn else None)} of connected); lead (engine first rx − preconf rx): {fmt_dist(dist(leads))}. "
      f"Live: {sum(1 for r in rows if r['result'] == 'sold')} sold, {sum(1 for r in rows if r['result'] and r['result'] != 'sold')} not filled, "
      f"curve P&L {sum(r['curve_pnl_sol'] or 0 for r in rows):+.4f} SOL (before tips/fees; MEASURED).\n")
    summ = {}
    if any(r.get("model") for r in rows):
        P("MODELLED (simple shift replay, NOT the donor sim): our buy lands after every trade that arrived (recorder bin clock) before the "
          "landing time; fill only if tokens ≥ min_out; exit on the recorded curve at the end of entry slot + hold_slots; fee 1.25%; tips/base fees "
          "excluded; with preconf the same landing latency starts `lead` ms earlier (fires without a preconf copy unchanged). Rows = landing latency "
          "after the engine saw the dump; 'live' = each fire's REAL chain position when it landed (close.land), else its measured landing time "
          "(timing.buy_first_rx − dump first rx); with preconf it moves to the position reached `lead` ms earlier.\n")
        P("| landing row | fires modelled | fills base | fills w/ preconf | P&L base SOL | P&L w/ preconf SOL | Δ SOL |"); P("|---|---|---|---|---|---|---|")
        for L in [str(x) for x in LAT_ROWS] + ["live"]:
            fb = fw = m = 0; pb = pw = 0.0
            for r in rows:
                mm = (r.get("model") or {}).get(L)
                if not mm or mm[0] is None or mm[1] is None: continue
                m += 1
                if mm[0][0] == "fill": fb += 1; pb += mm[0][1]
                if mm[1][0] == "fill": fw += 1; pw += mm[1][1]
            if m:
                P(f"| {L}{' ms' if L != 'live' else ''} | {m} | {fb} | {fw} | {pb:+.4f} | {pw:+.4f} | {pw - pb:+.4f} |")
                summ[L] = dict(n=m, fills_base=fb, fills_pre=fw, pnl_base=round(pb, 5), pnl_pre=round(pw, 5), delta=round(pw - pb, 5))
        cal = [(r["curve_pnl_sol"], r["model"]["live"][0][1]) for r in rows if r.get("model") and r["result"] == "sold" and "live" in r["model"]
               and r["model"]["live"][0] and r["model"]["live"][0][0] == "fill" and r["curve_pnl_sol"] is not None]
        if cal: P(f"\nCalibration ('live' row vs the real curve P&L of {len(cal)} sold fires): real {sum(x for x, _ in cal):+.4f} SOL, model {sum(y for _, y in cal):+.4f} SOL.\n")
    # pre-send arms
    fills_by = collections.defaultdict(list)
    for f in E["fills"]: fills_by[(f.get("mint"), f.get("w"))].append(f)
    real_by = collections.defaultdict(list)
    for r in E["realized"]: real_by[(r.get("mint"), r.get("w"))].append(r)
    arows = []; arms_in = []
    for o in E["arms"]:
        tr = o.get("trig") or {}; sig = tr.get("sig"); te_raw = fr.get(sig) or tr.get("t"); te = clk(te_raw); tp = rx_pre(sig)
        if te is None or not (t_lo <= te <= t_hi): continue
        key = (tr.get("mint"), o.get("w")); att = sorted(E["attempts"].get(key, []), key=lambda x: x.get("t", 0))
        rz = real_by.get(key, []); lead = (te - tp) / 1e6 if (te and tp) else None
        arows.append(dict(kind="presend_arm", t_pkt=pkt(te), mint=tr.get("mint"), w=o.get("w"), trig_sig=sig, connected=in_wins(te, pre.win),
                          has_pre=tp is not None, lead_ms=round(lead, 3) if lead is not None else None,
                          first_try_ms_after_trigger=round((att[0]["t"] - te_raw) / 1e6, 2) if att else None, tries=len(att),
                          filled=bool(fills_by.get(key)), realized_pnl_sol=sum(x.get("pnl") or 0 for x in rz) / 1e9 if rz else None))
        arms_in.append(o)
    na = len(arows); nac = sum(r["connected"] for r in arows); nap = sum(r["has_pre"] for r in arows)
    la = [r["lead_ms"] for r in arows if r["lead_ms"] is not None]
    P(f"**Pre-send arms** ({lab}): {na} live arms, {nac} while preconf connected, {nap} with a preconf copy of the trigger ({fmtp(nap / nac if nac else None)}); "
      f"lead {fmt_dist(dist(la))}; {sum(r['filled'] for r in arows)} windows filled; realized P&L {sum(r['realized_pnl_sol'] or 0 for r in arows):+.4f} SOL (MEASURED). "
      f"First try left {fmt_dist(dist([r['first_try_ms_after_trigger'] for r in arows if r['first_try_ms_after_trigger'] is not None]), 'ms after the engine saw the trigger', False)}.\n")
    # MODELLED pre-send shift replay
    ps = {}
    for o, r in zip(arms_in, arows):
        tr = o.get("trig") or {}; mint = tr.get("mint"); rws = tapes.get(mint)
        if not rws or not o.get("lim0"): continue
        tv = TapeView(rws, our, rx_of, clock)
        if not tv.rows: continue
        att = sorted(E["attempts"].get((mint, o.get("w")), []), key=lambda x: x.get("t", 0))
        tries = [(clk(x["t"]), x.get("lim") or o["lim0"]) for x in att if isinstance(x.get("t"), int)]
        if not tries: continue
        lead = r["lead_ms"] if (r["lead_ms"] or 0) > 0 else 0.0
        mr = {}
        for L in LAT_ROWS:
            b = ps_sim_tries(tv, tries, L, 0.0, o.get("spend") or 500_000_000, o.get("en_slot") or 1 << 62)
            w_ = ps_sim_tries(tv, tries, L, lead, o.get("spend") or 500_000_000, o.get("en_slot") or 1 << 62) if lead else b
            mr[str(L)] = [b, w_]
        r["model"] = mr
    if any(r.get("model") for r in arows):
        P("Pre-send MODELLED (simple shift replay, NOT the donor sim): every REAL try of the window (presend_attempt send time, its own limit) lands L ms "
          "after it was sent, after every trade that arrived by then; with preconf all tries go out `lead` ms earlier (same count). The first try that lands at a "
          "curve price ≤ its limit (slot ≤ en_slot) fills with the arm's spend; exit TP +10% / SL −20% on later trades, else end of entry slot + 2; fee 1.25%; "
          "tips/fees excluded; one fill per window.\n")
        P("| landing row | arms modelled | fills base | fills w/ preconf | P&L base SOL | P&L w/ preconf SOL | Δ SOL |"); P("|---|---|---|---|---|---|---|")
        for L in [str(x) for x in LAT_ROWS]:
            fb = fw = m = 0; pb = pw = 0.0
            for r in arows:
                mm = (r.get("model") or {}).get(L)
                if not mm: continue
                m += 1
                if mm[0]: fb += 1; pb += mm[0][1] / 1e9
                if mm[1]: fw += 1; pw += mm[1][1] / 1e9
            if m:
                P(f"| {L} ms | {m} | {fb} | {fw} | {pb:+.4f} | {pw:+.4f} | {pw - pb:+.4f} |")
                ps[L] = dict(n=m, fills_base=fb, fills_pre=fw, pnl_base=round(pb, 5), pnl_pre=round(pw, 5), delta=round(pw - pb, 5))
        P(f"\nCalibration: real fills {sum(r['filled'] for r in arows if r.get('model'))} of {sum(1 for r in arows if r.get('model'))} modelled arms, real realized "
          f"{sum(r['realized_pnl_sol'] or 0 for r in arows if r.get('model')):+.4f} SOL (MEASURED; includes tips/fees and the real try pacing).\n")
    else: P("Pre-send SOL effect not modelled (no chain tapes for the armed mints).\n")
    # B rules
    P(f"### B. Management rules\n\nVisibility = preconf receive time on the recorder clock vs engine decision times ({lab}); outcomes from the engine log "
      f"(MEASURED) and the chain tape (MODELLED where stated).\n")
    def pre_trades(mint, a_, b_):
        out = []
        for r in tapes.get(mint, []):
            tp = rx_pre(r[2])
            if tp is not None and a_ < tp <= b_: out.append((tp, r[2], r[3], r[4], r[0], r[1]))
        return sorted(out)
    b1 = []
    for c in E["pcloses"]:
        mint = c.get("mint"); bl = c.get("land") or []; sl = c.get("sell_land") or []
        ex = [x for x in E["exits"] if x.get("mint") == mint and x.get("w") == c.get("w")]
        if len(bl) < 3 or not sl or not ex: continue
        t_exit = clk(ex[0]["t"])
        if not (t_lo <= t_exit <= t_hi): continue
        sin = c.get("sol_in_curve") or 0; sout = c.get("sol_out_curve") or 0
        if not sin or abs(sout - sin) / sin >= 0.02: continue
        vis = [x for x in pre_trades(mint, clk(bl[2]), t_exit) if x[2] and (x[4], x[5]) > (bl[0], bl[1])]
        row = dict(mint=mint, w=c.get("w"), applies=bool(vis), buyers=len(vis), real_pnl=(sout - sin) / 1e9, model_pnl=None)
        if vis:
            after = [x for x in vis if (x[4], x[5]) > (sl[0], sl[1])]
            row["buyers_after_our_sell"] = len(after)
            if not after: row["model_pnl"] = row["real_pnl"]          # they landed before our sell anyway: no change
            else:
                last = max(after, key=lambda x: (x[4], x[5])); rr = [r for r in tapes.get(mint, []) if r[2] == last[1]]
                if rr: row["model_pnl"] = (exit_curve(rr[0][6], rr[0][7], sin, c.get("tokens") or 0) - sin) / 1e9
        b1.append(row)
    ap1 = [x for x in b1 if x["applies"] and x["model_pnl"] is not None]
    d1 = sum(x["model_pnl"] - x["real_pnl"] for x in ap1)
    P(f"**B1** hold a flat pre-send position (|curve P&L| < 2%) when a buyer is visible in preconf before our exit: {len(b1)} flat positions, rule applies to "
      f"{len(ap1)}; real {sum(x['real_pnl'] for x in ap1):+.4f} SOL (MEASURED) → sell right after that buyer on its post-trade curve "
      f"{sum(x['model_pnl'] for x in ap1):+.4f} SOL (MODELLED); Δ {d1:+.4f} SOL.\n")
    b2 = []
    for c in E["pcloses"]:
        mint = c.get("mint"); bl = c.get("land") or []
        if len(bl) < 3: continue
        tb = clk(bl[2])
        if not (t_lo <= tb <= t_hi): continue
        arm = [o for o in E["arms"] if (o.get("trig") or {}).get("mint") == mint and o.get("w") == c.get("w")]
        t_arm = clk((arm[0].get("trig") or {}).get("t")) if arm else tb - 3 * NS
        dumps = [x for x in pre_trades(mint, t_arm, tb) if not x[2] and x[3] >= DUMP_MIN]
        rz = real_by.get((mint, c.get("w")), [])
        real = sum(x.get("pnl") or 0 for x in rz) / 1e9 if rz else ((c.get("sol_out_curve") or 0) - (c.get("sol_in_curve") or 0)) / 1e9
        row = dict(mint=mint, w=c.get("w"), dumps_visible_before_fill=len(dumps), applies=len(dumps) >= 2, real_pnl=real, exit_early=None)
        # exit-early variant: after our fill, a dump >= 0.3 SOL visible in preconf before our exit decision -> sell right after it
        ex = [x for x in E["exits"] if x.get("mint") == mint and x.get("w") == c.get("w")]
        sl = c.get("sell_land") or []
        if ex and sl and c.get("tokens"):
            nd = [x for x in pre_trades(mint, tb, clk(ex[0]["t"])) if not x[2] and x[3] >= DUMP_MIN and (x[4], x[5]) > (bl[0], bl[1]) and (x[4], x[5]) < (sl[0], sl[1])]
            if nd:
                first = min(nd, key=lambda x: (x[4], x[5])); rr = [r for r in tapes.get(mint, []) if r[2] == first[1]]
                sin = c.get("sol_in_curve") or 0
                if rr: row["exit_early"] = dict(real_curve=((c.get("sol_out_curve") or 0) - sin) / 1e9,
                                                model_curve=(exit_curve(rr[0][6], rr[0][7], sin, c["tokens"]) - sin) / 1e9)
        b2.append(row)
    ap2 = [x for x in b2 if x["applies"]]
    ee = [x["exit_early"] for x in b2 if x.get("exit_early")]
    P(f"**B2** stop pre-send tries when a second dump (sell ≥ 0.3 SOL) is visible in preconf before our fill landed: {len(b2)} fills, rule skips {len(ap2)}; "
      f"their realized P&L {sum(x['real_pnl'] for x in ap2):+.4f} SOL (MEASURED) → Δ {-sum(x['real_pnl'] for x in ap2):+.4f} SOL "
      f"(INFERRED: no other fill replaces a skipped one). Exit-early variant (a dump ≥ 0.3 SOL visible in preconf after our fill and before our exit "
      f"decision, landing before our sell → sell right after it, MODELLED on its post-trade curve): applies {len(ee)}, real curve P&L "
      f"{sum(x['real_curve'] for x in ee):+.4f} → {sum(x['model_curve'] for x in ee):+.4f} SOL (Δ {sum(x['model_curve'] - x['real_curve'] for x in ee):+.4f}).\n")
    b3 = []
    for r in rows:
        f = next((x for x in E["fires"] if x.get("buy_sig") == r["buy_sig"]), None)
        if not f: continue
        tfire = clk(f.get("t_fire") or 0); mint = f.get("mint"); ds = f.get("dump_sig")
        dpos = next(((x[0], x[1]) for x in tapes.get(mint, []) if x[2] == ds), None)
        sec = [x for x in pre_trades(mint, tfire - 2 * NS, tfire + 2_000_000) if not x[2] and x[3] >= DUMP_MIN and x[1] != ds and (dpos is None or (x[4], x[5]) > dpos)]
        b3.append(dict(buy_sig=r["buy_sig"], mint=mint, second_dump_visible=bool(sec), result=r["result"], real_pnl=r["curve_pnl_sol"]))
    ap3 = [x for x in b3 if x["second_dump_visible"]]
    P(f"**B3** skip a regular buy when a second dump is lined up right behind the first (visible in preconf by fire time + 2 ms): {len(b3)} fires, rule skips "
      f"{len(ap3)}; their curve P&L {sum(x['real_pnl'] or 0 for x in ap3):+.4f} SOL (MEASURED, before tips) → Δ {-sum(x['real_pnl'] or 0 for x in ap3):+.4f} SOL.\n")
    P("Per-event lists: whatif_events.json, engine_events.csv.\n")
    W.update(A_fires=rows, A_fires_model=summ, A_arms=arows, B1=b1, B2=b2, B3=b3)
    R["whatif"] = {"label": lab, "A_fires": {"n": n, "connected": nconn, "with_pre": npre, "lead": dist(leads), "model": summ},
                   "A_arms": {"n": na, "connected": nac, "with_pre": nap, "lead": dist(la), "model": ps},
                   "B1": {"n_flat": len(b1), "applies": len(ap1), "delta_sol": round(d1, 5)},
                   "B2": {"n": len(b2), "applies": len(ap2), "delta_sol": round(-sum(x['real_pnl'] for x in ap2), 5),
                          "exit_early_applies": len(ee), "exit_early_delta_sol": round(sum(x['model_curve'] - x['real_curve'] for x in ee), 5)},
                   "B3": {"n": len(b3), "applies": len(ap3), "delta_sol": round(-sum(x['real_pnl'] or 0 for x in ap3), 5)}}
    with open(os.path.join(OUT, "engine_events.csv"), "w") as fh:
        ks = ["kind", "t_pkt", "mint", "connected", "has_pre", "lead_ms", "result", "curve_pnl_sol", "realized_pnl_sol", "land_ms_after_dump",
              "first_try_ms_after_trigger", "tries", "filled", "client", "dump_sig", "buy_sig", "trig_sig", "w"]
        fh.write(",".join(ks) + "\n")
        for r in rows + arows: fh.write(",".join("" if r.get(k) is None else str(r.get(k)) for k in ks) + "\n")
    with open(os.path.join(OUT, "whatif_events.json"), "w") as fh: json.dump(W, fh, indent=1, default=str)

def short(R, OUT):
    print(f"PRECONF ANALYSIS {R['window']['from_pkt']} → {R['window']['to_pkt'][11:]} PKT ({R['window']['minutes']} min) [{R['runtime_s']} s, {R.get('peak_rss_mb')} MB]")
    for mach, rc in R.get("coverage", {}).items():
        p = rc.get("pre") or {}; b = rc.get("bin") or {}
        print(f" {mach}: preconf has {fmtp(p.get('tx_share'))} of landed pump txs ({fmtp(p.get('slot_share'))} of slots; {p.get('leaders_connected')} of "
              f"{p.get('leaders_seen')} leaders ≥50%; {fmtp(p.get('tx_share_within_covered_slots'))} inside covered slots); bin {fmtp(b.get('tx_share'))}")
        lm = R.get("lead", {}).get(mach) or {}
        l = lm.get("pre_vs_bin_chain_pump", {}).get("all", {}); src = "chain-truth pump txs"
        if not l.get("n"): l = lm.get("pre_vs_bin_view_all") or {}; src = "all pump-view txs"
        if l.get("n"): print(f"   lead pre vs bin P10/P50/P90 {l['p10']:.1f}/{l['p50']:.1f}/{l['p90']:.1f} ms (n={l['n']} {src}, pre earlier {100 * l['share_pre_earlier']:.0f}%)")
        ac = R.get("accuracy", {}).get(mach)
        if ac: print(f"   accuracy: landed {fmtp(ac.get('land_share'))} (failed {fmtp(ac.get('failed_share'))}), never landed {fmtp(ac.get('never_landed_share'))}, "
                     f"same slot {fmtp(ac.get('same_slot_share'))}" + (f", in-slot order agreement {fmtp(ac['order'].get('pair_agreement'))}" if ac.get("order") else ""))
    pe = R.get("lead", {}).get("pre_vs_engine")
    if pe:
        for k, d in pe["by_type"].items():
            if d.get("n"): print(f"   pre vs engine [{k}] P50 {d['p50']:.1f} ms (n={d['n']} of {d['events']} events)" + ("" if pe["engine_host"] == pe["recorder"] else f" INFERRED ±{pe['unc_ms']:.2f} ms" if pe['unc_ms'] is not None else " INFERRED (offset unknown)"))
    w = R.get("whatif")
    if w:
        m = w["A_fires"].get("model") or {}
        print(f" what-if A: fires {w['A_fires']['n']} (preconf copy {w['A_fires']['with_pre']}), arms {w['A_arms']['n']} (preconf copy {w['A_arms']['with_pre']})"
              + ("; modelled Δ SOL per landing row " + ", ".join(f"{k}:{v['delta']:+.3f}" for k, v in m.items()) if m else ""))
        pm = w["A_arms"].get("model") or {}
        if pm: print(" what-if A pre-send: modelled Δ SOL per landing row " + ", ".join(f"{k}:{v['delta']:+.3f}" for k, v in pm.items()))
        print(f" what-if B: B1 {w['B1']['applies']} → {w['B1']['delta_sol']:+.4f}, B2 {w['B2']['applies']} → {w['B2']['delta_sol']:+.4f}, B3 {w['B3']['applies']} → {w['B3']['delta_sol']:+.4f} SOL")
    if R.get("skipped"): print(" skipped:", "; ".join(R["skipped"]))
    print(f" report: {os.path.join(OUT, 'report.md')}")

if __name__ == "__main__":
    main()
