"""Brute-force checks behind DESIGN.md §2.4, §2.5 and §3.3 (pure maths, no RPC).
1. DLMM drain test: SDK 0.12's `in - ceil(in*r/1e9) >= max_in` vs the old `in >= max_in + ceil(max_in*r/(1e9-r))`.
2. DAMM v2 range-exit capacities (closed forms) vs the swap's own next-sqrt-price formulas.
3. CPMM-CPMM closed form: profit at floor(x*) vs the best integer size nearby."""
import random, math
cd = lambda a, b: -(-a // b)
random.seed(7)

# 1 ------------------------------------------------------------------------------------------------------------------
D = 10**9; n = diff = 0
for _ in range(300000):
    r = random.choice([random.randint(1, 10**8), random.randint(1, 1000) * 10**5, 10**8, 2_500_000])
    M = random.choice([random.randint(1, 1000), random.randint(1, 10**12)])
    thr = M + cd(M * r, D - r)
    for R in (thr - 2, thr - 1, thr, thr + 1):
        if R <= 0: continue
        n += 1
        diff += (R - cd(R * r, D) >= M) != (R >= thr)
print(f"1. DLMM drain test: {n} cases, {diff} differences")

# 2 ------------------------------------------------------------------------------------------------------------------
bad = 0
for _ in range(20000):
    L = random.randint(1, 2**100); P = random.randint(2**40, 2**80); Pmin = random.randint(2, P)
    nmax = cd(L * (P - Pmin + 1), (Pmin - 1) * P) - 1
    ok = lambda k: cd(L * P, L + k * P) >= Pmin
    if nmax >= 0 and not (ok(nmax) and not ok(nmax + 1)): bad += 1
    Pmax = P + random.randint(0, 2**60)
    nmax2 = cd((Pmax - P + 1) * L, 2**128) - 1
    ok2 = lambda k: P + (k * 2**128) // L <= Pmax
    if nmax2 >= 0 and not (ok2(nmax2) and not ok2(nmax2 + 1)): bad += 1
    f = random.randint(0, D - 1); k = random.randint(0, 2**60)
    xmax = cd((k + 1) * D, D - f) - 1
    net = lambda x: x - cd(x * f, D)
    if not (net(xmax) <= k and net(xmax + 1) > k): bad += 1
print(f"2. DAMM v2 capacities: 60000 checks, {bad} failures")

# 3 ------------------------------------------------------------------------------------------------------------------
worst = 0; tried = 0; worst_ratio = 0.0
for _ in range(300):
    r0i = random.randint(10**9, 10**12); r0o = random.randint(10**9, 10**14)
    r1i = random.randint(10**9, 10**14); r1o = int(r1i * (r0i / r0o) * (1 + random.uniform(0.003, 0.05)))
    fee = 25; den = 10000
    leg = lambda x, ri, ro: ro * (x - cd(x * fee, den)) // (ri + x - cd(x * fee, den))
    prof = lambda x: leg(leg(x, r0i, r0o), r1i, r1o) - x
    g = 1 - fee / den
    A, B, C = g * r0o * g * r1o, r0i * r1i, g * r1i + g * g * r0o
    if A <= B: continue
    tried += 1
    xh = int((math.sqrt(A * B) - B) / C)
    lo, hi = 1, 3 * xh + 10
    while hi - lo > 3:
        m1 = lo + (hi - lo) // 3; m2 = hi - (hi - lo) // 3
        if prof(m1) < prof(m2): lo = m1
        else: hi = m2
    best = max(prof(x) for x in range(max(1, lo - 2000), hi + 2000))
    worst = max(worst, best - prof(xh))
    p0, p1 = r0o / r0i, r1o / r1i
    worst_ratio = max(worst_ratio, (best - prof(xh)) / (2 * (3 + 2 * p1 + p0 * p1)))
print(f"3. CPMM-CPMM closed form: {tried} profitable pool pairs, max(best integer - profit(floor x*)) = {worst} units; max of that / (2*eps), eps = 3 + 2*p1 + p0*p1: {worst_ratio:.3f} (must be <= 1)")
