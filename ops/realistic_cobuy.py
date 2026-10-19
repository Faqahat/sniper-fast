import json, statistics

OBSERVE_MS = 1095  # when the demand gate confirms (~1 slot)
CAP_MS = 40000
DERISK = 0.30
RIDE = 1.15
TRAIL = 0.95
FEE = 0.015  # ~1.5% round-trip friction (pump fee + slippage both legs)


def entry_and_fwd(path, fill_penalty):
    # entry r = price at observe_ms (realistic demand-confirmed entry), times a fill penalty for our rank
    e = None
    for t, r in path:
        if t >= OBSERVE_MS:
            e = r
            break
    if e is None:
        e = path[-1][1]
    entry = e * fill_penalty
    fwd = [(t - OBSERVE_MS, r) for t, r in path if t >= OBSERVE_MS]
    return entry, fwd


def sim(entry, fwd):
    if not fwd or entry <= 0:
        return None
    rem = 0.70
    real = 0.0  # 30% derisked at entry = 0 gain
    peak = entry
    armed = False
    for t, r in fwd:
        if t > CAP_MS:
            real += rem * (r / entry - 1)
            rem = 0
            break
        if r > peak:
            peak = r
        if r >= RIDE * entry:
            armed = True
        if armed and r <= TRAIL * peak:
            real += rem * (r / entry - 1)
            rem = 0
            break
    if rem > 0:
        real += rem * (fwd[-1][1] / entry - 1)
    return real - FEE  # subtract round-trip friction


for label, fp in [("entry = demand-confirm price (rank 0/no penalty)", 1.00),
                  ("entry = demand-confirm x1.05 (our ~rank-2 fill)", 1.05),
                  ("entry = demand-confirm x1.10 (worse fill)", 1.10)]:
    pnls = []
    rows = []
    for line in open("/root/arbx-fast/paths_cobuy.jsonl"):
        d = json.loads(line)
        entry, fwd = entry_and_fwd(d["path"], fp)
        p = sim(entry, fwd)
        if p is not None:
            pnls.append(p)
            rows.append((d["mint"][:8], d["dev"], entry, p))
    n = len(pnls)
    wins = sum(1 for x in pnls if x > 0)
    print(f"=== {label} ===")
    print(f"  n={n}  mean={sum(pnls)/n:+.3f}  median={statistics.median(pnls):+.3f}  win%={wins/n*100:.0f}  total={sum(pnls):+.2f} SOL")

# detail at the realistic x1.05
print("\nper-token (entry=demand-confirm x1.05):")
for line in open("/root/arbx-fast/paths_cobuy.jsonl"):
    d = json.loads(line)
    entry, fwd = entry_and_fwd(d["path"], 1.05)
    p = sim(entry, fwd)
    peak = max(r for _, r in d["path"])
    if p is not None:
        print(f"  {d['mint'][:8]} dev={d['dev']:.1f} entry={entry:.2f}x peak={peak:.2f}x -> {p:+.3f} SOL")
