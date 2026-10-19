#!/usr/bin/env bash
# cpu-check.sh - find out what CPU a VPS really runs on and how fast/steady its cores are.
#
# Measures the REAL clock speed (lscpu's "@ 2.0GHz" is just the virtual CPU's label),
# per-core and all-cores-at-once speed, steal time (other customers using your CPU),
# scheduling jitter (pauses the bot would feel), and a Bun speed score.
#
# Run it on the Cherry VPS AND on the OVH Rise-S, then compare.
# Stop the bot first (it keeps one core at 100% and would skew the results).
#   bash cpu-check.sh            (takes ~2 minutes)
set -u
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
N=$(nproc)

if ! command -v gcc >/dev/null; then
  echo "Installing gcc (needed for the clock test)..."
  (apt-get update -qq && apt-get install -y -qq gcc) >/dev/null 2>&1 || { echo "Please install gcc: apt install gcc"; exit 1; }
fi

cat > "$W/probe.c" <<'EOF'
#define _GNU_SOURCE
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static uint64_t now_ns(void){ struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t); return (uint64_t)t.tv_sec*1000000000ull+t.tv_nsec; }

/* 100 dependent multiplies per loop pass: each must wait for the previous one.
   A 64-bit multiply takes exactly 3 clock cycles on every modern AMD and Intel core,
   so multiplies/second x 3 = real clock speed. */
#define A "imul %2,%0\n\t"
#define A10 A A A A A A A A A A
#define A100 A10 A10 A10 A10 A10 A10 A10 A10 A10 A10
static void chain(uint64_t it){ uint64_t a=1,k=1; __asm__ volatile("1:\n\t" A100 "dec %1\n\tjnz 1b\n\t":"+r"(a),"+r"(it):"r"(k):"cc"); }

/* 4 independent chains: shows how much of the physical core you really get
   (drops if a "sibling" vCPU on the same physical core is busy). */
#define B "add %5,%0\n\tadd %5,%1\n\tadd %5,%2\n\tadd %5,%3\n\t"
#define B10 B B B B B B B B B B
#define B50 B10 B10 B10 B10 B10
static void wide(uint64_t it){ uint64_t a=0,b=0,c=0,d=0,k=1; __asm__ volatile("1:\n\t" B50 "dec %4\n\tjnz 1b\n\t":"+r"(a),"+r"(b),"+r"(c),"+r"(d),"+r"(it):"r"(k):"cc"); }

int main(int argc,char**argv){
  const char*mode=argc>1?argv[1]:"freq"; double secs=argc>2?atof(argv[2]):3;
  if(!strcmp(mode,"jitter")){
    uint64_t start=now_ns(),end=start+(uint64_t)(secs*1e9),prev=start,t,max=0,c50=0,c1m=0;
    while((t=now_ns())<end){ uint64_t g=t-prev; if(g>max)max=g; if(g>50000)c50++; if(g>1000000)c1m++; prev=t; }
    printf("%.0f %llu %llu\n",max/1000.0,(unsigned long long)c50,(unsigned long long)c1m); return 0;
  }
  int w=!strcmp(mode,"wide"); uint64_t blk=w?200000:70000; double best=0,sum=0; int n=0;
  uint64_t end=now_ns()+(uint64_t)(secs*1e9);
  while(now_ns()<end){ uint64_t t0=now_ns(); if(w) wide(blk); else chain(blk); uint64_t dt=now_ns()-t0;
    double r=(w?200.0:300.0)*blk/dt; /* chain: cycles per ns = GHz */ if(r>best)best=r; sum+=r; n++; }
  printf("%.2f %.2f\n",best,sum/n); return 0;
}
EOF
gcc -O2 -o "$W/probe" "$W/probe.c" || { echo "compile failed"; exit 1; }

steal_pct(){ # steal% of all CPU time between two /proc/stat snapshots
  awk -v a="$1" -v b="$2" 'BEGIN{split(a,x," ");split(b,y," ");t=0;for(i=2;i<=9;i++)t+=y[i]-x[i]; printf "%.1f", t?100*(y[9]-x[9])/t:0}'; }

echo "=================== CPU INFO ==================="
lscpu | grep -E "Model name|^CPU\(s\)|Thread\(s\) per core|Hypervisor|L3 cache" | sed 's/^ */  /'
flags=$(grep -m1 '^flags' /proc/cpuinfo)
for f in avx512f avx512_bf16 avx_vnni vaes; do echo "$flags" | grep -qw $f && echo "  flag $f: yes" || echo "  flag $f: no"; done
echo "  (VMs often hide flags to look like the named model, so flags alone don't prove the host CPU)"

echo; echo "============ 1) REAL CLOCK, ONE CORE AT A TIME ============"
echo "  core   max_GHz  avg_GHz"
single=()
for c in $(seq 0 $((N-1))); do
  r=$(taskset -c $c "$W/probe" freq 3); single+=("$r")
  printf "  %-5s  %-7s  %s\n" "$c" $r
done

echo; echo "============ 2) ALL CORES LOADED AT ONCE ============"
s1=$(grep '^cpu ' /proc/stat)
for c in $(seq 0 $((N-1))); do taskset -c $c "$W/probe" freq 5 > "$W/all_$c" & done; wait
s2=$(grep '^cpu ' /proc/stat)
echo "  core   max_GHz  avg_GHz"
for c in $(seq 0 $((N-1))); do printf "  %-5s  %-7s  %s\n" "$c" $(cat "$W/all_$c"); done
echo "  steal time during this test: $(steal_pct "$s1" "$s2")%   (0-1% good, >5% = neighbours taking your CPU)"

echo; echo "============ 3) HOW MUCH OF A PHYSICAL CORE YOU GET ============"
alone=$(taskset -c 0 "$W/probe" wide 3 | awk '{print $2}')
for c in $(seq 1 $((N-1))); do taskset -c $c "$W/probe" wide 5 >/dev/null & done
sleep 0.5; busy=$(taskset -c 0 "$W/probe" wide 3 | awk '{print $2}'); wait
echo "  core 0 work rate alone:            $alone ops/ns"
echo "  core 0 work rate, other cores busy: $busy ops/ns"
awk -v a="$alone" -v b="$busy" 'BEGIN{printf "  -> you keep %.0f%% of core 0 when everything is busy (~100%% = real core, ~50-60%% = shares a physical core)\n", 100*b/a}'

echo; echo "============ 4) JITTER (pauses the bot would feel), 20 s on core 0 ============"
s1=$(grep '^cpu ' /proc/stat)
read mx c50 c1m < <(taskset -c 0 "$W/probe" jitter 20)
s2=$(grep '^cpu ' /proc/stat)
echo "  longest pause: ${mx} us | pauses >50us: $c50 | pauses >1ms: $c1m | steal: $(steal_pct "$s1" "$s2")%"
echo "  (bare metal: longest pause usually <100 us and 0 pauses >1ms)"

if command -v bun >/dev/null; then
  echo; echo "============ 5) BUN SPEED SCORE (single thread, higher = faster) ============"
  cat > "$W/b.js" <<'EOF'
const { createHash } = require("crypto");
const msg = JSON.stringify({ slot: 1, accounts: Array.from({ length: 30 }, (_, i) => "Acc" + i + "x".repeat(40)), data: "A".repeat(600) });
const buf = Buffer.alloc(1232, 7);
let n = 0; const t0 = performance.now(), end = t0 + 5000;
while (performance.now() < end) {
  for (let i = 0; i < 200; i++) { JSON.parse(msg); createHash("sha256").update(buf).digest(); buf.readBigUInt64LE(i); }
  n += 200;
}
console.log(Math.round(n / ((performance.now() - t0) / 1000)));
EOF
  echo "  $(taskset -c 0 bun "$W/b.js") ops/s   (compare this number between servers)"
fi

echo; echo "============ WHAT THE CLOCK SAYS ============"
best=$(printf "%s\n" "${single[@]}" | awk '{if($1>m)m=$1}END{print m}')
awk -v g="$best" 'BEGIN{
  if (g>=4.4)      print "  Top single-core speed " g " GHz -> consistent with a Ryzen / Zen4-5 desktop-class host (4.5-5.7 GHz).";
  else if (g>=3.2) print "  Top single-core speed " g " GHz -> consistent with an EPYC server host (Milan/Genoa boost ~3.5-4.3 GHz), NOT a 5 GHz Ryzen.";
  else             print "  Top single-core speed " g " GHz -> slow/limited host or heavy throttling.";
}'
