#!/usr/bin/env python3
# Merge everything into one row per launch: ds.jsonl
# inputs: blk_rand.jsonl blk_his.jsonl paths_*.jsonl creator.jsonl meta.jsonl his_mints.json wtx.jsonl rand_targets.json
import json, os, re, glob, collections, math, bisect, unicodedata
from urllib.parse import urlparse

D = "/root/nob/"
W = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
VSOL0, VTOK0 = 30_000_000_000, 1_073_000_000_000_000
FEE = 0.0125
CLOSE_NET = 2_034_280
SL3, SL10, SL40, SL60 = 8, 25, 100, 150


def jl(p):
    out = []
    if os.path.exists(p):
        for l in open(p):
            try:
                out.append(json.loads(l))
            except Exception:
                pass
    return out


rand_sigs = {t["sig"] for t in json.load(open(D + "rand_targets.json"))}
blk = {}
for r in jl(D + "blk_rand.jsonl") + jl(D + "blk_rand2.jsonl") + jl(D + "blk_his.jsonl"):
    if r.get("missing"):
        continue
    blk.setdefault(r["mint"], r)
paths = {}
for f in glob.glob(D + "paths_*.jsonl"):
    for r in jl(f):
        paths[r["mint"]] = r
creator = {r["mint"]: r for r in jl(D + "creator.jsonl")}
meta = {}
for r in jl(D + "meta.jsonl"):
    if r["mint"] not in meta or r.get("status") == "ok":
        meta[r["mint"]] = r
his = json.load(open(D + "his_mints.json"))
try:
    attempted = json.load(open(D + "attempted.json"))
except Exception:
    attempted = {}

# failed-tx fees: attribute to a bought mint (by mint key, else nearest first-buy slot within 4 slots)
wtx = jl(D + "wtx.jsonl")
buy_slots = sorted((d["buys"][0]["slot"], m) for m, d in his.items())
bs_slots = [x[0] for x in buy_slots]
fail_fee = collections.Counter()
fail_n = collections.Counter()
unattrib = [0, 0]
for t in wtx:
    if not t.get("err") or "fail" in t:
        continue
    m = None
    for k in t.get("mints") or []:
        if k in his:
            m = k
            break
    if m is None:
        i = bisect.bisect_left(bs_slots, t["slot"] - 4)
        best = None
        while i < len(buy_slots) and buy_slots[i][0] <= t["slot"] + 4:
            if best is None or abs(buy_slots[i][0] - t["slot"]) < abs(best[0] - t["slot"]):
                best = buy_slots[i]
            i += 1
        m = best[1] if best else None
    if m is None:
        unattrib[0] += 1
        unattrib[1] += t.get("fee") or 0
        continue
    fail_fee[m] += t.get("fee") or 0
    fail_n[m] += 1
json.dump({"unattrib_fail_n": unattrib[0], "unattrib_fail_fee_sol": unattrib[1] / 1e9}, open(D + "fail_unattrib.json", "w"))

EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️]")


def host(u):
    try:
        h = urlparse(u if "://" in u else "http://" + u).netloc.lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def tweet_ts(u):
    m = re.search(r"/status(?:es)?/(\d{15,20})", u or "")
    if not m:
        return None
    return ((int(m.group(1)) >> 22) + 1288834974657) / 1000.0


def tw_kind(u):
    u = (u or "").lower()
    if not u:
        return "none"
    if "/status/" in u:
        return "status"
    if "/i/communities" in u or "/communities/" in u:
        return "community"
    if "x.com/" in u or "twitter.com/" in u:
        if "/search" in u or "?q=" in u:
            return "search"
        return "profile"
    return "other"


def str_feats(s, p):
    s = s or ""
    f = {}
    f[p + "len"] = len(s)
    f[p + "words"] = len(s.split())
    f[p + "upper"] = s.isupper()
    f[p + "lower"] = s.islower()
    f[p + "emoji"] = bool(EMOJI_RE.search(s))
    f[p + "digit"] = any(c.isdigit() for c in s)
    f[p + "nonascii"] = any(ord(c) > 127 for c in s)
    f[p + "punct"] = any(unicodedata.category(c).startswith("P") or unicodedata.category(c).startswith("S") for c in s if ord(c) < 128 and not c.isalnum() and c != " ")
    return f


def path_labels(r, pr, his_d):
    """price/floor path: create slot from the block (exact order), later slots from the last tx of each slot/bucket.
    adj_ = with the target's own net SOL removed from the curve (what the launch would have done without his trades)."""
    base = r["base"]
    S = r["slot"]
    seq = []  # (slot offset, vsol, his net sol in curve)
    hnet = 0
    for x in r.get("later", []):
        if not x.get("ok"):
            continue
        for e in x["ev"]:
            if e[1] == W:
                hnet += e[2] if e[0] else -e[2]
            seq.append((0, e[4], hnet))
    ht = []
    if his_d:
        ht = sorted([(b["slot"], b["sol"]) for b in his_d["buys"]] + [(x["slot"], -x["sol"]) for x in his_d["sells"]])

    def hnet_at(sl):
        return sum(v for s_, v in ht if s_ <= sl)
    if pr:
        for row in pr.get("rows", []):
            if row[0] <= S or not row[1]:
                continue
            hn = hnet_at(row[0])
            for e in row[1]:
                seq.append((row[0] - S, e[4], hn))
    out = {"path_ok": pr is not None and "sig_err" not in (pr or {}), "n_ev": len(seq), "n_sig60": (pr or {}).get("n_sig"),
           "n_ok60": (pr or {}).get("n_ok"), "n_ok10": (pr or {}).get("n_ok_dense"), "later_trunc": r.get("nlater", 0) > len(r.get("later", []))}
    act = dict((pr or {}).get("act") or [])
    out["act_ok_3s"] = sum(v for k, v in act.items() if k <= SL3)
    seqr = [(d, (v / base) ** 2, ((v - h) / base) ** 2) for d, v, h in seq]
    bm = max(1.0, r["bmult"] or 1.0)
    for tag, k in (("", 1), ("adj_", 2)):
        for nm, lim in (("3", SL3), ("10", SL10), ("40", SL40), ("60", SL60)):
            vals = [x[k] for x in seqr if x[0] <= lim]
            out[tag + "peak" + nm] = max(vals + [1.0])
        for nm, lim in (("10", SL10), ("40", SL40), ("60", SL60)):
            vals = [x[k] for x in seqr if x[0] <= lim]
            out[tag + "px" + nm] = vals[-1] if vals else 1.0
        for ename, entry in (("e100", 1.00), ("e102", 1.02), ("e105", 1.05), ("eb", 1.02 * bm)):
            for nm, lim in (("3", SL3), ("10", SL10), ("40", SL40)):
                ex = None
                last = 1.0
                for x in seqr:
                    if x[0] > lim:
                        break
                    p = x[k]
                    last = p
                    if p >= entry * 1.3:
                        ex = entry * 1.3
                        break
                if ex is None:
                    ex = last
                out[f"{tag}ret_{ename}_tp130_{nm}"] = ex / entry * (1 - FEE) ** 2 - 1
    return out


rows = []
for m, r in blk.items():
    f = {"mint": m, "slot": r["slot"], "bt": r["bt"], "in_rand": r["csig"] in rand_sigs, "his": m in his,
         "attempted": (m in attempted) and (m not in his), "att_ntx": attempted.get(m, 0)}
    cx = r["cx"]
    f["quote"] = bool(cx.get("quote"))
    f["v0_std"] = r["v0"] == VSOL0
    f["mayhem"] = bool(cx.get("flag1"))
    f["tail_last"] = (cx.get("tail") or "")[-2:]
    f["ins0"] = r["ins"][0] if r["ins"] else None
    f["t22"] = r["t22"]
    f["dev_sol"] = r["dev"] / 1e9
    f["dev_n"] = len(r["dev_buys"])
    f["cu_price"] = r["cu_price"] or 0
    f["cu_limit"] = r["cu_limit"] or 0
    nsig = len(r["signers"])
    f["nsig"] = nsig
    f["prio_sol"] = max(0, (r["fee"] or 0) - 5000 * nsig) / 1e9
    tips = r["tips"]
    f["ctip"] = bool(tips)
    f["ctip_label"] = tips[0][0] if tips else "none"
    f["ctip_sol"] = sum(t[1] for t in tips) / 1e9
    f["keytip"] = ",".join(r["keytip"]) or "none"
    f["progs"] = ">".join(r["progs"][:6])
    f["payer_is_creator"] = r["payer"] == r["creator"]
    f["user_is_creator"] = r["user"] == r["creator"]
    f["txver"] = str(r.get("ver"))
    f["nkeys"] = r["nkeys"]
    f["cpre_sol"] = (r["cpre"] or 0) / 1e9
    f["cleft_sol"] = (r["cpost"] or 0) / 1e9
    f["dev_frac"] = r["dev"] / r["cpre"] if r["cpre"] else None
    tail_uri = r["uri"].rsplit("/", 1)[-1]
    f["uri_cid"] = "Qm" if tail_uri.startswith("Qm") else ("bafk" if tail_uri.startswith("baf") else ("json" if tail_uri.endswith(".json") else "other"))
    f["client"] = r["client"]
    f["cnv"] = r["cnv"]
    f["cnv_frac"] = r["cnv"] / max(1, r["nnv"])
    f["hour"] = (r["bt"] % 86400) // 3600 if r["bt"] else None
    f["glued"] = r["glued"]
    f["gsol"] = r["gsol"] / 1e9
    f["bmult"] = r["bmult"]
    f["nb"] = r["gsol"] <= 300_000_000
    f["name"], f["symbol"], f["uri"] = r["name"], r["symbol"], r["uri"]
    f.update(str_feats(r["name"], "n_"))
    f.update(str_feats(r["symbol"], "s_"))
    f["sym_in_name"] = r["symbol"].lower() in r["name"].lower()
    f["sym_eq_name"] = r["symbol"].lower() == r["name"].lower()
    f["uri_host"] = host(r["uri"])
    f["mint_pump"] = m.endswith("pump")
    # same-slot others (NOT visible for same-slot entries; descriptive only)
    oth = [x for x in r.get("later", []) if x.get("ok") and not x.get("glued") and not x.get("his") and any(e[0] for e in x["ev"])]
    f["x_s_indep_buys"] = len(oth)
    # metadata
    mt = meta.get(m)
    f["meta_ok"] = bool(mt and mt.get("status") == "ok")
    if f["meta_ok"]:
        j = mt["j"]
        low = {str(k).lower(): v for k, v in j.items()}
        tw = str(low.get("twitter") or "")
        f["tw_kind"] = tw_kind(tw)
        tts = tweet_ts(tw)
        f["tweet_age_s"] = (r["bt"] - tts) if (tts and r["bt"]) else None
        f["tw_host"] = host(tw) if tw else "none"
        f["has_tw"] = bool(tw.strip())
        f["has_tg"] = bool(str(low.get("telegram") or "").strip())
        web = str(low.get("website") or "").strip()
        f["has_web"] = bool(web)
        f["web_host"] = host(web) if web else "none"
        desc = str(low.get("description") or "").strip()
        f["desc_len"] = len(desc)
        f["has_desc"] = len(desc) > 0
        f["desc_url"] = "http" in desc
        img = str(low.get("image") or "")
        f["img_host"] = host(img) if img else "none"
        mm = re.search(r"/([1-9A-HJ-NP-Za-km-z]{32,44})\.(?:webp|png|jpg|jpeg|gif)", img)
        f["img_named_mint"] = bool(mm)
        f["img_other_mint"] = bool(mm and mm.group(1) != m)
        f["created_on"] = str(low.get("createdon") or "none")[:30]
        f["has_showname"] = "showname" in low
        f["has_community"] = "coin_community" in low
        f["meta_keys"] = ",".join(sorted(low.keys()))[:120]
        f["meta_nkeys"] = len(low)
        f["n_socials"] = f["has_tw"] + f["has_tg"] + f["has_web"]
        f["meta_name_eq"] = str(low.get("name") or "") == r["name"]
    # creator
    c = creator.get(m)
    f["cr_ok"] = bool(c and "n_prior" in c)
    if f["cr_ok"]:
        f["cr_nprior"] = c["n_prior"]
        f["cr_nprior_ok"] = c["n_prior_ok"]
        f["cr_capped"] = c["n_prior"] >= 1000
        f["cr_age_h"] = (r["slot"] - c["oldest_slot"]) * 0.4 / 3600 if c.get("oldest_slot") else 0.0
        f["cr_age_censored"] = bool(c.get("oldest_slot") and c["oldest_slot"] < 457_460_000)
        f["cr_idle_s"] = (r["slot"] - c["newest_slot"]) * 0.4 if c.get("newest_slot") else None
        f["cr_nlaunch"] = c["n_prior_launch"]
        f["cr_last_launch_h"] = (r["slot"] - c["last_launch_slot"]) * 0.4 / 3600 if c.get("last_launch_slot") else None
        pri = c.get("prior") or []
        f["cr_prior_maxsig"] = max([p["n_sig_before"] or 0 for p in pri] + [0])
        f["cr_prior_maxpx"] = max([((p["vsol_latest"] or VSOL0) / VSOL0) ** 2 for p in pri] + [0])
        f["cr_prior_ran"] = any(((p["vsol_latest"] or 0) / VSOL0) ** 2 >= 2.0 or (p["n_sig_before"] or 0) >= 500 for p in pri)
        fu = c.get("funders") or {}
        fl = c.get("fund") or []
        first = None
        for src, lam, s12, sl in reversed(fl[:2]) if len(fl) else []:
            first = (src, lam)
        f["cr_nfunders"] = len(fu)
        f["cr_funder"] = fl[0][0] if fl else None
        f["cr_fund_sol"] = (fl[0][1] / 1e9) if fl else None
        f["cr_funder_n"] = max([v.get("n") or 0 for v in fu.values()] + [0])
        f["cr_funder_hub"] = any((v.get("n") or 0) >= 1000 and (v.get("span_slots") or 1e9) < 20000 for v in fu.values())
    # his trades
    if m in his:
        d = his[m]
        b0 = d["buys"][0]
        base = r["base"]
        fl = base ** 2 / (VSOL0 * VTOK0)
        f["h_off"] = b0["slot"] - r["slot"]
        f["h_sol"] = sum(x["sol"] for x in d["buys"]) / 1e9
        f["h_fill"] = (b0["sol"] / b0["tok"]) / fl if b0["tok"] else None
        f["h_pre"] = ((b0["vsol"] - b0["sol"]) / base) ** 2
        f["h_nsell"] = len(d["sells"])
        f["h_hold_s"] = (d["sells"][-1]["slot"] - b0["slot"]) * 0.4 if d["sells"] else None
        f["h_first_sell_s"] = (d["sells"][0]["slot"] - b0["slot"]) * 0.4 if d["sells"] else None
        tok_b = sum(x["tok"] for x in d["buys"])
        tok_s = sum(x["tok"] for x in d["sells"])
        f["h_unsold"] = 1 - tok_s / tok_b if tok_b else None
        f["h_pnl"] = (d["dsol_ok"] + CLOSE_NET) / 1e9
        f["h_failfee"] = fail_fee[m] / 1e9
        f["h_nfail"] = fail_n[m]
        f["h_pnl_net"] = f["h_pnl"] - f["h_failfee"]
        f["h_ret"] = f["h_pnl"] / f["h_sol"] if f["h_sol"] else None
        f["h_prio"] = b0["fee"] / 1e9
        f["h_tip"] = sum(t[1] for t in b0["tips"]) / 1e9
        # his position in the create slot: glued ahead, other buys ahead
        if f["h_off"] == 0:
            ahead = 0
            ahead_sol = 0
            for x in r.get("later", []):
                if x.get("his"):
                    break
                if x.get("ok") and any(e[0] for e in x["ev"]):
                    ahead += 1
                    ahead_sol += sum(e[2] for e in x["ev"] if e[0])
            f["h_ahead_n"] = ahead
            f["h_ahead_sol"] = ahead_sol / 1e9
        f["h_ahead_glued_sol"] = r["gsol"] / 1e9
    f.update(path_labels(r, paths.get(m), his.get(m)) if m in paths else {"path_ok": False})
    rows.append(f)
with open(D + "ds.jsonl", "w") as o:
    for f in rows:
        o.write(json.dumps(f) + "\n")
print("rows", len(rows), "his", sum(f["his"] for f in rows), "rand", sum(f["in_rand"] for f in rows),
      "with path", sum(1 for f in rows if f.get("path_ok")), "meta_ok", sum(1 for f in rows if f.get("meta_ok")),
      "cr_ok", sum(1 for f in rows if f.get("cr_ok")))
print("unattributed failed txs", unattrib[0], "fee SOL", unattrib[1] / 1e9)
