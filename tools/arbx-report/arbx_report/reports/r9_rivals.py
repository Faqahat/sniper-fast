"""R9 Rivals and the field (MEASUREMENT.md §6.4): arbitrage-like transactions on watched accounts; clean wins
(signer's SOL + WSOL gain > 0 and no other token left); per signer wins, profit, tips, senders, bundle membership.
Only transactions touching watched accounts are seen."""
from __future__ import annotations

from .. import blockctx, solana, streams
from . import section

CAVEAT = "only transactions touching watched accounts are seen"


def clean_gain(e: dict):
    tok = e.get("signer_tok") or {}
    other = [m for m, v in tok.items() if m != solana.WSOL and str(v) not in ("0", "")]
    if other or not e.get("ok"):
        return None
    g = (e.get("signer_sol") or 0) + int(tok.get(solana.WSOL, "0") or 0)
    return g if g > 0 else None


def run(seg, ctx: dict) -> dict:
    sec = section("R9", "Rivals and the field")
    d = sec["data"]
    if ctx.get("quick"):
        sec["complete"] = False
        sec["incomplete"].append("skipped (--quick)")
        return sec
    per: dict = {}
    ours = seg.wallet
    if seg.legacy:
        if not seg.has("rivals"):
            sec["complete"] = False
            sec["incomplete"].append("v1 rivals.jsonl missing (recorder off)")
            return sec
        meta: dict = {}
        for r in streams.iter_jsonl(seg.stream_files("rivals"), "rivals"):
            meta[r.get("sig")] = (r.get("signer"), [t[2] for t in r.get("tips") or [] if len(t) > 2], sum(t[1] for t in r.get("tips") or [] if len(t) > 1))
        n_exec = 0
        for e in seg.iter_exec():
            m = meta.get(e.get("sig"))
            if not m:
                continue
            n_exec += 1
            _acc(per, m[0], e, m[2], m[1], None)
        d["rivals_seen"] = len(meta)
        d["with_executed_result"] = n_exec
        sec["caveats"].append("v1: executed results exist only for PumpSwap transactions (one program filter)")
    else:
        n = 0
        wins = []
        all_pos_rows = []
        for e in seg.iter_exec():
            if e.get("idx") is not None:
                all_pos_rows.append({"sig": e.get("sig"), "slot": e.get("slot"), "idx": e.get("idx")})
            if not (e.get("arb_like") or {}).get("is"):
                continue
            n += 1
            _acc(per, e.get("signer"), e, e.get("tip_total") or 0, e.get("tip_senders") or [], e.get("bundle"))
            g = clean_gain(e)
            if g is not None and e.get("signer") != ours:
                wins.append((e.get("sig"), e.get("slot"), e.get("idx"), e.get("pools") or [], g, e.get("signer")))
        d["arb_like_txs"] = n
        # the ladder (rival-synthesis §5): each clean win against the last earlier writer of its pools (its opener)
        pos = blockctx.positions(seg, all_pos_rows)
        writers = blockctx.pool_writers(seg, pos)
        ladder: dict = {}
        for sig, slot, idx, pools, g, signer in wins:
            p = pos.get(sig) or ((slot, idx) if idx is not None else None)
            op = blockctx.opener_of(writers, pools, p, sig) if p else None
            rg = blockctx.rung(op[:2], p) if op else None
            k = blockctx.RUNG_NAMES.get(rg, "unknown")
            b = ladder.setdefault(k, {"wins": 0, "profit": 0})
            b["wins"] += 1
            b["profit"] += g
            if signer in per:
                per[signer].setdefault("rungs", {})
                per[signer]["rungs"][k] = per[signer]["rungs"].get(k, 0) + 1
        d["ladder_clean_wins"] = dict(sorted(ladder.items()))
        d["ladder_note"] = "rung 0 needs bundle membership, which v2 exec only has when known; such wins show as rung 1"
    rows = []
    for s, b in per.items():
        if s == ours:
            continue
        rows.append({"signer": s, **b, "senders": dict(sorted(b["senders"].items())), "rungs": dict(sorted((b.get("rungs") or {}).items()))})
    rows.sort(key=lambda r: (-r["clean_profit"], -r["n"], r["signer"] or ""))
    d["signers"] = len(rows)
    d["top_by_clean_profit"] = rows[:30]
    sec["caveats"].append(CAVEAT)
    return sec


def _acc(per, signer, e, tip, senders, bundle):
    b = per.setdefault(signer, {"n": 0, "ok": 0, "clean_wins": 0, "clean_profit": 0, "tips": 0, "senders": {},
                                "in_known_bundle": 0, "fees": 0})
    b["n"] += 1
    b["ok"] += bool(e.get("ok"))
    b["fees"] += e.get("fee") or 0
    g = clean_gain(e)
    if g is not None:
        b["clean_wins"] += 1
        b["clean_profit"] += g
    if e.get("ok"):
        b["tips"] += tip or 0
    for s in senders or []:
        if s:
            b["senders"][s] = b["senders"].get(s, 0) + 1
    if bundle and bundle.get("known"):
        b["in_known_bundle"] += 1
