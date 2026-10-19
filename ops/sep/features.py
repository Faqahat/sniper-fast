import os, json, time, struct, hashlib, base64, urllib.request, urllib.error, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

RPC = "https://rpc-frankfurt.constant-k.com/?api-key=" + os.environ["CONSTANTK_TOKEN"]
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
CREATE_V2 = "d6904cec5f8b31b4"; CREATE = "181ec828051c0777"; BUY = "66063d1201daebea"
GATEWAYS = ["https://pump.mypinata.cloud/ipfs/", "https://ipfs.io/ipfs/", "https://cloudflare-ipfs.com/ipfs/"]


def b58dec(s):
    n = 0
    for c in s:
        n = n * 58 + B58.index(c)
    full = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\x00" * (len(s) - len(s.lstrip("1"))) + full


def b58enc(bb):
    n = int.from_bytes(bb, "big"); out = ""
    while n:
        n, r = divmod(n, 58); out = B58[r] + out
    return "1" * (len(bb) - len(bb.lstrip(b"\x00"))) + out


def rpc(m, p, tries=7):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode()
    for t in range(tries):
        try:
            req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=45) as r:
                j = json.loads(r.read())
            if "error" in j:
                time.sleep(0.3 * (t + 1)); continue
            return j.get("result")
        except urllib.error.HTTPError as e:
            time.sleep(1.0 + 0.8 * t if getattr(e, "code", 0) == 429 else 0.4 * (t + 1))
        except Exception:
            time.sleep(0.4 * (t + 1))
    return None


def get_tx(sig):
    for v in (0, 1, 2):
        r = rpc("getTransaction", [sig, {"maxSupportedTransactionVersion": v, "encoding": "jsonParsed"}])
        if r:
            return r
    return None


def all_sigs(addr, cap=1000):
    out = rpc("getSignaturesForAddress", [addr, {"limit": cap}])
    if not out:
        return []
    acc = list(out)
    while len(out) == cap:
        out = rpc("getSignaturesForAddress", [addr, {"limit": cap, "before": acc[-1]["signature"]}])
        if not out:
            break
        acc += out
    return acc


def parse_create(raw):
    # raw = pump create ix data bytes. returns name, symbol, uri, arg_creator(b58)
    p = 8
    fields = []
    for _ in range(3):
        if p + 4 > len(raw):
            return None
        ln = struct.unpack_from("<I", raw, p)[0]; p += 4
        if ln > 4000 or p + ln > len(raw):
            return None
        fields.append(raw[p:p + ln].decode("utf-8", "replace")); p += ln
    creator = None
    if p + 32 <= len(raw):
        creator = b58enc(raw[p:p + 32])
    return fields[0], fields[1], fields[2], creator


def fetch_uri_json(uri):
    tail = None
    if "/ipfs/" in uri:
        tail = uri.split("/ipfs/", 1)[1]
    elif uri.startswith("ipfs://"):
        tail = uri[len("ipfs://"):]
    urls = [g + tail for g in GATEWAYS] if tail else [uri]
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=18) as r:
                return json.loads(r.read())
        except Exception:
            continue
    return None


SOCIAL = {"twitter": ["twitter", "x", "twitter_url", "x_url"],
          "telegram": ["telegram", "telegram_url", "tg"],
          "website": ["website", "web", "url", "homepage"],
          "discord": ["discord"]}


def has_emoji(s):
    return any(ord(ch) > 0x2600 for ch in s)


def extract(row):
    mint = row["mint"]
    out = {"mint": mint, "label": row["label"], "slot": row["slot"], "dev": row["dev"]}
    try:
        sigs = all_sigs(mint)
        if not sigs:
            out["status"] = "no_sigs"; return out
        # oldest = create
        csig = sigs[-1]
        creation_slot = min(s["slot"] for s in sigs)
        # slot-0 / slot-1 PEEK features (co-buys landing same slot as create)
        n_slot0 = sum(1 for s in sigs if s["slot"] == creation_slot)
        n_slot01 = sum(1 for s in sigs if creation_slot <= s["slot"] <= creation_slot + 1)
        out["peek_n_slot0"] = n_slot0 - 1           # exclude the create tx itself
        out["peek_n_slot0_1"] = n_slot01 - 1
        out["total_sigs_lifetime"] = len(sigs)

        tx = get_tx(csig["signature"])
        if not tx:
            out["status"] = "no_createtx"; return out
        out["create_sig"] = csig["signature"]
        out["create_slot"] = tx.get("slot")
        bt = tx.get("blockTime") or csig.get("blockTime")
        out["blockTime"] = bt
        if bt:
            dt = datetime.datetime.utcfromtimestamp(bt)
            out["hour_utc"] = dt.hour
            out["minute"] = dt.minute
        msg = tx["transaction"]["message"]
        keys = [k["pubkey"] if isinstance(k, dict) else k for k in msg.get("accountKeys", [])]
        signers = [k["pubkey"] for k in msg.get("accountKeys", []) if isinstance(k, dict) and k.get("signer")]
        out["feepayer"] = signers[0] if signers else None
        out["n_signers"] = len(signers)
        out["n_account_keys"] = len(keys)
        ixs = list(msg.get("instructions", []))
        for inner in (tx.get("meta", {}).get("innerInstructions") or []):
            ixs += inner.get("instructions", [])
        n_pump = n_buy = 0
        create_raw = None
        for ix in ixs:
            if ix.get("programId") != PUMP:
                continue
            d = ix.get("data")
            if not d:
                continue
            try:
                raw = b58dec(d)
            except Exception:
                continue
            h = raw[:8].hex()
            n_pump += 1
            if h == BUY:
                n_buy += 1
            if h == CREATE_V2:
                create_raw = raw
            elif h == CREATE and create_raw is None:
                create_raw = raw
        out["n_pump_ix"] = n_pump
        out["n_buy_ix_in_createtx"] = n_buy
        # bundled SOL = total lamports spent by signers in this tx (approx insider bundle size)
        meta = tx.get("meta", {})
        pre = meta.get("preBalances", []); post = meta.get("postBalances", [])
        bundled_lamports = 0
        for i, k in enumerate(msg.get("accountKeys", [])):
            if isinstance(k, dict) and k.get("signer") and i < len(pre) and i < len(post):
                bundled_lamports += max(0, pre[i] - post[i])
        out["bundled_lamports"] = bundled_lamports

        if create_raw is None:
            # fall back: longest pump ix
            best = None
            for ix in ixs:
                if ix.get("programId") == PUMP and ix.get("data"):
                    try:
                        raw = b58dec(ix["data"])
                    except Exception:
                        continue
                    if best is None or len(raw) > len(best):
                        best = raw
            create_raw = best
        out["create_disc"] = create_raw[:8].hex() if create_raw else None
        pc = parse_create(create_raw) if create_raw else None
        if pc:
            nm, sym, uri, argcreator = pc
            out["name"] = nm; out["symbol"] = sym; out["uri"] = uri
            out["arg_creator"] = argcreator
            out["name_len"] = len(nm); out["symbol_len"] = len(sym)
            out["name_has_space"] = (" " in nm.strip())
            out["name_has_emoji"] = has_emoji(nm) or has_emoji(sym)
            out["symbol_upper"] = sym.isupper()
            out["name_lower"] = nm.islower()
            host = uri.split("://", 1)[-1].split("/", 1)[0] if uri else "?"
            out["uri_host"] = host
            path = uri.split("://", 1)[-1][len(host):] if uri else ""
            out["uri_path"] = path
            out["uri_file"] = path.rsplit("/", 1)[-1] if "/" in path else path
            cid = out["uri_file"]
            out["cid_style"] = ("bafk" if cid.startswith("bafk") else
                                "bafy" if cid.startswith("bafy") else
                                "Qm" if cid.startswith("Qm") else
                                "json" if cid.endswith(".json") else "other")
            # off-chain metadata
            j = fetch_uri_json(uri)
            if isinstance(j, dict):
                low = {str(k).lower(): v for k, v in j.items()}

                def present(keys):
                    for k in keys:
                        v = low.get(k)
                        if v is not None and str(v).strip() not in ("", "null", "false", "#", "https://", "http://"):
                            return True
                    return False
                out["has_image"] = bool(low.get("image"))
                desc = low.get("description")
                out["desc_len"] = len(str(desc).strip()) if desc else 0
                out["has_twitter"] = present(SOCIAL["twitter"])
                out["has_telegram"] = present(SOCIAL["telegram"])
                out["has_website"] = present(SOCIAL["website"])
                out["n_socials"] = sum([out["has_twitter"], out["has_telegram"], out["has_website"]])
                out["n_meta_fields"] = len(j)
                co = low.get("createdon") or low.get("created_on")
                out["created_on"] = str(co)[:60] if co else None
                out["meta_ok"] = True
            else:
                out["meta_ok"] = False

        # creator age via arg_creator
        cr = out.get("arg_creator")
        if cr:
            csigs = rpc("getSignaturesForAddress", [cr, {"limit": 100}])
            out["creator_total_sigs"] = len(csigs) if csigs is not None else -1
            prior = rpc("getSignaturesForAddress", [cr, {"limit": 100, "before": csig["signature"]}])
            out["creator_prior_sigs"] = len(prior) if prior is not None else -1
        out["status"] = "ok"
    except Exception as e:
        out["status"] = "err:" + str(e)[:120]
    return out


def main():
    rows = json.load(open("/root/sep/labels.json"))
    outpath = "/root/sep/features.json"
    cache = {}
    if os.path.exists(outpath):
        try:
            cache = json.load(open(outpath))
        except Exception:
            pass
    todo = [r for r in rows if cache.get(r["mint"], {}).get("status") != "ok"]
    print(f"total={len(rows)} todo={len(todo)}", flush=True)
    out = dict(cache)
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(extract, r): r["mint"] for r in todo}
        done = 0
        for f in as_completed(futs):
            r = f.result(); out[r["mint"]] = r; done += 1
            print(f"  {done}/{len(todo)} {r['mint'][:8]} {r.get('status')} host={r.get('uri_host')} disc={r.get('create_disc')} nbuy={r.get('n_buy_ix_in_createtx')} peek0={r.get('peek_n_slot0')} cprior={r.get('creator_prior_sigs')}", flush=True)
            json.dump(out, open(outpath, "w"), indent=0)
    json.dump(out, open(outpath, "w"), indent=0)
    from collections import Counter
    print("STATUS", Counter(v.get("status") for v in out.values()), flush=True)


if __name__ == "__main__":
    main()
