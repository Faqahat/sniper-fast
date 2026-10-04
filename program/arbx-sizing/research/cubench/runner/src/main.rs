use litesvm::LiteSVM;
use solana_address::Address;
use solana_instruction::Instruction;
use solana_keypair::Keypair;
use solana_message::Message;
use solana_signer::Signer;
use solana_transaction::Transaction;

fn main() {
    let so = std::env::args().nth(1).unwrap();
    let mut fs = LiteSVM::mainnet_feature_set();
    fs.activate(&Address::from_str_const("5TuppMutoyzhUSfuYdhgzD47F92GL1g89KpCZQKqedxP"), 0);
    let mut svm = LiteSVM::new().with_feature_set(fs).with_builtins();
    let pid = Address::new_unique();
    svm.add_program_from_file(pid, &so).unwrap();
    let payer = Keypair::new();
    svm.airdrop(&payer.pubkey(), 10_000_000_000).unwrap();
    let names = ["loop+lcg baseline", "u64*u64->u128", "u128*u128 wrapping", "u128/u128 (wide divisor)", "u128/u64-sized divisor",
        "U256::mul128", "U256 div_rem 256/128", "isqrt u128 (Newton)", "DLMM bin step (drain test + fill)", "DLMM fee rate for a bin",
        "CPMM leg quote", "CPMM-CPMM closed form (u128 fixed point + isqrt)", "16-byte load"];
    let mut base = [0f64; 2];
    for op in 0u8..13 {
        let mut per = Vec::new();
        for n in [1u32, 51] {
            let mut d = vec![op]; d.extend_from_slice(&n.to_le_bytes());
            let cb = Instruction { program_id: Address::from_str_const("ComputeBudget111111111111111111111111111111"), accounts: vec![], data: { let mut v = vec![2u8]; v.extend_from_slice(&1_400_000u32.to_le_bytes()); v } };
            let ix = Instruction { program_id: pid, accounts: vec![], data: d };
            let tx = Transaction::new(&[&payer], Message::new(&[cb, ix], Some(&payer.pubkey())), svm.latest_blockhash());
            let r = svm.send_transaction(tx).map_err(|e| format!("{:?}", e.meta.logs)).unwrap();
            let line = r.logs.iter().find(|l| l.starts_with("Program log: 0x")).unwrap().clone();
            let cu = u64::from_str_radix(line.split(", ").nth(2).unwrap().trim_start_matches("0x"), 16).unwrap();
            per.push(cu as f64);
            svm.expire_blockhash();
        }
        let per_op = (per[1] - per[0]) / 50.0;
        if op == 0 { base = [per[0], per_op]; }
        println!("{:>2} {:<50} {:>8.1} CU/op (net of loop {:>6.1})", op, names[op as usize], per_op, per_op - base[1]);
    }
}
