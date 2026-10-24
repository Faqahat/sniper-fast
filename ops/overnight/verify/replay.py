#!/usr/bin/env python3
"""Independent re-implementation of the S4 trade math (placement, guard, fill, replay, exit, PnL).

Inputs (raw):
  work/chain_events.json.gz      (built by extract.py from the collector's raw tx chunks)
  launches.jsonl                 (create slot / idx / sig / user / creator)
  shadow/scores_v{1,2,3}.jsonl   (engine arrival timeline: type=obs, outs)
Checked file (only read for comparison): report/s4_forward.json

Run: python3 -I replay.py            -> writes verify.json + prints the comparison
"""
import gzip
import json
import math
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
RUN = "/home/moiz/sniper-data/collect/run_20261022_1543"
SHADOW = "/home/moiz/sniper-data/collect/shadow"
RESULT = "/home/moiz/sniper/ops/overnight/report/s4_forward.json"

LS = (45, 60, 75)
SIZE = 500_000_000          # 0.5 SOL incl. pump fees
PEN = 0.985                 # 1.5% pessimistic fill penalty on our tokens
GUARD = 1.01                # fail if our spot > 1% above post-bundle spot
FAIL_COST = 0.005
SELL_TX = 0.0005
BUY_COST = 0.5 * 1.02       # 0.51 incl. 2% priority/tip overhead
HOLD_SLOTS = 5              # ceil(1000/212)
GRAD_V = 114_000_000_000
MATCH_SLOTS = 7             # chain trades in slots cs .. cs+6 ("first 6 slots after the create") are matchable


def load_chain():
    D = json.load(gzip.open(os.path.join(HERE, "work", "chain_events.json.gz"), "rt"))
    per = {}
    for m, v in D["per_mint"].items():
        seen = set()
        tr = []
        for t in v["trades"]:
            if t["err"] is not None:
                continue
            key = (t["sig"], t["k"])
            if key in seen:          # restart re-write duplicates
                continue
            seen.add(key)
            tr.append(t)
        tr.sort(key=lambda d: (d["s"], d["i"], d["k"]))
        cr = [c for c in v["creates"] if c["err"] is None]
        per[m] = {"trades": tr, "creates": cr}
    return per


def load_launches(mints):
    out = {}
    with open(os.path.join(RUN, "launches.jsonl")) as fh:
        for ln in fh:
            try:
                o = json.loads(ln)
            except Exception:
                continue
            if o.get("mint") in mints:
                out.setdefault(o["mint"], []).append(o)
    return out


def load_obs(mints):
    obs = {}
    for f in ("scores_v1.jsonl", "scores_v2.jsonl", "scores_v3.jsonl"):
        with open(os.path.join(SHADOW, f)) as fh:
            for ln in fh:
                try:
                    o = json.loads(ln)
                except Exception:
                    continue
                if o.get("type") == "obs" and o.get("mint") in mints:
                    obs.setdefault(o["mint"], []).append((f, o))
    return obs


def parse_outs(s):
    res = []
    if not s or s == "-":
        return res
    for n, part in enumerate(s.split(",")):
        a = part.split(":")
        if len(a) != 4:
            continue
        res.append({"ms": float(a[0]), "sol": float(a[1]), "buy": int(a[2]), "w6": a[3], "n": n})
    return res


def spot(v, t):
    return v / t


def mc_sol(v, t):
    # 1e9 tokens * 1e6 decimals = 1e15 raw supply; price in lamports/raw -> SOL mc
    return v / t * 1e15 / 1e9


def glued(trades, cs, ci, create_sig):
    """Indices (into trades) of the create-tx events and of the glued bundle events."""
    create_idx = [j for j, t in enumerate(trades) if t["sig"] == create_sig]
    j0 = (max(create_idx) + 1) if create_idx else 0
    prev_i = ci
    glue = []
    j = j0
    while j < len(trades):
        t = trades[j]
        if t["s"] != cs:
            break
        if t["is_buy"] and (t["i"] == prev_i or t["i"] == prev_i + 1):
            glue.append(j)
            prev_i = t["i"]
            j += 1
            continue
        break
    return create_idx, glue


def match(outs, trades, eligible, L, w_mode="user", mono=False):
    """Greedy: outs with ms < L in increasing ms order; each takes the first unmatched eligible chain
    trade (chain order) with same buy flag, wallet prefix, SOL tolerance for buys."""
    used = set()
    matched = []
    unmatched = []
    last = -1
    for o in sorted([o for o in outs if o["ms"] < L], key=lambda o: (o["ms"], o["n"])):
        hit = None
        for j in eligible:
            if j in used:
                continue
            if mono and j <= last:
                continue
            t = trades[j]
            if bool(t["is_buy"]) != bool(o["buy"]):
                continue
            if w_mode == "user":
                okw = t["user"].startswith(o["w6"])
            elif w_mode == "signer":
                okw = any(s.startswith(o["w6"]) for s in (t["signers"] or []))
            else:  # either
                okw = t["user"].startswith(o["w6"]) or any(s.startswith(o["w6"]) for s in (t["signers"] or []))
            if not okw:
                continue
            if o["buy"]:
                cs_ = t["sol"] / 1e9
                if abs(o["sol"] - cs_) > max(0.02, 0.15 * o["sol"]):
                    continue
            hit = j
            break
        if hit is None:
            unmatched.append(o)
        else:
            used.add(hit)
            matched.append((o, hit))
            last = max(last, hit)
    return matched, unmatched


def simulate(m, info, trades, outs, L, opts):
    cs, ci, csig = info["slot"], info["idx"], info["sig"]
    deployer, creator = info["user"], info["creator"]
    create_idx, glue = glued(trades, cs, ci, csig)
    # reference state: after last glued buy, else after the dev buy in the create tx, else initial curve
    if glue:
        ref_j = glue[-1]
    elif create_idx:
        ref_j = create_idx[-1]
    else:
        ref_j = None
    if ref_j is not None:
        Vb, Tb = trades[ref_j]["vsol"], trades[ref_j]["vtok"]
    else:
        Vb, Tb = info["vsol0"], info["vtok0"]
    excl = set(create_idx) | set(glue)
    glue_wallets = {trades[j]["user"] for j in glue}
    ins = {deployer, creator}
    if opts.get("excl_glue_wallets", True):
        ins |= glue_wallets
    eligible = [j for j, t in enumerate(trades)
                if j not in excl and t["s"] - cs < opts.get("match_slots", MATCH_SLOTS) and t["user"] not in ins]
    matched, unmatched = match(outs, trades, eligible, L, opts.get("w_mode", "user"), opts.get("mono", False))
    floor_j = ref_j if ref_j is not None else -1
    last_m = max([h for _, h in matched], default=-1)
    p = max(last_m, floor_j)
    r = {"bundle_sigs": [], "matched": len(matched), "unmatched_outs": len(unmatched)}
    seen = set()
    for j in glue:
        if trades[j]["sig"] not in seen and trades[j]["sig"] != csig:
            seen.add(trades[j]["sig"])
            r["bundle_sigs"].append(trades[j]["sig"])
    if p < 0:
        # nothing on chain to land after (no dev buy, no bundle, no match): land on initial curve
        V, T = info["vsol0"], info["vtok0"]
        after = None
        buy_slot = cs
        fbps = None
    else:
        a = trades[p]
        V, T = a["vsol"], a["vtok"]
        after = a
        buy_slot = a["s"]
        if opts.get("buy_slot_mode") == "next" and p + 1 < len(trades):
            # variant that reproduces the file: hold measured from the slot of the next chain trade
            buy_slot = trades[p + 1]["s"]
    r["after_sig"] = after["sig"] if after else None
    r["after_user"] = after["user"] if after else None
    r["after_j"] = p
    r["ahead_nonglued"] = sum(1 for j in range(0, p + 1) if j not in excl)
    ratio = spot(V, T) / spot(Vb, Tb)
    r["ratio"] = ratio
    r["mc_fill"] = mc_sol(V, T)
    r["mc_bundle"] = mc_sol(Vb, Tb)
    r["V_fill"], r["T_fill"] = V, T
    r["filled"] = ratio <= GUARD
    if not r["filled"]:
        r["pnl"] = -FAIL_COST
        return r
    a = after if after else (trades[0] if trades else None)
    fb = (a["fee_bps"] + a["cfee_bps"]) if a else 125
    if opts.get("fee_override") is not None:
        fb = opts["fee_override"]
    f = fb / 1e4
    X = int(SIZE * 10_000 // (10_000 + fb))           # == floor(0.5e9/(1+f)) exactly
    q = (T * X) // (V + X)
    q_eff = math.floor(q * PEN)
    r.update({"fee_bps_total": fb, "X": X, "q": q, "q_eff": q_eff})
    V += X
    T -= q
    nb = ns = 0
    sell_before = None
    sell_after = after["sig"] if after else None
    grad = False
    j = p + 1
    max_v = V
    while j < len(trades):
        t = trades[j]
        if t["s"] >= buy_slot + HOLD_SLOTS:
            sell_before = t
            break
        if t["is_buy"]:
            s = t["sol"]
            dT = (T * s) // (V + s)
            V += s
            T -= dT
            nb += 1
        else:
            k = t["tok"]
            dV = (V * k) // (T + k)
            V -= dV
            T += k
            ns += 1
        sell_after = t["sig"]
        max_v = max(max_v, V)
        j += 1
        if V >= GRAD_V:
            grad = True
            sell_before = trades[j] if j < len(trades) else None
            break
    fs = f
    if opts.get("sell_fee_from_last"):
        lt = trades[j - 1] if j - 1 >= 0 else a
        fs = (lt["fee_bps"] + lt["cfee_bps"]) / 1e4
    gross = (V * q_eff) // (T + q_eff)
    out = gross * (1 - fs)
    r.update({
        "sell_before_sig": sell_before["sig"] if sell_before else None,
        "sell_after_sig": sell_after,
        "buys_after": nb, "sells_after": ns, "grad": grad, "max_v": max_v,
        "mc_sell": mc_sol(V, T), "V_sell": V, "T_sell": T,
        "sol_out": out / 1e9,
        "sell_slot": (sell_before["s"] if sell_before else None),
        "buy_slot": buy_slot,
        "buy_slot_landing": after["s"] if after else cs,
        "no_later_trade": sell_before is None and not grad,
    })
    r["pnl"] = out / 1e9 - SELL_TX - BUY_COST
    return r


def continuity(trades, upto_j):
    """Check that each event's pre-state equals the previous event's post-state (completeness check)."""
    bad = []
    for j in range(1, min(upto_j + 1, len(trades))):
        a, b = trades[j - 1], trades[j]
        if b["is_buy"]:
            pv, pt = b["vsol"] - b["sol"], b["vtok"] + b["tok"]
        else:
            pv, pt = b["vsol"] + b["sol"], b["vtok"] - b["tok"]
        if (pv, pt) != (a["vsol"], a["vtok"]):
            bad.append((j, b["sig"], pv - a["vsol"], pt - a["vtok"]))
    return bad


def main(opts=None, write=True, quiet=False):
    opts = opts or {}
    res = json.load(open(RESULT))
    mints = {x["mint"] for x in res}
    chain = load_chain()
    launches = load_launches(mints)
    obs = load_obs(mints)
    out = []
    for x in res:
        m = x["mint"]
        L0 = launches.get(m, [])
        info = dict(L0[0]) if L0 else {}
        cr = chain[m]["creates"]
        info["vsol0"] = cr[0]["vsol0"] if cr else 30_000_000_000
        info["vtok0"] = cr[0]["vtok0"] if cr else 1_073_000_000_000_000
        trades = chain[m]["trades"]
        o = obs[m][0][1]
        outs = parse_outs(o["outs"])
        row = {"mint": m, "n_launch_rows": len(L0), "create_sig_ok": info.get("sig") == x["create_sig"],
               "bt_ok": info.get("bt") == x["bt"], "deployer_ok": info.get("user") == x["deployer"],
               "creator_ok": info.get("creator") == x.get("creator_field"),
               "obs_file": obs[m][0][0], "n_outs": len(outs), "land": {}}
        if cr:
            c = cr[0]
            row["create_event"] = {"vsol0": c["vsol0"], "vtok0": c["vtok0"], "rtok0": c["rtok0"],
                                   "supply": c["supply"], "token_program": c["token_program"],
                                   "tail_hex": c["tail_hex"], "slot": c["s"], "i": c["i"], "sig": c["sig"]}
        maxp = 0
        for L in LS:
            r = simulate(m, info, trades, outs, L, opts)
            row["land"][str(L)] = r
            maxp = max(maxp, r["after_j"])
        # continuity check from first event through the furthest exit point needed (both hold rules)
        endj = 0
        for L in LS:
            r = row["land"][str(L)]
            for mode in ("after", "next"):
                rr = r if mode == opts.get("buy_slot_mode", "after") else simulate(
                    m, info, trades, outs, L, dict(opts, buy_slot_mode=mode))
                sb = rr.get("sell_before_sig")
                if sb:
                    endj = max(endj, next(j for j, t in enumerate(trades) if t["sig"] == sb))
                else:
                    endj = max(endj, len(trades) - 1 if rr.get("filled") else rr["after_j"] + 1)
        row["cont_end_j"] = endj
        row["cont_breaks"] = continuity(trades, endj)
        row["n_trades_chain"] = len(trades)
        out.append(row)
    if write:
        with open(os.path.join(HERE, "work", "replay_rows.json"), "w") as fh:
            json.dump(out, fh, default=str)
    return res, out


if __name__ == "__main__":
    main()
    print("ok")
