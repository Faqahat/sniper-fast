p="/root/review/arbx-rv/src/bin/snipe_engine.rs"
s=open(p).read()
old="                if f.junk { return; }\n"
new='''                if f.junk {
                    // REVIEW-ONLY: dump the real signed tx the junk run discarded (never sent)
                    if let Ok(fname) = std::env::var("RV_DUMP") {
                        use std::io::Write as _;
                        let tips: Vec<serde_json::Value> = p.tips.iter().map(|(k, l)| serde_json::json!([b58(k), l])).collect();
                        let j = serde_json::json!({ "mint": b58(&p.launch.mint), "slot": p.slot, "route": p.meta.route, "leader": p.meta.leader, "client": p.meta.client,
                            "fan": p.fan.iter().map(|x| x.name.clone()).collect::<Vec<_>>(), "tips": tips, "min_out": p.min_out, "bh": b58(&p.bh), "dev": p.launch.dev_buy_lamports,
                            "creator": b58(&p.launch.creator), "bc": b58(&p.launch.bonding_curve), "buyback": b58(&p.launch.buyback_fee_recipient), "fast_built": p.fast_built,
                            "sig": p.meta.sig, "t_ns": arbx::feeds::clock::now_ns(), "raw": base64::engine::general_purpose::STANDARD.encode(&p.raw) });
                        if let Ok(mut fh) = std::fs::OpenOptions::new().create(true).append(true).open(&fname) { let _ = writeln!(fh, "{j}"); }
                    }
                    return;
                }
'''
assert s.count(old)==1
s=s.replace(old,new)
open(p,"w").write(s)
print("patched")
