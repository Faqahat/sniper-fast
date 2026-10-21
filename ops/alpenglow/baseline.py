# Pre/post-Alpenglow baseline from a paper/dry engine log: slot length, detection volume, feed lag, create position in
# slot, rule-2 race/fire counts, peers' feed timing, RPC latency, runtime lag. usage: python3 baseline.py <log> <label>
import sys, re, statistics as st, collections
L, label = sys.argv[1], sys.argv[2]
txt = open(L, errors="replace").read().splitlines()
q = lambda v, p: sorted(v)[min(len(v) - 1, int(p * len(v)))] if v else None
slots = [int(m.group(1)) for l in txt for m in [re.search(r" slot=(\d+)", l)] if m]
poh = [float(m.group(1)) for l in txt for m in [re.search(r"POH CLOCK: .* -> ([\d.]+) ms a slot", l)] if m]
span_slots = (max(slots) - min(slots)) if slots else 0
slot_ms = poh[-1] if poh else 217.4
hours = span_slots * slot_ms / 3.6e6
det = collections.Counter(); dt = collections.defaultdict(list); mints = set(); verdict = collections.Counter()
for l in txt:
    m = re.search(r"DETECT feed=(\S+) first=(\d) dt_us=(\d+) slot=\d+ .*mint=(\w+).*verdict=(\w+)", l)
    if m:
        det[m.group(1)] += 1; mints.add(m.group(4))
        if m.group(2) == "0": dt[m.group(1)].append(int(m.group(3)) / 1000)
        if m.group(2) == "1": verdict[m.group(5)] += 1
cms = [float(m.group(1)) for l in txt for m in [re.search(r"GATE-CREATE-MS .*create_ms=([\d.]+)", l)] if m]
seen = sum(1 for l in txt if "RACE seen" in l); dec = [l for l in txt if "RACE decide" in l]
fires = sum(1 for l in txt if re.search(r"^\s+FIRE slot=", l))
first_ms = [float(m.group(1)) for l in txt for m in [re.search(r"RACE obs .*first_ms=([\d.]+)", l)] if m and float(m.group(1)) >= 0]
rpc = [float(m.group(1)) for l in txt for m in [re.search(r"RPC-LAT 60s bh-primary .*p50=([\d.]+)ms", l)] if m]
rt = [float(m.group(1)) for l in txt for m in [re.search(r"RUNTIME lag 60s .*p99=([\d.]+)ms", l)] if m]
print(f"== {label}: {hours:.2f} h, slot {slot_ms:.1f} ms (POH CLOCK samples {len(poh)}: {', '.join(f'{x:.1f}' for x in poh[-5:])})")
print(f"   creates seen {len(mints)} ({len(mints) / hours:.0f}/h); first-feed verdicts {dict(verdict.most_common(4))}")
print(f"   feed lag behind the first feed (ms, p50/p90): " + "; ".join(f"{f} {q(v, .5):.2f}/{q(v, .9):.2f} (n {len(v)})" for f, v in dt.items() if v))
print(f"   create_ms in slot: n {len(cms)} p25 {q(cms, .25)} median {q(cms, .5)} p75 {q(cms, .75)}; >150 ms {sum(1 for x in cms if x > 150)}")
print(f"   rule-2 pipeline: RACE seen {seen} ({seen / hours:.1f}/h), race decisions {len(dec)}, race pass {sum(1 for l in dec if 'pass=true' in l)}, FIRES {fires} ({fires / hours:.1f}/h)")
print(f"   first outside buy after create (feed ms): n {len(first_ms)} p25 {q(first_ms, .25)} median {q(first_ms, .5)} p75 {q(first_ms, .75)}")
print(f"   RPC blockhash p50 ms median {q(rpc, .5)}; runtime lag p99 median {q(rt, .5)} ms")
