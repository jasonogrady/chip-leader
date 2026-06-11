# chip-leader — 🦫 Chip Leader 🏆 · Gameday Live Tracker

Headless gameday-only fork of [`chip-input`](https://github.com/jasonogrady/chip-input). Designed to run on the home Mac mini server during PGA tournaments and publish a live leaderboard to the LAN (Phase 1) and the open internet via Tailscale Funnel (Phase 2).

**My entry:** TIGER WOODS YALL!

---

## What this repo does

- **`chip lb`** — terminal 3-panel scoreboard (Tournament Top 20 · Pool Top 20 · Top TKEs).
- **`chip web`** — browser dark-theme dashboard at `localhost:8765` with sortable tables, 120s auto-refresh, mobile-responsive collapse.

Inputs (read-only; written by chip-input, symlinked in from the local `chip-input` working tree):

- `standings/standings_latest.json` — season-to-date pool standings (winnings, score, FedEx, cuts_made, cuts_ratio, fedex).
- `picks_history.json` — historical picks across all entries.

Outputs:

- Live tour data fetched on-demand via the upstream live-stats and prediction endpoints (provider API key required at startup; stored under the `DATAGOLF_API_KEY` env var name for historical compatibility).

---

## Deploy / redeploy on modelhost

**Trigger phrase (type this into Claude on the mini, in this repo):**
> **"pull and restart the leaderboard"**

Steps — run locally on the mini (no SSH needed; Claude here has local access):

```zsh
cd ~/chip-leader                                              # the live working tree (NOT ~/dev/chip-leader)
git pull origin main                                          # origin = github.com/jasonogrady/chip-leader.git
launchctl kickstart -k gui/$(id -u)/com.feitclub.chipleader   # restart the service
sleep 2
lsof -nP -iTCP:8765 -sTCP:LISTEN                               # confirm something is listening
tail -n 40 ~/Library/Logs/chip-leader.log                     # if NOT listening, the crash is here
```

- `origin` is the GitHub remote **`https://github.com/jasonogrady/chip-leader.git`**. (It used to be an
  iCloud copy under `~/Library/Mobile Documents/.../GitHub/chip-leader`; that path is gone — the repo
  moved off iCloud. If `git pull` ever reports the remote "does not appear to be a git repository", the
  remote URL is pointing at the old iCloud path: `git remote set-url origin https://github.com/jasonogrady/chip-leader.git`.)
- **`picks_history.json` not found in the log = dangling input symlinks.** The two data files are
  symlinked in from the local `chip-input` working tree (see "Data sync from chip-input" below). If that
  tree moves, the symlinks dangle, the tracker exits at startup, and KeepAlive respawns it forever without
  binding 8765. Re-point the symlinks and kickstart.

- The live view runs as a **KeepAlive LaunchAgent** labeled `com.feitclub.chipleader`
  (plist in `deploy/launchd/`), executing `chip web 8765`.
- **If the page won't load at all, read `~/Library/Logs/chip-leader.log` FIRST.** Because
  KeepAlive is on, a startup crash makes launchd respawn the process every ~10s without ever
  binding 8765 — so the symptom is a dead page, and the Python traceback in the log is the cause.
- The DataGolf key is loaded from Keychain at launch
  (`security find-generic-password -s chip-leader -a datagolf -w`); a missing/locked keychain
  entry is a common "won't start" cause.
- Public URL is **chip.ogrady.golf** (Cloudflare tunnel). `modelhost.local:8765` is LAN-only
  (mDNS) and will not resolve off-network — use the public URL on a phone/cellular.

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

The two cross-cutting data files are produced by `chip-input` and symlinked into chip-leader's working
tree so reads are direct. The `chip-input` working tree lives at **`~/dev/chip-input`** on this mini:

- `~/dev/chip-input/standings/standings_latest.json`
- `~/dev/chip-input/picks_history.json`

```zsh
cd ~/chip-leader
ln -sf ~/dev/chip-input/standings/standings_latest.json standings/standings_latest.json
ln -sf ~/dev/chip-input/picks_history.json              picks_history.json
# verify they resolve (a dangling symlink crash-loops the service — see "Deploy / redeploy"):
ls -lL picks_history.json standings/standings_latest.json
```

> **History:** both repos used to live in iCloud Drive (`~/Library/Mobile Documents/.../GitHub/`) and
> synced between laptop and mini that way. They have since moved off iCloud to local working trees
> (`~/chip-leader`, `~/dev/chip-input`). If you see the old `~/Library/Mobile Documents/...` path
> anywhere — a symlink target or a git remote — it's stale and needs re-pointing to the local copy.

---

## Mac mini deployment

See `BACKLOG.md` → "Mac mini deployment" for the LaunchAgent + Caddy + Tailscale Funnel walkthrough.

### Active deployment on this Mac mini (`modelhost`, user `tensor`)

- Live working tree: `~/chip-leader` (the `~/dev/chip-leader` path is an unrelated empty dir — ignore it). To ship: commit + push to GitHub, then on the mini `cd ~/chip-leader && git pull origin main && launchctl kickstart -k gui/$(id -u)/com.feitclub.chipleader`.
- LaunchAgent: `~/Library/LaunchAgents/com.feitclub.chipleader.plist`, sets `CHIP_NO_OPEN=1` so `webbrowser.open` is suppressed.
- LAN URL: `http://modelhost.local:8765` (also `http://192.168.0.172:8765`).
- Logs: `~/Library/Logs/chip-leader.log`.

### Full Disk Access (legacy — only relevant if inputs live in iCloud)

> Now that the input files are symlinked from a local tree (`~/dev/chip-input`) rather than iCloud, FDA
> is no longer required for normal operation. Keep this section for the case where a symlink ever points
> back into `~/Library/Mobile Documents` — the iCloud EDEADLK failures below only happen there.

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
