//! TEST-ONLY mock venue. Never deploy it. It is a constant-product AMM (fee 25 bps) with native-SOL pools and some
//! hostile operations. arbx-exec's LiteSVM tests (tests/litesvm.rs) load this .so at several allowlisted venue
//! addresses, to stand in for an honest venue or a malicious upgrade of one, and at one unlisted address.
//!
//! data (32 bytes): [0] op  [1] bump of the ["auth"] PDA  [8..16] amount_in (patched by arbx-exec)
//!                  [16..24] min_out  [24..32] arg (op-specific)
//! The ["auth"] PDA (of the address the program is loaded at) is the token owner of every vault.
//!
//! ops and accounts:
//!   0 SWAP                token -> token
//!       0 user (s)  1 user src (w)  2 user dst (w)  3 vault in (w)  4 vault out (w)  5 auth PDA  6 token program
//!       7.. ignored (so a test can give a leg 64+ accounts)
//!   1 BUY_NATIVE          lamports -> token. The user pays by System transfer into the pool account, which this
//!                         program owns (data = the virtual SOL reserve, u64).
//!       0 user (s,w)  1 pool (w)  2 user dst (w)  3 vault out (w)  4 auth PDA  5 token program  6 system program
//!   2 SELL_NATIVE         token -> lamports. The pool account pays the user lamports directly.
//!       0 user (s,w)  1 pool (w)  2 user src (w)  3 vault in (w)  4 token program
//!   3 SWAP_STEAL_LAMPORTS SWAP, then a System transfer of `arg` lamports from the user to accounts[7]
//!       (accounts[8] = system program)
//!   4 NOTHING             does nothing: a leg that delivers nothing
//!   5 SWAP_DRAIN_TOKENS   SWAP, then a token transfer of `arg` from accounts[7] (a user token account) to accounts[8]
//!   6 SWAP_ASSIGN_USER    SWAP, then a System assign of the user to this program (accounts[7] = system program)
//!   7 SWAP_SKIM           SWAP, but delivers only `arg` basis points of the fair output (a venue that under-delivers)
use solana_program::{
    account_info::AccountInfo,
    entrypoint::ProgramResult,
    instruction::{AccountMeta, Instruction},
    program::{invoke, invoke_signed},
    program_error::ProgramError,
    pubkey::Pubkey,
};

solana_program::entrypoint!(process);

const SYSTEM_PROGRAM: Pubkey = Pubkey::from_str_const("11111111111111111111111111111111");

fn u64_at(d: &[u8], o: usize) -> u64 {
    let mut b = [0u8; 8];
    b.copy_from_slice(&d[o..o + 8]);
    u64::from_le_bytes(b)
}

fn token_amount(ai: &AccountInfo) -> Result<u64, ProgramError> {
    let d = ai.try_borrow_data()?;
    if d.len() < 72 { return Err(ProgramError::InvalidAccountData); }
    Ok(u64_at(&d, 64))
}

/// constant product, 25 bps fee on the input
fn quote_out(amount_in: u64, reserve_in: u64, reserve_out: u64) -> u64 {
    let in_net = amount_in as u128 * 9_975 / 10_000;
    (reserve_out as u128 * in_net / (reserve_in as u128 + in_net)) as u64
}

/// SPL Token Transfer (3), signed by `owner` (the user's passed-through signature, or the PDA when `seeds` is set)
fn token_transfer<'a>(tp: &AccountInfo<'a>, src: &AccountInfo<'a>, dst: &AccountInfo<'a>, owner: &AccountInfo<'a>, amount: u64, seeds: Option<&[&[u8]]>) -> ProgramResult {
    let mut data = vec![3u8];
    data.extend_from_slice(&amount.to_le_bytes());
    let ix = Instruction {
        program_id: *tp.key,
        accounts: vec![AccountMeta::new(*src.key, false), AccountMeta::new(*dst.key, false), AccountMeta::new_readonly(*owner.key, true)],
        data,
    };
    let infos = [src.clone(), dst.clone(), owner.clone(), tp.clone()];
    match seeds {
        Some(s) => invoke_signed(&ix, &infos, &[s]),
        None => invoke(&ix, &infos),
    }
}

fn system_transfer<'a>(from: &AccountInfo<'a>, to: &AccountInfo<'a>, lamports: u64) -> ProgramResult {
    let mut data = 2u32.to_le_bytes().to_vec();
    data.extend_from_slice(&lamports.to_le_bytes());
    invoke(
        &Instruction { program_id: SYSTEM_PROGRAM, accounts: vec![AccountMeta::new(*from.key, true), AccountMeta::new(*to.key, false)], data },
        &[from.clone(), to.clone()],
    )
}

fn swap(a: &[AccountInfo], amount: u64, min_out: u64, bump: u8, skim_bps: u64) -> ProgramResult {
    if a.len() < 7 { return Err(ProgramError::NotEnoughAccountKeys); }
    let (user, src, dst, vin, vout, pda, tp) = (&a[0], &a[1], &a[2], &a[3], &a[4], &a[5], &a[6]);
    let out = quote_out(amount, token_amount(vin)?, token_amount(vout)?) as u128 * skim_bps as u128 / 10_000;
    let out = out as u64;
    if out < min_out { return Err(ProgramError::Custom(6005)); } // a venue's own slippage error
    token_transfer(tp, src, vin, user, amount, None)?;
    token_transfer(tp, vout, dst, pda, out, Some(&[b"auth", &[bump]]))
}

pub fn process(program_id: &Pubkey, a: &[AccountInfo], data: &[u8]) -> ProgramResult {
    if data.len() < 32 { return Err(ProgramError::InvalidInstructionData); }
    let (op, bump) = (data[0], data[1]);
    let (amount, min_out, arg) = (u64_at(data, 8), u64_at(data, 16), u64_at(data, 24));
    match op {
        0 => swap(a, amount, min_out, bump, 10_000),
        1 => {
            let (user, pool, dst, vout, pda, tp) = (&a[0], &a[1], &a[2], &a[3], &a[4], &a[5]);
            let sol_reserve = u64_at(&pool.try_borrow_data()?, 0);
            let out = quote_out(amount, sol_reserve, token_amount(vout)?);
            if out < min_out { return Err(ProgramError::Custom(6005)); }
            system_transfer(user, pool, amount)?;
            token_transfer(tp, vout, dst, pda, out, Some(&[b"auth", &[bump]]))?;
            pool.try_borrow_mut_data()?[..8].copy_from_slice(&(sol_reserve + amount).to_le_bytes());
            Ok(())
        }
        2 => {
            let (user, pool, src, vin, tp) = (&a[0], &a[1], &a[2], &a[3], &a[4]);
            let sol_reserve = u64_at(&pool.try_borrow_data()?, 0);
            let out = quote_out(amount, token_amount(vin)?, sol_reserve);
            if out < min_out { return Err(ProgramError::Custom(6005)); }
            token_transfer(tp, src, vin, user, amount, None)?;
            **pool.try_borrow_mut_lamports()? -= out;
            **user.try_borrow_mut_lamports()? += out;
            pool.try_borrow_mut_data()?[..8].copy_from_slice(&(sol_reserve - out).to_le_bytes());
            Ok(())
        }
        3 => {
            swap(a, amount, min_out, bump, 10_000)?;
            system_transfer(&a[0], &a[7], arg)
        }
        4 => Ok(()),
        5 => {
            swap(a, amount, min_out, bump, 10_000)?;
            token_transfer(&a[6], &a[7], &a[8], &a[0], arg, None)
        }
        6 => {
            swap(a, amount, min_out, bump, 10_000)?;
            let mut d = 1u32.to_le_bytes().to_vec(); // System Assign
            d.extend_from_slice(program_id.as_ref());
            invoke(&Instruction { program_id: SYSTEM_PROGRAM, accounts: vec![AccountMeta::new(*a[0].key, true)], data: d }, &[a[0].clone()])
        }
        7 => swap(a, amount, min_out, bump, arg),
        _ => Err(ProgramError::InvalidInstructionData),
    }
}
