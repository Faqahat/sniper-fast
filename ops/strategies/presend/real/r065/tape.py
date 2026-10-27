#!/usr/bin/env python3
"""REPLAY_065 step 3 (read-only, offline): the per-token chain tape of the two runs' tokens, from extract.py's raw txs.
  trades: every pump.fun TradeEvent of a SUCCESSFUL tx for that mint, chain order (slot, tx index, event index), with the
          tx's signature, first signer, instruction names, fee, our-wallet flag
  fails : every FAILED tx that names the mint (slot, index, signature, error, signer, programs, instruction names)
  clock : per slot the block size seen (max tx index + 1) and block time (the chain clock of the replay, as rlib.Clock)
Checks (MEASURED): reserve chaining per mint (pre-state of each trade = post-state of the previous one).
Writes /home/moiz/sniper-data/replay065/tape.pkl"""
import sys, os, json, pickle, base64, struct, collections, time
import numpy as np

RAW = "/home/moiz/sniper-data/replay065/raw"
OUT = "/home/moiz/sniper-data/replay065/tape.pkl"
DISC = bytes.fromhex("bddb7fd34ee661ee")
CPI = bytes.fromhex("e445a52e51cb9a1d")
A58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR": "ams", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE": "fra"}


def b58(b):
    n = int.from_bytes(b, "big"); s = ""
    while n:
        n, r = divmod(n, 58); s = A58[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s


def parse_trade(b):
    """pump TradeEvent (after the 8-byte disc): mint, sol, tok, buy, user, ts, vsol, vtok, rsol, rtok, fee_recipient, fee_bps, fee,
    creator, creator_fee_bps, creator_fee (decode.py's layout)"""
    if len(b) < 225: return None
    o = 8
    mint = b58(b[o:o + 32]); o += 32
    sol, tok = struct.unpack_from("<QQ", b, o); o += 16
    buy = b[o]; o += 1
    user = b58(b[o:o + 32]); o += 32
    o += 8
    vsol, vtok, rsol, rtok = struct.unpack_from("<QQQQ", b, o); o += 32
    o += 32
    fee_bps, fee = struct.unpack_from("<QQ", b, o); o += 16
    o += 32
    cfee_bps, cfee = struct.unpack_from("<QQ", b, o)
    return dict(mint=mint, sol=sol, tok=tok, buy=bool(buy), user=user, vsol=vsol, vtok=vtok, rsol=rsol, rtok=rtok, fbps=fee_bps, fee=fee, cbps=cfee_bps, cfee=cfee)


def chunks(evs):
    for e in evs or []:
        for ch in e.split(" "):
            try: b = base64.b64decode(ch + "=" * (-len(ch) % 4))
            except Exception: continue
            if b[:8] == CPI: b = b[8:]
            yield b


def main():
    t0 = time.time()
    D = pickle.load(open(f"{RAW}/tx.pkl", "rb"))
    print("loaded", len(D), f"{time.time() - t0:.0f}s", flush=True)
    TAPE = {}
    bad_chain = 0; n_tr = 0; n_fail = 0
    for mint, txs in D.items():
        trades = []; fails = []
        for r in txs:
            sg = (r.get("signers") or ["?"])[0]
            if r.get("err") is not None:
                fails.append((r["s"], r["i"], r["sig"], json.dumps(r["err"], separators=(",", ":")), sg, tuple(r.get("progs") or ()), tuple(r.get("ixn") or ()), r.get("fee")))
                continue
            j = 0
            for b in chunks(r.get("ev")):
                if b[:8] != DISC: continue
                t = parse_trade(b)
                if t is None: continue
                jj = j; j += 1
                if t["mint"] != mint: continue
                trades.append(dict(s=r["s"], i=r["i"], j=jj, sig=r["sig"], signer=sg, ixn=tuple(r.get("ixn") or ()), txfee=r.get("fee"), bt=r["bt"],
                                   ours=OURS.get(t["user"]) or OURS.get(sg), **{k: t[k] for k in ("buy", "sol", "tok", "vsol", "vtok", "fbps", "cbps", "user", "fee", "cfee")}))
        trades.sort(key=lambda x: (x["s"], x["i"], x["j"]))
        # reserve chaining: the pre-state of each trade = the post-state of the previous one
        for a, b in zip(trades, trades[1:]):
            pv = b["vsol"] - b["sol"] if b["buy"] else b["vsol"] + b["sol"]
            if pv != a["vsol"]: bad_chain += 1
        n_tr += len(trades); n_fail += len(fails)
        TAPE[mint] = dict(trades=trades, fails=fails)
    S = np.load(f"{RAW}/slots.npy")
    slot0 = int(S["slot"][0]); n = int(S["slot"][-1]) - slot0 + 1
    bsize = np.zeros(n, np.int32); bsize[S["slot"].astype(np.int64) - slot0] = S["maxi"].astype(np.int32) + 1
    bt = np.zeros(n, np.int64); bt[S["slot"].astype(np.int64) - slot0] = S["bt"]
    pickle.dump(dict(tape=TAPE, slot0=slot0, bsize=bsize, bt=bt), open(OUT, "wb"))
    print(f"trades {n_tr:,} fails {n_fail:,} | chain breaks {bad_chain} | slots {n:,} recorded {int((bsize > 0).sum()):,} | {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
