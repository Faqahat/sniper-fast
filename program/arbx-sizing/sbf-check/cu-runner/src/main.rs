//! CU of arbx-sizing on SBF (LiteSVM 0.17): the sbf-check program run on real mainnet HOTBOT accounts and on
//! synthetic pools, minus the same instruction on the baseline build (same entrypoint, account borrows and log),
//! then each phase alone (parse, one exact quote, the locator, the whole plan) as (CU at 11 reps − CU at 1) / 10.
//! Usage: cargo run --release -- <dir with full.so and baseline.so> (see ../README.txt).
#[path = "../../../tests/common/mod.rs"]
#[allow(dead_code)]
mod common;
use arbx_sizing::desc::{encode_block, SizingBlock, MAX_PAIRS, MAX_SIZED_LEGS};
use arbx_sizing::{Kind, LegDesc, SzFlags};
use common::*;
use litesvm::LiteSVM;
use solana_address::Address;
use solana_instruction::{AccountMeta, Instruction};
use solana_keypair::Keypair;
use solana_message::Message;
use solana_signer::Signer;
use solana_transaction::Transaction;

struct Svm { svm: LiteSVM, full: Address, base: Address, payer: Keypair }

fn addr(k: &Pk) -> Address { Address::new_from_array(*k) }

impl Svm {
    fn new(full: &str, base: &str) -> Self {
        let mut svm = LiteSVM::new().with_builtins();
        let (f, b) = (Address::new_unique(), Address::new_unique());
        svm.add_program_from_file(f, full).unwrap();
        svm.add_program_from_file(b, base).unwrap();
        let payer = Keypair::new();
        svm.airdrop(&payer.pubkey(), 100_000_000_000).unwrap();
        let mut clock: solana_clock::Clock = svm.get_sysvar();
        clock.slot = CLOCK.slot; clock.unix_timestamp = CLOCK.unix_timestamp; clock.epoch = CLOCK.epoch;
        svm.set_sysvar(&clock);
        Svm { svm, full: f, base: b, payer }
    }
    fn set_clock(&mut self, slot: u64, ts: i64) {
        let mut clock: solana_clock::Clock = self.svm.get_sysvar();
        clock.slot = slot; clock.unix_timestamp = ts;
        self.svm.set_sysvar(&clock);
    }
    /// (cu, logs)
    fn run(&mut self, program: Address, accts: &[Acct], data: &[u8]) -> (u64, Vec<String>) {
        for a in accts {
            let lam = 1_000_000_000 + a.data.len() as u64 * 10_000;
            self.svm.set_account(addr(&a.key), solana_account::Account { lamports: lam, data: a.data.clone(), owner: addr(&a.owner), executable: false, rent_epoch: 0 }).unwrap();
        }
        let metas = accts.iter().map(|a| AccountMeta::new_readonly(addr(&a.key), false)).collect();
        let cb = Instruction { program_id: Address::from_str_const("ComputeBudget111111111111111111111111111111"), accounts: vec![], data: { let mut v = vec![2u8]; v.extend_from_slice(&1_400_000u32.to_le_bytes()); v } };
        let ix = Instruction { program_id: program, accounts: metas, data: data.to_vec() };
        self.svm.expire_blockhash();
        let tx = Transaction::new(&[&self.payer], Message::new(&[cb, ix], Some(&self.payer.pubkey())), self.svm.latest_blockhash());
        let r = match self.svm.send_transaction(tx) { Ok(r) => r.logs, Err(e) => { if e.meta.logs.is_empty() { eprintln!("tx error: {:?}", e.err); } e.meta.logs } };
        let tag = format!("Program {program} consumed ");
        let cu = r.iter().find_map(|l| l.strip_prefix(&tag).and_then(|s| s.split(' ').next()).and_then(|n| n.parse().ok())).unwrap_or(0);
        (cu, r)
    }
}

/// The sbf-check instruction for these legs: accounts deduplicated, venue program accounts appended
fn instruction(legs: &[OwnedLeg], pairs: &[(u8, u8)], basket: bool, amount_in: u64, e: u64, flags: u8) -> (Vec<Acct>, Vec<u8>) {
    let mut accts: Vec<Acct> = vec![];
    let idx = |a: &Acct, accts: &mut Vec<Acct>| -> u8 {
        if let Some(i) = accts.iter().position(|x| x.key == a.key) { return i as u8; }
        accts.push(a.clone());
        (accts.len() - 1) as u8
    };
    let mut leg_bytes = vec![];
    let mut descs = [LegDesc::placeholder(); MAX_SIZED_LEGS];
    for (i, l) in legs.iter().enumerate() {
        descs[i] = l.desc;
        let prog = Acct { key: *l.desc.kind.program(), owner: [0u8; 32], data: vec![] };
        leg_bytes.push(idx(&prog, &mut accts));
        leg_bytes.push(l.state.len() as u8);
        for a in &l.state { let k = idx(a, &mut accts); leg_bytes.push(k); }
        let mint_ix = match accts.iter().position(|x| x.key == l.input_mint) { Some(i) => i as u8, None => idx(&Acct { key: l.input_mint, owner: [0u8; 32], data: vec![] }, &mut accts) };
        leg_bytes.push(mint_ix);
    }
    let mut p = [(0u8, 0u8); MAX_PAIRS];
    for (s, q) in p.iter_mut().zip(pairs) { *s = *q; }
    let block = SizingBlock { flags: SzFlags(flags), min_size: 1_000, engine_amount: e, lamport_offset: 0, max_iters: if flags & SzFlags::SEARCH != 0 { 24 } else { 0 }, pairs: p,
        n_pairs: pairs.len() as u8, legs: descs, n_legs: legs.len() as u8, basket };
    let mut data = vec![0u8, 0u8, legs.len() as u8, basket as u8];
    data.extend(amount_in.to_le_bytes());
    data.extend(1u64.to_le_bytes());
    data.extend(u64::MAX.to_le_bytes());
    encode_block(&block, &mut data);
    data.extend(leg_bytes);
    (accts, data)
}

fn axz1(logs: &[String]) -> Option<String> {
    use base64::Engine;
    let l = logs.iter().find(|l| l.starts_with("Program data: "))?;
    let b = base64::engine::general_purpose::STANDARD.decode(l.trim_start_matches("Program data: ").trim()).ok()?;
    if &b[..4] != b"AXZ1" { return None; }
    let u = |o: usize| u64::from_le_bytes(b[o..o + 8].try_into().unwrap());
    let i = |o: usize| i64::from_le_bytes(b[o..o + 8].try_into().unwrap());
    Some(format!("outcome {} pair {} reason {} evals {} bins {} | x {} e {} x* {} profit_x {} profit_e {}",
        b[4], b[5], u16::from_le_bytes([b[8], b[9]]), b[10], b[11], u(12), u(20), u(28), i(60), if i(68) == i64::MIN { "-".into() } else { i(68).to_string() }))
}

/// The engine's walk budget per DLMM leg (DESIGN.md §4.3): the bins with liquidity its exact swap needs at the cap
/// (a sell leg at the first pair's buy-leg output at the cap), 1..=255; 255 when the cap is past the passed arrays.
fn engine_budgets(legs: &mut [OwnedLeg], pairs: &[(u8, u8)], cap: u64) {
    use arbx_sizing::venue::dlmm::NO_BUDGET;
    use arbx_sizing::AnyLeg;
    let unbounded = |l: &OwnedLeg, refs: &[arbx_sizing::AcctRef], x: u64| -> (Option<u64>, Option<u16>) {
        let li = arbx_sizing::LegIn { desc: l.desc, program: l.desc.kind.program(), state: refs, input_mint: &l.input_mint };
        match arbx_sizing::AnyLeg::parse(&li, &CLOCK, pda).ok().and_then(|p| p.leg.ok()) {
            Some(AnyLeg::Dlmm(d)) => { let d = d.with_budget(NO_BUDGET); (d.quote(x).ok().map(|q| q.out), d.bins_for(x)) }
            Some(o) => (o.quote(x).ok().map(|q| q.out), None),
            None => (None, None),
        }
    };
    let budgets: Vec<Option<u8>> = {
        let v = views(legs);
        let buy0 = pairs[0].0 as usize;
        let y = unbounded(&legs[buy0], &v.refs[buy0], cap).0;
        legs.iter().enumerate().map(|(i, l)| {
            if l.desc.kind != Kind::Dlmm { return None; }
            let x = if pairs.iter().any(|p| p.0 as usize == i) { Some(cap) } else { y };
            Some(x.and_then(|x| unbounded(l, &v.refs[i], x).1).map_or(255, |b| b.clamp(1, 255) as u8))
        }).collect()
    };
    for (l, b) in legs.iter_mut().zip(budgets) { if let Some(b) = b { l.desc.max_bins = b; } }
}

/// The tighter engine rule (DESIGN.md §4.3): plan off chain with the cap-sized budgets, then give each DLMM leg the
/// bins its exact swap reads at max(e, 1.25·x̂) of every pair using it (+2), so the bound covers e and the optimum
/// with room for the state to move, not the whole cap.
fn engine_budgets_tight(legs: &mut [OwnedLeg], pairs: &[(u8, u8)], cap: u64, e: u64) {
    use arbx_sizing::venue::dlmm::NO_BUDGET;
    use arbx_sizing::{AnyLeg, PlanIn, SzFlags};
    engine_budgets(legs, pairs, cap);
    let mut target = vec![0u64; legs.len()];
    {
        let v = views(legs);
        let ins = leg_ins(legs, &v);
        let parsed: Vec<Option<AnyLeg>> = ins.iter().map(|l| AnyLeg::parse(l, &CLOCK, pda).ok().and_then(|p| p.leg.ok())
            .map(|l| match l { AnyLeg::Dlmm(d) => AnyLeg::Dlmm(d.with_budget(NO_BUDGET)), o => o })).collect();
        for &(b, sl) in pairs {
            let one = [(b, sl)];
            let p = PlanIn { clock: CLOCK, cap, min_size: 1_000, engine_amount: e, min_profit: 1, tip: None, flags: SzFlags(0), max_iters: 0,
                lamport_offset: 0, legs: &ins, pairs: &one, pda };
            let xh = arbx_sizing::plan(&p).map(|r| r.amount).unwrap_or(e);
            let x = e.max(xh.saturating_add(xh / 4)).min(cap);
            let y = parsed[b as usize].and_then(|l| l.quote(x).ok()).map_or(0, |q| q.out);
            target[b as usize] = target[b as usize].max(x);
            target[sl as usize] = target[sl as usize].max(y);
        }
        for (i, l) in parsed.iter().enumerate() {
            if let Some(AnyLeg::Dlmm(d)) = l {
                let bins = d.bins_for(target[i]).map_or(255, |b| (b as u32 + 2).clamp(1, 255) as u8);
                target[i] = bins as u64;
            }
        }
    }
    for (i, l) in legs.iter_mut().enumerate() { if l.desc.kind == Kind::Dlmm { l.desc.max_bins = target[i] as u8; } }
}

fn measure(s: &mut Svm, name: &str, legs: &[OwnedLeg], pairs: &[(u8, u8)], amount_in: u64, e: u64, flags: u8) -> u64 {
    measure_with(s, name, legs, pairs, amount_in, e, flags, u8::MAX)
}

/// `max_cap`: the engine also caps each DLMM leg's budget (to fit its CU limit: DESIGN.md §4.7)
fn measure_with(s: &mut Svm, name: &str, legs: &[OwnedLeg], pairs: &[(u8, u8)], amount_in: u64, e: u64, flags: u8, max_cap: u8) -> u64 {
    let mut legs = legs.to_vec();
    if TIGHT.with(|t| *t.borrow()) { engine_budgets_tight(&mut legs, pairs, amount_in, e); } else { engine_budgets(&mut legs, pairs, amount_in); }
    for l in legs.iter_mut() { if l.desc.kind == Kind::Dlmm { l.desc.max_bins = l.desc.max_bins.min(max_cap); } }
    let budgets: Vec<u8> = legs.iter().filter(|l| l.desc.kind == Kind::Dlmm).map(|l| l.desc.max_bins).collect();
    let (accts, mut data) = instruction(&legs, pairs, pairs.len() > 1, amount_in, e, flags);
    let (full, logs) = s.run(s.full, &accts, &data);
    let (base, _) = s.run(s.base, &accts, &data);
    let rec = axz1(&logs).unwrap_or_else(|| format!("NO RECORD: {:?}", logs.iter().rev().take(4).collect::<Vec<_>>()));
    // the static bound (arbx_sizing::cu_bound) of the very block sent
    let (block, _) = arbx_sizing::parse_block(&data[2..], 26, legs.len(), pairs.len() > 1, amount_in).expect("block");
    let bound = arbx_sizing::cu_bound(&block);
    let sizing = full.saturating_sub(base);
    println!("{name:<58} {sizing:>7} CU sizing, bound {bound:>8} (full {full}, baseline {base}; {} accounts, {} B data; DLMM max_bins {budgets:?}) {rec}", accts.len(), data.len());
    if sizing > bound { BOUND_FAILS.with(|f| f.borrow_mut().push(format!("{name}: {sizing} > bound {bound}"))); }
    // per-phase costs: (CU at 1 + k reps − CU at 1 rep) / k, k = 10 (or 2 when 11 reps would pass the CU limit)
    let mut per = vec![];
    let k: u8 = if full > 100_000 { 2 } else { 10 };
    for (mode, label) in [(1u8, "parse all legs"), (2, "exact leg0@e"), (3, "exact leg1"), (4, "locate"), (5, "plan")] {
        data[0] = mode;
        data[1] = 1;
        let (a, _) = s.run(s.full, &accts, &data);
        data[1] = 1 + k;
        let (b, _) = s.run(s.full, &accts, &data);
        per.push(format!("{label} {}", (b.saturating_sub(a)) / k as u64));
    }
    data[0] = 0;
    println!("{:<58}   per op: {}", "", per.join(", "));
    full.saturating_sub(base)
}

const A: Pk = arbx_sizing::layout::WSOL;

thread_local! {
    static BOUND_FAILS: std::cell::RefCell<Vec<String>> = std::cell::RefCell::new(vec![]);
    /// budgets by the tight engine rule (second pass) instead of the bins at the cap
    static TIGHT: std::cell::RefCell<bool> = std::cell::RefCell::new(false);
}

fn cp_leg(rng: &mut Rng, amm: bool, buy: bool, ra: u64, rx: u64, x: Pk, fee: u64) -> OwnedLeg {
    if amm {
        let st = ammv4(rng, rx, ra, fee, 10_000, x, A);
        OwnedLeg::new(Kind::RayAmmV4, !buy, st, if buy { A } else { x })
    } else {
        let spec = CpmmSpec { r0: ra, r1: rx, trade: fee * 100, creator: 0, enable_creator: false, creator_on: 0, owed0: 0, owed1: 0 };
        let st = cpmm(rng, &spec, A, x, buy);
        OwnedLeg::new(Kind::RayCpmm, buy, st, if buy { A } else { x })
    }
}

fn dlmm_pair(rng: &mut Rng, x: Pk, bin_step: u16, active: i32, depth: u64, vfc: u32) -> (Acct, Acct, Acct, Vec<Acct>) {
    let mut spec = DlmmSpec { bin_step, active, idx_ref: active - 3, last_ts: CLOCK.unix_timestamp - 10, vfc, max_va: 150_000, v_ref: 10_000, base_factor: 20_000, bins: vec![], ..Default::default() };
    for id in active - 180..=active + 180 {
        let price = dlmm_price(bin_step, id) as f64 / 18446744073709551616.0;
        let ay = depth;
        let ax = (ay as f64 / price) as u64;
        let (bx, by) = if id < active { (0, ay) } else if id > active { (ax, 0) } else { (ax / 2, ay / 2) };
        spec.bins.push((id, bx, by, (0, 0, 0)));
    }
    dlmm(rng, &spec, x, A)
}
fn dlmm_leg(p: &(Acct, Acct, Acct, Vec<Acct>), buy: bool) -> OwnedLeg {
    let st = dlmm_state(&p.0, &p.1, &p.2, &p.3, !buy);
    OwnedLeg::new(Kind::Dlmm, !buy, st, if buy { A } else { p.1.key })
}

fn main() {
    let dir = std::env::args().nth(1).expect("deploy dir with full.so and baseline.so");
    // pass 1: budgets = the bins at the cap; pass 2 (TIGHT=1): the tight rule
    if std::env::var("TIGHT").is_ok_and(|v| v == "1") { TIGHT.with(|t| *t.borrow_mut() = true); println!("== budgets: the tight engine rule (bins at max(e, 1.25·x̂) + 2) =="); }
    else { println!("== budgets: the bins at the cap =="); }
    let mut s = Svm::new(&format!("{dir}/full.so"), &format!("{dir}/baseline.so"));
    let mut rng = Rng(7);
    let x: Pk = rng.key();
    let mut table = vec![];

    // CPMM-family ↔ CPMM-family (closed form)
    let (ra, rx) = (200_000_000_000u64, 40_000_000_000_000u64);
    let legs = vec![cp_leg(&mut rng, false, true, ra, rx, x, 25), cp_leg(&mut rng, true, false, ra, rx * 96 / 100, x, 25)];
    table.push(("CPMM → AMM v4", measure(&mut s, "CPMM → AMM v4 (closed form)", &legs, &[(0, 1)], 50_000_000_000, 100_000_000, 0)));

    // PumpSwap buy → CPMM (PumpSwap canonical PDA syscall + fee tiers)
    let p = pump(&mut rng, &PumpSpec { base: 70_000_000_000_000, quote: 300_000_000_000, ..Default::default() });
    let xk = p.base_key();
    let legs = vec![OwnedLeg::pump(&p, false), cp_leg(&mut rng, false, false, 330_000_000_000, 70_000_000_000_000, xk, 25)];
    table.push(("PumpSwap → CPMM", measure(&mut s, "PumpSwap buy → CPMM (closed form)", &legs, &[(0, 1)], 50_000_000_000, 100_000_000, 0)));

    // DLMM ↔ CPMM with k bins touched at the optimum
    for (depth, label) in [(2_000_000_000u64, "deep bins"), (200_000_000, "~3-5 bins"), (40_000_000, "many bins")] {
        let pair = dlmm_pair(&mut rng, x, 100, 0, depth, 7_500);
        let legs = vec![dlmm_leg(&pair, true), cp_leg(&mut rng, false, false, 100_000_000_000, 100_000_000_000 * 100 / 104, x, 25)];
        table.push(("DLMM → CPMM", measure(&mut s, &format!("DLMM buy → CPMM sell ({label})"), &legs, &[(0, 1)], 50_000_000_000, 100_000_000, 0)));
    }
    // DLMM ↔ DLMM
    let p1 = dlmm_pair(&mut rng, x, 100, -4, 300_000_000, 7_500);
    let p2 = dlmm_pair(&mut rng, x, 100, 0, 300_000_000, 7_500);
    let legs = vec![dlmm_leg(&p1, true), dlmm_leg(&p2, false)];
    table.push(("DLMM → DLMM", measure(&mut s, "DLMM → DLMM (4-bin gap)", &legs, &[(0, 1)], 50_000_000_000, 100_000_000, 0)));

    // real HOTBOT: GLL3 (PumpSwap) → 6D4E (DLMM), at the real state and with GLL3's quote vault 10% lower
    let m = Mainnet::load_from(concat!(env!("CARGO_MANIFEST_DIR"), "/../../tests/data/mainnet-accounts.json"));
    s.set_clock(m.clock().slot, m.clock().unix_timestamp);
    let gll3 = "GLL3CzybpSCLZdoACf8QUM5YrKVwyA65kQ2RcTsJxxzV";
    let st = m.state(gll3);
    let hotbot = st[2].key;
    let mut buy = OwnedLeg::new(Kind::PumpBuy, false, st, A);
    buy.desc.pump_bump = m.pool(gll3)["bump"].as_u64().unwrap() as u8;
    let d6 = "6D4EWF22HfQamimKhX47tqiu9DVCkcxDMrmhnSvewKAo";
    let st6 = m.state(d6);
    let mut arrs: Vec<(i64, String)> = m.pool(d6)["arrays"].as_object().unwrap().iter().map(|(k, v)| (k.parse().unwrap(), v.as_str().unwrap().to_string())).collect();
    arrs.retain(|(i, _)| *i <= -8);
    arrs.sort_by_key(|(i, _)| -i);
    let mut s6 = st6[..3].to_vec();
    s6.extend(arrs.iter().map(|(_, k)| m.acct(k)));
    let sell6 = OwnedLeg::new(Kind::Dlmm, true, s6, hotbot);
    table.push(("PumpSwap → DLMM (real, no gap)", measure(&mut s, "HOTBOT GLL3 → 6D4E, real state", &[buy.clone(), sell6.clone()], &[(0, 1)], 50_000_000_000, 100_000_000, 0)));
    let mut gap = buy.clone();
    let q = u64::from_le_bytes(gap.state[5].data[64..72].try_into().unwrap());
    put_u64(&mut gap.state[5].data, 64, q / 100 * 88);
    table.push(("PumpSwap → DLMM (real, 12% gap)", measure(&mut s, "HOTBOT GLL3 → 6D4E, GLL3 quote vault −12%", &[gap.clone(), sell6.clone()], &[(0, 1)], 50_000_000_000, 100_000_000, 0)));
    table.push(("same, SHADOW", measure(&mut s, "HOTBOT GLL3 → 6D4E, −12%, SHADOW", &[gap.clone(), sell6.clone()], &[(0, 1)], 50_000_000_000, 100_000_000, SzFlags::SHADOW)));

    // DAMM v2 (a vector pool) ↔ CPMM
    let v: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/../../../../testdata/dammv2-vectors.json")).unwrap()).unwrap();
    s.set_clock(452_967_433, 1_791_039_568);
    for (name, pv) in v["pools"].as_object().unwrap().iter().take(3) {
        let raw = b64(pv["b64"].as_str().unwrap());
        let pool = arbx_sizing::venue::dammv2::decode(&raw).unwrap();
        let (ma, mb) = (*arbx_sizing::math::key_at(&raw, 168).unwrap(), *arbx_sizing::math::key_at(&raw, 200).unwrap());
        let pab = (pool.sqrt_price as f64 / 18446744073709551616.0).powi(2);
        // DAMM buys a with b; a CPMM sells a for b 4% dearer
        let rb = 1u64 << 40;
        let ra_ = ((rb as f64) / (pab * 1.04)).clamp(1000.0, 1.8e19) as u64;
        let spec = CpmmSpec { r0: rb, r1: ra_, trade: 2_500, creator: 0, enable_creator: false, creator_on: 0, owed0: 0, owed1: 0 };
        let cp = OwnedLeg::new(Kind::RayCpmm, false, cpmm(&mut rng, &spec, mb, ma, false), ma);
        let dl = OwnedLeg::new(Kind::DammV2, false, vec![Acct { key: rng.key(), owner: arbx_sizing::layout::DAMM_V2, data: raw.clone() }, mint(ma, 0, false, None), mint(mb, 0, false, None)], mb);
        table.push(("DAMM v2 → CPMM", measure(&mut s, &format!("DAMM v2 {}… (b→a) → CPMM", &name[..6]), &[dl, cp], &[(0, 1)], 1 << 40, 1_000_000, 0)));
    }
    s.set_clock(CLOCK.slot, CLOCK.unix_timestamp);

    // 3-pair DLMM basket over 4 legs, DESIGN.md §4.4 shape: (0,1) (0,2) (3,1)
    let pa = dlmm_pair(&mut rng, x, 100, -4, 300_000_000, 7_500); // cheap pair: buy here
    let pb = dlmm_pair(&mut rng, x, 100, 0, 300_000_000, 7_500);
    let pc = dlmm_pair(&mut rng, x, 200, 0, 300_000_000, 7_500);
    let legs = vec![dlmm_leg(&pa, true), dlmm_leg(&pb, false), dlmm_leg(&pc, false), dlmm_leg(&pc, true)];
    table.push(("3-pair DLMM basket", measure(&mut s, "BASKET 3 pairs, 4 DLMM legs (5 arrays each)", &legs, &[(0, 1), (0, 2), (3, 1)], 50_000_000_000, 100_000_000, 0)));
    // the same with the PumpSwap buy leg (HOTBOT shape): GLL3-like pump + 3 DLMM legs
    let p = pump(&mut rng, &PumpSpec { base: 70_000_000_000_000, quote: 270_000_000_000, ..Default::default() });
    let xk = p.base_key();
    let pb = dlmm_pair(&mut rng, xk, 100, -530, 300_000_000, 7_500);
    let pc = dlmm_pair(&mut rng, xk, 200, -266, 300_000_000, 7_500);
    let legs = vec![OwnedLeg::pump(&p, false), dlmm_leg(&pb, false), dlmm_leg(&pc, false), dlmm_leg(&pc, true)];
    table.push(("3-pair PumpSwap/DLMM basket", measure(&mut s, "BASKET 3 pairs: PumpSwap buy + 3 DLMM legs", &legs, &[(0, 1), (0, 2), (3, 1)], 50_000_000_000, 100_000_000, 0)));
    // per-bin costs of the DLMM walk (modes 6-8 on leg 0): CU(2 reps) − CU(1 rep), over the bins walked
    for (bin_step, label) in [(1u16, "bs 1"), (100, "bs 100")] {
        let pair = dlmm_pair_ref(&mut rng, x, bin_step, 0, 40_000_000, -20);
        let mut leg = dlmm_leg(&pair, true);
        leg.desc.max_bins = 200;
        let cp = cp_leg(&mut rng, false, false, 400_000_000_000, 400_000_000_000, x, 25);
        let legs = vec![leg, cp];
        let bins = { let v = views(&legs); let l = any_leg(&legs[0], &v.refs[0]); let arbx_sizing::AnyLeg::Dlmm(d) = l else { panic!() }; let mut w = d.walker(); let mut n = 0; while w.next().is_ok() { n += 1; } n };
        let (accts, mut data) = instruction(&legs, &[(0, 1)], false, 50_000_000_000, 100_000_000, 0);
        let mut per = vec![];
        for (mode, what) in [(6u8, "walk"), (7, "exact pieces"), (9, "locator pieces"), (8, "cap_in + exact quote")] {
            data[0] = mode;
            data[1] = 1;
            let (a, _) = s.run(s.full, &accts, &data);
            data[1] = 2;
            let (b, _) = s.run(s.full, &accts, &data);
            per.push(format!("{what} {:.0}", b.saturating_sub(a) as f64 / bins as f64));
        }
        println!("{:<58} per bin with liquidity ({bins} bins): {}", format!("DLMM walk costs, {label}"), per.join(", "));
    }
    // REVIEW.md F4 worst cases: shallow bin-step-1/5/25 DLMM legs against a CPMM 3-5% away (the optimum is dozens to
    // hundreds of bins out), with the fee rising (idx_ref behind) or falling (ahead) along the walk
    for (bin_step, gap, label) in [(1u16, 1.03f64, "DLMM(bs 1, 3% gap) → CPMM"), (5, 1.03, "DLMM(bs 5, 3% gap) → CPMM"), (25, 1.05, "DLMM(bs 25, 5% gap) → CPMM")] {
        for (idx_ref, how) in [(-20, "fee rising"), (20, "fee falling")] {
            let pair = dlmm_pair_ref(&mut rng, x, bin_step, 0, 40_000_000, idx_ref);
            let p0 = dlmm_price(bin_step, 0) as f64 / 18446744073709551616.0;
            let ra = 400_000_000_000u64;
            let legs = vec![dlmm_leg(&pair, true), cp_leg(&mut rng, false, false, ra, (ra as f64 / (p0 * gap)) as u64, x, 25)];
            table.push((label, measure(&mut s, &format!("{label}, {how}"), &legs, &[(0, 1)], 200_000_000_000, 100_000_000, 0)));
        }
    }
    // the reversion arb of F6: DLMM bin step 100, shallow bins, idx_ref ahead of the walk (the fee falls), CPMM sell
    let pair = dlmm_pair_ref(&mut rng, x, 100, 0, 20_000_000, 20);
    let ra = 40_000_000_000_000u64;
    let legs = vec![dlmm_leg(&pair, true), cp_leg(&mut rng, false, false, ra, (ra as f64 / 1.06) as u64, x, 25)];
    table.push(("DLMM reversion arb (F6)", measure(&mut s, "DLMM(bs 100) buy toward idx_ref → CPMM (F6)", &legs, &[(0, 1)], 200_000_000_000, 100_000_000, 0)));
    // the 3-pair basket of bin-step-1 legs with a 3% gap (REVIEW.md F4: 456,626 CU before)
    let pa = dlmm_pair_ref(&mut rng, x, 1, -300, 40_000_000, 0);
    let pb = dlmm_pair_ref(&mut rng, x, 1, 0, 40_000_000, 0);
    let pc = dlmm_pair_ref(&mut rng, x, 1, 0, 40_000_000, 0);
    let legs = vec![dlmm_leg(&pa, true), dlmm_leg(&pb, false), dlmm_leg(&pc, false), dlmm_leg(&pc, true)];
    table.push(("3-pair bin-step-1 basket", measure(&mut s, "BASKET 3 pairs, 4 bin-step-1 DLMM legs, 3% gap", &legs, &[(0, 1), (0, 2), (3, 1)], 200_000_000_000, 100_000_000, 0)));
    // the same with the budgets the engine can afford: 4 legs of at most 48 bins keep sizing + the chosen pair's two
    // DLMM CPIs (47k + 5.45k per bin each) inside 1.4M
    table.push(("3-pair bin-step-1 basket, 48-bin budgets", measure_with(&mut s, "BASKET 3 pairs, 4 bin-step-1 DLMM legs, 3% gap, max_bins 48", &legs, &[(0, 1), (0, 2), (3, 1)], 200_000_000_000, 100_000_000, 0, 48)));
    println!("\nsummary:");
    for (k, v) in &table { println!("  {k:<34} {v:>7}"); }
    // CI regression (DESIGN.md §6.4): every route within the static bound of its block (arbx_sizing::cu_bound),
    // every mix within its measured budget + 10%, and the few-bin 3-pair DLMM basket within the 60k design target
    let budget = |k: &str| -> u64 {
        match k {
            "3-pair DLMM basket" => 60_000,
            "CPMM → AMM v4" | "PumpSwap → CPMM" | "DAMM v2 → CPMM" => 20_000,
            "DLMM → CPMM" | "DLMM → DLMM" | "PumpSwap → DLMM (real, no gap)" | "PumpSwap → DLMM (real, 12% gap)" | "same, SHADOW" | "DLMM reversion arb (F6)" => 32_000,
            "DLMM(bs 25, 5% gap) → CPMM" => 60_000,
            "DLMM(bs 5, 3% gap) → CPMM" => 110_000,
            "3-pair PumpSwap/DLMM basket" => 140_000,
            "DLMM(bs 1, 3% gap) → CPMM" => 210_000,
            "3-pair bin-step-1 basket, 48-bin budgets" => 420_000,
            _ => 1_400_000,
        }
    };
    let mut over: Vec<String> = table.iter().filter(|(k, v)| *v > budget(k) + budget(k) / 10).map(|(k, v)| format!("{k}: {v} > {}", budget(k))).collect();
    BOUND_FAILS.with(|f| over.extend(f.borrow().iter().cloned()));
    if !over.is_empty() { eprintln!("CU REGRESSION: {over:?}"); std::process::exit(1); }
    println!("CU regression check: every route within its static bound and its measured budget");
}

fn dlmm_pair_ref(rng: &mut Rng, x: Pk, bin_step: u16, active: i32, depth: u64, idx_ref_off: i32) -> (Acct, Acct, Acct, Vec<Acct>) {
    let mut spec = DlmmSpec { bin_step, active, idx_ref: active + idx_ref_off, last_ts: CLOCK.unix_timestamp - 10, vfc: 7_500, max_va: 150_000, v_ref: 0, base_factor: 20_000, bins: vec![], ..Default::default() };
    for id in active - 340..=active + 340 {
        let price = dlmm_price(bin_step, id) as f64 / 18446744073709551616.0;
        let ay = depth;
        let ax = (ay as f64 / price) as u64;
        let (bx, by) = if id < active { (0, ay) } else if id > active { (ax, 0) } else { (ax / 2, ay / 2) };
        spec.bins.push((id, bx, by, (0, 0, 0)));
    }
    dlmm(rng, &spec, x, A)
}
