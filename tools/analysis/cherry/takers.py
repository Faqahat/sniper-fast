#!/usr/bin/env python3
"""Who took our opportunities: for every live trade of ours that landed and failed, read its block (and the slots
between the trigger and it), list in block order every transaction that touched our buy or sell pool, and compare
the ones that took the gap (touched both pools, signer gained SOL/WSOL) with us: position, priority fee, CU price, tip.
Read-only RPC (getBlock). Writes takers.jsonl next to this script's output dir and prints a summary."""
import json, os, sys, time, urllib.request, collections, statistics as S

RUNS = sys.argv[1].split(",") if len(sys.argv) > 1 else ["live-run-1", "live-run-2"]
BASE = "/root/arb-lab/runs"
WSOL = "So11111111111111111111111111111111111111112"
CB = "ComputeBudget111111111111111111111111111111"
TIPS = set("""96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5 HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY
ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49 DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt
DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL 3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT 4ACfpUFoaSD9bfPdeu6DBt89gB6ENTeHBXCAi87NhDEE
D2L6yPZ2FmmmTKPgzaMKdhu6EWZcTpLy1Vhx8uvZe7NZ 9bnz4RShgq1hAnLnZbP8kbgBg1kEmcJBYQq3gQbmnSta 5VY91ws6B2hMmBFRsXkoAAdsPHBJwRfBht4DXox3xkwn
2nyhqdwKcJZR2vcqCyrYsaPVdAnFoJjiksCXJ7hfEYgD 2q5pghRs6arqVjRvT5gfgWfWcHWmw1ZuCzphgd5KfWGJ wyvPkWjVZz1M8fHQnMMCDTQDbkManefNNhweYk5WkcF
3KCKozbAaF75qEU33jtzozcJ29yJuaLJTy2jFdzUY8bT 4vieeGHPYPG2MmyPRcYjdiDmmhN3ww7hsFNap8pVN3Ey 4TQLFNWK8AovT1gFvda5jfw2oJeRMKEmw7aH6MGBJ3or
t1TcSg9biJsz4NjKjhopK8QZzPS4KzBgFSszu5QTGgF t2XFAFBaUkCzxJwEbLWFX9PKFjfBCp2tSyFtx5z4RZM t3QLYyXH4vZYbEifLqjD581t5dPVhq9LABxWceySzL2
t46SqGmwStEffUMp1fr2xmv5uyR85TB9annJuLKLf83 t55hdzzftxWkYy3J8t32C9RRcZDuMZ4LDuBmbTzJFkU t6UtTQLUGHJJrzxAb8PBBZdZKra8SWUqvTv9zPnxKNz
t7qUQU35sLpPydh42BcPmtEfTWW8gBe4Ry3gjwVnokJ t8pPgarSK3TnuLbbHmoE1RCQdLxfxuPqNTyFjBKahok t96GGdw3MiaGR993XN8PSsRpKGXx56t5Wf6zcF1hBpY
astrazznxsGUhWShqgNtAdfrzP2G83DzcWVJDxwV9bF astra4uejePWneqNaJKuFFA8oonqCE1sqF6b45kDMZm astra9xWY93QyfG6yM8zwsKsRodscjQ2uU2HKNL5prk
astraRVUuTHjpwEVvNBeQEgwYx9w9CFyfxjYoobCZhL astraEJ2fEj8Xmy6KLG7B3VfbKfsHXhHrNdCQx7iGJK astraubkDw81n4LuutzSQ8uzHCv4BhPVhfvTcYv8SKC
astraZW5GLFefxNPAatceHhYjfA1ciq9gvfEg2S47xk astrawVNP4xDBKT7rAdxrLYiTSTdqtUr63fSMduivXK AstrA1ejL4UeXC2SBP4cpeEmtcFPZVLxx3XGKXyCW6to
AsTra79FET4aCKWspPqeSFvjJNyp96SvAnrmyAxqg5b7 AstrABAu8CBTyuPXpV4eSCJ5fePEPnxN8NqBaPKQ9fHR AsTRADtvb6tTmrsqULQ9Wji9PigDMjhfEMza6zkynEvV
AsTRAEoyMofR3vUPpf9k68Gsfb6ymTZttEtsAbv8Bk4d AStrAJv2RN2hKCHxwUMtqmSxgdcNZbihCwc1mCSnG83W Astran35aiQUF57XZsmkWMtNCtXGLzs8upfiqXxth2bz
AStRAnpi6kFrKypragExgeRoJ1QnKH7pbSjLAKQVWUum ASTRaoF93eYt73TYvwtsv6fMWHWbGmMUZfVZPo3CRU9C ASdXviZw2kbViFuAgZF26RPZL1HdybUoWdcveG2nfU8D
Ax2JBnTPUpBFWe75z3YtgueWUfvZPZ6ZFXiMWJMUnjbo moon17L6BgxXRX5uHKudAmqVF96xia9h8ygcmG2sL3F moon26Sek222Md7ZydcAGxoKG832DK36CkLrS3PQY4c
moon7fwyajcVstMoBnVy7UBcTx87SBtNoGGAaH2Cb8V moonBtH9HvLHjLqi9ivyrMVKgFUsSfrz9BwQ9khhn1u moonCJg8476LNFLptX1qrK8PdRsA1HD1R6XWyu9MB93
moonF2sz7qwAtdETnrgxNbjonnhGGjd6r4W4UC9284s moonKfftMiGSak3cezvhEqvkPSzwrmQxQHXuspC96yj moonQBUKBpkifLcTd78bfxxt4PYLwmJ5admLW6cBBs8
moonXwpKwoVkMegt5Bc776cSW793X1irL5hHV1vJ3JA moonZ6u9E2fgk6eWd82621eLPHt9zuJuYECXAYjMY1C""".split())

ALPH = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n = 0
    for ch in s: n = n * 58 + ALPH.index(ch)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + raw

def env(name):
    for line in open("/root/arb-lab/.env"):
        line = line.strip()
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
URL = env("RMR_RPC_URL")

def rpc(method, params, tries=4):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for i in range(tries):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(URL, data=body, headers={"content-type": "application/json"}), timeout=60))
            if "error" in r:
                if i == tries - 1: return {"_error": r["error"]}
                time.sleep(1 + i); continue
            return r["result"]
        except Exception as e:
            if i == tries - 1: return {"_error": str(e)[:200]}
            time.sleep(1 + i)

_blocks = {}
def block(slot):
    if slot not in _blocks:
        b = rpc("getBlock", [slot, {"encoding": "json", "maxSupportedTransactionVersion": 1, "transactionDetails": "full", "rewards": False, "commitment": "confirmed"}])
        _blocks[slot] = b
        time.sleep(0.15)
    return _blocks[slot]

def facts(tx, idx, slot):
    """the facts we compare for one transaction of a block"""
    m, t = tx["meta"], tx["transaction"]
    keys = t["message"]["accountKeys"] + m.get("loadedAddresses", {}).get("writable", []) + m.get("loadedAddresses", {}).get("readonly", [])
    signer = keys[0]
    cu_price = cu_limit = None
    for ix in t["message"]["instructions"]:
        if keys[ix["programIdIndex"]] == CB:
            d = b58d(ix["data"])
            if d[:1] == b"\x03" and len(d) >= 9: cu_price = int.from_bytes(d[1:9], "little")
            if d[:1] == b"\x02" and len(d) >= 5: cu_limit = int.from_bytes(d[1:5], "little")
    # v1 (SIMD-0385): the fee settings live in transactionConfig (priorityFee is a total in lamports)
    tc = t["message"].get("transactionConfig")
    if tc:
        cu_limit = tc.get("computeUnitLimit") or cu_limit
        if tc.get("priorityFee") and cu_limit: cu_price = tc["priorityFee"] * 1_000_000 // cu_limit
    nsig = len(t["signatures"])
    fee = m["fee"]
    prio = max(0, fee - 5000 * nsig)
    tip = sum(max(0, m["postBalances"][i] - m["preBalances"][i]) for i, k in enumerate(keys) if k in TIPS and i < len(m["postBalances"]))
    lam = m["postBalances"][0] - m["preBalances"][0]
    w = lambda side: sum(int(b["uiTokenAmount"]["amount"]) for b in m.get(side) or [] if b.get("owner") == signer and b.get("mint") == WSOL)
    gain = lam + w("postTokenBalances") - w("preTokenBalances")
    progs = sorted({keys[ix["programIdIndex"]] for ix in t["message"]["instructions"]})
    return {"slot": slot, "index": idx, "sig": t["signatures"][0], "signer": signer, "ok": m["err"] is None, "fee": fee, "priority_fee": prio,
            "cu_price": cu_price, "cu_limit": cu_limit, "cu_used": m.get("computeUnitsConsumed"), "tip": tip, "version": str(tx.get("version")),
            "signer_sol_wsol_change": gain, "keys": set(keys), "programs": progs, "nsig": nsig}

def find(slot, sig):
    b = block(slot)
    if not b or "_error" in b: return None, b
    for i, tx in enumerate(b["transactions"]):
        if tx["transaction"]["signatures"][0] == sig: return i, b
    return None, b

out = open("/root/arb-lab/runs/" + (sys.argv[2] if len(sys.argv) > 2 else "takers.jsonl"), "w")
summary = []
for run in RUNS:
    att = {x["attempt"]: x for x in map(json.loads, open(f"{BASE}/{run}/attempts.jsonl"))}
    for o in map(json.loads, open(f"{BASE}/{run}/outcomes.jsonl")):
        if not o.get("landed"): continue
        a = att[o["attempt"]]
        our_slot, our_sig, trig = o["slot"], o["sig"], o["trigger"]
        pools = {a["buy_pool"], a["sell_pool"]}
        our_i, b = find(our_slot, our_sig)
        if our_i is None:
            print(f"{run} a{o['attempt']}: our tx not found in block {our_slot}: {str(b)[:160] if b else None}", flush=True); continue
        ours = facts(b["transactions"][our_i], our_i, our_slot)
        # the trigger: in our slot or up to 4 slots before it
        trig_at = None
        for s in range(our_slot, our_slot - 5, -1):
            i, bb = find(s, trig)
            if i is not None: trig_at = (s, i); break
        trig_f = facts(block(trig_at[0])["transactions"][trig_at[1]], trig_at[1], trig_at[0]) if trig_at else None
        # every transaction that touched our pools between the trigger and us, in block order
        lo = trig_at if trig_at else (our_slot, -1)
        between = []
        for s in range(lo[0], our_slot + 1):
            bb = block(s)
            if not bb or "_error" in bb: continue
            for i, tx in enumerate(bb["transactions"]):
                if (s, i) <= lo or (s, i) >= (our_slot, our_i): continue
                if tx["meta"] is None: continue
                keys = set(tx["transaction"]["message"]["accountKeys"]) | set(tx["meta"].get("loadedAddresses", {}).get("writable", [])) | set(tx["meta"].get("loadedAddresses", {}).get("readonly", []))
                if keys & pools:
                    f = facts(tx, i, s)
                    f["both_pools"] = pools <= f["keys"]
                    between.append(f)
        takers = [f for f in between if f["both_pools"] and f["ok"] and f["signer_sol_wsol_change"] > 0]
        rec = {"run": run, "attempt": o["attempt"], "landed_via": o["landed"], "ok": o.get("ok"), "code": o.get("code"), "profit": o.get("profit_lamports"), "arm": a.get("fee_arm"), "buy_venue": a["buy_venue"], "sell_venue": a["sell_venue"],
               "source": a["buy_source"] + "/" + a["sell_source"], "expected_profit": a["expected_profit"], "size": a["size_lamports"],
               "our": {k: ours[k] for k in ("slot", "index", "fee", "priority_fee", "cu_price", "cu_limit", "cu_used", "tip")},
               "block_txs": len(b["transactions"]),
               "trigger": None if not trig_f else {"slot": trig_f["slot"], "index": trig_f["index"], "ok": trig_f["ok"], "signer": trig_f["signer"], "cu_price": trig_f["cu_price"]},
               "touched_between": len(between), "same_signer_as_trigger": sum(1 for f in between if trig_f and f["signer"] == trig_f["signer"]),
               "takers": [{k: f[k] for k in ("slot", "index", "sig", "signer", "fee", "priority_fee", "cu_price", "cu_limit", "cu_used", "tip", "signer_sol_wsol_change", "programs", "version")} for f in takers],
               "others_between": [{k: f[k] for k in ("slot", "index", "signer", "ok", "both_pools", "priority_fee", "cu_price", "tip", "signer_sol_wsol_change")} for f in between if f not in takers][:12]}
        out.write(json.dumps(rec) + "\n"); out.flush()
        summary.append(rec)
        print(f"{run} a{o['attempt']:<3} slot {our_slot} our idx {our_i:>4}/{len(b['transactions'])} cu {ours['cu_price']} tip {ours['tip']} | trigger {('slot %d idx %d %s' % (trig_f['slot'], trig_f['index'], 'ok' if trig_f['ok'] else 'FAILED')) if trig_f else 'not found'} | touched between {len(between)}, takers {len(takers)}"
              + (f" first: {takers[0]['signer'][:8]} idx {takers[0]['index']} cu {takers[0]['cu_price']} tip {takers[0]['tip']} gain {takers[0]['signer_sol_wsol_change']}" if takers else ""), flush=True)
print("done", len(summary))
