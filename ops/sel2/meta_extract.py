import os, json, time, urllib.request, urllib.error, struct, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

RPC = "https://rpc-frankfurt.constant-k.com/?api-key=" + os.environ["CONSTANTK_TOKEN"]
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
ALPH = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

GATEWAYS = [
    "https://pump.mypinata.cloud/ipfs/",
    "https://ipfs.io/ipfs/",
    "https://cloudflare-ipfs.com/ipfs/",
]


def b58dec(s):
    n = 0
    for c in s:
        n = n * 58 + ALPH.index(c)
    full = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    pad = len(s) - len(s.lstrip("1"))
    return b"\x00" * pad + full


def rpc(method, params, tries=6):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    last = None
    for t in range(tries):
        try:
            req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as r:
                j = json.loads(r.read())
            if "error" in j:
                last = j["error"]
                if isinstance(last, dict) and last.get("code") == -32015:
                    return ("__VERR__", last)
                time.sleep(0.3 * (t + 1))
                continue
            return j.get("result")
        except urllib.error.HTTPError as e:
            last = e
            time.sleep(0.8 + 0.6 * t if e.code == 429 else 0.4 * (t + 1))
        except Exception as e:
            last = e
            time.sleep(0.4 * (t + 1))
    return ("__FAIL__", str(last))


def parse_create_strings(data_b58):
    d = b58dec(data_b58)
    off = 8
    out = []
    for _ in range(3):
        ln = struct.unpack_from("<I", d, off)[0]
        off += 4
        if ln > 2000 or off + ln > len(d):
            raise ValueError("bad len")
        out.append(d[off:off + ln].decode("utf8", "replace"))
        off += ln
    return out  # name, symbol, uri


def get_name_sym_uri(create_sig):
    tx = None
    for attempt in range(5):
        got_verr = False
        for ver in (1, 2, 3):
            tx = rpc("getTransaction", [create_sig, {"maxSupportedTransactionVersion": ver, "encoding": "jsonParsed"}])
            if isinstance(tx, tuple):
                if tx[0] == "__VERR__":
                    tx = None
                    got_verr = True
                    continue
                tx = None
                break  # hard rpc fail -> retry outer
            if tx:
                break
            # tx is None (result:null) -> treat ver as not the issue
        if tx:
            break
        if got_verr and not tx:
            # all versions returned VERR but no higher version worked; genuinely odd -> retry
            pass
        time.sleep(0.5 * (attempt + 1))
    if not tx:
        return "__RPCFAIL__"
    msg = tx["transaction"]["message"]
    cands = list(msg.get("instructions", []))
    for grp in (tx.get("meta", {}).get("innerInstructions") or []):
        cands += grp["instructions"]
    for ins in cands:
        if ins.get("programId") == PUMP and isinstance(ins.get("data"), str) and len(ins["data"]) > 40:
            try:
                nm, sym, uri = parse_create_strings(ins["data"])
                if uri.startswith("http") or uri.startswith("ipfs"):
                    return nm, sym, uri
            except Exception:
                continue
    return None


def fetch_uri_json(uri):
    # normalize to a bare CID path if ipfs
    tail = None
    if "/ipfs/" in uri:
        tail = uri.split("/ipfs/", 1)[1]
    elif uri.startswith("ipfs://"):
        tail = uri[len("ipfs://"):]
    urls = []
    if tail:
        urls = [g + tail for g in GATEWAYS]
    else:
        urls = [uri]
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=18) as r:
                raw = r.read()
            return json.loads(raw)
        except Exception:
            continue
    return None


SOCIAL_KEYS = {
    "twitter": ["twitter", "x", "twitter_url", "x_url"],
    "telegram": ["telegram", "telegram_url", "tg"],
    "website": ["website", "web", "url", "homepage"],
    "discord": ["discord"],
}


def extract_meta(mint, create_sig):
    out = {"mint": mint, "create_sig": create_sig}
    try:
        nsu = get_name_sym_uri(create_sig)
        if nsu == "__RPCFAIL__":
            out["status"] = "rpc_fail"
            return out
        if not nsu:
            out["status"] = "no_create_parse"
            return out
        nm, sym, uri = nsu
        out["name"] = nm
        out["symbol"] = sym
        out["uri"] = uri
        out["name_len"] = len(nm)
        out["symbol_len"] = len(sym)
        out["name_has_space"] = (" " in nm.strip())
        out["symbol_upper"] = sym.isupper()
        j = fetch_uri_json(uri)
        if j is None:
            out["status"] = "no_uri_json"
            return out
        # case-insensitive key lookup
        low = {str(k).lower(): v for k, v in j.items()} if isinstance(j, dict) else {}

        def present(keys):
            for k in keys:
                v = low.get(k)
                if v is not None and str(v).strip() not in ("", "null", "false", "#", "https://", "http://"):
                    return True
            return False

        out["has_twitter"] = present(SOCIAL_KEYS["twitter"])
        out["has_telegram"] = present(SOCIAL_KEYS["telegram"])
        out["has_website"] = present(SOCIAL_KEYS["website"])
        out["has_discord"] = present(SOCIAL_KEYS["discord"])
        desc = low.get("description")
        out["desc_len"] = len(str(desc).strip()) if desc else 0
        out["has_desc"] = out["desc_len"] > 0
        out["has_image"] = bool(low.get("image"))
        out["show_name"] = bool(low.get("showname") if "showname" in low else low.get("show_name"))
        co = low.get("createdon") or low.get("created_on")
        out["created_on"] = str(co)[:40] if co else None
        out["n_socials"] = sum([out["has_twitter"], out["has_telegram"], out["has_website"], out["has_discord"]])
        out["meta_keys"] = sorted([str(k) for k in (j.keys() if isinstance(j, dict) else [])])[:25]
        out["status"] = "ok"
        return out
    except Exception as e:
        out["status"] = "err:" + str(e)[:80]
        return out


def main():
    label = sys.argv[1]
    mints = json.load(open(sys.argv[2]))
    if isinstance(mints, dict):
        mints = list(mints.keys())
    # map mint -> create_sig from the existing feat files if available
    sig_map = {}
    for fp in sys.argv[4:]:
        try:
            d = json.load(open(fp))
            for m, r in (d.items() if isinstance(d, dict) else []):
                if r.get("create_sig") and m not in sig_map:  # first file wins (expanded_raw trusted)
                    sig_map[m] = r["create_sig"]
        except Exception:
            pass
    outpath = sys.argv[3]
    cache = {}
    if os.path.exists(outpath):
        try:
            cache = json.load(open(outpath))
        except Exception:
            cache = {}
    KEEP = ("ok", "no_uri_json")
    todo = [m for m in mints if m not in cache or cache[m].get("status") not in KEEP]
    print(f"[{label}] total={len(mints)} todo={len(todo)} have_sig={sum(1 for m in todo if m in sig_map)}", file=sys.stderr, flush=True)
    out = dict(cache)
    with ThreadPoolExecutor(max_workers=7) as ex:
        futs = {ex.submit(extract_meta, m, sig_map.get(m)): m for m in todo if sig_map.get(m)}
        done = 0
        for f in as_completed(futs):
            r = f.result()
            out[r["mint"]] = r
            done += 1
            if done % 50 == 0:
                json.dump(out, open(outpath, "w"))
                print(f"  [{label}] {done}/{len(futs)}", file=sys.stderr, flush=True)
    json.dump(out, open(outpath, "w"))
    from collections import Counter
    print(f"[{label}] DONE {outpath} status=" + str(Counter(v.get('status') for v in out.values())), file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
