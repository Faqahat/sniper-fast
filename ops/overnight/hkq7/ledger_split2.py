#!/usr/bin/env python3
# Split HkQ7hMjy's 24 h net SOL change into: landed trades (pump buy/sell events), failed attempts (fees only), and other txs
# (transfers in/out, account closes, PumpSwap etc.), so a sweep or deposit cannot fake the profit. Also tips/fees totals and
# the biggest single-tx changes. Local file from ledger24.py.
import json, collections, time, sys
R = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "/home/moiz/sniper/ops/overnight/hkq7/ledger24.json"))
TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json"))
tr = [r for r in R if r["ok"] and r["evs"]]; bad = [r for r in R if not r["ok"]]; oth = [r for r in R if r["ok"] and not r["evs"]]
f = lambda v: sum(r["dsol"] for r in v) / 1e9
print(f"landed trade txs {len(tr)}: {f(tr):+.3f} SOL | failed txs {len(bad)} (signed by it {sum(1 for r in bad if r['signer'])}): {f(bad):+.3f} | other txs {len(oth)}: {f(oth):+.3f}")
print(f"tx fees on landed trades {sum(r['fee'] for r in tr) / 1e9:.3f} SOL (base + priority)")
oth.sort(key=lambda r: r["dsol"])
for r in oth[:5] + oth[-5:]:
    print(f"  other {time.strftime('%m-%d %H:%M', time.gmtime(r['bt'] + 18000))} PKT {r['dsol'] / 1e9:+.4f} signer={r['signer']} https://solscan.io/tx/{r['sig']}")
by = collections.defaultdict(float)
for r in tr: by[time.gmtime(r["bt"] + 18000).tm_hour] += r["dsol"] / 1e9
print("trade-only net by PKT hour:", {h: round(v, 2) for h, v in sorted(by.items())})
ts = [r["bt"] for r in R]; print("span PKT", time.strftime('%m-%d %H:%M', time.gmtime(min(ts) + 18000)), "->", time.strftime('%m-%d %H:%M', time.gmtime(max(ts) + 18000)))
# hour 16 drill-down: biggest losing trade txs
h16 = sorted([r for r in tr if time.gmtime(r["bt"] + 18000).tm_hour == 16], key=lambda r: r["dsol"])[:6]
for r in h16: print(f"  h16 {time.strftime('%H:%M:%S', time.gmtime(r['bt'] + 18000))} {r['dsol'] / 1e9:+.4f} {'buy' if r['evs'][0]['buy'] else 'sell'} {r['evs'][0]['sol'] / 1e9:.3f} mint {r['evs'][0]['mint'][:8]} https://solscan.io/tx/{r['sig']}")
