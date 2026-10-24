#!/usr/bin/env python3
# PASS 1 (read-only): one raw file -> one output pickle (never shared between processes).
#  trades : every pump bonding-curve trade event (SOL and quote curves) with tx metadata
#  nontr  : successful txs with no curve trade event that touch a mint or the pump / pump-fee programs (not AMM-only)
#  tgt    : full raw lines of txs touching the target wallets (success or failed)
#  smax   : slot -> max block index seen (lower bound of block size)
#  fail   : (mint, slot, program code) -> count of failed txs
import sys, os, json, gzip, base64, binascii, pickle, zlib, collections
TD = bytes([189, 219, 127, 211, 78, 230, 97, 238])
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58(b):
    n = int.from_bytes(b, "big"); o = []
    while n: n, r = divmod(n, 58); o.append(B58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(o))
U8 = lambda raw, a: int.from_bytes(raw[a:a + 8], "little")
TGT = set(l.split()[0] for l in open("/home/moiz/sniper/ops/overnight/minhold/trigger/targets.txt") if l.strip())
STD = {"11111111111111111111111111111111", "ComputeBudget111111111111111111111111111111", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
       "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL", "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ",
       "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P", "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr", "MAyhSmzXzV1pTf7LsNkrNwkWKTo4ougAJ1PPg47MD4e",
       "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo"}
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"; PFEE = "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ"; AMM = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
def main(f, out):
    I = {}
    def it(x): return I.setdefault(x, x)
    trades = []; nontr = []; tgt = []; smax = {}; fail = collections.Counter(); nlines = 0; bad = 0
    try:
        fh = gzip.open(f, "rt")
        for line in fh:
            nlines += 1
            try: r = json.loads(line)
            except Exception: bad += 1; continue
            s = r.get("s"); i = r.get("i")
            if s is None: continue
            if i is not None and i > smax.get(s, -1): smax[s] = i
            signers = r.get("signers") or []
            progs = r.get("progs") or []
            hit_t = bool(TGT.intersection(signers))
            if r.get("err") is not None:
                pc = next((p[:4] for p in progs if p not in STD), "std")
                for m in (r.get("mints") or [])[:3]: fail[(it(m), s, it(pc))] += 1
                if hit_t: tgt.append(line)
                continue
            sd = r.get("sd") or []
            sdd = dict((a, d) for a, d in sd)
            if not hit_t and TGT.intersection(sdd): hit_t = True
            rprog = next((p for p in progs if p not in STD), "")
            tip = sum(t[1] for t in (r.get("tips") or []) if isinstance(t, (list, tuple)) and len(t) > 1)
            payer = signers[0] if signers else ""
            got = False
            for j, e in enumerate(r.get("ev") or []):
                if not e.startswith("vdt/"): continue
                try: raw = base64.b64decode(e + "=" * (-len(e) % 4))
                except (binascii.Error, ValueError): continue
                if raw[:8] != TD or len(raw) < 129: continue
                got = True
                user = b58(raw[57:89])
                if user in TGT: hit_t = True
                ixname = ""
                if len(raw) >= 262:
                    ln = int.from_bytes(raw[258:262], "little")
                    if 0 < ln < 40: ixname = raw[262:262 + ln].decode("ascii", "replace")
                trades.append((it(b58(raw[8:40])), s, i, j, r.get("bt") or 0, it(user), it(payer), raw[56] == 1, U8(raw, 40), U8(raw, 48), U8(raw, 97), U8(raw, 105),
                               U8(raw, 169) if len(raw) >= 177 else 0, U8(raw, 161) if len(raw) >= 169 else 0, it(ixname), r.get("fee") or 0, r.get("cup") or 0, tip,
                               it(rprog), sdd.get(user, 0), sdd.get(payer, 0)))
            if not got:
                mints = r.get("mints") or []
                if (PUMP in progs or PFEE in progs or mints) and not (AMM in progs and PUMP not in progs):
                    nontr.append((s, i, r.get("sig"), tuple(signers[:3]), tuple(mints[:5]), tuple(dict.fromkeys(r.get("ixn") or [])),
                                  tuple(p for p in progs if p not in STD)[:6], tuple((x[0], x[1], x[2], x[3]) for x in (r.get("tb") or [])[:6]), tuple(sd[:6])))
            if hit_t: tgt.append(line)
    except (EOFError, OSError, zlib.error) as ex:
        bad += 1
    pickle.dump(dict(trades=trades, nontr=nontr, tgt=tgt, smax=smax, fail=dict(fail), nlines=nlines, bad=bad), gzip.open(out + ".tmp", "wb", compresslevel=3))
    os.rename(out + ".tmp", out)
if __name__ == "__main__":
    f = sys.argv[1]; run = f.split("/")[-3]; b = os.path.basename(f).replace(".jsonl.gz", "")
    out = f"/home/moiz/sniper/ops/overnight/minhold/trigger/x1/{run}_{b}.pkl.gz"
    if not os.path.exists(out): main(f, out)
