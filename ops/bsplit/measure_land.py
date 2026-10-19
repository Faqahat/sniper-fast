# READ-ONLY: where did OUR buys land? For each BUY in a live_land_*.log: same slot as the create?, position after the
# create, creator-bundle ahead, OUTSIDERS ahead, SOL ahead, our fill vs floor and vs the post-bundle price (= our gap).
# usage: measure_land.py <log> [<log> ...]
import sys, re, json, statistics as st
sys.path.insert(0, "/root/indep")
from common import get_block, events, is_vote, tx_summary, load_tipmap, rpc, VSOL0, VTOK0
ME = "FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS"
tm = load_tipmap()
nodes = {x["pubkey"]: x for x in json.load(open("/root/stakepaths/clusternodes.json"))["result"]}
cache = {}


def blk(s):
    if s not in cache:
        cache[s] = get_block(s)
    return cache[s]


def client(s):
    r = rpc("getSlotLeaders", [s, 1])
    return nodes.get(r[0], {}).get("clientId", "?") if isinstance(r, list) and r else "?"


rows = []
for lg in sys.argv[1:]:
    tag = lg.split("live_land_")[-1].replace(".log", "")
    cs = {}
    buys = []
    for l in open(lg):
        m = re.search(r"FIRE slot=(\d+) mint=(\w+)", l)
        if m:
            cs[m.group(2)] = int(m.group(1))
            continue
        m = re.search(r"BUY\s+sig=(\w+) send_slot=(\d+) land_slot=(\d+) delta=(-?\d+) ok=(\w+)", l)
        if m:
            buys.append((m.group(1), int(m.group(3)), m.group(5) == "true"))
    fires = []
    for sig, land, okb in buys:
        t = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
        mint = None
        if isinstance(t, dict) and "meta" in t:
            tr, _ = events(t["meta"].get("logMessages"))
            mm = [e["mint"] for e in tr if e["user"] == ME and e["buy"]]
            mint = mm[0] if mm else None
        if mint is None or mint not in cs:
            continue
        fires.append({"cslot": cs[mint], "mint": mint, "tag": tag, "sig": sig, "land": land, "ok": okb})
    for f in fires:
        S, M = f["cslot"], f["mint"]
        b = blk(S)
        if not isinstance(b, dict) or "transactions" not in b:
            f["err"] = "no block"; rows.append(f); continue
        txs = [t for t in b["transactions"] if not is_vote(t)]
        ci = None
        for i, t in enumerate(txs):
            tr, cr = events((t.get("meta") or {}).get("logMessages"))
            if any(c["mint"] == M for c in cr):
                ci = i
                dev = [e for e in tr if e["mint"] == M and e["buy"]]
                base = dev[-1]["vsol"] if dev else VSOL0
                break
        if ci is None:
            f["err"] = "create not in that slot"; rows.append(f); continue
        floor = base ** 2 / (VSOL0 * VTOK0)
        glued, gv, run = 0, base, True
        ahead_out, sol_ahead, mypos, myfill, mylanded_here = 0, 0, None, None, False
        for j, t in enumerate(txs[ci + 1:], start=1):
            meta = t.get("meta") or {}
            tr, _ = events(meta.get("logMessages"))
            ev = [e for e in tr if e["mint"] == M and e["buy"]]
            okk = meta.get("err") is None
            if t["transaction"]["signatures"][0] == f["sig"]:
                mypos, mylanded_here = j, True
                mine = [e for e in ev if e["user"] == ME]
                if mine and mine[0]["tok"]:
                    myfill = (mine[0]["sol"] / mine[0]["tok"]) / floor
                break
            if run:
                if ev and okk:
                    glued += 1; gv = ev[-1]["vsol"]
                    continue
                run = False
            if ev and okk:
                ahead_out += 1
                sol_ahead += sum(e["sol"] for e in ev)
        pb = (gv / base) ** 2
        f.update(client=client(S), same_slot=(f.get("land") == S), pos=mypos, bundle_buys=glued, post_bundle=pb,
                 outsiders_ahead=ahead_out if mylanded_here else None, sol_ahead_out=sol_ahead / 1e9 if mylanded_here else None,
                 fill=myfill, gap=(myfill / pb if myfill else None))
        if not mylanded_here and f.get("land"):
            # landed in a later slot: everything in the create slot after the bundle was ahead of us
            f["outsiders_ahead"] = f"all of slot S (+{f['land'] - S} slots)"
            t2 = rpc("getTransaction", [f["sig"], {"encoding": "json", "maxSupportedTransactionVersion": 1}])
            if isinstance(t2, dict) and "meta" in t2:
                tr, _ = events(t2["meta"].get("logMessages"))
                mine = [e for e in tr if e["mint"] == M and e["user"] == ME and e["buy"]]
                if mine and mine[0]["tok"]:
                    f["fill"] = (mine[0]["sol"] / mine[0]["tok"]) / floor
                    f["gap"] = f["fill"] / pb
        rows.append(f)

print(f"{'arm':8} {'mint':9} {'client':14} {'slot':>5} {'pos':>4} {'bundle':>6} {'out-ahead':>16} {'SOL-ahead':>9} {'post-b':>6} {'fill':>5} {'GAP':>6} ok")
for f in rows:
    if "err" in f:
        print(f"{f['tag']:8} {f['mint'][:8]:9} {f['err']}")
        continue
    print(f"{f['tag']:8} {f['mint'][:8]:9} {f['client']:14} {('S' if f['same_slot'] else '+' + str(f['land'] - f['cslot'])):>5} {str(f['pos']):>4} {f['bundle_buys']:6} "
          f"{str(f['outsiders_ahead']):>16} {f['sol_ahead_out'] if f['sol_ahead_out'] is not None else '':>9} {f['post_bundle']:6.2f} "
          f"{(f['fill'] or 0):5.2f} {('%+.1f%%' % ((f['gap'] - 1) * 100)) if f['gap'] else '   ?':>6} {f['ok']}")
for tag in sorted(set(f["tag"] for f in rows)):
    g = [f for f in rows if f["tag"] == tag and "err" not in f]
    if not g:
        continue
    first = sum(1 for f in g if f["same_slot"] and f["outsiders_ahead"] == 0)
    gaps = [f["gap"] for f in g if f.get("gap")]
    print(f"\nARM {tag}: buys {len(g)} | same slot as create {sum(f['same_slot'] for f in g)} | FIRST behind the bundle {first} | "
          f"median gap {(st.median(gaps) - 1) * 100 if gaps else float('nan'):+.1f}% (today ~+6%, his spot ~0%)")
