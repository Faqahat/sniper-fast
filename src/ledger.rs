//! The ledger (PLAN WP-07 items 1-4, 6, 7; MEASUREMENT §4.42-§4.44): money from the chain, never from the bot's
//! counters (invariant 7).
//!
//! - **Entries** (`ledger.jsonl`, core): one per wallet transaction, keyed by signature. The chain-fetch service turns
//!   each wallet record's full transaction into a [`Raw`] (lamports, token amounts, fee, tip, the accounts it created
//!   and closed with their rent class: [`raw`]); INPUT 7 `wallet_tx` carries it to the engine, where [`entry`] values
//!   the non-SOL tokens at the engine's pool quote and splits the change of total equity into the summing categories
//!   (`trade_gross`, `tip`, `fee_win`, `fee_fail`, `fee_other`, `rent_nonrecoverable`, `transfer_in`, `transfer_out`,
//!   `other`: their sum is `equity_delta` on every line).
//! - **Snapshots** (`snapshots.jsonl`): the wallet's balances at one common context slot (F34: one `getMultipleAccounts`
//!   per 100 accounts, each later call with `minContextSlot` = the first answer's slot; answers at different slots are
//!   asked again up to `snapshot_retries` times, then written `slot_mismatch` and not reconciled), at start, every
//!   `snapshot_min` and at stop, on the background runtime; the answer comes back as INPUT 13 `snapshot` (journaled).
//! - **Reconciliation** (`recon.jsonl`), `recon_grace_s` after each snapshot: the snapshots' change against the entries
//!   between them on both bases (total: Δequity_total = Σequity_delta + inventory_reval; liquid: Δ(SOL + WSOL) =
//!   Σliquid_delta) and every token's raw amount exactly; and the executor's money (its landings' fees, tips and round
//!   trips) against the entries of the same signatures, with every refused bundle confirmed absent from the chain. An
//!   unexplained residual is searched with getSignaturesForAddress over the window, and decided once more a grace later.
//!   A miss puts the SendGate in shadow (`reconcile_miss`).
//! - **The executor's provisional money** (WP-05 hand-off): a landing its expiry check found first counts the base fee
//!   and an unknown round trip; the executor then asks the chain-fetch service for its record (`note_landed`), and its
//!   entry settles it. Status `money` is the ledger's; the bot's counters are `money.bot`, diagnostics.
//! - **The stop basis** for the supervisor (src/supervisor.rs; STAGE1-PLAN review F6): SOL + WSOL lamports, from the
//!   last snapshot and the entries after it; each non-SOL token is a quantity (its own floor); recoverable rent is
//!   tracked apart.
use crate::chainfetch::txjson::RpcTx;
use crate::config::LedgerCfg;
use crate::control::{SendGate, Stopper};
use crate::feeds::{Event, InputKind};
use crate::notify::Level;
use crate::rec::{self, Rec};
use crate::rpc::{Bounds, Rpc};
use crate::supervisor::{Series, Supervisor, DAY_NS, HOUR_NS};
use crate::tx::{b58, Pk};
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::path::Path;
use std::sync::{Arc, LazyLock};
use std::time::Duration;

pub const WSOL_MINT: &str = "So11111111111111111111111111111111111111112";
const SYSTEM: Pk = [0u8; 32];
pub static ALT_PROGRAM: LazyLock<Pk> = LazyLock::new(|| crate::tx::pk("AddressLookupTab1e1111111111111111111111111"));
/// PumpSwap: the user volume accumulator it creates for a payer can never be closed (res-pnl C2): non-recoverable rent
pub static PUMPSWAP: LazyLock<Pk> = LazyLock::new(|| crate::tx::pk("pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"));
/// what a new token account's rent is estimated at before the rent cap admits it (SPL 2,039,280; Token-2022 a little more)
pub const ATA_RENT_ESTIMATE: u64 = 2_100_000;

/// The PumpSwap user volume accumulator of `payer` (the program's PDA `["user_volume_accumulator", payer]`): made by the
/// payer's first PumpSwap buy (1,346,200 lamports) and never closable. The snapshots read it (owned, not recoverable)
pub fn accumulator_of(payer: &Pk) -> Pk { crate::pda::find_program_address(&[b"user_volume_accumulator", payer], &PUMPSWAP).0 }

/// `YYYY-MM-DD` (UTC) of a time in ns
pub fn utc_date(t_ns: u64) -> String {
    let d = (t_ns / 1_000_000_000 / 86_400) as i64;
    let z = d + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = if mp < 10 { mp + 3 } else { mp - 9 };
    let year = yoe + era * 400 + if month <= 2 { 1 } else { 0 };
    format!("{year:04}-{month:02}-{day:02}")
}

fn u32_at(d: &[u8], i: usize) -> Option<u32> { d.get(i..i + 4).map(|b| u32::from_le_bytes(b.try_into().unwrap())) }
fn u64_at(d: &[u8], i: usize) -> Option<u64> { d.get(i..i + 8).map(|b| u64::from_le_bytes(b.try_into().unwrap())) }
fn pk_at(d: &[u8], i: usize) -> Option<Pk> { d.get(i..i + 32).and_then(|b| b.try_into().ok()) }
fn pk58(s: &str) -> Option<Pk> { bs58::decode(s).into_vec().ok().and_then(|b| b.try_into().ok()) }
fn wsol() -> Pk { *crate::venues::WSOL }

// ------------------------------------------------------------------ raw entries (the chain-fetch side)

/// Whether a wallet-funded account's lamports are an asset the wallet can get back
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RentClass { Recoverable, Nonrecoverable }

impl RentClass { pub fn as_str(self) -> &'static str { match self { RentClass::Recoverable => "recoverable", RentClass::Nonrecoverable => "nonrecoverable" } } }

/// An account a wallet transaction created (funded by the wallet) or closed (one the wallet owned), and its rent: the
/// lamports, or for a WSOL token account the lamports beyond its token amount
#[derive(Clone, Debug, PartialEq)]
pub struct RentAcct { pub acct: Pk, pub lamports: u64, pub rent: u64, pub class: RentClass, pub what: &'static str, pub owner: Option<Pk>, pub mint: Option<Pk>, pub to: Option<Pk> }

impl RentAcct {
    fn json(&self) -> Value {
        json!({ "acct": b58(&self.acct), "lamports": self.lamports, "rent": self.rent, "class": self.class.as_str(), "what": self.what,
            "owner": self.owner.map(|o| b58(&o)), "mint": self.mint.map(|m| b58(&m)), "to": self.to.map(|t| b58(&t)) })
    }
    fn from_json(v: &Value) -> Option<RentAcct> {
        let what = match v["what"].as_str()? { "token" => "token", "nonce" => "nonce", "alt" => "alt", _ => "other" };
        Some(RentAcct { acct: pk58(v["acct"].as_str()?)?, lamports: v["lamports"].as_u64()?, rent: v["rent"].as_u64()?,
            class: if v["class"] == "recoverable" { RentClass::Recoverable } else { RentClass::Nonrecoverable }, what,
            owner: v["owner"].as_str().and_then(pk58), mint: v["mint"].as_str().and_then(pk58), to: v["to"].as_str().and_then(pk58) })
    }
}

/// What one transaction did to the wallet, from its chain record alone (no valuation): MEASUREMENT §4.42's raw fields
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Raw {
    /// wallet.jsonl `wallet_kind`
    pub kind: String,
    pub ok: bool,
    /// the wallet paid the fee (account 0)
    pub payer: bool,
    /// the wallet's lamport change (0 when it is not among the keys)
    pub wallet_sol: i64,
    /// the change of the WSOL token amount of the wallet's token accounts
    pub wsol: i64,
    /// the other mints' token-amount changes of the wallet's token accounts (non-zero only)
    pub tokens: BTreeMap<Pk, i128>,
    /// `meta.fee` when the wallet paid it, else 0
    pub fee: u64,
    /// in an ok route transaction: System transfers from the wallet to an account neither created in it nor one of the
    /// wallet's token accounts (the sender tip and the CPI tip; expected.json `conventions.tip`)
    pub tip: u64,
    pub rent_locked: u64,
    pub rent_reclaimed: u64,
    pub rent_nonrecoverable: u64,
    pub created: Vec<RentAcct>,
    pub closed: Vec<RentAcct>,
    /// the wallet's token accounts it touched (account, mint): the snapshots read them from then on
    pub token_accounts: Vec<(Pk, Pk)>,
}

/// one token account in a transaction's token balances
struct Tok { mint: Pk, owner: String, pre: Option<i128>, post: Option<i128> }

/// The System create of `k` in `ixs`: (funding account, owner, space, lamports)
fn system_create_of(ixs: &[(Pk, Vec<Pk>, &[u8])], k: &Pk) -> Option<(Pk, Option<Pk>, Option<u64>, u64)> {
    for (p, a, d) in ixs {
        if *p != SYSTEM || a.get(1) != Some(k) { continue; }
        match u32_at(d, 0) {
            // u32 0 | lamports u64 | space u64 | owner (32)
            Some(0) => return Some((a[0], pk_at(d, 20), u64_at(d, 12), u64_at(d, 4).unwrap_or(0))),
            Some(3) => {
                // u32 3 | base (32) | seed (u64 length + bytes) | lamports u64 | space u64 | owner (32)
                let n = u64_at(d, 36)? as usize;
                let at = 44usize.checked_add(n)?;
                return Some((a[0], pk_at(d, at + 16), u64_at(d, at + 8), u64_at(d, at).unwrap_or(0)));
            }
            _ => {}
        }
    }
    None
}

/// where a token CloseAccount (tag 9) of `k` sent its lamports
fn token_close_of(ixs: &[(Pk, Vec<Pk>, &[u8])], k: &Pk) -> Option<Option<Pk>> {
    ixs.iter().find(|(p, a, d)| (*p == *crate::pda::TOKEN_PROGRAM || *p == *crate::pda::TOKEN_2022) && d.first() == Some(&9) && a.first() == Some(k))
        .map(|(_, a, _)| a.get(1).copied())
}

/// `k` was made a durable-nonce account whose authority is the wallet (System InitializeNonceAccount, tag 6)
fn nonce_init_by(ixs: &[(Pk, Vec<Pk>, &[u8])], k: &Pk, wallet: &Pk) -> bool {
    ixs.iter().any(|(p, a, d)| *p == SYSTEM && u32_at(d, 0) == Some(6) && a.first() == Some(k) && pk_at(d, 4).as_ref() == Some(wallet))
}

/// `k` is a lookup table created with the wallet as its authority (CreateLookupTable: [table, authority, payer, system])
fn alt_created_by(ixs: &[(Pk, Vec<Pk>, &[u8])], k: &Pk, wallet: &Pk) -> bool {
    ixs.iter().any(|(p, a, d)| *p == *ALT_PROGRAM && u32_at(d, 0) == Some(0) && a.first() == Some(k) && a.get(1) == Some(wallet))
}

/// The ledger's raw view of one wallet transaction (`wsol_ata`: the wallet's WSOL account, for the kind; `route`: the
/// route program). Rent: an account created in a transaction the wallet pays, funded by the wallet, is recoverable when
/// the wallet can close it (one of its token accounts, a nonce account it is the authority of, a lookup table it is the
/// authority of) and non-recoverable otherwise (the PumpSwap user volume accumulator, any other program's account, a
/// token account of another owner); a new account that got lamports without a create is a transfer, not rent. A
/// closed account gives its rent back when it was the wallet's (a token account; for WSOL the lamports beyond the
/// amount, which is a WSOL decrease), a nonce or a lookup table
pub fn raw(x: &RpcTx, wallet: &Pk, wsol_ata: &Pk, route: &Pk) -> Raw {
    let f = crate::chainfetch::wallet::fields(x, wallet, wsol_ata, route);
    let meta = x.meta.as_ref();
    let ok = meta.is_some_and(|m| m.err.is_none());
    let payer = x.keys.first() == Some(wallet);
    let fee = if payer { meta.map_or(0, |m| m.fee) } else { 0 };
    let w58 = b58(wallet);
    let mut toks: BTreeMap<u32, Tok> = BTreeMap::new();
    if let Some(m) = meta {
        for (post, list) in [(false, &m.pre_token_balances), (true, &m.post_token_balances)] {
            for b in list {
                let Some(mint) = pk58(&b.mint) else { continue };
                let amt = b.ui_token_amount.as_ref().and_then(|u| u.amount.parse::<i128>().ok()).unwrap_or(0);
                let e = toks.entry(b.account_index).or_insert(Tok { mint, owner: b.owner.clone(), pre: None, post: None });
                if e.owner.is_empty() { e.owner = b.owner.clone(); }
                if post { e.post = Some(amt); } else { e.pre = Some(amt); }
            }
        }
    }
    let (mut wsol_d, mut tokens, mut token_accounts, mut own) = (0i128, BTreeMap::<Pk, i128>::new(), Vec::new(), BTreeSet::new());
    for (i, t) in &toks {
        if t.owner != w58 { continue; }
        let Some(k) = x.keys.get(*i as usize).copied() else { continue };
        own.insert(k);
        token_accounts.push((k, t.mint));
        let d = t.post.unwrap_or(0) - t.pre.unwrap_or(0);
        if t.mint == wsol() { wsol_d += d; } else if d != 0 { *tokens.entry(t.mint).or_default() += d; }
    }
    tokens.retain(|_, v| *v != 0);
    let ixs = crate::chainfetch::wallet::all_ixs(x);
    let (mut created, mut closed) = (Vec::new(), Vec::new());
    // every account made in this transaction (a System create, or no lamports before and some after): a transfer into
    // one is never a tip
    let mut fresh: BTreeSet<Pk> = ixs.iter().filter(|(p, a, d)| *p == SYSTEM && matches!(u32_at(d, 0), Some(0 | 3)) && a.len() > 1).map(|(_, a, _)| a[1]).collect();
    if let Some(m) = meta {
        for (i, k) in x.keys.iter().enumerate() {
            if k == wallet { continue; }
            let (pre, post) = (m.pre_balances.get(i).copied().unwrap_or(0), m.post_balances.get(i).copied().unwrap_or(0));
            let tok = toks.get(&(i as u32));
            if pre == 0 && post > 0 {
                fresh.insert(*k);
                let create = system_create_of(&ixs, k);
                if let Some(t) = tok.filter(|t| t.post.is_some()) {
                    // a token account: the wallet's own is recoverable rent (also one another payer made for it: an inflow,
                    // airdrop spam creates such accounts); another owner's that the wallet funded is lost (not recoverable)
                    let ours = t.owner == w58;
                    let funded_by_us = create.as_ref().map_or(payer, |c| c.0 == *wallet);
                    if !ours && !funded_by_us { continue; }
                    let rent = if t.mint == wsol() { post.saturating_sub(t.post.unwrap_or(0).max(0) as u64) } else { post };
                    let class = if ours { RentClass::Recoverable } else { RentClass::Nonrecoverable };
                    created.push(RentAcct { acct: *k, lamports: post, rent, class, what: "token", owner: create.and_then(|c| c.1), mint: Some(t.mint), to: None });
                    continue;
                }
                let Some((funder, owner, _space, _)) = create else { continue };
                if funder != *wallet { continue; }
                let (class, what) = match owner {
                    Some(o) if o == SYSTEM => {
                        if !nonce_init_by(&ixs, k, wallet) { continue; }
                        (RentClass::Recoverable, "nonce")
                    }
                    Some(o) if o == *ALT_PROGRAM => (if alt_created_by(&ixs, k, wallet) { RentClass::Recoverable } else { RentClass::Nonrecoverable }, "alt"),
                    _ => (RentClass::Nonrecoverable, "other"),
                };
                created.push(RentAcct { acct: *k, lamports: post, rent: post, class, what, owner, mint: None, to: None });
            } else if pre > 0 && post == 0 {
                if let Some(t) = tok.filter(|t| t.pre.is_some()) {
                    if t.owner != w58 { continue; }
                    let rent = if t.mint == wsol() { pre.saturating_sub(t.pre.unwrap_or(0).max(0) as u64) } else { pre };
                    let to = token_close_of(&ixs, k).flatten();
                    closed.push(RentAcct { acct: *k, lamports: pre, rent, class: RentClass::Recoverable, what: "token", owner: None, mint: Some(t.mint), to });
                } else if let Some((_, a, _)) = ixs.iter().find(|(p, a, d)| *p == SYSTEM && u32_at(d, 0) == Some(5) && a.first() == Some(k) && a.get(4) == Some(wallet)) {
                    // a nonce account the wallet withdrew whole: [nonce, to, recent blockhashes, rent, authority]
                    closed.push(RentAcct { acct: *k, lamports: pre, rent: pre, class: RentClass::Recoverable, what: "nonce", owner: Some(SYSTEM), mint: None, to: a.get(1).copied() });
                } else if let Some((_, a, _)) = ixs.iter().find(|(p, a, d)| *p == *ALT_PROGRAM && u32_at(d, 0) == Some(4) && a.first() == Some(k) && a.get(1) == Some(wallet)) {
                    // a lookup table the wallet closed: [table, authority, recipient]
                    closed.push(RentAcct { acct: *k, lamports: pre, rent: pre, class: RentClass::Recoverable, what: "alt", owner: Some(*ALT_PROGRAM), mint: None, to: a.get(2).copied() });
                }
            } else if pre == 0 && post == 0 {
                // made and closed in this transaction (WP-06's rent-neutral create + close): its rent went out and came back
                // (MEASUREMENT §4.42: rent_locked = rent_reclaimed)
                let Some((funder, owner, _, lamports)) = system_create_of(&ixs, k) else { continue };
                let Some(to) = token_close_of(&ixs, k) else { continue };
                if funder != *wallet || lamports == 0 { continue; }
                created.push(RentAcct { acct: *k, lamports, rent: lamports, class: RentClass::Recoverable, what: "token", owner, mint: None, to: None });
                closed.push(RentAcct { acct: *k, lamports, rent: lamports, class: RentClass::Recoverable, what: "token", owner: None, mint: None, to });
            }
        }
    }
    let sum = |v: &[RentAcct], c: RentClass| v.iter().filter(|a| a.class == c).map(|a| a.rent).sum::<u64>();
    let tip = if ok && f.wallet_kind == "route" {
        ixs.iter().filter(|(p, a, d)| *p == SYSTEM && u32_at(d, 0) == Some(2) && d.len() >= 12 && a.first() == Some(wallet))
            .filter(|(_, a, _)| a.get(1).is_some_and(|to| to != wallet && !fresh.contains(to) && !own.contains(to)))
            .filter_map(|(_, _, d)| u64_at(d, 4)).sum()
    } else { 0 };
    Raw { kind: f.wallet_kind.to_string(), ok, payer, wallet_sol: f.wallet_sol.unwrap_or(0), wsol: wsol_d as i64, tokens, fee, tip,
        rent_locked: sum(&created, RentClass::Recoverable), rent_reclaimed: sum(&closed, RentClass::Recoverable), rent_nonrecoverable: sum(&created, RentClass::Nonrecoverable),
        created, closed, token_accounts }
}

impl Raw {
    /// INPUT 7 `wallet_tx.ledger`
    pub fn json(&self) -> Value {
        json!({ "kind": self.kind, "ok": self.ok, "payer": self.payer, "wallet_sol": self.wallet_sol, "wsol": self.wsol,
            "tokens": self.tokens.iter().map(|(m, a)| (b58(m), json!(a.to_string()))).collect::<Map<_, _>>(),
            "fee": self.fee, "tip": self.tip, "rent_locked": self.rent_locked, "rent_reclaimed": self.rent_reclaimed, "rent_nonrecoverable": self.rent_nonrecoverable,
            "created": self.created.iter().map(RentAcct::json).collect::<Vec<_>>(), "closed": self.closed.iter().map(RentAcct::json).collect::<Vec<_>>(),
            "token_accounts": self.token_accounts.iter().map(|(a, m)| json!([b58(a), b58(m)])).collect::<Vec<_>>() })
    }
    pub fn from_json(v: &Value) -> Option<Raw> {
        let tokens = v["tokens"].as_object()?.iter().filter_map(|(m, a)| Some((pk58(m)?, a.as_str()?.parse::<i128>().ok()?))).collect();
        let list = |k: &str| v[k].as_array().map(|a| a.iter().filter_map(RentAcct::from_json).collect()).unwrap_or_default();
        Some(Raw { kind: v["kind"].as_str()?.to_string(), ok: v["ok"].as_bool()?, payer: v["payer"].as_bool().unwrap_or(false), wallet_sol: v["wallet_sol"].as_i64()?,
            wsol: v["wsol"].as_i64()?, tokens, fee: v["fee"].as_u64()?, tip: v["tip"].as_u64()?, rent_locked: v["rent_locked"].as_u64()?,
            rent_reclaimed: v["rent_reclaimed"].as_u64()?, rent_nonrecoverable: v["rent_nonrecoverable"].as_u64()?, created: list("created"), closed: list("closed"),
            token_accounts: v["token_accounts"].as_array().map(|a| a.iter().filter_map(|x| Some((pk58(x[0].as_str()?)?, pk58(x[1].as_str()?)?))).collect()).unwrap_or_default() })
    }
}

// ------------------------------------------------------------------ valued entries (the engine side)

/// What `amount` of `mint` is worth in lamports, and where the price came from (the engine: the best pool's quote for
/// selling it into WSOL). None: no price
pub type Valuer<'a> = &'a dyn Fn(&Pk, u128) -> Option<(u64, String)>;

/// a valuer that knows no price (tests, tools)
pub fn no_prices(_: &Pk, _: u128) -> Option<(u64, String)> { None }

/// `amount` (signed) of `mint` in lamports, less the haircut (a sale's quote, so a token never counts for more than the
/// pools would pay)
fn value_of(value: Valuer, mint: &Pk, amount: i128, haircut: f64) -> (i64, Option<String>) {
    if amount == 0 { return (0, None); }
    match value(mint, amount.unsigned_abs()) {
        Some((v, src)) => { let x = (v as f64 * (1.0 - haircut)).floor() as i64; (if amount < 0 { -x } else { x }, Some(src)) }
        None => (0, None),
    }
}

/// a token change and its value
#[derive(Clone, Debug, PartialEq)]
pub struct TokVal { pub amount: i128, pub value: i64, pub mid_src: Option<String> }

/// One ledger.jsonl line (MEASUREMENT §4.42)
#[derive(Clone, Debug, PartialEq)]
pub struct Entry {
    pub sig: String,
    pub slot: u64,
    pub idx: Option<u64>,
    /// the engine's time when the record reached it
    pub t_ns: u64,
    pub attempt: Option<u64>,
    pub kind: String,
    pub ok: bool,
    pub wallet_sol: i64,
    pub wsol: i64,
    pub tokens: BTreeMap<String, TokVal>,
    pub fee: u64,
    pub tip: u64,
    pub rent_locked: u64,
    pub rent_reclaimed: u64,
    pub rent_nonrecoverable: u64,
    pub liquid_delta: i64,
    pub equity_delta: i64,
    pub trade_gross: i64,
    pub trade_net: i64,
    /// the summing categories (non-zero ones), in A.3's order: their sum is `equity_delta`
    pub categories: Vec<(&'static str, i64)>,
    pub stranded: Vec<(String, i128)>,
    /// from before this segment's state stream (getSignaturesForAddress reads the last hour): the previous segment may
    /// have it
    pub pre_run: bool,
    /// wins: `trade_gross` against the route program's round trip (the last leg's output − the size)
    pub check: Option<Value>,
    pub created: Vec<RentAcct>,
    pub closed: Vec<RentAcct>,
}

/// where an entry sits and whose it is
pub struct Head<'a> { pub sig: &'a str, pub slot: u64, pub idx: Option<u64>, pub t_ns: u64, pub attempt: Option<u64>, pub pre_run: bool }

/// the summing categories in MEASUREMENT A.3's order
pub const CATEGORIES: [&str; 9] = ["trade_gross", "tip", "fee_win", "fee_fail", "fee_other", "rent_nonrecoverable", "transfer_in", "transfer_out", "other"];

/// A wallet transaction as a ledger line. A route transaction that succeeded: `trade_gross` = equity_delta + fee + tip +
/// rent_nonrecoverable, with `tip`, `fee_win`, `rent_nonrecoverable`; a route transaction that failed: `fee_fail`
/// (anything else, which a failed transaction cannot change, is `other`); any other transaction: `fee_other` (a failed
/// one too: `fee_fail` stays the bot's failed landings), `rent_nonrecoverable`, and the rest of the equity change as
/// `transfer_in` or `transfer_out`
pub fn entry(r: &Raw, h: &Head, haircut: f64, value: Valuer) -> Entry {
    let tokens: BTreeMap<String, TokVal> = r.tokens.iter().map(|(m, a)| {
        let (v, src) = value_of(value, m, *a, haircut);
        (b58(m), TokVal { amount: *a, value: v, mid_src: src })
    }).collect();
    let tok_value: i64 = tokens.values().map(|t| t.value).sum();
    let liquid = r.wallet_sol + r.wsol;
    let equity = liquid + tok_value + r.rent_locked as i64 - r.rent_reclaimed as i64;
    let (fee, tip, nonrec) = (r.fee as i64, r.tip as i64, r.rent_nonrecoverable as i64);
    let route = r.kind == "route";
    let (gross, net) = match (route, r.ok) { (true, true) => { let g = equity + fee + tip + nonrec; (g, g - fee - tip) } (true, false) => (0, -fee), _ => (0, 0) };
    let mut cats: Vec<(&'static str, i64)> = Vec::new();
    match (route, r.ok) {
        (true, true) => { cats.extend([("trade_gross", gross), ("tip", -tip), ("fee_win", -fee), ("rent_nonrecoverable", -nonrec)]); }
        (true, false) => { cats.extend([("fee_fail", -fee), ("rent_nonrecoverable", -nonrec), ("other", equity + fee + nonrec)]); }
        _ => {
            let rest = equity + fee + nonrec;
            cats.extend([("fee_other", -fee), ("rent_nonrecoverable", -nonrec), (if rest >= 0 { "transfer_in" } else { "transfer_out" }, rest)]);
        }
    }
    cats.retain(|c| c.1 != 0);
    cats.sort_by_key(|c| CATEGORIES.iter().position(|x| *x == c.0));
    debug_assert_eq!(cats.iter().map(|c| c.1).sum::<i64>(), equity);
    let stranded = if route && r.ok { tokens.iter().filter(|(_, t)| t.amount > 0).map(|(m, t)| (m.clone(), t.amount)).collect() } else { Vec::new() };
    Entry { sig: h.sig.to_string(), slot: h.slot, idx: h.idx, t_ns: h.t_ns, attempt: h.attempt, kind: r.kind.clone(), ok: r.ok, wallet_sol: r.wallet_sol, wsol: r.wsol,
        tokens, fee: r.fee, tip: r.tip, rent_locked: r.rent_locked, rent_reclaimed: r.rent_reclaimed, rent_nonrecoverable: r.rent_nonrecoverable,
        liquid_delta: liquid, equity_delta: equity, trade_gross: gross, trade_net: net, categories: cats, stranded, pre_run: h.pre_run, check: None,
        created: r.created.clone(), closed: r.closed.clone() }
}

impl Entry {
    /// the change of SOL + WSOL (no rent, no token value: STAGE1-PLAN review F6); the money view's, informational
    pub fn stop_delta(&self) -> i64 { self.liquid_delta }
    pub fn token_value(&self) -> i64 { self.tokens.values().map(|t| t.value).sum() }
    /// The trading result of a route transaction on the budget's basis (BUDGET.md "Trading P&L"): its change of SOL +
    /// WSOL and of recoverable rent, plus what it paid in fee, tip and non-recoverable rent; a token it left behind counts
    /// 0 (price-free, and never in the bot's favour). `trade_gross` less the token value; 0 for anything but a route
    pub fn trade_pnl(&self) -> i64 {
        if !self.is_route() { return 0; }
        self.liquid_delta + self.rent_locked as i64 - self.rent_reclaimed as i64 + self.fee as i64 + self.tip as i64 + self.rent_nonrecoverable as i64
    }
    /// What this transaction cost the test budget (review WP-07 #4: the stops' basis, free of the owner's transfers and of
    /// any price): a route of ours its fee, tip and non-recoverable rent less its trading result (= minus its change of
    /// SOL + WSOL and of recoverable rent); any other transaction the wallet paid for its fee and its non-recoverable
    /// rent only: a deposit or a withdrawal (`transfer_in`, `transfer_out`) costs nothing and extends nothing
    pub fn spend(&self) -> i64 {
        if self.is_route() { self.fee as i64 + self.tip as i64 + self.rent_nonrecoverable as i64 - self.trade_pnl() }
        else { self.fee as i64 + self.rent_nonrecoverable as i64 }
    }
    /// the owner's own transfer (a transaction that is not a route of ours and moved equity in or out beyond its fee):
    /// recorded and alerted (`owner_transfer`), never a stop; (category, lamports)
    pub fn owner_transfer(&self) -> Option<(&'static str, i64)> {
        if self.is_route() { return None; }
        let (i, o) = (self.cat("transfer_in"), self.cat("transfer_out"));
        if i != 0 { Some(("transfer_in", i)) } else if o != 0 { Some(("transfer_out", o)) } else { None }
    }
    pub fn cat(&self, c: &str) -> i64 { self.categories.iter().filter(|x| x.0 == c).map(|x| x.1).sum() }
    /// a route transaction of ours that failed: a failed landing's fee (Stage-0 exit: 0 in 24 h)
    pub fn is_route(&self) -> bool { self.kind == "route" }

    pub fn json(&self) -> Value {
        json!({ "sig": self.sig, "slot": self.slot, "idx": self.idx, "t_ns": self.t_ns, "attempt": self.attempt, "kind": self.kind, "ok": self.ok,
            "wallet_sol": self.wallet_sol, "wsol": self.wsol,
            "tokens": self.tokens.iter().map(|(m, t)| (m.clone(), json!({ "amount": t.amount.to_string(), "value_lamports": t.value, "mid_src": t.mid_src }))).collect::<Map<_, _>>(),
            "fee": self.fee, "tip": self.tip, "rent_locked": self.rent_locked, "rent_reclaimed": self.rent_reclaimed, "rent_nonrecoverable": self.rent_nonrecoverable,
            "liquid_delta": self.liquid_delta, "equity_delta": self.equity_delta, "stop_delta": self.stop_delta(), "trade_gross": self.trade_gross, "trade_net": self.trade_net,
            "categories": self.categories.iter().map(|(c, l)| json!({ "cat": c, "lamports": l })).collect::<Vec<_>>(),
            "stranded": self.stranded.iter().map(|(m, a)| json!({ "mint": m, "amount": a.to_string() })).collect::<Vec<_>>(),
            "check": self.check, "pre_run": self.pre_run,
            "created": self.created.iter().map(RentAcct::json).collect::<Vec<_>>(), "closed": self.closed.iter().map(RentAcct::json).collect::<Vec<_>>() })
    }

    /// a ledger.jsonl line read back (earlier segments: the campaign's series and spend)
    pub fn from_json(v: &Value) -> Option<Entry> {
        let tokens = v["tokens"].as_object().map(|o| o.iter().filter_map(|(m, t)| Some((m.clone(), TokVal { amount: t["amount"].as_str()?.parse().ok()?,
            value: t["value_lamports"].as_i64().unwrap_or(0), mid_src: t["mid_src"].as_str().map(String::from) }))).collect()).unwrap_or_default();
        let cats = v["categories"].as_array()?.iter().filter_map(|c| {
            let name = c["cat"].as_str()?;
            let n = CATEGORIES.iter().find(|x| **x == name)?;
            Some((*n, c["lamports"].as_i64()?))
        }).collect();
        let list = |k: &str| v[k].as_array().map(|a| a.iter().filter_map(RentAcct::from_json).collect()).unwrap_or_default();
        Some(Entry { sig: v["sig"].as_str()?.to_string(), slot: v["slot"].as_u64()?, idx: v["idx"].as_u64(), t_ns: v["t_ns"].as_u64().unwrap_or(0),
            attempt: v["attempt"].as_u64(), kind: v["kind"].as_str()?.to_string(), ok: v["ok"].as_bool()?, wallet_sol: v["wallet_sol"].as_i64()?, wsol: v["wsol"].as_i64()?,
            tokens, fee: v["fee"].as_u64()?, tip: v["tip"].as_u64()?, rent_locked: v["rent_locked"].as_u64()?, rent_reclaimed: v["rent_reclaimed"].as_u64()?,
            rent_nonrecoverable: v["rent_nonrecoverable"].as_u64()?, liquid_delta: v["liquid_delta"].as_i64()?, equity_delta: v["equity_delta"].as_i64()?,
            trade_gross: v["trade_gross"].as_i64()?, trade_net: v["trade_net"].as_i64()?, categories: cats,
            stranded: v["stranded"].as_array().map(|a| a.iter().filter_map(|s| Some((s["mint"].as_str()?.to_string(), s["amount"].as_str()?.parse().ok()?))).collect()).unwrap_or_default(),
            pre_run: v["pre_run"].as_bool().unwrap_or(false), check: v.get("check").cloned().filter(|c| !c.is_null()), created: list("created"), closed: list("closed") })
    }

    /// outcomes.jsonl `ledger` (MEASUREMENT §4.40)
    pub fn outcome_json(&self) -> Value {
        json!({ "trade_gross": self.trade_gross, "tip": self.tip, "fee": self.fee, "rent_nonrecoverable": self.rent_nonrecoverable, "rent_locked": self.rent_locked,
            "rent_reclaimed": self.rent_reclaimed, "trade_net": self.trade_net, "equity_delta": self.equity_delta, "liquid_delta": self.liquid_delta })
    }
}

// ------------------------------------------------------------------ totals (status, spend.json)

/// Sums over entries (MEASUREMENT §4.8 money; docs/field-tests/BUDGET.md's columns)
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct Totals {
    pub entries: u64,
    pub trade_gross: i64,
    pub trade_net: i64,
    pub tips: i64,
    pub fee_win: i64,
    pub fee_fail: i64,
    pub fee_other: i64,
    pub rent_locked: i64,
    pub rent_reclaimed: i64,
    pub rent_nonrecoverable: i64,
    pub transfer_in: i64,
    pub transfer_out: i64,
    pub other: i64,
    pub wins: u64,
    pub landed_fail: u64,
    /// the routes' trading result on the budget's basis (`Entry::trade_pnl`: stranded tokens at 0)
    pub trade_pnl: i64,
    /// Σ`Entry::spend`: the net spend (the stops' and the budget's basis)
    pub spend: i64,
    pub owner_transfers: u64,
}

impl Totals {
    pub fn add(&mut self, e: &Entry) {
        self.entries += 1;
        self.trade_pnl += e.trade_pnl();
        self.spend += e.spend();
        if e.owner_transfer().is_some() { self.owner_transfers += 1; }
        self.trade_gross += e.trade_gross;
        self.trade_net += e.trade_net;
        self.tips += e.tip as i64;
        self.fee_win += -e.cat("fee_win");
        self.fee_fail += -e.cat("fee_fail");
        self.fee_other += -e.cat("fee_other");
        self.rent_locked += e.rent_locked as i64;
        self.rent_reclaimed += e.rent_reclaimed as i64;
        self.rent_nonrecoverable += e.rent_nonrecoverable as i64;
        self.transfer_in += e.cat("transfer_in");
        self.transfer_out += -e.cat("transfer_out");
        self.other += e.cat("other");
        if e.is_route() && e.ok { self.wins += 1; }
        if e.is_route() && !e.ok && e.fee > 0 { self.landed_fail += 1; }
    }
    pub fn fees(&self) -> i64 { self.fee_win + self.fee_fail + self.fee_other }
    /// What testing cost (BUDGET.md "Net spend"; the stops' basis, review WP-07 #4): fees + tips + non-recoverable rent −
    /// the trading result (`trade_pnl`: stranded tokens at 0, recoverable rent apart). The owner's own transfers are not
    /// in it: a deposit extends no allowance, a withdrawal spends none
    pub fn net_spend(&self) -> i64 { self.spend }
    pub fn json(&self) -> Value {
        json!({ "entries": self.entries, "fees": self.fees(), "fee_win": self.fee_win, "fee_fail": self.fee_fail, "fee_other": self.fee_other, "tips": self.tips,
            "rent_locked": self.rent_locked, "rent_recovered": self.rent_reclaimed, "rent_nonrecoverable": self.rent_nonrecoverable, "trade_gross": self.trade_gross,
            "trade_net": self.trade_net, "trade_pnl": self.trade_pnl, "transfer_in": self.transfer_in, "transfer_out": self.transfer_out, "other": self.other,
            "owner_transfers": self.owner_transfers, "wins": self.wins, "landed_fail": self.landed_fail, "net_spend": self.net_spend() })
    }
}

// ------------------------------------------------------------------ snapshots

/// a wallet token account in a snapshot
#[derive(Clone, Debug, PartialEq)]
pub struct SnapTok { pub mint: String, pub account: Pk, pub program: Pk, pub amount: u64, pub rent: u64, pub value: Option<u64>, pub mid_src: Option<String> }

/// One snapshots.jsonl line (MEASUREMENT §4.43)
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Snapshot {
    pub t_ns: u64,
    pub slot: u64,
    pub slot_mismatch: bool,
    pub why: String,
    pub sol: u64,
    pub wsol: u64,
    pub tokens: Vec<SnapTok>,
    pub wsol_accounts: Vec<(Pk, u64, u64)>,
    pub nonce_accounts: Vec<(Pk, u64)>,
    pub alts: Vec<(Pk, u64)>,
    pub other_owned: Vec<(Pk, Pk, u64, bool)>,
    pub missing: Vec<Pk>,
    /// accounts read that are not the wallet's (a nonce account or lookup table of another authority, another owner's
    /// token account): left out
    pub not_ours: Vec<Pk>,
    pub rent_recoverable: u64,
    pub rent_nonrecoverable: u64,
    pub token_value: u64,
    pub rpc: Value,
}

impl Snapshot {
    pub fn equity_liquid(&self) -> i64 { (self.sol + self.wsol) as i64 }
    /// the stop basis: SOL + WSOL (BUDGET.md's "starting wallet" basis; rent and tokens tracked apart)
    pub fn equity_stop(&self) -> i64 { self.equity_liquid() }
    /// MEASUREMENT §4.42's total equity: liquid + the tokens' value + recoverable rent
    pub fn equity_total(&self) -> i64 { self.equity_liquid() + self.rent_recoverable as i64 + self.token_value as i64 }
    /// the non-SOL tokens' raw amounts by mint
    pub fn token_amounts(&self) -> BTreeMap<String, u128> {
        let mut m = BTreeMap::new();
        for t in &self.tokens { *m.entry(t.mint.clone()).or_insert(0u128) += t.amount as u128; }
        m
    }
    /// every account read (the next snapshot reads them again)
    pub fn accounts(&self) -> Vec<Pk> {
        self.tokens.iter().map(|t| t.account).chain(self.wsol_accounts.iter().map(|w| w.0)).chain(self.nonce_accounts.iter().map(|n| n.0))
            .chain(self.alts.iter().map(|a| a.0)).chain(self.other_owned.iter().map(|o| o.0)).collect()
    }

    /// The snapshot from its RPC answer (`fetch_snapshot`'s INPUT 13): the wallet's lamports; its token accounts (WSOL:
    /// its amount, and the lamports beyond it as rent); nonce accounts and lookup tables it is the authority of
    /// (recoverable); the payer's PumpSwap accumulator (owned, not recoverable); any other account is not the wallet's
    /// and left out. Tokens are valued at the valuer's quote less `haircut` (unpriced: 0, flagged)
    pub fn parse(d: &Value, wallet: &Pk, haircut: f64, value: Valuer, t_ns: u64) -> Result<Snapshot, String> {
        if let Some(e) = d["error"].as_str() { return Err(e.to_string()); }
        let keys: Vec<Pk> = d["keys"].as_array().ok_or("no keys")?.iter().filter_map(|k| k.as_str().and_then(pk58)).collect();
        let answers = d["answers"].as_array().ok_or("no answers")?;
        let mut vals: Vec<&Value> = Vec::with_capacity(keys.len());
        let mut slot = 0;
        for a in answers {
            slot = slot.max(a["slot"].as_u64().unwrap_or(0));
            for v in a["values"].as_array().ok_or("an answer without values")? { vals.push(v); }
        }
        if vals.len() != keys.len() { return Err(format!("{} answers for {} accounts", vals.len(), keys.len())); }
        let mut s = Snapshot { t_ns, slot, slot_mismatch: d["slot_mismatch"].as_bool().unwrap_or(false), why: d["why"].as_str().unwrap_or("").into(),
            rpc: json!({ "provider": d["provider"], "calls": answers.len(), "ms": d["ms"], "attempts": d["attempts"] }), ..Default::default() };
        let b64 = |v: &Value| -> Vec<u8> {
            use base64::Engine as _;
            v["data"].as_str().or_else(|| v["data"][0].as_str()).and_then(|x| base64::engine::general_purpose::STANDARD.decode(x).ok()).unwrap_or_default()
        };
        for (k, v) in keys.iter().zip(vals) {
            if v.is_null() { if k != wallet { s.missing.push(*k); } continue; }
            let lamports = v["lamports"].as_u64().unwrap_or(0);
            if k == wallet { s.sol = lamports; continue; }
            let owner = v["owner"].as_str().and_then(pk58).unwrap_or(SYSTEM);
            let data = b64(v);
            if owner == *crate::pda::TOKEN_PROGRAM || owner == *crate::pda::TOKEN_2022 {
                let (Some(mint), Some(holder), Some(amount)) = (pk_at(&data, 0), pk_at(&data, 32), u64_at(&data, 64)) else { s.not_ours.push(*k); continue };
                if holder != *wallet { s.not_ours.push(*k); continue; }
                if mint == wsol() {
                    s.wsol += amount;
                    s.rent_recoverable += lamports.saturating_sub(amount);
                    s.wsol_accounts.push((*k, lamports, amount));
                } else {
                    let (v, src) = value_of(value, &mint, amount as i128, haircut);
                    s.rent_recoverable += lamports;
                    s.token_value += v.max(0) as u64;
                    s.tokens.push(SnapTok { mint: b58(&mint), account: *k, program: owner, amount, rent: lamports, value: src.as_ref().map(|_| v.max(0) as u64), mid_src: src });
                }
            } else if owner == SYSTEM && data.len() == 80 && pk_at(&data, 8).as_ref() == Some(wallet) {
                s.rent_recoverable += lamports;
                s.nonce_accounts.push((*k, lamports));
            } else if owner == *ALT_PROGRAM && data.get(21) == Some(&1) && pk_at(&data, 22).as_ref() == Some(wallet) {
                s.rent_recoverable += lamports;
                s.alts.push((*k, lamports));
            } else if owner == *PUMPSWAP && *k == accumulator_of(wallet) {
                s.rent_nonrecoverable += lamports;
                s.other_owned.push((*k, owner, lamports, false));
            } else {
                s.not_ours.push(*k);
            }
        }
        Ok(s)
    }

    pub fn json(&self) -> Value {
        json!({ "t_ns": self.t_ns, "slot": self.slot, "slot_mismatch": self.slot_mismatch, "why": self.why, "sol": self.sol, "wsol": self.wsol,
            "tokens": self.tokens.iter().map(|t| json!({ "mint": t.mint, "account": b58(&t.account), "program": b58(&t.program), "amount": t.amount.to_string(),
                "rent_lamports": t.rent, "mid_lamports_per_unit": t.value.filter(|_| t.amount > 0).map(|v| v as f64 / t.amount as f64), "value_lamports": t.value,
                "mid_src": t.mid_src, "stranded": t.value.is_none() })).collect::<Vec<_>>(),
            "wsol_accounts": self.wsol_accounts.iter().map(|w| json!({ "account": b58(&w.0), "lamports": w.1, "amount": w.2.to_string() })).collect::<Vec<_>>(),
            "nonce_accounts": self.nonce_accounts.iter().map(|n| json!({ "account": b58(&n.0), "lamports": n.1 })).collect::<Vec<_>>(),
            "alts": self.alts.iter().map(|a| json!({ "table": b58(&a.0), "lamports": a.1 })).collect::<Vec<_>>(),
            "other_owned": self.other_owned.iter().map(|o| json!({ "account": b58(&o.0), "owner": b58(&o.1), "lamports": o.2, "recoverable": o.3 })).collect::<Vec<_>>(),
            "missing": self.missing.iter().map(b58).collect::<Vec<_>>(), "not_ours": self.not_ours.iter().map(b58).collect::<Vec<_>>(),
            "rent_recoverable": self.rent_recoverable, "rent_nonrecoverable": self.rent_nonrecoverable, "token_value": self.token_value,
            "equity_liquid": self.equity_liquid(), "equity_total": self.equity_total(), "equity_stop": self.equity_stop(), "rpc": self.rpc })
    }

    /// a snapshots.jsonl line read back (earlier segments)
    pub fn from_json(v: &Value) -> Option<Snapshot> {
        let tokens = v["tokens"].as_array()?.iter().filter_map(|t| Some(SnapTok { mint: t["mint"].as_str()?.to_string(), account: pk58(t["account"].as_str()?)?,
            program: t["program"].as_str().and_then(pk58).unwrap_or(*crate::pda::TOKEN_PROGRAM), amount: t["amount"].as_str()?.parse().ok()?,
            rent: t["rent_lamports"].as_u64().unwrap_or(0), value: t["value_lamports"].as_u64(), mid_src: t["mid_src"].as_str().map(String::from) })).collect();
        let pairs = |k: &str, n: &str| v[k].as_array().map(|a| a.iter().filter_map(|x| Some((pk58(x[n].as_str()?)?, x["lamports"].as_u64()?))).collect()).unwrap_or_default();
        Some(Snapshot { t_ns: v["t_ns"].as_u64()?, slot: v["slot"].as_u64()?, slot_mismatch: v["slot_mismatch"].as_bool().unwrap_or(false),
            why: v["why"].as_str().unwrap_or("").into(), sol: v["sol"].as_u64()?, wsol: v["wsol"].as_u64()?, tokens,
            wsol_accounts: v["wsol_accounts"].as_array().map(|a| a.iter().filter_map(|x| Some((pk58(x["account"].as_str()?)?, x["lamports"].as_u64()?,
                x["amount"].as_str()?.parse().ok()?))).collect()).unwrap_or_default(),
            nonce_accounts: pairs("nonce_accounts", "account"), alts: pairs("alts", "table"),
            other_owned: v["other_owned"].as_array().map(|a| a.iter().filter_map(|x| Some((pk58(x["account"].as_str()?)?, pk58(x["owner"].as_str()?)?,
                x["lamports"].as_u64()?, x["recoverable"].as_bool().unwrap_or(false)))).collect()).unwrap_or_default(),
            missing: v["missing"].as_array().map(|a| a.iter().filter_map(|x| x.as_str().and_then(pk58)).collect()).unwrap_or_default(),
            not_ours: v["not_ours"].as_array().map(|a| a.iter().filter_map(|x| x.as_str().and_then(pk58)).collect()).unwrap_or_default(),
            rent_recoverable: v["rent_recoverable"].as_u64()?, rent_nonrecoverable: v["rent_nonrecoverable"].as_u64().unwrap_or(0),
            token_value: v["token_value"].as_u64().unwrap_or(0), rpc: v["rpc"].clone() })
    }
}

/// The snapshot's RPC calls (`call`: one `getMultipleAccounts` with its params → (the result, the provider)), on one
/// common context slot (F34): `keys` in chunks of 100, every chunk after the first with `minContextSlot` = the first
/// answer's slot; when the answers' slots differ, all of it is asked again, up to `retries` times, then returned with
/// `slot_mismatch: true`. A failed call: asked again (same budget), then `error`. Returns INPUT 13's body
pub async fn fetch_with<F, Fut>(call: F, keys: Vec<Pk>, retries: u32, why: &str) -> Value
where F: Fn(Value) -> Fut, Fut: std::future::Future<Output = Result<(Value, String), String>> {
    let t0 = std::time::Instant::now();
    let ks: Vec<String> = keys.iter().map(b58).collect();
    let mut last_err = None;
    let mut out = None;
    for attempt in 0..=retries {
        let mut answers = Vec::new();
        let mut first: Option<u64> = None;
        let mut provider = String::new();
        let mut failed = None;
        for chunk in ks.chunks(100) {
            let mut cfg = json!({ "encoding": "base64", "commitment": "confirmed" });
            if let Some(s) = first { cfg["minContextSlot"] = json!(s); }
            match call(json!([chunk, cfg])).await {
                Ok((v, p)) => {
                    let slot = v["context"]["slot"].as_u64().unwrap_or(0);
                    first.get_or_insert(slot);
                    provider = p;
                    answers.push(json!({ "slot": slot, "values": v["value"] }));
                }
                Err(e) => { failed = Some(e); break; }
            }
        }
        if let Some(e) = failed { last_err = Some(e); continue; }
        let mismatch = answers.windows(2).any(|w| w[0]["slot"] != w[1]["slot"]);
        let v = json!({ "what": "snapshot", "why": why, "keys": ks, "answers": answers, "slot_mismatch": mismatch, "attempts": attempt + 1, "provider": provider,
            "ms": t0.elapsed().as_secs_f64() * 1e3, "error": null });
        if !mismatch { return v; }
        out = Some(v);
    }
    out.unwrap_or_else(|| json!({ "what": "snapshot", "why": why, "keys": ks, "error": last_err.unwrap_or_else(|| "no answer".into()), "attempts": retries + 1,
        "ms": t0.elapsed().as_secs_f64() * 1e3 }))
}

/// `fetch_with` through the bounded RPC (role `ledger`; 5 s, two more providers)
pub async fn fetch_snapshot(rpc: Rpc, keys: Vec<Pk>, retries: u32, why: &str) -> Value {
    fetch_with(|params| {
        let rpc = rpc.clone();
        async move { rpc.call_bounded("getMultipleAccounts", params, Bounds::fetch(Duration::from_secs(5), 2)).await.map(|f| (f.value, f.provider)).map_err(|e| e.msg) }
    }, keys, retries, why).await
}

// ------------------------------------------------------------------ reconciliation (pure)

/// MEASUREMENT §4.44: snapshot `to` against `from` and the entries between them (slot in (from.slot, to.slot]). Returns
/// the recon.jsonl line and whether it passed (both residuals within `tol`, every token amount exact)
pub fn reconcile(from: &Snapshot, to: &Snapshot, entries: &[&Entry], tol: u64, t_ns: u64) -> (Value, bool) {
    let win: Vec<&&Entry> = entries.iter().filter(|e| e.slot > from.slot && e.slot <= to.slot).collect();
    let sum = |f: &dyn Fn(&Entry) -> i64| win.iter().map(|e| f(e)).sum::<i64>();
    let delta_equity = to.equity_total() - from.equity_total();
    let sum_entries = sum(&|e| e.equity_delta);
    let inventory_reval = (to.token_value as i64 - from.token_value as i64) - sum(&|e| e.token_value());
    let residual = delta_equity - sum_entries - inventory_reval;
    let liquid_delta = to.equity_liquid() - from.equity_liquid();
    let liquid_sum = sum(&|e| e.liquid_delta);
    let liquid_residual = liquid_delta - liquid_sum;
    // raw token amounts: exact
    let (fa, ta) = (from.token_amounts(), to.token_amounts());
    let mut mints: BTreeSet<String> = fa.keys().chain(ta.keys()).cloned().collect();
    for e in &win { mints.extend(e.tokens.keys().cloned()); }
    let mut toks_ok = true;
    let token_amounts: Vec<Value> = mints.iter().map(|m| {
        let d = ta.get(m).copied().unwrap_or(0) as i128 - fa.get(m).copied().unwrap_or(0) as i128;
        let s: i128 = win.iter().filter_map(|e| e.tokens.get(m)).map(|t| t.amount).sum();
        let ok = d == s;
        toks_ok &= ok;
        json!({ "mint": m, "delta_snapshot": d.to_string(), "sum_entries": s.to_string(), "ok": ok })
    }).collect();
    let mut by_cat = Map::new();
    for c in CATEGORIES { let x = sum(&|e| e.cat(c)); if x != 0 { by_cat.insert(c.to_string(), json!(x)); } }
    let ok = residual.unsigned_abs() <= tol && liquid_residual.unsigned_abs() <= tol && toks_ok;
    let line = json!({ "t_ns": t_ns, "from": { "t_ns": from.t_ns, "slot": from.slot, "why": from.why }, "to": { "t_ns": to.t_ns, "slot": to.slot, "why": to.why },
        "entries": win.len(), "delta_equity": delta_equity, "sum_entries": sum_entries, "inventory_reval": inventory_reval, "residual": residual,
        "liquid": { "delta": liquid_delta, "sum_entries": liquid_sum, "residual": liquid_residual }, "token_amounts": token_amounts, "tolerance": tol, "ok": ok,
        "by_category": by_cat, "informational": { "rent_locked": sum(&|e| e.rent_locked as i64), "rent_reclaimed": sum(&|e| e.rent_reclaimed as i64),
            "liquid_delta": liquid_sum } });
    (line, ok)
}

/// What the executor counted for one of its attempts (`Exec::landings`): its final, whether it landed and how it knows
/// (`src` `statuses`: the expiry check found it first, `wallet_seen` false while its record has not come: provisional
/// money), and the money it counted (the fee, the tip, the round trip; `rt_unknown`: a win whose round trip it lacks)
/// `refused`: the attempt's first final was `not_landed_refused` (immutable: a later landing's amend never clears it;
/// review WP-07 #6); `t_final`: the engine time of its final (or of the landing that amended it)
#[derive(Clone, Debug, PartialEq)]
pub struct Landing { pub attempt: u64, pub sig: String, pub fin: &'static str, pub landed: bool, pub ok: bool, pub src: &'static str, pub wallet_seen: bool,
    pub fee: u64, pub tip: u64, pub round_trip: i64, pub rt_unknown: bool, pub refused: bool, pub t_final: u64 }

impl Landing {
    /// the provisional money of a landing whose record has not come (the executor counted the base fee)
    pub fn provisional(&self) -> bool { self.landed && !self.wallet_seen }
}

/// an attempt of an earlier segment of the campaign (its signature, from that segment's outcomes)
#[derive(Clone, Debug, PartialEq)]
pub struct Earlier { pub segment: String, pub attempt: u64, pub fin: String }

/// The executor's money against the chain (PLAN WP-07 brief: hourly, chain truth vs the executor's accounting, within
/// `tol`): for every attempt the executor counted as landed whose entry the ledger has, the executor's net (round trip
/// − tip − fee) against the entry's `trade_net`; landings without an entry are listed (`provisional`: the executor
/// asked for their records; a residual they leave shows in the snapshots); a route entry of ours that no attempt of
/// this segment (nor an earlier segment's open one) explains, an attempt the chain shows landed that the executor
/// counts as not landed, and **any refused bundle that landed**, are misses. An earlier segment's open or expired
/// attempt that landed is listed (`earlier_landed`: its segment ended before its record came), not a miss
pub fn exec_recon(entries: &BTreeMap<String, Entry>, view: &[Landing], earlier: &HashMap<String, Earlier>, tol: u64) -> (Value, bool) {
    let by_sig: HashMap<&str, &Landing> = view.iter().map(|l| (l.sig.as_str(), l)).collect();
    let (mut diff, mut matched) = (0i64, 0u64);
    let (mut diffs, mut provisional, mut refused_landed, mut not_counted, mut unknown, mut earlier_landed) = (Vec::new(), Vec::new(), Vec::new(), Vec::new(), Vec::new(), Vec::new());
    for l in view {
        let e = entries.get(&l.sig);
        // a refused bundle (its first final, kept whatever amended it later) that the chain or the executor shows landed
        if l.refused || l.fin == "not_landed_refused" {
            if l.landed || e.is_some() { refused_landed.push(json!({ "attempt": l.attempt, "sig": l.sig, "slot": e.map(|e| e.slot), "fee": e.map(|e| e.fee), "fin_now": l.fin })); }
            continue;
        }
        match (l.landed, e) {
            (true, Some(e)) => {
                matched += 1;
                let exec_net = l.round_trip - l.tip as i64 - l.fee as i64;
                let d = exec_net - e.trade_net;
                diff += d;
                if d != 0 || l.rt_unknown { diffs.push(json!({ "attempt": l.attempt, "sig": l.sig, "exec_net": exec_net, "trade_net": e.trade_net, "diff": d, "rt_unknown": l.rt_unknown })); }
            }
            (true, None) => provisional.push(json!({ "attempt": l.attempt, "sig": l.sig, "src": l.src, "fee_counted": l.fee })),
            (false, Some(e)) => not_counted.push(json!({ "attempt": l.attempt, "sig": l.sig, "fin": l.fin, "slot": e.slot })),
            (false, None) => {}
        }
    }
    for (sig, e) in entries {
        if !e.is_route() || by_sig.contains_key(sig.as_str()) { continue; }
        // an earlier segment's refused bundle that landed is a miss even when this segment's wallet stream found it as a
        // pre-run record (review WP-07 #6: across segments)
        if let Some(x) = earlier.get(sig).filter(|x| x.fin == "not_landed_refused") {
            refused_landed.push(json!({ "segment": x.segment, "attempt": x.attempt, "sig": sig, "slot": e.slot, "fee": e.fee }));
            continue;
        }
        if e.pre_run { continue; }
        match earlier.get(sig) {
            Some(x) => earlier_landed.push(json!({ "segment": x.segment, "attempt": x.attempt, "fin": x.fin, "sig": sig, "slot": e.slot, "trade_net": e.trade_net })),
            // an attempt of this segment's executor (the chain-fetch service knew its signature) whose final it no longer
            // keeps (FINALS_KEEP): compared while it was kept
            None if e.attempt.is_some() => {}
            None => unknown.push(json!({ "sig": sig, "slot": e.slot, "attempt": e.attempt, "trade_net": e.trade_net })),
        }
    }
    let ok = diff.unsigned_abs() <= tol && refused_landed.is_empty() && not_counted.is_empty() && unknown.is_empty();
    (json!({ "landings": matched, "diff": diff, "tolerance": tol, "ok": ok, "diffs": diffs, "provisional": provisional, "refused_landed": refused_landed,
        "not_counted": not_counted, "unknown_route_landings": unknown, "earlier_landed": earlier_landed }), ok)
}

// ------------------------------------------------------------------ earlier segments (the campaign)

/// A JSON-lines stream's records, tolerant of a torn last line (a segment that was killed): lines that do not parse
/// are skipped and counted
pub fn read_lines(dir: &Path, stream: &str) -> (Vec<Value>, usize) {
    let mut out = Vec::new();
    let mut bad = 0;
    for bytes in rec::read_files(dir, stream).unwrap_or_default() {
        for (i, l) in bytes.split(|b| *b == b'\n').filter(|l| !l.is_empty()).enumerate() {
            match serde_json::from_slice::<Value>(l) {
                Ok(v) if i == 0 && v["schema"].as_str().is_some_and(|s| s.starts_with("arbx.")) && v.get("file_seq").is_some() => {}
                Ok(v) => out.push(v),
                Err(_) => bad += 1,
            }
        }
    }
    (out, bad)
}

/// The campaign's start (the first good snapshot of its first segment): SOL + WSOL (`equity_stop`), the recoverable rent
/// and every token's amount and value, each on its own. The stops count the net spend since then (`Entry::spend`), so
/// the start anchors the stop value (`equity_stop` − net spend) and the floor (`equity_stop` − the test budget)
#[derive(Clone, Debug, PartialEq)]
pub struct Start { pub t_ns: u64, pub slot: u64, pub segment: String, pub equity_stop: i64, pub equity_total: i64, pub sol: u64, pub wsol: u64, pub rent_recoverable: u64,
    pub tokens: BTreeMap<String, u128>, pub token_value: u64 }

impl Start {
    fn of(s: &Snapshot, segment: &str) -> Start {
        Start { t_ns: s.t_ns, slot: s.slot, segment: segment.to_string(), equity_stop: s.equity_stop(), equity_total: s.equity_total(), sol: s.sol, wsol: s.wsol,
            rent_recoverable: s.rent_recoverable, tokens: s.token_amounts(), token_value: s.token_value }
    }
    pub fn json(&self) -> Value {
        json!({ "basis": "sol_wsol", "stop_basis": STOP_BASIS, "t_ns": self.t_ns, "slot": self.slot, "segment": self.segment, "equity_stop": self.equity_stop,
            "equity_total": self.equity_total, "sol": self.sol, "wsol": self.wsol, "rent_recoverable": self.rent_recoverable,
            "tokens": self.tokens.iter().map(|(m, a)| (m.clone(), json!(a.to_string()))).collect::<Map<_, _>>(), "token_value": self.token_value })
    }
}

/// what the stops measure (status, campaign.json; review WP-07 #4)
pub const STOP_BASIS: &str = "net_spend";

/// What a campaign's segments say about money, read from their files: the campaign's start, its test budget
/// (campaign.json), the net spend since the start (each signature once) and the stop value's series (the start's SOL +
/// WSOL less the net spend, at each entry: the owner's transfers move neither), the routes' token changes (the token
/// floors), the signatures already in a ledger, the open, expired or refused attempts of the last segments (a later
/// landing joins them by signature), the totals, the balances now, the reconciliation misses, and the window the next
/// segment reconciles (the last snapshot, or the start of a stop reconciliation left undecided, with the entries after it)
#[derive(Clone, Debug, Default)]
pub struct History {
    pub series: Series,
    pub start: Option<Start>,
    pub test_budget: Option<u64>,
    pub known_sigs: HashSet<String>,
    pub earlier: HashMap<String, Earlier>,
    pub segments_read: Vec<String>,
    pub totals: Totals,
    pub per_segment: Vec<(String, Totals)>,
    /// the net spend since the start (= `totals.net_spend()`) and the routes' token changes since then
    pub spent: i64,
    pub route_tokens: BTreeMap<String, i128>,
    /// SOL + WSOL and the token amounts now as the files show them (the last snapshot and the entries after it; the
    /// owner's transfers included: informational, never a stop)
    pub equity_stop_now: Option<i64>,
    pub equity_total_now: Option<i64>,
    pub tokens_now: BTreeMap<String, u128>,
    pub last_snapshot: Option<Snapshot>,
    /// lines that did not parse
    pub bad_lines: usize,
    /// reconciliation misses in the segments' recon.jsonl (final ones; a stop's undecided one is not)
    pub recon_misses: Vec<(String, u64)>,
    /// the owner's transfers since the start: (segment, sig, category, lamports)
    pub owner_transfers: Vec<(String, String, &'static str, i64)>,
    /// the window the next segment reconciles first (review WP-07 #7, #9): from the last good snapshot (or the start of
    /// the last segment's stop reconciliation it could not decide), with the earlier segments' entries after it
    pub prev_window: Option<PrevWindow>,
    /// a stop reconciliation of the last segment left undecided (`final: false`), the next segment decides it
    pub undecided: Option<(String, u64)>,
    /// integration (FT-000 x WP-07): the newest earlier ledger entry (sig, slot) at or before `prev_window`'s first
    /// snapshot: where a wallet cursor may start at the latest ([`bound_wallet_cursor`])
    pub window_cursor: Option<(String, u64)>,
}

/// Integration (FT-000 x WP-07): the wallet cursor a campaign's segment may start from. FT-000's cursor
/// (`wallet-cursor.json`, the newest signature the previous segment recorded) makes source (d) list only newer
/// signatures. This ledger reconciles the window between segments from the previous segment's last good snapshot (or
/// the start of its undecided stop reconciliation) with the earlier ledgers' entries and this segment's own records of
/// the span. A record the previous segment wrote to wallet.jsonl but never entered in its ledger (at its end, or killed)
/// is in neither: a cursor past the window's start would keep it from being listed again, and a residual under the
/// tolerance (a failed landing's fee) would hide it from the net spend. So the cursor never passes the window's start:
/// a later one is moved back to the newest earlier ledger entry at or before it (`History::window_cursor`; what it lists
/// again the ledger finds `dup` or counts), or dropped (the last hour is listed, as without a cursor) when there is none.
/// Without a window (no good snapshot yet in the campaign) the cursor stands: the campaign's start is this segment's
/// first snapshot, and nothing before it counts. Returns the cursor and what was done: `kept`, `moved_back`, `dropped`,
/// `none`
pub fn bound_wallet_cursor(cursor: Option<(String, u64)>, h: &History) -> (Option<(String, u64)>, &'static str) {
    let Some(c) = cursor else { return (None, "none") };
    let Some(w) = &h.prev_window else { return (Some(c), "kept") };
    if c.1 <= w.from.slot { return (Some(c), "kept"); }
    match &h.window_cursor { Some(e) => (Some(e.clone()), "moved_back"), None => (None, "dropped") }
}

/// The window between segments: its first snapshot, the segment it is from, and the entries of the earlier segments that
/// landed after it
#[derive(Clone, Debug, Default)]
pub struct PrevWindow { pub from: Snapshot, pub segment: String, pub entries: Vec<Entry>, pub undecided: bool }

impl History {
    /// the stop value now: the start's SOL + WSOL less the net spend since
    pub fn stop_value_now(&self) -> Option<i64> { self.start.as_ref().map(|s| s.equity_stop - self.spent) }
    /// the token amounts the token floors watch: the start's, moved by routes only
    pub fn stop_tokens_now(&self) -> BTreeMap<String, u128> { stop_tokens(self.start.as_ref(), &self.route_tokens) }
}

/// the token amounts the token floors watch: each start amount moved by the routes' token changes since (the owner's
/// own token transfers are not the bot's)
pub fn stop_tokens(start: Option<&Start>, route: &BTreeMap<String, i128>) -> BTreeMap<String, u128> {
    let Some(s) = start else { return BTreeMap::new() };
    s.tokens.iter().map(|(m, a)| (m.clone(), (*a as i128 + route.get(m).copied().unwrap_or(0)).max(0) as u128)).collect()
}

/// the segment directories of a campaign, oldest first (meta.json `run.started_ns`, else the name)
pub fn segments(dir: &Path) -> Vec<(String, std::path::PathBuf)> {
    let mut v: Vec<(u64, String, std::path::PathBuf)> = std::fs::read_dir(dir).into_iter().flatten().flatten().filter(|e| e.path().is_dir()).filter_map(|e| {
        let p = e.path();
        let name = e.file_name().to_string_lossy().into_owned();
        let has = p.join("meta.json").exists() || p.join("snapshots.jsonl").exists() || !rec::stream_files(&p, "ledger").is_empty();
        if !has { return None; }
        let started = std::fs::read(p.join("meta.json")).ok().and_then(|b| serde_json::from_slice::<Value>(&b).ok()).and_then(|m| m["run"]["started_ns"].as_u64()).unwrap_or(0);
        Some((started, name, p))
    }).collect();
    v.sort();
    v.into_iter().map(|x| (x.1, x.2)).collect()
}

/// a campaign.json test budget, at most the owner's hard cap (a file edited past it is read at the cap)
fn budget_of(dir: &Path) -> Option<u64> {
    std::fs::read(dir.join("campaign.json")).ok().and_then(|b| serde_json::from_slice::<Value>(&b).ok())
        .and_then(|c| c["budget"]["test_budget_lamports"].as_u64()).map(|b| b.min(crate::config::TEST_BUDGET_HARD_CAP))
}

/// Read a campaign's money history (`exclude`: the running segment's own directory). Points older than `keep_ns`
/// before `now` leave the series (the value carried into the window stays)
pub fn history(dir: &Path, exclude: Option<&str>, now: u64, keep_ns: u64) -> History {
    let segs: Vec<(String, std::path::PathBuf)> = segments(dir).into_iter().filter(|(n, _)| Some(n.as_str()) != exclude).collect();
    history_of(segs, budget_of(dir), now, keep_ns)
}

/// `history` over one run directory that is not a campaign (a manual `arbx run`: the budget state's spend of it)
pub fn history_of_run(dir: &Path, now: u64) -> History {
    let name = dir.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
    history_of(vec![(name, dir.to_path_buf())], None, now, DAY_NS)
}

fn history_of(segs: Vec<(String, std::path::PathBuf)>, test_budget: Option<u64>, now: u64, keep_ns: u64) -> History {
    let mut h = History { test_budget, ..Default::default() };
    let n = segs.len();
    // the balances carried from segment to segment (informational): a segment's own snapshot resets them, its entries
    // after the last snapshot's slot move them
    let mut cur: Option<(u64, i64, BTreeMap<String, i128>)> = None;
    // entries read before the start was known (a first segment that recorded before its first snapshot)
    let mut early: Vec<(u64, Entry, String)> = Vec::new();
    // the last good snapshot and every entry read (the window the next segment reconciles)
    let mut last_good: Option<(Snapshot, String)> = None;
    let mut all: Vec<Entry> = Vec::new();
    let mut undecided_from: Option<(u64, String, u64)> = None;
    let mut snaps_by_slot: BTreeMap<u64, (Snapshot, String)> = BTreeMap::new();
    for (k, (name, p)) in segs.into_iter().enumerate() {
        let (snaps, b1) = read_lines(&p, "snapshots");
        let (lines, b2) = read_lines(&p, "ledger");
        let (recons, b3) = read_lines(&p, "recon");
        h.bad_lines += b1 + b2 + b3;
        h.segments_read.push(name.clone());
        for r in &recons {
            if r["ok"] == json!(false) && r["final"] != json!(false) { h.recon_misses.push((name.clone(), r["t_ns"].as_u64().unwrap_or(0))); }
            // the window between segments decides an undecided one (passed, or a miss counted above)
            if r["between_segments"] == json!(true) { undecided_from = None; }
            // a stop reconciliation left undecided: the next segment decides it again, from its first snapshot
            if r["ok"] == json!(false) && r["final"] == json!(false) {
                if let Some(s) = r["from"]["slot"].as_u64() { undecided_from = Some((s, name.clone(), r["t_ns"].as_u64().unwrap_or(0))); }
            }
        }
        // the snapshots and the entries, in the order they were taken / reached the engine
        let mut ev: Vec<(u64, u8, Value)> = snaps.into_iter().filter(|s| s["slot_mismatch"] != json!(true) && s["error"].is_null()).map(|s| (s["t_ns"].as_u64().unwrap_or(0), 0u8, s))
            .chain(lines.into_iter().filter(|l| l["dup"] != json!(true)).map(|l| (l["t_ns"].as_u64().unwrap_or(0), 1u8, l))).collect();
        ev.sort_by_key(|x| (x.0, x.1));
        let mut seg_tot = Totals::default();
        for (t, kind, v) in ev {
            if kind == 0 {
                let Some(s) = Snapshot::from_json(&v) else { continue };
                if h.start.is_none() {
                    let st = Start::of(&s, &name);
                    h.series.push(t, st.equity_stop);
                    h.start = Some(st);
                    // what was read before the start: counted when it landed after it
                    for (te, e, seg) in std::mem::take(&mut early) {
                        if h.start.as_ref().is_some_and(|st| e.slot > st.slot) { count_entry(&mut h, &mut seg_tot, &e, te, &seg); }
                    }
                }
                cur = Some((s.slot, s.equity_stop(), s.token_amounts().into_iter().map(|(m, a)| (m, a as i128)).collect()));
                h.equity_total_now = Some(s.equity_total());
                snaps_by_slot.insert(s.slot, (s.clone(), name.clone()));
                last_good = Some((s.clone(), name.clone()));
                h.last_snapshot = Some(s);
            } else {
                let Some(e) = Entry::from_json(&v) else { continue };
                if !h.known_sigs.insert(e.sig.clone()) { continue; }
                match &h.start {
                    Some(st) if e.slot > st.slot => count_entry(&mut h, &mut seg_tot, &e, t, &name),
                    Some(_) => {}
                    None => early.push((t, e.clone(), name.clone())),
                }
                if let Some(c) = cur.as_mut().filter(|c| e.slot > c.0) {
                    c.1 += e.stop_delta();
                    for (m, tv) in &e.tokens { *c.2.entry(m.clone()).or_insert(0) += tv.amount; }
                    if let Some(x) = h.equity_total_now.as_mut() { *x += e.equity_delta; }
                }
                all.push(e);
            }
        }
        if let Some(c) = &cur { h.equity_stop_now = Some(c.1); h.tokens_now = c.2.iter().map(|(m, a)| (m.clone(), (*a).max(0) as u128)).collect(); }
        h.per_segment.push((name.clone(), seg_tot));
        // the last two segments' attempts that did not land as far as they knew (a later landing joins them); an attempt
        // whose first final was a refusal stays refused, whatever amended it (review WP-07 #6)
        if k + 2 >= n {
            let (outs, b4) = read_lines(&p, "outcomes");
            h.bad_lines += b4;
            for o in outs {
                let (Some(sig), Some(a), Some(fin)) = (o["sig"].as_str(), o["attempt"].as_u64(), o["final"].as_str()) else { continue };
                if o["refused_then_landed"] == json!(true) {
                    h.recon_misses.push((name.clone(), o["t_ns"].as_u64().unwrap_or(0)));
                    h.earlier.insert(sig.to_string(), Earlier { segment: name.clone(), attempt: a, fin: "not_landed_refused".into() });
                    continue;
                }
                if h.earlier.get(sig).is_some_and(|e| e.fin == "not_landed_refused") { continue; }
                if matches!(fin, "unsettled" | "not_landed_expired" | "not_landed_refused") { h.earlier.insert(sig.to_string(), Earlier { segment: name.clone(), attempt: a, fin: fin.into() }); }
                else { h.earlier.remove(sig); }
            }
        }
    }
    // the window the next segment reconciles: from the undecided stop reconciliation's first snapshot, else the last
    // good snapshot
    let from = undecided_from.as_ref().and_then(|(slot, _, _)| snaps_by_slot.get(slot).cloned()).or(last_good);
    if let Some((s, seg)) = from {
        h.window_cursor = all.iter().filter(|e| e.slot <= s.slot).max_by_key(|e| e.slot).map(|e| (e.sig.clone(), e.slot));
        let entries = all.into_iter().filter(|e| e.slot > s.slot).collect();
        h.prev_window = Some(PrevWindow { from: s, segment: seg, entries, undecided: undecided_from.is_some() });
    }
    h.undecided = undecided_from.map(|(_, seg, t)| (seg, t));
    h.series.trim(now, keep_ns);
    h
}

/// one entry after the campaign's start into the history's totals, spend, stop series and route tokens
fn count_entry(h: &mut History, seg_tot: &mut Totals, e: &Entry, t: u64, seg: &str) {
    seg_tot.add(e);
    h.totals.add(e);
    h.spent += e.spend();
    if e.is_route() { for (m, tv) in &e.tokens { *h.route_tokens.entry(m.clone()).or_insert(0) += tv.amount; } }
    if let Some((c, l)) = e.owner_transfer() { h.owner_transfers.push((seg.to_string(), e.sig.clone(), c, l)); }
    if let Some(s) = &h.start { h.series.push(t, s.equity_stop - h.spent); }
}

/// spend.json (docs/field-tests/BUDGET.md's numbers for one campaign): per segment and in all, from the segments' ledgers
/// (each signature once), with the test budget and what is left of it
pub fn spend_json(dir: &Path, campaign: &str, t_ns: u64) -> Value {
    let h = history(dir, None, t_ns, DAY_NS);
    let total = h.totals;
    let budget = h.test_budget;
    let date = utc_date(t_ns);
    let row = format!("| {date} | {campaign} | {} | {} | {} | {} | {} | {} |", total.fees(), total.tips, total.rent_locked + total.rent_nonrecoverable, total.rent_reclaimed,
        total.trade_pnl, total.net_spend());
    json!({ "schema": "arbx.spend/1.1", "campaign": campaign, "t_ns": t_ns, "segments": h.per_segment.iter().map(|(n, t)| { let mut v = t.json(); v["segment"] = json!(n); v }).collect::<Vec<_>>(),
        "total": total.json(), "budget": { "test_budget_lamports": budget, "net_spend": total.net_spend(), "remaining": budget.map(|b| b as i64 - total.net_spend()) },
        "equity": { "start": h.start.as_ref().map(Start::json), "equity_stop_now": h.equity_stop_now, "equity_total_now": h.equity_total_now, "stop_value_now": h.stop_value_now() },
        "owner_transfers": h.owner_transfers.iter().map(|(s, sig, c, l)| json!({ "segment": s, "sig": sig, "category": c, "lamports": l })).collect::<Vec<_>>(),
        "budget_md_columns": ["Date (UTC)", "Test", "Fees", "Tips", "Rent locked", "Rent recovered", "Trading P&L", "Net spend"], "budget_md_row": row,
        "note": "Net spend = fees + tips + non-recoverable rent - trading P&L (the routes' change of SOL + WSOL and recoverable rent plus what they paid; a token left behind at 0); the owner's transfers are not in it; rent locked is recoverable rent plus the non-recoverable part; every figure from the ledger (chain data)" })
}

// ------------------------------------------------------------------ the segment's ledger

/// What the executor reads of the ledger (`Exec::set_money`; the engine journals it in every decision-point record that
/// differs from the last, and a replay's offline executor applies it: review WP-07 #1): whether the start equity is known
/// (live and canary send nothing until it is, `equity_unknown`), whether the view is stale (`equity_stale`: nothing is
/// sent until a fresh one, review WP-07 #3), the liquid SOL (native + WSOL) and WSOL now (the bankroll cap), the native
/// SOL, the recoverable rent now (the rent cap)
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct MoneyView { pub equity_known: bool, pub stale: bool, pub liquid: Option<u64>, pub wsol: Option<u64>, pub native: Option<u64>, pub rent_recoverable: Option<u64> }

impl MoneyView {
    /// the decision-point record's `money`
    pub fn json(&self) -> Value {
        json!({ "equity_known": self.equity_known, "stale": self.stale, "liquid": self.liquid, "wsol": self.wsol, "native": self.native, "rent_recoverable": self.rent_recoverable })
    }
    /// read back (None: no `money` in the record, a recording made before WP-07)
    pub fn from_json(v: &Value) -> Option<MoneyView> {
        if !v.is_object() { return None; }
        Some(MoneyView { equity_known: v["equity_known"].as_bool()?, stale: v["stale"].as_bool().unwrap_or(false), liquid: v["liquid"].as_u64(), wsol: v["wsol"].as_u64(),
            native: v["native"].as_u64(), rent_recoverable: v["rent_recoverable"].as_u64() })
    }
}

/// What the ledger reads of the rest of the process at a tick (the engine hands it over): when the oldest landing the
/// executor found by a status check, whose wallet record has not come, became final (engine time), and how many wallet
/// records the chain-fetch service gave up on so far (None: no service). Neither is journaled: what they change reaches a
/// decision only through the money view and the gate, which are
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct TickIn { pub provisional_since: Option<u64>, pub wallet_gave_up: Option<u64> }

/// the balances now: the last good snapshot and the entries landed after it
#[derive(Clone, Debug, Default)]
struct Cur { slot: u64, sol: i64, wsol: i64, rent: i64, tokens: BTreeMap<String, i128> }

/// where a reconciliation window starts: one of this segment's snapshots, or (between segments, review WP-07 #7, #9) an
/// earlier segment's, with the earlier entries after it
#[derive(Clone, Debug)]
enum From { Own(usize), Earlier(Box<PrevWindow>) }

/// A reconciliation waiting to be decided. `at_stop`: the stop's (a snapshot residual still unexplained after its search
/// and grace is written `final: false`: the next segment decides it again from its own records)
#[derive(Clone, Debug)]
struct Pending { from: From, to: usize, due: u64, searched: bool, unexplained: Vec<Value>, at_stop: bool }

/// the background runtime the snapshots run on, and the way back to the engine
struct Io { rpc: Rpc, rt: tokio::runtime::Handle, back: crossbeam_channel::Sender<Event> }

/// The segment's ledger (owned by the engine; every input reaches it journaled, at engine time)
pub struct Ledger {
    pub cfg: LedgerCfg,
    wallet: Pk,
    pub sup: Supervisor,
    rec: Rec,
    io: Option<Io>,
    candidates: BTreeSet<Pk>,
    pub entries: BTreeMap<String, Entry>,
    known_earlier: HashSet<String>,
    earlier: HashMap<String, Earlier>,
    pub snaps: Vec<Snapshot>,
    /// the last snapshot a reconciliation may start from
    last_good: Option<usize>,
    pending: Vec<Pending>,
    /// snapshots: one in flight, why the next one is wanted, when the periodic one is due, a retry after a failure
    inflight: bool,
    want: Option<&'static str>,
    next_periodic: u64,
    retry_at: Option<u64>,
    stop_asked: bool,
    stop_done: bool,
    started: bool,
    t_start: u64,
    /// the stop value over time (the campaign's start SOL + WSOL less the net spend since; campaign-wide: the earlier
    /// segments' points of the last 25 h, then this segment's)
    pub series: Series,
    /// the campaign's start (from the earlier segments, else this segment's first good snapshot)
    pub start: Option<Start>,
    start_src: &'static str,
    test_budget: Option<u64>,
    budget_left: Option<u64>,
    floor_arg: Option<i64>,
    cur: Option<Cur>,
    /// this segment's totals (its entries after the campaign's start), the earlier segments' net spend, the routes'
    /// token changes since the start (the earlier segments' and this one's)
    pub totals: Totals,
    prev: Totals,
    spent_before: i64,
    route_tokens: BTreeMap<String, i128>,
    /// the stop value at this segment's first snapshot (its own floor candidate: that less what is left of the budget)
    own_start_value: Option<i64>,
    stranded: BTreeMap<String, u64>,
    recon_seq: u64,
    pub recon_misses: u32,
    last_recon: Option<(u64, bool)>,
    unreconciled_now: i64,
    pub counts: BTreeMap<&'static str, u64>,
    entries_seen_delta: u64,
    // ---- the money view's freshness (review WP-07 #3)
    /// engine time of the last good snapshot; snapshots failed (or mismatched) in a row since; a wallet-record failure
    /// (since when, why) a snapshot asked for after it clears; the chain-fetch give-ups last read
    last_good_t: Option<u64>,
    fail_run: u32,
    suspect: Option<(u64, String)>,
    gave_up_seen: Option<u64>,
    /// why the money view is stale now (None: fresh), and which rule says so (`age`, `failures`, `record_wait`, `gave_up`:
    /// a change of rule is a new event, a change of the age it reports is not)
    pub stale: Option<String>,
    stale_kind: Option<&'static str>,
    // ---- between segments (review WP-07 #7, #9)
    prev_window: Option<PrevWindow>,
    undecided: Option<(String, u64)>,
}

impl Ledger {
    pub fn new(cfg: LedgerCfg, sup_cfg: crate::config::SupervisorCfg, wallet: Pk, rec: Rec, segment: &str) -> Ledger {
        let sup = Supervisor::new(sup_cfg, rec.clone(), segment);
        Ledger { cfg, wallet, sup, rec, io: None, candidates: BTreeSet::new(), entries: BTreeMap::new(), known_earlier: HashSet::new(), earlier: HashMap::new(),
            snaps: Vec::new(), last_good: None, pending: Vec::new(), inflight: false, want: None, next_periodic: 0, retry_at: None, stop_asked: false, stop_done: false,
            started: false, t_start: 0, series: Series::new(), start: None, start_src: "segment", test_budget: None, budget_left: None, floor_arg: None, cur: None,
            totals: Totals::default(), prev: Totals::default(), spent_before: 0, route_tokens: BTreeMap::new(), own_start_value: None, stranded: BTreeMap::new(),
            recon_seq: 0, recon_misses: 0, last_recon: None, unreconciled_now: 0, counts: BTreeMap::new(), entries_seen_delta: 0, last_good_t: None, fail_run: 0,
            suspect: None, gave_up_seen: None, stale: None, stale_kind: None, prev_window: None, undecided: None }
    }

    /// The ledger and its stops as `arbx run` assembles them (review WP-07 #2: the wiring that arms them is tested here):
    /// bound to the run's gate and stop path; the stop rules act only in a run that sends (`sends`: live, canary; a shadow
    /// or dry run records what would have fired); the campaign so far (`hist`), the budget (`[supervisor]
    /// test_budget_lamports`, what a campaign or the budget state leaves, `--equity-floor`)
    #[allow(clippy::too_many_arguments)]
    pub fn for_run(cfg: &crate::config::Config, wallet: Pk, rec: Rec, segment: &str, sends: bool, gate: Arc<SendGate>, stopper: Arc<Stopper>, hist: History,
        budget_left: Option<u64>, floor: Option<i64>) -> Ledger {
        let mut l = Ledger::new(cfg.ledger.clone(), cfg.supervisor.clone(), wallet, rec, segment);
        l.bind(gate, stopper);
        l.sup.acts = sends;
        l.set_campaign(hist, (cfg.supervisor.test_budget_lamports > 0).then_some(cfg.supervisor.test_budget_lamports), budget_left, floor);
        l
    }

    /// the snapshots' RPC (role `ledger`), the background runtime, the engine's channel (INPUT 13 comes back on it)
    pub fn set_io(&mut self, rpc: Rpc, rt: tokio::runtime::Handle, back: crossbeam_channel::Sender<Event>) { self.io = Some(Io { rpc, rt, back }); }

    /// the run's SendGate and stop path (the supervisor acts on them)
    pub fn bind(&mut self, gate: Arc<SendGate>, stopper: Arc<Stopper>) { self.sup.bind(gate, stopper); }

    /// accounts every snapshot reads besides the wallet (the token accounts held at boot, `[ledger] extra_mints`' ATAs,
    /// nonce accounts, lookup tables, the PumpSwap accumulator)
    pub fn add_candidates(&mut self, keys: impl IntoIterator<Item = Pk>) { for k in keys { if k != self.wallet { self.candidates.insert(k); } } }

    /// The campaign so far (`history` of the earlier segments) and this segment's budget: `test_budget` (campaign.json,
    /// else `[supervisor] test_budget_lamports`), `budget_left` (`--budget-left`: what the campaign or the budget state
    /// leaves), `floor` (`--equity-floor`); each budget at most the owner's hard cap (review WP-07 #8). The floor, on the
    /// stop value, is the highest of: the campaign's start − the test budget, this segment's start − what is left, the
    /// floor given
    pub fn set_campaign(&mut self, h: History, test_budget: Option<u64>, budget_left: Option<u64>, floor: Option<i64>) {
        let cap = crate::config::TEST_BUDGET_HARD_CAP;
        if h.start.is_some() { self.start_src = "campaign"; }
        self.start = h.start;
        self.series = h.series;
        self.known_earlier = h.known_sigs;
        self.earlier = h.earlier;
        self.spent_before = h.spent;
        self.route_tokens = h.route_tokens;
        self.prev_window = h.prev_window;
        self.undecided = h.undecided;
        self.test_budget = h.test_budget.or(test_budget).filter(|b| *b > 0).map(|b| b.min(cap));
        self.budget_left = budget_left.map(|b| b.min(cap));
        self.floor_arg = floor;
        self.apply_limits();
    }

    fn count(&mut self, k: &'static str) { *self.counts.entry(k).or_default() += 1; }

    /// the floor and the token floors from the start and the budget
    fn apply_limits(&mut self) {
        let a = self.start.as_ref().zip(self.test_budget).map(|(s, b)| s.equity_stop - b as i64);
        let b = self.own_start_value.zip(self.budget_left).map(|(v, b)| v - b as i64);
        self.sup.limits.floor = [a, b, self.floor_arg].into_iter().flatten().max();
        if let Some(s) = &self.start { let t = s.tokens.clone(); self.sup.limits.set_token_floors(&t); }
    }

    /// what the executor reads
    pub fn view(&self) -> MoneyView {
        match &self.cur {
            Some(c) => MoneyView { equity_known: true, stale: self.stale.is_some(), liquid: Some((c.sol + c.wsol).max(0) as u64), wsol: Some(c.wsol.max(0) as u64),
                native: Some(c.sol.max(0) as u64), rent_recoverable: Some(c.rent.max(0) as u64) },
            None => MoneyView::default(),
        }
    }

    /// SOL + WSOL now as the money view has it (the last snapshot and the entries after it; the owner's transfers
    /// included): informational and the bankroll's, never a stop's
    pub fn equity_stop(&self) -> Option<i64> { self.cur.as_ref().map(|c| c.sol + c.wsol) }

    /// the net spend since the campaign's start (the earlier segments' and this one's)
    pub fn spent(&self) -> i64 { self.spent_before + self.totals.net_spend() }

    /// The stop value now (review WP-07 #4): the campaign's start SOL + WSOL less the net spend since. A deposit or a
    /// withdrawal moves neither; the floor is the start less the budget, the drop caps are on its series
    pub fn stop_value(&self) -> Option<i64> { self.start.as_ref().map(|s| s.equity_stop - self.spent()) }

    /// the token amounts the token floors watch (the start's, moved by routes only)
    pub fn stop_tokens(&self) -> BTreeMap<String, u128> { stop_tokens(self.start.as_ref(), &self.route_tokens) }

    fn tokens_now(&self) -> BTreeMap<String, u128> {
        self.cur.as_ref().map(|c| c.tokens.iter().map(|(m, a)| (m.clone(), (*a).max(0) as u128)).collect()).unwrap_or_default()
    }

    /// INPUT 7 `wallet_tx` at engine time `t`: its `ledger` (the raw fields the chain-fetch service computed) valued and
    /// written to ledger.jsonl, once per signature (a signature an earlier segment's ledger has is left out: `dup`).
    /// `round_trip`: the executor's on-chain round trip of the attempt (a win's check). Returns the entry
    pub fn on_wallet_tx(&mut self, d: &Value, t: u64, value: Valuer, round_trip: Option<i64>) -> Option<Entry> {
        let sig = d["sig"].as_str()?.to_string();
        let Some(raw) = Raw::from_json(&d["ledger"]) else { self.count("raw_missing"); return None };
        if self.entries.contains_key(&sig) { self.count("dup_segment"); return self.entries.get(&sig).cloned(); }
        let pre_run = d["pre_run"].as_bool().unwrap_or(false);
        let mut e = entry(&raw, &Head { sig: &sig, slot: d["slot"].as_u64().unwrap_or(0), idx: d["idx"].as_u64(), t_ns: t, attempt: d["attempt"].as_u64(), pre_run },
            self.cfg.token_haircut, value);
        if let Some(rt) = round_trip.filter(|_| e.is_route() && e.ok) { e.check = Some(json!({ "delivered_round_trip": rt, "diff": e.trade_gross - rt })); }
        if self.known_earlier.contains(&sig) {
            // an earlier segment's ledger has it (getSignaturesForAddress reads the last hour): written once, marked
            self.count("dup_campaign");
            let mut line = e.json();
            line["dup"] = json!(true);
            self.rec.json(rec::LEDGER, line);
            return Some(e);
        }
        self.rec.json(rec::LEDGER, e.json());
        self.entries_seen_delta += 1;
        // the snapshots read the token accounts it touched from now on
        for (a, _) in &raw.token_accounts { if *a != self.wallet { self.candidates.insert(*a); } }
        for c in e.created.iter().chain(e.closed.iter()) { self.candidates.insert(c.acct); }
        // the money view, when it landed after the last snapshot
        if let Some(c) = self.cur.as_mut().filter(|c| e.slot > c.slot) {
            c.sol += e.wallet_sol;
            c.wsol += e.wsol;
            c.rent += e.rent_locked as i64 - e.rent_reclaimed as i64;
            for (m, tv) in &e.tokens { *c.tokens.entry(m.clone()).or_insert(0) += tv.amount; }
        }
        for (m, _) in &e.stranded { self.stranded.entry(m.clone()).or_insert(t); }
        self.entries.insert(sig, e.clone());
        // the stops: what landed after the campaign's start (nothing is sent before it)
        if self.start.as_ref().is_some_and(|s| e.slot > s.slot) { self.count_stop(&e, t); }
        Some(e)
    }

    /// one entry after the campaign's start: its spend into the totals and the stop series, a route's token changes into
    /// the token floors' amounts; the owner's own transfer is recorded and alerted (`owner_transfer`), never a stop
    fn count_stop(&mut self, e: &Entry, t: u64) {
        self.totals.add(e);
        if e.is_route() { for (m, tv) in &e.tokens { *self.route_tokens.entry(m.clone()).or_insert(0) += tv.amount; } }
        if let Some(v) = self.stop_value() { self.series.push(t, v); }
        if let Some((cat, lamports)) = e.owner_transfer() {
            self.count("owner_transfer");
            self.sup.owner_transfer(t, json!({ "sig": e.sig, "slot": e.slot, "kind": e.kind, "category": cat, "lamports": lamports, "fee": e.fee,
                "equity_stop_now": self.equity_stop(), "stop_value_now": self.stop_value() }));
        }
    }

    /// A refused bundle that landed (review WP-07 #6): the executor amended an attempt it had finalized
    /// `not_landed_refused` with its landing. A broken invariant (WP-05's refusal semantics), raised at once: recon.jsonl
    /// (`kind` `refused_bundle_landed`, a final miss), events.jsonl `refused_bundle_landed`, the gate in shadow for the
    /// rest of the segment (`reconcile_miss`), a Critical notice
    pub fn on_refused_landed(&mut self, t: u64, landed: Vec<Value>) {
        if landed.is_empty() { return; }
        self.count("refused_bundle_landed");
        self.recon_seq += 1;
        self.recon_misses += 1;
        let line = json!({ "t_ns": t, "seq": self.recon_seq, "kind": "refused_bundle_landed", "refused_landed": landed, "ok": false, "final": true, "action": "shadow" });
        self.rec.json(rec::RECON, line);
        self.rec.event("refused_bundle_landed", "ledger", None, json!(landed));
        self.last_recon = Some((t, false));
        self.sup.reconcile_miss_at(t, json!({ "why": "a refused bundle landed", "refused_landed": landed }), Level::Critical);
    }

    /// INPUT 13 at engine time `t`: a snapshot's answer (`what` `snapshot`) or the window search of an unexplained
    /// reconciliation (`what` `sigs`)
    pub fn on_input(&mut self, d: &Value, t: u64, value: Valuer) {
        match d["what"].as_str() {
            Some("sigs") => self.on_sigs(d, t),
            _ => self.on_snapshot(d, t, value),
        }
    }

    /// a snapshot that failed or whose answers' slots differed: the next one `snapshot_retry_s` later (the periodic one
    /// waits for it too, so a failing provider is not asked again at every tick)
    fn retry_later(&mut self, t: u64) {
        let at = t + self.cfg.snapshot_retry_s * 1_000_000_000;
        self.retry_at = Some(at);
        if self.next_periodic > 0 { self.next_periodic = self.next_periodic.max(at); }
    }

    /// how long after a good snapshot the next periodic one is asked for: `snapshot_min`, less a lead (a quarter of the
    /// period, at most 30 s) so that a provider that answers refreshes the view before it is `max_view_age_s` old
    fn periodic_ns(&self) -> u64 { let p = self.cfg.snapshot_min * 60_000_000_000; p - (p / 4).min(30_000_000_000) }

    fn on_snapshot(&mut self, d: &Value, t: u64, value: Valuer) {
        self.inflight = false;
        let why = d["why"].as_str().unwrap_or("");
        let s = match Snapshot::parse(d, &self.wallet, self.cfg.token_haircut, value, t) {
            Ok(s) => s,
            Err(e) => {
                self.count("snapshot_failed");
                self.fail_run += 1;
                self.retry_later(t);
                if why == "stop" { self.stop_done = true; }
                self.rec.event("snapshot_failed", "ledger", None, json!({ "why": why, "error": crate::rpc::scrub(&e), "retry_s": self.cfg.snapshot_retry_s, "failed_in_a_row": self.fail_run }));
                return;
            }
        };
        self.count("snapshot");
        self.retry_at = None;
        if why == "stop" { self.stop_done = true; }
        self.rec.json(rec::SNAPSHOTS, s.json());
        if s.slot_mismatch {
            self.count("snapshot_slot_mismatch");
            self.fail_run += 1;
            self.rec.event("snapshot_slot_mismatch", "ledger", None, json!({ "why": why, "attempts": d["attempts"], "slots": d["answers"].as_array().map(|a| a.iter().map(|x| x["slot"].clone()).collect::<Vec<_>>()) }));
            // not reconciled, not a balance (F34): taken again after `snapshot_retry_s`
            self.retry_later(t);
            self.snaps.push(s);
            return;
        }
        self.rec.event("snapshot", "ledger", None, json!({ "why": why, "slot": s.slot, "equity_stop": s.equity_stop(), "equity_total": s.equity_total(), "sol": s.sol, "wsol": s.wsol }));
        for k in s.accounts() { self.candidates.insert(k); }
        // the money view: the snapshot, and the entries that reached the ledger before it but landed after its slot
        let mut c = Cur { slot: s.slot, sol: s.sol as i64, wsol: s.wsol as i64, rent: s.rent_recoverable as i64,
            tokens: s.token_amounts().into_iter().map(|(m, a)| (m, a as i128)).collect() };
        for e in self.entries.values().filter(|e| e.slot > s.slot) {
            c.sol += e.wallet_sol;
            c.wsol += e.wsol;
            c.rent += e.rent_locked as i64 - e.rent_reclaimed as i64;
            for (m, tv) in &e.tokens { *c.tokens.entry(m.clone()).or_insert(0) += tv.amount; }
        }
        let first = self.cur.is_none();
        self.cur = Some(c);
        // fresh: the view is the chain's again (a wallet-record failure is cleared by a snapshot asked for after it)
        self.last_good_t = Some(t);
        self.fail_run = 0;
        let asked = d["t_req_ns"].as_u64().unwrap_or(t);
        if self.suspect.as_ref().is_some_and(|(since, _)| asked >= *since) { self.suspect = None; }
        let idx = self.snaps.len();
        self.snaps.push(s);
        let grace = self.cfg.recon_grace_s * 1_000_000_000;
        if first {
            if self.start.is_none() {
                // the campaign starts here: its start read from the chain; what reached the ledger before it and landed
                // after it counts from now
                let st = Start::of(&self.snaps[idx], &self.sup.segment);
                self.series.push(t, st.equity_stop);
                self.start = Some(st);
                self.start_src = "segment";
                let slot = self.snaps[idx].slot;
                let late: Vec<Entry> = self.entries.values().filter(|e| e.slot > slot).cloned().collect();
                for e in late { self.count_stop(&e, t); }
            }
            self.own_start_value = self.stop_value();
            self.apply_limits();
            // the window since the earlier segment's last snapshot (or its undecided stop reconciliation), decided once this
            // segment's own records of it had their grace
            if let Some(p) = self.prev_window.take() {
                self.pending.push(Pending { from: From::Earlier(Box::new(p)), to: idx, due: t + grace, searched: false, unexplained: Vec::new(), at_stop: false });
            }
        }
        if let Some(from) = self.last_good { self.pending.push(Pending { from: From::Own(from), to: idx, due: t + grace, searched: false, unexplained: Vec::new(), at_stop: why == "stop" }); }
        self.last_good = Some(idx);
        if why != "stop" { self.next_periodic = t + self.periodic_ns(); }
    }

    /// the window search's answer: the window's signatures the ledger lacks (asked of the chain-fetch service)
    fn on_sigs(&mut self, d: &Value, _t: u64) {
        let Some(i) = self.pending.iter().position(|p| Some(p.to as u64) == d["to"].as_u64()) else { return };
        let from = match &self.pending[i].from { From::Own(f) => self.snaps[*f].slot, From::Earlier(p) => p.from.slot };
        let to = self.snaps[self.pending[i].to].slot;
        let earlier_entries: HashSet<String> = match &self.pending[i].from { From::Earlier(p) => p.entries.iter().map(|e| e.sig.clone()).collect(), _ => HashSet::new() };
        let mut out = Vec::new();
        for r in d["result"].as_array().into_iter().flatten() {
            let (Some(sig), Some(slot)) = (r["signature"].as_str(), r["slot"].as_u64()) else { continue };
            if slot <= from || slot > to || self.entries.contains_key(sig) || self.known_earlier.contains(sig) || earlier_entries.contains(sig) { continue; }
            out.push(json!({ "sig": sig, "slot": slot, "src": "getSignaturesForAddress" }));
            if let Some(s) = bs58::decode(sig).into_vec().ok().and_then(|v| <[u8; 64]>::try_from(v).ok()) { crate::chainfetch::note_landed(&s, Some(slot), None); }
        }
        if let Some(e) = d["error"].as_str() { out.push(json!({ "search_error": crate::rpc::scrub(e) })); }
        self.pending[i].unexplained = out;
    }

    /// Ask for the stop snapshot (the run is stopping); `stop_snapshot_done` says when it came (or failed)
    pub fn want_stop_snapshot(&mut self) { self.stop_asked = true; }
    pub fn stop_snapshot_done(&self) -> bool { self.stop_done || self.io.is_none() }

    fn spawn_snapshot(&mut self, why: &'static str, t: u64) {
        let Some(io) = &self.io else { return };
        if self.inflight { return; }
        self.inflight = true;
        let mut keys = vec![self.wallet];
        keys.extend(self.candidates.iter().copied());
        let (rpc, back, retries) = (io.rpc.clone(), io.back.clone(), self.cfg.snapshot_retries);
        io.rt.spawn(async move {
            let mut d = fetch_snapshot(rpc, keys, retries, why).await;
            d["t_req_ns"] = json!(t);
            let _ = back.send(Event::Input { kind: InputKind::Snapshot, data: Arc::new(d) });
        });
    }

    fn spawn_sigs(&mut self, to: usize, from_slot: u64) {
        let Some(io) = &self.io else { return };
        let (rpc, back, w) = (io.rpc.clone(), io.back.clone(), b58(&self.wallet));
        io.rt.spawn(async move {
            // pages back (newest first) until the window's first slot
            let (mut all, mut before, mut err) = (Vec::new(), None::<String>, None);
            for _ in 0..10 {
                let mut cfg = json!({ "limit": 1_000, "commitment": "confirmed" });
                if let Some(b) = &before { cfg["before"] = json!(b); }
                match rpc.call_bounded("getSignaturesForAddress", json!([w, cfg]), Bounds::fetch(Duration::from_secs(5), 1)).await {
                    Ok(f) => {
                        let rows = f.value.as_array().cloned().unwrap_or_default();
                        let done = rows.len() < 1_000 || rows.last().and_then(|r| r["slot"].as_u64()).is_some_and(|s| s <= from_slot);
                        before = rows.last().and_then(|r| r["signature"].as_str()).map(String::from);
                        all.extend(rows.into_iter().map(|r| json!({ "signature": r["signature"], "slot": r["slot"], "err": r["err"] })));
                        if done { break; }
                    }
                    Err(e) => { err = Some(e.msg); break; }
                }
            }
            let _ = back.send(Event::Input { kind: InputKind::Snapshot, data: Arc::new(json!({ "what": "sigs", "to": to, "result": all, "error": err })) });
        });
    }

    /// `tick_with` without what the rest of the process says (tests, a ledger without an executor)
    pub fn tick(&mut self, t: u64, landings: &dyn Fn() -> Vec<Landing>) -> MoneyView { self.tick_with(t, landings, TickIn::default()) }

    /// The ledger's timers at engine time `t` (housekeeping): the snapshots (start, every `snapshot_min`, a retry, a
    /// refresh, stop), the money view's freshness, the reconciliations due (`landings`: the executor's, read only then),
    /// the stop rules and the alerts. Returns what the executor reads
    pub fn tick_with(&mut self, t: u64, landings: &dyn Fn() -> Vec<Landing>, tin: TickIn) -> MoneyView {
        if !self.started { self.started = true; self.t_start = t; self.want = Some("start"); }
        if self.stop_asked && !self.stop_done { self.want = Some("stop"); }
        else if self.want.is_none() {
            if self.retry_at.is_some_and(|r| t >= r) { self.want = Some(if self.cur.is_none() { "start" } else { "retry" }); }
            else if self.cur.is_some() && self.next_periodic > 0 && t >= self.next_periodic { self.want = Some("periodic"); }
        }
        self.freshness(t, &tin);
        if let Some(w) = self.want { if !self.inflight && self.io.is_some() { self.want = None; self.retry_at = None; self.spawn_snapshot(w, t); } }
        self.decide_recons(t, landings);
        self.evaluate(t);
        self.view()
    }

    /// The money view's freshness (review WP-07 #3; invariant 4: no send on a stale input): it is stale while its last
    /// good snapshot is older than `max_view_age_s`, while `stale_after_failures` snapshots in a row failed, while a
    /// landing the executor found by a status check has had no wallet record for `max_record_wait_s`, and from a wallet
    /// record the chain-fetch service gave up on until a snapshot asked for after it (one is asked for at once). The
    /// supervisor puts the gate in shadow (`equity_stale`) while it lasts and lifts it when fresh; the executor refuses
    /// `equity_stale` meanwhile (the money view says so)
    fn freshness(&mut self, t: u64, tin: &TickIn) {
        let Some(last) = self.last_good_t else { return };
        if let Some(g) = tin.wallet_gave_up {
            if let Some(p) = self.gave_up_seen.filter(|p| g > *p) {
                if self.suspect.is_none() {
                    self.suspect = Some((t, format!("the chain-fetch service gave up on {} wallet record(s)", g - p)));
                    if self.want.is_none() && !self.stop_asked { self.want = Some("refresh"); }
                }
            }
            self.gave_up_seen = Some(g);
        }
        let s = 1_000_000_000u64;
        let age = t.saturating_sub(last);
        let (kind, why) = if age > self.cfg.max_view_age_s * s {
            (Some("age"), Some(format!("the last balance snapshot is {} s old (max_view_age_s {})", age / s, self.cfg.max_view_age_s)))
        } else if self.fail_run >= self.cfg.stale_after_failures {
            (Some("failures"), Some(format!("{} balance snapshots in a row failed (stale_after_failures {})", self.fail_run, self.cfg.stale_after_failures)))
        } else if let Some(p) = tin.provisional_since.filter(|p| t >= p + self.cfg.max_record_wait_s * s) {
            (Some("record_wait"), Some(format!("a landing found by a status check has had no wallet record for {} s (max_record_wait_s {})", (t - p) / s, self.cfg.max_record_wait_s)))
        } else {
            match &self.suspect { Some(x) => (Some("gave_up"), Some(format!("{}: until a balance snapshot asked for after it", x.1))), None => (None, None) }
        };
        if kind == self.stale_kind {
            // the same state: the message follows (the age grows); a gate reopened meanwhile is closed again
            if why.is_some() { self.stale = why; }
            if let Some(w) = self.stale.clone() { self.sup.hold_stale(t, &w); }
            return;
        }
        let detail = json!({ "why": why, "rule": kind, "was": self.stale, "last_snapshot_age_s": age / s, "failed_in_a_row": self.fail_run,
            "provisional_since_ns": tin.provisional_since, "wallet_gave_up_total": tin.wallet_gave_up, "max_view_age_s": self.cfg.max_view_age_s });
        if why.is_some() && self.stale.is_none() { self.count("equity_stale"); }
        self.sup.equity_stale(t, why.as_deref(), detail);
        self.stale = why;
        self.stale_kind = kind;
    }

    /// the stop rules and the alerts now
    pub fn evaluate(&mut self, t: u64) {
        if let Some(v) = self.stop_value() {
            self.series.trim(t, DAY_NS + HOUR_NS);
            let toks = self.stop_tokens();
            self.sup.evaluate(t, &self.series, v, &toks);
        }
        let cfg = self.sup.cfg.clone();
        // native SOL low (tips and fees are paid from it)
        if let Some(c) = &self.cur {
            let floor = (cfg.native_floor_sol * 1e9) as i64;
            if c.sol < floor {
                let sol = c.sol;
                self.sup.alert_once("low_native_sol", "low_native_sol", Level::Warn, format!("native SOL {sol} lamports, under {floor} (auto_unwrap off: an owner decision)"),
                    json!({ "native": sol, "floor": floor }));
            } else { self.sup.clear_alert("low_native_sol"); }
        }
        // a token a route left behind, still held
        let toks = self.tokens_now();
        let stranded_ns = cfg.stranded_s * 1_000_000_000;
        let due: Vec<(String, u64)> = self.stranded.iter().filter(|(_, t0)| t >= **t0 + stranded_ns).map(|(m, t0)| (m.clone(), *t0)).collect();
        for (m, t0) in due {
            let start = self.start.as_ref().and_then(|s| s.tokens.get(&m)).copied().unwrap_or(0);
            let now_amt = toks.get(&m).copied().unwrap_or(0);
            if now_amt > start {
                self.sup.alert_once(&format!("stranded_token:{m}"), "stranded_token", Level::Warn, format!("token {m}: {} left by a route for {} s (automatic sale is Stage 2+)",
                    now_amt - start, (t - t0) / 1_000_000_000), json!({ "mint": m, "amount": (now_amt - start).to_string(), "since_ns": t0 }));
            }
            self.stranded.remove(&m);
        }
        // no start equity yet: nothing is sent (the executor's `equity_unknown`)
        if self.cur.is_none() && self.started && t >= self.t_start + cfg.equity_wait_s * 1_000_000_000 {
            self.sup.alert_once("equity_unknown", "equity_unknown", Level::Error, format!("no balance snapshot {} s after the start: nothing is sent until one lands", cfg.equity_wait_s),
                json!({ "wait_s": cfg.equity_wait_s, "snapshots_failed": self.counts.get("snapshot_failed").copied().unwrap_or(0) }));
        }
    }

    fn decide_recons(&mut self, t: u64, landings: &dyn Fn() -> Vec<Landing>) {
        let mut keep = Vec::new();
        let tol = self.cfg.tolerance_lamports;
        for mut p in std::mem::take(&mut self.pending) {
            if t < p.due { keep.push(p); continue; }
            let between: Option<String> = match &p.from { From::Earlier(w) => Some(w.segment.clone()), From::Own(_) => None };
            let own_from = match &p.from { From::Own(f) => Some(*f), From::Earlier(_) => None };
            // the window's first snapshot and its entries: this segment's, or (between segments) the earlier segment's last
            // snapshot with the earlier entries after it and this segment's records of the same slots
            let w = {
                let to = &self.snaps[p.to];
                let (from, mut ents): (&Snapshot, Vec<&Entry>) = match &p.from {
                    From::Own(f) => (&self.snaps[*f], self.entries.values().collect()),
                    From::Earlier(w) => (&w.from, w.entries.iter().chain(self.entries.values()).collect()),
                };
                let mut seen = HashSet::new();
                ents.retain(|e| seen.insert(e.sig.as_str()));
                // a token account a window entry created that the closing snapshot did not read: not reconciled (that is not
                // a miss; the next snapshot reads it, and spans the window)
                let read: BTreeSet<Pk> = to.accounts().into_iter().chain(to.missing.iter().copied()).collect();
                let unread: Vec<String> = ents.iter().filter(|e| e.slot > from.slot && e.slot <= to.slot)
                    .flat_map(|e| e.created.iter().filter(|c| c.class == RentClass::Recoverable && !read.contains(&c.acct)).map(|c| b58(&c.acct))).collect();
                let (line, ok_snap) = reconcile(from, to, &ents, tol, t);
                // the executor's money against the chain: this segment's attempts (between segments: the earlier segments'
                // refused attempts the window's records show landed)
                let (exec_line, ok_exec) = if between.is_none() { exec_recon(&self.entries, &landings(), &self.earlier, tol) } else {
                    let refused: Vec<Value> = ents.iter().filter(|e| e.slot > from.slot && e.slot <= to.slot && e.is_route())
                        .filter_map(|e| self.earlier.get(&e.sig).filter(|x| x.fin == "not_landed_refused")
                            .map(|x| json!({ "segment": x.segment, "attempt": x.attempt, "sig": e.sig, "slot": e.slot, "fee": e.fee }))).collect();
                    let ok = refused.is_empty();
                    (json!({ "between_segments": true, "refused_landed": refused, "ok": ok }), ok)
                };
                // the owner's transfers in the window: recorded, never a miss
                let transfers: Vec<Value> = ents.iter().filter(|e| e.slot > from.slot && e.slot <= to.slot)
                    .filter_map(|e| e.owner_transfer().map(|(c, l)| json!({ "sig": e.sig, "slot": e.slot, "category": c, "lamports": l }))).collect();
                (from.slot, from.t_ns, to.slot, to.t_ns, unread, line, ok_snap, exec_line, ok_exec, transfers)
            };
            let (from_slot, from_t, to_slot, to_t, unread, mut line, ok_snap, exec_line, ok_exec, transfers) = w;
            if !unread.is_empty() && between.is_none() {
                self.recon_seq += 1;
                self.rec.json(rec::RECON, json!({ "t_ns": t, "seq": self.recon_seq, "from": { "t_ns": from_t, "slot": from_slot }, "to": { "t_ns": to_t, "slot": to_slot },
                    "skipped": "snapshot_incomplete", "unread": unread, "ok": null, "final": true }));
                // the window stays open: the next snapshot closes it
                if let Some(f) = own_from { self.last_good = Some(f); }
                continue;
            }
            let ok = ok_snap && ok_exec;
            if !ok && !p.searched && self.io.is_some() {
                // unexplained: search the window's signatures, decide once more a grace later
                p.searched = true;
                p.due = t + self.cfg.recon_grace_s * 1_000_000_000;
                self.spawn_sigs(p.to, from_slot);
                keep.push(p);
                continue;
            }
            // at the stop a residual still unexplained (the records of what landed just before it may be on their way) is
            // left undecided: the next segment decides it again from its own records (review WP-07 #7)
            let undecided = !ok && p.at_stop && ok_exec;
            self.recon_seq += 1;
            line["seq"] = json!(self.recon_seq);
            line["executor"] = exec_line.clone();
            line["unexplained"] = json!(p.unexplained);
            line["owner_transfers"] = json!(transfers);
            line["ok"] = json!(ok);
            line["final"] = json!(!undecided);
            line["at_stop"] = json!(p.at_stop);
            if let Some(seg) = &between {
                line["between_segments"] = json!(true);
                line["from"]["segment"] = json!(seg);
                line["decides"] = json!(self.undecided.as_ref().map(|(s, t0)| json!({ "segment": s, "t_ns": t0 })));
            }
            line["action"] = if ok { Value::Null } else if undecided { json!("undecided") } else { json!("shadow") };
            self.unreconciled_now = line["residual"].as_i64().unwrap_or(0);
            self.last_recon = Some((t, ok));
            self.rec.json(rec::RECON, line.clone());
            if !transfers.is_empty() { self.count("recon_owner_transfers"); }
            let refused = exec_line["refused_landed"].as_array().is_some_and(|a| !a.is_empty());
            if ok { self.count("recon_ok"); }
            else if undecided {
                self.count("recon_undecided");
                self.sup.alert_once(&format!("recon_undecided:{}", self.recon_seq), "recon_undecided", Level::Warn,
                    format!("the stop's reconciliation is not decided (residual {}, liquid {}): the next segment decides it", line["residual"], line["liquid"]["residual"]),
                    json!({ "seq": self.recon_seq, "residual": line["residual"], "liquid_residual": line["liquid"]["residual"], "unexplained": p.unexplained }));
            } else {
                self.count("recon_miss");
                self.recon_misses += 1;
                let why = if !ok_snap { format!("residual {} (liquid {}) against tolerance {tol}{}", line["residual"], line["liquid"]["residual"],
                        if between.is_some() { " between segments" } else { "" }) }
                    else if refused { "a refused bundle landed".to_string() }
                    else { format!("the executor's money differs from the chain by {} lamports", exec_line["diff"]) };
                self.sup.reconcile_miss_at(t, json!({ "why": why, "seq": self.recon_seq, "residual": line["residual"], "liquid_residual": line["liquid"]["residual"],
                    "executor": exec_line, "unexplained": p.unexplained, "between_segments": between.is_some() }), if refused { Level::Critical } else { Level::Error });
            }
            if refused { self.rec.event("refused_bundle_landed", "ledger", None, exec_line["refused_landed"].clone()); }
            if between.is_some() { self.undecided = None; }
        }
        self.pending = keep;
    }

    /// The stop's reconciliation (after the stop snapshot): every pending window is due now; one that does not pass is
    /// searched and decided once more `recon_grace_s` later, inside the drain (`final_settled` says when nothing waits)
    pub fn final_begin(&mut self, t: u64) { for p in &mut self.pending { p.due = p.due.min(t); p.at_stop = true; } }

    /// nothing pending waits for its search or its grace
    pub fn final_settled(&self) -> bool { self.pending.is_empty() }

    /// The end of the stop: what is still pending is decided now (a residual still unexplained is written `final:
    /// false`, and the next segment decides it again)
    pub fn final_recon(&mut self, t: u64, landings: &dyn Fn() -> Vec<Landing>) {
        for p in &mut self.pending { p.due = 0; p.searched = true; p.at_stop = true; }
        self.decide_recons(t, landings);
        self.evaluate(t);
    }

    /// status.jsonl `money` (MEASUREMENT §4.8, ledger-derived); `bot`: the executor's own counters (diagnostics);
    /// `provisional_failed_fees`: failed landings the executor counted whose records have not come (they join
    /// `failed_fees_total_lamports`, which the bash supervisor reads)
    pub fn money_json(&mut self, t: u64, bot: Value, provisional_failed_fees: u64) -> Value {
        let tt = self.totals;
        let p = self.prev;
        self.prev = tt;
        let eq = self.equity_stop();
        let v = self.stop_value();
        let floor = self.sup.limits.floor;
        let last = self.snaps.iter().rev().find(|s| !s.slot_mismatch);
        let tokens_now = self.tokens_now();
        let token_value_now = last.map(|s| s.token_value);
        let entries_delta = std::mem::take(&mut self.entries_seen_delta);
        let spent = self.spent();
        let mut m = json!({ "src": "ledger", "stop_basis": STOP_BASIS,
            "stop_value_now": v, "net_spend_now": spent, "equity_stop_now": eq, "equity_liquid_now": self.cur.as_ref().map(|c| c.sol + c.wsol),
            "native_sol_now": self.cur.as_ref().map(|c| c.sol), "wsol_now": self.cur.as_ref().map(|c| c.wsol), "rent_recoverable_now": self.cur.as_ref().map(|c| c.rent),
            "equity_total_now": self.cur.as_ref().map(|c| c.sol + c.wsol + c.rent + token_value_now.unwrap_or(0) as i64), "token_value_now": token_value_now,
            "tokens_now": tokens_now.iter().map(|(m, a)| (m.clone(), json!(a.to_string()))).collect::<Map<_, _>>(),
            "stop_tokens_now": self.stop_tokens().iter().map(|(m, a)| (m.clone(), json!(a.to_string()))).collect::<Map<_, _>>(),
            "drop_1h_now": self.series.drop_over(t, HOUR_NS), "drop_24h_now": self.series.drop_over(t, DAY_NS), "drop_window_src": self.start_src,
            "start": self.start.as_ref().map(Start::json), "floor_lamports": floor, "floor_margin_now": v.zip(floor).map(|(e, f)| e - f),
            "budget_left_now": self.test_budget.map(|b| b as i64 - spent), "stale": self.stale });
        let totals = json!({ "trade_gross_total": tt.trade_gross, "trade_pnl_total": tt.trade_pnl, "tips_total": tt.tips, "fees_win_total": tt.fee_win, "fees_fail_total": tt.fee_fail,
            "fees_other_total": tt.fee_other, "rent_nonrecoverable_total": tt.rent_nonrecoverable,
            "failed_fees_total_lamports": tt.fee_fail as u64 + provisional_failed_fees, "failed_fees_delta_lamports": tt.fee_fail - p.fee_fail,
            "rent_locked_total": tt.rent_locked, "rent_locked_delta": tt.rent_locked - p.rent_locked, "rent_reclaimed_total": tt.rent_reclaimed,
            "rent_reclaimed_delta": tt.rent_reclaimed - p.rent_reclaimed, "trade_net_total": tt.trade_net, "net_spend_total": tt.net_spend(),
            "transfer_in_total": tt.transfer_in, "transfer_out_total": tt.transfer_out, "owner_transfers_total": tt.owner_transfers, "entries_total": tt.entries,
            "entries_delta": entries_delta });
        let recon = json!({ "unreconciled_now": self.unreconciled_now, "last_recon_ok": self.last_recon.map(|r| r.1), "last_recon_t_ns": self.last_recon.map(|r| r.0),
            "recon_misses_total": self.recon_misses, "snapshots_total": self.snaps.len(), "last_snapshot_age_s_now": self.last_good_t.map(|s| t.saturating_sub(s) / 1_000_000_000),
            "counts": self.counts, "supervisor": self.sup.json(), "bot": bot });
        for part in [totals, recon] { if let (Some(o), Value::Object(x)) = (m.as_object_mut(), part) { o.extend(x); } }
        m
    }

    /// meta.json `limits.ledger`
    pub fn limits_json(&self) -> Value {
        json!({ "snapshot_min": self.cfg.snapshot_min, "max_view_age_s": self.cfg.max_view_age_s, "stale_after_failures": self.cfg.stale_after_failures,
            "max_record_wait_s": self.cfg.max_record_wait_s, "tolerance_lamports": self.cfg.tolerance_lamports, "token_haircut": self.cfg.token_haircut,
            "stop_basis": STOP_BASIS, "test_budget_lamports": self.test_budget, "budget_left_lamports": self.budget_left, "equity_floor_arg": self.floor_arg,
            "max_drop_per_hour_lamports": self.sup.limits.hour_drop, "max_drop_per_day_lamports": self.sup.limits.day_drop, "start_src": self.start_src,
            "stops_act": self.sup.acts, "campaign_start": self.start.as_ref().map(Start::json), "campaign_net_spend": self.spent_before,
            "between_segments_window": self.prev_window.as_ref().map(|w| json!({ "segment": w.segment, "from_slot": w.from.slot, "entries": w.entries.len(), "undecided": w.undecided })),
            "candidates": self.candidates.len() + 1 })
    }
}

/// tests: a balance snapshot's answer (INPUT 13) for `wallet`: native SOL, its WSOL account (rent 2,039,280), its USDC
/// account (`usdc` raw, rent 2,039,280), its PumpSwap accumulator, an account that does not exist
#[cfg(test)]
pub(crate) fn test_snapshot_answer(wallet: &Pk, slot: u64, sol: u64, wsol_amt: u64, usdc: u64, why: &str) -> Value {
    use base64::Engine as _;
    let acct = |lamports: u64, owner: &Pk, data: &[u8]| json!({ "lamports": lamports, "owner": b58(owner), "data": [base64::engine::general_purpose::STANDARD.encode(data), "base64"] });
    let token = |mint: &Pk, amount: u64| { let mut d = vec![0u8; 165]; d[..32].copy_from_slice(mint); d[32..64].copy_from_slice(wallet); d[64..72].copy_from_slice(&amount.to_le_bytes()); d };
    let usdc_mint = crate::tx::pk("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v");
    let tokp = *crate::pda::TOKEN_PROGRAM;
    let (wa, ua, acc) = (crate::build::ata_of(wallet, &wsol(), &tokp), crate::build::ata_of(wallet, &usdc_mint, &tokp), accumulator_of(wallet));
    json!({ "what": "snapshot", "why": why, "keys": [b58(wallet), b58(&wa), b58(&ua), b58(&acc), b58(&[9u8; 32])],
        "answers": [{ "slot": slot, "values": [acct(sol, &SYSTEM, &[]), acct(wsol_amt + 2_039_280, &tokp, &token(&wsol(), wsol_amt)),
            acct(2_039_280, &tokp, &token(&usdc_mint, usdc)), acct(1_346_200, &PUMPSWAP, &[0u8; 137]), Value::Null] }],
        "slot_mismatch": false, "attempts": 1, "provider": "fake", "ms": 1.0, "error": null })
}

#[cfg(test)]
mod tests;
