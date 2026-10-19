#!/usr/bin/env python3
# READ-ONLY: feed race + lag from AFTER DETECT lines. usage: lat.py <paper_A.log>
import sys, re, statistics as st, collections as C
D = [dict(re.findall(r"(\w+)=(\S+)", l)) for l in open(sys.argv[1], errors="replace") if "DETECT feed=" in l]
by = C.defaultdict(dict)
for d in D:
    by[d["mint"]].setdefault(d["feed"], d)
both = [p for p in by.values() if "erpc" in p and "kaldera" in p]
dts = sorted((int(p["erpc"]["t_rx"]) - int(p["kaldera"]["t_rx"])) / 1e6 for p in both)
q = lambda v, f: v[min(len(v) - 1, int(f * len(v)))]
print(f"creates detected {len(by)} | both feeds {len(both)} | erpc-only {sum(1 for p in by.values() if list(p)==['erpc'])} | kaldera-only {sum(1 for p in by.values() if list(p)==['kaldera'])}")
if dts:
    print(f"t(erpc)-t(kaldera) ms: p10 {q(dts,.1):+.2f} p25 {q(dts,.25):+.2f} median {st.median(dts):+.2f} p75 {q(dts,.75):+.2f} p90 {q(dts,.9):+.2f} | kaldera first {sum(1 for x in dts if x>0)/len(dts):.0%}")
    big = [x for x in dts if abs(x) > 50]
    print(f"   |gap|>50 ms: {len(big)} ({len(big)/len(dts):.1%}); max kaldera lead {max(dts):.0f} ms, max erpc lead {-min(dts):.0f} ms")
lag = sorted(float(d["lag_ms"]) for d in D if d["feed"] == "erpc" and d.get("lag_ms", "-") != "-")
if lag:
    print(f"erpc batch lag after the slot's earliest PoH-normalised arrival: p50 {st.median(lag):.1f} p90 {q(lag,.9):.1f} p99 {q(lag,.99):.1f} ms (n={len(lag)})")
poh = sorted(float(d["poh_ms"]) for d in D if d["feed"] == "erpc" and d.get("poh_ms", "-") != "-" and d.get("first") in ("0", "1"))
if poh:
    print(f"create position in its slot (PoH ms): p25 {q(poh,.25):.0f} median {st.median(poh):.0f} p75 {q(poh,.75):.0f}")
slotd = C.Counter(int(p["erpc"]["slot"]) - int(p["kaldera"]["slot"]) for p in both)
print("slot label erpc-kaldera:", dict(slotd))
