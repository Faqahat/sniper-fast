#!/usr/bin/env python3
"""WHALE FAST-DUMP LEDGER seed (engine dip41 --presend-live-dumper-ledger on, --presend-live-dumper-state FILE) [MEASURED, read-only on the tape].

Builds the engine's dumper-ledger state from the collector tape (/home/it/sniper-studies/sniper-reviewer/tape.py tape.load; data
/data/tapes/collect/run_*) over the last --hours (default 48), so a run starts warm. The rule is the engine's (psdl.rs) and the
4ggJ study's (/home/it/sniper-4ggj2 x12_feat.py / x15_ledger.py / ledger.py):
  * a ledger BUY = one buy trade of >= 3% of supply (tok >= 3e13 raw), not on a mayhem curve (the mint's max vtok > 1.0731e15), not in the
    mint's first slot on the tape (its create slot; the tape is loaded from 2 h before the window so a young token's first slot is its create);
  * d = DUMPED: the same wallet's sells of that mint AFTER the buy (tape order), in slots <= buy + --dump-slots (20), sum >= --dump-frac
    (0.3) of the buy's tokens (WIDE-DUMPER's WIN:FRAC);
  * q = QUICK: any such sell in slots <= buy + --quick-slots (10) (QF2's WIN);
  * a buy counts once 25 slots have passed (buys newer than the tape's last slot - 25 are left out: the engine would still hold them);
  * per wallet: its newest 50 resolved buys, oldest first; "t" = the buy's block time + 25 slots (~10 s; the engine's resolution clock);
    wallets idle > 48 h before the state's "t" are left out (the engine drops them at load).
State FORMAT (what the engine loads; psdl.rs header):
  {"v": 1, "kind": "dumper_ledger", "t": <ns: the tape's newest block time>, "slot": <its slot>,
   "rule": {"min_tok": 3e13, "dump_frac": 0.3, "dump_slots": 20, "quick_slots": 10, "resolve_slots": 25, "keep": 50, "idle_h": 48},
   "w": {"<wallet>": {"t": <ns>, "b": [[slot, d 0|1, q 0|1], ...]}}, "built": {...}}   ("built" is ignored by the engine)
The engine refuses a state whose dump_frac / dump_slots / quick_slots differ from its flags (--presend-live-wide-dumper N:SCORE:WIN:FRAC,
--presend-live-qf2 N:SCORE:WIN): build it with the same values.
usage: PYTHONPATH=/home/it/sniper-studies/sniper-reviewer/lib python3 ops/prod/dumper_seed.py --out FILE [--hours 48] [--end UNIX_S]
       [--dump-slots 20 --dump-frac 0.3 --quick-slots 10] [--show WALLET]"""
import argparse
import collections
import json
import os
import sys
import time

sys.path.insert(0, "/home/it/sniper-studies/sniper-reviewer")
sys.path.insert(0, "/home/it/sniper-studies/sniper-reviewer/lib")
import numpy as np  # noqa: E402
import tape  # noqa: E402

MIN_TOK = 30_000_000_000_000
MAYHEM_VTOK = 1.0731e15
RESOLVE_SLOTS = 25
KEEP = 50
IDLE_NS = 48 * 3600 * 10**9
SLOT_NS = 400_000_000  # the resolution clock: buy time + 25 slots


def build(tp, t0, dump_slots=20, frac_pm=300, quick_slots=10):
    """tape (sorted by s, i) -> ({wallet: [(slot, d, q, t_ns)] oldest first}, stats)"""
    tp = tp.reset_index(drop=True)
    mx = tp.groupby("mint").vtok.max()
    may = set(mx[mx > MAYHEM_VTOK].index)
    first = tp.groupby("mint").s.min()
    last_slot = int(tp.s.max())
    keep = ~tp.mint.isin(may)
    c = tp[keep & tp.buy & (tp.tok >= MIN_TOK) & (tp.bt >= t0)]
    c = c[c.s.values != first.reindex(c.mint).values]
    n_cand_all = len(c)
    c = c[c.s + RESOLVE_SLOTS <= last_slot]
    # the wallets' sells of the candidates' mints: (user, mint) -> (row, slot, tok) in tape order
    keys = set(zip(c.user.values, c.mint.values))
    sl = tp[(~tp.buy) & tp.mint.isin(set(c.mint))]
    sells = collections.defaultdict(list)
    for r, u, m, s, q in zip(sl.index.values, sl.user.values, sl.mint.values, sl.s.values, sl.tok.values):
        if (u, m) in keys:
            sells[(u, m)].append((r, s, q))
    out = collections.defaultdict(list)
    nd = nq = 0
    for r, u, m, s, q, bt in zip(c.index.values, c.user.values, c.mint.values, c.s.values, c.tok.values, c.bt.values):
        sold, quick = 0, False
        for (r2, s2, q2) in sells.get((u, m), ()):
            if r2 > r and s2 <= s + dump_slots:
                sold += int(q2)
            if r2 > r and s2 <= s + quick_slots and q2 > 0:
                quick = True
        d = sold * 1000 >= int(q) * frac_pm
        nd += d
        nq += quick
        out[u].append((int(s), bool(d), bool(quick), int(bt) * 10**9 + RESOLVE_SLOTS * SLOT_NS))
    st = {k: int(v) for k, v in {"tape_rows": len(tp), "mayhem_mints": len(may), "big_buys": n_cand_all, "resolved": len(c), "dumped": nd, "quick": nq,
                                 "last_slot": last_slot}.items()}
    return out, st


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--hours", type=float, default=48.0)
    ap.add_argument("--end", type=float, default=None, help="the window's end (unix s; default now)")
    ap.add_argument("--dump-slots", type=int, default=20, help="WIDE-DUMPER's WIN (1..20)")
    ap.add_argument("--dump-frac", type=float, default=0.3, help="WIDE-DUMPER's FRAC (0, 1]")
    ap.add_argument("--quick-slots", type=int, default=10, help="QF2's WIN (1..20)")
    ap.add_argument("--n", type=int, default=3, help="WIDE-DUMPER's N (counts only)")
    ap.add_argument("--score", type=float, default=0.8, help="WIDE-DUMPER's SCORE (counts only)")
    ap.add_argument("--qf-n", type=int, default=5, help="QF2's N (counts only)")
    ap.add_argument("--qf-score", type=float, default=0.3, help="QF2's SCORE (counts only)")
    ap.add_argument("--show", default=None)
    a = ap.parse_args()
    t1 = a.end or time.time()
    t0 = t1 - a.hours * 3600
    tl = time.time()
    tp = tape.load(t0 - 7200, t1)
    if not len(tp):
        sys.exit("no tape in the window")
    tp = tp[tp.bt <= t1]
    if not (1 <= a.dump_slots <= 20 and 1 <= a.quick_slots <= 20 and 0 < a.dump_frac <= 1):
        sys.exit("--dump-slots / --quick-slots 1..20, --dump-frac (0, 1]")
    frac_pm = round(a.dump_frac * 1000)
    hist, st = build(tp, t0, a.dump_slots, frac_pm, a.quick_slots)
    t_state = int(tp.bt.max()) * 10**9
    slot_state = int(tp.s.max())
    w = {}
    for u, v in hist.items():
        v = v[-KEEP:]
        tw = max(x[3] for x in v)
        if tw < t_state - IDLE_NS:
            continue
        w[u] = {"t": tw, "b": [[s, int(d), int(q)] for s, d, q, _ in v]}
    nv = [(len(x["b"]), sum(e[1] for e in x["b"]), sum(e[2] for e in x["b"])) for x in w.values()]
    passing = sum(1 for n, d, _ in nv if n >= a.n and n > 0 and d >= a.score * n - 1e-9)
    pass_qf = sum(1 for n, _, q in nv if n >= a.qf_n and n > 0 and q >= a.qf_score * n - 1e-9)
    built = {"from": float(t0), "to": float(t1), "hours": a.hours, "made": time.time(), **st, "wallets": len(w), "pass": passing, "spec": f"{a.n}:{a.score}",
             "pass_qf2": pass_qf, "spec_qf2": f"{a.qf_n}:{a.qf_score}"}
    j = {"v": 1, "kind": "dumper_ledger", "t": t_state, "slot": slot_state,
         "rule": {"min_tok": MIN_TOK, "dump_frac": frac_pm / 1000, "dump_slots": a.dump_slots, "quick_slots": a.quick_slots, "resolve_slots": RESOLVE_SLOTS, "keep": KEEP,
                  "idle_h": IDLE_NS // 3_600_000_000_000},
         "w": w, "built": built}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    tmp = a.out + ".new"
    with open(tmp, "w") as f:
        json.dump(j, f, separators=(",", ":"))
    os.replace(tmp, a.out)
    ns = np.array([n for n, _, _ in nv]) if nv else np.zeros(0)
    print(f"window {time.strftime('%m-%d %H:%M', time.gmtime(t0 + 5 * 3600))} .. {time.strftime('%m-%d %H:%M', time.gmtime(t1 + 5 * 3600))} PKT ({a.hours:g} h), "
          f"tape {st['tape_rows']:,} trades (+2 h lead-in), loaded in {time.time() - tl:.0f} s")
    print(f">= 3% buys {st['big_buys']:,} (resolved {st['resolved']:,}; dumped >= {a.dump_frac:g} within {a.dump_slots} slots {st['dumped']:,} = "
          f"{st['dumped'] / max(st['resolved'], 1) * 100:.1f}%; sold within {a.quick_slots} slots {st['quick']:,} = {st['quick'] / max(st['resolved'], 1) * 100:.1f}%); "
          f"mayhem mints left out {st['mayhem_mints']:,}")
    print(f"wallets {len(w):,}: n >= 3 {int((ns >= 3).sum()):,}, n >= 10 {int((ns >= 10).sum()):,}, n = 50 (capped) {int((ns >= KEEP).sum()):,}; "
          f"pass WIDE-DUMPER {a.n}:{a.score} {passing:,}, QF2 {a.qf_n}:{a.qf_score} {pass_qf:,}")
    print(f"wrote {a.out} ({os.path.getsize(a.out):,} bytes; t {t_state}, slot {slot_state})")
    if a.show:
        print(a.show, json.dumps(w.get(a.show)))


if __name__ == "__main__":
    main()
