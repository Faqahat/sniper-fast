#!/usr/bin/env python3
"""Feed race report from a feed_race log (see /root/gap/feed_race.rs header for the line format).
Usage: race_report.py LOG [--leaders /root/gap/leaders.json] [--since-min M]
Prints: per-feed health, % of creates each feed delivers first, misses, pairwise lead (median/p10/p90) on creates,
on all pump txs and on slot first-data; by leader client; by slot position (third of the slot, from the PoH tick count
of an entries feed); provider created_at -> local receive lag for Yellowstone feeds."""
import sys, json, collections, itertools

def pct(v, q):
    if not v: return float("nan")
    v = sorted(v); i = (len(v) - 1) * q; lo = int(i); hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)

def main():
    a = sys.argv[1:]
    if not a: raise SystemExit(__doc__)
    log = a[0]
    lpath = a[a.index("--leaders") + 1] if "--leaders" in a else "/root/gap/leaders.json"
    since = float(a[a.index("--since-min") + 1]) if "--since-min" in a else None
    try: L = json.load(open(lpath))
    except Exception: L = {"leaders": {}, "nodes": {}}
    def lclass(slot):
        i = L["leaders"].get(str(slot)); n = L["nodes"].get(i, {}) if i else {}
        return n.get("class", "unknown")
    def lrtt(slot):
        i = L["leaders"].get(str(slot)); n = L["nodes"].get(i, {}) if i else {}
        return n.get("rtt_ms")

    tx = {}                 # sig -> {"slot", "create", feeds: {feed: t}, "eidx": {feed: eidx}}
    sfirst = collections.defaultdict(dict)   # slot -> feed -> t
    ufirst = collections.defaultdict(dict)   # slot -> feed -> (t, created_at) for status 3 (first shred at provider)
    ent = collections.defaultdict(dict)      # (feed, slot) -> eidx -> ticks_before
    health = {}
    lag = collections.defaultdict(list)      # feed -> t - created_at (ms)
    tmin = None
    feeds = set(); feeds_dec = set()
    for line in open(log, errors="replace"):
        p = line.rstrip("\n").split("\t")
        if len(p) < 4: continue
        k, f = p[0], p[1]
        try: t = int(p[2])
        except ValueError: continue
        if tmin is None: tmin = t
        if since is not None and t < tmin + since * 60e9: continue
        if k == "H": health.setdefault(f, {}); health[f]["last"] = " ".join(p[3:]); continue
        feeds.add(f)
        slot = int(p[3])
        if k == "X":
            sig, cr, eidx, created = p[4], p[5] == "1", p[6], int(p[7])
            d = tx.get(sig)
            if d is None: d = tx[sig] = {"slot": slot, "create": cr, "f": {}, "e": {}}
            d["create"] |= cr
            if f not in d["f"] or t < d["f"][f]: d["f"][f] = t
            if eidx != "-": d["e"][f] = int(eidx)
            if created: lag[f].append((t - created) / 1e6)
        elif k == "R" and len(p) >= 10:
            # udp receive path: the time the tx came out of OUR assembler (= what the engine can act on); a pseudo-feed
            # "<feed>@dec" next to the kernel-timestamp feed
            sig = p[4]; d = tx.get(sig)
            if d is not None:
                fd = f + "@dec"; td = int(p[9])
                if fd not in d["f"] or td < d["f"][fd]: d["f"][fd] = td
                feeds_dec.add(fd)
        elif k == "S":
            if f not in sfirst[slot]: sfirst[slot][f] = t
        elif k == "U":
            if p[4] == "3" and f not in ufirst[slot]: ufirst[slot][f] = (t, int(p[5]))
        elif k == "E":
            ent[(f, slot)][int(p[4])] = int(p[7])
    # virtual feeds = first arrival across a set of real feeds: DZ (all dz-*), COMBO (constantk* + kaldera +
    # turbo-kaldera), ALL (every real feed). --combo none skips them. They are excluded from the 'first' shares.
    real_feeds = sorted(feeds)
    feeds |= feeds_dec
    virt = {}
    if "--combo" not in a or a[a.index("--combo") + 1] != "none":
        dz = [f for f in real_feeds if f.startswith("dz-")]
        co = [f for f in real_feeds if f.startswith("constantk") or f in ("kaldera", "turbo-kaldera")]
        if len(dz) >= 2: virt["DZ"] = dz
        if len(co) >= 2: virt["COMBO"] = co
        if len(real_feeds) >= 3: virt["ALL"] = real_feeds
    for cname, members in virt.items():
        for d in tx.values():
            v = [d["f"][f] for f in members if f in d["f"]]
            if v: d["f"][cname] = min(v)
        for sl in sfirst.values():
            v = [sl[f] for f in members if f in sl]
            if v: sl[cname] = min(v)
        feeds.add(cname)
    feeds = sorted(feeds)
    out = []
    if feeds_dec: out.append("(<feed>@dec = the time OUR assembler decoded the tx (udp feeds, creates + 1/50 txs); the plain udp feed name = kernel arrival of the completing shred; excluded from 'first' shares)")
    for cname, members in virt.items(): out.append(f"({cname} = first arrival across {','.join(members)}; excluded from 'first' shares)")
    P = out.append
    P(f"== feed race: {log}  feeds={','.join(feeds)}")
    for f in sorted(health): P(f"  health {f}: {health[f].get('last','')}")

    creates = {s: d for s, d in tx.items() if d["create"]}
    def block(title, items):
        P(f"\n-- {title}: n={len(items)}")
        if not items: return
        first = collections.Counter(); seen = collections.Counter()
        for d in items:
            fs = d["f"]
            for f in fs: seen[f] += 1
            real = {k: v for k, v in fs.items() if k not in virt and not k.endswith("@dec")}
            w = min(real, key=real.get) if real else None
            if len(real) > 1: first[w] += 1
        multi = sum(1 for d in items if len([k for k in d["f"] if k not in virt and not k.endswith("@dec")]) > 1)
        P("  feed            seen    miss   first (of %d seen by >=2)" % multi)
        for f in feeds:
            P(f"  {f:14s} {seen[f]:6d} {len(items)-seen[f]:6d}  {first[f]*100/max(multi,1):5.1f}%")
        P("  pair (a vs b)                 n   a-first  median(b-a) ms  p10    p90   [+ = a earlier]")
        for x, y in itertools.combinations(feeds, 2):
            ds = [(d["f"][y] - d["f"][x]) / 1e6 for d in items if x in d["f"] and y in d["f"]]
            if not ds: continue
            P(f"  {x+' vs '+y:26s} {len(ds):6d}  {sum(1 for v in ds if v>0)*100/len(ds):5.1f}%   {pct(ds,.5):8.2f}  {pct(ds,.1):7.2f} {pct(ds,.9):7.2f}")
    block("pump.fun CREATES", list(creates.values()))
    block("all pump txs", list(tx.values()))

    # by leader client and by slot position, creates only
    def sub(title, keyf):
        groups = collections.defaultdict(list)
        for d in creates.values(): groups[keyf(d)].append(d)
        P(f"\n-- creates by {title}")
        hdr = "  " + f"{'group':12s} {'n':>5s} " + " ".join(f"{f[:10]+' 1st':>14s}" for f in feeds)
        ref = "kaldera" if "kaldera" in feeds else feeds[0]
        pairs = [(f, ref) for f in feeds if f != ref]
        hdr += "  lead vs " + ref + " (med ms): " + " ".join(f"{x[:10]:>10s}" for x, _ in pairs)
        P(hdr)
        for g in sorted(groups, key=lambda g: -len(groups[g])):
            items = groups[g]; c = collections.Counter(); m = 0
            for d in items:
                real = {k: v for k, v in d["f"].items() if k not in virt and not k.endswith("@dec")}
                if len(real) > 1: c[min(real, key=real.get)] += 1; m += 1
            row = f"  {str(g):12s} {len(items):5d} " + " ".join(f"{c[f]*100/max(m,1):13.0f}%" for f in feeds)
            row += "  " + " " * (len("lead vs " + ref + " (med ms): ") - 1)
            for x, y in pairs:
                ds = [(d["f"][y] - d["f"][x]) / 1e6 for d in items if x in d["f"] and y in d["f"]]
                row += f" {pct(ds,.5):10.2f}" if ds else f" {'-':>10s}"
            P(row)
    sub("leader client", lambda d: lclass(d["slot"]))
    def rttb(d):
        r = lrtt(d["slot"])
        if r is None: return "rtt?"
        return "rtt<3ms" if r < 3 else ("rtt3-20" if r < 20 else ("rtt20-100" if r < 100 else "rtt>100"))
    sub("leader RTT from us", rttb)
    def pos(d):
        for (f, e) in d["e"].items():
            tb = ent.get((f, d["slot"]), {}).get(e)
            if tb is not None: return ["pos 0-1/3", "pos 1/3-2/3", "pos 2/3-1"][min(2, tb * 3 // 64)]
        return "pos ?"
    sub("slot position (PoH ticks)", pos)

    # slot first shred: entries feeds = first entries message, udp = first shred (kernel time), yellowstone = local
    # receive time of the provider's FIRST_SHRED_RECEIVED slot status (first pump tx if the provider sends no statuses)
    first_shred = collections.defaultdict(dict)
    for s, v in sfirst.items():
        for f, t in v.items(): first_shred[s][f] = t
    for s, v in ufirst.items():
        for f, (t, c) in v.items(): first_shred[s][f] = t
    P(f"\n-- slot FIRST SHRED per feed (entries: first message; udp: first shred; yellowstone: FIRST_SHRED_RECEIVED status, else first pump tx): {len(first_shred)} slots")
    for x, y in itertools.combinations(feeds, 2):
        ds = [(v[y] - v[x]) / 1e6 for v in first_shred.values() if x in v and y in v]
        if ds: P(f"  {x+' vs '+y:26s} n={len(ds):5d} a-first {sum(1 for v in ds if v>0)*100/len(ds):5.1f}%  median {pct(ds,.5):7.2f}  p10 {pct(ds,.1):7.2f}  p90 {pct(ds,.9):7.2f} ms")
    if ufirst:
        P("  provider FIRST_SHRED_RECEIVED (status 3) -> local receive, per feed:")
        for f in feeds:
            v = [(t - c) / 1e6 for s in ufirst.values() for ff, (t, c) in s.items() if ff == f and c]
            if v: P(f"    {f:14s} n={len(v)} median {pct(v,.5):.2f} p90 {pct(v,.9):.2f} ms")
    if lag:
        P("  provider created_at -> local receive (transit + clock offsets), per tx:")
        for f, v in sorted(lag.items()): P(f"    {f:14s} n={len(v)} median {pct(v,.5):.2f} p10 {pct(v,.1):.2f} p90 {pct(v,.9):.2f} ms")
    print("\n".join(out))

if __name__ == "__main__":
    main()
