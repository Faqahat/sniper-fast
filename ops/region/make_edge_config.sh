#!/bin/bash
# Multi-region kit (owner 10-24 16:00 PKT: "prepare the bot for multi region setup", Amsterdam edge server).
# Runs ON THE FRANKFURT SERVER as root: builds the edge config from the Frankfurt base config by swapping every regional
# endpoint host for its Amsterdam twin (all checked by DNS 10-24: constant-k rpc / staked-rpc / kaldera / turbo-kaldera
# amsterdam, jito block engine amsterdam, helius ams-sender, nozomi ams1, astralane ams, harmonic ams, bolt ams, landx ams1).
# Secrets stay in the file (never printed); only the remaining non-Amsterdam hosts are listed at the end (no paths / keys).
# The Amsterdam Constant-K key differs from Frankfurt's (owner 10-24): pass it on STDIN (never as an argument) and it replaces
# the api-key of every constant-k URL (rpc_url, staked-rpc, tpu-direct); the Kaldera feeds read KALDERA_TOKEN / CONSTANTK_TOKEN
# from the edge's own .env (deploy_edge.sh sets those). LandX: ams2.landx.dev (Cherry Servers, like our fra3) unless LANDX_HOST.
# usage: printf %s "$AMS_KEY" | sudo bash make_edge_config.sh [region=ams] [base=/root/sniper-dip/dip_probe.toml]
set -eu
REGION=${1:-ams}; BASE=${2:-/root/sniper-dip/dip_probe.toml}; OUT=/root/sniper-dip/dip_edge_${REGION}.toml
[ "$REGION" = ams ] || { echo "only ams is mapped so far"; exit 1; }
[ -f "$BASE" ] || { echo "missing $BASE"; exit 1; }
sed -e 's#staked-rpc-frankfurt\.constant-k\.com#staked-rpc-amsterdam.constant-k.com#g' \
    -e 's#turbo-kaldera-frankfurt\.constant-k\.com#turbo-kaldera-amsterdam.constant-k.com#g' \
    -e 's#kaldera-frankfurt\.constant-k\.com#kaldera-amsterdam.constant-k.com#g' \
    -e 's#rpc-frankfurt\.constant-k\.com#rpc-amsterdam.constant-k.com#g' \
    -e 's#frankfurt\.mainnet\.block-engine\.jito\.wtf#amsterdam.mainnet.block-engine.jito.wtf#g' \
    -e 's#fra-sender\.helius-rpc\.com#ams-sender.helius-rpc.com#g' \
    -e 's#fra2\.nozomi\.temporal\.xyz#ams1.nozomi.temporal.xyz#g' \
    -e 's#fr\.gateway\.astralane\.io#ams.gateway.astralane.io#g' \
    -e 's#fra\.be\.harmonic\.gg#ams.be.harmonic.gg#g' \
    -e 's#fra\.bolt\.raiden\.wtf#ams.bolt.raiden.wtf#g' \
    -e "s#fra3\.landx\.dev#${LANDX_HOST:-ams2.landx.dev}#g" \
    "$BASE" > "$OUT.new"
chmod 600 "$OUT.new"
KEY=$(cat); [ -n "$KEY" ] || { echo "no Amsterdam constant-k key on stdin"; rm -f "$OUT.new"; exit 1; }
KEY="$KEY" python3 - "$OUT.new" <<'PY'
import os, re, sys
p = sys.argv[1]; key = os.environ["KEY"]; s = open(p).read()
s2, n = re.subn(r'(https://[a-z-]*amsterdam\.constant-k\.com[^"?]*\?(?:[^"]*&)?api-key=)[^"&]+', lambda m: m.group(1) + key, s)
open(p, "w").write(s2); print(f"constant-k URLs given the Amsterdam key: {n}")
PY
mv "$OUT.new" "$OUT"
echo "wrote $OUT ($(grep -c . "$OUT") lines). Hosts in it (no paths / keys):"
grep -oE '(https?|udp|grpcs?)://[^/:" ]+' "$OUT" | sort | uniq -c | sed 's/^/   /'
echo "still pointing at Frankfurt (expected: none, or feeds you keep on purpose):"
grep -oE '(https?|udp|grpcs?)://[^/:" ]*(frankfurt|fra[0-9-]*\.|fra-|\.fr\.)[^/:" ]*' "$OUT" | sort -u | sed 's/^/   /' || true
