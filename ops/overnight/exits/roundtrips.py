#!/usr/bin/env python3
# READ-ONLY, offline. Per-token round trips of an AKbot wallet on SOL-quoted pump.fun tokens (bonding curve):
# every buy and sell leg with slot / time / size / fraction of position / price multiple vs entry / SOL in-out, and the
# per-token PnL after every cost (curve + 1.25% pump fees + priority + tips + AKbot 0.99% sell fee in the sell tx +
# AKbot 1% buy fee billed later in a separate transfer, attributed here as 1% of the buy's curve SOL).
# usage: python3 -I roundtrips.py 9Sh2fd|DGmspi   -> roundtrips_<w>.json
import sys, os, json, collections, statistics, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

w = sys.argv[1]; W = WALLETS[w]
D = json.load(open(f"{LEDGER}/ledger_{w}.json"))
MAIN_END = max(x["slot"] for x in D["txs"] if x.get("slot"))          # end of the saved full ledger (10-22 ~20:15 UTC)
RECENT = f"{EXITS}/cache/ledger_{w}_recent.json"                       # extension fetched by fetch_recent.py (after the ledger end)
if os.path.exists(RECENT):
    known = {x["sig"] for x in D["txs"]}
    D["txs"] += [x for x in json.load(open(RECENT))["txs"] if x["sig"] not in known]
MISSING = f"{EXITS}/cache/ledger_{w}_missing.json"                     # txs the saved ledger marked missing, re-fetched
if os.path.exists(MISSING):
    D["txs"] += json.load(open(MISSING))["txs"]
CACHES = [f"{LEDGER}/txc_{w}", f"{EXITS}/cache/txc_{w}"]
def raw_tx(sig):
    for c in CACHES:
        p = os.path.join(c, sig + ".json")
        if os.path.exists(p):
            try: return json.load(open(p))
            except Exception: return None
    return None

txs = sorted([x for x in D["txs"] if not x.get("missing")], key=lambda x: x["slot"])
ok = [x for x in txs if not x.get("err")]

# ---- SOL-quoted pump.fun mints: at least one buy TradeEvent with SOL > 0 and no zero-SOL (other-quote) events
ev = collections.defaultdict(collections.Counter)
for x in ok:
    for t in x["trades"]: ev[t["mint"]][("b" if t["buy"] else "s") + ("0" if t["sol"] == 0 else "+")] += 1
SOLQ = {m for m, c in ev.items() if c["b+"] > 0 and c["b0"] == 0 and c["s0"] == 0}

# ---- creators: raw events (9Sh2fd), create-tx caches, collector launches
creator = {}
legs = collections.defaultdict(list); n_raw = n_rec = 0; rec_err = []
for x in ok:
    ms = {t["mint"] for t in x["trades"]} | {m for m, d in x["tok"].items() if m != WSOL and not m.startswith(STABLE_PREFIX) and abs(d) > 0}
    mine = [m for m in ms if m in SOLQ]
    if not mine: continue
    rt = raw_tx(x["sig"]); evs = [e for e in decode_events(rt) if e["user"] == W] if rt else None
    if rt:
        for e in decode_events(rt): creator.setdefault(e["mint"], e["creator"])
    tips = sum(l for s, d, l in x["xfers"] if s == W and d and (d.startswith(("LandX", "AsTRAE", "astra", "ste11", "AStrAJ", "Astran", "D2L6yP", "DiTmWE", "CPJpjL", "AbKhzZ", "FqK544", "A9TT5P"))))
    ak = sum(l for s, d, l in x["xfers"] if s == W and d == AKBOT_FEE)
    for m in mine:
        tl = [t for t in x["trades"] if t["mint"] == m]
        if not tl:   # token moved without a trade of this wallet (transfer in/out, burn)
            legs[m].append(dict(kind="xfer", sig=x["sig"], slot=x["slot"], bt=x["bt"], tok=x["tok"].get(m, 0) * 1e6, net=x["sol_chg"] / len(ms))); continue
        e_m = [e for e in evs if e["mint"] == m] if evs is not None else None
        for k, t in enumerate(tl):
            sol = round(t["sol"] * 1e9)
            if e_m is not None and k < len(e_m):
                e = e_m[k]; tok = e["tok"]; pre = pre_state(e["buy"], e["sol"], e["tok"], e["vsol"], e["vtok"]); src = "raw"; n_raw += 1
                chk = pre_state(e["buy"], e["sol"], e["tok"])
                if chk: rec_err.append(abs(chk[0] / pre[0] - 1))
            else:
                tok = abs(x["tok"].get(m, 0)) * 1e6 / len(tl); pre = pre_state(t["buy"], sol, tok); src = "rebuilt"; n_rec += 1
            post = post_state(t["buy"], sol, tok, pre) if pre else None
            legs[m].append(dict(kind="buy" if t["buy"] else "sell", sig=x["sig"], slot=x["slot"], bt=x["bt"], sol=sol, tok=tok,
                                pre=pre, post=post, src=src, net=x["sol_chg"] / len(ms) / len(tl), fee=x["fee"] / len(ms) / len(tl),
                                tip=tips / len(ms) / len(tl), ak=ak / len(ms) / len(tl)))

def order_key(l):
    # same-slot order: buys before sells, sells by falling curve SOL (each own sell lowers it)
    return (l["slot"], 0 if l["kind"] == "buy" else 1, -(l["pre"][0] if l.get("pre") else 0))

hold_now = {m: a for m, a in D.get("holdings_now", [])}
OUT = []
for m in sorted(legs, key=lambda m: min(l["slot"] for l in legs[m])):
    L = sorted(legs[m], key=order_key)
    buys = [l for l in L if l["kind"] == "buy"]
    if not buys: continue
    b0 = buys[0]; pos = 0.0; cost_sol = 0.0; cost_tok = 0.0; seq = []; peak_seen = None
    for l in L:
        if l["kind"] == "buy":
            pos += l["tok"]; cost_sol += l["sol"]; cost_tok += l["tok"]
            seq.append(dict(side="buy", sig=l["sig"], slot=l["slot"], bt=l["bt"], dslot=l["slot"] - b0["slot"], dt=(l["bt"] or 0) - (b0["bt"] or 0),
                            sol=l["sol"] / 1e9, tok=l["tok"] / 1e6, px=l["sol"] / l["tok"], px_pre=l["pre"][0] / l["pre"][1] if l["pre"] else None,
                            px_post=l["post"][0] / l["post"][1] if l["post"] else None, mc_pre=mc_sol(*l["pre"]) if l["pre"] else None,
                            net=l["net"], fee=l["fee"], tip=l["tip"], src=l["src"]))
        elif l["kind"] == "sell":
            held = pos; pos -= l["tok"]
            entry = cost_sol / cost_tok if cost_tok else None
            px_pre = l["pre"][0] / l["pre"][1] if l["pre"] else None
            seq.append(dict(side="sell", sig=l["sig"], slot=l["slot"], bt=l["bt"], dslot=l["slot"] - b0["slot"], dt=(l["bt"] or 0) - (b0["bt"] or 0),
                            sol=l["sol"] / 1e9, tok=l["tok"] / 1e6, frac=l["tok"] / held if held > 0 else None, px=l["sol"] / l["tok"] if l["tok"] else None,
                            px_pre=px_pre, mult_pre=px_pre / entry if (px_pre and entry) else None,
                            mult_exec=(l["sol"] / l["tok"]) / entry if (entry and l["tok"]) else None,
                            mc_pre=mc_sol(*l["pre"]) if l["pre"] else None, net=l["net"], fee=l["fee"], tip=l["tip"], ak=l["ak"], src=l["src"]))
        else:
            pos += l["tok"]
            seq.append(dict(side="xfer", sig=l["sig"], slot=l["slot"], bt=l["bt"], dslot=l["slot"] - b0["slot"], tok=l["tok"] / 1e6, net=l["net"]))
    sells = [s for s in seq if s["side"] == "sell"]
    buy_sol = sum(s["sol"] for s in seq if s["side"] == "buy")
    ak_buy = 0.01 * buy_sol                                           # billed later as a standalone transfer
    net = sum(s["net"] for s in seq) - ak_buy
    gross_curve = sum(s["sol"] for s in sells) - buy_sol
    cost = -sum(s["net"] for s in seq if s["side"] == "buy") + ak_buy
    t_last = sells[-1] if sells else None
    open_tok = hold_now.get(m, 0) if pos / 1e6 > 1 else 0
    OUT.append(dict(mint=m, period="ledger" if b0["slot"] <= MAIN_END else "recent", creator=creator.get(m), n_buys=len(buys), n_sells=len(sells), buy_slot=b0["slot"], buy_bt=b0["bt"], buy_sol=buy_sol,
                    cost=cost, entry_px=(sum(l["sol"] for l in buys) / sum(l["tok"] for l in buys)), entry_mc=(seq[0]["mc_pre"]),
                    hold_slots=(t_last["slot"] - b0["slot"]) if t_last else None, hold_s=((t_last["bt"] or 0) - (b0["bt"] or 0)) if t_last else None,
                    left_tok=pos / 1e6, open=pos / 1e6 > 1, open_now=open_tok, pnl=net, gross_curve=gross_curve, ak_buy=ak_buy,
                    max_mult_sold=max([s["mult_pre"] or 0 for s in sells], default=None), legs=seq))

json.dump(dict(wallet=W, n_tokens=len(OUT), raw_legs=n_raw, rebuilt_legs=n_rec, rebuild_err_max=max(rec_err) if rec_err else None, tokens=OUT),
          open(f"{EXITS}/roundtrips_{w}.json", "w"), indent=0)
for per in ("ledger", "recent"):
    R = [r for r in OUT if r["n_sells"] and r["period"] == per]
    if R: print(f"   {per}: {len(R)} tokens, PnL {sum(r['pnl'] for r in R):+.3f} SOL, win {sum(r['pnl'] > 0 for r in R) / len(R):.0%}, open {sum(r['open'] for r in R)}")
R = [r for r in OUT if r["n_sells"]]
print(f"{w}: {len(OUT)} SOL-quoted pump tokens ({len(R)} with sells, {sum(r['open'] for r in OUT)} with >1 token left); legs raw {n_raw}, rebuilt {n_rec}; "
      f"rebuild check max rel err {max(rec_err) if rec_err else float('nan'):.2e}")
print(f"   PnL total {sum(r['pnl'] for r in OUT):+.3f} SOL (curve gross {sum(r['gross_curve'] for r in OUT):+.3f}); win {sum(r['pnl'] > 0 for r in R) / len(R):.0%}; "
      f"median {statistics.median(r['pnl'] for r in R):+.4f}")
