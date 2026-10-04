//! One clock for every source: CLOCK_REALTIME in nanoseconds. Kernel UDP receive timestamps (SO_TIMESTAMPNS) are
//! CLOCK_REALTIME too, so raw-shred and gRPC arrivals are directly comparable on the same machine.

pub fn now_ns() -> u64 {
    let mut ts = libc::timespec { tv_sec: 0, tv_nsec: 0 };
    // SAFETY: valid pointer to a timespec on the stack
    unsafe { libc::clock_gettime(libc::CLOCK_REALTIME, &mut ts) };
    ts.tv_sec as u64 * 1_000_000_000 + ts.tv_nsec as u64
}
