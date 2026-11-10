#!/usr/bin/env python3
"""dip36 FP-NOBOT level-2 parity fixture (read-only): the raw inputs the Rust store needs to rebuild the parity file's x for a cluster of
r55 positions -> /home/it/sniper-data/flatperfect/engine_fixture_r55.bin, read by src/fpnb_tests.rs (fpnb_parity_chain_inputs; the test
skips when the file is absent).
Picks the densest ~SPAN-slot cluster of parity positions (both kinds), then writes:
  line 1: JSON header {positions, bots (u64), core (u64), ours (u64), span_lo, feed_lo, own, shadow, shadow_arms, rows, fails, wh}
  trade rows  slot u64, idx u32, j i32, mint u64, user u64, buy u8, sol u64, tok u64, vsol u64      (57 bytes, little-endian)
  fail rows   slot u64, idx u32, payer u64, mint u64, kind u8                                     (29 bytes)
  whale rows  wallet u64, mint u64, slot u32, flags u8 (1 buy, 2 big)                             (21 bytes; the whales' rows before feed_lo)
Trade rows: every chain row with slot in [feed_lo, hi] plus every row of the positions' mints (their whole history); fails likewise.
Ids are the chain's u64 prefixes (the test makes pubkeys of them). usage: fp_engine_fixture.py [SPAN]"""
import sys, json, pickle, struct, collections
import numpy as np

D = "/home/it/sniper-data/flatperfect"
FS = "/home/it/sniper-data/flatsig"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
B58I = {c: i for i, c in enumerate(B58)}
NAMED = {"haqq6qnVBCZt97amh9VUFZRFCkD6NJxoYifacCuqqqq": "haqq", "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq": "haqq",
         "2VggYpPumR3sV4K9vBqDzsmKzpB3BgSM4woRwbqqzweg": "haqq", "9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN": "9pQQ",
         "8PgC4ngpx6zUG3KFQAQHqSeePDFA7kGyEaA2yMoZ4HUk": "8PgC"}
OURS = ["EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"]


def pk64(s):
    n = 0
    for c in s: n = n * 58 + B58I[c]
    return int.from_bytes(n.to_bytes(32, "big")[:8], "big")


def main():
    span = int(sys.argv[1]) if len(sys.argv) > 1 else 2500
    L = open(f"{D}/parity_r55.jsonl").read().splitlines()
    rows = [json.loads(l) for l in L[1:]]
    pos = {}
    for r in rows: pos.setdefault(r["key"], r)
    P = sorted(pos.values(), key=lambda r: r["trig_slot"])
    best = (0, 0)
    for a in range(len(P)):
        b = a
        while b < len(P) and P[b]["trig_slot"] <= P[a]["trig_slot"] + span: b += 1
        ks = {p["kind"] for p in P[a:b]}
        if len(ks) == 2 and b - a > best[1] - best[0]: best = (a, b)
    sel = P[best[0]:best[1]]
    keys = {p["key"] for p in sel}
    ex = pickle.load(open(f"{D}/runs/ex_r55.pkl", "rb"))
    bykey = {f'{p["run"]}|{p["mint"]}|{p["pid"]}|{p["kind"]}|{p["w"]}': p for p in ex["pos"]}
    z = np.load(f"{D}/chain/chain.npz"); f = np.load(f"{D}/chain/fails.npz")
    spans = json.load(open(f"{D}/chain/spans.json"))
    lo = min(p["trig_slot"] for p in sel) - 8400 - 60
    hi = max(p["fill_slot"] for p in sel)
    span_lo = [s[1] for s in spans if s[1] <= lo <= s[2]][0]
    mints = {pk64(p["mint"]) for p in sel}
    S, M = z["slot"], z["mint"]
    tm = ((S >= lo) & (S <= hi)) | np.isin(M, np.array(sorted(mints), dtype=np.uint64))
    tm &= S <= hi
    FSl, FM = f["slot"], f["mint"]
    fm = (((FSl >= lo) & (FSl <= hi)) | np.isin(FM, np.array(sorted(mints), dtype=np.uint64))) & (FSl <= hi)
    whales = {}
    for p in sel:
        e = bykey[p["key"]]
        whales[pk64(e["whale"])] = e["whale"]
    U = z["user"]
    wm = np.isin(U, np.array(sorted(whales), dtype=np.uint64)) & (S < lo)
    coh = sorted({int(x) for x in json.load(open(f"{FS}/cohort.json"))["ids"]})
    named = sorted({pk64(k) for k in json.load(open(f"{D}/cohort_full_b58.json"))["named"]})
    bots = sorted(set(coh) | set(named))
    core = sorted(pk64(k) for k in NAMED)
    # own results / shadow (fp2_own.run_feats inputs)
    own = [{"k": p["known"], "pnl": p["pnl"], "fol": len(p.get("fol") or []), "mint": p["mint"], "whale": p.get("whale"), "creator": p.get("creator")} for p in ex["pos"]]
    shf = [[(s["cfill"][2] or s["t"]) + 2e9, s["c"]] for s in ex["sh"] if s["c"] is not None and s.get("cfill")]
    sha = [s["t"] for s in ex["sh"]]
    positions = []
    for p in sel:
        e = bykey[p["key"]]
        T = {"pct": e.get("trig_pct"), "sol": e.get("trig_sol"), "age_slots": e.get("trig_age"), "vsol": e.get("trig_vsol"), "t": e["t0"]}
        arm = {"nb": e.get("nb"), "ann": {"nb50": e.get("nb50"), "cr_pct": e.get("cr_pct")}, "quiet": e.get("quiet") or {}, "v2": e.get("v2") or {}}
        if e.get("arm_holders"): arm["holders"] = e["arm_holders"]
        arm["trig" if p["kind"] == "T2" else "dump"] = T
        positions.append({"key": p["key"], "kind": p["kind"], "mint": p["mint"], "mint64": pk64(p["mint"]), "trig_slot": p["trig_slot"], "trig_idx": p["trig_idx"],
                          "fill_slot": p["fill_slot"], "whale": e["whale"], "whale64": pk64(e["whale"]), "creator": e.get("creator"), "t0": e["t0"], "arm": arm})
    hdr = {"positions": positions, "bots": bots, "core": core, "ours": [pk64(k) for k in OURS], "span_lo": int(span_lo), "feed_lo": int(lo), "hi": int(hi),
           "own": own, "shadow": shf, "shadow_arms": sha, "rows": int(tm.sum()), "fails": int(fm.sum()), "wh": int(wm.sum())}
    out = open(f"{D}/engine_fixture_r55.bin", "wb")
    out.write((json.dumps(hdr) + "\n").encode())
    tr = np.zeros(int(tm.sum()), dtype=[("s", "<u8"), ("i", "<u4"), ("j", "<i4"), ("m", "<u8"), ("u", "<u8"), ("b", "u1"), ("sol", "<u8"), ("tok", "<u8"), ("v", "<u8")])
    for a, b in (("s", "slot"), ("i", "idx"), ("j", "j"), ("m", "mint"), ("u", "user"), ("b", "buy"), ("sol", "sol"), ("tok", "tok"), ("v", "vsol")): tr[a] = z[b][tm]
    out.write(tr.tobytes())
    fr = np.zeros(int(fm.sum()), dtype=[("s", "<u8"), ("i", "<u4"), ("p", "<u8"), ("m", "<u8"), ("k", "u1")])
    for a, b in (("s", "slot"), ("i", "idx"), ("p", "payer"), ("m", "mint"), ("k", "kind")): fr[a] = f[b][fm]
    out.write(fr.tobytes())
    wr = np.zeros(int(wm.sum()), dtype=[("w", "<u8"), ("m", "<u8"), ("s", "<u4"), ("f", "u1")])
    wr["w"] = U[wm]; wr["m"] = M[wm]; wr["s"] = S[wm]
    B = z["buy"][wm]; TOK = z["tok"][wm].astype(np.float64)
    wr["f"] = (B == 1).astype(np.uint8) | (((B == 1) & (TOK >= 0.06 * 1e15)).astype(np.uint8) * 2)
    out.write(wr.tobytes())
    out.close()
    print("positions", len(sel), collections.Counter(p["kind"] for p in sel), "lines", sum(1 for r in rows if r["key"] in keys),
          "rows", hdr["rows"], "fails", hdr["fails"], "wh", hdr["wh"], "slots", lo, hi)


if __name__ == "__main__":
    main()
