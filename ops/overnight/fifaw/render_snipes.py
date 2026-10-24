#!/usr/bin/env python3
# READ-ONLY, offline: FiFawH_snipes.html = its last 15 collected snipes (every tx / wallet / token linked) + key facts.
import json, gzip, sys, datetime, html, re, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core"); import rp
W = "FiFawHqxeTVBhv6YbqbLwDVuvokRpPUM1bNwAyxhGc6W"; PKT = datetime.timezone(datetime.timedelta(hours=5))
T = json.load(open("truth_FiFawH.json")); LED = {x["sig"]: x for x in json.load(open("ledger_FiFawH.json"))}
P = {r["mint"]: r for r in json.load(open("q25_pnl_exits.json"))["positions"]}
Q = json.load(open("q25_pnl_exits.json")); INF = json.load(open("q1_infra.json"))
Q["net"] = sum(x["val"] for x in T["txs"])          # all 1,519 txs (incl. 1 failed tx without block time)
L = rp.load_launches(); ROWS = json.load(open("fifaw_rows.json"))
SEL = {}
for l in gzip.open("selection/sel_dataset.jsonl.gz", "rt"):
    r = json.loads(l)
    if r["att"]: SEL[r["mint"]] = r
BAD = re.compile(r"(fuck|shit|nigg|cunt|fag|rape|porn|dick|cock|puss|bitch|slut|whore|nazi|hitler|retard|kike|spic|chink|nsfw|cum|sex|tit|anal|ass\b)", re.I)
def mask(s): return "[masked]" if s and BAD.search(s) else (s or "")
def short(a, n=6): return f"{a[:n]}…{a[-4:]}"
def tx(sig, label): return f'<a href="https://solscan.io/tx/{sig}" target="_blank" rel="noopener">{label}</a>'
def acct(a, label=None, gm=False):
    lab = label or short(a); mk = mask(a[:8])
    if mk == "[masked]": lab = "[masked]"
    u = f"https://gmgn.ai/sol/address/{a}" if gm else f"https://solscan.io/account/{a}"
    return f'<a href="{u}" target="_blank" rel="noopener">{html.escape(lab)}</a>'
def tok(m, label): return f'<a href="https://gmgn.ai/sol/token/{m}" target="_blank" rel="noopener">{html.escape(label)}</a>'
buys = {}
for x in T["txs"]:
    if x["cat"] == "buy":
        for m in x["pos"]: buys.setdefault(m, x)
cand = [m for m in P if m in L and m in buys and P[m]["sells"]]
cand.sort(key=lambda m: P[m]["buy_bt"]); last = cand[-15:]
rows = []
for m in reversed(last):
    p = P[m]; c = L[m]; b = buys[m]; lb = LED[b["sig"]]
    tip = [(t[0], t[1] / 1e9) for t in lb["tips"]] + [("AsTz (private)", l / 1e9) for d, l in lb["xout"] if d.startswith("AsTzjKRA")]
    prio = (lb["fee"] - 5000) / 1e9
    me = [r for r in ROWS.get(m, []) if r[1] == "T" and r[15] == W and r[16] == 1 and r[13] == 0]
    pos_in_block = (me[0][4] - (c.get("idx") or 0)) if me and me[0][3] == c["slot"] else None
    sel = SEL.get(m, {}); meinfo = sel.get("me") or {}
    ev = [e for e in lb["ev"] if e["buy"]]; size = ev[0]["sol"] / 1e9 if ev and 20e9 < ev[0]["vsol"] < 200e9 else None
    usd = -sum(d for k, d in lb["tok"].items() if k.startswith("EPjFWdd5")) if size is None else None
    nm = mask(c.get("name", "").strip()) or "?"; sym = mask(c.get("symbol", "").strip())
    rows.append(dict(m=m, name=nm, sym=sym, c=c, b=b, p=p, tip=tip, prio=prio, slot_off=b["slot"] - c["slot"], pib=pos_in_block, ahead=meinfo.get("n_before"),
                     size=size, usd=usd, dev=sel.get("dev_buy"), glued=sel.get("glued_n"), dep_prior=sel.get("dep_prior"), dep_prior_att=sel.get("dep_prior_att")))
tot = sum(r["p"]["pnl"] for r in rows)
css = open("/home/moiz/sniper/ops/snipers/w9sh/9Sh2fd_snipes.html").read().split("<style>")[1].split("</style>")[0]
o = []
A = o.append
A(f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>FiFawH Sniper Study</title><style>{css}</style></head><body><div class='wrap'>")
A("<h1>How wallet FiFawH snipes pump.fun launches</h1>")
A('<p class="mut">Its last 15 snipes on launches our collector recorded, from on-chain data only (read-only). Every transaction, wallet and token links to Solscan or GMGN. Times are PKT (UTC+5).</p>')
A(f'<div class="chips"><span class="chip">Wallet {acct(W, short(W, 8), gm=True)}</span><span class="chip">Custom bot (own on-chain programs)</span><span class="chip">Durable nonce + multi-relay fan-out</span><span class="chip">Window {Q["window_pkt"][0][5:]} → {Q["window_pkt"][1][5:]} PKT</span></div>')
co = Q["costs"]
A('<div class="card tldr"><b>In short</b><ul>')
A(f'<li><b>Profitable after all costs:</b> {Q["net"]:+.1f} SOL in {(T["window"][1]-T["window"][0])/3600:.0f} h ({Q["net"]/((T["window"][1]-T["window"][0])/86400):+.1f} SOL/day) <span class="badge m">measured</span>. Gross trading {Q["gross"]:+.1f} SOL; it spends {Q["gross"]-Q["net"]:.1f} SOL on tips, priority fees and failed buys.</li>')
A('<li><b>It picks launches that keep attracting ordinary buyers.</b> With its own trades removed, its picks are at a median 1.14× the post-bundle price after 5 s; all other launches are at 1.00× <span class="badge m">measured</span>.</li>')
A('<li><b>It is the first outside buyer</b> in 123 of 127 of its landed snipes: 96 in the create block, 29 in the next one. Every buy uses a durable nonce, and its landed buys tip 9 different landing services. This suggests it sends each buy through several services at once <span class="badge i">inferred</span>.</li>')
A('<li><b>It sells into strength.</b> 332 of 429 positions are dumped in one sell at about 3 s, and these lose money as a group. The 97 positions that rose were laddered (49% first, the rest later) and made all of the profit.</li>')
A('<li><b>We can only catch this edge by being in the first slot.</b> Copying its picks 0.6–5 s later loses money, about −2 to −5% per trade. Its picks cannot be predicted from create-time data: the best rule we found is right only 3–6% of the time.</li></ul></div>')
A('<div class="grid">')
for v, lab in ((f'{Q["net"]:+.1f}', "SOL net, 61 h"), (f"{len(P)}", "positions"), ("61 ms", "median landing after create (our feed)"), (f'{co["buy_tips"]:.1f}', "SOL tips on landed buys"),
               (f'{co["failed_buy_fees"]:.1f}', "SOL fees on 402 failed buys"), (f'{co["cb_only_fee_burn"]+co["noop_guard_total"]:.1f}', "SOL lost on odd txs (fee-only, guard no-ops)")):
    A(f'<div class="stat"><b>{v}</b><span>{lab}</span></div>')
A('</div>')
# anatomy of one buy
ex = rows[0]; lb = LED[ex["b"]["sig"]]
A(f'<h2>Anatomy of one snipe: {html.escape(ex["name"])} <span class="badge m">measured</span></h2>')
c = ex["c"]
A(f'<p>Token {tok(ex["m"], ex["name"])} ({acct(ex["m"], short(ex["m"]))}), created {datetime.datetime.fromtimestamp(c["bt"], PKT):%b %d, %H:%M:%S} PKT in block {c["slot"]} by {acct(c["user"], short(c["user"]), gm=True)} ({tx(c["sig"], "create tx")}).</p>')
A('<ol class="steps">')
A(f'<li><b>Its buy lands {ex["slot_off"]} block(s) after the create</b>' + (f', {ex["pib"]} transactions after the create tx' if ex["pib"] is not None else "") + f' ({tx(ex["b"]["sig"], "buy tx")}).</li>')
tips_s = ", ".join(f"{s} {a:.4f} SOL" for s, a in ex["tip"]) or "none, priority fee only"
A(f'<li><b>It paid</b> a {ex["prio"]:.4f} SOL priority fee and a tip of {tips_s}.</li>')
sl = ex["p"]["sells"]
A(f'<li><b>It sold in {len(sl)} piece(s)</b>: ' + ", ".join(tx(s["sig"], f'{s["ds"]} s, {100*(s["frac"] or 0):.0f}%') for s in sl[:8]) + (" …" if len(sl) > 8 else "") + f'. Result for this snipe: <span class="{"pos" if ex["p"]["pnl"] > 0 else "neg"}">{ex["p"]["pnl"]:+.3f}</span> SOL (after fees and tips).</li></ol>')
A('<h3>Its buy transaction, instruction by instruction</h3><div class="card">')
ixs = [("1", "<b>Advance durable nonce</b> (nonce account " + acct("4kT5gqyZkLqkFV3J5yRwqF3qCxmvExTtZiyf4saT3Cah") + "). No fresh blockhash is needed. <i>Inferred:</i> each copy of a buy carries a different marker account (next row), so each copy has its own signature, and only one copy can land because the nonce advances."),
       ("2–4", "<b>Compute budget</b>: CU price, CU limit (≈51–64k), and a loaded-accounts-data limit. The CU-limit instruction carries a dummy read-only marker account; it used 37 different ones. Tip size and priority fee grow with buy size."),
       ("5", "<b>Token account via createAccountWithSeed</b>. The seed is the first 8 characters of the nonce blockhash. initializeAccount3 follows. No ATA program."),
       ("6", "<b>The buy</b>: either a direct pump.fun <span class='mono'>BuyExactQuoteInV3</span> (spend X SOL, minimum tokens out ≈2% under quote), or its own guard program " + acct("B78FW9mVQT2fDhsW7ChvqTBhZzhCbRrtWYC6K5oa7xuv", "B78FW9…") + " / " + acct("9f2uHxWdaB5nRgjRgsUe4T1LtyzejLNnxuzLfvyMyyxP", "9f2uHx…") + ". For USDC- or other-quoted curves it uses " + acct("9uGqm7Xh7Vq2EzqTNHVG5Ca4echELK1UjDq9W9Qg5kzF", "9uGqm7…") + ", which swaps USDC on Meteora/Orca first."),
       ("7", "<b>Tip transfer</b> to one landing service per copy: Jito, Helius, Nozomi, LandX, Stellium, Falcon, BlockRazor, bloXroute, or the unlisted account " + acct("AsTzjKRAZ91h6VpiR7Za5EWP8MPYRhfnRxAG4CUXL3oT", "AsTzjK…") + ". One copy has no tip and a high priority fee.")]
for n, t in ixs: A(f'<div class="ix"><span class="n">#{n}</span><div>{t}</div></div>')
A(f'<p class="small mut">v0 transaction, 1 signer, {lb["cu"]:,} compute units used. Sells skip the nonce: they use a recent blockhash, a Jito 0.0003 + Helius 0.0016 SOL tip pair and a 0.0035 SOL priority fee. A sell is one call to its own program {acct("2kAA3Bm3npaBzrevWXJfojagG1BEAac4KwayWphYMYQG", "2kAA3B…")} ("sell N%", minimum out 0), then a close of the token account. FiFawH is that program\'s upgrade authority.</p></div>')
A('<h2>The 15 snipes <span class="badge m">measured</span></h2>')
A('<p class="mut small">Block = blocks after the create. Pos = transactions between the create tx and its buy in the create block. Ahead = outside buyers before it. Result = SOL change over the buy and all sells, after fees and tips. Other-quoted buys are shown in USDC.</p>')
A('<div class="tbl"><table><tr><th class="l">Created (PKT)</th><th class="l">Token</th><th class="l">Deployer</th><th>Dev buy</th><th>Block</th><th>Pos</th><th>Ahead</th><th>Buy</th><th class="l">Landed via (tip)</th><th>Sells</th><th>Hold</th><th>Result</th><th class="l">Txs</th></tr>')
for r in rows:
    c = r["c"]; p = r["p"]; sl = p["sells"]
    land = ", ".join(f"{s} {a:.3f}" for s, a in r["tip"]) or f"priority only {r['prio']:.3f}"
    buy = f"{r['size']:.2f} SOL" if r["size"] else (f"{r['usd']:.0f} USDC" if r["usd"] else "?")
    txs = " ".join([tx(c["sig"], "create"), tx(r["b"]["sig"], "buy")] + [tx(s["sig"], f"s{i+1}") for i, s in enumerate(sl[:4])]) + (" …" if len(sl) > 4 else "")
    A(f'<tr><td class="l">{datetime.datetime.fromtimestamp(c["bt"], PKT):%m-%d %H:%M:%S}</td><td class="l">{tok(r["m"], (r["name"][:18] + (" (" + r["sym"][:10] + ")" if r["sym"] else "")))}</td>'
      f'<td class="l">{acct(c["user"], short(c["user"], 5), gm=True)}</td><td>{(f"{r[chr(100)+chr(101)+chr(118)]:.2f}" if r["dev"] is not None else "–")}</td><td>{r["slot_off"]}</td><td>{r["pib"] if r["pib"] is not None else "–"}</td>'
      f'<td>{r["ahead"] if r["ahead"] is not None else "–"}</td><td>{buy}</td><td class="l">{land}</td><td>{len(sl)}</td><td>{sl[-1]["ds"] if sl else "–"} s</td>'
      f'<td class="{"pos" if p["pnl"] > 0 else "neg"}">{p["pnl"]:+.3f}</td><td class="l">{txs}</td></tr>')
A(f'</table></div><p class="small mut">These 15 snipes total {tot:+.3f} SOL.</p>')
A('<h2>What it costs, and where its money comes from <span class="badge m">measured</span></h2><div class="card">')
A(f'<p>Window {Q["window_pkt"][0]} → {Q["window_pkt"][1]} PKT. Gross trading {Q["gross"]:+.2f} SOL. Costs: buy tips {co["buy_tips"]:.2f}, failed-buy fees {co["failed_buy_fees"]:.2f}, priority-fee-only txs {co["cb_only_fee_burn"]:.2f}, guard no-op buys that still paid tips {co["noop_guard_total"]:.2f}, buy fees {co["buy_fees"]:.2f}, sell fees {co["sell_fees"]:.2f}, sell tips {co["sell_tips"]:.2f}. <b>Net {Q["net"]:+.2f} SOL.</b></p>')
A('<p>By number of sells: positions with 1 sell (332) −19.9 SOL · 2 sells (75) +33.3 · 3 sells (9) +12.2 · 4+ sells (13) +30.2. Its 16 biggest buys (≥4.5 SOL, with a 5-minute 15%-steps ladder) made +24.0 SOL.</p></div>')
A('<h2>Method and references</h2><div class="card small">')
A('<p><b>Data.</b> Every transaction it signed in the owner-RPC window (1,519), parsed from the chain. Launches, block positions and the price paths of other traders come from our collector (two runs, 10-22 03:07 → 10-23 05:37 PKT).</p>')
A('<p><b>Accounts.</b> Wallet ' + acct(W) + ' · nonce ' + acct("4kT5gqyZkLqkFV3J5yRwqF3qCxmvExTtZiyf4saT3Cah") + ' · upgrade authority of its 6 buy/sell programs ' + acct("D9VpYFsfLXDoWkUUgYoKBcKdzV745qDajxLsjpNWuaNk") +
  ' · first funded 07-01 with 7.56 SOL by ' + acct("2AQdpHJ2JpcEgPiATUXjQxA8QmafFegfQwSLWSprPicm") + ' (185k SOL, pays many wallets; looks like an exchange) · copy follower ' + acct("DeFG8i8zoJ3hN155nmvLq266ZVxWmNgRaTz5KQVHfe2S", gm=True) +
  ' (433 txs that reference FiFawH, via program ' + acct("F7hMV94qDyUXuv5HirXYJhU59AjuPfJMFaZFbwzLD62r") + ') · the AsTz tip account is also paid by ' + acct("DxhpC9c4kGkYJR34xUrfFeDx9vwb6yoHUMWrTCZybwtH", gm=True) + '.</p>')
A('<p><b>Not known.</b> Who runs AsTz, who operates D9VpYF, and why it sent five fee-only transactions (0.4–2.96 SOL each, to five different leaders).</p></div>')
A(f'<footer>Generated {datetime.datetime.now(PKT):%b %d, %Y %H:%M} PKT from on-chain data (read-only). Scripts: ops/overnight/fifaw (q1_infra.py, q25_pnl_exits.py, render_snipes.py, copy/q6.py).</footer></div></body></html>')
open("FiFawH_snipes.html", "w").write("".join(o))
print("rows", len(rows), "total", round(tot, 3), [(r["name"], r["slot_off"], r["pib"], r["ahead"], round(r["p"]["pnl"], 3)) for r in rows])
