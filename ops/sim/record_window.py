# READ-ONLY, zero cost. RECORD the on-chain trade history of the launches a (dry) run saw, so the what-if simulation can
# be re-run later with any size / fee / exit.
#   - every launch the engine FIRED on, and every other launch with a Lunar tip and a creator bundle of 2-9.5 SOL
#     (the rule-#2 neighbourhood: far leaders, late creates, Lunar-not-largest, bundles outside 3-5) for comparison;
#   - exact in-block order for slots S..S+K_BLK (getBlock), then every trade up to S+WIN slots (signatures + txs,
#     ordered inside each slot by chaining the curve state);
#   - per launch: create index, dev buy, glued creator bundle, largest top-level transfer (Lunar?), leader + RTT/client,
#     why the engine skipped it (from the log).
# usage: python3 record_window.py <engine log> <out dir> [K_BLK=30] [WIN=280] [LIMIT=0]
import sys, os, re, json, base64, time, threading
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/indep")
from common import rpc, get_block, is_vote, b58dec, b58enc, TRADE_DISC, CREATE_DISC, parse_create, load_tipmap

LOG, OUT = sys.argv[1], sys.argv[2]
K_BLK = int(sys.argv[3]) if len(sys.argv) > 3 else 30
WIN = int(sys.argv[4]) if len(sys.argv) > 4 else 280
LIMIT = int(sys.argv[5]) if len(sys.argv) > 5 else 0
os.makedirs(OUT, exist_ok=True)
SYS = "11111111111111111111111111111111"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
TM = load_tipmap()
RTT = {}
try:
    RTT = json.load(open("/root/fix2/leader_rtt_new.json"))["leaders"]
except Exception:
    pass
GEO = {}
try:
    GEO = {r["pk"]: r for r in json.load(open("/root/fix2/leader_geo.json"))["rows"]}
except Exception:
    pass

txt = open(LOG, errors="replace").read()
m = re.search(r"POH CLOCK: .*?-> ([0-9.]+) ms a slot", txt)
SLOT_MS = float(m.group(1)) if m else 217.0
fires = {mm: int(s) for s, mm in re.findall(r"^\s*FIRE slot=(\d+) mint=(\w+)", txt, re.M)}
base = {}
for mm in re.finditer(r"DETECT feed=\S+ first=1 .*?slot=(\d+) .*?mint=(\w+) .*?verdict=(\w+)", txt):
    if mm.group(3) == "pass":
        base.setdefault(mm.group(2), int(mm.group(1)))
for mint, s in fires.items():
    base.setdefault(mint, s)
decide = {mm.group(1): mm.group(2) for mm in re.finditer(r"RACE decide slot=\d+ mint=(\w+) .*?pass=(\w+)", txt)}
static_rej = set(re.findall(r"RACE reject-static slot=\d+ mint=(\w+)", txt))
t_first = re.search(r"DETECT feed=\S+ first=1 dt_us=\d+ slot=(\d+)", txt)
print(f"log: slot {SLOT_MS} ms; base-pass creates {len(base)}; fires {len(fires)}", flush=True)


def trades_of(logs):
    out = []
    for l in logs or []:
        if not l.startswith("Program data: "): continue
        try:
            raw = base64.b64decode(l[14:] + "===")
        except Exception:
            continue
        if raw[:8] != TRADE_DISC or len(raw) < 225: continue
        g = lambda a, b: int.from_bytes(raw[a:b], "little")
        out.append(dict(mint=b58enc(raw[8:40]), sol=g(40, 48), tok=g(48, 56), buy=raw[56], user=b58enc(raw[57:89]), vsol=g(97, 105),
                        vtok=g(105, 113), fbps=g(161, 169), cbps=g(209, 217)))
    return out


def creates_of(logs):
    out = []
    for l in logs or []:
        if not l.startswith("Program data: "): continue
        try:
            raw = base64.b64decode(l[14:] + "===")
        except Exception:
            continue
        if raw[:8] == CREATE_DISC:
            c = parse_create(raw)
            if c: out.append(c)
    return out


BLK = {}
blk_lock = threading.Lock()


def compact(x):
    # keep ONLY what the recorder needs from a block (pump trades/creates + the create tx's transfers); a full block is
    # tens of MB as Python objects and caching them OOM-killed the recorder on the 4 GB server (2026-10-20)
    rows = []; n = 0
    for t in x["transactions"]:
        if is_vote(t): continue
        meta = t.get("meta") or {}
        logs = meta.get("logMessages")
        i = n; n += 1
        tr = trades_of(logs)
        cr = creates_of(logs)
        if not tr and not cr: continue
        row = dict(idx=i, ok=meta.get("err") is None, payer=t["transaction"]["message"]["accountKeys"][0], trades=tr, creates=cr)
        if cr:
            (lam, dst), any_moon, signers = largest_toplevel_transfer(t)
            row.update(largest=(lam, dst), any_moon=any_moon, signers=signers)
        rows.append(row)
    return dict(blockTime=x.get("blockTime"), n_txs=n, rows=rows)


def blk(s):
    # a failed fetch is RETRIED with back-off and never cached (a cached failure silently dropped every launch in that slot)
    with blk_lock:
        if s in BLK: return BLK[s]
    b = None
    for attempt in range(5):
        x = get_block(s)
        if isinstance(x, dict) and "transactions" in x:
            b = compact(x); x = None
            break
        if isinstance(x, dict) and x.get("__err") in (-32007, -32009):   # slot skipped / missing: a real empty slot
            return None
        time.sleep(1.5 * (attempt + 1))
    if b is not None:
        with blk_lock:
            BLK[s] = b
    return b


def largest_toplevel_transfer(t):
    msg = t["transaction"]["message"]; meta = t["meta"]
    la = meta.get("loadedAddresses") or {}
    keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
    nsig = msg["header"]["numRequiredSignatures"]
    best = (0, None); any_moon = False
    for ix in msg["instructions"]:
        if keys[ix["programIdIndex"]] != SYS: continue
        d = b58dec(ix["data"])
        if len(d) >= 12 and int.from_bytes(d[:4], "little") == 2 and len(ix["accounts"]) >= 2:
            if ix["accounts"][1] < nsig: continue
            dst = keys[ix["accounts"][1]]; lam = int.from_bytes(d[4:12], "little")
            any_moon |= dst.startswith("moon")
            if lam > best[0]: best = (lam, dst)
    return best, any_moon, keys[:nsig]


def scan_create(mint, S):
    b = blk(S)
    if not b: return None
    rows = b["rows"]
    for k, r in enumerate(rows):
        cr = [c for c in r["creates"] if c["mint"] == mint]
        if not cr: continue
        tr = [e for e in r["trades"] if e["mint"] == mint]
        lam, dst = r["largest"]
        gl, gsol, members = 0, 0, set(r["signers"]) | {cr[0]["user"], cr[0]["creator"]}
        nxt = r["idx"] + 1; glued_end = nxt
        for r2 in rows[k + 1:]:
            if r2["idx"] != nxt: break            # a non-pump (or other) tx breaks the glued run
            ev = [e for e in r2["trades"] if e["mint"] == mint and e["buy"]]
            if not ev or not r2["ok"]: break
            gl += 1; gsol += sum(e["sol"] for e in ev); members |= {e["user"] for e in ev}; members.add(r2["payer"])
            nxt += 1; glued_end = nxt
        return dict(cidx=r["idx"], n_txs=b["n_txs"], glued_end=glued_end, dev=sum(e["sol"] for e in tr if e["buy"]) / 1e9, gsol=gsol / 1e9, glued=gl,
                    bundle_members=sorted(members), largest_to=(dst or "")[:44], largest_lam=lam, largest_moon=bool(dst and dst.startswith("moon")),
                    any_moon=r["any_moon"], name=cr[0].get("name"), symbol=cr[0].get("symbol"), uri=cr[0].get("uri"), creator=cr[0].get("creator"),
                    block_time=b["blockTime"])
    return None


def block_trades(mint, s, after_idx=-1):
    b = blk(s)
    if not b: return None
    out = []
    for r in b["rows"]:
        if r["idx"] <= after_idx or not r["ok"]: continue
        for e in r["trades"]:
            if e["mint"] == mint:
                e = dict(e); e.update(slot=s, idx=r["idx"], payer=r["payer"]); out.append(e)
    return out


def pre_state(e):
    return (e["vsol"] - e["sol"], e["vtok"] + e["tok"]) if e["buy"] else (e["vsol"] + e["sol"], e["vtok"] - e["tok"])


def chain_order(evs, start_state):
    out, cur, rest = [], start_state, list(evs)
    while rest:
        k = next((n for n, e in enumerate(rest) if pre_state(e) == cur), None)
        if k is None:   # break in the chain: take the closest pre-state
            k = min(range(len(rest)), key=lambda n: abs(pre_state(rest[n])[0] - (cur[0] if cur else 0)))
        e = rest.pop(k); out.append(e); cur = (e["vsol"], e["vtok"])
    return out


def later_trades(mint, s_from, s_to):
    sigs, before = [], None
    for _ in range(40):
        p = {"limit": 1000}
        if before: p["before"] = before
        r = rpc("getSignaturesForAddress", [mint, p])
        if not isinstance(r, list) or not r: break
        sigs += [x for x in r if s_from <= x["slot"] <= s_to and x.get("err") is None]
        before = r[-1]["signature"]
        if r[-1]["slot"] < s_from or len(r) < 1000: break
    out = []
    def get(x):
        t = rpc("getTransaction", [x["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
        if not isinstance(t, dict) or "meta" not in t: return []
        return [dict(e, slot=t["slot"], idx=None, payer=t["transaction"]["message"]["accountKeys"][0]) for e in trades_of(t["meta"].get("logMessages")) if e["mint"] == mint]
    with ThreadPoolExecutor(4) as ex:
        for evs in ex.map(get, sigs):
            out += evs
    return out


def reason(mint):
    if mint in fires: return "fired"
    if mint in static_rej: return "static reject (Lunar not the largest tip / name / dev)"
    if mint in decide: return "race gate passed, create-ms gate skipped (late/unknown)" if decide[mint] == "true" else "race reject (bundle not 3-5 / unknown)"
    return "not watched: far leader (close-leader gate) or base filter"


def record(item):
    mint, S = item
    path = os.path.join(OUT, mint + ".json")
    if os.path.exists(path): return mint, "cached"
    c = scan_create(mint, S)
    if not c: return mint, "create not found"
    keep = mint in fires or (c["any_moon"] and 2.0 <= c["gsol"] <= 9.5)
    if not keep: return mint, None
    tr = block_trades(mint, S, c["cidx"])          # same slot, after the create (incl. the glued bundle)
    for s in range(S + 1, S + K_BLK + 1):
        x = block_trades(mint, s)
        if x is None: continue
        tr += x
    last = max([t["slot"] for t in tr] or [S])
    late = later_trades(mint, S + K_BLK + 1, S + WIN)
    by = {}
    for e in late: by.setdefault(e["slot"], []).append(e)
    cur = (tr[-1]["vsol"], tr[-1]["vtok"]) if tr else None
    for s in sorted(by):
        o = chain_order(by[s], cur)
        tr += o
        if o: cur = (o[-1]["vsol"], o[-1]["vtok"])
    ld = rpc("getSlotLeaders", [S, 1]); ld = ld[0] if isinstance(ld, list) and ld else None
    lr = RTT.get(ld or "", {})
    g = GEO.get(ld or "", {})
    rec = dict(mint=mint, S=S, slot_ms=SLOT_MS, fired=mint in fires, engine=reason(mint), leader=ld, leader_rtt=lr.get("rtt"), leader_client=lr.get("client"),
               leader_city=g.get("city"), leader_asn=g.get("asn"), rule2_largest=bool(c["largest_moon"] and 2.95 <= c["gsol"] <= 5.05 and 0.49 <= c["dev"] <= 8.1),
               **c, trades=tr, recorded_at=time.time(), window_slots=WIN, exact_order_slots=K_BLK)
    json.dump(rec, open(path, "w"))
    return mint, f"recorded {len(tr)} trades"


items = sorted(base.items(), key=lambda kv: kv[1])
if LIMIT: items = items[:LIMIT]
n_rec = 0; missing = []
with ThreadPoolExecutor(3) as ex:
    for mint, st in ex.map(record, items):
        if st == "create not found":
            missing.append(mint)
            if mint in fires: print(f"  !!! FIRED {mint} NOT RECORDED: create block could not be read", flush=True)
        elif st:
            n_rec += 1
            print(f"  {mint[:10]} {'FIRED ' if mint in fires else ''}{st}", flush=True)
print(f"not recorded (create block unreadable): {len(missing)} of {len(items)}, of which fired: {sum(1 for x in missing if x in fires)}", flush=True)
json.dump(dict(log=LOG, slot_ms=SLOT_MS, fires=fires, n_base=len(base), recorded=n_rec, t=time.time()), open(os.path.join(OUT, "_index.json"), "w"))
print(f"DONE: recorded {n_rec} launches into {OUT}", flush=True)
