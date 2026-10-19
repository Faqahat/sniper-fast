import json
from collections import Counter, defaultdict

F = json.load(open("/root/sep/features.json"))
rows = sorted(F.values(), key=lambda r: r["slot"])
for r in rows:
    r["dev_sol"] = r["dev"] / 1e9

WIN = [r for r in rows if r["label"] == "WIN"]
LOSE = [r for r in rows if r["label"] == "LOSE"]
MID = [r for r in rows if r["label"] == "MID"]
print(f"N={len(rows)}  WIN={len(WIN)} LOSE={len(LOSE)} MID={len(MID)}\n")

# ---------- derived dev features ----------
for r in rows:
    d = r["dev"]
    r["dev_round_1"] = (d % 1_000_000_000 == 0)          # exact N.0 SOL
    r["dev_round_01"] = (d % 100_000_000 == 0)           # round to 0.1 SOL
    r["dev_eq_3"] = (d == 3_000_000_000)
    r["dev_is_oddexact"] = (d % 1_000_000 != 0)          # not even a round million (fingerprint buys)
    r["dev_lt_1"] = (d < 1_000_000_000)

# ---------- full table ----------
hdr = f"{'mint':<9} {'lab':<4} {'dev':>4} {'host':<17} {'disc':<4} {'nmLen':>5} {'symU':>4} {'soc':>3} {'dsc':>4} {'cPri':>4} {'cTot':>4} {'pk0':>3} {'hr':>2}"
print(hdr)
for r in rows:
    print(f"{r['mint'][:8]:<9} {r['label']:<4} {r['dev_sol']:>4.2f} {str(r.get('uri_host'))[:16]:<17} "
          f"{str(r.get('create_disc'))[:4]:<4} {r.get('name_len','?'):>5} {str(r.get('symbol_upper'))[:1]:>4} "
          f"{r.get('n_socials','?'):>3} {r.get('desc_len','?'):>4} {r.get('creator_prior_sigs','?'):>4} "
          f"{r.get('creator_total_sigs','?'):>4} {r.get('peek_n_slot0','?'):>3} {r.get('hour_utc','?'):>2}")

# ---------- univariate: binary / categorical ----------
def rate(sub):
    w = sum(1 for r in sub if r["label"] == "WIN")
    l = sum(1 for r in sub if r["label"] == "LOSE")
    m = sum(1 for r in sub if r["label"] == "MID")
    n = len(sub)
    prec = w / (w + l) if (w + l) else float("nan")
    return w, l, m, n, prec

print("\n===== CATEGORICAL / BINARY FEATURE SPLITS (precision = WIN/(WIN+LOSE)) =====")
def cat_feature(name, keyfn):
    groups = defaultdict(list)
    for r in rows:
        groups[keyfn(r)].append(r)
    print(f"\n[{name}]")
    for k in sorted(groups, key=lambda x: str(x)):
        w, l, m, n, prec = rate(groups[k])
        print(f"   {str(k):<22} n={n:>2} WIN={w:>2} LOSE={l:>2} MID={m:>2}  win-prec={prec:.2f}" if (w+l) else
              f"   {str(k):<22} n={n:>2} WIN={w:>2} LOSE={l:>2} MID={m:>2}")

cat_feature("uri_host", lambda r: r.get("uri_host"))
cat_feature("cid_style", lambda r: r.get("cid_style"))
cat_feature("create_disc", lambda r: r.get("create_disc"))
cat_feature("has_twitter", lambda r: r.get("has_twitter"))
cat_feature("has_telegram", lambda r: r.get("has_telegram"))
cat_feature("has_website", lambda r: r.get("has_website"))
cat_feature("n_socials", lambda r: r.get("n_socials"))
cat_feature("has_image", lambda r: r.get("has_image"))
cat_feature("name_has_space", lambda r: r.get("name_has_space"))
cat_feature("name_has_emoji", lambda r: r.get("name_has_emoji"))
cat_feature("symbol_upper", lambda r: r.get("symbol_upper"))
cat_feature("name_lower", lambda r: r.get("name_lower"))
cat_feature("dev_round_1sol(N.0)", lambda r: r.get("dev_round_1"))
cat_feature("dev_round_0.1", lambda r: r.get("dev_round_01"))
cat_feature("dev_eq_3.0", lambda r: r.get("dev_eq_3"))
cat_feature("dev_lt_1.0", lambda r: r.get("dev_lt_1"))

# ---------- univariate: numeric AUC (Mann-Whitney, WIN vs LOSE) ----------
def auc(name, valfn):
    xs = [(valfn(r), r["label"]) for r in rows if r["label"] in ("WIN", "LOSE") and valfn(r) is not None and valfn(r) >= 0]
    pos = [v for v, l in xs if l == "WIN"]
    neg = [v for v, l in xs if l == "LOSE"]
    if not pos or not neg:
        print(f"   {name:<24} n/a"); return
    gt = eq = 0
    for a in pos:
        for b in neg:
            if a > b: gt += 1
            elif a == b: gt += 0.5
    a_ = gt / (len(pos) * len(neg))
    # orient so >0.5 means "higher => more likely WIN"
    direction = "higher=WIN" if a_ >= 0.5 else "lower=WIN"
    print(f"   {name:<24} AUC={max(a_,1-a_):.3f} ({direction})  win_med={sorted(pos)[len(pos)//2]} lose_med={sorted(neg)[len(neg)//2]}")

print("\n===== NUMERIC FEATURE DISCRIMINATION (AUC, WIN vs LOSE) =====")
auc("dev_lamports", lambda r: r.get("dev"))
auc("name_len", lambda r: r.get("name_len"))
auc("symbol_len", lambda r: r.get("symbol_len"))
auc("desc_len", lambda r: r.get("desc_len"))
auc("n_meta_fields", lambda r: r.get("n_meta_fields"))
auc("n_socials", lambda r: r.get("n_socials"))
auc("creator_prior_sigs", lambda r: r.get("creator_prior_sigs"))
auc("creator_total_sigs", lambda r: r.get("creator_total_sigs"))
auc("bundled_lamports", lambda r: r.get("bundled_lamports"))
auc("peek_n_slot0", lambda r: r.get("peek_n_slot0"))
auc("peek_n_slot0_1", lambda r: r.get("peek_n_slot0_1"))
auc("hour_utc", lambda r: r.get("hour_utc"))

# ---------- exact dev-amount fingerprint table ----------
print("\n===== EXACT dev_buy fingerprint =====")
dd = defaultdict(list)
for r in rows:
    dd[r["dev"]].append(r["label"])
for d in sorted(dd):
    c = Counter(dd[d])
    print(f"   {d/1e9:>6.3f} SOL ({d:>11})  n={len(dd[d]):>2}  WIN={c.get('WIN',0)} LOSE={c.get('LOSE',0)} MID={c.get('MID',0)}")
