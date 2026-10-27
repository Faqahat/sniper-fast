# sniper-rec shared helpers (stdlib only): paths, PKT time, catalog IO, chunk indexing, locking.
import os, json, time, calendar, gzip, zlib, hashlib, re, fcntl, glob, contextlib

ROOT = os.environ.get("REC_ROOT", "/home/moiz/sniper-data/rec")
LEGACY = os.environ.get("REC_LEGACY", "/home/moiz/sniper-data/collect")       # FRA runs copied by the keeper (run_*)
DAYS = os.path.join(ROOT, "days"); CACHE = os.path.join(ROOT, "cache"); STATE = os.path.join(ROOT, "state")
LOGS = os.path.join(ROOT, "logs"); SLIM = os.path.join(ROOT, "slim"); INDEX = os.path.join(STATE, "index")
CATALOG = os.path.join(ROOT, "catalog.json")
HOST_KEEP_DAYS = int(os.environ.get("REC_HOST_KEEP_DAYS", "7"))
REMOTE_KEEP_DAYS = int(os.environ.get("REC_REMOTE_KEEP_DAYS", "28"))
CACHE_CAP_GB = float(os.environ.get("REC_CACHE_CAP_GB", "60"))
PKT = 5 * 3600
DAY_RE = re.compile(r"^\d{4}-\d\d-\d\d$"); RUN_RE = re.compile(r"^run_20\d{6}_\d{4}$")

def pkt_day(ts): return time.strftime("%Y-%m-%d", time.gmtime(ts + PKT))
def day_start(day):
    y, m, d = map(int, day.split("-")); return calendar.timegm((y, m, d, 0, 0, 0)) - PKT
def next_day(day): return pkt_day(day_start(day) + 86400 + 3600)
def pkt_str(ts, sec=True):
    if ts is None: return None
    return time.strftime("%Y-%m-%d %H:%M:%S" if sec else "%Y-%m-%d %H:%M", time.gmtime(ts + PKT)) + " PKT"
def today(): return pkt_day(time.time())
def days_between(a, b):
    out, d = [], a
    while d <= b: out.append(d); d = next_day(d)
    return out
def parse_when(x):
    """'2026-10-27', '2026-10-27 16:40' (PKT), epoch seconds, or a slot number (> 1e8) -> ('slot', n) / ('time', epoch)"""
    x = str(x).strip()
    if re.fullmatch(r"\d+(\.\d+)?", x):
        v = float(x)
        return ("slot", int(v)) if v > 1e8 and v < 1e10 and "." not in x and len(x) <= 10 and v < 1.5e9 else ("time", v) if v > 1.5e9 else ("slot", int(v))
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try: return ("time", calendar.timegm(time.strptime(x.replace(" PKT", ""), fmt)) - PKT)
        except ValueError: pass
    raise ValueError(f"cannot parse {x!r} (PKT time like '2026-10-27 16:40', epoch, or slot)")

def jload(p, default=None):
    try:
        with open(p) as f: return json.load(f)
    except Exception: return default
def jdump(p, obj, indent=None):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + f".tmp{os.getpid()}"
    with open(tmp, "w") as f: json.dump(obj, f, indent=indent)
    os.replace(tmp, p)

@contextlib.contextmanager
def lock(name, wait=True):
    os.makedirs(STATE, exist_ok=True)
    f = open(os.path.join(STATE, name + ".lock"), "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
    except BlockingIOError:
        f.close(); raise RuntimeError(f"another '{name}' job holds the lock")
    try: yield
    finally: fcntl.flock(f, fcntl.LOCK_UN); f.close()

def log(name, *a):
    os.makedirs(LOGS, exist_ok=True)
    with open(os.path.join(LOGS, name + ".log"), "a") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%SZ ", time.gmtime()) + " ".join(str(x) for x in a) + "\n")

def sha256_file(p, bs=1 << 22):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(bs)
            if not b: break
            h.update(b)
    return h.hexdigest()

def index_chunk(p):
    """one pass over a txs chunk: sha256 of the file, record count, first/last slot + block time (records are written in
    slot order). A truncated gzip (chunk being written, or a crash) is indexed up to the last complete line: ok=False."""
    h = hashlib.sha256(); d = zlib.decompressobj(16 + zlib.MAX_WBITS); n = 0; first = None; tail = b""; ok = True
    with open(p, "rb") as f:
        while True:
            b = f.read(1 << 22)
            if not b: break
            h.update(b)
            try:
                out = d.decompress(b)
                while d.eof and d.unused_data:                         # multi-member gzip
                    rest = d.unused_data; d = zlib.decompressobj(16 + zlib.MAX_WBITS); out += d.decompress(rest)
            except zlib.error:
                ok = False; out = b""
            if out:
                if first is None:
                    j = out.find(b"\n")
                    first = out[:j] if j >= 0 else None
                n += out.count(b"\n"); tail = (tail + out)[-65536:]
    if not d.eof: ok = False
    lines = tail.split(b"\n"); last = None
    for l in reversed(lines[:-1] if not tail.endswith(b"\n") else lines):
        if l: last = l; break
    def sb(l):
        if not l: return None, None
        m = re.match(rb'\{"s":(\d+),"i":\d+,"bt":(null|\d+)', l)
        if not m:
            try: j = json.loads(l); return j.get("s"), j.get("bt")
            except Exception: return None, None
        return int(m.group(1)), (None if m.group(2) == b"null" else int(m.group(2)))
    s0, b0 = sb(first); s1, b1 = sb(last)
    return dict(size=os.path.getsize(p), sha256=h.hexdigest(), n=n, slot=[s0, s1], bt=[b0, b1], ok=ok)

def index_plain(p, count_lines=True):
    e = dict(size=os.path.getsize(p), sha256=sha256_file(p))
    if count_lines and p.endswith((".jsonl", ".tsv")):
        with open(p, "rb") as f: e["n"] = sum(b.count(b"\n") for b in iter(lambda: f.read(1 << 22), b""))
    return e

def file_list(base):
    out = []
    for dp, dn, fn in os.walk(base):
        dn.sort()
        for f in sorted(fn):
            if f.endswith((".tmp", ".part")) or ".tmp" in f: continue
            out.append(os.path.relpath(os.path.join(dp, f), base))
    return out

def cat_load():
    c = jload(CATALOG) or {}
    c.setdefault("version", 1); c.setdefault("days", {}); c.setdefault("runs", {}); c.setdefault("pins", [])
    return c
def cat_save(c):
    c["updated"] = time.time(); c["updated_pkt"] = pkt_str(c["updated"]); c["tz"] = "PKT (UTC+5)"
    jdump(CATALOG, c, indent=1)

def local_day_path(day, c=None):
    """where a day can be read on this host right now (host day dir, else cache), or None"""
    for p in (os.path.join(DAYS, day), os.path.join(CACHE, "days", day)):
        if os.path.isdir(os.path.join(p, "txs")): return p
    return None
