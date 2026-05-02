# Changelog

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
