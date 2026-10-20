# READ-ONLY: how many ms after the create does each buyer's tx show up in our shred feed (the engine's RACE obs line),
# joined with what it paid and through which route (bundlestudy.py output), per leader client. Also OUR fires (FAST-FIRE
# route + paths, decide time, and when our own tx showed up). Feed time is relative to the create in the same feed, so
# the leader-to-us propagation cancels: it measures when the leader recorded the tx after the create.
# usage: python3 landtime.py <bundlestudy json> <engine log> [<engine log> ...]
import sys, re, json, collections, statistics as st

BS = json.load(open(sys.argv[1]))
OURS6 = {"2g7rYv", "FRZh63"}
rows = {}      # (mint, wallet6) -> list of bundlestudy rows (create slot buys)
lc_of = {}
for L in BS:
    lc_of[L["mint"]] = L.get("leader_client")
    for r in L["rows"]:
        if r["buy"] and r["pos"] > 0:
            for u in r["users"]: rows.setdefault((L["mint"], u[:6]), []).append(r)

obs = []; fires = {}
for fn in sys.argv[2:]:
    for line in open(fn, errors="replace"):
        if "RACE obs" in line:
            m = re.search(r"slot=(\d+) mint=(\w+) .* outs=(\S*)", line)
            if not m: continue
            slot, mint, outs = int(m.group(1)), m.group(2), m.group(3)
            for o in outs.split(","):
                p = o.split(":")
                if len(p) < 4: continue
                obs.append(dict(slot=slot, mint=mint, ms=float(p[0]), sol=float(p[1]), flag=p[2], w=p[3], src=fn))
        elif "FAST-FIRE" in line:
            m = re.search(r"slot=(\d+) mint=(\w+).*route:(\S+) leader=(\w+) client=(\w+).*writes: (.*)", line)
            if m: fires[(int(m.group(1)), m.group(2))] = dict(route=m.group(3), leader=m.group(4), client=m.group(5), paths=re.findall(r"([\w-]+)=written", m.group(6)))
        elif "RACE decide" in line:
            m = re.search(r"slot=(\d+) mint=(\w+) at_ms=([\d.]+)", line)
            if m: fires.setdefault((int(m.group(1)), m.group(2)), {})["decide_ms"] = float(m.group(3))

# one record per (mint, wallet): the FIRST time it showed up
first = {}
for o in obs:
    k = (o["mint"], o["w"])
    if k not in first or o["ms"] < first[k]["ms"]: first[k] = o
peers = []
for (mint, w), o in first.items():
    if w in OURS6: continue
    rs = rows.get((mint, w))
    if not rs: continue
    r = rs[0]
    if r["cls"] != "sniper" or not r["ok"]: continue
    paid = r["prio"] + sum(t[1] for t in r["tips"])
    route = max(r["tips"], key=lambda t: t[1])[0] if r["tips"] else "prio-only"
    if r.get("bundle") and r["bundle"] != "ERR": route = "JITO-BUNDLE"
    peers.append(dict(ms=o["ms"], paid=paid, route=route, lc=lc_of.get(mint) or "?", pos=r["pos"], w=w))


def q(v, p):
    v = sorted(v); return v[min(len(v) - 1, int(p * len(v)))] if v else None


print(f"peer buys matched (feed time + what they paid): {len(peers)}")
print("\nPEERS: ms after the create, by route (n>=3)")
by = collections.defaultdict(list)
for x in peers: by[x["route"]].append(x)
for k, v in sorted(by.items(), key=lambda kv: q([x['ms'] for x in kv[1]], .5)):
    if len(v) >= 3:
        ms = [x["ms"] for x in v]
        print(f"  {k:12} n {len(v):3}  p10 {q(ms, .1):6.1f}  median {q(ms, .5):6.1f}  p90 {q(ms, .9):6.1f}   paid median {st.median(x['paid'] for x in v):.4f}")
print("\nPEERS: ms after the create, by paid")
for lo, hi in ((0, 0.002), (0.002, 0.005), (0.005, 0.02), (0.02, 0.05), (0.05, 0.1), (0.1, 99)):
    v = [x["ms"] for x in peers if lo <= x["paid"] < hi]
    if v: print(f"  {lo:.3f}-{hi if hi < 99 else '':5}  n {len(v):3}  p10 {q(v, .1):6.1f}  median {q(v, .5):6.1f}  p90 {q(v, .9):6.1f}")
print("\nPEERS: by leader client x route (n>=3), median ms")
by2 = collections.defaultdict(list)
for x in peers: by2[(x["lc"], x["route"])].append(x["ms"])
for (lc, rt), v in sorted(by2.items()):
    if len(v) >= 3: print(f"  {lc:20} {rt:12} n {len(v):3}  median {q(v, .5):6.1f}  p10 {q(v, .1):6.1f}")

print("\nOURS: decide -> our tx seen in the feed (ms after the create)")
for (slot, mint), f in sorted(fires.items()):
    if "route" not in f: continue
    me = [o for o in obs if o["mint"] == mint and o["w"] in OURS6]
    seen = min(o["ms"] for o in me) if me else None
    fp = [o for o in obs if o["mint"] == mint and o["w"] not in OURS6 and o["flag"] == "1"]
    fpm = min(fp, key=lambda o: o["ms"]) if fp else None
    print(f"  {slot} {mint[:8]} {f['client']:15} route {f['route']:15} paths {','.join(f['paths']):45} decide {f.get('decide_ms', 0):4.1f} ms  ours seen "
          f"{('%.1f' % seen) if seen is not None else '  -  '} ms   first peer {('%.1f %s' % (fpm['ms'], fpm['w'])) if fpm else '-'}")
