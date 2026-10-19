import json, statistics as st
R = [json.loads(l) for l in open("/root/bsplit/out.jsonl")]
ok = [r for r in R if "glued" in r]
print(f"classified {len(ok)}/{len(R)} (missing block/create: {len(R)-len(ok)})")


def pnl_at(r, f):
    return (1 + r["pnl1"]) / f - 1


def row(name, g, entry):
    if not g:
        print(f"{name:26} n=0")
        return
    n = len(g)
    peak = st.median(r["peak"] for r in g)
    p2 = sum(r["peak"] >= 2 for r in g) / n
    flo = [r["pnl1"] for r in g]
    real = [pnl_at(r, entry(r)) for r in g]
    ent = st.median(entry(r) for r in g)
    rel = st.median(r["peak"] / entry(r) for r in g)
    rel15 = sum(r["peak"] / entry(r) >= 1.5 for r in g) / n
    ex = sorted(real)[:-10] if n > 20 else real
    print(f"{name:26} n={n:3}  peak/floor med {peak:4.2f}x  >=2x {p2:4.0%} | PAPER@floor avg {st.mean(flo):+.3f} | "
          f"real entry med {ent:4.2f}x  peak/entry med {rel:4.2f}x  >=1.5x {rel15:4.0%}  REAL avg {st.mean(real):+.3f} "
          f"(ex-top10 {st.mean(ex):+.3f}, win {sum(x > 0 for x in real)/n:3.0%})")


nob = [r for r in ok if r["glued"] == 0]
bun = [r for r in ok if r["glued"] >= 1]
print(f"\nno-bundle {len(nob)} ({len(nob)/len(ok):.0%})  bundled {len(bun)} ({len(bun)/len(ok):.0%})")
print("\nREAL entry = where an outside sniper can actually buy: no-bundle -> 1.00x (first) ; bundled -> right behind the bundle (best case)")
row("NO bundle (first ind)", nob, lambda r: 1.00)
row("NO bundle (2nd ind 1.04)", nob, lambda r: 1.04)
row("BUNDLED (just behind)", bun, lambda r: max(1.0, r["bmult"]))
row("BUNDLED (+4% realistic)", bun, lambda r: max(1.0, r["bmult"]) * 1.04)
print("\nbundled by bundle size (entry just behind bundle):")
for lo, hi in [(0, 1), (1, 3), (3, 10), (10, 999)]:
    row(f"  bundle {lo}-{hi} SOL", [r for r in bun if lo <= r["gsol"] < hi], lambda r: max(1.0, r["bmult"]))
print("\nshare of PAPER@floor profit:")
tot = sum(r["pnl1"] for r in ok)
print(f"  total {tot:+.1f} SOL-units ; no-bundle {sum(r['pnl1'] for r in nob):+.1f} ; bundled {sum(r['pnl1'] for r in bun):+.1f}")
print(f"  bundled REAL (just behind) {sum(pnl_at(r, max(1, r['bmult'])) for r in bun):+.1f}  -> the gap is profit bought BELOW the bundle (impossible for us)")
print(f"\nmedian bundle {st.median(r['gsol'] for r in bun):.2f} SOL, median post-bundle price {st.median(r['bmult'] for r in bun):.2f}x floor; "
      f"first outside buyer actual fill med {st.median([r['first_ind'] for r in bun if r['first_ind']] or [0]):.2f}x (n={sum(1 for r in bun if r['first_ind'])})")
