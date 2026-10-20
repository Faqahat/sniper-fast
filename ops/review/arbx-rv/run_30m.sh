#!/bin/bash
cd /root/sniper-fast
rm -f enrich.done reputation_enriched.json
./target/debug/snipe_shadow --config /root/sniper-fast/snipe_feeds.toml --minutes 30 --out /root/sniper-fast/shadow_30m.jsonl >/root/sniper-fast/shadow_30m.log 2>&1
sleep 180
python3 -Iu /tmp/enrich_rep.py >/root/sniper-fast/enrich.log 2>&1
echo done > /root/sniper-fast/enrich.done
