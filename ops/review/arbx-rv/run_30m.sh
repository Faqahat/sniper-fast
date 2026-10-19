#!/bin/bash
cd /root/arbx-fast
rm -f enrich.done reputation_enriched.json
./target/debug/snipe_shadow --config /root/arbx-fast/snipe_feeds.toml --minutes 30 --out /root/arbx-fast/shadow_30m.jsonl >/root/arbx-fast/shadow_30m.log 2>&1
sleep 180
python3 -Iu /tmp/enrich_rep.py >/root/arbx-fast/enrich.log 2>&1
echo done > /root/arbx-fast/enrich.done
