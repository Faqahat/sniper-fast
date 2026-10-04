//! TEST-ONLY hostile venue. Simulates a malicious upgrade of an allowlisted, third-party-upgradeable
//! venue (RayFork / RayFork2) that receives the payer as signer+writable inside a nexus-arb-v2 leg.
//! Never deploy.
//!
//! data: [0] ops bitmask  [1] mint-authority PDA bump  [8..16] input (patched by nexus-arb-v2)
//!       [16..24] lamports to steal  [24..32] tokens to mint to dst  [32..40] tokens to steal from victim
//! accounts: 0 payer (s,w)  1 src token (w)  2 dst token (w)  3 token program  4 system program
//!           5 lamport sink (w)  6 mint (w)  7 mint authority PDA ["mint"]  8 victim token (w)  9 attacker (w)
//! ops: 1 swap: transfer input src->dst          2 steal lamports payer->sink
//!      4 mint bonus to dst (pays the "profit")  8 transfer victim->attacker
//!      16 SetAuthority(AccountOwner) victim->attacker key   32 system assign payer -> this program
use solana_program::{
    account_info::AccountInfo,
    entrypoint,
    entrypoint::ProgramResult,
    instruction::{AccountMeta, Instruction},
    program::{invoke, invoke_signed},
    program_error::ProgramError,
    pubkey::Pubkey,
    system_instruction,
};

entrypoint!(process);

fn u64_at(d: &[u8], o: usize) -> u64 {
    let mut b = [0u8; 8];
    b.copy_from_slice(&d[o..o + 8]);
    u64::from_le_bytes(b)
}

fn transfer<'a>(tp: &AccountInfo<'a>, src: &AccountInfo<'a>, dst: &AccountInfo<'a>, owner: &AccountIn