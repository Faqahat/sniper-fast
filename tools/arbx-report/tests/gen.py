"""Deterministic generator of a synthetic arbx v2 segment (MEASUREMENT.md §4 schemas), used by the tests and by the
golden report. Every stream is written the way the bot writes it: JSON-lines with a header line, rotated/compressed
streams as `<name>.000.<ext>.zst` (raw-block zstd frames), plain streams uncompressed, binary accounts/journal.

The scenario (pools A = PumpSwap, B = DLMM; wallet W; slots 1000-1013):
- attempt 0: trigger T0 @1000/10; ours O0 lands @1000/40 and wins            -> closer = ours
- attempt 1: trigger T1 @1003/5; F1 (arb bot, failed) @1003/6 touches the route; S1 (single-pool user swap) @1003/7
             closes the gap (net 0 <= min_profit)                            -> closer = S1 (user_swap), attempted = [F1]
- attempt 2: trigger T2 @1006/3; W2 (two-pool arb) @1006/9 and Y3 @1010/4 leave net above min_profit; ours O2 lands
             failed @1007/12                                                  -> persisted (complete)
- attempt 3: trigger T3 @1008/2; slot 1013 has no slot-index line            -> persisted_incomplete; outcome amended
- attempt 4: signed, never sent (copy t_sent = 0)                            -> not in the land-rate denominator
Slots 1008-1011 are shared by attempts 2 and 3 (blockctx deduplication)."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from arbx_report import solana, zstd  # noqa: E402

T0_NS = 1_791_100_000_000_000_000
RUN = "synth-p1"


def pk(name: str) -> str:
    return solana.b58encode(hashlib.sha256(b"pk:" + name.encode()).digest())


def sg(name: str) -> str:
    return solana.b58encode(hashlib.sha512(b"sig:" + name.encode()).digest())


def t_slot(slot: int, ms: float = 0.0) -> int:
    return T0_NS + (slot - 1000) * 400_000_000 + int(ms * 1_000_000)


W = pk("wallet")
WSOL_ATA = pk("wallet-wsol")
TIP = "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5"  # a Jito tip account
ROUTE = pk("arbx-exec")
MINT = pk("mint-M")
PA, VA0, VA1 = pk("pool-A"), pk("pool-A-v0"), pk("pool-A-v1")
PB, VB0, VB1, BA = pk("pool-B"), pk("pool-B-v0"), pk("pool-B-v1"), pk("pool-B-bins")
POOL_A = [PA, VA0, VA1]
POOL_B = [PB, VB0, VB1, BA]
ROUTE_ACCTS = POOL_A + POOL_B
L1, L2, L3 = pk("leader-1"), pk("leader-2"), pk("leader-3")

S = {n: sg(n) for n in ["T0", "O0", "T1", "F1", "S1", "O1", "T2", "W2", "O2", "T3", "Y3", "O3", "O4", "Z9"]}
SIGNERS = {"T0": pk("user-0"), "T1": pk("user-1"), "F1": pk("bot-R1"), "S1": pk("user-2"), "T2": pk("user-3"),
           "W2": pk("bot-R2"), "T3": pk("user-4"), "Y3": pk("user-5"), "O0": W, "O2": W, "Z9": pk("user-9")}
# (slot, idx, writes, ok, venues, pools)
TXS = {
    "T0": (1000, 10, POOL_A, True, ["PumpSwap"], [PA]),
    "O0": (1000, 40, POOL_A + POOL_B, True, ["PumpSwap", "Dlmm"], [PA, PB]),
    "T1": (1003, 5, POOL_B, True, ["Dlmm"], [PB]),
    "F1": (1003, 6, [], False, ["PumpSwap", "Dlmm"], [PA, PB]),
    "S1": (1003, 7, POOL_A, True, ["PumpSwap"], [PA]),
    "T2": (1006, 3, POOL_A, True, ["PumpSwap"], [PA]),
    "W2": (1006, 9, POOL_A + POOL_B, True, ["PumpSwap", "Dlmm"], [PA, PB]),
    "O2": (1007, 12, [], False, ["PumpSwap", "Dlmm"], [PA, PB]),
    "T3": (1008, 2, POOL_B, True, ["Dlmm"], [PB]),
    "Y3": (1010, 4, POOL_A, True, ["PumpSwap"], [PA]),
    "Z9": (1009, 1, [], True, [], []),
}


# ------------------------------------------------------------------------------------------------ writers

def header(stream: str, ver: str, seq: int = 0) -> dict:
    return {"schema": f"arbx.{stream}/{ver}", "run": RUN, "file_seq": seq, "started_ns": T0_NS, "producer": "synth000"}


def jl(rows) -> bytes:
    return "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows).encode()


def write_plain(d, name, stream, ver, rows):
    with open(os.path.join(d, name), "wb") as f:
        f.write(jl([header(stream, ver)] + rows))


def write_z(d, name, data: bytes, frames: int = 1):
    """Raw-block zstd, optionally split into several frames (as the bot's per-flush frames)."""
    out = b""
    if frames <= 1:
        out = zstd.compress_raw(data)
    else:
        step = max(1, len(data) // frames)
        for i in range(0, len(data), step):
            out += zstd.compress_raw(data[i:i + step])
    with open(os.path.join(d, name), "wb") as f:
        f.write(out)


def write_zjsonl(d, stream, ver, rows, frames=2):
    write_z(d, f"{stream}.000.jsonl.zst", jl([header(stream, ver)] + rows), frames)


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


# ------------------------------------------------------------------------------------------------ binary

def accounts_bin(records: list, accts: list, gaps: dict | None = None) -> bytes:
    """`gaps`: {aseq: (first_lost, n_lost)} writes a GAP record just before the record with that aseq."""
    hdr = json.dumps(header("accounts", "2.0"), sort_keys=True).encode()
    out = bytearray(b"ARBXACC\0" + struct.pack("<HH", 2, len(hdr)) + hdr)
    ids = {}
    roles = {PA: 1, PB: 1, VA0: 2, VA1: 2, VB0: 2, VB1: 2, BA: 4}
    pidx = {PA: 0, VA0: 0, VA1: 0, PB: 1, VB0: 1, VB1: 1, BA: 1}
    for a in accts:
        ids[a] = len(ids)
        body = struct.pack("<I", ids[a]) + solana.b58decode(a).rjust(32, b"\0") + bytes([roles.get(a, 0)]) + struct.pack("<I", pidx.get(a, 0xFFFFFFFF))
        out += bytes([1]) + struct.pack("<I", len(body)) + body
    last = {}
    count = {}
    for (aseq, acct, slot, wv, t, txn, data) in records:
        if gaps and aseq in gaps:
            g = struct.pack("<QQ", *gaps[aseq])
            out += bytes([6]) + struct.pack("<I", len(g)) + g
        kind = 2
        payload = data
        if acct in last and len(last[acct]) == len(data) and count.get(acct, 0) % 64 != 0:
            kind = 3
            payload = bytes(x ^ y for x, y in zip(data, last[acct]))
        count[acct] = count.get(acct, 0) + 1
        last[acct] = data
        flags = 1 if txn else 0
        body = struct.pack("<QIQQQBB", aseq, ids[acct], slot, wv, t, 0 if txn else 1, flags)
        if txn:
            body += solana.b58decode(txn).rjust(64, b"\0")
        body += struct.pack("<Q", 2_039_280) + solana.b58decode(solana.PUMPSWAP).rjust(32, b"\0")
        body += struct.pack("<QI", 0, len(payload)) + payload
        out += bytes([kind]) + struct.pack("<I", len(body)) + body
    mark = struct.pack("<QBI", t_slot(1000), 2, 0)
    out += bytes([4]) + struct.pack("<I", len(mark)) + mark
    return bytes(out)


def wire_tx(signer: str) -> bytes:
    """A minimal legacy transaction: 1 signature, 1 key, no instructions."""
    return (bytes([1]) + bytes(64) + bytes([1, 0, 0]) + bytes([1]) + solana.b58decode(signer).rjust(32, b"\0")
            + bytes(32) + bytes([0]))


def journal_bin() -> bytes:
    hdr = json.dumps(header("journal", "2.0"), sort_keys=True).encode()
    out = bytearray(b"ARBXJRN\0" + struct.pack("<HH", 2, len(hdr)) + hdr)
    seq = 0

    def rec(kind, t, body):
        nonlocal seq
        out.extend(struct.pack("<BIQQ", kind, len(body), seq, t) + body)
        seq += 1

    raw = wire_tx(W)
    rec(4, t_slot(1000), struct.pack("<QQiQ", 1000, 999, 1, t_slot(1000)))
    rec(1, t_slot(1000, 1), struct.pack("<HQQQbBI", 0, 1000, t_slot(1000, 1), t_slot(1000, 1), -1, 0, len(raw)) + raw + bytes([0, 0]))
    rec(3, t_slot(1000, 2), struct.pack("<QB", 0, 0))
    payload = json.dumps({"mode": "live"}).encode()
    rec(7, t_slot(1000, 3), struct.pack("<BI", 3, len(payload)) + payload)
    rec(10, t_slot(1000, 4), struct.pack("<Q", t_slot(1000, 4)))
    rec(8, t_slot(1000, 5), b"")
    return bytes(out)


# ------------------------------------------------------------------------------------------------ chain rows

def logs_for(name: str) -> list:
    v = TXS[name][4]
    if name.startswith("O"):
        lines = [f"Program {ROUTE} invoke [1]"]
        cu = {"PumpSwap": 40_000, "Dlmm": 60_000}
        for x in v:
            prog = solana.PUMPSWAP if x == "PumpSwap" else solana.DLMM
            lines += [f"Program {prog} invoke [2]", f"Program {prog} consumed {cu[x]} of 180000 compute units", f"Program {prog} success"]
        lines += [f"Program {ROUTE} consumed 120000 of 200000 compute units", f"Program {ROUTE} success"]
        return lines
    lines = []
    for i, x in enumerate(v):
        prog = solana.PUMPSWAP if x == "PumpSwap" else solana.DLMM
        cu = 41_000 + 1000 * i + (len(name) * 7) if x == "PumpSwap" else 61_000 + 500 * i
        lines += [f"Program {prog} invoke [1]", f"Program {solana.TOKEN} invoke [2]",
                  f"Program {solana.TOKEN} consumed 4645 of 150000 compute units", f"Program {solana.TOKEN} success",
                  f"Program {prog} consumed {cu} of 200000 compute units", f"Program {prog} success"]
    return lines


def exec_row(name: str, *, idx_null: bool = False) -> dict:
    slot, idx, writes, ok, venues, pools = TXS[name]
    signer = SIGNERS[name]
    touched = sorted(set(writes) | (set(POOL_A + POOL_B) if name in ("F1", "O2") else set()))
    keys = [signer] + touched + ([solana.PUMPSWAP] if "PumpSwap" in venues else []) + ([solana.DLMM] if "Dlmm" in venues else [])
    arb = len(set(pools)) >= 2
    return {"sig": S[name], "slot": slot, "idx": None if idx_null else idx, "src": "grpc-tx" if "PumpSwap" in venues else "rpc-backfill",
            "found_by": ["account_update"] if writes else ["shred"], "t": t_slot(slot, 30), "ok": ok,
            "err": None if ok else "ix2:custom:0x4e580002", "err_ix": None if ok else 2, "why": None, "fee": 5000,
            "cu": 90_000, "cost_units": None, "cu_limit": None, "cu_price_micro": None, "priority_fee": 0,
            "loaded_data_limit": None, "version": "0", "signer": signer, "signers": [signer], "recent_blockhash": pk("bh"),
            "nonce": None, "keys": keys, "n_static": len(keys), "alts": [], "ixs": [], "inner": [], "logs": logs_for(name),
            "return_data": None, "pre": [1_000_000_000] * len(keys), "post": [1_000_000_000 - (5000 if i == 0 else 0) for i in range(len(keys))],
            "pre_tok": [], "post_tok": [], "signer_sol": -5000 if not ok else (120_000 if arb else -5000),
            "signer_tok": {} if arb or not ok else {MINT: "1000"},
            "watched": [{"acct": a, "role": "pool", "pool": 0} for a in writes], "venues": venues, "pools": pools,
            "transfers": [], "tip_total": 10_000 if arb and ok else 0, "tip_senders": ["jito"] if arb and ok else [],
            "jito_tipped": bool(arb and ok), "bundle": None, "arb_like": {"is": arb, "why": "venues" if arb else None},
            "ours": None, "prog_events": None}


def wallet_row(name: str, attempt: int) -> dict:
    """Our transaction with full keys/instructions/balances (the toolkit recomputes the ledger from it)."""
    slot, idx, writes, ok, venues, pools = TXS[name]
    keys = [W, WSOL_ATA, TIP] + POOL_A + POOL_B + [solana.SYSTEM, ROUTE, solana.COMPUTE_BUDGET, solana.PUMPSWAP, solana.DLMM, solana.TOKEN]
    ki = {k: i for i, k in enumerate(keys)}
    tip, fee, gain = (30_000, 5000, 50_000) if ok else (0, 5000, 0)
    pre = [10_000_000_000, 1_002_039_280, 1_000_000] + [2_039_280] * 7 + [1, 1, 1, 1, 1, 1]
    post = list(pre)
    post[0] = pre[0] - fee - tip
    post[1] = pre[1] + gain
    post[2] = pre[2] + tip
    ixs = [{"p": ki[solana.COMPUTE_BUDGET], "a": [], "d": b64(bytes([2]) + struct.pack("<I", 200_000))},
           {"p": ki[ROUTE], "a": [ki[k] for k in [W, WSOL_ATA] + POOL_A + POOL_B], "d": b64(b"\x01")},
           {"p": ki[solana.SYSTEM], "a": [ki[W], ki[TIP]], "d": b64(struct.pack("<IQ", 2, 30_000))}]
    inner = [{"ix": 1, "list": [{"p": ki[solana.PUMPSWAP], "a": [ki[k] for k in POOL_A], "d": b64(b"\x02"), "h": 2},
                                {"p": ki[solana.DLMM], "a": [ki[k] for k in POOL_B], "d": b64(b"\x03"), "h": 2}]}]
    r = exec_row(name)
    r.update({"keys": keys, "n_static": len(keys), "ixs": ixs, "inner": inner, "pre": pre, "post": post,
              "pre_tok": [{"i": 1, "mint": solana.WSOL, "owner": W, "prog": solana.TOKEN, "amount": "1000000000", "dec": 9}],
              "post_tok": [{"i": 1, "mint": solana.WSOL, "owner": W, "prog": solana.TOKEN, "amount": str(1_000_000_000 + gain), "dec": 9}],
              "signer_sol": post[0] - pre[0], "signer_tok": {solana.WSOL: str(gain)} if gain else {}, "src": "rpc-wallet",
              "found_by": ["ours", "account_update"], "ours": {"attempt": attempt}, "attempt": attempt, "wallet_kind": "route",
              "wallet_sol": post[0] - pre[0], "wallet_tok": {solana.WSOL: str(gain)} if gain else {}, "created": [], "closed": [],
              "tip_total": tip, "jito_tipped": True})
    r["logs"] = logs_for(name)
    return r


# ------------------------------------------------------------------------------------------------ segment

def generate(d: str) -> str:
    os.makedirs(d, exist_ok=True)
    # accounts: boot versions (RPC, slot 999) and every route write, in block order
    recs = []
    aseq = 0
    wv = 5000
    for a in ROUTE_ACCTS:
        recs.append((aseq, a, 999, 0, t_slot(999), None, bytes([aseq % 251]) * 16))
        aseq += 1
    order = sorted((v[0], v[1], n) for n, v in TXS.items() if v[2])
    versions = {}
    for slot, idx, n in order:
        for a in TXS[n][2]:
            wv += 1
            data = bytes([(aseq * 7) % 251]) * 16
            recs.append((aseq, a, slot, wv, t_slot(slot, 20 + idx * 0.01), S[n], data))
            versions[(n, a)] = (aseq, wv)
            aseq += 1
    write_z(d, "accounts.000.bin.zst", accounts_bin(recs, ROUTE_ACCTS), frames=3)
    write_z(d, "journal.000.bin.zst", journal_bin())

    def route_in(at_name):
        """route accounts at the version the decision read (the trigger's writes, else boot)"""
        acc = []
        for a in ROUTE_ACCTS:
            best = None
            for (n, aa), (q, w) in versions.items():
                if aa == a and (TXS[n][0], TXS[n][1]) <= (TXS[at_name][0], TXS[at_name][1]):
                    if best is None or q > best[0]:
                        best = (q, w)
            acc.append({"acct": a, "wv": best[1] if best else 0})
        return {"accounts": acc, "dlmm_arrays": {PB: [0]}, "buy_end": None, "sell_end": None}

    # exec (one record without idx, filled by an idx_update line), wallet
    ex = [exec_row(n, idx_null=(n == "Y3")) for n in ["T0", "T1", "F1", "S1", "T2", "W2", "T3", "Y3", "Z9"]]
    ex.append({"sig": S["Y3"], "idx_update": 4, "src": "slotidx"})
    ex += [wallet_row("O0", 0), wallet_row("O2", 2)]  # ours reach exec too (src rpc-wallet)
    write_zjsonl(d, "exec", "2.0", ex, frames=3)
    write_zjsonl(d, "wallet", "1.0", [wallet_row("O0", 0), wallet_row("O2", 2)])
    # slot index (no line for 1013), slots, leaders, blocks
    by_slot: dict = {}
    for n, v in TXS.items():
        by_slot.setdefault(v[0], []).append([S[n], v[1]])
    si = []
    for slot in range(1000, 1013):
        si.append({"slot": slot, "parent_slot": slot - 1, "status": "ok", "blockhash": pk(f"bh{slot}"),
                   "previous_blockhash": pk(f"bh{slot - 1}"), "block_height": slot - 100, "block_time": 1791100000 + (slot - 1000) // 3,
                   "tx_count": 1500 + slot % 7, "tracked": sorted(by_slot.get(slot, []), key=lambda x: x[1]), "missing": [],
                   "idx_check": {"n": len(by_slot.get(slot, [])), "mismatches": 0}, "t_fetch_ns": t_slot(slot, 900),
                   "latency_ms": 35.0, "provider": "synth"})
    write_zjsonl(d, "slotidx", "1.0", si)
    write_zjsonl(d, "slots", "1.0", [{"slot": s, "status": "confirmed", "parent": s - 1, "dead_error": None, "t": t_slot(s, 500)} for s in range(1000, 1014)])
    lead = []
    for s in range(1000, 1014):
        lid, kind = (L1, "jito") if s < 1004 else ((L2, "bam") if s < 1008 else (L3, "jito"))
        lead.append({"slot": s, "leader": lid, "kind": kind, "kind_src": "bundle_result", "kind_age_s": 60,
                     "region": "fra" if kind == "jito" else "ams", "rtt_ms": 3.0, "rtt_age_s": 10, "rtt_src": "quic_handshake",
                     "client": "jito-agave", "t_ns": t_slot(999)})
    write_zjsonl(d, "leaders", "1.0", lead)
    # text logs
    s8 = solana.sig8
    tx_lines = ["# arbx.txarr/1.1 feeds=feedA,feedB"]
    for n in ["T0", "T1", "F1", "S1", "T2", "W2", "T3", "Y3"]:
        slot = TXS[n][0]
        tx_lines.append(f"{s8(S[n])} {slot} {t_slot(slot, 5 + TXS[n][1])} 0 {150 + TXS[n][1]}")
    tx_lines.append(f"{s8(S['O0'])} 1000 {t_slot(1000, 60)} - 0")
    write_z(d, "txarr.000.log.zst", ("\n".join(tx_lines) + "\n").encode())
    poh = ["# arbx.poh/2.0"]
    for n, ms in [("T0", 50.0), ("O0", 61.5), ("T1", 120.0), ("F1", 120.4), ("S1", 121.25), ("T2", 30.0), ("W2", 33.0)]:
        poh.append(f"{s8(S[n])} {TXS[n][0]} {ms:.3f} 0 {TXS[n][1]}")
    write_z(d, "poh.000.log.zst", ("\n".join(poh) + "\n").encode())
    mv = ["# arbx.moves/2.0"]
    for slot, idx, n in order:
        for a in TXS[n][2]:
            if a in (PA, PB):
                mv.append(f"{S[n]} {slot} {a} {t_slot(slot, 20)} {a} {versions[(n, a)][1]} pool")
    write_z(d, "moves.000.log.zst", ("\n".join(mv) + "\n").encode())
    sf = ["# arbx.slots-feed/2.0"]
    for s in range(1000, 1013):
        for f in (0, 1):
            sf.append(f"{f} {s} 64 {700 + s % 5} {1400 + s % 9} {t_slot(s, 1)} {t_slot(s, 399)} 1 - - - - {1 if f == 0 or s % 4 else 0}")
    write_z(d, "slots-feed.000.log.zst", ("\n".join(sf) + "\n").encode())
    # engine streams
    trig = []
    for n in ["T0", "T1", "T2", "T3"]:
        slot, idx = TXS[n][0], TXS[n][1]
        trig.append({"sig": S[n], "feed": 0, "slot": slot, "pool": TXS[n][5][0], "venue": TXS[n][4][0], "source": "seed",
                     "zfo": True, "amount": 1_000_000, "exact_out": False, "executed": True,
                     "st": {"rx": t_slot(slot, 5), "decoded": t_slot(slot, 5.01), "engine": t_slot(slot, 5.02), "resolved": None, "decided": None},
                     "opp": None, "hint_only": True, "signer": SIGNERS[n], "signer_stats": [3, 1], "skip": None,
                     "w_expected": TXS[n][2], "shadow_pred": True})
    trig.append({**trig[0], "sig": sg("hint-skip"), "skip": "will_fail", "shadow_pred": False})
    write_zjsonl(d, "triggers", "2.0", trig)
    commits = []
    for i, n in enumerate(["T0", "T1", "T2", "T3"]):
        slot = TXS[n][0]
        commits.append({"txn": S[n], "slot": slot, "w_src": "tx-stream" if "PumpSwap" in TXS[n][4] else "shred",
                        "w_expected": TXS[n][2], "w_seen": [{"acct": a, "wv": versions[(n, a)][1], "aseq": versions[(n, a)][0], "t": t_slot(slot, 20)} for a in TXS[n][2]],
                        "t_first_shred": t_slot(slot, 5), "t_first_update": t_slot(slot, 20), "t_resolved": t_slot(slot, 21 + i),
                        "spread_ms": 0.5, "outcome": "complete", "lag_ms": 16.0 + i, "late_members": [], "torn_suspect_decisions": [],
                        "pools": TXS[n][5], "evaluated": 1})
    commits.append({**commits[1], "late": True, "late_members": [{"acct": VB0, "wv": 1, "aseq": 99, "t": t_slot(1003, 80)}]})
    write_zjsonl(d, "commits", "1.0", commits)
    att_spec = [  # attempt, trigger, sig, band, min_profit, gross, size, leader, x4 arm
        (0, "T0", "O0", 1, 35_001, 50_000, 100_000_000, (L1, "jito"), "0.6"),
        (1, "T1", "O1", 2, 500_000, 2_000_000, 1_000_000_000, (L1, "jito"), "0.4"),
        (2, "T2", "O2", 2, 500_000, 1_500_000, 900_000_000, (L2, "bam"), "0.6"),
        (3, "T3", "O3", 3, 500_000, 12_000_000, 2_000_000_000, (L3, "jito"), "0.4"),
        (4, "T3", "O4", 3, 500_000, 11_000_000, 2_000_000_000, (L3, "jito"), "0.6"),
    ]
    decisions, attempts, copies, bundles, outcomes = [], [], [], [], []
    for (a, tn, on, band, minp, gross, size, (lid, lkind), arm) in att_spec:
        slot = TXS[tn][0]
        tf = t_slot(slot, 5)
        st = {"t_first_shred": tf, "t_update_recv": tf + 15_000_000, "t_commit": tf + 15_500_000, "t_engine": tf + 15_600_000,
              "t_priced": tf + 15_700_000, "t_decided": tf + 15_750_000}
        routes = [{"buy": PA, "sell": PB, "mint": MINT, "buy_venue": "PumpSwap", "sell_venue": "Dlmm", "size": size,
                   "gross": gross, "net": gross - 5000, "cu": 200_000, "crossed": [0, 1 + a % 3], "reason": "best"},
                  {"buy": PB, "sell": PA, "mint": MINT, "buy_venue": "Dlmm", "sell_venue": "PumpSwap", "size": size // 2,
                   "gross": -1000, "net": -6000, "cu": 200_000, "crossed": [2, 0], "reason": "below_min_profit"}]
        decisions.append({"decision": a, "t_ns": st["t_decided"], "kind": "commit", "trigger": {"txn": S[tn], "slot": slot, "t_first_shred": tf, "pool": TXS[tn][5][0]},
                          "routes": routes, "best": 0, "sv": {"h": f"{a:016x}", "slot_max": slot, "wv_max": 6000 + a},
                          "route_age_ms": 350.0 + 10 * a, "parts_skew_slots": {"buy": 0, "sell": 0}, "w_src": "tx-stream",
                          "torn_suspect": False, "fork_priced": False, "band": band,
                          "crowding": {"signers_6h": 12, "bucket": 0, "src": "map"}, "verdict": "send", "reason": "sent",
                          "ev": gross * 0.1, "rank": 0, "attempt": a, "experiments": {"x4_share": arm}, "stages": st})
        t_sent = None if a == 4 else st["t_decided"] + 1_000_000
        stages = {**st, "t_built": st["t_decided"] + 200_000, "t_signed": st["t_decided"] + 300_000,
                  "t_enqueued": st["t_decided"] + 350_000, "t_dequeued": st["t_decided"] + 900_000,
                  "t_sent": t_sent, "t_ack": None if t_sent is None else t_sent + 800_000}
        attempts.append({"attempt": a, "decision": a, "opp": a, "t_ns": stages["t_signed"], "kind": "live",
                         "trigger": {"txn": S[tn], "slot": slot, "kind": "commit", "t_first_shred": tf},
                         "route": {"buy_pool": PA, "buy_venue": "PumpSwap", "buy_source": "seed", "sell_pool": PB, "sell_venue": "Dlmm",
                                   "sell_source": "seed", "mint": MINT, "mint_prog": solana.TOKEN, "hub": solana.WSOL},
                         "size_lamports": size, "expected": {"mid": 10 ** 9, "back": size + gross, "gross": gross, "fee": 5000,
                                                             "tip": int(0.6 * (gross - 5000)), "net": gross - 5000 - int(0.6 * (gross - 5000))},
                         "band": band, "sv": decisions[-1]["sv"], "route_age_ms": decisions[-1]["route_age_ms"],
                         "parts_skew_slots": {"buy": 0, "sell": 0}, "min_profit_onchain": minp, "margin": 1,
                         "tip": {"lamports": int(0.6 * (gross - 5000)), "account": TIP, "sender": "jito", "share": float(arm),
                                 "band": band, "arm": arm, "policy": "share"},
                         "tx": {"sig": S[on], "bytes": 1000 + 40 * a, "locks": 30, "alts": [], "alt_fallback": "none",
                                "cu_limit": 200_000, "cu_src": "PumpSwap|Dlmm|1-2|false", "cu_price_micro": 0,
                                "loaded_data_limit": None, "creates_ata": False, "closes_ata": False, "guard_max_drop": 0,
                                "program": {"id": ROUTE, "kind": "arbx-exec", "layout": "v3"}},
                         "blockhash": {"hash": pk(f"bh{slot - 2}"), "slot": slot - 2, "height": slot - 102, "age_slots": 2 + 30 * (a == 3),
                                       "commitment": "confirmed", "src": "slotidx"},
                         "leader": {"target_slot": slot, "identity": lid, "kind": lkind, "kind_src": "bundle_result", "region": "fra" if lkind == "jito" else "ams",
                                    "rtt_ms": 3.0 + a, "rtt_src": "quic_handshake", "rtt_age_s": 10, "client": "jito-agave", "be_rtt_ms": 1.2,
                                    "next": {"slot": slot + 1, "identity": lid, "kind": lkind}},
                         "crowding": {"signers_6h": 12, "bucket": 0, "src": "map"},
                         "inflight": {"key": f"{PA}|{PB}", "prev_attempt": None, "prev_sv": None, "why_allowed": "first"},
                         "queue": {"rank": 0, "ev": gross * 0.1, "wait_us": 500 + 100 * a, "lambda": 0.4},
                         "experiments": {"x4_share": arm}, "stages": stages,
                         "copies": [{"path": "jito-bundle", "sig": S[on], "bytes": 1000 + 40 * a, "tip": int(0.6 * (gross - 5000)), "min_profit": minp}],
                         "route_in": route_in(tn)})
        bid = f"bundle-{a:04d}"
        copies.append({"attempt": a, "path": "jito-bundle", "sig": S[on], "tip_account": TIP, "tip_lamports": int(0.6 * (gross - 5000)),
                       "t_sent": t_sent or 0, "t_ack": (t_sent + 800_000) if t_sent else 0, "ms": 0.8 if t_sent else None,
                       "ok": bool(t_sent), "status": None, "reply": bid if t_sent else "not sent", "bundle": bid if t_sent else None,
                       "blockhash_slot": slot - 2, "queue_wait_us": 500 + 100 * a})
    # verdicts
    vb = [(0, "accepted", 1000, None, None), (0, "processed", 1000, 40, None), (1, "would-fail", None, None, "0x4e580002"),
          (2, "accepted", 1007, None, None), (3, "lost-auction", None, None, None)]
    for i, (a, oc, slot, index, code) in enumerate(vb):
        t_sent = copies[a]["t_sent"]
        bundles.append({"t_ns": t_sent + (i + 1) * 3_000_000, "bundle": f"bundle-{a:04d}", "outcome": oc, "slot": slot, "index": index,
                        "bid": 700_000 if oc == "lost-auction" else None, "detail": None, "code": code, "sig": S[att_spec[a][2]],
                        "seq": sum(1 for x in vb[:i] if x[0] == a), "validator": L1 if a == 0 else (L2 if a == 2 else None),
                        "attempt": a, "stream_epoch": 0})
    led0 = {"trade_gross": 50_000, "tip": 30_000, "fee": 5000, "rent_nonrecoverable": 0, "rent_locked": 0, "rent_reclaimed": 0,
            "trade_net": 15_000, "equity_delta": 15_000, "liquid_delta": 15_000}
    led2 = {"trade_gross": 0, "tip": 0, "fee": 5000, "rent_nonrecoverable": 0, "rent_locked": 0, "rent_reclaimed": 0,
            "trade_net": -5000, "equity_delta": -5000, "liquid_delta": -5000}

    def outcome(a, final, **kw):
        base = {"attempt": a, "opp": a, "t_ns": t_slot(1013, 100 + a), "sig": S[att_spec[a][2]], "final": final, "final_t_ns": t_slot(1013, 100 + a),
                "final_src": "wallet" if final.startswith("landed") else "expiry", "amend": False,
                "verdicts": [{k: b.get(k) for k in ("t_ns", "outcome", "slot", "validator", "index", "bid", "code", "detail")} for b in bundles if b["attempt"] == a],
                "first_verdict_ms": None, "accepted": None, "processed": None, "landed": None, "slots_after_trigger": None,
                "poh": {"trigger": None, "ours": None, "ours_ms_after_trigger": None}, "ms_after_trigger_src": None, "seen": None,
                "send_to_seen_ms": None, "ok": None, "err": None, "code": None, "meaning": None, "fee_lamports": None, "cu_consumed": None,
                "prog_events": None, "delivered": None, "predicted": None, "round_trip_on_chain": None, "round_trip_predicted": None,
                "ledger": None, "closer": None, "statuses_checks": []}
        base.update(kw)
        return base

    outcomes.append(outcome(0, "landed_ok", landed={"slot": 1000, "idx": 40, "t_wallet_ns": t_slot(1001, 200), "leader": L1, "leader_kind": "jito"},
                            ok=True, fee_lamports=5000, cu_consumed=120_000, ledger=led0, round_trip_on_chain=50_000, round_trip_predicted=50_000,
                            delivered=[10 ** 9, 100_050_000], predicted=[10 ** 9, 100_050_000], slots_after_trigger=0,
                            poh={"trigger": {"slot": 1000, "ms": 50.0, "feed": 0}, "ours": {"slot": 1000, "ms": 61.5, "feed": 0}, "ours_ms_after_trigger": 11.5},
                            ms_after_trigger_src="poh", seen={"first_ns": t_slot(1000, 60), "first_feed": "feedB", "by": {"feedB": t_slot(1000, 60)}},
                            send_to_seen_ms=round((t_slot(1000, 60) - copies[0]["t_sent"]) / 1e6, 3), first_verdict_ms=3.0,
                            accepted={"t_ns": bundles[0]["t_ns"], "slot": 1000, "validator": L1}, processed={"slot": 1000, "index": 40, "validator": L1}))
    outcomes.append(outcome(1, "not_landed_expired", first_verdict_ms=3.0))
    outcomes.append(outcome(2, "landed_fail", landed={"slot": 1007, "idx": 12, "t_wallet_ns": t_slot(1008, 200), "leader": L2, "leader_kind": "bam"},
                            ok=False, err="ix2:custom:0x4e580002", code="0x4e580002", meaning="profit check", fee_lamports=5000, ledger=led2,
                            accepted={"t_ns": bundles[3]["t_ns"], "slot": 1007, "validator": L2}))
    outcomes.append(outcome(3, "unsettled"))
    outcomes.append(outcome(4, "not_landed_refused", final_src="jito"))
    outcomes.append({**outcomes[3], "final": "not_landed_expired", "amend": True, "t_ns": t_slot(1013, 300)})
    # two rejected decisions and a follow-up flag line
    decisions.append({**decisions[0], "decision": 5, "verdict": "reject", "reason": "inflight_same_state", "attempt": None, "best": 0})
    decisions.append({**decisions[0], "decision": 6, "verdict": "reject", "reason": "below_min_profit", "attempt": None, "best": None,
                      "routes": [dict(decisions[0]["routes"][1])]})
    decisions.append({"decision": 1, "torn_suspect": True})
    write_zjsonl(d, "decisions", "1.0", decisions)
    write_zjsonl(d, "attempts", "2.0", attempts)
    write_zjsonl(d, "copies", "1.0", copies)
    write_zjsonl(d, "bundles", "2.0", bundles)
    write_zjsonl(d, "outcomes", "2.0", outcomes)
    ledger = []
    for (name, a, row) in (("O0", 0, led0), ("O2", 2, led2)):
        slot, idx = TXS[name][0], TXS[name][1]
        ok = name == "O0"
        cats = [{"cat": "trade_gross", "lamports": 50_000}, {"cat": "tip", "lamports": -30_000}, {"cat": "fee_win", "lamports": -5000}] if ok \
            else [{"cat": "fee_fail", "lamports": -5000}]
        ledger.append({"sig": S[name], "slot": slot, "idx": idx, "t_ns": t_slot(slot, 300), "attempt": a, "kind": "route", "ok": ok,
                       "wallet_sol": -35_000 if ok else -5000, "wsol": 50_000 if ok else 0, "tokens": {}, "fee": 5000,
                       "tip": 30_000 if ok else 0, "rent_locked": 0, "rent_reclaimed": 0, "rent_nonrecoverable": 0,
                       "liquid_delta": row["liquid_delta"], "equity_delta": row["equity_delta"], "trade_gross": row["trade_gross"],
                       "trade_net": row["trade_net"], "categories": cats, "stranded": [],
                       "check": {"delivered_round_trip": 50_000, "diff": 0} if ok else None})
    write_zjsonl(d, "ledger", "1.0", ledger)
    snaps = [{"t_ns": t_slot(999), "slot": 999, "slot_mismatch": False, "sol": 10_000_000_000, "wsol": 1_000_000_000, "tokens": [],
              "nonce_accounts": [], "alts": [], "other_owned": [], "rent_recoverable": 2_039_280, "rent_nonrecoverable": 0, "token_value": 0,
              "equity_liquid": 11_000_000_000, "equity_total": 11_002_039_280, "mids_src": {}, "rpc": {"provider": "synth", "calls": 3, "ms": 40, "attempts": 1}},
             {"t_ns": t_slot(1012), "slot": 1012, "slot_mismatch": False, "sol": 9_999_960_000, "wsol": 1_000_050_000, "tokens": [],
              "nonce_accounts": [], "alts": [], "other_owned": [], "rent_recoverable": 2_039_280, "rent_nonrecoverable": 0, "token_value": 0,
              "equity_liquid": 11_000_010_000, "equity_total": 11_002_049_280, "mids_src": {}, "rpc": {"provider": "synth", "calls": 3, "ms": 40, "attempts": 1}}]
    write_plain(d, "snapshots.jsonl", "snapshots", "1.0", snaps)
    write_plain(d, "recon.jsonl", "recon", "1.0", [{"t_ns": t_slot(1012, 10), "from": {"t_ns": t_slot(999), "slot": 999}, "to": {"t_ns": t_slot(1012), "slot": 1012},
                                                    "delta_equity": 10_000, "sum_entries": 10_000, "inventory_reval": 0, "residual": 0,
                                                    "liquid": {"delta": 10_000, "sum_entries": 10_000, "residual": 0}, "token_amounts": [],
                                                    "tolerance": 10_000, "ok": True, "by_category": {"trade_gross": 50_000, "tip": -30_000, "fee_win": -5000, "fee_fail": -5000},
                                                    "unexplained": [], "action": None}])
    # predictions, caps, experiments
    preds = [{"sig": S["T0"], "venue": "PumpSwap", "pool": PA, "t_ns": t_slot(1000, 25), "slot": 1000, "hint": {"exact": True, "err": 0},
              "pre_state": {"known": True, "versions": []}, "input_src": "executed", "exact": True, "dlmm_bins": None, "window_exact_pct": 100.0, "quarantine_action": "log"},
             {"sig": S["T1"], "venue": "Dlmm", "pool": PB, "t_ns": t_slot(1003, 25), "slot": 1003, "hint": {"exact": False, "err": 1},
              "pre_state": {"known": True, "versions": []}, "input_src": "executed", "exact": True, "dlmm_bins": {"checked": 2, "exact": 2}, "window_exact_pct": 98.5, "quarantine_action": "log"},
             {"sig": S["T3"], "venue": "Dlmm", "pool": PB, "t_ns": t_slot(1008, 25), "slot": 1008, "hint": {"exact": False, "err": 3},
              "pre_state": {"known": False, "versions": []}, "input_src": "decoded", "exact": None, "dlmm_bins": None, "window_exact_pct": 98.5, "quarantine_action": "log"},
             # WP-16: a swap arbx-sizing refuses (known pre-state, `refused`), and an exact-out swap solved through exact-in quotes
             {"sig": S["T3"], "venue": "PumpSwap", "pool": PA, "t_ns": t_slot(1009, 25), "slot": 1009, "hint": {"exact": None, "err": None},
              "pre_state": {"known": True, "versions": []}, "input_src": "decoded", "exact": None, "refused": "sz_transfer_fee", "quarantine_action": "log"},
             {"sig": S["T3"], "venue": "PumpSwap", "pool": PA, "t_ns": t_slot(1010, 25), "slot": 1010, "hint": {"exact": None, "err": None},
              "pre_state": {"known": True, "versions": []}, "input_src": "decoded", "exact": False, "exact_out": True, "exact_out_model": "solved",
              "window_exact_pct": 50.0, "quarantine_action": "log"}]
    write_zjsonl(d, "predictions", "2.0", preds)
    caps = [{"id": i, "kind": "state", "slot": 1000 + s, "buy": PA, "sell": PB, "buy_venue": "PumpSwap", "sell_venue": "Dlmm", "mint": MINT,
             "best_size": 10 ** 8, "best_net": 1000 * (i + 1), "at_trade_size": [10 ** 8, 1000 * (i + 1)],
             "caps": [[0.165, 10 ** 8, 1000 * (i + 1)], [4.2, 10 ** 8, 1200 * (i + 1)]], "decision": i} for i, s in enumerate([0, 3, 12])]
    write_zjsonl(d, "caps", "1.0", caps)
    write_plain(d, "experiments.jsonl", "experiments", "1.0", [{"t_ns": T0_NS, "experiment": "x4_share", "event": "config", "arms": ["0.6", "0.4"],
                                                                "control": "0.6", "weights": [0.5, 0.5], "seed": 7, "scope": "attempt", "block": None}])
    # slow streams
    events = [{"t_ns": T0_NS + 500_000_000, "kind": "warmup_ready", "subsystem": "engine", "feed": None, "detail": {}},
              {"t_ns": t_slot(1004), "kind": "gate_change", "subsystem": "send", "feed": None, "detail": {"from": "live", "to": "shadow", "reason": "control"}},
              {"t_ns": t_slot(1005), "kind": "gate_change", "subsystem": "send", "feed": None, "detail": {"from": "shadow", "to": "live", "reason": "control"}},
              {"t_ns": t_slot(1009), "kind": "jito_stream_down", "subsystem": "jito", "feed": None, "detail": {}},
              {"t_ns": t_slot(1009, 100), "kind": "jito_stream_up", "subsystem": "jito", "feed": None, "detail": {}}]
    write_plain(d, "events.jsonl", "events", "1.0", events)
    status = []
    tot = {"attempt": 0, "landed_ok": 0, "landed_fail": 0, "trigger": 0, "evaluation": 0}
    deltas = [{"attempt": 2, "landed_ok": 1, "landed_fail": 0, "trigger": 2, "evaluation": 3},
              {"attempt": 2, "landed_ok": 0, "landed_fail": 1, "trigger": 2, "evaluation": 3},
              {"attempt": 1, "landed_ok": 0, "landed_fail": 0, "trigger": 1, "evaluation": 1}]
    fail_tot = 0
    for i, dl in enumerate(deltas):
        for k, v in dl.items():
            tot[k] += v
        fd = 5000 if i == 1 else 0
        fail_tot += fd
        status.append({"seq": i, "t_ns": T0_NS + (i + 1) * 2_000_000_000, "interval_ns": 2_000_000_000, "run_s": 2.0 * (i + 1),
                       "slot": {"processed": 1004 + 4 * i, "confirmed": 1003 + 4 * i, "finalized": 970 + 4 * i}, "tip_lag_slots_now": 1,
                       "send_gate": {"mode": "live", "reason": None, "since_ns": T0_NS},
                       "counts_total": dict(tot), "counts_delta": dict(dl),
                       "exec": {"attempts_total": tot["attempt"], "attempts_delta": dl["attempt"], "in_flight_now": 1, "landed_total": tot["landed_ok"] + tot["landed_fail"]},
                       "money": {"failed_fees_total_lamports": fail_tot, "failed_fees_delta_lamports": fd, "trade_net_total": 15_000 - fail_tot,
                                 "tips_total": 30_000, "fees_win_total": 5000, "fees_fail_total": fail_tot, "fees_other_total": 0,
                                 "equity_total_now": 11_002_039_280 + 15_000 - fail_tot},
                       "lag_slo": {"window": "minute", "p50_ms": 16.0, "p90_ms": 19.0 + i, "ok": i != 2, "breaches_in_row": int(i == 2), "good_in_row": 0, "action": "log"},
                       "coverage": {"unseen_share_sample": 0.004, "watched_with_tx_pct": 100.0},
                       "chainfetch": {"need_rps_now": 20.0, "have_rps_now": 25.0},
                       "latency": {"engine→priced": {"window": "interval", "n": 3, "p50": 90, "p90": 120, "p99": 150}}})
    write_plain(d, "status.jsonl", "status", "2.0", status)
    fh = []
    for i in range(2):
        for f, name in ((0, "feedA"), (1, "feedB")):
            fh.append({"seq": i, "t_ns": T0_NS + (i + 1) * 2_000_000_000, "interval_ns": 2_000_000_000, "feed": f, "name": name, "kind": "shred",
                       "connected_now": not (f == 1 and i == 1), "reconnects_total": f * i, "errors_total": 0, "packets_delta": 1000 + f,
                       "txs_delta": 900, "forwarded_delta": 40, "first_arrivals_delta": 30 if f == 0 else 10,
                       "lead_ms": {"window": "interval", "n": 40, "p50": 0.1 * (f + 1), "p90": 0.5, "p99": 1.0}, "last_msg_age_ms_now": 1.0,
                       "slot_max_now": 1004 + 4 * i, "slot_lag_now": 0, "provider_lag_ms": None, "shreds": None, "udp_drops_delta": 0, "channel_drops_delta": 0})
    write_plain(d, "feedhealth.jsonl", "feedhealth", "1.0", fh)
    write_plain(d, "resources.jsonl", "resources", "1.0", [
        {"seq": i, "t_ns": T0_NS + (i + 1) * 2_000_000_000, "interval_ns": 2_000_000_000, "cpu_user_ms_delta": 900 + i,
         "cpu_sys_ms_delta": 100, "engine_cpu_ms_delta": 400, "rss_bytes_now": (300 + 10 * i) << 20, "threads_now": 24,
         "load_avg_1m_now": 1.5, "recorder_queues": {}, "recorder_bytes_delta": {},
         "disk": {"run_dir_bytes_now": 1 << 20, "fs_free_bytes_now": (100 - i) << 30}, "rpc": {}, "runtimes": {}} for i in range(2)])
    write_plain(d, "keepalive.jsonl", "keepalive", "1.0", [
        {"t_ns": T0_NS + i * 1_000_000_000, "path": "jito-bundle", "ms": None if i == 2 else 1.1 + 0.1 * i,
         "error": "timeout" if i == 2 else None} for i in range(4)])
    write_zjsonl(d, "txfetch", "1.0", [
        {"t_ns": t_slot(s, 950), "role": "slotidx", "method": "getBlock", "key": str(s), "reason": "slot_index",
         "queued_ns": t_slot(s, 900), "provider": "synth", "ok": s != 1013, "err": None if s != 1013 else "rate_limited",
         "latency_ms": 35.0 + s % 3, "bytes": 200_000} for s in range(1000, 1014)])
    write_zjsonl(d, "alts", "2.0", [
        {"t_ns": T0_NS + 1, "table": pk("alt-1"), "event": "fetch_start", "n_addrs": None, "attempt": 1, "next_retry_ms": None,
         "waiting_txs": 2, "err": None},
        {"t_ns": T0_NS + 2, "table": pk("alt-1"), "event": "fetch_ok", "n_addrs": 30, "attempt": 1, "next_retry_ms": None,
         "waiting_txs": 0, "err": None}])
    with open(os.path.join(d, "probe.json"), "w") as f:
        json.dump({"schema": "arbx.probe/1.0", "t_ns": T0_NS - 10 ** 12, "provider_host": "synth",
                   "subs": [{"sub": "accounts_full", "accepted": True, "error": None, "messages_30s": 900, "first_msg_ms": 40},
                            {"sub": "blocks_meta", "accepted": False, "error": "unsupported", "messages_30s": 0, "first_msg_ms": None}]},
                  f, sort_keys=True, indent=1)
    meta = {"schema": "arbx.meta/2.0",
            "run": {"campaign": "synth", "segment": RUN, "dir": "runs/synth/synth-p1", "started_ns": T0_NS, "host": "synth", "pid": 1, "uid": 1000,
                    "argv": ["arbx", "run"], "mode": "live", "forced_shadow": False, "live_flag": True},
            "build": {"version": "0.0", "git_commit": "0" * 40, "git_dirty": False, "binary_sha256": "1" * 64},
            "config": {"path": "config.toml", "file_sha256": "2" * 64, "normalized_sha256": "3" * 64, "matches_campaign": True},
            "programs": [{"role": "route", "id": ROUTE, "name": "arbx-exec", "elf_sha256": "4" * 64, "ok": True}],
            "wallet": {"pubkey": W, "keystore_path": "(redacted)", "held_mints_at_boot": []},
            "feeds": [{"id": 0, "name": "feedA", "kind": "shred", "enabled": True, "host": "a"}, {"id": 1, "name": "feedB", "kind": "grpc", "enabled": True, "host": "b"}],
            "clock": {"source": "CLOCK_REALTIME", "sync_offset_ms": 0.2, "sync_source": "chronyc"}}
    with open(os.path.join(d, "meta.json"), "w") as f:
        json.dump(meta, f, sort_keys=True, indent=1)
    with open(os.path.join(d, "stop.json"), "w") as f:
        json.dump({"schema": "arbx.stop/1.0", "ended_ns": T0_NS + 6_000_000_000, "reason": "deadline", "detail": "synthetic", "signal": None,
                   "control": None, "exit_code": 0, "in_flight_at_stop": 1, "drained": False, "drain_ms": 0, "unsettled": [3],
                   "final_status_seq": 2}, f, sort_keys=True, indent=1)
    with open(os.path.join(d, "pools.json"), "w") as f:
        json.dump([{"idx": 0, "venue": "PumpSwap", "pool": PA, "t0": MINT, "t1": solana.WSOL, "vault0": VA0, "vault1": VA1, "extra": [], "source": "seed"},
                   {"idx": 1, "venue": "Dlmm", "pool": PB, "t0": MINT, "t1": solana.WSOL, "vault0": VB0, "vault1": VB1, "extra": [BA], "source": "seed"}],
                  f, sort_keys=True, indent=1)
    names = sorted(n.split(".")[0] for n in os.listdir(d) if n not in ("meta.json", "stop.json", "pools.json", "manifest.json", "probe.json"))
    cls = {"ledger": "core", "wallet": "core", "attempts": "core", "copies": "core", "bundles": "core", "outcomes": "core",
           "decisions": "core", "commits": "core", "accounts": "replay", "journal": "replay"}
    with open(os.path.join(d, "manifest.json"), "w") as f:
        json.dump({"schema": "arbx.manifest/1.0", "t_ns": T0_NS + 6_000_000_000, "final": True,
                   "streams": [{"name": n, "schema": None, "class": cls.get(n, "chain"), "files": [], "records_total": 10, "dropped_total": 0,
                                "queue_cap": 262144, "queue_hwm": 3} for n in names],
                   "disk": {"budget_bytes": 40 << 30, "used_bytes": 1 << 20, "fs_free_bytes": 100 << 30, "actions": []}}, f, sort_keys=True, indent=1)
    return d


def generate_campaign(root: str) -> str:
    """A campaign of two segments (campaign.json lists them). Segment p1's attempt 3 ends unsettled -> expired; its
    signature lands in p2's wallet stream: a late landing the campaign report must join (§6.2 rule 14)."""
    os.makedirs(root, exist_ok=True)
    generate(os.path.join(root, "synth-p1"))
    p2 = generate(os.path.join(root, "synth-p2"))
    late = wallet_row("O2", 3)
    late.update({"sig": S["O3"], "slot": 1020, "idx": 7, "attempt": None, "ours": None})
    write_z(p2, "wallet.001.jsonl.zst", jl([header("wallet", "1.0", 1), late]))
    with open(os.path.join(root, "campaign.json"), "w") as f:
        json.dump({"schema": "arbx.campaign/1.0", "name": "synth", "started_ns": T0_NS, "ended_ns": T0_NS + 20 * 10 ** 9,
                   "operator": "test", "binary": {"path": "arbx-00000000", "sha256": "1" * 64},
                   "config": {"path": "config.frozen.toml", "sha256": "2" * 64, "normalized_sha256": "3" * 64},
                   "budget": {"equity_drop_day_sol": 0.5, "failed_fee_budget_lamports": 0},
                   "segments": [{"name": "synth-p1", "started_ns": T0_NS, "ended_ns": T0_NS + 6 * 10 ** 9, "exit_code": 0,
                                 "stop_reason": "deadline", "class": "natural"},
                                {"name": "synth-p2", "started_ns": T0_NS + 7 * 10 ** 9, "ended_ns": T0_NS + 13 * 10 ** 9,
                                 "exit_code": 0, "stop_reason": "deadline", "class": "natural"}],
                   "crash_count_15min": 0}, f, sort_keys=True, indent=1)
    return root


TABLE = {  # the route's net (lamports) after each transaction, per attempt: the R4 test's "arbx quote"
    (1, S["S1"]): 0, (1, S["W2"]): 0,
    (2, S["W2"]): 900_000, (2, S["T3"]): 850_000, (2, S["Y3"]): 800_000,
    (3, S["Y3"]): 600_000,
    (4, S["Y3"]): 600_000,
}

if __name__ == "__main__":
    print(generate(sys.argv[1] if len(sys.argv) > 1 else "synth-p1"))
