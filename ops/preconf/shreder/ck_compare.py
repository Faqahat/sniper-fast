#!/usr/bin/env python3
"""ck_compare.py — Shreder (Binary + preconf) vs Constant-K, PER TRANSACTION, SAME MACHINE, SAME CLOCK (FRA).

Sources (all optional; a missing one is skipped with a note):
  <run-dir>/fra/bin_*.jsonl, pre_*.jsonl     Shreder pump-view records {"t","ca","s","sig","pf","p",...} (recorder contract)
  <run-dir>/fra/{bin,pre}_*.rec.gz           Shreder FULL dataset ('<IQqqQBBHI' header + tx bytes; first sig = tx[1:65]):
                                             used for misses vs chain truth and for pump txs the pump view's static-key
                                             filter left out (address-lookup-table only)
  <run-dir>/fra/events.jsonl                 recorder stream states (connected intervals; preconf has no data-gap rule)
  <run-dir>/ck/race_*.log                    Constant-K feed race on FRA (feed_race X lines: X feed t slot sig16hex create
                                             eidx created_at); feeds = what the engines use (kaldera, turbo-kaldera,
                                             kaldera-tx [, erpc])
  <run-dir>/engine/*.jsonl                   dip engine records (FRA = same clock; AMS = cross-machine, converted with
                                             fra/clock_{start,end}.json bracket.offset_ms = AMS minus FRA: INFERRED)
  --collect-root/run_*/txs/txs_*.jsonl.gz    chain truth (every pump.fun tx): trade typing + misses

Feeds compared on FRA: every race feed, CK_BEST (= first arrival over the race's Constant-K feeds: what an engine with
all of them sees), shreder_bin, shreder_pre. Engine-derived feeds (only the txs the engine logged): eng_exec (its
executed feed, kaldera-tx), eng_first (first over its feeds), eng:<feed> (per feed, fired dumps only).

Trade classes (chain truth, slot order): whale = the engine's pre-send T2 trigger (wallet's FIRST >= 3% crossing that
leaves it >= WHALE% of supply, not creator / create-slot insider, curve < 100 SOL, standard curve; tokens without a create
in the loaded chain: a single buy >= WHALE% of supply); dump = a sell >= 0.3 SOL; create; small = other trades;
failed; other (no pump trade); unknown (not in chain truth). WHALE% = the engine's presend whale_pct (6).

usage: python3 ck_compare.py --run-dir DIR [--engine F ...] [--engine-host auto|fra|ams] [--race F ...]
         [--collect-root DIR] [--from HH:MM --to HH:MM] [--whale-pct 6] [--dump-sol 0.3] [--no-rec] [--preroll-min 60]
Writes DIR/analysis/ck_compare.md + ck_compare.json; prints a short summary. Times in PKT (UTC+5).
"""
import argparse
import base64
import datetime as dt
import glob
import gzip
import json
import os
import re
import struct
import sys
import time
import zlib

PKT = dt.timezone(dt.timedelta(hours=5))
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMP_AMM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
TE = bytes([189, 219, 127, 211, 78, 230, 97, 238])     # pump TradeEvent
CE = bytes([27, 114, 169, 77, 222, 235, 99, 118])      # pump CreateEvent
SUPPLY = 1_000_000_000_000_000                         # raw units (1B tokens x 1e6)
HX = 30_000_000_000_000                                # 3% = a wallet becomes "big" (first crossing only)
UNTRADE_V = 100_000_000_000                            # curve >= 100 SOL: no trigger
FRA_WALLETS = {"2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
AMS_WALLETS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
SHR = ("shreder_bin", "shreder_pre")
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
B58I = {c: i for i, c in enumerate(B58)}
CLASSES = ("all", "whale", "dump", "small", "create")
NOTES = []


def note(s):
    NOTES.append(s)
    print("note:", s, file=sys.stderr)


def b58int(s):
    n = 0
    for c in s:
        n = n * 58 + B58I[c]
    return n


def b58enc(b):
    n = int.from_bytes(b, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = B58[r] + out
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + out


def k8_sig(sig):
    """first 8 bytes (big-endian int) of a base58 64-byte signature"""
    try:
        return b58int(sig) >> 448
    except (KeyError, TypeError):
        return None


def k8_b58_8(s):
    try:
        return b58int(s)
    except (KeyError, TypeError):
        return None


def pk(v):
    return None if v is None else round(v, 3)


def three(v):
    if not v:
        return {"n": 0}
    v = sorted(v)
    at = lambda q: v[int(round((len(v) - 1) * q))]
    return {"n": len(v), "p10": pk(at(0.1)), "p50": pk(at(0.5)), "p90": pk(at(0.9))}


def pkt(ns):
    return dt.datetime.fromtimestamp(ns / 1e9, PKT).strftime("%m-%d %H:%M:%S")


def jl(path):
    """stream a jsonl (plain or .gz); a truncated / bad line is skipped"""
    op = gzip.open if path.endswith(".gz") else open
    try:
        with op(path, "rt", errors="replace") as f:
            for line in f:
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
    except (OSError, EOFError, zlib.error) as e:
        note(f"{os.path.basename(path)}: read stopped ({type(e).__name__}: {e})")


class Feeds:
    """per feed: k8 -> earliest t (ns); shared k8 -> slot"""

    def __init__(self):
        self.t = {}
        self.slot = {}
        self.secs = {}      # feed -> set of whole seconds with data

    def add(self, feed, k, t, slot=None):
        d = self.t.setdefault(feed, {})
        o = d.get(k)
        if o is None or t < o:
            d[k] = t
        if slot and k not in self.slot:
            self.slot[k] = slot
        self.secs.setdefault(feed, set()).add(t // 1_000_000_000)


# ---------------------------------------------------------------- sources
def load_shreder(F, d, tmin, tmax, ptx):
    """pump-view jsonl -> F (shreder_bin / shreder_pre); ca kept for the provider-lag line; p kept for fallback typing"""
    ca = {"shreder_bin": [], "shreder_pre": []}
    pf = {"shreder_bin": [0, 0], "shreder_pre": [0, 0]}
    for st, feed in (("bin", "shreder_bin"), ("pre", "shreder_pre")):
        # the pump view only: <st>_YYYYMMDD_HH.jsonl (not the dataset's .idx.jsonl)
        files = sorted(p for p in glob.glob(os.path.join(d, f"{st}_*.jsonl")) if re.fullmatch(rf"{st}_\d{{8}}_\d{{2}}\.jsonl", os.path.basename(p)))
        if not files:
            note(f"no Shreder {st} pump-view files in {d}")
        for p in files:
            for r in jl(p):
                t, sig = r.get("t"), r.get("sig")
                if not t or not sig or t < tmin or t > tmax:
                    continue
                k = k8_sig(sig)
                if k is None:
                    continue
                F.add(feed, k, t, r.get("s"))
                if r.get("ca"):
                    ca[feed].append((t - r["ca"]) / 1e6)
                pf[feed][1 if r.get("pf") else 0] += 1
                if r.get("p") and k not in ptx:
                    ptx[k] = r["p"]
    return ca, pf


REC_HDR = struct.Struct("<IQqqQBBHI")


def rec_scan(path, want, tmin, tmax, slots_all=None):
    """full-dataset scan: k8 -> (earliest rx_ns, flags, slot) for k8 in `want`; returns (hits, n_records, n_preconf_flag);
    slots_all (a set) collects the slot of every record in [tmin, tmax]"""
    hits, n, npf = {}, 0, 0
    hs = REC_HDR.size
    mode = None
    try:
        with gzip.open(path, "rb") as f:
            buf = b""
            while True:
                chunk = f.read(16 << 20)
                if not chunk:
                    break
                buf = buf[0:] + chunk if buf else chunk
                o, L = 0, len(buf)
                while o + hs <= L:
                    rl, seq, rx, ca, slot, flags, nps, _r, tl = REC_HDR.unpack_from(buf, o)
                    if mode is None:
                        mode = "total" if rl == hs + tl else "after_len" if rl == hs - 4 + tl else "tx" if rl == tl else "?"
                        if mode == "?":
                            raise ValueError(f"rec_len {rl} vs tx_len {tl}: unknown framing")
                    end = o + hs + tl
                    if end > L:
                        break
                    n += 1
                    if flags & 1:
                        npf += 1
                    if tmin <= rx <= tmax:
                        if slots_all is not None:
                            slots_all.add(slot)
                        k = int.from_bytes(buf[o + hs + 1:o + hs + 9], "big")
                        if k in want:
                            h = hits.get(k)
                            if h is None or rx < h[0]:
                                hits[k] = (rx, flags, slot)
                    o = end
                buf = buf[o:]
    except (OSError, EOFError, zlib.error, struct.error, ValueError) as e:
        note(f"{os.path.basename(path)}: dataset scan stopped ({type(e).__name__}: {e}); trying read_rec.py" if mode in (None, "?")
             else f"{os.path.basename(path)}: dataset scan stopped ({type(e).__name__}: {e})")
        if mode in (None, "?"):
            try:
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                import read_rec   # the recorder agent's reader: iter_records(path) -> (seq, rx_ns, ca_ns, slot, flags, sig_b58, tx)
                for seq, rx, ca, slot, flags, sig, tx in read_rec.iter_records(path):
                    n += 1
                    npf += flags & 1
                    if tmin <= rx <= tmax:
                        k = int.from_bytes(tx[1:9], "big") if tx else k8_sig(sig)
                        if k in want:
                            h = hits.get(k)
                            if h is None or rx < h[0]:
                                hits[k] = (rx, flags, slot)
            except Exception as e2:   # noqa: BLE001 (a reader we do not own)
                note(f"{os.path.basename(path)}: read_rec.py fallback failed ({type(e2).__name__}: {e2})")
    return hits, n, npf


def load_race(F, files, tmin, tmax):
    feeds, created = [], {}
    for p in files:
        try:
            with open(p, "rb") as f:
                for raw in f:
                    if raw[:2] != b"X\t":
                        continue
                    x = raw.rstrip(b"\n").split(b"\t")
                    if len(x) < 6:
                        continue
                    try:
                        feed, t, slot, k = x[1].decode(), int(x[2]), int(x[3]), int(x[4], 16)
                    except ValueError:
                        continue
                    if t < tmin or t > tmax:
                        continue
                    if feed not in feeds:
                        feeds.append(feed)
                    F.add(feed, k, t, slot)
                    if len(x) >= 8 and x[7] not in (b"0", b"-"):
                        try:
                            created.setdefault(feed, []).append((t - int(x[7])) / 1e6)
                        except ValueError:
                            pass
        except OSError as e:
            note(f"race file {p}: {e}")
        # feeds the harness was started with but that delivered nothing (its .err lists them): reported as "no data"
        ep = p[:-4] + ".err" if p.endswith(".log") else None
        if ep and os.path.exists(ep):
            for l in open(ep, errors="replace"):
                if l.startswith("feed_race: feed ") and " kind " in l:
                    n = l.split()[2]
                    if n not in feeds:
                        feeds.append(n)
                        note(f"race feed {n} was started but delivered no pump tx in the window")
    return feeds, created


def clock_offset_ms(fra_dir):
    """AMS minus FRA (ms) from the recorder's clock probe files (INFERRED): the host-hub bracket.offset_ms (mean of start /
    end), or the chrony-based chrony_offset_ams_minus_fra_ms when the bracket's best RTT / 2 exceeds 1 ms (a far host
    makes the bracket loose; both servers' chrony is ~0.1-0.2 ms from NTP). -> (offset_ms, [best_rtt_ms...], source)"""
    br, ch = [], []
    for n in ("clock_start.json", "clock_end.json"):
        p = os.path.join(fra_dir, n)
        try:
            j = json.load(open(p))
        except (OSError, ValueError):
            continue
        b = j.get("bracket") or {}
        if b.get("offset_ms") is not None:
            br.append((float(b["offset_ms"]), b.get("best_rtt_ms")))
        if j.get("chrony_offset_ams_minus_fra_ms") is not None:
            ch.append(float(j["chrony_offset_ams_minus_fra_ms"]))
    rtts = [x[1] for x in br]
    loose = any(r is None or r / 2 > 1.0 for r in rtts)
    if ch and (not br or loose):
        return sum(ch) / len(ch), rtts, "chrony (both servers vs NTP)"
    if br:
        return sum(x[0] for x in br) / len(br), rtts, "host-hub ssh bracket"
    return None, None, None


def load_engine(F, files, host, off_ms, tmin, tmax, ours):
    """dip engine records -> eng_exec / eng_first / eng:<feed>; times shifted to the FRA clock when host == ams"""
    sh = int(round(off_ms * 1e6)) if (host == "ams" and off_ms is not None) else 0
    n = {"eng_exec": 0, "eng_first": 0, "eng:feeds": 0}
    fires = {}
    info = {}

    def put(feed, k, t, slot=None):
        if k is None or not t:
            return
        t = t - sh
        if tmin <= t <= tmax:
            F.add(feed, k, t, slot)

    recs = []
    for p in files:
        for r in jl(p):
            recs.append(r)
    for r in recs:
        ev = r.get("ev")
        if ev == "run_start":
            info = {"wallet": r.get("wallet"), "whale_pct": ((r.get("presend") or {}).get("whale_pct")
                                                             or (r.get("presend_live") or {}).get("whale_pct")), "t": r.get("t")}
            if r.get("wallet"):
                ours.add(r["wallet"])
        elif ev in ("dump", "tape", "presend_live_tape", "presend_arm", "presend_skip"):
            if ev in ("tape", "presend_live_tape") and r.get("user") in ours:
                continue
            put("eng_exec", k8_sig(r.get("sig")), r.get("t"), r.get("slot"))
        elif ev in ("presend_live_arm", "presend_live_skip"):
            tr = r.get("trig") or {}
            put("eng_exec", k8_sig(tr.get("sig")), tr.get("t"), tr.get("slot"))
        elif ev == "presend_attempt_land":
            for e in [r.get("d") or {}] + list(r.get("after") or []) + list(r.get("between") or []):
                k = k8_b58_8(e.get("sig8"))
                put("eng_exec", k, e.get("t"), e.get("slot"))
                put("eng_first", k, e.get("first_rx"), e.get("slot"))
        elif ev == "fire" and r.get("via") != "shred":
            fires[r.get("buy_sig")] = r
            put("eng_exec", k8_sig(r.get("dump_sig")), r.get("t_dump_rx"), r.get("slot"))
    for r in recs:
        if r.get("ev") != "timing" or r.get("kind") != "fire":
            continue
        fr = fires.get(r.get("buy_sig"))
        if not fr:
            continue
        k = k8_sig(fr.get("dump_sig"))
        put("eng_first", k, r.get("dump_first_rx"), fr.get("slot"))
        for name, v in (((r.get("clock2") or {}).get("feeds")) or {}).items():
            if isinstance(v, list) and v and v[0]:
                put("eng:" + name, k, v[0], fr.get("slot"))
    for f in list(F.t):
        if f.startswith("eng"):
            n[f] = len(F.t[f])
    return info, n


# ---------------------------------------------------------------- chain truth
def dec_trade(raw):
    sol, tok = struct.unpack_from("<QQ", raw, 40)
    vsol, vtok = struct.unpack_from("<QQ", raw, 97)
    return raw[8:40], sol, tok, raw[56] == 1, raw[57:89], vsol, vtok


def dec_create(raw):
    o = 8
    for _ in range(3):
        n = struct.unpack_from("<I", raw, o)[0]
        o += 4 + n
    mint, user, creator = raw[o:o + 32], raw[o + 64:o + 96], raw[o + 96:o + 128]
    o += 128 + 40 + 32
    mayhem = len(raw) > o and raw[o] == 1
    return mint, user, creator, mayhem


def chain_files(root, t0, t1):
    out = []
    for p in glob.glob(os.path.join(root, "run_*", "txs", "txs_*.jsonl.gz")):
        try:
            e = int(os.path.basename(p)[4:-9])
        except ValueError:
            continue
        if t0 - 330 <= e <= t1 + 30:
            out.append((e, p))
    return [p for _, p in sorted(out)]


def decode_evs(evs):
    trades, creates = [], []
    for e in evs or ():
        try:
            raw = base64.b64decode(e + "=" * (-len(e) % 4))
        except (ValueError, TypeError):
            continue
        if raw[:8] == TE and len(raw) >= 129:
            trades.append(dec_trade(raw))
        elif raw[:8] == CE:
            try:
                creates.append(dec_create(raw))
            except struct.error:
                pass
    return trades, creates


def load_chain(root, t0s, t1s, whale_pct, dump_lam, win_lo=None):
    """-> (cls: k8 -> class, pump: k8 -> slot (pump-program txs), stats, amm: k8 set of pump-AMM-only txs).
    Rows before win_lo (the whale rule's pre-roll) are kept only when they carry pump trade / create events (memory)."""
    files = chain_files(root, t0s, t1s)
    if not files:
        note(f"no chain-truth chunks in {root} for {pkt(t0s * 1e9)}..{pkt(t1s * 1e9)} PKT")
        return {}, {}, {}, set()
    rows, seen = [], set()
    for p in files:
        for r in jl(p):
            k = k8_sig(r.get("sig"))
            if k is None or k in seen:
                continue
            seen.add(k)
            inwin = win_lo is None or (r.get("bt") or 0) >= win_lo - 5
            evs = r.get("ev")
            if not inwin and not evs:
                continue
            trades, creates = decode_evs(evs)
            if not inwin and not trades and not creates:
                continue
            progs = r.get("progs") or ()
            rows.append((r.get("s", 0), r.get("i", 0), k, r.get("err") is not None, PUMP in progs, PUMP_AMM in progs, trades, creates))
    seen = None
    rows.sort(key=lambda x: (x[0], x[1]))
    toks = {}          # mint -> [s0, creator, signer, n, out, wal{user: [bal, became, ins, trig]}]
    cls, pump, amm = {}, {}, set()
    st = {"rows": len(rows), "files": len(files), "whale": 0, "whale_nohist": 0, "dump": 0}
    wp = whale_pct / 100.0
    for s, i, k, err, has_pump, has_amm, trades, creates in rows:
        if has_pump:
            pump[k] = s
        elif has_amm:
            amm.add(k)
        c = "failed" if err else None
        for mint, user, creator, mayhem in creates:
            if mint not in toks and not mayhem:
                toks[mint] = [s, creator, user, 0, False, {}]
        is_whale = is_dump = False
        for mint, sol, tok, buy, user, vsol, vtok in trades:
            if not buy and sol >= dump_lam:
                is_dump = True
            tk = toks.get(mint)
            if tk is None:
                if buy and tok >= wp * SUPPLY and vsol < UNTRADE_V:
                    is_whale = True
                    st["whale_nohist"] += 1
                continue
            if tk[4]:
                continue
            if tk[3] < 50 and (vsol < 25_000_000_000 or vsol > 200_000_000_000 or vtok == 0):
                tk[4] = True
                tk[5] = {}
                continue
            tk[3] += 1
            w = tk[5].setdefault(user, [0, False, False, False])
            w[0] += tok if buy else -tok
            if buy and s == tk[0] and user != tk[1] and user != tk[2]:
                w[2] = True
            if buy and vsol < UNTRADE_V and not w[1]:
                ht = 1 if user == tk[1] else 2 if w[2] else 3 if w[0] >= HX else 0
                if ht:
                    w[1] = True
                if ht == 3 and w[0] / SUPPLY * 100.0 >= whale_pct:
                    w[3] = True
                    is_whale = True
                    st["whale"] += 1
        if is_whale:
            c = "whale"
        elif is_dump:
            c = "dump"
            st["dump"] += 1
        elif creates:
            c = "create"
        elif trades:
            c = "small"
        elif c is None:
            c = "other"
        cls[k] = c
    st["amm_only"] = len(amm)
    return cls, pump, st, amm


def cls_from_p(p, whale_pct, dump_lam):
    """fallback typing from the recorder's parsed pump instructions (no chain truth): approximate"""
    best = "other"
    for it in p or []:
        if not it:
            continue
        kd = str(it[0])
        a1 = it[3] if len(it) > 3 else 0
        a2 = it[4] if len(it) > 4 else 0
        try:
            a1, a2 = int(a1 or 0), int(a2 or 0)
        except (TypeError, ValueError):
            a1 = a2 = 0
        if (kd == "buy" and a1 >= whale_pct / 100 * SUPPLY) or (kd == "bxs" and a2 >= whale_pct / 100 * SUPPLY):
            return "whale"
        if kd == "sell" and a2 >= dump_lam:
            best = "dump"
        elif kd in ("create", "create_v2") and best not in ("dump",):
            best = "create"
        elif kd in ("buy", "sell", "bxs", "amm_buy", "amm_sell") and best == "other":
            best = "small"
    return best


# ---------------------------------------------------------------- windows
def up_seconds(secs, pad=3):
    out = set()
    for s in secs:
        out.update(range(s - pad, s + pad + 1))
    return out


def events_intervals(path, tmin, tmax, data_end=None):
    """recorder events.jsonl -> {st: [(a, b)]} connected intervals (ns); an interval still open ends at the later of the
    last event and the stream's last record"""
    iv, open_ = {"pre": [], "bin": []}, {}
    last_t = None
    if not os.path.exists(path):
        return None
    for r in jl(path):
        t, st, ev = r.get("t"), r.get("st"), r.get("ev")
        if not t:
            continue
        last_t = t
        sts = ["pre", "bin"] if st == "all" else [st]
        for s in sts:
            if s not in iv:
                continue
            if ev in ("subscribed", "first_msg"):
                open_.setdefault(s, t)
            elif ev in ("stream_end", "error", "stop") and s in open_:
                iv[s].append((open_.pop(s), t))
    for s, a in open_.items():
        iv[s].append((a, max(last_t or a, (data_end or {}).get(s) or a)))
    return iv


def secs_of_iv(ivs):
    out = set()
    for a, b in ivs:
        out.update(range(a // 1_000_000_000, b // 1_000_000_000 + 1))
    return out


# ---------------------------------------------------------------- analysis
def analyse_group(F, feeds, ck_feeds, cls, window, pre_slots, chain_pump, extra_seen, title, universe_feeds=None, exclude=None):
    """one comparison group on one clock: first shares, lead/lag vs fastest, pairwise Shreder vs CK, misses.
    universe_feeds: only txs seen by one of these (the engine logs a subset); exclude: keys left out (pump-AMM-only txs:
    the race filters on the pump program only)"""
    T = {f: F.t.get(f, {}) for f in feeds}
    have = [f for f in feeds if T[f]]
    res = {"title": title, "feeds": have, "missing_feeds": [f for f in feeds if not T[f]]}
    if len(have) < 2:
        res["skipped"] = "fewer than 2 feeds with data"
        return res
    best_ck = [f for f in ck_feeds if f in have]
    # universe: txs seen by >= 1 feed, first arrival inside the joint window
    keys = set()
    for f in (universe_feeds or have):
        keys.update(T.get(f, F.t.get(f, {})).keys())
    if exclude:
        keys -= exclude
    U = []
    for k in keys:
        ts = [T[f][k] for f in have if k in T[f]]
        if window is not None and (min(ts) // 1_000_000_000) not in window:
            continue
        U.append(k)
    res["n_any"] = len(U)
    full = [f for f in have if f != "shreder_pre"]

    def cl(k):
        return cls.get(k, "unknown")

    # first-arrival shares
    def shares(us, fs):
        c = {f: 0 for f in fs}
        for k in us:
            ts = {f: T[f][k] for f in fs if k in T[f]}
            m = min(ts.values())
            for f, t in ts.items():
                if t == m:
                    c[f] += 1
        n = len(us)
        return {f: (round(100.0 * c[f] / n, 1) if n else None) for f in fs}
    res["first_any"] = shares(U, have)
    U_all = [k for k in U if all(k in T[f] for f in have)]
    res["n_all"] = len(U_all)
    res["first_all"] = shares(U_all, have) if U_all else {}
    U_full = [k for k in U if all(k in T[f] for f in full)]
    res["n_all_but_pre"] = len(U_full)
    res["first_all_but_pre"] = shares(U_full, full) if U_full else {}
    # lead/lag vs the fastest feed per tx (ms, >= 0), by class
    lag = {f: {c: [] for c in CLASSES} for f in have + (["CK_BEST"] if best_ck else [])}
    pair = {}
    for k in U:
        ts = {f: T[f][k] for f in have if k in T[f]}
        if best_ck:
            cks = [ts[f] for f in best_ck if f in ts]
            if cks:
                ts["CK_BEST"] = min(cks)
        m = min(ts.values())
        c = cl(k)
        for f, t in ts.items():
            d = (t - m) / 1e6
            lag[f]["all"].append(d)
            if c in lag[f]:
                lag[f][c].append(d)
        for s in SHR:
            if s not in ts:
                continue
            for ck in best_ck + (["CK_BEST"] if best_ck else []) + [f for f in have if f.startswith("eng")]:
                if ck in ts:
                    d = (ts[ck] - ts[s]) / 1e6
                    pp = pair.setdefault(f"{s} vs {ck}", {x: [] for x in CLASSES})
                    pp["all"].append(d)
                    if c in pp:
                        pp[c].append(d)
    res["lag_vs_fastest_ms"] = {f: {c: three(v) for c, v in d.items()} for f, d in lag.items()}
    out = {}
    for name, d in pair.items():
        o = {}
        for c, v in d.items():
            if not v:
                o[c] = {"n": 0}
                continue
            x = three(v)
            x["shreder_earlier_pct"] = round(100.0 * sum(1 for y in v if y > 0) / len(v), 1)
            x["tie_pct"] = round(100.0 * sum(1 for y in v if y == 0) / len(v), 1)
            o[c] = x
        out[name] = o
    res["pairwise_ck_minus_shreder_ms"] = out
    # class counts in the universe
    cc = {}
    for k in U:
        cc[cl(k)] = cc.get(cl(k), 0) + 1
    res["classes"] = cc
    # misses relative to the union of the group's feeds; preconf also restricted to its own slots
    mu = {}
    for f in have:
        miss = [k for k in U if k not in T[f]]
        x = {"n_union": len(U), "miss": len(miss), "miss_pct": round(100.0 * len(miss) / len(U), 2) if U else None}
        if f == "shreder_pre" and pre_slots:
            Us = [k for k in U if F.slot.get(k) in pre_slots]
            ms = [k for k in Us if k not in T[f]]
            x["in_preconf_slots"] = {"n": len(Us), "miss": len(ms), "miss_pct": round(100.0 * len(ms) / len(Us), 2) if Us else None,
                                    "slots": len(pre_slots)}
        mu[f] = x
    res["miss_vs_union"] = mu
    # misses vs chain truth (pump program txs whose slot is inside the window)
    if chain_pump and window is not None:
        slot_sec = {}
        for f in have:
            for k, t in T[f].items():
                s = F.slot.get(k)
                if s is not None:
                    v = slot_sec.get(s)
                    if v is None or t < v:
                        slot_sec[s] = t
        win_slots = {s for s, t in slot_sec.items() if (t // 1_000_000_000) in window}
        exp = [k for k, s in chain_pump.items() if s in win_slots]
        mc = {}
        for f in have:
            seen = T[f]
            ex = extra_seen.get(f, set())
            m1 = [k for k in exp if k not in seen]
            m2 = [k for k in m1 if k not in ex]
            x = {"n_chain": len(exp), "miss": len(m1), "miss_pct": round(100.0 * len(m1) / len(exp), 2) if exp else None}
            if f in extra_seen:
                x["miss_with_dataset"] = len(m2)
                x["miss_with_dataset_pct"] = round(100.0 * len(m2) / len(exp), 2) if exp else None
            if f == "shreder_pre" and pre_slots:
                e2 = [k for k in exp if chain_pump[k] in pre_slots]
                m3 = [k for k in e2 if k not in seen and k not in ex]
                x["in_preconf_slots"] = {"n_chain": len(e2), "miss": len(m3), "miss_pct": round(100.0 * len(m3) / len(e2), 2) if e2 else None}
            mc[f] = x
        res["miss_vs_chain"] = mc
        res["window_slots"] = len(win_slots)
    return res


# ---------------------------------------------------------------- report
def md_group(g, L):
    L.append(f"\n## {g['title']}\n")
    if g.get("note"):
        L.append(f"({g['note']})\n")
    if g.get("skipped"):
        L.append(f"skipped: {g['skipped']} (feeds with data: {', '.join(g.get('feeds', [])) or 'none'})\n")
        return
    if g.get("missing_feeds"):
        L.append(f"no data from: {', '.join(g['missing_feeds'])}\n")
    L.append(f"txs in the joint window: {g['n_any']} seen by >=1 feed, {g['n_all']} by all, {g['n_all_but_pre']} by all but preconf. "
             f"classes: {', '.join(f'{k} {v}' for k, v in sorted(g.get('classes', {}).items()))}\n")
    L.append("| feed | first % (>=1 seen) | first % (all seen) | first % (all but pre) | lag vs fastest P10/P50/P90 ms | whale P50 | dump P50 | small P50 | miss vs union % | miss vs chain % |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for f in g["feeds"] + (["CK_BEST"] if "CK_BEST" in g["lag_vs_fastest_ms"] else []):
        lg = g["lag_vs_fastest_ms"].get(f, {})
        a = lg.get("all", {})
        mu = g["miss_vs_union"].get(f, {})
        mc = g.get("miss_vs_chain", {}).get(f, {})
        mcs = "-" if not mc else (f"{mc.get('miss_pct')}" + (f" (dataset {mc.get('miss_with_dataset_pct')})" if "miss_with_dataset_pct" in mc else ""))
        mus = "-" if not mu else f"{mu.get('miss_pct')}"
        if f == "shreder_pre" and mu.get("in_preconf_slots"):
            mus += f" (own slots {mu['in_preconf_slots']['miss_pct']})"
        if f == "shreder_pre" and mc.get("in_preconf_slots"):
            mcs += f" (own slots {mc['in_preconf_slots']['miss_pct']})"
        L.append(f"| {f} | {g['first_any'].get(f, '-')} | {g['first_all'].get(f, '-') if g['first_all'] else '-'} | "
                 f"{g['first_all_but_pre'].get(f, '-') if g['first_all_but_pre'] else '-'} | "
                 f"{a.get('p10', '-')}/{a.get('p50', '-')}/{a.get('p90', '-')} (n {a.get('n', 0)}) | "
                 f"{lg.get('whale', {}).get('p50', '-')} | {lg.get('dump', {}).get('p50', '-')} | {lg.get('small', {}).get('p50', '-')} | {mus} | {mcs} |")
    L.append("\nPairwise (t_CK - t_Shreder, ms; + = Shreder earlier):\n")
    L.append("| pair | class | n | P10 | P50 | P90 | Shreder earlier % |")
    L.append("|---|---|---|---|---|---|---|")
    for name, d in g["pairwise_ck_minus_shreder_ms"].items():
        for c in CLASSES:
            x = d.get(c, {})
            if not x.get("n"):
                continue
            L.append(f"| {name} | {c} | {x['n']} | {x['p10']} | {x['p50']} | {x['p90']} | {x['shreder_earlier_pct']} |")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--engine", nargs="*")
    ap.add_argument("--engine-host", default="auto", choices=["auto", "fra", "ams"])
    ap.add_argument("--race", nargs="*")
    ap.add_argument("--collect-root", default="/home/moiz/sniper-data/collect")
    ap.add_argument("--from", dest="t_from")
    ap.add_argument("--to", dest="t_to")
    ap.add_argument("--whale-pct", type=float, default=None)
    ap.add_argument("--dump-sol", type=float, default=0.3)
    ap.add_argument("--preroll-min", type=float, default=60.0)
    ap.add_argument("--no-rec", action="store_true", help="skip the full-dataset (.rec.gz) scan")
    ap.add_argument("--ams-offset-ms", type=float, default=None,
                    help="AMS minus FRA clock offset to use for an AMS engine (default: fra/clock_*.json bracket.offset_ms; 0 = trust chrony)")
    a = ap.parse_args()
    t_start = time.time()
    R = a.run_dir.rstrip("/")
    fra = os.path.join(R, "fra")
    race_files = a.race if a.race else sorted(glob.glob(os.path.join(R, "ck", "race_*.log")) + glob.glob(os.path.join(R, "ck", "*", "race_*.log")))
    eng_files = a.engine if a.engine else sorted(glob.glob(os.path.join(R, "engine", "*.jsonl")))
    dump_lam = int(a.dump_sol * 1e9)

    # --from/--to (PKT): HH:MM on the date of the earliest data (a cheap first look: the first records of each file); a
    # time earlier than that data by > 1 h means the next day (a window that starts after midnight)
    tmin, tmax = 0, 2**63 - 1
    if a.t_from or a.t_to:
        firsts = []
        for p in sorted(x for x in glob.glob(os.path.join(fra, "*_*.jsonl")) if re.fullmatch(r"(bin|pre)_\d{8}_\d{2}\.jsonl", os.path.basename(x)))[:4] + race_files:
            try:
                with open(p, "rb") as f:
                    for _, raw in zip(range(2000), f):
                        try:
                            if raw[:2] == b"X\t":
                                firsts.append(int(raw.split(b"\t")[2]))
                                break
                            if raw[:1] == b"{":
                                t = json.loads(raw).get("t")
                                if t:
                                    firsts.append(int(t))
                                    break
                        except (ValueError, IndexError):
                            continue
            except OSError:
                pass
        if not firsts:
            note("--from/--to given but no data to anchor the date: ignored")
        else:
            t0 = min(firsts)
            d0 = dt.datetime.fromtimestamp(t0 / 1e9, PKT).date()

            def at(hm):
                h, m = map(int, hm.split(":"))
                x = int(dt.datetime(d0.year, d0.month, d0.day, h, m, tzinfo=PKT).timestamp() * 1e9)
                return x + 86_400 * 10**9 if x < t0 - 3_600 * 10**9 else x
            tmin = at(a.t_from) if a.t_from else 0
            tmax = at(a.t_to) if a.t_to else 2**63 - 1
            if a.t_from and a.t_to and tmax <= tmin:
                tmax += 86_400 * 10**9
            note(f"window limited to {pkt(tmin) if tmin else '-'} .. {pkt(tmax) if tmax < 2**62 else '-'} PKT")
    F = Feeds()
    ptx = {}
    ca, pf = load_shreder(F, fra, tmin, tmax, ptx)
    race_feeds, created = load_race(F, race_files, tmin, tmax) if race_files else ([], {})
    if not race_files:
        note(f"no feed-race output (looked for {R}/ck/race_*.log)")
    # engine
    eng_info, eng_n, host, off = {}, {}, None, None
    ours = set()
    if eng_files:
        probe = {}
        for p in eng_files:
            for r in jl(p):
                if r.get("ev") == "run_start":
                    probe = r
                    break
            if probe:
                break
        host = a.engine_host
        hf = os.path.join(R, "engine", "ENGINE_HOST")
        if host == "auto" and os.path.exists(hf):
            h0 = open(hf).read().strip().lower()
            if h0 in ("fra", "ams"):
                host = h0
        if host == "auto":
            w = probe.get("wallet")
            host = "fra" if w in FRA_WALLETS else "ams" if w in AMS_WALLETS else "fra"
            if w not in FRA_WALLETS | AMS_WALLETS:
                note(f"engine wallet {w} unknown: treated as FRA (same clock); pass --engine-host ams if it ran on AMS")
        off, rtts, osrc = clock_offset_ms(fra)
        if a.ams_offset_ms is not None:
            off, rtts, osrc = a.ams_offset_ms, None, "--ams-offset-ms"
        if host == "ams" and off is not None:
            note(f"AMS engine times shifted by {-off:+.3f} ms to the FRA clock ({osrc}; INFERRED"
                 + (f"; bracket uncertainty up to best_rtt/2 = {[None if r is None else round(r / 2, 3) for r in rtts]} ms)" if rtts else ")"))
        if host == "ams" and off is None:
            note("engine on AMS but no fra/clock_*.json bracket: AMS times NOT corrected (cross-machine numbers unusable for <~1 ms)")
        eng_info, eng_n = load_engine(F, eng_files, host, off, tmin, tmax, ours)
    else:
        note(f"no engine records (looked for {R}/engine/*.jsonl)")
    whale_pct = a.whale_pct or float(eng_info.get("whale_pct") or 6.0)

    # windows: data-driven for continuous feeds (gap > ~6 s = down), recorder events for Shreder (preconf has no gap rule)
    dend = {st: max(F.t[f].values()) for st, f in (("bin", "shreder_bin"), ("pre", "shreder_pre")) if F.t.get(f)}
    ev_iv = events_intervals(os.path.join(fra, "events.jsonl"), tmin, tmax, dend)
    win_secs = {}
    for f in race_feeds + ["shreder_bin"]:
        if F.secs.get(f):
            win_secs[f] = up_seconds(F.secs[f])
    if ev_iv is not None:
        for st, f in (("bin", "shreder_bin"), ("pre", "shreder_pre")):
            if F.secs.get(f):
                s = secs_of_iv(ev_iv.get(st, []))
                if s:
                    win_secs[f] = (win_secs[f] & s) if f in win_secs else s
                else:
                    note(f"events.jsonl has no connected interval for {st}: using its data span")
    if "shreder_pre" in F.secs and "shreder_pre" not in win_secs:
        s = F.secs["shreder_pre"]
        win_secs["shreder_pre"] = set(range(min(s), max(s) + 1))
    window = None
    for s in win_secs.values():
        window = set(s) if window is None else (window & s)
    w_lo = min(window) if window else None
    w_hi = max(window) if window else None
    pre_slots = {F.slot[k] for k in F.t.get("shreder_pre", {}) if k in F.slot}

    # chain truth (window + pre-roll for the whale rule's history)
    cls, chain_pump, cst, amm = {}, {}, {}, set()
    if w_lo is not None:
        cls, chain_pump, cst, amm = load_chain(a.collect_root, int(w_lo - a.preroll_min * 60), w_hi + 5, whale_pct, dump_lam, win_lo=w_lo)
    n_fb = 0
    for k, p in ptx.items():
        if k not in cls:
            cls[k] = cls_from_p(p, whale_pct, dump_lam)
            n_fb += 1
    if n_fb:
        note(f"{n_fb} txs typed from the recorder's parsed instructions (not in chain truth: approximate)")
    for k, p in ptx.items():   # pump-AMM-only txs in the Shreder view (the race's filter is the pump program only)
        if p and all(str(it[0]).startswith("amm_") for it in p if it):
            amm.add(k)

    # full dataset: Shreder arrivals of chain pump txs / race txs the pump view did not carry
    extra_seen, rec_stats = {}, {}
    if not a.no_rec and w_lo is not None:
        want = set(chain_pump)
        for f in race_feeds:
            want.update(F.t.get(f, {}).keys())
        for st, feed in (("bin", "shreder_bin"), ("pre", "shreder_pre")):
            files = sorted(glob.glob(os.path.join(fra, f"{st}_*.rec.gz")))
            if not files:
                continue
            hits_all, n_all, npf_all = {}, 0, 0
            sl_all = set() if feed == "shreder_pre" else None
            for p in files:
                h, n, npf = rec_scan(p, want, max(tmin, (w_lo - 60) * 10**9), min(tmax, (w_hi + 60) * 10**9), sl_all)
                n_all += n
                npf_all += npf
                for k, v in h.items():
                    o = hits_all.get(k)
                    if o is None or v[0] < o[0]:
                        hits_all[k] = v
            view = F.t.get(feed, {})
            added = 0
            for k, (rx, flags, slot) in hits_all.items():
                if k not in view:
                    F.add(feed, k, rx, slot)
                    added += 1
            extra_seen[feed] = set(hits_all)
            rec_stats[feed] = {"files": len(files), "records": n_all, "preconf_flag": npf_all, "want_hits": len(hits_all), "added_to_view": added}
            if feed == "shreder_pre":
                pre_slots |= {v[2] for v in hits_all.values()}
                if sl_all:
                    pre_slots |= sl_all
                    rec_stats[feed]["slots_with_any_tx"] = len(sl_all)

    ck_feeds = [f for f in race_feeds if f != "erpc"]
    groups = []
    g_fra = analyse_group(F, race_feeds + list(SHR), ck_feeds, cls, window, pre_slots, chain_pump, extra_seen,
                          "FRA: Constant-K feed race vs Shreder (same machine, same clock)", exclude=amm)
    groups.append(g_fra)
    if eng_files:
        eng_feeds = sorted(f for f in F.t if f.startswith("eng"))
        lab = "same clock" if host == "fra" else (f"AMS clock shifted by {-off:+.3f} ms (INFERRED offset)" if off is not None else "AMS clock UNCORRECTED")
        w_sh = win_secs.get("shreder_bin") or win_secs.get("shreder_pre")
        g_eng = analyse_group(F, eng_feeds + list(SHR), [], cls, w_sh, pre_slots, {}, {},
                              f"Engine ({host.upper()}, {lab}) logged txs vs Shreder FRA — only the txs the engine logged",
                              universe_feeds=eng_feeds, exclude=amm)
        groups.append(g_eng)
        if race_feeds:
            # engine vs race: the same Constant-K feeds, two views (sanity on the clock / region)
            sv = {}
            for ef, rf in (("eng_exec", "kaldera-tx"), ("eng:kaldera", "kaldera"), ("eng:turbo-kaldera", "turbo-kaldera"), ("eng:kaldera-tx", "kaldera-tx")):
                A, B = F.t.get(ef, {}), F.t.get(rf, {})
                v = [(A[k] - B[k]) / 1e6 for k in A if k in B]
                if v:
                    sv[f"{ef} - race {rf}"] = three(v)
            groups.append({"title": "engine minus race, same tx (ms)", "engine_vs_race": sv})

    out = {"run_dir": R, "generated_pkt": dt.datetime.now(PKT).strftime("%Y-%m-%d %H:%M"), "window": None if w_lo is None else
           {"from_pkt": pkt(w_lo * 1e9), "to_pkt": pkt(w_hi * 1e9), "seconds": len(window)},
           "sources": {"race_files": race_files, "race_feeds": race_feeds, "engine_files": eng_files, "engine_host": host,
                       "engine_clock_offset_ms_ams_minus_fra": off, "engine_info": eng_info, "engine_counts": eng_n,
                       "shreder_pf_flags": pf, "shreder_rec": rec_stats, "chain": cst, "whale_pct": whale_pct, "dump_sol": a.dump_sol},
           "provider_lag_ms": {**{f: three(v) for f, v in ca.items() if v}, **{f"race {f}": three(v) for f, v in created.items()}},
           "groups": groups, "notes": NOTES, "elapsed_s": round(time.time() - t_start, 1)}
    od = os.path.join(R, "analysis")
    os.makedirs(od, exist_ok=True)
    json.dump(out, open(os.path.join(od, "ck_compare.json"), "w"), indent=1)
    L = [f"# Shreder vs Constant-K, per tx (ck_compare.py, {out['generated_pkt']} PKT)\n",
         f"run dir `{R}`; window {out['window']}; whale = T2 trigger >= {whale_pct}% of supply; dump = sell >= {a.dump_sol} SOL.",
         f"Race feeds: {', '.join(race_feeds) or 'none'}; engine: {host or 'none'} ({len(eng_files)} file(s)); chain rows {cst.get('rows', 0)}.",
         "Lag vs fastest = t_feed - min over the group's feeds (ms, 0 = first). CK_BEST = first arrival over the race's Constant-K feeds.",
         f"Provider stamp -> receive (t - created_at, ms): {json.dumps(out['provider_lag_ms'])}"]
    L.append("\n## Headline (t_CK - t_Shreder, ms: + = Shreder earlier)\n")
    for g in groups:
        pw = g.get("pairwise_ck_minus_shreder_ms") or {}
        for name in [n for n in pw if n.endswith("CK_BEST") or n.endswith("eng_first")]:
            d = pw[name]
            parts = []
            for c in ("all", "whale", "dump", "small"):
                x = d.get(c, {})
                if x.get("n"):
                    parts.append(f"{c} n {x['n']} P50 {x['p50']:+.3f} (P10 {x['p10']:+.3f} / P90 {x['p90']:+.3f}), earlier {x['shreder_earlier_pct']}%")
            if parts:
                L.append(f"- **{name}** [{g['title'].split(':')[0]}]: " + "; ".join(parts))
        mc = g.get("miss_vs_chain") or {}
        for f in SHR:
            if f in mc:
                x = mc[f]
                extra = f", own slots {x['in_preconf_slots']['miss_pct']}% of {x['in_preconf_slots']['n_chain']}" if x.get("in_preconf_slots") else ""
                L.append(f"- {f} chain misses: {x.get('miss_with_dataset_pct', x['miss_pct'])}% of {x['n_chain']} pump txs in the window{extra}")
    for g in groups:
        if g.get("title", "").startswith("Engine"):
            g["note"] = "engine feeds are PARTIAL (only the txs the engine logged): their first / miss columns are not coverage"
        if "engine_vs_race" in g:
            L.append(f"\n## {g['title']}\n")
            for k, v in g["engine_vs_race"].items():
                L.append(f"- {k}: {v}")
            continue
        md_group(g, L)
    if NOTES:
        L.append("\n## Notes\n")
        L += [f"- {x}" for x in NOTES]
    open(os.path.join(od, "ck_compare.md"), "w").write("\n".join(L) + "\n")
    # short summary
    print(f"ck_compare: window {out['window']} | elapsed {out['elapsed_s']} s -> {od}/ck_compare.md")
    for g in groups:
        if g.get("skipped") or "pairwise_ck_minus_shreder_ms" not in g:
            continue
        print(f"[{g['title'][:60]}] n_any {g['n_any']}  first%: " + ", ".join(f"{f} {v}" for f, v in g["first_any"].items()))
        for name, d in g["pairwise_ck_minus_shreder_ms"].items():
            x = d.get("all", {})
            if x.get("n"):
                print(f"   {name:<36} n {x['n']:>7}  P10/P50/P90 {x['p10']}/{x['p50']}/{x['p90']} ms  Shreder earlier {x['shreder_earlier_pct']}%")


if __name__ == "__main__":
    main()
