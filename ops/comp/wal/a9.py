# READ-ONLY offline: what sets 9XPMCaxt's size units k (size = k x 0.494 SOL)?
import json, collections, statistics as st, time
F = [json.loads(l) for l in open("/root/comp/wal/9X_feat.jsonl")]
F = [f for f in F if "dev" in f]
print("rows with launch features", len(F))
P = lambda xs, q: sorted(xs)[min(len(xs) - 1, int(q * len(xs)))] if xs else None
for f in F:
    f["hour"] = time.gmtime(f["bt"]).tm_hour
    f["nlen"] = len(f["name"]); f["slen"] = len(f["sym"])
    f["caps"] = f["sym"].isupper()
    f["dK"] = "dK" in f["other"]; f["4y"] = "4y" in f["other"]
    f["n_tip"] = len(f["ctips"])
    f["tipprov"] = "+".join(sorted({x[0][:8] for x in f["ctips"]})) or "-"
    f["fee_per_unit"] = f["land"] / max(1, f["k"])
    f["pos_"] = f["pos"] if f["pos"] is not None else 999


def rank(xs):
    o = sorted(range(len(xs)), key=lambda i: xs[i]); r = [0] * len(xs)
    i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and xs[o[j + 1]] == xs[o[i]]: j += 1
        for t in range(i, j + 1): r[o[t]] = (i + j) / 2
        i = j + 1
    return r


def spear(a, b):
    ra, rb = rank(a), rank(b)
    ma, mb = st.mean(ra), st.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return num / den if den else 0


ks = [f["k"] for f in F]
print("\nSpearman(k, feature)  [|rho|>0.2 with n~100 is roughly p<0.05]")
num = ["dev", "gsol", "glued", "ctip_sol", "n_tip", "c_cu", "c_fee", "mc_pre", "dslot", "pos_", "n_ahead_slot", "sol_ahead_slot", "cpos", "nnv", "nlen", "slen",
       "hour", "bt", "land", "cu", "tip", "pnl_pct"]
res = []
for k in num:
    xs = [float(f.get(k) or 0) for f in F]
    res.append((abs(spear(ks, xs)), k, spear(ks, xs)))
for a, k, r in sorted(res, reverse=True):
    print(f"  {k:15} {r:+.2f}")
print("\nby size unit k:")
print(f"{'k':>3} {'n':>3} {'dev':>5} {'bund':>5} {'gl':>3} {'moon%':>5} {'ctip':>6} {'mc':>5} {'dslot':>5} {'pos':>4} {'ahead':>6} {'dK%':>4} {'4y%':>4} {'land':>6} {'pnl_avg':>7} {'pnl_med':>7} {'win%':>4}")
for k in sorted(set(ks)):
    g = [f for f in F if f["k"] == k]
    print(f"{k:3} {len(g):3} {P([f['dev'] for f in g], .5):5.2f} {P([f['gsol'] for f in g], .5):5.2f} {P([f['glued'] for f in g], .5):3} {sum(f['moon'] for f in g) / len(g) * 100:5.0f}"
          f" {P([f['ctip_sol'] for f in g], .5):6.4f} {P([f['mc_pre'] for f in g], .5):5.1f} {P([f['dslot'] for f in g], .5):5} {P([f['pos_'] for f in g], .5):4} {P([f['sol_ahead_slot'] for f in g], .5):6.2f}"
          f" {sum(f['dK'] for f in g) / len(g) * 100:4.0f} {sum(f['4y'] for f in g) / len(g) * 100:4.0f} {P([f['land'] for f in g], .5):6.3f}"
          f" {st.mean(f['pnl_pct'] for f in g) * 100:+7.1f} {st.median(f['pnl_pct'] for f in g) * 100:+7.1f} {sum(f['pnl_pct'] > 0 for f in g) / len(g) * 100:4.0f}")
print("\ncategoricals (share per k-group: small k<=2, mid 3-4, big >=5):")
grp = lambda k: "small" if k <= 2 else ("mid" if k <= 4 else "big")
for cat in ("uri", "tipprov", "mayhem", "caps", "tiplab"):
    c = collections.defaultdict(collections.Counter)
    for f in F: c[str(f[cat])][grp(f["k"])] += 1
    rows = sorted(c.items(), key=lambda kv: -sum(kv[1].values()))[:8]
    print(f"  {cat}: " + " | ".join(f"{v}: s{n['small']} m{n['mid']} b{n['big']}" for v, n in rows))
cr = collections.defaultdict(list)
for f in F: cr[f["creator"]].append(f["k"])
rep = {c: v for c, v in cr.items() if len(v) > 1}
print(f"\nrepeat creators: {len(rep)}  ", "; ".join(f"{c[:6]}:{v}" for c, v in list(rep.items())[:10]))
print("\nper-row (sorted by k):")
for f in sorted(F, key=lambda f: (f["k"], f["bt"])):
    print(f"  k={f['k']:2} {time.strftime('%m-%d %H:%M', time.gmtime(f['bt']))} dev {f['dev']:5.2f} bund {f['gsol']:5.2f}/{f['glued']} moon {int(f['moon'])} ctip {f['ctip_sol']:.4f} {f['tipprov'][:16]:16}"
          f" mc {f['mc_pre']:5.1f} ds {f['dslot']} pos {str(f['pos']):>4} ahead {f['sol_ahead_slot']:5.2f} {f['uri'][:22]:22} {f['name'][:16]:16} dK {f['other'].get('dK', '-')} 4y {f['other'].get('4y', '-')} pnl {f['pnl_pct'] * 100:+.0f}%")
