//! QUIET BOOK (dip21; owner 10-27 PM: "keep the 24 h whale dump history on the host and give it to every node at engine start";
//! ops/strategies/presend/filter/QUIET_BOOK.md). The host's book: the whale dump history built from the host's copies of the raw
//! recording (ops/collect/keeper.sh) with the ENGINE'S OWN code (arbx::presend_quiet::build_book: the recording reader and the live
//! path's DumpBook rules), written atomically in the engine's journal format (session markers = the recording's continuous coverage,
//! one line per final dump), so the engine reads it with the loader it uses for its own journal (--presend-live-quiet-book).
//!
//!   quiet_book [--rec DIR] [--out FILE] [--hist-h 24] [--full] [--until UNIX_S] [--now UNIX_S] [--summary FILE]
//!     --rec      the recording copies (default /home/moiz/sniper-data/collect: every run_*/txs)
//!     --out      the book (default /home/moiz/sniper-data/quiet_book/quiet_book.jsonl); a pass EXTENDS it (reads only the chunks
//!                from its end on); --full rebuilds it from the last --hist-h hours
//!     --until    only the recording up to this block time (a book "as of" then); --now: the clock for the 24 h window (tests)
//!     --summary  also write the pass's numbers as JSON
//! One line on stdout. Exit 0 = written; 1 = failed (the previous book is left as it was); 2 = nothing to build from
use arbx::presend_quiet as pq;
use std::path::Path;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let arg = |f: &str| args.iter().position(|x| x == f).and_then(|i| args.get(i + 1)).cloned();
    let has = |f: &str| args.iter().any(|x| x == f);
    for a in args.iter().skip(1).filter(|a| a.starts_with("--")) {
        if !["--rec", "--out", "--hist-h", "--full", "--until", "--now", "--summary"].contains(&a.as_str()) { println!("quiet_book: unknown flag {a}"); std::process::exit(1); }
    }
    let rec = arg("--rec").unwrap_or_else(|| "/home/moiz/sniper-data/collect".into());
    let out = arg("--out").unwrap_or_else(|| "/home/moiz/sniper-data/quiet_book/quiet_book.jsonl".into());
    let hist_h: f64 = arg("--hist-h").and_then(|x| x.parse().ok()).unwrap_or(24.0);
    if !(hist_h > 0.0 && hist_h <= 48.0) { println!("quiet_book: --hist-h must be in (0, 48]"); std::process::exit(1); }
    let hist_ns = (hist_h * 3.6e12) as u64;
    let now_ns = arg("--now").and_then(|x| x.parse::<u64>().ok()).map(|s| s * 1_000_000_000).unwrap_or_else(arbx::feeds::clock::now_ns);
    let until = arg("--until").and_then(|x| x.parse::<i64>().ok());
    let full = has("--full");
    let runs = match pq::run_dirs(Path::new(&rec)) { Ok(r) => r, Err(e) => { println!("quiet_book: FAILED: {e}"); std::process::exit(1) } };
    if let Some(d) = Path::new(&out).parent() { let _ = std::fs::create_dir_all(d); }
    let prev = if full { None } else {
        let l = pq::load_state(Path::new(&out), now_ns, hist_ns);
        (!l.missing && l.err.is_none() && !l.sessions.is_empty()).then_some(l)
    };
    let mode = if prev.is_some() { "incremental" } else { "full" };
    let p = match pq::build_book(&runs, prev, now_ns, until, hist_ns) {
        Ok(p) => p,
        Err(e) => { println!("quiet_book: FAILED: {e} (the previous book is left as it was)"); std::process::exit(1) }
    };
    if p.book.sessions.is_empty() { println!("quiet_book: nothing to build from under {rec} (no recording in the last {hist_h} h)"); std::process::exit(2); }
    let (lines, bytes) = match pq::write_book(Path::new(&out), &p.book) {
        Ok(x) => x,
        Err(e) => { println!("quiet_book: FAILED to write {out}: {e} (the previous book is left as it was)"); std::process::exit(1) }
    };
    let sellers: std::collections::HashSet<[u8; 32]> = p.book.dumps.iter().map(|(d, _)| d.seller).collect();
    let cov = pq::coverage(&p.book.sessions.iter().map(|x| (x.t0, x.t1)).collect::<Vec<_>>(), now_ns, 30 * 60_000_000_000);
    let end = p.book.sessions.iter().map(|x| x.t1).max().unwrap_or(0);
    let pkt = |ns: u64| { let s = (ns / 1_000_000_000) as i64 + 5 * 3600; format!("{:02}:{:02} PKT", (s / 3600) % 24, (s / 60) % 60) };
    println!("quiet_book: {mode}{}: read {} chunks ({:.2} GB gz, {} txs; {} run(s) being written, complete to slot {} of {}), +{} dumps ({} held back to the next pass) in {:.1} s | \
              book {} dumps / {} sellers, {} session(s), {:.2} h continuous to {} (slot {}; {:.1} min before now) | {} lines, {:.2} MB -> {out}",
        if p.resumed { format!(" (resumed at slot {})", p.resume_slot) } else { String::new() }, p.st.chunks, p.st.bytes_gz as f64 / 1e9, p.st.txs, p.active_runs, p.end_slot, p.last_slot,
        p.added, p.held_back, p.secs, p.book.dumps.len(), sellers.len(), p.book.sessions.len(), cov.covered_ns as f64 / 3.6e12, pkt(end),
        p.book.sessions.iter().map(|x| x.s1).max().unwrap_or(0), now_ns.saturating_sub(end) as f64 / 6e10, lines, bytes as f64 / 1e6);
    if let Some(f) = arg("--summary") {
        let j = serde_json::json!({"mode": mode, "resumed": p.resumed, "resume_slot": p.resume_slot, "chunks": p.st.chunks, "gz_bytes": p.st.bytes_gz, "txs": p.st.txs,
            "added": p.added, "held_back": p.held_back, "secs": p.secs, "last_slot": p.last_slot, "end_slot": p.end_slot, "active_runs": p.active_runs, "dumps": p.book.dumps.len(), "sellers": sellers.len(), "sessions": p.book.sessions.len(),
            "covered_h": cov.covered_ns as f64 / 3.6e12, "end_ns": end, "end_slot": p.book.sessions.iter().map(|x| x.s1).max(), "lag_min": now_ns.saturating_sub(end) as f64 / 6e10,
            "lines": lines, "bytes": bytes, "out": out, "bad_lines_read": p.st.bad_lines, "truncated_chunks": p.st.truncated.len()});
        let _ = std::fs::write(&f, j.to_string());
    }
}
