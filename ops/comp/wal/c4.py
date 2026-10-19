# READ-ONLY offline: what sets 4yFAz's size tier? launch features + token metadata class
import json, statistics as st, time, collections, sys
FE, ME = sys.argv[1], sys.argv[2]
F = [json.loads(l) for l in open(FE)]
F = [f for f in F if "dev" in f]
M = json.load(open(ME))
print("rows with launch features", len(F), " metadata ok", sum(1 for f in F if M.get(f["mint"], {}).get("ok")))
MEDIA = ("x.com", "twitter.com", "youtube", "youtu.be", "instagram", "cnn.com", "gettyimages", "dexerto", "4chan", "otcdesks.cash", "usepaid",
         "tiktok", "reddit", "bbc", "reuters", "google", "t.me", "wikipedia", "imgur", "github.com", "medium.com", "linktr")
P = lambda xs, q: sorted(xs)[min(len(xs) - 1, int(q * len(xs)))] if xs else None


def dom(u):
    u = (u or "").lower().split("://")[-1].split("/")[0]
    return u[4:] if u.startswith("www.") else u


def cls(f):
    o = M.get(f["mint"], {})
    if not o.get("ok"): return "no-meta"
    w = dom(o.get("website")); t = (o.get("twitter") or "").lower()
    own_site = bool(w) and not any(m in w for m in MEDIA)
    acct = bool(t) and "/status/" not in t and "/i/communities" not in t
    if own_site and acct: return "PROJECT site+X acct"
    if own_site: return "own site, no X acct"
    if acct: return "X acct, no site"
    if "/i/communities" in t: return "X community"
    if "otcdesks" in w: return "otcdesks (j7/Lunar)"
    if "/status/" in t: return "tweet-ref meme"
    return "bare (no links)"


def grp(s):
    return "small <1" if s < 1 else ("mid 1-2" if s < 2 else "big >=2")


for f in F:
    f["cls"] = cls(f); f["g"] = grp(f["sol"])
    f["hour"] = time.gmtime(f["bt"]).tm_hour
    f["pos_"] = f["pos"] if f.get("pos") is not None else 999
    f["nlen"] = len(f.get("name", ""))
    o = M.get(f["mint"], {})
    f["desc"] = o.get("desc_len", -1) if o.get("ok") else None


def rank(xs):
    o = sorted(range(len(xs)), key=lambda i: xs[i]); r = [0] * len(xs); i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and xs[o[j + 1]] == xs[o[i]]: j += 1
        for t in range(i, j + 1): r[o[t]] = (i + j) / 2
        i = j + 1
    return r


def spear(a, b):
    ra, rb = rank(a), rank(b); ma, mb = st.mean(ra), st.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return num / den if den else 0


sz = [f["sol"] for f in F]
print("\nSpearman(size, feature)  [|rho|>0.1 with n~500 is roughly p<0.05]")
res = []
for k in ("dev", "gsol", "glued", "ctip_sol", "n_ahead_slot", "sol_ahead_slot", "mc_pre", "dslot", "pos_", "cpos", "nlen", "hour", "bt", "c_cu", "land", "pnl_pct"):
    xs = [float(f.get(k) or 0) for f in F]
    res.append((abs(spear(sz, xs)), k, spear(sz, xs)))
for a, k, r in sorted(res, reverse=True): print(f"  {k:15} {r:+.2f}")
fd = [f for f in F if f["desc"] is not None]
print(f"  {'desc_len':15} {spear([f['sol'] for f in fd], [f['desc'] for f in fd]):+.2f}  (n={len(fd)})")

print(f"\n{'metadata class':22} {'n':>4} {'SOL med':>7} {'SOL avg':>7} {'small%':>6} {'mid%':>5} {'big%':>5}  pnl_avg pnl_med win%")
G = collections.defaultdict(list)
for f in F: G[f["cls"]].append(f)
for c, g in sorted(G.items(), key=lambda kv: -st.mean(f["sol"] for f in kv[1])):
    pc = lambda gg: sum(f["g"] == gg for f in g) / len(g) * 100
    print(f"{c:22} {len(g):4} {P([f['sol'] for f in g], .5):7.2f} {st.mean(f['sol'] for f in g):7.2f} {pc('small <1'):6.0f} {pc('mid 1-2'):5.0f} {pc('big >=2'):5.0f}"
          f"  {st.mean(f['pnl_pct'] for f in g) * 100:+6.1f} {st.median(f['pnl_pct'] for f in g) * 100:+6.1f} {sum(f['pnl_pct'] > 0 for f in g) / len(g) * 100:4.0f}")

print("\nby size group:")
print(f"{'group':9} {'n':>4} {'dev':>5} {'bund':>5} {'ctip':>6} {'mc':>5} {'ds0%':>5} {'pos':>4} {'proj%':>5} {'tweet%':>6} {'bare%':>5} {'land':>6}  pnl_avg pnl_med win%")
for gname in ("small <1", "mid 1-2", "big >=2"):
    g = [f for f in F if f["g"] == gname]
    gm = [f for f in g if f["cls"] != "no-meta"] or [None]
    pm = lambda c: (sum(f["cls"] == c for f in gm if f) / max(1, len([f for f in gm if f])) * 100)
    print(f"{gname:9} {len(g):4} {P([f['dev'] for f in g], .5):5.2f} {P([f['gsol'] for f in g], .5):5.2f} {P([f['ctip_sol'] for f in g], .5):6.4f} {P([f['mc_pre'] for f in g], .5):5.1f}"
          f" {sum(f.get('dslot') == 0 for f in g) / len(g) * 100:5.0f} {P([f['pos_'] for f in g], .5):4} {pm('PROJECT site+X acct'):5.0f} {pm('tweet-ref meme'):6.0f} {pm('bare (no links)'):5.0f} {P([f['land'] for f in g], .5):6.3f}"
          f"  {st.mean(f['pnl_pct'] for f in g) * 100:+6.1f} {st.median(f['pnl_pct'] for f in g) * 100:+6.1f} {sum(f['pnl_pct'] > 0 for f in g) / len(g) * 100:4.0f}")

print("\nuri host by size group (top 10 hosts):")
c = collections.defaultdict(collections.Counter)
for f in F: c[f.get("uri", "?")][f["g"]] += 1
for k, v in sorted(c.items(), key=lambda kv: -sum(kv[1].values()))[:10]:
    tot = sum(v.values()); print(f"  {k[:30]:30} n={tot:3}  small {v['small <1']:3} mid {v['mid 1-2']:3} big {v['big >=2']:3}   SOL avg {st.mean(f['sol'] for f in F if f.get('uri') == k):.2f}")

print("\ncreate-tx tip provider by size group:")
c = collections.defaultdict(collections.Counter)
for f in F: c["+".join(sorted({x[0][:8] for x in f.get("ctips", [])})) or "-"][f["g"]] += 1
for k, v in sorted(c.items(), key=lambda kv: -sum(kv[1].values()))[:8]:
    print(f"  {k[:24]:24} small {v['small <1']:3} mid {v['mid 1-2']:3} big {v['big >=2']:3}")

print("\ndev buy bands:")
for lo, hi in ((0, 0.5), (0.5, 1.5), (1.5, 2.5), (2.5, 3.5), (3.5, 99)):
    g = [f for f in F if lo <= f["dev"] < hi]
    if g: print(f"  dev {lo}-{hi}: n={len(g):3} SOL med {P([f['sol'] for f in g], .5):.2f} avg {st.mean(f['sol'] for f in g):.2f}  big% {sum(f['g'] == 'big >=2' for f in g) / len(g) * 100:.0f}  pnl avg {st.mean(f['pnl_pct'] for f in g) * 100:+.1f}%")
print("\nbundle bands:")
for lo, hi in ((0, 0.01), (0.01, 2), (2, 3), (3, 5.01), (5.01, 9), (9, 999)):
    g = [f for f in F if lo <= f["gsol"] < hi]
    if g: print(f"  bundle {lo}-{hi}: n={len(g):3} SOL med {P([f['sol'] for f in g], .5):.2f} avg {st.mean(f['sol'] for f in g):.2f}  big% {sum(f['g'] == 'big >=2' for f in g) / len(g) * 100:.0f}  pnl avg {st.mean(f['pnl_pct'] for f in g) * 100:+.1f}%")

cr = collections.defaultdict(list)
for f in F: cr[f.get("creator")].append(round(f["sol"], 2))
rep = sorted(((c, v) for c, v in cr.items() if len(v) >= 3), key=lambda kv: -len(kv[1]))
print(f"\nrepeat creators (>=3 buys): {len(rep)}")
for c, v in rep[:12]: print(f"  {str(c)[:8]} n={len(v)} sizes {sorted(v)}")
ow = collections.Counter()
for f in F:
    for w in f.get("other", {}): ow[w] += 1
print("\nother pros on same mint:", dict(ow))
for w in ("dK",):
    g = [f for f in F if w in f.get("other", {})]
    if g: print(f"  with {w}: n={len(g)} 4y SOL avg {st.mean(f['sol'] for f in g):.2f} vs without {st.mean(f['sol'] for f in F if w not in f.get('other', {})):.2f}")
