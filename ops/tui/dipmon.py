#!/usr/bin/env python3
# dipmon: a read-only, real-time terminal monitor for one pump.fun dip-bot run (the engine's <TAG>.jsonl + <TAG>.log).
#
#   sudo dipmon                 the running engine's run (its --dip-log), else the newest run file in /root/prod/runs
#   sudo dipmon --run 26        /root/prod/runs/dip_ams_r26.* (--region ams|fra; default: the one that exists)
#   sudo dipmon --snapshot      plain-text summary with the overview's numbers, then exit (--json: machine-readable)
#   dipmon --file X.jsonl       any run file (finished runs, local copies); the .log next to it is read too
#
# Never touches the engine: reads the run files, the budget file and /proc only (incremental tails, chunked initial load with
# sleeps between chunks); no RPC; never reads .env files, keystores or configs. The only network use is the SOL/USD price
# (Binance, then CoinGecko, every 60 s in a background thread, cached in /tmp). Python 3.9+ standard library only.
#
# Accounting = ops/dip/report/make_run_report.py (README.md has the details):
#   pre-send net = sum presend_live_realized.pnl + sum presend_live_ata_close.delta (ok ones) - failed-attempt fees
#                  (fees counted live = sum presend_attempt_land.fee where res != "ok"; checked against the engine's counter:
#                  the status line's "failed-attempt fees", presend_live_stop.fees at the end; the larger one is used)
#   regular      = the log's "REALIZED mint=.. pnl=.." of each filled buy + every failed buy at its tx fee (505,000 lamports)
#   run P&L      = pre-send net + regular;   wallet now (est.) = the session's START BALANCE + the session's P&L
import argparse
import collections
import datetime as dt
import json
import locale
import os
import re
import sys
import threading
import time
import unicodedata
import urllib.request

VERSION = "1.0"
LAM = 1_000_000_000
PKT = dt.timezone(dt.timedelta(hours=5))
FAILED_BUY_FEE = 505_000          # 5,000 base + 100,000 CU x 5,000,000 uL/CU (run script: --cu-limit 100000 --cu-price-micro 5000000)
PS_FAIL_FEE = 5_120               # 5,000 base + 120,000 CU x 1,000 uL/CU (the engine prints its own: "a failed attempt N lamports")
DEFAULT_DIR = "/root/prod/runs"
KIND = {"JitoLabs": "Jito", "AgaveBam": "BAM", "FireBAM": "BAM", "HarmonicAgave": "Harmonic", "HarmonicFiredancer": "Harmonic",
        "Firedancer": "Firedancer", "Frankendancer": "Firedancer", "Agave": "Agave", "Rakurai": "Rakurai", "Raiku": "Raiku"}
EXIT_SHORT = {"take-profit": "TP", "stop-loss": "SL", "time-limit": "time", "time": "time"}
# route presets of ops/prod/run_dip_prod.sh (--routes vN): the engine gets the expanded string; matched back to a name
ROUTE_PRESETS = {
    "v13": "bam=nozomi+helius-swqos+bolt+falcon+falcon-udp+soyas+solami+0slot;jito=solami+soyas+glaive+falcon+falcon-udp+helius-swqos+0slot;harmonic=nozomi+landx-fra3+falcon+falcon-udp+glaive+soyas+solami+0slot;fd=0slot+nozomi+landx-fra3+staked-rpc+soyas+solami;agave=nozomi+helius-swqos+bolt+staked-rpc;other=nozomi+helius-swqos+bolt+staked-rpc;default=nozomi+helius-swqos+bolt+staked-rpc",
    "v12": "bam=nozomi+helius-swqos+bolt+falcon+falcon-udp+soyas+solami;jito=solami+soyas+glaive+falcon+falcon-udp+helius-swqos;harmonic=nozomi+landx-fra3+falcon+falcon-udp+glaive+soyas+solami;fd=nozomi+landx-fra3+staked-rpc+soyas+solami;agave=nozomi+helius-swqos+bolt+staked-rpc;other=nozomi+helius-swqos+bolt+staked-rpc;default=nozomi+helius-swqos+bolt+staked-rpc",
    "v11": "bam=nozomi+helius-swqos+bolt+falcon+falcon-udp;jito=falcon+falcon-udp+helius-swqos+helius;harmonic=nozomi+falcon+falcon-udp+landx-fra3;fd=nozomi+landx-fra3+staked-rpc;agave=nozomi+helius-swqos+bolt+staked-rpc;other=nozomi+helius-swqos+bolt+staked-rpc;default=nozomi+helius-swqos+bolt+staked-rpc",
    "v10": "bam=nozomi+helius-swqos+bolt+falcon;jito=falcon+helius-swqos+helius;harmonic=nozomi+falcon+landx-fra3;fd=nozomi+landx-fra3+staked-rpc;agave=nozomi+helius-swqos+bolt+staked-rpc;other=nozomi+helius-swqos+bolt+staked-rpc;default=nozomi+helius-swqos+bolt+staked-rpc",
    "v9": "bam=nozomi+helius-swqos+bolt;jito=helius+helius-swqos+staked-rpc;harmonic=nozomi+landx-fra3;fd=nozomi+landx-fra3+staked-rpc;agave=nozomi+helius-swqos+bolt+staked-rpc;other=nozomi+helius-swqos+bolt+staked-rpc;default=nozomi+helius-swqos+bolt+staked-rpc",
    "v8": "bam=nozomi+helius-swqos+bolt+staked-rpc;jito=helius+nozomi+jito-bundle+staked-rpc;harmonic=nozomi+helius-swqos+landx-fra3+staked-rpc;fd=nozomi+landx-fra3+staked-rpc;agave=nozomi+helius-swqos+bolt+staked-rpc;other=nozomi+helius-swqos+bolt+staked-rpc;default=nozomi+helius-swqos+bolt+staked-rpc",
}


def _route_map(spec):
    out = {}
    for part in (spec or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = tuple(x.strip() for x in v.replace(" ", "").split("+") if x.strip())
    return out


PRESET_MAPS = {name: _route_map(s) for name, s in ROUTE_PRESETS.items()}


def route_preset(routes):
    """a {kind: (paths)} map -> the preset name (v8..v13) or 'custom'"""
    if not routes:
        return None
    for name, m in PRESET_MAPS.items():
        if all(m.get(k) == v for k, v in routes.items()) and len(routes) >= 5:
            return name
    return "custom"


# ------------------------------------------------------------------------------------------------------------------ glyphs
UNI = dict(on="●", sep="·", arrow="→", dash="–", hr="─", vr="│", bar="━", bar0="─",
           spark="▁▂▃▄▅▆▇█", ell="…", x="×", ok="✓", no="✗",
           up="▲", down="▼", tri="▸", dia="◆", ge="≥", minus="-")
ASC = dict(on="*", sep="|", arrow="->", dash="-", hr="-", vr="|", bar="=", bar0="-", spark="_.:-=+*#", ell="~", x="x", ok="ok",
           no="x", up="^", down="v", tri=">", dia="+", ge=">=", minus="-")
G = dict(UNI)
BADGE_ASCII = {"on": "+", "off": "-", "part": "~", "na": "."}


def set_ascii(on):
    G.clear()
    G.update(ASC if on else UNI)
    G["ascii"] = on


set_ascii(False)

# big numerals: 3 rows of half blocks (a 3x5 pixel font), and a seven-segment ASCII fallback
BIG_UNI = {
    "0": ("█▀█", "█ █", "▀▀▀"),
    "1": ("▄█ ", " █ ", "▀▀▀"),
    "2": ("▀▀█", "█▀▀", "▀▀▀"),
    "3": ("▀▀█", "▀▀█", "▀▀▀"),
    "4": ("█ █", "▀▀█", "  ▀"),
    "5": ("█▀▀", "▀▀█", "▀▀▀"),
    "6": ("█▀▀", "█▀█", "▀▀▀"),
    "7": ("▀▀█", "  █", "  ▀"),
    "8": ("█▀█", "█▀█", "▀▀▀"),
    "9": ("█▀█", "▀▀█", "▀▀▀"),
    ".": (" ", " ", "▀"),
    "+": (" ▄ ", "▀█▀", "   "),
    "-": ("   ", "▀▀▀", "   "),
    "$": ("▄█▄", "█▄▄", "▄▄█"),
}
BIG_ASC = {
    "0": (" _ ", "| |", "|_|"), "1": ("   ", "  |", "  |"), "2": (" _ ", " _|", "|_ "), "3": (" _ ", " _|", " _|"),
    "4": ("   ", "|_|", "  |"), "5": (" _ ", "|_ ", " _|"), "6": (" _ ", "|_ ", "|_|"), "7": (" _ ", "  |", "  |"),
    "8": (" _ ", "|_|", "|_|"), "9": (" _ ", "|_|", " _|"), ".": (" ", " ", "."), "+": ("   ", "_|_", " | "),
    "-": ("   ", " _ ", "   "), "$": (" _ ", "(_ ", " _)"),
}


BITMAP = {"0": ("111", "101", "101", "101", "111"), "1": ("010", "110", "010", "010", "111"), "2": ("111", "001", "111", "100", "111"),
          "3": ("111", "001", "111", "001", "111"), "4": ("101", "101", "111", "001", "001"), "5": ("111", "100", "111", "001", "111"),
          "6": ("111", "100", "111", "101", "111"), "7": ("111", "001", "001", "001", "001"), "8": ("111", "101", "111", "101", "111"),
          "9": ("111", "101", "111", "001", "111"), ".": ("0", "0", "0", "0", "1"), "+": ("000", "010", "111", "010", "000"),
          "-": ("000", "000", "111", "000", "000"), "$": ("011", "110", "010", "011", "110")}


def big_text5(s):
    """5 lines of large numerals (2 columns a pixel)"""
    px = "##" if G.get("ascii") else "\u2588\u2588"
    rows = ["", "", "", "", ""]
    for i, ch in enumerate(s):
        g = BITMAP.get(ch)
        if g is None:
            continue
        for r in range(5):
            rows[r] += "".join(px if b == "1" else "  " for b in g[r]) + (" " if i < len(s) - 1 else "")
    return rows


def big_text(s):
    """3 lines of big numerals for s (digits, sign, point, $)"""
    font = BIG_ASC if G.get("ascii") else BIG_UNI
    rows = ["", "", ""]
    for i, ch in enumerate(s):
        g = font.get(ch)
        if g is None:
            continue
        for r in range(3):
            rows[r] += g[r] + (" " if i < len(s) - 1 else "")
    return rows


# ------------------------------------------------------------------------------------------------------------------ helpers
def pkt(ns, fmt="%H:%M:%S"):
    if not ns:
        return G["dash"]
    try:
        return dt.datetime.fromtimestamp(ns / 1e9, PKT).strftime(fmt)
    except (ValueError, OverflowError, OSError, TypeError):
        return "?"


def hms(sec, secs=False):
    """seconds -> h:mm (or h:mm:ss)"""
    if sec is None:
        return G["dash"]
    sec = int(max(0, sec))
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if secs else f"{h}:{m:02d}"


def age_s(sec):
    if sec is None:
        return G["dash"]
    sec = max(0, sec)
    if sec < 90:
        return f"{sec:.0f}s"
    if sec < 5400:
        return f"{sec / 60:.0f}m"
    return f"{sec / 3600:.1f}h"


def sol(lam, d=4, sign=True):
    if lam is None:
        return G["dash"]
    v = lam / LAM
    return f"{v:+.{d}f}" if sign else f"{v:.{d}f}"


def usd(lam, price, sign=True, d=2):
    if lam is None or not price:
        return "USD n/a"
    v = lam / LAM * price
    if sign:
        return ("+" if v >= 0 else "-") + f"${abs(v):,.{d}f}"
    return f"${v:,.{d}f}"


def pct_s(x, d=1, sign=True):
    if x is None:
        return G["dash"]
    return f"{x * 100:+.{d}f}%" if sign else f"{x * 100:.{d}f}%"


def med(v):
    v = sorted(x for x in v if x is not None)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def short(m, n=6):
    return (m or "?")[:n]


def kind_of(client):
    return KIND.get(client or "", client or "?")


_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_SECRET = re.compile(r"(?i)((?:api[-_]?key|token|secret|auth|passw(?:or)?d|key)=)[^&\s\"']+")
_USERINFO = re.compile(r"(://)[^/\s:@]+:[^/\s@]+@")


def clean(s):
    """a log line made safe to show: no control chars, no wide / emoji / combining chars, no secret-looking URL parts"""
    s = s.replace("\t", "  ")
    s = _CTRL.sub("?", s)
    if "=" in s:
        s = _SECRET.sub(r"\1***", s)
    if "@" in s:
        s = _USERINFO.sub(r"\1***@", s)
    if G.get("ascii"):
        return s.encode("ascii", "replace").decode("ascii")
    if s.isascii():
        return s
    out = []
    for ch in s:
        o = ord(ch)
        if o < 128:
            out.append(ch)
        elif o >= 0x1F000 or unicodedata.east_asian_width(ch) in ("W", "F") or unicodedata.combining(ch) or \
                unicodedata.category(ch) in ("Cf", "Cs", "Co", "Cn", "Mn", "Me"):
            out.append("?")
        else:
            out.append(ch)
    return "".join(out)


def _num_after(line, key):
    """bytes: the integer right after key (e.g. b'"fee":'), or None"""
    i = line.find(key)
    if i < 0:
        return None
    i += len(key)
    j = i
    n = len(line)
    if j < n and line[j] == 45:  # '-'
        j += 1
    while j < n and 48 <= line[j] <= 57:
        j += 1
    try:
        return int(line[i:j])
    except ValueError:
        return None


def _t_of(line):
    """bytes: the record's top-level time: its last "t": (sorted keys put nested trades' "t" first), else "t_send":"""
    i = line.rfind(b'"t":')
    k = 4
    if i < 0:
        i = line.rfind(b'"t_send":')
        k = 9
        if i < 0:
            return None
    i += k
    j = i
    n = len(line)
    while j < n and 48 <= line[j] <= 57:
        j += 1
    try:
        return int(line[i:j])
    except ValueError:
        return None


# ------------------------------------------------------------------------------------------------------------------ tail
class Tail:
    """incremental reader of a growing file: remembers its offset, keeps a partial last line, notices truncation / replacement"""

    def __init__(self, path):
        self.path = path
        self.off = 0
        self.buf = b""
        self.ino = None
        self.size = 0
        self.mtime = None
        self.reset = False          # set when the file was truncated or replaced (the caller re-reads everything)
        self.exists = False
        self.err = None

    def stat(self):
        try:
            st = os.stat(self.path)
        except OSError as e:
            self.exists = False
            self.err = str(e)
            return None
        self.exists = True
        self.err = None
        if self.ino is not None and (st.st_ino != self.ino or st.st_size < self.off):
            self.off = 0
            self.buf = b""
            self.reset = True
        self.ino = st.st_ino
        self.size = st.st_size
        self.mtime = st.st_mtime
        return st

    def pending(self):
        return max(0, self.size - self.off)

    def read(self, max_bytes):
        """complete new lines (bytes, without the newline), at most ~max_bytes of them"""
        st = self.stat()
        if st is None or st.st_size <= self.off:
            return []
        try:
            with open(self.path, "rb") as f:
                f.seek(self.off)
                data = f.read(min(max_bytes, st.st_size - self.off))
        except OSError as e:
            self.err = str(e)
            return []
        self.off += len(data)
        if self.buf:
            data = self.buf + data
        lines = data.split(b"\n")
        self.buf = lines.pop()
        if len(self.buf) > 8_000_000:     # a runaway line without a newline: drop it (never grow without bound)
            self.buf = b""
        return lines

    def flush_partial_json(self):
        """a complete JSON object sitting without its newline (the writer paused between the record and the newline)"""
        b = self.buf.strip()
        if b.startswith(b"{") and b.endswith(b"}"):
            try:
                json.loads(b)
            except ValueError:
                return None
            self.buf = b""
            return b
        return None


# ------------------------------------------------------------------------------------------------------------------ model
JSON_EVENTS = {b"run_start", b"run_end", b"fire", b"buy_land", b"buy_failed", b"land_poll", b"timing", b"exit", b"sell_land", b"close",
               b"presend_live_arm", b"presend_live_disarm", b"presend_live_skip", b"presend_live_fill", b"presend_live_exit",
               b"presend_live_close", b"presend_live_realized", b"presend_live_ata_close", b"presend_live_stop",
               b"presend_live_end_check", b"presend_live_held", b"presend_live_quiet_preload", b"presend_live_quiet_state"}
IGNORED_EVENTS = {b"tape", b"presend_live_tape", b"presend_arm", b"presend_disarm", b"presend_skip", b"presend_fill", b"presend_exit",
                  b"presend_live_parity", b"presend_live_ata", b"presend_live_sell_land", b"shred_dump", b"shred_parity", b"feed_lag",
                  b"probe_land"}


NUM_KEYS = {"t", "t_fire", "t_dump_rx", "t_send", "spend", "dev_spend", "minutes", "loss_cap", "tp", "sl", "hold_slots", "guard", "max_buys",
            "max_inflight", "thr", "decision_us", "slot", "rx_ms_after_dump", "slots_after_dump", "fee", "fees", "sol", "sol_in",
            "ms_send_to_rx", "slots_after_trigger", "tip", "slots_held", "value", "held_s", "exit_slot", "curve_pnl", "pnl", "delta", "fills",
            "secs", "covered_h", "arm_rule_on_at", "w", "k", "drop", "deadline_slots", "max_fills", "fee_budget", "fail_fee", "exit_slots",
            "pct", "warmup_min", "hist_h", "fol", "min", "realized", "fired", "closed", "landed_buys", "dumps", "picks", "reaction_ms",
            "exec_lag_ms", "fire_to_seen_ms", "limit", "score", "merged", "late"}
STR_KEYS = {"ev", "mint", "client", "leader", "route", "buy_sig", "dump_sig", "sig", "why", "exit_why", "result", "path", "src", "action",
            "res", "routes", "mode", "model", "tier", "dev_tier", "wallet", "stop"}
NESTED = ("presend_live", "quiet", "trig", "m2", "variant")


TIME_KEYS = {"t", "t_fire", "t_dump_rx", "t_send", "arm_rule_on_at"}


def time_ok(t):
    """a record time (ns) from 2017..2049"""
    return isinstance(t, int) and 1_500_000_000_000_000_000 < t < 2_500_000_000_000_000_000


def _san(o, depth=0):
    """a parsed record with wrong-typed fields dropped (an odd line must never break a view later)"""
    for k in list(o.keys()):
        v = o[k]
        if k in NUM_KEYS:
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or abs(v) > 1e20 or (k in TIME_KEYS and not time_ok(v)):
                o[k] = None
        elif k in STR_KEYS:
            if not isinstance(v, str):
                o[k] = None
        elif k in ("land", "sell_land") and isinstance(v, list):
            o[k] = [x if (isinstance(x, (int, float)) and not isinstance(x, bool) and abs(x) < 4e18) else None for x in v]
            if len(o[k]) > 2 and o[k][2] is not None and not time_ok(o[k][2]):
                o[k][2] = None
        elif k in ("buy_sigs", "devs", "nonce_accounts", "writes", "sell_sigs") and not isinstance(v, list):
            o[k] = None
        elif depth < 2 and k in NESTED and isinstance(v, dict):
            _san(v, depth + 1)
    return o


class Sess:
    """one engine session (one run_start; a restart into the same log is the next session)"""

    def __init__(self, idx):
        self.idx = idx
        self.has_rs = False
        self.rs = {}                  # run_start config (subset)
        self.t0 = None                # run_start t (ns)
        self.re = None                # run_end (subset)
        self.cur_t = 0                # newest record time of this session
        # ---- log
        self.live = {}                # "DIP LIVE | ..." fields
        self.start_bal = None         # START BALANCE (lamports)
        self.kill_level = None        # kill switch below (lamports)
        self.psl = {}                 # "DIP PRESEND LIVE (REAL attempts) | ..." fields
        self.quiet = {}               # "DIP PRESEND LIVE QUIET: ..." fields (+ preload / status updates)
        self.cfg = {}                 # other start lines: routes, nonce, sell fan-out, near gate, M2, shadow, dev list, skip clients
        self.done = None              # "=== DIP DONE" (dict)
        self.signal = None
        self.kill = None
        self.ps_stopped = None        # (why, fills, cap) from "PRESEND LIVE STOPPED (why)"
        self.end_check = None         # (n, sold, closed, held, unreadable)
        self.status = {}              # latest "DIP status" pieces
        self.engine_realized = None   # the engine's run_realized (REALIZED lines / DIP DONE), lamports
        self.paper = None             # shadow row c: (fills, gross SOL, net SOL) from the status / end lines
        self.log_ps_fees = 0          # max "failed-attempt fees X" in PRESEND LIVE lines (lamports)
        self.log_ps_real = []         # PRESEND LIVE REALIZED (fallback when the jsonl has no pre-send records)
        self.errors = []
        # ---- regular (reactive) bot
        self.reg = []
        self.by_mint = collections.defaultdict(list)
        self.real_q = collections.defaultdict(collections.deque)   # REALIZED pnl (lamports) per mint, waiting for its filled buy
        self.dumps = 0
        self.picks = 0
        # ---- pre-send live
        self.ps_rec = False           # any presend_live_* / attempt record
        self.ps_fills = 0
        self.ps_wins = 0
        self.ps_nreal = 0
        self.ps_realized = 0
        self.ps_rent = 0
        self.ps_fee_cnt = 0           # sum of the failed attempts' fees (presend_attempt_land res != ok)
        self.ps_fee_n = 0             # failed attempts that cost a fee
        self.ps_fee_each = collections.Counter()
        self.ps_sent = 0
        self.ps_dry = 0
        self.ps_res = collections.Counter()
        self.ps_armed = 0
        self.ps_open = set()
        self.ps_skips = collections.Counter()
        self.ps_disarms = collections.Counter()
        self.ps_pos = {}              # (w, mint) -> the newest trade
        self.ps_bykey = collections.defaultdict(list)   # (w, mint) -> every trade of that window, oldest first
        self.ps_list = []
        self.ps_stop = []
        self.ps_endchk = collections.Counter()
        self.ps_held = 0
        self.ps_ata_fail = 0
        self.ps_land_ms = []
        self.ps_after = []
        self.q_skips = 0
        self.q_stops = 0
        self.q_would = 0
        self.q_rule_on = None         # the newest arm / skip record's "rule_on"
        self.q_preload = None         # presend_live_quiet_preload record (subset)
        self.buckets = collections.Counter()   # unix minute -> P&L change (lamports)

    # ---------------------------------------------------------------- derived
    def ps_fees(self):
        stop = max([s.get("fees") or 0 for s in self.ps_stop] or [0])
        return max(self.ps_fee_cnt, self.log_ps_fees, stop)

    def ps_active(self):
        return bool(self.ps_rec or self.psl or self.log_ps_real or self.log_ps_fees)

    def ps_net(self):
        if self.ps_rec:
            return self.ps_realized + self.ps_rent - self.ps_fees()
        return sum(self.log_ps_real) - self.log_ps_fees

    def reg_total(self):
        return sum(t["pnl"] or 0 for t in self.reg)

    def total(self):
        return self.ps_net() + self.reg_total()

    def ended(self):
        return bool(self.done or self.re)

    def t_end(self):
        if self.re and self.re.get("t"):
            return self.re["t"]
        return None

    def minutes(self):
        return self.rs.get("minutes") or self.live.get("minutes")

    def loss_cap(self):
        if self.rs.get("loss_cap") is not None:
            return self.rs["loss_cap"]
        return self.live.get("loss_cap")


class Model:
    def __init__(self, fail_buy_fee=None, log_keep=3000):
        self.sessions = []
        self.jsess = -1               # jsonl: index of the current session (its run_start)
        self.lsess = -1               # log: index of the current session (its "DIP LIVE |" line)
        self.lpend = {}               # log start lines seen before this engine start's "DIP LIVE |" line
        self.version = 0
        self.cur_t = 0
        self.bad = 0
        self.jlines = 0
        self.llines = 0
        self.log_min = 0              # minutes of log (one "RUNTIME lag 60s" line a minute)
        self.log_ring = collections.deque(maxlen=log_keep)
        self.log_imp = collections.deque(maxlen=max(200, log_keep // 2))
        self.rpc = {}                 # (name, method) -> dict(p50, p99, n, to, min)
        self.runtime = None           # (p50, p99, max) latest
        self.runtime_worst = 0.0
        self.poll_err = collections.Counter()           # log minute -> POLL-RPC-ERROR lines
        self.poll_err_total = 0
        self.path_err = collections.defaultdict(collections.Counter)   # path -> log minute -> errors
        self.path_kind = {}           # path -> last error kind
        self.path_total = collections.Counter()
        self.engine_starts = 0
        self.seg_live = False         # this engine start reached its "DIP LIVE |" line
        self.refused = []             # "Error: ..." of starts that never reached "DIP LIVE |"
        self.panics = []
        self.fail_buy_fee = fail_buy_fee or FAILED_BUY_FEE
        self.fail_buy_fee_src = "cmdline" if fail_buy_fee else "default"
        self.arm_info = collections.OrderedDict()       # (session, w) -> (whale pct, whale SOL)
        self.trades = []              # every trade (REG + PS), creation order
        self.ev_count = collections.Counter()
        self._jh = {b"dump": self._j_dump, b"presend_attempt": self._j_attempt, b"presend_attempt_land": self._j_attempt_land,
                    b"pick": self._j_pick, b"pick_skip": self._j_count}

    # ---------------------------------------------------------------- sessions
    def sess(self, i):
        i = max(0, i)
        while len(self.sessions) <= i:
            self.sessions.append(Sess(len(self.sessions)))
        return self.sessions[i]

    def jcur(self):
        return self.sess(self.jsess)

    def lcur(self):
        return self.sess(self.lsess)

    # ---------------------------------------------------------------- jsonl
    def feed_jsonl(self, lines):
        for line in lines:
            self.jlines += 1
            i = line.find(b'"ev":"')
            if i < 0:
                if line.strip():
                    self.bad += 1
                continue
            j = line.find(b'"', i + 6)
            ev = line[i + 6:j]
            if ev in IGNORED_EVENTS:
                continue
            try:
                h = self._jh.get(ev)
                if h is not None:
                    h(line)
                elif ev in JSON_EVENTS:
                    self._j_json(json.loads(line))
                else:
                    self.ev_count[ev] += 1
                    if len(self.ev_count) > 200:
                        self.ev_count.clear()
            except Exception:
                self.bad += 1
        self.version += 1

    def _time(self, S, t):
        if not time_ok(t):
            return
        if t > S.cur_t:
            S.cur_t = t
            if t > self.cur_t:
                self.cur_t = t

    def _j_dump(self, line):
        S = self.jcur()
        S.dumps += 1
        self._time(S, _t_of(line))

    def _j_pick(self, line):
        self.jcur().picks += 1

    def _j_count(self, line):
        pass

    def _j_attempt(self, line):
        S = self.jcur()
        S.ps_rec = True
        if b'"dry":true' in line:
            S.ps_dry += 1
        else:
            S.ps_sent += 1

    def _j_attempt_land(self, line):
        S = self.jcur()
        S.ps_rec = True
        i = line.find(b'"res":"')
        res = "?"
        if i >= 0:
            j = line.find(b'"', i + 7)
            res = line[i + 7:j].decode("ascii", "replace")
        S.ps_res[res] += 1
        t = _t_of(line)
        self._time(S, t)
        if res != "ok":
            fee = _num_after(line, b'"fee":') or 0
            if fee:
                S.ps_fee_cnt += fee
                S.ps_fee_n += 1
                S.ps_fee_each[fee] += 1
                S.buckets[(t if time_ok(t) else (S.cur_t or self.cur_t)) // 60_000_000_000] -= fee

    def _j_json(self, o):
        if not isinstance(o, dict):
            self.bad += 1
            return
        o = _san(o)
        e = o.get("ev") or ""
        if e == "run_start":
            self.jsess = 0 if self.jsess < 0 and not self.sess(0).has_rs else self.jsess + 1
            S = self.jcur()
            S.has_rs = True
            S.t0 = o.get("t")
            self._time(S, S.t0)
            keep = ("minutes", "loss_cap", "spend", "dev_spend", "dev_tier", "tier", "model", "tp", "sl", "hold_slots", "guard", "max_buys",
                    "max_inflight", "live", "wallet", "thr", "skip_clients")
            S.rs = {k: o.get(k) for k in keep if k in o}
            S.rs["devs"] = len(o.get("devs") or [])
            S.rs["nonce"] = len(o.get("nonce_accounts") or [])
            m2 = o.get("m2")
            if isinstance(m2, dict):
                S.rs["m2"] = {"mode": m2.get("mode"), "model": m2.get("model"), "min": m2.get("min")}
            if isinstance(o.get("presend"), dict):
                S.rs["presend"] = True
            pl = o.get("presend_live")
            if isinstance(pl, dict):
                S.rs["psl"] = {k: pl.get(k) for k in ("dry", "spend", "k", "drop", "deadline_slots", "routes", "max_fills", "fee_budget",
                                                      "fail_fee", "tp", "sl", "exit_slots", "create_slot", "one_position")}
                q = pl.get("quiet")
                if isinstance(q, dict):
                    S.rs["quiet"] = {"stop": q.get("stop"), "skip": q.get("skip"), "warmup_min": q.get("warmup_min"),
                                     "preload": bool(q.get("preload")), "hist_h": q.get("hist_h"), "fol": q.get("fol")}
            return
        S = self.jcur()
        t = o.get("t")
        if t:
            self._time(S, t)
        if e.startswith("presend_live_"):
            S.ps_rec = True
            self._ps(S, e, o)
        elif e == "run_end":
            S.re = {k: o.get(k) for k in ("t", "fired", "closed", "landed_buys", "realized", "dumps", "picks", "skipped")}
            pl = o.get("presend_live") or {}
            if isinstance(pl.get("quiet"), dict):
                S.re["quiet"] = {k: pl["quiet"].get(k) for k in ("skips", "stops", "warm_would", "arm_rule_on_at")}
        else:
            self._reg(S, e, o)

    # ---------------------------------------------------------------- regular bot (the report's build_trades / classify)
    def _reg(self, S, e, o):
        if e == "fire":
            paths = [w.get("path") for w in (o.get("writes") or []) if isinstance(w, dict) and w.get("st") == "written"]
            tr = dict(kind="REG", s=S.idx, t=o.get("t_fire") or o.get("t") or S.cur_t, mint=o.get("mint") or "", spend=o.get("spend"),
                      dev=bool(o.get("dev")), client=o.get("client") or "?", leader=o.get("leader") or "", route=o.get("route") or "",
                      buy_sig=o.get("buy_sig"), dump_sig=o.get("dump_sig"), dec_us=o.get("decision_us"), t_dump=o.get("t_dump_rx"),
                      slot=o.get("slot"), paths=[p for p in dict.fromkeys(paths) if p], land=None, failed=None, poll_err=None,
                      timing=None, exit=None, sells=[], close=None, pnl=None, src=None, res="open", booked=0, bm=None)
            S.reg.append(tr)
            S.by_mint[tr["mint"]].append(tr)
            self.trades.append(tr)
            return
        m = o.get("mint")
        cands = S.by_mint.get(m)
        if not cands:
            return
        tr = next((x for x in cands if x["close"] is None), None) or cands[-1]
        if e == "buy_land":
            if tr["land"] is None:
                v = o.get("variant") or {}
                tr["land"] = dict(t=o.get("t"), slot=o.get("slot"), ms=o.get("rx_ms_after_dump"), blk=o.get("slots_after_dump"),
                                  fee=o.get("fee"), sig=o.get("sig"), via="+".join(v.get("paths") or []) if isinstance(v, dict) else "",
                                  sol=o.get("sol"))
                if o.get("fee") and self.fail_buy_fee_src != "cmdline":
                    self.fail_buy_fee_src = "landed buy fee"
                    if o["fee"] != self.fail_buy_fee:           # a failed buy pays the same fee as a landed one (tips revert)
                        self.fail_buy_fee = o["fee"]
                        for S2 in self.sessions:
                            for t2 in S2.reg:
                                if t2["res"] in ("guard", "lighthouse", "failed"):
                                    self._reg_update(S2, t2)
        elif e == "buy_failed":
            if tr["failed"] is None:
                v = o.get("variant") or {}
                tr["failed"] = dict(t=o.get("t"), sig=o.get("sig"), slot=o.get("slot"),
                                    via="+".join(v.get("paths") or []) if isinstance(v, dict) else "")
        elif e == "land_poll":
            if tr["poll_err"] is None and o.get("err"):
                tr["poll_err"] = json.dumps(o.get("err"))
        elif e == "timing":
            t2 = next((x for x in cands if x["timing"] is None), None)
            if t2 is not None:
                t2["timing"] = {k: o.get(k) for k in ("reaction_ms", "exec_lag_ms", "fire_to_seen_ms")}
        elif e == "exit":
            if tr["exit"] is None:
                tr["exit"] = dict(why=o.get("why"), slots=o.get("slots_held"), t=o.get("t"))
        elif e == "sell_land":
            tr["sells"].append(dict(sig=o.get("sig"), t=o.get("t"), sol=o.get("sol"), fee=o.get("fee")))
        elif e == "close":
            sl = o.get("sell_land") or []
            land = o.get("land") or []
            tr["close"] = dict(result=o.get("result"), why=o.get("exit_why"), held_s=o.get("held_s"), err=json.dumps(o.get("err")) if o.get("err") else "",
                               sell_sigs=[x[0] for x in (o.get("sell_sigs") or []) if isinstance(x, list) and len(x) > 1 and x[1]],
                               t=(sl[2] if len(sl) > 2 else None) or (land[2] if len(land) > 2 else None) or S.cur_t,
                               sol_out=sl[3] if len(sl) > 3 else None, exit_slot=o.get("exit_slot"), land_slot=land[0] if land else None,
                               curve=o.get("curve_pnl"), spend=o.get("spend"), score=o.get("score"))
        self._reg_update(S, tr)
        self._reconcile(S, m)

    def _classify(self, tr):
        c = tr["close"] or {}
        res = c.get("result")
        if tr["land"] or res == "sold":
            return "filled"
        err = c.get("err") or tr["poll_err"] or ""
        if res == "buy_failed" or tr["failed"]:
            if "6042" in err:
                return "guard"
            return "lighthouse" if "6001" in err else "failed"
        if res is None:
            return "open"
        if res in ("not_landed", "buy_not_landed", "dropped", "expired"):
            return "not landed"
        return res

    def _book(self, S, tr, amount, t):
        """put a trade's P&L change into its session's minute buckets (the cumulative P&L line)"""
        if tr["bm"] is None:
            tr["bm"] = (t if time_ok(t) else (S.cur_t or self.cur_t)) // 60_000_000_000
        d = (amount or 0) - tr["booked"]
        if d:
            S.buckets[tr["bm"]] += d
            tr["booked"] = amount or 0

    def _reg_update(self, S, tr):
        tr["res"] = self._classify(tr)
        if tr["res"] in ("guard", "lighthouse", "failed"):
            tr["pnl"] = -self.fail_buy_fee
            tr["src"] = "fee"
            self._book(S, tr, tr["pnl"], (tr["failed"] or {}).get("t") or tr["t"])
        elif tr["res"] == "filled" and tr["src"] != "tx":
            c = tr["close"]
            if c and c.get("result") == "sold":
                # until the engine's REALIZED line (chain txs) arrives: the feed's estimate (sell proceeds - spend), as the engine's fallback
                if c.get("sol_out") is not None and tr["spend"]:
                    tr["pnl"] = c["sol_out"] - tr["spend"]
                    tr["src"] = "est"
                    self._book(S, tr, tr["pnl"], c.get("t"))

    def _reconcile(self, S, mint):
        q = S.real_q.get(mint)
        if not q:
            return
        for tr in S.by_mint.get(mint, ()):
            if not q:
                break
            if tr["res"] == "filled" and tr["src"] != "tx":
                tr["pnl"] = q.popleft()
                tr["src"] = "tx"
                self._book(S, tr, tr["pnl"], (tr["close"] or {}).get("t") or tr["t"])

    # ---------------------------------------------------------------- pre-send live (the report's ps_session)
    def _ps(self, S, e, o):
        w = o.get("w")
        mint = o.get("mint") or ""
        key = (w, mint)
        if e == "presend_live_arm":
            S.ps_armed += 1
            S.ps_open.add(w)
            trig = o.get("trig") or {}
            self.arm_info[(S.idx, w)] = (trig.get("pct"), trig.get("sol"))
            if len(self.arm_info) > 3000:
                self.arm_info.popitem(last=False)
            self._quiet_rec(S, o)
        elif e == "presend_live_skip":
            why = o.get("why") or "?"
            S.ps_skips[why] += 1
            if why == "quiet" or o.get("quiet_skip"):
                S.q_skips += 1
            self._quiet_rec(S, o)
        elif e == "presend_live_disarm":
            S.ps_open.discard(w)
            why = o.get("why") or "?"
            S.ps_disarms[why] += 1
            if why == "quiet":
                S.q_stops += 1
        elif e == "presend_live_fill":
            S.ps_fills += 1
            tr = S.ps_pos.get(key)
            if tr is not None and tr["close"] is None:
                tr["nfills"] += 1                          # a second attempt of the same window filled: merged into the position
                if o.get("sig"):
                    tr["buy_sigs"].append(o["sig"])
                return
            pct, wsol = self.arm_info.get((S.idx, w), (None, None))
            psl = S.rs.get("psl") or {}
            tr = dict(kind="PS", s=S.idx, w=w, t=o.get("t") or S.cur_t, mint=mint, spend=psl.get("spend") or S.psl.get("spend"),
                      sol_in=o.get("sol_in"), client=o.get("client") or "?", path=o.get("path") or "", ms=o.get("ms_send_to_rx"),
                      after=o.get("slots_after_trigger"), nfills=1, buy_sigs=[o.get("sig")] if o.get("sig") else [], sell_sigs=[],
                      exit=None, slots=None, held_s=None, close=None, pnl=None, rent=None, res="open", src=None, trig_pct=pct,
                      trig_sol=wsol, booked=0, bm=None, fee=o.get("fee"), tip=o.get("tip"), late=bool(o.get("after_exit")))
            S.ps_pos[key] = tr
            S.ps_bykey[key].append(tr)
            S.ps_list.append(tr)
            self.trades.append(tr)
            if o.get("ms_send_to_rx") is not None:
                S.ps_land_ms.append(o["ms_send_to_rx"])
            if o.get("slots_after_trigger") is not None:
                S.ps_after.append(o["slots_after_trigger"])
        elif e == "presend_live_exit":
            tr = S.ps_pos.get(key)
            if tr is not None and tr["exit"] is None:
                tr["exit"] = o.get("why")
                tr["slots"] = o.get("slots_held")
                tr["value"] = o.get("value")
        elif e == "presend_live_close":
            tr = S.ps_pos.get(key)
            if tr is None:
                tr = self._ps_bare(S, w, mint, o.get("spend"))
                S.ps_pos[key] = tr
                S.ps_bykey[key].append(tr)
            sl = o.get("sell_land") or []
            land = o.get("land") or []
            tr["close"] = dict(t=(sl[2] if len(sl) > 2 else None) or (land[2] if len(land) > 2 else None) or S.cur_t,
                               curve=o.get("curve_pnl"), merged=o.get("merged") or 0, late=o.get("late") or 0)
            tr["exit"] = o.get("exit_why") or tr["exit"]
            tr["held_s"] = o.get("held_s")
            tr["res"] = o.get("result") or "?"
            if o.get("buy_sigs"):
                tr["buy_sigs"] = [x for x in o["buy_sigs"] if isinstance(x, str)]
            tr["sell_sigs"] = [x[0] for x in (o.get("sell_sigs") or []) if isinstance(x, list) and x and x[0]]
            tr["client"] = o.get("client") or tr["client"]
            tr["path"] = o.get("path") or tr["path"]
            if o.get("spend"):
                tr["spend"] = o["spend"]
            if tr["slots"] is None and o.get("exit_slot") and land:
                tr["slots"] = o["exit_slot"] - land[0]
        elif e == "presend_live_realized":
            # the oldest closed position of this window without its P&L (the report matches them in order), else any without
            cands = [x for x in S.ps_bykey.get(key, ()) if x["src"] != "tx"]
            tr = next((x for x in cands if x["close"] is not None), None) or (cands[0] if cands else None)
            if tr is None:
                tr = self._ps_bare(S, w, mint, None)
            pnl = o.get("pnl")
            tr["pnl"] = pnl
            tr["src"] = "tx" if o.get("src") in (None, "tx") else str(o.get("src"))
            S.ps_nreal += 1
            if pnl is not None:
                S.ps_realized += pnl
                if pnl > 0:
                    S.ps_wins += 1
                self._book(S, tr, pnl + (tr["rent"] or 0), (tr["close"] or {}).get("t") or tr["t"])
        elif e == "presend_live_ata_close":
            if o.get("ok", True) is False:
                S.ps_ata_fail += 1
                return
            d = o.get("delta") or 0
            S.ps_rent += d
            tr = next((x for x in S.ps_list if x["mint"] == mint and x["rent"] is None and x["close"] is not None), None) or \
                next((x for x in reversed(S.ps_list) if x["mint"] == mint and x["rent"] is None), None)
            if tr is not None:
                tr["rent"] = d
                self._book(S, tr, (tr["pnl"] or 0) + d, (tr["close"] or {}).get("t") or tr["t"])
            else:
                S.buckets[(S.cur_t or self.cur_t) // 60_000_000_000] += d
        elif e == "presend_live_stop":
            S.ps_stop.append(dict(why=o.get("why"), t=o.get("t"), fees=o.get("fees"), fills=o.get("fills")))
        elif e == "presend_live_end_check":
            S.ps_endchk[o.get("action") or "?"] += 1
        elif e == "presend_live_held":
            S.ps_held += 1
        elif e == "presend_live_quiet_preload":
            S.q_preload = dict(ok=o.get("ok"), secs=o.get("secs"), covered_h=o.get("covered_h"), on_at=o.get("arm_rule_on_at"), t=o.get("t"))

    def _ps_bare(self, S, w, mint, spend):
        psl = S.rs.get("psl") or {}
        tr = dict(kind="PS", s=S.idx, w=w, t=S.cur_t, mint=mint, spend=spend or psl.get("spend"), sol_in=None, client="?", path="", ms=None,
                  after=None, nfills=0, buy_sigs=[], sell_sigs=[], exit=None, slots=None, held_s=None, close=None, pnl=None, rent=None,
                  res="?", src=None, trig_pct=None, trig_sol=None, booked=0, bm=None, fee=None, tip=None, late=False)
        S.ps_list.append(tr)
        self.trades.append(tr)
        return tr

    def _quiet_rec(self, S, o):
        q = o.get("quiet")
        if isinstance(q, dict):
            if q.get("would_skip"):
                S.q_would += 1
            if "rule_on" in q:
                S.q_rule_on = bool(q.get("rule_on"))

    # ---------------------------------------------------------------- log
    RX_REAL = re.compile(r"^\s*REALIZED mint=(\S+) pnl=([-+]?[\d.]+) SOL source=(\S+)(?: run_realized=([-+]?[\d.]+) SOL)?")
    RX_START = re.compile(r"START BALANCE ([\d.]+) SOL; kill switch below ([\d.]+) SOL")
    RX_DONE = re.compile(r"fired (\d+) closed (\d+) landed buys (\d+) realized ([-+]?[\d.]+) SOL")
    RX_KILL = re.compile(r"DIP KILL-SWITCH: run PnL ([-+]?[\d.]+) SOL")
    RX_RT = re.compile(r"RUNTIME lag 60s .*?n=(\d+) p50=([\d.]+)ms p99=([\d.]+)ms max=([\d.]+)ms")
    RX_RPC = re.compile(r"RPC-LAT 60s (\S+) (\S+): n=(\d+) p50=([\d.]+)ms p90=([\d.]+)ms p99=([\d.]+)ms max=([\d.]+)ms timeouts/transport=(\d+)")
    RX_KA = re.compile(r"keepalive: (\S+) keep-alive: (.*)")
    RX_SP = re.compile(r"SEND-PATH (\S+) UNHEALTHY")
    RX_PSFEE = re.compile(r"failed-attempt fees ([\d.]+) ?/ ?([\d.]+)")
    RX_STOPPED = re.compile(r"PRESEND LIVE STOPPED \((\w+)\)")
    RX_FILLS = re.compile(r"fills (\d+) ?/ ?(\d+)")
    RX_ENDCHK = re.compile(r"END CHECK: (\d+) mint\(s\) read at confirmed: (\d+) sold now, (\d+) empty account\(s\) closed, (\d+) held / (\d+) unreadable")
    RX_PSREAL = re.compile(r"PRESEND LIVE REALIZED (\S+) ([-+]?[\d.]+) SOL")
    RX_SHADOW = re.compile(r"PRESEND shadow: .*?fills (\d+)/(\d+)/(\d+) exits .*?gross ([-+]?[\d.]+)/([-+]?[\d.]+)/([-+]?[\d.]+) SOL "
                           r"net\([^)]*\) ([-+]?[\d.]+)/([-+]?[\d.]+)/([-+]?[\d.]+)")
    RX_ST_REG = re.compile(r"fired (\d+) closed (\d+) open (\d+) slot \d+ skipped (\{[^}]*\})")
    RX_ST_PS = re.compile(r"PRESEND LIVE( DRY)?(?: STOPPED \((\w+)\))?: triggers (\d+) armed (\d+) \(now (\d+)\)")
    RX_ST_Q = re.compile(r"QUIET: skips (\d+) \(would-skip in the warm-up (\d+)\) stops (\d+) \| arm rule (.*?) \| signals")
    RX_ST_QPRE = re.compile(r"\| preload (running|done \(([\d.]+) s, ([\d.]+) h\)|FAILED)")
    RX_HHMM = re.compile(r"(\d{1,2}):(\d{2}) PKT")
    IMPORTANT = ("PRESEND LIVE FILL", "PRESEND LIVE EXIT", "PRESEND LIVE REALIZED", "REALIZED mint=", "DIP FIRE", "DIP BUY", "DIP EXIT",
                 "KILL", "SIGNAL", "STOPPED", "END CHECK", "QUIET", "START BALANCE", "DIP LIVE |", "=== DIP DONE", "Error", "panicked",
                 "UNHEALTHY", "UNSOLD", "SELL-FAIL", "SELL-GIVE", "SELL-STUCK", "refused", "DIP PRESEND LIVE")

    def feed_log(self, lines):
        for raw in lines:
            self.llines += 1
            try:
                s = raw.decode("utf-8", "replace").rstrip("\r")
                self._log_line(s)
            except Exception:
                self.bad += 1
        self.version += 1


    def _log_line(self, s):
        st = s.strip()
        if not st:
            return
        short_line = clean(st[:1000])
        self.log_ring.append(short_line)
        if any(k in st for k in self.IMPORTANT) and not st.startswith("DIP status"):
            self.log_imp.append(short_line)
        c0 = st[0]
        # ---- engine start / session boundaries
        if st.startswith("WARNING: date >=") or (st.startswith("snipe_engine: payer") and not self._recent_start):
            self.engine_starts += 1
            self.seg_live = False
            self.lpend = {}
            self._recent_start = True
            self._seg_lines = 0
            return
        self._seg_lines = getattr(self, "_seg_lines", 0) + 1
        if self._seg_lines > 5:
            self._recent_start = False
        if st.startswith("DIP LIVE |"):
            self.lsess += 1
            self.seg_live = True
            S = self.lcur()
            S.cfg.update(self.lpend)
            self.lpend = {}
            S.live = self._parse_live(st)
            return
        tgt = self.lcur().cfg if self.seg_live else self.lpend
        S = self.lcur()
        if c0 == "R":
            if st.startswith("RUNTIME lag"):
                m = self.RX_RT.search(st)
                if m:
                    self.runtime = (float(m.group(2)), float(m.group(3)), float(m.group(4)))
                    self.runtime_worst = max(self.runtime_worst, self.runtime[1])
                self.log_min += 1
                self._prune()
                return
            if st.startswith("RPC-LAT"):
                m = self.RX_RPC.search(st)
                if m:
                    k = (m.group(1), m.group(2))
                    r = self.rpc.get(k) or dict(to=0)
                    r.update(n=int(m.group(3)), p50=float(m.group(4)), p99=float(m.group(6)), mx=float(m.group(7)), min=self.log_min)
                    r["to"] += int(m.group(8))
                    r["to_last"] = int(m.group(8))
                    self.rpc[k] = r
                return
            if st.startswith("REALIZED mint="):
                m = self.RX_REAL.search(st)
                if m:
                    pnl = int(round(float(m.group(2)) * LAM))
                    if m.group(4):
                        S.engine_realized = int(round(float(m.group(4)) * LAM))
                    S2 = self.sess(self.lsess)
                    S2.real_q[m.group(1)].append(pnl)
                    self._reconcile(S2, m.group(1))
                return
        if c0 == "D" and st.startswith("DIP status"):
            self._status_line(S, st)
            return
        if c0 == "P":
            if st.startswith("PRESEND LIVE"):
                self._ps_log(S, st)
                return
            if st.startswith("POLL-RPC-ERROR"):
                self.poll_err[self.log_min] += 1
                self.poll_err_total += 1
                return
        if c0 == "k" and st.startswith("keepalive:"):
            m = self.RX_KA.match(st)
            if m:
                msg = m.group(2).lower()
                kind = "refused" if "refused" in msg else ("timeout" if ("timed out" in msg or "timeout" in msg or "deadline" in msg)
                                                           else ("error" if ("error" in msg or "fail" in msg) else None))
                if kind:
                    self._path_err(m.group(1), kind)
            return
        if c0 == "S":
            if st.startswith("SEND-PATH"):
                m = self.RX_SP.search(st)
                if m:
                    self._path_err(m.group(1), "unhealthy")
                return
            if st.startswith("START BALANCE"):
                m = self.RX_START.search(st)
                if m:
                    S.start_bal = int(round(float(m.group(1)) * LAM))
                    S.kill_level = int(round(float(m.group(2)) * LAM))
                return
            if st.startswith("SIGNAL"):
                S.signal = st.split(":")[0].replace("SIGNAL ", "")
                return
        if c0 == "D":
            if st.startswith("DIP PRESEND LIVE QUIET"):
                S.quiet.update(self._parse_quiet(S, st))
                return
            if st.startswith("DIP PRESEND LIVE"):
                S.psl = self._parse_psl(st)
                return
            if st.startswith("DIP KILL-SWITCH"):
                m = self.RX_KILL.search(st)
                S.kill = float(m.group(1)) if m else True
                return
            if st.startswith("DIP PRESEND SHADOW"):
                tgt["shadow"] = True
                return
            if st.startswith("DIP M2"):
                tgt["m2"] = "gate" if " GATE" in st else ("shadow" if "SHADOW" in st.upper() else "on")
                return
            if st.startswith("DIP dev list"):
                m = re.search(r"(\d+) wallet\(s\).*?spend ([\d.]+) SOL", st)
                tgt["dev"] = (int(m.group(1)), float(m.group(2))) if m else True
                return
            if st.startswith("DIP near-leader gate"):
                m = re.search(r"(\d+) leaders", st)
                tgt["near"] = int(m.group(1)) if m else True
                return
            if st.startswith("DIP SKIP CLIENTS"):
                tgt["skip_clients"] = st.split("leader is", 1)[-1].strip() if "leader is" in st else "on"
                return
            if st.startswith("DIP BUY") or st.startswith("DIP FIRE"):
                return
        if c0 == "=":
            if st.startswith("=== DIP DONE"):
                m = self.RX_DONE.search(st)
                S.done = dict(fired=int(m.group(1)), closed=int(m.group(2)), landed=int(m.group(3)),
                              realized=int(round(float(m.group(4)) * LAM))) if m else {"line": True}
                if m:
                    S.engine_realized = S.done["realized"]
                return
            if st.startswith("=== DIP PRESEND:"):
                m = self.RX_SHADOW.search(st)
                if m:
                    S.paper = (int(m.group(3)), float(m.group(6)), float(m.group(9)))
                return
            if st.startswith("=== DIP PRESEND LIVE"):
                m = self.RX_PSFEE.search(st)
                if m:
                    S.log_ps_fees = max(S.log_ps_fees, int(round(float(m.group(1)) * LAM)))
                return
        if c0 == "N" and st.startswith("NONCE-FANOUT"):
            m = re.search(r"ON: (\d+)", st)
            tgt["nonce"] = int(m.group(1)) if m else (0 if "OFF" in st else True)
            return
        if c0 == "s":
            if st.startswith("snipe_engine: ROUTE"):
                m = re.match(r"snipe_engine: ROUTE (\S+)\s+-> (.+)$", st)
                if m:
                    tgt.setdefault("routes", {})[m.group(1)] = tuple(x.strip() for x in m.group(2).split("+") if x.strip())
                return
            if st.startswith("snipe_engine: SELL FAN-OUT"):
                m = re.search(r"goes to (\S+) AND (\S+?)[ (]", st)
                tgt["sellfan"] = m.group(2) if m else True
                return
        if c0 == "Q" and st.startswith("QUIET preload"):
            S.quiet["preload"] = "done" if "preload done" in st else ("failed" if "FAILED" in st else S.quiet.get("preload"))
            m = re.search(r"([\d.]+) h of history", st)
            if m:
                S.quiet["preload_h"] = float(m.group(1))
            if "arm rule on now" in st:
                S.quiet["rule_state"] = "on"
            else:
                m = re.search(r"(?:arm rule on at|on at) (\d{1,2}):(\d{2}) PKT", st)
                if m:
                    S.quiet["on_hhmm"] = (int(m.group(1)), int(m.group(2)))
            return
        if c0 == "E" and st.startswith("Error:"):
            if not self.seg_live:
                self.refused.append(st[:200])
            else:
                S.errors.append(st[:200])
            return
        if "panicked" in st:
            self.panics.append(st[:200])

    def _ps_log(self, S, st):
        m = self.RX_PSFEE.search(st)
        if m:
            S.log_ps_fees = max(S.log_ps_fees, int(round(float(m.group(1)) * LAM)))
        if st.startswith("PRESEND LIVE STOPPED"):
            m = self.RX_STOPPED.search(st)
            f = self.RX_FILLS.search(st)
            S.ps_stopped = (m.group(1) if m else "?", int(f.group(1)) if f else None, int(f.group(2)) if f else None)
        elif st.startswith("PRESEND LIVE END CHECK"):
            m = self.RX_ENDCHK.search(st)
            if m:
                S.end_check = tuple(int(x) for x in m.groups())
        elif st.startswith("PRESEND LIVE REALIZED"):
            m = self.RX_PSREAL.search(st)
            if m:
                S.log_ps_real.append(int(round(float(m.group(2)) * LAM)))

    def _status_line(self, S, st):
        d = {}
        m = self.RX_ST_REG.search(st)
        if m:
            d["fired"], d["closed"], d["open"] = int(m.group(1)), int(m.group(2)), int(m.group(3))
            try:
                d["skipped"] = json.loads(m.group(4))
            except ValueError:
                pass
        m = self.RX_ST_PS.search(st)
        if m:
            d["ps_dry"] = bool(m.group(1))
            d["ps_stopped"] = m.group(2)
            d["ps_triggers"], d["ps_armed"], d["ps_now"] = int(m.group(3)), int(m.group(4)), int(m.group(5))
            rest = st[m.end():]
            f = self.RX_FILLS.search(rest)
            if f:
                d["ps_fills"], d["ps_cap"] = int(f.group(1)), int(f.group(2))
            fe = self.RX_PSFEE.search(rest)
            if fe:
                d["ps_fee"], d["ps_budget"] = float(fe.group(1)), float(fe.group(2))
                S.log_ps_fees = max(S.log_ps_fees, int(round(float(fe.group(1)) * LAM)))
        m = self.RX_SHADOW.search(st)
        if m:
            S.paper = (int(m.group(3)), float(m.group(6)), float(m.group(9)))
        m = self.RX_ST_Q.search(st)
        if m:
            d["q_skips"], d["q_would"], d["q_stops"] = int(m.group(1)), int(m.group(2)), int(m.group(3))
            rule = m.group(4)
            d["q_rule"] = rule
            S.quiet["rule_state"] = "on" if rule.startswith("on") else ("off" if rule == "off" else "warm-up")
            h = self.RX_HHMM.search(rule)
            if h:
                S.quiet["on_hhmm"] = (int(h.group(1)), int(h.group(2)))
            p = self.RX_ST_QPRE.search(st)
            if p:
                S.quiet["preload"] = "running" if p.group(1) == "running" else ("done" if p.group(1).startswith("done") else "failed")
                if p.group(3):
                    S.quiet["preload_h"] = float(p.group(3))
        d["min"] = self.log_min
        S.status = d

    def _path_err(self, path, kind):
        self.path_err[path][self.log_min] += 1
        self.path_kind[path] = kind
        self.path_total[path] += 1

    def _prune(self):
        lim = self.log_min - 70
        if lim <= 0:
            return
        for k in [k for k in self.poll_err if k < lim]:
            del self.poll_err[k]
        for p, c in self.path_err.items():
            for k in [k for k in c if k < lim]:
                del c[k]

    _recent_start = False

    @staticmethod
    def _parse_live(st):
        d = {}
        for part in st.split(" | ")[1:]:
            p = part.strip()
            m = re.match(r"model (\S+) tier (\S+)", p)
            if m:
                d["model"], d["tier"] = m.group(1), m.group(2)
                continue
            m = re.match(r"exit TP (\S+) / SL -?([\d.]+)% / (\d+) slots", p)
            if m:
                d["tp"], d["sl"], d["hold"] = m.group(1), float(m.group(2)), int(m.group(3))
                continue
            m = re.match(r"guard x([\d.]+)", p)
            if m:
                d["guard"] = float(m.group(1))
                continue
            m = re.match(r"spend ([\d.]+) SOL", p)
            if m:
                d["spend"] = int(round(float(m.group(1)) * LAM))
                continue
            m = re.match(r"max buys (\d+)", p)
            if m:
                d["max_buys"] = int(m.group(1))
                continue
            m = re.match(r"loss cap ([\d.]+) SOL", p)
            if m:
                d["loss_cap"] = int(round(float(m.group(1)) * LAM))
                continue
            m = re.match(r"(\d+) min$", p)
            if m:
                d["minutes"] = int(m.group(1))
        return d

    @staticmethod
    def _parse_psl(st):
        d = {"dry": st.startswith("DIP PRESEND LIVE DRY") or " DRY" in st.split("|")[0]}
        for k, rx, f in (("k", r"(\d+) attempts per slot", int), ("spend", r"([\d.]+) SOL, limit", lambda x: int(round(float(x) * LAM))),
                         ("limit", r"price x ([\d.]+)", float), ("fail_fee", r"a failed attempt (\d+) lamports", int),
                         ("routes", r"routes (\S+)", lambda x: re.sub(r"\(.*?\)", "", x)), ("max_fills", r"caps: (\d+) fills", int),
                         ("fee_budget", r"caps: \d+ fills, fees ([\d.]+) SOL", lambda x: int(round(float(x) * LAM))),
                         ("exit_slots", r"exit (\d+) slots", int), ("tp", r"TP \+?([\d.]+)%", float), ("sl", r"SL -?([\d.]+)%", float)):
            m = re.search(rx, st)
            if m:
                try:
                    d[k] = f(m.group(1))
                except ValueError:
                    pass
        return d

    def _parse_quiet(self, S, st):
        d = {"line": True}
        m = re.search(r"stop at trigger \+ (\d+) slots with < (\d+) other trades", st)
        d["stop"] = f"{m.group(1)}:{m.group(2)}" if m else ("off" if re.search(r"stop off", st) else None)
        m = re.search(r"\| skip (on|off)", st)
        d["skip"] = (m.group(1) == "on") if m else None
        m = re.search(r"arm rule from (\d{1,2}):(\d{2}) PKT \(warm-up ([\d.]+) min\)", st)
        if m:
            d["on_hhmm"] = (int(m.group(1)), int(m.group(2)))
            d["warmup_min"] = float(m.group(3))
        if "RUNNING" in st and "preload" in st:
            d["preload"] = "running"
        elif "preload FAILED" in st:
            d["preload"] = "failed"
        return d

    # ---------------------------------------------------------------- end-of-file partial lines (a writer that paused)
    def reset(self):
        self.__init__(self.fail_buy_fee if self.fail_buy_fee_src == "cmdline" else None, self.log_ring.maxlen)


# ------------------------------------------------------------------------------------------------------------------ source
RUN_RX = re.compile(r"^dip_(ams_)?r(\d+)\.jsonl$")


def run_info(path):
    """(region, run) from a run file name: dip_ams_rN -> AMS, dip_rN -> FRA"""
    m = RUN_RX.match(os.path.basename(path or ""))
    if not m:
        return None, None
    return ("AMS" if m.group(1) else "FRA"), int(m.group(2))


class Source:
    """the run's two files and the model they feed"""

    def __init__(self, jsonl, log=None, fail_buy_fee=None, log_keep=3000):
        self.jsonl = jsonl
        self.log = log if log is not None else (jsonl[:-6] + ".log" if jsonl.endswith(".jsonl") else jsonl + ".log")
        self.region, self.run = run_info(jsonl)
        self.fail_buy_fee = fail_buy_fee
        self.log_keep = log_keep
        self.model = Model(fail_buy_fee, log_keep)
        self.tj = Tail(self.jsonl)
        self.tl = Tail(self.log)
        self.loaded = False
        self.resets = 0
        self.t_last_growth = time.time()

    def total_bytes(self):
        a = self.tj.stat()
        b = self.tl.stat()
        return (a.st_size if a else 0) + (b.st_size if b else 0)

    def done_bytes(self):
        return self.tj.off + self.tl.off

    def step(self, max_bytes):
        """read up to max_bytes from each file; returns bytes read"""
        n0 = self.done_bytes()
        lj = self.tj.read(max_bytes)
        if self.tj.reset or self.tl.reset:
            return self._reset()
        if lj:
            self.model.feed_jsonl(lj)
        ll = self.tl.read(max_bytes)
        if self.tj.reset or self.tl.reset:
            return self._reset()
        if ll:
            self.model.feed_log(ll)
        n = self.done_bytes() - n0
        if n:
            self.t_last_growth = time.time()
        elif self.tj.buf and time.time() - self.t_last_growth > 3:
            b = self.tj.flush_partial_json()      # a record whose newline never came (an engine killed mid-write)
            if b:
                self.model.feed_jsonl([b])
        return n

    def _reset(self):
        self.resets += 1
        self.tj = Tail(self.jsonl)
        self.tl = Tail(self.log)
        self.model = Model(self.fail_buy_fee, self.log_keep)
        self.loaded = False
        return 0

    def load_all(self, chunk=1 << 20, duty=0.0, progress=None):
        """read both files to their end in chunks; duty > 0 sleeps that fraction of each chunk's time (yield the CPU)"""
        while True:
            t0 = time.time()
            n = self.step(chunk)
            if progress:
                progress(self)
            if not n and not self.tj.pending() and not self.tl.pending():
                break
            if duty > 0:
                time.sleep(max(0.001, (time.time() - t0) * duty))
        self.loaded = True


def session_totals(S):
    """one session's figures (lamports), the report's definitions"""
    reg = S.reg
    fills = [t for t in reg if t["res"] == "filled"]
    fail = [t for t in reg if t["res"] in ("guard", "lighthouse", "failed")]
    return dict(
        ps_fills=S.ps_fills, ps_wins=S.ps_wins, ps_real=S.ps_realized, ps_rent=S.ps_rent, ps_fees=S.ps_fees(), ps_fees_counted=S.ps_fee_cnt,
        ps_net=S.ps_net(), ps_sent=S.ps_sent, reg_fires=len(reg), reg_fills=len(fills),
        reg_wins=sum(1 for t in fills if (t["pnl"] or 0) > 0), reg_guard=sum(1 for t in reg if t["res"] == "guard"),
        reg_lighthouse=sum(1 for t in reg if t["res"] == "lighthouse"), reg_other=sum(1 for t in reg if t["res"] == "failed"),
        reg_fill_pnl=sum(t["pnl"] or 0 for t in fills), reg_fail_pnl=sum(t["pnl"] or 0 for t in fail), reg_total=S.reg_total(),
        total=S.total(), est=sum(1 for t in fills if t["src"] != "tx"))


def run_totals(model):
    out = collections.Counter()
    for S in model.sessions:
        for k, v in session_totals(S).items():
            out[k] += v
    return dict(out)


# ------------------------------------------------------------------------------------------------------------------ engine
SAFE_FLAGS = {"--minutes", "--max-loss-sol", "--cu-limit", "--cu-price-micro", "--spend-lamports", "--dip-tier", "--dip-tp", "--dip-sl",
              "--dip-hold-slots", "--dip-guard", "--dip-m2-mode", "--presend-live-size-sol", "--presend-live-k", "--presend-live-max-fills",
              "--presend-live-fee-budget-sol", "--presend-live-routes", "--presend-live-quiet-stop", "--presend-live-quiet-skip",
              "--presend-live-quiet-warmup-min", "--sell-fanout", "--route-by-client", "--skip-clients", "--max-buys", "--max-inflight"}
SAFE_SWITCHES = {"--presend-live", "--presend-live-dry", "--presend-shadow", "--nonce-fanout", "--dip-near-leaders",
                 "--presend-live-quiet-preload", "--dip-dev-list", "--dip-m2", "--live"}


class Engine:
    """the engine process of this run, found by its --dip-log in /proc/*/cmdline (read-only). Only a fixed set of flags is
    kept (numbers, names); never paths, URLs or keys."""

    def __init__(self, jsonl=None, enabled=True):
        self.target = os.path.realpath(jsonl) if jsonl else None
        self.enabled = enabled and os.path.isdir("/proc")
        self.pid = None
        self.flags = {}
        self.build = None
        self.seen = False
        self.gone_at = None
        self.cpu = None
        self.rss = None
        self.threads = None
        self.start = None
        self._last = None
        self._scan_t = 0
        self.hz = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
        try:
            self.btime = next(int(l.split()[1]) for l in open("/proc/stat") if l.startswith("btime"))
        except Exception:
            self.btime = None

    @staticmethod
    def _dip_log(pid):
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                raw = f.read()
        except OSError:
            return None, None
        if b"--dip-log" not in raw:
            return None, None
        args = [a.decode("utf-8", "replace") for a in raw.split(b"\0") if a]
        try:
            p = args[args.index("--dip-log") + 1]
        except (ValueError, IndexError):
            return None, None
        if not os.path.isabs(p):
            try:
                p = os.path.join(os.readlink(f"/proc/{pid}/cwd"), p)
            except OSError:
                pass
        return os.path.realpath(p), args

    @classmethod
    def find_all(cls):
        out = []
        me = os.getpid()
        try:
            pids = [int(d) for d in os.listdir("/proc") if d.isdigit()]
        except OSError:
            return out
        for pid in pids:
            if pid == me:
                continue
            p, args = cls._dip_log(pid)
            if p:
                out.append((pid, p, args))
        return out

    def scan(self, force=False):
        if not self.enabled or not self.target:
            return
        now = time.time()
        if not force and now - self._scan_t < 10:
            return
        self._scan_t = now
        for pid, p, args in self.find_all():
            if p == self.target:
                self._adopt(pid, args)
                return

    def _adopt(self, pid, args):
        self.pid = pid
        self.seen = True
        self.gone_at = None
        self._last = None
        exe = os.path.basename(args[0]) if args else ""
        m = re.search(r"(dip\d+)", exe)
        if not m:
            try:
                m = re.search(r"(dip\d+)", os.path.basename(os.readlink(f"/proc/{pid}/exe")))
            except OSError:
                m = None
        if not m:
            m = next((re.search(r"snipe_engine\w*?(dip\d+)", a) for a in args if "snipe_engine" in a), None)
        self.build = m.group(1) if m else (exe[:20] or None)
        fl = {}
        for i, a in enumerate(args):
            if a in SAFE_FLAGS and i + 1 < len(args):
                fl[a] = args[i + 1][:300]
            elif a in SAFE_SWITCHES:
                fl[a] = True
        self.flags = fl

    def sample(self):
        if not self.enabled:
            return
        if self.pid is None:
            self.scan()
            return
        try:
            with open(f"/proc/{self.pid}/stat") as f:
                rest = f.read().rsplit(")", 1)[1].split()
            with open(f"/proc/{self.pid}/statm") as f:
                rss_pages = int(f.read().split()[1])
        except (OSError, IndexError, ValueError):
            self.pid = None
            self.cpu = None
            self.gone_at = time.time()
            self.scan(force=True)
            return
        ticks = int(rest[11]) + int(rest[12])
        now = time.time()
        if self._last:
            dtw = now - self._last[0]
            if dtw > 0.2:
                self.cpu = (ticks - self._last[1]) / self.hz / dtw * 100
                self._last = (now, ticks)
        else:
            self._last = (now, ticks)
        self.threads = int(rest[17])
        self.rss = rss_pages * os.sysconf("SC_PAGE_SIZE")
        if self.btime:
            st = self.btime + int(rest[19]) / self.hz
            self.start = st if 0 < now - st < 90 * 86400 else None

    @property
    def alive(self):
        return self.pid is not None


# ------------------------------------------------------------------------------------------------------------------ price
class Price:
    """SOL/USD: Binance, else CoinGecko, every 60 s in a daemon thread (5 s timeouts); the last price cached in /tmp"""
    SOURCES = (("binance", "https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT", lambda d: float(d["price"])),
               ("coingecko", "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd", lambda d: float(d["solana"]["usd"])))

    def __init__(self, fixed=None, net=True, every=60.0):
        self.fixed = fixed
        self.usd = fixed
        self.t = time.time() if fixed else None
        self.src = "fixed" if fixed else None
        self.err = None
        self.every = every
        self.net = net and not fixed
        self.cache = f"/tmp/dipmon-solusd-{os.getuid() if hasattr(os, 'getuid') else 0}.json"
        self._ev = threading.Event()
        self._th = None
        if not fixed:
            self._load_cache()

    def _load_cache(self):
        try:
            with open(self.cache) as f:
                d = json.load(f)
            if 1 < float(d["usd"]) < 100000 and time.time() - float(d["t"]) < 12 * 3600:
                self.usd, self.t, self.src = float(d["usd"]), float(d["t"]), str(d.get("src", "cache"))[:12] + " (cache)"
        except Exception:
            pass

    def _save_cache(self):
        try:
            tmp = self.cache + f".{os.getpid()}"
            with open(tmp, "w") as f:
                json.dump({"usd": self.usd, "t": self.t, "src": self.src}, f)
            os.replace(tmp, self.cache)
        except Exception:
            pass

    def fetch_once(self, timeout=5.0):
        errs = []
        for name, url, parse in self.SOURCES:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "dipmon/" + VERSION, "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    p = parse(json.loads(r.read(65536)))
                if 1 < p < 100000:
                    self.usd, self.t, self.src, self.err = p, time.time(), name, None
                    self._save_cache()
                    return True
                errs.append(f"{name}: odd price {p}")
            except Exception as e:
                errs.append(f"{name}: {type(e).__name__}")
        self.err = "; ".join(errs)[:120]
        return False

    def start(self):
        if not self.net or self._th:
            return
        self._th = threading.Thread(target=self._loop, name="dipmon-price", daemon=True)
        self._th.start()

    def _loop(self):
        while True:
            self.fetch_once()
            self._ev.wait(self.every)
            self._ev.clear()

    def refresh(self):
        self._ev.set()

    def age(self):
        return None if self.t is None or self.fixed else time.time() - self.t


# ------------------------------------------------------------------------------------------------------------------ system
class SysInfo:
    def __init__(self, path):
        self.path = path
        self.disk = None
        self.load = None
        self.mem = None
        self.ncpu = os.cpu_count() or 1
        self.own_cpu = None
        self.own_rss = None
        self._own = None
        self._t = 0

    def sample(self, force=False):
        now = time.time()
        if not force and now - self._t < 5:
            return
        self._t = now
        try:
            st = os.statvfs(self.path)
            self.disk = (1 - st.f_bavail / st.f_blocks) * 100 if st.f_blocks else None
        except OSError:
            self.disk = None
        try:
            self.load = os.getloadavg()
        except OSError:
            self.load = None
        try:
            mi = {}
            with open("/proc/meminfo") as f:
                for l in f:
                    k, v = l.split(":", 1)
                    if k in ("MemTotal", "MemAvailable"):
                        mi[k] = int(v.split()[0]) * 1024
            self.mem = (mi["MemTotal"] - mi["MemAvailable"], mi["MemTotal"])
        except Exception:
            self.mem = None
        try:
            t = os.times()
            c = t.user + t.system
            if self._own:
                self.own_cpu = (c - self._own[1]) / max(1e-6, now - self._own[0]) * 100
            self._own = (now, c)
            with open("/proc/self/statm") as f:
                self.own_rss = int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
        except Exception:
            pass


def read_budget(path):
    try:
        with open(path) as f:
            d = json.load(f)
        return {"first_start": d.get("first_start"), "max_total_loss": d.get("max_total_loss")}
    except Exception:
        return None


# ------------------------------------------------------------------------------------------------------------------ view
class Ctx:
    """everything a view needs besides the model"""

    def __init__(self, src, engine, price, sysinfo, budget_path=None, now=None, assume_running=False):
        self.src = src
        self.engine = engine
        self.price = price
        self.sys = sysinfo
        self.budget_path = budget_path
        self.budget = None
        self._budget_t = 0
        self.fixed_now = now
        self.assume_running = assume_running

    def now(self):
        return self.fixed_now if self.fixed_now else time.time()

    def read_budget(self):
        if self.budget_path and time.time() - self._budget_t > 60:
            self._budget_t = time.time()
            self.budget = read_budget(self.budget_path)


def agg_ps(sessions):
    A = dict(active=False, fills=0, wins=0, nreal=0, real=0, rent=0, fees=0, fees_cnt=0, fees_eng=0, fee_n=0, net=0, sent=0, dry=0,
             res=collections.Counter(), armed=0, skips=collections.Counter(), disarms=collections.Counter(), exits={}, land_ms=[], after=[],
             best=None, worst=None, q_skips=0, q_stops=0, q_would=0, paper=False, paper_fills=0, paper_gross=0.0, paper_net=0.0,
             held=0, endchk=collections.Counter(), ata_fail=0, not_sold=0, open_pos=0, fee_each=collections.Counter(), stop_fees=0, closed=0)
    for S in sessions:
        if S.paper:
            A["paper"] = True
            A["paper_fills"] += S.paper[0]
            A["paper_gross"] += S.paper[1]
            A["paper_net"] += S.paper[2]
        if not S.ps_active():
            continue
        A["active"] = True
        for k, sk in (("fills", "ps_fills"), ("wins", "ps_wins"), ("nreal", "ps_nreal"), ("real", "ps_realized"), ("rent", "ps_rent"),
                      ("fees_cnt", "ps_fee_cnt"), ("fee_n", "ps_fee_n"), ("sent", "ps_sent"), ("dry", "ps_dry"), ("armed", "ps_armed"),
                      ("q_skips", "q_skips"), ("q_stops", "q_stops"), ("q_would", "q_would"), ("held", "ps_held"), ("ata_fail", "ps_ata_fail")):
            A[k] += getattr(S, sk)
        if not S.ps_rec:                                  # an old run: only the log's PRESEND LIVE lines
            A["fills"] += len(S.log_ps_real)
            A["real"] += sum(S.log_ps_real)
            A["wins"] += sum(1 for x in S.log_ps_real if x > 0)
            A["nreal"] += len(S.log_ps_real)
        A["fees"] += S.ps_fees() if S.ps_rec else S.log_ps_fees
        stop = max([s.get("fees") or 0 for s in S.ps_stop] or [0])
        A["fees_eng"] += max(S.log_ps_fees, stop)
        A["stop_fees"] += stop
        A["all_stopped"] = A.get("all_stopped", True) and bool(S.ps_stop)
        A["net"] += S.ps_net()
        A["res"].update(S.ps_res)
        A["skips"].update(S.ps_skips)
        A["disarms"].update(S.ps_disarms)
        A["endchk"].update(S.ps_endchk)
        A["fee_each"].update(S.ps_fee_each)
        A["land_ms"] += S.ps_land_ms
        A["after"] += S.ps_after
        for tr in S.ps_list:
            if tr["close"] is None and tr["pnl"] is None:
                A["open_pos"] += 1
                continue
            A["closed"] += 1
            if tr["res"] not in ("sold", "?", None) and tr["close"] is not None:
                A["not_sold"] += 1
            e = A["exits"].setdefault(tr["exit"] or "?", [0, 0, 0])
            e[0] += 1
            e[1] += 1 if (tr["pnl"] or 0) > 0 else 0
            e[2] += tr["pnl"] or 0
            if tr["pnl"] is not None:
                if A["best"] is None or tr["pnl"] > A["best"]["pnl"]:
                    A["best"] = tr
                if A["worst"] is None or tr["pnl"] < A["worst"]["pnl"]:
                    A["worst"] = tr
    return A


def agg_reg(sessions):
    R = dict(fires=0, fills=0, wins=0, guard=0, lighthouse=0, failed=0, notl=0, open=0, fill_pnl=0, fail_pnl=0, total=0, est=0, exits={},
             kinds={}, land_ms=[], same=0, open_list=[], skipped=collections.Counter(), picks=0, dumps=0, best=None, worst=None, fail_ms=[])
    for S in sessions:
        R["dumps"] += S.dumps
        R["picks"] += S.picks
        sk = (S.re or {}).get("skipped") or S.status.get("skipped") or {}
        if isinstance(sk, dict):
            R["skipped"].update({k: v for k, v in sk.items() if isinstance(v, int)})
        for tr in S.reg:
            R["fires"] += 1
            res = tr["res"]
            p = tr["pnl"]
            R["total"] += p or 0
            k = R["kinds"].setdefault(kind_of(tr["client"]), [0, 0, 0, 0])
            k[0] += 1
            k[3] += p or 0
            if res == "filled":
                R["fills"] += 1
                k[1] += 1
                R["fill_pnl"] += p or 0
                if (p or 0) > 0:
                    R["wins"] += 1
                    k[2] += 1
                if tr["src"] != "tx":
                    R["est"] += 1
                if tr["land"]:
                    if tr["land"].get("ms") is not None:
                        R["land_ms"].append(tr["land"]["ms"])
                    if tr["land"].get("blk") == 0:
                        R["same"] += 1
                if tr["close"] is None:
                    R["open"] += 1
                    R["open_list"].append(tr)
                else:
                    why = (tr["close"].get("why") or (tr["exit"] or {}).get("why") or "?")
                    e = R["exits"].setdefault(why, [0, 0, 0])
                    e[0] += 1
                    e[1] += 1 if (p or 0) > 0 else 0
                    e[2] += p or 0
                if p is not None:
                    if R["best"] is None or p > R["best"]["pnl"]:
                        R["best"] = tr
                    if R["worst"] is None or p < R["worst"]["pnl"]:
                        R["worst"] = tr
            elif res in ("guard", "lighthouse", "failed"):
                R[res] += 1
                R["fail_pnl"] += p or 0
                if tr["failed"] and tr["failed"].get("t") and tr["t_dump"]:
                    R["fail_ms"].append((tr["failed"]["t"] - tr["t_dump"]) / 1e6)
            elif res == "open":
                R["open"] += 1
                R["open_list"].append(tr)
            else:
                R["notl"] += 1
    return R


def hhmm_ns(base, hh, mm):
    """an HH:MM PKT clock time on or after (base - 1 h) -> ns"""
    if not base or not (0 <= int(hh) < 24 and 0 <= int(mm) < 60):
        return None
    d0 = dt.datetime.fromtimestamp(base / 1e9, PKT)
    x = d0.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
    if x < d0 - dt.timedelta(hours=1):
        x += dt.timedelta(days=1)
    return int(x.timestamp() * 1e9)


def resolve_on_at(S, model):
    q = S.quiet
    if S.q_preload and S.q_preload.get("on_at"):
        return S.q_preload["on_at"]
    if q.get("on_hhmm"):
        return hhmm_ns(S.t0 or model.cur_t, *q["on_hhmm"])
    rq = S.rs.get("quiet") or {}
    if rq.get("skip") and S.t0 and rq.get("warmup_min") is not None:
        return int(S.t0 + rq["warmup_min"] * 60e9)
    return None


def infer_build(S, engine):
    if engine is not None and engine.alive and engine.build:
        return engine.build, True
    if any(l for l in (S.quiet.get("state"),)):
        return "dip21", False
    if S.quiet.get("line") or S.rs.get("quiet"):
        return "dip20", False
    if S.ps_endchk or S.ps_rent or S.end_check:
        return "dip19", False
    if S.ps_rec:
        return "dip13+", False
    return "?", False


class V:
    pass


def build_view(ctx, scope=None):
    M = ctx.src.model
    now = ctx.now()
    v = V()
    v.now = now
    sessions = M.sessions or [Sess(0)]
    v.nsess = len(sessions)
    v.scope = scope if (scope is not None and scope < len(sessions)) else None
    sel = sessions if v.scope is None else [sessions[v.scope]]
    S = sessions[-1] if v.scope is None else sessions[v.scope]
    v.S = S
    v.cur = sessions[-1]
    v.region, v.run = ctx.src.region or "?", ctx.src.run
    eng = ctx.engine
    v.build, v.build_live = infer_build(v.cur, eng)
    v.price = ctx.price.usd if ctx.price else None
    v.price_age = ctx.price.age() if ctx.price else None
    v.price_src = ctx.price.src if ctx.price else None
    # ---- status
    cur = v.cur
    alive = (eng is not None and eng.alive) or ctx.assume_running
    jm, lm = ctx.src.tj.mtime, ctx.src.tl.mtime
    v.last_write = max([x for x in (jm, lm) if x] or [0]) or None
    v.write_age = (now - v.last_write) if v.last_write else None
    v.log_age = (now - lm) if lm else None
    v.jsonl_age = (now - jm) if jm else None
    t_first = min([x.t0 for x in sessions if x.t0] or [M.cur_t or 0]) or None
    v.t_first = t_first
    if not M.sessions or (not cur.t0 and not cur.live and not M.jlines):
        v.status = "WAITING"
    elif cur.ended():
        v.status = "ENDED"
    elif alive:
        planned_end = cur.t0 + (cur.minutes() or 0) * 60e9 if cur.t0 and cur.minutes() else None
        v.status = "STOPPING" if (cur.signal or cur.kill or (planned_end and now * 1e9 > planned_end)) else "RUNNING"
    elif (eng is not None and eng.seen) or (v.write_age is not None and v.write_age < 600):
        v.status = "ENGINE GONE"
    else:
        v.status = "NO END RECORD"
    v.running = v.status in ("RUNNING", "STOPPING")
    t_end = cur.t_end() or (cur.cur_t if cur.ended() else None)
    v.t_end = t_end
    now_ns = now * 1e9 if v.running or v.status == "WAITING" else (t_end or M.cur_t or now * 1e9)
    if v.status in ("ENGINE GONE", "NO END RECORD"):
        now_ns = M.cur_t or now_ns
    v.now_ns = now_ns
    s_t0 = S.t0 or t_first
    v.s_t0 = s_t0
    v.elapsed = (now_ns - (t_first if v.scope is None else s_t0)) / 1e9 if (t_first and s_t0) else None
    v.s_elapsed = (now_ns - s_t0) / 1e9 if s_t0 else None
    v.planned = S.minutes()
    v.ends_at = s_t0 + v.planned * 60e9 if (s_t0 and v.planned) else None
    if S.ended() and S.t_end():
        v.s_t_end = S.t_end()
    else:
        v.s_t_end = None
    v.how_ended = None
    if cur.ended() or v.status == "STOPPING":
        if cur.kill:
            v.how_ended = "kill switch"
        elif cur.signal:
            v.how_ended = "Ctrl+C" if cur.signal == "SIGINT" else cur.signal
        elif cur.ended():
            v.how_ended = "time limit / max trades"
    # ---- money
    v.ps = agg_ps(sel)
    v.reg = agg_reg(sel)
    v.total = v.ps["net"] + v.reg["total"]
    v.per_hour = v.total / (v.elapsed / 3600) if v.elapsed and v.elapsed > 60 else None
    v.ps_cfg = dict(S.rs.get("psl") or {})
    for k, x in S.psl.items():
        v.ps_cfg.setdefault(k, x)
    if "routes" in v.ps_cfg and v.ps_cfg["routes"]:
        v.ps_cfg["routes"] = re.sub(r"\(.*?\)", "", str(v.ps_cfg["routes"]))
    v.ps_fail_each = (v.ps["fee_each"].most_common(1)[0][0] if v.ps["fee_each"] else v.ps_cfg.get("fail_fee") or PS_FAIL_FEE)
    normal_end = ("run_end", "run_stopping")
    v.ps_stopped = next((x for x in ((S.ps_stopped[0] if S.ps_stopped else None),
                                     next((x.get("why") for x in S.ps_stop if x.get("why") not in normal_end), None),
                                     S.status.get("ps_stopped")) if x and x not in normal_end), None)
    v.ps_open_now = len(S.ps_open) if v.running else 0
    if v.running and S.status.get("ps_now") is not None and not S.ps_rec:
        v.ps_open_now = S.status["ps_now"]
    # ---- wallet (the session's START BALANCE + its P&L; the kill switch is per session)
    v.start_bal = S.start_bal
    v.run_start_bal = sessions[0].start_bal if v.scope is None else S.start_bal
    v.s_total = S.total()
    v.est_now = (S.start_bal + v.s_total) if S.start_bal is not None else None
    v.kill_level = S.kill_level
    v.loss_cap = S.loss_cap()
    if v.kill_level is None and S.start_bal is not None and v.loss_cap:
        v.kill_level = S.start_bal - v.loss_cap
    v.kill_dist = (v.est_now - v.kill_level) if (v.est_now is not None and v.kill_level is not None) else None
    v.loss_used = None
    if v.start_bal is not None and v.est_now is not None and v.loss_cap:
        v.loss_used = max(0.0, (v.start_bal - v.est_now) / v.loss_cap)
    ctx.read_budget()
    v.budget_left = None
    b = ctx.budget
    if b and b.get("first_start") and b.get("max_total_loss") and v.est_now is not None:
        v.budget_left = b["max_total_loss"] - max(0, b["first_start"] - v.est_now)
        v.budget_max = b["max_total_loss"]
    # ---- series: cumulative P&L a minute
    buckets = collections.Counter()
    for x in sel:
        buckets.update(x.buckets)
    m0 = int((t_first if v.scope is None else s_t0) or 0) // 60_000_000_000 if (t_first or s_t0) else (min(buckets) if buckets else 0)
    if buckets:
        m0 = min(m0, min(buckets)) if m0 else min(buckets)
    m1 = int(now_ns) // 60_000_000_000
    if buckets:
        m1 = max(m1, max(buckets))
    series = []
    if m0 and m1 >= m0 and m1 - m0 < 7 * 1440:
        acc = 0
        for mm in range(m0, m1 + 1):
            acc += buckets.get(mm, 0)
            series.append(acc)
    v.series = series
    v.series_m0 = m0
    if series:
        hi = max(range(len(series)), key=lambda i: series[i])
        lo = min(range(len(series)), key=lambda i: series[i])
        v.best = (series[hi], (m0 + hi) * 60e9)
        v.worst = (series[lo], (m0 + lo) * 60e9)
    else:
        v.best = v.worst = None
    # ---- trades
    tl = [t for t in M.trades if v.scope is None or t["s"] == v.scope]
    v.trades = tl
    v.sessions = sessions
    # ---- QUIET
    v.quiet = quiet_state(S, M, now_ns / 1e9)
    v.cfg_items = config_items(v, S, eng)
    v.alerts = make_alerts(v, ctx, M)
    return v


def quiet_state(S, M, now):
    rq = S.rs.get("quiet") or {}
    q = S.quiet
    present = bool(rq or q.get("line"))
    out = dict(present=present, stop=None, skip=None, state=None, on_at=None, preload=q.get("preload"), preload_h=q.get("preload_h"))
    if not present:
        return out
    out["stop"] = q.get("stop") or rq.get("stop")
    sk = q.get("skip") if q.get("skip") is not None else rq.get("skip")
    out["skip"] = bool(sk)
    if not out["preload"] and rq.get("preload"):
        out["preload"] = "running"
    if S.q_preload:
        out["preload"] = "done" if S.q_preload.get("ok") else "failed"
        if S.q_preload.get("covered_h") is not None:
            out["preload_h"] = S.q_preload["covered_h"]
    on_at = resolve_on_at(S, M)
    out["on_at"] = on_at
    if not out["skip"]:
        out["state"] = "off"
    elif q.get("rule_state") == "on" or S.q_rule_on:
        out["state"] = "on"
    elif on_at and now * 1e9 >= on_at:
        out["state"] = "on"
    else:
        out["state"] = "warm-up"
    return out


def _sol2(lam):
    return f"{lam / LAM:.2f}" if lam is not None else "?"


def config_items(v, S, eng):
    """the run's configuration as badges: dict(key, state on|off|part|na, short, full, label)"""
    items = []
    fl = eng.flags if (eng is not None and eng.alive) else {}

    SL = {"ps": "Pre-send", "qstop": "QUIET stop", "qskip": "QUIET skip", "quiet": "QUIET", "paper": "Paper", "m2": "M2 gate",
          "dev": "Dev list", "reg": "Regular", "guard": "Guard", "routes": "Routes", "sellfan": "Sell fan", "nonce": "Nonce",
          "near": "Near gate", "skipcl": "Skip cl.", "kill": "Kill sw.", "planned": "Planned", "build": "Engine"}

    def add(key, label, state, short, full=None):
        items.append(dict(key=key, label=label, slabel=SL.get(key, label[:10]), state=state, short=short, full=full or short))
    # pre-send live
    pc = v.ps_cfg
    ps = v.ps
    if pc or ps["active"]:
        cap = pc.get("max_fills")
        budget = pc.get("fee_budget")
        st = "part" if (pc.get("dry") or v.ps_stopped) else "on"
        tag = " DRY" if pc.get("dry") else (f" ({v.ps_stopped})" if v.ps_stopped else "")
        sf, sfee = (S.ps_fills, S.ps_fees()) if S.ps_rec else (len(S.log_ps_real), S.log_ps_fees)   # the caps are per session
        short = f"PS {_sol2(pc.get('spend'))} k{pc.get('k', '?')} {sf}/{cap or '?'} fee {sfee / LAM:.2f}/{(budget or 0) / LAM:.2f}" + tag
        drop = pc.get("drop")
        full = (f"{_sol2(pc.get('spend'))} SOL {G['sep']} {pc.get('k', '?')} tries/slot" + (f" {G['sep']} limit {G['x']}{1 - drop:.2f}" if drop else
                (f" {G['sep']} limit {G['x']}{pc['limit']:.2f}" if pc.get("limit") else "")) +
                (f" {G['sep']} deadline +{pc['deadline_slots']}" if pc.get("deadline_slots") else "") +
                f" {G['sep']} route {pc.get('routes') or '?'}" + (f" {G['sep']} exit {pc['exit_slots']} slots" if pc.get("exit_slots") else "") +
                (f" / TP +{pc['tp'] * 100 if pc['tp'] < 1 else pc['tp']:.0f}%" if pc.get("tp") else "") +
                (f" / SL {pc['sl'] * 100 if pc['sl'] < 1 else pc['sl']:.0f}%" if pc.get("sl") else "") + tag)
        add("ps", "Pre-send live", st, short, full)
    else:
        add("ps", "Pre-send live", "off", "PS off", "off")
    # QUIET
    q = v.quiet
    if q["present"]:
        add("qstop", "QUIET stop rule", "on" if q["stop"] and q["stop"] != "off" else "off", f"stop {q['stop'] or 'off'}",
            (f"at trigger + {q['stop'].split(':')[0]} slots with < {q['stop'].split(':')[1]} other trades: no more attempts"
             if q["stop"] and ":" in q["stop"] else "off"))
        pre = ""
        if q["preload"]:
            pre = f" {G['sep']} preload {q['preload']}" + (f" {q['preload_h']:.1f} h" if q.get("preload_h") and q["preload"] == "done" else "")
        if q["state"] == "on":
            add("qskip", "QUIET skip rule", "on", "skip on", "on (all 4 quiet signals skip a trigger)" + pre)
        elif q["state"] == "warm-up":
            when = pkt(q["on_at"], "%H:%M") if q["on_at"] else "?"
            left = (q["on_at"] / 1e9 - v.now) if q["on_at"] else None
            cd = f" (in {hms(left)})" if left is not None and left > 0 else ""
            add("qskip", "QUIET skip rule", "part", f"skip on {when}", f"warming up: on at {when} PKT{cd}" + pre)
        else:
            add("qskip", "QUIET skip rule", "off", "skip off", "off" + pre)
    else:
        b = v.build or ""
        nm = re.match(r"dip(\d+)", b)
        why = "not in this engine" if (nm and int(nm.group(1)) < 20) else "off"
        add("quiet", "QUIET", "off", "QUIET off", why)
    # shadow, M2, dev list
    sh = S.cfg.get("shadow") or S.rs.get("presend")
    add("paper", "Paper (shadow)", "on" if sh else "off", "paper", "on (rows a/b/c = +0/+5/+10 ms)" if sh else "off")
    m2 = (S.rs.get("m2") or {}).get("mode") or S.cfg.get("m2") or (fl.get("--dip-m2-mode") if fl.get("--dip-m2") else None)
    if m2:
        mm = S.rs.get("m2") or {}
        add("m2", "M2 gate", "on" if m2 == "gate" else "part", f"M2 {m2}",
            f"{m2}" + (f" {G['sep']} model {mm['model']}" if mm.get("model") else "") + (f" {G['sep']} score {G['ge']} {mm['min']:.4f}" if mm.get("min") else ""))
    else:
        add("m2", "M2 gate", "off", "M2 off", "off (IMIT1 gate)")
    devn = S.rs.get("devs")
    dev = S.cfg.get("dev")
    if devn or dev:
        size = S.rs.get("dev_spend")
        if size is None and isinstance(dev, tuple):
            size = int(dev[1] * LAM)
        n = devn or (dev[0] if isinstance(dev, tuple) else "?")
        add("dev", "Dev list", "on", f"dev {_sol2(size)}", f"{n} dev wallet(s) {G['sep']} {_sol2(size)} SOL" +
            (f" {G['sep']} tier {S.rs.get('dev_tier')}" if S.rs.get("dev_tier") else ""))
    else:
        add("dev", "Dev list", "off", "dev off", "off")
    # regular buy + exit
    spend = S.rs.get("spend") or S.live.get("spend")
    tp = S.rs.get("tp")
    tp_s = ("off" if (tp is None or tp >= 99) else f"+{tp * 100:.0f}%") if tp is not None else (S.live.get("tp") or "?")
    sl = S.rs.get("sl")
    sl_s = f"{sl * 100:.0f}%" if sl is not None else (f"{S.live['sl']:.0f}%" if S.live.get("sl") is not None else "?")
    hold = S.rs.get("hold_slots") or S.live.get("hold")
    add("reg", "Regular buy", "na", f"{_sol2(spend)} TP {tp_s} SL {sl_s} {hold or '?'}sl",
        f"{_sol2(spend)} SOL {G['sep']} model {S.rs.get('model') or S.live.get('model') or '?'} {S.rs.get('tier') or S.live.get('tier') or ''} "
        f"{G['sep']} exit TP {tp_s} / SL {sl_s} / {hold or '?'} slots (~{(hold or 0) * 0.212:.1f} s)")
    guard = S.rs.get("guard") or S.live.get("guard")
    add("guard", "Price guard", "na", f"{G['x']}{guard:.2f}" if guard else "guard ?",
        f"{G['x']}{guard:.2f} over the post-dump price (pump error 6042 above it)" if guard else "?")
    routes = S.cfg.get("routes")
    if not routes and fl.get("--route-by-client"):
        routes = _route_map(fl["--route-by-client"])
    pre_name = route_preset(routes)
    add("routes", "Routes", "na", pre_name or "routes ?", (pre_name or "?") + (" " + "; ".join(f"{k}: {'+'.join(x)}" for k, x in sorted(routes.items())) if routes else ""))
    sf = S.cfg.get("sellfan") or fl.get("--sell-fanout")
    add("sellfan", "Sell fan-out", "on" if sf else "off", "sell-fan" if sf else "sell-fan off",
        f"staked-rpc + {sf if isinstance(sf, str) else 'on'}" if sf else "off")
    nonce = S.cfg.get("nonce") if S.cfg.get("nonce") is not None else (S.rs.get("nonce") or (8 if fl.get("--nonce-fanout") else None))
    add("nonce", "Nonce fan-out", "on" if nonce else "off", f"nonce {nonce}" if nonce else "nonce off",
        f"{nonce} durable-nonce accounts (one tip per landed buy)" if nonce else "off")
    near = S.cfg.get("near") or (True if fl.get("--dip-near-leaders") else None)
    add("near", "Near-leader gate", "on" if near else "off", f"near {near}" if isinstance(near, int) else ("near" if near else "near off"),
        f"{near} leaders" if isinstance(near, int) else ("on" if near else "off (every leader)"))
    skc = S.rs.get("skip_clients") or S.cfg.get("skip_clients")
    if skc:
        add("skipcl", "Skip clients", "na", "skip " + (",".join(skc) if isinstance(skc, list) else str(skc)),
            ", ".join(skc) if isinstance(skc, list) else str(skc))
    if v.kill_level is not None:
        add("kill", "Kill switch", "na", f"kill {v.kill_level / LAM:.3f}",
            f"below {v.kill_level / LAM:.4f} SOL" + (f" (loss cap {v.loss_cap / LAM:.3f})" if v.loss_cap else ""))
    if v.planned:
        add("planned", "Planned", "na", f"{v.planned}m", f"{v.planned} min" + (f" (ends {pkt(v.ends_at, '%H:%M')} PKT)" if v.ends_at else ""))
    add("build", "Engine", "na", v.build or "?", (v.build or "?") + ("" if v.build_live else " (inferred from the records)") +
        (f" {G['sep']} pid {eng.pid}" if eng is not None and eng.alive else ""))
    return items


def make_alerts(v, ctx, M):
    A = []
    S = v.cur
    if v.status == "ENGINE GONE":
        A.append(("bad", "engine gone without DIP DONE"))
    if M.panics:
        A.append(("bad", "engine panic: " + M.panics[-1][:60]))
    if M.refused and not M.seg_live:
        A.append(("bad", "start refused: " + M.refused[-1][7:70]))
    if S.kill:
        A.append(("bad", f"KILL SWITCH fired (run P&L {S.kill:+.4f})" if isinstance(S.kill, float) else "KILL SWITCH fired"))
    elif v.running and v.kill_dist is not None and v.kill_dist < 0.15 * LAM:
        A.append(("bad", f"kill switch {v.kill_dist / LAM:.3f} SOL away"))
    if v.running and v.write_age is not None and v.write_age > 30:
        A.append(("bad", f"log stalled {age_s(v.write_age)}"))
    ps = v.ps
    pc = v.ps_cfg
    if v.running and ps["active"]:
        if pc.get("fee_budget") and ps["fees"] > 0.8 * pc["fee_budget"]:
            A.append(("warn", f"pre-send fees {ps['fees'] / pc['fee_budget'] * 100:.0f}% of budget"))
        if pc.get("max_fills") and ps["fills"] > 0.9 * pc["max_fills"]:
            A.append(("warn", f"pre-send fills {ps['fills']}/{pc['max_fills']}"))
    if v.ps_stopped and not S.ended():
        A.append(("warn", f"pre-send stopped ({v.ps_stopped})"))
    if v.status == "STOPPING" and S.signal:
        A.append(("warn", f"stopping ({S.signal}): open positions finish"))
    lo = M.log_min - 9
    for path, c in sorted(M.path_err.items()):
        n = sum(x for k, x in c.items() if k >= lo)
        if n >= 3:
            A.append(("warn", f"{path} {M.path_kind.get(path, 'error')} {n}/10m"))
    pe = M.poll_err.get(M.log_min, 0) + M.poll_err.get(M.log_min - 1, 0)
    if v.running and pe >= 20:
        A.append(("warn", f"POLL-RPC-ERROR {pe}/2m"))
    if v.running and M.runtime and M.runtime[1] > 10:
        A.append(("warn", f"runtime lag p99 {M.runtime[1]:.1f} ms"))
    if S.end_check and any(S.end_check[1:]):
        A.append(("warn", "END CHECK found work: {} sold, {} closed, {} held, {} unreadable".format(*S.end_check[1:])))
    if ps["not_sold"] or ps["ata_fail"]:
        A.append(("warn", f"pre-send: {ps['not_sold']} unsold, {ps['ata_fail']} account closes failed"))
    if v.reg["est"] and not v.running:
        A.append(("warn", f"{v.reg['est']} regular fill(s) without the REALIZED line (feed estimate)"))
    if v.status == "ENDED":
        ec = S.end_check
        ecs = (f"END CHECK {ec[0]} read: {ec[1]} sold, {ec[2]} closed, {ec[3]} held" + (" " + G["ok"] if not any(ec[1:]) else "")) if ec else \
            ("no END CHECK line" if S.ps_active() else "")
        A.append(("end", f"RUN ENDED {pkt(v.t_end, '%H:%M')} ({v.how_ended or '?'}) {sol(v.total)} SOL" + (f" {G['sep']} {ecs}" if ecs else "")))
    if v.status == "NO END RECORD":
        A.append(("warn", "no DIP DONE / run_end in the files (incomplete copy?)"))
    order = {"bad": 0, "warn": 1, "end": 2, "info": 3}
    A.sort(key=lambda a: order.get(a[0], 9))
    return A


# ------------------------------------------------------------------------------------------------------------------ drawing
# a "line" is a list of (text, style) segments; styles: lbl dim val b pos neg posb negb acc accb warn bad good sel banner
def slen(L):
    return sum(len(t) for t, _ in L)


def fit(L, w):
    if w <= 0:
        return []
    out, n = [], 0
    for t, s in L:
        if not t:
            continue
        if n + len(t) <= w:
            out.append((t, s))
            n += len(t)
            continue
        room = w - n
        el = G["ell"]
        if room > len(el):
            out.append((t[:room - len(el)] + el, s))
        elif room > 0:
            out.append((t[:room], s))
        break
    return out


def pad(L, w):
    n = slen(L)
    if n > w:
        return fit(L, w)
    return L + [(" " * (w - n), "val")] if n < w else L


def lr(left, right, w):
    nl, nr = slen(left), slen(right)
    if nl + nr + 1 > w:
        return fit(left + [(" ", "val")] + right, w)
    return left + [(" " * (w - nl - nr), "val")] + right


def hjoin(blocks, gap=3, rule=True):
    """side-by-side blocks [(lines, width)]"""
    n = max((len(b[0]) for b in blocks), default=0)
    sep = (" " * (gap // 2) + G["vr"] + " " * (gap - gap // 2 - 1)) if rule else " " * gap
    out = []
    for i in range(n):
        L = []
        for k, (lines, w) in enumerate(blocks):
            seg = lines[i] if i < len(lines) else []
            if k == len(blocks) - 1:
                L += fit(seg, w)
            else:
                L += pad(seg, w)
                L.append((sep, "dim"))
        out.append(L)
    return out


def head(title, w, right=None):
    L = [(title, "accb")]
    r = list(right or [])
    n = w - slen(L) - slen(r) - 2
    L.append((" " + G["hr"] * n + " " if n > 0 else " ", "dim"))
    return fit(L + r, w)


def kv(label, vals, lw=11):
    return [(label.ljust(lw)[:lw], "lbl")] + list(vals)


def gauge(frac, w, style="acc"):
    w = max(1, w)
    if frac is None:
        return [(G["bar0"] * w, "dim")]
    k = int(round(max(0.0, min(1.0, frac)) * w))
    return [(G["bar"] * k, style), (G["bar0"] * (w - k), "dim")]


def merge(L):
    out = []
    for t, s in L:
        if out and out[-1][1] == s:
            out[-1] = (out[-1][0] + t, s)
        else:
            out.append((t, s))
    return out


def sparkline(series, w):
    if not series or w <= 0:
        return [(G["dash"], "lbl")]
    n = len(series)
    vals = [series[min(n - 1, max(0, int((i + 1) * n / w) - 1))] for i in range(w)] if n > w else list(series)
    lo, hi = min(vals), max(vals)
    ch = G["spark"]
    L = []
    for x in vals:
        lvl = 0 if hi == lo else int((x - lo) / (hi - lo) * (len(ch) - 1) + 0.5)
        L.append((ch[lvl], "pos" if x > 0 else ("neg" if x < 0 else "lbl")))
    return merge(L)


def wrap_text(text, w, indent=0):
    """hard-wrap a plain string into lines of width w (continuation lines indented)"""
    out, first = [], True
    s = text
    while s:
        room = w if first else w - indent
        if room <= 0:
            break
        if len(s) <= room:
            out.append(("" if first else " " * indent) + s)
            break
        cut = s.rfind(" ", 0, room + 1)
        if cut <= room // 3:
            cut = room
        out.append(("" if first else " " * indent) + s[:cut].rstrip())
        s = s[cut:].lstrip()
        first = False
    return out or [""]


class TextCanvas:
    def __init__(self, h, w):
        self.h, self.w = h, w
        self.rows = [[" "] * w for _ in range(h)]

    def put(self, y, x, text, style=None):
        if not (0 <= y < self.h):
            return
        row = self.rows[y]
        for i, ch in enumerate(text):
            if 0 <= x + i < self.w:
                row[x + i] = ch

    def dump(self):
        return "\n".join("".join(r).rstrip() for r in self.rows)


class CursesCanvas:
    def __init__(self, scr, attrs):
        self.scr = scr
        self.attrs = attrs
        self.h, self.w = scr.getmaxyx()

    def put(self, y, x, text, style=None):
        if y < 0 or y >= self.h or x >= self.w or not text:
            return
        text = text[: self.w - x]
        if y == self.h - 1 and x + len(text) >= self.w:
            text = text[: self.w - x - 1]
        if not text:
            return
        try:
            self.scr.addstr(y, x, text, self.attrs.get(style, 0))
        except Exception:
            pass


def draw_line(cv, y, L, w):
    x = 0
    for t, s in fit(L, w):
        cv.put(y, x, t, s)
        x += len(t)


# ------------------------------------------------------------------------------------------------------------------ screens
TABS = ["Overview", "Pre-send", "Regular", "Trades", "Health", "Log", "Config"]
TABS_SHORT = ["Ovw", "PS", "Reg", "Trd", "Hlth", "Log", "Cfg"]
FILTERS = ["all", "pre-send", "regular", "wins", "losses", "open"]


class R:
    """render context: the app state + the view + the screen size"""

    def __init__(self, app, w, h):
        self.app = app
        self.v = app.view
        self.w, self.h = w, h
        self.narrow = w < 70
        self.wide = w >= 120
        self.price = self.v.price if self.v else None
        self.usd_first = app.usd_first and bool(self.price)


def money(r, lam, d=4, unit=True, plain=False, tight=False):
    if lam is None:
        return [(G["dash"], "lbl")]
    st = "val" if plain else ("pos" if lam > 0 else ("neg" if lam < 0 else "val"))
    s_sol = sol(lam, d, not plain) + (" SOL" if unit else "")
    s_usd = (usd(lam, r.price, not plain) if r.price else "USD n/a")
    gap = " " if tight else "  "
    if r.usd_first:
        return [(s_usd, st), (gap + s_sol, "lbl")]
    return [(s_sol, st), (gap + s_usd, "lbl")]


def badge(it):
    st = {"on": "good", "off": "bad", "part": "warn"}.get(it["state"])
    if st is None:
        return []
    return [(BADGE_ASCII[it["state"]] if G.get("ascii") else G["on"], st)]


def status_style(v):
    return {"RUNNING": "good", "STOPPING": "warn", "ENDED": "acc", "ENGINE GONE": "bad", "NO END RECORD": "warn", "WAITING": "lbl"}.get(v.status, "val")


def pnl_style(lam, bold=False):
    if not lam:
        return "b" if bold else "val"
    return ("posb" if bold else "pos") if lam > 0 else ("negb" if bold else "neg")


def cfg_strip(r, items, w, max_lines=2, skip=()):
    """the config badges, packed into at most max_lines lines"""
    lines, cur = [], []
    for it in items:
        if it["key"] in skip:
            continue
        seg = badge(it)
        seg = seg + [((" " if seg else "") + it["short"], "val" if it["state"] != "na" else "lbl")]
        if cur and slen(cur) + 2 + slen(seg) > w:
            lines.append(cur)
            cur = []
            if len(lines) >= max_lines:
                break
        cur = cur + ([("  ", "val")] if cur else []) + seg
    if cur and len(lines) < max_lines:
        lines.append(cur)
    return [fit(L, w) for L in lines]


def kpis(r, compact=False, kill=True):
    v = r.v
    d = 4
    L = []
    L.append(kv("per hour", money(r, int(v.per_hour) if v.per_hour is not None else None, d), 10))
    ps, rg = v.ps, v.reg
    L.append(kv("pre-send", money(r, ps["net"] if ps["active"] else None, d) +
                ([] if compact or not ps["active"] else [(f"  {ps['fills']} fills {ps['wins']}W", "lbl")]), 10))
    L.append(kv("regular", money(r, rg["total"], d) + ([] if compact else [(f"  {rg['fills']} fills {rg['wins']}W", "lbl")]), 10))
    if kill and v.kill_dist is not None:
        st = "bad" if v.kill_dist < 0.15 * LAM else ("warn" if v.kill_dist < 0.3 * LAM else "val")
        L.append(kv("kill sw.", [(f"{v.kill_dist / LAM:.3f} SOL away", st)], 10))
    return L


def hero_block(r, large=False):
    v = r.v
    lam = v.total
    if r.usd_first:
        x = lam / LAM * r.price
        txt = f"{x:+.2f}" if abs(x) < 1e6 else f"{x:+.0f}"
        unit, sec = "USD", sol(lam, 4) + " SOL"
    else:
        x = lam / LAM
        txt = f"{x:+.3f}" if abs(x) < 1000 else f"{x:+.1f}"
        unit, sec = "SOL", (usd(lam, r.price) if r.price else "USD n/a")
    st = pnl_style(lam, True)
    st2 = pnl_style(lam)
    title = [("RUN P&L", "accb")] + ([(f"  session {v.scope + 1}", "lbl")] if v.scope is not None else [])
    if large:
        rows = big_text5(txt)
        return [title, []] + [[(rows[i], st)] + ([("  " + unit, "lbl")] if i == 4 else []) for i in range(5)] + [[], [(sec, st2)]]
    rows = big_text(txt)
    return [title, [(rows[0], st)], [(rows[1], st), ("  " + unit, "lbl")], [(rows[2], st)], [(sec, st2)]]


def run_lines(r, w):
    v = r.v
    st = status_style(v)
    L1 = [(G["on"] if not G.get("ascii") else "*", st), (" " + v.status, st + ("b" if st in ("pos", "neg") else ""))]
    if v.status == "ENDED" and v.t_end:
        L1 += [(f" {pkt(v.t_end, '%H:%M')}", "val"), (f" ({v.how_ended})" if v.how_ended else "", "lbl")]
    elif v.status == "STOPPING" and v.how_ended:
        L1 += [(f" ({v.how_ended})", "lbl")]
    if r.narrow:
        L1 += [(f"  {v.build}", "lbl")]
    if v.nsess > 1:
        L1 += [(f"  {v.nsess} sessions" if v.scope is None else f"  session {v.scope + 1}/{v.nsess}", "lbl")]
    t0 = v.t_first if v.scope is None else v.s_t0
    end = v.t_end if v.status == "ENDED" else v.ends_at
    L2 = [(pkt(t0, "%H:%M"), "val"), (f" {G['arrow']} ", "lbl"), (pkt(end, "%H:%M") if end else "?", "val"), (" PKT", "lbl")]
    frac = None
    if v.s_elapsed is not None and v.planned:
        frac = v.s_elapsed / (v.planned * 60)
        L2 += [("  ", "val"), (hms(v.s_elapsed), "val"), (f" / {hms(v.planned * 60)}", "lbl")]
    elif v.elapsed is not None:
        L2 += [("  ran ", "lbl"), (hms(v.elapsed), "val")]
    out = [L1, L2]
    if frac is not None:
        gw = max(6, min(30, w - slen(L2) - 7))
        if slen(L2) + gw + 7 <= w:
            out[1] = L2 + [("  ", "val")] + gauge(frac, gw, "acc") + [(f" {min(frac, 9.99) * 100:.0f}%", "lbl")]
        else:
            out.append(gauge(frac, max(6, w - 6), "acc") + [(f" {min(frac, 9.99) * 100:.0f}%", "lbl")])
    return out


def wallet_lines(r, w):
    v = r.v
    out = []
    if v.est_now is None:
        out.append(kv("wallet", [("start balance not in the log yet", "lbl")], 10))
        return out
    out.append(kv("wallet", [(f"{v.est_now / LAM:.4f}", "b"), (" SOL est.", "lbl"), (f"  start {v.start_bal / LAM:.4f}", "lbl")], 10))
    if v.kill_level is not None:
        st = "bad" if (v.kill_dist or 0) < 0.15 * LAM else "lbl"
        L = kv("kill sw.", [(f"< {v.kill_level / LAM:.4f}", st), (f"  {v.kill_dist / LAM:.3f} away", "val" if st == "lbl" else st)], 10)
        if v.loss_used is not None:
            gw = max(6, min(20, w - slen(L) - 14))
            if slen(L) + gw + 14 <= w:
                L += [("  ", "val")] + gauge(1 - v.loss_used, gw, "good" if v.loss_used < 0.7 else "bad") + \
                    [(f" cap {min(v.loss_used, 9.99) * 100:.0f}% used", "lbl")]
        out.append(L)
    if v.budget_left is not None:
        out.append(kv("budget", [(f"{v.budget_left / LAM:.3f}", "val"), (f" of {v.budget_max / LAM:.3f} SOL left (all dip runs)", "lbl")], 10))
    return out


def spark_lines(r, w):
    v = r.v
    L = [("P&L ", "lbl")] + sparkline(v.series, max(4, w - 4))
    out = [fit(L, w)]
    if v.best and v.worst:
        out.append([("hi ", "lbl"), (sol(v.best[0], 3), pnl_style(v.best[0])), (f" {pkt(v.best[1], '%H:%M')}", "lbl"),
                    ("   lo ", "lbl"), (sol(v.worst[0], 3), pnl_style(v.worst[0])), (f" {pkt(v.worst[1], '%H:%M')}", "lbl"),
                    ("   now ", "lbl"), (sol(v.total, 3), pnl_style(v.total))])
    return out


def trade_exit(tr):
    if tr["kind"] == "PS":
        if tr["close"] is None and tr["pnl"] is None:
            return "open"
        return EXIT_SHORT.get(tr["exit"] or "", (tr["exit"] or "?")[:5])
    res = tr["res"]
    if res == "filled":
        if tr["close"] is None:
            return "hold"
        return EXIT_SHORT.get(tr["close"].get("why") or "", (tr["close"].get("why") or "?")[:5])
    return {"guard": "6042", "lighthouse": "6001", "failed": "fail", "open": "open", "not landed": "drop"}.get(res, res[:5])


def trade_held(tr):
    if tr["kind"] == "PS":
        return f"{tr['slots']}sl" if tr.get("slots") is not None else (f"{tr['held_s']:.1f}s" if tr.get("held_s") else "")
    if tr["exit"] and tr["exit"].get("slots") is not None:
        return f"{tr['exit']['slots']}sl"
    if tr["close"] and tr["close"].get("exit_slot") and tr["close"].get("land_slot"):
        return f"{tr['close']['exit_slot'] - tr['close']['land_slot']}sl"
    return ""


def trade_path(tr):
    if tr["kind"] == "PS":
        return tr["path"] or ""
    if tr["land"]:
        return tr["land"].get("via") or ""
    if tr["failed"]:
        return tr["failed"].get("via") or ""
    return ""


def trade_row(r, tr, w, sel=False):
    p = tr["pnl"]
    spend = tr["spend"] or 0
    pct = (p / spend) if (p is not None and spend) else None
    st = "sel" if sel else None
    typ = "PS " if tr["kind"] == "PS" else "REG"
    ps_ = pnl_style(p)
    est = "~" if (p is not None and tr.get("src") == "est") else " "
    sp = sol(p, 4) + est if p is not None else (G["dash"] + "      ")
    us = (usd(p, r.price) if (p is not None and r.price) else "")
    ex = trade_exit(tr)
    exst = "lbl" if ex in ("time", "open", "hold") else ("warn" if ex in ("6042", "6001", "fail", "drop", "SL") else "val")
    if w >= 110:
        cells = [(pkt(tr["t"]), "lbl"), (" " + typ, "acc" if tr["kind"] == "PS" else "val"), (" " + short(tr["mint"], 8), "val"),
                 (f" {spend / LAM:5.2f}", "lbl"), (f" {sp:>9}", ps_), (f" {us:>9}", ps_), (f" {pct_s(pct):>7}", ps_),
                 (f"  {ex:<5}", exst), (f" {trade_held(tr):>5}", "lbl"), (f"  {kind_of(tr['client'])[:10]:<10}", "val"),
                 (f" {trade_path(tr)[:24]}", "lbl")]
    elif w >= 70:
        cells = [(pkt(tr["t"]), "lbl"), (" " + typ, "acc" if tr["kind"] == "PS" else "val"), (" " + short(tr["mint"], 6), "val"),
                 (f" {spend / LAM:4.2f}", "lbl"), (f" {sp:>9}", ps_), (f" {us:>8}", ps_), (f" {pct_s(pct):>7}", ps_),
                 (f" {ex:<5}", exst), (f" {trade_held(tr):>4}", "lbl"), (f" {kind_of(tr['client'])[:12]}", "val")]
    else:
        cells = [(pkt(tr["t"], "%H:%M"), "lbl"), (" " + ("PS" if tr["kind"] == "PS" else "RG"), "acc" if tr["kind"] == "PS" else "val"), (" " + short(tr["mint"], 6), "val"),
                 (f" {sp:>9}", ps_), (f" {us:>8}", ps_), (f" {pct_s(pct, 0):>5}", ps_), (f" {ex[:4]}", exst)]
    if st:
        cells = [(t, st) for t, _ in cells]
    return pad(cells, w) if sel else fit(cells, w)


def trade_header(w):
    if w >= 110:
        t = "time     type mint       size   P&L SOL       USD       %  exit   held  client     path"
    elif w >= 70:
        t = "time     typ mint   size   P&L SOL      USD       % exit  held client"
    else:
        t = "time  ty mint     P&L SOL      USD     % exit"
    return [(t[:w], "lbl")]


def sorted_trades(v, flt="all"):
    tl = v.trades
    if flt == "pre-send":
        tl = [t for t in tl if t["kind"] == "PS"]
    elif flt == "regular":
        tl = [t for t in tl if t["kind"] == "REG"]
    elif flt == "wins":
        tl = [t for t in tl if (t["pnl"] or 0) > 0]
    elif flt == "losses":
        tl = [t for t in tl if (t["pnl"] or 0) < 0]
    elif flt == "open":
        tl = [t for t in tl if t["res"] in ("open",) or (t["kind"] == "PS" and t["close"] is None and t["pnl"] is None)
              or (t["kind"] == "REG" and t["res"] == "filled" and t["close"] is None)]
    return sorted(tl, key=lambda t: t["t"] or 0, reverse=True)


# ---------------------------------------------------------------- 1 overview
def scr_overview(r, bh):
    v = r.v
    w = r.w
    out = []
    banner = next((a for a in v.alerts if a[0] == "end"), None)
    strip_skip = ("kill", "planned", "build", "skipcl")
    if r.narrow:
        out += run_lines(r, w)
        out.append([])
        out += kpis(r, compact=w < 56, kill=False)
        out += wallet_lines(r, w)
        out.append([])
        out += cfg_strip(r, v.cfg_items, w, max_lines=4, skip=strip_skip)
        out.append([])
        out += spark_lines(r, w)
        out.append(head("LAST TRADES", w))
        n = max(3, bh - len(out))
        out += [trade_row(r, t, w) for t in sorted_trades(v)[:n]] or [[("no trades yet", "lbl")]]
        return out
    if r.wide:
        hb = hero_block(r, large=True)
        kp = kpis(r)
        left = hb + [[]] + kp
        lw = max(30, max(slen(L) for L in left) + 3)
        rw = w - lw - 3
        right = [head("RUN", rw)] + run_lines(r, rw) + [[]] + [head("WALLET", rw)] + wallet_lines(r, rw)
        if v.nsess > 1:
            right += [[]] + [head("SESSIONS", rw)] + session_rows(r, rw, max_rows=4)
        out += hjoin([(left, lw), (right, rw)])
        out.append([])
        if banner:
            out.append([(" " + banner[1] + " ", "banner")])
            out.append([])
        out.append(head("CONFIG", w))
        out += cfg_strip(r, v.cfg_items, w, max_lines=2)
        out.append([])
        out.append(head("CUMULATIVE P&L", w))
        out += spark_lines(r, w)
        out.append([])
        out.append(head("LAST TRADES", w))
        out.append(trade_header(w))
        n = max(4, bh - len(out))
        out += [trade_row(r, t, w) for t in sorted_trades(v)[:n]] or [[("no trades yet", "lbl")]]
        return out
    # medium: the hero with the key figures beside it
    hb = hero_block(r)
    lw = max(slen(L) for L in hb) + 3
    kp = kpis(r, compact=w < 100)
    out += hjoin([(hb, lw), ([[]] + kp, w - lw - 3)])
    out += run_lines(r, w)
    out += wallet_lines(r, w)[:2]
    if banner:
        out.append([(" " + banner[1] + " ", "banner")])
    out += cfg_strip(r, v.cfg_items, w, max_lines=2, skip=strip_skip)
    out += spark_lines(r, w)
    out.append(head("LAST TRADES", w))
    n = max(3, bh - len(out))
    out += [trade_row(r, t, w) for t in sorted_trades(v)[:n]] or [[("no trades yet", "lbl")]]
    return out


def session_rows(r, w, max_rows=20):
    v = r.v
    rows = [[("#  start  ", "lbl"), ("     P&L", "lbl"), ("  pre-send", "lbl"), ("  regular", "lbl"), ("  end", "lbl")]]
    for S in v.sessions[-max_rows:]:
        t = S.total()
        end = pkt(S.t_end(), "%H:%M") if S.t_end() else ("now" if S is v.cur and v.running else "?")
        rows.append([(f"{S.idx + 1:<2} {pkt(S.t0, '%H:%M'):<6} ", "val"), (f"{sol(t, 4):>8}", pnl_style(t)), (f"  {sol(S.ps_net(), 4):>8}", "lbl"),
                     (f"  {sol(S.reg_total(), 4):>7}", "lbl"), (f"  {end}", "lbl")])
    return [fit(L, w) for L in rows]


# ---------------------------------------------------------------- 2 pre-send
def scr_presend(r, bh):
    v = r.v
    w = r.w
    ps, pc, S = v.ps, v.ps_cfg, v.S
    it = next((x for x in v.cfg_items if x["key"] == "ps"), None)
    if not ps["active"] and not pc:
        out = [head("PRE-SEND LIVE", w), [("off in this run", "lbl")]]
        if ps["paper"]:
            out += [[], head("PAPER (shadow)", w), kv("row c", [(f"{ps['paper_fills']} fills  gross {ps['paper_gross']:+.3f}  net {ps['paper_net']:+.3f} SOL", "val")])]
        return out
    cw = (w - 3) // 2 if r.wide else w
    # ---- caps (the session's: the caps are per engine session)
    C = []
    cap, budget = pc.get("max_fills"), pc.get("fee_budget")
    sfills, sfees = (S.ps_fills, S.ps_fees()) if S.ps_rec else (len(S.log_ps_real), S.log_ps_fees)
    tag = f" (session {S.idx + 1})" if v.nsess > 1 else ""
    C.append(head("PRE-SEND LIVE" + tag, cw, right=badge(it) + [(" " + (it["short"].split(" ", 1)[1] if it else ""), "lbl")] if (it and cw >= 70) else badge(it) if it else None))
    gw = max(8, min(30, cw - 30))
    C.append(kv("fills", [(f"{sfills:>4} / {cap or '?':<5}", "val")] + gauge(sfills / cap if cap else None, gw, "acc") +
                [(f" {sfills / cap * 100:.0f}%" if cap else "", "lbl")]))
    fr = sfees / budget if budget else None
    C.append(kv("fee budget", [(f"{sfees / LAM:.3f}/{(budget or 0) / LAM:.2f}", "val"), (" ", "val")] +
                gauge(fr, gw - 2, "warn" if (fr or 0) > 0.8 else "acc") + [(f" {fr * 100:.0f}%" if fr is not None else "", "lbl")]))
    C.append(kv("armed now", [(f"{v.ps_open_now}", "b" if v.ps_open_now else "val"), (" window" + ("" if v.ps_open_now == 1 else "s"), "lbl"),
                              (f"   armed {ps['armed']:,}", "lbl"),
                              (f"   tries {ps['sent']:,}" + (f" (+{ps['dry']:,} dry)" if ps["dry"] else ""), "lbl")]))
    if v.ps_stopped:
        C.append(kv("stopped", [(v.ps_stopped, "warn"), ("  no new attempts this session", "lbl")]))
    # ---- result
    A = [head("RESULT", cw)]
    A.append(kv("net", money(r, ps["net"])))
    A.append(kv("realized", [(sol(ps["real"]), pnl_style(ps["real"])), ("   rent back ", "lbl"), (sol(ps["rent"]), pnl_style(ps["rent"]))]))
    each = v.ps_fail_each
    A.append(kv("failed", [(sol(-ps["fees"]), "neg" if ps["fees"] else "val"), (f"   {ps['fee_n']:,} tries x {each:,}", "lbl")]))
    if ps.get("all_stopped") and ps["fees_eng"]:
        d = ps["fees_eng"] - ps["fees_cnt"]
        A.append(kv("fee check", [(f"counted {ps['fees_cnt'] / LAM:.6f}  engine {ps['fees_eng'] / LAM:.6f}  ", "lbl"),
                                  (G["ok"] if abs(d) < each else f"differs {d / LAM:+.6f}", "good" if abs(d) < each else "warn")]))
    elif ps["fees_eng"]:
        A.append(kv("engine", [(f"{ps['fees_eng'] / LAM:.6f} at its last status line (60 s)", "lbl")]))
    nl = ps["nreal"] - ps["wins"]
    wr = ps["wins"] / ps["nreal"] if ps["nreal"] else None
    A.append(kv("wins", [(f"{ps['wins']} W / {nl} L", "val"), (f"  ({wr * 100:.0f}%)" if wr is not None else "", "lbl"),
                         ("   avg/fill ", "lbl"), (sol(int(ps["real"] / ps["fills"]) if ps["fills"] else None), pnl_style(ps["real"]))]))
    if ps["best"]:
        b, x = ps["best"], ps["worst"]
        A.append(kv("best", [(short(b["mint"]) + " ", "val"), (sol(b["pnl"]), pnl_style(b["pnl"])), (f"  {EXIT_SHORT.get(b['exit'] or '', b['exit'] or '?')} {kind_of(b['client'])}", "lbl")]))
        A.append(kv("worst", [(short(x["mint"]) + " ", "val"), (sol(x["pnl"]), pnl_style(x["pnl"])), (f"  {EXIT_SHORT.get(x['exit'] or '', x['exit'] or '?')} {kind_of(x['client'])}", "lbl")]))
    # ---- exits + landing
    E = [head("EXITS", cw)]
    for why, (n, wn, p) in sorted(ps["exits"].items(), key=lambda kv_: -kv_[1][0]):
        E.append([(f"{why:<12}", "lbl"), (f"{n:>5}", "val"), (f"  {wn:>4} W", "lbl"), (f"  {sol(p):>8}", pnl_style(p)),
                  (f"  {sol(int(p / n)) if n else '':>8}/fill", "lbl")])
    if not ps["exits"]:
        E.append([("no closed fills yet", "lbl")])
    if ps["open_pos"]:
        E.append([(f"{'open now':<12}", "lbl"), (f"{ps['open_pos']:>5}", "warn")])
    Ld = [head("LANDING", cw)]
    lm = med(ps["land_ms"])
    Ld.append(kv("send>seen", [(f"median {lm:.0f} ms" if lm is not None else G["dash"], "val"), (f"  ({len(ps['land_ms'])} fills)", "lbl")]))
    if ps["after"]:
        c = collections.Counter(min(x, 5) for x in ps["after"])
        Ld.append(kv("after trig", [(f"median +{med(ps['after']):.0f} slots", "val")]))
        Ld.append(kv("", [(" ".join(f"+{k}{'+' if k == 5 else ''}:{c[k]}" for k in sorted(c)), "lbl")]))
    # ---- QUIET
    q = v.quiet
    Q = [head("QUIET", cw)]
    if not q["present"]:
        qi = next((x for x in v.cfg_items if x["key"] == "quiet"), None)
        Q.append(kv("QUIET", badge(qi) + [(" " + (qi["full"] if qi else "off"), "lbl")]))
    else:
        si = next((x for x in v.cfg_items if x["key"] == "qstop"), None)
        ki = next((x for x in v.cfg_items if x["key"] == "qskip"), None)
        Q.append(kv("stop rule", badge(si) + [(f" {q['stop'] or 'off'}", "val"), (f"   stops {ps['q_stops']}", "lbl")]))
        kt = ki["full"] if ki else ""
        kl = wrap_text(kt, max(10, cw - 13))
        Q.append(kv("skip rule", badge(ki) + [(" " + kl[0], "val")]))
        for ln in kl[1:]:
            Q.append(kv("", [("  " + ln, "val")]))
        Q.append(kv("", [(f"skips {ps['q_skips']}   would-skip in the warm-up {ps['q_would']}", "lbl")]))
    # ---- paper vs live
    P = [head("PAPER vs LIVE", cw)]
    if ps["paper"]:
        P.append(kv("paper (c)", [(f"{ps['paper_fills']:>4} fills", "val"), (f"  gross {ps['paper_gross']:+.3f}", "lbl"),
                                  ("  net ", "lbl"), (f"{ps['paper_net']:+.3f}", pnl_style(ps['paper_net']))]))
    else:
        P.append(kv("paper (c)", [("no shadow numbers yet", "lbl")]))
    P.append(kv("live", [(f"{ps['fills']:>4} fills", "val"), ("  net ", "lbl"), (sol(ps["net"], 3), pnl_style(ps["net"]))]))
    # ---- windows detail
    Wn = [head("WINDOWS", cw)]
    for lab, cnt in (("skipped", ps["skips"]), ("disarmed", ps["disarms"]), ("results", ps["res"])):
        txt = f" {G['sep']} ".join(f"{k} {n:,}" for k, n in cnt.most_common()) or G["dash"]
        for i, ln in enumerate(wrap_text(txt, max(10, cw - 11))):
            Wn.append(kv(lab if i == 0 else "", [(ln, "val")]))
    Ss = []
    if v.nsess > 1 and v.scope is None:
        Ss = [head("SESSIONS", cw), [("#  start  fills  wins   realized     rent     fees      net  stop", "lbl")]]
        for X in v.sessions:
            a = agg_ps([X])
            stop = next((s_.get("why") for s_ in X.ps_stop if s_.get("why") not in ("run_end",)), None) or (X.ps_stop[-1]["why"] if X.ps_stop else "")
            Ss.append([(f"{X.idx + 1:<2} {pkt(X.t0, '%H:%M'):<6}{a['fills']:>5} {a['wins']:>5} {sol(a['real']):>10} {sol(a['rent']):>8} "
                        f"{sol(-a['fees']):>8} ", "val"), (f"{sol(a['net']):>8}", pnl_style(a["net"])), (f"  {stop}", "lbl")])
    if r.wide:
        left = C + [[]] + A + [[]] + E + [[]] + Ld
        right = Q + [[]] + P + [[]] + Wn + ([[]] + Ss if Ss else [])
        return hjoin([(left, cw), (right, w - cw - 3)])
    out = C + [[]] + A + [[]] + Q + [[]] + E + [[]] + P + [[]] + Ld + [[]] + Wn
    return out + ([[]] + Ss if Ss else [])


# ---------------------------------------------------------------- 3 regular
def scr_regular(r, bh):
    v = r.v
    w = r.w
    g = v.reg
    cw = (w - 3) // 2 if r.wide else w
    ri = next((x for x in v.cfg_items if x["key"] == "reg"), None)
    mi = next((x for x in v.cfg_items if x["key"] == "m2"), None)
    A = [head("REGULAR BUYS", cw, right=(badge(mi) + [(" " + mi["short"], "lbl")]) if mi else None)]
    if ri:
        A.append(kv("setup", [(ri["short"], "val")]))
    A.append(kv("P&L", money(r, g["total"])))
    A.append(kv("", [("fills ", "lbl"), (sol(g["fill_pnl"]), pnl_style(g["fill_pnl"])), ("   failed buys ", "lbl"), (sol(g["fail_pnl"]), pnl_style(g["fail_pnl"]))]))
    fr = g["fills"] / g["fires"] if g["fires"] else None
    A.append(kv("buys", [(f"{g['fires']} fired", "val"), (f" {G['arrow']} ", "lbl"), (f"{g['fills']} filled", "b"),
                         (f" ({fr * 100:.0f}%)" if fr is not None else "", "lbl"), (f"  {g['guard'] + g['lighthouse'] + g['failed']} failed", "val"),
                         (f"  {g['open']} open" if g["open"] else "", "warn")]))
    nl = g["fills"] - g["wins"]
    A.append(kv("wins", [(f"{g['wins']} W / {nl} L", "val"), ("   avg/fill ", "lbl"),
                         (sol(int(g["fill_pnl"] / g["fills"])) if g["fills"] else G["dash"], pnl_style(g["fill_pnl"]))]))
    if g["est"]:
        A.append(kv("", [(f"{g['est']} fill(s) still on the feed estimate (~) until the engine's REALIZED line", "warn")]))
    if g["best"]:
        A.append(kv("best", [(short(g["best"]["mint"]) + " ", "val"), (sol(g["best"]["pnl"]), pnl_style(g["best"]["pnl"])),
                             ("   worst ", "lbl"), (short(g["worst"]["mint"]) + " ", "val"), (sol(g["worst"]["pnl"]), pnl_style(g["worst"]["pnl"]))]))
    A.append([])
    A.append(head("FAILED BUYS", cw))
    fee = r.app.ctx.src.model.fail_buy_fee
    for lab, k in (("price 6042", "guard"), ("lighthouse 6001", "lighthouse"), ("other", "failed")):
        n = g[k]
        A.append([(f"{lab:<16}", "lbl"), (f"{n:>4}", "val" if n else "lbl"), (f"   {sol(-n * fee)}", "neg" if n else "lbl")])
    A.append([(f"(each costs its tx fee {fee / LAM:.6f} SOL; tips revert)", "lbl")])
    A.append([])
    A.append(head("EXITS", cw))
    for why, (n, wn, p) in sorted(g["exits"].items(), key=lambda kv_: -kv_[1][0]):
        A.append([(f"{why:<12}", "lbl"), (f"{n:>5}", "val"), (f"  {wn:>4} W", "lbl"), (f"  {sol(p):>8}", pnl_style(p))])
    if not g["exits"]:
        A.append([("no sold fills yet", "lbl")])
    B = [head("BY LEADER CLIENT", cw)]
    B.append([("client        buys fills    W    P&L SOL", "lbl")])
    for k, (n, f, wn, p) in sorted(g["kinds"].items(), key=lambda kv_: -kv_[1][0]):
        B.append([(f"{k[:12]:<12}{n:>6}{f:>6}{wn:>5}", "val"), (f"  {sol(p):>9}", pnl_style(p))])
    if not g["kinds"]:
        B.append([("no buys yet", "lbl")])
    B.append([])
    B.append(head("LANDING", cw))
    lm = med(g["land_ms"])
    B.append(kv("fills", [(f"median {lm:.0f} ms after the dump" if lm is not None else G["dash"], "val")]))
    B.append(kv("", [(f"{g['same']} of {g['fills']} in the dump's own block", "lbl")]))
    fm = med(g["fail_ms"])
    if fm is not None:
        B.append(kv("fails", [(f"median {fm:.0f} ms after the dump (seen)", "lbl")]))
    B.append([])
    B.append(head("OPEN NOW", cw))
    if g["open_list"]:
        for tr in g["open_list"][-5:]:
            B.append([(pkt(tr["t"]) + " ", "lbl"), (short(tr["mint"], 8), "val"), (f" {(tr['spend'] or 0) / LAM:.2f} SOL", "val"),
                      (f"  {'holding' if tr['res'] == 'filled' else 'in flight'}", "warn"), (f"  {kind_of(tr['client'])}", "lbl")])
    else:
        B.append([("no open position", "lbl")])
    B.append([])
    B.append(head("FUNNEL", cw))
    B.append(kv("dumps", [(f"{g['dumps']:,}", "val"), (f"   picks {g['picks']:,}", "lbl")]))
    txt = f" {G['sep']} ".join(f"{k} {n:,}" for k, n in g["skipped"].most_common()) or G["dash"]
    for i, ln in enumerate(wrap_text(txt, max(10, cw - 11))):
        B.append(kv("skipped" if i == 0 else "", [(ln, "val")]))
    if r.wide:
        return hjoin([(A, cw), (B, w - cw - 3)])
    return A + [[]] + B


# ---------------------------------------------------------------- 4 trades (own scrolling)
def scr_trades(r, bh):
    app = r.app
    v = r.v
    w = r.w
    flt = FILTERS[app.tfilter]
    tl = sorted_trades(v, flt)
    app._tlist = tl
    n = len(tl)
    app.sel = max(0, min(app.sel, n - 1)) if n else 0
    rows = bh - 2
    if app.sel < app.top:
        app.top = app.sel
    if app.sel >= app.top + rows:
        app.top = app.sel - rows + 1
    app.top = max(0, min(app.top, max(0, n - rows)))
    wins = sum(1 for t in tl if (t["pnl"] or 0) > 0)
    tot = sum(t["pnl"] or 0 for t in tl)
    hdr = lr([("TRADES ", "accb"), (f"{flt} ", "acc"), (f"({n})", "lbl")],
             [(f"{wins}W ", "lbl"), (sol(tot), pnl_style(tot)), ("  f filter  Enter details", "lbl")] if w >= 70 else [(sol(tot), pnl_style(tot))], w)
    out = [hdr, trade_header(w)]
    if not tl:
        out.append([("no trades" + ("" if flt == "all" else " for this filter"), "lbl")])
    for i in range(app.top, min(n, app.top + rows)):
        out.append(trade_row(r, tl[i], w, sel=(i == app.sel)))
    return out


# ---------------------------------------------------------------- 5 health
def scr_health(r, bh):
    app = r.app
    v = r.v
    w = r.w
    M = app.ctx.src.model
    eng = app.ctx.engine
    sy = app.ctx.sys
    src = app.ctx.src
    out = [head("ENGINE", w)]
    if eng is not None and eng.alive:
        up = (time.time() - eng.start) if eng.start else (v.s_elapsed or 0)
        out.append(kv("process", [(f"pid {eng.pid}", "val"), (f"  {eng.build or '?'}", "lbl"),
                                  ("  cpu ", "lbl"), (f"{eng.cpu:.0f}%" if eng.cpu is not None else G["dash"], "val"),
                                  ("  rss ", "lbl"), (f"{(eng.rss or 0) / 1e6:,.0f} MB", "val"),
                                  ("  up ", "lbl"), (hms(up), "val"), (f"  {eng.threads} thr" if eng.threads else "", "lbl")]))
    else:
        st = "bad" if v.status == "ENGINE GONE" else "lbl"
        why = "no engine process with this --dip-log" + (" (it was running)" if (eng is not None and eng.seen) else "")
        out.append(kv("process", [(why, st)]))
    la, ja = v.log_age, v.jsonl_age
    stall = v.running and v.write_age is not None and v.write_age > 30
    out.append(kv("log", [(f"{src.tl.size / 1e6:,.1f} MB", "val"), ("  written ", "lbl"), (age_s(la) + " ago" if la is not None else "never", "bad" if stall else "val"),
                          (f"  {M.llines:,} lines", "lbl")]))
    out.append(kv("records", [(f"{src.tj.size / 1e6:,.1f} MB", "val"), ("  written ", "lbl"), (age_s(ja) + " ago" if ja is not None else "never", "bad" if stall else "val"),
                              (f"  {M.jlines:,} lines", "lbl"), (f"  bad {M.bad}", "warn" if M.bad else "lbl")]))
    if M.runtime:
        p50, p99, mx = M.runtime
        out.append(kv("runtime", [("lag p50 ", "lbl"), (f"{p50:.2f}", "val"), ("  p99 ", "lbl"), (f"{p99:.2f}", "warn" if p99 > 10 else "val"),
                                  ("  max ", "lbl"), (f"{mx:.1f} ms", "val"), (f"  worst p99 {M.runtime_worst:.1f}", "lbl")]))
    out.append([])
    out.append(head("ERRORS", w))
    pe1 = M.poll_err.get(M.log_min, 0)
    pe10 = sum(x for k, x in M.poll_err.items() if k >= M.log_min - 9)
    out.append(kv("poll errs", [(f"{pe1}", "warn" if pe1 >= 10 else "val"), (" this min", "lbl"), (f"  {pe10}", "val"), (" in 10 min", "lbl"),
                                  (f"  {M.poll_err_total} total", "lbl")]))
    lo = M.log_min - 9
    pe = []
    for path, c in sorted(M.path_err.items(), key=lambda kv_: -M.path_total[kv_[0]]):
        n10 = sum(x for k, x in c.items() if k >= lo)
        pe.append([(f"{path[:14]:<14}", "val"), (f" {M.path_kind.get(path, 'error'):<9}", "warn" if n10 >= 3 else "lbl"),
                   (f"{n10:>4}", "warn" if n10 >= 3 else "val"), (" in 10 min", "lbl"), (f"  {M.path_total[path]} total", "lbl")])
    out.append(kv("send paths", [] if pe else [("no keep-alive / connection errors", "lbl")]))
    out += pe
    if M.panics:
        out.append(kv("panics", [(M.panics[-1][:w - 12], "bad")]))
    if M.refused:
        out.append(kv("refused", [(M.refused[-1][:w - 12], "warn")]))
    out.append([])
    out.append(head("SYSTEM", w))
    if sy is not None:
        out.append(kv("disk", [(f"{sy.disk:.0f}%" if sy.disk is not None else G["dash"], "warn" if (sy.disk or 0) > 85 else "val"),
                               ("  load ", "lbl"), (" ".join(f"{x:.2f}" for x in sy.load) if sy.load else G["dash"], "val"),
                               (f" ({sy.ncpu} cpu)", "lbl")]))
        if sy.mem:
            out.append(kv("memory", [(f"{sy.mem[0] / 1e9:.2f} / {sy.mem[1] / 1e9:.2f} GB", "val"),
                                     (f"  ({sy.mem[0] / sy.mem[1] * 100:.0f}% used)", "lbl")]))
        out.append(kv("dipmon", [(f"cpu {sy.own_cpu:.1f}%" if sy.own_cpu is not None else "cpu " + G["dash"], "val"),
                                 (f"  rss {(sy.own_rss or 0) / 1e6:.0f} MB", "val"), (f"  pid {os.getpid()}", "lbl")]))
    pr = app.ctx.price
    if pr is not None:
        out.append(kv("SOL/USD", [(f"${pr.usd:,.2f}" if pr.usd else "n/a", "val"),
                                  (f"  {pr.src or ''}" + (f", {age_s(pr.age())} ago" if pr.age() is not None else ""), "lbl"),
                                  (f"  {pr.err[:w - 40]}" if pr.err and not pr.usd else "", "warn")]))
    out.append([])
    out.append(head("RPC LATENCY (latest minute, ms)", w))
    if M.rpc:
        nw = 14 if w >= 70 else 11
        mw = 20 if w >= 70 else 14
        out.append([(f"{'name':<{nw}}{'method':<{mw}}{'p50':>7}{'p99':>8}{'n':>6}{'to':>5}", "lbl")])
        for (nm, meth), x in sorted(M.rpc.items(), key=lambda kv_: (-kv_[1].get("min", 0), kv_[0])):
            if M.log_min - x.get("min", 0) > 30:
                continue
            out.append([(f"{nm[:nw - 1]:<{nw}}{meth[:mw - 1]:<{mw}}", "val"), (f"{x['p50']:>7.1f}", "val"),
                        (f"{x['p99']:>8.1f}", "warn" if x["p99"] > 300 else "val"), (f"{x['n']:>6}", "lbl"),
                        (f"{x['to']:>5}", "warn" if x["to"] else "lbl")])
    else:
        out.append([("no RPC-LAT lines yet", "lbl")])
    return out


# ---------------------------------------------------------------- 6 log (own scrolling)
def scr_log(r, bh):
    app = r.app
    w = r.w
    M = app.ctx.src.model
    src_lines = M.log_ring if app.log_all else M.log_imp
    rows = bh - 1
    if app.log_wrap:                      # wrap only what can be shown: from the newest line back
        need = rows + min(app.log_off, 10 ** 6)
        lines = []
        for s in reversed(src_lines):
            lines[:0] = wrap_text(s, w, 2)
            if len(lines) >= need:
                break
    else:
        lines = src_lines
    n = len(lines)
    app.log_off = max(0, min(app.log_off, max(0, n - rows)))
    end = n - app.log_off
    start = max(0, end - rows)
    hdr = lr([("LOG ", "accb"), ("all lines" if app.log_all else "important", "acc"), (f"  ({len(src_lines):,})", "lbl")],
             [("following" if app.log_off == 0 else f"{app.log_off} up", "lbl" if app.log_off == 0 else "warn"),
              ("  f all/imp  w wrap" if w >= 60 else "", "lbl")], w)
    out = [hdr]
    for i in range(start, end):
        s = lines[i]
        st = "val"
        if "KILL" in s or "panicked" in s or "Error" in s or "FAILED" in s:
            st = "bad" if ("KILL" in s or "panicked" in s) else "warn"
        elif "REALIZED" in s:
            m = re.search(r"(?:pnl=|REALIZED \S+ )([-+][\d.]+)", s)
            st = ("pos" if m.group(1).startswith("+") else "neg") if m else "val"
        elif "DIP FIRE" in s or "FILL" in s:
            st = "acc"
        elif "QUIET" in s or "STOPPED" in s or "SIGNAL" in s or "refused" in s or "UNHEALTHY" in s:
            st = "warn"
        elif s.startswith("===") or "START BALANCE" in s or s.startswith("DIP LIVE"):
            st = "b"
        out.append([(s[:w], st)])
    if not lines:
        out.append([("no log lines" + ("" if app.log_all else " marked important yet (f: show all)"), "lbl")])
    return out


# ---------------------------------------------------------------- 7 config
def scr_config(r, bh):
    v = r.v
    w = r.w
    S = v.S
    out = [head("CONFIG", w, right=[(f"session {S.idx + 1}/{v.nsess}" if v.nsess > 1 else "", "lbl")])]
    lw = 19 if w >= 70 else 11
    for it in v.cfg_items:
        b = badge(it) or [(" ", "val")]
        text = it["full"]
        if it["key"] == "routes" and w < 70:
            text = text.split(" ", 1)[0] + (" (wider screen: per leader kind)" if " " in text else "")
        lines = wrap_text(text, max(10, w - lw - 3))
        out.append(b + [(" " + (it["label"] if w >= 70 else it["slabel"]).ljust(lw)[:lw], "lbl"), (" " + lines[0], "val")])
        for ln in lines[1:]:
            out.append([(" " * (lw + 2) + " " + ln, "val")])
    out.append([])
    out.append(head("WALLET", w))
    if v.start_bal is not None:
        out.append(kv("start", [(f"{v.start_bal / LAM:.6f} SOL", "val"), ("  (START BALANCE of this session)", "lbl")], lw + 2))
        out.append(kv("now (est.)", [(f"{v.est_now / LAM:.6f} SOL", "val"), ("  start + this session's P&L", "lbl")], lw + 2))
    if v.budget_left is not None:
        out.append(kv("dip budget left", [(f"{v.budget_left / LAM:.4f} of {v.budget_max / LAM:.3f} SOL", "val")], lw + 2))
    wal = S.rs.get("wallet")
    if wal:
        out.append(kv("address", [(f"{wal[:8]}{G['ell']}{wal[-4:]}", "val"), ("  (public)", "lbl")], lw + 2))
    out.append([])
    out.append(head("LEGEND", w))
    out.append([(G["on"] if not G.get("ascii") else "+", "good"), (" on   ", "lbl"), (G["on"] if not G.get("ascii") else "~", "warn"),
                (" warming up / partial / stopped   ", "lbl"), (G["on"] if not G.get("ascii") else "-", "bad"), (" off", "lbl")])
    return out


# ---------------------------------------------------------------- detail / help
def scr_detail(r, bh, tr):
    v = r.v
    w = r.w
    out = []
    ps = tr["kind"] == "PS"
    title = "PRE-SEND FILL" if ps else "REGULAR BUY"
    out.append(head(f"{title}  {pkt(tr['t'], '%Y-%m-%d %H:%M:%S')} PKT", w, right=[(f"session {tr['s'] + 1}", "lbl")]))
    lw = 10

    def url_lines(label, kind, sig):
        if not sig:
            return []
        u = f"https://solscan.io/{kind}/{sig}"
        ls = wrap_text(u, max(10, w - lw))
        return [kv(label, [(ls[0], "acc")], lw)] + [kv("", [(x, "acc")], lw) for x in ls[1:]]
    out += [kv("mint" if i == 0 else "", [(x, "val")], lw) for i, x in enumerate(wrap_text(tr["mint"], max(10, w - lw)))]
    out += url_lines("", "token", tr["mint"])
    p = tr["pnl"]
    spend = tr["spend"] or 0
    out.append(kv("size", [(f"{spend / LAM:.4f} SOL", "val")] + ([(f"  (into the curve {tr['sol_in'] / LAM:.4f})", "lbl")] if ps and tr.get("sol_in") else []), lw))
    if p is not None:
        out.append(kv("P&L", money(r, p) + [(f"  {pct_s(p / spend) if spend else ''}", pnl_style(p))] +
                      ([("  feed estimate", "warn")] if tr.get("src") == "est" else []), lw))
    else:
        out.append(kv("P&L", [("not realized yet", "lbl")], lw))
    if ps:
        if tr.get("rent") is not None:
            out.append(kv("rent back", [(sol(tr["rent"]), "pos"), ("  (account closed; not in the P&L)" if w >= 56 else "  (not in P&L)", "lbl")], lw))
        ex = tr["exit"] or "open"
        out.append(kv("exit", [(ex, "val"), (f"  after {tr['slots']} slot(s)" if tr.get("slots") is not None else "", "lbl"),
                               (f"  held {tr['held_s']:.2f} s" if tr.get("held_s") else "", "lbl"), (f"  value x{tr['value']:.3f}" if tr.get("value") else "", "lbl")], lw))
        out.append(kv("landed", [(f"{kind_of(tr['client'])}", "val"), (f" ({tr['client']})", "lbl"), (f"  path {tr['path']}", "lbl")], lw))
        bits = []
        if tr.get("trig_pct") is not None:
            bits.append(f"whale {tr['trig_pct']:.1f}%" + (f" ({tr['trig_sol'] / LAM:.2f} SOL)" if tr.get("trig_sol") else ""))
        if tr.get("after") is not None:
            bits.append(f"+{tr['after']} slots after the trigger")
        if tr.get("ms") is not None:
            bits.append(f"send>seen {tr['ms']:.0f} ms")
        if tr.get("nfills", 1) > 1:
            bits.append(f"{tr['nfills']} fills merged")
        for i, ln in enumerate(wrap_text(f" {G['sep']} ".join(bits), max(10, w - lw))):
            out.append(kv("timing" if i == 0 else "", [(ln, "val")], lw))
        for i, s_ in enumerate(tr["buy_sigs"]):
            out += url_lines("buy" if i == 0 else "", "tx", s_)
        for i, s_ in enumerate(tr["sell_sigs"]):
            out += url_lines("sell" if i == 0 else "", "tx", s_)
    else:
        res = tr["res"]
        resd = {"filled": "filled", "guard": "failed: price guard 6042", "lighthouse": "failed: Lighthouse slot guard 6001",
                "failed": "failed on chain", "open": "in flight", "not landed": "never landed"}.get(res, res)
        out.append(kv("result", [(resd, "warn" if res in ("guard", "lighthouse", "failed") else "val"), ("  dev list" if tr["dev"] else "", "acc")], lw))
        c = tr["close"] or {}
        if res == "filled":
            why = c.get("why") or (tr["exit"] or {}).get("why") or "holding"
            out.append(kv("exit", [(why, "val"), (f"  after {trade_held(tr)}" if trade_held(tr) else "", "lbl"),
                                   (f"  held {c['held_s']:.2f} s" if c.get("held_s") else "", "lbl")], lw))
        out.append(kv("leader", [(kind_of(tr["client"]), "val"), (f" ({tr['client']})", "lbl"), (f"  {tr['leader'][:8]}", "lbl"),
                                 (f"  {tr['route'].replace('route:', '')}", "lbl")], lw))
        bits = []
        if tr["land"]:
            ld = tr["land"]
            if ld.get("via"):
                bits.append(f"landed via {ld['via']}")
            if ld.get("blk") is not None:
                bits.append("dump's block" if ld["blk"] == 0 else f"+{ld['blk']} block(s)")
            if ld.get("ms") is not None:
                bits.append(f"{ld['ms']:.0f} ms after the dump")
        elif tr["failed"] and tr["failed"].get("via"):
            bits.append(f"failed copy via {tr['failed']['via']}")
        if tr["dec_us"] is not None:
            bits.append(f"decision {tr['dec_us']:.0f} us")
        tm = tr["timing"] or {}
        if tm.get("reaction_ms") is not None:
            bits.append(f"reaction {tm['reaction_ms']:.2f} ms")
        if tm.get("exec_lag_ms") is not None:
            bits.append(f"exec lag {tm['exec_lag_ms']:.2f} ms")
        if tm.get("fire_to_seen_ms") is not None:
            bits.append(f"fire>seen {tm['fire_to_seen_ms']:.0f} ms")
        for i, ln in enumerate(wrap_text(f" {G['sep']} ".join(bits) or G["dash"], max(10, w - lw))):
            out.append(kv("timing" if i == 0 else "", [(ln, "val")], lw))
        out += url_lines("dump", "tx", tr["dump_sig"])
        bsig = (tr["land"] or tr["failed"] or {}).get("sig") or tr["buy_sig"]
        out += url_lines("buy", "tx", bsig)
        sells = c.get("sell_sigs") or [x.get("sig") for x in tr["sells"] if x.get("sig")]
        for i, s_ in enumerate(dict.fromkeys(sells)):
            out += url_lines("sell" if i == 0 else "", "tx", s_)
    out.append([])
    out.append([("Esc back", "lbl")])
    return out


HELP = [
    ("1-7 Tab", "switch tabs (Overview, Pre-send, Regular, Trades, Health, Log, Config); Shift-Tab back"),
    ("Arrows PgUp/Dn", "scroll / move the selection"),
    ("Home End", "top / bottom (Log: End follows the tail again)"),
    ("Enter", "Trades: details of the selected trade (mint, signatures, solscan links)"),
    ("Esc", "back"),
    ("f", "Trades: all / pre-send / regular / wins / losses / open   Log: important / all"),
    ("w", "Log: wrap long lines"),
    ("s", "scope: all sessions / one session (runs restarted into the same log)"),
    ("u", "swap the primary unit (SOL / USD)"),
    ("p", "pause the screen (data keeps loading)"),
    ("r", "refresh the SOL/USD price now"),
    ("+ -", "refresh faster / slower (0.5 - 5 s)"),
    ("? q", "this help / quit"),
    ("", ""),
    ("RUN P&L", "pre-send net + regular, after every fee; the same accounting as the run reports"),
    ("pre-send net", "realized (chain txs of each buy + sell) + token-account rent back - failed-attempt fees"),
    ("regular", "the engine's REALIZED P&L of each fill + each failed buy at its tx fee (~ = feed estimate until REALIZED)"),
    ("wallet est.", "the session's START BALANCE + its P&L (no RPC: an estimate; unseen tries' fees are not in it)"),
    ("kill sw.", "how far the wallet is above the engine's kill switch (START BALANCE - loss cap)"),
    ("badges", "green = on, yellow = warming up / partial / stopped, red = off"),
]


def scr_help(r, bh):
    w = r.w
    out = [head("HELP", w, right=[(f"dipmon {VERSION}", "lbl")])]
    kw = 18 if w >= 70 else 13
    for k, d in HELP:
        if not k and not d:
            out.append([])
            continue
        lines = wrap_text(d, max(10, w - kw - 1))
        kk = ("Arrows" if k.startswith("Arrows") and w < 70 else k)
        out.append([(kk.ljust(kw)[:kw] + " ", "accb" if k.isupper() or k[:1].isdigit() else "acc"), (lines[0], "val")])
        for ln in lines[1:]:
            out.append([(" " * (kw + 1) + ln, "val")])
    out.append([])
    out.append([("read-only: run files, the budget file and /proc; no RPC; the price from Binance / CoinGecko", "lbl")])
    return out


# ---------------------------------------------------------------- frame
def header_line(r):
    v = r.v
    app = r.app
    w = r.w
    reg = f"{v.region} r{v.run}" if v.run is not None else os.path.basename(app.ctx.src.jsonl)[:20]
    st = status_style(v)
    dot = (G["on"] if not G.get("ascii") else "*", st)
    if r.narrow:
        left = [(" " + reg + " ", "accb"), dot, (" ", "val")]
        left += [(sol(v.total, 4) + " SOL", pnl_style(v.total, True))]
        if v.price and w >= 44:
            left += [("  " + usd(v.total, v.price), pnl_style(v.total))]
        right = [("PAUSED ", "warn")] if app.paused else []
        return lr(left, right, w)
    left = [(" " + reg + " ", "accb"), (v.build + " ", "lbl"), dot, (" " + v.status, st)]
    if app.tab != 0 or app.detail is not None or app.help:
        left += [("   ", "val"), (sol(v.total, 4) + " SOL", pnl_style(v.total, True))]
        if v.price:
            left += [("  " + usd(v.total, v.price), pnl_style(v.total))]
    right = []
    if app.paused:
        right += [("PAUSED  ", "warn")]
    if v.price:
        right += [("SOL ", "lbl"), (f"${v.price:,.2f}", "val"), (f" {age_s(v.price_age)} " if v.price_age is not None else " fixed ", "lbl")]
    else:
        right += [("USD n/a ", "lbl")]
    return lr(left, right, w)


def tabbar_line(r):
    app = r.app
    w = r.w
    names = TABS if w >= 80 else TABS_SHORT
    L = []
    for i, nm in enumerate(names):
        seg = f" {i + 1} {nm} " if w >= 44 else f" {i + 1}{nm[0]} "
        L.append((seg, "sel" if i == app.tab else "lbl"))
    right = []
    v = r.v
    if v.nsess > 1:
        right.append((("all sessions" if v.scope is None else f"session {v.scope + 1}/{v.nsess}") + " ", "acc"))
    if slen(L) + slen(right) > w:
        right = []
    return lr(L, right, w)


def alerts_line(r):
    v = r.v
    w = r.w
    if not v.alerts:
        return [((G["ok"] + " ") if not G.get("ascii") else "", "good"), ("all clear", "lbl")]
    L = []
    shown = 0
    for lvl, text in v.alerts:
        sym = {"bad": G["up"], "warn": G["up"], "end": G["dia"]}.get(lvl, G["tri"])
        st = {"bad": "bad", "warn": "warn", "end": "acc"}.get(lvl, "lbl")
        seg = [(sym + " ", st), (text, st)]
        if L and slen(L) + 3 + slen(seg) > w - 6:
            break
        L += ([("  ", "val")] if L else []) + seg
        shown += 1
    if shown < len(v.alerts):
        L.append((f"  +{len(v.alerts) - shown}", "lbl"))
    return fit(L, w)


def footer_line(r):
    app = r.app
    w = r.w
    ud = "Up/Down" if G.get("ascii") else "\u2191\u2193"
    if app.detail is not None:
        keys = "Esc back  u $/SOL  q quit"
    elif app.help:
        keys = "any key closes  q quit"
    elif app.tab == 3:
        keys = f"{ud} select  Enter details  f filter  u $/SOL  p pause  ? help  q quit" if w >= 80 else f"{ud} Enter  f filter  ? help  q quit"
    elif app.tab == 5:
        keys = f"{ud} scroll  End follow  f all/important  w wrap  ? help  q quit" if w >= 80 else "f all/imp  w wrap  ? help  q quit"
    elif w >= 100:
        keys = f"1-7 tabs  {ud} scroll  u $/SOL  p pause  s scope  r price  +/- rate  ? help  q quit"
    elif w >= 80:
        keys = f"1-7 tabs  {ud} scroll  u $/SOL  p pause  ? help  q quit"
    else:
        keys = "1-7 tabs  u $/SOL  ? help  q quit"
    more = getattr(app, "_more", "")
    right = ([(more + "  ", "acc")] if more else []) + [(f"{app.interval:g}s ", "lbl")]
    if slen(right) + len(keys) + 2 > w and more:
        keys = keys[: max(0, w - slen(right) - 3)]
    return lr([(" " + keys, "lbl")], right, w)


def body_lines(r, bh):
    app = r.app
    if app.help:
        return scr_help(r, bh), True
    if app.detail is not None:
        return scr_detail(r, bh, app.detail), True
    t = app.tab
    if t == 0:
        return scr_overview(r, bh), True
    if t == 1:
        return scr_presend(r, bh), True
    if t == 2:
        return scr_regular(r, bh), True
    if t == 3:
        return scr_trades(r, bh), False
    if t == 4:
        return scr_health(r, bh), True
    if t == 5:
        return scr_log(r, bh), False
    return scr_config(r, bh), True


def render(app, cv, w, h):
    if h < 10 or w < 36:
        cv.put(0, 0, "terminal too small"[:w], "warn")
        cv.put(1, 0, f"need 36x10, have {w}x{h}"[:w], "lbl")
        return
    r = R(app, w, h)
    bh = h - 4
    draw_line(cv, 0, header_line(r), w)
    draw_line(cv, 1, tabbar_line(r), w)
    lines, scrolls = body_lines(r, bh)
    key = "help" if app.help else ("detail" if app.detail is not None else app.tab)
    off = app.scroll.get(key, 0) if scrolls else 0
    if scrolls:
        off = max(0, min(off, max(0, len(lines) - bh)))
        app.scroll[key] = off
        app._maxscroll = max(0, len(lines) - bh)
    for i, L in enumerate(lines[off:off + bh]):
        draw_line(cv, 2 + i, L, w)
    app._more = ""
    if scrolls and len(lines) > bh:
        left = len(lines) - bh - off
        app._more = f"{G['down']} {left} more" if left > 0 else f"{G['up']} Home"
    draw_line(cv, h - 2, alerts_line(r), w)
    draw_line(cv, h - 1, footer_line(r), w)


def render_loading(app, cv, w, h, frac, label):
    cv.put(0, 0, (" dipmon " + VERSION)[:w], "accb")
    y = max(2, h // 2 - 2)
    msg = f"loading {frac * 100:.0f}%  {label}"
    cv.put(y, 2, msg[: w - 4], "val")
    gw = max(10, min(60, w - 4))
    k = int(round(frac * gw))
    cv.put(y + 1, 2, (G["bar"] * k)[: w - 4], "acc")
    cv.put(y + 1, 2 + k, (G["bar0"] * (gw - k))[: max(0, w - 4 - k)], "dim")
    cv.put(y + 3, 2, "read-only; chunked, the CPU is yielded between chunks (q quits)"[: w - 4], "lbl")


# ------------------------------------------------------------------------------------------------------------------ app
LOAD_CHUNK = 512 * 1024
TICK_BYTES = 4 * 1024 * 1024


class App:
    def __init__(self, ctx, args):
        self.ctx = ctx
        self.args = args
        self.tab = 0
        self.scroll = {}
        self.sel = 0
        self.top = 0
        self.tfilter = 0
        self.detail = None
        self.help = False
        self.usd_first = False
        self.paused = False
        self.interval = max(0.5, min(5.0, args.interval))
        self.scope = None
        self.log_all = False
        self.log_wrap = False
        self.log_off = 0
        self.view = None
        self._tlist = []
        self._maxscroll = 0
        self.ui_err = None
        self.ui_errs = 0

    def refresh_view(self, force=False):
        if self.paused and not force and self.view is not None:
            return
        self.view = build_view(self.ctx, self.scope)

    def key(self, ch):
        """one key; False = quit"""
        import curses
        if ch in (ord("q"), ord("Q")):
            return False
        if self.help:
            self.help = False
            return True
        if ch == ord("?"):
            self.help = True
            return True
        if ch == 27:
            self.detail = None
            return True
        page = max(1, (curses.LINES if hasattr(curses, "LINES") else 24) - 6)
        if ord("1") <= ch <= ord("7"):
            self.tab = ch - ord("1")
            self.detail = None
        elif ch == 9:
            self.tab = (self.tab + 1) % len(TABS)
            self.detail = None
        elif ch == getattr(curses, "KEY_BTAB", 353):
            self.tab = (self.tab - 1) % len(TABS)
            self.detail = None
        elif ch == ord("u"):
            self.usd_first = not self.usd_first
        elif ch == ord("p"):
            self.paused = not self.paused
            if not self.paused:
                self.refresh_view(force=True)
        elif ch == ord("r"):
            if self.ctx.price:
                self.ctx.price.refresh()
        elif ch in (ord("+"), ord("=")):
            steps = [0.5, 1.0, 2.0, 3.0, 5.0]
            self.interval = max([x for x in steps if x < self.interval] or [0.5])
        elif ch in (ord("-"), ord("_")):
            steps = [0.5, 1.0, 2.0, 3.0, 5.0]
            self.interval = min([x for x in steps if x > self.interval] or [5.0])
        elif ch == ord("s"):
            n = len(self.ctx.src.model.sessions)
            if n > 1:
                self.scope = 0 if self.scope is None else (None if self.scope + 1 >= n else self.scope + 1)
                self.refresh_view(force=True)
        elif ch in (ord("f"), ord("i")):
            if self.tab == 3 and self.detail is None:
                self.tfilter = (self.tfilter + 1) % len(FILTERS)
                self.sel = self.top = 0
            elif self.tab == 5:
                self.log_all = not self.log_all
                self.log_off = 0
        elif ch == ord("w"):
            if self.tab == 5:
                self.log_wrap = not self.log_wrap
        elif ch in (10, 13, getattr(curses, "KEY_ENTER", 343)):
            if self.tab == 3 and self.detail is None and self._tlist:
                self.detail = self._tlist[min(self.sel, len(self._tlist) - 1)]
                self.scroll["detail"] = 0
        else:
            self._scroll_key(ch, page)
        return True

    def _scroll_key(self, ch, page):
        import curses
        up, down = (curses.KEY_UP, ord("k")), (curses.KEY_DOWN, ord("j"))
        d = 0
        if ch in up:
            d = -1
        elif ch in down:
            d = 1
        elif ch == curses.KEY_PPAGE:
            d = -page
        elif ch == curses.KEY_NPAGE:
            d = page
        home = ch in (curses.KEY_HOME, ord("g"))
        end = ch in (curses.KEY_END, ord("G"))
        if not (d or home or end):
            return
        if self.tab == 3 and self.detail is None and not self.help:
            n = len(self._tlist)
            self.sel = 0 if home else (max(0, n - 1) if end else max(0, min(n - 1, self.sel + d)))
        elif self.tab == 5 and self.detail is None and not self.help:
            self.log_off = 10 ** 9 if home else (0 if end else max(0, self.log_off - d))
        else:
            key = "help" if self.help else ("detail" if self.detail is not None else self.tab)
            cur = self.scroll.get(key, 0)
            self.scroll[key] = 0 if home else (10 ** 9 if end else max(0, cur + d))


def init_styles(no_color):
    import curses
    A, D, RV, U = curses.A_BOLD, curses.A_DIM, curses.A_REVERSE, curses.A_UNDERLINE
    mono = {"lbl": D, "dim": D, "val": 0, "b": A, "pos": A, "neg": A | U, "posb": A, "negb": A | U, "acc": A, "accb": A,
            "warn": A, "bad": A | RV, "good": 0, "sel": RV | A, "banner": RV | A}
    if no_color:
        return mono
    try:
        if not curses.has_colors():
            return mono
        curses.start_color()
        try:
            curses.use_default_colors()
            bg = -1
        except curses.error:
            bg = curses.COLOR_BLACK
        n = curses.COLORS
        if n >= 256:
            gray, dimc, green, red, yellow, acc, black = 245, 240, 78, 203, 179, 75, 16
        else:
            gray, dimc, green, red, yellow, acc, black = -1, -1, curses.COLOR_GREEN, curses.COLOR_RED, curses.COLOR_YELLOW, curses.COLOR_CYAN, curses.COLOR_BLACK

        def pair(i, fg, b=bg):
            curses.init_pair(i, fg, b)
            return curses.color_pair(i)
        lbl, dim = pair(1, gray), pair(2, dimc)
        pos, neg, warn, accp = pair(3, green), pair(4, red), pair(5, yellow), pair(6, acc)
        sel = pair(7, black, acc)
        xd = D if n < 256 else 0
        return {"lbl": lbl | xd, "dim": dim | xd, "val": 0, "b": A, "pos": pos, "neg": neg, "posb": pos | A, "negb": neg | A, "acc": accp,
                "accb": accp | A, "warn": warn, "bad": neg | A, "good": pos, "sel": sel | A, "banner": sel | A}
    except Exception:
        return mono


def curses_main(scr, app):
    import curses
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    scr.keypad(True)
    attrs = init_styles(app.args.no_color)
    ctx = app.ctx
    src = ctx.src
    total = max(1, src.total_bytes())
    loading = not src.loaded
    t_next = 0.0
    last_draw = 0.0
    dirty = True
    while True:
        now = time.time()
        if loading:
            t0 = time.time()
            n = src.step(LOAD_CHUNK)
            work = time.time() - t0
            total = max(total, src.done_bytes() + src.tj.pending() + src.tl.pending())
            if not n and not src.tj.pending() and not src.tl.pending():
                loading = False
                src.loaded = True
                ctx.engine.sample()
                ctx.sys.sample(force=True)
                app.refresh_view(force=True)
                dirty = True
                t_next = time.time() + app.interval
            elif now - last_draw > 0.25:
                scr.erase()
                h, w = scr.getmaxyx()
                render_loading(app, CursesCanvas(scr, attrs), w, h, min(1.0, src.done_bytes() / total),
                               f"{src.done_bytes() / 1e6:,.1f} / {total / 1e6:,.1f} MB")
                scr.noutrefresh()
                curses.doupdate()
                last_draw = now
            scr.timeout(max(2, int(work * 1000 * app.args.load_duty)))
        else:
            if now >= t_next:
                t_next = now + app.interval
                src.step(TICK_BYTES)
                if src.tj.pending() or src.tl.pending():
                    t_next = now + 0.05
                ctx.engine.sample()
                ctx.sys.sample()
                if not app.paused:
                    app.refresh_view()
                    dirty = True
                if not src.loaded:                                     # the files were truncated / replaced: reload
                    loading = True
                    total = max(1, src.total_bytes())
            scr.timeout(max(10, min(250, int((t_next - time.time()) * 1000))))
        if dirty and not loading:
            scr.erase()
            h, w = scr.getmaxyx()
            cv = CursesCanvas(scr, attrs)
            try:
                render(app, cv, w, h)
            except Exception as e:
                app.ui_errs += 1
                app.ui_err = f"{type(e).__name__}: {e}"
                if app.args.strict:
                    raise
                cv.put(h - 1, 0, ("UI ERROR " + app.ui_err)[: w - 1], "bad")
            scr.noutrefresh()
            curses.doupdate()
            dirty = False
            last_draw = time.time()
        try:
            ch = scr.getch()
        except KeyboardInterrupt:
            break
        if ch == -1:
            continue
        if ch == curses.KEY_RESIZE:
            try:
                curses.update_lines_cols()
            except Exception:
                pass
            dirty = True
            continue
        if not app.key(ch):
            break
        if app.view is None:
            app.refresh_view(force=True)
        dirty = True


# ------------------------------------------------------------------------------------------------------------------ snapshot
def snapshot_text(v, ctx, width=110):
    out = []
    S = v.cur
    u = v.price
    region = f"{v.region} run {v.run}" if v.run is not None else os.path.basename(ctx.src.jsonl)
    end = f" {pkt(v.t_end, '%H:%M')} PKT ({v.how_ended})" if v.status == "ENDED" and v.t_end else (f" ({v.how_ended})" if v.how_ended else "")
    out.append(f"dipmon snapshot  {region}  ({v.build})  {v.status}{end}")
    out.append(f"files     {ctx.src.jsonl} (+ .log)  {ctx.src.tj.size / 1e6:.1f} MB + {ctx.src.tl.size / 1e6:.1f} MB")
    plan = f" of {hms(v.planned * 60)} planned" if v.planned else ""
    out.append(f"started   {pkt(v.t_first, '%Y-%m-%d %H:%M:%S')} PKT   ran {hms(v.elapsed)}{plan}   sessions {v.nsess}"
               + (f"   ends {pkt(v.ends_at, '%H:%M')} PKT" if v.running and v.ends_at else ""))
    out.append(f"SOL/USD   " + (f"${u:,.2f} ({v.price_src}" + (f", {age_s(v.price_age)} old)" if v.price_age is not None else ")") if u else "n/a"))
    out.append("")
    ps, rg = v.ps, v.reg

    def m(lam):
        return f"{sol(lam)} SOL  {usd(lam, u) if u else 'USD n/a'}"
    out.append(f"RUN P&L   {m(v.total):<32}  per hour " + (m(int(v.per_hour)) if v.per_hour is not None else G["dash"]))
    if ps["active"]:
        out.append(f"pre-send  {m(ps['net']):<32}  {ps['fills']} fills, {ps['wins']} wins | realized {sol(ps['real'])}, rent back {sol(ps['rent'])}, "
                   f"failed tries {sol(-ps['fees'])} ({ps['fee_n']:,} x {v.ps_fail_each:,})")
        if ps.get("all_stopped") and ps["fees_eng"]:
            d = ps["fees_eng"] - ps["fees_cnt"]
            out.append(f"          failed-try fees: counted {ps['fees_cnt'] / LAM:.6f}, engine at the end {ps['fees_eng'] / LAM:.6f} "
                       + ("(match)" if abs(d) < v.ps_fail_each else f"(differ by {d / LAM:+.6f})"))
        elif ps["fees_eng"]:
            out.append(f"          failed-try fees: counted {ps['fees_cnt'] / LAM:.6f}, engine {ps['fees_eng'] / LAM:.6f} at its last 60 s status line")
    else:
        out.append("pre-send  off")
    nf = rg["guard"] + rg["lighthouse"] + rg["failed"]
    out.append(f"regular   {m(rg['total']):<32}  {rg['fires']} buys, {rg['fills']} fills, {rg['wins']} wins | fills {sol(rg['fill_pnl'])}, failed buys "
               f"{sol(rg['fail_pnl'])} ({nf}: 6042 {rg['guard']}, 6001 {rg['lighthouse']}, other {rg['failed']})" + (f", {rg['open']} open" if rg["open"] else "")
               + (f", {rg['est']} on the feed estimate" if rg["est"] else ""))
    if v.est_now is not None:
        out.append(f"wallet    start {v.start_bal / LAM:.4f}  now {v.est_now / LAM:.4f} est." +
                   (f"  kill switch below {v.kill_level / LAM:.4f} ({v.kill_dist / LAM:.3f} SOL away)" if v.kill_level is not None else "") +
                   (f"  budget left {v.budget_left / LAM:.3f}" if v.budget_left is not None else ""))
    if v.best:
        out.append(f"P&L line  hi {sol(v.best[0], 3)} {pkt(v.best[1], '%H:%M')}  lo {sol(v.worst[0], 3)} {pkt(v.worst[1], '%H:%M')}  now {sol(v.total, 3)}")
    if ps["active"]:
        cap = v.ps_cfg.get("max_fills")
        bud = v.ps_cfg.get("fee_budget")
        sf, sfee = (S.ps_fills, S.ps_fees())
        out.append(f"caps      pre-send fills {sf}/{cap or '?'}, fee budget {sfee / LAM:.4f}/{(bud or 0) / LAM:.4f} SOL" +
                   (f", stopped ({v.ps_stopped})" if v.ps_stopped else "") + f", windows armed now {v.ps_open_now}")
        if ps["paper"]:
            out.append(f"paper     row c {ps['paper_fills']} fills, gross {ps['paper_gross']:+.3f}, net {ps['paper_net']:+.3f} SOL  vs live {ps['fills']} fills, net {sol(ps['net'], 3)}")
    q = v.quiet
    if q["present"]:
        ki = next((x for x in v.cfg_items if x["key"] == "qskip"), None)
        out.append(f"QUIET     stop {q['stop']}, skip rule: {ki['full'] if ki else '?'}; skips {ps['q_skips']}, stops {ps['q_stops']}, would-skip {ps['q_would']}")
    strip = "  ".join((BADGE_ASCII.get(it["state"], "") + " " if it["state"] != "na" else "") + it["short"] for it in v.cfg_items)
    for i, ln in enumerate(wrap_text(strip, width - 10)):
        out.append(("config    " if i == 0 else "          ") + ln)
    out.append("          (+ on, ~ partial / warming up, - off)")
    if v.nsess > 1:
        out.append("")
        out.append("sessions  #  start    P&L SOL   pre-send    regular  end")
        for X in v.sessions:
            e = pkt(X.t_end(), "%H:%M") if X.t_end() else ("now" if X is v.cur and v.running else "?")
            out.append(f"          {X.idx + 1:<2} {pkt(X.t0, '%H:%M'):<6} {sol(X.total()):>9}  {sol(X.ps_net()):>9}  {sol(X.reg_total()):>9}  {e}")
    out.append("")
    out.append("last trades (PKT, newest first; P&L = realized, ~ = feed estimate):")
    for tr in sorted_trades(v)[:8]:
        p = tr["pnl"]
        sp = tr["spend"] or 0
        out.append(f"  {pkt(tr['t'])} {'PS ' if tr['kind'] == 'PS' else 'REG'} {short(tr['mint'], 8)}  {sp / LAM:.2f}  "
                   f"{(sol(p) + ('~' if tr.get('src') == 'est' else ' ')) if p is not None else '-':>9} {usd(p, u) if (p is not None and u) else '':>9}  "
                   f"{pct_s(p / sp) if (p is not None and sp) else '':>7}  {trade_exit(tr):<5} {kind_of(tr['client'])}")
    out.append("")
    if v.alerts:
        for lvl, text in v.alerts:
            out.append(f"{'ALERT' if lvl == 'bad' else ('warn' if lvl == 'warn' else 'note'):<9} {text}")
    else:
        out.append("alerts    none")
    return "\n".join(out)


def snapshot_json(v, ctx):
    ps, rg = v.ps, v.reg
    d = dict(region=v.region, run=v.run, file=ctx.src.jsonl, status=v.status, how_ended=v.how_ended, build=v.build, sessions=v.nsess,
             started=v.t_first, ended=v.t_end if v.status == "ENDED" else None, elapsed_s=v.elapsed, planned_min=v.planned,
             sol_usd=v.price, total_lamports=v.total, total_sol=v.total / LAM, per_hour_sol=(v.per_hour / LAM if v.per_hour is not None else None),
             presend=dict(active=ps["active"], fills=ps["fills"], wins=ps["wins"], realized=ps["real"], rent=ps["rent"], fees=ps["fees"],
                          fees_counted=ps["fees_cnt"], fees_engine=ps["fees_eng"], failed_tries=ps["fee_n"], net=ps["net"], sent=ps["sent"],
                          results=dict(ps["res"]), armed=ps["armed"], skips=dict(ps["skips"]), disarms=dict(ps["disarms"]),
                          exits={k: dict(n=x[0], wins=x[1], pnl=x[2]) for k, x in ps["exits"].items()}, quiet_skips=ps["q_skips"],
                          quiet_stops=ps["q_stops"], quiet_would=ps["q_would"], paper_fills=ps["paper_fills"], paper_net=ps["paper_net"],
                          stopped=v.ps_stopped, open_windows=v.ps_open_now),
             regular=dict(fires=rg["fires"], fills=rg["fills"], wins=rg["wins"], guard_6042=rg["guard"], lighthouse_6001=rg["lighthouse"],
                          failed_other=rg["failed"], open=rg["open"], fill_pnl=rg["fill_pnl"], failed_pnl=rg["fail_pnl"], total=rg["total"],
                          estimated=rg["est"], exits={k: dict(n=x[0], wins=x[1], pnl=x[2]) for k, x in rg["exits"].items()},
                          by_client={k: dict(buys=x[0], fills=x[1], wins=x[2], pnl=x[3]) for k, x in rg["kinds"].items()}),
             wallet=dict(start=v.start_bal, est_now=v.est_now, kill_level=v.kill_level, kill_distance=v.kill_dist, budget_left=v.budget_left),
             quiet=dict(v.quiet), config={it["key"]: dict(state=it["state"], short=it["short"]) for it in v.cfg_items},
             alerts=[dict(level=a, text=t) for a, t in v.alerts],
             per_session=[dict(n=X.idx + 1, start=X.t0, end=X.t_end(), start_balance=X.start_bal, **session_totals(X)) for X in v.sessions],
             series_hi=v.best, series_lo=v.worst)
    return json.dumps(d, default=str, indent=1)


def dump_screens(app, outdir, sizes, tag="", only=None):
    """text screenshots of every tab (and help + a trade's details) at each size"""
    os.makedirs(outdir, exist_ok=True)
    written = []
    for (w, h) in sizes:
        pages = [(i, TABS[i].lower().replace("-", "")) for i in range(len(TABS))] + [("help", "help"), ("detail", "detail")]
        if only:
            pages = [pg for pg in pages if pg[1] in only or str(pg[0] + 1 if isinstance(pg[0], int) else pg[0]) in only]
        for key, name in pages:
            app.help = key == "help"
            app.detail = None
            app.tab = key if isinstance(key, int) else (3 if key == "detail" else 0)
            if key == "detail":
                tl = sorted_trades(app.view)
                cand = [t for t in tl if t["kind"] == "PS" and t["pnl"] is not None] or tl
                if not cand:
                    continue
                app.detail = cand[0]
            app.scroll = {}
            cv = TextCanvas(h, w)
            render(app, cv, w, h)
            fn = os.path.join(outdir, f"{w}x{h}_{'0' + str(key + 1) if isinstance(key, int) else ('8' if key == 'help' else '9')}-{name}{'-' + tag if tag else ''}.txt")
            with open(fn, "w") as f:
                f.write(cv.dump() + "\n")
            written.append(fn)
    app.help = False
    app.detail = None
    app.tab = 0
    return written


# ------------------------------------------------------------------------------------------------------------------ main
def find_run(args):
    if args.file:
        return args.file
    d = args.dir
    if args.run is not None:
        cands = []
        for rg in ([args.region] if args.region else ["ams", "fra"]):
            tag = f"dip_ams_r{args.run}" if rg == "ams" else f"dip_r{args.run}"
            p = os.path.join(d, tag + ".jsonl")
            if os.path.exists(p) or os.path.exists(p[:-6] + ".log"):
                cands.append(p)
        if len(cands) == 1:
            return cands[0]
        if len(cands) > 1:
            sys.exit(f"dipmon: both dip_ams_r{args.run} and dip_r{args.run} are in {d}: pass --region ams|fra")
        if not os.access(d, os.R_OK | os.X_OK):
            sys.exit(f"dipmon: cannot read {d} (the run files are root-only: sudo dipmon ...)")
        sys.exit(f"dipmon: no run {args.run} in {d}")
    eng = [e for e in Engine.find_all()]
    if eng:
        eng.sort(key=lambda e: os.path.getmtime(e[1]) if os.path.exists(e[1]) else 0, reverse=True)
        return eng[0][1]
    try:
        files = [os.path.join(d, f) for f in os.listdir(d) if RUN_RX.match(f)]
    except PermissionError:
        sys.exit(f"dipmon: cannot read {d} (the run files are root-only: sudo dipmon ...)")
    except FileNotFoundError:
        sys.exit(f"dipmon: no {d} here; pass --dir DIR, --file X.jsonl or --run N")
    if not files:
        sys.exit(f"dipmon: no running engine and no dip_*rN.jsonl in {d}")
    return max(files, key=os.path.getmtime)


def setup_terminal(args):
    """TERM may be unset under sudo; the locale may not be UTF-8: fall back to ASCII glyphs"""
    os.environ.setdefault("ESCDELAY", "25")
    t = os.environ.get("TERM", "")
    if not t or t == "dumb":
        os.environ["TERM"] = "xterm-256color"
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        pass
    enc = (locale.nl_langinfo(locale.CODESET) if hasattr(locale, "nl_langinfo") else "") or ""
    if "UTF-8" not in enc.upper() and "UTF8" not in enc.upper():
        for loc in ("C.UTF-8", "en_US.UTF-8"):
            try:
                locale.setlocale(locale.LC_ALL, loc)
                enc = locale.nl_langinfo(locale.CODESET)
                break
            except (locale.Error, AttributeError):
                continue
    if "UTF" not in (enc or "").upper():
        args.ascii = True


def parse_args(argv=None):
    ap = argparse.ArgumentParser(prog="dipmon", description="read-only live monitor for a dip-bot run (the engine's .jsonl + .log)")
    ap.add_argument("--file", help="a run's records (X.jsonl); its .log is read from next to it")
    ap.add_argument("--log", help="the text log (default: the .jsonl's name with .log)")
    ap.add_argument("--run", type=int, help="run number N: <dir>/dip_ams_rN or dip_rN")
    ap.add_argument("--region", choices=["ams", "fra"], help="with --run")
    ap.add_argument("--dir", default=DEFAULT_DIR, help=f"run files directory (default {DEFAULT_DIR})")
    ap.add_argument("--budget", help="the dip budget file (default: <dir>/../dip_budget_ams.json or dip_budget.json)")
    ap.add_argument("--snapshot", action="store_true", help="print a plain-text summary and exit (no curses)")
    ap.add_argument("--json", action="store_true", help="with --snapshot: JSON instead of text")
    ap.add_argument("--usd", type=float, help="fixed SOL/USD price (no network)")
    ap.add_argument("--no-usd", action="store_true", help="no price fetch (SOL only unless cached)")
    ap.add_argument("--ascii", action="store_true", help="ASCII only (no Unicode glyphs)")
    ap.add_argument("--no-color", action="store_true", help="monochrome")
    ap.add_argument("--interval", type=float, default=1.0, help="refresh seconds, 0.5-5 (default 1)")
    ap.add_argument("--load-duty", type=float, default=1.0, help="initial load: sleep this many times each chunk's work time (default 1 = at most ~50%% of a core)")
    ap.add_argument("--screens", metavar="DIR", help="write text screenshots of every tab to DIR and exit")
    ap.add_argument("--sizes", default="50x30,80x24,160x50", help="with --screens: WxH list")
    ap.add_argument("--screens-tag", default="", help=argparse.SUPPRESS)
    ap.add_argument("--screens-only", default="", help=argparse.SUPPRESS)
    ap.add_argument("--now", type=float, help=argparse.SUPPRESS)
    ap.add_argument("--assume-running", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--strict", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--exit-json", help=argparse.SUPPRESS)
    ap.add_argument("--version", action="version", version=f"dipmon {VERSION}")
    return ap.parse_args(argv)


def build_ctx(args):
    path = find_run(args)
    eng = Engine(path)
    eng.scan(force=True)
    fee = None
    if eng.alive:
        try:
            fee = 5_000 + int(eng.flags["--cu-limit"]) * int(eng.flags["--cu-price-micro"]) // 1_000_000
        except (KeyError, ValueError):
            fee = None
    src = Source(path, args.log, fee)
    region = (src.region or "").lower()
    budget = args.budget or os.path.join(os.path.dirname(os.path.abspath(path)), "..", "dip_budget_ams.json" if region == "ams" else "dip_budget.json")
    price = Price(fixed=args.usd, net=not args.no_usd)
    sysi = SysInfo(os.path.dirname(os.path.abspath(path)) or "/")
    ctx = Ctx(src, eng, price, sysi, budget if os.path.exists(budget) else None, now=args.now, assume_running=args.assume_running)
    return ctx


def main(argv=None):
    if sys.version_info < (3, 9):
        sys.exit("dipmon needs Python 3.9+")
    args = parse_args(argv)
    try:
        if os.nice(0) < 19:
            os.nice(19 - os.nice(0))
    except OSError:
        pass
    setup_terminal(args)
    set_ascii(args.ascii)
    ctx = build_ctx(args)
    src = ctx.src
    if not os.path.exists(src.jsonl) and not os.path.exists(src.log):
        sys.exit(f"dipmon: {src.jsonl} not found")
    if args.snapshot or args.screens:
        src.load_all(chunk=LOAD_CHUNK, duty=0.0 if args.screens else args.load_duty)
        ctx.engine.sample()
        time.sleep(0.25)
        ctx.engine.sample()
        ctx.sys.sample(force=True)
        if ctx.price.net and not ctx.price.usd and not args.screens:
            ctx.price.fetch_once(timeout=4.0)
        app = App(ctx, args)
        app.refresh_view(force=True)
        if args.screens:
            sizes = []
            for x in args.sizes.split(","):
                w_, h_ = x.lower().split("x")
                sizes.append((int(w_), int(h_)))
            only = set(x.strip() for x in args.screens_only.split(",") if x.strip()) or None
            for fn in dump_screens(app, args.screens, sizes, args.screens_tag, only):
                print(fn)
            return 0
        print(snapshot_json(app.view, ctx) if args.json else snapshot_text(app.view, ctx))
        return 0
    try:
        import curses
    except ImportError:
        sys.exit("dipmon: no curses in this Python (use --snapshot)")
    ctx.price.start()
    app = App(ctx, args)
    try:
        curses.wrapper(curses_main, app)
    except KeyboardInterrupt:
        pass
    if app.ui_errs:
        print(f"dipmon: {app.ui_errs} UI error(s); last: {app.ui_err}", file=sys.stderr)
    if args.exit_json:                       # tests: the curses session's own (incremental) numbers at exit
        with open(args.exit_json, "w") as f:
            f.write(snapshot_json(build_view(ctx), ctx))
    return 1 if app.ui_errs else 0


if __name__ == "__main__":
    sys.exit(main())
