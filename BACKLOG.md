# chip-leader Backlog

Gameday-only fork of chip-input. Picking-pipeline backlog stays in chip-input.

## Mac mini deployment (Phase 1 — LAN)

1. **Prereqs.** `brew install python@3 caddy` (and `poppler` only if PDF parsing is ever added back; not needed for the gameday-only path).
2. **Clone.** `git clone https://github.com/jasonogrady/chip-leader.git ~/chip-leader`.
3. **DataGolf key in keychain.**
   ```zsh
   security add-generic-password -s chip-leader -a datagolf -w '<key>'
   ```
4. **iCloud symlinks** for the two cross-cutting data files (see CLAUDE.md → Data sync).
5. **LaunchAgent.** Drop `deploy/launchd/com.feitclub.chipleader.plist` into `~/Library/LaunchAgents/` and `launchctl load` it. KeepAlive=true, RunAtLoad=true. Logs to `~/Library/Logs/chip-leader.log`.
6. **Bind 0.0.0.0** in the Python server. Verify access from another device on the LAN at `http://macmini.local:8765` (Bonjour gives `.local` for free).
7. **Caddy reverse-proxy** for TLS + clean URL: `chip.local { reverse_proxy localhost:8765 }`. Optional on Phase 1; the bare port is fine.
8. **Warm-cache cron** (optional) so the page is fresh when first opened on phone Sunday afternoon.

## Mac mini deployment (Phase 2 — chip.ogrady.football) [P0]

Public URL: **`https://chip.ogrady.football`**, fronted by Cloudflare Tunnel
so we don't need port forwarding, a static IP, or dynamic DNS. Bluehost stays
the registrar; Cloudflare takes over DNS for the zone.

### One-time setup (in this order)

1. **Cloudflare account.** Free plan. Add the site `ogrady.football` →
   Cloudflare scans existing Bluehost DNS records and imports them. Verify the
   imports look right (especially MX for any Bluehost mailboxes).
2. **Nameserver swap at Bluehost.** Domain Manager → `ogrady.football` →
   Nameservers → switch from Bluehost's defaults to the two Cloudflare
   nameservers shown on the CF dashboard. Propagation: usually < 1 hr,
   sometimes 24. Existing Bluehost web hosting keeps working as long as the
   imported A/CNAME records are correct on Cloudflare.
3. **Mac mini: install cloudflared.**
   ```zsh
   brew install cloudflared
   cloudflared tunnel login          # opens browser, picks the CF zone
   cloudflared tunnel create chipleader
   cloudflared tunnel route dns chipleader chip.ogrady.football
   ```
   The `route dns` step writes the proxied CNAME on Cloudflare automatically
   (`chip → <tunnel-id>.cfargotunnel.com`, orange-cloud on).
4. **Tunnel config** at `~/.cloudflared/config.yml`:
   ```yaml
   tunnel: chipleader
   credentials-file: /Users/tensor/.cloudflared/<tunnel-id>.json
   ingress:
     - hostname: chip.ogrady.football
       service: http://localhost:8765
     - service: http_status:404
   ```
5. **Run as a service.**
   ```zsh
   sudo cloudflared service install   # writes a launchd plist + starts it
   ```
6. **Auth gate (Cloudflare Access, free for ≤50 users).** Zero Trust →
   Access → Applications → Add → Self-hosted → `chip.ogrady.football`. Policy:
   *Allow* if email matches `jason@ogrady.ai` (and any pool members you want).
   Identity provider: One-time PIN (email magic link) — zero account setup
   for guests; or Google SSO if you'd rather.
7. **Verify.**
   ```zsh
   curl -I https://chip.ogrady.football/        # → 302 to CF Access login
   # complete email PIN once; bookmark on phone
   curl -I https://chip.ogrady.football/data    # → 200 after auth
   ```

### Why Cloudflare Tunnel (not Tailscale Funnel + custom domain)

Tailscale Funnel only serves on `*.ts.net` — TLS SNI on a custom domain isn't
supported. We'd need Cloudflare or a port-forward + Let's Encrypt setup
anyway, and Cloudflare Tunnel is the cleanest path: no router config, no
public IP exposure, free TLS cert, free auth (CF Access).

### Why not stay on Bluehost DNS only

Bluehost can host an A record for `chip.ogrady.football → <home IP>`, but
that requires (a) a static IP or dynamic DNS daemon, (b) opening port 443 on
the router to the Mac mini, and (c) provisioning a Let's Encrypt cert via
Caddy. Cloudflare Tunnel sidesteps all three.

### Local-only fallback (Phase 1, still works)

LAN access at `http://macmini.local:8765` from any device on home wifi —
keep this as the always-available fallback. No auth, no TLS, but it's behind
the router NAT.

### Operational notes

- **DG quota under public access.** Auto-pause (overnight + tab-hidden +
  off-hours 10-min poll) keeps requests low. Add a server-side `/data` cache
  (30s TTL keyed on `meta.last_update`) if Sunday traffic ever spikes.
- **Mac mini sleep.** `sudo pmset -a sleep 0 disksleep 0 displaysleep 30`
  so the box stays reachable.
- **iCloud symlink lag.** On tournament Sunday, run
  `brctl download standings/standings_latest.json picks_history.json` if the
  laptop's recent edits haven't propagated.
- **Logs.** `cloudflared` → `~/Library/Logs/com.cloudflare.cloudflared.out.log`.
  `chip-leader` → `~/Library/Logs/chip-leader.log` (per LaunchAgent plist).

## Mac mini deployment (Phase 3 — PWA)

- `manifest.json` + service worker so iPhone "Add to Home Screen" yields a real app icon.
- Web Push for round-end notifications (subscribe on first install; trigger from server when round flips).

## Outstanding leaderboard polish (carried over from chip-input)

- `today` fallback when DG returns null mid-round (compute as `current_score − Σ prior_round_totals`).
- ETag / 304 on `/data` keyed on `meta.last_update`.
- Row-change flash (5s yellow fade) when score/rank changes between polls.
- Cut-watch badge for entries whose pick has make_cut < 0.7.
- Round selector — flip leaderboards across R1/R2/R3/R4.
- SSE push (server fetches DG, pushes diffs) instead of 120s client poll.
- Closest-rivals banner on Pool tab (already in narrative; surface on the table view).
- Sparkline of pool rank over rounds, per entry.
- Pick simulator — what would my projected rank be if I'd picked X?
- Slack/Discord webhook posting round-end summary.
- Keyboard shortcuts — 1/2/3/4 for tabs, r for refresh.
