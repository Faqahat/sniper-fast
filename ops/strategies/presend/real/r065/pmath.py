#!/usr/bin/env python3
"""REPLAY_065: pump.fun bonding-curve math in exact integers (checked on the chain tape by `check()`; MEASURED).
  buy  (net SOL n into the curve): tokens = t * n // (v + n)
  sell (q tokens in):              sol    = v * q // (t + q)       (gross; the fees come out of it)
  fees on an amount a: ceil(a * fee_bps / 1e4) + ceil(a * creator_fee_bps / 1e4)
  buy_exact_quote_in (a SOL budget B incl. fees): n = the largest n with n + fees(n) <= B
  buy exact tokens (legacy `buy`, a tokens, max SOL M): n = v * a // (t - a) + 1, cost n + fees(n) <= M"""


def cdiv(a, b): return -((-a) // b)


def fees(a, fb, cb): return cdiv(a * fb, 10000) + cdiv(a * cb, 10000)


def net_of_budget(B, fb, cb):
    """largest n with n + fees(n) <= B"""
    n = B * 10000 // (10000 + fb + cb)
    while n > 0 and n + fees(n, fb, cb) > B: n -= 1
    while n + 1 + fees(n + 1, fb, cb) <= B: n += 1
    return n


def buy_tok(v, t, n): return t * n // (v + n)


def sell_sol(v, t, q): return v * q // (t + q)


def cost_exact_tok(v, t, a): return v * a // (t - a) + 1 if a < t else None


def check(tape, limit=None):
    """MEASURED: the formulas against every recorded trade whose pre-state is known (previous trade of the mint in the tape)"""
    import collections
    c = collections.Counter(); bad = []
    for mint, T in tape.items():
        tr = T["trades"]
        for a, b in zip(tr, tr[1:]):
            if b["buy"]:
                v0, t0 = b["vsol"] - b["sol"], b["vtok"] + b["tok"]
            else:
                v0, t0 = b["vsol"] + b["sol"], b["vtok"] - b["tok"]
            if (v0, t0) != (a["vsol"], a["vtok"]): c["chain_break"] += 1; continue
            if b["buy"]:
                ok_tok = buy_tok(v0, t0, b["sol"]) == b["tok"]
                c["buy_tok_ok" if ok_tok else "buy_tok_bad"] += 1
                if not ok_tok and len(bad) < 5: bad.append(("buy", mint, b["sig"][:12], b["tok"], buy_tok(v0, t0, b["sol"])))
                # legacy exact-tokens buys: the cost formula
                ce = cost_exact_tok(v0, t0, b["tok"])
                c["buy_costexact_eq" if ce == b["sol"] else "buy_costexact_ne"] += 1
            else:
                ok = sell_sol(v0, t0, b["tok"]) == b["sol"]
                c["sell_ok" if ok else "sell_bad"] += 1
                if not ok and len(bad) < 10: bad.append(("sell", mint, b["sig"][:12], b["sol"], sell_sol(v0, t0, b["tok"])))
            ff = fees(b["sol"], b["fbps"], b["cbps"])
            c["fee_ok" if ff == b["fee"] + b["cfee"] else "fee_bad"] += 1
        if limit and sum(c.values()) > limit: break
    return c, bad


if __name__ == "__main__":
    import pickle
    TP = pickle.load(open("/home/moiz/sniper-data/replay065/tape.pkl", "rb"))
    c, bad = check(TP["tape"])
    print(dict(c)); print(bad)
