# Changelog

## v1.1.2 — 2026-05-02

### Live UI
- Auto-pause live updates when the tab is hidden (`visibilitychange`). Countdown ring shows ⏸ in muted gray; on tab refocus, fetches immediately and resumes the 120s ticker. Saves DG quota when no one's watching.

## v1.1.1 — 2026-05-02

### Live UI
- Tournament/Pool/TKE table rows flash gold for 5s when rank, score, or today's score changes between refreshes (`row-flash` keyframe + per-tab `prevSnapshot`).
- Mid-round `today` score falls back to `current_score − sum(prior rounds)` when DG returns null for the active round.

### Branding & PWA
- Terminal scoreboards now print "🦫 CHIP LEADER 🏆" headers (matching the web title).
- Web view declares favicon, apple-touch-icon, and PWA meta tags so iOS "Add to Home Screen" gets the beaver/trophy icon and a black status bar.
- Footer reads "🦫 Chip Leader 🏆 · Feit Club One-and-Done".

### Docs
- `CLAUDE.md` H1 rebranded to match.

## v1.1.0 — 2026-05-02

### Branding
- Rebranded from "FEIT CLUB GOLF POOL" to **🦫 Chip Leader 🏆** (beaver = Chip, trophy = Leader).
- "Chip Leaderboard" on desktop, "Chip Leader" on phones; tournament + round shown as a subtle context tail.
- Tabs got emoji + short mobile labels: 🏆 Pool / ⛳ Board / 🐉 TKEs / 📝 Story.
- Header meta line gains 👥 / 🛰 / 📊 / 🕒 markers.

### Live UI
- Countdown ring is bigger on mobile (50→56px), adds a red glow + label pulse in the final 10 seconds.
- During refresh: ⛳ ring label, animated blue shimmer bar across the top of the page, ring spinner.

### Headless deployment
- Server now binds `0.0.0.0` (was `127.0.0.1`) so phones on the LAN can reach it. Prints the `<host>.local` URL on startup.
- Skips auto-opening the browser when not a TTY or when `CHIP_NO_OPEN=1` (LaunchAgent sets this).
- LaunchAgent template at `deploy/launchd/com.feitclub.chipleader.plist` documented in BACKLOG Phase 1.

## v1.0.0 — 2026-05-01

Initial fork from `chip-input` v4.2.1.

### Forked
- `track_tournament.py` — terminal + web live tracker
- `chip` — CLI dispatcher (lb / web subcommands only)
- `standings/standings_latest.json` — latest season-to-date pool standings (read-only mirror; chip-input writes it on the laptop, iCloud syncs it to the Mac mini)

### Pruned out
- All Wednesday-picking pipeline code: `datagolf-week.zsh`, `enrich_board.py`, `competitor_model.py`, `predict_season.py`, `parse_picks.py`, `parse_standings.py`, `pick_history.py`, `track_odds.py`, `evaluate_predictions.py`, `masters_history.py`, `dg_pull_latest.py`, `players-pick.zsh`, `dg-latest.zsh`, `houston-board.zsh`, `valspar-board.zsh`.
- Generated state directories: `predictions/`, `archive_cache/`, `odds-history/`, `datagolf-latest/`, `Results/`, `Picks Reports/`, `reports/`, `standings/archive/`.
- Per-week PDF + CSV archives (`standings/standings-w*.pdf`, `standings/standings_w*.json`, `leaderboard/`).
- Burn list and pick history (`golf-picks-used.txt`, `picks_history.{json,csv}`) — re-introduced as iCloud symlinks at deploy time.

### Why this fork
- chip-leader is read-only at runtime; chip-input is read-write. Splitting them means the Mac mini gets a stable, pruned codebase with no DG fetch helpers, no CSV ingest, no PDF parsing — and the laptop pipeline doesn't pay any deployment overhead.
- Working tree dropped from ~22 MB to ~200 KB after prune.

See `chip-input/CHANGELOG.md` for the v4.x history that this fork inherits behaviorally.
