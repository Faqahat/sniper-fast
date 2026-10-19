#!/usr/bin/env python3
# READ-ONLY. Score a forward PAPER run of the race gate against the chain.
# usage: fwd_eval.py <paper.log> <onchain.jsonl> <paths.jsonl> [window_ms_of_the_gate]
# - per launch the engine logged RACE seen (create features), RACE decide (gate), RACE obs (outsiders seen in the stream);
# - onchain.jsonl (onchain.py) holds block S + S+1..S+8 -> race labels (race_lib.labels), 4yFAz, and the S/S+1 price path;
# - paths.jsonl (engine --dump-paths, fired + shadow) extends the path to 40 s (approx. time-aligned, see notes).
import sys, re, json, statistics as st, collections
sys.path.insert(0, "/root/race")
from race_lib import labels, path_pts, W, bad_events

LOG, OC, PATHS = sys.argv[1], sys.argv[2], sys.argv[3]
GATE_W = float(sys.argv[4]) if len(sys.argv) > 4 else 100.0
K = 30.0 * 1.073e9
FEE, PRIO_RT = 0.0125, 0.0013
ENGINE_T0_MS = 200.0   # calibrated: engine 250 ms curve polls vs chain trades, best fit at +200 ms after the create (217 ms slots)
pros = frozenset(json.load(open("/root/race/pros.json")))


def kv(line):
    return dict(re.findall(r"(\w+)=([^\s]+)", line))


seen, dec, obs = {}, {}, {}
for l in open(LOG, errors="replace"):
    if "RACE seen" in l:
        d = kv(l)
        seen.setdefault(d["mint"], d)
    elif "RACE decide" in l:
        d = kv(l)
        dec[d["mint"]] = d
    elif "RACE obs" in l:
        d = kv(l)
        outs = []
        if d.get("outs", "-") != "-":
            for x in d["outs"].split(","):
                p = x.split(":")
                if len(p) >= 3:
                    outs.append((float(p[0]), float(p[1]), p[2] == "1", p[3] if len(p) > 3 else ""))
        d["outs_l"] = outs
        obs[d["mint"]] = d
oc = {}
for l in open(OC):
    try:
        r = json.loads(l)
    except Exception:
        continue
    oc[r["mint"]] = r
eng = {}
for l in open(PATHS):
    try:
        r = json.loads(l)
    except Exception:
        continue
    eng[r["mint"]] = r
print(f"engine log: RACE seen {len(seen)} | decide {len(dec)} | obs {len(obs)} | on-chain records {len(oc)} | engine paths {len(eng)}")

rows = []
miss = collections.Counter()
for m, f in seen.items():
    r = oc.get(m)
    if not r or "b" not in r or "csig" not in (r.get("b") or {}):
        miss["no block"] += 1
        continue
    b, s = r["b"], r.get("s")
    if not s or "sig_err" in s:
        miss["no s1"] += 1
        continue
    if not b.get("base") or bad_events(b, s):
        miss["non-SOL quote / zero-vsol events (excluded)"] += 1
        continue
    if eng.get(m) and eng[m].get("path") and max(rb for _, rb in eng[m]["path"]) >= 19.99:
        miss["engine curve read hit the 20x cap (excluded)"] += 1
        continue
    o = labels(b, s, pros)
    o["mint"] = m
    o["slot"] = r["slot"]
    o["dev"] = int(f.get("dev", 0)) / 1e9
    o["dev_sized"] = int(f.get("dev_sized", 0)) / 1e9
    o["kind"] = int(f.get("kind", 0))
    o["host"] = f.get("host")
    o["name_len"] = int(f.get("name_len", 99))
    o["luts"] = int(f.get("luts", 0))
    o["v1"] = f.get("v1") == "true"
    o["nsig"] = int(f.get("nsig", 0))
    o["cu_price"] = int(f.get("cu_price", 0))
    o["tip"] = int(f.get("tip", 0))
    o["tip_to"] = f.get("tip_to", "-")
    o["glued"], o["gsol"] = b.get("glued", 0), (b.get("gsol") or 0) / 1e9
    o["base"] = b.get("base")
    pts, mpt = path_pts(b, s)
    o["ms_per_tx"] = mpt
    # extend with the engine's 40 s path (price/floor ratio -> vsol = base * sqrt(ratio))
    e = eng.get(m)
    if e and e.get("path"):
        last_t = pts[-1][0] if pts else 0
        for ms, rb in e["path"]:
            t = ENGINE_T0_MS + ms
            if t > max(last_t, 6 * 217.0):
                pts.append([round(t), o["base"] * max(rb, 1e-6) ** 0.5])
    pts.sort(key=lambda z: z[0])
    o["path"] = pts
    o["has_path"] = bool(e)
    o["sv"] = [(x["d"], x["ev"][-1][4]) for x in b.get("later") or [] if x.get("ok") and x["ev"]]
    his = any(o["outS_his"]) or any(x.get("payer") == W or any(ev[1] == W for ev in x.get("ev") or []) for x in (s.get("rows") or []))
    o["his"] = his
    dd = dec.get(m, {})
    o["fired"] = dd.get("pass") == "true" if dd else (obs.get(m, {}).get("fired") == "true")
    ob = obs.get(m, {})
    o["eng_outs"] = ob.get("outs_l", [])
    o["eng_n100"] = int(ob.get("n100", 0) or 0)
    o["eng_sol100"] = float(ob.get("sol100", 0) or 0)
    o["eng_bundle"] = int(ob.get("bundle_n", 0) or 0)
    rows.append(o)
print("unmatched:", dict(miss), "| scored launches:", len(rows))


def RACE(o):
    return o["out2s_nx"] >= 3 and o["out2s_solx"] >= 3


def entry_vsol(o, d_land):
    v = o["base"]
    for d, vs in o["sv"]:
        if d <= d_land:
            v = vs
        else:
            break
    return v


def sim(o, d_land, tp=None, T=1000, size=1.0):
    ve, t0 = entry_vsol(o, d_land) / 1e9, d_land * o["ms_per_tx"]
    s_in = size * (1 - FEE)
    tok = K / ve - K / (ve + s_in)
    vx = ve
    for t, v in o["path"]:
        if t <= t0:
            continue
        if t - t0 > T:
            break
        vx = v / 1e9
        if tp and (vx / ve) ** 2 >= tp:
            break
    vq = vx + s_in
    out = (vq - K / (K / vq + tok)) * (1 - FEE)
    return (out - size - PRIO_RT) / size, (ve * 1e9 / o["base"]) ** 2


def eng_win(o, ms, min_n=1, min_sol=0.0):
    xs = [x for x in o["eng_outs"] if x[0] <= ms]
    return len({x[3] for x in xs}) >= min_n and sum(x[1] for x in xs) >= min_sol


def stats(v):
    if not v:
        return "n=0"
    ex = sorted(v)[:-3] if len(v) > 12 else v
    return f"avg {st.mean(v):+.1%} med {st.median(v):+.1%} ex-top3 {st.mean(ex):+.1%} win {sum(x > 0 for x in v) / len(v):.0%}"


old = lambda o: 0.5 <= o["dev_sized"] <= 8
GROUPS = [
    ("ALL base launches (dev-from-cap, 0.5-8 SOL, host ok, vanilla)", lambda o: True, 0),
    ("OLD filter subset (sized dev 0.5-8)", old, 0),
    ("  cap-family dev launches (the fixed bug)", lambda o: o["kind"] >= 2, 0),
    (f"RACE GATE FIRED (engine decision, wait {GATE_W:.0f} ms)", lambda o: o["fired"], GATE_W),
    ("RACE GATE rejected", lambda o: not o["fired"], 0),
    ("alt: >=1 outsider & >=0.5 SOL in 50 ms (engine stream)", lambda o: eng_win(o, 50, 1, 0.5), 50),
    ("alt: >=2 SOL outside in 100 ms (engine stream)", lambda o: eng_win(o, 100, 1, 2.0), 100),
    ("alt: >=2 outsiders & >=2 SOL in 100 ms (engine stream)", lambda o: eng_win(o, 100, 2, 2.0), 100),
    ("alt B: dev>=2 & creator bundle>=1 SOL (chain glued run)", lambda o: o["dev"] >= 2 and o["gsol"] >= 1, 1),
    ("alt A: dev>=2", lambda o: o["dev"] >= 2, 0),
    ("GATE B: dev>=3 & creator bundle>=2 tx & name<=12 (~3 ms)", lambda o: o["dev"] >= 3 and o["glued"] >= 2 and o["name_len"] <= 12, 3),
    ("  B without the name rule: dev>=3 & bundle>=2 tx", lambda o: o["dev"] >= 3 and o["glued"] >= 2, 3),
    ("4yFAz bought (S..S+5)", lambda o: o["his"], 0),
    ("HINDSIGHT: RACE=1", RACE, 0),
]
print(f"\n{'group':62} {'n':>4} | race | S+S1>=2 | med out01 | med 2sSOL | 4yFAz | entry med | PnL X1 (sell +1 s) land S @<=100+wait | X2 tp1.3/10s (engine path)")
for gn, fn, wait in GROUPS:
    g = [o for o in rows if fn(o)]
    if not g:
        print(f"{gn:62} {0:4}")
        continue
    dl = lambda o: 100 + int(wait / o["ms_per_tx"])
    v1 = [sim(o, dl(o))[0] for o in g]
    fills = [sim(o, dl(o))[1] for o in g]
    gp = [o for o in g if o["has_path"]]
    v2 = [sim(o, dl(o), tp=1.3, T=10000)[0] for o in gp]
    print(f"{gn[:62]:62} {len(g):4} | {sum(RACE(o) for o in g) / len(g):4.0%} | {sum(o['out01_nx'] >= 2 for o in g) / len(g):7.0%} | "
          f"{st.median(o['out01_nx'] for o in g):9.1f} | {st.median(o['out2s_solx'] for o in g):9.2f} | {sum(o['his'] for o in g):5} | "
          f"{st.median(fills):8.2f}x | {stats(v1)} | n={len(gp)} {stats(v2)}")

print("\n-- landing sensitivity, exit X1: avg PnL when we land behind the first d txs of S (+ the group's wait)")
for gn, fn, wait in GROUPS:
    g = [o for o in rows if fn(o)]
    if len(g) < 5:
        continue
    cells = []
    for d in (5, 25, 50, 100, 200):
        v = [sim(o, d + int(wait / o["ms_per_tx"]))[0] for o in g]
        cells.append(f"d{d} {st.mean(v):+.1%}")
    print(f"   {gn[:60]:60} n={len(g):4}  " + "  ".join(cells))

# stream signal vs chain: does what the engine saw in 100 ms match the chain?
print("\n-- engine stream (100 ms) vs chain (S): outsiders seen by the engine within 100 ms vs chain outsiders at offset <= 100 ms")
pairs = []
for o in rows:
    chain = len([d for d in o["outS_d"] if d * o["ms_per_tx"] <= 100])
    pairs.append((o["eng_n100"], chain))
agree = sum(1 for a, c in pairs if (a > 0) == (c > 0))
print(f"   launches {len(pairs)} | engine saw >=1: {sum(a > 0 for a, _ in pairs)} | chain had >=1: {sum(c > 0 for _, c in pairs)} | agree on (>=1) {agree / max(1, len(pairs)):.0%}")
# per fired launch: what the chain says
print("\n-- per FIRED launch (gate pass), verified on chain: outside buyers excl. 4yFAz in S / S+S1 / 2 s, outside SOL 2 s, race, 4yFAz, bundle")
for o in sorted([o for o in rows if o["fired"]], key=lambda o: o["slot"]):
    print(f"   {o['mint'][:10]} slot {o['slot']} dev {o['dev']:5.2f} kind {o['kind']} | outS {o['outS_nx']:2} S+S1 {o['out01_nx']:2} 2s {o['out2s_nx']:2} | 2s SOL {o['out2s_solx']:6.2f} | "
          f"race {'Y' if RACE(o) else '-'} | 4yFAz {'Y' if o['his'] else '-'} | bundle {o['glued']}/{o['gsol']:.1f} | engine sol100 {o['eng_sol100']:.2f} | X1@100+w {sim(o, 100 + int(GATE_W / o['ms_per_tx']))[0]:+.1%}")
# create-time engine features (not in the historical set): race rate by LUT use, v1 tx, signers, tip
try:
    sys.path.insert(0, "/root/indep")
    from common import load_tipmap
    tm = load_tipmap()
except Exception:
    tm = {}
print("\n-- create-tx features logged by the engine (forward only): race rate by feature (n)")
feats = {"luts>0": lambda o: o["luts"] > 0, "luts=0": lambda o: o["luts"] == 0, "v1 tx": lambda o: o["v1"], "not v1": lambda o: not o["v1"],
         "nsig=1": lambda o: o["nsig"] == 1, "nsig>=2": lambda o: o["nsig"] >= 2, "cu_price>=1M": lambda o: o["cu_price"] >= 1_000_000,
         "cu_price<100k": lambda o: o["cu_price"] < 100_000, "sender tip (known tip acct)": lambda o: o["tip_to"] in tm,
         "other SOL transfer (launchpad fee?)": lambda o: o["tip"] > 0 and o["tip_to"] not in tm, "no transfer": lambda o: o["tip"] == 0,
         "dev kind sized": lambda o: o["kind"] == 1, "dev kind cap": lambda o: o["kind"] == 2, "dev kind cap-unlimited": lambda o: o["kind"] == 3}
for fn_, fn in feats.items():
    g = [o for o in rows if fn(o)]
    if g:
        print(f"   {fn_:36} n={len(g):4} race {sum(RACE(o) for o in g) / len(g):4.0%}  4yFAz {sum(o['his'] for o in g)}")
tips = collections.Counter(tm.get(o["tip_to"], "other") for o in rows if o["tip"] > 0)
print("   create-tx transfer destinations:", dict(tips.most_common(8)))
json.dump([{k: v for k, v in o.items() if k not in ("path", "sv")} for o in rows], open(LOG.replace(".log", "_eval.json"), "w"))
