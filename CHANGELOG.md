# Changelog

## v1.6.0 — 2026-05-23

### Data-provider scrub
- Removed user-visible and in-source mentions of the upstream live-feed provider across HTML (banner, footer, meta line), terminal output ("DG updated:" → "live updated:"), docstrings, comments, and internal identifiers (`DG_NAME_MAP` → `LIVE_EVENT_NAME_MAP`, `dg_tournament` arg → `live_tournament`, User-Agent header). Env var name (`DATAGOLF_API_KEY`), keychain account (`-a datagolf`), and the actual API hostname stay — they're operational truth, not user-visible.

### My pick always visible on Tournament Board (incl. mobile)
- When my pick is outside the live top-25, the row now prepends to `tournament_top` instead of appending. Previously the `.me` row was the 26th row in the table — visible on desktop but below the fold on mobile. Now it's row 1 when outside the window, in natural position when inside.

### Narrative — round-aware tone for my pick
- "Sunday-charge mode" and friends now only fire on Sunday (R4 in progress). Earlier rounds get round-appropriate framing:
  - **R1 (Thursday)**: "fired a low one" / "off to a hot start" / "off to a solid start" / etc.
  - **R2 (Friday)**: cut-line focused — "well clear of the cut line" / "in cut-line danger" / etc.
  - **R3 (Saturday)**: moving-day focused — "dominating moving day" / "making a big move" / "fading on Saturday" / etc.
  - **R4 in progress (Sunday)**: original Sunday-charge language preserved.
  - **R4 finished**: existing final-tone branch preserved.
- "Cut survival: X%" line suppressed in R3/R4 (cut decision is in by then).

## v1.5.0 — 2026-05-23

### Fix — chip.ogrady.golf works post-Access auth
- Root cause: the original Cloudflare Access "Chip Leader" application held a stale binding (likely the deleted `chip-ogrady-golf` Worker as its service URL), so post-auth requests dead-ended at Cloudflare's edge and never reached the tunnel daemon. The tunnel itself was healthy the entire time — `/Library/Logs/com.cloudflare.cloudflared.err.log` showed zero failed-proxy entries because zero requests arrived.
- Fix: delete the broken Access app and recreate it per `deploy/cloudflared/SETUP.md` §6 (Self-hosted, domain `chip.ogrady.golf`, One-time PIN, allow-list policy). New app's JWT `kid` flipped from `1d49dc19…` to `47258c7a…`, confirming clean rebind. End-to-end verified: `curl https://chip.ogrady.golf/` → 200 chip-leader HTML when Access was momentarily disabled; with the new Access app in place, browser email-PIN auth lands on the leaderboard.

### Deploy template + docs polish
- `deploy/launchd/com.feitclub.chipleader.plist` no longer hardcodes `/Users/jason/...`; uses a `__USERNAME__` placeholder with a one-line `sed` snippet in the header comment.
- BACKLOG: dropped the stale "cloudflared log path" doc-bug entry (SETUP.md already shows the correct `/Library/Logs/...` system path).

## v1.4.0 — 2026-05-14

### Tournament tab — always show my pick
- `tournament_top` now always includes the user's pick row, even when the player is outside the top-25 by score. Refactored to `_tournament_row()` helper and appends my-pick row if absent.
- `.me` row styling upgraded: gold text + 700 weight (existing) **+** dark-gold row background (`#1f1809`) + 3px gold inset border on the first cell. Stands out from the regular gold-Win% cells which previously made the `.me` row easy to miss in a busy table.

### Braille activity & trend animations
- New `.braille-spin` class drives a 10-frame Unicode braille spinner (⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏, 120ms cadence) via a single global `setInterval` that mutates every `.braille-spin` element's `textContent`.
- Banner-load indicator: replaced the blue pulsing dot with an inline braille spinner ("⠋ Fetching live data…").
- Update Now button shows "⠋ Updating" while a `/data` fetch is in-flight.
- Ring countdown indicator left as-is (⛳ + shimmer is more on-theme for golf than braille).
- **Per-player trend indicators** on the Tournament tab (top 25 + my-pick row) and TKE leaderboard. A small braille glyph prefixes each player name:
  - **Up** (score improved between refreshes — `cur < prev`): green ascending fill (⢀⢠⢰⢸)
  - **Down** (score worsened — `cur > prev`): red descending fill (⠈⠘⠸⢸)
  - **Flat** (no change or first render): faint `·`
  - 30s `trend-fade` keyframe drops opacity to 55% so changes are obvious right after a refresh but recede over time. `lastScoreTournament` and `lastScoreTKE` JS objects retain prior scores; reset on full page reload.

### Forked file reunited
- chip-input's `track_tournament.py` is now a **symlink** to this repo's copy (was a stale 2190-line fork; this repo is 2530+ lines). One file, no more drift. Going forward, edit only here.

## v1.3.0 — 2026-05-03

### Fix — HTTP 500 on /data
- Long-running launchd-spawned process intermittently hit `OSError(EDEADLK)` on iCloud-symlinked `picks_history.json` / `standings_latest.json` and on concurrent SSL handshakes to the upstream feed, surfacing as HTTP 500.
- New `_retry_edeadlk` helper unwraps `URLError.reason` chains so EDEADLK is detected when nested inside `urllib` errors.
- File reads route through `_read_text_resilient`, which retries `read_text()` and falls back to shelling out to `/bin/cat` (bypasses the fd path that EDEADLKs in long-running daemons).
- `get_cached_data` now serves the last successful payload if `build_web_data` raises, so transient upstream/iCloud blips never reach the client once the cache is warm.

### Auto-pause on tournament completion
- `compute_play_status` accepts a `tournament_complete` flag → status `concluded` / label `Concluded`.
- `build_web_data` derives it from live data: `current_round >= 4` and every player `thru == 18`. Catches the case where the upstream schedule endpoint hasn't flipped to `completed` yet.
- Frontend `startTicker` treats `play.status === 'concluded'` like off-hours: paused ⏸ ring + 10-min poll cadence (was: kept polling at 2-min cadence).

## v1.2.1 — 2026-05-03

### Fix
- `/data` collapses concurrent requests through a 30s in-memory cache + lock. Eliminates intermittent HTTP 500 ("[Errno 11] Resource deadlock avoided") that happened when ThreadingHTTPServer ran two SSL handshakes against the upstream feed simultaneously, and cuts provider quota burn when several phones poll within the same window.

## v1.2.0 — 2026-05-02

### Play status & event-local time
- New `meta.play` block on `/data`: tournament location, course, event-local time, IANA tz, abbreviation (EDT/PDT/etc.), PT offset (e.g. `PT+3`), 7am–7pm play-window flag, last-update age in minutes, and a derived status emoji.
- Status indicator at the top of the page: 🟢 active (live data fresh < 15 min), 🔴 play concluded / overnight, 🟡 unknown, ⚡ play suspended (in window but live data stale 15–240 min). Pulses on 🟢/⚡.
- Header status line shows: `<emoji> <Tournament> · R<n> · <City, State> · <H:MM TZ> (PT±N)`.
- Schedule data fetched from the upstream `get-schedule` endpoint once per hour; mapped via US-state → IANA tz table (no new deps).

### Auto-pause
- When event-local time is outside 7am–7pm, client polls every 10 min instead of 2 min and shows ⏸ on the countdown ring (FR1). Combines with the v1.1.2 tab-hidden pause.

## v1.1.2 — 2026-05-02

### Live UI
- Auto-pause live updates when the tab is hidden (`visibilitychange`). Countdown ring shows ⏸ in muted gray; on tab refocus, fetches immediately and resumes the 120s ticker. Saves provider quota when no one's watching.

## v1.1.1 — 2026-05-02

### Live UI
- Tournament/Pool/TKE table rows flash gold for 5s when rank, score, or today's score changes between refreshes (`row-flash` keyframe + per-tab `prevSnapshot`).
- Mid-round `today` score falls back to `current_score − sum(prior rounds)` when the live feed returns null for the active round.

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
- All Wednesday-picking pipeline code (live-feed fetchers, board enrichment, competitor model, season projection, picks/standings parsers, history tools, odds tracker, prediction evaluator, weekly board scripts) and generated state directories (predictions, archive caches, odds history, weekly feed snapshots, results, picks reports, standings archive).
- Per-week PDF + CSV archives (`standings/standings-w*.pdf`, `standings/standings_w*.json`, `leaderboard/`).
- Burn list and pick history (`golf-picks-used.txt`, `picks_history.{json,csv}`) — re-introduced as iCloud symlinks at deploy time.

### Why this fork
- chip-leader is read-only at runtime; chip-input is read-write. Splitting them means the Mac mini gets a stable, pruned codebase with no upstream-fetch helpers, no CSV ingest, no PDF parsing — and the laptop pipeline doesn't pay any deployment overhead.
- Working tree dropped from ~22 MB to ~200 KB after prune.

See `chip-input/CHANGELOG.md` for the v4.x history that this fork inherits behaviorally.
