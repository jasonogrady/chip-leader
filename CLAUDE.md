# chip-leader — 🦫 Chip Leader 🏆 · Gameday Live Tracker

Headless gameday-only fork of [`chip-input`](https://github.com/jasonogrady/chip-input). Designed to run on the home Mac mini server during PGA tournaments and publish a live leaderboard to the LAN (Phase 1) and the open internet via Tailscale Funnel (Phase 2).

**My entry:** TIGER WOODS YALL!

---

## What this repo does

- **`chip lb`** — terminal 3-panel scoreboard (Tournament Top 20 · Pool Top 20 · Top TKEs).
- **`chip web`** — browser dark-theme dashboard at `localhost:8765` with sortable tables, 120s auto-refresh, mobile-responsive collapse.

Inputs (read-only; written by chip-input on the laptop and synced via iCloud):

- `standings/standings_latest.json` — season-to-date pool standings (winnings, score, FedEx, cuts_made, cuts_ratio, fedex).
- `picks_history.json` — historical picks across all entries.

Outputs:

- Live tour data fetched on-demand via the upstream live-stats and prediction endpoints (provider API key required at startup; stored under the `DATAGOLF_API_KEY` env var name for historical compatibility).

---

## What this repo *does not* do

The Wednesday picking pipeline lives in `chip-input`:

- Live-feed board enrichment, course fit, course history.
- Competitor model + predicted ownership.
- Pre-tournament odds tracking.
- Season projection.
- PDF parsing (standings, picks, results).
- Pick tier calibration.

When chip-input changes one of the cross-cutting JSON files, chip-leader picks it up on its next refresh.

---

## Run locally

```zsh
export DATAGOLF_API_KEY='your-key-here'
./chip web        # browser at http://localhost:8765
./chip lb         # terminal scoreboard
```

On the Mac mini, `DATAGOLF_API_KEY` should be in the macOS keychain rather than an env var:

```zsh
security add-generic-password -s chip-leader -a datagolf -w '<key>'
# read at startup:
export DATAGOLF_API_KEY="$(security find-generic-password -s chip-leader -a datagolf -w)"
```

---

## Data sync from chip-input

Both machines share iCloud Drive. The two cross-cutting data files are produced by chip-input on the laptop:

- `~/Library/Mobile Documents/com~apple~CloudDocs/GitHub/chip-input/standings/standings_latest.json`
- `~/Library/Mobile Documents/com~apple~CloudDocs/GitHub/chip-input/picks_history.json`

On the Mac mini, symlink them into chip-leader's working tree so reads are direct:

```zsh
cd ~/chip-leader
ln -sf "$ICLOUD/GitHub/chip-input/standings/standings_latest.json" standings/standings_latest.json
ln -sf "$ICLOUD/GitHub/chip-input/picks_history.json"             picks_history.json
```

Where `$ICLOUD` is `~/Library/Mobile Documents/com~apple~CloudDocs`.

---

## Mac mini deployment

See `BACKLOG.md` → "Mac mini deployment" for the LaunchAgent + Caddy + Tailscale Funnel walkthrough.

### Active deployment on this Mac mini (`modelhost`, user `tensor`)

- Live working tree: `~/chip-leader` (cloned from this iCloud copy). Edits land in iCloud first, then sync to `~/chip-leader` and `launchctl kickstart -k gui/$(id -u)/com.feitclub.chipleader`.
- LaunchAgent: `~/Library/LaunchAgents/com.feitclub.chipleader.plist`, sets `CHIP_NO_OPEN=1` so `webbrowser.open` is suppressed.
- LAN URL: `http://modelhost.local:8765` (also `http://192.168.0.172:8765`).
- Logs: `~/Library/Logs/chip-leader.log`.

### Full Disk Access (required for iCloud reads under launchd)

LaunchAgent-spawned `/bin/zsh`, `/usr/bin/python3`, and `/bin/cat` cannot traverse `~/Library/Mobile Documents` without Full Disk Access. Symptoms when missing:

- `getcwd: cannot access parent directories: Operation not permitted` (if WorkingDirectory is in iCloud).
- `{"error": "[Errno 11] Resource deadlock avoided"}` from `/data` (EDEADLK on iCloud-symlinked reads).
- `subprocess.CalledProcessError: Command '['/bin/cat', '.../picks_history.json']' returned non-zero exit status 1` — the resilient reader in `track_tournament.py` shells out to `/bin/cat` to dodge Python's iCloud EDEADLK, so `/bin/cat` needs its own FDA grant.

Fix: System Settings → Privacy & Security → Full Disk Access → add **`/bin/zsh`**, **`/usr/bin/python3`**, and **`/bin/cat`** (Cmd+Shift+G to type the paths). Granting FDA to Terminal.app alone does NOT propagate to launchd-spawned children. After granting, kickstart the agent.

### Pushing to GitHub

Remote is `https://github.com/jasonogrady/chip-leader.git`. `gh` on this Mac mini may be logged in as `chipcutstack`; if so, `git push` returns 403. Run `gh auth switch` (or `gh auth login` to add jasonogrady) before pushing.

---

## File inventory

| Path | Purpose |
|---|---|
| `track_tournament.py` | Live pool tracker — terminal + web server (`--serve PORT`); sortable tables, 120s countdown |
| `chip` | CLI dispatcher (`chip lb`, `chip web`) |
| `standings/standings_latest.json` | Season-to-date pool standings (synced from chip-input via iCloud) |
| `picks_history.json` | Historical picks (synced from chip-input via iCloud) |
| `deploy/launchd/` | LaunchAgent plist for headless run on Mac mini |
| `deploy/caddy/` | Caddyfile for reverse-proxy + TLS |

---

## Web view features

- **Pool Standings tab** — projected rank, current rank, current $, projected $, Δ$, Cuts ratio, projected position delta.
- **Tournament Board tab** — live top 25 with win%, top10%, make-cut%; my pick always shown (prepended if outside the window).
- **Top TKEs tab** — scored leaderboard for the TKE friend group with 🐉 markers.
- **Narrative tab** — generated commentary on tournament + pool + TKE.

TKE entries on the mixed Pool Standings tab are highlighted in red with a 🐉 emoji suffix; on the Top TKEs tab they render in default white so the gold "TIGER WOODS YALL!" row stands out.

---

## Versioning

This repo starts at **v1.0**, forked from chip-input v4.2.1. The two version timelines diverge from here.
