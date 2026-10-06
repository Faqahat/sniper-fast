"""Solana helpers: base58, signatures, transaction messages and getTransaction results (standard library only)."""
from __future__ import annotations

import base64
import json

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_IDX = {c: i for i, c in enumerate(B58)}

SYSTEM = "11111111111111111111111111111111"
COMPUTE_BUDGET = "ComputeBudget111111111111111111111111111111"
TOKEN = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
ATA = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
WSOL = "So11111111111111111111111111111111111111112"
PUMPSWAP = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
DLMM = "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"
DAMM_V2 = "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG"
RAY_CPMM = "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C"
RAY_AMM_V4 = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"

VENUE_PROGRAMS = {
    PUMPSWAP: "PumpSwap",
    DLMM: "Dlmm",
    DAMM_V2: "DammV2",
    RAY_CPMM: "RayCpmm",
    RAY_AMM_V4: "RayAmmV4",
}
# PLAN-ADDENDUM WP-21: the concentrated-liquidity venues the engine prices behind `[pools] rayclmm` / `whirlpool` (the
# cu-table samples their legs by swap steps; the other reports keep the five venues above)
RAY_CLMM = "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"
WHIRLPOOL = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
CLMM_PROGRAMS = {RAY_CLMM: "RayClmm", WHIRLPOOL: "Whirlpool"}
TOKEN_PROGRAMS = {TOKEN, TOKEN_2022}


def b58encode(b: bytes) -> str:
    n = int.from_bytes(b, "big")
    out = []
    while n:
        n, r = divmod(n, 58)
        out.append(B58[r])
    pad = len(b) - len(b.lstrip(b"\0"))
    return "1" * pad + "".join(reversed(out))


def b58decode(s: str) -> bytes:
    n = 0
    for c in s:
        n = n * 58 + _B58_IDX[c]
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    pad = len(s) - len(s.lstrip("1"))
    return b"\0" * pad + body


def sig8(sig: str) -> str:
    """The `sig8` key of txarr/poh: the first 8 signature bytes as 16 lowercase hex characters."""
    raw = b58decode(sig)
    raw = raw.rjust(64, b"\0")
    return raw[:8].hex()


def _cu16(b: bytes, p: int) -> tuple[int, int]:
    v = 0
    for i in range(3):
        x = b[p + i]
        v |= (x & 0x7F) << (7 * i)
        if not x & 0x80:
            return v, p + i + 1
    raise ValueError("bad compact-u16")


def parse_wire(raw: bytes) -> dict:
    """Parse a serialized transaction (legacy or v0): signatures, header, static keys, blockhash, instructions,
    lookup tables. Account indices refer to static keys, then loaded writable, then loaded readonly."""
    n, p = _cu16(raw, 0)
    sigs = [b58encode(raw[p + 64 * i:p + 64 * (i + 1)]) for i in range(n)]
    p += 64 * n
    version = "legacy"
    if raw[p] & 0x80:
        version = str(raw[p] & 0x7F)
        p += 1
    nreq, nro_signed, nro_unsigned = raw[p], raw[p + 1], raw[p + 2]
    p += 3
    nk, p = _cu16(raw, p)
    keys = [b58encode(raw[p + 32 * i:p + 32 * (i + 1)]) for i in range(nk)]
    p += 32 * nk
    blockhash = b58encode(raw[p:p + 32])
    p += 32
    ni, p = _cu16(raw, p)
    ixs = []
    for _ in range(ni):
        prog = raw[p]
        p += 1
        na, p = _cu16(raw, p)
        accts = list(raw[p:p + na])
        p += na
        nd, p = _cu16(raw, p)
        data = raw[p:p + nd]
        p += nd
        ixs.append({"p": prog, "a": accts, "d": base64.b64encode(data).decode()})
    lookups = []
    if version != "legacy":
        nl, p = _cu16(raw, p)
        for _ in range(nl):
            table = b58encode(raw[p:p + 32])
            p += 32
            nw, p = _cu16(raw, p)
            w = list(raw[p:p + nw])
            p += nw
            nr, p = _cu16(raw, p)
            r = list(raw[p:p + nr])
            p += nr
            lookups.append({"table": table, "w": w, "r": r})
    return {"signatures": sigs, "version": version, "header": [nreq, nro_signed, nro_unsigned], "keys": keys,
            "recent_blockhash": blockhash, "ixs": ixs, "alts": lookups}


def tx_error(err) -> str | None:
    """MEASUREMENT §4.14 `err` text from a JSON-RPC TransactionError: `ix<i>:custom:0x<code>`, `ix<i>:ie<variant>`,
    `tx<variant>` (variant names, since JSON-RPC gives names, not bincode numbers)."""
    if err is None:
        return None
    if isinstance(err, str):
        return f"tx{err}"
    if isinstance(err, dict) and "InstructionError" in err:
        ix, e = err["InstructionError"]
        if isinstance(e, dict) and "Custom" in e:
            return f"ix{ix}:custom:0x{int(e['Custom']):x}"
        name = e if isinstance(e, str) else next(iter(e))
        return f"ix{ix}:ie{name}"
    if isinstance(err, dict):
        return f"tx{next(iter(err))}"
    return f"tx{err}"


def custom_code(err) -> str | None:
    if isinstance(err, dict) and "InstructionError" in err:
        e = err["InstructionError"][1]
        if isinstance(e, dict) and "Custom" in e:
            return f"0x{int(e['Custom']):x}"
    return None


class TxView:
    """A getTransaction result (`json`, `jsonParsed` or `base64` encoding) seen as plain fields."""

    def __init__(self, res: dict, sig: str | None = None):
        if "result" in res and "meta" not in res:
            res = res["result"]
        self.res = res
        self.meta = res.get("meta") or {}
        self.slot = res.get("slot")
        self.block_time = res.get("blockTime")
        tx = res.get("transaction")
        msg: dict = {}
        if isinstance(tx, list):  # [data, "base64"]
            w = parse_wire(base64.b64decode(tx[0]))
            self.sigs = w["signatures"]
            static = w["keys"]
            self.header = w["header"]
            self.ixs = w["ixs"]
            self.version = w["version"]
            self.alts = w["alts"]
            self.recent_blockhash = w["recent_blockhash"]
        else:
            msg = (tx or {}).get("message") or {}
            self.sigs = (tx or {}).get("signatures") or []
            static = [k if isinstance(k, str) else k.get("pubkey") for k in msg.get("accountKeys") or []]
            h = msg.get("header") or {}
            self.header = [h.get("numRequiredSignatures", 1), h.get("numReadonlySignedAccounts", 0),
                           h.get("numReadonlyUnsignedAccounts", 0)]
            self.ixs = msg.get("instructions") or []
            v = res.get("version", "legacy")
            self.version = str(v)
            self.alts = msg.get("addressTableLookups") or []
            self.recent_blockhash = msg.get("recentBlockhash")
        la = self.meta.get("loadedAddresses") or {}
        self.n_static = len(static)
        self.keys = list(static) + list(la.get("writable") or []) + list(la.get("readonly") or [])
        self.sig = sig or (self.sigs[0] if self.sigs else None)

    @classmethod
    def from_exec(cls, rec: dict) -> "TxView":
        """A v2 exec.jsonl / wallet.jsonl record (§4.14) as a TxView."""
        def tok(rows):
            return [{"accountIndex": r["i"], "mint": r.get("mint"), "owner": r.get("owner"), "programId": r.get("prog"),
                     "uiTokenAmount": {"amount": str(r.get("amount") or "0"), "decimals": r.get("dec")}} for r in rows or []]
        meta = {"fee": rec.get("fee"), "err": None if rec.get("ok") else (rec.get("err") or "failed"),
                "preBalances": rec.get("pre") or [], "postBalances": rec.get("post") or [],
                "preTokenBalances": tok(rec.get("pre_tok")), "postTokenBalances": tok(rec.get("post_tok")),
                "innerInstructions": [{"index": g.get("ix"), "instructions": [
                    {"p": x.get("p"), "a": x.get("a"), "d": x.get("d"), "stackHeight": x.get("h")} for x in g.get("list") or []]}
                    for g in rec.get("inner") or []],
                "logMessages": rec.get("logs"), "computeUnitsConsumed": rec.get("cu")}
        v = cls.__new__(cls)
        v.res = {"slot": rec.get("slot"), "meta": meta}
        v.meta = meta
        v.slot = rec.get("slot")
        v.block_time = None
        v.sigs = [rec.get("sig")]
        v.keys = list(rec.get("keys") or [])
        v.n_static = rec.get("n_static") or len(v.keys)
        v.header = None
        v.ixs = rec.get("ixs") or []
        v.version = rec.get("version")
        v.alts = rec.get("alts") or []
        v.recent_blockhash = rec.get("recent_blockhash")
        v.sig = rec.get("sig")
        return v

    @property
    def signer(self) -> str | None:
        return self.keys[0] if self.keys else None

    @property
    def err(self):
        return self.meta.get("err")

    @property
    def ok(self) -> bool:
        return self.meta.get("err") is None

    @property
    def fee(self) -> int:
        return int(self.meta.get("fee") or 0)

    def balance_delta(self, i: int) -> int:
        pre, post = self.meta.get("preBalances") or [], self.meta.get("postBalances") or []
        if i >= len(pre) or i >= len(post):
            return 0
        return int(post[i]) - int(pre[i])

    def token_rows(self, side: str) -> list:
        return self.meta.get("preTokenBalances" if side == "pre" else "postTokenBalances") or []

    def token_amounts(self, side: str) -> dict:
        """{account index: (mint, owner, raw amount, program)}"""
        out = {}
        for r in self.token_rows(side):
            ui = r.get("uiTokenAmount") or {}
            out[int(r["accountIndex"])] = (r.get("mint"), r.get("owner"), int(ui.get("amount") or 0), r.get("programId"))
        return out

    def owner_token_delta(self, owner: str) -> dict:
        """{mint: raw amount change} over token accounts `owner` owns (absent on one side counts as 0)."""
        d: dict = {}
        for side, sign in (("pre", -1), ("post", 1)):
            for _i, (mint, own, amt, _p) in self.token_amounts(side).items():
                if own == owner:
                    d[mint] = d.get(mint, 0) + sign * amt
        return {m: v for m, v in d.items() if v != 0}

    def logs(self) -> list | None:
        return self.meta.get("logMessages")

    def _ix(self, ix: dict, top: int, depth: int) -> "Ix":
        if "parsed" in ix or ("programId" in ix and "programIdIndex" not in ix):
            prog = ix.get("programId")
            parsed = ix.get("parsed") if isinstance(ix.get("parsed"), dict) else None
            accts = ix.get("accounts") or []
            data = None
            if isinstance(ix.get("data"), str):
                try:
                    data = b58decode(ix["data"])
                except KeyError:
                    data = None
            return Ix(top, depth, prog, [a for a in accts if isinstance(a, str)], data, parsed)
        if "programIdIndex" in ix:
            prog = self.keys[ix["programIdIndex"]] if ix["programIdIndex"] < len(self.keys) else None
            accts = [self.keys[i] for i in ix.get("accounts") or [] if i < len(self.keys)]
            d = ix.get("data")
            try:
                data = b58decode(d) if isinstance(d, str) else None
            except KeyError:
                data = None
            return Ix(top, depth, prog, accts, data, None)
        # parse_wire / exec.jsonl shape: {p, a, d(base64)}
        prog = self.keys[ix["p"]] if ix.get("p") is not None and ix["p"] < len(self.keys) else None
        accts = [self.keys[i] for i in ix.get("a") or [] if i < len(self.keys)]
        return Ix(top, depth, prog, accts, base64.b64decode(ix.get("d") or ""), None)

    def instructions(self) -> list:
        """Top-level and inner instructions in execution order: Ix(top, depth, program, accounts, data, parsed)."""
        inner: dict = {}
        for grp in self.meta.get("innerInstructions") or []:
            inner[grp.get("index")] = grp.get("instructions") or []
        out = []
        for i, ix in enumerate(self.ixs):
            out.append(self._ix(ix, i, 1))
            for sub in inner.get(i, []):
                depth = sub.get("stackHeight") or 2
                out.append(self._ix(sub, i, depth))
        return out


class Ix:
    __slots__ = ("top", "depth", "program", "accounts", "data", "parsed")

    def __init__(self, top, depth, program, accounts, data, parsed):
        self.top, self.depth, self.program, self.accounts, self.data, self.parsed = top, depth, program, accounts, data, parsed

    def system(self) -> dict | None:
        """System instruction: {type, from, to, lamports, owner} for create/transfer; None otherwise."""
        if self.program != SYSTEM:
            return None
        if self.parsed:
            t, info = self.parsed.get("type"), self.parsed.get("info") or {}
            if t in ("createAccount", "createAccountWithSeed"):
                return {"type": "create", "from": info.get("source"), "to": info.get("newAccount"),
                        "lamports": int(info.get("lamports") or 0), "owner": info.get("owner")}
            if t == "transfer":
                return {"type": "transfer", "from": info.get("source"), "to": info.get("destination"),
                        "lamports": int(info.get("lamports") or 0)}
            if t == "advanceNonce":
                return {"type": "advance_nonce", "nonce": info.get("nonceAccount")}
            return {"type": t}
        d = self.data or b""
        if len(d) < 4:
            return None
        t = int.from_bytes(d[:4], "little")
        a = self.accounts
        if t == 0 and len(d) >= 52 and len(a) >= 2:
            return {"type": "create", "from": a[0], "to": a[1], "lamports": int.from_bytes(d[4:12], "little"),
                    "owner": b58encode(d[20:52])}
        if t == 3 and len(a) >= 2:
            try:
                n = int.from_bytes(d[36:44], "little")
                p = 44 + n
                return {"type": "create", "from": a[0], "to": a[1], "lamports": int.from_bytes(d[p:p + 8], "little"),
                        "owner": b58encode(d[p + 16:p + 48])}
            except Exception:
                return {"type": "create_with_seed"}
        if t == 2 and len(d) >= 12 and len(a) >= 2:
            return {"type": "transfer", "from": a[0], "to": a[1], "lamports": int.from_bytes(d[4:12], "little")}
        if t == 4:
            return {"type": "advance_nonce", "nonce": a[0] if a else None}
        if t == 6:
            return {"type": "initialize_nonce", "nonce": a[0] if a else None}
        return {"type": f"system{t}"}

    def token(self) -> dict | None:
        """SPL Token / Token-2022 instruction: {type, account, destination} for close; {type} otherwise."""
        if self.program not in TOKEN_PROGRAMS:
            return None
        if self.parsed:
            t, info = self.parsed.get("type"), self.parsed.get("info") or {}
            if t == "closeAccount":
                return {"type": "close", "account": info.get("account"), "destination": info.get("destination")}
            return {"type": t}
        d = self.data or b""
        if not d:
            return None
        if d[0] == 9 and len(self.accounts) >= 2:
            return {"type": "close", "account": self.accounts[0], "destination": self.accounts[1]}
        if d[0] == 17:
            return {"type": "syncNative"}
        return {"type": f"token{d[0]}"}


def load_tx_file(path: str) -> list:
    """Read wallet transactions: a single getTransaction JSON (`<sig>.json`), or JSON lines of
    {"sig": ..., "tx": <result>} (the research capture format)."""
    import lzma

    opener = lzma.open if path.endswith(".xz") else open
    with opener(path, "rt") as f:
        text = f.read()
    out = []
    text_s = text.lstrip()
    if text_s.startswith("{") and "\n{" not in text_s.strip():
        obj = json.loads(text_s)
        if "tx" in obj and isinstance(obj["tx"], dict):
            out.append(TxView(obj["tx"], obj.get("sig")))
        else:
            out.append(TxView(obj))
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if "tx" in obj:
            if obj["tx"] is None:
                continue
            out.append(TxView(obj["tx"], obj.get("sig")))
        else:
            out.append(TxView(obj))
    return out
