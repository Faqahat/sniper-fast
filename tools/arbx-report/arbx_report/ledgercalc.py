"""Money by signature from a wallet transaction, with MEASUREMENT.md §4.42's definitions.

The bot's `src/ledger.rs` (WP-07) writes `ledger.jsonl`; the toolkit recomputes the same fields from the wallet's
transactions so that it can (a) cross-check the bot's ledger and (b) give arb-lab's runs a ledger at all.

Rent comes from the transaction's own instructions when they are available (System CreateAccount names the new
account's owner program, Token CloseAccount names the destination), else from balances only (`rent_src`).
"""
from __future__ import annotations

from . import solana

#: owner programs whose accounts the wallet can close (recoverable rent, §4.42)
RECOVERABLE_OWNERS = {solana.TOKEN, solana.TOKEN_2022, solana.SYSTEM,
                      "AddressLookupTab1e1111111111111111111111111"}
#: owners whose accounts the wallet cannot close: PumpSwap's user volume accumulator (1,346,200 lamports)
NONRECOVERABLE_OWNERS = {solana.PUMPSWAP}

BORING_PROGRAMS = {solana.COMPUTE_BUDGET, solana.ATA, solana.SYSTEM, solana.TOKEN, solana.TOKEN_2022,
                   "AddressLookupTab1e1111111111111111111111111", "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr",
                   "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo"}

SUMMING = ["trade_gross", "tip", "fee_win", "fee_fail", "fee_other", "rent_nonrecoverable", "transfer_in",
           "transfer_out", "other"]


def _wallet_index(tx: solana.TxView, wallet: str) -> int | None:
    try:
        return tx.keys.index(wallet)
    except ValueError:
        return None


def compute(tx: solana.TxView, wallet: str, *, route: bool | None = None, attempt=None, tip_accounts: set | None = None,
            mids: dict | None = None) -> dict:
    """The §4.42 fields of one wallet transaction. `route` says whether it is one of our route transactions (matched
    to an attempt); when None it is guessed from the instructions. `mids`: {mint: lamports per raw unit} to value
    non-quote tokens; a token change without a mid makes `equity_delta` null (missing is not zero)."""
    wi = _wallet_index(tx, wallet)
    ok = tx.ok
    fee = tx.fee if wi == 0 else 0
    wallet_sol = tx.balance_delta(wi) if wi is not None else 0
    # token changes of wallet-owned accounts, by mint
    tok = tx.owner_token_delta(wallet)
    wsol = tok.pop(solana.WSOL, 0)
    pre_tok, post_tok = tx.token_amounts("pre"), tx.token_amounts("post")
    wallet_tok_accts = {tx.keys[i] for i, r in list(pre_tok.items()) + list(post_tok.items())
                        if r[1] == wallet and i < len(tx.keys)}

    all_ixs = tx.instructions()
    route_guess = any(ix.program in solana.VENUE_PROGRAMS for ix in all_ixs) or any(
        ix.depth == 1 and ix.program is not None and ix.program not in BORING_PROGRAMS for ix in all_ixs)
    ixs = all_ixs if ok else []  # a failed transaction's effects revert (only the fee is charged)
    have_ixs = bool(tx.ixs)
    created: list = []
    closed: list = []
    tips = 0
    transfers_out = 0
    transfers_in_known = 0
    kinds = set()
    for ix in all_ixs:
        s = ix.system()
        if s and s["type"] == "initialize_nonce":  # AdvanceNonce at index 0 is a durable-nonce tx, not a nonce op
            kinds.add("nonce")
    for ix in ixs:
        s = ix.system()
        if s:
            if s["type"] == "create" and s.get("from") == wallet:
                created.append({"acct": s["to"], "lamports": s["lamports"], "owner": s.get("owner")})
            elif s["type"] == "transfer" and s.get("from") == wallet and s.get("to") != wallet:
                to = s.get("to")
                if to in wallet_tok_accts:
                    kinds.add("wrap")
                elif tip_accounts is not None and to in tip_accounts:
                    tips += s["lamports"]
                elif any(c["acct"] == to for c in created):
                    pass  # pre-funding an account created here
                else:
                    transfers_out += s["lamports"]
            elif s["type"] == "transfer" and s.get("to") == wallet:
                transfers_in_known += s["lamports"]
            continue
        t = ix.token()
        if t:
            if t["type"] == "close" and t.get("destination") == wallet:
                closed.append(t["account"])
            continue
    is_route = route if route is not None else route_guess
    if is_route and tip_accounts is None:
        tips, transfers_out = tips + transfers_out, 0  # route txs pay no one else
    if not ok:
        tips = 0

    # rent: from instructions when available, else from balances (pre 0 -> post > 0 created, pre > 0 -> post 0 closed)
    rent_locked = rent_reclaimed = rent_nonrec = 0
    rent_src = "instructions" if have_ixs and ok else "balances"
    created_out, closed_out = [], []
    if ok:
        if have_ixs:
            created_accts = {}
            for c in created:
                own = c.get("owner")
                rec = own in RECOVERABLE_OWNERS or (own not in NONRECOVERABLE_OWNERS and not is_route)
                created_accts[c["acct"]] = c
                if rec:
                    rent_locked += c["lamports"]
                else:
                    rent_nonrec += c["lamports"]
                created_out.append({"acct": c["acct"], "lamports": c["lamports"], "owner": own, "recoverable": rec})
            for a in closed:
                i = tx.keys.index(a) if a in tx.keys else None
                if a in created_accts:
                    lam = created_accts[a]["lamports"]
                elif i is not None:
                    pre_l = int((tx.meta.get("preBalances") or [0])[i]) if i < len(tx.meta.get("preBalances") or []) else 0
                    amt = pre_tok.get(i, (None, None, 0, None))
                    lam = pre_l - (amt[2] if amt[0] == solana.WSOL else 0)
                else:
                    lam = 0
                rent_reclaimed += lam
                closed_out.append({"acct": a, "lamports": lam, "to": wallet})
        else:
            pre, post = tx.meta.get("preBalances") or [], tx.meta.get("postBalances") or []
            for i, k in enumerate(tx.keys):
                if i == wi or i >= len(pre) or i >= len(post):
                    continue
                if pre[i] == 0 and post[i] > 0 and k not in (tip_accounts or set()):
                    is_tok = i in post_tok and post_tok[i][1] == wallet
                    if is_tok:
                        amt = post_tok[i][2] if post_tok[i][0] == solana.WSOL else 0
                        rent_locked += post[i] - amt
                    elif is_route:
                        rent_nonrec += post[i]
                    else:
                        rent_locked += post[i]
                    created_out.append({"acct": k, "lamports": post[i], "owner": None, "recoverable": is_tok or not is_route})
                elif pre[i] > 0 and post[i] == 0 and i in pre_tok and pre_tok[i][1] == wallet:
                    amt = pre_tok[i][2] if pre_tok[i][0] == solana.WSOL else 0
                    rent_reclaimed += pre[i] - amt
                    closed_out.append({"acct": k, "lamports": pre[i] - amt, "to": wallet})

    # non-quote tokens at the recorded mid
    tokens = {}
    tok_value = 0
    tok_missing = False
    for mint, amt in sorted(tok.items()):
        mid = (mids or {}).get(mint)
        v = None if mid is None else int(round(amt * mid))
        if v is None:
            tok_missing = True
        else:
            tok_value += v
        tokens[mint] = {"amount": str(amt), "value_lamports": v, "mid_src": "given" if mid is not None else None}

    liquid = wallet_sol + wsol
    equity = None if tok_missing else liquid + tok_value + rent_locked - rent_reclaimed
    if is_route:
        kind = "route"
    elif "nonce" in kinds:
        kind = "nonce"
    elif closed_out and wsol < 0:
        kind = "unwrap"
    elif "wrap" in kinds:
        kind = "wrap"
    elif created_out and not closed_out:
        kind = "ata_create"
    elif closed_out:
        kind = "close"
    elif transfers_out:
        kind = "transfer_out"
    elif liquid > 0:
        kind = "transfer_in"
    else:
        kind = "other"

    trade_gross = 0
    cats: dict = {}
    if equity is not None:
        if not ok:
            cats["fee_fail"] = -fee
        elif is_route:
            trade_gross = equity + fee + tips + rent_nonrec
            cats.update({"trade_gross": trade_gross, "tip": -tips, "fee_win": -fee})
            if rent_nonrec:
                cats["rent_nonrecoverable"] = -rent_nonrec
        else:
            cats["fee_other"] = -fee
            if rent_nonrec:
                cats["rent_nonrecoverable"] = -rent_nonrec
            rest = equity - sum(cats.values())
            if rest:
                cats["transfer_in" if rest > 0 and kind == "transfer_in" else
                     "transfer_out" if rest < 0 and kind == "transfer_out" else "other"] = rest
    stranded = [{"mint": m, "amount": str(a)} for m, a in sorted(tok.items()) if is_route and a > 0]
    row = {
        "sig": tx.sig, "slot": tx.slot, "attempt": attempt, "kind": kind, "ok": ok,
        "wallet_sol": wallet_sol, "wsol": wsol, "tokens": tokens, "fee": fee, "tip": tips,
        "rent_locked": rent_locked, "rent_reclaimed": rent_reclaimed, "rent_nonrecoverable": rent_nonrec,
        "liquid_delta": liquid, "equity_delta": equity,
        "trade_gross": trade_gross if equity is not None else None,
        # trade_gross - fee - tip on route transactions (a failed route tx: -fee); 0 on the others, whose fees are
        # `fee_other` and are not trading
        "trade_net": (trade_gross - fee - tips) if (equity is not None and is_route) else (0 if equity is not None else None),
        "categories": [{"cat": c, "lamports": v} for c, v in cats.items() if v or c.startswith("fee")],
        "stranded": stranded, "created": created_out, "closed": closed_out, "rent_src": rent_src,
        "transfer_out_lamports": transfers_out, "src": "toolkit",
    }
    return row


def check_identities(row: dict) -> list:
    """The §4.42 identities a reader may rely on; returns the violated ones (empty = all hold)."""
    bad = []
    eq = row.get("equity_delta")
    if eq is None:
        return bad
    s = sum(c["lamports"] for c in row.get("categories") or [] if c["cat"] in SUMMING)
    if s != eq:
        bad.append(f"sum(categories)={s} != equity_delta={eq}")
    if row.get("ok") is False:
        if not (eq == row.get("liquid_delta") == -row.get("fee", 0)):
            bad.append("failed tx: equity_delta == liquid_delta == -fee does not hold")
    tv = sum((t.get("value_lamports") or 0) for t in (row.get("tokens") or {}).values())
    if eq - row.get("liquid_delta", 0) != tv + row.get("rent_locked", 0) - row.get("rent_reclaimed", 0):
        bad.append("equity_delta - liquid_delta != tokens + rent_locked - rent_reclaimed")
    return bad


def recon_check(r: dict, tolerance: int = 10_000) -> list:
    """The §4.44 recon line's own arithmetic: residual and ok."""
    bad = []
    try:
        res = r["delta_equity"] - r["sum_entries"] - r["inventory_reval"]
        if res != r["residual"]:
            bad.append(f"residual {r['residual']} != delta_equity - sum_entries - inventory_reval = {res}")
        liq = r.get("liquid") or {}
        ok = abs(res) <= tolerance and abs(liq.get("residual", 0)) <= tolerance and all(t.get("ok", True) for t in r.get("token_amounts") or [])
        if bool(r.get("ok")) != ok:
            bad.append(f"ok={r.get('ok')} but the tolerance rule gives {ok}")
    except (KeyError, TypeError) as e:
        bad.append(f"missing field {e}")
    return bad
