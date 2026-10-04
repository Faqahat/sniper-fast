#!/usr/bin/env python3
"""Capture mainnet snapshots for arbx-exec's real-venue SVM tests (tests/venues.rs). Read-only public RPC; stdlib only.

For every pool below it reads the pool account, derives every account the engine's leg builder names (src/build.rs
`leg`, `pump_leg`, `dlmm_leg`; src/pools.rs `boot` for the pool layouts), and fetches them ALL in one
getMultipleAccounts call, so each venue's snapshot is consistent at one slot. Venue program ELFs (and the PumpSwap fee
program) are read from their programdata accounts into tests/fixtures/programs/<id>.so, with a MANIFEST.json of
md5/sha256 and the last-deploy slot.

    python3 tests/fixtures/fetch_venues.py [--rpc URL] [--only NAME ...]

Never sends a transaction; never reads keys.
"""
import argparse, base64, hashlib, json, os, struct, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RPC = "https://api.mainnet-beta.solana.com"

# ---------------------------------------------------------------------------------------------------------------------
# base58, ed25519 on-curve test, PDAs
# ---------------------------------------------------------------------------------------------------------------------
ALPHA = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def b58d(s):
    n = 0
    for c in s:
        n = n * 58 + ALPHA.index(c)
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(s) - len(s.lstrip("1"))) + b

def b58e(b):
    n = int.from_bytes(b, "big")
    s = ""
    while n:
        n, r = divmod(n, 58)
        s = ALPHA[r] + s
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + s

def k(s):
    v = b58d(s)
    assert len(v) == 32, s
    return v

P = 2**255 - 19
D = (-121665 * pow(121666, P - 2, P)) % P

def on_curve(b):
    """curve25519-dalek CompressedEdwardsY::decompress().is_some(): y (high bit cleared, reduced mod p) has an x."""
    y = (int.from_bytes(b, "little") & ((1 << 255) - 1)) % P
    y2 = y * y % P
    u, v = (y2 - 1) % P, (D * y2 + 1) % P
    x2 = u * pow(v, P - 2, P) % P
    return x2 == 0 or pow(x2, (P - 1) // 2, P) == 1

def create_pda(seeds, program):
    h = hashlib.sha256(b"".join(seeds) + program + b"ProgramDerivedAddress").digest()
    return None if on_curve(h) else h

def find_pda(seeds, program):
    for bump in range(255, -1, -1):
        a = create_pda(seeds + [bytes([bump])], program)
        if a is not None:
            return a, bump
    raise ValueError("no bump")

TOKEN = k("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
ATA_PROGRAM = k("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
WSOL = k("So11111111111111111111111111111111111111112")
DLMM = k("LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo")
PUMPSWAP = k("pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA")
CPMM = k("CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C")
AMMV4 = k("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8")
DAMMV2 = k("cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG")
PUMP_FEE_PROGRAM = k("pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ")
PUMP_GLOBAL_CONFIG = k("ADyA8hdefvWN2dbGGWFotbzWxrAvLW83WG6QCVXvJKqw")
PUMP_EVENT_AUTHORITY = k("GS4CU59F31iL7aR2Q8zVS8DRrcRnXX1yjQ66TqNVQnaR")
PUMP_GVA = k("C2aFPdENg4A2HQsmrd5rTw5TaYBX5Ku887cWjbFKtZpw")
PUMP_FEE_CONFIG = k("5PHirr8joyTMp9JMm6nW7hNDVyEYdkzDqazxPD7RaTjx")
RAYCPMM_AUTHORITY = k("GpMZbSM2GgvTKHJirzeGfMFoaZ8UR2X7F4v8vHTvxFbL")
DAMMV2_POOL_AUTHORITY = k("HLnpSz9h2S4hiLQ43rnSD9XkcUThA7B8hQMKmDaiTLcC")
DAMMV2_EVENT_AUTHORITY = k("3rmHSu74h1ZcmAisVcWerTCiRDQbUrBKmcwptYGjHfet")

def ata(owner, mint, prog):
    return find_pda([owner, prog, mint], ATA_PROGRAM)[0]

# ---------------------------------------------------------------------------------------------------------------------
# RPC
# ---------------------------------------------------------------------------------------------------------------------
def rpc(url, method, params, tries=6):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for i in range(tries):
        try:
            req = urllib.request.Request(url, body, {"Content-Type": "application/json", "User-Agent": "arbx-exec-fixtures"})
            with urllib.request.urlopen(req, timeout=60) as r:
                out = json.loads(r.read())
            if "error" in out:
                raise RuntimeError(out["error"])
            return out["result"]
        except Exception as e:  # noqa: BLE001 (429s and timeouts from the public endpoint)
            if i + 1 == tries:
                raise
            time.sleep(1.5 * (i + 1))
            print(f"  retry {method}: {e}", file=sys.stderr)

def accounts(url, keys):
    """[(key, account or None)], one consistent snapshot; returns (slot, list)"""
    assert len(keys) <= 100
    res = rpc(url, "getMultipleAccounts", [[b58e(x) for x in keys], {"encoding": "base64", "commitment": "confirmed"}])
    out = []
    for key, a in zip(keys, res["value"]):
        if a is None:
            out.append((key, None))
        else:
            out.append((key, {"lamports": a["lamports"], "owner": a["owner"], "executable": a["executable"],
                              "rent_epoch": int(a.get("rentEpoch", 0)) & 0xFFFFFFFFFFFFFFFF,
                              "data": base64.b64decode(a["data"][0])}))
    return res["context"]["slot"], out

def one(url, key):
    return accounts(url, [key])[1][0][1]

# ---------------------------------------------------------------------------------------------------------------------
# per-venue derivations (ports of the engine's builder; the Rust test re-derives and checks every key exists)
# ---------------------------------------------------------------------------------------------------------------------
def pk(d, o):
    return bytes(d[o:o + 32])

def mint_owner(url, mint):
    return k(one(url, mint)["owner"])

def derive(url, venue, pool):
    """(role -> key) for everything this pool's legs name, plus extra keys to snapshot"""
    d = one(url, pool)["data"]
    roles = {"pool": pool}
    if venue == "ammv4":
        nonce = struct.unpack_from("<Q", d, 8)[0]
        auth = create_pda([b"amm authority", bytes([nonce])], AMMV4) or find_pda([b"amm authority"], AMMV4)[0]
        roles.update(authority=auth, vault0=pk(d, 336), vault1=pk(d, 368), mint0=pk(d, 400), mint1=pk(d, 432))
    elif venue == "cpmm":
        roles.update(authority=RAYCPMM_AUTHORITY, config=pk(d, 8), vault0=pk(d, 72), vault1=pk(d, 104),
                     mint0=pk(d, 168), mint1=pk(d, 200), observation=pk(d, 296))
    elif venue == "dammv2":
        roles.update(authority=DAMMV2_POOL_AUTHORITY, event_authority=DAMMV2_EVENT_AUTHORITY,
                     mint0=pk(d, 168), mint1=pk(d, 200), vault0=pk(d, 232), vault1=pk(d, 264))
    elif venue == "dlmm":
        active = struct.unpack_from("<i", d, 76)[0]
        roles.update(mint0=pk(d, 88), mint1=pk(d, 120), vault0=pk(d, 152), vault1=pk(d, 184), oracle=pk(d, 552),
                     bitmap_ext=find_pda([b"bitmap", pool], DLMM)[0], event_authority=find_pda([b"__event_authority"], DLMM)[0])
        c = active // 70
        for i in range(c - 3, c + 4):
            roles[f"bin_array_{i}"] = find_pda([b"bin_array", pool, struct.pack("<q", i)], DLMM)[0]
    elif venue == "pumpswap":
        base, quote = pk(d, 43), pk(d, 75)
        roles.update(mint0=base, mint1=quote, vault0=pk(d, 139), vault1=pk(d, 171), global_config=PUMP_GLOBAL_CONFIG,
                     event_authority=PUMP_EVENT_AUTHORITY, gva=PUMP_GVA, fee_config=PUMP_FEE_CONFIG)
        g = one(url, PUMP_GLOBAL_CONFIG)["data"]
        keys = lambda at, n: [pk(g, at + 32 * i) for i in range(n) if pk(g, at + 32 * i) != b"\0" * 32]
        protocol, reserved, buyback = keys(57, 8), keys(385, 1) + keys(418, 7), keys(643, 8)
        quote_prog = mint_owner(url, quote)
        creator = pk(d, 211)
        for i, f in enumerate(protocol + reserved):
            roles[f"fee_recipient_{i}"] = f
            roles[f"fee_recipient_{i}_ata"] = ata(f, quote, quote_prog)
        for i, b in enumerate(buyback):
            roles[f"buyback_{i}"] = b
            roles[f"buyback_{i}_ata"] = ata(b, quote, quote_prog)
        cva = find_pda([b"creator_vault", creator], PUMPSWAP)[0]
        roles.update(creator_vault_authority=cva, creator_vault_ata=ata(cva, quote, quote_prog),
                     pool_v2=find_pda([b"pool-v2", base], PUMPSWAP)[0])
    else:
        raise ValueError(venue)
    return roles

PROGRAM_OF = {"ammv4": AMMV4, "cpmm": CPMM, "dammv2": DAMMV2, "dlmm": DLMM, "pumpswap": PUMPSWAP}
EXTRA_PROGRAMS = {"pumpswap": [PUMP_FEE_PROGRAM]}

# name -> (venue, pool). SOL/USDC where the venue has it (so routes can cross venues), plus a canonical pump-token
# PumpSwap pool (the engine's widest leg: creator vault, pool-v2, buyback).
POOLS = {
    "dlmm_sol_usdc": ("dlmm", "HTvjzsfX3yU6BUodCjZ5vZkUrAxMDTrBs3CJaq43ashR"),
    "ammv4_sol_usdc": ("ammv4", "58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2"),
    "dammv2_sol_usdc": ("dammv2", "8Pm2kZpnxD3hoMmt4bjStX2Pw2Z9abpbHzZxMPqxPmie"),
    "pumpswap_sol_usdc": ("pumpswap", "Gf7sXMoP8iRw4iiXmJ1nq4vxcRycbGXy5RL8a8LnTd3v"),
    "pumpswap_pump_token": ("pumpswap", "4w2cysotX6czaUGmmWg13hDpY4QEMG2CzeKYEQyK9Ama"),
    "cpmm_sol_token": ("cpmm", "47tCsDbcgzd4uv6brb7SjRvv5th9QfHTMq5YXQRSBQmS"),
}

def elf_len(b):
    """the ELF's own length (the programdata account pads it with zeros to the max length)"""
    assert b[:4] == b"\x7fELF", "not an ELF"
    shoff, = struct.unpack_from("<Q", b, 40)
    shentsize, shnum = struct.unpack_from("<HH", b, 58)
    end = shoff + shentsize * shnum
    phoff, = struct.unpack_from("<Q", b, 32)
    phentsize, phnum = struct.unpack_from("<HH", b, 54)
    for i in range(phnum):
        _, _, off, _, _, filesz, _, _ = struct.unpack_from("<IIQQQQQQ", b, phoff + i * phentsize)
        end = max(end, off + filesz)
    for i in range(shnum):
        _, stype, _, _, off, size = struct.unpack_from("<IIQQQQ", b, shoff + i * shentsize)
        if stype != 8:  # SHT_NOBITS
            end = max(end, off + size)
    return end

def fetch_program(url, prog, manifest):
    acc = one(url, prog)
    owner = acc["owner"]
    if owner == "BPFLoaderUpgradeab1e11111111111111111111111":
        pd_key = bytes(acc["data"][4:36])
        pd = one(url, pd_key)
        data = pd["data"]
        slot, = struct.unpack_from("<Q", data, 4)
        elf = data[45:]
    else:
        pd_key, slot, elf = None, None, acc["data"]
    elf = elf[:elf_len(elf)]
    path = os.path.join(HERE, "programs", b58e(prog) + ".so")
    with open(path, "wb") as f:
        f.write(elf)
    manifest[b58e(prog)] = {"loader": owner, "programdata": b58e(pd_key) if pd_key else None, "last_deploy_slot": slot,
                            "bytes": len(elf), "md5": hashlib.md5(elf).hexdigest(), "sha256": hashlib.sha256(elf).hexdigest()}
    print(f"  program {b58e(prog)}: {len(elf)} bytes md5 {manifest[b58e(prog)]['md5']} deployed slot {slot}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rpc", default=RPC)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--no-programs", action="store_true")
    a = ap.parse_args()
    os.makedirs(os.path.join(HERE, "venues"), exist_ok=True)
    os.makedirs(os.path.join(HERE, "programs"), exist_ok=True)
    mpath = os.path.join(HERE, "programs", "MANIFEST.json")
    manifest = json.load(open(mpath)) if os.path.exists(mpath) else {}
    names = a.only or list(POOLS)
    progs = set()
    for name in names:
        venue, pool = POOLS[name]
        print(f"{name}: {venue} {pool}")
        roles = derive(a.rpc, venue, k(pool))
        keys = list(dict.fromkeys(roles.values()))
        # mints (and so the token programs) are in the same snapshot
        slot, accs = accounts(a.rpc, keys)
        by = dict(accs)
        out = {"name": name, "venue": venue, "pool": pool, "program": b58e(PROGRAM_OF[venue]), "slot": slot,
               "unix_timestamp": int(time.time()), "rpc": a.rpc,
               "roles": {r: b58e(x) for r, x in roles.items()},
               "missing": sorted(b58e(x) for x, v in accs if v is None),
               "accounts": {b58e(x): {**{kk: vv for kk, vv in v.items() if kk != "data"}, "data": base64.b64encode(v["data"]).decode()}
                            for x, v in accs if v is not None}}
        with open(os.path.join(HERE, "venues", name + ".json"), "w") as f:
            json.dump(out, f, indent=1, sort_keys=True)
        print(f"  slot {slot}: {len(out['accounts'])} accounts, missing {len(out['missing'])}")
        progs.add(PROGRAM_OF[venue])
        progs.update(EXTRA_PROGRAMS.get(venue, []))
    if not a.no_programs:
        for p in sorted(progs):
            fetch_program(a.rpc, p, manifest)
        with open(mpath, "w") as f:
            json.dump(manifest, f, indent=1, sort_keys=True)

if __name__ == "__main__":
    main()
