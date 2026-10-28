#!/usr/bin/env python3
"""MINOR step 7 (read-only): decode his router trade_v3 args from the public-RPC sample (minor/rpc/*.json) and place each buy on the
tape: tokens the spend would buy at (a) the state just before his tx position, (b) right after the trigger (biggest outside drop in
the 5 slots before), (c) just before the trigger, (d) the state before the previous haqq buy on the mint (sibling reference).
Ratios min_out / tokens_x show which state his limit is anchored to and how wide it is. MEASURED.
Out: minor/m7.txt"""
import json, glob, pickle, sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import xlib as X
from plib import Out
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/minor"
ROUTER = "haqqqMGN35ehCftXca3KWxJFXTBcWTWeNHNtUHLGQdh"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58d(s):
    n = 0
    for ch in s: n = n * 58 + B58.index(ch)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + raw


def toks(v, t, spend, fee=0.0125):
    sn = spend / (1 + fee); return t - v * t / (v + sn)


def main():
    P = Out(f"{OUT}/m7.txt")
    ids, idm = L.ids_map()
    R, MI, span, CC = X.tape(); H = MI["who"]["haqq"]
    rows = []
    for f in sorted(glob.glob(f"{OUT}/rpc/*.json")):
        j = json.load(open(f)); t = j["result"]; rec = j["_rec"]
        msg = t["transaction"]["message"]; la = t["meta"].get("loadedAddresses") or {}
        keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
        data = [b58d(ix["data"]) for ix in msg["instructions"] if keys[ix["programIdIndex"]] == ROUTER]
        if not data: continue
        d = data[0]
        x = d[8]; a = int.from_bytes(d[9:17], "little"); b = int.from_bytes(d[17:25], "little"); side = d[25] if len(d) > 25 else None
        exp = int.from_bytes(d[26:34], "little") if len(d) >= 34 else None
        spend_l = None
        for v in (a, b):
            if 5_000_000 <= v <= 2_000_000_000 and v % 1_000_000 == 0: spend_l = v
        if spend_l is None: spend_l = min(a, b)
        mo = b if spend_l == a else a
        r = dict(code=rec["code"], ok=rec["ok"], sig=f.split("/")[-1][:-5], spend=spend_l / 1e9, min_out=mo, exp=exp, x=x, side=side, len=len(d),
                 err=str(t["meta"].get("err"))[:60], mint=rec["mint"], s=rec["s"], i=rec["i"])
        m = idm.get(rec["mint"])
        if m is not None and m in span:
            M = X.Mint(m)
            k = int(np.searchsorted(M.sl * 100000 + M.ix, rec["s"] * 100000 + rec["i"]))     # first row at/after his position
            if rec["ok"] and k < M.n and M.sl[k] == rec["s"] and M.ix[k] == rec["i"]: kk = k
            else: kk = k
            vb, tb = M.vsp[kk] if kk < M.n else M.vs[-1], M.vtp[kk] if kk < M.n else M.vt[-1]
            r["tok_pos"] = toks(vb / 1, tb, spend_l / 1e9 * 1e9) if False else toks(vb, tb, spend_l / 1e9)
            lo5 = int(np.searchsorted(M.sl, rec["s"] - 5))
            cand = [q for q in range(lo5, kk) if not M.bu[q] and M.us[q] != H]
            if cand:
                dj = max(cand, key=lambda q: 1 - M.px[q] / M.pxp[q])
                r["tok_post"] = toks(M.vs[dj], M.vt[dj], spend_l / 1e9); r["tok_pre"] = toks(M.vsp[dj], M.vtp[dj], spend_l / 1e9)
                r["d_drop"] = float(1 - M.px[dj] / M.pxp[dj]); r["d_slots"] = int(rec["s"] - M.sl[dj])
                r["n_between"] = int(kk - dj - 1)
            hb = [q for q in range(max(0, kk - 400), kk) if M.us[q] == H and M.bu[q]]
            if hb:
                q = hb[-1]; r["tok_sib"] = toks(M.vsp[q], M.vtp[q], spend_l / 1e9); r["sib_ms"] = float(M.cc[kk] - M.cc[q]) if kk < M.n else None
            r["vpre"] = float(vb / 1e9)
        rows.append(r)
    pickle.dump(rows, open(f"{OUT}/m7.pkl", "wb"))
    P("# Minor bots: decoded limits (public-RPC sample of his buy txs; MEASURED)")
    P("ratio = min_out / tokens the spend buys at that state (1.00 = no slippage allowed; 0.90 = accepts a 10% worse fill); exp = router's post-trade cap")
    for c in sorted(set(r["code"] for r in rows)):
        v = [r for r in rows if r["code"] == c]
        P(f"\n## code {c}: {len(v)} txs ({sum(r['ok'] for r in v)} landed ok)")
        P("| ok | spend | min_out/tok_pos | min_out/tok_post | min_out/tok_pre | min_out/tok_sib | exp/tok_post | exp/min_out | drop | slots after | trades between | curve | sig |")
        P("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in sorted(v, key=lambda r: -r["ok"]):
            g = lambda k: f"{r['min_out'] / r[k]:.3f}" if r.get(k) else "-"
            e1 = f"{r['exp'] / r['tok_post']:.3f}" if r.get("exp") and r.get("tok_post") else "-"
            e2 = f"{r['exp'] / max(r['min_out'], 1):.3f}" if r.get("exp") else "-"
            P(f"| {r['ok']} | {r['spend']:.3f} | {g('tok_pos')} | {g('tok_post')} | {g('tok_pre')} | {g('tok_sib')} | {e1} | {e2} | {r.get('d_drop', 0):.3f} | {r.get('d_slots', '-')} | {r.get('n_between', '-')} | {r.get('vpre', 0):.1f} | {r['sig'][:10]} |")
    P.save()


if __name__ == "__main__":
    main()
