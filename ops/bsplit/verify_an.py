import json, collections as C
R = [json.loads(l) for l in open("/root/bsplit/verify.jsonl")]


def grp(c):
    c = c or "?"
    if "Harmonic" in c:
        return "Harmonic"
    if "Bam" in c or "BAM" in c:
        return "BAM"
    if c == "JitoLabs":
        return "Jito-Solana"
    if c in ("Firedancer", "Frankendancer", "Rakurai"):
        return "Firedancer/other"
    return c


# wallet -> set of creators it was glued behind (inside OUR set)
wc = C.defaultdict(set)
for r in R:
    cr = (r.get("create_signers") or ["?"])[0]
    for g in r.get("glued_txs") or []:
        wc[g["payer"]].add(cr)

rows = C.defaultdict(lambda: C.Counter())
for r in R:
    k = grp(r.get("client"))
    s = rows[k]
    s["launches"] += 1
    cb = r.get("create_bundle") or {}
    if cb.get("in"):
        s["create_in_jito_bundle"] += 1
    signers = set(r.get("create_signers") or [])
    for g in r.get("glued_txs") or []:
        s["glued_buys"] += 1
        s["glued_sol"] += g["sol"]
        if g.get("in_create_bundle"):
            s["in_SAME_bundle"] += 1
            s["sol_same_bundle"] += g["sol"]
        else:
            s["not_in_create_bundle"] += 1
            if g["payer"] in signers:
                s["  ..payer=creator"] += 1
            if len(wc[g["payer"]]) >= 2:
                s["  ..multi-creator wallet (bot-like)"] += 1
    fb = r.get("first_glued_bundle")
    if fb and fb.get("in"):
        s["first_glued_buy_in_OTHER_bundle"] += 1

order = ["launches", "create_in_jito_bundle", "glued_buys", "in_SAME_bundle", "not_in_create_bundle", "  ..payer=creator",
         "  ..multi-creator wallet (bot-like)", "first_glued_buy_in_OTHER_bundle", "glued_sol", "sol_same_bundle"]
ks = sorted(rows, key=lambda k: -rows[k]["launches"])
tot = C.Counter()
for k in ks:
    tot.update(rows[k])
print(f"{'':38}" + "".join(f"{k:>18}" for k in ks) + f"{'ALL':>12}")
for o in order:
    print(f"{o:38}" + "".join(f"{rows[k][o]:>18.0f}" for k in ks) + f"{tot[o]:>12.0f}")
print(f"\nglued buys verified in the creator's own Jito bundle: {tot['in_SAME_bundle']}/{tot['glued_buys']} "
      f"({tot['in_SAME_bundle']/max(1,tot['glued_buys']):.0%}); SOL {tot['sol_same_bundle']:.1f}/{tot['glued_sol']:.1f}")
bots = [w for w, cs in wc.items() if len(cs) >= 2]
print(f"glued wallets seen behind >=2 different creators in our set: {len(bots)} of {len(wc)}")
# examples for the record
ex = [r for r in R if (r.get("create_bundle") or {}).get("in")][:3]
for r in ex:
    print("EXAMPLE create", r["create_sig"][:20], "bundle", r["create_bundle"]["id"][:16], "txs", len(r["create_bundle"]["txs"]),
          "glued", [(g["sig"][:10], g.get("in_create_bundle")) for g in r["glued_txs"]])
