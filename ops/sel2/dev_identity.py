import os, json, time, urllib.request, urllib.error, base64, hashlib, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

RPC = "https://rpc-frankfurt.constant-k.com/?api-key=" + os.environ["CONSTANTK_TOKEN"]
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
ALPH = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
P = 2**255 - 19
D = (-121665 * pow(121666, P - 2, P)) % P
DISC = bytes.fromhex("17b7f83760d8ac60")  # BondingCurve anchor discriminator


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


def on_curve(b):
    if len(b) != 32:
        return False
    y = int.from_bytes(b, "little"); sign = (y >> 255) & 1; y &= (1 << 255) - 1
    if y >= P:
        return False
    y2 = (y * y) % P; u = (y2 - 1) % P; v = (D * y2 + 1) % P
    try:
        vinv = pow(v, P - 2, P)
    except Exception:
        return False
    x2 = (u * vinv) % P
    x = pow(x2, (P + 3) // 8, P)
    if (x * x - x2) % P != 0:
        x = (x * pow(2, (P - 1) // 4, P)) % P
    if (x * x - x2) % P != 0:
        return False
    if x == 0 and sign:
        return False
    return True


PUMP_B = b58dec(PUMP)


def bc_pda(mint):
    seeds = b"bonding-curve" + b58dec(mint)
    for bump in range(255, -1, -1):
        h = hashlib.sha256(seeds + bytes([bump]) + PUMP_B + b"ProgramDerivedAddress").digest()
        if not on_curve(h):
            return b58enc(h)
    return None


def rpc(method, params, tries=7):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    last = None
    for t in range(tries):
        try:
            req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                j = json.loads(r.read())
            if "error" in j:
                last = j["error"]; time.sleep(0.4 * (t + 1)); continue
            return j.get("result")
        except urllib.error.HTTPError as e:
            last = e; time.sleep(0.8 + 0.6 * t if getattr(e, "code", 0) == 429 else 0.4 * (t + 1))
        except Exception as e:
            last = e; time.sleep(0.5 * (t + 1))
    return ("__FAIL__", str(last))


def get_creator(mint):
    pda = bc_pda(mint)
    if not pda:
        return {"status": "no_pda"}
    res = rpc("getAccountInfo", [pda, {"encoding": "base64"}])
    if isinstance(res, tuple):
        return {"status": "rpc_fail"}
    val = (res or {}).get("value")
    if not val:
        return {"status": "no_bc"}
    d = base64.b64decode(val["data"][0])
    if len(d) < 81 or d[:8] != DISC:
        return {"status": "bad_layout", "len": len(d)}
    return {"status": "ok", "bc": pda, "creator": b58enc(d[49:81]), "complete": bool(d[48])}


def creator_count(creator):
    filt = [{"memcmp": {"offset": 0, "bytes": b58enc(DISC)}},
            {"memcmp": {"offset": 49, "bytes": creator}}]
    res = rpc("getProgramAccounts", [PUMP, {"encoding": "base64",
              "dataSlice": {"offset": 0, "length": 0}, "filters": filt}])
    if isinstance(res, tuple) or res is None:
        return None
    return len(res)


def main():
    phase = sys.argv[1]  # "creators" or "counts"
    if phase == "creators":
        mints = json.load(open(sys.argv[2]))
        if isinstance(mints, dict):
            mints = list(mints.keys())
        outpath = sys.argv[3]
        cache = json.load(open(outpath)) if os.path.exists(outpath) else {}
        todo = [m for m in mints if m not in cache or cache[m].get("status") not in ("ok", "no_bc")]
        print(f"creators: total={len(mints)} todo={len(todo)}", file=sys.stderr, flush=True)
        out = dict(cache)
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs = {ex.submit(get_creator, m): m for m in todo}
            done = 0
            for f in as_completed(futs):
                m = futs[f]; out[m] = f.result(); done += 1
                if done % 100 == 0:
                    json.dump(out, open(outpath, "w")); print(f"  {done}/{len(todo)}", file=sys.stderr, flush=True)
        json.dump(out, open(outpath, "w"))
        from collections import Counter
        print("creators DONE " + str(Counter(v.get("status") for v in out.values())), file=sys.stderr, flush=True)
    elif phase == "counts":
        # argv[2..] = creator-map json files; argv with --out <path>
        files = []
        outpath = None
        a = sys.argv[2:]
        i = 0
        while i < len(a):
            if a[i] == "--out":
                outpath = a[i + 1]; i += 2
            else:
                files.append(a[i]); i += 1
        creators = set()
        for fp in files:
            d = json.load(open(fp))
            for m, v in d.items():
                if v.get("status") == "ok" and v.get("creator"):
                    creators.add(v["creator"])
        cache = json.load(open(outpath)) if os.path.exists(outpath) else {}
        todo = [c for c in creators if c not in cache or cache[c] is None]
        print(f"counts: distinct_creators={len(creators)} todo={len(todo)}", file=sys.stderr, flush=True)
        out = dict(cache)
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = {ex.submit(creator_count, c): c for c in todo}
            done = 0
            for f in as_completed(futs):
                c = futs[f]; out[c] = f.result(); done += 1
                if done % 50 == 0:
                    json.dump(out, open(outpath, "w")); print(f"  {done}/{len(todo)}", file=sys.stderr, flush=True)
        json.dump(out, open(outpath, "w"))
        got = sum(1 for v in out.values() if v is not None)
        print(f"counts DONE got={got}/{len(out)}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
