//! capture-post: real swaps on every fixture pool (and the byte mutations `tests/exactness.rs` uses), recording what
//! each swap left in the pool's own accounts. The engine's accuracy monitor (`src/accuracy.rs`, PLAN-ADDENDUM WP-16)
//! predicts exactly that post-state from the pre-state, so these records are its oracle on the real programs: the
//! engine's tests read them from `testdata/venue-parity/` (copied there with the fixture snapshots, which are the
//! pre-states; I-11: tests read only testdata/).
//!
//!   cargo run --release --bin capture_post > ../../testdata/venue-parity/real-swaps.json
//!
//! Output: `{"swaps": [{case, patches, venue, pool, dir, exact_out, amount_in, ok, out, spent, err, dlmm_arrays, post}]}`.
//! `exact_out` (PumpSwap's `buy`, WP-16 review F6): `amount_in` is then the base amount out asked for.
//! `patches` are the case's byte mutations ([key, offset, hex]); `post` lists, per fixture account the swap changed (in
//! key order), the u64 words that changed ([offset, value after]); accounts outside the snapshot (the test wallet's,
//! ones the swap created) are left out. Sizes: the 14-size ladder of `tests/swaps.rs` per direction (an exact-out buy:
//! over the base reserve), DLMM legs with the engine's 5 bin arrays (`dlmm_arrays`: the ones passed). The output is
//! byte-for-byte reproducible from the fixtures (tools/ci-venue-parity.sh checks the testdata copy against a fresh run).
//!
//! PLAN-ADDENDUM WP-21: `--clmm` does the same on `fixtures/pools-clmm` (Raydium CLMM and Orca Whirlpool, with the
//! mutations of `tests/clmm_exactness.rs`), exact in and exact out both ways, each swap with the remaining accounts the
//! leg passed (`tick_arrays`: their start indexes in order; `ext`: the bitmap extension first; at most 7 in all, the
//! engine's limit), into `testdata/venue-parity/real-swaps-clmm.json`:
//!
//!   cargo run --release --bin capture_post -- --clmm > ../../testdata/venue-parity/real-swaps-clmm.json
use serde_json::{json, Value};
use solana_address::Address;
use venue_harness::*;

fn u64_at(d: &[u8], o: usize) -> u64 { u64::from_le_bytes(d[o..o + 8].try_into().unwrap()) }
fn hex(b: &[u8]) -> String { b.iter().map(|x| format!("{x:02x}")).collect() }

fn i32_at(d: &[u8], o: usize) -> i32 { i32::from_le_bytes(d[o..o + 4].try_into().unwrap()) }

/// the words a swap changed in each snapshot account (key order), `post` of the output
fn post_words(h: &Harness, keys: &[Address], s: &Session) -> Vec<Value> {
    let mut post = vec![];
    for k in keys {
        let before = &h.view[k];
        if before.executable { continue; }
        let Some(after) = s.svm.get_account(k) else { continue };
        if after.data.len() != before.data.len() { post.push(json!({"key": k.to_string(), "resized": after.data.len()})); continue; }
        let words: Vec<Value> = (0..before.data.len() / 8).filter(|w| before.data[8 * w..8 * w + 8] != after.data[8 * w..8 * w + 8])
            .map(|w| json!([8 * w, u64_at(&after.data, 8 * w)])).collect();
        if !words.is_empty() { post.push(json!({"key": k.to_string(), "words": words})); }
    }
    post
}

/// PLAN-ADDENDUM WP-21: the CLMM fixtures (`--clmm`)
fn clmm() {
    let fx = Fixtures::load_clmm().unwrap();
    // the engine passes the extension and at most 6 tick arrays (arbx-sizing's 7 remaining accounts)
    let opts = BuildOpts { tick_max_arrays: 6, ..Default::default() };
    let mut swaps = vec![];
    let mut pools: Vec<&PoolFixture> = fx.pools.values().collect();
    pools.sort_by(|a, b| a.pool.cmp(&b.pool));
    for p in pools {
        let pool = p.pool_key();
        let h0 = Harness::new(&fx, &pool).unwrap();
        let d = h0.view[&pool].data.clone();
        // the mutations of tests/clmm_exactness.rs `cases`
        let mut cases: Vec<(String, Vec<Patch>)> = vec![("snapshot".into(), vec![])];
        match p.venue {
            Venue::RayClmm => {
                let fee_on = d[390];
                for f in [0u8, 1, 2] { if f != fee_on { cases.push((format!("fee_on={f}"), vec![Patch::new(pool, 390, &[f])])); } }
                if d[1096..1176].iter().any(|b| *b != 0) {
                    cases.push(("dynamic fee cleared".into(), vec![Patch::new(pool, 1096, &[0u8; 80])]));
                } else {
                    let ts = u16::from_le_bytes([d[235], d[236]]) as i32;
                    let idx = i32_at(&d, 269).div_euclid(ts);
                    let mut b = vec![];
                    b.extend(10u16.to_le_bytes()); b.extend(60u16.to_le_bytes()); b.extend(5_000u16.to_le_bytes());
                    b.extend(20_000u32.to_le_bytes()); b.extend(200_000u32.to_le_bytes()); b.extend(idx.to_le_bytes());
                    b.extend(30_000u32.to_le_bytes()); b.extend(40_000u32.to_le_bytes()); b.extend((p.clock.unix_timestamp as u64 - 5).to_le_bytes());
                    cases.push(("dynamic fee set".into(), vec![Patch::new(pool, 1096, &b)]));
                }
            }
            Venue::Whirlpool => {
                let oracle = keys::whirl_oracle(&pool);
                if h0.view.contains_key(&oracle) { cases.push(("adaptive state reset".into(), vec![Patch::new(oracle, 82, &[0u8; 28])])); }
            }
            _ => {}
        }
        for (label, patches) in cases {
            let h = Harness::with_patches(&fx, &pool, &patches).unwrap();
            let mut keys: Vec<Address> = h.view.keys().copied().collect();
            keys.sort_by_key(|k| k.to_bytes());
            for dir in Dir::BOTH {
                for exact_out in [false, true] {
                    let o = BuildOpts { exact_out, ..opts.clone() };
                    let sw = h.build(dir, 1, &o).unwrap();
                    let n_fixed = if p.venue == Venue::RayClmm { 13 } else { 15 };
                    let ext = p.venue == Venue::RayClmm && sw.ix.accounts.len() > n_fixed && h.view.get(&sw.ix.accounts[n_fixed].pubkey).is_some_and(|a| a.data.len() == 1_832);
                    let ladder = if exact_out { size_ladder(h.output_reserve(dir), 14) } else { size_ladder(h.input_reserve(dir), 14) };
                    for x in ladder {
                        let mut s = h.session();
                        let r = s.swap_opts(dir, x, &o);
                        let post = if r.ok { post_words(&h, &keys, &s) } else { vec![] };
                        let err = r.err.as_ref().map(|_| r.venue_error().chars().take(160).collect::<String>());
                        swaps.push(json!({"case": label, "patches": patches.iter().map(|p| json!([p.key.to_string(), p.offset, hex(&p.bytes)])).collect::<Vec<_>>(),
                            "venue": p.venue.name(), "pool": p.pool, "dir": dir.short(), "exact_out": exact_out, "amount_in": x, "ok": r.ok, "out": r.amount_out, "spent": r.spent,
                            "err": err, "tick_arrays": sw.tick_arrays, "ext": ext, "cu": r.cu_venue, "post": post}));
                    }
                }
            }
        }
    }
    eprintln!("{} swaps", swaps.len());
    println!("{}", serde_json::to_string(&json!({"source": "program/venue-harness capture_post --clmm (real mainnet programs in LiteSVM on fixtures/pools-clmm)",
        "swaps": swaps})).unwrap());
}

fn main() {
    if std::env::args().any(|a| a == "--clmm") { return clmm(); }
    let fx = Fixtures::load().unwrap();
    let opts = BuildOpts { dlmm_max_arrays: 5, ..Default::default() };
    let mut swaps = vec![];
    for p in fx.pools.values() {
        let pool = p.pool_key();
        let h0 = Harness::new(&fx, &pool).unwrap();
        let fee_mint = venues::pool_has_transfer_fee(&h0.view, &h0.tokens);
        let u64b = |v: u64| v.to_le_bytes().to_vec();
        // the mutations of tests/exactness.rs `cases`
        let mut cases: Vec<(String, Vec<Patch>)> = vec![("snapshot".into(), vec![])];
        match p.venue {
            Venue::RayCpmm if !fee_mint => for on in 0u8..=2 {
                cases.push((format!("enable_creator_fee=1 creator_fee_on={on}"), vec![Patch::new(pool, 389, &[on, 1])]));
            },
            Venue::RayAmmV4 => {
                let coin = venues::token_amount(&h0.view[&h0.tokens.vault0].data).unwrap();
                let pc = venues::token_amount(&h0.view[&h0.tokens.vault1].data).unwrap();
                cases.push(("need_take_pnl 1%".into(), vec![Patch::new(pool, 192, &u64b(coin / 100)), Patch::new(pool, 200, &u64b(pc / 100))]));
            }
            Venue::Dlmm => {
                let cfm = h0.view[&pool].data[36];
                cases.push((format!("collect_fee_mode={}", 1 - cfm.min(1)), vec![Patch::new(pool, 36, &[1 - cfm.min(1)])]));
            }
            Venue::PumpSwap => {
                cases.push(("virtual_quote_reserves=0".into(), vec![Patch::new(pool, 245, &[0u8; 16])]));
                cases.push(("creator_fee_bps=0".into(), vec![Patch::new(pool, 261, &[0u8; 8])]));
            }
            Venue::DammV2 if !fee_mint => {
                let cfm = h0.view[&pool].data[484];
                if cfm <= 1 { cases.push((format!("collect_fee_mode={}", 1 - cfm), vec![Patch::new(pool, 484, &[1 - cfm])])); }
            }
            _ => {}
        }
        for (label, patches) in cases {
            let h = Harness::with_patches(&fx, &pool, &patches).unwrap();
            // in key order: the output is byte-for-byte reproducible (tools/ci-venue-parity.sh compares it)
            let mut keys: Vec<Address> = h.view.keys().copied().collect();
            keys.sort_by_key(|k| k.to_bytes());
            // PumpSwap: also the exact-out `buy` (WP-16 review F6), the amount being the base out
            let exact_out_buy = p.venue == Venue::PumpSwap && venues::engine_leg_executes(p.venue, &h.view[&pool].data);
            for (dir, exact_out) in Dir::BOTH.into_iter().map(|d| (d, false)).chain(exact_out_buy.then_some((Dir::OneForZero, true))) {
                let o_opts = BuildOpts { exact_out, ..opts.clone() };
                let ladder = if exact_out { size_ladder(h.output_reserve(dir), 14) } else { size_ladder(h.input_reserve(dir), 14) };
                for x in ladder {
                    let mut s = h.session();
                    let o = s.swap_opts(dir, x, &o_opts);
                    let mut post = vec![];
                    if o.ok {
                        for k in &keys {
                            let before = &h.view[k];
                            if before.executable { continue; }
                            let Some(after) = s.svm.get_account(k) else { continue };
                            if after.data.len() != before.data.len() { post.push(json!({"key": k.to_string(), "resized": after.data.len()})); continue; }
                            let words: Vec<Value> = (0..before.data.len() / 8).filter(|w| before.data[8 * w..8 * w + 8] != after.data[8 * w..8 * w + 8])
                                .map(|w| json!([8 * w, u64_at(&after.data, 8 * w)])).collect();
                            if !words.is_empty() { post.push(json!({"key": k.to_string(), "words": words})); }
                        }
                    }
                    let err = o.err.as_ref().map(|_| o.venue_error().chars().take(160).collect::<String>());
                    swaps.push(json!({"case": label, "patches": patches.iter().map(|p| json!([p.key.to_string(), p.offset, hex(&p.bytes)])).collect::<Vec<_>>(),
                        "venue": p.venue.name(), "pool": p.pool, "dir": dir.short(), "exact_out": exact_out, "amount_in": x, "ok": o.ok, "out": o.amount_out, "spent": o.spent,
                        "err": err, "dlmm_arrays": o.dlmm_arrays, "post": post}));
                }
            }
        }
    }
    eprintln!("{} swaps", swaps.len());
    println!("{}", serde_json::to_string(&json!({"source": "program/venue-harness capture_post (real mainnet programs in LiteSVM on fixtures/pools)",
        "swaps": swaps})).unwrap());
}
