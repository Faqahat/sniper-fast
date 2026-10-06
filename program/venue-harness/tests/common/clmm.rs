//! Shared by the WP-21 suites (tests/clmm_exactness.rs, tests/clmm_adversarial.rs, tests/clmm_route.rs): the leg as the
//! bridge reads it, and the post-state of a real swap in the fields arbx-sizing predicts.
use serde_json::{json, Value};
use venue_harness::keys;
use venue_harness::*;

fn u128_at(d: &[u8], o: usize) -> u128 { u128::from_le_bytes(d[o..o + 16].try_into().unwrap()) }
fn u64_at(d: &[u8], o: usize) -> u64 { u64::from_le_bytes(d[o..o + 8].try_into().unwrap()) }
fn u32_at(d: &[u8], o: usize) -> u32 { u32::from_le_bytes(d[o..o + 4].try_into().unwrap()) }
fn i32_at(d: &[u8], o: usize) -> i32 { i32::from_le_bytes(d[o..o + 4].try_into().unwrap()) }

/// the sizing kind (DESIGN.md §1.2): 7 Raydium CLMM, 8 Orca Whirlpool
pub fn kind_of(venue: Venue) -> u8 { if venue == Venue::RayClmm { 7 } else { 8 } }

/// the descriptor's array count: Raydium CLMM's remaining accounts (after the 13 fixed), Orca's supplemental tick
/// arrays (after the 15 fixed)
pub fn n_arrays(venue: Venue, sw: &venues::SwapIx) -> usize { sw.ix.accounts.len() - if venue == Venue::RayClmm { 13 } else { 15 } }

/// the leg's own accounts as the program sees them before the swap (executables without their ELF; an absent account
/// as the System program's, empty)
pub fn leg_accounts(h: &Harness, sw: &venues::SwapIx) -> Vec<Value> {
    use base64::Engine as _;
    sw.ix.accounts.iter().map(|m| {
        let a = h.svm().get_account(&m.pubkey).unwrap_or_default();
        let data = if a.executable { vec![] } else { a.data };
        json!({"key": m.pubkey.to_string(), "owner": a.owner.to_string(), "data": base64::engine::general_purpose::STANDARD.encode(&data)})
    }).collect()
}

/// the pool's (and the Orca oracle's) post-state fields the crate predicts: `side` is the fee token (Raydium: token 0 by
/// `fee_on` and the direction) or the input token (Orca: a when a→b)
pub fn venue_post(venue: Venue, pool: &[u8], oracle: Option<&[u8]>, side: bool) -> Value {
    match venue {
        Venue::RayClmm => {
            let dynamic = pool[1096..1176].iter().any(|b| *b != 0);
            json!({"sqrt_price": u128_at(pool, 253).to_string(), "tick": i32_at(pool, 269), "liquidity": u128_at(pool, 237).to_string(),
                "fee_growth_global": u128_at(pool, if side { 277 } else { 293 }).to_string(), "protocol_fees": u64_at(pool, if side { 309 } else { 317 }),
                "fund_fees": u64_at(pool, if side { 1064 } else { 1072 }),
                "dynamic": if dynamic { json!({"idx_ref": i32_at(pool, 1110), "v_ref": u32_at(pool, 1114), "va": u32_at(pool, 1118), "last_update": u64_at(pool, 1122)}) } else { Value::Null }})
        }
        Venue::Whirlpool => json!({"sqrt_price": u128_at(pool, 65).to_string(), "tick": i32_at(pool, 81), "liquidity": u128_at(pool, 49).to_string(),
            "fee_growth_global": u128_at(pool, if side { 165 } else { 245 }).to_string(), "protocol_fee_owed": u64_at(pool, if side { 85 } else { 93 }),
            "adaptive": oracle.map_or(Value::Null, |o| json!({"last_reference_update": u64_at(o, 82), "last_major_swap": u64_at(o, 90),
                "v_ref": u32_at(o, 98), "idx_ref": i32_at(o, 102), "va": u32_at(o, 106)}))}),
        _ => Value::Null,
    }
}

/// the crate's predicted post-state (the bridge's `clmm.post`) in the fields the venue's accounts carry
pub fn crate_post(q: &Value) -> Value {
    let mut p = q["clmm"]["post"].clone();
    if let Some(o) = p.as_object_mut() { o.remove("fee_on_token0"); }
    p
}

/// one real swap in a fresh session (under `clock` when given), with the post-state
pub fn swap_with_post(h: &Harness, dir: Dir, x: u64, o: &BuildOpts, clock: Option<&solana_clock::Clock>) -> (SwapOutcome, Option<Value>) {
    let mut s = h.session();
    if let Some(c) = clock { s.svm.set_sysvar(c); }
    let out = s.swap_opts(dir, x, o);
    if !out.ok { return (out, None); }
    let pool = s.svm.get_account(&h.pool).unwrap();
    let oracle = if h.venue == Venue::Whirlpool { s.svm.get_account(&keys::whirl_oracle(&h.pool)).filter(|a| !a.data.is_empty()).map(|a| a.data) } else { None };
    let side = if h.venue == Venue::RayClmm { match h.view[&h.pool].data[390] { 1 => true, 2 => false, _ => dir.zfo() } } else { dir.zfo() };
    let post = venue_post(h.venue, &pool.data, oracle.as_deref(), side);
    (out, Some(post))
}
