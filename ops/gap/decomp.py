#!/usr/bin/env python3
"""Per live buy: create -> our landing (PoH ms, from position) split into: leader batching (create recorded -> its
shreds published; DZ leader-feed FEC-set gaps, time-weighted, by client), transit leader -> us on the feed we had
(leader RTT/2 + DZ hop 0.4 ms for the leader-direct path, + 1.6 ms Kaldera's measured lag behind dz-leader), our
processing 0.4 ms (Oct 18 build), us -> provider 0.5 ms, remainder = provider -> leader + leader queue/scheduling."""
import json, statistics as st
B = {"bam": 7.4, "harmonic": 12.2, "jito": 11.2, "fd": 19.9}
rows = json.load(open("/root/gap/livebuys.json"))
out = []
print(f"{'slot':10s} {'client':14s} {'rtt':>5s} {'total':>6s} | {'batch':>5s} {'transit':>7s} {'proc':>4s} {'send':>4s} | {'seen-late':>9s} {'after-send':>10s}")
for r in sorted(rows, key=lambda r: r["ms_after_create"]):
    c = r["class"] or "jito"; bt = B.get(c, 10.5); rtt = r["rtt_ms"] or 10
    tr = rtt / 2 + 0.4 + 1.6
    seen = bt + tr; after = r["ms_after_create"] - seen - 0.4
    out.append((r, bt, tr, seen, after))
    print(f"{r['slot']:<10d} {str(r['client']):14s} {rtt:5.1f} {r['ms_after_create']:6.1f} | {bt:5.1f} {tr:7.1f} {0.4:4.1f} {0.5:4.1f} | {seen:9.1f} {after:10.1f}")
med = lambda i: st.median([o[i] for o in out])
print(f"MEDIAN     {'':14s} {'':5s} {st.median([o[0]['ms_after_create'] for o in out]):6.1f} | {med(1):5.1f} {med(2):7.1f} {0.4:4.1f} {0.5:4.1f} | {med(3):9.1f} {med(4):10.1f}")
for c in ("bam", "jito", "harmonic", "fd"):
    g = [o for o in out if (o[0]["class"] or "") == c]
    if g: print(f"  {c:9s} n={len(g)} total med {st.median([o[0]['ms_after_create'] for o in g]):5.1f}  seen-late med {st.median([o[3] for o in g]):5.1f}  after-send med {st.median([o[4] for o in g]):5.1f}")
