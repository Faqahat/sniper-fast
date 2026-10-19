#!/usr/bin/env python3
"""Report on a junk-fanout dry run log (dry_<tag>.log): feeds (who delivers creates first, by how much), the quote-verdict
disagreement between feeds, fires (rx->fire), routes by leader class, per-path junk ack latency and fan-out offsets.
usage: dry_report.py /root/lat/dry_<tag>.log"""
import re, sys, collections, statistics as st

def q(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(p * (len(v) - 1)))] if v else float("nan")

lg = sys.argv[1]
first = collections.Counter(); behind = collections.defaultdict(list); verdicts = collections.defaultdict(dict)
fires = []; routes = collections.Counter(); acks = collections.defaultdict(list); offs = collections.defaultdict(list)
builds = []; decide = []
for l in open(lg, errors="replace"):
    m = re.search(r"DETECT feed=(\S+) first=(\d) dt_us=(-?\d+) slot=\d+ .*?mint=(\w+) kind=(\S+) sig=\S+(.*)", l)
    if m:
        f, fi, dt, mint, kind, rest = m.groups()
        if fi == "1": first[f] += 1
        else: behind[f].append(int(dt) / 1000)
        vq = re.search(r"quote=(\S+) verdict=(\S+)", rest)
        if vq: verdicts[mint][f] = (vq.group(1), vq.group(2), fi == "1")
        continue
    m = re.search(r"FIRE slot=\d+ mint=\w+ dev_buy=\d+ rx_to_fire_us=(\d+)", l)
    if m: fires.append(int(m.group(1)) / 1000); continue
    m = re.search(r"RACE decide .* at_ms=([\d.]+) .* pass=true", l)
    if m: decide.append(float(m.group(1))); continue
    m = re.search(r"JUNK-FAN .* (route:\S+) leader=\S* client=(\S*) paths=(\S+) tips=(\d+) build_us=(\d+)", l)
    if m: routes[m.group(1)] += 1; builds.append(int(m.group(5))); continue
    m = re.search(r"JUNK-ACK path=(\S+) t_off_us=(\d+) ack_ms=([\d.]+) answered=(\w+)", l)
    if m: acks[m.group(1)].append(float(m.group(3))); offs[m.group(1)].append(int(m.group(2)) / 1000)

print("== FEEDS: first arrival of each create (copies), and how far behind the first the other copies were ==")
tot = sum(first.values())
for f, n in first.most_common(): print(f"  {f:14} first {n:5} ({n / max(tot, 1):.0%})")
for f, v in behind.items(): print(f"  {f:14} when not first: behind by p10 {q(v, .1):.2f} / p50 {q(v, .5):.2f} / p90 {q(v, .9):.2f} ms (n={len(v)})")
dis = [(m, v) for m, v in verdicts.items() if len({x[0] == 'sol' for x in v.values()}) > 1]
lost = [(m, v) for m, v in dis if any(x[2] and x[1] == "skip_quote" for x in v.values()) and any(x[0] == "sol" for x in v.values())]
print(f"\n== QUOTE VERDICT disagreement between feeds: {len(dis)} of {len(verdicts)} creates; first copy wrongly skip_quote while another feed read SOL: {len(lost)}")
for m, v in lost[:5]: print("   ", m[:10], {f: x[:2] for f, x in v.items()})
print(f"\n== FIRES (Gate B passed): {len(fires)}; rx->fire ms p10/p50/p90 {q(fires, .1):.2f} / {q(fires, .5):.2f} / {q(fires, .9):.2f};"
      f" gate decide at_ms p50 {q(decide, .5):.2f}; build+sign us p50 {q(builds, .5):.0f}")
print("  routes:", dict(routes))
print("\n== JUNK ACK per path (real send handler, warm pooled connection) ==")
for p, v in sorted(acks.items()):
    print(f"  {p:12} n={len(v):3} ack p50 {q(v, .5):.2f} p90 {q(v, .9):.2f} max {max(v):.2f} ms | fan-out start offset p50 {q(offs[p], .5):.3f} p90 {q(offs[p], .9):.3f} ms")
