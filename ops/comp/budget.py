# READ-ONLY offline. Task 6: day budget for >= $500/day from the simulated per-launch PnL.
import sys, json, statistics as st, random, math, collections, glob
SET = sys.argv[1] if len(sys.argv) > 1 else "r2"
EXIT = sys.argv[2] if len(sys.argv) > 2 else "T3"
SELL_FEE = 0.002
SOLPX = json.load(open("/root/solprice.json")).get("price", 104)
D = json.load(open(f"/root/comp/sim_{SET}.json"))
SIZES = [0.25, 0.5, 1.0, 2.0, 3.0]
rnd = random.Random(3)
# --- fire-rate inputs ---
R2_PER_H = float(sys.argv[3]) if len(sys.argv) > 3 else 61.8      # [M] on-chain rule-#2 launches per hour (1271 in 20.55 h)
GATE = 0.34 * 0.68                                                 # [M] close-leader slot share x create<=150ms share
FIRES = {"gated (on-chain rate x gates)": R2_PER_H * 24 * GATE, "gated (live measured 7.7/h)": 7.7 * 24, "ungated (all rule-#2)": R2_PER_H * 24}

def pnl(r, sc, x, land, ex=EXIT):
    if sc == "today":   # [M-input] ~3/4 land in S at ~+100, 1/4 in S+1
        return 0.75 * pnl(r, "d100", x, land, ex) + 0.25 * pnl(r, "s1", x, land, ex)
    if sc == "today_bad":  # [M] earlier live record: 38% in S
        return 0.38 * pnl(r, "d100", x, land, ex) + 0.62 * pnl(r, "s1", x, land, ex)
    v = r["r"][f"{sc}|{x}"]["ex"][ex]
    return v[0] - x - land - SELL_FEE * v[2]

def day_dist(v, n, iters=3000):
    out = []
    for _ in range(iters):
        k = n  # fixed number of fires per day (Poisson noise ignored)
        out.append(sum(v[rnd.randrange(len(v))] for _ in range(int(k))))
    out.sort()
    return out

print(f"exit {EXIT}; SOL ${SOLPX:.1f}; launches {len(D)}")
print("fires/day:", {k: round(v) for k, v in FIRES.items()})
SC = [("d8", 0.045, "+8 (fast lane), comp-level fee 0.045"), ("d25", 0.045, "+25 / first outsider, fee 0.045"), ("d25", 0.006, "+25, fee 0.006"),
      ("today", 0.006, "today: 3/4 S@+100, 1/4 S+1, fee 0.006"), ("today_bad", 0.006, "old live record: 38% S, fee 0.006")]
nf = FIRES["gated (on-chain rate x gates)"]; nf2 = FIRES["gated (live measured 7.7/h)"]
print(f"\n{'scenario':42} {'size':>5} {'mean/trade':>10} {'90%CI lo':>8} {'SOL/day@'+str(round(nf)):>12} {'$/day':>7} {'$/day lo':>8} {'P50 day $':>9} {'P5 day $':>8} {'P(>=$500)':>9} {'$/day@'+str(round(nf2)):>10}")
best = {}
for sc, land, name in SC:
    for x in SIZES:
        v = [pnl(r, sc, x, land) for r in D]
        m = st.mean(v)
        bs = sorted(st.mean([v[rnd.randrange(len(v))] for _ in range(len(v))]) for _ in range(800))
        lo = bs[40]
        dd = day_dist(v, nf, 1500)
        p50, p5 = dd[len(dd) // 2], dd[int(len(dd) * 0.05)]
        p500 = sum(1 for d in dd if d * SOLPX >= 500) / len(dd)
        print(f"{name:42} {x:5.2f} {m:10.4f} {lo:8.4f} {m*nf:12.2f} {m*nf*SOLPX:7.0f} {lo*nf*SOLPX:8.0f} {p50*SOLPX:9.0f} {p5*SOLPX:8.0f} {p500:9.2f} {m*nf2*SOLPX:10.0f}")
# concurrency / capital: ALL on-chain rule-#2 launch slots (1271), thinned by the gate share, hold H seconds
BOT = {"gg.sc", "ipfs.launchblitz.ai", "pf.jake-98f.workers.dev", "storage.googleapis.com"}
seen = {}
for fn in sorted(glob.glob("/root/race/*_onchain.jsonl")):
    for l in open(fn):
        try: r = json.loads(l)
        except Exception: continue
        b = r.get("b") or {}
        if "dev" not in b or r["mint"] in seen: continue
        host = (b.get("uri") or "").split("://")[-1].split("/")[0]
        dev = b["dev"] / 1e9; gs = b.get("gsol", 0) / 1e9
        moon = any(str(x[2]).startswith("moon") for x in b.get("tips", []))
        ok = 0.49 <= dev <= 8.1 and not (host in BOT or host.endswith(".trycloudflare.com")) and "CreateV2" in (b.get("ins") or []) and 2.95 <= gs <= 5.05 and moon
        seen[r["mint"]] = b["slot"] if ok else None
ts = sorted(s for s in seen.values() if s)
for hold_s, gate in ((30, GATE), (30, 1.0), (60, GATE)):
    mx = []
    for _ in range(100):
        sel = [s for s in ts if rnd.random() < gate]
        j = 0; m = 0
        for i in range(len(sel)):
            while sel[i] - sel[j] > hold_s / 0.4: j += 1
            m = max(m, i - j + 1)
        mx.append(m)
    print(f"max concurrent positions over the {len(ts)}-launch / 20.5 h record (hold {hold_s}s, gate share {gate:.2f}): median {st.median(mx)}, p95 {sorted(mx)[int(len(mx)*0.95)]}")
