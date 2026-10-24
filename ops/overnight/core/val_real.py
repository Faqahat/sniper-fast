#!/usr/bin/env python3
# VALIDATION 5 ("do the numbers add up" on REAL money): for every round trip of the case-study wallets in the forward
# window, rebuild their trade with our engine and compare to what really happened on chain.
#  A) exact: their buy re-inserted at its real chain position, their sells at their real positions (same token amounts)
#     -> simulated SOL in/out vs the real TradeEvent amounts (tests path completeness + curve math + our insertion code)
#  B) model: their buy placed by OUR place-in-line model from their ARRIVAL ms in our feed (as we place ours), 1.5% fill
#     penalty, sells at their real slots (same fractions) -> simulated vs real PnL (tests the place model on real money)
import sys, json, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
L = rp.load_launches(); O = rp.load_obs(); A = json.load(open("attempts.json"))
W = {"9Sh2fd": "9Sh2fdqMQcec7W9LzzfvkYphrdyR3S8aUBsKdv9xNYa1", "DGmspi": "DGmspiBs2ePJ7WgN1pyX5RJDpzhyxYrBN1P4bXNC1NR3", "D24ipY": "D24ipYXuDt6PXEPV6rZqfWb35WJaTJW3gDoXwt7yJCwQ"}
todo = [(m, w) for m, v in A.items() for w, a in v.items() if a[0] == 1 and m in O and m in L and L[m]["run"] == "R2"]
byb = collections.defaultdict(set)
for m, w in todo: byb[rp.bucket(m)].add(m)
res = []
for b, ms in byb.items():
    tra = rp.read_bucket("R2", b, ms)
    for m, w in todo:
        if m not in ms or m not in tra: continue
        tr = tra[m]; me = W[w]; c = L[m]
        if min(t["vsol"] for t in tr) < 25e9: continue
        mine = [(k, t) for k, t in enumerate(tr) if t["user"] == me]
        buys = [(k, t) for k, t in mine if t["buy"]]; sells = [(k, t) for k, t in mine if not t["buy"]]
        if len(buys) != 1 or not sells: continue
        kb, tb = buys[0]
        fr = (tr[0]["fbps"] + tr[0]["cbps"]) / 1e4
        real_in = tb["sol"] * (1 + fr) / 1e9; real_out = sum(t["sol"] * (1 - fr) for _, t in sells) / 1e9
        tok_total = tb["tok"]
        def run(entry_idx_path, pen):
            path = [t for t in tr if t["user"] != me]
            V, T = (path[entry_idx_path - 1]["vsol"], path[entry_idx_path - 1]["vtok"]) if entry_idx_path > 0 else (30e9, 1.073e15)
            X = tb["sol"]; q = int(T * X // (V + X)); V += X; T -= q; q_eff = int(q * (1 - pen))
            # sells: at the real chain position of each real sell (index in the path without me), same FRACTION of the position
            spos = []
            for k, t in sells:
                spos.append((sum(1 for u in tr[:k] if u["user"] != me), t["tok"] / tok_total))
            got = 0.0; left = q_eff; si = 0
            for j in range(entry_idx_path, len(path) + 1):
                while si < len(spos) and spos[si][0] == j:
                    kk = min(left, int(q_eff * spos[si][1])) if si < len(spos) - 1 else left
                    so = V * kk // (T + kk); V -= so; T += kk; got += so * (1 - fr) / 1e9; left -= kk; si += 1
                if j == len(path): break
                t = path[j]
                if t["buy"]: d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d
                else: so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
            return got, q
        # A) exact position
        kpath = sum(1 for u in tr[:kb] if u["user"] != me)
        gotA, qA = run(kpath, 0.0)
        # B) model position from their arrival ms
        arr = [o[0] for o in O[m]["outs"] if o[3] == w and o[2]]
        if not arr: continue
        others = [o for o in O[m]["outs"] if o[3] != w]
        path = [t for t in tr if t["user"] != me]
        idx, na = rp.place(path, c, rp.structure(path, c), others, arr[0])
        gotB, qB = run(idx, 0.015)
        res.append(dict(m=m, w=w, real_in=real_in, real_out=real_out, real_pnl=real_out - real_in, A_tok=qA / tok_total, A_out=gotA, A_pnl=gotA - real_in,
                        B_pnl=gotB - real_in, arr=arr[0], kpath=kpath, idx=idx, sig=tb["sig"]))
print(f"round trips checked: {len(res)} (one buy, sold at least once, wallet seen by our engine)")
dA = [r["A_out"] - r["real_out"] for r in res]; tA = [r["A_tok"] for r in res]
print(f"A) exact re-insertion: tokens got / real tokens: median {statistics.median(tA):.6f}; SOL out sim - real: median {statistics.median(dA):+.6f}, max |diff| {max(abs(x) for x in dA):.4f} SOL")
print(f"   total real PnL {sum(r['real_pnl'] for r in res):+.3f} SOL vs exact replay {sum(r['A_pnl'] for r in res):+.3f} SOL (pump fees only, before their tips/bot fee)")
dB = [r["B_pnl"] - r["real_pnl"] for r in res]
print(f"B) place model from arrival ms: total model PnL {sum(r['B_pnl'] for r in res):+.3f} vs real {sum(r['real_pnl'] for r in res):+.3f}; per trade model-real median {statistics.median(dB):+.4f}, mean {statistics.mean(dB):+.4f}")
print(f"   position: model idx == real idx {sum(1 for r in res if r['idx'] == r['kpath']) / len(res):.0%}, model earlier {sum(1 for r in res if r['idx'] < r['kpath']) / len(res):.0%}, later {sum(1 for r in res if r['idx'] > r['kpath']) / len(res):.0%}")
for w in W:
    v = [r for r in res if r["w"] == w]
    if v: print(f"   {w}: n {len(v)} real {sum(r['real_pnl'] for r in v):+.3f}  exact {sum(r['A_pnl'] for r in v):+.3f}  model {sum(r['B_pnl'] for r in v):+.3f}")
json.dump(res, open("val_real.json", "w"), indent=0)
