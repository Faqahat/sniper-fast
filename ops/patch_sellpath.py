# Patch snipe_engine.rs: (1) --sell-path <name>: sells go through a different send path than buys (Helius 429'd sells);
# (2) --sell-held <mint,mint,..> --live: sell our whole balance of each mint via the sell path and close the ATA.
import re, sys
P = "/root/sniper-fast/src/bin/snipe_engine.rs"
s = open(P).read()
if "SELL_PATH" in s:
    print("already patched"); sys.exit(0)

# (1) static + helper after the imports
anchor = "use std::time::{Duration, Instant};\n"
assert s.count(anchor) == 1
s = s.replace(anchor, anchor + """
/// --sell-path: the path SELLS go through (default: the buy path). Helius Sender rate-limited our sells (HTTP 429).
static SELL_PATH: std::sync::OnceLock<Arc<send::Path>> = std::sync::OnceLock::new();
fn sp(p: &Arc<send::Path>) -> &Arc<send::Path> { SELL_PATH.get().unwrap_or(p) }
""", 1)

# set it in main after the fire path is chosen
a2 = "    let path = paths.list[pidx].clone();\n"
assert s.count(a2) == 1
s = s.replace(a2, a2 + """    if let Some(sn) = arg("--sell-path") {
        match paths.index(&sn) {
            Some(i) => { let _ = SELL_PATH.set(paths.list[i].clone()); eprintln!("snipe_engine: SELL path = {}", paths.list[i].name); }
            None => bail!("--sell-path {sn}: no such [[send]] path"),
        }
    }
""", 1)

# (2) --sell-held dispatch after the path is warm
a3 = "    wait_until_warm(&path, &rpc).await?;\n"
assert s.count(a3) == 1
s = s.replace(a3, a3 + """    if let Some(list) = arg("--sell-held") {
        if !live { bail!("--sell-held sends real sells: needs --live"); }
        run_sell_held(&key, user, &rpc, &path, &list).await?;
        stop.store(true, Ordering::Relaxed);
        return Ok(());
    }
""", 1)

# route the sells through sp(path)
n0 = s.count("send_and_poll(key, user, rpc, path, &sell_ixs, land_timeout)")
s = s.replace("send_and_poll(key, user, rpc, path, &sell_ixs, land_timeout)", "send_and_poll(key, user, rpc, sp(path), &sell_ixs, land_timeout)")
a4 = "        ixs.push(build::close_account_ix(snipe_build::assoc_user(&user, &launch.mint), user, user, *pda::TOKEN_2022));\n    }\n    send_and_poll(key, user, rpc, path, &ixs, land_timeout).await\n}"
assert s.count(a4) == 1, "do_sell anchor"
s = s.replace(a4, a4.replace("send_and_poll(key, user, rpc, path, &ixs", "send_and_poll(key, user, rpc, sp(path), &ixs"), 1)
print("sell calls rerouted:", n0, "+ do_sell")

# the --sell-held routine, appended before token_balance
a5 = "async fn token_balance(rpc: &rpc::Rpc, ata: &Pk) -> Result<u64> {"
assert s.count(a5) == 1
s = s.replace(a5, """/// --sell-held: for each mint, rebuild its Launch from the create tx (oldest signature, raw wire bytes -> the same
/// parser as the shred feed), then sell our whole Token-2022 balance via the SELL path and close the ATA (rent back).
async fn run_sell_held(key: &SigningKey, user: Pk, rpc: &rpc::Rpc, path: &Arc<send::Path>, list: &str) -> Result<()> {
    let cu = arg_u64("--cu-limit", 120_000) as u32;
    let price = arg_u64("--sell-cu-price-micro", 1_500_000);
    for m in list.split(',').map(|x| x.trim()).filter(|x| !x.is_empty()) {
        let mint = pk(m);
        let ata = pda::ata(&user, &mint, &pda::TOKEN_2022);
        let amount = token_balance(rpc, &ata).await?;
        if amount == 0 { eprintln!("  SELL-HELD {m}: balance 0 — skip"); continue; }
        // oldest signature = the create
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
        let Some(csig) = oldest else { eprintln!("  SELL-HELD {m}: no signatures — skip"); continue; };
        let t = rpc.call("getTransaction", serde_json::json!([csig, { "encoding": "base64", "maxSupportedTransactionVersion": 0, "commitment": "confirmed" }])).await?;
        let raw = t["transaction"][0].as_str().and_then(|b| base64::engine::general_purpose::STANDARD.decode(b).ok());
        let Some(raw) = raw else { eprintln!("  SELL-HELD {m}: create tx not decodable — skip"); continue; };
        let Some((tx, _)) = arbx::tx::parse_wire(&raw) else { eprintln!("  SELL-HELD {m}: parse_wire failed — skip"); continue; };
        let Some(launch) = snipe::detect_launch(&tx) else { eprintln!("  SELL-HELD {m}: oldest tx is not a create — skip"); continue; };
        let ixs = snipe_build::sell_message_ixs(user, &launch, amount, 0, cu, price, false);
        match send_and_poll(key, user, rpc, sp(path), &ixs, Duration::from_secs(30)).await {
            Ok(l) => eprintln!("  SELL-HELD {m}: qty={amount} sig={} land_slot={:?} ok={}", l.sig, l.land_slot, l.ok),
            Err(e) => eprintln!("  SELL-HELD {m}: send failed: {e}"),
        }
    }
    Ok(())
}

""" + a5, 1)
open(P, "w").write(s)
print("patched OK")
