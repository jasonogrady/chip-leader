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

## Mac mini deployment (Phase 2 — anywhere)

1. **Tailscale Funnel.**
   ```zsh
   brew install tailscale
   sudo tailscale up
   sudo tailscale funnel 8765
   ```
   Public TLS URL: `chip.<tailnet>.ts.net`.
2. **Basic auth at Caddy** so the pool roster isn't world-readable:
   ```caddyfile
   chip.<tailnet>.ts.net {
     basicauth { jason <bcrypt-hash> }
     reverse_proxy localhost:8765
   }
   ```

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
