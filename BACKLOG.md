# chip-leader Backlog

Gameday-only fork of chip-input. Picking-pipeline backlog stays in chip-input.

## Gameday playbook — CJ Cup Byron Nelson (Thu 2026-05-21)

**Current state (end of night 2026-05-20):**
- Hostname-normalization fix committed (`325f80c`) and pushed.
- modelhost is live at `http://modelhost.local:8765` — `/` and `/data` both 200, FDA grants intact.
- Picks PDF for this week: **not yet dropped**. User will save it to `chip-input/picks/w{N}.pdf` Thursday AM; chip-input pipeline rewrites `picks_history.json` and iCloud syncs it to modelhost. No chip-leader restart needed — next 120s refresh picks it up.
- Cloudflare zone `ogrady.golf` added under "JDOGs account"; Namecheap nameservers swapped to the two `*.ns.cloudflare.com` values on 2026-05-20 ~midnight PT. Awaiting CF "zone Active" email (typical 30 min – 4 hr; worst case 48 hr).

### Order of operations for tomorrow ("tell me what to do")

1. **First tee fallback (always works):** open `http://modelhost.local:8765` on phone/laptop. Done. No DNS required.
2. **On modelhost — pull the hostname fix** (one time):
   ```zsh
   ssh tensor@modelhost.local
   cd ~/chip-leader && git pull
   launchctl kickstart -k gui/$(id -u)/com.feitclub.chipleader
   ```
3. **When CF zone goes Active** (check with `dig NS ogrady.golf +short` — should return the two `*.ns.cloudflare.com` values), set up the tunnel on modelhost per Phase 2 steps 3–7 below.
4. **After picks PDF lands:** confirm `picks_history.json` mtime updates, then `curl -s http://modelhost.local:8765/data | python3 -m json.tool | head -40` — `meta.tournament` should flip to the Byron Nelson and `pool_entries` should populate.

### Known smoke-test commands
```zsh
# LAN health
curl -sS -o /dev/null -w "%{http_code} %{time_total}s\n" http://modelhost.local:8765/
curl -sS http://modelhost.local:8765/data | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['meta']['tournament'], d['meta']['play']['status'])"

# DNS propagation
dig NS ogrady.golf +short
dig chip.ogrady.golf +short   # only resolves after `cloudflared tunnel route dns` runs
```

## Recently shipped (v1.4.0, 2026-05-14)

- **Always show my pick on Tournament tab** — appended outside top-25 if necessary; `.me` row visually pops (background + border + bold gold).
- **Braille activity spinners** — banner-load + Update button animate (⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏) while fetching.
- **Trend animations per player** — top-25 + TKE rows show braille up/down indicator vs. previous refresh; 30s fade.
- **Forked file reunited** — chip-input's `track_tournament.py` symlinked to this repo's. End of fork divergence.

## Active deploy on `modelhost` Mac Mini (user `tensor`, May 2026)

Phase 1 LAN deploy is **live**: LaunchAgent `com.feitclub.chipleader` serves `*:8765`, reachable at `http://modelhost.local:8765` and `http://192.168.0.172:8765`. Live working tree is `~/chip-leader` (cloned from iCloud); deploy template at `deploy/launchd/com.feitclub.chipleader.plist` still hardcodes `/Users/jason/...` — edit before installing on a new machine.

### Open issues on this deploy

- **Full Disk Access for launchd-spawned `/bin/zsh`, `/usr/bin/python3`, and `/bin/cat`**. Without it, `/data` returns `{"error": "[Errno 11] Resource deadlock avoided"}` (EDEADLK on iCloud-symlinked reads) or `subprocess.CalledProcessError: Command '['/bin/cat', '.../picks_history.json']' returned non-zero exit status 1` (the resilient reader shells out to `/bin/cat`). HTML serves fine — the error only hits the data endpoint. Fix: System Settings → Privacy & Security → Full Disk Access → add all three binaries; granting FDA to Terminal.app does not propagate. Then `launchctl kickstart -k gui/$(id -u)/com.feitclub.chipleader`.
- **Fallback if FDA doesn't pan out**: periodic copy step (cron or second LaunchAgent) that mirrors the two iCloud files into a non-iCloud cache directory; repoint chip-leader's symlinks at the cache.
- **GitHub push auth**: remote is `jasonogrady/chip-leader` but local `gh` is logged in as `chipcutstack` — `gh auth switch`/`login` before pushing v1.1.0 and beyond.

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

## Mac mini deployment (Phase 2 — chip.ogrady.golf) [P0]

Public URL: **`https://chip.ogrady.golf`**, fronted by Cloudflare Tunnel
so we don't need port forwarding, a static IP, or dynamic DNS. Namecheap
stays the registrar; Cloudflare takes over DNS for the zone.

### One-time setup (in this order)

1. **Cloudflare account.** Free plan. Add the site `ogrady.golf` →
   Cloudflare scans any existing DNS records (likely empty for a fresh
   Namecheap registration) and presents two assigned nameservers.
2. **Nameserver swap at Namecheap.** Domain List → `ogrady.golf` → Manage →
   Nameservers → **Custom DNS** → paste the two Cloudflare nameservers from
   the CF dashboard. Save. Propagation: usually < 1 hr, sometimes 24.
   Cloudflare flips the zone to **Active** automatically once it sees the
   change.
3. **Mac mini: install cloudflared.**
   ```zsh
   brew install cloudflared
   cloudflared tunnel login          # opens browser, picks the CF zone
   cloudflared tunnel create chipleader
   cloudflared tunnel route dns chipleader chip.ogrady.golf
   ```
   The `route dns` step writes the proxied CNAME on Cloudflare automatically
   (`chip → <tunnel-id>.cfargotunnel.com`, orange-cloud on).
4. **Tunnel config** at `~/.cloudflared/config.yml`:
   ```yaml
   tunnel: chipleader
   credentials-file: /Users/tensor/.cloudflared/<tunnel-id>.json
   ingress:
     - hostname: chip.ogrady.golf
       service: http://localhost:8765
     - service: http_status:404
   ```
5. **Run as a service.**
   ```zsh
   sudo cloudflared service install   # writes a launchd plist + starts it
   ```
6. **Auth gate (Cloudflare Access, free for ≤50 users).** Zero Trust →
   Access → Applications → Add → Self-hosted → `chip.ogrady.golf`. Policy:
   *Allow* if email matches `jason@ogrady.ai` (and any pool members you want).
   Identity provider: One-time PIN (email magic link) — zero account setup
   for guests; or Google SSO if you'd rather.
7. **Verify.**
   ```zsh
   curl -I https://chip.ogrady.golf/        # → 302 to CF Access login
   # complete email PIN once; bookmark on phone
   curl -I https://chip.ogrady.golf/data    # → 200 after auth
   ```

### Why Cloudflare Tunnel (not Tailscale Funnel + custom domain)

Tailscale Funnel only serves on `*.ts.net` — TLS SNI on a custom domain isn't
supported. We'd need Cloudflare or a port-forward + Let's Encrypt setup
anyway, and Cloudflare Tunnel is the cleanest path: no router config, no
public IP exposure, free TLS cert, free auth (CF Access).

### Why not stay on Namecheap DNS or move to Bluehost

Namecheap (or Bluehost shared hosting) can host an A record for
`chip.ogrady.golf → <home IP>`, but that requires (a) a static IP or
dynamic DNS daemon, (b) opening port 443 on the router to the Mac mini,
and (c) provisioning a Let's Encrypt cert via Caddy. Cloudflare Tunnel
sidesteps all three. Bluehost shared hosting also can't host the live
tracker itself — it needs a long-running Python daemon with macOS keychain
access and read access to iCloud-symlinked picks/standings, which only
makes sense on the Mac mini.

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

- ~~`today` fallback when DG returns null mid-round (compute as `current_score − Σ prior_round_totals`).~~ — done in v1.1.1 (`_today_with_fallback`).
- ETag / 304 on `/data` keyed on `meta.last_update`.
- ~~Row-change flash (5s yellow fade) when score/rank changes between polls.~~ — done in v1.1.1 (`flashIfChanged` + `row-flash` keyframe).
- Cut-watch badge for entries whose pick has make_cut < 0.7.
- Round selector — flip leaderboards across R1/R2/R3/R4.
- SSE push (server fetches DG, pushes diffs) instead of 120s client poll.
- Closest-rivals banner on Pool tab (already in narrative; surface on the table view).
- Sparkline of pool rank over rounds, per entry.
- Pick simulator — what would my projected rank be if I'd picked X?
- Slack/Discord webhook posting round-end summary.
- Keyboard shortcuts — 1/2/3/4 for tabs, r for refresh.
