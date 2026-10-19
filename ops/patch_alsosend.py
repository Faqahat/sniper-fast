# Patch snipe_engine.rs: --also-send <name>: every BUY (non-sell) send is signed once with BOTH paths' tips and sent
# through the fire path AND <name> at the same time (e.g. helius + nozomi). Sells (via --sell-path) are unaffected.
import sys
P = "/root/arbx-fast/src/bin/snipe_engine.rs"
s = open(P).read()
if "ALSO_PATH" in s:
    print("already patched"); sys.exit(0)

a = "fn sp(p: &Arc<send::Path>) -> &Arc<send::Path> { SELL_PATH.get().unwrap_or(p) }\n"
assert s.count(a) == 1
s = s.replace(a, a + """/// --also-send: a second path every BUY goes through too (same signed tx, both tips). Not used for sells.
static ALSO_PATH: std::sync::OnceLock<Arc<send::Path>> = std::sync::OnceLock::new();
""", 1)

a = """            None => bail!("--sell-path {sn}: no such [[send]] path"),
        }
    }
"""
assert s.count(a) == 1
s = s.replace(a, a + """    if let Some(an) = arg("--also-send") {
        match paths.index(&an) {
            Some(i) => { let _ = ALSO_PATH.set(paths.list[i].clone()); eprintln!("snipe_engine: ALSO-SEND buys via {}", paths.list[i].name); }
            None => bail!("--also-send {an}: no such [[send]] path"),
        }
    }
""", 1)

old = """    let _tip_owned: Vec<build::Ix>;
    let ixs: &[build::Ix] = match path.tip(0) {
        Some((tip_to, tip_lam)) if tip_lam > 0 => {
            let mut v = Vec::with_capacity(ixs.len() + 1);
            v.push(build::transfer_ix(user, tip_to, tip_lam));
            v.extend_from_slice(ixs);
            _tip_owned = v;
            &_tip_owned
        }
        _ => ixs,
    };
"""
new = """    let _tip_owned: Vec<build::Ix>;
    // --also-send: only for non-sell sends (a sell goes through SELL_PATH), and only to a different path.
    let also = ALSO_PATH.get().filter(|a| a.name != path.name && SELL_PATH.get().map_or(true, |s| !Arc::ptr_eq(s, path)));
    let mut tips: Vec<(Pk, u64)> = Vec::new();
    if let Some((t, l)) = path.tip(0) { if l > 0 { tips.push((t, l)); } }
    if let Some(a) = also { if let Some((t, l)) = a.tip(0) { if l > 0 { tips.push((t, l)); } } }
    let ixs: &[build::Ix] = if tips.is_empty() { ixs } else {
        let mut v = Vec::with_capacity(ixs.len() + tips.len());
        for (t, l) in &tips { v.push(build::transfer_ix(user, *t, *l)); }
        v.extend_from_slice(ixs);
        _tip_owned = v;
        &_tip_owned
    };
"""
assert s.count(old) == 1, "tip block"
s = s.replace(old, new, 1)

old = """    path.send(&raw, send::Prio { band: 0, crowd: 0, ev: 0 }, None).await.map_err(|e| anyhow::anyhow!("send refused: {e}"))?;
    let mut out = Landed { sig, send_slot, land_slot: None, ok: false };"""
new = """    match also {
        Some(a) => {
            let (r1, r2) = tokio::join!(path.send(&raw, send::Prio { band: 0, crowd: 0, ev: 0 }, None),
                                        a.send(&raw, send::Prio { band: 0, crowd: 0, ev: 0 }, None));
            match (&r1, &r2) {
                (Err(e1), Err(e2)) => bail!("send refused: {}: {e1} / {}: {e2}", path.name, a.name),
                (Err(e1), Ok(_)) => eprintln!("  (also-send: {} refused: {e1}; {} accepted)", path.name, a.name),
                (Ok(_), Err(e2)) => eprintln!("  (also-send: {} refused: {e2}; {} accepted)", a.name, path.name),
                _ => {}
            }
        }
        None => { path.send(&raw, send::Prio { band: 0, crowd: 0, ev: 0 }, None).await.map_err(|e| anyhow::anyhow!("send refused: {e}"))?; }
    }
    let mut out = Landed { sig, send_slot, land_slot: None, ok: false };"""
assert s.count(old) == 1, "send line"
s = s.replace(old, new, 1)
open(P, "w").write(s)
print("patched OK")
