# Full 24 h PnL incl. graduated tokens sold on PumpSwap / aggregators: every non-curve tx of the wallet is classified as
# TRADE (a non-SOL/USDC token balance of the wallet changed) or TRANSFER (deposit / withdrawal / payout). Value = native + WSOL + USDC.
import json, os, sys, urllib.request, time, collections, concurrent.futures as cf
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip(); PX = 101.7
WSOL = "So11111111111111111111111111111111111111112"; USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
def rpc(m, p):
    for i in range(5):
        try: return json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(), headers={"content-type":"application/json"}), timeout=60)).get("result")
        except Exception: time.sleep(1+i)
for u in sys.argv[1:]:
    fn = f"ledu_{u[:8]}.json" if os.path.exists(f"ledu_{u[:8]}.json") else f"ledw_{u[:8]}.json"
    R = json.load(open(fn)); curve = sum(r["nat"] + r["dws"] for r in R if r["ok"] and r["evs"]) / 1e9
    oth = [r for r in R if r["ok"] and not r["evs"] and abs(r["nat"] + r["dws"]) > 1e6]
    def cls(r):
        t = rpc("getTransaction", [r["sig"], {"encoding": "json", "maxSupportedTransactionVersion": 1}])
        if not t: return ("?", r["nat"] + r["dws"], None)
        own = lambda L: {(b["mint"]): int(b["uiTokenAmount"]["amount"]) for b in (L or []) if b.get("owner") == u}
        pre, post = own(t["meta"].get("preTokenBalances")), own(t["meta"].get("postTokenBalances"))
        tok = {m for m in set(pre) | set(post) if m not in (WSOL, USDC) and pre.get(m, 0) != post.get(m, 0)}
        return ("trade" if tok else "transfer", r["nat"] + r["dws"], next(iter(tok), None))
    with cf.ThreadPoolExecutor(12) as ex: C = list(ex.map(cls, oth))
    tr = sum(v for c, v, _ in C if c == "trade") / 1e9; tf = sum(v for c, v, _ in C if c == "transfer") / 1e9; unk = sum(v for c, v, _ in C if c == "?") / 1e9
    span = (max(r["bt"] for r in R) - min(r["bt"] for r in R)) / 86400
    print(f"{u} | {span*24:.1f} h | curve trades {curve:+.2f} + off-curve trades (PumpSwap/aggregators) {tr:+.2f} = ALL TRADING {curve+tr:+.2f} SOL ({(curve+tr)/span:+.1f}/day) | "
          f"deposits/withdrawals/payouts {tf:+.2f} | unread {unk:+.2f} | off-curve trade txs {sum(1 for c,_,_ in C if c=='trade')}")
