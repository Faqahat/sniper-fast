//! UDP receivers for raw shreds: unicast (a provider pushes to our IP:port) and multicast (DoubleZero). Uses
//! recvmmsg in batches and kernel receive timestamps (SO_TIMESTAMPNS, CLOCK_REALTIME), so the arrival time is taken
//! when the packet reaches the socket, not when our code gets around to it.
use crate::feeds::clock::now_ns;
use anyhow::{bail, Context, Result};
use socket2::{Domain, Protocol, Socket, Type};
use std::net::{Ipv4Addr, SocketAddrV4};
use std::os::fd::AsRawFd;
use std::time::Duration;

pub struct Packet<'a> { pub data: &'a [u8], pub t_ns: u64, pub src: Ipv4Addr, pub kernel_ts: bool, pub truncated: bool }

pub fn open_unicast(bind: &str) -> Result<Socket> {
    let addr: SocketAddrV4 = bind.parse().with_context(|| format!("bad bind address {bind}"))?;
    let s = Socket::new(Domain::IPV4, Type::DGRAM, Some(Protocol::UDP))?;
    s.set_reuse_address(true)?;
    s.bind(&addr.into()).with_context(|| format!("bind {bind}"))?;
    tune(&s)?;
    Ok(s)
}

pub fn open_multicast(group: &str, port: u16, iface: &str) -> Result<Socket> {
    let g: Ipv4Addr = group.parse().with_context(|| format!("bad multicast group {group}"))?;
    if !g.is_multicast() { bail!("{group} is not a multicast address"); }
    let cname = std::ffi::CString::new(iface)?;
    // SAFETY: valid NUL-terminated string
    let idx = unsafe { libc::if_nametoindex(cname.as_ptr()) };
    if idx == 0 { bail!("interface {iface} not found (is the tunnel up?)"); }
    let s = Socket::new(Domain::IPV4, Type::DGRAM, Some(Protocol::UDP))?;
    s.set_reuse_address(true)?;
    s.set_reuse_port(true)?;
    // bind to the group address so this socket only gets this group even when several share the port
    s.bind(&SocketAddrV4::new(g, port).into()).with_context(|| format!("bind {group}:{port}"))?;
    s.join_multicast_v4_n(&g, &socket2::InterfaceIndexOrAddress::Index(idx))
        .with_context(|| format!("join {group} on {iface}"))?;
    tune(&s)?;
    Ok(s)
}

fn tune(s: &Socket) -> Result<()> {
    let fd = s.as_raw_fd();
    let size: libc::c_int = 64 * 1024 * 1024;
    // SAFETY: plain setsockopt calls with correct sizes
    unsafe {
        // SO_RCVBUFFORCE ignores net.core.rmem_max (needs root / CAP_NET_ADMIN); fall back to the capped option
        if libc::setsockopt(fd, libc::SOL_SOCKET, libc::SO_RCVBUFFORCE, &size as *const _ as *const libc::c_void,
            std::mem::size_of::<libc::c_int>() as u32) != 0 {
            let _ = s.set_recv_buffer_size(size as usize);
        }
        let on: libc::c_int = 1;
        libc::setsockopt(fd, libc::SOL_SOCKET, libc::SO_TIMESTAMPNS, &on as *const _ as *const libc::c_void,
            std::mem::size_of::<libc::c_int>() as u32);
    }
    s.set_read_timeout(Some(Duration::from_millis(200)))?;
    Ok(())
}

pub fn recv_buffer_bytes(s: &Socket) -> usize { s.recv_buffer_size().unwrap_or(0) }

const BATCH: usize = 64;
const CMSG_SPACE: usize = 128;

/// Receive until `stop()` says so. Calls `on_packet` for every datagram. `maxpkt` is the largest datagram kept
/// (2048 for shreds; 65536 for feeds that send whole entry batches in one datagram).
pub fn run(s: &Socket, maxpkt: usize, mut stop: impl FnMut() -> bool, mut on_packet: impl FnMut(Packet)) -> Result<()> {
    let fd = s.as_raw_fd();
    let mut bufs = vec![vec![0u8; maxpkt]; BATCH];
    let mut ctrl = vec![[0u8; CMSG_SPACE]; BATCH];
    let mut addrs: Vec<libc::sockaddr_in> = vec![unsafe { std::mem::zeroed() }; BATCH];
    let mut iovs: Vec<libc::iovec> = bufs.iter_mut()
        .map(|b| libc::iovec { iov_base: b.as_mut_ptr() as *mut libc::c_void, iov_len: maxpkt }).collect();
    let mut hdrs: Vec<libc::mmsghdr> = vec![unsafe { std::mem::zeroed() }; BATCH];
    // GAP (2026-10-19), opt-in: UDP_PIN_CPU=n pins this receive thread; UDP_BUSY_POLL=1 spins on a non-blocking recvmmsg
    // instead of sleeping in the kernel (one core busy while the feed runs; measured in /root/gap/NOTES.md)
    if let Some(cpu) = std::env::var("UDP_PIN_CPU").ok().and_then(|v| v.parse::<usize>().ok()) {
        // SAFETY: plain sched_setaffinity on the calling thread
        unsafe { let mut set: libc::cpu_set_t = std::mem::zeroed(); libc::CPU_SET(cpu, &mut set); libc::sched_setaffinity(0, std::mem::size_of::<libc::cpu_set_t>(), &set); }
    }
    let busy = std::env::var("UDP_BUSY_POLL").map(|v| v == "1").unwrap_or(false);
    let flags = if busy { libc::MSG_DONTWAIT } else { libc::MSG_WAITFORONE };
    loop {
        if stop() { return Ok(()); }
        for i in 0..BATCH {
            let h = &mut hdrs[i].msg_hdr;
            h.msg_name = &mut addrs[i] as *mut _ as *mut libc::c_void;
            h.msg_namelen = std::mem::size_of::<libc::sockaddr_in>() as u32;
            h.msg_iov = &mut iovs[i];
            h.msg_iovlen = 1;
            h.msg_control = ctrl[i].as_mut_ptr() as *mut libc::c_void;
            h.msg_controllen = CMSG_SPACE as _;
            h.msg_flags = 0;
            hdrs[i].msg_len = 0;
        }
        // SAFETY: all pointers above stay valid for the call; the kernel writes at most the given lengths
        let n = unsafe { libc::recvmmsg(fd, hdrs.as_mut_ptr(), BATCH as u32, flags, std::ptr::null_mut()) };
        if n < 0 {
            let err = std::io::Error::last_os_error();
            match err.raw_os_error() {
                Some(libc::EAGAIN) | Some(libc::EINTR) => continue,
                _ => return Err(err.into()),
            }
        }
        let fallback_t = now_ns();
        for i in 0..n as usize {
            let len = hdrs[i].msg_len as usize;
            let (t_ns, kernel_ts) = kernel_timestamp(&hdrs[i].msg_hdr).map(|t| (t, true)).unwrap_or((fallback_t, false));
            let src = Ipv4Addr::from(u32::from_be(addrs[i].sin_addr.s_addr));
            let truncated = hdrs[i].msg_hdr.msg_flags & libc::MSG_TRUNC != 0;
            on_packet(Packet { data: &bufs[i][..len.min(maxpkt)], t_ns, src, kernel_ts, truncated });
        }
    }
}

fn kernel_timestamp(h: &libc::msghdr) -> Option<u64> {
    // SAFETY: walking the control buffer the kernel filled for this message
    unsafe {
        let mut c = libc::CMSG_FIRSTHDR(h);
        while !c.is_null() {
            if (*c).cmsg_level == libc::SOL_SOCKET && (*c).cmsg_type == libc::SCM_TIMESTAMPNS {
                let ts = std::ptr::read_unaligned(libc::CMSG_DATA(c) as *const libc::timespec);
                return Some(ts.tv_sec as u64 * 1_000_000_000 + ts.tv_nsec as u64);
            }
            c = libc::CMSG_NXTHDR(h, c);
        }
    }
    None
}
