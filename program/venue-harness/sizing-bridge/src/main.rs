//! sizing-bridge: stdin = {"clock": {slot, unix_timestamp, epoch}, "legs": [LegReq]}, stdout = {"legs": [LegResp]}.
//!
//! LegReq  = {id, kind (1..=8), base_or_token0_in, n_bin_arrays, pump_bump, [max_bins (DLMM; default 255; CLMM: none
//!            unless given)], program, input_mint, accounts: [{key, owner, data (base64)}]   (the leg's own account list,
//!            engine layout), amounts: [u64], [exact_out (a PumpSwap buy leg: each amount is the base out,
//!            `PumpLeg::quote_exact_out`; a Raydium CLMM / Orca Whirlpool leg: each amount is the output wanted)]}
//! LegResp = {id, parse: "ok" | "abort:<Abort>" | "desc:<DescError>", max_bins,
//!            quotes: [{amount, ok, out, spent, err, [bins], [unbounded: {ok, out, spent, err}], [clmm]}]}
//! A Raydium CLMM / Orca Whirlpool quote carries `clmm`: the walk (steps, initialized ticks crossed, the tick arrays read)
//! and the post-swap pool the crate predicts (PLAN-ADDENDUM WP-21: compared with the real program's post-state).
//! A DLMM quote carries the bins with liquidity the swap needs without a budget (`bins`); one that ends at the walk
//! budget (`err` "Budget": not evaluated) also carries the same quote without a budget (`unbounded`, the maths the
//! test compares with the venue).
//!
//! Plan mode (tests/route.rs): a request with a `"plan"` object {cap, min_size, engine_amount, min_profit, flags,
//! max_iters, lamport_offset, pairs: [[buy, sell]]} runs `arbx_sizing::plan` over its legs (each resolved as above)
//! and answers {"plan": {outcome, reason, pair, amount, x_star, modeled_profit, modeled_profit_e, modeled_y,
//! modeled_y_e, evals, bins}, "max_bins": [per leg]} or {"plan_error": "<DescError>"}. A DLMM leg's `max_bins`
//! "auto" applies the engine's rule (DESIGN.md §4.3): the bins with liquidity the leg's exact swap needs at the
//! route's cap (a buy leg at `cap`, a sell leg at the output of the first pair's buy leg at `cap`), at most 255.
//!
//! Optional `"probe": true` on a LegReq (tests/adversarial.rs): the bridge also quotes the leg's boundary sizes as the
//! crate itself sees them, each with its ±1 and ±2 neighbours, and returns them in `quotes` after `amounts`:
//! DLMM: every layer edge and every bin's drain threshold along the crate's walk (first 24 bins); PumpSwap sell, DLMM
//! and DAMM v2: `cap_in()` (exact); every kind: x with x·fee ≡ 0 or −1 (mod the fee denominator) near each requested
//! amount.
//!
//! It resolves the state accounts exactly as arbx-exec will (`layout::check_positions` over the leg's account list),
//! then calls `AnyLeg::parse(&LegIn, &Clock, PdaFn)` and `quote` (arbx-sizing's leg API, DESIGN.md §5.3). Only
//! `adapter` touches the arbx-sizing API: if the crate's API changes, this is the one function to align.
use base64::Engine as _;
use serde_json::{json, Value};
use std::io::Read;

fn b58(s: &str) -> [u8; 32] {
    const A: &[u8] = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
    let mut n = [0u8; 40];
    for c in s.bytes() {
        let mut carry = A.iter().position(|&a| a == c).expect("base58") as u32;
        for b in n.iter_mut().rev() { carry += *b as u32 * 58; *b = carry as u8; carry >>= 8; }
    }
    let mut out = [0u8; 32];
    out.copy_from_slice(&n[8..]);
    out
}

struct Acct { key: [u8; 32], owner: [u8; 32], data: Vec<u8> }

/// create_program_address on the host: sha256(seeds || program || "ProgramDerivedAddress"), valid iff off the curve
fn create_program_address(seeds: &[&[u8]], program: &[u8; 32]) -> Option<[u8; 32]> {
    use sha2::Digest;
    let mut h = sha2::Sha256::new();
    for s in seeds { h.update(s); }
    h.update(program);
    h.update(b"ProgramDerivedAddress");
    let out: [u8; 32] = h.finalize().into();
    curve25519_dalek::edwards::CompressedEdwardsY(out).decompress().is_none().then_some(out)
}

/// One leg: parse once, then quote every amount. Returns (parse status, per-amount rows {ok, out, spent, err, ...}).
fn adapter(clock: &Value, leg: &Value, accts: &[Acct], amounts: &mut Vec<u64>) -> (String, Vec<Value>) {
    use arbx_sizing::*;
    let clock = Clock { slot: clock["slot"].as_u64().unwrap(), unix_timestamp: clock["unix_timestamp"].as_i64().unwrap(), epoch: clock["epoch"].as_u64().unwrap() };
    let kind = Kind::from_u8(leg["kind"].as_u64().unwrap() as u8).expect("kind");
    let mut desc = LegDesc::new(kind, leg["base_or_token0_in"].as_bool().unwrap());
    desc.n_bin_arrays = leg["n_bin_arrays"].as_u64().unwrap() as u8;
    desc.pump_bump = leg["pump_bump"].as_u64().unwrap() as u8;
    if kind == Kind::Dlmm { desc.max_bins = leg["max_bins"].as_u64().unwrap_or(255) as u8; }
    // a CLMM leg's walk budget (swap steps): only when the request gives one (else unbounded after parse)
    let clmm = matches!(kind, Kind::RayClmm | Kind::Whirlpool);
    if clmm { desc.max_bins = leg["max_bins"].as_u64().unwrap_or(255).clamp(1, 255) as u8; }
    let pos = match layout::check_positions(&desc, accts.len()) { Ok(p) => p, Err(e) => return (format!("desc:{e:?}"), vec![]) };
    let state: Vec<AcctRef> = pos.into_iter().map(|i| { let a = &accts[i as usize]; AcctRef { key: &a.key, owner: &a.owner, data: &a.data } }).collect();
    let program = b58(leg["program"].as_str().unwrap());
    let input_mint = b58(leg["input_mint"].as_str().unwrap());
    let li = LegIn { desc, program: &program, state: &state, input_mint: &input_mint };
    let l = match AnyLeg::parse(&li, &clock, create_program_address) {
        Err(e) => return (format!("desc:{e:?}"), vec![]),
        Ok(Parsed { leg: Err(a), .. }) => return (format!("abort:{a:?}"), vec![]),
        Ok(Parsed { leg: Ok(l), .. }) => l,
    };
    let l = if clmm && leg["max_bins"].as_u64().is_none() {
        match l {
            AnyLeg::RayClmm(x) => AnyLeg::RayClmm(x.with_budget(arbx_sizing::venue::raydium_clmm::NO_BUDGET)),
            AnyLeg::Whirl(x) => AnyLeg::Whirl(x.with_budget(arbx_sizing::venue::orca_whirlpool::NO_BUDGET)),
            o => o,
        }
    } else { l };
    if leg["probe"].as_bool() == Some(true) {
        let mut extra = boundaries(&l, amounts);
        extra.retain(|x| *x > 0 && !amounts.contains(x));
        extra.sort();
        extra.dedup();
        amounts.extend(extra);
    }
    // `"exact_out": true` (a PumpSwap buy leg): each amount is the base out, quoted by `PumpLeg::quote_exact_out`
    let exact_out = leg["exact_out"].as_bool() == Some(true);
    let quotes = amounts.iter().map(|&x| {
        // a CLMM leg: the walk and the post-swap pool with the quote
        let walk = clmm_walk(&l, x, exact_out);
        let r = if let Some(w) = &walk { w.0 } else if exact_out {
            match l { AnyLeg::Pump(p) => p.quote_exact_out(x).map(|(_, q)| q), _ => Err(QuoteErr::Abort(Abort::Unsupported)) }
        } else { l.quote(x) };
        let mut row = quote_row(&r);
        if let Some((_, Some(v))) = walk { row["clmm"] = v; }
        if let AnyLeg::Dlmm(d) = l {
            // the bins with liquidity the swap needs (no budget): the venue's own CU grows with them
            row["bins"] = json!(d.bins_for(x));
            if r == Err(QuoteErr::Budget) { row["unbounded"] = quote_row(&d.with_budget(arbx_sizing::venue::dlmm::NO_BUDGET).quote(x)); }
        }
        row
    }).collect();
    ("ok".into(), quotes)
}

/// A CLMM leg's exact swap: the quote and, when Ok, its walk and the post-swap pool as JSON. None for other kinds
fn clmm_walk(l: &arbx_sizing::AnyLeg, x: u64, exact_out: bool) -> Option<(Result<arbx_sizing::Quote, arbx_sizing::QuoteErr>, Option<Value>)> {
    use arbx_sizing::AnyLeg;
    match l {
        AnyLeg::RayClmm(c) => {
            let r = c.fills(x, exact_out, &mut |_| {});
            Some(match r {
                Ok(w) => {
                    let d = w.post.dynamic;
                    (Ok(w.quote), Some(json!({"steps": w.steps, "crossed": w.crossed, "arrays": w.arrays[..w.n_arrays as usize].to_vec(),
                        "post": {"sqrt_price": w.post.sqrt_price.to_string(), "tick": w.post.tick, "liquidity": w.post.liquidity.to_string(),
                            "fee_growth_global": w.post.fee_growth_global.to_string(), "protocol_fees": w.post.protocol_fees, "fund_fees": w.post.fund_fees,
                            "fee_on_token0": c.fee_on_token0,
                            "dynamic": d.map(|d| json!({"idx_ref": d.idx_ref, "v_ref": d.v_ref, "va": d.va, "last_update": d.last_update}))}})))
                }
                Err(e) => (Err(e), None),
            })
        }
        AnyLeg::Whirl(c) => {
            let r = c.fills(x, exact_out, &mut |_| {});
            Some(match r {
                Ok(w) => {
                    let a = w.post.adaptive;
                    (Ok(w.quote), Some(json!({"steps": w.steps, "crossed": w.crossed, "arrays": w.arrays[..w.n_arrays as usize].to_vec(),
                        "arrays_used": w.arrays_used,
                        "post": {"sqrt_price": w.post.sqrt_price.to_string(), "tick": w.post.tick, "liquidity": w.post.liquidity.to_string(),
                            "fee_growth_global": w.post.fee_growth_global.to_string(), "protocol_fee_owed": w.post.protocol_fee_owed,
                            "adaptive": a.map(|a| json!({"last_reference_update": a.last_reference_update, "last_major_swap": a.last_major_swap,
                                "v_ref": a.v_ref, "idx_ref": a.idx_ref, "va": a.va}))}})))
                }
                Err(e) => (Err(e), None),
            })
        }
        _ => None,
    }
}

fn quote_row(r: &Result<arbx_sizing::Quote, arbx_sizing::QuoteErr>) -> Value {
    match r {
        Ok(q) => json!({"ok": true, "out": q.out, "spent": q.spent, "err": ""}),
        Err(e) => json!({"ok": false, "out": 0, "spent": 0, "err": format!("{e:?}")}),
    }
}

/// The leg's boundary sizes as arbx-sizing sees them (probe mode), each with ±1, ±2.
fn boundaries(l: &arbx_sizing::AnyLeg, amounts: &[u64]) -> Vec<u64> {
    use arbx_sizing::AnyLeg;
    let mut b: Vec<u128> = vec![];
    match l {
        AnyLeg::Dlmm(d) => {
            let mut w = d.walker();
            let (mut total, mut n) = (0u128, 0);
            while let Some(bin) = w.next_bin() {
                n += 1;
                if n > 24 || bin.price == 0 { break; }
                let Some(rate) = d.rate(bin.id) else { break };
                let gross = |e: u128| if d.p.fee_on_input { e + (e * rate).div_ceil(1_000_000_000 - rate) } else { e };
                let mut e = 0u128;
                for &lay in bin.layers.iter().filter(|&&x| x > 0) {
                    let lay = lay as u128;
                    let need = if d.p.swap_for_y { (lay << 64).div_ceil(bin.price) } else { (lay * bin.price).div_ceil(1u128 << 64) };
                    e += need;
                    b.push(total + gross(e));
                }
                total += gross(e);
                if total > u64::MAX as u128 { break; }
            }
        }
        _ => {}
    }
    // a CLMM leg: the cumulative input at the end of each swap step of an unbounded swap (a tick crossing, a
    // tick-spacing or tick-group boundary, a limit-order fill), first 48 steps
    match l {
        AnyLeg::RayClmm(c) => {
            let mut st = c.stream();
            let mut acc = 0u128;
            for _ in 0..48 {
                let mut ends: Vec<u128> = vec![];
                if st.next(&mut |p| { acc += p.used as u128; ends.push(acc); }).is_err() { break; }
                b.extend(ends);
            }
        }
        AnyLeg::Whirl(c) => {
            let mut st = c.stream();
            let mut acc = 0u128;
            for _ in 0..48 {
                let mut ends: Vec<u128> = vec![];
                if st.next(&mut |p| { acc += p.used as u128; ends.push(acc); }).is_err() { break; }
                b.extend(ends);
            }
        }
        _ => {}
    }
    // every closed-form or walked capacity is exact now (DLMM within the leg's budget)
    if let Some(c) = l.cap_in() { b.push(c as u128); }
    // fee-rounding residues: x·f mod den in {0, den-1} next to each requested amount
    let fee = match l {
        AnyLeg::Cpmm(c) => Some((c.fee_in as u128, 1_000_000u128)),
        AnyLeg::Amm(a) => Some((a.num as u128, a.den as u128)),
        AnyLeg::Damm(d) => d.fee_fixed.map(|f| (f as u128, 1_000_000_000u128)),
        AnyLeg::RayClmm(c) => Some((c.trade_fee_rate as u128, 1_000_000u128)),
        AnyLeg::Whirl(c) => Some((c.fee_rate as u128, 1_000_000u128)),
        _ => None,
    };
    if let Some((f, den)) = fee {
        if f > 0 {
            let g = gcd(f, den);
            let period = den / g;
            for &x in amounts.iter().filter(|&&x| x > 1_000) {
                let base = (x as u128 / period) * period;
                b.push(base);
                // x·f ≡ −1 (mod den) exists only when gcd(f, den) == 1
                if g == 1 { if let Some(inv) = modinv(f % den, den) { b.push(base + ((den - 1) * inv) % den); } }
            }
        }
    }
    let mut out = vec![];
    for v in b {
        for d in [-2i128, -1, 0, 1, 2] {
            let x = v as i128 + d;
            if x > 0 && x <= u64::MAX as i128 { out.push(x as u64); }
        }
    }
    out
}

fn gcd(a: u128, b: u128) -> u128 { if b == 0 { a } else { gcd(b, a % b) } }
fn modinv(a: u128, m: u128) -> Option<u128> {
    let (mut t, mut nt, mut r, mut nr) = (0i128, 1i128, m as i128, a as i128);
    while nr != 0 { let q = r / nr; (t, nt) = (nt, t - q * nt); (r, nr) = (nr, r - q * nr); }
    if r != 1 { return None; }
    Some(((t % m as i128 + m as i128) % m as i128) as u128)
}

fn decode_accts(leg: &Value) -> Vec<Acct> {
    leg["accounts"].as_array().unwrap().iter().map(|a| Acct {
        key: b58(a["key"].as_str().unwrap()), owner: b58(a["owner"].as_str().unwrap()),
        data: base64::engine::general_purpose::STANDARD.decode(a["data"].as_str().unwrap()).unwrap() }).collect()
}

/// plan mode: every leg resolved through `layout::check_positions`, then `plan`
fn plan_mode(req: &Value) -> Value {
    use arbx_sizing::*;
    let c = &req["clock"];
    let clock = Clock { slot: c["slot"].as_u64().unwrap(), unix_timestamp: c["unix_timestamp"].as_i64().unwrap(), epoch: c["epoch"].as_u64().unwrap() };
    let legs = req["legs"].as_array().unwrap();
    let accts: Vec<Vec<Acct>> = legs.iter().map(decode_accts).collect();
    let mut descs = vec![];
    let mut keys = vec![];
    for leg in legs {
        let mut d = LegDesc::new(Kind::from_u8(leg["kind"].as_u64().unwrap() as u8).expect("kind"), leg["base_or_token0_in"].as_bool().unwrap());
        d.n_bin_arrays = leg["n_bin_arrays"].as_u64().unwrap() as u8;
        d.pump_bump = leg["pump_bump"].as_u64().unwrap() as u8;
        if d.kind == Kind::Dlmm { d.max_bins = leg["max_bins"].as_u64().unwrap_or(255) as u8; }
        if matches!(d.kind, Kind::RayClmm | Kind::Whirlpool) { d.max_bins = leg["max_bins"].as_u64().unwrap_or(255).clamp(1, 255) as u8; }
        descs.push(d);
        keys.push((b58(leg["program"].as_str().unwrap()), b58(leg["input_mint"].as_str().unwrap())));
    }
    let mut states: Vec<Vec<AcctRef>> = vec![];
    for (d, a) in descs.iter().zip(&accts) {
        let pos = match layout::check_positions(d, a.len()) { Ok(p) => p, Err(e) => return json!({"plan_error": format!("{e:?}")}) };
        states.push(pos.into_iter().map(|i| { let x = &a[i as usize]; AcctRef { key: &x.key, owner: &x.owner, data: &x.data } }).collect());
    }
    let pr = &req["plan"];
    let pairs: Vec<(u8, u8)> = pr["pairs"].as_array().unwrap().iter().map(|p| (p[0].as_u64().unwrap() as u8, p[1].as_u64().unwrap() as u8)).collect();
    let cap = pr["cap"].as_u64().unwrap();
    // the engine's budget rule for legs that ask for it (DESIGN.md §4.3)
    let auto: Vec<bool> = legs.iter().map(|l| l["max_bins"].as_str() == Some("auto")).collect();
    if auto.iter().any(|&a| a) {
        let probe: Vec<LegIn> = descs.iter().zip(&states).zip(&keys).map(|((d, st), (prog, im))| LegIn { desc: *d, program: prog, state: st, input_mint: im }).collect();
        let parsed: Vec<Option<AnyLeg>> = probe.iter().map(|l| AnyLeg::parse(l, &clock, create_program_address).ok().and_then(|p| p.leg.ok())).collect();
        let unbounded = |i: usize| parsed[i].map(|l| match l { AnyLeg::Dlmm(d) => AnyLeg::Dlmm(d.with_budget(arbx_sizing::venue::dlmm::NO_BUDGET)), o => o });
        let sell_in = pairs.first().and_then(|&(b, _)| unbounded(b as usize)).and_then(|l| l.quote(cap).ok()).map(|q| q.out);
        for (i, d) in descs.iter_mut().enumerate() {
            if !auto[i] || d.kind != Kind::Dlmm { continue; }
            let is_buy = pairs.iter().any(|&(b, _)| b as usize == i);
            let x = if is_buy { Some(cap) } else { sell_in };
            let bins = match (unbounded(i), x) { (Some(AnyLeg::Dlmm(l)), Some(x)) => l.bins_for(x), _ => None };
            d.max_bins = bins.map_or(255, |b| b.clamp(1, 255) as u8);
        }
    }
    let ins: Vec<LegIn> = descs.iter().zip(&states).zip(&keys).map(|((d, st), (prog, im))| LegIn { desc: *d, program: prog, state: st, input_mint: im }).collect();
    let p = PlanIn { clock, cap, min_size: pr["min_size"].as_u64().unwrap(), engine_amount: pr["engine_amount"].as_u64().unwrap(),
        min_profit: pr["min_profit"].as_u64().unwrap(), tip: None, flags: SzFlags(pr["flags"].as_u64().unwrap_or(0) as u8),
        max_iters: pr["max_iters"].as_u64().unwrap_or(0) as u8, lamport_offset: pr["lamport_offset"].as_i64().unwrap_or(0),
        legs: &ins, pairs: &pairs, pda: create_program_address };
    let max_bins: Vec<u8> = descs.iter().map(|d| d.max_bins).collect();
    match plan(&p) {
        Err(e) => json!({"plan_error": format!("{e:?}")}),
        Ok(pl) => json!({"plan": {"outcome": format!("{:?}", pl.outcome), "reason": pl.reason, "pair": pl.pair, "amount": pl.amount, "x_star": pl.x_star,
            "modeled_profit": pl.modeled_profit.to_string(), "modeled_profit_e": pl.modeled_profit_e.map(|v| v.to_string()),
            "modeled_y": pl.modeled_y, "modeled_y_e": pl.modeled_y_e, "evals": pl.evals, "bins": pl.bins}, "max_bins": max_bins}),
    }
}

fn main() {
    let mut s = String::new();
    std::io::stdin().read_to_string(&mut s).unwrap();
    let req: Value = serde_json::from_str(&s).expect("request json");
    if req.get("plan").is_some() { println!("{}", plan_mode(&req)); return; }
    let mut out = vec![];
    for leg in req["legs"].as_array().unwrap() {
        let accts = decode_accts(leg);
        let mut amounts: Vec<u64> = leg["amounts"].as_array().unwrap().iter().map(|v| v.as_u64().unwrap()).collect();
        let (parse, quotes) = adapter(&req["clock"], leg, &accts, &mut amounts);
        let quotes: Vec<Value> = amounts.iter().zip(quotes.into_iter().map(Some).chain(std::iter::repeat(None)))
            .map(|(a, q)| match q {
                Some(mut v) => { v["amount"] = json!(a); v }
                None => json!({"amount": a, "ok": false, "out": 0, "spent": 0, "err": parse}),
            }).collect();
        out.push(json!({"id": leg["id"], "parse": parse, "max_bins": leg["max_bins"].as_u64().unwrap_or(255), "quotes": quotes}));
    }
    println!("{}", json!({"legs": out}));
}
