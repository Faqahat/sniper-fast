#!/bin/bash
# Multi-region kit (owner 10-24 16:00 PKT): set up an EDGE server (Amsterdam) for the dip bot. Run FROM THE CONTAINER.
# Nothing here trades or sends a transaction. Secrets (.env, the edge config) go Frankfurt server -> edge through an ssh pipe
# (never printed, never written in the container). Each copied file is checked by sha256 on both ends.
# usage: bash ops/region/deploy_edge.sh <user@edge-host> [ssh port, 22] [region, ams]
set -eu
EDGE=${1:?usage: deploy_edge.sh user@host [port] [region]}; PORT=${2:-22}; REGION=${3:-ams}
FRA=it@84.32.100.36; FPORT=1996; R=/home/moiz/sniper
E() { ssh -p "$PORT" -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new "$EDGE" "$@"; }
F() { ssh -p "$FPORT" -o ConnectTimeout=20 "$FRA" "$@"; }
say() { echo "== $*"; }

say "1. edge basics"
S=$(E 'if [ "$(id -u)" = 0 ]; then echo ""; else echo sudo; fi')
E "uname -m; . /etc/os-release; echo \"\$PRETTY_NAME\"; ldd --version | head -1; nproc; free -m | awk '/Mem/{print \$2\" MB RAM\"}'; df -h / | tail -1"
GL=$(E "ldd --version | head -1 | grep -oE '[0-9]+\.[0-9]+$'")
awk -v g="$GL" 'BEGIN{exit !(g >= 2.34)}' || { echo "glibc $GL < 2.34: the engine needs a newer OS (Ubuntu 22.04+ / Debian 12+)"; exit 1; }

say "2. packages (tmux, python3, ping)"
E "$S bash -c 'command -v tmux >/dev/null && command -v python3 >/dev/null && command -v ping >/dev/null || (apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq tmux python3 iputils-ping >/dev/null)'; command -v tmux python3 ping"
E "$S mkdir -p /root/sniper-dip /root/dip /root/prod/runs /root/indep /root/sniper/deploy && $S chmod 700 /root/prod"

say "3. binaries + scripts from the container (engine = Frankfurt's dip9, sha checked)"
want=$(F 'sudo sha256sum /root/sniper-dip/snipe_engine_dip9' | cut -c1-64)
have=$(sha256sum $R/target/release/snipe_engine | cut -c1-64)
[ "$want" = "$have" ] || { echo "the container's engine build differs from Frankfurt's dip9: rebuild or copy it first"; exit 1; }
put() {   # put <local file> <remote path> <mode>
  scp -P "$PORT" -q "$1" "$EDGE:/tmp/.deploy.$$" && E "$S install -m $3 /tmp/.deploy.$$ $2 && rm -f /tmp/.deploy.$$"
  [ "$(sha256sum "$1" | cut -c1-64)" = "$(E "$S sha256sum $2" | cut -c1-64)" ] && echo "   ok $2" || { echo "   SHA MISMATCH $2"; exit 1; }
}
put $R/target/release/snipe_engine /root/sniper-dip/snipe_engine_dip9 755
put $R/target/release/arbx /root/sniper-dip/arbx 755
put $R/ops/prod/run_dip_prod.sh /root/prod/run_dip_prod.sh 755
put $R/ops/region/leader_rtt.py /root/sniper-dip/leader_rtt.py 644
# provisional near list (Netherlands leaders 5-12 ms from Frankfurt, none shared with Frankfurt's list; 19% of slots) until
# leader_rtt.py on the edge + split_near.py give the measured one
put $R/ops/region/near_leaders_${REGION}_provisional.txt /root/sniper-dip/near_leaders_${REGION}.txt 644

say "4. model, dev list, RPC helper, .env and the edge config from Frankfurt (pipe; secrets not shown)"
pipe() {  # pipe <frankfurt path> <edge path> <mode>
  F "sudo cat $1" | E "$S tee $2 >/dev/null && $S chmod $3 $2"
  [ "$(F "sudo sha256sum $1" | cut -c1-64)" = "$(E "$S sha256sum $2" | cut -c1-64)" ] && echo "   ok $2" || { echo "   SHA MISMATCH $2"; exit 1; }
}
F "sudo test -f /root/sniper-dip/dip_edge_$REGION.toml" || F "sudo bash /root/sniper-dip/make_edge_config.sh $REGION >/dev/null"
pipe /root/dip/IMIT1.json /root/dip/IMIT1.json 644
pipe /root/dip/cohort_train.json /root/dip/cohort_train.json 644
pipe /root/sniper-dip/dev_list.txt /root/sniper-dip/dev_list.txt 644
pipe /root/indep/common.py /root/indep/common.py 644
pipe /root/sniper/deploy/.env /root/sniper/deploy/.env 600
pipe /root/sniper-dip/dip_edge_$REGION.toml /root/sniper-dip/dip_edge_$REGION.toml 600

say "5. zero-cost checks on the edge"
E "$S /root/sniper-dip/snipe_engine_dip9 --help >/dev/null 2>&1 && echo '   engine runs' || echo '   ENGINE DID NOT START'"
E "for h in kaldera-amsterdam.constant-k.com ams-sender.helius-rpc.com ams1.nozomi.temporal.xyz amsterdam.mainnet.block-engine.jito.wtf ams.gateway.astralane.io ams.be.harmonic.gg ams.bolt.raiden.wtf ams1.landx.dev kaldera-frankfurt.constant-k.com; do printf '   %-40s ' \$h; ping -n -c 3 -i 0.2 -W 1 \$h 2>/dev/null | awk -F/ '/min\\/avg/{print \$4\" ms\"} END{if(!NR)print \"no reply\"}'; done"
cat <<EOT

NEXT (see ops/region/README.md):
  a) leader distances from the edge (zero cost):  ssh -p $PORT $EDGE "cd /root/sniper-dip && $S bash -c 'set -a; . /root/sniper/deploy/.env; set +a; REGION=$REGION RPC_HOST=rpc-amsterdam.constant-k.com python3 -I leader_rtt.py'"
  b) the OWNER creates the edge wallet on the edge (interactive passphrase, shows a one-time backup):
       sudo /root/sniper-dip/arbx keystore-encrypt --out /root/prod/wallet-$REGION.enc --generate --show-backup
     then writes its address:  echo <ADDRESS> | sudo tee /root/prod/wallet-$REGION.address   and funds it
  c) zero-cost engine checks on the edge (byte check of the buy templates, endpoint warm-up), then cheap landing probes
  d) the OWNER starts runs:  sudo bash /root/prod/run_dip_prod.sh --region $REGION --run 1 ... --near /root/sniper-dip/near_leaders_$REGION.txt
EOT
