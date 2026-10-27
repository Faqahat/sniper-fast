#!/usr/bin/env python3
# Summarise anatomy.json (x8): per wallet tx shape. All MEASURED (getTransaction).
import sys, json, collections, statistics as st
sys.path.insert(0, "/home/moiz/sniper/ops/dip/speed/landing2")
import lib2
A = json.load(open(f"{lib2.D}/anatomy.json"))
med = lambda v: round(st.median(v)) if v else None
by = collections.defaultdict(list)
for a in A: by[a["who"]].append(a)
order = ["OURS-FRA", "OURS-AMS", "HkQ7hMjy", "haqqiUUX", "DYXDDrZC", "8PgC4ngp", "6n2cCJrr", "9u5f8WMf", "G9G3dCBG", "5w8xtjc6", "DF7eRXHn", "EprLoV21",
         "HLU8QbLd", "GKd5EMzR", "EMKY7r6U", "BUkpShoE", "3MHgGwdL", "E6JasdE8", "EjywYBfN", "CZ77onJz"]
print("| wallet | n | durable nonce | nonce accts seen | version | size (bytes) | signatures | account keys | lookup table | ixs | CU limit | CU price µL | "
      "loaded-data limit set | tips per tx | tip vs buy | Lighthouse | own program | cost units |")
print("|---|" + "---|" * 17)
for w in order:
    v = by.get(w) or []
    if not v: continue
    n = len(v)
    vers = collections.Counter(a["ver"] for a in v).most_common(2)
    tw = collections.Counter(a["tip_where"] for a in v).most_common(2)
    own = collections.Counter(p[:6] for a in v for p in a["own"]).most_common(2)
    print(f"| {w} | {n} | {sum(1 for a in v if a['nonce'])/n:.0%} | {len({a['nonce'] for a in v if a['nonce']})} | {', '.join(f'{k} {c}' for k, c in vers)} | "
          f"{med([a['size'] for a in v])} | {med([a['nsig'] for a in v])} | {med([a['nkeys'] for a in v])} | {sum(1 for a in v if a['alt'])/n:.0%} | {med([a['nix'] for a in v])} | "
          f"{med([a['cul'] or 0 for a in v]):,} | {med([a['cup'] or 0 for a in v]):,} | {sum(1 for a in v if a['ldl'])/n:.0%} | "
          f"{med([len(a['tips']) for a in v])} (max {max(len(a['tips']) for a in v)}) | {', '.join(f'{k} {c}' for k, c in tw)} | {sum(1 for a in v if a['lighthouse'])/n:.0%} | "
          f"{', '.join(f'{k}… {c}' for k, c in own) or '-'} | {med([a['cost'] or 0 for a in v]):,} |")
print("\nexamples (Solscan: https://solscan.io/tx/<sig>):")
for w in order:
    v = [a for a in by.get(w) or [] if not a["err"]]
    v.sort(key=lambda a: a["ms"])
    for a in v[:2]:
        print(f"  {w:9s} {a['cl']:12s} {a['ms']:5.1f} ms route {a['svc']:12s} nonce {'Y' if a['nonce'] else 'n'} {a['ver']} {a['size']}B CUlim {a['cul']} price {a['cup']} tips {a['tips']} {a['sig']}")
