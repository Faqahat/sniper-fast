//! Run real swaps from the command line on a fixture pool:
//!   cargo run --release --bin venue-swap -- <pool address or prefix> <0|1 (1 = token0 in)> <amount> [amount ...] [-v]
//!   cargo run --release --bin venue-swap -- list
use venue_harness::{Dir, Fixtures, Harness};

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let fx = Fixtures::load_all().unwrap_or_else(|e| { eprintln!("{e}"); std::process::exit(1) });
    if args.first().map(|s| s.as_str()) == Some("list") || args.len() < 3 {
        for p in fx.pools.values() { println!("{:<9} {} slot {} {}  t0 {} t1 {}", p.venue.name(), p.pool, p.slot, p.label, p.token0, p.token1); }
        if args.len() < 3 && args.first().map(|s| s.as_str()) != Some("list") { eprintln!("usage: venue-swap <pool> <1|0: token0 in?> <amount>... [-v]"); }
        return;
    }
    let p = fx.find(&args[0]).unwrap_or_else(|| { eprintln!("no fixture pool matching {}", args[0]); std::process::exit(1) });
    let dir = Dir::from_zfo(args[1] == "1");
    let verbose = args.iter().any(|a| a == "-v");
    let h = Harness::new(&fx, &p.pool_key()).unwrap_or_else(|e| { eprintln!("{e}"); std::process::exit(1) });
    for a in args[2..].iter().filter(|a| *a != "-v") {
        let amount: u64 = a.replace('_', "").parse().expect("amount");
        let o = h.swap(dir, amount);
        if o.ok {
            println!("{} {} in {amount} -> out {} (spent {}) cu {} (tx {}) arrays {:?}", p.venue.name(), dir.short(), o.amount_out, o.spent,
                o.cu_venue.unwrap_or(0), o.cu_tx, o.dlmm_arrays);
        } else {
            println!("{} {} in {amount} -> FAILED {}", p.venue.name(), dir.short(), o.venue_error());
        }
        if verbose { for l in &o.logs { println!("    {l}"); } }
    }
}
