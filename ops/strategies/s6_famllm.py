#!/usr/bin/env python3
# Family synthesis: Haiku 5.5 reads each code-built family's stats + its members' per-wallet labels (s4_llm.py) and writes a
# plain-language description, one concrete testable rule and a reachability call for a ~35 ms bot. 10 small sync calls
# (under the 50-request batch threshold); usage goes into the same spend ledger (cap $15). Key never printed.
import json, sys, os
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/home/moiz/sniper/ops/strategies")
import s4_llm as S
OUT = "/home/moiz/sniper-data/strategies"
J = json.load(open(f"{OUT}/families.json")); LAB = {}
for l in open(f"{OUT}/llm/labels_cards.jsonl"):
    o = json.loads(l); LAB[o["id"]] = o
SYS = """You are a quantitative analyst. A code rule grouped consistently profitable pump.fun bonding-curve wallets into one
"family" by their entry/exit context. You get the family's measured statistics and, for its top members, a per-wallet
strategy reading written earlier from each wallet's evidence card. Our own bot lands a buy ~35 ms after a trigger it sees
(about 65 transactions later in the same block; blocks hold ~395 transactions per 212 ms slot) on ~56% of slots, slower
otherwise; it pays ~0.0035 SOL fixed per round trip plus pump fees (~1.25% per side). Write for a non-specialist owner.
Reply with ONLY one JSON object:
{"name": "<2-5 words>", "what_they_do": "<2 plain sentences>", "why_it_works": "<1-2 sentences>",
 "testable_rule": "<one concrete replayable rule: trigger + filters + size + exit, with numbers>",
 "speed_needed": "<plain words with ms>", "can_a_35ms_bot_do_it": "<yes / partly / no + one-sentence reason>",
 "red_flags": "<what could make the family's profit not reproducible (coordination, lottery wins, crowding, size)>"}"""
def prompt(fid, v):
    keep = {k: v[k] for k in v if k not in ("members", "llm_families", "llm_info", "llm_speed")}
    lines = [f"FAMILY {fid}: {json.dumps(keep)}", "", "TOP MEMBERS (wallet, 46 h P&L SOL, trips) with their per-wallet readings:"]
    for u in v["members"][:14]:
        o = LAB.get(u[:60], {})
        a = next((x for x in v["top"] if x[0] == u[:8]), None)
        lines.append(f"- {u[:8]}: family='{o.get('family')}', entry='{o.get('entry_rule')}', exit='{o.get('exit_rule')}', speed={o.get('speed')}/{o.get('latency_ms')} ms, "
                     f"money='{o.get('how_it_makes_money')}', rule='{o.get('testable_rule')}', crowding='{o.get('crowding_hint')}'")
    return "\n".join(lines)
def run(fid):
    v = J["fams"][fid]
    m = S.call("POST", "/messages", {"model": S.MODEL, "max_tokens": 12000, "system": SYS, "messages": [{"role": "user", "content": prompt(fid, v)}]})
    u = m.get("usage", {})
    txt = "".join(c.get("text", "") for c in m.get("content", []) if c.get("type") == "text")
    return fid, S.parse(txt), u.get("input_tokens", 0), u.get("output_tokens", 0)
if __name__ == "__main__":
    if S.ledger()["usd"] + 10 * 12000 * S.PRICE_OUT / 1e6 + 0.05 > S.CAP: raise SystemExit("cap")
    out = {}; tin = tout = 0
    with ThreadPoolExecutor(4) as ex:
        for fid, o, a, b in ex.map(run, list(J["fams"])):
            out[fid] = o; tin += a; tout += b
    usd = S.add_spend("families_sync", tin, tout, batch=False)
    json.dump(out, open(f"{OUT}/llm/families_llm.json", "w"), indent=1, ensure_ascii=False)
    print(f"families: {sum(1 for o in out.values() if o)} parsed; usage {tin} in + {tout} out = ${usd:.3f}; ledger ${S.ledger()['usd']:.3f}")
