"""BIGLOSS rule families (causal). Each make_* returns (rule, learn)."""
from bscore import Ledger


def learn_all(s_min=0.5):
    def learn(r, L):
        for k in ("dump", "pres", "wh", "cr", "whr"):
            L.setdefault(k, Ledger())
        tc = r["t_close"]; p = r["pnl"]
        sel = r.get("sellers") or {}
        for w, v in sel.items():
            if v >= s_min: L["dump"].add(w, tc, p, v)
        for h in r.get("holders") or []:
            if h[1] >= 2.0: L["pres"].add(h[0], tc, p, 1.0 if sel.get(h[0], 0) >= s_min else 0.0)
        if r["kind"] == "t2" and r["whale"]:
            L["wh"].add(r["whale"], tc, p, 1.0 if sel.get(r["whale"], 0) >= s_min else 0.0)
        if r["creator"]: L["cr"].add(r["creator"], tc, p)
    return learn


def holders_at(r, pmin):
    return [h for h in (r.get("holders") or []) if h[1] >= pmin and h[0] != r["whale"]]


def make_dumper(k, X, pmin=2.0, win_h=None, tau_h=None, kinds=("t2", "rearm"), incl_whale=False, s_min=0.5, cut=1.0):
    """skip if a holder at signing (>= pmin %) sold >= s_min SOL into >= k of our earlier kept holds, net of those <= X."""
    def rule(r, L):
        if r["kind"] not in kinds or "dump" not in L: return 0.0
        hs = [h for h in (r.get("holders") or []) if h[1] >= pmin and (incl_whale or h[0] != r["whale"])]
        for h in hs:
            n, net, fl, ws = L["dump"].stats(h[0], r["t_sign"], win_h, tau_h)
            if n >= k and net <= X: return cut
        return 0.0
    return rule, learn_all(s_min)


def make_presence(k, X, pmin=2.0, win_h=None, tau_h=None, kinds=("t2", "rearm"), min_rate=0.0, cut=1.0):
    """skip if a holder at signing has >= k earlier kept positions where it held >= 2% at signing, their net <= X and the
    share of them where it sold into our hold >= min_rate."""
    def rule(r, L):
        if r["kind"] not in kinds or "pres" not in L: return 0.0
        for h in holders_at(r, pmin):
            n, net, fl, ws = L["pres"].stats(h[0], r["t_sign"], win_h, tau_h)
            if n >= k and net <= X and (ws <= 0 or fl / ws >= min_rate): return cut
        return 0.0
    return rule, learn_all()


def make_whale(k, X, win_h=None, tau_h=None, need_resold=1, cut=1.0):
    """T2: skip if the trigger whale has >= k earlier kept positions as our trigger, net <= X, and resold into >= need_resold."""
    def rule(r, L):
        if r["kind"] != "t2" or "wh" not in L: return 0.0
        n, net, fl, ws = L["wh"].stats(r["whale"], r["t_sign"], win_h, tau_h)
        if n >= k and net <= X and fl >= need_resold: return cut
        return 0.0
    return rule, learn_all()


def make_creator(k=2, X=-0.05, cut=1.0):
    """reference: the live creator loss ledger (n >= 2, sum <= -0.05 over kept positions)."""
    def rule(r, L):
        if "cr" not in L or not r["creator"]: return 0.0
        n, net, fl, ws = L["cr"].stats(r["creator"], r["t_sign"])
        return cut if (n >= k and net <= X) else 0.0
    return rule, learn_all()


def make_feat(fn, kinds=("t2",), cut=1.0):
    def rule(r, L):
        if r["kind"] not in kinds: return 0.0
        try: return cut if fn(r) else 0.0
        except Exception: return 0.0
    return rule, learn_all()


def combine(*rules, cut=None):
    learn = rules[0][1]
    def rule(r, L):
        c = max(x[0](r, L) for x in rules)
        return c if cut is None or c == 0 else cut
    return rule, learn
