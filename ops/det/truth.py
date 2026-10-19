#!/usr/bin/env python3
# READ-ONLY on-chain truth for pump.fun creates in a slot window (det audit 2026-10-18).
# Enumerates every create via getSignaturesForAddress(mint authority TSLvdd1...), fetches each tx (json, logs, inner ixs,
# loaded addresses) and records: create top-level vs CPI, create vs create_v2, ALT-loaded accounts, token program, quote
# mint, initial virtual reserves, flags (ix args as the engine parses them vs the CreateEvent), true dev buy (TradeEvents)
# vs the BEFORE engine read (sized discs only) and the AFTER read (sized + cap-family priced on the curve), URI host.
# usage: truth.py <out.jsonl> <slot_from> <slot_to> [workers]      (resumable: sigs already in out are skipped)
import sys, json, os, threading, collections
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/det")
from dlib import *

OUT, S0, S1 = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
NW = int(sys.argv[4]) if len(sys.argv) > 4 else 8

# ---- 1. signatures of the mint authority in [S0, S1]
sigs = []
before = None
pages = 0
while True:
    prm = {"limit": 1000}
    if before:
        prm["before"] = before
    r = rpc("getSignaturesForAddress", [MINT_AUTH, prm])
    pages += 1
    if not isinstance(r, list) or not r:
        print("sig page err", str(r)[:200], flush=True)
        break
    for x in r:
        if S0 <= x["slot"] <= S1:
            sigs.append(x)
    before = r[-1]["signature"]
    if r[-1]["slot"] < S0 or pages > 400:
        break
print(f"pages {pages} sigs in window {len(sigs)}", flush=True)
done = set()
if os.path.exists(OUT):
    for l in open(OUT):
        try:
            done.add(json.loads(l)["sig"])
        except Exception:
            pass
todo = [x for x in sigs if x["signature"] not in done]
print("todo", len(todo), flush=True)
lk = threading.Lock()
fh = open(OUT, "a")

BUY_MINT_IDX = {"buy": 2, "exact_sol_in": 2, "buy_v2": 1, "quote_in_v2": 1, "buy_v3": 1, "quote_in_v3": 1}


def analyze(x):
    sig = x["signature"]
    t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    rec = {"sig": sig, "slot": x["slot"], "err": x.get("err") is not None}
    if not isinstance(t, dict) or "meta" not in t:
        rec["miss"] = str(t)[:100]
        return rec
    msg = t["transaction"]["message"]
    meta = t["meta"] or {}
    static = msg["accountKeys"]
    la = meta.get("loadedAddresses") or {}
    keys = static + la.get("writable", []) + la.get("readonly", [])
    nstatic = len(static)
    rec.update(bt=t.get("blockTime"), ver=t.get("version"), nstatic=nstatic, nalt=len(keys) - nstatic, payer=static[0],
               signers=static[:msg["header"]["numRequiredSignatures"]], pump_static=PUMP in static)
    tr, cr = events(meta.get("logMessages"))
    # locate create ix: top-level first, else inner
    cix, top, outer = None, None, None
    for i, ix in enumerate(msg["instructions"]):
        if keys[ix["programIdIndex"]] == PUMP:
            d = b58dec(ix["data"])
            if d[:8] in (CREATE, CREATE_V2):
                cix, top = (ix, d), True
                break
    if cix is None:
        for inn in meta.get("innerInstructions") or []:
            for ix in inn.get("instructions") or []:
                if keys[ix["programIdIndex"]] == PUMP:
                    d = b58dec(ix["data"])
                    if d[:8] in (CREATE, CREATE_V2):
                        cix, top = (ix, d), False
                        outer = keys[msg["instructions"][inn["index"]]["programIdIndex"]]
                        break
            if cix:
                break
    if cix is None:
        rec["nocreate"] = True
        return rec
    ix, d = cix
    rec.update(top=top, outer=outer, kind="create_v2" if d[:8] == CREATE_V2 else "create")
    acc = ix["accounts"]
    rec["acct_idx"] = [acc[0] if len(acc) > 0 else None, acc[2] if len(acc) > 2 else None, acc[3] if len(acc) > 3 else None]
    rec["acct_alt"] = any(a is not None and a >= nstatic for a in rec["acct_idx"])
    mint = keys[acc[0]] if acc else None
    rec["mint"] = mint
    args = parse_create_args(d)
    rec["args"] = {k: v for k, v in args.items() if k != "uri"}
    uri = create_uri(d)
    rec["host"] = host_of(uri)
    rec["bl"] = is_bot_host(rec["host"])
    ev = [e for e in cr if e.get("mint") == mint]
    rec["ev"] = ev[0] if ev else None
    if rec["ev"]:
        rec["ev"].pop("name", None); rec["ev"].pop("symbol", None)
        rec["ev"]["uri"] = rec["ev"].get("uri", "")[:120]
    # true dev buy: trade events on this mint inside the create tx
    tev = [e for e in tr if e.get("mint") == mint]
    rec["true_dev"] = sum(e["sol"] for e in tev if e.get("buy"))
    rec["true_dev_tok"] = sum(e["tok"] for e in tev if e.get("buy"))
    rec["n_dev_trades"] = len(tev)
    rec["dev_users"] = sorted({e["user"] for e in tev if e.get("buy")})[:4]
    # engine reads (top-level pump buys only, as the shred detector sees them)
    before_dev, kinds = 0, []
    vq, vt, after_dev = VQ0, VT0, 0
    sized_first = {}
    for ix2 in msg["instructions"]:
        if keys[ix2["programIdIndex"]] != PUMP:
            continue
        d2 = b58dec(ix2["data"])
        k8 = d2[:8]
        name = SIZED.get(k8) or CAP.get(k8)
        if not name:
            continue
        a2 = ix2["accounts"]
        mi = BUY_MINT_IDX[name]
        bmint = keys[a2[mi]] if len(a2) > mi else None
        amt = int.from_bytes(d2[8:16], "little") if len(d2) >= 16 else 0
        cap = int.from_bytes(d2[16:24], "little") if len(d2) >= 24 else 0
        kinds.append([name, len(a2), bmint == mint, amt, cap])
        if k8 in SIZED and k8 not in sized_first:
            sized_first[k8] = amt
        if bmint != mint:
            continue
        if k8 in SIZED:
            after_dev += amt
            vq += amt
            vt = (VQ0 * VT0) // vq
        else:
            c, vq, vt = cap_cost(vq, vt, amt)
            if 0 < cap < c:
                c = cap
            after_dev += c
    before_dev = max(sized_first.values()) if sized_first else 0
    rec.update(dev_kinds=kinds[:6], dev_before=before_dev, dev_after=after_dev)
    rec["inner_buy"] = (rec["true_dev"] > 0 and not kinds)
    return rec


def work(x):
    try:
        rec = analyze(x)
    except Exception as ex:
        rec = {"sig": x["signature"], "slot": x["slot"], "exc": repr(ex)[:200]}
    with lk:
        fh.write(json.dumps(rec) + "\n")
        fh.flush()


with ThreadPoolExecutor(NW) as ex:
    list(ex.map(work, todo))
print("FINISHED", len(todo), "rpc", stats, flush=True)
