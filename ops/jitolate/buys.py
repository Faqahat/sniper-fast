# READ-ONLY per-buy timeline for the live test final1: log (DETECT/FAST-FIRE/RACE obs), sends jsonl (acks, bundle ids),
# chain (create slot/pos, our slot/pos, leaders), Jito explorer (landed bundle of our tx, its txs, tip, block index).
import sys, re, json, time, os, urllib.request, urllib.error
sys.path.insert(0, "/root/indep")
from common import rpc, get_block, is_vote, events, tx_summary, load_tipmap
tm = load_tipmap()
ME = "FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS"
LOG, SENDS = "/root/lat/live_land_final1.log", "/root/lat/sends_final1.jsonl"
CACHE = "/root/jitolate/cache"; os.makedirs(CACHE, exist_ok=True)
nodes = {x["pubkey"]: x for x in json.load(open("/root/stakepaths/clusternodes.json"))["result"]}
EPOCH0 = 458784000

def cached(key, fn):
    p = f"{CACHE}/{key}.json"
    if os.path.exists(p):
        return json.load(open(p))
    v = fn()
    if v is not None and not (isinstance(v, dict) and "__err" in v):
        json.dump(v, open(p, "w"))
    return v

def jget(url):
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"user-agent": "research"})
            with urllib.request.urlopen(req, timeout=20) as r:
                v = json.load(r); time.sleep(0.6); return v
        except urllib.error.HTTPError as e:
            if e.code in (404, 400):
                time.sleep(0.6); return {"__nf": e.code}
            time.sleep(2 * (i + 1))
        except Exception:
            time.sleep(2 * (i + 1))
    return None

def bundle_of_tx(sig):
    a = cached("jtx_" + sig[:40], lambda: jget(f"https://bundles.jito.wtf/api/v1/bundles/transaction/{sig}"))
    if not isinstance(a, list) or not a:
        return None
    bid = a[0]["bundle_id"]
    b = cached("jb_" + bid, lambda: jget(f"https://bundles.jito.wtf/api/v1/bundles/bundle/{bid}"))
    return b[0] if isinstance(b, list) and b else {"bundleId": bid}

def blk(s):
    return cached(f"blk_{s}", lambda: get_block(s))

def leader(s):
    r = cached(f"ldr_{s}", lambda: rpc("getSlotLeaders", [s, 1]))
    pk = r[0] if isinstance(r, list) and r else "?"
    return pk, nodes.get(pk, {}).get("clientId", "?")

def nonvote(b):
    return [t for t in b["transactions"] if not is_vote(t)]

def main():
    # ---- parse log
    L = open(LOG).read().splitlines()
    fires = []
    det = {}
    obs = {}
    for l in L:
        m = re.search(r"DETECT feed=(\S+) first=(\d) dt_us=(\d+) slot=(\d+) t_rx=(\d+) poh_ms=(\S+) lag_ms=(\S+) mint=(\w+)", l)
        if m:
            d = det.setdefault(m.group(8), {})
            d.setdefault("feeds", {})[m.group(1)] = int(m.group(5))
            if m.group(6) != "-": d.setdefault("poh_ms", float(m.group(6)))
            continue
        m = re.search(r"FAST-FIRE tag=(\d+) slot=(\d+) mint=(\w+) (route:\S+) leader=(\S+) client=(\S+) .*tips=(\d+) .*decide_to_first_write_us=([\d.]+) writes: (.*)", l)
        if m:
            fires.append(dict(tag=int(m.group(1)), slot=int(m.group(2)), mint=m.group(3), route=m.group(4), leader=m.group(5), client=m.group(6),
                              tips=int(m.group(7)), d2w=float(m.group(8)), writes=m.group(9)))
            continue
        m = re.search(r"RACE obs slot=\d+ mint=(\w+) .* outs=(\S+)", l)
        if m:
            obs[m.group(1)] = m.group(2)
        m = re.search(r"BUY\s+sig=(\w+) send_slot=(\d+) land_slot=(\d+)", l)
        if m and fires and "sig" not in fires[-1]:
            fires[-1]["sig"], fires[-1]["land"] = m.group(1), int(m.group(3))
        m = re.search(r"JITO-RESULT path=jito-bundle sig=(\w+) (.*)", l)
        if m and fires:
            fires[-1]["jito_result"] = m.group(2)
    acks = {}
    for l in open(SENDS):
        r = json.loads(l)
        if r.get("ev") == "fast_ack":
            acks.setdefault(r["tag"], {})[r["path"]] = r

    out = []
    for f in fires:
        M, S = f["mint"], f["slot"]
        d = det.get(M, {})
        t_det = min(d.get("feeds", {}).values()) if d.get("feeds") else None
        f["first_feed"] = min(d["feeds"], key=d["feeds"].get) if d.get("feeds") else None
        f["poh_ms_create"] = d.get("poh_ms")
        a = acks.get(f["tag"], {})
        f["acks"] = {p: round(v["ack_ms"], 2) for p, v in a.items()}
        send_t = min((v["t_ns"] - v["ack_ms"] * 1e6) for v in a.values()) if a else None
        f["detect_to_send_ms"] = round((send_t - t_det) / 1e6, 2) if send_t and t_det else None
        f["our_bundle_id"] = a.get("jito-bundle", {}).get("reply")
        # our tx seen in shreds (RACE obs, ms after create detect)
        seen = [x for x in (obs.get(M) or "").split(",") if ":FRZh63" in x]
        f["our_seen_ms"] = float(seen[0].split(":")[0]) if seen else None
        # chain: create slot
        b = blk(S); txs = nonvote(b)
        ci = None
        for i, t in enumerate(txs):
            tr, cr = events((t.get("meta") or {}).get("logMessages"))
            if any(c["mint"] == M for c in cr):
                ci = i; break
        f["S_nonvote"] = len(txs); f["create_idx"] = ci
        f["S_leader"], f["S_client"] = leader(S)
        f["S_slot_in_window"] = (S - EPOCH0) % 4
        cs = tx_summary(txs[ci], tm)[0]
        f["create_sig"] = cs["sig"]; f["create_tips"] = cs["tips"]
        cb = bundle_of_tx(cs["sig"])
        f["create_bundle"] = {"n": len(cb.get("txSignatures", [])), "blockIndex": cb.get("blockIndex"), "tip": cb.get("landedTipLamports")} if cb else None
        # count successful buys of M in S after create, until ours or end
        after = []
        for j, t in enumerate(txs[ci + 1:], start=1):
            meta = t.get("meta") or {}
            tr, _ = events(meta.get("logMessages"))
            ev = [e for e in tr if e["mint"] == M and e["buy"]]
            if ev:
                s2 = tx_summary(t, tm)[0]
                after.append({"d": j, "sig": s2["sig"], "payer": s2["payer"][:6], "ok": meta.get("err") is None, "sol": round(sum(e["sol"] for e in ev) / 1e9, 3),
                              "tips": s2["tips"], "cu_price": s2["cu_price"], "is_me": s2["payer"] == ME})
        f["S_buys_after_create"] = after
        # our landed tx
        land = f["land"]
        bl = blk(land); txl = nonvote(bl)
        myi = next((i for i, t in enumerate(txl) if t["transaction"]["signatures"][0] == f["sig"]), None)
        f["land_idx"], f["land_nonvote"] = myi, len(txl)
        f["land_leader"], f["land_client"] = leader(land)
        f["land_frac"] = round(myi / len(txl), 3) if myi is not None else None
        if land != S and myi is not None:
            # buys of M in land slot before us
            f["buys_before_us_in_land_slot"] = sum(1 for t in txl[:myi] if any(e["mint"] == M and e["buy"] for e in events((t.get("meta") or {}).get("logMessages"))[0]))
        mb = bundle_of_tx(f["sig"])
        if mb:
            others = [s for s in mb.get("txSignatures", []) if s != f["sig"]]
            oth = []
            for s in others:
                t = cached("tx_" + s[:40], lambda: rpc("getTransaction", [s, {"encoding": "json", "maxSupportedTransactionVersion": 1}]))
                if isinstance(t, dict) and "transaction" in t:
                    ss = tx_summary(t, tm)[0]; oth.append({"sig": s[:10], "payer": ss["payer"][:8], "tips": ss["tips"]})
            f["landed_bundle"] = {"id": mb.get("bundleId"), "same_as_ours": mb.get("bundleId") == f["our_bundle_id"], "slot": mb.get("slot"), "blockIndex": mb.get("blockIndex"),
                                  "tip": mb.get("landedTipLamports"), "ntx": len(mb.get("txSignatures", [])), "others": oth, "validator": (mb.get("validator") or "")[:8]}
        else:
            f["landed_bundle"] = None
        out.append(f)
        print(json.dumps(f), flush=True)
    json.dump(out, open("/root/jitolate/buys.json", "w"), indent=1)

if __name__ == '__main__':
    main()
