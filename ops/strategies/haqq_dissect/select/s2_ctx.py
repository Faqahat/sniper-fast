#!/usr/bin/env python3
"""SELECT step 2 (read-only): per-mint CREATE-TX features from s0 (cr/*.jsonl) + creates.json flags. Strings are only parsed (no URL fetch).
  name/symbol style: lengths, all-caps ticker, ticker == name, spaces, digits, non-ASCII, emoji-ish
  uri: host (top hosts one-hot + 'other'), length, ipfs CID style (Qm.. / bafk..), path tokens (tg_ / padre / launch tools)
  tx shape: fee, CU price / limit / used, programs beyond the pump.fun + system set (router one-hot), signers, tips (count, SOL),
            payer != creator, the creator's buy inside the create tx (SOL), number of buys in it, Buy version (Buy / BuyV2 / BuyV3)
  flags: CreateV2, cashback, holder, quote
Out: select/ctx.npz (mint id -> row), ctx_vocab.json, s2.txt (host / router counts)"""
import json, glob, os, collections, re, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/select"
STD = {"11111111111111111111111111111111", "ComputeBudget111111111111111111111111111111", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
       "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P", "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
       "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ", "MAyhSmzXzV1pTf7LsNkrNwkWKTo4ougAJ1PPg47MD4e"}


def host_of(u):
    m = re.match(r"^[a-z]+://([^/]+)", u or "")
    return m.group(1).lower() if m else ("(none)" if not u else "(raw)")


def main():
    ids, idm = L.ids_map()
    CR = json.load(open(f"{L.TAB}/creates.json"))
    recs = {}
    for f in sorted(glob.glob(f"{OUT}/cr/*.jsonl")):
        for line in open(f):
            r = json.loads(line); k = r["mint"]
            if k not in recs or (r["s"], r["i"]) < (recs[k]["s"], recs[k]["i"]): recs[k] = r
    print(len(recs), "create txs with strings")
    hosts = collections.Counter(host_of(r["uri"]) for r in recs.values())
    rset = collections.Counter(tuple(sorted(set(r["progs"] or []) - STD)) for r in recs.values())
    TOPH = [h for h, _ in hosts.most_common(16)]; TOPR = [p for p, _ in rset.most_common(12)]
    allp = collections.Counter(p for r in recs.values() for p in set(r["progs"] or []) - STD)
    TOPP = [p for p, _ in allp.most_common(12)]
    cols = ["c_name_len", "c_sym_len", "c_sym_caps", "c_sym_eq_name", "c_name_space", "c_name_digit", "c_name_nonascii", "c_name_words",
            "c_uri_len", "c_uri_qm", "c_uri_bafk", "c_uri_tg", "c_host_freq", "c_fee", "c_cup", "c_cul", "c_cu", "c_nprogs", "c_nsigners",
            "c_ntips", "c_tipsol", "c_payer_ne_creator", "c_devbuy_tx", "c_nbuys_tx", "c_buyver", "c_v2", "c_cashback", "c_holder", "c_quote_sol",
            "c_nixn", "c_payer_sd", "c_mint_pump", "c_mint_vanity"] + [f"c_h_{h}" for h in TOPH] + [f"c_p_{p[:8]}" for p in TOPP]
    rows = np.full((len(ids), len(cols)), np.nan, np.float32)
    have = np.zeros(len(ids), bool)
    for k, r in recs.items():
        m = idm.get(k)
        if m is None: continue
        c = CR.get(k, {})
        nm = r.get("name") or ""; sy = r.get("sym") or ""; u = r.get("uri") or ""; h = host_of(u)
        progs = set(r.get("progs") or [])
        tips = r.get("tips") or []
        buys = [b for b in (r.get("buys") or []) if b[0] == k and b[3] == 1]
        dev = sum(b[1] for b in buys if b[4] == r.get("creator")) / 1e9
        ixn = r.get("ixn") or []
        bv = 3 if "BuyV3" in ixn else 2 if "BuyV2" in ixn else 1 if any(x in ("Buy", "BuyExactSolIn") for x in ixn) else 0
        v = [len(nm), len(sy), float(sy.isupper()), float(sy.strip().lower() == nm.strip().lower()), float(" " in nm.strip()), float(any(ch.isdigit() for ch in nm)),
             float(any(ord(ch) > 127 for ch in nm + sy)), len(nm.split()), len(u), float("/Qm" in u), float("/bafk" in u), float("tg_" in u), hosts[h],
             r.get("fee") or 0, r.get("cup") or 0, r.get("cul") or 0, r.get("cu") or 0, len(progs - STD), len(r.get("signers") or []),
             len(tips), sum(t[1] for t in tips) / 1e9, float((r.get("signers") or [None])[0] != r.get("creator")), dev, len(buys), bv,
             float(bool(c.get("v2"))), float(bool(c.get("cashback"))), float(bool(c.get("holder"))),
             float(c.get("quote", "11111111111111111111111111111111") == "11111111111111111111111111111111"), len(ixn), (r.get("payer_sd") or 0) / 1e9,
             float(k.endswith("pump")), float(k.endswith("pump") or k.endswith("bonk") or k[-4:].lower() in ("moon", "dood", "meme") )]
        v += [float(h == x) for x in TOPH] + [float(p in progs) for p in TOPP]
        rows[m] = v; have[m] = True
    np.savez(f"{OUT}/ctx.npz", X=rows, have=have, cols=np.array(cols))
    json.dump(dict(TOPH=TOPH, TOPR=[list(p) for p in TOPR], TOPP=TOPP), open(f"{OUT}/ctx_vocab.json", "w"))
    with open(f"{OUT}/s2.txt", "w") as f:
        f.write(f"create txs with strings: {len(recs):,}\nTop URI hosts:\n" + "\n".join(f"  {h}: {n:,}" for h, n in hosts.most_common(30)))
        f.write("\nTop extra-program sets in create txs:\n" + "\n".join(f"  {list(p)}: {n:,}" for p, n in rset.most_common(25)))
    print(open(f"{OUT}/s2.txt").read()[:3000])


if __name__ == "__main__":
    main()
