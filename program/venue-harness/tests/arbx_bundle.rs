//! arbx's own bundles on the real programs (PLAN WP-06; PLAN-ADDENDUM go-live gate: "new token accounts only through
//! WP-06's rent-neutral create+close inside the same atomic transaction"). The vectors are what arbx's builder makes
//! (`src/exec/tests.rs bundle_vectors_for_the_venue_harness` writes ../../testdata/builder/bundle-vectors.json): the
//! recorded HOTBOT route (PumpSwap GLL3 ↔ DLMM 6D4E; HOTBOT a Token-2022 mint) with a gap opened by scaling GLL3's quote
//! vault, signed by the test wallet. Each one runs here, as signed (v0, its lookup table), in LiteSVM on the dumped
//! mainnet programs (PumpSwap, its fee program, DLMM, SPL Token, Token-2022, the ATA program) and the deployed
//! nexus-arb-v2 ELF (../../testdata/programs, md5 809315be), and the ledger of the payer is checked:
//!   - a create+close bundle lands; the payer's native lamports move by the base fee and the tip only (the create's rent
//!     comes back in the same transaction: rent locked, read from the ATA program's System CPI, = rent reclaimed); its
//!     WSOL account gains the route's profit, exactly arbx-sizing's quote, at least min_profit; the HOTBOT account does
//!     not exist after it; the transaction's CU stays within the CU limit the builder asked;
//!   - a held token's bundle creates and closes nothing: the account is still there, empty;
//!   - a bundle whose min_profit the route cannot reach fails with nexus-v2's 0x4e580002, and nothing it did stays: no
//!     token account, the WSOL untouched (a bundle that fails never lands; LiteSVM charges at most the fee);
//!   - the CU the builder allowed holds what the programs consumed: the ATA create and close within their allowances
//!     (`cu_ata`), the rest of the transaction (the route, the compute-budget instructions, the tip) within the route's
//!     (`cu_route`); the same for an SPL Token account (USDC, from the AMM v4 58oQ fixture), created and closed in one
//!     transaction, rent-neutral too;
//!   - the measurements (overhead, legs, ATA create and close) go to results/arbx-bundle-runs.json.
//!
//!   cargo test --release --test arbx_bundle -- --nocapture
use base64::Engine as _;
use litesvm::LiteSVM;
use serde_json::{json, Value};
use solana_account::Account;
use solana_address::Address;
use solana_instruction::{AccountMeta, Instruction};
use solana_keypair::Keypair;
use solana_message::compiled_instruction::CompiledInstruction;
use solana_message::v0::{Message as V0Message, MessageAddressTableLookup};
use solana_message::{Hash, MessageHeader, VersionedMessage};
use solana_signer::Signer;
use solana_transaction::versioned::VersionedTransaction;
use solana_transaction::{Signature, Transaction};
use venue_harness::fixture::{elf_extent, program_elf, Fixtures};
use venue_harness::harness::{create_ata_idempotent, pump_init_user_volume_accumulator};
use venue_harness::keys::{self, *};

const NEXUS: Address = Address::from_str_const("8K8uyQDtVKHYRPACP9fepz91q4sEZLBppR2Ty4vdXuWg");
const ALT_PROGRAM: Address = Address::from_str_const("AddressLookupTab1e1111111111111111111111111");
const ERR_PROFIT: u32 = 0x4e58_0002;

fn repo(rel: &str) -> std::path::PathBuf { std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..").join(rel) }
fn b64(s: &str) -> Vec<u8> { base64::engine::general_purpose::STANDARD.decode(s).unwrap() }
fn addr(s: &str) -> Address { keys::parse(s).unwrap() }

/// the deployed nexus-arb-v2 ELF: its programdata account as fetched (45-byte header, the ELF, zero padding)
fn nexus_elf() -> Vec<u8> {
    let v: Value = serde_json::from_str(&std::fs::read_to_string(repo("testdata/programs/8K8uyQDt-programdata.json")).unwrap()).unwrap();
    let data = b64(v["result"]["value"]["data"][0].as_str().unwrap());
    let elf = &data[45..];
    elf[..elf_extent(elf).unwrap()].to_vec()
}

/// a v0 transaction's wire bytes (one signature) as LiteSVM takes it
fn versioned(raw: &[u8]) -> VersionedTransaction {
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
fn alt_account(addrs: &[Address]) -> Account {
    let mut d = vec![0u8; 56];
    d[..4].copy_from_slice(&1u32.to_le_bytes());          // LookupTable
    d[4..12].copy_from_slice(&u64::MAX.to_le_bytes());    // deactivation_slot: active
    d[12..20].copy_from_slice(&1u64.to_le_bytes());       // last_extended_slot
    for a in addrs { d.extend_from_slice(a.as_ref()); }
    Account { lamports: 10_000_000_000, data: d, owner: ALT_PROGRAM, executable: false, rent_epoch: u64::MAX }
}

fn token_amount(svm: &LiteSVM, k: &Address) -> Option<u64> { svm.get_account(k).filter(|a| a.data.len() >= 72 && a.lamports > 0).map(|a| u64::from_le_bytes(a.data[64..72].try_into().unwrap())) }

/// The base state every vector runs on: the programs, both pools' snapshots (DLMM 6D4E's Clock), the wallet (native SOL,
/// its WSOL account with 50 SOL, its PumpSwap volume accumulator, created as an owner's wallet prep would), the Jito tip
/// account, the vectors' lookup table
fn base(fx: &Fixtures, v: &Value, payer: &Keypair) -> LiteSVM {
    let mut svm = LiteSVM::new().with_log_bytes_limit(None).with_transaction_history(0).with_blockhash_check(false);
    for (name, id) in keys::PROGRAMS {
        if ![PUMPSWAP, PUMP_FEE_PROGRAM, DLMM, TOKEN, TOKEN_2022, ATA_PROGRAM].contains(id) { continue; }
        let e = fx.manifest.get(id).unwrap_or_else(|| panic!("{name} not in fixtures/programs"));
        let elf = program_elf(e).unwrap();
        let r = if keys::parse(&e.loader).unwrap() == BPF_LOADER_UPGRADEABLE { svm.add_program(*id, &elf) } else { svm.add_program_with_loader(*id, &elf, keys::parse(&e.loader).unwrap()) };
        r.unwrap_or_else(|err| panic!("loading {name}: {err:?}"));
    }
    svm.add_program(NEXUS, &nexus_elf()).unwrap();
    let (g, d) = (fx.find("GLL3").expect("GLL3 fixture"), fx.find("6D4E").expect("6D4E fixture"));
    for p in [g, d] { for (k, a) in p.account_map().unwrap() { svm.set_account(k, a).unwrap(); } }
    svm.set_sysvar(&d.clock.to_clock());
    if let Some(r) = &d.rent { svm.set_sysvar(&r.to_rent()); }
    let u = payer.pubkey();
    svm.set_account(u, Account { lamports: 100_000_000_000, data: vec![], owner: SYSTEM, executable: false, rent_epoch: u64::MAX }).unwrap();
    let ixs = vec![create_ata_idempotent(&u, &u, &WSOL, &TOKEN), pump_init_user_volume_accumulator(&u)];
    let tx = Transaction::new_signed_with_payer(&ixs, Some(&u), &[payer], svm.latest_blockhash());
    svm.send_transaction(tx).unwrap_or_else(|f| panic!("wallet prep: {:?} {:?}", f.err, f.meta.logs));
    let wsol = keys::ata(&u, &WSOL, &TOKEN);
    let mut a = svm.get_account(&wsol).unwrap();
    a.data[64..72].copy_from_slice(&50_000_000_000u64.to_le_bytes());
    a.lamports += 50_000_000_000;
    svm.set_account(wsol, a).unwrap();
    let tip = addr(v["cases"][0]["tip"][0].as_str().unwrap());
    svm.set_account(tip, Account { lamports: 1_000_000_000, data: vec![], owner: SYSTEM, executable: false, rent_epoch: u64::MAX }).unwrap();
    let alt: Vec<Address> = v["alt"]["addrs"].as_array().unwrap().iter().map(|a| addr(a.as_str().unwrap())).collect();
    svm.set_account(addr(v["alt"]["table"].as_str().unwrap()), alt_account(&alt)).unwrap();
    svm
}

/// the rent the ATA program's System CPI moved (CreateAccount: lamports at 4..12; Transfer when the address held some)
fn rent_locked(meta_inner: &solana_message::inner_instruction::InnerInstructionsList, keys: &[Address]) -> u64 {
    meta_inner.iter().flatten().filter(|i| keys.get(i.instruction.program_id_index as usize) == Some(&SYSTEM))
        .filter_map(|i| { let d = &i.instruction.data; (d.len() >= 12 && (d[..4] == [0, 0, 0, 0] || d[..4] == [2, 0, 0, 0])).then(|| u64::from_le_bytes(d[4..12].try_into().unwrap())) })
        .sum()
}

#[test]
fn arbx_bundles_are_rent_neutral_on_the_real_programs() {
    let path = repo("testdata/builder/bundle-vectors.json");
    let v: Value = serde_json::from_str(&std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{}: {e}", path.display()))).unwrap();
    assert_eq!(v["schema"], "arbx.bundle-vectors/1");
    let fx = Fixtures::load().unwrap();
    let payer = Keypair::new_from_array([v["payer_seed_byte"].as_u64().unwrap() as u8; 32]);
    assert_eq!(payer.pubkey().to_string(), v["payer"].as_str().unwrap(), "the vectors' payer is the test wallet");
    let base = base(&fx, &v, &payer);
    let u = payer.pubkey();
    let wsol = keys::ata(&u, &WSOL, &TOKEN);
    let mut runs = Vec::new();
    let mut problems = Vec::new();
    for c in v["cases"].as_array().unwrap() {
        let name = c["name"].as_str().unwrap();
        let mut svm = base.clone();
        // the gap: GLL3's quote vault scaled (its lamports keep covering the amount)
        let qv = addr(c["gll3_quote_vault"].as_str().unwrap());
        let mut a = svm.get_account(&qv).unwrap();
        a.data[64..72].copy_from_slice(&c["gll3_quote_vault_amount"].as_u64().unwrap().to_le_bytes());
        svm.set_account(qv, a).unwrap();
        let (mint, prog, mid) = (addr(c["mint"].as_str().unwrap()), addr(c["token_program"].as_str().unwrap()), addr(c["mid_account"].as_str().unwrap()));
        assert_eq!(mid, keys::ata(&u, &mint, &prog));
        if c["held"].as_bool().unwrap() {
            let tx = Transaction::new_signed_with_payer(&[create_ata_idempotent(&u, &u, &mint, &prog)], Some(&u), &[&payer], svm.latest_blockhash());
            svm.send_transaction(tx).unwrap();
        }
        let (tip_acct, tip) = (addr(c["tip"][0].as_str().unwrap()), c["tip"][1].as_u64().unwrap());
        let pre = (svm.get_account(&u).unwrap().lamports, token_amount(&svm, &wsol).unwrap(), svm.get_account(&tip_acct).unwrap().lamports, svm.get_account(&mid).map(|a| a.lamports));
        let tx = versioned(&b64(c["tx_b64"].as_str().unwrap()));
        let keys_static = tx.message.static_account_keys().to_vec();
        let res = svm.send_transaction(tx);
        let post = (svm.get_account(&u).map_or(0, |a| a.lamports), token_amount(&svm, &wsol).unwrap_or(0), svm.get_account(&tip_acct).unwrap().lamports,
            svm.get_account(&mid).filter(|a| a.lamports > 0).map(|a| a.lamports));
        let native = post.0 as i128 - pre.0 as i128;
        let wsol_delta = post.1 as i128 - pre.1 as i128;
        match (c["expect"].as_str().unwrap(), res) {
            ("ok", Ok(meta)) => {
                let fee = 5_000i128;
                let locked = rent_locked(&meta.inner_instructions, &keys_static);
                let reclaimed = (native + fee + tip as i128 + locked as i128) as u64;
                let legs: Vec<u64> = [PUMPSWAP, DLMM].iter().filter_map(|p| venue_cu_depth(&meta.logs, p, 2)).collect();
                let outer = venue_cu_depth(&meta.logs, &NEXUS, 1).unwrap_or(0);
                let create = venue_cu_depth(&meta.logs, &ATA_PROGRAM, 1);
                let close = venue_cu_depth(&meta.logs, &prog, 1);
                println!("{name:<44} ok: native {native} (fee {fee} + tip {tip}), WSOL +{wsol_delta} (quoted {}), rent locked {locked} reclaimed {reclaimed}, \
                    CU {} of {} (route {outer}: legs {legs:?}; create {create:?}, close {close:?})", c["expected_profit"], meta.compute_units_consumed, c["cu_limit"]);
                if native != -fee - tip as i128 { problems.push(format!("{name}: native moved {native}, not -fee -tip = {}", -fee - tip as i128)); }
                if locked != reclaimed { problems.push(format!("{name}: rent locked {locked} != reclaimed {reclaimed}")); }
                let held = c["held"].as_bool().unwrap();
                if !held && locked == 0 { problems.push(format!("{name}: no rent was locked: no account created")); }
                if held && locked != 0 { problems.push(format!("{name}: a held token's bundle created an account ({locked})")); }
                if wsol_delta != c["expected_profit"].as_i64().unwrap() as i128 { problems.push(format!("{name}: WSOL +{wsol_delta}, arbx-sizing quoted {}", c["expected_profit"])); }
                if wsol_delta < c["min_profit"].as_u64().unwrap() as i128 { problems.push(format!("{name}: below min_profit")); }
                if post.2 - pre.2 != tip { problems.push(format!("{name}: the tip account got {}", post.2 - pre.2)); }
                match (held, post.3) {
                    (false, Some(l)) => problems.push(format!("{name}: the created account is still there ({l} lamports): rent locked")),
                    (true, None) => problems.push(format!("{name}: the held account was closed")),
                    (true, Some(_)) => if token_amount(&svm, &mid) != Some(0) { problems.push(format!("{name}: the held account kept tokens")); },
                    _ => {}
                }
                if meta.compute_units_consumed > c["cu_limit"].as_u64().unwrap() { problems.push(format!("{name}: CU {} over the limit", meta.compute_units_consumed)); }
                // each part within what the builder allowed for it
                let (a_create, a_close, a_route) = (c["cu_ata"][0].as_u64().unwrap(), c["cu_ata"][1].as_u64().unwrap(), c["cu_route"].as_u64().unwrap());
                if create.is_some_and(|x| x > a_create) { problems.push(format!("{name}: the ATA create took {create:?} CU, allowed {a_create}")); }
                if close.is_some_and(|x| x > a_close) { problems.push(format!("{name}: the close took {close:?} CU, allowed {a_close}")); }
                let rest = meta.compute_units_consumed - create.unwrap_or(0) - close.unwrap_or(0);
                if rest > a_route { problems.push(format!("{name}: the route and the rest took {rest} CU, allowed {a_route}")); }
                runs.push(json!({ "name": name, "ok": true, "cu_tx": meta.compute_units_consumed, "cu_limit": c["cu_limit"], "cu_route_outer": outer, "cu_legs": legs,
                    "cu_overhead": outer.saturating_sub(legs.iter().sum::<u64>()), "cu_ata_create": create, "cu_ata_close": close, "rent_locked": locked,
                    "rent_reclaimed": reclaimed, "native_delta": native as i64, "wsol_delta": wsol_delta as i64, "tip": tip, "bytes": c["bytes"],
                    "loaded_data_limit": c["loaded_data_limit"], "cu_allowed": { "route": c["cu_route"], "ata_create": c["cu_ata"][0], "ata_close": c["cu_ata"][1] } }));
            }
            ("profit_fail", Err(f)) => {
                let code = match &f.err { solana_transaction_error::TransactionError::InstructionError(_, solana_instruction_error::InstructionError::Custom(c)) => Some(*c), _ => None };
                println!("{name:<44} failed as built to: {:?}; native {native}, WSOL {wsol_delta}, account after {:?}", f.err, post.3);
                if code != Some(ERR_PROFIT) { problems.push(format!("{name}: failed with {:?}, not 0x4e580002", f.err)); }
                if post.3.is_some() { problems.push(format!("{name}: a failed bundle left the created account")); }
                if wsol_delta != 0 { problems.push(format!("{name}: a failed bundle moved WSOL {wsol_delta}")); }
                if !(native == 0 || native == -5_000) { problems.push(format!("{name}: a failed bundle moved native {native}")); }
                runs.push(json!({ "name": name, "ok": false, "err": format!("{:?}", f.err), "native_delta": native as i64 }));
            }
            (want, got) => problems.push(format!("{name}: expected {want}, got {:?}", got.map(|m| m.logs).map_err(|f| (f.err, f.meta.logs)))),
        }
    }
    // an SPL Token account: USDC's (the mint from the AMM v4 58oQ fixture), created and closed in one transaction as the
    // builder lays them out, measured against the same allowances
    let spl = {
        let mut svm = base.clone();
        let usdc = addr("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v");
        let amm = fx.find("58oQ").expect("AMM v4 58oQ fixture (SOL/USDC)");
        let (k, a) = amm.account_map().unwrap().into_iter().find(|(k, _)| *k == usdc).expect("the USDC mint in the 58oQ fixture");
        assert_eq!(a.owner, TOKEN, "USDC is an SPL Token mint");
        svm.set_account(k, a).unwrap();
        let acct = keys::ata(&u, &usdc, &TOKEN);
        let close = Instruction { program_id: TOKEN, data: vec![9], accounts: vec![AccountMeta::new(acct, false), AccountMeta::new(u, false), AccountMeta::new_readonly(u, true)] };
        let tx = Transaction::new_signed_with_payer(&[create_ata_idempotent(&u, &u, &usdc, &TOKEN), close], Some(&u), &[&payer], svm.latest_blockhash());
        let keys_static = tx.message.account_keys.clone();
        let pre = svm.get_account(&u).unwrap().lamports;
        let meta = svm.send_transaction(tx).unwrap_or_else(|f| panic!("SPL create+close: {:?} {:?}", f.err, f.meta.logs));
        let native = svm.get_account(&u).unwrap().lamports as i128 - pre as i128;
        let locked = rent_locked(&meta.inner_instructions, &keys_static);
        let reclaimed = (native + 5_000 + locked as i128) as u64;
        let (create, close) = (venue_cu_depth(&meta.logs, &ATA_PROGRAM, 1), venue_cu_depth(&meta.logs, &TOKEN, 1));
        let c0 = &v["cases"][0];
        let (a_create, a_close) = (c0["cu_ata"][0].as_u64().unwrap(), c0["cu_ata"][1].as_u64().unwrap());
        println!("{:<44} ok: native {native} (fee 5000), rent locked {locked} reclaimed {reclaimed}, create {create:?} close {close:?} (allowed {a_create} / {a_close})",
            "spl_usdc_create_close");
        if locked == 0 || locked != reclaimed || native != -5_000 { problems.push(format!("SPL create+close: rent locked {locked}, reclaimed {reclaimed}, native {native}")); }
        if svm.get_account(&acct).is_some_and(|a| a.lamports > 0) { problems.push("SPL create+close: the account is still there".into()); }
        if create.map_or(true, |x| x > a_create) || close.map_or(true, |x| x > a_close) {
            problems.push(format!("SPL create+close: create {create:?} / close {close:?} CU, allowed {a_create} / {a_close}"));
        }
        json!({ "name": "spl_usdc_create_close", "mint": usdc.to_string(), "cu_tx": meta.compute_units_consumed, "cu_ata_create": create, "cu_ata_close": close,
            "rent_locked": locked, "rent_reclaimed": reclaimed, "native_delta": native as i64 })
    };
    runs.push(spl);
    let out = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("results");
    std::fs::create_dir_all(&out).unwrap();
    std::fs::write(out.join("arbx-bundle-runs.json"), serde_json::to_string_pretty(&json!({ "vectors": v["cases"].as_array().unwrap().len(), "runs": runs })).unwrap()).unwrap();
    for p in &problems { println!("PROBLEM {p}"); }
    assert!(problems.is_empty(), "{} problems", problems.len());
}

/// CU of `program`'s invocation at `depth` (its "consumed" line): the route program at 1, a leg at 2
fn venue_cu_depth(logs: &[String], program: &Address, want: usize) -> Option<u64> {
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
