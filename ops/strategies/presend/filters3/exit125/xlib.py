"""EXIT-125v200 pricing library.
Curve model: pump.fun constant product on virtual reserves; a sell of q tokens from (vsol, vtok) pays floor(q*vsol/(vtok+q)) gross
(the tape's 'sol' for a sell, before the 1.25% fee). The state is carried in vtok space: other traders' TOKEN amounts are kept as they
were (their sol re-priced), so removing / moving our own sell only shifts vtok by our tokens; vsol = k / vtok with the tape's own k."""
import json, bisect

def gross_out(q, vsol, vtok):
    return q * vsol // (vtok + q)

def prep(x):
    """sorted tape (slot, idx, j) with our fill/sell located; None if no tape"""
    tp = x.get("tape")
    if not tp or not x["sells"]: return None
    tr = sorted(tp, key=lambda a: (a["slot"], a["idx"], a.get("j", 0)))
    sell_sig = x["sells"][0]["sig"]
    fi = next((i for i, a in enumerate(tr) if a["sig"] == x["sig"]), None)
    si = next((i for i, a in enumerate(tr) if a["sig"] == sell_sig and not a["buy"]), None)
    if fi is None or si is None: return None
    return dict(tr=tr, fi=fi, si=si, q=x["tokens"])

def state_at(P, T, tok_adj_after_sell=True, follow_cut=0.0):
    """curve state (vsol, vtok) our cf sell sees if it lands at rx time T (ns): after every OTHER tape trade with t < T that is
    after our fill (by tape order), with our real sell removed.  follow_cut: fraction of other BUYS' tokens after our fill removed
    (stress: followers buy less).  Returns (vsol, vtok, n_trades_used, last_t)."""
    tr, fi, si, q = P["tr"], P["fi"], P["si"], P["q"]
    ref = tr[fi]; ref_i = fi
    cut = 0
    for i in range(fi + 1, len(tr)):
        a = tr[i]
        if i == si: continue
        if a["t"] >= T: continue          # time placement: anything that reached us before T is ahead of our sell
        if i > ref_i: ref = a; ref_i = i
        if follow_cut and a["buy"]: cut += int(a["tok"] * follow_cut)
    vtok = ref["vtok"]; k = ref["vsol"] * ref["vtok"]
    if ref_i > si: vtok -= q              # our real sell had put q tokens back; in the cf world it has not happened yet
    vtok += cut
    vsol = k // vtok if (ref_i > si or cut) else ref["vsol"]
    return vsol, vtok, ref_i, ref["t"]

def value_path(P, spend, fee=0.0125, upto_t=None, follow_cut=0.0):
    """engine-style mark after each other trade after the fill: (t, value=gross(q)*(1-fee)/(spend SOL)) with our real sell removed"""
    tr, fi, si, q = P["tr"], P["fi"], P["si"], P["q"]
    out = []
    cut = 0
    for i in range(fi + 1, len(tr)):
        if i == si: continue
        a = tr[i]
        if upto_t is not None and a["t"] > upto_t: continue
        if follow_cut and a["buy"]: cut += int(a["tok"] * follow_cut)
        vtok = a["vtok"] - (q if i > si else 0) + cut
        vsol = (a["vsol"] * a["vtok"]) // vtok
        out.append((a["t"], gross_out(q, vsol, vtok) * (1 - fee) / (spend * 1e9), i))
    return out
