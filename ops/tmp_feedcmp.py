import re, collections, sys
d = collections.defaultdict(dict)   # mint -> {feed_idx: earliest_trx_ns}
for line in open('/root/sniper-fast/feedcmp.log'):
    m = re.search(r'FEEDCMP feed=(\d+) trx=(\d+) slot=\d+ mint=(\S+)', line)
    if not m: continue
    feed, trx, mint = int(m.group(1)), int(m.group(2)), m.group(3)
    if feed not in d[mint] or trx < d[mint][feed]: d[mint][feed] = trx
f0 = sum(1 for v in d.values() if 0 in v)   # erpc
f1 = sum(1 for v in d.values() if 1 in v)   # kaldera
both = [(e, k) for v in d.values() if 0 in v and 1 in v for e, k in [(v[0], v[1])]]
deltas = sorted((e - k) / 1e6 for e, k in both)   # ms; + => kaldera delivered first (erpc later)
n = len(deltas)
print(f"creates on erpc(0): {f0}   on kaldera(1): {f1}   matched on BOTH: {n}")
if n:
    q = lambda p: deltas[min(n-1, int(p*n))]
    kwin = sum(1 for x in deltas if x > 0); ewin = sum(1 for x in deltas if x < 0); tie = sum(1 for x in deltas if x == 0)
    print(f"\ndelta = erpc_trx - kaldera_trx  (POSITIVE => KALDERA faster)")
    print(f"  median {deltas[n//2]:+.1f} ms   mean {sum(deltas)/n:+.1f} ms   p10 {q(.1):+.1f}   p90 {q(.9):+.1f}   min {deltas[0]:+.1f}   max {deltas[-1]:+.1f}")
    print(f"  KALDERA faster: {kwin}/{n} ({100*kwin/n:.0f}%)   erpc faster: {ewin}/{n} ({100*ewin/n:.0f}%)   tie: {tie}")
else:
    print("no mints matched on both feeds — check kaldera feed connected (grep kaldera/feed=1 in feedcmp.log)")
