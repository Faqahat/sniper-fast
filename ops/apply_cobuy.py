import os
os.chdir("/root/sniper-fast")
f = "src/bin/snipe_engine.rs"
s = open(f).read()
if "--demand-cobuy-sol" in s:
    print("already has cobuy gate")
else:
    # 1) flag def after observe_ms
    a1 = '    let observe_ms = arg_u64("--observe-ms", early_slots * 215 + 450); // wait this long after detect before the demand check + entry'
    assert s.count(a1) == 1, ("a1", s.count(a1))
    s = s.replace(a1, a1 + '\n    let demand_cobuy_lam = (arg_f64("--demand-cobuy-sol", 0.0) * 1e9) as u64; // co-buy demand gate: non-dev same-slot co-buy SOL')

    # 2) gate inserted right after the price-demand block, before the Entry comment
    a2 = '''                eprintln!("  PAPER PASS demand mint={} demand={:.3}x — entering", b58(&launch.mint), dm);
            }
            // Entry = first readable curve price (post-observe when the demand gate is on = realistic observe-then-buy).'''
    assert s.count(a2) == 1, ("a2", s.count(a2))
    gate = '''                eprintln!("  PAPER PASS demand mint={} demand={:.3}x — entering", b58(&launch.mint), dm);
            }
            // CO-BUY DEMAND GATE (--demand-cobuy-sol, the agent's OOS-perfect loser separator): observe, then require
            // non-dev same-slot co-buys >= threshold. co-buy SOL = curve real_sol (vq - 30 SOL virtual base) - dev buy.
            if demand_cobuy_lam > 0 {
                tokio::time::sleep(Duration::from_millis(observe_ms)).await;
                match curve_reserves(&rpc2, &bc).await {
                    Some((_vt, vq)) => {
                        let cobuy = vq.saturating_sub(30_000_000_000).saturating_sub(launch.dev_buy_lamports);
                        if cobuy < demand_cobuy_lam {
                            eprintln!("  PAPER SKIP no-cobuy mint={} cobuy={:.2}SOL (< {:.2})", b58(&launch.mint), cobuy as f64 / 1e9, demand_cobuy_lam as f64 / 1e9);
                            return;
                        }
                        eprintln!("  PAPER PASS cobuy mint={} cobuy={:.2}SOL — entering", b58(&launch.mint), cobuy as f64 / 1e9);
                    }
                    None => return,
                }
            }
            // Entry = first readable curve price (post-observe when the demand gate is on = realistic observe-then-buy).'''
    s = s.replace(a2, gate)
    open(f, "w").write(s)
    print("cobuy demand gate added to paper")
