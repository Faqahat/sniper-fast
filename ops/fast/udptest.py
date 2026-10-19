import socket, time, os, sys
# cost of one UDP send() syscall on this VM: to TEST-NET-1 (192.0.2.1, RFC 5737: dropped upstream) vs loopback
def run(dst, n, gap):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(dst)
    b = b'\x00' * 1100; v = []
    for i in range(n):
        t = time.perf_counter_ns(); s.send(b); v.append(time.perf_counter_ns() - t)
        if gap: time.sleep(gap)
    v.sort(); return v[len(v)//2]/1e3, v[int(len(v)*.9)]/1e3, v[int(len(v)*.99)]/1e3
cpu = int(sys.argv[1]) if len(sys.argv) > 1 else None
if cpu is not None: os.sched_setaffinity(0, {cpu})
print('cpu', cpu)
r = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); r.bind(('127.0.0.1', 0)); r.setblocking(False)
print('loopback  back-to-back p50/p90/p99 us', run(r.getsockname(), 200, 0))
print('TEST-NET  back-to-back p50/p90/p99 us', run(('192.0.2.1', 9), 300, 0))
print('TEST-NET  20ms apart   p50/p90/p99 us', run(('192.0.2.1', 9), 100, 0.02))
