#!/usr/bin/env python3
"""SIZE study library (read-only, offline). REPLAY_065's exact replay (real/r065: core.py, positions.py, pmath.py) plus ONE addition
needed to replay a run at a SMALLER size than it ran:

  failed follower buys come back. A buy by another wallet that FAILED on chain with a slippage error (6042 below min tokens out,
  6002 too much SOL) inside our span is a row "fail_buy" with its decoded limit (getTransaction, fetch.py): quote buys
  (38fc7408 / c2ab1c46 / e1f7501e: a1 = SOL budget, a2 = min tokens; net SOL = pump's net_of_budget(a1), 100 % match on 1,883
  recorded buys) and exact-token buys (66063d12 / 07051dc4 / b817ee61: a1 = tokens, a2 = max SOL). On the replayed state it is
  re-tried; if it would now pass, it is applied (it buys, the price goes up). Guards (conservative for small sizes):
    * a failed buy that would PASS at the live size (state = chain) is unexplained -> never re-tried ("bad");
    * a wallet that had a successful buy in the same span live is not re-tried (its failed tx may be a duplicate copy);
    * at most one revived buy per wallet per position; a revived buyer's later sell is not invented (none in the records).
  At sizes above live nothing changes (failed buys stay failed; REPLAY_065 is reproduced exactly).

Everything else is REPLAY_065 unchanged (follower limits fixed/requote rule, cascade, 6003 sell retries, exits, costs).
Replay outputs are INFERRED; the tape, records and decoded limits are MEASURED."""
import sys, re, json, math, pickle, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real/r065")
import numpy as np
import core, pmath as PM

OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
AMS = "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"
BUY_TOK = {"b817ee6167c5d33d", "07051dc4f5176550", "66063d1201daebea"}
BUY_QUOTE = {"38fc74089edfcd5f", "c2ab1c46684d5b2f", "e1f7501ed5b38488"}
CODE = re.compile(r'"Custom":(\d+)')
CFG = dict(resurrect=True)
_prepare0 = core.prepare
_walk0 = core.walk


def code_of(err):
    m = CODE.search(err or ""); return int(m.group(1)) if m else None


def prepare2(D, mint, buy_pos, sell_pos, end_slot, our_sigs):
    pre, ob, rows = _prepare0(D, mint, buy_pos, sell_pos, end_slot, our_sigs)
    for x in D.tape[mint]["fails"]:
        s, i, sig, err, signer = x[0], x[1], x[2], x[3], x[4]
        if (s, i) <= buy_pos or s > end_slot or signer in OURS: continue
        c = code_of(err)
        if c not in (6002, 6042): continue
        a = D.args.get(sig)
        if not a or a.get("kind") != "ok":
            rows.append(dict(kind="fail_buy_nodec", s=s, i=i, j=0, sig=sig, user=signer, code=c)); continue
        cand = [p for p in a.get("pump", []) if p["disc"] in BUY_TOK or p["disc"] in BUY_QUOTE]
        if not cand:
            rows.append(dict(kind="fail_buy_nodec", s=s, i=i, j=0, sig=sig, user=signer, code=c)); continue
        p = cand[0]
        rows.append(dict(kind="fail_buy", s=s, i=i, j=0, sig=sig, a1=p["a1"], a2=p["a2"], bkind="tok" if p["disc"] in BUY_TOK else "quote",
                         disc=p["disc"], src="outer" if p["q"] == -1 else "cpi", user=a.get("signer") or signer, code=c, n_ix=len(cand), bad=False))
    rows.sort(key=lambda r: (r["s"], r["i"], r["j"]))
    return pre, ob, rows


def try_buy(v, t, r, fb, cb):
    """a failed buy re-tried on state (v, t): (ok, net SOL in, tokens out)"""
    if r["bkind"] == "quote":
        n = PM.net_of_budget(r["a1"], fb, cb)
        if n <= 1: return False, 0, 0
        q = t * (n - 1) // (v + n - 1)
        return q >= r["a2"], n, q
    a = r["a1"]
    if a >= t: return False, 0, 0
    c = PM.cost_exact_tok(v, t, a)
    return c + PM.fees(c, fb, cb) <= r["a2"], c, a


def walk2(D, mint, pre, rows, size, fb, cb, upto, rng=None, cut=0.0, cpi_free=False, record=None, nolim=False, fmode="refined", buy_slot=None):
    """core.walk + the fail_buy rows (see the module doc). Same outputs, plus out['revived'] = [(row index, SOL in)]."""
    v, t = pre["vsol"], pre["vtok"]
    n = PM.net_of_budget(size, fb, cb)
    q = t * (n - 1) // (v + n - 1)
    v += n; t -= q
    out = dict(q=q, n=n, v_after=v, t_after=t, dropped=[], resurrected=[], applied=[], states=[], revived=[], fb_live_pass=[])
    delta = collections.defaultdict(int)
    rows_slot0 = buy_slot if buy_slot is not None else (pre["s"] if pre is not None else 0)
    live_buyers = {r["tr"]["user"] for r in rows if r["kind"] == "trade" and r["tr"]["buy"]} | \
                  {r["tr"]["signer"] for r in rows if r["kind"] == "trade" and r["tr"]["buy"]}
    revived_users = set()
    lfb, lcb = fb, cb
    for k, r in enumerate(rows):
        if (r["s"], r["i"], r["j"]) >= upto: break
        if r["kind"] == "fail_buy_nodec": continue
        if r["kind"] == "fail_buy":
            draw = rng.random() if (cut > 0 and rng is not None) else 1.0
            if nolim or not CFG["resurrect"] or r.get("bad") or r["user"] in live_buyers or r["user"] in revived_users: continue
            ok, nn, qq = try_buy(v, t, r, lfb, lcb)
            if not ok: continue
            if draw < cut: continue                       # stress: this revived buyer is among the 20 % that never come
            v += nn; t -= qq; revived_users.add(r["user"]); out["revived"].append((k, nn))
            out["states"].append((k, v, t, True)); continue
        if r["kind"] == "fail_sell":
            if nolim or (cpi_free and r["src"] == "cpi"): continue
            qa = r["a1"] - delta.get(r["user"], 0)
            if qa <= 0: continue
            o = PM.sell_sol(v, t, qa); fr = PM.fees(o, 95, 30)
            if o - fr >= r["a2"]:
                v -= o; t += qa; out["resurrected"].append(k)
                out["states"].append((k, v, t, True))
            continue
        tr = r["tr"]; c = r["cls"]; u = r["user"]
        lfb, lcb = tr["fbps"], tr["cbps"]
        free = nolim or (fmode in ("refined", "adaptive") and r.get("requote", False)) or \
            (fmode == "adaptive" and r.get("ref") == "unclear" and r["s"] > rows_slot0)
        if tr["buy"]:
            if cut > 0 and rng is not None and rng.random() < cut:
                out["dropped"].append((k, "cut")); delta[u] += tr["tok"]; out["states"].append((k, v, t, False)); continue
            if c["kind"] == "tok":
                a = tr["tok"]
                if a >= t: ok = False
                else:
                    nn = PM.cost_exact_tok(v, t, a)
                    ok = free or (nn + PM.fees(nn, tr["fbps"], tr["cbps"]) <= c["lim"]) or (cpi_free and c["src"] == "cpi")
                if not ok:
                    out["dropped"].append((k, "slip")); delta[u] += tr["tok"]; out["states"].append((k, v, t, False)); continue
                v += nn; t -= a
            else:
                nn = tr["sol"]
                form = r.get("form", "n1")
                qq = core.buy_out(v, t, nn, form)
                if c["kind"] == "quote" and qq < c["lim"] and not free and not (cpi_free and c["src"] == "cpi"):
                    out["dropped"].append((k, "slip")); delta[u] += tr["tok"]; out["states"].append((k, v, t, False)); continue
                v += nn; t -= qq
                delta[u] += tr["tok"] - qq
        else:
            qa = tr["tok"] - max(delta.get(u, 0), 0)
            if qa <= 0:
                out["dropped"].append((k, "nobal")); out["states"].append((k, v, t, False)); continue
            if qa < tr["tok"]: delta[u] = 0
            o = PM.sell_sol(v, t, qa)
            if c["kind"] == "sell" and o - PM.fees(o, tr["fbps"], tr["cbps"]) < c["lim"] and not free and not (cpi_free and c["src"] == "cpi"):
                out["dropped"].append((k, "slip")); out["states"].append((k, v, t, False)); continue
            v -= o; t += qa
        out["states"].append((k, v, t, True))
    out["v"], out["t"] = v, t
    return out


def install():
    core.prepare = prepare2
    core.walk = walk2


def mark_bad(D, p):
    """a failed buy that would pass on the LIVE state (live size) is unexplained: never re-tried. Returns how many."""
    fbr = [k for k, r in enumerate(p.rows) if r["kind"] == "fail_buy"]
    if not fbr: return 0
    ob = p.ours_buy
    nb = 0
    # walk at the live size, re-trying every failed buy on the live state without applying it
    v, t = ob["vsol"], ob["vtok"]
    lfb, lcb = ob["fbps"], ob["cbps"]
    for k, r in enumerate(p.rows):
        if r["kind"] == "trade":
            v, t = r["tr"]["vsol"], r["tr"]["vtok"]; lfb, lcb = r["tr"]["fbps"], r["tr"]["cbps"]
        elif r["kind"] == "fail_buy":
            ok, _, _ = try_buy(v, t, r, lfb, lcb)
            if ok: r["bad"] = True; nb += 1
    return nb


def replay2(D, p, size, delays, cut=0.0, rng=None, cpi_free=False, force_live_exit=False, nolim=False, fmode="refined"):
    """positions.replay (REPLAY_065) unchanged in logic, on walk2; adds: revived buys (n, SOL), priced-out buys (n, SOL), flat flag
    (no applied trade of another wallet strictly before our sell), others' buy SOL before our sell."""
    import positions as PO
    ob = p.ours_buy
    fb, cb = ob["fbps"], ob["cbps"]
    pre = p.pre
    r = dict(size=size)
    n = PM.net_of_budget(size, fb, cb)
    q = pre["vtok"] * (n - 1) // (pre["vsol"] + n - 1)
    if p.kind == "ps":
        a = p.att
        mo = core.limit_min_out(a["vsol"], a["vtok"], size, p.fr_sign, 0.12)
    else:
        d = p.dump
        mo = core.guard_min_out(d["vsol"], d["vtok"], size, d["fbps"], d["cbps"], p.guard)
    r.update(n=n, q=q, min_out=mo, filled=(mo is not None and q >= mo))
    if not r["filled"]:
        return r
    W = walk2(D, p.mint, pre, p.rows, size, fb, cb, (10 ** 15, 0, 0), rng=rng, cut=cut, cpi_free=cpi_free, nolim=nolim, fmode=fmode, buy_slot=p.buy_pos[0])
    st = {k: (v, t, ap) for k, v, t, ap in W["states"]}
    spend = size
    land = p.land_slot
    if p.kind == "ps":
        last_chk = land + 1; tp, sl_ = 0.10, 0.20
    else:
        last_chk = land + p.hold - 2; tp, sl_ = None, 0.50
    dec = None
    for k, row in enumerate(p.rows):
        if k not in st: continue
        if not PO.checked(p, row, last_chk): continue
        v, t, ap = st[k]
        if not ap: continue
        if row["kind"] == "trade":
            tfb, tcb = row["tr"]["fbps"], row["tr"]["cbps"]
        else:
            tfb, tcb = 95, 30
        if p.kind == "ps":
            val = PO.value_ps(v, t, q, tfb, tcb, spend)
            if val >= 1.0 + tp: dec = ("take-profit", k, val); break
            if val <= 1.0 - sl_: dec = ("stop-loss", k, val); break
        else:
            val = PO.value_reg(v, t, q, tfb, tcb, spend)
            if val <= 1.0 - sl_: dec = ("stop-loss", k, val); break
    why = dec[0] if dec else "time-limit"
    r["why"] = why
    live_dec_row = getattr(p, "live_dec_row", "unset")
    same = (why == p.exit_why) and (why == "time-limit" or (dec and dec[1] == live_dec_row))
    if force_live_exit or same:
        sp = p.sell_pos; r["sell_src"] = "live"
    elif dec:
        rw = p.rows[dec[1]]
        a = D.ck.cc(rw["s"], rw["i"]) + delays[p.kind + ":tpsl"]
        sp = D.ck.inv(a); sp = (sp[0], sp[1]); r["sell_src"] = "model_tpsl"
    else:
        a = (land + (2 if p.kind == "ps" else p.hold)) * core.SMS + delays[p.kind + ":time"]
        sp = D.ck.inv(a); sp = (sp[0], sp[1]); r["sell_src"] = "model_time"
    r["sell_pos"] = sp
    v, t = W["v_after"], W["t_after"]
    for k, row in enumerate(p.rows):
        if (row["s"], row["i"]) >= (sp[0], sp[1]): break
        if k in st: v, t = st[k][0], st[k][1]
    gross = PM.sell_sol(v, t, q)
    sfb, scb = (p.sell_tr["fbps"], p.sell_tr["cbps"]) if p.sell_tr else (fb, cb)
    net = gross - PM.fees(gross, sfb, scb)
    before = lambda k: (p.rows[k]["s"], p.rows[k]["i"]) < (sp[0], sp[1])
    slip = [k for k, why in W["dropped"] if why == "slip" and before(k)]
    r.update(gross=gross, net=net, pnl=net - size - p.costs,
             priced_out_n=sum(1 for k in slip if p.rows[k]["tr"]["buy"]), priced_out_sol=sum(p.rows[k]["tr"]["sol"] for k in slip if p.rows[k]["tr"]["buy"]) / 1e9,
             sells_failed_n=sum(1 for k in slip if not p.rows[k]["tr"]["buy"]),
             revived_n=sum(1 for k, _ in W["revived"] if before(k)), revived_sol=sum(nn for k, nn in W["revived"] if before(k)) / 1e9,
             flat=not any(ap and before(k) and p.rows[k]["kind"] in ("trade", "fail_buy", "fail_sell") for k, (v_, t_, ap) in st.items()),
             buys_in=sum(1 for k, (v_, t_, ap) in st.items() if ap and before(k) and ((p.rows[k]["kind"] == "trade" and p.rows[k]["tr"]["buy"]) or p.rows[k]["kind"] == "fail_buy")))
    return r
