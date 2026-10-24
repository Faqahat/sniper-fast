#!/usr/bin/env python3
# DOES PAYING MORE GET YOU EARLIER IN THE BLOCK? (read-only) Full blocks of the slots where our reverted buys lost the race:
# every non-vote tx's position (0 = top) vs its priority fee per CU and its tips (tip accounts of Jito / Helius / Nozomi / ...).
# Per leader client: rank correlation position ~ pay (negative = higher payers earlier), share of adjacent pairs ordered by
# priority, position of tipped vs untipped txs, and for our races: did the winner pay more than us?
import os, json, time, urllib.request, collections, statistics, concurrent.futures as cf
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
TIP = json.load(open("/home/moiz/sniper-data/work/tipmap.json")); SYS = "11111111111111111111111111111111"; CB = "ComputeBudget111111111111111111111111111111"
VOTE = "Vote111111111111111111111111111111111111111"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; BI = {c: i for i, c in enumerate(B58)}
def dec(s):
    n = 0
    for c in s: n = n * 58 + BI[c]
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b
def rpc(m, p):
    for i in range(6):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"}), timeout=120))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(1 + i)
H = [x for x in json.load(open("/home/moiz/sniper/ops/overnight/hkq7/howtowin.json")) if x.get("cross_sig")]
R = {r["sig"]: r for r in json.load(open("/home/moiz/sniper/ops/overnight/hkq7/replay_reverted.json"))}
slots = sorted({R[x["sig"]]["slot"] for x in H} | {R[x["sig"]]["slot"] - x["we_after_cross_pos"][0] for x in H})
def parse(slot):
    b = rpc("getBlock", [slot, {"encoding": "json", "transactionDetails": "full", "maxSupportedTransactionVersion": 1, "rewards": False}])
    if not b: return slot, None
    out = []
    for t in b["transactions"]:
        msg = t["transaction"]["message"]; la = (t["meta"] or {}).get("loadedAddresses") or {}; keys = msg["accountKeys"] + la.get("writable", []) + la.get("readonly", [])
        progs = {keys[ix["programIdIndex"]] for ix in msg["instructions"]}
        if VOTE in progs: continue
        cup = 0; tip = 0; svc = set()
        for ix in msg["instructions"]:
            p = keys[ix["programIdIndex"]]; d = dec(ix["data"])
            if p == CB and d and d[0] == 3: cup = int.from_bytes(d[1:9], "little")
            elif p == SYS and len(d) >= 12 and int.from_bytes(d[:4], "little") == 2 and keys[ix["accounts"][1]] in TIP:
                tip += int.from_bytes(d[4:12], "little"); svc.add(TIP[keys[ix["accounts"][1]]])
        out.append(dict(sig=t["transaction"]["signatures"][0], cup=cup, tip=tip, svc="+".join(sorted(svc)), pump="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P" in progs or "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P" in keys))
    return slot, out
with cf.ThreadPoolExecutor(6) as ex: BL = dict(ex.map(parse, slots))
def spearman(a, b):
    def rank(v):                                   # average ranks for ties (most txs share tip 0 / the same priority)
        o = sorted(range(len(v)), key=lambda i: v[i]); r = [0.0] * len(v); k = 0
        while k < len(o):
            j = k
            while j + 1 < len(o) and v[o[j + 1]] == v[o[k]]: j += 1
            for m in range(k, j + 1): r[o[m]] = (k + j) / 2
            k = j + 1
        return r
    ra, rb = rank(a), rank(b); n = len(a); ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb)); den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return num / den if den else 0
client_of = {R[x["sig"]]["slot"]: x["client"] for x in H}
G = collections.defaultdict(lambda: collections.defaultdict(list))
for slot, txs in BL.items():
    if not txs: continue
    cl = client_of.get(slot, client_of.get(slot + 1, "?")); n = len(txs)
    pos = [i / n for i in range(n)]
    G[cl]["rho_prio"].append(spearman(pos, [t["cup"] for t in txs])); G[cl]["rho_tip"].append(spearman(pos, [t["tip"] for t in txs]))
    pairs = [(a["cup"], b["cup"]) for a, b in zip(txs, txs[1:]) if a["cup"] != b["cup"]]
    G[cl]["desc_pairs"].append(sum(1 for a, b in pairs if a > b) / len(pairs) if pairs else 0.5)
    tipped = [i / n for i, t in enumerate(txs) if t["tip"] > 0]; untipped = [i / n for i, t in enumerate(txs) if t["tip"] == 0]
    if tipped and untipped: G[cl]["pos_tipped"].append(statistics.median(tipped)); G[cl]["pos_untipped"].append(statistics.median(untipped))
    hi = sorted(txs, key=lambda t: -(t["cup"]))[:max(1, n // 10)]; G[cl]["top10pay_pos"].append(statistics.median([txs.index(t) / n for t in hi]))
med = lambda v: statistics.median(v) if v else float("nan")
print(f"blocks analysed: {sum(1 for v in BL.values() if v)} (non-vote txs per block median {med([len(v) for v in BL.values() if v]):.0f})")
print("rho < 0 means higher payers sit EARLIER; desc pairs 50% = random, 100% = strictly sorted by priority")
for cl, g in sorted(G.items(), key=lambda x: -len(x[1]["rho_prio"])):
    print(f"  {cl:20s} blocks {len(g['rho_prio']):3d} | rho(position, priority) {med(g['rho_prio']):+.2f} | rho(position, tip) {med(g['rho_tip']):+.2f} | "
          f"adjacent pairs priority-descending {med(g['desc_pairs']):.0%} | median position: tipped txs {med(g['pos_tipped']):.0%} vs untipped {med(g['pos_untipped']):.0%} | top-10% payers at {med(g['top10pay_pos']):.0%}")
# our races: the crossing buy vs us, inside the same block
w = []
for x in H:
    r = R[x["sig"]]; txs = BL.get(r["slot"]) or []
    me = next((t for t in txs if t["sig"] == x["sig"]), None); cx = next((t for t in txs if t["sig"] == x["cross_sig"]), None)
    if me and cx: w.append((x["client"], cx["cup"] > me["cup"], cx["tip"] > me["tip"], cx["cup"], me["cup"], cx["tip"], me["tip"]))
print(f"\nsame-block races ({len(w)}): the buy that beat us had a HIGHER priority fee in {sum(1 for x in w if x[1])}, a HIGHER tip in {sum(1 for x in w if x[2])}")
print(f"   priority per CU (micro-lamports): winner median {med([x[3] for x in w]):.0f} vs ours {med([x[4] for x in w]):.0f} | tip lamports: winner {med([x[5] for x in w]):.0f} vs ours {med([x[6] for x in w]):.0f}")
