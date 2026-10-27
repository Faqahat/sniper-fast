#!/usr/bin/env python3
# INSTANT-BOTS study, step 9 (read-only): classify EVERY fast follow (a buy landing <= 40 block positions after a >= 4% dump of
# >= 0.3 SOL, same slot) by mechanism, from the window rows (i8 = every recorded tx on the mint in the dump slot - 3 .. + 1):
#   B  "seller's own bundle": the buy runs the SAME custom program as the dump, or shares a signer with it (one operator: a
#      sell-then-rebuy tool); confirmed per sample with the Jito bundle API (i10);
#   P  "pre-sender" (H1): the buyer (any of its signers) sent attempts on the same mint that FAILED or did NOTHING (successful,
#      no trade) in the 3 slots before the dump and/or the dump slot before the dump;
#   P2 "pre-sender, sibling wallets": no own attempts, but other wallets running the buyer's exact custom-program set did;
#   R  "no visible attempt, not the seller's tool": reaction (H5) or a bundle/backrun by an unrelated sender (H2/H3), or chance.
# usage: python3 -I i9_classify.py FOLLOWERS.json WIN.jsonl.gz OUT.json
import sys, json, gzip, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/haqq")
folp, winp, outp = sys.argv[1], sys.argv[2], sys.argv[3]
F = json.load(open(folp))
W = collections.defaultdict(list)
for l in gzip.open(winp, "rt"):
    r = json.loads(l); W[(r[0], r[1])].append(r)          # NOTE keyed by (mint, slot of the row)
GENERIC = {"", "L2TExMFKdjpN9kozasaurPirfHy9P8sbXoAN1qA3S95", "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr", "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"}
def custom(pr): return "|".join(p for p in pr.split("|") if p and p not in GENERIC)
out = []; miss = 0
for e in F["ev"]:
    m, S = e["mint"], e["s"]
    rows = [r for s in range(S - 3, S + 2) for r in W.get((m, s), [])]
    if not rows: miss += 1; continue
    rows.sort(key=lambda r: (r[1], r[2]))
    me = next((r for r in rows if r[3] == e["sig"]), None)
    dump = next((r for r in rows if r[3] == e["dsig"]), None)
    if me is None or dump is None: miss += 1; continue
    sg = set(me[4]); prs = me[10]; cpr = custom(prs)
    dpos = (S, e["di"]); mypos = (S, e["di"] + e["gap"])
    def is_att(r): return r[5] is not None or not r[12]                 # failed, or successful without a trade on this mint
    own = [r for r in rows if set(r[4]) & sg and is_att(r)]
    own_before = [r for r in own if (r[1], r[2]) < dpos]
    own_same_slot_before = [r for r in own_before if r[1] == S]
    own_between = [r for r in own if dpos < (r[1], r[2]) < mypos]
    own_after = [r for r in own if (r[1], r[2]) > mypos]
    sib = [r for r in rows if cpr and custom(r[10]) == cpr and not (set(r[4]) & sg) and is_att(r) and (r[1], r[2]) < dpos]
    # everything between the dump and the follow (any wallet) on this mint
    betw = [r for r in rows if dpos < (r[1], r[2]) < mypos]
    shared = bool(set(dump[4]) & sg)
    same_prog = bool(cpr) and custom(dump[10]) == cpr
    cls = "B" if (same_prog or shared) else ("P" if own_before else ("P2" if sib else "R"))
    slots_with = collections.Counter(r[1] for r in own_before)
    out.append(dict(e, cls=cls, own_before=len(own_before), own_same_slot_before=len(own_same_slot_before), own_between=len(own_between), own_after=len(own_after),
                    own_slots=len(slots_with), own_max_per_slot=max(slots_with.values()) if slots_with else 0, sib_before=len(sib), sib_wallets=len({r[4][0] for r in sib}),
                    own_errs=collections.Counter((r[5] or "noop") for r in own_before).most_common(3), n_between=len(betw),
                    att_fee_med=statistics.median([r[6] for r in own_before]) if own_before else None, signers=me[4], dsigners=dump[4],
                    my_progs=prs, d_progs=dump[10], my_tips=me[13], d_tips=dump[13]))
json.dump(out, open(outp, "w"))
print(f"classified {len(out)} fast follows (missing rows {miss})")
def summ(rows, lab):
    c = collections.Counter(r["cls"] for r in rows); n = len(rows)
    print(f"  {lab:24s} n {n:5d} | " + " | ".join(f"{k} {c[k]} ({100 * c[k] / max(n, 1):.0f}%)" for k in ("B", "P", "P2", "R")))
print("by block gap after the dump:")
for lab, lo, hi in (("gap 1", 1, 1), ("gap 2-5", 2, 5), ("gap 6-10", 6, 10), ("gap 11-20", 11, 20), ("gap 21-40", 21, 40), ("ALL <= 40", 1, 40), ("ALL <= 10 (~<=1 ms feed)", 1, 10)):
    summ([r for r in out if lo <= r["gap"] <= hi], lab)
print("first buyer after the dump only (rank 1):")
for lab, lo, hi in (("gap 1", 1, 1), ("gap 2-5", 2, 5), ("gap 6-10", 6, 10), ("gap 11-40", 11, 40)):
    summ([r for r in out if lo <= r["gap"] <= hi and r["rank"] == 1], lab)
print("by leader client (gap <= 10):")
for c in ("jito", "bam", "harmonic", "fd", "agave", "other"):
    summ([r for r in out if r["gap"] <= 10 and r["client"] == c], c)
P = [r for r in out if r["cls"] == "P"]
if P:
    print(f"P (pre-senders): own attempts before the dump median {statistics.median(r['own_before'] for r in P)}, in the dump slot before it median {statistics.median(r['own_same_slot_before'] for r in P)}, "
          f"max per slot median {statistics.median(r['own_max_per_slot'] for r in P)}; failed copies after the fill median {statistics.median(r['own_after'] for r in P)}")
for cls in ("B", "P", "P2", "R"):
    rows = [r for r in out if r["cls"] == cls and r["gap"] <= 10]
    cw = collections.Counter(r["u"] for r in rows)
    print(f"\n{cls} (gap <= 10): {len(rows)} follows by {len(cw)} wallets; top: " + ", ".join(f"{w[:8]} {n}" for w, n in cw.most_common(15)))
