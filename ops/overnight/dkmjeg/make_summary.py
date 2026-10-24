#!/usr/bin/env python3
# READ-ONLY, offline: summary.json for the HTML page (TL;DR, stat tiles, extra sections) from the analysis outputs.
import json, os, datetime
HERE = "/home/moiz/sniper/ops/overnight/dkmjeg"
F = json.load(open(f"{HERE}/final.json")); RS = json.load(open(f"{HERE}/rescore.json"))
PKT = datetime.timezone(datetime.timedelta(hours=5))
w0 = datetime.datetime.fromisoformat(F["window"]["first"]).astimezone(PKT).strftime("%b %d %H:%M"); w1 = datetime.datetime.fromisoformat(F["window"]["last"]).astimezone(PKT).strftime("%b %d %H:%M")
def a(addr, label=None, gm=False): return f'<a href="https://{"gmgn.ai/sol/address" if gm else "solscan.io/account"}/{addr}" target="_blank" rel="noopener">{label or addr[:6] + "…" + addr[-4:]}</a>'
ven = F["venue"]; sq = ven.get("pump SOL-quoted", {})
nb = F["tokens"]["n"]; pnl = F["pnl_total"]; wd = F["withdrawals"]
tl = [
    f'It is a <b>custom, self-built bot</b>, not a commercial one: buys go through its own on-chain router {a("ENFJAVp6hQWbzCbdRm69pUnuAmLgKPy18DiNg8fEDve8", "ENFJAV…Dve8")}, whose upgrade authority is the wallet itself; no other wallet used it in its last 1,000 calls. <span class="badge m">measured</span>',
    'Each buy is signed in <b>~20 copies, one per landing service</b> (Jito, Helius, Nozomi, SpeedLanding, Bolt, Astralane, Flashblock, 0slot, bloXroute, NextBlock, …). Every copy carries its own tip and a service tag in the last digits of the buy amount (Jito …042, Helius …108, …). All copies share one durable nonce, so exactly one executes. <span class="badge m">measured</span> (copies that did not land are invisible on chain)',
    f'The copy that lands most often is the <b>Jito one</b> (about a third of fills; no priority fee, tip ≈ 3% of the buy, <span class="mono">jitodontfront</span>). On average, landing costs it <b>≈ 2.4% of every buy</b> (102 SOL in 61 h), more than 9Sh2fd\'s ~2% LandX tip. <span class="badge m">measured</span>',
    f'Ground truth over {F["window"]["hours"]:.0f} h ({w0} → {w1} PKT): <b>{pnl:+.1f} SOL after every cost</b> on {nb} tokens. It is not a thin tail: without its best 10 tokens it is still {F["tokens"]["ex_top10"]:+.1f} SOL. The money is in its 3.6–8 SOL buys and in tokens it sells in 6+ pieces. It cashes out in 5-SOL chunks swapped to USDC and sent to {a("HunS7Ek5kTnRNc6QYB76PeLw5zQ3X26sCyHTYV91HFLn", "HunS7E…HFLn")} ({wd["n"]} times, {wd["usdc"]:,.0f} USDC). <span class="badge m">measured</span>',
    'Exits are <b>time-driven, not price-driven</b>: first sell a median 1.7 s after the buy (half; all of it when follow-on buying is weak; 30% within ~0.4 s on 5–8 SOL buys), then pieces at ~4, ~6, ~9 and ~12 s; median hold 4.7 s. A new high or a drop below entry does not change its sell rate; a dev/bundle sell raises it about 1.9×. <span class="badge i">inferred from measured timing</span>',
    'For us: every copy idea (its picks, its deployer list, a model of its picks) is profitable in replay <b>only because fast snipers, dKMjeG among them, buy after us</b>. Without those buys every variant is negative. <b>Rejected</b> under the owner\'s rule. <span class="badge m">measured</span>',
]
stats = [("first outside buyer (R1+R2)", "65%"), ("its buys in the create block", "66%"), ("arrival in our feed (median)", "42 ms"),
         ("landing copies per buy", "~20"), ("PnL after all costs", f"{pnl:+.1f} SOL"), ("without best 10 tokens", f'{F["tokens"]["ex_top10"]:+.1f} SOL')]
oa = RS.get("(a) oracle: its attempted launches L75", {}); lb = RS.get("(b) walk-forward deployer list L75", {})
sec = [f'''<h2>Can we use it? <span class="badge m">measured</span></h2><div class="card small"><p>Replay at our mechanics (0.5 SOL, land 75 ms after the create, 1% price guard, sell at the end of the next slot), R2 launches with our engine's timeline. Then the same with the buys of the 374 fast sniper wallets after our entry removed (fast = ≥ 5 launches bought within 2 slots of the create and ≥ 50% of their launches).</p>
<div class="tbl"><table><tr><th class="l">Idea</th><th>Fills</th><th>Replay SOL</th><th>+ slip limits</th><th>Without fast snipers</th><th>Without top-10 after-us buyers</th><th>No outside buy before our sell</th></tr>
<tr><td class="l">Its attempted launches (oracle)</td><td>{oa.get("fills")}/{oa.get("n")}</td><td>{oa.get("base", [0])[0]:+.2f}</td><td>{oa.get("slip", [0])[0]:+.2f}</td><td>{oa.get("noFAST", [0])[0]:+.2f}</td><td>{oa.get("noTOP10", [0])[0]:+.2f}</td><td>{oa.get("no_out_buy", 0):.0%}</td></tr>
<tr><td class="l">Walk-forward deployer list from its attempts</td><td>{lb.get("fills")}/{lb.get("n")}</td><td>{lb.get("base", [0])[0]:+.2f}</td><td>{lb.get("slip", [0])[0]:+.2f}</td><td>{lb.get("noFAST", [0])[0]:+.2f}</td><td>{lb.get("noTOP10", [0])[0]:+.2f}</td><td>{lb.get("no_out_buy", 0):.0%}</td></tr></table></div>
<p>Verdict: <b>rejected</b>. The replay profit depends on fast snipers (dKMjeG itself and others) buying after us; it does not come from generic flow.</p></div>''']
json.dump(dict(n_bought=nb, window=f"{w0} → {w1} PKT", tldr_html=tl, stats=stats, sections_html=sec), open(f"{HERE}/summary.json", "w"), indent=1)
print("summary.json written")
