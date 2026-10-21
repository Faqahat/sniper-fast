# READ-ONLY (host; public RPC): add the block tx index of his first buy (trades_rows.json buy0.tidx) for mints in
# feat_rows.json where txs.jsonl rows were fetched before txs.py stored transactionIndex. Rewrites trades_rows.json.
# usage (in the data dir): python3 tidx_backfill.py ; then re-run features.py
import sys, os, json
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import txs  # noqa: E402
F = json.load(open('feat_rows.json')); T = json.load(open('trades_rows.json'))
need = {r['mint'] for r in F}
todo = [t for t in T if t['mint'] in need and t['buy0'].get('tidx') is None]


def j(t):
    x = txs.rpc("getTransaction", [t['buy0']['sig'], {"encoding": "json", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}])
    return t['mint'], (x.get('transactionIndex') if isinstance(x, dict) else None)


with ThreadPoolExecutor(2) as ex: got = dict(ex.map(j, todo))
for t in T:
    if t['mint'] in got: t['buy0']['tidx'] = got[t['mint']]
json.dump(T, open('trades_rows.json', 'w'))
print(len(todo), sum(v is not None for v in got.values()))
