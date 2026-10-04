//! SBF build check for arbx-sizing, shaped like the arbx-exec integration (DESIGN.md §4.5) but standalone:
//!
//! data: mode u8 | reps u8 | n_legs u8 | basket u8 | amount_in u64 | min_profit u64 | quote_balance u64 |
//!       sizing block (arbx_sizing::parse_block) |
//!       per leg: program account index u8, n_state u8, n_state × account index u8, input-mint account index u8
//! accounts: whatever the indexes name (the input-mint account's KEY is the input mint)
//!
//! mode 0 parses the block, builds the borrowed views, runs `plan`, logs the AXZ1 record and returns Ok, or
//! Custom(0x4E58000D) for a DescError (ERR_SIZING_DESC), Custom(0x4E58000E) for STRICT + Fallback.
//! Modes 1-5 repeat one phase `reps` times for per-operation CU (the runner differences two rep counts):
//! 1 parse every leg, 2 exact quote of leg 0 at engine_amount, 3 exact quote of leg 1 at leg 0's output,
//! 4 the locator on pair 0, 5 the whole plan; with a DLMM leg 0: 6 its bare bin walk, 7 the locator's exact pieces
//! over the walk, 8 cap_in and the exact quote at it.
#![cfg_attr(feature = "baseline", allow(unused))]
use arbx_sizing::{AcctRef, Clock, LegIn, Outcome, PlanIn};
use solana_program::account_info::AccountInfo;
use solana_program::entrypoint::ProgramResult;
use solana_program::program_error::ProgramError;
use solana_program::pubkey::Pubkey;

solana_program::entrypoint!(process);

const ERR_SIZING_DESC: u32 = 0x4E58_000D;
const ERR_SIZING_UNSUPPORTED: u32 = 0x4E58_000E;
const MAX_STATE: usize = 8;

fn pda(seeds: &[&[u8]], program: &[u8; 32]) -> Option<[u8; 32]> {
    Pubkey::create_program_address(seeds, &Pubkey::new_from_array(*program)).ok().map(|k| k.to_bytes())
}

fn desc() -> ProgramError { ProgramError::Custom(ERR_SIZING_DESC) }

fn key32<'a>(a: &AccountInfo<'a>) -> &'a [u8; 32] { a.key.as_array() }
fn owner32<'a>(a: &AccountInfo<'a>) -> &'a [u8; 32] { a.owner.as_array() }

fn u64_at(d: &[u8], o: usize) -> Option<u64> { d.get(o..o + 8).and_then(|b| b.try_into().ok()).map(u64::from_le_bytes) }

#[cfg(feature = "baseline")]
pub fn process(_program_id: &Pubkey, accounts: &[AccountInfo], data: &[u8]) -> ProgramResult {
    // the shell's own work without the crate: borrow the accounts, read the clock, log a record
    let c = solana_program::clock::Clock::get_clock()?;
    let mut guards: [Option<core::cell::Ref<&mut [u8]>>; 48] = core::array::from_fn(|_| None);
    for (g, a) in guards.iter_mut().zip(accounts.iter()) { *g = Some(a.data.borrow()); }
    let n = guards.iter().flatten().map(|g| g.len()).sum::<usize>() as u64;
    solana_program::log::sol_log_data(&[&c.slot.to_le_bytes(), &n.to_le_bytes(), data]);
    Ok(())
}

#[cfg(not(feature = "baseline"))]
pub fn process(_program_id: &Pubkey, accounts: &[AccountInfo], data: &[u8]) -> ProgramResult {
    let mode = *data.first().ok_or(desc())?;
    let reps = *data.get(1).ok_or(desc())?;
    let data = data.get(2..).ok_or(desc())?;
    let n_legs = *data.first().ok_or(desc())? as usize;
    let basket = *data.get(1).ok_or(desc())? != 0;
    let amount_in = u64_at(data, 2).ok_or(desc())?;
    let min_profit = u64_at(data, 10).ok_or(desc())?;
    let balance = u64_at(data, 18).ok_or(desc())?;
    let (block, len) = arbx_sizing::parse_block(data, 26, n_legs, basket, amount_in).map_err(|_| desc())?;
    let c = solana_program::clock::Clock::get_clock()?;
    run(accounts, data, 26 + len, &block, Clock { slot: c.slot, unix_timestamp: c.unix_timestamp, epoch: c.epoch }, amount_in.min(balance), min_profit, mode, reps)
}

trait GetClock { fn get_clock() -> Result<solana_program::clock::Clock, ProgramError>; }
impl GetClock for solana_program::clock::Clock {
    fn get_clock() -> Result<solana_program::clock::Clock, ProgramError> {
        use solana_program::sysvar::Sysvar;
        solana_program::clock::Clock::get()
    }
}

#[cfg(not(feature = "baseline"))]
/// Resolve the per-leg views and plan. Its own frame (DESIGN.md §4.8): the view arrays live here.
#[inline(never)]
fn run(accounts: &[AccountInfo], data: &[u8], mut at: usize, block: &arbx_sizing::SizingBlock, clock: Clock, cap: u64, min_profit: u64, mode: u8, reps: u8) -> ProgramResult {
    let n = block.n_legs as usize;
    // borrow every account's data once; the plan ends before anything else could touch them
    let mut guards: [Option<core::cell::Ref<&mut [u8]>>; 48] = core::array::from_fn(|_| None);
    for (g, a) in guards.iter_mut().zip(accounts.iter()) { *g = Some(a.data.borrow()); }
    let empty: [u8; 0] = [];
    let view = |i: usize| -> Result<AcctRef, ProgramError> {
        let a = accounts.get(i).ok_or(desc())?;
        let d: &[u8] = guards.get(i).and_then(|g| g.as_ref()).map(|g| &***g).unwrap_or(&empty);
        Ok(AcctRef { key: key32(a), owner: owner32(a), data: d })
    };
    let zero = [0u8; 32];
    let blank = AcctRef { key: &zero, owner: &zero, data: &empty };
    let mut states: [[AcctRef; MAX_STATE]; 6] = [[blank; MAX_STATE]; 6];
    let mut counts = [0usize; 6];
    let mut progs: [&[u8; 32]; 6] = [&zero; 6];
    let mut inputs: [&[u8; 32]; 6] = [&zero; 6];
    for l in 0..n {
        let prog = *data.get(at).ok_or(desc())? as usize;
        let k = *data.get(at + 1).ok_or(desc())? as usize;
        if k > MAX_STATE { return Err(desc()); }
        for j in 0..k { states[l][j] = view(*data.get(at + 2 + j).ok_or(desc())? as usize)?; }
        counts[l] = k;
        progs[l] = key32(accounts.get(prog).ok_or(desc())?);
        inputs[l] = key32(accounts.get(*data.get(at + 2 + k).ok_or(desc())? as usize).ok_or(desc())?);
        at += 3 + k;
    }
    let legs: [LegIn; 6] = core::array::from_fn(|l| LegIn {
        desc: block.legs[l], program: progs[l], state: &states[l][..counts[l]], input_mint: inputs[l],
    });
    let p = PlanIn {
        clock, cap, min_size: block.min_size as u64, engine_amount: block.engine_amount, min_profit, tip: None, flags: block.flags,
        max_iters: block.max_iters, lamport_offset: block.lamport_offset as i64, legs: &legs[..n], pairs: block.pairs(), pda,
    };
    #[cfg(feature = "bench")]
    if mode != 0 { return bench(&p, mode, reps); }
    let _ = (mode, reps);
    let plan = arbx_sizing::plan(&p).map_err(|_| desc())?;
    let rec = arbx_sizing::axz1_record(&plan, block.n_pairs, block.flags, block.engine_amount, cap);
    solana_program::log::sol_log_data(&[&rec]);
    if plan.outcome == Outcome::Fallback && block.flags.strict() { return Err(ProgramError::Custom(ERR_SIZING_UNSUPPORTED)); }
    Ok(())
}

#[cfg(all(not(feature = "baseline"), feature = "bench"))]
#[inline(never)]
fn bench(p: &PlanIn, mode: u8, reps: u8) -> ProgramResult {
    use core::hint::black_box;
    use arbx_sizing::AnyLeg;
    let parse = |i: usize| AnyLeg::parse(&p.legs[i], &p.clock, p.pda).ok().and_then(|x| x.leg.ok());
    let (l0, l1) = (parse(p.pairs[0].0 as usize).ok_or(desc())?, parse(p.pairs[0].1 as usize).ok_or(desc())?);
    let y = l0.quote(p.engine_amount).map(|q| q.out).unwrap_or(1);
    for _ in 0..reps {
        match mode {
            1 => { for l in p.legs { black_box(AnyLeg::parse(black_box(l), &p.clock, p.pda).map(|x| x.leg.is_ok()).ok()); } }
            2 => { black_box(black_box(&l0).quote(black_box(p.engine_amount)).ok()); }
            3 => { black_box(black_box(&l1).quote(black_box(y)).ok()); }
            4 => {
                let (m0, m1) = (l0.model().map_err(|_| desc())?, l1.model().map_err(|_| desc())?);
                black_box(arbx_sizing::opt::locate(black_box(&m0), black_box(&m1), arbx_sizing::Fx::from_u64(p.cap)).count());
            }
            // DLMM leg 0 only: 6 the bare bin walk, 7 the locator's exact pieces, 8 the exact quote of its whole walk
            9 => {
                let arbx_sizing::AnyLeg::Dlmm(d) = l0 else { return Err(desc()) };
                let m = arbx_sizing::opt::LegModel::Bins(&d);
                let mut st = arbx_sizing::opt::Stream::new(black_box(&m));
                while !matches!(black_box(st.next()), arbx_sizing::opt::Piece::End) {}
            }
            6 | 7 | 8 => {
                let arbx_sizing::AnyLeg::Dlmm(d) = l0 else { return Err(desc()) };
                match mode {
                    6 => { let mut w = d.walker(); let mut n = 0u32; while w.next().is_ok() { n += 1; } black_box(n); }
                    7 => {
                        let mut c = d.start();
                        let mut memo = arbx_sizing::venue::dlmm::RateMemo::default();
                        while let Ok((bp, true)) = d.advance(black_box(&mut c), &mut memo, None) { black_box(bp.drain_in); }
                        black_box(c.used);
                    }
                    _ => { let _ = black_box(d.quote(black_box(d.cap_in().unwrap_or(1)))); }
                }
            }
            _ => { black_box(arbx_sizing::plan(black_box(p)).map(|x| x.amount).ok()); }
        }
    }
    Ok(())
}
