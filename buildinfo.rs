//! Build script (Cargo.toml `build = "buildinfo.rs"`; the name keeps it apart from the transaction builder
//! `src/build.rs`). It stamps the binary with its build provenance, which `src/provenance.rs` writes to meta.json
//! `build` (PLAN WP-01 item 3, MEASUREMENT §4.2):
//!   ARBX_GIT_COMMIT       HEAD's commit ("unknown" outside a git checkout)
//!   ARBX_GIT_DIRTY        "true" when the files that make up the binary differ from HEAD ("unknown" without git)
//!   ARBX_DIRTY_SHA256     sha256 of `git diff HEAD` over those files plus every untracked file under src/ (and an
//!                         untracked Cargo.lock), names and bytes; "" when clean
//!   ARBX_RUSTC            `rustc -V` of the compiler that built it
//!   ARBX_PROFILE          the Cargo profile (release, debug)
//!   ARBX_TARGET_FEATURES  the enabled target features (CARGO_CFG_TARGET_FEATURE)
//!   ARBX_BUILD_TS         build time, ns since the Unix epoch
//! The files that make up the binary are `BINARY_PATHS`. `rerun-if-changed` covers them plus the git files whose change
//! means a new commit or index state: HEAD, the ref file HEAD points to (resolved here, each time the script runs),
//! packed-refs and the index (review F20: watching HEAD alone misses a new commit on the same branch).
//!
//! The helpers are plain functions so the library's tests can include this file (`lib.rs`, `cfg(test)`).
use std::path::{Path, PathBuf};
use std::process::Command;

/// the files that make up the binary: what ARBX_GIT_DIRTY / ARBX_DIRTY_SHA256 describe and what reruns this script
pub const BINARY_PATHS: [&str; 4] = ["src", "Cargo.toml", "Cargo.lock", "buildinfo.rs"];

/// `git -C dir <args>` without optional locks (a build script must never rewrite the index it watches), stdout on success
pub fn git(dir: &Path, args: &[&str]) -> Option<Vec<u8>> {
    let out = Command::new("git").arg("-C").arg(dir).arg("--no-optional-locks").args(args).env("GIT_OPTIONAL_LOCKS", "0").output().ok()?;
    out.status.success().then_some(out.stdout)
}

fn git_line(dir: &Path, args: &[&str]) -> Option<String> {
    git(dir, args).map(|o| String::from_utf8_lossy(&o).trim().to_string()).filter(|s| !s.is_empty())
}

/// The ref file HEAD points to, resolved from HEAD's text: `ref: refs/heads/master` -> `<dir>/refs/heads/master`, looked
/// up in the worktree's own git dir first, then in the common dir (a linked worktree keeps its branches there). None for
/// a detached HEAD, or when the ref exists only in packed-refs.
pub fn resolve_head_ref(git_dir: &Path, common_dir: &Path, head_text: &str) -> Option<PathBuf> {
    let r = head_text.trim().strip_prefix("ref:")?.trim();
    if r.is_empty() || r.contains("..") { return None; }
    [git_dir, common_dir].iter().map(|d| d.join(r)).find(|p| p.is_file())
}

/// The git files to watch: HEAD, the resolved ref file, packed-refs and the index, only those that exist (Cargo treats
/// a missing rerun-if-changed file as changed, so a missing one would rebuild the crate on every build)
pub fn git_watch_paths(git_dir: &Path, common_dir: &Path) -> Vec<PathBuf> {
    let head = git_dir.join("HEAD");
    let mut out = vec![head.clone()];
    if let Some(r) = std::fs::read_to_string(&head).ok().and_then(|t| resolve_head_ref(git_dir, common_dir, &t)) { out.push(r); }
    out.push(common_dir.join("packed-refs"));
    out.push(git_dir.join("index"));
    out.retain(|p| p.is_file());
    out.dedup();
    out
}

/// (dirty, sha256 of the dirty state): `git diff HEAD` over `BINARY_PATHS`, then each untracked file under src/ (and an
/// untracked Cargo.lock) as `path\0bytes\0`, sorted by path. None without git.
pub fn dirty_state(root: &Path) -> Option<(bool, String)> {
    use sha2::{Digest, Sha256};
    // review N2: no external diff driver, no colour, no textconv: the bytes depend on the tree only, not on user config
    let mut args = vec!["-c", "core.quotePath=true", "diff", "--no-ext-diff", "--no-color", "--no-textconv", "HEAD", "--binary", "--"];
    args.extend(BINARY_PATHS);
    let diff = git(root, &args)?;
    let untracked = git(root, &["ls-files", "--others", "--exclude-standard", "-z", "--", "src", "Cargo.lock"])?;
    let mut files: Vec<&[u8]> = untracked.split(|b| *b == 0).filter(|f| !f.is_empty()).collect();
    files.sort();
    if diff.is_empty() && files.is_empty() { return Some((false, String::new())); }
    let mut h = Sha256::new();
    h.update(b"diff\0");
    h.update(&diff);
    for f in files {
        h.update(f);
        h.update([0u8]);
        h.update(std::fs::read(root.join(String::from_utf8_lossy(f).as_ref())).unwrap_or_default());
        h.update([0u8]);
    }
    Some((true, h.finalize().iter().map(|b| format!("{b:02x}")).collect()))
}

/// a path git printed, relative to `root` unless absolute
fn git_path(root: &Path, p: String) -> PathBuf { let p = PathBuf::from(p); if p.is_absolute() { p } else { root.join(p) } }

#[allow(dead_code)] // the library's tests include this file and do not call main
fn main() {
    let root = PathBuf::from(std::env::var("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR"));
    for p in BINARY_PATHS { println!("cargo:rerun-if-changed={}", root.join(p).display()); }
    let git_dir = git_line(&root, &["rev-parse", "--git-dir"]).map(|p| git_path(&root, p));
    let common = git_line(&root, &["rev-parse", "--git-common-dir"]).map(|p| git_path(&root, p));
    if let (Some(g), Some(c)) = (&git_dir, &common) {
        for p in git_watch_paths(g, c) { println!("cargo:rerun-if-changed={}", p.display()); }
    }
    let commit = git_line(&root, &["rev-parse", "HEAD"]).unwrap_or_else(|| "unknown".into());
    let (dirty, dirty_sha) = match dirty_state(&root) { Some((d, s)) => (d.to_string(), s), None => ("unknown".into(), String::new()) };
    let rustc = std::env::var("RUSTC").unwrap_or_else(|_| "rustc".into());
    let rustc_v = Command::new(&rustc).arg("-V").output().ok().filter(|o| o.status.success())
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string()).unwrap_or_else(|| "unknown".into());
    let ts = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_nanos()).unwrap_or(0);
    for (k, v) in [("ARBX_GIT_COMMIT", commit), ("ARBX_GIT_DIRTY", dirty), ("ARBX_DIRTY_SHA256", dirty_sha), ("ARBX_RUSTC", rustc_v),
        ("ARBX_PROFILE", std::env::var("PROFILE").unwrap_or_default()), ("ARBX_TARGET_FEATURES", std::env::var("CARGO_CFG_TARGET_FEATURE").unwrap_or_default()),
        ("ARBX_BUILD_TS", ts.to_string())] {
        println!("cargo:rustc-env={k}={}", v.replace(['\n', '\r'], " "));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tmp(name: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("arbx-buildinfo-{name}-{}-{:?}", std::process::id(), std::thread::current().id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(&d).unwrap();
        d
    }

    /// PLAN WP-01 acceptance (F20): the rerun-if-changed list includes the ref file HEAD points to, resolved, so a new
    /// commit on the same branch reruns the script; packed-refs and the index too; nothing that does not exist
    #[test]
    fn rerun_list_includes_the_resolved_ref_file() {
        let g = tmp("plain");
        std::fs::write(g.join("HEAD"), "ref: refs/heads/wp-01\n").unwrap();
        std::fs::create_dir_all(g.join("refs/heads")).unwrap();
        std::fs::write(g.join("refs/heads/wp-01"), "b4d94a3cd81183da0d21145e69e5319a0d54c547\n").unwrap();
        std::fs::write(g.join("index"), b"DIRC").unwrap();
        assert_eq!(git_watch_paths(&g, &g), vec![g.join("HEAD"), g.join("refs/heads/wp-01"), g.join("index")], "no packed-refs file: not listed");
        std::fs::write(g.join("packed-refs"), "# pack-refs\n").unwrap();
        assert_eq!(git_watch_paths(&g, &g), vec![g.join("HEAD"), g.join("refs/heads/wp-01"), g.join("packed-refs"), g.join("index")]);
        // the branch only in packed-refs (after `git pack-refs`): no loose ref file, packed-refs covers it
        std::fs::remove_file(g.join("refs/heads/wp-01")).unwrap();
        assert_eq!(git_watch_paths(&g, &g), vec![g.join("HEAD"), g.join("packed-refs"), g.join("index")]);
        // detached HEAD: HEAD itself changes on a new commit
        std::fs::write(g.join("HEAD"), "b4d94a3cd81183da0d21145e69e5319a0d54c547\n").unwrap();
        assert_eq!(resolve_head_ref(&g, &g, "b4d94a3cd81183da0d21145e69e5319a0d54c547\n"), None);
        assert_eq!(resolve_head_ref(&g, &g, "ref: ../../etc/passwd"), None);
        let _ = std::fs::remove_dir_all(&g);
    }

    /// a linked worktree: HEAD and the index in its own git dir, the branch ref in the common dir
    #[test]
    fn worktree_ref_resolves_in_the_common_dir() {
        let c = tmp("common");
        let g = c.join("worktrees/lane");
        std::fs::create_dir_all(&g).unwrap();
        std::fs::create_dir_all(c.join("refs/heads/lane")).unwrap();
        std::fs::write(g.join("HEAD"), "ref: refs/heads/lane/wp-01\n").unwrap();
        std::fs::write(c.join("refs/heads/lane/wp-01"), "0000\n").unwrap();
        std::fs::write(g.join("index"), b"DIRC").unwrap();
        assert_eq!(git_watch_paths(&g, &c), vec![g.join("HEAD"), c.join("refs/heads/lane/wp-01"), g.join("index")]);
        let _ = std::fs::remove_dir_all(&c);
    }

    /// this checkout: the helper resolves the real HEAD the same way git does
    #[test]
    fn resolves_this_checkouts_head() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR"));
        let Some(g) = git_line(root, &["rev-parse", "--git-dir"]).map(|p| git_path(root, p)) else { return };
        let c = git_line(root, &["rev-parse", "--git-common-dir"]).map(|p| git_path(root, p)).unwrap();
        let sym = git_line(root, &["symbolic-ref", "-q", "HEAD"]);
        let paths = git_watch_paths(&g, &c);
        assert_eq!(paths[0], g.join("HEAD"));
        if let Some(r) = sym {
            let loose = [g.join(&r), c.join(&r)].into_iter().find(|p| p.is_file());
            if let Some(l) = loose { assert!(paths.contains(&l), "{} in {paths:?}", l.display()); }
        }
    }
}
