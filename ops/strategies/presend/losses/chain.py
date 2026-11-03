"""Decode the recorder lines (grep of our fill mints) into per-mint trade lists with the tx signer. Read-only."""
import json, glob, sys, collections, gzip
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real")
import decode as D
G = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/losses/grep/*.jsonl"
out = collections.defaultdict(dict)
for fn in sorted(glob.glob(G)):
    for line in open(fn):
        try: d = json.loads(line)
        except Exception: continue
        if d.get("err") is not None: continue
        signer = (d.get("signers") or [None])[0]
        for j, b in enumerate(D.chunks_of(d.get("ev"))):
            if b[:8] != D.DISC: continue
            p = D.parse_trade(b)
            if not p: continue
            out[p[0]][(d["s"], d["i"], j)] = [d["s"], d["i"], j, p[4], signer, p[3], p[1], p[2], p[5], p[6], d["bt"]]
res = {m: sorted(v.values()) for m, v in out.items()}
json.dump(res, gzip.open("/home/moiz/sniper-data/presend_losses/chain_trades.json.gz", "wt"))
print(len(res), sum(len(v) for v in res.values()))
