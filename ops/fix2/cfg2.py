p = "/root/fix2/final2_landing.toml"; s = open(p).read()
old = 'url     = "https://fra.be.harmonic.gg/api/v1/bundles"\nmax_per_sec = 1\n'
assert old in s
new = ('url     = "https://fra.be.harmonic.gg/api/v1/bundles"\n'
       '# authenticated SearcherService.SendBundle (Jito-style login, role 3) with the owner\'s DEDICATED Harmonic keypair\n'
       '# (pubkey 8C1hako7zHpu1hiwLvrH6TMccY1G61puvjpGVhAk32hv, whitelisting applied for 2026-10-19). Login failure (not yet\n'
       '# whitelisted) is logged at start ("HARMONIC AUTH FAILED") and the path falls back to the public JSON-RPC above.\n'
       'auth_keypair = "/root/.harmonic-searcher-auth.json"\n'
       'max_per_sec = 1\n')
s = s.replace(old, new)
s = s.replace("# Routes (live_final2.sh): harmonic leaders (HarmonicAgave + HarmonicFiredancer) get harmonic-bundle first; BAM and\n",
              "# Routes (live_final2.sh): harmonic-bundle is built here but OFF in the live route until Harmonic confirms the whitelist\n# (ROUTES_HB in live_final2.sh puts it first on harmonic leaders: HarmonicAgave + HarmonicFiredancer); BAM and\n")
open(p, "w").write(s)
p = "/root/lat/live_final2.sh"; s = open(p).read()
old = [l for l in s.splitlines() if l.startswith("ROUTES=")][0]
hb = old.replace("ROUTES=", "ROUTES_HB=")
off = old.replace("harmonic=harmonic-bundle+jito-bundle+nozomi+staked-rpc", "harmonic=jito-bundle+nozomi+staked-rpc")
assert off != old
s = s.replace(old, "# harmonic-bundle stays OUT of the route until Harmonic confirms the whitelist of 8C1hako7...; then use ROUTES_HB:\n" + hb + "\n" + off)
s = s.replace("#    harmonic-bundle first. NOTE:", "#    harmonic-bundle first ONLY once whitelisted (ROUTES_HB; default ROUTES leaves it out). NOTE:")
open(p, "w").write(s)
