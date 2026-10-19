#!/usr/bin/env python3
# Apply the RACE-GATE patch (2026-10-18) to snipe.rs + snipe_engine.rs. Additive; new flags default OFF.
# usage: patch_race.py <snipe.rs> <snipe_engine.rs> <snipe_race_add.rs> <engine_race_block.rs>
import sys

snipe_p, eng_p, add_p, blk_p = sys.argv[1:5]
s = open(snipe_p).read()
if "RACE-GATE helpers" not in s:
    i = s.index("#[cfg(test)]\nmod tests {")
    s = s[:i] + open(add_p).read().lstrip("\n") + "\n" + s[i:]
    open(snipe_p, "w").write(s)

e = open(eng_p).read()
assert "RACE GATE (2026-10-18)" not in e, "engine already patched"


def rep(old, new, cnt=1):
    global e
    assert e.count(old) == cnt, (e.count(old), old[:120])
    e = e.replace(old, new)


# ---- race block before run_paper_trade's doc comment
anchor = "/// --paper-trade (ZERO-COST): run the shred detector with the LIVE profit filter"
rep(anchor, open(blk_p).read().lstrip("\n") + "\n" + anchor)

# ---- PAPER loop
rep("""    loop {
        if Instant::now() >= deadline || stop.load(Ordering::Relaxed) { break; }
        let ev = match tokio::time::timeout(Duration::from_secs(2), arx.recv()).await {
            Ok(Some(e)) => e,
            Ok(None) => break,
            Err(_) => continue, // timeout: re-check the deadline
        };
        let arbx::feeds::Event::Tx(a) = ev else { continue };
        let Some(launch) = snipe::detect_launch(&a.tx) else { continue };
        if !dedup.first(launch.mint) { continue; } // same create seen on the other feed -> skip the duplicate
        if launch.dev_buy_lamports < min_dev_buy { skipped_dev += 1; continue; }
        if launch.dev_buy_lamports > max_dev_buy_lam { skipped_dev += 1; continue; } // R2 whale gate
        if !allow_nonvanilla && !launch.is_snipeable() { skipped_flag += 1; continue; }
        if uri_whitelist && !snipe::trusted_launch_host(&a.tx) { skipped_host += 1; continue; }
        if uri_blacklist && snipe::is_bot_launchpad(&a.tx) { skipped_host += 1; continue; }
        // CREATOR-FRESHNESS selection gate (4yFAz's measured selector): count the creator's signatures strictly
        // BEFORE this create slot; skip if the deployer isn't fresh. One getSignaturesForAddress; fine in paper.
        if max_creator_sigs > 0 {
            let prior = match rpc.call("getSignaturesForAddress", serde_json::json!([b58(&launch.creator), { "limit": max_creator_sigs + 20 }])).await {
                Ok(v) => v.as_array().map(|arr| arr.iter().filter(|s| s["slot"].as_u64().map(|sl| sl < a.slot).unwrap_or(false)).count() as u64).unwrap_or(0),
                Err(_) => 0,
            };
            if prior > max_creator_sigs { skipped_creator += 1; continue; }
        }
        detected += 1;
        let vanilla = launch.is_vanilla();
        eprintln!("  PAPER launch #{detected} slot={} mint={} dev_buy={} vanilla={vanilla} — tracking price path", a.slot, b58(&launch.mint), launch.dev_buy_lamports);
""", """    // RACE GATE (default off): with --race-gate / --race-log launches that pass the base filter go through the race watch.
    let mut race = RaceWatch::new(RaceCfg::from_args());
    if race.cfg.active() || race.cfg.dev_from_cap { eprintln!("RACE: {}", race.cfg.describe()); }
    let mut ready: Vec<(Launch, u64)> = Vec::new();
    loop {
        if Instant::now() >= deadline || stop.load(Ordering::Relaxed) { break; }
        let wait = if race.cfg.active() { race.next_wait() } else { Duration::from_secs(2) };
        let ev = match tokio::time::timeout(wait, arx.recv()).await {
            Ok(Some(e)) => Some(e),
            Ok(None) => break,
            Err(_) => None, // timeout: re-check the deadline (and due race decisions)
        };
        if let Some(arbx::feeds::Event::Tx(a)) = ev {
            match snipe::detect_launch(&a.tx) {
                None => { if race.cfg.active() { race.observe(&a.tx); } }
                Some(mut launch) => 'create: {
                    race_dev_fix(&race.cfg, &mut launch, &a.tx);
                    if !dedup.first(launch.mint) { break 'create; } // same create seen on the other feed -> skip the duplicate
                    if launch.dev_buy_lamports < min_dev_buy { skipped_dev += 1; break 'create; }
                    if launch.dev_buy_lamports > max_dev_buy_lam { skipped_dev += 1; break 'create; } // R2 whale gate
                    if !allow_nonvanilla && !launch.is_snipeable() { skipped_flag += 1; break 'create; }
                    if uri_whitelist && !snipe::trusted_launch_host(&a.tx) { skipped_host += 1; break 'create; }
                    if uri_blacklist && snipe::is_bot_launchpad(&a.tx) { skipped_host += 1; break 'create; }
                    // CREATOR-FRESHNESS selection gate (4yFAz's measured selector): count the creator's signatures strictly
                    // BEFORE this create slot; skip if the deployer isn't fresh. One getSignaturesForAddress; fine in paper.
                    if max_creator_sigs > 0 {
                        let prior = match rpc.call("getSignaturesForAddress", serde_json::json!([b58(&launch.creator), { "limit": max_creator_sigs + 20 }])).await {
                            Ok(v) => v.as_array().map(|arr| arr.iter().filter(|s| s["slot"].as_u64().map(|sl| sl < a.slot).unwrap_or(false)).count() as u64).unwrap_or(0),
                            Err(_) => 0,
                        };
                        if prior > max_creator_sigs { skipped_creator += 1; break 'create; }
                    }
                    if !race.cfg.active() || race.add(&launch, &a.tx, a.slot) { ready.push((launch, a.slot)); }
                }
            }
        }
        if race.cfg.active() { ready.extend(race.due()); }
        for (launch, create_slot) in ready.drain(..) {
        detected += 1;
        let vanilla = launch.is_vanilla();
        eprintln!("  PAPER launch #{detected} slot={create_slot} mint={} dev_buy={} vanilla={vanilla} — tracking price path", b58(&launch.mint), launch.dev_buy_lamports);
""")
rep("""            eprintln!("  PAPER done mint={} entry={:.3e} fill={:.3}x peak_r={:.3} legs={} pnl_R={:+.4} pnl_NET{}{}",
                rec.mint, rec.entry, rec.fill, rec.peak_r, rec.legs, rec.pnl_r, net_str, scale_str);
            sink2.lock().unwrap().push(rec);
        });
    }
""", """            eprintln!("  PAPER done mint={} entry={:.3e} fill={:.3}x peak_r={:.3} legs={} pnl_R={:+.4} pnl_NET{}{}",
                rec.mint, rec.entry, rec.fill, rec.peak_r, rec.legs, rec.pnl_r, net_str, scale_str);
            sink2.lock().unwrap().push(rec);
        });
        } // ready.drain
    }
""")

# ---- LIVE loop (run_snipe_live)
rep("""    loop {
        if Instant::now() >= deadline || stop.load(Ordering::Relaxed) { break; }
        if spent.load(Ordering::Relaxed) + spend_per > total_cap { eprintln!("  TOTAL spend cap reached — no more fires."); break; }
        let ev = match tokio::time::timeout(Duration::from_secs(2), arx.recv()).await { Ok(Some(e)) => e, Ok(None) => break, Err(_) => continue };
        let arbx::feeds::Event::Tx(a) = ev else { continue };
        let Some(launch) = snipe::detect_launch(&a.tx) else { continue };
        if !dedup.first(launch.mint) { continue; } // same create seen on the other feed -> skip the duplicate
        if launch.dev_buy_lamports < min_dev_buy { continue; }
        if launch.dev_buy_lamports > max_dev_buy_lam { continue; } // whale gate: dev>8 SOL is poison (50% dump)
        if !allow_nonvanilla && !launch.is_snipeable() { continue; }
        if uri_whitelist && !snipe::trusted_launch_host(&a.tx) { skipped_host += 1; continue; }
        if uri_blacklist && snipe::is_bot_launchpad(&a.tx) { skipped_host += 1; continue; }
        // leader-proximity gate: only fire when the create slot's leader is close (skip far/unknown).
        if close_set.as_ref().map(|cs| !slot_leader.get(&a.slot).map(|l| cs.contains(l)).unwrap_or(false)).unwrap_or(false) {
            skipped_far += 1; continue;
        }
        // reserve a concurrency slot (never block the detector) and budget
        let permit = match sem.clone().try_acquire_owned() { Ok(p) => p, Err(_) => continue };
        if spent.fetch_add(spend_per, Ordering::Relaxed) + spend_per > total_cap { spent.fetch_sub(spend_per, Ordering::Relaxed); break; }
        fired.fetch_add(1, Ordering::Relaxed);
        let (key2, rpc2, path2) = (key.clone(), rpc.clone(), path.clone());
        let create_slot = a.slot;
        tokio::spawn(async move {""", """    // RACE GATE (default off): same watch as the paper loop. With no race flag the launch goes straight to `ready` and is
    // fired in the same iteration, exactly as before.
    let mut race = RaceWatch::new(RaceCfg::from_args());
    if race.cfg.active() || race.cfg.dev_from_cap { eprintln!("RACE: {}", race.cfg.describe()); }
    let mut ready: Vec<(Launch, u64)> = Vec::new();
    loop {
        if Instant::now() >= deadline || stop.load(Ordering::Relaxed) { break; }
        if spent.load(Ordering::Relaxed) + spend_per > total_cap { eprintln!("  TOTAL spend cap reached — no more fires."); break; }
        let wait = if race.cfg.active() { race.next_wait() } else { Duration::from_secs(2) };
        let ev = match tokio::time::timeout(wait, arx.recv()).await { Ok(Some(e)) => Some(e), Ok(None) => break, Err(_) => None };
        if let Some(arbx::feeds::Event::Tx(a)) = ev {
            match snipe::detect_launch(&a.tx) {
                None => { if race.cfg.active() { race.observe(&a.tx); } }
                Some(mut launch) => 'create: {
                    race_dev_fix(&race.cfg, &mut launch, &a.tx);
                    if !dedup.first(launch.mint) { break 'create; } // same create seen on the other feed -> skip the duplicate
                    if launch.dev_buy_lamports < min_dev_buy { break 'create; }
                    if launch.dev_buy_lamports > max_dev_buy_lam { break 'create; } // whale gate: dev>8 SOL is poison (50% dump)
                    if !allow_nonvanilla && !launch.is_snipeable() { break 'create; }
                    if uri_whitelist && !snipe::trusted_launch_host(&a.tx) { skipped_host += 1; break 'create; }
                    if uri_blacklist && snipe::is_bot_launchpad(&a.tx) { skipped_host += 1; break 'create; }
                    // leader-proximity gate: only fire when the create slot's leader is close (skip far/unknown).
                    if close_set.as_ref().map(|cs| !slot_leader.get(&a.slot).map(|l| cs.contains(l)).unwrap_or(false)).unwrap_or(false) {
                        skipped_far += 1; break 'create;
                    }
                    if !race.cfg.active() || race.add(&launch, &a.tx, a.slot) { ready.push((launch, a.slot)); }
                }
            }
        }
        if race.cfg.active() { ready.extend(race.due()); }
        for (launch, create_slot) in ready.drain(..) {
        // reserve a concurrency slot (never block the detector) and budget
        let permit = match sem.clone().try_acquire_owned() { Ok(p) => p, Err(_) => continue };
        if spent.fetch_add(spend_per, Ordering::Relaxed) + spend_per > total_cap { spent.fetch_sub(spend_per, Ordering::Relaxed); break; }
        fired.fetch_add(1, Ordering::Relaxed);
        let (key2, rpc2, path2) = (key.clone(), rpc.clone(), path.clone());
        tokio::spawn(async move {""")
rep("""            if let Err(e) = round_trip_launch(&key2, user, &rpc2, &path2, &launch, cap_lamports, max_sol, land_timeout, Some(create_slot)).await {
                eprintln!("  position {} ended: {e:#}", b58(&launch.mint));
            }
        });
    }
""", """            if let Err(e) = round_trip_launch(&key2, user, &rpc2, &path2, &launch, cap_lamports, max_sol, land_timeout, Some(create_slot)).await {
                eprintln!("  position {} ended: {e:#}", b58(&launch.mint));
            }
        });
        } // ready.drain
    }
""")
open(eng_p, "w").write(e)
print("patched OK")
