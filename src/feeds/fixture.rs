//! Test support (PLAN WP-03 item 4, F12): the vendored Yellowstone proto text (`testdata/proto/`), a protobuf encoder
//! that takes field numbers from that text by name (never from the prost structs of `grpc.rs`), and the synthetic
//! stream fixture `testdata/grpc/stream.bin` built with it: wallet and pool account updates, PumpSwap transactions
//! (one with inner instructions, return data and loaded addresses, one failed), slots with a fork, and block meta.
//! Decoding these bytes with `grpc.rs`'s structs checks their field numbers against the upstream text.
use std::collections::HashMap;

/// message name -> field name -> (number, type, repeated)
pub struct Proto { msgs: HashMap<String, HashMap<String, (u32, String, bool)>> }

impl Proto {
    /// Every `.proto` under testdata/proto
    pub fn load() -> Proto {
        let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("testdata/proto");
        let mut text = String::new();
        for f in ["geyser.proto", "solana-storage.proto", "google/protobuf/timestamp.proto"] {
            text.push_str(&std::fs::read_to_string(dir.join(f)).unwrap());
            text.push('\n');
        }
        Proto::parse(&text)
    }

    /// A small parser for proto3 text: messages (with oneofs), their fields' numbers, types and labels
    pub fn parse(text: &str) -> Proto {
        let clean: String = text.lines().map(|l| l.split("//").next().unwrap_or("")).collect::<Vec<_>>().join("\n");
        let mut msgs: HashMap<String, HashMap<String, (u32, String, bool)>> = HashMap::new();
        // the open blocks: Some(message name) for a message or a oneof inside one, None for anything else
        let mut stack: Vec<Option<String>> = Vec::new();
        let mut stmt = String::new();
        for c in clean.chars() {
            match c {
                '{' => {
                    let w: Vec<&str> = stmt.split_whitespace().collect();
                    let open = match w.first() {
                        Some(&"message") => Some(w[1].to_string()),
                        Some(&"oneof") => stack.last().cloned().flatten(),
                        _ => None,
                    };
                    stack.push(open);
                    stmt.clear();
                }
                '}' => { stack.pop(); stmt.clear(); }
                ';' => {
                    if let Some(Some(m)) = stack.last() {
                        let norm = stmt.replace(", ", ",");
                        let w: Vec<&str> = norm.split_whitespace().collect();
                        if let Some(eq) = w.iter().position(|x| *x == "=") {
                            if eq >= 2 && !matches!(w[0], "option" | "reserved") {
                                let (name, ty) = (w[eq - 1], w[eq - 2]);
                                let num: u32 = w[eq + 1].trim_end_matches(|c: char| !c.is_ascii_digit()).parse().unwrap();
                                let repeated = w[..eq - 2].contains(&"repeated");
                                msgs.entry(m.clone()).or_default().insert(name.to_string(), (num, ty.rsplit('.').next().unwrap().to_string(), repeated));
                            }
                        }
                    }
                    stmt.clear();
                }
                c => stmt.push(c),
            }
        }
        Proto { msgs }
    }

    /// (number, type, repeated) of `msg.field`
    pub fn field(&self, msg: &str, field: &str) -> (u32, String, bool) {
        self.msgs.get(msg).and_then(|m| m.get(field)).cloned().unwrap_or_else(|| panic!("{msg}.{field} is not in testdata/proto"))
    }
    pub fn has(&self, msg: &str) -> bool { self.msgs.contains_key(msg) }

    pub fn msg(&self, name: &str) -> M<'_> { assert!(self.has(name), "no message {name} in testdata/proto"); M { p: self, name: name.into(), buf: Vec::new() } }
}

fn varint(o: &mut Vec<u8>, mut v: u64) { loop { let b = (v & 0x7f) as u8; v >>= 7; if v == 0 { o.push(b); return; } o.push(b | 0x80); } }

/// One message being encoded; every field is named, its number and wire type come from the proto text
pub struct M<'a> { p: &'a Proto, name: String, buf: Vec<u8> }

impl<'a> M<'a> {
    fn key(&mut self, f: &str, wire: u8, types: &[&str]) {
        let (n, ty, _) = self.p.field(&self.name, f);
        assert!(types.is_empty() || types.contains(&ty.as_str()), "{}.{f} is {ty}, not one of {types:?}", self.name);
        varint(&mut self.buf, ((n as u64) << 3) | wire as u64);
    }
    pub fn u64(mut self, f: &str, v: u64) -> Self { self.key(f, 0, &["uint64", "uint32", "int32", "int64", "bool", "SlotStatus", "CommitmentLevel"]); varint(&mut self.buf, v); self }
    pub fn i64(self, f: &str, v: i64) -> Self { self.u64(f, v as u64) }
    pub fn bool(self, f: &str, v: bool) -> Self { self.u64(f, v as u64) }
    pub fn bytes(mut self, f: &str, v: &[u8]) -> Self { self.key(f, 2, &["bytes"]); varint(&mut self.buf, v.len() as u64); self.buf.extend_from_slice(v); self }
    pub fn str(mut self, f: &str, v: &str) -> Self { self.key(f, 2, &["string"]); varint(&mut self.buf, v.len() as u64); self.buf.extend_from_slice(v.as_bytes()); self }
    pub fn msg(mut self, f: &str, m: M) -> Self {
        let (_, ty, _) = self.p.field(&self.name, f);
        assert_eq!(ty, m.name, "{}.{f} holds {ty}", self.name);
        self.key(f, 2, &[]);
        varint(&mut self.buf, m.buf.len() as u64);
        self.buf.extend_from_slice(&m.buf);
        self
    }
    /// a packed repeated varint field
    pub fn packed(mut self, f: &str, v: &[u64]) -> Self {
        let (_, _, rep) = self.p.field(&self.name, f);
        assert!(rep, "{}.{f} is not repeated", self.name);
        self.key(f, 2, &["uint64"]);
        let mut b = Vec::new();
        for x in v { varint(&mut b, *x); }
        varint(&mut self.buf, b.len() as u64);
        self.buf.extend(b);
        self
    }
    pub fn done(self) -> Vec<u8> { self.buf }
}

/// The field number of the first field in an encoded message (the prost structs' side of the check)
pub fn first_field(b: &[u8]) -> u32 {
    let (mut v, mut s) = (0u64, 0);
    for x in b { v |= ((x & 0x7f) as u64) << s; s += 7; if x & 0x80 == 0 { break; } }
    (v >> 3) as u32
}

// ------------------------------------------------------------------ the synthetic stream

pub const T0: u64 = 1_791_000_000_000_000_000;
pub fn k(n: u8) -> [u8; 32] { [n; 32] }
pub fn sig(n: u8) -> [u8; 64] { [n; 64] }
pub const WALLET: u8 = 0x51;
pub const SIGNER: u8 = 0x52;
pub const POOL: u8 = 0x61;
pub const VAULT0: u8 = 0x62;
pub const VAULT1: u8 = 0x63;
pub const ALT: u8 = 0x70;
pub const LW: u8 = 0x71;
pub const LR: u8 = 0x72;
pub const OURS: u8 = 0x81;
pub const T1: u8 = 0x91;
pub const T2: u8 = 0x92;
pub const OLD: u8 = 0x93;
pub fn pumpswap() -> [u8; 32] { *crate::venues::PUMPSWAP }
pub fn token() -> [u8; 32] { *crate::pda::TOKEN_PROGRAM }
pub fn vault_data(amount: u64) -> Vec<u8> { let mut v = vec![0u8; 165]; v[0..32].copy_from_slice(&k(0x41)); v[32..64].copy_from_slice(&k(0x42)); v[64..72].copy_from_slice(&amount.to_le_bytes()); v }

fn created(p: &Proto, ns: u64) -> M<'_> { p.msg("Timestamp").i64("seconds", (ns / 1_000_000_000) as i64).i64("nanos", (ns % 1_000_000_000) as i64) }

fn account<'a>(p: &'a Proto, key: [u8; 32], owner: [u8; 32], lamports: u64, data: &[u8], wv: u64, txn: Option<[u8; 64]>, slot: u64, startup: bool) -> M<'a> {
    let mut info = p.msg("SubscribeUpdateAccountInfo").bytes("pubkey", &key).u64("lamports", lamports).bytes("owner", &owner).bytes("data", data).u64("write_version", wv);
    if let Some(s) = txn { info = info.bytes("txn_signature", &s); }
    let mut a = p.msg("SubscribeUpdateAccount").msg("account", info).u64("slot", slot);
    if startup { a = a.bool("is_startup", true); }
    p.msg("SubscribeUpdate").msg("account", a)
}

fn slot<'a>(p: &'a Proto, slot: u64, parent: Option<u64>, status: u64, dead: Option<&str>) -> M<'a> {
    let mut s = p.msg("SubscribeUpdateSlot").u64("slot", slot);
    if let Some(x) = parent { s = s.u64("parent", x); }
    if status != 0 { s = s.u64("status", status); }
    if let Some(d) = dead { s = s.str("dead_error", d); }
    p.msg("SubscribeUpdate").msg("slot", s)
}

fn token_balance<'a>(p: &'a Proto, i: u64, owner: &str, amount: &str) -> M<'a> {
    p.msg("TokenBalance").u64("account_index", i).str("mint", &bs58::encode(k(0x41)).into_string())
        .msg("ui_token_amount", p.msg("UiTokenAmount").u64("decimals", 6).str("amount", amount)).str("owner", owner).str("program_id", &bs58::encode(token()).into_string())
}

/// A PumpSwap transaction: keys [signer, pool, vault0, vault1, PumpSwap, ComputeBudget, Token], a compute-unit limit and
/// price, the swap, one lookup table (loaded writable LW, readonly LR), an inner token transfer, logs and return data.
/// `fail`: InstructionError(2, Custom(6001)), logs omitted (`log_messages_none`)
fn pumpswap_tx(p: &Proto, s: [u8; 64], slot: u64, idx: u64, fail: bool) -> M<'_> {
    let cb = crate::tx::COMPUTE_BUDGET;
    let keys = [k(SIGNER), k(POOL), k(VAULT0), k(VAULT1), pumpswap(), cb, token()];
    let mut msg = p.msg("Message").msg("header", p.msg("MessageHeader").u64("num_required_signatures", 1).u64("num_readonly_unsigned_accounts", 3));
    for key in &keys { msg = msg.bytes("account_keys", key); }
    let mut limit = vec![2u8]; limit.extend(200_000u32.to_le_bytes());
    let mut price = vec![3u8]; price.extend(5_000u64.to_le_bytes());
    msg = msg.bytes("recent_blockhash", &k(0x33))
        .msg("instructions", p.msg("CompiledInstruction").u64("program_id_index", 5).bytes("data", &limit))
        .msg("instructions", p.msg("CompiledInstruction").u64("program_id_index", 5).bytes("data", &price))
        .msg("instructions", p.msg("CompiledInstruction").u64("program_id_index", 4).bytes("accounts", &[0, 1, 2, 3, 7, 8]).bytes("data", &[0x66, 1, 2, 3]))
        .bool("versioned", true)
        .msg("address_table_lookups", p.msg("MessageAddressTableLookup").bytes("account_key", &k(ALT)).bytes("writable_indexes", &[3]).bytes("readonly_indexes", &[9]));
    let tx = p.msg("Transaction").bytes("signatures", &s).msg("message", msg);
    let signer = bs58::encode(k(SIGNER)).into_string();
    let mut meta = p.msg("TransactionStatusMeta");
    if fail {
        let mut e = 8u32.to_le_bytes().to_vec(); e.push(2); e.extend(25u32.to_le_bytes()); e.extend(6001u32.to_le_bytes());
        meta = meta.msg("err", p.msg("TransactionError").bytes("err", &e));
    }
    meta = meta.u64("fee", 6_000).packed("pre_balances", &[1_000_000_000, 2_039_280, 2_039_280, 2_039_280, 1, 1, 1, 1, 1])
        .packed("post_balances", &[999_994_000, 2_039_280, 2_039_280, 2_039_280, 1, 1, 1, 1, 1]);
    if fail {
        meta = meta.bool("inner_instructions_none", true).bool("log_messages_none", true);
    } else {
        meta = meta.msg("inner_instructions", p.msg("InnerInstructions").u64("index", 2)
                .msg("instructions", p.msg("InnerInstruction").u64("program_id_index", 6).bytes("accounts", &[2, 0]).bytes("data", &[3, 9, 9]).u64("stack_height", 2)))
            .str("log_messages", "Program pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA invoke [1]").str("log_messages", "Program log: Instruction: Buy")
            .msg("pre_token_balances", token_balance(p, 2, &signer, "1000"))
            .msg("post_token_balances", token_balance(p, 2, &signer, "1500"))
            .msg("return_data", p.msg("ReturnData").bytes("program_id", &pumpswap()).bytes("data", &[1, 2, 3]))
            .u64("cost_units", 61_000);
    }
    meta = meta.bytes("loaded_writable_addresses", &k(LW)).bytes("loaded_readonly_addresses", &k(LR)).u64("compute_units_consumed", 45_000);
    let info = p.msg("SubscribeUpdateTransactionInfo").bytes("signature", &s).msg("transaction", tx).msg("meta", meta).u64("index", idx);
    p.msg("SubscribeUpdate").msg("transaction", p.msg("SubscribeUpdateTransaction").msg("transaction", info).u64("slot", slot))
}

/// The synthetic stream: (receive time, encoded SubscribeUpdate)
pub fn stream(p: &Proto) -> Vec<(u64, Vec<u8>)> {
    let sys = [0u8; 32];
    let mut v: Vec<M> = Vec::new();
    // our wallet paid for a landed transaction (it writes the wallet even when it fails)
    v.push(account(p, k(WALLET), sys, 4_999_995_000, &[], 100, Some(sig(OURS)), 1_000, false));
    v.push(slot(p, 1_000, Some(999), 0, None));
    // T1 moves the pool: both vaults and the pool account, each stamped with it
    v.push(account(p, k(VAULT0), token(), 2_039_280, &vault_data(1_000_000), 101, Some(sig(T1)), 1_000, false));
    v.push(account(p, k(VAULT1), token(), 2_039_280, &vault_data(2_000_000), 102, Some(sig(T1)), 1_000, false));
    v.push(account(p, k(POOL), pumpswap(), 3_000_000, &[7u8; 300], 103, Some(sig(T1)), 1_000, false));
    v.push(pumpswap_tx(p, sig(T1), 1_000, 17, false));
    // a late update from an older slot: recorded, refused by the store (stale)
    v.push(account(p, k(VAULT0), token(), 2_039_280, &vault_data(900_000), 90, Some(sig(OLD)), 999, false));
    // slots: 1001 begins (first shred, bank created), its sibling 1002 is processed, 1001 dies (a fork)
    v.push(slot(p, 1_001, Some(1_000), 3, None));
    v.push(slot(p, 1_001, Some(1_000), 5, None));
    v.push(slot(p, 1_002, Some(1_000), 0, None));
    v.push(slot(p, 1_001, Some(1_000), 6, Some("fork abandoned")));
    v.push(slot(p, 1_000, Some(999), 1, None));
    v.push(p.msg("SubscribeUpdate").msg("block_meta", p.msg("SubscribeUpdateBlockMeta").u64("slot", 1_000).str("blockhash", &bs58::encode(k(0x34)).into_string())
        .msg("block_time", p.msg("UnixTimestamp").i64("timestamp", 1_791_000_000)).msg("block_height", p.msg("BlockHeight").u64("block_height", 900))
        .u64("parent_slot", 999).str("parent_blockhash", &bs58::encode(k(0x33)).into_string()).u64("executed_transaction_count", 1_234).u64("entries_count", 64)));
    // a failed PumpSwap transaction (no logs from this provider)
    v.push(pumpswap_tx(p, sig(T2), 1_002, 3, true));
    // the second update of vault1 (same length: an XOR record), at startup
    v.push(account(p, k(VAULT1), token(), 2_039_280, &vault_data(2_100_000), 104, Some(sig(T2)), 1_002, true));
    v.into_iter().enumerate().map(|(i, m)| {
        let t = T0 + i as u64 * 1_000_000;
        // the provider stamps each message 2 ms before we receive it
        (t, m.msg("created_at", created(p, t - 2_000_000)).done())
    }).collect()
}

/// A PumpSwap transaction writing `writable` (after the signer; the program, ComputeBudget and Token programs read
/// only): the transaction stream's message for a route through several pools (review WP-04 #6)
fn route_tx<'a>(p: &'a Proto, s: [u8; 64], slot: u64, idx: u64, writable: &[[u8; 32]]) -> M<'a> {
    let mut keys = vec![k(SIGNER)];
    keys.extend_from_slice(writable);
    let prog = keys.len() as u64;
    keys.extend([pumpswap(), crate::tx::COMPUTE_BUDGET, token()]);
    let mut msg = p.msg("Message").msg("header", p.msg("MessageHeader").u64("num_required_signatures", 1).u64("num_readonly_unsigned_accounts", 3));
    for key in &keys { msg = msg.bytes("account_keys", key); }
    let accounts: Vec<u8> = (0..prog as u8).collect();
    msg = msg.bytes("recent_blockhash", &k(0x33)).msg("instructions", p.msg("CompiledInstruction").u64("program_id_index", prog).bytes("accounts", &accounts).bytes("data", &[0x66, 1, 2, 3]));
    let tx = p.msg("Transaction").bytes("signatures", &s).msg("message", msg);
    let meta = p.msg("TransactionStatusMeta").u64("fee", 5_000).u64("compute_units_consumed", 60_000);
    let info = p.msg("SubscribeUpdateTransactionInfo").bytes("signature", &s).msg("transaction", tx).msg("meta", meta).u64("index", idx);
    p.msg("SubscribeUpdate").msg("transaction", p.msg("SubscribeUpdateTransaction").msg("transaction", info).u64("slot", slot))
}

/// review WP-04 #6: pools A (POOL, VAULT0, VAULT1), B and C of the WP-04 sequences
pub const POOL_B: u8 = 0x64;
pub const VAULT_B0: u8 = 0x65;
pub const VAULT_B1: u8 = 0x66;
pub const POOL_C: u8 = 0x67;
pub const VAULT_C0: u8 = 0x68;
pub const VAULT_C1: u8 = 0x69;
/// the split route (S1), the transaction on C, the unknown-W transaction with a late member (S1b'), the minority fork's
pub const T3: u8 = 0x95;
pub const U: u8 = 0x96;
pub const T4: u8 = 0x97;
pub const T5: u8 = 0x98;

/// The WP-04 sequences as the state and transaction streams deliver them (review WP-04 #6; `testdata/grpc/wp04.bin`):
/// - **S1** (slot 2000): T3, a route through pools A and B, writes both pools' accounts; its transaction-stream message
///   (W(T3) authoritative) comes after its first two updates; U writes C meanwhile and resolves (quiescence, by stream
///   evidence) while T3 still misses B's vaults: C's routes through A and B are `pending_commit`; T3 then completes;
/// - **S1b'** (slot 2001): T4 writes A's vault1 (W unknown), resolves by quiescence, then its A vault0 write arrives: a
///   late member;
/// - **S8b** (slots 2002, 2003, siblings on 2001): T5 writes A in 2002, A's routes are `fork_pending` while both are
///   unconfirmed; 2003 is confirmed and 2002 abandoned with no `dead` status: A's 2002 versions are dropped.
pub fn wp04_stream(p: &Proto) -> Vec<(u64, Vec<u8>)> {
    let acct = |key: u8, amount: u64, wv: u64, txn: u8, slot: u64| account(p, k(key), token(), 2_039_280, &vault_data(amount), wv, Some(sig(txn)), slot, false);
    let pool = |key: u8, wv: u64, txn: u8, slot: u64| account(p, k(key), pumpswap(), 3_000_000, &[8u8; 300], wv, Some(sig(txn)), slot, false);
    // (receive time after T0 in µs, message): T3's updates within its 5 ms commit timeout; U's (W unknown) quiet 3 ms
    // before T3's last two; T4 quiet 3 ms before its late write; T5 quiet 3 ms before 2003 is processed
    let v: Vec<(u64, M)> = vec![
        (0, slot(p, 2_000, Some(1_999), 1, None)),
        (1_000, acct(VAULT0, 1_100_000, 201, T3, 2_000)),
        (1_200, acct(VAULT1, 1_900_000, 202, T3, 2_000)),
        (1_400, route_tx(p, sig(T3), 2_000, 5, &[k(POOL), k(VAULT0), k(VAULT1), k(POOL_B), k(VAULT_B0), k(VAULT_B1)])),
        (1_600, acct(VAULT_C0, 1_050_000, 203, U, 2_000)),
        (1_800, acct(VAULT_C1, 1_950_000, 204, U, 2_000)),
        (2_000, pool(POOL, 205, T3, 2_000)),
        (2_200, pool(POOL_B, 206, T3, 2_000)),
        (5_000, acct(VAULT_B0, 900_000, 207, T3, 2_000)),
        (5_200, acct(VAULT_B1, 2_100_000, 208, T3, 2_000)),
        (6_000, slot(p, 2_001, Some(2_000), 0, None)),
        (7_000, acct(VAULT1, 1_910_000, 209, T4, 2_001)),
        (8_000, slot(p, 2_001, Some(2_000), 1, None)),
        (9_000, slot(p, 2_002, Some(2_001), 3, None)),
        (10_000, slot(p, 2_002, Some(2_001), 5, None)),
        (11_000, acct(VAULT0, 1_090_000, 210, T4, 2_001)),
        (12_000, acct(VAULT0, 1_000_000, 211, T5, 2_002)),
        (12_200, acct(VAULT1, 2_000_000, 212, T5, 2_002)),
        (13_000, slot(p, 2_003, Some(2_001), 3, None)),
        (14_000, slot(p, 2_002, Some(2_001), 0, None)),
        (15_500, slot(p, 2_003, Some(2_001), 0, None)),
        (16_000, slot(p, 2_003, Some(2_001), 1, None)),
        (17_000, slot(p, 2_004, Some(2_003), 0, None)),
    ];
    v.into_iter().map(|(us, m)| {
        let t = T0 + us * 1_000;
        (t, m.msg("created_at", created(p, t - 2_000_000)).done())
    }).collect()
}
pub fn wp04_file_path() -> std::path::PathBuf { std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("testdata/grpc/wp04.bin") }

/// testdata/grpc/stream.bin: `u64 t_recv | u32 len | SubscribeUpdate bytes`, repeated
pub fn encode_file(s: &[(u64, Vec<u8>)]) -> Vec<u8> {
    let mut o = Vec::new();
    for (t, b) in s { o.extend(t.to_le_bytes()); o.extend((b.len() as u32).to_le_bytes()); o.extend(b); }
    o
}
pub fn decode_file(b: &[u8]) -> Vec<(u64, Vec<u8>)> {
    let mut out = Vec::new();
    let mut p = 0;
    while p < b.len() {
        let t = u64::from_le_bytes(b[p..p + 8].try_into().unwrap());
        let n = u32::from_le_bytes(b[p + 8..p + 12].try_into().unwrap()) as usize;
        out.push((t, b[p + 12..p + 12 + n].to_vec()));
        p += 12 + n;
    }
    out
}
pub fn file_path() -> std::path::PathBuf { std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("testdata/grpc/stream.bin") }
