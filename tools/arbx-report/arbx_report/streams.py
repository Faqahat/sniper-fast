"""Readers for every recorded stream (MEASUREMENT.md §1.3, §4): file discovery and rotation series, compression,
the JSON-lines header and schema-version check, the text logs, and the binary formats (accounts §4.12,
journal §4.13, entries §4.25). arb-lab v1 files (no header) are read here too; `legacy.py` maps their meaning.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import lzma
import os
import re
import struct
from dataclasses import dataclass, field

from . import solana, zstd

# ------------------------------------------------------------------------------------------------- schema registry

#: major versions this toolkit reads, per stream (MEASUREMENT §1.3 rule: refuse unknown majors; minors may add fields)
SUPPORTED_MAJORS: dict = {
    "campaign": {1}, "meta": {2}, "stop": {1}, "manifest": {1}, "probe": {1}, "events": {1}, "control": {1},
    "supervisor": {1}, "status": {2}, "feedhealth": {1}, "resources": {1}, "keepalive": {1}, "accounts": {2},
    "journal": {2}, "exec": {2}, "wallet": {1, 2}, "blocks": {1}, "slotidx": {1}, "slots": {1}, "txfetch": {1},
    "txarr": {1}, "arrivals": {1}, "rivals": {1}, "moves": {2}, "poh": {2}, "slots-feed": {2}, "entries": {1},
    "alts": {2}, "alts-final": {1, 2}, "leaders": {1}, "validators": {1}, "pools": {1}, "triggers": {2},
    "commits": {1}, "decisions": {1}, "opportunities": {1}, "predictions": {2}, "caps": {1}, "sims": {1},
    "attempts": {2}, "copies": {1}, "bundles": {2}, "outcomes": {2}, "blockctx": {1}, "ledger": {1},
    "snapshots": {1}, "recon": {1}, "experiments": {1}, "verify": {1}, "discovery": {1}, "cu-table": {1},
}

#: arb-lab file names that differ from arbx's (§1.1: `slots.log` became `slots-feed`)
LEGACY_NAMES = {"slots": "slots-feed"}

_HEADER_RE = re.compile(r"^arbx\.([a-z0-9_-]+)/(\d+)\.(\d+)$")
_FILE_RE = re.compile(r"^(?P<name>[a-z0-9_-]+?)(?:\.(?P<seq>\d{3}))?\.(?P<ext>jsonl|log|bin|json)(?P<comp>\.zst|\.xz|\.gz)?$")


class SchemaError(Exception):
    """A file with a major schema version this toolkit does not know (it refuses to guess)."""


@dataclass
class FileInfo:
    path: str
    stream: str
    seq: int
    ext: str
    comp: str | None
    size: int
    schema: str | None = None
    major: int | None = None
    minor: int | None = None
    legacy: bool = False
    records: int = 0
    bad_lines: int = 0
    partial_tail: bool = False
    truncated_bytes: int = 0
    header: dict | None = None

    @property
    def name(self) -> str:
        return os.path.basename(self.path)


def parse_schema(s: str) -> tuple[str, int, int]:
    m = _HEADER_RE.match(s or "")
    if not m:
        raise SchemaError(f"not an arbx schema string: {s!r}")
    return m.group(1), int(m.group(2)), int(m.group(3))


def registry_name(stream: str) -> str:
    return "entries" if stream.startswith("entries-") else stream


def check_version(stream: str, major: int, path: str = "") -> None:
    """Refuse a known stream at an unknown major version. A stream this toolkit does not know is not read by any
    report, so it is listed (R0) but not refused."""
    ok = SUPPORTED_MAJORS.get(registry_name(stream))
    if ok is not None and major not in ok:
        raise SchemaError(f"{path or stream}: schema arbx.{stream}/{major}.x is not supported (known majors: {sorted(ok)})")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


# ---------------------------------------------------------------------------------------------------- discovery

def discover(seg_dir: str) -> dict:
    """{stream: [FileInfo, ...]} for every recorded file of a segment, rotation series in `NNN` order."""
    out: dict = {}
    if not os.path.isdir(seg_dir):
        return out
    for fn in sorted(os.listdir(seg_dir)):
        p = os.path.join(seg_dir, fn)
        if not os.path.isfile(p):
            continue
        if fn == "entries.zst":  # arb-lab's single raw entries archive
            out.setdefault("entries", []).append(FileInfo(p, "entries", 0, "bin", ".zst", os.path.getsize(p), legacy=True))
            continue
        m = _FILE_RE.match(fn)
        if not m:
            continue
        name = m.group("name")
        stream = LEGACY_NAMES.get(name, name) if m.group("ext") == "log" else name
        fi = FileInfo(p, stream, int(m.group("seq") or 0), m.group("ext"), m.group("comp"), os.path.getsize(p))
        out.setdefault(stream, []).append(fi)
    for v in out.values():
        v.sort(key=lambda f: (f.seq, f.name))
    return out


def open_bytes(fi_or_path) -> tuple[io.BufferedIOBase, int]:
    """A binary stream of a file's content; also returns the count of ignored trailing bytes (zstd only)."""
    path = fi_or_path.path if isinstance(fi_or_path, FileInfo) else fi_or_path
    if path.endswith(".zst"):
        f, sc = zstd.open_zst(path)
        return f, sc.truncated_tail_bytes
    if path.endswith(".xz"):
        return lzma.open(path, "rb"), 0  # type: ignore[return-value]
    if path.endswith(".gz"):
        return gzip.open(path, "rb"), 0  # type: ignore[return-value]
    return open(path, "rb"), 0


def _lines(fi: FileInfo):
    """Complete text lines of a file. A last line without '\n' is a write in progress: skipped and flagged."""
    f, trunc = open_bytes(fi)
    fi.truncated_bytes = trunc
    try:
        pending = b""
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            chunk = pending + chunk
            parts = chunk.split(b"\n")
            pending = parts.pop()
            for p in parts:
                yield p
        if pending.strip():
            fi.partial_tail = True
    finally:
        f.close()


# ---------------------------------------------------------------------------------------------------- JSON lines

def _is_header(obj) -> bool:
    return isinstance(obj, dict) and isinstance(obj.get("schema"), str) and obj["schema"].startswith("arbx.") and "file_seq" in obj


def iter_jsonl(files: list, stream: str | None = None):
    """Records of a rotation series. The header line is checked and skipped; files without one are arb-lab v1.
    Mixed v1/v2 series and unknown majors raise SchemaError."""
    series_major = None
    for fi in files:
        first = True
        for raw in _lines(fi):
            if not raw.strip():
                continue
            try:
                obj = json.loads(raw)
            except ValueError:
                fi.bad_lines += 1
                continue
            if first:
                first = False
                if _is_header(obj):
                    name, major, minor = parse_schema(obj["schema"])
                    check_version(stream or fi.stream, major, fi.name)
                    fi.schema, fi.major, fi.minor, fi.header = obj["schema"], major, minor, obj
                else:
                    fi.legacy = True
                    fi.major, fi.minor = 1, 0
                if series_major is not None and fi.major != series_major:
                    raise SchemaError(f"{fi.name}: major version {fi.major} in a series of version {series_major}")
                series_major = fi.major
                if not fi.legacy:
                    continue
            fi.records += 1
            yield obj
        if first:  # empty file
            fi.legacy = fi.legacy or fi.schema is None


def read_jsonl(files: list, stream: str | None = None) -> list:
    return list(iter_jsonl(files, stream))


def read_json(path: str, stream: str | None = None) -> dict | list | None:
    """A whole-file JSON document (meta, stop, manifest, campaign, probe, pools). Checks `schema` when present."""
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        obj = json.load(f)
    if isinstance(obj, dict) and isinstance(obj.get("schema"), str) and obj["schema"].startswith("arbx."):
        name, major, _minor = parse_schema(obj["schema"])
        check_version(stream or name, major, path)
    return obj


def iter_exec(files: list):
    """exec.jsonl (and wallet.jsonl) records with `idx_update` lines merged into their first line (§4.14).
    Two passes: the first collects the (few) idx updates, the second yields the records."""
    updates: dict = {}
    for fi in files:
        for raw in _lines(fi):
            if b'"idx_update"' in raw:
                try:
                    o = json.loads(raw)
                except ValueError:
                    continue
                if "idx_update" in o and "sig" in o:
                    updates[o["sig"]] = o["idx_update"]
    for fi in files:
        fi.records = 0
    for o in iter_jsonl(files):
        if "idx_update" in o and len(o) <= 4 and "slot" not in o:
            continue
        sig = o.get("sig")
        if sig in updates and o.get("idx") is None:
            o = dict(o)
            o["idx"] = updates[sig]
            o["idx_src"] = "slotidx"
        yield o


# ---------------------------------------------------------------------------------------------------- text logs

def _text_header(fi: FileInfo, line: str, stream: str) -> dict | None:
    """`# arbx.<stream>/<maj>.<min> key=value ...` (arbx adds it; arb-lab files have none)."""
    if not line.startswith("#"):
        return None
    parts = line[1:].split()
    if not parts:
        return {}
    name, major, minor = parse_schema(parts[0])
    check_version(stream, major, fi.name)
    fi.schema, fi.major, fi.minor = parts[0], major, minor
    kv = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            kv[k] = v
    fi.header = kv
    return kv


def iter_text(files: list, stream: str):
    """(file, columns) for each data line of a text log, header handled."""
    for fi in files:
        first = True
        for raw in _lines(fi):
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            if first:
                first = False
                if _text_header(fi, line, stream) is not None:
                    continue
                fi.legacy = True
                fi.major, fi.minor = 1, 0
            if line.startswith("#"):
                continue
            fi.records += 1
            yield fi, line.split()


def iter_txarr(files: list):
    """txarr.log: {sig8, slot, first_ns, d: [µs after first or None per feed]} (§4.19)."""
    for _fi, c in iter_text(files, "txarr"):
        if len(c) < 3:
            continue
        yield {"sig8": c[0], "slot": int(c[1]), "first_ns": int(c[2]), "d": [None if x == "-" else int(x) for x in c[3:]]}


def txarr_feeds(files: list) -> list | None:
    for fi in files:
        if fi.header and "feeds" in fi.header:
            return fi.header["feeds"].split(",")
    return None


def iter_poh(files: list):
    """poh.log: {sig8, slot, ms, feed, entry_idx} (§4.23; v1 has the first three columns only)."""
    for _fi, c in iter_text(files, "poh"):
        if len(c) < 3:
            continue
        yield {"sig8": c[0], "slot": int(c[1]), "ms": float(c[2]),
               "feed": int(c[3]) if len(c) > 3 and c[3] != "-" else None,
               "entry_idx": int(c[4]) if len(c) > 4 and c[4] != "-" else None}


def iter_moves(files: list):
    """moves.log: {sig, slot, pool, t_ns, acct, wv, role} (§4.22; v1 has the first four columns)."""
    for _fi, c in iter_text(files, "moves"):
        if len(c) < 4:
            continue
        yield {"sig": c[0], "slot": int(c[1]), "pool": c[2], "t_ns": int(c[3]),
               "acct": c[4] if len(c) > 4 else None,
               "wv": int(c[5]) if len(c) > 5 and c[5] != "-" else None,
               "role": c[6] if len(c) > 6 else None}


_SF_COLS = ["feed", "slot", "ticks", "entries", "txs", "t_first", "t_last", "valid", "data_shreds", "code_shreds",
            "sets_ok", "sets_failed", "poh_complete"]


def iter_slots_feed(files: list):
    """slots-feed.log (arb-lab slots.log): one finished slot per feed (§4.24). `-` is null."""
    for _fi, c in iter_text(files, "slots-feed"):
        if len(c) < 8:
            continue
        row = {}
        for i, k in enumerate(_SF_COLS):
            v = c[i] if i < len(c) else None
            row[k] = None if v in (None, "-") else int(v)
        yield row


# ---------------------------------------------------------------------------------------------------- binary

class BinFormatError(Exception):
    pass


def _bin_header(f, magic: bytes, path: str) -> tuple[int, dict]:
    m = f.read(8)
    if m != magic:
        raise BinFormatError(f"{path}: bad magic {m!r}")
    fmt, hlen = struct.unpack("<HH", f.read(4))
    hdr = json.loads(f.read(hlen) or b"{}")
    return fmt, hdr


ACC_DICT, ACC_FULL, ACC_XOR, ACC_MARK, ACC_GAP = 1, 2, 3, 4, 6
MARK_NAMES = {1: "boot_begin", 2: "boot_end", 3: "stream_reconnect", 4: "watch_list_changed", 5: "fork_refetch"}
ROLE_NAMES = {0: "other", 1: "pool", 2: "vault", 3: "extra", 4: "dlmm_bin_array", 5: "mint", 6: "clock_sysvar",
              7: "dlmm_bitmap_ext", 8: "programdata", 9: "wallet", 10: "wallet_token_account", 11: "pump_fee_config"}
SRC_NAMES = {0: "grpc", 1: "rpc_boot", 2: "rpc_refetch", 3: "rpc_snapshot"}


@dataclass
class AccountRecord:
    aseq: int
    acct: str
    role: int
    pool_index: int | None
    slot: int
    wv: int
    t_recv_ns: int
    src: int
    flags: int
    txn: str | None
    lamports: int
    owner: str
    data_xxh3: int
    data: bytes
    kind: int  # 2 FULL, 3 XOR


@dataclass
class AccountsScan:
    records: list = field(default_factory=list)
    marks: list = field(default_factory=list)
    gaps: list = field(default_factory=list)
    unknown_kinds: dict = field(default_factory=dict)
    aseq_holes: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def iter_accounts(files: list, keep_data: bool = True, scan: AccountsScan | None = None):
    """accounts.bin records with XOR deltas applied (§4.12). Each file restarts its dictionary and keyframes.
    GAP and MARK records go to `scan`; aseq holes not covered by a GAP are reported there too."""
    scan = scan if scan is not None else AccountsScan()
    prev_aseq = None
    for fi in files:
        f, trunc = open_bytes(fi)
        fi.truncated_bytes = trunc
        try:
            fmt, hdr = _bin_header(f, b"ARBXACC\0", fi.name)
            if fmt != 2:
                raise SchemaError(f"{fi.name}: accounts format {fmt} not supported")
            fi.header, fi.major, fi.minor = hdr, 2, 0
            fi.schema = hdr.get("schema")
            if fi.schema:
                _n, major, minor = parse_schema(fi.schema)
                check_version("accounts", major, fi.name)
                fi.major, fi.minor = major, minor
            dct: dict = {}
            last: dict = {}
            while True:
                h = f.read(5)
                if len(h) < 5:
                    if h:
                        fi.partial_tail = True
                    break
                kind, blen = h[0], struct.unpack("<I", h[1:])[0]
                body = f.read(blen)
                if len(body) < blen:
                    fi.partial_tail = True
                    break
                fi.records += 1
                if kind == ACC_DICT:
                    aid = struct.unpack_from("<I", body, 0)[0]
                    pk = solana.b58encode(body[4:36])
                    role = body[36]
                    pidx = struct.unpack_from("<I", body, 37)[0]
                    dct[aid] = (pk, role, None if pidx == 0xFFFFFFFF else pidx)
                elif kind in (ACC_FULL, ACC_XOR):
                    aseq, aid, slot, wv, t, src, flags = struct.unpack_from("<QIQQQBB", body, 0)
                    p = 38
                    txn = None
                    if flags & 1:
                        txn = solana.b58encode(body[p:p + 64])
                        p += 64
                    lamports = struct.unpack_from("<Q", body, p)[0]
                    p += 8
                    owner = solana.b58encode(body[p:p + 32])
                    p += 32
                    xh, dlen = struct.unpack_from("<QI", body, p)
                    p += 12
                    data = body[p:p + dlen]
                    if kind == ACC_XOR:
                        base = last.get(aid)
                        if base is None or len(base) != dlen:
                            scan.errors.append(f"{fi.name}: XOR record aseq {aseq} without a matching base")
                            data = data
                        else:
                            data = bytes(a ^ b for a, b in zip(data, base))
                    last[aid] = data
                    if aid not in dct:
                        scan.errors.append(f"{fi.name}: aseq {aseq} names unknown acct_id {aid}")
                    pk, role, pidx = dct.get(aid, ("?", 0, None))
                    if prev_aseq is not None and aseq != prev_aseq + 1:
                        covered = any(g[0] == prev_aseq + 1 and g[0] + g[1] == aseq for g in scan.gaps)
                        if not covered:
                            scan.aseq_holes.append((prev_aseq + 1, aseq - 1))
                    prev_aseq = aseq
                    yield AccountRecord(aseq, pk, role, pidx, slot, wv, t, src, flags, txn, lamports, owner, xh,
                                        data if keep_data else b"", kind)
                elif kind == ACC_MARK:
                    t, mark, n = struct.unpack_from("<QBI", body, 0)
                    ids = struct.unpack_from(f"<{n}I", body, 13) if n else ()
                    scan.marks.append({"t_ns": t, "mark": MARK_NAMES.get(mark, str(mark)),
                                       "accts": [dct.get(i, ("?",))[0] for i in ids]})
                elif kind == ACC_GAP:
                    first, n = struct.unpack_from("<QQ", body, 0)
                    scan.gaps.append((first, n))
                else:
                    scan.unknown_kinds[kind] = scan.unknown_kinds.get(kind, 0) + 1
        finally:
            f.close()


J_TX_FIRST, J_TX_COPY, J_ACCOUNT, J_SLOT, J_BLOCK_META, J_ALT, J_INPUT, J_TICK, J_STATUS, J_TIMER, J_GAP = (
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12)
J_NAMES = {1: "TX_FIRST", 2: "TX_COPY", 3: "ACCOUNT", 4: "SLOT", 5: "BLOCK_META", 6: "ALT", 7: "INPUT", 8: "TICK",
           9: "STATUS", 10: "TIMER", 12: "GAP"}
INPUT_KINDS = {1: "blockhash_head", 2: "leader_window", 3: "gate", 4: "quarantine", 5: "inflight_release",
               6: "health", 7: "wallet_tx", 8: "slotidx_missing"}

#: journal record framing: `u8 kind | u32 body_len | u64 seq | u64 t_engine_ns | body`. body_len counts the body
#: only (not seq and t_engine_ns). Keep in step with src/rec/journal.rs (WP-03).
JOURNAL_BODY_LEN_EXCLUDES_SEQ_T = True


def _parse_journal_body(kind: int, b: bytes) -> dict:
    if kind == J_TX_FIRST:
        feed, slot, t_rx, t_dec, executed, enc, ln = struct.unpack_from("<HQQQbBI", b, 0)
        p = 32
        raw = b[p:p + ln]
        p += ln
        d = {"feed": feed, "slot": slot, "t_rx": t_rx, "t_decoded": t_dec,
             "executed": None if executed == -1 else bool(executed), "enc": enc, "len": ln}
        if enc == 0 and raw:
            try:
                w = solana.parse_wire(raw)
                d["sig"] = w["signatures"][0] if w["signatures"] else None
            except Exception:
                d["sig"] = None
        has_loaded = b[p]
        p += 1
        if has_loaded:
            nw = struct.unpack_from("<H", b, p)[0]
            p += 2 + 32 * nw
            nr = struct.unpack_from("<H", b, p)[0]
            p += 2 + 32 * nr
            d["loaded"] = [nw, nr]
        has_poh = b[p] if p < len(b) else 0
        p += 1
        if has_poh:
            ps, hashes, ticks, hpt = struct.unpack_from("<QQIQ", b, p)
            d["poh"] = {"slot": ps, "hashes": hashes, "ticks": ticks, "hpt": hpt}
        return d
    if kind == J_TX_COPY:
        return {"sig": solana.b58encode(b[:64]), "feed": struct.unpack_from("<H", b, 64)[0],
                "t_rx": struct.unpack_from("<Q", b, 66)[0]}
    if kind == J_ACCOUNT:
        aseq, verdict = struct.unpack_from("<QB", b, 0)
        return {"aseq": aseq, "store_verdict": "accepted" if verdict == 0 else "stale"}
    if kind == J_SLOT:
        slot, parent, status, t = struct.unpack_from("<QQiQ", b, 0)
        return {"slot": slot, "parent": None if parent == 0xFFFFFFFFFFFFFFFF else parent, "status": status, "t": t}
    if kind == J_BLOCK_META:
        slot = struct.unpack_from("<Q", b, 0)[0]
        bh = solana.b58encode(b[8:40])
        height, parent, t = struct.unpack_from("<QQQ", b, 40)
        return {"slot": slot, "blockhash": bh, "height": height, "parent_slot": parent, "t": t}
    if kind == J_ALT:
        table = solana.b58encode(b[:32])
        found, n = b[32], struct.unpack_from("<H", b, 33)[0]
        return {"table": table, "found": bool(found), "addrs": [solana.b58encode(b[35 + 32 * i:67 + 32 * i]) for i in range(n)]}
    if kind == J_INPUT:
        ik, ln = struct.unpack_from("<BI", b, 0)
        try:
            payload = json.loads(b[5:5 + ln] or b"null")
        except ValueError:
            payload = None
        return {"input": INPUT_KINDS.get(ik, str(ik)), "data": payload}
    if kind == J_TIMER:
        return {"t": struct.unpack_from("<Q", b, 0)[0]}
    if kind == J_GAP:
        first, n = struct.unpack_from("<QQ", b, 0)
        return {"first_lost_seq": first, "n_lost": n}
    return {}


@dataclass
class JournalScan:
    gaps: list = field(default_factory=list)
    seq_holes: list = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    unknown_kinds: dict = field(default_factory=dict)


def iter_journal(files: list, scan: JournalScan | None = None):
    """journal.bin records: {kind, seq, t_engine_ns, ...body fields} (§4.13)."""
    scan = scan if scan is not None else JournalScan()
    prev = None
    for fi in files:
        f, trunc = open_bytes(fi)
        fi.truncated_bytes = trunc
        try:
            fmt, hdr = _bin_header(f, b"ARBXJRN\0", fi.name)
            if fmt != 2:
                raise SchemaError(f"{fi.name}: journal format {fmt} not supported")
            fi.header, fi.major, fi.minor, fi.schema = hdr, 2, 0, hdr.get("schema")
            while True:
                h = f.read(21)
                if len(h) < 21:
                    if h:
                        fi.partial_tail = True
                    break
                kind, blen, seq, t = struct.unpack("<BIQQ", h)
                if not JOURNAL_BODY_LEN_EXCLUDES_SEQ_T:
                    blen -= 16
                body = f.read(blen)
                if len(body) < blen:
                    fi.partial_tail = True
                    break
                fi.records += 1
                name = J_NAMES.get(kind)
                if name is None:
                    scan.unknown_kinds[kind] = scan.unknown_kinds.get(kind, 0) + 1
                    continue
                scan.counts[name] = scan.counts.get(name, 0) + 1
                rec = {"kind": name, "seq": seq, "t_engine_ns": t}
                rec.update(_parse_journal_body(kind, body))
                if kind == J_GAP:
                    scan.gaps.append((rec["first_lost_seq"], rec["n_lost"]))
                if prev is not None and seq != prev + 1:
                    covered = any(g[0] == prev + 1 and g[0] + g[1] == seq for g in scan.gaps)
                    if not covered:
                        scan.seq_holes.append((prev + 1, seq - 1))
                prev = seq
                yield rec
        finally:
            f.close()


def iter_entries(files: list):
    """entries-<feed>.bin frames: {slot, t_ns, len} (§4.25; arb-lab `entries.zst` has no file header)."""
    for fi in files:
        f, trunc = open_bytes(fi)
        fi.truncated_bytes = trunc
        try:
            head = f.read(8)
            if head == b"ARBXENT\0":
                fmt, hlen = struct.unpack("<HH", f.read(4))
                fi.header = json.loads(f.read(hlen) or b"{}")
                fi.major, fi.minor = 1, 0
                pending = b""
            else:
                fi.legacy = True
                pending = head
            while True:
                h = pending + f.read(20 - len(pending))
                pending = b""
                if len(h) < 20:
                    if h:
                        fi.partial_tail = True
                    break
                slot, t, ln = struct.unpack("<QQI", h)
                data = f.read(ln)
                if len(data) < ln:
                    fi.partial_tail = True
                    break
                fi.records += 1
                yield {"slot": slot, "t_ns": t, "len": ln}
        finally:
            f.close()


def peek(fi: FileInfo) -> FileInfo:
    """Read only a file's header (JSON-lines header line, text-log `#` line or binary header) into `fi`."""
    if fi.schema or fi.legacy:
        return fi
    try:
        f, _ = open_bytes(fi)
    except Exception as e:  # unreadable: R0 reports it
        fi.header = {"error": str(e)}
        return fi
    try:
        if fi.ext == "bin":
            head = f.read(8)
            if head[:4] == b"ARBX":
                fmt, hlen = struct.unpack("<HH", f.read(4))
                hdr = json.loads(f.read(hlen) or b"{}")
                fi.header = hdr
                fi.schema = hdr.get("schema") or f"{fi.stream}/format{fmt}"
            else:
                fi.legacy = True
            return fi
        line = f.readline(1 << 20).strip()
        if not line:
            return fi
        if fi.ext == "log":
            s = line.decode("utf-8", "replace")
            if s.startswith("#"):
                _text_header(fi, s, fi.stream)
            else:
                fi.legacy, fi.major, fi.minor = True, 1, 0
            return fi
        try:
            obj = json.loads(line)
        except ValueError:
            return fi
        if _is_header(obj):
            _n, major, minor = parse_schema(obj["schema"])
            fi.schema, fi.major, fi.minor, fi.header = obj["schema"], major, minor, obj
        else:
            fi.legacy, fi.major, fi.minor = True, 1, 0
        return fi
    finally:
        f.close()


# ---------------------------------------------------------------------------------------------------- writers (tests)

def jsonl_header(stream: str, version: str, run: str, file_seq: int = 0, started_ns: int = 0, producer: str = "synthetic") -> str:
    return json.dumps({"schema": f"arbx.{stream}/{version}", "run": run, "file_seq": file_seq,
                       "started_ns": started_ns, "producer": producer}, sort_keys=True)
