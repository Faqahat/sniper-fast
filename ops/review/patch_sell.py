p="/root/review/arbx-rv/src/bin/snipe_engine.rs"
s=open(p).read()
hook = "    if simulate {\n        return run_simulate(probe, &key, user, &rpc, &stop).await;\n    }\n"
assert s.count(hook)==1
s = s.replace(hook, hook + "    if has(\"--rv-sellsim\") { return rv_sellsim(&key, user, &rpc).await; }\n")
s += r'''

// ======================= REVIEW-ONLY (/root/review copy): zero-cost buy+sell simulation =======================
async fn rv_simulate(rpc: &rpc::Rpc, user: Pk, key: &SigningKey, ixs: &[build::Ix], bh: [u8; 32], accts: &[Pk]) -> Result<serde_json::Value> {
    let msg = build::compile_v0(user, ixs, bh, &[], &[]).map_err(|e| anyhow::anyhow!(e))?;
    let mut raw = build::sign(&msg, key);
    for b in raw[1..65].iter_mut() { *b = 0; } // signature zeroed: this can never be a valid transaction
    let b64 = base64::engine::general_purpose::STANDARD.encode(&raw);
    let a: Vec<String> = accts.iter().map(|k| b58(k)).collect();
    let opts = serde_json::json!({ "sigVerify": false, "replaceRecentBlockhash": true, "encoding": "base64", "commitment": "processed",
        "accounts": { "encoding": "base64", "addresses": a } });
    eprintln!("  RV-SIM tx bytes={}", raw.len());
    rpc.call("simulateTransaction", serde_json::json!([b64, opts])).await
}

async fn rv_sellsim(key: &SigningKey, user: Pk, rpc: &rpc::Rpc) -> Result<()> {
    let m = arg("--mint").context("--rv-sellsim needs --mint")?;
    let mint = pk(&m);
    let mut before: Option<String> = None;
    let mut oldest: Option<String> = None;
    for _ in 0..40 {
        let mut o = serde_json::json!({ "limit": 1000 });
        if let Some(b) = &before { o["before"] = serde_json::json!(b); }
        let v = rpc.call("getSignaturesForAddress", serde_json::json!([m, o])).await?;
        let arr = v.as_array().cloned().unwrap_or_default();
        if arr.is_empty() { break; }
        let last = arr.last().and_then(|x| x["signature"].as_str()).map(|x| x.to_string());
        oldest = last.clone();
        if arr.len() < 1000 { break; }
        before = last;
    }
    let csig = oldest.context("no signatures")?;
    let t = rpc.call("getTransaction", serde_json::json!([csig, { "encoding": "base64", "maxSupportedTransactionVersion": 1, "commitment": "confirmed" }])).await?;
    let raw = t["transaction"][0].as_str().and_then(|b| base64::engine::general_purpose::STANDARD.decode(b).ok()).context("create tx")?;
    let (tx, _) = arbx::tx::parse_wire(&raw).context("parse_wire")?;
    let launch = snipe::detect_launch(&tx).context("oldest tx is not a create")?;
    eprintln!("RV-SELLSIM mint={} bc={} creator={} buyback={}", m, b58(&launch.bonding_curve), b58(&launch.creator), b58(&launch.buyback_fee_recipient));
    let bh = rpc.latest_blockhash().await?.0;
    let ata = pda::ata(&user, &mint, &pda::TOKEN_2022);
    // 1. the engine's buy (spend --spend-lamports, min_out 1) alone: tokens it would receive
    let (buy_ixs, spend) = build_buy(user, &launch, None, 1_000_000, 1);
    let v = rv_simulate(rpc, user, key, &buy_ixs, bh, &[ata]).await?;
    let val = &v["value"];
    let data = val["accounts"][0]["data"][0].as_str().and_then(|b| base64::engine::general_purpose::STANDARD.decode(b).ok()).unwrap_or_default();
    let amount = if data.len() >= 72 { u64::from_le_bytes(data[64..72].try_into().unwrap()) } else { 0 };
    eprintln!("RV-SELLSIM 1 buy-only: err={} cu={} tokens={amount} (spend {spend})", val["err"], val["unitsConsumed"]);
    if amount == 0 { bail!("no tokens in the simulated buy"); }
    // 2. buy + the engine's sell (sell_message_ixs, as round_trip_tail builds it, minus its compute-budget ixs) in ONE tx
    let cu = arg_u64("--cu-limit", 120_000) as u32;
    let price = arg_u64("--sell-cu-price-micro", 1_500_000);
    let sell_ixs = snipe_build::sell_message_ixs(user, &launch, amount, 0, 90_000, price, has("--wrap"));
    eprintln!("RV-SELLSIM sell ixs: {} (cu_limit ix data {:?}, cu_price ix data {:?}); sell programs: {}", sell_ixs.len(), sell_ixs[0].data, sell_ixs[1].data,
        sell_ixs.iter().map(|i| b58(&i.program)[..6].to_string()).collect::<Vec<_>>().join(","));
    let mut both: Vec<build::Ix> = buy_ixs.clone();
    both.extend(sell_ixs.iter().skip(2).cloned());
    let _ = cu;
    let v = rv_simulate(rpc, user, key, &both, bh, &[ata, user]).await?;
    let val = &v["value"];
    let logs: Vec<String> = val["logs"].as_array().map(|a| a.iter().filter_map(|l| l.as_str().map(String::from)).collect()).unwrap_or_default();
    eprintln!("RV-SELLSIM 2 buy+sell+close: err={} cu={} ata_after={} ", val["err"], val["unitsConsumed"], if val["accounts"][0].is_null() { "CLOSED (null)".to_string() } else { "STILL OPEN".to_string() });
    for l in logs.iter().filter(|l| l.contains("Instruction:") || l.contains("consumed") || l.contains("rror")) { eprintln!("     {l}"); }
    let lam_after = val["accounts"][1]["lamports"].as_u64().unwrap_or(0);
    let bal = rpc.call("getBalance", serde_json::json!([b58(&user), { "commitment": "processed" }])).await?;
    eprintln!("RV-SELLSIM payer lamports now {} -> after buy+sell sim {} (delta {})", bal["value"], lam_after, lam_after as i64 - bal["value"].as_i64().unwrap_or(0));
    Ok(())
}
'''
open(p,"w").write(s)
print("ok")
