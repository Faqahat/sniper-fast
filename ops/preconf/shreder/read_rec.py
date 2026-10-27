#!/usr/bin/env python3
"""Reader for the shreder_rec dataset (stdlib only).

Files per stream (HH = PKT hour of the local receive time):
  <stream>_<YYYYMMDD_HH>_<part>.rec.gz    concatenated gzip members (one per ~1 s flush); every message received
  <stream>_<YYYYMMDD_HH>_<part>.idx.jsonl one line per gzip member: m, off (compressed byte offset), clen, ulen, n,
                                           q0/q1 (seq range), t0/t1 (rx_ns range), s0/s1 (slot range)
Record layout inside the decompressed stream (little-endian), struct '<IQqqQBBHI' (44 bytes) + tx bytes:
  u32 rec_len (bytes after this field = 40 + tx_len) | u64 seq (per stream, 1-based, gap-free unless the recorder dropped
  on a full queue — see events.jsonl 'dropped') | i64 rx_ns (local CLOCK_REALTIME at receive, after protobuf decode) |
  i64 ca_ns (server created_at, 0 if absent) | u64 slot (as sent by Shreder) | u8 flags (bit0 = preconf flag from the
  server, bit1 = tx bytes did not parse, bit2 = empty tx) | u8 n_proto_sigs | u16 reserved | u32 tx_len | tx bytes =
  bincode VersionedTransaction (Solana wire format; first signature = tx[1:65] when tx[0] < 0x80).

API:
  iter_records(path, with_tx=True) -> yields Rec(seq, rx_ns, ca_ns, slot, flags, sig, tx)   (sig = base58 of first sig)
  iter_stream(dir, stream)         -> all parts of one stream in time order
  members(path)                    -> idx entries; read_member(path, entry) -> records of one member (random access)
  parse_tx(tx) -> dict(version, sigs, keys (static, base58), header, ixs=[(program_idx, [acct idx], data bytes)], lookups)
CLI:
  read_rec.py PATH_OR_DIR [--stream bin] [--tsv] [--limit N] [--summary]
    --tsv     print seq, rx_ns, ca_ns, slot, preconf, sig   (one line per record)
    --summary counts, time span, slot span, rates, size
A truncated last member (recorder killed) is tolerated: records up to the last complete one are returned.
"""
import collections, glob, gzip, json, os, struct, sys, zlib

HDR = struct.Struct("<IQqqQBBHI")
Rec = collections.namedtuple("Rec", "seq rx_ns ca_ns slot flags sig tx")
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58(b: bytes) -> str:
    n = int.from_bytes(b, "big")
    out = []
    while n:
        n, r = divmod(n, 58)
        out.append(_B58[r])
    pad = len(b) - len(b.lstrip(b"\0"))
    return "1" * pad + "".join(reversed(out))


def _first_sig(tx: bytes):
    if len(tx) >= 65 and tx[0] < 0x80 and tx[0] >= 1:
        return tx[1:65]
    return None


def _decompress_members(f):
    """yield decompressed chunks of a multi-member gzip file; stop quietly at a truncated tail"""
    d = zlib.decompressobj(31)
    while True:
        chunk = f.read(1 << 20)
        if not chunk:
            break
        while chunk:
            try:
                out = d.decompress(chunk)
            except zlib.error:
                return
            if out:
                yield out
            if d.eof:
                chunk = d.unused_data
                d = zlib.decompressobj(31)
            else:
                chunk = b""


def iter_records(path, with_tx=True, with_sig=True):
    buf = b""
    with open(path, "rb") as f:
        for out in _decompress_members(f):
            buf = buf + out if buf else out
            off = 0
            n = len(buf)
            while off + 44 <= n:
                rl, seq, rx, ca, slot, flags, nps, _r, txl = HDR.unpack_from(buf, off)
                end = off + 4 + rl
                if end > n:
                    break
                tx = buf[off + 44:end]
                sig = None
                if with_sig:
                    s = _first_sig(tx)
                    sig = b58(s) if s else None
                yield Rec(seq, rx, ca, slot, flags, sig, tx if with_tx else None)
                off = end
            buf = buf[off:]


def stream_files(d, stream):
    return sorted(glob.glob(os.path.join(d, f"{stream}_*_*.rec.gz")))


def iter_stream(d, stream, **kw):
    for p in stream_files(d, stream):
        yield from iter_records(p, **kw)


def members(path):
    ip = path[:-len(".rec.gz")] + ".idx.jsonl"
    with open(ip) as f:
        return [json.loads(l) for l in f if l.strip()]


def read_member(path, entry, with_tx=True):
    with open(path, "rb") as f:
        f.seek(entry["off"])
        raw = gzip.decompress(f.read(entry["clen"]))
    off, out = 0, []
    while off + 44 <= len(raw):
        rl, seq, rx, ca, slot, flags, nps, _r, txl = HDR.unpack_from(raw, off)
        tx = raw[off + 44:off + 4 + rl]
        s = _first_sig(tx)
        out.append(Rec(seq, rx, ca, slot, flags, b58(s) if s else None, tx if with_tx else None))
        off += 4 + rl
    return out


def _cu16(b, o):
    v = 0
    for i in range(3):
        x = b[o]; o += 1
        v |= (x & 0x7F) << (7 * i)
        if not x & 0x80:
            return v, o
    raise ValueError("bad compact-u16")


def parse_tx(b: bytes):
    """minimal VersionedTransaction parse (same as the Rust recorder). Raises on malformed input."""
    o = 0
    ns, o = _cu16(b, o)
    sigs = [b[o + 64 * i:o + 64 * (i + 1)] for i in range(ns)]
    o += 64 * ns
    ver = -1
    if b[o] & 0x80:
        ver = b[o] & 0x7F; o += 1
    header = tuple(b[o:o + 3]); o += 3
    nk, o = _cu16(b, o)
    keys = [b[o + 32 * i:o + 32 * (i + 1)] for i in range(nk)]
    o += 32 * nk
    o += 32  # blockhash
    ni, o = _cu16(b, o)
    ixs = []
    for _ in range(ni):
        pi = b[o]; o += 1
        na, o = _cu16(b, o); acc = list(b[o:o + na]); o += na
        nd, o = _cu16(b, o); data = b[o:o + nd]; o += nd
        ixs.append((pi, acc, data))
    lookups = []
    if ver == 0:
        nl, o = _cu16(b, o)
        for _ in range(nl):
            k = b[o:o + 32]; o += 32
            nw, o = _cu16(b, o); w = list(b[o:o + nw]); o += nw
            nr, o = _cu16(b, o); r = list(b[o:o + nr]); o += nr
            lookups.append((b58(k), w, r))
    return {"version": ver, "sigs": [b58(s) for s in sigs], "header": header, "keys": [b58(k) for k in keys],
            "ixs": ixs, "lookups": lookups}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--stream", default="bin")
    ap.add_argument("--tsv", action="store_true")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    files = [a.path] if os.path.isfile(a.path) else stream_files(a.path, a.stream)
    n = 0; t0 = t1 = None; s0 = s1 = None; pf = 0; size = sum(os.path.getsize(p) for p in files); ub = 0
    try:
        for p in files:
            for r in iter_records(p, with_tx=a.summary, with_sig=a.tsv):
                n += 1
                if a.tsv:
                    print(f"{r.seq}\t{r.rx_ns}\t{r.ca_ns}\t{r.slot}\t{r.flags & 1}\t{r.sig}")
                if a.summary:
                    t0 = r.rx_ns if t0 is None else min(t0, r.rx_ns); t1 = r.rx_ns if t1 is None else max(t1, r.rx_ns)
                    s0 = r.slot if s0 is None else min(s0, r.slot); s1 = r.slot if s1 is None else max(s1, r.slot)
                    pf += r.flags & 1; ub += 44 + len(r.tx)
                if a.limit and n >= a.limit:
                    raise StopIteration
    except (StopIteration, BrokenPipeError):
        pass
    if a.summary:
        span = (t1 - t0) / 1e9 if n > 1 else 0
        print(json.dumps({"files": len(files), "records": n, "preconf_flagged": pf, "span_s": round(span, 1),
                          "rate_per_s": round(n / span, 1) if span else None, "slots": [s0, s1],
                          "gz_bytes": size, "raw_bytes": ub, "ratio": round(ub / size, 2) if size else None}))


if __name__ == "__main__":
    main()
