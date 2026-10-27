#!/usr/bin/env python3
# MODEL CHECK step 2: real bot dip buys vs the model's replays of them (trades_<day>.jsonl.gz from m1_trades.py).
# All P&L in SOL, pump fees in; tx costs (fee + tips) from txc_<run>.npz when present (real bots), our FIX otherwise.
# usage: nice python3 -I m2_analyze.py [--tx]   -> prints tables; writes m2_rows.npz for later steps
import sys, os, json, gzip, zlib, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
OUT = "/home/moiz/sniper-data/modelcheck"
BANDS = [(0, 10), (10, 35), (35, 50), (50, 75), (75, 401)]
BN = ["0-10", "10-35", "35-50", "50-75", "75+"]
FOCUS = ["HkQ7hMjy", "haqqiUUX", "DYXDDrZC", "ETwEAQPL", "sssssDdM", "ssssswdk", "EMKY7r6U", "9pQQc1xy", "BUkpShoE", "3MHgGwdL", "5mWe9kLZ", "CZ77onJz",
         "omegoMAe", "E2x1ewwX", "6VzXcLk9", "5k2Ckkiu"]

def clients():
    lb = json.load(open("/home/moiz/sniper/ops/overnight/dipshadow/leaders_book.json"))["leaders"]
    sc = json.load(open("/home/moiz/sniper/ops/dip/speed/leaders/schedule_cur.json"))
    pk = {r["pk"]: r["client"] for r in json.load(open("/home/moiz/sniper-data/leader_geo.json"))["rows"]}
    def f(s):
        u = lb.get(str(s))
        if u is None and sc["start"] <= s < sc["start"] + len(sc["slot_leader"]): u = sc["ids"][sc["slot_leader"][s - sc["start"]]]
        return pk.get(u, "?") if u else "?"
    return f

def load(days=("R1", "R2", "R3", "R4"), tx=False):
    R = []; seen = set()
    for day in days:
        for l in gzip.open(f"{OUT}/trades_{day}.jsonl.gz", "rt"):
            r = json.loads(l)
            key = (r["m"], r["w"], r["s"], r["i"])
            if key in seen: continue            # R3 / R4 overlap
            seen.add(key); R.append(r)
    if tx:
        TX = {}
        for run in days:
            p = f"{OUT}/txc_{run}.npz"
            if not os.path.exists(p): continue
            z = np.load(p)
            for s, i, w, ok, fee, tips, sd in zip(z["s"].tolist(), z["i"].tolist(), z["w"].tolist(), z["ok"].tolist(), z["fee"].tolist(), z["tips"].tolist(), z["sd"].tolist()):
                TX[(s, i, w)] = (fee + tips, ok, sd)
        for r in R:
            w = zlib.crc32(r["w"].encode())
            b = TX.get((r["s"], r["i"], w)); r["txb"] = b[0] / 1e9 if b else None
            sc = 0.0; okc = True
            for s, i, f in r["sells"]:
                x = TX.get((s, i, w))
                if x is None: okc = False; continue
                sc += x[0] / 1e9 * min(1.0, f)        # a sell tx closing several lots: pro rata (approx by the lot's fraction)
            r["txs"] = sc if okc else None
    return R

def stat(v):
    v = np.asarray([x for x in v if x is not None], float)
    if not len(v): return "n 0"
    return f"n {len(v):6d} mean {v.mean() * 1000:+7.2f} med {np.median(v) * 1000:+7.2f} sum {v.sum():+8.2f}"

def main():
    tx = "--tx" in sys.argv
    R = load(tx=tx); cl = clients()
    for r in R:
        r["band"] = next(b for (lo, hi), b in zip(BANDS, BN) if lo <= r["L"] < hi)
        r["cli"] = cl(r["s"]); r["w8"] = r["w"][:8]
    C = [r for r in R if r["closed"] and r["I_real"] is not None]
    print(f"bot dip buys {len(R)} (closed lots {len(C)}), wallets {len({r['w'] for r in R})}, P&L in mSOL per trade (pump fees in, no tx costs)")
    print("\n== 1. IDENTITY: the model replays the bot's own trade (same spot, same SOL, same sell rows) -- model minus real")
    print("  real P&L           :", stat([r["real"] for r in C]))
    print("  model (same rows)  :", stat([r["I_real"] for r in C]))
    print("  model - real       :", stat([r["I_real"] - r["real"] for r in C]))
    e = np.array([r["I_real"] - r["real"] for r in C]); print(f"  |error| < 0.1 mSOL: {np.mean(np.abs(e) < 1e-4):.1%}; < 1 mSOL {np.mean(np.abs(e) < 1e-3):.1%}; entry tokens model/real mean {np.mean([r['I_q'] for r in C]):.6f}")
    print("\n== 2. EXIT LANDING: our sell at 75 ms into the same slot as each real sell (model) vs the real sell row")
    for lab, k in (("first in slot (0 ms)", "I_0"), ("75 ms (model)", "I_75"), ("150 ms", "I_150")):
        print(f"  {lab:22s}: model - real", stat([r[k] - r["I_real"] for r in C]))
    pos = [i / max(400, i + 1) * 212 for r in C for s, i, f in r["sells"]]
    print(f"  real sells: position in slot (block-position ms) p10/25/50/75/90: " + " / ".join(f"{np.percentile(pos, p):.0f}" for p in (10, 25, 50, 75, 90)))
    print("\n== 3. EXIT POLICY (same real entry): the model's exits vs the bot's own exit")
    for lab, k in (("c2", "I_c2"), ("c4", "I_c4"), ("c6 SL10", "I_c6"), ("c9", "I_c9"), ("c19", "I_c19")):
        print(f"  {lab:8s}: model exit  ", stat([r[k] for r in C]), "| minus real", stat([r[k] - r["real"] for r in C]))
    print("\n== 4. EXTRA BUYER: ours inserted right BEFORE the bot, the bot kept (paper situation) vs ours replacing the bot")
    for lab, a, b in (("c4", "X_c4", "I_c4"), ("c6 SL10", "X_c6", "I_c6")):
        print(f"  {lab:8s}: extra - replace", stat([r[a] - r[b] for r in C]), f"| model dropped the bot's buy {np.mean([r['X_botdrop'] for r in C]):.1%}")
    # ---- by band / client / wallet
    def table(key, keys, rows, title):
        print(f"\n== {title}")
        print(f"  {'group':14s} {'n':>6s} {'SOL in':>8s} | {'real':>7s} {'real/SOL':>8s} | {'ident.err':>9s} | {'75ms-real':>9s} | {'c4':>7s} {'c6':>7s} | {'X-I c4':>7s} | {'drop':>5s} | {'txc':>6s} {'net':>7s}")
        for g in keys:
            v = [r for r in rows if r[key] == g]
            if len(v) < 30: continue
            sol = sum(r["cost"] for r in v)
            m = lambda k: np.mean([r[k] for r in v]) * 1000
            txs = [r["txb"] + r["txs"] for r in v if r.get("txb") is not None and r.get("txs") is not None]
            txc = np.mean(txs) * 1000 if txs else float("nan")
            print(f"  {g:14s} {len(v):6d} {sol:8.1f} | {m('real'):+7.2f} {sum(r['real'] for r in v) / sol * 100:+7.2f}% | {np.mean([r['I_real'] - r['real'] for r in v]) * 1000:+9.3f} | "
                  f"{np.mean([r['I_75'] - r['I_real'] for r in v]) * 1000:+9.3f} | {m('I_c4'):+7.2f} {m('I_c6'):+7.2f} | {np.mean([r['X_c4'] - r['I_c4'] for r in v]) * 1000:+7.2f} | "
                  f"{np.mean([r['X_botdrop'] for r in v]):5.1%} | {txc:6.2f} {m('real') - txc:+7.2f}")
    table("band", BN, C, "BY LATENCY BAND (bot's landing after the dump, block-position ms); mSOL per trade unless %")
    table("cli", [c for c, _ in collections.Counter(r["cli"] for r in C).most_common()], C, "BY LEADER CLIENT (slot of the bot's buy)")
    table("w8", FOCUS + [w for w, _ in collections.Counter(r["w8"] for r in C).most_common(40) if w not in FOCUS], C, "BY WALLET")
    for lab, f in (("in envelope", lambda r: r["pf"] and r["pf"]["env"]), ("IMIT1 top4 dumps", lambda r: r["pf"] and r["pf"]["top4"]),
                   ("M2 pick dumps", lambda r: r["pf"] and r["pf"]["m2"])):
        v = [r for r in C if f(r)]
        for r in v: r["_g"] = r["band"]
        table("_g", BN, v, f"{lab.upper()}: by latency band")
    np.save(f"{OUT}/m2_cache.npy", np.array([0]))

if __name__ == "__main__":
    main()
