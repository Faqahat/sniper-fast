#!/usr/bin/env python3
# READ-ONLY. For each target create (slot + create sig or mint) fetch the create block S and record:
# create tx features, CreateEvent (incl. extra fields), dev buy, glued creator-bundle run (same rule as /root/bsplit),
# every later buy/sell of the mint in S (order, user, sol, vsol), leader + client.
# usage: blk.py <targets.json> <out.jsonl> [workers]
import sys, json, os, threading, time, collections, base64
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/indep")
from common import *

INP, OUT = sys.argv[1], sys.argv[2]
NW = int(sys.argv[3]) if len(sys.argv) > 3 else 8
T22 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
TARGET = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
tipmap = load_tipmap()
nodes = {x["pubkey"]: x for x in json.load(open("/root/stakepaths/clusternodes.json"))["result"]}
targets = json.load(open(INP))
done = set()
if os.path.exists(OUT):
    for l in open(OUT):
        try:
            r = json.loads(l)
            done.add(r["key"])
        except Exception:
            pass
byslot = collections.defaultdict(list)
for t in targets:
    k = t.get("sig") or t.get("mint")
    if k in done:
        continue
    t["key"] = k
    byslot[t["slot"]].append(t)
slots = sorted(byslot)
print("slots todo", len(slots), "targets", sum(len(v) for v in byslot.values()), flush=True)

# leaders
leaders = {}
lk = threading.Lock()


def fetch_leaders(lo, hi):
    s = lo
    while s <= hi:
        n = min(5000, hi - s + 1)
        r = rpc("getSlotLeaders", [s, n])
        if isinstance(r, list):
            for i, l in enumerate(r):
                leaders[s + i] = l
        s += n


rng = []
for s in slots:
    if rng and s - rng[-1][1] < 5000:
        rng[-1][1] = s + 2
    else:
        rng.append([s, s + 2])
for lo, hi in rng:
    fetch_leaders(lo, hi)
print("leaders", len(leaders), flush=True)


def parse_create_full(raw):
    o = 8
    strs = []
    for _ in range(3):
        n = int.from_bytes(raw[o:o + 4], "little"); o += 4
        strs.append(raw[o:o + n].decode("utf8", "replace")); o += n
    mint = b58enc(raw[o:o + 32]); o += 32
    o += 32
    user = b58enc(raw[o:o + 32]); o += 32
    creator = b58enc(raw[o:o + 32]) if len(raw) >= o + 32 else user
    o += 32
    extra = {"rawlen": len(raw)}
    try:
        if len(raw) >= o + 8 * 5:
            extra["ts"] = int.from_bytes(raw[o:o + 8], "little", signed=True); o += 8
            extra["vtok"] = int.from_bytes(raw[o:o + 8], "little"); o += 8
            extra["vsol"] = int.from_bytes(raw[o:o + 8], "little"); o += 8
            extra["rtok"] = int.from_bytes(raw[o:o + 8], "little"); o += 8
            extra["supply"] = int.from_bytes(raw[o:o + 8], "little"); o += 8
        if len(raw) >= o + 32:
            extra["tokprog"] = b58enc(raw[o:o + 32]); o += 32
        if len(raw) >= o + 1:
            extra["flag1"] = raw[o]; o += 1
        if len(raw) > o:
            extra["tail"] = raw[o:].hex()
            if len(raw) >= o + 33 and any(raw[o + 1:o + 33]):
                extra["quote"] = b58enc(raw[o + 1:o + 33])
    except Exception:
        pass
    return dict(name=strs[0][:60], symbol=strs[1][:30], uri=strs[2][:300], mint=mint, user=user, creator=creator, x=extra)


def cevents(logs):
    out = []
    for l in logs or []:
        if l.startswith("Program data: "):
            try:
                raw = base64.b64decode(l[14:] + "===")
            except Exception:
                continue
            if raw[:8] == CREATE_DISC:
                try:
                    out.append(parse_create_full(raw))
                except Exception:
                    pass
    return out


out = open(OUT, "a")
olk = threading.Lock()
stats = collections.Counter()


def process(S):
    blk = get_block(S)
    if not isinstance(blk, dict) or "transactions" not in blk:
        with olk:
            for t in byslot[S]:
                out.write(json.dumps({"key": t["key"], "slot": S, "tag": t.get("tag"), "missing": "block"}) + "\n")
            stats["missing_block"] += 1
        return
    txs = blk["transactions"]
    want_sig = {t["sig"]: t for t in byslot[S] if t.get("sig")}
    want_mint = {t["mint"]: t for t in byslot[S] if t.get("mint")}
    found = set()
    nv = -1
    nvl = []
    for t in txs:
        if is_vote(t):
            nvl.append(None)
        else:
            nv += 1
            nvl.append(nv)
    for idx, t in enumerate(txs):
        if nvl[idx] is None:
            continue
        meta = t.get("meta") or {}
        if meta.get("err") is not None:
            continue
        sig = t["transaction"]["signatures"][0]
        logs = meta.get("logMessages") or []
        if sig not in want_sig and not any(("Instruction: Create" in l) for l in logs):
            continue
        crs = cevents(logs)
        for c in crs:
            tgt = want_sig.get(sig) or want_mint.get(c["mint"])
            if not tgt:
                continue
            mint = c["mint"]
            found.add(tgt["key"])
            s, keys = tx_summary(t, tipmap)
            tr, _ = events(logs)
            cev = [e for e in tr if e["mint"] == mint]
            dev = sum(e["sol"] for e in cev if e["buy"])
            base = cev[-1]["vsol"] if cev else (c["x"].get("vsol") or VSOL0)
            v0 = c["x"].get("vsol") or VSOL0
            ins = [l for l in logs if l.startswith("Program log: Instruction: ")]
            try:
                ci = keys.index(c["creator"]) if c["creator"] in keys else keys.index(c["user"])
                cpre = meta["preBalances"][ci]
                cpost = meta["postBalances"][ci]
            except Exception:
                cpre = cpost = None
            rec = {"key": tgt["key"], "tag": tgt.get("tag"), "slot": S, "bt": blk.get("blockTime"), "leader": leaders.get(S),
                   "client": nodes.get(leaders.get(S), {}).get("clientId", "?"), "ntx": len(txs), "nnv": nv + 1,
                   "mint": mint, "csig": sig, "cidx": idx, "cnv": nvl[idx], "name": c["name"], "symbol": c["symbol"], "uri": c["uri"],
                   "creator": c["creator"], "user": c["user"], "cx": c["x"], "payer": s["payer"], "signers": s["signers"],
                   "cu_price": s["cu_price"], "cu_limit": s["cu_limit"], "fee": s["fee"], "cuu": s["cuu"], "tips": s["tips"],
                   "keytip": s["keytip"], "progs": s["progs"], "ins": [l[26:40] for l in ins][:12], "t22": T22 in keys,
                   "nkeys": len(keys), "dev": dev, "dev_buys": [[e["user"][:8], e["sol"]] for e in cev if e["buy"]],
                   "base": base, "v0": v0, "cpre": cpre, "cpost": cpost, "ver": t["transaction"].get("version", "legacy") if isinstance(t.get("transaction"), dict) else None}
            rec["ver"] = t.get("version")
            # subsequent txs of the mint in S, glued run
            glued, gsol, gv, run_open = 0, 0, base, True
            gsig = []
            later = []
            for j in range(idx + 1, len(txs)):
                if nvl[j] is None:
                    continue
                tt = txs[j]
                m2 = tt.get("meta") or {}
                ok = m2.get("err") is None
                tr2, _ = events(m2.get("logMessages")) if ok else ([], [])
                ev = [e for e in tr2 if e["mint"] == mint]
                evb = [e for e in ev if e["buy"]]
                if run_open:
                    if evb and ok:
                        glued += 1
                        gsol += sum(e["sol"] for e in evb)
                        gv = evb[-1]["vsol"]
                        gsig.append(tt["transaction"]["signatures"][0][:12])
                    else:
                        run_open = False
                touch = False
                if not ev:
                    msg = tt["transaction"]["message"]
                    if mint in msg["accountKeys"] or mint in (m2.get("loadedAddresses") or {}).get("writable", []):
                        touch = True
                if ev or touch:
                    s2, k2 = tx_summary(tt, tipmap)
                    later.append({"d": nvl[j] - nvl[idx], "sig": s2["sig"][:20], "payer": s2["payer"], "ok": ok,
                                  "ev": [[e["buy"], e["user"], e["sol"], e["tok"], e["vsol"]] for e in ev],
                                  "cu_price": s2["cu_price"], "tips": [[x[0], x[1]] for x in s2["tips"]], "glued": run_open and bool(evb) and ok,
                                  "his": TARGET in s2["signers"]})
            rec.update(glued=glued, gsol=gsol, gv=gv, bmult=(gv / base) ** 2, gsig=gsig, later=later[:400], nlater=len(later))
            with olk:
                out.write(json.dumps(rec) + "\n")
                out.flush()
                stats["ok"] += 1
    with olk:
        for t in byslot[S]:
            if t["key"] not in found:
                out.write(json.dumps({"key": t["key"], "slot": S, "tag": t.get("tag"), "missing": "create_not_in_block"}) + "\n")
                stats["notfound"] += 1


def worker(chunk):
    for S in chunk:
        try:
            process(S)
        except Exception as ex:
            stats["exc"] += 1
            print("EXC", S, repr(ex)[:300], flush=True)
        stats["slots"] += 1
        if stats["slots"] % 100 == 0:
            print(time.strftime("%H:%M:%S"), dict(stats), flush=True)


k = max(1, (len(slots) + NW - 1) // NW)
chunks = [slots[i::NW] for i in range(NW)]
with ThreadPoolExecutor(max_workers=NW) as ex:
    list(ex.map(worker, chunks))
print("FINISHED", dict(stats), flush=True)
