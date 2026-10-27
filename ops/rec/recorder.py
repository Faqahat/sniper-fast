#!/usr/bin/env python3
# sniper-rec RECORDER (host). READ-ONLY raw pump.fun recorder: no wallet, no sends, no filtering, no analysis.
# Continuous (one process, every slot in order), written as ONE DIRECTORY PER PKT DAY (00:00 PKT = 19:00 UTC):
#   $REC_ROOT/days/YYYY-MM-DD/ run.json status.json launches.jsonl enrich.jsonl gaps.jsonl slots.tsv txs/txs_<unix>.jsonl.gz
# Same record format as ops/collect/collect.py (the FRA collector): every pump.fun create, and every later tx touching one
# of those mints (curve trades, aggregator routes, transfers, burns, migration, PumpSwap) for REC_FOLLOW_H hours after
# its create. Day rotation is by BLOCK time, decided in slot order: the first block whose blockTime >= next 00:00 PKT
# opens the next day, so adjacent days' slot ranges touch with no gap and no overlap (slots.tsv has one line per slot).
# Endpoints come from env (URLs never printed). Modes (REC_MODE):
#   overlap : side by side with FRA's collector -> SHYFT only, hard cap REC_EP_TOTAL_RPS req/s per endpoint across all
#             methods, no Constant-K (refuses to build its URL), enrichment = metadata + Jito only, final pass deferred,
#             and it STOPS (HOLD file + clean exit) on the first 429 / usage / credit / quota error.
#   normal  : exactly like FRA today: blocks from SHYFT_RPC_URL,RMR_RPC_URL,CK at 6/s each, getSlot + enrichment +
#             final pass on CK at 20/s.
# Every knob is an env var (REC_*), see cfg() below. Crash-safe: chunks are sync-flushed + fsynced every REC_SYNC_S
# seconds before slots.tsv is written, and a restart repairs the last chunk and resumes at the slot after the last
# slots.tsv line. A HOLD file in $REC_ROOT stops it from starting (exit 0, so systemd does not restart it).
import os, sys, json, time, gzip, zlib, base64, hashlib, threading, queue, urllib.request, urllib.error, urllib.parse
import collections, traceback, signal, re, calendar, glob, shutil, faulthandler
from concurrent.futures import ThreadPoolExecutor

PKT = 5 * 3600
def pkt_day(ts): return time.strftime("%Y-%m-%d", time.gmtime(ts + PKT))
def day_start(day):
    y, m, d = map(int, day.split("-")); return calendar.timegm((y, m, d, 0, 0, 0)) - PKT
def next_day(day): return pkt_day(day_start(day) + 86400 + 3600)
def pkt_str(ts): return time.strftime("%Y-%m-%d %H:%M:%S PKT", time.gmtime(ts + PKT))

# ---------------- config ----------------
MODE = os.environ.get("REC_MODE", "normal")
assert MODE in ("normal", "overlap"), MODE
DEF = dict(
    normal=dict(REC_BLOCK_EPS="SHYFT_RPC_URL,RMR_RPC_URL,CK", REC_RPC_EP="CK", REC_BLOCK_RPS="6", REC_RPC_RPS="20",
                REC_EP_TOTAL_RPS="0", REC_ENRICH_RPC="1", REC_FINAL_PASS="run", REC_TRIP_ON_LIMIT="0", REC_SLOT_EVERY="0.4",
                REC_FETCH_THREADS="10", REC_FORBID_CK="0"),
    overlap=dict(REC_BLOCK_EPS="SHYFT_RPC_URL", REC_RPC_EP="SHYFT_RPC_URL", REC_BLOCK_RPS="5.8", REC_RPC_RPS="5.8",
                 REC_EP_TOTAL_RPS="5.8", REC_ENRICH_RPC="0", REC_FINAL_PASS="defer", REC_TRIP_ON_LIMIT="1",
                 REC_SLOT_EVERY="4", REC_FETCH_THREADS="6", REC_FORBID_CK="1"))[MODE]
def cfg(k, d=None): return os.environ.get(k) or DEF.get(k) or d
ROOT = cfg("REC_ROOT", "/home/moiz/sniper-data/rec")
DAYS = os.path.join(ROOT, "days"); STATE = os.path.join(ROOT, "state"); REPAIR = os.path.join(ROOT, "repair")
LAG = int(cfg("REC_LAG", "32")); AHEAD = int(cfg("REC_AHEAD", "40")); FETCH_THREADS = int(cfg("REC_FETCH_THREADS"))
FOLLOW_S = float(cfg("REC_FOLLOW_H", "24.333")) * 3600
SYNC_S = float(cfg("REC_SYNC_S", "10")); CHUNK_S = float(cfg("REC_CHUNK_S", "300"))
SLOT_EVERY = float(cfg("REC_SLOT_EVERY")); ENRICH_RPC = cfg("REC_ENRICH_RPC") == "1"; FINAL_PASS = cfg("REC_FINAL_PASS")
TRIP = cfg("REC_TRIP_ON_LIMIT") == "1"; FORBID_CK = cfg("REC_FORBID_CK") == "1"
ENRICH_WORKERS = int(cfg("REC_ENRICH_WORKERS", "4")); ENRICH_ON = cfg("REC_ENRICH", "on") == "on"   # off: tests only
STOP_AT = float(cfg("REC_STOP_AT", "0"))   # epoch; 0 = never
NO_NET = cfg("REC_TEST_NO_NET", "0") == "1"   # tests only: no metadata / Jito HTTP calls
STOP_SLOT = int(cfg("REC_STOP_SLOT", "0"))  # stop cleanly (HOLD) after this slot: rollback / backfill up to a known slot
START_SLOT = int(cfg("REC_START_SLOT", "0"))  # FRESH start only: first slot (cut-over: FRA's last slot - margin; caught up from RPC history)
SEED = cfg("REC_SEED_LAUNCHES", "")         # FRESH start only: launches.jsonl files whose mints are followed too (FRA's current run)
TIPMAP = json.load(open(cfg("REC_TIPMAP", os.path.join(os.path.dirname(os.path.abspath(__file__)), "tipmap.json"))))
HOLD = os.path.join(ROOT, "HOLD")
SAMPLE = int(cfg("REC_SAMPLE_EVERY", "1"))          # overlap test only: fetch only slots with slot % SAMPLE == 0
SAVE_RAW = cfg("REC_SAVE_RAW", "")                  # overlap test only: dir for the raw getBlock results (replay tests)
for d in (DAYS, STATE, REPAIR, os.path.join(ROOT, "logs")): os.makedirs(d, exist_ok=True)

PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"; PUMPAMM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
VOTE = "Vote111111111111111111111111111111111111111"; CB = "ComputeBudget111111111111111111111111111111"
CREATE_DISC = hashlib.sha256(b"event:CreateEvent").digest()[:8]
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; B58I = {c: i for i, c in enumerate(B58)}
def b58enc(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
def b58dec(s):
    n = 0
    for c in s: n = n * 58 + B58I[c]
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b

LOGF = open(os.path.join(ROOT, "logs", "recorder.log"), "a", buffering=1)
STACKF = open(os.path.join(ROOT, "logs", "stacks.txt"), "a")
faulthandler.register(signal.SIGUSR1, file=STACKF, all_threads=True)      # kill -USR1 <pid>: dump every thread's stack
def log(*a):
    LOGF.write(time.strftime("%Y-%m-%dT%H:%M:%SZ ", time.gmtime()) + " ".join(str(x) for x in a) + "\n")

# ---------------- endpoints: per-endpoint pacing on ACTUAL call starts; URLs never printed ----------------
class Stopped(Exception): pass
STOP = threading.Event(); STOP_WHY = [None]; EXIT_CODE = [0]
ST = collections.Counter()
class Pace:
    def __init__(self, rps): self.dt = 1.0 / rps if rps > 0 else 0.0; self.lk = threading.Lock(); self.last = 0.0
    def wait(self):
        if not self.dt: return
        while True:
            if STOP.is_set(): raise Stopped()
            with self.lk:
                now = time.time()
                if now >= self.last + self.dt: self.last = now; return
                d = self.last + self.dt - now
            time.sleep(d)
class EP:
    def __init__(self, name):
        self.name = name; self.label = name.replace("_RPC_URL", "")
        if name == "CK":
            if FORBID_CK: raise SystemExit("REFUSED: Constant-K is forbidden in this mode (REC_FORBID_CK=1)")
            self.url = "https://rpc-frankfurt.constant-k.com/?api-key=" + os.environ["CONSTANTK_TOKEN"]
        else:
            self.url = os.environ.get(name) or ""
            if not self.url: raise SystemExit(f"endpoint env {name} is not set")
            if "constant-k" in self.url and FORBID_CK: raise SystemExit(f"REFUSED: {name} points at Constant-K")
        # heavy = the final pass (getTokenLargestAccounts / getMultipleAccounts): Constant-K's "veryheavy" class is
        # limited to 2/s; FRA's collector runs its final pass at 20/s and gets ~1/3 of those calls 429-ed for hours
        # (measured 10-27: ~50 429s/min, never completes). The host paces it at REC_HEAVY_RPS (default 1.8/s).
        self.pace = dict(block=Pace(float(cfg("REC_BLOCK_RPS"))), rpc=Pace(float(cfg("REC_RPC_RPS"))),
                         heavy=Pace(min(float(cfg("REC_HEAVY_RPS", "1.8")), float(cfg("REC_RPC_RPS")))))
        self.total = Pace(float(cfg("REC_EP_TOTAL_RPS")))
EPS = {}
def ep(name):
    if name not in EPS: EPS[name] = EP(name)
    return EPS[name]
BEPS = [ep(n) for n in cfg("REC_BLOCK_EPS").split(",") if n]
REP = ep(cfg("REC_RPC_EP"))
# last-resort endpoints (e.g. CK after the cut-over, once the recorder has its own key): used only after the primaries fail
BFALL = [ep(n) for n in cfg("REC_BLOCK_FALLBACK", "").split(",") if n]
RFALL = [ep(n) for n in cfg("REC_RPC_FALLBACK", "").split(",") if n]
LIMIT_RE = re.compile(r"(too many|rate.?limit|max usage|usage|credit|quota|exceed|limit reached|throttl)", re.I)

def trip(e, why):
    ST[f"limit_{e.label}"] += 1
    if not TRIP: return
    if not STOP.is_set():
        STOP_WHY[0] = f"TRIP {e.label}: {why}"
        json.dump(dict(reason=STOP_WHY[0], by="recorder", t=time.time(), pkt=pkt_str(time.time())), open(HOLD, "w"))
        log("TRIPPED:", STOP_WHY[0], "-> HOLD written, stopping")
        STOP.set()

def call(e, kind, method, params, timeout=60):
    """one JSON-RPC call through endpoint e's pacers. Returns the parsed JSON (may contain 'error'). Raises on HTTP/IO."""
    e.pace[kind].wait(); e.total.wait()
    if STOP.is_set(): raise Stopped()
    ST[f"{e.label}.{method}"] += 1
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    try:
        r = urllib.request.urlopen(urllib.request.Request(e.url, data=data, headers={"content-type": "application/json"}), timeout=timeout)
        j = json.loads(r.read())
    except urllib.error.HTTPError as x:
        body = ""
        try: body = x.read(300).decode("utf-8", "replace")
        except Exception: pass
        ST[f"{e.label}.http{x.code}"] += 1
        if x.code in (429, 402) or (x.code in (403, 503) and LIMIT_RE.search(body or "")): trip(e, f"HTTP {x.code} {body[:80]!r} on {method}")
        raise
    if isinstance(j, dict) and "error" in j:
        msg = str((j.get("error") or {}).get("message", ""))
        code = (j.get("error") or {}).get("code")
        if code in (-32005, -32429, 429) or (LIMIT_RE.search(msg) and code not in (-32007, -32009, -32004, -32001)):
            trip(e, f"rpc error {code} {msg[:80]!r} on {method}")
    return j

def rpc(m, p, tries=10, timeout=90, kind="rpc"):
    """getSlot / enrichment / final pass calls (FRA: rpc() on Constant-K). With REC_RPC_FALLBACK, every retry after a
    failed attempt on the primary goes to the next fallback endpoint (the primary is always tried first)."""
    for i in range(tries):
        e = REP if (i == 0 or not RFALL) else (RFALL[(i - 1) % len(RFALL)] if i % 2 else REP)
        if e is not REP: ST["rpc_fallback"] += 1
        try:
            if kind == "heavy": e.pace["rpc"].wait()        # heavy calls also count against the endpoint's normal rpc pace
            r = call(e, kind, m, p, timeout)
        except Stopped: return None
        except urllib.error.HTTPError as x:
            ST["rpc_429" if x.code == 429 else "rpc_http"] += 1; time.sleep(min(30, 2 + 3 * i)); continue
        except Exception:
            ST["rpc_exc"] += 1; time.sleep(min(30, 1 + 2 * i)); continue
        if "error" in r:
            code = r["error"].get("code")
            if code in (-32007, -32009, -32004, -32001) and m == "getBlock": return {"_skip": code}
            ST["rpc_err"] += 1; time.sleep(min(30, 1 + 2 * i)); continue
        return r.get("result")
    return None

def get_block(slot):
    """FRA's logic (ask every endpoint, twice, before calling a slot skipped) + 'not available yet' (-32004) is retried
    for up to ~20 s instead of counting as a skip (with one endpoint a lagging node would otherwise drop the slot)."""
    params = [slot, {"encoding": "json", "maxSupportedTransactionVersion": 1, "transactionDetails": "full", "rewards": False, "commitment": "confirmed"}]
    n = len(BEPS); skips = []; na = 0; k = 0
    while k < 4 * n:
        e = BEPS[(slot + k) % n]; k += 1
        try: r = call(e, "block", "getBlock", params, 60)
        except Stopped: return None
        except urllib.error.HTTPError as ex:
            ST[f"blk_http{ex.code}_{e.label}"] += 1; time.sleep(0.5 * ((k - 1) // n + 1)); continue
        except Exception:
            ST[f"blk_exc_{e.label}"] += 1; time.sleep(0.5 * ((k - 1) // n + 1)); continue
        if "error" in r:
            code = r["error"].get("code")
            if code == -32004 and na < 8:
                na += 1; k -= 1; ST["blk_notavail_retry"] += 1; time.sleep(2.5); continue
            if code in (-32007, -32009, -32004, -32001):
                ST[f"blk_skipcode{code}_{e.label}"] += 1; skips.append((e.label, code))
                if len(skips) >= 2 * n:
                    return {"_skip": code, "_codes": skips}
                if len(skips) == n: time.sleep(1.5)
                continue
            ST[f"blk_err_{e.label}"] += 1; time.sleep(0.5 * ((k - 1) // n + 1)); continue
        if skips: ST["blk_skip_recovered"] += 1
        return r.get("result")
    for e in BFALL:                                     # every primary failed (errors, not agreed skips): last resort
        for _ in range(2):
            try: r = call(e, "block", "getBlock", params, 60)
            except Stopped: return None
            except Exception: ST[f"blk_fallback_err_{e.label}"] += 1; time.sleep(0.5); continue
            if "error" in r:
                code = r["error"].get("code")
                if code in (-32007, -32009, -32001) and skips: return {"_skip": code, "_codes": skips + [(e.label, code)]}
                ST[f"blk_fallback_err_{e.label}"] += 1; time.sleep(0.5); continue
            ST[f"blk_fallback_used_{e.label}"] += 1
            return r.get("result")
    return None

# ---------------- per-day output ----------------
_wl = threading.Lock()
def ddir(day): return os.path.join(DAYS, day)
def jlog(day, name, obj):
    with _wl:
        with open(os.path.join(ddir(day), name), "a") as f: f.write(json.dumps(obj, separators=(",", ":")) + "\n")
def jdump(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f: json.dump(obj, f)
    os.replace(tmp, path)

class Day:
    """the day currently being written: chunk files + slots.tsv (written only after the chunk is synced)"""
    def __init__(self, day, start_slot, start_time, fresh):
        self.day = day; self.dir = ddir(day); os.makedirs(os.path.join(self.dir, "txs"), exist_ok=True)
        rp = os.path.join(self.dir, "run.json")
        if os.path.exists(rp) and not fresh: self.run = json.load(open(rp))
        else:
            self.run = dict(start_slot=start_slot, start_time=start_time, window_end_time=day_start(next_day(day)),
                            tail_end_time=day_start(next_day(day)), end_slot=None, day=day, tz="PKT (UTC+5)",
                            layout="sniper-rec day v1", recorder_started=time.time())
        self.run.update(mode=MODE, follow_h=FOLLOW_S / 3600, block_eps=[e.label for e in BEPS], rpc_ep=REP.label,
                        enrich_rpc=ENRICH_RPC, final_pass=FINAL_PASS)
        if SAMPLE > 1: self.run["sample_every"] = SAMPLE
        jdump(rp, self.run)
        self.gz = None; self.raw = None; self.t_open = 0; self.n = 0; self.pend = []; self.synced_lines = 0
        self.slots = open(os.path.join(self.dir, "slots.tsv"), "a")
    def is_blank(self):
        return self.n == 0 and self.synced_lines == 0 and os.path.getsize(os.path.join(self.dir, "slots.tsv")) == 0 and \
            not os.listdir(os.path.join(self.dir, "txs")) and not os.path.exists(os.path.join(self.dir, "launches.jsonl"))
    def abandon(self):
        """a fresh day dir that got nothing (the first block belongs to another PKT day): remove our own empty files"""
        self.slots.close(); gl = os.path.join(self.dir, "gaps.jsonl")
        gaps = open(gl).read() if os.path.exists(gl) else ""
        for f in ("run.json", "status.json", "slots.tsv", "gaps.jsonl"):
            try: os.remove(os.path.join(self.dir, f))
            except FileNotFoundError: pass
        try: os.rmdir(os.path.join(self.dir, "txs")); os.rmdir(self.dir)
        except OSError: pass
        return gaps
    def write(self, rec):
        now = time.time()
        if self.gz is None or now - self.t_open > CHUNK_S: self.open_chunk(now)
        self.gz.write((json.dumps(rec, separators=(",", ":")) + "\n").encode()); self.n += 1; self.dirty = True
    def open_chunk(self, now):
        self.close_chunk()
        t = int(now)
        while os.path.exists(os.path.join(self.dir, "txs", f"txs_{t}.jsonl.gz")): t += 1
        p = os.path.join(self.dir, "txs", f"txs_{t}.jsonl.gz")
        self.raw = open(p, "wb"); self.gz = gzip.GzipFile(filename=os.path.basename(p)[:-3], mode="wb", compresslevel=3, fileobj=self.raw)
        self.t_open = now; self.chunk = os.path.basename(p)
    def close_chunk(self):
        if self.gz is not None:
            self.gz.close(); self.raw.flush(); os.fsync(self.raw.fileno()); self.raw.close(); self.gz = None; self.raw = None
    def slot_line(self, *f): self.pend.append("\t".join(str(x) for x in f) + "\n")
    def sync(self):
        if self.gz is not None and getattr(self, "dirty", False):
            self.gz.flush(zlib.Z_SYNC_FLUSH); self.raw.flush(); os.fsync(self.raw.fileno()); self.dirty = False
        if self.pend:
            self.slots.write("".join(self.pend)); self.synced_lines += len(self.pend); self.pend = []; self.slots.flush(); os.fsync(self.slots.fileno())
    def close(self):
        self.close_chunk(); self.sync(); self.slots.close()

class RawSaver:
    def __init__(self, d): self.d = d; os.makedirs(d, exist_ok=True); self.f = None; self.t = 0
    def put(self, slot, b):
        now = time.time()
        if self.f is None or now - self.t > 300:
            if self.f: self.f.close()
            self.f = gzip.open(os.path.join(self.d, f"raw_{int(now)}.jsonl.gz"), "wt", compresslevel=1); self.t = now
        self.f.write(json.dumps({"slot": slot, "block": b}, separators=(",", ":")) + "\n")
    def close(self):
        if self.f: self.f.close(); self.f = None
RAW = RawSaver(SAVE_RAW) if SAVE_RAW else None

# ---------------- block parsing (identical record format to collect.py) ----------------
TRACK = {}            # mint -> create slot
TBT = {}              # mint -> create block time (expiry)
LDAY = {}             # mint -> PKT day of its create
EARLY = {}            # mint -> earliest trade tx sigs in the create slot (for the Jito check)
LCACHE = {}
PENDING = collections.Counter()   # day -> launches still waiting for enrichment
_pl = threading.Lock()

def parse_create(raw):
    o = 8; s = []
    for _ in range(3):
        n = int.from_bytes(raw[o:o + 4], "little"); s.append(raw[o + 4:o + 4 + n].decode("utf-8", "replace")); o += 4 + n
    k = lambda j: b58enc(raw[o + 32 * j:o + 32 * (j + 1)]) if len(raw) >= o + 32 * (j + 1) else None
    return dict(name=s[0], symbol=s[1], uri=s[2], mint=k(0), bonding_curve=k(1), user=k(2), creator=k(3))

def process_block(D, slot, b, in_window=True):
    bt = b.get("blockTime"); txs = b.get("transactions") or []
    nrec = 0; ncre = 0
    for i, t in enumerate(txs):
        msg = t["transaction"]["message"]; meta = t.get("meta") or {}
        keys = msg["accountKeys"]
        if VOTE in keys: continue
        la = meta.get("loadedAddresses") or {}
        allk = keys + la.get("writable", []) + la.get("readonly", [])
        logs = meta.get("logMessages") or []
        evs = []; creates = []
        has_pump = PUMP in allk or PUMPAMM in allk
        if has_pump:
            for l in logs:
                if l.startswith("Program data: "):
                    s = l[14:].strip(); evs.append(s)
                    if in_window:
                        try: raw = base64.b64decode(s + "=" * (-len(s) % 4))
                        except Exception: continue
                        if raw[:8] == CREATE_DISC:
                            try: creates.append(parse_create(raw))
                            except Exception: pass
        sig = t["transaction"]["signatures"][0]
        for c in creates:
            if c["mint"] and c["mint"] not in TRACK:
                TRACK[c["mint"]] = slot; TBT[c["mint"]] = bt or time.time(); LDAY[c["mint"]] = D.day
                EARLY[c["mint"]] = []; LCACHE[c["mint"]] = c
                c.update(slot=slot, idx=i, bt=bt, sig=sig, payer=keys[0], err=meta.get("err"), fee=meta.get("fee"),
                         ixn=[l[26:] for l in logs if l.startswith("Program log: Instruction: ")][:12])
                ST["launches"] += 1; ncre += 1; jlog(D.day, "launches.jsonl", c)
                with _pl: PENDING[D.day] += 1
                EQ.put((time.time() + 25, c["mint"]))
        tb_m = {x.get("mint") for x in (meta.get("preTokenBalances") or []) + (meta.get("postTokenBalances") or [])}
        mints = [k for k in set(allk) | tb_m if k in TRACK]
        if not mints: continue
        nsig = msg["header"]["numRequiredSignatures"]
        pre, post = meta.get("preBalances") or [], meta.get("postBalances") or []
        sd = sorted(((allk[j], post[j] - pre[j]) for j in range(min(len(pre), len(post), len(allk))) if post[j] != pre[j]), key=lambda x: -abs(x[1]))
        tips = [[k, d] for k, d in sd if d > 0 and (k in TIPMAP or k.startswith("noz"))]
        cup = cul = None
        for ix in msg["instructions"]:
            if allk[ix["programIdIndex"]] == CB:
                try:
                    d = b58dec(ix["data"])
                    if d[:1] == b"\x03": cup = int.from_bytes(d[1:9], "little")
                    elif d[:1] == b"\x02": cul = int.from_bytes(d[1:5], "little")
                except Exception: pass
        progs = sorted({allk[ix["programIdIndex"]] for ix in msg["instructions"]} |
                       {allk[ix["programIdIndex"]] for inn in (meta.get("innerInstructions") or []) for ix in inn.get("instructions") or [] if ix["programIdIndex"] < len(allk)})
        tbal = {}
        for x in meta.get("preTokenBalances") or []:
            if x.get("mint") in TRACK: tbal[(x["accountIndex"])] = [x["mint"], x.get("owner"), int(x["uiTokenAmount"]["amount"]), 0]
        for x in meta.get("postTokenBalances") or []:
            if x.get("mint") in TRACK:
                r = tbal.setdefault(x["accountIndex"], [x["mint"], x.get("owner"), 0, 0]); r[3] = int(x["uiTokenAmount"]["amount"])
        rec = dict(s=slot, i=i, bt=bt, sig=sig, err=meta.get("err"), fee=meta.get("fee"), cu=meta.get("computeUnitsConsumed"), cup=cup, cul=cul,
                   signers=keys[:nsig], mints=mints, progs=progs, ixn=[l[26:] for l in logs if l.startswith("Program log: Instruction: ")][:16],
                   ev=evs[:12], tb=[v for v in tbal.values() if v[2] != v[3]], sd=sd[:14], tips=tips)
        D.write(rec); nrec += 1; ST["txs"] += 1
        if slot == TRACK.get(mints[0]) and len(EARLY.get(mints[0], [])) < 4 and not meta.get("err") and evs:
            EARLY[mints[0]].append([i, sig])
    return len(txs), nrec, ncre

# ---------------- enrichment (as collect.py; RPC part only when REC_ENRICH_RPC=1) ----------------
EQ = queue.PriorityQueue(); _jl = threading.Lock(); _jlast = [0.0]
def jito(path):
    if NO_NET: return None
    for i in range(5):
        if STOP.is_set(): return "ERR"
        with _jl:
            w = _jlast[0] + 0.15 - time.time()
            if w > 0: time.sleep(w)
            _jlast[0] = time.time()
        try:
            ST["jito_calls"] += 1
            return json.load(urllib.request.urlopen(urllib.request.Request("https://bundles.jito.wtf/api/v1/bundles/" + path, headers={"user-agent": "sniper-collect"}), timeout=20))
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            ST["jito_err"] += 1; time.sleep(2 * (i + 1))
        except Exception:
            ST["jito_err"] += 1; time.sleep(2 * (i + 1))
    return "ERR"

def bundle_of(sig):
    j = jito("transaction/" + sig)
    if not (isinstance(j, list) and j): return None if j != "ERR" else "ERR"
    bid = j[0].get("bundle_id"); d = jito("bundle/" + bid)
    d = d[0] if isinstance(d, list) and d else {}
    return dict(bundle_id=bid, txs=d.get("txSignatures"), tippers=d.get("tippers"), tip=d.get("landedTipLamports"), validator=d.get("validator"), ts=d.get("timestamp"))

def fetch_uri(u):
    out = dict(uri=u)
    if not u: return out
    if NO_NET: out["skipped"] = "test"; return out
    urls = [u]
    if "/ipfs/" in u:
        cid = u.split("/ipfs/", 1)[1]
        urls += [g + cid for g in ("https://gateway.pinata.cloud/ipfs/", "https://w3s.link/ipfs/", "https://4everland.io/ipfs/", "https://ipfs.io/ipfs/") if g + cid != u]
    for x in urls:
        if STOP.is_set(): break
        try:
            r = urllib.request.urlopen(urllib.request.Request(x, headers={"user-agent": "Mozilla/5.0"}), timeout=12)
            body = r.read(65536); out.update(status=r.status, ctype=r.headers.get("content-type"), host=urllib.parse.urlparse(x).hostname, fetched=x)
            try: out["json"] = json.loads(body)
            except Exception: out["text"] = body[:2000].decode("utf-8", "replace")
            return out
        except Exception as e:
            out["error"] = str(e)[:200]
    return out

def enrich_rpc(res, L):
    cre = L.get("creator") or L.get("user")
    sigs = rpc("getSignaturesForAddress", [cre, {"limit": 100, "before": L.get("sig")}]) or []
    res["creator_prior_sigs"] = [[s["signature"], s["slot"], s.get("blockTime"), bool(s.get("err"))] for s in sigs]
    res["creator_prior_n"] = len(sigs)
    if sigs and len(sigs) < 100:
        t = rpc("getTransaction", [sigs[-1]["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1}])
        if t:
            k = t["transaction"]["message"]["accountKeys"]; m = t["meta"]
            d = [(k[j], m["postBalances"][j] - m["preBalances"][j]) for j in range(len(k))]
            src = min(d, key=lambda x: x[1]); res["funder"] = dict(sig=sigs[-1]["signature"], slot=t["slot"], from_=src[0], amount=-src[1], payer=k[0])
    prev = []
    for s in sigs[:8]:
        t = rpc("getTransaction", [s["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1}])
        if not t: continue
        for l in (t["meta"] or {}).get("logMessages") or []:
            if l.startswith("Program data: "):
                try: raw = base64.b64decode(l[14:].strip() + "=" * (-len(l[14:].strip()) % 4))
                except Exception: continue
                if raw[:8] == CREATE_DISC:
                    try: c = parse_create(raw); prev.append(dict(sig=s["signature"], slot=s["slot"], mint=c["mint"], name=c["name"], symbol=c["symbol"]))
                    except Exception: pass
    res["creator_recent_creates"] = prev

def enrich(mint):
    L = LCACHE.get(mint) or {}
    res = dict(mint=mint, t=time.time())
    if not ENRICH_ON:
        res["enrich"] = "off"; jlog(LDAY.get(mint) or pkt_day(time.time()), "enrich.jsonl", res); ST["enriched"] += 1; return True
    try:
        res["meta"] = fetch_uri(L.get("uri"))
        j = (res["meta"].get("json") or {}) if isinstance(res["meta"].get("json"), dict) else {}
        hosts = {}
        for k in ("image", "website", "twitter", "telegram", "discord"):
            v = j.get(k) or (j.get("extensions") or {}).get(k) if isinstance(j.get("extensions"), dict) else j.get(k)
            if isinstance(v, str) and v: hosts[k] = urllib.parse.urlparse(v if "://" in v else "https://" + v).hostname
        res["hosts"] = hosts
    except Exception as e: res["meta_err"] = str(e)[:200]
    if ENRICH_RPC:
        try: enrich_rpc(res, L)
        except Exception as e: res["hist_err"] = str(e)[:200]
    else:
        res["rpc"] = "deferred"           # creator history / funder / recent creates: backfill later (rec enrich-backfill)
    try:
        res["jito_create"] = bundle_of(L.get("sig"))
        res["jito_early"] = [dict(idx=i, sig=s, bundle=bundle_of(s)) for i, s in EARLY.get(mint, [])[:3]]
    except Exception as e: res["jito_err"] = str(e)[:200]
    if STOP.is_set(): return False        # partial (stopping): leave it for the resume
    jlog(LDAY.get(mint) or pkt_day(time.time()), "enrich.jsonl", res); ST["enriched"] += 1
    return True

def enrich_worker():
    while True:
        due, mint = EQ.get()
        if mint is None: return
        while not STOP.is_set() and due - time.time() > 0: time.sleep(min(1.0, due - time.time()))
        if STOP.is_set(): return
        try: enrich(mint)
        except Exception: ST["enrich_exc"] += 1
        with _pl: PENDING[LDAY.get(mint)] -= 1

# ---------------- final pass (curve account + top holders per mint of a finished day) ----------------
def final_pass(day):
    mints, curves = [], {}
    lp = os.path.join(ddir(day), "launches.jsonl")
    for l in (open(lp) if os.path.exists(lp) else []):
        try: c = json.loads(l); mints.append(c["mint"]); curves[c["mint"]] = c.get("bonding_curve")
        except Exception: pass
    done = set()
    fp = os.path.join(ddir(day), "final.jsonl")
    if os.path.exists(fp):
        for l in open(fp):
            try: done.add(json.loads(l)["mint"])
            except Exception: pass
    todo = [m for m in mints if m not in done and curves.get(m)]
    log("final pass", day, "todo", len(todo))
    sp = os.path.join(ddir(day), "status.json")
    for k in range(0, len(todo), 100):
        if STOP.is_set(): return False
        try:                                              # progress for the watchdog (FRA writes the same "final k/n")
            st = json.load(open(sp)) if os.path.exists(sp) else {}
            st.update(phase=f"final {k}/{len(todo)}", now=time.time()); jdump(sp, st)
        except Exception: pass
        part = todo[k:k + 100]
        acc = rpc("getMultipleAccounts", [[curves[m] for m in part], {"encoding": "base64"}], kind="heavy") or {}
        vals = iter((acc or {}).get("value") or [])
        for m in part:
            a = next(vals, None)
            hold = rpc("getTokenLargestAccounts", [m], kind="heavy")
            if STOP.is_set(): return False
            jlog(day, "final.jsonl", dict(mint=m, t=time.time(), curve=a, top_holders=(hold or {}).get("value")))
    return True

# ---------------- resume / repair ----------------
def last_line_slot(path):
    """last complete slots.tsv line -> slot (truncates a partial last line)"""
    if not os.path.exists(path) or os.path.getsize(path) == 0: return None
    with open(path, "rb+") as f:
        f.seek(0, 2); size = f.tell(); back = min(size, 65536); f.seek(size - back); tail = f.read()
        if not tail.endswith(b"\n"):
            cut = tail.rfind(b"\n"); f.truncate(size - back + cut + 1 if cut >= 0 else 0)
            tail = tail[:cut + 1] if cut >= 0 else b""
        lines = tail.splitlines()
        return int(lines[-1].split(b"\t")[0]) if lines else None

def repair_chunks(day, keep_upto):
    """make every chunk of `day` a complete gzip holding only records with slot <= keep_upto (the original goes to
    $REC_ROOT/repair/, never deleted)"""
    for p in sorted(glob.glob(os.path.join(ddir(day), "txs", "*.jsonl.gz")))[-3:]:
        good = []; bad = False; maxs = -1
        try:
            with gzip.open(p, "rb") as g:
                for line in g:
                    if not line.endswith(b"\n"): bad = True; break
                    s = json.loads(line)["s"]
                    if s > keep_upto: bad = True; continue
                    good.append(line); maxs = max(maxs, s)
        except (EOFError, OSError, zlib.error, ValueError):
            bad = True
        if not bad: continue
        os.makedirs(os.path.join(REPAIR, day), exist_ok=True)
        orig = os.path.join(REPAIR, day, os.path.basename(p) + f".orig_{int(time.time())}")
        tmp = p + ".repair.tmp"
        with open(tmp, "wb") as raw:
            with gzip.GzipFile(filename=os.path.basename(p)[:-3], mode="wb", compresslevel=3, fileobj=raw) as g: g.writelines(good)
            raw.flush(); os.fsync(raw.fileno())
        shutil.copy2(p, orig); os.replace(tmp, p)
        log(f"repaired {day}/{os.path.basename(p)}: kept {len(good)} records (max slot {maxs}), original copied to {orig}")
        ST["chunks_repaired"] += 1

def truncate_jsonl_after(day, name, upto):
    p = os.path.join(ddir(day), name)
    if not os.path.exists(p): return
    keep = []; drop = 0
    for l in open(p):
        try: s = json.loads(l).get("slot")
        except Exception: drop += 1; continue
        if s is not None and s > upto: drop += 1; continue
        keep.append(l)
    if drop:
        with open(p + ".tmp", "w") as f: f.writelines(keep)
        os.replace(p + ".tmp", p); log(f"{day}/{name}: dropped {drop} line(s) after slot {upto} (re-recorded on resume)")

def load_tracking(days, ref_bt=None):
    """TRACK etc. from launches.jsonl of the given days (mints created less than REC_FOLLOW_H before ref_bt, the block
    time we resume at); re-queue launches without an enrich row. Also the mints seeded at the cut-over (FRA's run)."""
    horizon = (ref_bt or time.time()) - FOLLOW_S - 600
    sp = os.path.join(STATE, "seed_launches.jsonl")
    if os.path.exists(sp):
        for l in open(sp):
            try: c = json.loads(l)
            except Exception: continue
            if (c.get("bt") or 0) < horizon: continue
            m = c["mint"]; TRACK[m] = c["slot"]; TBT[m] = c.get("bt") or time.time(); LDAY[m] = "seeded"; LCACHE[m] = c; EARLY.setdefault(m, [])
    for day in days:
        lp = os.path.join(ddir(day), "launches.jsonl")
        if not os.path.exists(lp): continue
        done = set()
        ep_ = os.path.join(ddir(day), "enrich.jsonl")
        if os.path.exists(ep_):
            for l in open(ep_):
                try: done.add(json.loads(l)["mint"])
                except Exception: pass
        for l in open(lp):
            try: c = json.loads(l)
            except Exception: continue
            m = c["mint"]
            if (c.get("bt") or 0) < horizon: continue
            TRACK[m] = c["slot"]; TBT[m] = c.get("bt") or time.time(); LDAY[m] = day; LCACHE[m] = c; EARLY.setdefault(m, [])
            if m not in done:
                with _pl: PENDING[day] += 1
                EQ.put((time.time(), m))

def last_times(day):
    """-> (block time of the last 'ok' line, processed-at wall time of the last line) from a day's slots.tsv; the
    block time falls back to run.json / the wall time when the tail has no 'ok' line (a long run of failed slots)"""
    p = os.path.join(ddir(day), "slots.tsv"); bt = wt = None
    with open(p, "rb") as f:
        f.seek(0, 2); size = f.tell(); f.seek(max(0, size - (1 << 20))); tail = f.read().splitlines()
    for l in reversed(tail):
        x = l.split(b"\t")
        if wt is None and len(x) > 6:
            try: wt = float(x[6])
            except ValueError: pass
        if bt is None and len(x) > 2 and x[1] == b"ok":
            try: bt = float(x[2])
            except ValueError: pass
        if bt is not None and wt is not None: break
    if bt is None:
        try: bt = json.load(open(os.path.join(ddir(day), "run.json"))).get("last_block_time")
        except Exception: bt = None
    return bt or wt, wt or bt

def tip():
    s0 = None
    while s0 is None and not STOP.is_set():
        s0 = rpc("getSlot", [{"commitment": "confirmed"}])
        if s0 is None: time.sleep(5)
    return s0

def resume():
    """-> (Day, next_slot). Resumes at the slot after the last slots.tsv line; starts fresh at the tip when there is no
    recording yet, when REC_FRESH=1, or when the last recorded block is older than REC_RESUME_MAX_H (a long HOLD:
    the hole is written to run.json 'holes' + gaps.jsonl, never silently)."""
    days = sorted(d for d in os.listdir(DAYS) if re.fullmatch(r"\d{4}-\d\d-\d\d", d))
    for day in reversed(days):
        s = last_line_slot(os.path.join(ddir(day), "slots.tsv"))
        if s is None: continue
        repair_chunks(day, s); truncate_jsonl_after(day, "gaps.jsonl", s)
        for nd in [d for d in days if d > day]:          # rotated, crashed before its first sync: its records come again
            for p in glob.glob(os.path.join(ddir(nd), "txs", "*.jsonl.gz")):
                os.makedirs(os.path.join(REPAIR, nd), exist_ok=True); shutil.move(p, os.path.join(REPAIR, nd, os.path.basename(p) + ".orphan"))
                log(f"moved orphan chunk {nd}/{os.path.basename(p)} to repair/ (re-recorded on resume)")
            truncate_jsonl_after(nd, "gaps.jsonl", s)
        lbt, lwt = last_times(day); lbt = lbt or 0; lwt = lwt or 0
        load_tracking([d for d in days if d >= pkt_day((lbt or time.time()) - FOLLOW_S - 86400)], lbt or None)
        max_gap = float(cfg("REC_RESUME_MAX_H", "6")) * 3600
        if os.environ.get("REC_FRESH") == "1" or time.time() - lwt > max_gap:          # down for longer than max_gap
            s0 = tip()
            if s0 is None: return None, None
            why = "REC_FRESH=1" if os.environ.get("REC_FRESH") == "1" else f"stopped since {pkt_str(lwt)}, more than {max_gap / 3600:.1f} h"
            today = pkt_day(time.time())
            if today == day:
                D = Day(day, None, None, fresh=False)
                D.run.setdefault("holes", []).append([s + 1, s0 - LAG - 1, why]); jdump(os.path.join(D.dir, "run.json"), D.run)
                jlog(day, "gaps.jsonl", dict(slot=s + 1, to=s0 - LAG - 1, why="hole: " + why))
                log(f"FRESH in the same day {day}: hole {s + 1}..{s0 - LAG - 1} ({why})")
            else:
                run = json.load(open(os.path.join(ddir(day), "run.json")))
                run.update(end_slot=s, last_block_time=lbt, rotated_at=time.time(), hole_after=[s + 1, s0 - LAG - 1, why])
                jdump(os.path.join(ddir(day), "run.json"), run); FIN[day] = time.time()
                D = Day(today, s0 - LAG, time.time(), fresh=True)
                D.run["hole_before"] = [s + 1, s0 - LAG - 1, why]; jdump(os.path.join(D.dir, "run.json"), D.run)
                log(f"FRESH: {day} closed at slot {s} (incomplete), new day {today} from slot {s0 - LAG} ({why})")
            return D, s0 - LAG
        D = Day(day, None, None, fresh=False)
        D.run.setdefault("resumed_at", []).append([time.time(), s + 1]); jdump(os.path.join(D.dir, "run.json"), D.run)
        log(f"RESUME day {day} at slot {s + 1}; tracking {len(TRACK)} mints; enrich queue {EQ.qsize()}")
        return D, s + 1
    s0 = tip()
    if s0 is None: return None, None
    t0 = time.time(); day = pkt_day(t0); first = s0 - LAG
    if START_SLOT:
        first = START_SLOT; t0 = None          # the day dir is re-homed to the first block's PKT day, start_time = its block time
    if SEED:
        n0 = len(TRACK)
        for sp in SEED.split(","):
            for l in open(sp):
                try: c = json.loads(l)
                except Exception: continue
                if c.get("slot") is None or c["slot"] >= first or (c.get("bt") or 0) < time.time() - FOLLOW_S - 3600: continue
                m = c["mint"]; TRACK[m] = c["slot"]; TBT[m] = c.get("bt") or time.time(); LDAY[m] = "seeded"; LCACHE[m] = c; EARLY.setdefault(m, [])
                with open(os.path.join(STATE, "seed_launches.jsonl"), "a") as f: f.write(json.dumps(c, separators=(",", ":")) + "\n")
        log(f"seeded {len(TRACK) - n0} mints from {SEED} (created before slot {first}; kept in state/seed_launches.jsonl, their launches stay in the source run)")
    D = Day(day, first, t0 if t0 else time.time(), fresh=True)
    if START_SLOT: D.run["start_time"] = None; D.run["start_slot_set_by"] = "REC_START_SLOT"; jdump(os.path.join(D.dir, "run.json"), D.run)
    log(f"FRESH START day {day} at slot {first} (tip {s0}; mode {MODE}, block eps {[e.label for e in BEPS]}, rpc ep {REP.label})")
    return D, first

# ---------------- status ----------------
RATE = collections.deque(maxlen=120)      # (t, counters) for per-minute rates
def write_status(D, cur, last_slot, last_bt, phase="recording"):
    now = time.time()
    RATE.append((now, dict(ST)))
    rates = {}
    old = next((x for x in RATE if now - x[0] <= 610), None)
    if old and now - old[0] > 50:
        dt = now - old[0]
        rates = {k: round((v - old[1].get(k, 0)) / dt, 3) for k, v in ST.items() if "." in k and v - old[1].get(k, 0) > 0}
    calls = sum(v for k, v in ST.items() if "." in k and ".http" not in k)
    s = dict(D.run, now=now, confirmed_slot=cur, last_slot=last_slot, last_block_time=last_bt,
             lag_slots=(cur - last_slot) if (cur and last_slot) else None, lag_s=(now - last_bt) if last_bt else None,
             phase=phase, tracked_mints=len(TRACK), enrich_queue=EQ.qsize(), chunk_records=D.n, chunk=getattr(D, "chunk", None),
             stats=dict(ST), rates_10m=rates, calls_total=calls)
    jdump(os.path.join(D.dir, "status.json"), s)
    g = dict(pid=os.getpid(), mode=MODE, day=D.day, now=now, pkt=pkt_str(now), confirmed_slot=cur, last_slot=last_slot,
             last_block_time=last_bt, lag_slots=s["lag_slots"], lag_s=s["lag_s"], tracked_mints=len(TRACK), enrich_queue=EQ.qsize(),
             pending_by_day={k: v for k, v in PENDING.items() if v}, chunk=s["chunk"], last_write=getattr(D, "t_last_write", None),
             stats=dict(ST), rates_10m=rates, block_eps=[e.label for e in BEPS], rpc_ep=REP.label, started=T_START,
             finalizing=sorted(FIN), stop_at=STOP_AT or None)
    jdump(os.path.join(STATE, "recorder.json"), g)

# ---------------- main ----------------
FIN = {}               # day -> rotation wall time (enrich drain / final pass pending)
T_START = time.time()
FIN_DELAY = float(cfg("REC_FINALIZE_DELAY_S", "60"))
def finalize_ready(day):
    with _pl: p = PENDING.get(day, 0)
    return p <= 0 and time.time() - FIN[day] > FIN_DELAY

def finalize(day):
    rp = os.path.join(ddir(day), "run.json"); run = json.load(open(rp))
    fp_state = "deferred"
    if FINAL_PASS == "run":
        ok = final_pass(day); fp_state = "done" if ok else "interrupted"
    elif FINAL_PASS == "skip": fp_state = "skipped"
    sp = os.path.join(ddir(day), "status.json")
    st = json.load(open(sp)) if os.path.exists(sp) else dict(run)
    st.update(phase="DONE", final_pass=fp_state, finalized=time.time(), enrich_queue=0)
    jdump(os.path.join(ddir(day), "status.json"), st)
    run.update(final_pass=fp_state, finalized=time.time()); jdump(rp, run)
    log(f"day {day} finalized (final pass {fp_state})")
    try:   # catalog this day (low priority, detached)
        import subprocess
        subprocess.Popen(["nice", "-n", "15", sys.executable, "-I", os.path.join(os.path.dirname(os.path.abspath(__file__)), "rec.py"), "catalog", "--day", day],
                         stdout=subprocess.DEVNULL, stderr=open(os.path.join(ROOT, "logs", "catalog.log"), "a"), start_new_session=True)
    except Exception as e: log("catalog spawn failed", e)

def main():
    if os.path.exists(HOLD):
        try: why = json.load(open(HOLD)).get("reason")
        except Exception: why = "?"
        log("HOLD present, not starting:", why); print("HOLD present, not starting:", why, flush=True); return 0
    def on_sig(sig, frm):
        if not STOP.is_set(): STOP_WHY[0] = f"signal {sig}"; STOP.set()
    signal.signal(signal.SIGTERM, on_sig); signal.signal(signal.SIGINT, on_sig)
    D, nxt = resume()
    if D is None: return 0
    # days that were rotated but not finalized before a restart
    for day in sorted(os.listdir(DAYS)):
        if day < D.day:
            try: ph = json.load(open(os.path.join(ddir(day), "status.json"))).get("phase")
            except Exception: ph = None
            if ph != "DONE" and os.path.exists(os.path.join(ddir(day), "slots.tsv")): FIN[day] = time.time()
    workers = [threading.Thread(target=enrich_worker, daemon=True) for _ in range(ENRICH_WORKERS)]
    for w in workers: w.start()
    fin_thread = [None]
    cur = None; t_gs = 0.0; pending = collections.deque(); submit = nxt
    last_slot = nxt - 1; last_bt = None; t_status = 0.0; t_sync = time.time(); t_exp = time.time()
    ex = ThreadPoolExecutor(FETCH_THREADS)
    log(f"recording from slot {nxt} day {D.day} mode {MODE}")
    while not STOP.is_set():
        now = time.time()
        if STOP_AT and now >= STOP_AT:
            STOP_WHY[0] = f"REC_STOP_AT reached ({pkt_str(STOP_AT)})"
            json.dump(dict(reason=STOP_WHY[0], by="recorder", t=now, pkt=pkt_str(now)), open(HOLD, "w")); STOP.set(); break
        # housekeeping every iteration (also while idle / caught up)
        if now - t_sync > SYNC_S: D.sync(); t_sync = now
        if now - t_status > 30 and cur is not None:
            t_status = now; write_status(D, cur, last_slot, last_bt)
        if now - t_exp > 600:
            t_exp = now; lim = (last_bt or now) - FOLLOW_S; n0 = len(TRACK)
            for m in [m for m, t in TBT.items() if t < lim]:
                TRACK.pop(m, None); TBT.pop(m, None); EARLY.pop(m, None); LCACHE.pop(m, None)
            if n0 != len(TRACK): log(f"expired {n0 - len(TRACK)} mints older than {FOLLOW_S / 3600:.2f} h; tracking {len(TRACK)}")
        if FIN and (fin_thread[0] is None or not fin_thread[0].is_alive()):
            for day in sorted(FIN):
                if finalize_ready(day):
                    def _f(dd=day):
                        try: finalize(dd)
                        except Exception: log("finalize failed", dd, traceback.format_exc()[-400:])
                        FIN.pop(dd, None)
                    fin_thread[0] = threading.Thread(target=_f, daemon=True); fin_thread[0].start(); break
        caught_up = cur is not None and submit > cur - LAG
        if cur is None or (caught_up and now - t_gs > SLOT_EVERY) or now - t_gs > max(10.0, SLOT_EVERY):
            t_gs = now; c = rpc("getSlot", [{"commitment": "confirmed"}], tries=3, timeout=20)
            if isinstance(c, int): cur = c
            if cur is None: time.sleep(1); continue
        while len(pending) < AHEAD and submit <= cur - LAG and not (STOP_SLOT and submit > STOP_SLOT):
            if submit % SAMPLE: submit += SAMPLE - submit % SAMPLE; continue
            pending.append((submit, ex.submit(get_block, submit))); submit += 1
        if not pending:
            time.sleep(0.3); continue
        sl, fut = pending[0]
        if not fut.done():
            if len(pending) < AHEAD and submit <= cur - LAG: continue
            try: fut.result(timeout=0.5)
            except Exception: pass
            if not fut.done(): continue
        b = fut.result(); pending.popleft()
        if STOP.is_set(): break                       # a block fetched while stopping may be incomplete (None): leave it
        if b is None:
            ST["blocks_failed"] += 1; jlog(D.day, "gaps.jsonl", dict(slot=sl, why="fetch failed"))
            D.slot_line(sl, "fail", "", "", 0, 0, round(time.time(), 1))
        elif "_skip" in b:
            ST["blocks_skipped"] += 1; jlog(D.day, "gaps.jsonl", dict(slot=sl, why="skip", codes=b.get("_codes")))
            D.slot_line(sl, "skip", "", "", 0, 0, round(time.time(), 1))
        else:
            if RAW: RAW.put(sl, b)
            bt = b.get("blockTime") or time.time()
            nd = pkt_day(bt)
            if nd != D.day and D.is_blank():              # fresh start near midnight: the day is the first block's day
                old = D; gaps = old.abandon()
                D = Day(nd, old.run["start_slot"], old.run["start_time"] or bt, fresh=True); D.pend = old.pend
                if gaps:
                    with open(os.path.join(D.dir, "gaps.jsonl"), "a") as f: f.write(gaps)
                log(f"fresh day re-homed {old.day} -> {nd} (first block time {pkt_str(bt)})"); t_sync = time.time()
            if nd > D.day:                            # ROTATE: this block is the first of the next PKT day
                D.sync(); D.close()
                D.run.update(end_slot=sl - 1, last_block_time=last_bt, rotated_at=time.time(), next_day=nd, next_start_slot=sl)
                jdump(os.path.join(D.dir, "run.json"), D.run)
                st = json.load(open(os.path.join(D.dir, "status.json"))) if os.path.exists(os.path.join(D.dir, "status.json")) else {}
                st.update(D.run, phase="rotated (enrich drain)", now=time.time()); jdump(os.path.join(D.dir, "status.json"), st)
                FIN[D.day] = time.time(); log(f"ROTATE {D.day} -> {nd}: {D.day} end_slot {sl - 1}, {nd} start_slot {sl} (block time {bt} = {pkt_str(bt)})")
                D = Day(nd, sl, day_start(nd), fresh=True); t_sync = time.time()
            elif nd < D.day: ST["bt_before_day"] += 1
            if D.run.get("start_time") is None:
                D.run["start_time"] = bt; jdump(os.path.join(D.dir, "run.json"), D.run)
            try:
                ntx, nrec, ncre = process_block(D, sl, b); ST["blocks_ok"] += 1
                D.slot_line(sl, "ok", bt, ntx, nrec, ncre, round(time.time(), 1))
                if nrec: D.t_last_write = time.time()
            except Exception as e:
                ST["blocks_parse_err"] += 1; jlog(D.day, "gaps.jsonl", dict(slot=sl, why="parse " + repr(e)[:200]))
                D.slot_line(sl, "perr", bt, "", 0, 0, round(time.time(), 1))
            last_bt = bt
        last_slot = sl
        if STOP_SLOT and sl >= STOP_SLOT:
            STOP_WHY[0] = f"REC_STOP_SLOT {STOP_SLOT} reached"
            json.dump(dict(reason=STOP_WHY[0], by="maintenance", t=time.time(), pkt=pkt_str(time.time())), open(HOLD, "w")); STOP.set(); break
    # ---- shutdown: records of every processed slot are in the chunk; slots.tsv after the sync ----
    log("stopping:", STOP_WHY[0]); STOP.set()
    if RAW: RAW.close()
    try: D.close()
    except Exception: log("close failed", traceback.format_exc()[-300:])
    try: write_status(D, cur, last_slot, last_bt, phase="stopped: " + str(STOP_WHY[0]))
    except Exception: pass
    ex.shutdown(wait=False, cancel_futures=True)
    log("stopped cleanly at slot", last_slot, "stats", json.dumps({k: v for k, v in ST.items() if "." in k}))
    return 0

if __name__ == "__main__":
    try: rc = main()
    except SystemExit as e:
        log("exit:", e); print(e, flush=True); LOGF.flush(); os._exit(3)
    except Exception:
        log("CRASH", traceback.format_exc()); traceback.print_exc(); LOGF.flush(); os._exit(1)
    LOGF.flush(); sys.stdout.flush(); os._exit(rc or 0)
