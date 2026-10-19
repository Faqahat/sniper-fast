# READ-ONLY: from RACE seen/decide/obs lines: first outsider rx time after the create (ms), moon (Lunar) creates vs others
import re, sys, statistics as st
seen, dec = {}, {}
rows = []
for fn in sys.argv[1:]:
    for l in open(fn):
        m = re.search(r"RACE seen slot=(\d+) mint=(\w+) dev=(\d+).* tip=(\d+) tip_to=(\w+)", l)
        if m: seen[m.group(2)] = (m.group(5).startswith("moon"), int(m.group(3)) / 1e9); continue
        m = re.search(r"RACE decide slot=\d+ mint=(\w+) .*bundle_n=(\d+) bundle_sol=([\d.]+)", l)
        if m: dec[m.group(1)] = (int(m.group(2)), float(m.group(3))); continue
        m = re.search(r"RACE obs slot=\d+ mint=(\w+) .*first_ms=(\S+) bundle_n=(\d+) bundle_sol=([\d.]+) fired=(\w+) outs=(\S*)", l)
        if m and m.group(1) in seen:
            outs = [x.split(":") for x in m.group(6).split(",") if x.count(":") >= 3]
            ok = [float(x[0]) for x in outs if x[2] == "1" and not x[3].startswith("FRZh63")]
            moon, dev = seen[m.group(1)]
            bn, bs = int(m.group(3)), float(m.group(4))
            rows.append((moon, 3 <= bs <= 5 and bn >= 1, dev, min(ok) if ok else None, m.group(5) == "true"))
def q(v, p): v = sorted(v); return v[min(len(v) - 1, int(p * len(v)))] if v else float("nan")
for name, f in [("rule2-type (moon & bundle 3-5 SOL)", lambda r: r[0] and r[1]), ("moon, other bundle", lambda r: r[0] and not r[1]),
                ("non-moon, bundle>=1", lambda r: not r[0] and r[1]), ("all", lambda r: True)]:
    g = [r for r in rows if f(r)]
    fm = [r[3] for r in g if r[3] is not None]
    print(f"{name:38} n={len(g):4}  any outsider in 200ms: {len(fm)/max(1,len(g)):.0%}  first-outsider rx ms after create p10/p25/p50: {q(fm,.1):.1f}/{q(fm,.25):.1f}/{q(fm,.5):.1f}  <=10ms: {sum(1 for x in fm if x<=10)/max(1,len(g)):.0%}  <=20ms: {sum(1 for x in fm if x<=20)/max(1,len(g)):.0%}")
