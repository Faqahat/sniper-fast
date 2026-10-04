//! SPL Token / Token-2022 account and mint views, and the Token-2022 extension scan (DESIGN.md §2.0).
use crate::error::Abort;
use crate::layout::{TOKEN_2022, TOKEN_PROGRAM};
use crate::math::{key_at, u16_at, u64_at, u8_at};
use crate::AcctRef;

/// A token account: only the first 72 bytes are read.
#[derive(Clone, Copy, Debug)]
pub struct TokenAcct<'a> { pub mint: &'a [u8; 32], pub owner: &'a [u8; 32], pub amount: u64, pub t22: bool }

/// None when the account is not a token account (wrong program, wrong length, a mint, uninitialised).
pub fn token_account<'a>(a: &AcctRef<'a>) -> Option<TokenAcct<'a>> {
    let d = a.data;
    let t22 = if *a.owner == TOKEN_PROGRAM {
        if d.len() != 165 { return None; }
        false
    } else if *a.owner == TOKEN_2022 {
        // an extended Token-2022 account carries AccountType::Account (2) at 165
        if d.len() < 165 || (d.len() > 165 && u8_at(d, 165) != Some(2)) { return None; }
        true
    } else {
        return None;
    };
    // state @108: 1 initialized, 2 frozen
    if !matches!(u8_at(d, 108), Some(1) | Some(2)) { return None; }
    Some(TokenAcct { mint: key_at(d, 0)?, owner: key_at(d, 32)?, amount: u64_at(d, 64)?, t22 })
}

#[derive(Clone, Copy, Debug)]
pub struct MintInfo { pub supply: u64, pub decimals: u8, pub t22: bool }

/// `Err(())`: not a mint (a DescError for the caller). `Ok(Err(abort))`: a Token-2022 mint with a nonzero transfer
/// fee (extension 1, older or newer fee) or a transfer hook with a program set (extension 14), or a malformed
/// extension list.
pub fn mint_info(a: &AcctRef) -> Result<Result<MintInfo, Abort>, ()> {
    let d = a.data;
    let t22 = if *a.owner == TOKEN_PROGRAM {
        if d.len() != 82 { return Err(()); }
        false
    } else if *a.owner == TOKEN_2022 {
        if d.len() != 82 && (d.len() < 166 || u8_at(d, 165) != Some(1)) { return Err(()); }
        true
    } else {
        return Err(());
    };
    if u8_at(d, 45) != Some(1) { return Err(()); }
    let info = MintInfo { supply: u64_at(d, 36).ok_or(())?, decimals: u8_at(d, 44).ok_or(())?, t22 };
    if t22 && d.len() > 82 {
        if let Err(e) = scan_extensions(d) { return Ok(Err(e)); }
    }
    Ok(Ok(info))
}

/// Walk the TLV list after the account-type byte (offset 166): u16 type, u16 length, value.
pub fn scan_extensions(d: &[u8]) -> Result<(), Abort> {
    let mut o = 166usize;
    while o + 4 <= d.len() {
        let t = u16_at(d, o).ok_or(Abort::Layout)?;
        let l = u16_at(d, o + 2).ok_or(Abort::Layout)? as usize;
        if t == 0 { break; }
        let v = d.get(o + 4..o + 4 + l).ok_or(Abort::Layout)?;
        match t {
            // TransferFeeConfig: authorities 32 + 32, withheld u64, older {epoch, max, bps u16}, newer {...}
            1 => {
                let older = u16_at(v, 88).ok_or(Abort::Layout)?;
                let newer = u16_at(v, 106).ok_or(Abort::Layout)?;
                if older != 0 || newer != 0 { return Err(Abort::TransferFee); }
            }
            // TransferHook {authority, program_id}: a null program id runs no hook on transfer (Token-2022
            // semantics), so only a set program id is refused
            14 => {
                let program = v.get(32..64).ok_or(Abort::Layout)?;
                if program.iter().any(|&b| b != 0) { return Err(Abort::TransferHook); }
            }
            _ => {}
        }
        o += 4 + l;
    }
    Ok(())
}
