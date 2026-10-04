import json, collections, statistics as S
B = "/root/arb-lab/runs/"
st = json.loads(open(B + "live-run-3/status.jsonl").readlines()[-1])
print("engine:", {k: v for k, v in st["counts"].items() if k.startswith("trigger") or k == "opportunity"})
a = {x["attempt"]: x for x in map(json.loads, open(B + "live-run-3/attempts.jsonl"))}
o = [json.loads(l) for l in open(B + "live-run-3/outcomes.jsonl")]
print("attempts", len(a), "by arm", dict(collections.Counter(x["fee_arm"] for x in a.values())))
for arm in ("spec", "bid"):
    oo = [x for x in o if a[x["attempt"]]["fee_arm"] == arm]
    L = [x for x in oo if x.get("landed")]
    print(f"  {arm}: sent {len(oo)}, landed {len(L)}, wins {sum(1 for x in L if x.get('ok'))}, landed by {dict(collections.Counter(x['landed'] for x in L))},"
          f" fee per landed median {S.median([x['fee_lamports'] for x in L]) if L else None}, total {sum(x['fee_lamports'] for x in L)},"
          f" expected profit median {S.median([a[x['attempt']]['expected_profit'] for x in oo]) if oo else None}")
R = [json.loads(l) for l in open(B + "takers-3.jsonl")]
print("block check of", len(R), "landed: trigger failed", sum(1 for r in R if r["trigger"] and not r["trigger"]["ok"]),
      "| trigger ok", sum(1 for r in R if r["trigger"] and r["trigger"]["ok"]), "| trigger not found", sum(1 for r in R if not r["trigger"]))
for arm in ("spec", "bid"):
    mine = [r for r in R if r.get("arm") == arm]
    rr = [r for r in mine if r["trigger"] and r["trigger"]["slot"] == r["our"]["slot"]]
    gaps = [r["our"]["index"] - r["trigger"]["index"] for r in rr]
    print(f"  {arm}: same slot as trigger {len(rr)}/{len(mine)}; our position after trigger median {S.median(gaps) if gaps else None} min {min(gaps) if gaps else None};"
          f" taken first by someone {sum(1 for r in mine if r['takers'])}; trigger failed {sum(1 for r in mine if r['trigger'] and not r['trigger']['ok'])}")
for r in R:
    t = r["trigger"]
    print(f"   a{r['attempt']:<3} {r['arm']:<4} exp {r['expected_profit']:>9} our prio {r['our']['priority_fee']:>9} | trigger {'ok' if t and t['ok'] else 'FAILED' if t else '?'} signer {(t or {}).get('signer','?')[:8]}"
          f" | us {'+' + str(r['our']['index'] - t['index']) if t and t['slot'] == r['our']['slot'] else 'slot+' + str(r['our']['slot'] - t['slot']) if t else '?'}"
          f" | takers {[(x['signer'][:8], x['index'] - t['index'] if t and x['slot'] == t['slot'] else 'next', x['priority_fee']) for x in r['takers']][:2]}")
