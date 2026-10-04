//! The public API other tests call: `venue_swap_output`, sessions (state carried across swaps), state mutation.
use venue_harness::*;

#[test]
fn venue_swap_output_on_every_pool() {
    let fx = Fixtures::load().unwrap();
    for p in fx.pools.values() {
        for dir in Dir::BOTH {
            let h = harness_for(&fx, &p.pool_key()).unwrap();
            let x = size_ladder(h.input_reserve(dir), 14)[4];
            let (out, cu) = venue_swap_output(&fx, &p.pool_key(), dir, x).unwrap_or_else(|o| panic!("{} {}: {}", p.pool, dir.short(), o.venue_error()));
            assert!(out > 0 && cu > 1_000, "{} {}: out {out} cu {cu}", p.pool, dir.short());
            // deterministic: the same call gives the same answer (each swap starts from the snapshot)
            assert_eq!(venue_swap_output(&fx, &p.pool_key(), dir, x).unwrap(), (out, cu));
        }
    }
}

/// In a session the second swap sees the first one's pool state: a round trip loses the fees, and the second leg
/// differs from the same swap run on the untouched snapshot.
#[test]
fn session_round_trip_loses_fees() {
    let fx = Fixtures::load().unwrap();
    let mut differs = 0;
    for p in fx.pools.values() {
        let h = Harness::new(&fx, &p.pool_key()).unwrap();
        let x = size_ladder(h.input_reserve(Dir::OneForZero), 14)[5];
        let mut s = h.session();
        let a = s.swap(Dir::OneForZero, x);
        assert!(a.ok, "{} leg 1: {}", p.pool, a.venue_error());
        let b = s.swap(Dir::ZeroForOne, a.amount_out);
        assert!(b.ok, "{} leg 2: {}", p.pool, b.venue_error());
        assert!(b.amount_out < x, "{}: round trip {x} -> {} -> {} made money", p.pool, a.amount_out, b.amount_out);
        let fresh = h.swap(Dir::ZeroForOne, a.amount_out);
        assert!(fresh.ok);
        if fresh.amount_out != b.amount_out { differs += 1; }
    }
    assert!(differs * 10 >= fx.pools.len() * 9, "the session did not carry state: {differs} of {} second legs differ", fx.pools.len());
}

/// Mutation hook: advance the Clock (DESIGN §6.3 "clock variations"); the swap still runs, against the new time.
#[test]
fn clock_variation_hook() {
    let fx = Fixtures::load().unwrap();
    let p = fx.pools.values().find(|p| p.venue == Venue::Dlmm).unwrap();
    let h = Harness::new(&fx, &p.pool_key()).unwrap();
    let x = size_ladder(h.input_reserve(Dir::ZeroForOne), 14)[6];
    let now = h.swap(Dir::ZeroForOne, x);
    let later = h.swap_with(Dir::ZeroForOne, x, &BuildOpts::default(), |svm| {
        let mut c = p.clock.to_clock();
        c.unix_timestamp += 3_600;
        svm.set_sysvar(&c);
    });
    assert!(now.ok && later.ok);
    println!("{} X->Y {x}: out {} at the snapshot's clock, {} one hour later", p.pool, now.amount_out, later.amount_out);
    assert!(later.amount_out >= now.amount_out);
}

#[test]
fn venue_cu_reads_the_top_level_line() {
    let logs: Vec<String> = [
        "Program ComputeBudget111111111111111111111111111111 invoke [1]",
        "Program ComputeBudget111111111111111111111111111111 success",
        "Program pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA invoke [1]",
        "Program log: Instruction: Sell",
        "Program TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA invoke [2]",
        "Program TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA consumed 100 of 1000 compute units",
        "Program TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA success",
        "Program pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA invoke [2]",
        "Program pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA consumed 2000 of 3000 compute units",
        "Program pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA success",
        "Program log: done success",
        "Program pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA consumed 72981 of 1399850 compute units",
        "Program pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA success",
    ].iter().map(|s| s.to_string()).collect();
    assert_eq!(harness::venue_cu(&logs, &keys::PUMPSWAP), Some(72981));
}

#[test]
fn ladders_and_elf_extent() {
    let l = size_ladder(1_000_000_000_000, 14);
    assert_eq!(l.len(), 14);
    assert!(l.windows(2).all(|w| w[0] < w[1]) && l[0] == 100_000 && *l.last().unwrap() <= 500_000_000_000);
    let fx = Fixtures::load().unwrap();
    for e in &fx.manifest.programs {
        let elf = fixture::program_elf(e).unwrap();
        assert_eq!(fixture::elf_extent(&elf), Some(elf.len()), "{}: stored file is not cut at the ELF extent", e.name);
        assert!(e.onchain_size >= e.size);
    }
}
