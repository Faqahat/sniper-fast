#!/usr/bin/env python3
"""REPLAY_065 core (read-only, offline): replay one live position at another size on the real chain sequence.

Per position (a pre-send fill or a regular M2 dip fill):
  * entry  : our buy at its ACTUAL chain position (slot, index); the curve state just before it; pump's own buy math
             (budget -> net SOL n with ceil fees; tokens = t (n-1) // (v + n - 1), the buy_exact_quote_in formula, MEASURED on
             the tape); our buy limit re-checked at the new size with the engine's exact formula (pre-send: limit_min_out at
             the attempt's signing state; regular: the guard's min_out on the dump's post-trade state / 1.05)
  * between: every real trade of the token after our buy, in chain order, with its own decoded limit (fetch.py):
               quote / exact-SOL buys: same net SOL, tokens from the new state, fail if below their min tokens out
               exact-token buys      : same tokens, cost from the new state, fail if above their max SOL
               sells                 : same tokens (less any tokens the wallet did not get because its own earlier buy in the
                                       window failed or got fewer tokens), fail if the SOL after fees is below their min out
             a failed trade is dropped and the state after it changes (cascade); failed sells with pump's TooLittleSolReceived
             (6003) are re-tried on the new state and applied if they would now pass
  * exit   : the engine's rule on the new state: pre-send TP +10% / SL -20% on each later trade (value = sell_sol_out x (1 - fr)
             / spend) before the engine's slot reaches entry slot + 2; regular: SL -50% (TP off) before slot + hold - 1.
             If the decision is the live one, the sell lands at the live sell's chain position; else at the decision + the
             median live delay of that exit kind (MEASURED on these runs)
  * P&L    : realized as the engine books it: sell SOL after pump's fees - spend - the buy's fee, tip and token-account rent
             - the sell's fee and tips (fees, tips and rent as live: they do not depend on size)
All replay outputs are INFERRED; the inputs (tape, live records, decoded limits) are MEASURED."""
import json, math, pickle, collections
import numpy as np
import pmath as PM

BASE = "/home/moiz/sniper-data/replay065"
SMS = 212.0
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
SUPPLY = 1e15


def f32(x): return float(np.float32(x))


def fee_rate_ps(fb, cb):
    """presend::fee_rate: (fee bps or 95) + (creator bps or 30), / 1e4, float32"""
    return f32(((fb if fb != 0 else 95) + (cb if cb != 0 else 30)) / 1e4)


def limit_min_out(vsol, vtok, spend, fr, drop):
    """src/presend_live.rs limit_min_out (f64 math as the engine)"""
    v, t = float(vsol), float(vtok)
    k = v * t
    vl = min(v * math.sqrt(1.0 - drop), 100e9 - 1.0)
    tl = k / vl
    x = spend / (1.0 + fr)
    q = math.floor(tl * x / (vl + x))
    return int(q) if q >= 1 else None


def guard_min_out(dvsol, dvtok, spend, fb, cb, guard):
    """dipmode.rs: fr = (fbps + cbps).max(1) / 1e4; xin = (spend / (1 + fr)) as u128; q = vtok * xin / (vsol + xin); floor(q / guard)"""
    fr = max(fb + cb, 1) / 1e4
    xin = int(spend / (1.0 + fr))
    q = dvtok * xin // (dvsol + xin)
    return max(int(math.floor(float(q) / guard)), 1)


def eng_sell_out(v, t, q):
    """dip::sell_sol_out: v - v * t / (t + q) (u128)"""
    return v - v * t // (t + q) if t + q else 0


class Clock:
    def __init__(self, slot0, bsize):
        self.slot0 = slot0; self.bsize = bsize
    def nblk(self, s):
        k = s - self.slot0
        if 0 <= k < len(self.bsize) and self.bsize[k] > 0: return int(self.bsize[k])
        return 0
    def cc(self, s, i):
        n = self.nblk(s) or 400
        return s * SMS + i / max(float(n), i + 1.0) * SMS
    def inv(self, a):
        s = int(a // SMS); f = a / SMS - s
        n = self.nblk(s) or 400
        return s, f * n


def classify(tr, args):
    """the decoded limit of one recorded trade: kind (quote / tok / sell / unk), limit, outer (signed limit) or cpi.
    tr: the tape trade; args: fetch.py record of its tx (or None). Several pump ixs in one tx: matched by amounts."""
    if args is None or args.get("kind") != "ok":
        return dict(kind="unk", lim=None, src="nofetch")
    n, q = tr["sol"], tr["tok"]
    for p in args.get("pump", []):
        a1, a2 = p["a1"], p["a2"]; src = "outer" if p["q"] == -1 else "cpi"
        if tr["buy"]:
            if a1 == q:
                return dict(kind="tok", lim=a2, src=src, disc=p["disc"])
            if a1 >= n and q >= a2:
                return dict(kind="quote", lim=a2, budget=a1, src=src, disc=p["disc"])
        else:
            if a1 == q:
                return dict(kind="sell", lim=a2, src=src, disc=p["disc"])
    return dict(kind="unk", lim=None, src="nomatch")


class Data:
    def __init__(self):
        TP = pickle.load(open(f"{BASE}/tape.pkl", "rb"))
        self.tape = TP["tape"]; self.ck = Clock(TP["slot0"], TP["bsize"])
        self.live = pickle.load(open(f"{BASE}/live.pkl", "rb"))
        self.args = {}
        for fn in ("args_hold.jsonl", "args_extra.jsonl"):
            try:
                for l in open(f"{BASE}/{fn}"):
                    r = json.loads(l)
                    if r.get("kind") == "ok" or r["sig"] not in self.args: self.args[r["sig"]] = r
            except FileNotFoundError:
                pass

    def state_before(self, mint, pos):
        """the curve state after the token's last successful trade strictly before chain position pos=(slot, idx[, j])"""
        tr = self.tape[mint]["trades"]
        last = None
        for t in tr:
            if (t["s"], t["i"], t["j"]) < tuple(pos) + ((0,) if len(pos) == 2 else ()): last = t
            else: break
        return last

    def trade_at(self, mint, s, i, ours=None):
        for t in self.tape[mint]["trades"]:
            if t["s"] == s and t["i"] == i and (ours is None or bool(t["ours"]) == ours): return t
        return None


def tok_formula(tr, v0, t0):
    """which buy formula reproduces this recorded buy at its real pre-state (MEASURED per trade)"""
    if tr["sol"] > 1 and t0 * (tr["sol"] - 1) // (v0 + tr["sol"] - 1) == tr["tok"]: return "n1"
    if t0 * tr["sol"] // (v0 + tr["sol"]) == tr["tok"]: return "floor"
    return "exact"


def buy_out(v, t, n, form):
    if form == "floor": return t * n // (v + n)
    return t * (n - 1) // (v + n - 1)


class Pos:
    """one live position, prepared for replay at any size"""
    pass


def prepare(D, mint, buy_pos, sell_pos, end_slot, our_sigs):
    """the token's later trades (chain order) after our buy up to end_slot, with decoded limits; the failed 6003 sells.
    Returns (pre-state trade, our buy trade, list of follower rows)."""
    T = D.tape[mint]
    rows = []
    pre = None; ours_buy = None
    for t in T["trades"]:
        p = (t["s"], t["i"], t["j"])
        if (t["s"], t["i"]) < buy_pos: pre = t; continue
        if (t["s"], t["i"]) == buy_pos:
            if t["sig"] in our_sigs: ours_buy = t
            else: pre = t                  # another trade in our own tx (never expected)
            continue
        if t["s"] > end_slot: break
        if t["sig"] in our_sigs: continue
        rows.append(dict(kind="trade", s=t["s"], i=t["i"], j=t["j"], tr=t, cls=classify(t, D.args.get(t["sig"])), user=t["user"]))
    for x in T["fails"]:
        s, i, sig, err = x[0], x[1], x[2], x[3]
        if (s, i) <= buy_pos or s > end_slot or "6003" not in err: continue
        a = D.args.get(sig)
        if not a or a.get("kind") != "ok": continue
        cand = [p for p in a.get("pump", []) if p["disc"] in ("33e685a4017f83ad", "1c92de7726c469d5", "5df6823ce7e940b2", "c2ab1c46684d5b2f")]
        if not cand: continue
        p = cand[0]
        rows.append(dict(kind="fail_sell", s=s, i=i, j=0, sig=sig, a1=p["a1"], a2=p["a2"], src="outer" if p["q"] == -1 else "cpi", user=a.get("signer")))
    rows.sort(key=lambda r: (r["s"], r["i"], r["j"]))
    return pre, ours_buy, rows


def walk(D, mint, pre, rows, size, fb, cb, upto, rng=None, cut=0.0, cpi_free=False, record=None, nolim=False, fmode="refined", buy_slot=None):
    """apply our buy of `size` lamports on the state after `pre`, then the follower rows in order, stopping before chain position
    `upto` (our sell). Returns dict(v, t, q, n, states=[(row index, v, t, applied)], dropped, resurrected).
    cut: drop this share of later BUYS at random (stress); cpi_free: CPI followers never fail (sensitivity);
    nolim: no follower ever fails (own price impact only; failed 6003 sells stay failed);
    fmode: "refined" (default) = a trade whose limit provably moves with our buy (requote: a CPI that computes its limit at
    execution, slack exactly 0 at its real state; or a limit already tighter than the quote on the state before our buy, so
    it was set after seeing our buy) never fails because of our size; "fixed" = every decoded limit fixed as signed;
    "adaptive" = refined, and a follower whose quote state is unclear also re-quotes when it landed in a later slot than our buy."""
    v, t = pre["vsol"], pre["vtok"]
    n = PM.net_of_budget(size, fb, cb)
    q = t * (n - 1) // (v + n - 1)
    v += n; t -= q
    out = dict(q=q, n=n, v_after=v, t_after=t, dropped=[], resurrected=[], applied=[], states=[])
    delta = collections.defaultdict(int)          # per wallet: real tokens bought in the window - replay tokens (for its later sells)
    rows_slot0 = buy_slot if buy_slot is not None else (pre["s"] if pre is not None else 0)
    for k, r in enumerate(rows):
        if (r["s"], r["i"], r["j"]) >= upto: break
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
                qq = buy_out(v, t, nn, form)
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
