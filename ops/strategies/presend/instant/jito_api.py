#!/usr/bin/env python3
# Read-only helper: the PUBLIC Jito bundle explorer API (bundles.jito.wtf, no key). transaction/<sig> -> the bundle id of a landed
# tx (404 = not in a Jito bundle the explorer knows); bundle/<id> -> slot, validator, tippers, landed tip, block index, all tx
# signatures of the bundle. Paced to <= 2 calls/s; every answer is cached on disk (never asked twice).
import json, os, time, urllib.request, urllib.error, threading
CACHE = "/home/moiz/sniper-data/presend_instant/jito_cache.json"
_C = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
_lk = threading.Lock(); _last = [0.0]; _n = [0]
def _get(path):
    if path in _C: return _C[path]
    for i in range(4):
        with _lk:
            w = _last[0] + 0.5 - time.time()
            if w > 0: time.sleep(w)
            _last[0] = time.time(); _n[0] += 1
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request("https://bundles.jito.wtf/api/v1/bundles/" + path, headers={"user-agent": "sniper-research"}), timeout=20))
            _C[path] = r; return r
        except urllib.error.HTTPError as e:
            if e.code == 404: _C[path] = None; return None
            time.sleep(2 * (i + 1))
        except Exception:
            time.sleep(2 * (i + 1))
    return "ERR"
def save():
    with _lk:
        tmp = CACHE + ".tmp"; json.dump(_C, open(tmp, "w")); os.replace(tmp, CACHE)
def bundle_of(sig):
    j = _get("transaction/" + sig)
    if j == "ERR": return "ERR"
    if not (isinstance(j, list) and j): return None
    bid = j[0].get("bundle_id"); d = _get("bundle/" + bid)
    if d == "ERR": return dict(bundle_id=bid, err=True)
    d = d[0] if isinstance(d, list) and d else {}
    return dict(bundle_id=bid, txs=d.get("txSignatures"), tippers=d.get("tippers"), tip=d.get("landedTipLamports"), validator=d.get("validator"),
                slot=d.get("slot"), block_index=d.get("blockIndex"), ts=d.get("timestamp"), cu=d.get("landedCu"))
def calls(): return _n[0]
