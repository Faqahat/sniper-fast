#!/usr/bin/env python3
"""verify_dip / handcheck: hand-check selected trades against the RAW collector lines. For each (mint, age): finds the sell,
the trades ahead of our L=35 ms buy, the followers until our exit, re-reads every one of those txs from the raw chunk
files (json line -> base64 TradeEvent decoded here), checks the decoded values equal the tape, and recomputes the PnL step by
step (our buy, followers kept/dropped by the imputed slippage, the exit state, fees, 0.0008 SOL per tx).
usage: python3 -I -B handcheck.py <out.md> <m|age> ...   (or 'auto' to pick 3 winners + 2 losers from the claim's L35 picks)"""
import sys, os, json, gzip, zlib, glob, base64, struct, collections, time, bisect
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import vx_replay as R
R.init("mine")
TE = bytes([189, 219, 127, 211, 78, 230, 97, 238])
RUNDIR = {"R1": "/home/moiz/sniper-data/collect/run_20261021_2207", "R2": "/home/moiz/sniper-data/collect/run_20261022_1543"}
def pkt(t): return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(t + 18000))
def raw_lines(tag, bt, sigs):
    files = sorted(glob.glob(os.path.join(RUNDIR[tag], "txs", "txs_*.jsonl.gz")))
    starts = [int(os.path.basename(f)[4:-9]) for f in files]
    j = max(0, bisect.bisect_right(starts, bt) - 1)
    out = {}
    for f in files[max(0, j - 1):j + 2]:
        try:
            for line in gzip.open(f, "rt"):
                p = line.find('"sig":"')
                sg = line[p + 7:line.find('"', p + 7)]
                if sg in sigs: out[sg] = (os.path.basename(f), json.loads(line))
        except (EOFError, OSError): pass
        if len(out) == len(sigs): break
    return out
def dec_events(o, mint):
    evs = []
    for e in o.get("ev") or []:
        try: raw = base64.b64decode(e + "=" * (-len(e) % 4))
        except Exception: continue
        if raw[:8] != TE: continue
        if R.G["L"].get(mint) is None: continue
        sol, tok = struct.unpack_from("<QQ", raw, 40); buy = raw[56]; vs, vt = struct.unpack_from("<QQ", raw, 97)
        fb = struct.unpack_from("<Q", raw, 161)[0]; cb = struct.unpack_from("<Q", raw, 209)[0]
        evs.append(dict(sol=sol, tok=tok, buy=buy, vsol=vs, vtok=vt, fbps=fb, cbps=cb))
    return evs
def check(key, L=35):
    m, age = key.split("|"); age = float(age); c = R.G["L"][m]; tag = c["run"]
    data = json.load(gzip.open(os.path.join(R.WORK, tag, f"b{zlib.crc32(m.encode()) % 256:03d}.json.gz"), "rt"))
    tr, _ = R.tape(data[m]["t"]); S = c["slot"]
    k = next(j for j, t in enumerate(tr) if not t["buy"] and not t["syn"] and t["sol"] >= R.MIN_SELL and round((t["s"] - S) * R.SMS / 1000, 2) == age)
    t0 = tr[k]; a0 = R.arr(t0); fr = R.fbps(t0)
    ke = k + 1
    while ke < len(tr) and R.arr(tr[ke]) < a0 + L: ke += 1
    s_in = tr[ke - 1]["s"]; E = s_in + 4
    fol = []
    for t in tr[ke:]:
        if t["s"] > E or (t["s"] == E and R.pos_ms(t) >= 75): break
        fol.append(t)
    nxt = next((t for t in tr[ke + len(fol):]), None)
    sigs = {t["sig"] for t in tr[k:ke + len(fol)] if not t["syn"]}
    raw = raw_lines(tag, t0.get("bt", c["bt"]) if False else c["bt"] + int(age), sigs)
    L_ = []
    L_.append(f"### {m[:8]}… age {age:.2f} s ({tag}), sell at {pkt(c['bt'] + age)} PKT")
    L_.append(f"- Token: https://gmgn.ai/sol/token/{m}")
    L_.append(f"- Sell tx: https://solscan.io/tx/{t0['sig']}")
    L_.append(f"- Raw lines found for {len(raw)} of {len(sigs)} txs in the window ({', '.join(sorted({v[0] for v in raw.values()}))}).")
    bad = 0
    for t in tr[k:ke + len(fol)]:
        if t["syn"]: continue
        if t["sig"] not in raw: bad += 1; continue
        fn, o = raw[t["sig"]]
        if o.get("err"): bad += 1
        evs = dec_events(o, m)
        if not any(e["sol"] == t["sol"] and e["tok"] == t["tok"] and e["vsol"] == t["vsol"] and e["vtok"] == t["vtok"] for e in evs): bad += 1
    L_.append(f"- Raw re-decode: every tape row in the window matches a TradeEvent in its raw line, tx not failed: {'yes' if bad == 0 else f'NO ({bad} mismatches)'}")
    p_before = (t0["vsol"] + t0["sol"]) / (t0["vtok"] - t0["tok"]); p_after = t0["vsol"] / t0["vtok"]
    L_.append(f"- Sell: {t0['user'][:8]} sold {t0['tok'] / 1e12:,.2f}M tokens for {t0['sol'] / 1e9:.3f} SOL (slot {t0['s']}, index {t0['i']}, proxy {R.pos_ms(t0):.0f} ms into the slot); "
              f"vsol after {t0['vsol'] / 1e9:.2f} SOL; price drop {p_after / p_before - 1:+.1%}; fee {fr * 1e4:.0f} bps")
    rows = ["| # | slot+ | ms into slot | arrival after sell (ms) | wallet | side | SOL | used? |", "|---|---|---|---|---|---|---|---|"]
    for j, t in enumerate(tr[k + 1:ke], 1):
        rows.append(f"| ahead {j} | {t['s'] - t0['s']} | {R.pos_ms(t):.0f} | {R.arr(t) - a0:.1f} | {t['user'][:8]} | {'buy' if t['buy'] else 'sell'} | {t['sol'] / 1e9:.3f} | ahead of us |")
    V, T = tr[ke - 1]["vsol"], tr[ke - 1]["vtok"]
    X = int(R.B * 1e9 / (1 + fr)); q = T * X // (V + X)
    L_.append(f"- Our buy (L=35 ms -> arrival {a0 + 35 - t0['s'] * R.SMS:.0f} ms into slot {t0['s']}): after {ke - k - 1} trade(s) ahead; curve before our buy vsol {V / 1e9:.4f} SOL / vtok {T / 1e12:,.2f}M tokens; "
              f"0.5 SOL -> {X / 1e9:.4f} SOL to the curve -> {q / 1e12:,.3f}M tokens; curve after our buy vsol {(V + X) / 1e9:.4f} / vtok {(T - q) / 1e12:,.2f}M; "
              f"our average price {X / q / p_after:.4f}x the post-sell price")
    V += X; T -= q; frs = fr; kept = 0; dropped = 0
    for t in fol:
        if t["buy"] and not t["syn"]:
            d = T * t["sol"] // (V + t["sol"]); sl = R.slack(t["sig"]); lim = t["tok"] / (1 + sl)
            if d < lim:
                rows.append(f"| follow | {t['s'] - t0['s']} | {R.pos_ms(t):.0f} | {R.arr(t) - a0:.1f} | {t['user'][:8]} | buy | {t['sol'] / 1e9:.3f} | DROPPED (slack {sl:.3f}) |"); dropped += 1; continue
            V += t["sol"]; T -= d; kept += 1
            rows.append(f"| follow | {t['s'] - t0['s']} | {R.pos_ms(t):.0f} | {R.arr(t) - a0:.1f} | {t['user'][:8]} | buy | {t['sol'] / 1e9:.3f} | kept (slack {sl:.3f}) |")
        elif t["buy"]:
            d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d; kept += 1
            rows.append(f"| follow | {t['s'] - t0['s']} | {R.pos_ms(t):.0f} | {R.arr(t) - a0:.1f} | gap-fill | buy | {t['sol'] / 1e9:.3f} | synthetic |")
        else:
            so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]; kept += 1
            rows.append(f"| follow | {t['s'] - t0['s']} | {R.pos_ms(t):.0f} | {R.arr(t) - a0:.1f} | {t['user'][:8]} | sell | {t['sol'] / 1e9:.3f} | kept |")
        frs = R.fbps(t)
    so = V * q // (T + q); pnl = so * (1 - frs) / 1e9 - R.B - 0.0016
    L_.append(f"- Exit: slot {E} (= slot of the last trade ahead + 4), before the first trade at >= 75 ms into it"
              + (f" (next trade: slot+{nxt['s'] - t0['s']}, {R.pos_ms(nxt):.0f} ms)" if nxt else "") + f"; {kept} followers applied, {dropped} dropped")
    L_.append(f"- Curve at our sell: vsol {V / 1e9:.4f} SOL / vtok {T / 1e12:,.2f}M tokens; our tokens sell for {so / 1e9:.4f} SOL, minus {frs * 1e4:.0f} bps fees = {so * (1 - frs) / 1e9:.4f}; "
              f"minus 0.5 and 2 x 0.0008 -> **PnL {pnl:+.4f} SOL**")
    L_ += [""] + rows + [""]
    return "\n".join(L_), pnl
if __name__ == "__main__":
    outp = sys.argv[1]; keys = sys.argv[2:]
    if keys == ["auto"]:
        sel = json.load(open(os.path.join(HERE, "out", "cv_claim_b05.json")))["35"]["sel"]
        sel = [s for s in sel if s["run"] == "R2"]; sel.sort(key=lambda s: s["pnl"]); n = len(sel)
        pick = [sel[int(n * 0.97)], sel[int(n * 0.85)], sel[int(n * 0.65)], sel[int(n * 0.25)], sel[int(n * 0.05)]]
        keys = [f"{s['m']}|{s['age']}" for s in pick]
        claim = {f"{s['m']}|{s['age']}": s["pnl"] for s in pick}
    else:
        claim = {}
    txt = []
    for k in keys:
        t, p = check(k); txt.append(t + (f"- Claim's PnL for this trade (ev4_b05, L35, exit 4): {claim[k]:+.4f} SOL\n" if k in claim else ""))
    open(outp, "w").write("\n".join(txt)); print("\n".join(txt))
