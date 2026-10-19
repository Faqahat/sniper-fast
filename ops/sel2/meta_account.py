import os, json, time, urllib.request, urllib.error, struct, sys, hashlib, base64
from concurrent.futures import ThreadPoolExecutor, as_completed

RPC = "https://rpc-frankfurt.constant-k.com/?api-key=" + os.environ["CONSTANTK_TOKEN"]
MPL = "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s"
ALPH = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
GATEWAYS = ["https://pump.mypinata.cloud/ipfs/", "https://ipfs.io/ipfs/", "https://cloudflare-ipfs.com/ipfs/"]

# ---------- base58 ----------
def b58dec(s):
    n = 0
    for c in s:
        n = n * 58 + ALPH.index(c)
    full = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\x00" * (len(s) - len(s.lstrip("1"))) + full

def b58enc(b):
    n = int.from_bytes(b, "big"); s = ""
    while n > 0:
        n, r = divmod(n, 58); s = ALPH[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\x00"))) + s

# ---------- ed25519 on-curve check (for PDA bump search) ----------
P = 2**255 - 19
D = (-121665 * pow(121666, P - 2, P)) % P

def on_curve(b):
    # b: 32-byte compressed point (y with sign bit). return True if valid curve point.
    if len(b) != 32:
        return False
    y = int.from_bytes(b, "little")
    sign = (y >> 255) & 1
    y &= (1 << 255) - 1
    if y >= P:
        return False
    y2 = (y * y) % P
    u = (y2 - 1) % P
    v = (D * y2 + 1) % P
    # x^2 = u / v
    try:
        vinv = pow(v, P - 2, P)
    except Exception:
        return False
    x2 = (u * vinv) % P
    # attempt sqrt: candidate = x2^((P+3)/8)
    x = pow(x2, (P + 3) // 8, P)
    if (x * x - x2) % P != 0:
        x = (x * pow(2, (P - 1) // 4, P)) % P
    if (x * x - x2) % P != 0:
        return False  # no sqrt -> not on curve
    if x == 0 and sign:
        return False
    return True

def find_metadata_pda(mint):
    mb = b58dec(mint); mpl = b58dec(MPL)
    seeds = b"metadata" + mpl + mb
    for bump in range(255, -1, -1):
        h = hashlib.sha256(seeds + bytes([bump]) + mpl + b"ProgramDerivedAddress").digest()
        if not on_curve(h):
            return b58enc(h)
    return None

# ---------- rpc ----------
def rpc(method, params, tries=6):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    last = None
    for t in range(tries):
        try:
            req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as r:
                j = json.loads(r.read())
            if "error" in j:
                last = j["error"]; time.sleep(0.3 * (t + 1)); continue
            return j.get("result")
        except urllib.error.HTTPError as e:
            last = e; time.sleep(0.8 + 0.6 * t if getattr(e, "code", 0) == 429 else 0.4 * (t + 1))
        except Exception as e:
            last = e; time.sleep(0.4 * (t + 1))
    return ("__FAIL__", str(last))

def read_str(d, off):
    ln = struct.unpack_from("<I", d, off)[0]; off += 4
    s = d[off:off + ln]; off += ln
    return s.split(b"\x00", 1)[0].decode("utf8", "replace"), off

def parse_metadata(data_b64):
    d = base64.b64decode(data_b64)
    off = 1 + 32 + 32  # key + update_auth + mint
    name, off = read_str(d, off)
    sym, off = read_str(d, off)
    uri, off = read_str(d, off)
    return name, sym, uri

def fetch_uri_json(uri):
    tail = None
    if "/ipfs/" in uri:
        tail = uri.split("/ipfs/", 1)[1]
    elif uri.startswith("ipfs://"):
        tail = uri[7:]
    urls = [g + tail for g in GATEWAYS] if tail else [uri]
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read())
        except Exception:
            continue
    return None

SK = {"twitter": ["twitter", "x", "twitter_url", "x_url"],
      "telegram": ["telegram", "telegram_url", "tg"],
      "website": ["website", "web", "url", "homepage"],
      "discord": ["discord"]}

def work(mint):
    out = {"mint": mint}
    try:
        pda = find_metadata_pda(mint)
        if not pda:
            out["status"] = "no_pda"; return out
        res = rpc("getAccountInfo", [pda, {"encoding": "base64"}])
        if isinstance(res, tuple):
            out["status"] = "rpc_fail"; return out
        val = (res or {}).get("value")
        if not val:
            out["status"] = "no_meta_acct"; return out
        nm, sym, uri = parse_metadata(val["data"][0])
        out.update(name=nm, symbol=sym, uri=uri, name_len=len(nm), symbol_len=len(sym),
                   name_has_space=(" " in nm.strip()), symbol_upper=sym.isupper())
        try:
            from urllib.parse import urlparse
            out["uri_host"] = urlparse(uri).netloc.lower() or "?"
        except Exception:
            out["uri_host"] = "?"
        j = fetch_uri_json(uri)
        if j is None:
            out["status"] = "no_uri_json"; return out
        low = {str(k).lower(): v for k, v in j.items()} if isinstance(j, dict) else {}
        def pres(keys):
            for k in keys:
                v = low.get(k)
                if v is not None and str(v).strip() not in ("", "null", "false", "#", "https://", "http://"):
                    return True
            return False
        out["has_twitter"] = pres(SK["twitter"]); out["has_telegram"] = pres(SK["telegram"])
        out["has_website"] = pres(SK["website"]); out["has_discord"] = pres(SK["discord"])
        desc = low.get("description")
        out["desc_len"] = len(str(desc).strip()) if desc else 0
        out["has_desc"] = out["desc_len"] > 0
        out["has_image"] = bool(low.get("image"))
        out["show_name"] = bool(low.get("showname") if "showname" in low else low.get("show_name"))
        co = low.get("createdon") or low.get("created_on")
        out["created_on"] = str(co)[:50] if co else None
        out["n_socials"] = sum([out["has_twitter"], out["has_telegram"], out["has_website"], out["has_discord"]])
        out["status"] = "ok"
        return out
    except Exception as e:
        out["status"] = "err:" + str(e)[:80]; return out

def main():
    label = sys.argv[1]
    mints = json.load(open(sys.argv[2]))
    if isinstance(mints, dict):
        mints = list(mints.keys())
    outpath = sys.argv[3]
    cache = {}
    if os.path.exists(outpath):
        try:
            cache = json.load(open(outpath))
        except Exception:
            cache = {}
    KEEP = ("ok", "no_uri_json", "no_meta_acct", "no_pda")
    todo = [m for m in mints if m not in cache or cache[m].get("status") not in KEEP]
    print(f"[{label}] total={len(mints)} todo={len(todo)}", file=sys.stderr, flush=True)
    out = dict(cache)
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(work, m): m for m in todo}
        done = 0
        for f in as_completed(futs):
            r = f.result(); out[r["mint"]] = r; done += 1
            if done % 50 == 0:
                json.dump(out, open(outpath, "w"))
                print(f"  [{label}] {done}/{len(todo)}", file=sys.stderr, flush=True)
    json.dump(out, open(outpath, "w"))
    from collections import Counter
    print(f"[{label}] DONE {outpath} " + str(Counter(v.get('status') for v in out.values())), file=sys.stderr, flush=True)

if __name__ == "__main__":
    main()
