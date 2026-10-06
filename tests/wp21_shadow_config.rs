//! PLAN-ADDENDUM WP-21, through the real binary: the shadow test's config (deploy/arbx-wp21-shadow.toml, FT-009) passes
//! `arbx check` in an empty environment (nothing reaches the network, no secret is read) with Raydium CLMM and Orca
//! Whirlpool on in `quote` mode, a canary impossible, the frz wallet and FT-006's builder; its seed list
//! (data/seed-pools-wp21-shadow.csv) is the 2026-10-06 list unchanged plus Raydium CLMM / Orca Whirlpool rows the seed
//! reader parses; the other maintained configs keep both venues off.
use std::path::{Path, PathBuf};
use std::process::Command;

const BIN: &str = env!("CARGO_BIN_EXE_arbx");

fn repo(rel: &str) -> PathBuf { Path::new(env!("CARGO_MANIFEST_DIR")).join(rel) }

fn check(cfg: &str) -> String {
    let out = Command::new(BIN).env_clear().args(["check", "--config"]).arg(repo(cfg)).output().unwrap();
    let text = String::from_utf8_lossy(&out.stdout).to_string();
    assert!(out.status.success(), "{cfg}: {text}{}", String::from_utf8_lossy(&out.stderr));
    text
}

#[test]
fn the_wp21_shadow_config_passes_arbx_check() {
    let text = check("deploy/arbx-wp21-shadow.toml");
    assert!(text.contains("mode shadow, wallet FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS"), "{text}");
    let venues = text.lines().find(|l| l.starts_with("venues (WP-21): ")).unwrap_or_else(|| panic!("no venues line: {text}"));
    assert!(venues.contains("Raydium CLMM quote (") && venues.contains("Orca Whirlpool quote (") && venues.contains("venue_quote_only"), "{venues}");
    assert!(text.contains("enabled send paths: jito-bundle (bundle-only"), "{text}");
    assert!(text.contains("dry run simulate true"), "{text}");
    // FT-006's tips, unchanged
    assert!(text.contains("[tips] by band [0.2, 0.2, 0.2, 0.6, 0.7] of the edge"), "{text}");
    // the config itself: shadow, no canary, the WP-21 seed list
    let cfg = arbx::config::Config::load(&repo("deploy/arbx-wp21-shadow.toml")).unwrap();
    assert_eq!((cfg.mode.as_str(), cfg.canary.enabled), ("shadow", false));
    assert_eq!((cfg.pools.rayclmm.as_str(), cfg.pools.whirlpool.as_str()), ("quote", "quote"));
    assert!(!cfg.pools.venue_sends(arbx::venues::Venue::RayClmm) && !cfg.pools.venue_sends(arbx::venues::Venue::Whirlpool));
    assert_eq!(cfg.pools.seed_csv, "/root/arbx/data/seed-pools-wp21-shadow.csv");
    // FT-006's config but for the WP-21 lines: every other line is the same
    let ft006 = std::fs::read_to_string(repo("deploy/arbx-ft006-frz.toml")).unwrap();
    let wp21 = std::fs::read_to_string(repo("deploy/arbx-wp21-shadow.toml")).unwrap();
    let body = |s: &str| s.lines().filter(|l| !l.starts_with('#')).map(String::from).collect::<Vec<_>>();
    // the two venue switches added, then line for line FT-006's but the seed list and [canary] enabled
    let (a, b) = (body(&ft006), body(&wp21));
    assert_eq!(b.iter().filter(|l| l.starts_with("rayclmm =") || l.starts_with("whirlpool =")).count(), 2);
    let b: Vec<String> = b.into_iter().filter(|l| !l.starts_with("rayclmm =") && !l.starts_with("whirlpool =")).collect();
    assert_eq!(a.len(), b.len());
    let diffs: Vec<(&String, &String)> = a.iter().zip(&b).filter(|(x, y)| x != y).collect();
    assert_eq!(diffs.len(), 2, "{diffs:?}");
    assert!(diffs[0].1.starts_with("seed_csv = ") && diffs[1].1.starts_with("enabled = false   # WP-21"), "{diffs:?}");
}

#[test]
fn the_wp21_seed_list_extends_the_2026_10_06_list() {
    let base = std::fs::read_to_string(repo("data/seed-pools-20261006.csv")).unwrap();
    let wp21 = std::fs::read_to_string(repo("data/seed-pools-wp21-shadow.csv")).unwrap();
    assert!(wp21.starts_with(&base), "the 2026-10-06 list's rows first, unchanged");
    let added: Vec<Vec<&str>> = wp21[base.len()..].lines().map(|l| l.split(',').collect()).collect();
    assert!(added.len() >= 200, "{} rows added", added.len());
    let mut seen = std::collections::HashSet::new();
    for r in &added {
        assert_eq!(r.len(), 3, "{r:?}");
        let v = arbx::venues::Venue::parse(r[0]).unwrap_or_else(|| panic!("{r:?}: venue"));
        assert!(v.is_clmm(), "{r:?}");
        assert_eq!(bs58::decode(r[1]).into_vec().map(|b| b.len()).ok(), Some(32), "{r:?}");
        assert!(r[2].starts_with("wp21:"), "{r:?}");
        assert!(seen.insert(r[1]) && !base.contains(r[1]), "{r:?}: listed once");
    }
    for v in ["RayCLMM", "Whirlpool"] { assert!(added.iter().filter(|r| r[0] == v).count() >= 50, "{v}"); }
}

/// Every other deploy config passes `arbx check` and keeps the WP-21 venues off (`[pools] rayclmm` / `whirlpool` default
/// "off")
#[test]
fn the_other_configs_keep_the_wp21_venues_off() {
    let mut files: Vec<String> = std::fs::read_dir(repo("deploy")).unwrap().map(|e| e.unwrap().file_name().to_string_lossy().into_owned())
        .filter(|n| n.ends_with(".toml") && n != "arbx-wp21-shadow.toml").map(|n| format!("deploy/{n}")).collect();
    files.sort();
    assert!(files.len() >= 4, "{files:?}");
    for f in &files {
        let f = f.as_str();
        let text = check(f);
        let venues = text.lines().find(|l| l.starts_with("venues (WP-21): ")).unwrap_or_else(|| panic!("{f}: no venues line"));
        assert!(venues.contains("Raydium CLMM off (") && venues.contains("Orca Whirlpool off ("), "{f}: {venues}");
    }
}
