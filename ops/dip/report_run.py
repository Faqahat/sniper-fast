# READ-ONLY run report for a live dip run (the engine's --dip-log JSONL): per trade the dump, our buy (decision time,
# landing slot / position / ms after the dump, route, leader client), who bought ahead of us and after us (the tape:
# the 3 imitated wallets, the 462-wallet cohort, others), the exit, the sell, curve P&L and the CHAIN P&L (getTransaction
# balance changes of the wallet: spend, fees, tips, ATA rent all included), then leftover tokens and room for improvement.
# usage: python3 -I report_run.py <run.jsonl> <wallet> [cohort.json]       (RPC from ~/.config/sniper/ck_rpc_url; never printed)
import sys, os, json, time, urllib.request, datetime as dt
RUN, W = sys.argv[1], sys.argv[2]
COH = set(json.load(open(sys.argv[3] if len(sys.argv) > 3 else os.path.expanduser("~/sniper/ops/overnight/sel/cohort_train.json"))))
CK = open(os.path.expanduser(os.environ.get("RPC_URL_FILE", "~/.config/sniper/ck_rpc_url"))).read().strip()
TGT = {a: a[:8] for a in ["HkQ7hMjyoJeaAE1u9dbXMTkqrpXuZPpmtkc2g7QkNExQ", "DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw",
                          "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"]}       # src/dip_imit.rs TARGETS

def rpc(m, p, tries=5):
    for i in range(tries):
        try:
            req = urllib.request.Request(CK, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"})
            r = json.load(urllib.request.urlopen(req, timeout=30))
            if "error" in r: raise RuntimeError(str(r["error"])[:200])
            return r["result"]
        except Exception as e:
            last = e; time.sleep(0.5 * (i + 1))
    raise RuntimeError(f"rpc {m}: {last}")

def pkt(ns): return dt.datetime.fromtimestamp(ns / 1e9, dt.timezone(dt.timedelta(hours=5))).strftime("%H:%M:%S")
def who(u):
    if u == W: return "US"
    if u in TGT: return TGT[u]
    return (u[:6] + "*") if u in COH else u[:6]

def chain_delta(sig):
    """the wallet's SOL change in one tx (fee payer: includes fee + tips + rent) and the tx's fee / err / slot"""
    tx = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}])
    if not tx: return None
    keys = tx["transaction"]["message"]["accountKeys"] + (tx["meta"].get("loadedAddresses") or {}).get("writable", []) + (tx["meta"].get("loadedAddresses") or {}).get("readonly", [])
    i = keys.index(W) if W in keys else None
    d = (tx["meta"]["postBalances"][i] - tx["meta"]["preBalances"][i]) if i is not None else 0
    return {"delta": d, "fee": tx["meta"]["fee"], "err": tx["meta"]["err"], "slot": tx["slot"]}

ev = [json.loads(l) for l in open(RUN) if l.strip()]
start = next((e for e in ev if e["ev"] == "run_start"), {})
end = next((e for e in reversed(ev) if e["ev"] == "run_end"), None)
fires = [e for e in ev if e["ev"] == "fire"]
by = lambda kind, mint, after_t=0: [e for e in ev if e["ev"] == kind and e.get("mint") == mint and e.get("t", e.get("t_fire", 1)) >= after_t]
picks = [e for e in ev if e["ev"] == "pick"]; skips = [e for e in ev if e["ev"] == "pick_skip"]
sk = {}
for s in skips: sk[s["why"]] = sk.get(s["why"], 0) + 1
print(f"# Dip run {os.path.basename(RUN)} — wallet {W[:6]}, tier {start.get('tier')}, size {start.get('spend', 0) / 1e9:.3f} SOL, exit TP +{start.get('tp', 0) * 100:.0f}% / SL -{start.get('sl', 0) * 100:.0f}% / {start.get('hold_slots')} slots")
print(f"started {pkt(start['t']) if start else '?'} PKT{', ended ' + pkt(end['t']) + ' PKT' if end else ' (still running?)'}; picks {len(picks) + len(skips)} (skipped {sk if sk else 0}); fired {len(fires)}\n")

tot_chain, tot_curve, notes, n_win, n_loss = 0, 0, [], 0, 0
for n, f in enumerate(fires, 1):
    m = f["mint"]
    pk_ = next((p for p in picks if p["mint"] == m and p["sig"] == f["dump_sig"]), {})
    land = next((e for e in ev if e["ev"] == "buy_land" and e["mint"] == m and e.get("sig") == f["buy_sig"] or e["ev"] == "buy_land" and e["mint"] == m and e.get("t", 0) >= f["t_fire"]), None)
    close = next((e for e in ev if e["ev"] == "close" and e["mint"] == m and e.get("buy_sig") == f["buy_sig"]), None)
    exitv = next((e for e in ev if e["ev"] == "exit" and e["mint"] == m and e.get("t", 0) >= f["t_fire"]), None)
    poll = next((e for e in ev if e["ev"] == "land_poll" and e.get("sig") == f["buy_sig"]), None)
    feats = pk_.get("feats") or []
    print(f"## {n}. [{m[:6]}…](https://gmgn.ai/sol/token/{m}) — dump {feats[1] if feats else 0:.2f} SOL −{feats[2] if feats else 0:.0f}% at {pkt(f['t_dump_rx'])} PKT (score {pk_.get('score', 0):.3f}, token age {pk_.get('age', 0):.1f} s)")
    print(f"- buy: decided {f['decision_us']:.0f} µs after we saw the dump; route {f['route']} → leader {f['leader'][:8]} ({f['client']}); tips {f['tips'] / 1e9:.4f} SOL; deadline slot {f.get('deadline')}"
          f" | writes: " + ", ".join(f"{w['path']} {w['st']}" for w in f.get("writes", [])))
    if f.get("lat_us"): print("- decision breakdown µs: " + ", ".join(f"{k} {v:.0f}" for k, v in f["lat_us"].items()))
    if not land:
        why = (close or {}).get("result", "?"); err = (close or {}).get("err") or (poll or {}).get("err")
        e6042 = "6042" in json.dumps(err or "")
        print(f"- result: **{why}**{' (price guard: the price was already >2% above the post-dump price)' if e6042 else ''} {('err ' + json.dumps(err)) if err else ''} — [buy tx](https://solscan.io/tx/{f['buy_sig']})")
        bf = next((e for e in ev if e["ev"] == "buy_failed" and e.get("sig") == f["buy_sig"]), None); buys = []
        if bf:
            tape = [e for e in ev if e["ev"] == "tape" and e["mint"] == m and f["t_dump_rx"] <= e["t"] <= bf["t"] and e["user"] != W]
            buys = [e for e in tape if e["buy"]]
            print(f"- our failed buy executed {(bf['t'] - f['t_dump_rx']) / 1e6:.0f} ms after the dump (slot +{bf['slot'] - f['slot']}); ahead of us: {len(buys)} buys, "
                  f"{sum(e['sol'] for e in buys) / 1e9:.2f} SOL — " + ", ".join(f"{who(e['user'])} {e['sol'] / 1e9:.2f} @{(e['t'] - f['t_dump_rx']) / 1e6:.0f}ms" for e in buys[:8]))
        c = chain_delta(f["buy_sig"]) if why == "buy_failed" else None
        if c: tot_chain += c["delta"]; print(f"- chain: {c['delta'] / 1e9:+.6f} SOL (fee {c['fee'] / 1e9:.6f}), landed slot {c['slot']} (dump slot {f['slot']}, +{c['slot'] - f['slot']})")
        if c and e6042 and bf:
            notes.append(f"#{n} {m[:6]}: blocked by the 2% guard — we executed {(bf['t'] - f['t_dump_rx']) / 1e6:.0f} ms after the dump (slot +{c['slot'] - f['slot']}, "
                         f"{f['route']} on {f['client']}); {len(buys)} buyers ({sum(e['sol'] for e in buys) / 1e9:.2f} SOL) got in first")
        else:
            notes.append(f"#{n} {m[:6]}: buy {why} " + (f"(landed +{c['slot'] - f['slot']} slots after the dump; err {json.dumps(err)})" if c else "(no landing: route / leader)"))
        print(); continue
    print(f"- landed: slot +{land.get('slots_after_dump', '?')} after the dump, block position {land.get('idx')} (dump at {f.get('slot')}/{pk_.get('idx')}), "
          f"{land.get('rx_ms_after_dump', float('nan')):.0f} ms after the dump on our feed; got {land.get('tokens', 0):,} tokens for {land.get('sol', 0) / 1e9:.4f} SOL (curve)")
    # the tape: buys between the dump and our buy (ahead of us), and after our buy until our sell (behind us)
    tape = sorted([e for e in ev if e["ev"] == "tape" and e["mint"] == m and e["t"] >= f["t_fire"] - 1], key=lambda e: (e["slot"], e["idx"], e["j"]))
    us_b = (land["slot"], land.get("idx", 0)); sell = next((e for e in ev if e["ev"] == "sell_land" and e["mint"] == m and e.get("t", 0) >= land.get("t", 0)), None)
    us_s = (sell["slot"], sell["idx"]) if sell else (1 << 62, 0)
    ahead = [e for e in tape if (e["slot"], e["idx"]) < us_b and e["user"] != W and (e["slot"], e["idx"]) > (f["slot"], pk_.get("idx", -1))]
    behind = [e for e in tape if us_b < (e["slot"], e["idx"]) < us_s and e["user"] != W]
    fmt = lambda L: ", ".join(f"{who(e['user'])} {'buy' if e['buy'] else 'sell'} {e['sol'] / 1e9:.2f}" for e in L[:10]) + (" …" if len(L) > 10 else "")
    print(f"- ahead of us (after the dump): {sum(e['buy'] for e in ahead)} buys / {sum(not e['buy'] for e in ahead)} sells — {fmt(ahead) or 'none'}")
    print(f"- behind us (before our sell): {sum(e['buy'] for e in behind)} buys / {sum(not e['buy'] for e in behind)} sells — {fmt(behind) or 'none'}")
    if exitv: print(f"- exit: {exitv['why']} after {exitv.get('slots_held')} slots" + (f" at value x{exitv['value']:.3f}" if exitv.get("value") else ""))
    if sell: print(f"- sold: slot +{sell['slot'] - land['slot']} after our buy, {sell['sol'] / 1e9:.4f} SOL out (curve)")
    sells_raw = (close or {}).get("sell_sigs") or []                  # [[sig, landed, tip lamports], ...]
    sells = [x[0] if isinstance(x, list) else x for x in sells_raw]
    sell_tips = sum(x[2] for x in sells_raw if isinstance(x, list) and len(x) > 2 and isinstance(x[2], int))
    cb = chain_delta(f["buy_sig"]); cs = [chain_delta(s) for s in sells]; cs = [c for c in cs if c]
    ch = (cb["delta"] if cb else 0) + sum(c["delta"] for c in cs)
    cur = (close or {}).get("curve_pnl")
    tot_chain += ch; tot_curve += cur or 0
    if close and close.get("result") == "sold": n_win += ch > 0; n_loss += ch <= 0
    print(f"- P&L: curve {(cur or 0) / 1e9:+.6f} SOL | **chain {ch / 1e9:+.6f} SOL** (buy tx {cb['delta'] / 1e9 if cb else 0:+.6f}, sell tx(s) {sum(c['delta'] for c in cs) / 1e9:+.6f}; tx fees {((cb or {}).get('fee', 0) + sum(c['fee'] for c in cs)) / 1e9:.6f}, tips buy {f['tips'] / 1e9:.4f} + sell {sell_tips / 1e9:.4f}) — result {(close or {}).get('result', 'OPEN?')}")
    print(f"- links: [buy](https://solscan.io/tx/{f['buy_sig']})" + "".join(f" · [sell {i + 1}](https://solscan.io/tx/{s})" for i, s in enumerate(sells)) + f" · [dump](https://solscan.io/tx/{f['dump_sig']})")
    if land.get("slots_after_dump", 0) >= 1: notes.append(f"#{n} {m[:6]}: landed {land['slots_after_dump']} slot(s) after the dump ({land.get('rx_ms_after_dump', 0):.0f} ms) via {f['route']} on {f['client']}")
    if sum(e["buy"] for e in ahead) >= 2: notes.append(f"#{n} {m[:6]}: {sum(e['buy'] for e in ahead)} buyers got in ahead of us ({fmt([e for e in ahead if e['buy']])})")
    if close and close.get("result") != "sold": notes.append(f"#{n} {m[:6]}: position {close.get('result')} — CHECK THE WALLET")
    print()

print(f"**Run total: chain {tot_chain / 1e9:+.6f} SOL** (curve {tot_curve / 1e9:+.6f}); sold trades {n_win} up / {n_loss} down")
# leftover tokens of the traded mints (an unsold position would show here)
try:
    r = rpc("getTokenAccountsByOwner", [W, {"programId": "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"}, {"encoding": "jsonParsed", "commitment": "confirmed"}])
    left = [(a["account"]["data"]["parsed"]["info"]["mint"], a["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"]) for a in r["value"]]
    left = [(mm, x) for mm, x in left if mm in {f["mint"] for f in fires} and x]
    print("leftover tokens: " + (", ".join(f"{mm[:6]} {x}" for mm, x in left) if left else "none (every traded token sold, accounts closed)"))
except Exception as e:
    print(f"leftover tokens: check failed ({e})")
print("\nRoom for improvement:")
for x in list(dict.fromkeys(notes)) or ["nothing flagged by the automatic checks"]: print(f"- {x}")
