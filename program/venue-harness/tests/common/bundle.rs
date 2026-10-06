//! Shared by the suites that run arbx's own bundles on the real programs (tests/arbx_bundle.rs, tests/arbx_bundle_clmm.rs):
//! the deployed nexus-arb-v2 ELF, a v0 transaction's wire bytes as LiteSVM takes them, a lookup table account, and what a
//! run's logs say (a program's CU at a depth, the rent a System CPI moved, what nexus-v2 says each leg delivered).
use base64::Engine as _;
use litesvm::LiteSVM;
use serde_json::Value;
use solana_account::Account;
use solana_address::Address;
use solana_message::compiled_instruction::CompiledInstruction;
use solana_message::v0::{Message as V0Message, MessageAddressTableLookup};
use solana_message::{Hash, MessageHeader, VersionedMessage};
use solana_transaction::versioned::VersionedTransaction;
use solana_transaction::Signature;
use venue_harness::fixture::elf_extent;
use venue_harness::keys::{self, SYSTEM};

pub const NEXUS: Address = Address::from_str_const("8K8uyQDtVKHYRPACP9fepz91q4sEZLBppR2Ty4vdXuWg");
pub const ALT_PROGRAM: Address = Address::from_str_const("AddressLookupTab1e1111111111111111111111111");
/// nexus-v2's ERR_PROFIT (the route made less than min_profit)
pub const ERR_PROFIT: u32 = 0x4e58_0002;

pub fn repo(rel: &str) -> std::path::PathBuf { std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..").join(rel) }
pub fn b64(s: &str) -> Vec<u8> { base64::engine::general_purpose::STANDARD.decode(s).unwrap() }
pub fn addr(s: &str) -> Address { keys::parse(s).unwrap() }

/// the deployed nexus-arb-v2 ELF: its programdata account as fetched (45-byte header, the ELF, zero padding)
pub fn nexus_elf() -> Vec<u8> {
    let v: Value = serde_json::from_str(&std::fs::read_to_string(repo("testdata/programs/8K8uyQDt-programdata.json")).unwrap()).unwrap();
    let data = b64(v["result"]["value"]["data"][0].as_str().unwrap());
    let elf = &data[45..];
    elf[..elf_extent(elf).unwrap()].to_vec()
}

/// a v0 transaction's wire bytes (one signature) as LiteSVM takes it
pub fn versioned(raw: &[u8]) -> VersionedTransaction {
    let mut p = 0usize;
    let mut take = |n: usize| { let s = &raw[p..p + n]; p += n; s };
    fn compact(b: &[u8], p: &mut usize) -> usize {
        let mut v = 0usize;
        for i in 0..3 { let x = b[*p] as usize; *p += 1; v |= (x & 0x7f) << (7 * i); if x & 0x80 == 0 { break; } }
        v
    }
    assert_eq!(take(1)[0], 1, "one signature");
    let sig = Signature::from(<[u8; 64]>::try_from(take(64)).unwrap());
    assert_eq!(take(1)[0], 0x80, "a v0 message");
    let h = take(3).to_vec();
    let header = MessageHeader { num_required_signatures: h[0], num_readonly_signed_accounts: h[1], num_readonly_unsigned_accounts: h[2] };
    let n = compact(raw, &mut p);
    let keys: Vec<Address> = (0..n).map(|i| Address::new_from_array(raw[p + 32 * i..p + 32 * i + 32].try_into().unwrap())).collect();
    p += 32 * n;
    let bh = Hash::new_from_array(raw[p..p + 32].try_into().unwrap());
    p += 32;
    let nix = compact(raw, &mut p);
    let mut ixs = Vec::new();
    for _ in 0..nix {
        let program_id_index = raw[p];
        p += 1;
        let na = compact(raw, &mut p);
        let accounts = raw[p..p + na].to_vec();
        p += na;
        let nd = compact(raw, &mut p);
        let data = raw[p..p + nd].to_vec();
        p += nd;
        ixs.push(CompiledInstruction { program_id_index, accounts, data });
    }
    let nl = compact(raw, &mut p);
    let mut lookups = Vec::new();
    for _ in 0..nl {
        let account_key = Address::new_from_array(raw[p..p + 32].try_into().unwrap());
        p += 32;
        let nw = compact(raw, &mut p);
        let writable_indexes = raw[p..p + nw].to_vec();
        p += nw;
        let nr = compact(raw, &mut p);
        let readonly_indexes = raw[p..p + nr].to_vec();
        p += nr;
        lookups.push(MessageAddressTableLookup { account_key, writable_indexes, readonly_indexes });
    }
    assert_eq!(p, raw.len(), "nothing after the message");
    let m = V0Message { header, account_keys: keys, recent_blockhash: bh, instructions: ixs, address_table_lookups: lookups };
    VersionedTransaction { signatures: vec![sig], message: VersionedMessage::V0(m) }
}

/// an address lookup table account (active, extended long ago) holding `addrs`
pub fn alt_account(addrs: &[Address]) -> Account {
    let mut d = vec![0u8; 56];
    d[..4].copy_from_slice(&1u32.to_le_bytes());          // LookupTable
    d[4..12].copy_from_slice(&u64::MAX.to_le_bytes());    // deactivation_slot: active
    d[12..20].copy_from_slice(&1u64.to_le_bytes());       // last_extended_slot
    for a in addrs { d.extend_from_slice(a.as_ref()); }
    Account { lamports: 10_000_000_000, data: d, owner: ALT_PROGRAM, executable: false, rent_epoch: u64::MAX }
}

pub fn token_amount(svm: &LiteSVM, k: &Address) -> Option<u64> {
    svm.get_account(k).filter(|a| a.data.len() >= 72 && a.lamports > 0).map(|a| u64::from_le_bytes(a.data[64..72].try_into().unwrap()))
}

/// the rent the ATA program's System CPI moved (CreateAccount: lamports at 4..12; Transfer when the address held some)
pub fn rent_locked(meta_inner: &solana_message::inner_instruction::InnerInstructionsList, keys: &[Address]) -> u64 {
    meta_inner.iter().flatten().filter(|i| keys.get(i.instruction.program_id_index as usize) == Some(&SYSTEM))
        .filter_map(|i| { let d = &i.instruction.data; (d.len() >= 12 && (d[..4] == [0, 0, 0, 0] || d[..4] == [2, 0, 0, 0])).then(|| u64::from_le_bytes(d[4..12].try_into().unwrap())) })
        .sum()
}

/// CU of `program`'s invocation at `depth` (its "consumed" line): the route program at 1, a leg at 2
pub fn venue_cu_depth(logs: &[String], program: &Address, want: usize) -> Option<u64> {
    let p = program.to_string();
    let mut depth = 0usize;
    let mut found = None;
    for l in logs {
        let Some(rest) = l.strip_prefix("Program ") else { continue };
        let Some((id, tail)) = rest.split_once(' ') else { continue };
        if id.ends_with(':') { continue; }
        if tail.starts_with("invoke [") { depth += 1; continue; }
        if let Some(x) = rest.strip_prefix(&format!("{p} consumed ")) {
            if depth == want { found = x.split(' ').next().and_then(|n| n.parse().ok()); }
            continue;
        }
        if tail == "success" || tail.starts_with("failed") { depth = depth.saturating_sub(1); }
    }
    found
}

/// What nexus-v2 logged each leg delivered (its `NXV2OUT` record: "Program data: " + base64 of "NXV2OUT", the leg index,
/// the amount u64 LE), in order
pub fn nexus_delivered(logs: &[String]) -> Vec<(u8, u64)> {
    logs.iter().filter_map(|l| l.strip_prefix("Program data: ")).filter_map(|d| base64::engine::general_purpose::STANDARD.decode(d.trim()).ok())
        .filter(|b| b.len() == 16 && &b[..7] == b"NXV2OUT").map(|b| (b[7], u64::from_le_bytes(b[8..16].try_into().unwrap()))).collect()
}
