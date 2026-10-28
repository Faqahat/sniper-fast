#!/usr/bin/env python3
"""REARM step 10 (read-only; G2): hand-checkable examples of re-arm fills ON the next whale dump (the trade the rule is for), with the
real signatures of the paid dump that armed the window and of the whale dump we buy, looked up in the raw recordings
(/home/moiz/sniper-data/collect/run_*/txs/txs_<unix>.jsonl.gz, line head {"s":slot,"i":idx,...,"sig":...}). Our own fill is a
REPLAY fill (INFERRED: slot and fractional tx index from the landing model); the dumps, the curve and haqq's buys are MEASURED tape.
GMGN: https://gmgn.ai/sol/token/<MINT>; Solscan: https://solscan.io/tx/<SIG>.
usage: r10_examples.py TAG CFG DAYS [--n 8] [--out examples.txt]"""
import sys, os, glob, gzip, pickle, re, subprocess, json, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import rlib
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/rearm"
COST = 2_015_140
HAQQ = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
FILES = sorted((int(re.search(r"txs_(\d+)", f).group(1)), f) for f in glob.glob("/home/moiz/sniper-data/collect/run_2026*/txs/txs_*.jsonl.gz"))


def find_sig(slot, idx, bt):
    """the tx at (slot, idx) in the recordings: try the chunks that start <= bt (latest first)"""
    cands = [f for t, f in FILES if t <= bt + 5][-3:][::-1]
    pat = f'{{"s":{slot},"i":{idx},'
    for f in cands:
        try:
            r = subprocess.run(f"zcat '{f}' 2>/dev/null | grep -m1 -F '{pat}'", shell=True, capture_output=True, text=True, timeout=120).stdout
        except Exception: continue
        if r:
            m = re.search(r'"sig":"([1-9A-HJ-NP-Za-km-z]+)"', r)
            if m: return m.group(1)
    return None


def main(tag, cfg, days, n, outf):
    picks = []
    for d in days:
        fn = f"{OUT}/res_D{d}_{tag}.pkl"
        if not os.path.exists(fn): continue
        Z = pickle.load(open(fn, "rb"))
        if cfg not in Z["out"]: continue
        EV = pickle.load(open(f"{OUT}/ev_D{d}.pkl", "rb"))["EV"]
        evk = {(e["mint"], e["slot"], e["idx"]): e for e in EV}
        G_ = int(cfg.split(":")[1])
        for r in Z["out"][cfg][0]:
            k = r[0]
            if k[0] != "re" or not r[3]: continue
            src = k[6]; e = evk.get((k[1], src[0], src[1]))
            if e is None or e["nxt"] is None: continue
            nx = e["nxt"]
            if not (nx[0] <= k[2] + G_ and nx[0] <= r[8][0] <= nx[0] + 1): continue
            e2 = evk.get((k[1], nx[0], nx[1]))
            picks.append((d, k, r, e, e2))
    rng = np.random.default_rng(7)
    win = [p for p in picks if p[2][8][2]["base"][0] - COST > 0]; lose = [p for p in picks if p[2][8][2]["base"][0] - COST <= 0]
    # a fair sample: winners and losers in their real proportion (at least 2 losers), spread over days
    nl = max(2, int(round(n * len(lose) / max(len(picks), 1)))); nw = n - nl
    sel = [win[i] for i in sorted(rng.choice(len(win), min(nw, len(win)), replace=False))] + [lose[i] for i in sorted(rng.choice(len(lose), min(nl, len(lose)), replace=False))]
    Lo = []; TP = {}
    def P(s=""): print(s, flush=True); Lo.append(s)
    P(f"# Re-arm example fills ON the next whale dump (window armed by the previous whale dump; X=any means no paid check), config {cfg}, tag {tag}; sample of {len(sel)} from {len(picks)} such fills ({len(win)} winners / {len(lose)} losers, model NOW)")
    P("Our fill = REPLAY (INFERRED). Dumps, prices, haqq's buys = MEASURED tape. P&L: model NOW costs; cal = 0.81 x if > 0.")
    for d, k, r, e, e2 in sel:
        if d not in TP: TP[d] = rlib.Tape(tab=f"{OUT}/tab_D{d}", with_ours=False)
        tp = TP[d]; hid = tp.ids.index(HAQQ) if HAQQ in tp.ids else -1
        a_, e_ = tp.span[tp.id_map()[k[1]]]
        sl = slice(a_, e_)
        hq = [(int(s_), int(i_)) for s_, i_, u_, b_ in zip(tp.s[sl], tp.i[sl], tp.user[sl], tp.buy[sl]) if u_ == hid and b_ and e["nxt"][0] <= s_ <= e["nxt"][0] + 1]
        nb = sum(1 for s_, i_, b_ in zip(tp.s[sl], tp.i[sl], tp.buy[sl]) if b_ and (s_, i_) > (e["nxt"][0], e["nxt"][1]) and s_ <= e["nxt"][0] + 2)
        g = (r[8][2]["base"][0] - COST) / 1e9; gw = (r[8][2]["wave"][0] - COST) / 1e9
        sig_paid = find_sig(e["slot"], e["idx"], e["bt"])
        bt2 = e2["bt"] if e2 else e["bt"] + int((k[5][0] - e["slot"]) * 0.4) + 1
        sig_dump = find_sig(e["nxt"][0], e["nxt"][1], bt2)
        P(f"\n- **{L.day_name(d)[:3]} {k[1]}** — GMGN https://gmgn.ai/sol/token/{k[1]}")
        P(f"  - arming whale dump: slot {e['slot']} idx {e['idx']}, seller {e['seller']}, {e['tok'] / 1e13:.1f}% of supply for {e['sol'] / 1e9:.3f} SOL, "
          f"token age {e['age_s']:.0f} s, 2-slot result of a 0.40 buy {e['r2']:+.4f} SOL — https://solscan.io/tx/{sig_paid}")
        if e2:
            P(f"  - next whale dump (the one we buy): slot {e2['slot']} idx {e2['idx']}, seller {e2['seller']}, {e2['tok'] / 1e13:.1f}% of supply for {e2['sol'] / 1e9:.3f} SOL, "
              f"{e2['slot'] - e['slot']} slots after the paid dump — https://solscan.io/tx/{sig_dump}")
        P(f"  - outside buys after that dump through 2 slots: {nb}; haqq bought it: {'yes, ' + str(hq) if hq else 'no'}")
        P(f"  - our replayed fill: slot {r[8][0]} (window slots {k[2]}..{k[2] + int(cfg.split(':')[1])}), exit {r[8][2]['base'][1]}, P&L model {1e3 * g:+.2f} mSOL "
          f"(cal {1e3 * (0.81 * g if g > 0 else g):+.2f}), wave exit {1e3 * gw:+.2f} mSOL; failed tries in the window {r[4]}")
        P(f"  - _record: day={d} mint={k[1]} paid=({e['slot']},{e['idx']}) dump=({e['nxt'][0]},{e['nxt'][1]}) sig_paid={sig_paid} sig_dump={sig_dump}_")
    if outf: open(f"{OUT}/{outf}", "w").write("\n".join(Lo) + "\n")
    return sel


if __name__ == "__main__":
    a = sys.argv
    n = int(a[a.index("--n") + 1]) if "--n" in a else 8
    outf = a[a.index("--out") + 1] if "--out" in a else "examples.txt"
    main(a[1], a[2], [int(x) for x in a[3].split(",")], n, outf)
