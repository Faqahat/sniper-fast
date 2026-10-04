//! An RPC transaction (`getTransaction` with `encoding: "base64"`, or one entry of a `getBlock` with
//! `transactionDetails: "full"`) as the Yellowstone protobuf shapes the exec.jsonl builder takes
//! (`rec::exec::exec_json`): backfilled, wallet and sampled records are then the very records the transaction stream
//! writes (MEASUREMENT §4.14, §4.15).
//!
//! - The wire bytes (legacy, v0, and v1 / SIMD-0385, which mainnet blocks carry: 181 of 1,193 transactions of slot
//!   453,032,285) become a `PbTransaction`: every signature, the header, the static keys, the recent blockhash (v1: the
//!   lifetime), the instructions, the lookups (v0), the inline budget config (v1).
//! - The JSON meta becomes a `PbMeta`: balances, token balances, inner instructions (base58 data), logs, loaded
//!   addresses, return data, compute units, cost units; the JSON error is encoded as the bincode `TransactionError`
//!   the stream sends, so `err` / `err_ix` read the same (`ix4:custom:0x4e580002`).
use crate::feeds::grpc::{PbHeader, PbInnerIx, PbInnerIxs, PbIx, PbLookup, PbMessage, PbMeta, PbReturnData, PbTokenBalance, PbTransaction, PbTxConfig, PbTxError, PbUiAmount};
use crate::tx::Pk;
use base64::Engine as _;
use serde_json::Value;

const B64: base64::engine::GeneralPurpose = base64::engine::general_purpose::STANDARD;

/// One transaction from the RPC, converted
#[derive(Clone, Debug)]
pub struct RpcTx {
    pub sig: [u8; 64],
    /// `getTransaction`'s `slot`, `transactionIndex` (newer nodes send it) and `blockTime`; None inside a block
    pub slot: Option<u64>,
    pub idx: Option<u64>,
    pub block_time: Option<i64>,
    pub tx: PbTransaction,
    pub meta: Option<PbMeta>,
    /// the full account list: static keys, then the loaded writable, then the loaded readonly addresses
    pub keys: Vec<Pk>,
}

impl RpcTx {
    pub fn is_v1(&self) -> bool { self.tx.message.as_ref().is_some_and(|m| m.config.is_some()) }
}

/// Convert one RPC transaction (`{transaction: [<base64>, "base64"], meta, version, [slot, blockTime, transactionIndex]}`)
pub fn from_rpc(v: &Value) -> Result<RpcTx, String> {
    let (b64, enc) = (v["transaction"][0].as_str(), v["transaction"][1].as_str());
    let Some(b64) = b64.filter(|_| enc == Some("base64")) else { return Err("not a base64 transaction".into()) };
    let raw = B64.decode(b64).map_err(|e| format!("transaction: {e}"))?;
    let tx = wire_to_pb(&raw).ok_or("the wire transaction does not parse")?;
    let sig: [u8; 64] = tx.signatures.first().and_then(|s| s.as_slice().try_into().ok()).ok_or("no signature")?;
    let meta = if v["meta"].is_null() { None } else { Some(meta_from_json(&v["meta"])?) };
    let mut keys: Vec<Pk> = tx.message.as_ref().map(|m| m.account_keys.iter().filter_map(|k| k.as_slice().try_into().ok()).collect()).unwrap_or_default();
    if let Some(m) = &meta {
        keys.extend(m.loaded_writable_addresses.iter().filter_map(|k| <[u8; 32]>::try_from(k.as_slice()).ok()));
        keys.extend(m.loaded_readonly_addresses.iter().filter_map(|k| <[u8; 32]>::try_from(k.as_slice()).ok()));
    }
    Ok(RpcTx { sig, slot: v["slot"].as_u64(), idx: v["transactionIndex"].as_u64(), block_time: v["blockTime"].as_i64(), tx, meta, keys })
}

struct Cur<'a> { b: &'a [u8], p: usize }
impl<'a> Cur<'a> {
    fn bytes(&mut self, n: usize) -> Option<&'a [u8]> { let s = self.b.get(self.p..self.p.checked_add(n)?)?; self.p += n; Some(s) }
    fn u8(&mut self) -> Option<u8> { Some(self.bytes(1)?[0]) }
    fn u16(&mut self) -> Option<u16> { Some(u16::from_le_bytes(self.bytes(2)?.try_into().ok()?)) }
    fn u32(&mut self) -> Option<u32> { Some(u32::from_le_bytes(self.bytes(4)?.try_into().ok()?)) }
    fn short_vec(&mut self) -> Option<usize> {
        let mut v = 0usize;
        for i in 0..3 {
            let b = self.u8()? as usize;
            v |= (b & 0x7f) << (7 * i);
            if b & 0x80 == 0 { return Some(v); }
        }
        None
    }
    fn short_bytes(&mut self) -> Option<Vec<u8>> { let n = self.short_vec()?; Some(self.bytes(n)?.to_vec()) }
}

/// The wire transaction as Yellowstone's `Transaction` (legacy, v0 or v1)
pub fn wire_to_pb(b: &[u8]) -> Option<PbTransaction> {
    if *b.first()? == 0x81 { return v1_to_pb(b); }
    let mut c = Cur { b, p: 0 };
    let nsig = c.short_vec()?;
    if nsig == 0 || nsig > 127 { return None; }
    let signatures: Vec<Vec<u8>> = (0..nsig).map(|_| c.bytes(64).map(<[u8]>::to_vec)).collect::<Option<_>>()?;
    let first = *b.get(c.p)?;
    let versioned = first & 0x80 != 0;
    if versioned {
        if first & 0x7f != 0 { return None; }
        c.p += 1;
    }
    let header = PbHeader { num_required_signatures: c.u8()? as u32, num_readonly_signed_accounts: c.u8()? as u32, num_readonly_unsigned_accounts: c.u8()? as u32 };
    let nkeys = c.short_vec()?;
    let account_keys: Vec<Vec<u8>> = (0..nkeys).map(|_| c.bytes(32).map(<[u8]>::to_vec)).collect::<Option<_>>()?;
    let recent_blockhash = c.bytes(32)?.to_vec();
    let nix = c.short_vec()?;
    let mut instructions = Vec::with_capacity(nix);
    for _ in 0..nix {
        let program_id_index = c.u8()? as u32;
        let accounts = c.short_bytes()?;
        let data = c.short_bytes()?;
        instructions.push(PbIx { program_id_index, accounts, data });
    }
    let mut address_table_lookups = Vec::new();
    if versioned {
        let n = c.short_vec()?;
        for _ in 0..n {
            let account_key = c.bytes(32)?.to_vec();
            let writable_indexes = c.short_bytes()?;
            let readonly_indexes = c.short_bytes()?;
            address_table_lookups.push(PbLookup { account_key, writable_indexes, readonly_indexes });
        }
    }
    Some(PbTransaction { signatures, message: Some(PbMessage { header: Some(header), account_keys, recent_blockhash, instructions, versioned, address_table_lookups, config: None }) })
}

/// v1 (SIMD-0385; the layout `tx::parse_wire` reads): 0x81, header (3), config mask (u32), lifetime (32), instruction
/// count (u8), address count (u8), addresses, the config values (4 bytes per set mask bit: bits 0-1 the priority fee as
/// a u64, bit 2 the compute-unit limit, bit 3 the loaded-accounts data size limit, bit 4 the heap size), one header per
/// instruction {program u8, account count u8, data length u16}, the instructions' accounts and data, then the signatures
fn v1_to_pb(b: &[u8]) -> Option<PbTransaction> {
    let mut c = Cur { b, p: 1 };
    let header = PbHeader { num_required_signatures: c.u8()? as u32, num_readonly_signed_accounts: c.u8()? as u32, num_readonly_unsigned_accounts: c.u8()? as u32 };
    let mask = c.u32()?;
    let recent_blockhash = c.bytes(32)?.to_vec();
    let nix = c.u8()? as usize;
    let naddr = c.u8()? as usize;
    let account_keys: Vec<Vec<u8>> = (0..naddr).map(|_| c.bytes(32).map(<[u8]>::to_vec)).collect::<Option<_>>()?;
    let mut words = Vec::new();
    for _ in 0..mask.count_ones() { words.push(c.u32()?); }
    let mut w = words.into_iter();
    let mut config = PbTxConfig::default();
    if mask & 0b11 == 0b11 { let (lo, hi) = (w.next()? as u64, w.next()? as u64); config.priority_fee = Some(lo | hi << 32); }
    else if mask & 0b11 != 0 { w.next()?; }
    if mask & 0b100 != 0 { config.compute_unit_limit = w.next(); }
    if mask & 0b1000 != 0 { config.loaded_accounts_data_size_limit = w.next(); }
    if mask & 0b1_0000 != 0 { config.heap_size = w.next(); }
    let mut hdr = Vec::with_capacity(nix);
    for _ in 0..nix { hdr.push((c.u8()? as u32, c.u8()? as usize, c.u16()? as usize)); }
    let mut instructions = Vec::with_capacity(nix);
    for (program_id_index, na, nd) in hdr {
        let accounts = c.bytes(na)?.to_vec();
        let data = c.bytes(nd)?.to_vec();
        instructions.push(PbIx { program_id_index, accounts, data });
    }
    let nsig = header.num_required_signatures as usize;
    if nsig == 0 { return None; }
    let signatures: Vec<Vec<u8>> = (0..nsig).map(|_| c.bytes(64).map(<[u8]>::to_vec)).collect::<Option<_>>()?;
    Some(PbTransaction { signatures, message: Some(PbMessage { header: Some(header), account_keys, recent_blockhash, instructions, versioned: true,
        address_table_lookups: vec![], config: Some(config) }) })
}

/// The first signature of a wire transaction (legacy / v0: after the count; v1: the signatures come last)
pub fn wire_sig(raw: &[u8]) -> Option<[u8; 64]> {
    if *raw.first()? == 0x81 { return wire_to_pb(raw)?.signatures.first()?.as_slice().try_into().ok(); }
    let n = *raw.first()? as usize;
    if n == 0 || n > 127 { return None; }
    raw.get(1..65)?.try_into().ok()
}

fn pk_b58(v: &Value) -> Option<Vec<u8>> { let b = bs58::decode(v.as_str()?).into_vec().ok()?; (b.len() == 32).then_some(b) }

fn u64s(v: &Value) -> Vec<u64> { v.as_array().map(|a| a.iter().map(|x| x.as_u64().unwrap_or(0)).collect()).unwrap_or_default() }

fn token_balances(v: &Value) -> Vec<PbTokenBalance> {
    v.as_array().map(|a| a.iter().map(|b| PbTokenBalance {
        account_index: b["accountIndex"].as_u64().unwrap_or(0) as u32,
        mint: b["mint"].as_str().unwrap_or("").to_string(),
        ui_token_amount: Some(PbUiAmount { decimals: b["uiTokenAmount"]["decimals"].as_u64().unwrap_or(0) as u32,
            amount: b["uiTokenAmount"]["amount"].as_str().unwrap_or("0").to_string() }),
        owner: b["owner"].as_str().unwrap_or("").to_string(),
        program_id: b["programId"].as_str().unwrap_or("").to_string(),
    }).collect()).unwrap_or_default()
}

/// The JSON meta as `TransactionStatusMeta`
pub fn meta_from_json(m: &Value) -> Result<PbMeta, String> {
    let inner = m.get("innerInstructions").filter(|x| !x.is_null());
    let mut inner_ixs = Vec::new();
    for g in inner.and_then(Value::as_array).into_iter().flatten() {
        let mut list = Vec::new();
        for x in g["instructions"].as_array().into_iter().flatten() {
            let data = match x["data"].as_str() { Some(d) => bs58::decode(d).into_vec().map_err(|e| format!("inner instruction data: {e}"))?, None => vec![] };
            list.push(PbInnerIx { program_id_index: x["programIdIndex"].as_u64().unwrap_or(0) as u32,
                accounts: x["accounts"].as_array().map(|a| a.iter().map(|i| i.as_u64().unwrap_or(0) as u8).collect()).unwrap_or_default(),
                data, stack_height: x["stackHeight"].as_u64().map(|h| h as u32) });
        }
        inner_ixs.push(PbInnerIxs { index: g["index"].as_u64().unwrap_or(0) as u32, instructions: list });
    }
    let logs = m.get("logMessages").filter(|x| !x.is_null());
    let la = &m["loadedAddresses"];
    let rd = m.get("returnData").filter(|x| !x.is_null());
    let return_data = match rd {
        Some(r) => Some(PbReturnData { program_id: pk_b58(&r["programId"]).unwrap_or_default(),
            data: r["data"][0].as_str().map(|d| B64.decode(d).unwrap_or_default()).unwrap_or_default() }),
        None => None,
    };
    Ok(PbMeta {
        err: (!m["err"].is_null()).then(|| PbTxError { err: encode_tx_error(&m["err"]) }),
        fee: m["fee"].as_u64().unwrap_or(0),
        pre_balances: u64s(&m["preBalances"]),
        post_balances: u64s(&m["postBalances"]),
        inner_instructions: inner_ixs,
        log_messages: logs.and_then(Value::as_array).map(|a| a.iter().filter_map(|l| l.as_str().map(String::from)).collect()).unwrap_or_default(),
        pre_token_balances: token_balances(&m["preTokenBalances"]),
        post_token_balances: token_balances(&m["postTokenBalances"]),
        inner_instructions_none: inner.is_none(),
        log_messages_none: logs.is_none(),
        loaded_writable_addresses: la["writable"].as_array().map(|a| a.iter().filter_map(pk_b58).collect()).unwrap_or_default(),
        loaded_readonly_addresses: la["readonly"].as_array().map(|a| a.iter().filter_map(pk_b58).collect()).unwrap_or_default(),
        return_data_none: return_data.is_none(),
        return_data,
        compute_units_consumed: m["computeUnitsConsumed"].as_u64(),
        cost_units: m["costUnits"].as_u64(),
    })
}

/// `TransactionError` variants by name, in bincode order (solana-transaction-error)
const TX_ERRORS: [&str; 39] = ["AccountInUse", "AccountLoadedTwice", "AccountNotFound", "ProgramAccountNotFound", "InsufficientFundsForFee",
    "InvalidAccountForFee", "AlreadyProcessed", "BlockhashNotFound", "InstructionError", "CallChainTooDeep", "MissingSignatureForFee",
    "InvalidAccountIndex", "SignatureFailure", "InvalidProgramForExecution", "SanitizeFailure", "ClusterMaintenance", "AccountBorrowOutstanding",
    "WouldExceedMaxBlockCostLimit", "UnsupportedVersion", "InvalidWritableAccount", "WouldExceedMaxAccountCostLimit",
    "WouldExceedAccountDataBlockLimit", "TooManyAccountLocks", "AddressLookupTableNotFound", "InvalidAddressLookupTableOwner",
    "InvalidAddressLookupTableData", "InvalidAddressLookupTableIndex", "InvalidRentPayingAccount", "WouldExceedMaxVoteCostLimit",
    "WouldExceedAccountDataTotalLimit", "DuplicateInstruction", "InsufficientFundsForRent", "MaxLoadedAccountsDataSizeExceeded",
    "InvalidLoadedAccountsDataSizeLimit", "ResanitizationNeeded", "ProgramExecutionTemporarilyRestricted", "UnbalancedTransaction",
    "ProgramCacheHitMaxLimit", "CommitCancelled"];

/// `InstructionError` variants by name, in bincode order (solana-instruction; `Custom` is 25)
const IX_ERRORS: [&str; 54] = ["GenericError", "InvalidArgument", "InvalidInstructionData", "InvalidAccountData", "AccountDataTooSmall",
    "InsufficientFunds", "IncorrectProgramId", "MissingRequiredSignature", "AccountAlreadyInitialized", "UninitializedAccount",
    "UnbalancedInstruction", "ModifiedProgramId", "ExternalAccountLamportSpend", "ExternalAccountDataModified", "ReadonlyLamportChange",
    "ReadonlyDataModified", "DuplicateAccountIndex", "ExecutableModified", "RentEpochModified", "NotEnoughAccountKeys", "AccountDataSizeChanged",
    "AccountNotExecutable", "AccountBorrowFailed", "AccountBorrowOutstanding", "DuplicateAccountOutOfSync", "Custom", "InvalidError",
    "ExecutableDataModified", "ExecutableLamportChange", "ExecutableAccountNotRentExempt", "UnsupportedProgramId", "CallDepth", "MissingAccount",
    "ReentrancyNotAllowed", "MaxSeedLengthExceeded", "InvalidSeeds", "InvalidRealloc", "ComputationalBudgetExceeded", "PrivilegeEscalation",
    "ProgramEnvironmentSetupFailure", "ProgramFailedToComplete", "ProgramFailedToCompile", "Immutable", "IncorrectAuthority", "BorshIoError",
    "AccountNotRentExempt", "InvalidAccountOwner", "ArithmeticOverflow", "UnsupportedSysvar", "IllegalOwner", "MaxAccountsDataAllocationsExceeded",
    "MaxAccountsExceeded", "MaxInstructionTraceLengthExceeded", "BuiltinProgramsMustConsumeComputeUnits"];

fn variant(list: &[&str], name: &str) -> Option<u32> { list.iter().position(|n| *n == name).map(|i| i as u32) }

/// The JSON `TransactionError` as its bincode encoding (what Yellowstone sends; `rec::tx_error` reads it): a unit
/// variant is its u32 index; `InstructionError` is 8, the instruction (u8) and the instruction error (`Custom` 25 with
/// its u32; `BorshIoError` 44 with its string); `DuplicateInstruction` (30), `InsufficientFundsForRent` (31) and
/// `ProgramExecutionTemporarilyRestricted` (35) carry a u8. An unknown error is empty (it reads as `?`)
pub fn encode_tx_error(e: &Value) -> Vec<u8> {
    let mut o = Vec::new();
    match e {
        Value::String(s) => { if let Some(i) = variant(&TX_ERRORS, s) { o.extend(i.to_le_bytes()); } }
        Value::Object(m) if m.len() == 1 => {
            let (k, v) = m.iter().next().unwrap();
            let Some(i) = variant(&TX_ERRORS, k) else { return o };
            match k.as_str() {
                "InstructionError" => {
                    let (Some(ix), inner) = (v[0].as_u64(), &v[1]) else { return o };
                    o.extend(8u32.to_le_bytes());
                    o.push(ix as u8);
                    match inner {
                        Value::String(n) => match variant(&IX_ERRORS, n) { Some(j) => o.extend(j.to_le_bytes()), None => o.truncate(5) },
                        Value::Object(im) if im.len() == 1 => {
                            let (n, x) = im.iter().next().unwrap();
                            match (n.as_str(), variant(&IX_ERRORS, n)) {
                                ("Custom", Some(j)) => { o.extend(j.to_le_bytes()); o.extend((x.as_u64().unwrap_or(0) as u32).to_le_bytes()); }
                                ("BorshIoError", Some(j)) => { let s = x.as_str().unwrap_or(""); o.extend(j.to_le_bytes()); o.extend((s.len() as u64).to_le_bytes()); o.extend(s.as_bytes()); }
                                (_, Some(j)) => o.extend(j.to_le_bytes()),
                                _ => o.truncate(5),
                            }
                        }
                        _ => o.truncate(5),
                    }
                }
                "DuplicateInstruction" => { o.extend(i.to_le_bytes()); o.push(v.as_u64().unwrap_or(0) as u8); }
                "InsufficientFundsForRent" | "ProgramExecutionTemporarilyRestricted" => { o.extend(i.to_le_bytes()); o.push(v["account_index"].as_u64().unwrap_or(0) as u8); }
                _ => o.extend(i.to_le_bytes()),
            }
        }
        _ => {}
    }
    o
}
