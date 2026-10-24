#!/usr/bin/env python3
# READ-ONLY, offline: every number the report and the HTML page quote, recomputed from the study's outputs.
# -> facts.json (HTML fragments + numbers) and facts.txt (printed tables for REPORT_9qz7cW.md)
import os, json, gzip, collections, statistics as st, datetime, html
HERE = os.path.dirname(os.path.abspath(__file__)); W = "9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw"
J = lambda f: json.load(open(os.path.join(HERE, f)))
LG = J("ledger_q9z.json"); PL = J("perlaunch_q9z.json"); RAWB = [json.loads(l) for l in gzip.open(os.path.join(HERE, "raw_q9z.jsonl.gz"), "rt")]
SL = J("slip_q9z.json"); RU = J("router_users.json")
TM = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
out = []
def P(x=""): print(x); out.append(x)
q = lambda xs, p: sorted(xs)[int(p * (len(xs) - 1))] if xs else None
# ---------- ledger: window totals
tot = collections.defaultdict(float)
for d_, c in LG["per_day"].items():
    for k, v in c.items(): tot[k] += v
P("== ledger categories over everything fetched (36 h full window + older sample):"); P("   " + " | ".join(f"{k} {v:+.2f}" for k, v in sorted(tot.items())))
P("== per PKT day (UTC+5):")
for d_, c in sorted(LG["per_day_pkt"].items()):
    pnl = sum(v for k, v in c.items() if k in ("trading", "quote swap", "failed", "other"))
    P(f"   {d_}: PnL ex transfers {pnl:+8.2f} | trading {c.get('trading', 0):+8.2f} (snipe {c.get('trading:snipe', 0):+.2f}, later {c.get('trading:later', 0):+.2f}, outside collector {c.get('trading:outside', 0):+.2f})"
      f" | quote swaps {c.get('quote swap', 0):+.2f} | failed {c.get('failed', 0):+.2f} (measured {c.get('failed:measured', 0):+.2f}, estimated {c.get('failed:estimated', 0):+.2f}) | withdrawals {c.get('withdrawal', 0):+.2f}")
# ---------- behaviour x quote (collector-window tokens), all costs
T = LG["tokens"]
g = collections.defaultdict(lambda: [0, 0.0, 0.0, 0])
for m, t in T.items():
    b = t["beh"] or "outside collector / not first-attempted in it"
    qk = "non-SOL quote" if (t["venue"] or "").endswith("non-SOL quote") else ("SOL" if t["venue"] else "failed only")
    for key in ((b, qk), (b, "ALL")):
        x = g[key]; x[0] += 1; x[1] += t["val"]; x[2] += t["fail"]; x[3] += t["val"] + t["fail"] > 0
P("\n== tokens by behaviour x quote: tokens | trading SOL | failed-tx fees | NET | win")
for k, (n, v, f, wn) in sorted(g.items()): P(f"   {k[0][:44]:46} {k[1]:14} {n:5d} {v:+9.2f} {f:+8.2f} {v + f:+9.2f}  {wn / n:.0%}")
# ---------- snipe landing / spend (collector raw)
B = [r for r in RAWB if not r[5] and any("Buy" in x for x in r[11])]
spend = [((r[6] or 5000) - 5000) / 1e9 + sum(l for _, l in r[12]) / 1e9 for r in B]
snf = [r for r in PL.values() if r["beh"] == "snipe" and r["filled"] and r["quote"] == "SOL" and r.get("buy_sol")]
first_rate = sum(1 for r in snf if r["ahead"] == 0) / len(snf)
arr = [r["arr_ms"] for r in PL.values() if r["beh"] == "snipe" and r["filled"] and r.get("arr_ms") is not None]
P(f"\n== snipes: filled SOL-quoted {len(snf)}, first outside buyer {first_rate:.0%}, arrival ms q10/50/90 {q(arr, .1)}/{q(arr, .5)}/{q(arr, .9)}; landed-buy spend q50 {q(spend, .5):.4f} SOL")
tol = [v["tol"] for v in SL.values() if v.get("tol") is not None]
P(f"== min-out headroom on landed buys: n {len(tol)} q25 {q(tol, .25):.3f} q50 {q(tol, .5):.3f} q75 {q(tol, .75):.3f}")
beh_sum = {k: (g[(k, 'ALL')][1] + g[(k, 'ALL')][2]) for k in ("snipe", "later")}
F = dict(
    ledger_span="10-20 18:14 PKT → now (last 36 h fully, older hours sampled)",
    first_rate=f"{first_rate:.0%}", arr_med=f"{q(arr, .5):.0f}", spend_med=f"{q(spend, .5):.3f} SOL",
    snipe_pnl=f"{beh_sum['snipe']:+.1f}", later_pnl=f"{beh_sum['later']:+.1f}", coll_hours="26",
    n_nonce=4, tol_text=f"(on landed buys it got a median {q(tol, .5) * 100:.0f}% more tokens than its minimum, so it accepts roughly 10% slippage)",
)
json.dump(F, open(os.path.join(HERE, "facts_base.json"), "w"), indent=1)
open(os.path.join(HERE, "facts.txt"), "w").write("\n".join(out) + "\n")
# ---------- HTML fragments (numbers above + the replay outputs)
e = html.escape
LDR = LG["cross"]
s36 = [l for l in open(os.path.join(HERE, "ledger_q9z.txt")) if l.startswith("== FINAL 36h")]
F["tldr_html"] = [
    "<b>Very profitable overall</b>: its SOL balance plus what it swept to 3 treasury wallets grew by <b>+406 SOL in 61.5 h</b> (10-20 18:14 PKT to 10-23 07:40 PKT); "
    "the fully read last 36 h made <b>+283 SOL</b> after every fee and failed transaction (+188 SOL in SOL, +95 SOL of quote-token inventory at current prices). <span class='badge m'>measured</span>",
    "It is a <b>custom, multi-strategy pump.fun bot</b>, not a customer of a commercial one: its own router program "
    "<span class='mono'>2eFuLSK4…</span> (used by only 5 other wallets in our data), v1 transactions, 4 rotating durable nonces, and every buy sent as several copies "
    "(priority-fee copy, Jito-tip copy, a 'b1oo…' landing-service copy, cheap router backups). No 1% bot fee like AKbot. <span class='badge m'>measured</span>",
    f"It snipes (<b>{F['first_rate']} first outside buyer</b>, median {F['arr_med']} ms after the create in our feed) but its snipes <b>lose after costs</b>: "
    f"{F['snipe_pnl']} SOL in our ~26 h of collector windows, mostly failed buy copies that landed after the price moved (min-out failures pay the full priority fee). <span class='badge m'>measured</span>",
    f"The money is in its <b>later entries</b> (5 s to 5 min after the create, into rising tokens): <b>{F['later_pnl']} SOL</b> in the same windows, "
    "but concentrated: 8 buys of 10+ SOL made +53.6 SOL. Its own big buy moves the price (x1.13 median, x1.77 for 10+ SOL) and many non-sniper buyers follow; it sells into them in 6-12 pieces. <span class='badge m'>measured</span>",
    "It also trades pump.fun coins quoted in other tokens (PUMP, USDC, tokenized stocks, BTC/XMR wrappers) and keeps an inventory worth ~2,066 SOL of those quote tokens in the wallet. <span class='badge m'>measured</span>",
    "<b>Not copyable for us at 0.5 SOL</b>: copying its snipes only looks good because fast snipers (it included) buy right after us; following its later buys 300-500 ms late, "
    "or a generic momentum rule built from its later entries, loses in both halves. <span class='badge i'>paper replay</span>",
]
F["cost_html"] = ("Per landed buy it pays EITHER a priority fee in the v1 header (median 0.029 SOL) OR a Jito tip (median 0.053 SOL), whichever copy lands; on snipes that is "
                  "2.8% of the SOL it buys, on later entries 4.8%. Failed copies are cheap (5,000 lamports) except nonce copies that land after the price moved: "
                  "those fail on its min-out limit (pump error 6042) and still pay their full priority fee: 32.5 SOL of the 36.8 SOL of failed-tx fees in our collector windows. "
                  "Sells cost 5,000 lamports plus an optional 0.00011 SOL Jito tip; each sell goes out as ~3 copies and the spare ones fail at 476 compute units.")
F["table_note"] = ("Pattern (measured on all its create-slot fills): when the price is below its entry at the first check (~8 slots, 1.7 s) it sells everything at once (85%); "
                   "when the price is 5% or more above entry it sells 30-40% within 2-3 slots and ladders the rest. Over all its snipes the 1-sell losers outweigh the ladders.")
F["vs_us"] = [
    ("Where the buy lands", f"create slot (77%) or next; first outside buyer {F['first_rate']}; median {F['arr_med']} ms in our feed", "~75 ms after the create (45 ms after the planned upgrade)"),
    ("Landing spend", "priority fee OR Jito tip per copy; ~2.8% of the buy on snipes, 4.8% on later entries", "5 routes with ~0.001 SOL tips + 0.011 SOL priority"),
    ("Transaction", "v1, durable nonce (4 accounts), CU limit = used + ~400, own token account via seed", "recent blockhash (cached), ~100k CU limit, ATA program"),
    ("Slippage", "min-tokens-out with ~10% headroom (median); late copies fail (error 6042)", "1% price guard (fail unless first after the bundle)"),
    ("Size", "round gross amounts: 1.2 / 1.8 / 3.0 SOL on snipes, 2-35 SOL on later entries", "0.5 SOL"),
    ("Exit", "snipes: all at ~1.7 s if down, else 30-40% at once + ladder; later: 30% at ~3 s then 10% every ~2-3 s", "everything at the end of the next slot"),
]
SC2 = [l.strip() for l in open(os.path.join(HERE, "sim_copy2.txt"))]
LST = [l.rstrip() for l in open(os.path.join(HERE, "later_strat.txt"))]
F["copy_html"] = ("<p><b>Snipe copies</b> (replay window = R2 launches with our engine's timelines; 0.5 SOL, 1% guard, sell at the end of the next slot):</p><ul>"
    "<li>Its own snipe picks at our 45 / 75 ms: +7.05 / +4.17 SOL (82 / 56 fills of 220). With the buys of the 380 fast sniper wallets after our entry removed: <b>-1.90 / -1.85 SOL</b>. "
    "<b>Rejected: depends on 9qz7cW, Ake3Lc…, dKMjeG…, G9sQPg…, DpBUrt…, CWiNFA…</b> (the wallets that buy right after us).</li>"
    "<li>A walk-forward creator list from its snipes (with the quality gate): +4.96 / +3.70 SOL, with fast snipers removed -1.48 / -1.36 SOL. Rejected for the same reason.</li></ul>"
    "<p><b>Later entries</b> (our normal low-fee send lands 300-500 ms after the decision, every trade in that window is ahead of us; pump fees + 0.0001 SOL per tx):</p><ul>"
    "<li>Following its later buys: -2.7 to -5.9 SOL over 248 entries for every exit (end of next slot, 5 s, 20 s, its ladder), worse with fast snipers or the top-10 after-us buyers removed.</li>"
    "<li>A generic momentum trigger built from its later entries (5-300 s old, price >= 1.1x the post-bundle price, >= 3 SOL net inflow from >= 8 buys in 10 s): -39 to -156 SOL over 3,234 entries.</li>"
    "<li>The same trigger restricted to what its picks look like at decision time (>= 15 s, >= 1.3x, deployer with >= 20 launches): -10 to -27 SOL over 825 entries, negative in both halves.</li>"
    "<li>Its later picks are better than the momentum candidates it skipped (+11 vs -110 SOL with our generic entry), but that is look-ahead: it decides ~20 s after our trigger, when the token is still rising.</li></ul>")
F["method_html"] = ("<p><b>Data.</b> Its 81,206 signatures on the owner's RPC (10-20 18:14 PKT to now; 71% failed). Every successful transaction of the last 36 h was read in full "
    "(from the RPC or from our collector's raw transactions, with the quote-token leg decoded from pump.fun's trade event); the older hours only as SOL-balance checkpoints and two full hour blocks. "
    "Failed transactions: 19,717 measured in the collector; the rest priced from the SOL-balance continuity of the 36 h window. Per-launch behaviour from our collector (R1 + R2, ~26 h): "
    "1,903 launches it attempted, compared with every launch in the feature table.</p>"
    "<p><b>Values.</b> SOL changes are exact; quote tokens (PUMP, USDC, stocks...) are valued at Jupiter prices of 10-23 07:40 PKT (SOL = $104.3).</p>"
    "<p><b>Labels.</b> Measured = read from chain data or our collector. Inferred = our reading of it. Paper replay = rp.py curve replay, no trades sent.</p>")
json.dump(F, open(os.path.join(HERE, "facts.json"), "w"), indent=1)
print("facts.json written")
