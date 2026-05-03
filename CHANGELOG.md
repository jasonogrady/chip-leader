# Changelog

## v1.3.0 — 2026-05-03

### Fix — HTTP 500 on /data
- Long-running launchd-spawned process intermittently hit `OSError(EDEADLK)` on iCloud-symlinked `picks_history.json` / `standings_latest.json` and on concurrent SSL handshakes to DG, surfacing as HTTP 500.
- New `_retry_edeadlk` helper unwraps `URLError.reason` chains so EDEADLK is detected when nested inside `urllib` errors.
- File reads route through `_read_text_resilient`, which retries `read_text()` and falls back to shelling out to `/bin/cat` (bypasses the fd path that EDEADLKs in long-running daemons).
- `get_cached_data` now serves the last successful payload if `build_web_data` raises, so transient DG/iCloud blips never reach the client once the cache is warm.

### Auto-pause on tournament completion
- `compute_play_status` accepts a `tournament_complete` flag → status `concluded` / label `Concluded`.
- `build_web_data` derives it from live data: `current_round >= 4` and every player `thru == 18`. Catches the case where DG's `get-schedule` hasn't flipped to `completed` yet.
- Frontend `startTicker` treats `play.status === 'concluded'` like off-hours: paused ⏸ ring + 10-min poll cadence (was: kept polling at 2-min cadence).

## v1.2.1 — 2026-05-03

### Fix
- `/data` collapses concurrent requests through a 30s in-memory cache + lock. Eliminates intermittent HTTP 500 ("[Errno 11] Resource deadlock avoided") that happened when ThreadingHTTPServer ran two SSL handshakes against DG simultaneously, and cuts DG quota burn when several phones poll within the same window.

## v1.2.0 — 2026-05-02

### Play status & event-local time
- New `meta.play` block on `/data`: tournament location, course, event-local time, IANA tz, abbreviation (EDT/PDT/etc.), PT offset (e.g. `PT+3`), 7am–7pm play-window flag, last-update age in minutes, and a derived status emoji.
- Status indicator at the top of the page: 🟢 active (DG data fresh < 15 min), 🔴 play concluded / overnight, 🟡 unknown, ⚡ play suspended (in window but DG stale 15–240 min). Pulses on 🟢/⚡.
- Header status line shows: `<emoji> <Tournament> · R<n> · <City, State> · <H:MM TZ> (PT±N)`.
- Schedule data fetched from DG `get-schedule` once per hour; mapped via US-state → IANA tz table (no new deps).

### Auto-pause
- When event-local time is outside 7am–7pm, client polls every 10 min instead of 2 min and shows ⏸ on the countdown ring (FR1). Combines with the v1.1.2 tab-hidden pause.

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
