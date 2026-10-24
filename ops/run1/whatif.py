# READ-ONLY what-if on real chain data: insert OUR buy of SIZE SOL (spend incl. pump fee) right after the creator's
# glued bundle in the create slot (ahead of every outside buyer), replay every later trade on the constant-product
# curve (others' buy SOL and sell tokens held fixed), and sell everything at the end of slot S+k. Costs: pump fee per
# side (from the events), landing fee = FEE_PCT of size, sell fee 0.0005 SOL.
# usage: python3 whatif.py <mint> <create slot> [size SOL=2] [fee %=3] [max k=8]
import sys
sys.path.insert(0, "/root/indep")
from common import get_block, events, is_vote
m, S = sys.argv[1], int(sys.argv[2])
SIZE = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
FEE_PCT = float(sys.argv[4]) if len(sys.argv) > 4 else 3.0
KMAX = int(sys.argv[5]) if len(sys.argv) > 5 else 8
SELL_FEE = 0.0005

trades = []   # ordered (slot, buy, sol_lamports, tok, vsol_after, vtok_after, fee_bps)
glued_end = None
from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(6) as ex:
    BLK = dict(zip(range(S, S + KMAX + 1), ex.map(get_block, range(S, S + KMAX + 1))))
for s in range(S, S + KMAX + 1):
    b = BLK[s]
    if not isinstance(b, dict): continue
    txs = [t for t in b["transactions"] if not is_vote(t)]
    ci = None
    for i, t in enumerate(txs):
        meta = t.get("meta") or {}
        if meta.get("err") is not None: continue
        tr, cr = events(meta.get("logMessages"))
        if s == S and any(c["mint"] == m for c in cr): ci = i
        for e in tr:
            if e["mint"] != m: continue
            trades.append(dict(slot=s, i=i, buy=e["buy"], sol=e["sol"], tok=e["tok"], vsol=e["vsol"], vtok=e["vtok"],
                               fbps=(e.get("fbps") or 0) + (e.get("cbps") or 0)))
        if s == S and ci is not None and i > ci and glued_end is None:
            ev = [e for e in tr if e["mint"] == m and e["buy"]]
            if not ev: glued_end = i   # first tx after the create that is not a glued bundle buy

ge = glued_end if glued_end is not None else 10**9
k0 = next(n for n, t in enumerate(trades) if (t["slot"] == S and t["i"] >= ge) or t["slot"] > S)   # first trade after the bundle
fee_rate = (trades[0]["fbps"] or 125) / 1e4
pre = trades[k0]
V = pre["vsol"] - pre["sol"] if pre["buy"] else pre["vsol"] + pre["sol"]
T = pre["vtok"] + pre["tok"] if pre["buy"] else pre["vtok"] - pre["tok"]
pb = V / T
x = SIZE * 1e9 / (1 + fee_rate)
q = T * x / (V + x); V += x; T -= q
entry = SIZE * 1e9 / q
print(f"mint {m}  create slot {S}  pump fee {fee_rate*100:.2f}%/side")
print(f"our buy: {SIZE} SOL right after the bundle (ahead of {sum(1 for t in trades[k0:] if t['slot']==S and t['buy'])} outside buys in S); "
      f"fill {entry/pb:.3f}x post-bundle (own impact {(V/T)/pb - 1:+.1%})")
by_slot = {}
for t in trades[k0:]:
    if t["buy"]:
        d = T * t["sol"] / (V + t["sol"]); V += t["sol"]; T -= d
    else:
        so = V * t["tok"] / (T + t["tok"]); V -= so; T += t["tok"]
    by_slot[t["slot"]] = (V, T)
land_fee = SIZE * FEE_PCT / 100
print(f"costs: landing fee {FEE_PCT}% = {land_fee:.3f} SOL, pump fee both sides, sell fee {SELL_FEE} SOL\n")
print(f"{'sell after':>15} {'price x pb':>10} {'proceeds':>9} {'PnL SOL':>8} {'PnL %':>7}")
cur = None
SHOW = {0, 1, 2, 3, 4, 5, 7, 10, 14, 23, 46, 92, 138, 184, 276}
for k in range(0, KMAX + 1):
    s = S + k
    if s in by_slot: cur = by_slot[s]
    if cur is None or k not in SHOW: continue
    Vk, Tk = cur
    so = Vk * q / (Tk + q) * (1 - fee_rate) / 1e9
    pnl = so - SIZE - land_fee - SELL_FEE
    print(f"{'S+%d (%.1f s)' % (k, k * 0.217):>15} {(Vk/Tk)/pb:10.2f} {so:9.4f} {pnl:+8.4f} {pnl/SIZE*100:+6.1f}%")
