"""Block-ordered route context per attempt (MEASUREMENT.md §4.41; PLAN F10).

Derived offline from `accounts.bin` (who wrote which route account, by `txn`), `slotidx.jsonl` (block positions of
tracked signatures, one line per confirmed slot) and `exec.jsonl` (results, signers and failed touches), plus our own
signatures and `leaders.jsonl`. Deterministic: the same files give the same rows.

- Window: [trigger slot, max(landed slot, last verdict slot, trigger slot + 4) + 1].
- Slots shared by several attempts are built once (`slot_cache`), then filtered per attempt.
- A slot without a slot-index line, or a route-writing transaction without an `exec` record with `idx`, is a gap:
  the row is `complete: false`. `fill_gaps` fetches the full block of such a slot through `chain.py`.
- Positions (FT-000 S1-2): a slot's transactions are ordered by ONE kind of position. In FT-000 the slot index's
  provider (Shyft) left the vote transactions out of getBlock's list, so its positions are ranks among the non-votes
  (`pos_kind` `nonvote_rank` in slotidx.jsonl 1.1), while exec.jsonl's `idx` is the block index (the stream's
  `TransactionInfo.index`, getTransaction's `transactionIndex`). Both keep the block order, but compared with each other
  they misorder (73% of FT-000's comparisons disagreed). Per slot: every transaction's exec block index when all have
  one (`pos_kind` `block_index`); else every transaction's slot-index position (the line's `pos_kind`; a line written
  before 1.1 is `unverified`); else the kind most of them have, the others without a position (`complete: false`, the
  slot's `pos_kind` `mixed`). An `idx` merged from an `idx_update` of a line that is not `block_index` (written before
  the fix) is not a block index.
"""
from __future__ import annotations

from . import solana, streams


def route_accounts(seg, a: dict) -> list:
    """The accounts the route reads: `route_in.accounts` (v2), else the two pools' registry entries (pools.json)."""
    ri = a.get("route_in") or {}
    accts = [x.get("acct") for x in ri.get("accounts") or [] if x.get("acct")]
    if accts:
        return sorted(set(accts))
    rt = a.get("route") or {}
    pools = {p.get("pool"): p for p in (seg.pools or []) if isinstance(p, dict)}
    out = set()
    for k in ("buy_pool", "sell_pool"):
        pk = rt.get(k)
        if not pk:
            continue
        out.add(pk)
        p = pools.get(pk) or {}
        for f in ("vault0", "vault1"):
            if p.get(f):
                out.add(p[f])
        for x in p.get("extra") or []:
            out.add(x)
    return sorted(out)


def window(seg, a: dict) -> tuple[int, int] | None:
    t = (a.get("trigger") or {}).get("slot")
    if t is None:
        return None
    o = seg.outcomes.get(a["attempt"]) or {}
    cands = [t + 4]
    if (o.get("landed") or {}).get("slot") is not None:
        cands.append(o["landed"]["slot"])
    for v in o.get("verdicts") or []:
        if v.get("slot") is not None:
            cands.append(v["slot"])
    for b in seg.verdicts_by_attempt.get(a["attempt"], []):
        if b.get("slot") is not None:
            cands.append(b["slot"])
    return t, max(cands) + 1


def our_sigs(seg, a: dict) -> set:
    s = {c.get("sig") for c in a.get("copies") or [] if c.get("sig")}
    if (a.get("tx") or {}).get("sig"):
        s.add(a["tx"]["sig"])
    o = seg.outcomes.get(a["attempt"]) or {}
    if o.get("sig"):
        s.add(o["sig"])
    return s


VOTE_PROGRAM = "Vote111111111111111111111111111111111111111"


def slot_pos_kind(si: dict | None) -> str | None:
    """What a slot-index line's positions are: `block_index`, `nonvote_rank` or `unverified` (a line written before
    slotidx 1.1 does not say: `unverified`); None without an ok line."""
    if not si or si.get("status") != "ok":
        return None
    return si.get("pos_kind") or "unverified"


def exec_block_index(e: dict, si_kind: str | None):
    """An exec / wallet record's block index: its `idx`, unless that came from a slot-index line whose positions are not
    block indexes (an `idx_update` merged by `streams.iter_exec`, `idx_src` slotidx)."""
    idx = e.get("idx")
    if idx is None or (e.get("idx_src") == "slotidx" and si_kind != "block_index"):
        return None
    return idx


def order_slot(txs: dict, si_pos: dict, si_kind: str | None) -> str | None:
    """Give every transaction of one slot (`txs[sig]` with `_bi`, its exec block index) one kind of position, in place:
    `idx` and the slot's `pos_kind` (module doc)."""
    if not txs:
        return si_kind
    bi = {s: t.get("_bi") for s, t in txs.items()}
    sp = {s: si_pos.get(s) for s in txs}
    if all(v is not None for v in bi.values()):
        for s, t in txs.items():
            t["idx"] = bi[s]
        return "block_index"
    if si_kind == "block_index":
        # both are block indexes
        for s, t in txs.items():
            t["idx"] = bi[s] if bi[s] is not None else sp[s]
        return "block_index"
    if si_kind is not None and all(v is not None for v in sp.values()):
        for s, t in txs.items():
            t["idx"] = sp[s]
        return si_kind
    n_bi = sum(v is not None for v in bi.values())
    n_sp = sum(v is not None for v in sp.values())
    use = bi if n_bi >= n_sp else sp
    for s, t in txs.items():
        t["idx"] = use[s]
    return "mixed"


def build(seg, chain=None, fill_gaps: bool = False) -> dict:
    """{"rows": [per attempt], "slots_processed": n, "slot_refs": n, "gaps_filled": n, "gap_slots": [...]}"""
    att = [a for a in seg.attempts if a.get("attempt") is not None]
    plan = {}
    union_accts: set = set()
    union_slots: set = set()
    ours_all: dict = {}
    for a in att:
        w = window(seg, a)
        if w is None:
            continue
        ra = route_accounts(seg, a)
        plan[a["attempt"]] = (w, ra)
        union_accts.update(ra)
        union_slots.update(range(w[0], w[1] + 1))
        for s in our_sigs(seg, a):
            ours_all[s] = a["attempt"]
    slot_refs = sum(w[1] - w[0] + 1 for w, _ in plan.values())

    # writers of route accounts, per slot: {slot: {txn: {acct: (aseq, wv)}}}
    writes: dict = {}
    wv_index: dict = {}  # (acct, write_version) -> aseq, for the route accounts (decision versions)
    if seg.has("accounts"):
        for r in streams.iter_accounts(seg.stream_files("accounts"), keep_data=False):
            if r.acct not in union_accts:
                continue
            if r.wv:
                wv_index[(r.acct, r.wv)] = r.aseq
            if r.txn and r.slot in union_slots:
                writes.setdefault(r.slot, {}).setdefault(r.txn, {})[r.acct] = (r.aseq, r.wv)
    # exec records in window slots that matter (writers, failed touches, ours)
    want_sigs = {t for s in writes.values() for t in s} | set(ours_all)
    execs: dict = {}
    if seg.has("exec"):
        for e in seg.iter_exec():
            if e.get("slot") not in union_slots:
                continue
            sig = e.get("sig")
            keys = e.get("keys") or []
            if sig in want_sigs or (not e.get("ok") and union_accts.intersection(keys)):
                execs[sig] = e
    for r in seg.wallet_rows:
        if r.get("sig") in ours_all and r.get("slot") in union_slots:
            execs.setdefault(r["sig"], r)

    gaps_filled = 0
    gap_slots = []
    slot_cache: dict = {}
    for slot in sorted(union_slots):
        si = seg.slotidx.get(slot)
        pos = {sig: idx for sig, idx in (si or {}).get("tracked") or []}
        si_kind = slot_pos_kind(si)
        txs = {}
        for sig, accts in writes.get(slot, {}).items():
            e = execs.get(sig) or {}
            txs[sig] = {"sig": sig, "idx": None, "_bi": exec_block_index(e, si_kind), "signer": e.get("signer"), "ok": e.get("ok", True),
                        "wrote": sorted(accts), "versions": {k: v[0] for k, v in accts.items()},
                        "has_exec": bool(e), "jito_tipped": e.get("jito_tipped"), "tip": e.get("tip_total"),
                        "bundle_pos": (e.get("bundle") or {}).get("pos"), "bundle_id": (e.get("bundle") or {}).get("id"), "keys": e.get("keys") or [],
                        "pools": e.get("pools") or [], "venues": e.get("venues") or [], "arb_like": (e.get("arb_like") or {}).get("is")}
        for sig, e in execs.items():
            if e.get("slot") != slot or sig in txs:
                continue
            txs[sig] = {"sig": sig, "idx": None, "_bi": exec_block_index(e, si_kind), "signer": e.get("signer"), "ok": e.get("ok"),
                        "wrote": [], "versions": {}, "has_exec": True, "jito_tipped": e.get("jito_tipped"),
                        "tip": e.get("tip_total"), "bundle_pos": (e.get("bundle") or {}).get("pos"), "bundle_id": (e.get("bundle") or {}).get("id"),
                        "keys": e.get("keys") or [], "pools": e.get("pools") or [], "venues": e.get("venues") or [],
                        "arb_like": (e.get("arb_like") or {}).get("is")}
        for sig, idx in pos.items():  # ours, landed but without an exec/wallet record yet
            if sig in ours_all and sig not in txs:
                txs[sig] = {"sig": sig, "idx": None, "_bi": None, "signer": seg.wallet, "ok": None, "wrote": [], "versions": {},
                            "has_exec": False, "keys": [], "pools": [], "venues": [], "arb_like": None}
        pos_kind = order_slot(txs, pos, si_kind)
        for t in txs.values():
            t.pop("_bi", None)
        complete = si is not None and si.get("status") in ("ok", "skipped") and pos_kind != "mixed" and all(
            t["has_exec"] and t["idx"] is not None for t in txs.values() if t["wrote"])
        src = "recorded"
        if not complete and fill_gaps and chain is not None:
            filled = _fill(chain, slot, txs, union_accts, ours_all)
            if filled:
                gaps_filled += 1
                src = "rpc-block"
                pos_kind = filled
                complete = all(t["idx"] is not None and t["ok"] is not None for t in txs.values())
        if not complete:
            gap_slots.append(slot)
        ld = seg.leaders.get(slot) or {}
        slot_cache[slot] = {"slot": slot, "leader": ld.get("leader"), "kind": ld.get("kind"),
                            "tx_count": (si or {}).get("tx_count"), "status": (si or {}).get("status"),
                            "complete": complete, "src": src, "pos_kind": pos_kind, "txs": txs}

    rows = []
    for a in att:
        if a["attempt"] not in plan:
            continue
        (lo, hi), ra = plan[a["attempt"]]
        ras = set(ra)
        mine = our_sigs(seg, a)
        trig = (a.get("trigger") or {}).get("txn")
        out_slots = []
        trig_pos = ours_pos = None
        srcs = set()
        comp = True
        for slot in range(lo, hi + 1):
            sc = slot_cache[slot]
            srcs.add(sc["src"])
            comp = comp and sc["complete"]
            tl = []
            for t in sc["txs"].values():
                wrote = [x for x in t["wrote"] if x in ras]
                touched = bool(ras.intersection(t["keys"]))
                is_ours = t["sig"] in mine
                if not (wrote or (touched and not t["ok"]) or is_ours or t["sig"] == trig):
                    continue
                tl.append({"idx": t["idx"], "sig": t["sig"], "signer": t["signer"], "ok": t["ok"], "wrote": wrote,
                           "versions": {k: v for k, v in t["versions"].items() if k in ras}, "ours": is_ours,
                           "jito_tipped": t.get("jito_tipped"), "tip": t.get("tip"), "bundle_pos": t.get("bundle_pos"), "bundle_id": t.get("bundle_id"),
                           "pools": t.get("pools"), "venues": t.get("venues"), "arb_like": t.get("arb_like")})
                if t["sig"] == trig:
                    trig_pos = {"slot": slot, "idx": t["idx"]}
                if is_ours and t["idx"] is not None:
                    ours_pos = {"slot": slot, "idx": t["idx"]}
            tl.sort(key=lambda x: (x["idx"] is None, x["idx"] if x["idx"] is not None else 0, x["sig"]))
            out_slots.append({"slot": slot, "leader": sc["leader"], "kind": sc["kind"], "tx_count": sc["tx_count"],
                              "complete": sc["complete"], "pos_kind": sc["pos_kind"], "txs": tl})
        if trig_pos is None and trig:
            # the trigger may have written nothing on our route (a hint); its position can still be in the slot index,
            # comparable with the slot's other positions only when they are of its kind
            for slot in range(lo, hi + 1):
                si = seg.slotidx.get(slot) or {}
                for sig, idx in si.get("tracked") or []:
                    if sig != trig:
                        continue
                    if not slot_cache[slot]["txs"] or slot_cache[slot]["pos_kind"] == slot_pos_kind(si):
                        trig_pos = {"slot": slot, "idx": idx}
        src = "recorded" if srcs == {"recorded"} else ("rpc-block" if srcs == {"rpc-block"} else "mixed")
        rows.append({"attempt": a["attempt"], "route_accounts": ra, "window": {"from_slot": lo, "to_slot": hi},
                     "slots": out_slots, "trigger": trig_pos, "ours": ours_pos, "closer": None, "src": src,
                     "complete": comp})
    return {"rows": rows, "slots_processed": len(slot_cache), "slot_refs": slot_refs, "gaps_filled": gaps_filled,
            "gap_slots": gap_slots, "wv_index": wv_index}


FILE_TX_FIELDS = ("idx", "sig", "signer", "ok", "wrote", "ours", "jito_tipped", "tip", "bundle_pos")
#: blockctx.jsonl slot fields (FT-000: `pos_kind`, what the slot's `idx` values are)
FILE_SLOT_FIELDS = ("slot", "leader", "kind", "tx_count", "complete", "pos_kind")

RUNG_NAMES = {0: "0 same bundle as opener", 1: "1 idx+1", 2: "2 idx+2..5", 3: "3 same slot, later", 4: "4 next slot",
              5: "5 two or more slots later"}


def rung(opener: tuple, pos: tuple, same_bundle: bool = False) -> int | None:
    """The latency/ordering ladder of rival-synthesis §5, from block positions (slot, idx) of the opener (the
    transaction that opened the gap) and of the taker."""
    if opener is None or pos is None or None in opener or None in pos:
        return None
    if same_bundle:
        return 0
    (os_, oi), (s, i) = opener, pos
    if s == os_:
        d = i - oi
        if d <= 0:
            return None
        return 1 if d == 1 else (2 if d <= 5 else 3)
    return 4 if s == os_ + 1 else (5 if s > os_ else None)


def positions(seg, rows=None) -> dict:
    """{sig: (slot, idx)} from the slot index (tracked signatures) and exec records (idx, idx_update merged). FT-000
    (S1-2): within a slot whose slot-index line is not `block_index`, the line's positions are the only ones used (an
    exec block index would not compare with them); an exec block index fills in where the slot has no line."""
    pos = {}
    kinds = {}
    for slot, r in seg.slotidx.items():
        kinds[slot] = slot_pos_kind(r)
        for sig, idx in r.get("tracked") or []:
            pos[sig] = (slot, idx)
    for e in rows if rows is not None else seg.iter_exec():
        slot = e.get("slot")
        k = kinds.get(slot)
        if e.get("idx") is None or e.get("sig") in pos or (k is not None and k != "block_index"):
            continue
        if exec_block_index(e, k) is None:
            continue
        pos[e["sig"]] = (slot, e["idx"])
    return pos


def pool_writers(seg, pos: dict) -> dict:
    """{pool pubkey: sorted [(slot, idx, txn)]}: every transaction that wrote an account of a registry pool (pool
    account, vaults, extras; a PumpSwap swap writes only the vaults), with its block position when known."""
    reg = {p.get("idx"): p.get("pool") for p in (seg.pools or []) if isinstance(p, dict)}
    out: dict = {}
    seen = set()
    if not seg.has("accounts"):
        return out
    for r in streams.iter_accounts(seg.stream_files("accounts"), keep_data=False):
        if not r.txn or r.pool_index is None:
            continue
        pool = reg.get(r.pool_index)
        if pool is None or (pool, r.txn) in seen:
            continue
        seen.add((pool, r.txn))
        p = pos.get(r.txn)
        out.setdefault(pool, []).append((r.slot, p[1] if p else None, r.txn))
    for v in out.values():
        v.sort(key=lambda x: (x[0], x[1] if x[1] is not None else -1, x[2]))
    return out


def opener_of(writers: dict, pools: list, pos: tuple, sig: str, max_slots_back: int = 2):
    """The last transaction before `pos` (block order) that wrote one of `pools`, within `max_slots_back` slots."""
    best = None
    for p in pools or []:
        for s, i, t in writers.get(p, []):
            if t == sig or i is None:
                continue
            if (s, i) < pos and s >= pos[0] - max_slots_back and (best is None or (s, i) > best[:2]):
                best = (s, i, t)
    return best


def file_rows(built: dict) -> list:
    """Rows as written to report/blockctx.jsonl (§4.41 fields only)."""
    out = []
    for r in built["rows"]:
        slots = [{**{k: s.get(k) for k in FILE_SLOT_FIELDS},
                  "txs": [{k: t.get(k) for k in FILE_TX_FIELDS} for t in s["txs"]]} for s in r["slots"]]
        c = r.get("closer")
        closer = None if not c else {k: c.get(k) for k in ("sig", "signer", "slot", "idx", "kind", "ms_after_trigger_poh")}
        out.append({"attempt": r["attempt"], "route_accounts": r["route_accounts"], "window": r["window"], "slots": slots,
                    "trigger": r["trigger"], "ours": r["ours"], "closer": closer, "src": r["src"], "complete": r["complete"]})
    return out


def _fill(chain, slot: int, txs: dict, accts: set, ours: dict):
    """Fill a gap slot from a full getBlock: positions, results and signers of route-touching transactions. Returns the
    positions' kind (`block_index`; `nonvote_rank` when the provider's list holds no vote transaction: it left them out,
    FT-000 S1-2), or False when there was no block."""
    try:
        blk = chain.get_block(slot, full=True)
    except Exception:
        return False
    if not blk:
        return False
    views = []
    for t in blk.get("transactions") or []:
        views.append(solana.TxView({"transaction": t.get("transaction"), "meta": t.get("meta"), "slot": slot, "version": t.get("version")}))
    kind = "block_index" if any(VOTE_PROGRAM in (v.keys or []) for v in views) or not views else "nonvote_rank"
    for t in txs.values():
        t["idx"] = None
    for idx, t in enumerate(blk.get("transactions") or []):
        v = views[idx]
        if v.sig in txs:
            txs[v.sig].update({"idx": idx, "ok": v.ok, "signer": v.signer, "has_exec": True, "keys": v.keys})
        elif accts.intersection(v.keys) or v.sig in ours:
            txs[v.sig] = {"sig": v.sig, "idx": idx, "signer": v.signer, "ok": v.ok, "wrote": [], "versions": {},
                          "has_exec": True, "keys": v.keys, "pools": [], "venues": [], "arb_like": None}
    return kind
