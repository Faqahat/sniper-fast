"""Fetch real mainnet pools (read-only, cached) and check every byte offset DESIGN.md relies on: owners, sizes,
discriminators, and cross-references (vault keys in the pool == the token accounts that hold the pool's mints, bin
arrays' lb_pair == the pair, ...). Prints one line per check; any FAIL is a wrong offset."""
import sys
from solrpc import *

PUMP = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"; DLMM = "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"
DAMM = "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG"; CPMM = "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C"
AMM4 = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"; FEEP = "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ"
TOK = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"; T22 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
WSOL = "So11111111111111111111111111111111111111112"
POOLS = {
    PUMP: ["GLL3CzybpSCLZdoACf8QUM5YrKVwyA65kQ2RcTsJxxzV", "6ejg4aYJM3Mk1t2zBKjbJ43df3s7rBMpC9mgo526K51G"],
    DLMM: ["6D4EWF22HfQamimKhX47tqiu9DVCkcxDMrmhnSvewKAo", "C9xcUNdJrY45uBeJiuAEiNUZzxs1M22mDFCus3dm1QWq", "7hvn8egrNGkpQFGyziHxvGkJFWtmoCyXmYYXp4V7tszd"],
    DAMM: ["C8jdide5evNRRVBiisJSnFeHH2k7FKbARP64iyfSrkdf", "2E8c2vnAKQ3WaSHjezHwQ6GozuXRx96JX7GoNoBeqBug", "3Bu5wTUftguy5BxhTgFrukz6wvG6d4xYRKuU43jWA3cg"],
    CPMM: ["GfApkU62yAmUXc6FNsZrBLgcUn8vXdhW6WzSbA5ETtDa", "Hmx1eHEdm67YYZYEathc6aki2q3zjhhTmw7wZPq66BnJ"],
    AMM4: ["FVq2chsiAcPqwL9L3zafF8juQHb7mui6LWMuE8g5L4K4"],
}
fails = 0
def check(cond, what):
    global fails
    print(("ok   " if cond else "FAIL ") + what)
    if not cond: fails += 1

all_pools = [p for v in POOLS.values() for p in v]
A, slot = accounts(all_pools + ["SysvarC1ock11111111111111111111111111111111"])
clk = A["SysvarC1ock11111111111111111111111111111111"][2]
clock_slot, clock_ts = u64(clk, 0), i64(clk, 32)
print(f"slot {slot}; Clock: slot {clock_slot} epoch {u64(clk,16)} unix_timestamp {clock_ts}")

def tok(d):  # SPL token account: mint, owner, amount
    return key(d, 0), key(d, 32), u64(d, 64)

# ---------------------------------------------------------------- PumpSwap
deps = []
for p in POOLS[PUMP]:
    d = A[p][2]
    deps += [key(d, 43), key(d, 75), key(d, 139), key(d, 171)]
gc = pda([b"global_config"], PUMP)[0]; fc = pda([b"fee_config", pk(PUMP)], FEEP)[0]
B, _ = accounts(deps + [gc, fc])
for p in POOLS[PUMP]:
    o, lam, d = A[p]
    check(o == PUMP and d[:8] == disc("Pool"), f"pump {p[:8]} owner+disc, len {len(d)}")
    base, quote, bv, qv = key(d, 43), key(d, 75), key(d, 139), key(d, 171)
    bm, _, bamt = tok(B[bv][2]); qm, _, qamt = tok(B[qv][2])
    check(bm == base and qm == quote and B[bv][0] in (TOK, T22), f"pump {p[:8]} base vault @139 / quote vault @171 hold base_mint @43 / quote_mint @75 (quote {quote[:6]})")
    creator = key(d, 11); canonical = creator == pda([b"pool-authority", pk(base)], "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")[0]
    virt = i128(d, 245); cfb = u64(d, 261) if len(d) >= 269 else None
    print(f"     coin_creator@211={key(d,211)[:8]} mayhem@243={d[243]} cashback@244={d[244]} virtual_quote_reserves(i128)@245={virt} "
          f"creator_fee_bps@261={cfb} can_edit@269={d[269] if len(d)>269 else None} canonical={canonical} reserves base={bamt} quote={qamt}")
    mint = B[base]; check(mint[0] in (TOK, T22) and len(mint[2]) >= 82, f"pump base mint supply@36 = {u64(mint[2],36)} decimals@44 = {mint[2][44]}")
o, _, g = B[gc]
check(o == PUMP and g[:8] == disc("GlobalConfig"), f"pump GlobalConfig {gc[:8]} len {len(g)}")
# GlobalConfig borsh: admin 8, lp_fee_bps 40, protocol_fee_bps 48, disable_flags 56, protocol_fee_recipients 57..313,
# coin_creator_fee_bps 313, admin_set_coin_creator_authority 321, whitelist_pda 353, reserved_fee_recipient 385,
# mayhem_mode_enabled 417, reserved_fee_recipients 418..642, is_cashback_enabled 642, buyback_fee_recipients 643..899,
# buyback_basis_points 899, boost_authority 907, boost_enabled 939, creator_fee_configurable 940, max_configurable_creator_fee_bps 941
print(f"     lp_bps@40={u64(g,40)} protocol_bps@48={u64(g,48)} disable_flags@56={g[56]:#04x} coin_creator_bps@313={u64(g,313)} "
      f"mayhem_enabled@417={g[417]} cashback_enabled@642={g[642]} buyback_bps@899={u64(g,899)} boost_enabled@939={g[939]} "
      f"creator_fee_configurable@940={g[940]} max_cfg_creator_bps@941={u64(g,941)} (len {len(g)})")
o, _, f = B[fc]
check(o == FEEP and f[:8] == disc("FeeConfig"), f"pump FeeConfig {fc[:8]} owner pfee, len {len(f)}")
# FeeConfig: bump 8, admin 9..41, flat_fees 41 (3 x u64), fee_tiers vec @65 (u32 len, then 40-byte {u128, 3 x u64}), stable vec, exotic
o_ = 65; n = u32(f, o_); o_ += 4
tiers = [(u128(f, o_ + 40 * i), u64(f, o_ + 40 * i + 16), u64(f, o_ + 40 * i + 24), u64(f, o_ + 40 * i + 32)) for i in range(n)]
o_ += 40 * n; ns = u32(f, o_); o_ += 4 + 40 * ns
print(f"     flat(lp,proto,creator)@41={u64(f,41),u64(f,49),u64(f,57)} fee_tiers n={n} first={tiers[:2]} last={tiers[-1:]} stable n={ns} exotic@{o_}={(u64(f,o_),u64(f,o_+8),u64(f,o_+16)) if len(f)>=o_+24 else None}")

# ---------------------------------------------------------------- Raydium CPMM
deps = []
for p in POOLS[CPMM]:
    d = A[p][2]; deps += [key(d, 8), key(d, 72), key(d, 104)]
B, _ = accounts(deps)
for p in POOLS[CPMM]:
    o, _, d = A[p]
    check(o == CPMM and d[:8] == disc("PoolState") and len(d) == 637, f"cpmm {p[:8]} owner+disc+len 637")
    cfg = B[key(d, 8)]; v0 = B[key(d, 72)][2]; v1 = B[key(d, 104)][2]
    check(tok(v0)[0] == key(d, 168) and tok(v1)[0] == key(d, 200), "cpmm vault0 @72 / vault1 @104 hold mint0 @168 / mint1 @200")
    check(cfg[0] == CPMM and cfg[2][:8] == disc("AmmConfig") and len(cfg[2]) == 236, f"cpmm amm_config @8 owner+disc+len 236")
    c = cfg[2]
    print(f"     status@329={d[329]:#04x} open_time@373={u64(d,373)} (now {clock_ts}) owed0 p/f/c @341/357/397={u64(d,341)},{u64(d,357)},{u64(d,397)} "
          f"owed1 @349/365/405={u64(d,349)},{u64(d,365)},{u64(d,405)} creator_fee_on@389={d[389]} enable_creator_fee@390={d[390]} "
          f"| cfg trade@12={u64(c,12)} protocol@20={u64(c,20)} fund@28={u64(c,28)} creator@108={u64(c,108)} creator_share@116={u64(c,116)} "
          f"| vaults {tok(v0)[2]} / {tok(v1)[2]}")

# ---------------------------------------------------------------- Raydium AMM v4
deps = []
for p in POOLS[AMM4]:
    d = A[p][2]; deps += [key(d, 336), key(d, 368)]
B, _ = accounts(deps)
for p in POOLS[AMM4]:
    o, _, d = A[p]
    check(o == AMM4 and len(d) == 752, f"ammv4 {p[:8]} owner+len 752")
    cv, pv = B[key(d, 336)][2], B[key(d, 368)][2]
    check(tok(cv)[0] == key(d, 400) and tok(pv)[0] == key(d, 432), "ammv4 coin vault @336 / pc vault @368 hold coin mint @400 / pc mint @432")
    print(f"     status@0={u64(d,0)} swap_fee num/den @176/184={u64(d,176)}/{u64(d,184)} trade_fee @144/152={u64(d,144)}/{u64(d,152)} "
          f"need_take_pnl coin/pc @192/200={u64(d,192)}/{u64(d,200)} pool_open_time@224={u64(d,224)} vaults {tok(cv)[2]} / {tok(pv)[2]}")

# ---------------------------------------------------------------- Meteora DLMM
def arr_index(b): return b // 70
for p in POOLS[DLMM]:
    o, _, d = A[p]
    check(o == DLMM and d[:8] == disc("LbPair") and len(d) == 904, f"dlmm {p[:8]} owner+disc+len 904")
    active, step = i32(d, 76), u16(d, 80)
    c = arr_index(active)
    keys = {i: pda([b"bin_array", pk(p), i.to_bytes(8, "little", signed=True)], DLMM)[0] for i in range(c - 2, c + 3)}
    ext = pda([b"bitmap", pk(p)], DLMM)[0]
    B, _ = accounts(list(keys.values()) + [key(d, 152), key(d, 184), key(d, 552), ext])
    check(tok(B[key(d, 152)][2])[0] == key(d, 88) and tok(B[key(d, 184)][2])[0] == key(d, 120), "dlmm reserve_x @152 / reserve_y @184 hold mint_x @88 / mint_y @120")
    check(B[key(d, 552)] is not None and B[key(d, 552)][0] == DLMM, "dlmm oracle @552 exists, owned by DLMM")
    # bitmap: u64[16] @584 covers array indices -512..511; bit (idx + 512)
    bm = int.from_bytes(d[584:712], "little")
    print(f"     base_factor@8={u16(d,8)} filter@10={u16(d,10)} decay@12={u16(d,12)} reduction@14={u16(d,14)} vfc@16={u32(d,16)} max_va@20={u32(d,20)} "
          f"protocol_share@32={u16(d,32)} power@34={d[34]} function_type@35={d[35]} collect_fee_mode@36={d[36]} | va@40={u32(d,40)} vref@44={u32(d,44)} "
          f"idx_ref@48={i32(d,48)} last_ts@56={i64(d,56)} (now {clock_ts}) | pair_type@75={d[75]} active@76={active} bin_step@80={step} status@82={d[82]} "
          f"activation_type@86={d[86]} activation_point@816={u64(d,816)} | rewards mint@264={key(d,264)[:6]} @408={key(d,408)[:6]} | flags x/y@880/881={d[880]},{d[881]} version@882={d[882]} | ext exists={B[ext] is not None}")
    for i, k in keys.items():
        bit = (bm >> (i + 512)) & 1 if -512 <= i < 512 else None
        a = B[k]
        if a is None:
            check(bit in (0, None), f"dlmm array {i}: absent, bitmap bit {bit}"); continue
        ad = a[2]
        check(a[0] == DLMM and ad[:8] == disc("BinArray") and len(ad) == 10136 and i64(ad, 8) == i and key(ad, 24) == p,
              f"dlmm array {i}: owner+disc+len 10136, index@8 == {i}, lb_pair@24 == pair, version@16={ad[16]}, bitmap bit {bit}")
        nonempty, lo_fields, zero_price = 0, 0, 0
        for j in range(70):
            b = 56 + 144 * j
            ax, ay, price = u64(ad, b), u64(ad, b + 8), u128(ad, b + 16)
            if ax or ay:
                nonempty += 1
                if price == 0: zero_price += 1
            if u64(ad, b + 112) or u64(ad, b + 120) or u64(ad, b + 128) or ad[b + 140]: lo_fields += 1
        print(f"     array {i}: {nonempty} bins with liquidity, {zero_price} of them with price 0, {lo_fields} bins with nonzero limit-order fields @112..141")
    if c * 70 <= active < c * 70 + 70 and B[keys[c]]:
        ad = B[keys[c]][2]; b = 56 + 144 * (active - c * 70)
        print(f"     active bin {active}: amount_x {u64(ad,b)} amount_y {u64(ad,b+8)} price(Q64.64) {u128(ad,b+16)} = {u128(ad,b+16)/2**64:.6e}  (1+step)^id = {(1+step/1e4)**active:.6e}")

# ---------------------------------------------------------------- Meteora DAMM v2
for p in POOLS[DAMM]:
    o, _, d = A[p]
    check(o == DAMM and d[:8] == disc("Pool") and len(d) == 1112, f"damm {p[:8]} owner+disc+len 1112")
    B, _ = accounts([key(d, 232), key(d, 264)])
    va, vb = B[key(d, 232)][2], B[key(d, 264)][2]
    check(tok(va)[0] == key(d, 168) and tok(vb)[0] == key(d, 200), "damm vault a @232 / vault b @264 hold mint a @168 / mint b @200")
    L, smin, smax, sp = u128(d, 360), u128(d, 424), u128(d, 440), u128(d, 456)
    check(smin <= sp <= smax, f"damm sqrt_min@424 <= sqrt_price@456 <= sqrt_max@440 ({smin} <= {sp} <= {smax})")
    print(f"     base_fee: cliff@8={u64(d,8)} mode@16={d[16]} | protocol%@48={d[48]} referral%@50={d[50]} compounding_bps@54={u16(d,54)} | dyn initialized@56={d[56]} "
          f"| liquidity@360={L} activation pt/type @472/480={u64(d,472)}/{d[480]} status@481={d[481]} flags a/b @482/483={d[482]},{d[483]} collect_fee_mode@484={d[484]} "
          f"fee_version@486={d[486]} token amounts a/b @680/688={u64(d,680)}/{u64(d,688)} layout@696={d[696]} | vaults {tok(va)[2]} / {tok(vb)[2]}")
print(f"\n{fails} failures")
sys.exit(1 if fails else 0)
