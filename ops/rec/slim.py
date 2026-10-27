#!/usr/bin/env python3
# SLIM trades-only extract of a recording day (for keeping long-term history cheaply). One row per trade EVENT of a
# successful tx: pump.fun bonding-curve TradeEvent (prog 0) and PumpSwap BuyEvent / SellEvent (prog 1).
# Columns: slot, idx (tx index in block), k (event index in the tx), bt (block time), side (1 buy / 0 sell),
#          sol, tok, vsol, vtok, fee (tx fee, lamports), tip (sum of tips in the tx, lamports), prog, mint, user
#   pump curve: sol/tok = sol_amount/token_amount, vsol/vtok = virtual reserves after the trade (TradeEvent)
#   PumpSwap  : sol = quote in/out (event u64 @64), tok = base out/in (@16), vsol/vtok = pool quote/base reserves (@56/@48),
#               mint = token account owned by the pool in the tx's token balances (else the tx's tracked mint)
#   fee and tip are per TRANSACTION (repeated on every event row of that tx).
# Format: b"SNIPERSLIM1\n" + header json line + blocks. A block holds <= 250k rows; per block every column is
# fixed-width little-endian, slot/bt delta-encoded, byte-shuffled, compressed (lzma default). mint/user are u32 ids into
# one string table per file (stored after the blocks). Rows are in (slot, idx, k) order within each source; a day built
# from two overlapping FRA runs is de-duplicated by (slot, idx, k).
# CLI: slim.py build <day> [lzma|zlib] | info <file> | cat <file> [n]      Python: hdr, cols = slim.load(path, cols)
import os, sys, json, time, gzip, zlib, lzma, base64, array, struct, glob
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reclib as R

MAGIC = b"SNIPERSLIM1\n"; BLOCK = 250_000
TRADE = bytes([189, 219, 127, 211, 78, 230, 97, 238])
AMM_BUY = bytes.fromhex("67f4521f2cf57777"); AMM_SELL = bytes.fromhex("3e2f370aa503dc2a")
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
COLS = [("slot", "q", True), ("idx", "I", False), ("k", "B", False), ("bt", "q", True), ("side", "B", False),
        ("sol", "Q", False), ("tok", "Q", False), ("vsol", "Q", False), ("vtok", "Q", False), ("fee", "Q", False),
        ("tip", "Q", False), ("prog", "B", False), ("mint", "I", False), ("user", "I", False)]
NI = 12   # integer columns before the two string-id columns

def rows_of(rec):
    if rec.get("err") is not None or not rec.get("ev"): return []
    out = []; fee = rec.get("fee") or 0; tip = sum(t[1] for t in rec.get("tips") or [] if t[1] > 0)
    for k, e in enumerate(rec["ev"]):
        try: raw = base64.b64decode(e + "=" * (-len(e) % 4))
        except Exception: continue
        d = raw[:8]
        if d == TRADE and len(raw) >= 113:
            u = lambda o: int.from_bytes(raw[o:o + 8], "little")
            out.append((rec["s"], rec["i"], k, rec.get("bt") or 0, 1 if raw[56] == 1 else 0, u(40), u(48), u(97), u(105), fee, tip, 0,
                        b58(raw[8:40]), b58(raw[57:89])))
        elif (d == AMM_BUY or d == AMM_SELL) and len(raw) >= 184:
            v = struct.unpack_from("<q13Q", raw, 8); pool = b58(raw[120:152]); user = b58(raw[152:184]); mint = None
            for m, owner, a, b in rec.get("tb") or []:
                if owner == pool: mint = m; break
            if mint is None: mint = (rec.get("mints") or [""])[0]
            out.append((rec["s"], rec["i"], k, rec.get("bt") or 0, 1 if d == AMM_BUY else 0, v[7], v[1], v[6], v[5], fee, tip, 1, mint or "", user))
    return out

def parse_file(args):
    """worker: one chunk -> compact columns (bytes) + mint/user strings, rows in (slot, idx, k) order"""
    path, lo_bt, hi_bt = args
    rows = []; ok = True
    try:
        with gzip.open(path, "rb") as f:
            for line in f:
                if not line.endswith(b"\n"): ok = False; break
                r = json.loads(line); bt = r.get("bt") or 0
                if lo_bt is not None and not (lo_bt <= bt < hi_bt): continue
                rows.extend(rows_of(r))
    except (EOFError, OSError, zlib.error): ok = False
    rows.sort(key=lambda x: (x[0], x[1], x[2]))
    cols = [array.array(COLS[j][1], [r[j] for r in rows]).tobytes() for j in range(NI)]
    return path, len(rows), cols, [r[12] for r in rows], [r[13] for r in rows], ok

def enc(a, delta):
    if delta:
        d = array.array("q", bytes(8 * len(a))); prev = 0
        for j, x in enumerate(a): d[j] = x - prev; prev = x
        a = d
    b = a.tobytes(); w = a.itemsize
    return b"".join(b[j::w] for j in range(w)) if w > 1 else b
def dec(blob, tc, delta, n):
    w = array.array(tc).itemsize
    if w > 1 and n:
        b = bytearray(n * w)
        for j in range(w): b[j::w] = blob[j * n:(j + 1) * n]
        blob = bytes(b)
    a = array.array("q" if delta else tc); a.frombytes(blob)
    if delta:
        s = 0
        for j in range(len(a)): s += a[j]; a[j] = s
    return a
def comp(b, codec): return lzma.compress(b, preset=6) if codec == "lzma" else zlib.compress(b, 9)
def decomp(b, codec): return lzma.decompress(b) if codec == "lzma" else zlib.decompress(b)

class Writer:
    def __init__(self, path, codec):
        self.path, self.codec = path, codec; self.body = open(path + ".body.tmp", "wb")
        self.buf = [array.array(t, []) for _, t, _ in COLS]; self.blocks = []; self.n = 0
        self.ids = [{}, {}]; self.raw = [0] * len(COLS); self.clen = [0] * len(COLS)
    def add(self, cols, mints, users, keep=None):
        arrs = [array.array(COLS[j][1]) for j in range(NI)]
        for j in range(NI): arrs[j].frombytes(cols[j])
        for t in range(len(mints)):
            if keep is not None and not keep[t]: continue
            for j in range(NI): self.buf[j].append(arrs[j][t])
            for q, s in ((0, mints[t]), (1, users[t])):
                v = self.ids[q].get(s)
                if v is None: v = self.ids[q][s] = len(self.ids[q])
                self.buf[NI + q].append(v)
            if len(self.buf[0]) >= BLOCK: self.flush()
    def flush(self):
        n = len(self.buf[0])
        if not n: return
        lens = []
        for j, (name, tc, delta) in enumerate(COLS):
            raw = enc(self.buf[j], delta); c = comp(raw, self.codec); self.body.write(c); lens.append(len(c))
            self.raw[j] += len(raw); self.clen[j] += len(c)
        self.blocks.append(dict(rows=n, lengths=lens)); self.n += n
        self.buf = [array.array(t, []) for _, t, _ in COLS]
    def close(self, meta):
        self.flush(); tables = []
        for q in range(2):
            t = comp("\n".join(sorted(self.ids[q], key=self.ids[q].get)).encode(), self.codec); self.body.write(t); tables.append(dict(n=len(self.ids[q]), length=len(t)))
        self.body.close()
        hdr = dict(version=1, rows=self.n, codec=self.codec, columns=[dict(name=c[0], dtype=c[1], delta=c[2], raw=self.raw[j], length=self.clen[j]) for j, c in enumerate(COLS)],
                   blocks=self.blocks, tables=dict(mint=tables[0], user=tables[1]), created=time.time(), **meta,
                   notes="fee/tip are per transaction; vsol/vtok: curve virtual reserves after the trade (prog 0) / pool quote/base reserves (prog 1); mint/user are ids into the tables")
        with open(self.path + ".tmp", "wb") as out, open(self.path + ".body.tmp", "rb") as body:
            out.write(MAGIC); out.write(json.dumps(hdr).encode() + b"\n")
            while True:
                b = body.read(1 << 22)
                if not b: break
                out.write(b)
        os.replace(self.path + ".tmp", self.path); os.remove(self.path + ".body.tmp")
        return hdr

def load(path, cols=None):
    """-> (header, {col: array}) ; mint/user come back as lists of strings"""
    with open(path, "rb") as f:
        assert f.readline() == MAGIC, "not a slim file"
        hdr = json.loads(f.readline()); data = f.read()
    codec = hdr["codec"]; want = [c for c in COLS if not cols or c[0] in cols]
    out = {c[0]: array.array("q" if c[2] else c[1]) for c in want}; off = 0
    for b in hdr["blocks"]:
        for j, (name, tc, delta) in enumerate(COLS):
            L = b["lengths"][j]
            if name in out: out[name].extend(dec(decomp(data[off:off + L], codec), tc, delta, b["rows"]))
            off += L
    for name in ("mint", "user"):
        t = hdr["tables"][name]; blob = data[off:off + t["length"]]; off += t["length"]
        if name in out:
            names = decomp(blob, codec).decode().split("\n") if t["n"] else []
            out[name] = [names[i] for i in out[name]]
    return hdr, out

def build_day(day, codec="lzma", workers=8, out_dir=None):
    c = R.cat_load(); lo, hi = R.day_start(day), R.day_start(R.next_day(day))
    srcs = []
    dp = R.local_day_path(day)
    if dp: srcs.append(("rec:" + day, sorted(glob.glob(os.path.join(dp, "txs", "*.jsonl.gz"))), None))
    else:
        for run, e in sorted(c.get("runs", {}).items()):
            files = [f for f in e.get("files", []) if f["p"].startswith("txs/") and f.get("bt") and None not in f["bt"] and f["bt"][1] >= lo and f["bt"][0] < hi]
            if files:
                srcs.append((run, [os.path.join(e["path"], f["p"]) for f in sorted(files, key=lambda f: f["slot"][0])], min(f["slot"][0] for f in files)))
    if not srcs: raise SystemExit(f"no data for {day} on this host (fetch it first, or run rec catalog --legacy)")
    out_dir = out_dir or R.SLIM; os.makedirs(out_dir, exist_ok=True); path = os.path.join(out_dir, f"{day}.slim")
    t0 = time.time(); W = Writer(path, codec); seen = set(); dup = 0; partial = []; lo_s = hi_s = None
    with ProcessPoolExecutor(workers) as ex:
        for si, (name, files, _) in enumerate(srcs):
            nxt_first = srcs[si + 1][2] if si + 1 < len(srcs) else None
            for p, n, cols, mints, users, ok in ex.map(parse_file, [(f, lo, hi) for f in files], chunksize=1):
                if not ok: partial.append(os.path.basename(p))
                if not n: continue
                sl = array.array("q"); sl.frombytes(cols[0]); ix = array.array("I"); ix.frombytes(cols[1]); kk = array.array("B"); kk.frombytes(cols[2])
                keep = None
                if seen or nxt_first is not None:
                    keep = []
                    for t in range(n):
                        key = (sl[t], ix[t], kk[t])
                        if key in seen: dup += 1; keep.append(False); continue
                        keep.append(True)
                        if nxt_first is not None and sl[t] >= nxt_first: seen.add(key)
                W.add(cols, mints, users, keep)
                lo_s = sl[0] if lo_s is None else min(lo_s, sl[0]); hi_s = sl[-1] if hi_s is None else max(hi_s, sl[-1])
    hdr = W.close(dict(day=day, tz="PKT (UTC+5)", sources=[s for s, _, _ in srcs], dup_removed=dup, partial_chunks=partial, slot_range=[lo_s, hi_s]))
    hdr["seconds"] = round(time.time() - t0, 1); hdr["bytes"] = os.path.getsize(path); hdr["sha256"] = R.sha256_file(path)
    return path, hdr

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "build":
        p, h = build_day(sys.argv[2], codec=(sys.argv[3] if len(sys.argv) > 3 else "lzma"))
        print(json.dumps(dict(file=p, rows=h["rows"], MB=round(h["bytes"] / 1e6, 1), seconds=h["seconds"], bytes_per_row=round(h["bytes"] / max(1, h["rows"]), 2),
                              per_column_MB={c["name"]: round(c["length"] / 1e6, 2) for c in h["columns"]}, tables={k: v["n"] for k, v in h["tables"].items()},
                              sources=h["sources"], dup_removed=h["dup_removed"], partial=len(h["partial_chunks"]))))
    elif cmd == "info":
        with open(sys.argv[2], "rb") as f: f.readline(); print(f.readline().decode()[:3000])
    elif cmd == "cat":
        h, d = load(sys.argv[2]); n = int(sys.argv[3]) if len(sys.argv) > 3 else 20
        names = [c[0] for c in COLS]; print("\t".join(names))
        for j in range(min(n, h["rows"])): print("\t".join(str(d[c][j]) for c in names))
    else: print("slim.py build <day> [lzma|zlib] | info <file> | cat <file> [n]")
