# Changelog

## v2.3.0 — 2026-06-11

### Feat — story narrative: intermission & round-concluded commissioner recap

A second narrative voice that only fires when play is paused — the between-events "final reckoning" and the overnight "round in the books" recaps. Where the live narrative is terse and factual, this is a structured card: up to four mini-charts with green ▲ / red ▼ arrows, followed by a commissioner recap that lauds the winners and barbecues the losers (with a rougher TKE-only section).

- `build_story_narrative` + `_story_recap`: chart and recap builders. Deterministic snark phrasing (stable across the 2-min refresh so the card doesn't reshuffle), plus dollar-gap "what's needed to climb a spot" math off the standings.
- Charts: pool movers, week's cash (or today's cards in round mode), TKE movers, and pick heroes/zeros — capped at four, deduped by golfer.
- `detect_narrative_mode`: fires on `intermission`/`concluded`, or an overnight `round_concluded` pause when >70% of the field is through 18. Returns `None` during live play, so the live `narrative_lines` keep driving the card then.
- `build_web_data` emits the `narrative` payload; client `renderNarrativeCard` renders it and falls back to `narrative_lines` when absent.
- `?preview=intermission|round` debug hook on `/data` rebuilds fresh with a forced mode (`no-store`, never cached) so the card can be previewed mid-tournament without waiting for a real pause.

A companion end-of-season `season_intermission` mode is scoped in `BACKLOG.md` (planned, not built).

## v2.2.2 — 2026-06-10

### Fix — intermission never fired because the two upstream feeds name events differently

The public board stayed stuck on the just-finished event ("The Memorial Tournament" R4, `play.status: off-hours`) instead of flipping to the intermission dark-state card, even though the event was over and the next event was on the schedule. This is the origin-side root cause behind the same symptom v2.2.1 partially addressed at the edge.

- Root cause: the in-play feed names events with the sponsor suffix (`the Memorial Tournament presented by Workday`); the `get-schedule` feed omits it (`the Memorial Tournament`). `compute_play_status` reached the schedule via `fetch_schedule().get(tournament)` — an exact-string lookup using the suffixed in-play name — which returned `None`, so the schedule's authoritative `status="completed"` never arrived and `concluded` stayed `False`. The `tournament_complete` fallback (`all(thru==18)`) can't cover the gap either: any event with a 36-hole cut leaves missed-cut players at `thru=0`, so it's never `True` for a cut event.
- Fix: new `schedule_row_for()` resolves the schedule row by exact name first, then falls back to matching on `clean_event_name()` (which already normalizes both spellings to `The Memorial Tournament`). The `after_name` exclusion in `next_scheduled_event()` is normalized the same way.
- Regression test: `tests/test_intermission_name_match.py` (first test infra in the repo) — fails against the old exact-`.get()` behavior, passes with the fix.

## v2.2.1 — 2026-06-10

### Fix — `no-store` on dynamic routes so the public URL can't serve a stale board

The public `chip.ogrady.golf` URL showed a stale live-tournament board during the intermission window while LAN (`modelhost.local:8765`) correctly showed the dark state. Root cause: the page is a static shell that client-side-polls `/data` for dark-vs-live state, and `/data` shipped `Cache-Control: no-cache` (store-but-revalidate). A Cloudflare edge cache pinned the last live `/data` snapshot and served it publicly; LAN bypasses Cloudflare, so only the public URL was affected.

- `/`, `/data` (200 + 304), and `/quota` now send `Cache-Control: no-store` so no edge/browser ever stores live state. Static assets (`/icon.svg`, `/assets/*`) keep `public, max-age=86400`.
- Operational follow-up (not code): purge the Cloudflare cache once to drop the already-pinned snapshot, and ensure any "Cache Everything" rule excludes `/data` (or sets Edge TTL to "respect existing headers").

## v2.2.0 — 2026-06-04

### Feat — intermission dark-state view + deploy runbook

Bundles the unreleased work since v2.1.0: a between-events dark state for the web view, and an in-repo redeploy runbook.

- **Intermission dark-state view** (`web: add intermission dark-state view between events`): a new `compute_play_status` `intermission` state, driven by `next_scheduled_event()` off the DataGolf schedule, renders a "has concluded / begins Thursday" card with a live tee-off countdown and braille spinners when the current event is over and the next scheduled event hasn't started. The standings table stays below; the refresh ring pauses; the server polls every 30 min so the board auto-flips to the live view at tee-off.
- **Intermission fires on tee-off day too** (`intermission: fire on tee-off day too`): the in-play feed keeps returning the just-finished event until the new one produces scores, so on Thursday morning the board showed a stale "prior event R4". The dark card now triggers when the next event starts today or later (was strictly future), with "begins today" wording.
- **Deploy/redeploy runbook** (`docs: add deploy/redeploy runbook`): CLAUDE.md now documents the "pull and restart the leaderboard" trigger phrase, the `com.feitclub.chipleader` KeepAlive label, the `~/Library/Logs/chip-leader.log` crash-first debugging note, the Keychain key-load failure mode, and the public-vs-LAN URL distinction.

## v2.1.0 — 2026-05-29

### Feat — background fetcher + upstream quota counter

Replaces the per-request upstream fetching model that caused the DataGolf 429 incident on 2026-05-28. Root cause: an iCloud Full Disk Access regression on `/bin/cat` (launchd-spawned children) made `_read_text_resilient` raise on every `picks_history.json` read, so `build_web_data` aborted before populating the 30s cache. Every `/data` poll then re-fired the 3–6 upstream calls; cloudflared exposed this publicly so a handful of clients per minute blew through the 45 req/min ceiling.

- **Background fetcher** (`_fetcher_loop`, daemon thread `upstream-fetcher`): a single loop now owns all upstream calls. Refresh cadence is keyed off `play.status` and day-of-week:
  - Active / lightning (play live): 60s
  - Off-hours (overnight pause): 30 min
  - Concluded: 1 hr
  - Mon–Wed (no PGA round that week): 6 hr — honors the "don't hit the API outside Thu–Sun" preference
  - Cold start (no payload yet): 30s
- `/data` is now a passive reader. Client request rate is fully decoupled from upstream rate — the cloudflared multiplier × cold-rebuild path that caused the incident no longer exists. Returns 503 with `Retry-After` only during the very first warm-up window.
- Initial synchronous fetch on startup warms the cache before binding the port, so the first client request gets data instead of the polite 503.
- Replaces the request-driven `DATA_TTL` / cold-fail-backoff branch in `get_cached_data`; the fetcher loop now owns failure semantics. The `_ServiceUnavailable` exception is retained for the cold-start window.

- **Upstream quota counter** (module-level `_QUOTA` / `_quota_record`): instruments `_urlopen_json` to count every outbound DataGolf request grouped by endpoint path. Daily rollover automatically logs `[quota] YYYY-MM-DD: preds/in-play=X live-tournament-stats=Y get-schedule=Z total=N` and resets at midnight local time.
- **`GET /quota`**: live snapshot endpoint returning per-endpoint counts plus `payload_age_s` (how fresh the cached payload is) and `next_refresh_s` (when the fetcher will tick next).

- Added `threading` to module-level imports (was previously imported only inside `serve_web`).
- Startup banner now also prints the fetcher cadence; both lines `flush=True` to handle launchd's fully-buffered stdout.

## v2.0.0 — 2026-05-25

### Chore: week 14 close-out (CJ Cup Byron Nelson)
- Tournament concluded 2026-05-24. My pick (Jordan Spieth) finished T19, +$100,597. Season YTD post-week-14: rank 24 of 148, $8,720,429 winnings, 9/10 cuts, 2,180 FedEx points.
- Standings refreshed on modelhost via iCloud sync of `standings_latest.json` (week 14, source=ytd_pdf, 148 entries, 3 baseline reconciliation issues, unchanged from prior weeks).
- Companion fix in chip-input (`jasonogrady/chip-input@2607cf1`): `parse_standings.py` now detects tournament name from PDF header structure (walks back from the `Rank/Entry/Player` column-header row) instead of substring-matching against `TOURNAMENT_DATES`. Future tournament weeks parse correctly even without their date entry. Added w14 (CJ Cup Byron Nelson, 2026-05-24) and w15 (Charles Schwab Challenge, 2026-05-31) to the date map while in there.
- `BACKLOG.md`: archived the CJ Cup gameday playbook to "Past gameday playbook" with the outcome summary; kept the pre-tournament checklist below as a template for next week.

## v1.9.0 — 2026-05-23

### Chore — ignore ad-hoc `screenshots/`
- Added `screenshots/` to `.gitignore`. Local QA/marketing captures (e.g. `friends.png`, `narrative.png`, `pool.png`, `tournament.png`) no longer show up as untracked on every `git status`.

## v1.8.0 — 2026-05-23

### Fix — "Sent!" modal renders unstyled
- The native `<dialog>` is a sibling of `<main class="scene">`, so when promoted to the top-layer by `showModal()` it could not resolve `var(--paper)`, `var(--ink)`, etc. — the tokens were defined on `.scene` and didn't cascade. Result: transparent background, missing border, missing red offset shadow — the "Sent!" text floated on top of the page.
- Fix: moved the seven design tokens (`--paper`, `--paper-deep`, `--ink`, `--ink-soft`, `--accent`, `--moss`, `--rule`) from `.scene` to `:root`. `.scene`'s own declarations (font, grid, isolation) are untouched. Verified post-fix: cream paper background, 2px ink border, 8×8 red offset shadow, `::backdrop` scrim with `blur(2px)` all render per the design handoff.

## v1.7.0 — 2026-05-23

### Custom 404 page (brutalist VHS / "Chip's closed" gag)
- New cream-paper / Bowlby-One 404 page leaning into the *National Lampoon's Vacation* "Sorry folks, park's closed" bit: meme-captioned security-guard photo on the left (with REC indicator, scanlines, vignette), giant 404 with a red jiggling middle "0" on the right, blurb, and a single "⏰ Wake up the admin" CTA. Replaces the previous empty 404 body.
- Routes: `GET /404` returns 200 + page (testable preview); any unknown path returns 404 + page. The existing `/`, `/data`, and icon routes are untouched.
- Static-file branch: `GET /assets/<path>` serves files from `./assets/` with proper Content-Type and `Cache-Control: public, max-age=86400`. Path-traversal-guarded: resolved target must stay inside `ROOT/assets`. Encoded `..%2F` and `%2e%2e` confirmed blocked.
- Self-hosted Google Fonts (Bowlby One 400, DM Mono 400/500, Instrument Serif 400 italic) under `assets/fonts/`, latin subset only (~55 KB total). No runtime third-party requests from this page.
- "Sent!" modal uses the browser-native `<dialog>` + `.showModal()`, which provides focus trap, Escape-to-close, and focus return to the trigger for free. Scrim click handled by `event.target === dlg`; backdrop styled via `dialog::backdrop`.
- `notifyAdmin()` stubbed with a TODO. Modal fires unconditionally on click; wire to a real notification channel later (Slack, PagerDuty, email).
- Looping animations (REC blink, "0" jiggle, alarm wiggle) gated behind `@media (prefers-reduced-motion: reduce)`. One-shot pop-ins kept enabled.
- Design handoff and prototype kept untouched at `design_handoff_404_page/` as reference.

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
