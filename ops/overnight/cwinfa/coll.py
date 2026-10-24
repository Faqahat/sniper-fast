#!/usr/bin/env python3
# READ-ONLY, offline: CWiNFA in our collector data (R1 = phaseA, R2 = hardlinked snapshot of phaseA_dry taken 02:44 UTC).
# Pass A: every row (trade 'T' or other tx 'X') with CWiNFA as user/signer -> its mints.
# Pass B: for each of those launches, the full chain-ordered trade list -> place in line (slot delta, outside buys ahead
#   = distinct non-insider buy txs between the creator's glued bundle and its first buy), entry multiple vs the post-bundle
#   price, its sells (slot / s after the buy, share of tokens, price multiple vs its entry), failed txs of it.
# Output: coll_cw.json {mint: {...}}
import os, sys, json, gzip, glob, zlib, collections
from multiprocessing import Pool
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["RP_PHASEA_R2"] = os.path.join(HERE, "phaseA_snap")
import rp
W = "CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J"; K = W[:10]
L = rp.load_launches()
def scanA(key):
    run, d = key; out = collections.defaultdict(list)
    for f in glob.glob(os.path.join(d, "*.jsonl.gz")):
        try:
            for line in gzip.open(f, "rt"):
                if K not in line: continue
                r = json.loads(line)
                if r[0] == "T" and r[14] != W and r[6] != W: continue
                if r[0] == "X" and r[6] != W: continue
                out[r[1]].append(r)
        except (EOFError, OSError, zlib.error): pass
    return run, dict(out)
def work(key):
    run, b, mints = key
    tra = rp.read_bucket(run, b, set(mints)); fa = rp.read_failed(run, b, set(mints)); out = {}
    for m in mints:
        c = L.get(m); tr = tra.get(m, [])
        if not c or not tr: out[m] = dict(run=run, no_rows=True); continue
        st = rp.structure(tr, c); S = c["slot"]; g = st["g_end"]
        ge = tr[g - 1] if g >= 1 else None
        p_b = ge["vsol"] / ge["vtok"] if ge and ge["vtok"] else None
        mine = [(k, t) for k, t in enumerate(tr) if t["user"] == W]
        r = dict(run=run, S=S, bt=c.get("bt"), dep=c.get("user"), creator=c.get("creator"), name=c.get("name"), symbol=c.get("symbol"), uri=c.get("uri"),
                 g_end=g, glued=len(st["glued"]), glued_sol=round(sum(t["sol"] for t in st["glued"]) / 1e9, 4),
                 dev=round(sum(t["sol"] for t in tr if t["sig"] == c.get("sig") and t["buy"]) / 1e9, 4), n_trades=len(tr),
                 quote_ok=not (min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9),
                 mayhem="InitializeMayhemState" in (c.get("ixn") or []), failed=[(s - S, i) for s, i, u in fa.get(m, []) if u == W])
        buys = [(k, t) for k, t in mine if t["buy"]]
        if buys:
            k0, t0 = buys[0]
            ahead = [t for t in tr[g:k0] if t["buy"] and t["user"] not in st["insiders"]]
            ahead_tx = len({t["sig"] for t in ahead})
            sells_any_ahead = sum(1 for t in tr[g:k0] if not t["buy"])
            px_in = t0["sol"] / t0["tok"] if t0["tok"] else None     # its average curve price (lamports per raw token)
            # first outside buy after it: who / when
            nxt = next((t for t in tr[k0 + 1:] if t["buy"] and t["user"] != W and t["user"] not in st["insiders"]), None)
            sells = []
            for k, t in mine:
                if t["buy"] or k < k0: continue
                px = (tr[k - 1]["vsol"] / tr[k - 1]["vtok"]) if k > 0 else None     # curve spot price before its sell
                sells.append(dict(ds=t["s"] - t0["s"], dt=(t["bt"] or 0) - (t0["bt"] or 0), tok=t["tok"], sol=t["sol"], sig=t["sig"],
                                  mult=round((t["sol"] / t["tok"]) / px_in, 4) if px_in and t["tok"] else None,
                                  n_between=k - k0 - 1, nb_out=sum(1 for x in tr[k0 + 1:k] if x["buy"] and x["user"] != W),
                                  ns_out=sum(1 for x in tr[k0 + 1:k] if (not x["buy"]) and x["user"] != W),
                                  ins_sold_before=any((not x["buy"]) and x["user"] in st["insiders"] for x in tr[k0 + 1:k]),
                                  fee=t["fee"], tips=t["tips"]))
            # path after its buy: spot price multiples vs its entry at slot offsets (for exit-trigger analysis)
            path = []
            for t in tr[k0 + 1:]:
                if t["s"] - t0["s"] > 30: break
                if t["vtok"]: path.append((t["s"] - t0["s"], round((t["vsol"] / t["vtok"]) / px_in, 4) if px_in else None, int(t["buy"]), t["user"] == W, t["user"] in st["insiders"]))
            r.update(buy=dict(sig=t0["sig"], ds=t0["s"] - S, i=t0["i"], sol=t0["sol"] / 1e9, tok=t0["tok"], fee=t0["fee"], tips=t0["tips"], bt=t0["bt"],
                              pos_after_bundle=k0 - g, ahead_tx=ahead_tx, sells_ahead=sells_any_ahead,
                              mult_vs_bundle=round(px_in / p_b, 4) if p_b and px_in else None,
                              spot_before_vs_bundle=round((tr[k0 - 1]["vsol"] / tr[k0 - 1]["vtok"]) / p_b, 4) if p_b and k0 >= 1 else None,
                              next_out=dict(ds=nxt["s"] - t0["s"], sol=nxt["sol"] / 1e9) if nxt else None),
                     nbuys=len(buys), sells=sells, path=path[:400],
                     tok_sold=sum(t["tok"] for k, t in mine if not t["buy"]), tok_bought=sum(t["tok"] for k, t in buys))
            # trade-event PnL (curve SOL only; fees per side are in sol? buy event sol excludes the pump fee)
        out[m] = r
    return out
if __name__ == "__main__":
    dirs = [("R1", d) for d in sorted(glob.glob(os.path.join(rp.D, "phaseA", "b*")))] + [("R2", d) for d in sorted(glob.glob(os.path.join(HERE, "phaseA_snap", "b*")))]
    rows = collections.defaultdict(list); runof = {}
    with Pool(8) as p:
        for run, o in p.imap_unordered(scanA, dirs):
            for m, v in o.items(): rows[m] += v; runof[m] = run
    print("pass A: launches touched by CWiNFA:", len(rows), collections.Counter(runof.values()), flush=True)
    keys = collections.defaultdict(list)
    for m in rows: keys[(runof[m], rp.bucket(m))].append(m)
    res = {}
    with Pool(8) as p:
        for o in p.imap_unordered(work, [(r, b, ms) for (r, b), ms in keys.items()]): res.update(o)
    for m in res: res[m]["rows"] = rows[m]
    json.dump(res, open(os.path.join(HERE, "coll_cw.json"), "w"))
    print("saved", len(res), "| with its buy:", sum(1 for v in res.values() if v.get("buy")), "| failed-only:", sum(1 for v in res.values() if not v.get("buy") and v.get("failed")), flush=True)
