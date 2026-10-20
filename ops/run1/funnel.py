# READ-ONLY, zero cost. Are we skipping launches we should buy? For every create the engine saw in a run log, check
# rule #2 ON CHAIN (guard.py check), then show what the engine did with each true rule-#2 launch and why:
# fired / far leader (close-leader gate) / late create (create-ms gate) / race reject / static reject / base-filter skip.
# usage: python3 funnel.py <engine log> [close_leaders file] [leader_rtt json]
import sys, re, json, collections
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/root/indep")
from common import get_block, events, is_vote, tx_summary, load_tipmap, rpc
TM = load_tipmap()
LOG = sys.argv[1]
CLOSE = sys.argv[2] if len(sys.argv) > 2 else "/root/fix2/close_leaders_5ms.txt"
RTT = sys.argv[3] if len(sys.argv) > 3 else "/root/fix2/leader_rtt_new.json"
BOT = {"gg.sc", "ipfs.launchblitz.ai", "pf.jake-98f.workers.dev", "storage.googleapis.com"}
close = {l.strip() for l in open(CLOSE) if l.strip()}
rtt = {k: v.get("rtt") for k, v in json.load(open(RTT))["leaders"].items()}

txt = open(LOG, errors="replace").read()
seen = {}
for m in re.finditer(r"DETECT feed=\S+ first=1 .*?slot=(\d+) .*?mint=(\w+) .*?verdict=(\w+)", txt):
    seen.setdefault(m.group(2), (int(m.group(1)), m.group(3)))
fired = set(re.findall(r"^\s*FIRE slot=\d+ mint=(\w+)", txt, re.M))
decide = {m.group(1): m.group(2) == "true" for m in re.finditer(r"RACE decide slot=\d+ mint=(\w+) .*?pass=(\w+)", txt)}
decide_line = {m.group(1): m.group(0) for m in re.finditer(r"RACE decide slot=\d+ mint=(\w+) [^\n]*", txt)}
static = set(re.findall(r"RACE reject-static slot=\d+ mint=(\w+)", txt))
seen_race = set(re.findall(r"RACE seen slot=\d+ mint=(\w+)", txt))


def check(item):
    mint, (slot, verdict) = item
    blk = get_block(slot)
    if not (isinstance(blk, dict) and "transactions" in blk): return mint, None
    txs = [t for t in blk["transactions"] if not is_vote(t)]
    for i, t in enumerate(txs):
        meta = t.get("meta") or {}
        tr, cr = events(meta.get("logMessages"))
        c = [x for x in cr if x["mint"] == mint]
        if not c: continue
        dev = sum(e["sol"] for e in tr if e["mint"] == mint and e["buy"]) / 1e9
        gsol = 0.0
        for t2 in txs[i + 1:]:
            m2 = t2.get("meta") or {}
            tr2, _ = events(m2.get("logMessages"))
            b = [e for e in tr2 if e["mint"] == mint and e["buy"]]
            if m2.get("err") is None and b: gsol += sum(e["sol"] for e in b) / 1e9
            else: break
        moon = any(str(x[2]).startswith("moon") for x in tx_summary(t, TM)[0]["tips"])
        host = c[0]["uri"].split("://")[-1].split("/")[0]
        v2 = any("Instruction: CreateV2" in x for x in (meta.get("logMessages") or []))
        r2 = (not (host in BOT or host.endswith(".trycloudflare.com"))) and 0.49 <= dev <= 8.1 and 2.95 <= gsol <= 5.05 and moon and v2
        return mint, dict(slot=slot, verdict=verdict, r2=r2, dev=dev, gsol=gsol, moon=moon, host=host, pos=i, n=len(txs), inslot_ms=(i + 0.5) / len(txs) * 217)
    return mint, None


items = [(m, v) for m, v in seen.items() if v[1] != "skip_quote"]
with ThreadPoolExecutor(6) as ex:
    res = dict(ex.map(check, items))
true_r2 = {m: r for m, r in res.items() if r and r["r2"]}
leaders = {}
for m, r in true_r2.items():
    sl = rpc("getSlotLeaders", [r["slot"], 1])
    leaders[m] = sl[0] if isinstance(sl, list) and sl else None
print(f"creates seen {len(seen)}; checked on chain {sum(1 for r in res.values() if r)} / {len(items)} (non-SOL-quote excluded); TRUE rule-#2 on chain: {len(true_r2)}")
out = collections.Counter()
for m, r in sorted(true_r2.items(), key=lambda kv: kv[1]["slot"]):
    ld = leaders.get(m); lr = rtt.get(ld) if ld else None
    if m in fired: why = "FIRED"
    elif r["verdict"] != "pass": why = f"BASE-FILTER {r['verdict']}"
    elif m in decide and decide[m]: why = "LATE/UNKNOWN create-ms gate (race passed, no fire)"
    elif m in decide and not decide[m]: why = "RACE REJECT"
    elif m in static: why = "STATIC REJECT"
    elif ld not in close: why = "FAR LEADER (close-leader gate)"
    else: why = "NOT DECIDED (?)"
    out[why.split(" (")[0]] += 1
    extra = ""
    if why == "RACE REJECT": extra = " | " + re.sub(r".*?(at_ms=\S+).*?(bundle_n=\S+ bundle_sol=\S+ glued_closed=\S+ glued_unknown=\S+ order=\S+).*", r"\1 \2", decide_line[m])
    print(f"  {m[:10]} slot {r['slot']} dev {r['dev']:.2f} bundle {r['gsol']:.2f} create@{r['inslot_ms']:.0f}ms leader {str(ld)[:8]} rtt {lr if lr is None else round(lr, 2)} in-list {ld in close} -> {why}{extra}")
print("\nTRUE rule-#2 outcome:", dict(out))
far_close = [m for m in true_r2 if m not in fired and leaders.get(m) not in close and (rtt.get(leaders.get(m)) or 99) < 5]
print(f"far-skipped but leader actually <5 ms from THIS server: {len(far_close)}")
wrong_base = [m for m, r in true_r2.items() if r["verdict"] != "pass"]
print(f"true rule-#2 rejected by the engine's base filter: {len(wrong_base)}")
