"""zstd frames without a zstd library.

MEASUREMENT.md §1.3: the bot ends a zstd frame at every flush, so every completed frame of a file that is still being
written decodes on its own, and a trailing incomplete frame must be ignored. This module

- walks the frame and block headers of a .zst file in pure Python (no decoding), so a reader knows where the last
  complete frame ends and how many trailing bytes it ignores;
- decodes frames that hold only raw and RLE blocks in pure Python (the synthetic test fixtures are written that way);
- hands frames with compressed blocks to the first available backend: `compression.zstd` (Python >= 3.14), the
  `zstandard` package, the `zstd` CLI, or Node's `zlib.createZstdDecompress` (Node >= 22.15);
- writes raw-block frames (`compress_raw`), which every zstd decoder accepts.

Nothing here reads a whole large file into memory: external backends stream through a pipe.
"""
from __future__ import annotations

import io
import os
import shutil
import struct
import subprocess
import threading
from dataclasses import dataclass, field

MAGIC = 0xFD2FB528
SKIP_LO, SKIP_HI = 0x184D2A50, 0x184D2A5F
BLOCK_MAX = 128 * 1024


class ZstdError(Exception):
    pass


@dataclass
class Frame:
    start: int
    end: int  # exclusive; for an incomplete frame, the file size
    complete: bool
    skippable: bool = False
    block_types: set = field(default_factory=set)
    content_size: int | None = None


@dataclass
class Scan:
    frames: list
    size: int

    @property
    def complete_end(self) -> int:
        """Offset just past the last complete frame."""
        end = 0
        for f in self.frames:
            if not f.complete:
                break
            end = f.end
        return end

    @property
    def truncated_tail_bytes(self) -> int:
        return self.size - self.complete_end

    @property
    def only_raw(self) -> bool:
        return all(f.skippable or f.block_types <= {0, 1} for f in self.frames if f.complete)


def _read_exact(f, n: int) -> bytes | None:
    b = f.read(n)
    return b if len(b) == n else None


def scan(f, size: int | None = None) -> Scan:
    """Walk the frames of a binary file object from its current position (0)."""
    if size is None:
        cur = f.tell()
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(cur)
    frames = []
    pos = f.tell()
    while pos < size:
        f.seek(pos)
        m = _read_exact(f, 4)
        if m is None:
            frames.append(Frame(pos, size, False))
            break
        magic = struct.unpack("<I", m)[0]
        if SKIP_LO <= magic <= SKIP_HI:
            n = _read_exact(f, 4)
            if n is None:
                frames.append(Frame(pos, size, False, True))
                break
            end = pos + 8 + struct.unpack("<I", n)[0]
            if end > size:
                frames.append(Frame(pos, size, False, True))
                break
            frames.append(Frame(pos, end, True, True))
            pos = end
            continue
        if magic != MAGIC:
            raise ZstdError(f"bad zstd magic 0x{magic:08x} at offset {pos}")
        fhd = _read_exact(f, 1)
        if fhd is None:
            frames.append(Frame(pos, size, False))
            break
        d = fhd[0]
        fcs_flag, single, checksum, did_flag = d >> 6, (d >> 5) & 1, (d >> 2) & 1, d & 3
        if (d >> 3) & 1:
            raise ZstdError(f"reserved bit set in frame header at {pos}")
        hdr = (0 if single else 1) + (0, 1, 2, 4)[did_flag] + (1 if single else 0, 2, 4, 8)[fcs_flag]
        rest = _read_exact(f, hdr)
        if rest is None:
            frames.append(Frame(pos, size, False))
            break
        fcs_n = (1 if single else 0, 2, 4, 8)[fcs_flag]
        content_size = None
        if fcs_n:
            raw = rest[hdr - fcs_n:]
            content_size = int.from_bytes(raw, "little") + (256 if fcs_n == 2 else 0)
        p = pos + 5 + hdr
        types: set = set()
        complete = False
        while True:
            f.seek(p)
            bh = _read_exact(f, 3)
            if bh is None:
                break
            h = bh[0] | (bh[1] << 8) | (bh[2] << 16)
            last, btype, bsize = h & 1, (h >> 1) & 3, h >> 3
            if btype == 3:
                raise ZstdError(f"reserved block type at {p}")
            types.add(btype)
            p += 3 + (1 if btype == 1 else bsize)
            if p > size:
                break
            if last:
                if checksum:
                    p += 4
                    if p > size:
                        break
                complete = True
                break
        if not complete:
            frames.append(Frame(pos, size, False, False, types, content_size))
            break
        frames.append(Frame(pos, p, True, False, types, content_size))
        pos = p
    return Scan(frames, size)


def decode_raw(data: bytes) -> bytes:
    """Decode a buffer of complete frames that hold only raw and RLE blocks."""
    out = bytearray()
    bio = io.BytesIO(data)
    for fr in scan(bio, len(data)).frames:
        if not fr.complete:
            break
        if fr.skippable:
            continue
        if not fr.block_types <= {0, 1}:
            raise ZstdError("compressed block: needs a zstd backend")
        d = data[fr.start + 4]
        fcs_flag, single, did_flag = d >> 6, (d >> 5) & 1, d & 3
        p = fr.start + 5 + (0 if single else 1) + (0, 1, 2, 4)[did_flag] + (1 if single else 0, 2, 4, 8)[fcs_flag]
        while True:
            h = data[p] | (data[p + 1] << 8) | (data[p + 2] << 16)
            last, btype, bsize = h & 1, (h >> 1) & 3, h >> 3
            p += 3
            if btype == 0:
                out += data[p:p + bsize]
                p += bsize
            else:
                out += bytes([data[p]]) * bsize
                p += 1
            if last:
                break
    return bytes(out)


def compress_raw(data: bytes, block: int = BLOCK_MAX) -> bytes:
    """One zstd frame of raw blocks holding `data` (no checksum). Deterministic."""
    n = len(data)
    if n < 256:
        fhd, fcs = (0 << 6) | (1 << 5), struct.pack("<B", n)
    elif n < 65536 + 256:
        fhd, fcs = (1 << 6) | (1 << 5), struct.pack("<H", n - 256)
    elif n < 1 << 32:
        fhd, fcs = (2 << 6) | (1 << 5), struct.pack("<I", n)
    else:
        fhd, fcs = (3 << 6) | (1 << 5), struct.pack("<Q", n)
    out = bytearray(struct.pack("<I", MAGIC))
    out.append(fhd)
    out += fcs
    if n == 0:
        out += (1).to_bytes(3, "little")  # last, raw, size 0
        return bytes(out)
    for i in range(0, n, block):
        chunk = data[i:i + block]
        last = 1 if i + block >= n else 0
        out += (last | (0 << 1) | (len(chunk) << 3)).to_bytes(3, "little")
        out += chunk
    return bytes(out)


# ---------------------------------------------------------------------------------------------------------- backends

#: one (possibly huge) frame: stream it through Node's zstd decompressor
_NODE_JS = (
    "const z=require('zlib');process.stdout.on('error',e=>{if(e.code==='EPIPE')process.exit(0);throw e});"
    "if(!z.createZstdDecompress){process.stderr.write('node without zstd');process.exit(3)}"
    "process.stdin.pipe(z.createZstdDecompress()).pipe(process.stdout);"
)
#: many frames (the bot's per-flush frames; Node's stream decoder stops after the first frame): stdin carries
#: `u32 length | frame` records and each frame is decoded on its own
_NODE_FRAMES_JS = (
    "const z=require('zlib');process.stdout.on('error',e=>{if(e.code==='EPIPE')process.exit(0);throw e});"
    "if(!z.zstdDecompressSync){process.stderr.write('node without zstd');process.exit(3)}"
    "const w=b=>new Promise(r=>{if(!process.stdout.write(b))process.stdout.once('drain',r);else r()});"
    "(async()=>{let buf=Buffer.alloc(0);for await(const c of process.stdin){buf=buf.length?Buffer.concat([buf,c]):c;"
    "while(buf.length>=4){const n=buf.readUInt32LE(0);if(buf.length<4+n)break;const f=buf.subarray(4,4+n);"
    "buf=buf.subarray(4+n);await w(z.zstdDecompressSync(f));}}})().catch(e=>{process.stderr.write(String(e));process.exit(1)});"
)


def _lib_decompressor():
    try:  # Python 3.14+
        from compression import zstd as cz  # type: ignore

        return lambda: cz.ZstdDecompressor()
    except Exception:
        pass
    try:
        import zstandard  # type: ignore

        return lambda: zstandard.ZstdDecompressor().decompressobj()
    except Exception:
        return None


def backend_name() -> str:
    """Which backend a compressed frame would use here (for R0's provenance line)."""
    try:
        from compression import zstd  # type: ignore  # noqa: F401

        return "compression.zstd"
    except Exception:
        pass
    try:
        import zstandard  # type: ignore  # noqa: F401

        return "zstandard"
    except Exception:
        pass
    if shutil.which("zstd"):
        return "zstd-cli"
    if shutil.which("node"):
        return "node-zlib"
    return "none"


def _file_chunks(path: str, end: int):
    with open(path, "rb") as f:
        left = end
        while left > 0:
            b = f.read(min(left, 1 << 20))
            if not b:
                break
            left -= len(b)
            yield b


def _frame_records(path: str, sc: "Scan"):
    """`u32 length | frame` for every complete, non-skippable frame (Node multi-frame protocol)."""
    with open(path, "rb") as f:
        for fr in sc.frames:
            if not fr.complete:
                break
            if fr.skippable:
                continue
            f.seek(fr.start)
            data = f.read(fr.end - fr.start)
            yield struct.pack("<I", len(data)) + data


class _PipeReader(io.RawIOBase):
    """Decompressed bytes from an external process fed by a writer thread from `chunks` (an iterator of bytes)."""

    def __init__(self, cmd: list, chunks):
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.err = None

        def feed():
            try:
                for b in chunks:
                    self.p.stdin.write(b)
            except (BrokenPipeError, ValueError) as e:  # reader closed early
                self.err = e
            finally:
                try:
                    self.p.stdin.close()
                except Exception:
                    pass

        self.t = threading.Thread(target=feed, daemon=True)
        self.t.start()

    def readable(self):
        return True

    def readinto(self, b):
        n = self.p.stdout.readinto(b)
        if n == 0:
            rc = self.p.wait()
            if rc not in (0, None):
                msg = self.p.stderr.read().decode(errors="replace")[:300]
                raise ZstdError(f"zstd backend failed ({rc}): {msg}")
        return n

    def close(self):
        if not self.closed:
            try:
                self.p.stdout.close()
            except Exception:
                pass
            if self.p.poll() is None:
                self.p.kill()
            self.p.wait()
            self.t.join(timeout=5)
            for s in (self.p.stdin, self.p.stderr):
                try:
                    s.close()
                except Exception:
                    pass
        super().close()


class _LibReader(io.RawIOBase):
    def __init__(self, path: str, end: int, make):
        self.f = open(path, "rb")
        self.left = end
        self.make = make
        self.d = make()
        self.buf = b""

    def readable(self):
        return True

    def readinto(self, b):
        while not self.buf:
            if self.left <= 0:
                return 0
            chunk = self.f.read(min(self.left, 1 << 20))
            if not chunk:
                return 0
            self.left -= len(chunk)
            out = self._feed(chunk)
            self.buf = out
        n = min(len(b), len(self.buf))
        b[:n] = self.buf[:n]
        self.buf = self.buf[n:]
        return n

    def _feed(self, chunk: bytes) -> bytes:
        out = bytearray()
        while chunk:
            out += self.d.decompress(chunk)
            rest = getattr(self.d, "unused_data", b"")
            if getattr(self.d, "eof", False):
                self.d = self.make()
                chunk = rest
            else:
                chunk = b""
        return bytes(out)

    def close(self):
        self.f.close()
        super().close()


def open_zst(path: str) -> tuple[io.BufferedReader, Scan]:
    """Open a .zst file as a buffered binary stream of its complete frames' content."""
    with open(path, "rb") as f:
        sc = scan(f)
    end = sc.complete_end
    if sc.only_raw:
        with open(path, "rb") as f:
            data = f.read(end)
        return io.BufferedReader(io.BytesIO(decode_raw(data))), sc  # type: ignore[arg-type]
    make = _lib_decompressor()
    if make is not None:
        return io.BufferedReader(_LibReader(path, end, make), 1 << 20), sc
    if shutil.which("zstd"):
        return io.BufferedReader(_PipeReader(["zstd", "-dc", "-q"], _file_chunks(path, end)), 1 << 20), sc
    if shutil.which("node"):
        n_frames = sum(1 for fr in sc.frames if fr.complete and not fr.skippable)
        if n_frames <= 1:
            return io.BufferedReader(_PipeReader(["node", "-e", _NODE_JS], _file_chunks(path, end)), 1 << 20), sc
        return io.BufferedReader(_PipeReader(["node", "-e", _NODE_FRAMES_JS], _frame_records(path, sc)), 1 << 20), sc
    raise ZstdError(f"{path}: compressed zstd frames and no backend (install zstandard, zstd or node >= 22.15)")
