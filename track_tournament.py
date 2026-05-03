#!/usr/bin/env python3
"""
track_tournament.py — Live in-tournament pool tracker.

Usage:
    python3 track_tournament.py [--my-entry ENTRY] [--top N] [--all] [--watch [SECS]]

    --my-entry  your pool entry name (default: "TIGER WOODS YALL!")
    --top N     show top N entries by pool standing (default: 30)
    --all       show all 148 entries
    --watch     auto-refresh every 60s (or --watch 30 for 30s interval)

Reads:
    picks_history.json                — parsed picks by tournament
    standings/standings_latest.json  — pre-tournament pool standings

DataGolf live (fetched fresh each run):
    /preds/in-play  — scores, win%, top_5/10/20, make_cut per player

Outputs:
    • Live tournament leaderboard (top 10)
    • Pool standings: pre-rank · projected rank · Δ · pick · live score · probs
    • My entry summary block
    • Alerts: cut danger / bleeding / contending
"""

import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT      = Path(__file__).parent
API_KEY   = os.environ.get("DATAGOLF_API_KEY")
BASE      = "https://feeds.datagolf.com"
MY_ENTRY  = "TIGER WOODS YALL!"

# US state → IANA tz. Pragmatic single-zone-per-state mapping; PGA venues sit
# in the dominant zone for every state we visit, so the edge cases (FL panhandle,
# IN/KY split, ND/SD split, etc.) don't matter in practice.
US_STATE_TZ = {
    "AL":"America/Chicago","AK":"America/Anchorage","AZ":"America/Phoenix",
    "AR":"America/Chicago","CA":"America/Los_Angeles","CO":"America/Denver",
    "CT":"America/New_York","DE":"America/New_York","FL":"America/New_York",
    "GA":"America/New_York","HI":"Pacific/Honolulu","ID":"America/Boise",
    "IL":"America/Chicago","IN":"America/Indiana/Indianapolis","IA":"America/Chicago",
    "KS":"America/Chicago","KY":"America/New_York","LA":"America/Chicago",
    "ME":"America/New_York","MD":"America/New_York","MA":"America/New_York",
    "MI":"America/Detroit","MN":"America/Chicago","MS":"America/Chicago",
    "MO":"America/Chicago","MT":"America/Denver","NE":"America/Chicago",
    "NV":"America/Los_Angeles","NH":"America/New_York","NJ":"America/New_York",
    "NM":"America/Denver","NY":"America/New_York","NC":"America/New_York",
    "ND":"America/Chicago","OH":"America/New_York","OK":"America/Chicago",
    "OR":"America/Los_Angeles","PA":"America/New_York","RI":"America/New_York",
    "SC":"America/New_York","SD":"America/Chicago","TN":"America/Chicago",
    "TX":"America/Chicago","UT":"America/Denver","VT":"America/New_York",
    "VA":"America/New_York","WA":"America/Los_Angeles","WV":"America/New_York",
    "WI":"America/Chicago","WY":"America/Denver","DC":"America/New_York",
}

# Schedule cache: (timestamp, by_event_name dict). Refresh hourly.
_SCHED_CACHE: dict = {"ts": 0.0, "by_name": {}}

def fetch_schedule() -> dict[str, dict]:
    """Return {event_name: schedule_row}, cached for 1 hour."""
    now = time.time()
    if _SCHED_CACHE["by_name"] and now - _SCHED_CACHE["ts"] < 3600:
        return _SCHED_CACHE["by_name"]
    url = f"{BASE}/get-schedule?tour=pga&file_format=json&key={API_KEY}"
    req = urllib.request.Request(url, headers={"User-Agent": "jdog-datagolf/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = json.loads(r.read().decode())
    by_name = {ev.get("event_name", ""): ev for ev in raw.get("schedule", [])}
    _SCHED_CACHE.update(ts=now, by_name=by_name)
    return by_name

def event_tz(location: str | None) -> ZoneInfo:
    """Parse 'Miami, FL' → ZoneInfo. Falls back to America/New_York."""
    if location and "," in location:
        state = location.rsplit(",", 1)[1].strip()[:2].upper()
        if state in US_STATE_TZ:
            return ZoneInfo(US_STATE_TZ[state])
    return ZoneInfo("America/New_York")

def parse_dg_last_update(s: str | None) -> datetime | None:
    """DG returns local-event time as 'YYYY-MM-DD H:MM PM' (no tz)."""
    if not s:
        return None
    for fmt in ("%Y-%m-%d %I:%M %p", "%Y-%m-%d %H:%M:%S UTC", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None

PLAY_WINDOW_START = 7   # 7am event-local
PLAY_WINDOW_END   = 19  # 7pm event-local
STALE_FRESH_MIN   = 15  # fresh if last_updated within 15 min

def compute_play_status(info: dict, sched_row: dict | None) -> dict:
    """Returns dict with status emoji, label, location, local time, pause flag."""
    location = (sched_row or {}).get("location") or ""
    tz = event_tz(location)
    now_local = datetime.now(tz)
    in_window = PLAY_WINDOW_START <= now_local.hour < PLAY_WINDOW_END

    last_update_naive = parse_dg_last_update(info.get("last_update") or info.get("last_updated"))
    if last_update_naive is not None:
        last_update_local = last_update_naive.replace(tzinfo=tz)
        age_min = (now_local - last_update_local).total_seconds() / 60.0
    else:
        age_min = None

    sched_status = (sched_row or {}).get("status", "")
    if sched_status == "completed":
        status, emoji, label = "concluded", "🔴", "Concluded"
    elif age_min is not None and age_min < STALE_FRESH_MIN:
        status, emoji, label = "active", "🟢", "Live"
    elif in_window and age_min is not None and age_min < 240:
        status, emoji, label = "lightning", "⚡", "Play suspended"
    elif not in_window:
        status, emoji, label = "off-hours", "🔴", "Play paused (overnight)"
    else:
        status, emoji, label = "unknown", "🟡", "Status unknown"

    # PT offset for the user (Pacific)
    pt = ZoneInfo("America/Los_Angeles")
    pt_offset_hours = int((tz.utcoffset(now_local.replace(tzinfo=None)).total_seconds()
                           - pt.utcoffset(now_local.replace(tzinfo=None)).total_seconds()) / 3600)
    pt_offset = f"PT{pt_offset_hours:+d}" if pt_offset_hours else "PT"

    return {
        "status": status,
        "emoji": emoji,
        "label": label,
        "location": location,
        "course": (sched_row or {}).get("course", ""),
        "tz_name": tz.key,
        "tz_abbr": now_local.strftime("%Z"),
        "local_time": now_local.strftime("%-I:%M %p"),
        "pt_offset": pt_offset,
        "in_play_window": in_window,
        "last_update_age_min": round(age_min) if age_min is not None else None,
        "play_window_start_hour": PLAY_WINDOW_START,
        "play_window_end_hour": PLAY_WINDOW_END,
    }

if not API_KEY:
    raise SystemExit("Set DATAGOLF_API_KEY first")

# ── Prize money model ─────────────────────────────────────────────────────────
# Approximate Masters 2026 payout tiers (marginal expected $ per finish band).
# Used to project each entry's earnings delta and re-rank the pool.
PRIZE_TIERS = {
    "win":     3_600_000,   # 1st
    "t2_5":    1_226_000,   # avg 2nd–5th  (2.16M / 1.37M / .96M / .82M)
    "t6_10":     648_000,   # avg 6th–10th
    "t11_20":    381_000,   # avg 11th–20th
    "t21_mc":    155_000,   # avg 21st–make cut
    "miss_cut":        0,
}

def expected_payout(p: dict) -> float:
    """Probability-weighted expected Masters payout from DG in-play fields."""
    win   = p.get("win",      0) or 0
    top5  = p.get("top_5",    0) or 0
    top10 = p.get("top_10",   0) or 0
    top20 = p.get("top_20",   0) or 0
    mkcut = p.get("make_cut", 0) or 0
    return (
        win                 * PRIZE_TIERS["win"]
        + (top5  - win)     * PRIZE_TIERS["t2_5"]
        + (top10 - top5)    * PRIZE_TIERS["t6_10"]
        + (top20 - top10)   * PRIZE_TIERS["t11_20"]
        + (mkcut - top20)   * PRIZE_TIERS["t21_mc"]
    )


# ── Formatting helpers ────────────────────────────────────────────────────────

def fmt_score(score) -> str:
    if score is None:
        return "-"
    return "E" if score == 0 else f"{score:+d}"

def fmt_pct(val) -> str:
    return "-" if val is None else f"{val * 100:.1f}%"

def fmt_money(val: float) -> str:
    return f"${val / 1_000_000:.2f}M"

def fmt_delta(d: int) -> str:
    if d == 0:
        return "—"
    arrow = "↑" if d < 0 else "↓"
    return f"{arrow}{abs(d)}"

def fmt_sg(val) -> str:
    if val is None:
        return "   —  "
    return f"{val:+.2f}"

def sg_diagnosis(sg: dict) -> str:
    """One-line interpretation of SG splits — helps flag regression vs. continuation."""
    ott  = sg.get("sg_ott")  or 0
    app  = sg.get("sg_app")  or 0
    arg  = sg.get("sg_arg")  or 0
    putt = sg.get("sg_putt") or 0
    ball = ott + app  # ball-striking composite

    parts = []
    if ball > 1.0:    parts.append("ball-striking strong")
    elif ball > 0.3:  parts.append("ball-striking solid")
    elif ball < -1.0: parts.append("ball-striking poor")
    elif ball < -0.3: parts.append("ball-striking shaky")

    if putt > 1.0:    parts.append("putter hot")
    elif putt > 0.3:  parts.append("putting well")
    elif putt < -1.5: parts.append(f"putter cost {abs(putt):.1f} strokes")
    elif putt < -0.5: parts.append("putter cold")

    if arg > 0.5:     parts.append("scrambling well")
    elif arg < -0.5:  parts.append("scrambling poor")

    if not parts:
        total = sg.get("sg_total") or 0
        if total > 0.5:  return "solid all-around"
        if total < -0.5: return "struggling across the board"
        return "neutral"
    return ", ".join(parts)


# ── Name mapping ──────────────────────────────────────────────────────────────
# DataGolf event names → picks_history tournament names

# ── TKE group ─────────────────────────────────────────────────────────────────
# (entry_name_in_pool, display_alias_or_None)
TKE_GROUP = [
    ("TIGER WOODS YALL!",  "O'Grady"),
    ("CURAÇAO BOYS",       "Charlton"),
    ("BILLY BAROO",        "Mascaro"),
    ("SCARLO",             "Carlo"),
    ("SWEETRUCKS",         "Norton"),
    ("MIKEBACC1452",       "Bacchini"),
    ("GO RILLA",           "Santilla"),
    ("LOVETHEBIRDS",       "Freidman"),
    ("ROACH",              "Corcoran"),
    ("WOOPSIES!",          "Diener"),
    ("DOUGAL",             "McDougal"),
    ("COOP",               "Cooper"),
    ("TACCONE1",           "Taccone"),
    ("TAJERKYAT1481",      "Tajerky"),
    ("LACEY UNDERALL",     "Fran"),
    ("STOMPER",            "Stahl"),
    ("ITSINTHEHOLE",       "Grease"),
    ("Blair Schlom",       "Yurchak"),
    ("SETHSTRADAMUS",      "Feit"),
]
TKE_NAMES = {e for e, _ in TKE_GROUP}


DG_NAME_MAP = {
    "Masters Tournament":    "The Masters",
    "PGA Championship":      "PGA Championship",
    "U.S. Open":             "U.S. Open Championship",
    "The Open Championship": "British Open Championship",
    "Cadillac Championship": "Miami Championship",
}


# ── Data loaders ──────────────────────────────────────────────────────────────

def load_picks(dg_tournament: str) -> tuple[dict[str, str], str]:
    """Return ({entry: dg_name}, resolved_tournament)."""
    path = ROOT / "picks_history.json"
    if not path.exists():
        sys.exit("picks_history.json not found — run parse_picks.py first")
    data = json.loads(path.read_text())
    known = {r["tournament"] for r in data}

    resolved = DG_NAME_MAP.get(dg_tournament)
    if not resolved or resolved not in known:
        resolved = dg_tournament if dg_tournament in known else None
    if not resolved:
        for t in known:
            if any(w in dg_tournament for w in t.split()):
                resolved = t
                break
    if not resolved:
        sys.exit(f"No picks for '{dg_tournament}'.\nKnown: {sorted(known)}\n"
                 "Add a mapping to DG_NAME_MAP or run parse_picks.py.")

    picks = {r["entry"]: r["dg_name"] for r in data if r["tournament"] == resolved}
    return picks, resolved


def load_standings() -> tuple[list[dict], str]:
    """Return (standings_list, date_str) sorted by rank."""
    path = ROOT / "standings" / "standings_latest.json"
    if not path.exists():
        sys.exit("standings/standings_latest.json not found — run parse_standings.py first")
    raw = json.loads(path.read_text())
    return sorted(raw["entries"], key=lambda e: e["rank"]), raw.get("date", "?")


def fetch_inplay() -> tuple[dict, dict]:
    """Fetch DG in-play. Returns (info, {player_name: record})."""
    url = (f"{BASE}/preds/in-play"
           f"?tour=pga&dead_heat=yes&odds_format=percent&file_format=json&key={API_KEY}")
    req = urllib.request.Request(url, headers={"User-Agent": "jdog-datagolf/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = json.loads(r.read().decode())
    live = {p["player_name"]: p for p in raw.get("data", [])}
    return raw.get("info", {}), live


def fetch_live_stats(round_str: str = "event") -> dict[str, dict]:
    """Fetch DG live-tournament-stats for a given round.

    round_str: 'event' (cumulative) or '1', '2', '3', '4'
    Returns {player_name: {sg_ott, sg_app, sg_arg, sg_putt, sg_total}}
    """
    url = (f"{BASE}/live-tournament-stats"
           f"?tour=pga&round={round_str}"
           f"&stat=sg_total,sg_ott,sg_app,sg_arg,sg_putt"
           f"&file_format=json&key={API_KEY}")
    req = urllib.request.Request(url, headers={"User-Agent": "jdog-datagolf/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = json.loads(r.read().decode())
    result = {}
    for p in raw.get("rows", []):
        name = p.get("player_name")
        if name:
            result[name] = {
                "sg_ott":   p.get("sg_ott"),
                "sg_app":   p.get("sg_app"),
                "sg_arg":   p.get("sg_arg"),
                "sg_putt":  p.get("sg_putt"),
                "sg_total": p.get("sg_total"),
            }
    return result


def fetch_sg_splits(current_round: int) -> dict[str, dict]:
    """Fetch per-round + cumulative SG. Returns {round_str: {player_name: sg_dict}}."""
    sg: dict[str, dict] = {}
    for r in range(1, current_round + 1):
        sg[str(r)] = fetch_live_stats(str(r))
    sg["event"] = fetch_live_stats("event")
    return sg


def demo_inplay() -> tuple[dict, dict]:
    """
    Synthetic mid-R2 snapshot — realistic scenario where Matsuyama is charging,
    Rahm/DeChambeau are near the cut line, and the pool is reshuffling.
    Used for --demo mode only; no API call made.
    """
    info = {
        "event_name":    "Masters Tournament",
        "current_round": 2,
        "last_update":   "2026-04-10 2:47 PM  [DEMO — simulated mid-round]",
    }
    # fmt: (player_name, R1, R2_today, thru, current_pos, current_score,
    #        win, top_5, top_10, top_20, make_cut)
    players_raw = [
        # Leaders
        ("McIlroy, Rory",       67, -6, 14, "T1",  -11, 0.31, 0.58, 0.75, 0.88, 0.99),
        ("Scheffler, Scottie",  70, -5, 14, "T1",  -11, 0.28, 0.54, 0.72, 0.86, 0.99),
        ("Schauffele, Xander",  70, -4, 14, "T3",   -9, 0.12, 0.32, 0.54, 0.72, 0.98),
        ("Rose, Justin",        70, -4, 13, "T3",   -9, 0.08, 0.25, 0.46, 0.66, 0.97),
        ("Day, Jason",          69, -3, 14, "T5",   -8, 0.05, 0.17, 0.36, 0.58, 0.96),
        ("Burns, Sam",          67, -2, 13, "T6",   -7, 0.04, 0.13, 0.29, 0.51, 0.95),
        # Mid-pack
        ("Matsuyama, Hideki",   72, -4, 14, "T7",   -7, 0.04, 0.12, 0.28, 0.50, 0.94),
        ("Fleetwood, Tommy",    71, -2, 14, "T8",   -6, 0.03, 0.09, 0.22, 0.43, 0.92),
        ("Spieth, Jordan",      72, -2, 13, "T9",   -6, 0.02, 0.07, 0.18, 0.38, 0.91),
        ("Young, Cameron",      73,  0, 18, "T10",  -5, 0.01, 0.05, 0.14, 0.31, 0.89),
        ("Reed, Patrick",       69,  0, 18, "T10",  -5, 0.01, 0.04, 0.13, 0.30, 0.88),
        ("Aberg, Ludvig",       74,  0, 13, "T12",  -4, 0.01, 0.03, 0.10, 0.25, 0.85),
        ("Fitzpatrick, Matt",   74, +1, 18, "T13",  -3, 0.01, 0.02, 0.07, 0.19, 0.80),
        ("Morikawa, Collin",    74, +1, 14, "T13",  -3, 0.00, 0.02, 0.06, 0.18, 0.79),
        ("Koepka, Brooks",      72, +1, 18, "T15",  -2, 0.00, 0.01, 0.04, 0.14, 0.74),
        ("Thomas, Justin",      72, +2, 18, "T16",  -1, 0.00, 0.01, 0.03, 0.10, 0.67),
        # Near cut (+3 is projected cut)
        ("Hovland, Viktor",     75, +1, 14, "T17",   0, 0.00, 0.01, 0.02, 0.07, 0.58),
        ("Lowry, Shane",        70, +3, 18, "T18",  +2, 0.00, 0.00, 0.01, 0.04, 0.49),
        # Bleeding — cut danger
        ("DeChambeau, Bryson",  76, +3, 14, "T19",  +3, 0.00, 0.00, 0.01, 0.03, 0.38),
        ("Rahm, Jon",           78, +2, 14, "T20",  +4, 0.00, 0.00, 0.00, 0.01, 0.22),
        ("Kitayama, Kurt",      69, +4, 18, "T21",  +5, 0.00, 0.00, 0.00, 0.01, 0.18),
        ("Homa, Max",           72, +4, 14, "T22",  +6, 0.00, 0.00, 0.00, 0.00, 0.12),
    ]
    live = {}
    for row in players_raw:
        (name, r1, today, thru, pos, total,
         win, top5, top10, top20, mkcut) = row
        live[name] = {
            "player_name":   name,
            "R1":            r1,
            "R2":            today,
            "current_pos":   pos,
            "current_score": total,
            "today":         today,
            "thru":          thru,
            "win":           win,
            "top_5":         top5,
            "top_10":        top10,
            "top_20":        top20,
            "make_cut":      mkcut,
        }
    return info, live


def demo_sg_splits() -> dict[str, dict]:
    """Synthetic SG splits for demo mode. {round_str: {player_name: sg_dict}}.

    Scenario: Matsuyama R1 even-par 72 — strong ball-striking, putter collapsed.
    R2 bounce-back: putting recovered, moved to -7.
    """
    r1 = {
        "McIlroy, Rory":      {"sg_ott": +1.2, "sg_app": +1.5, "sg_arg": +0.3, "sg_putt": +1.1, "sg_total": +4.1},
        "Scheffler, Scottie": {"sg_ott": +0.8, "sg_app": +1.8, "sg_arg": +0.5, "sg_putt": +0.6, "sg_total": +3.7},
        "Matsuyama, Hideki":  {"sg_ott": +0.6, "sg_app": +1.4, "sg_arg": -0.1, "sg_putt": -2.3, "sg_total": -0.4},
        "Schauffele, Xander": {"sg_ott": +0.9, "sg_app": +0.8, "sg_arg": +0.2, "sg_putt": +0.5, "sg_total": +2.4},
        "Fleetwood, Tommy":   {"sg_ott": +0.3, "sg_app": +0.7, "sg_arg": +0.1, "sg_putt": +0.6, "sg_total": +1.7},
        "Rahm, Jon":          {"sg_ott": -1.2, "sg_app": -0.9, "sg_arg": -0.3, "sg_putt": -0.8, "sg_total": -3.2},
        "Burns, Sam":         {"sg_ott": +0.5, "sg_app": +1.1, "sg_arg": +0.3, "sg_putt": +1.4, "sg_total": +3.3},
    }
    r2 = {
        "McIlroy, Rory":      {"sg_ott": +1.0, "sg_app": +1.3, "sg_arg": +0.4, "sg_putt": +0.9, "sg_total": +3.6},
        "Scheffler, Scottie": {"sg_ott": +0.7, "sg_app": +1.6, "sg_arg": +0.3, "sg_putt": +0.8, "sg_total": +3.4},
        "Matsuyama, Hideki":  {"sg_ott": +0.8, "sg_app": +1.2, "sg_arg": +0.2, "sg_putt": +0.7, "sg_total": +2.9},
        "Schauffele, Xander": {"sg_ott": +0.6, "sg_app": +0.9, "sg_arg": +0.0, "sg_putt": +0.7, "sg_total": +2.2},
        "Fleetwood, Tommy":   {"sg_ott": +0.1, "sg_app": +0.6, "sg_arg": -0.1, "sg_putt": +0.4, "sg_total": +1.0},
        "Rahm, Jon":          {"sg_ott": -0.8, "sg_app": -0.5, "sg_arg": -0.1, "sg_putt": +0.3, "sg_total": -1.1},
        "Burns, Sam":         {"sg_ott": +0.3, "sg_app": +0.8, "sg_arg": +0.1, "sg_putt": +0.7, "sg_total": +1.9},
    }
    keys = ("sg_ott", "sg_app", "sg_arg", "sg_putt", "sg_total")
    ev = {
        name: {k: round((r1.get(name, {}).get(k) or 0) + (r2.get(name, {}).get(k) or 0), 2)
               for k in keys}
        for name in set(r1) | set(r2)
    }
    return {"1": r1, "2": r2, "event": ev}


# ── Projection engine ─────────────────────────────────────────────────────────

def project_standings(standings: list[dict],
                      entry_pick: dict[str, str],
                      live: dict[str, dict]) -> dict[str, int]:
    """
    Re-rank every entry by (current_winnings + expected_tournament_payout).
    Returns {entry_name: projected_rank}.
    """
    scored = []
    for e in standings:
        name    = e["entry"]
        pick    = entry_pick.get(name)
        player  = live.get(pick) if pick else None
        exp     = expected_payout(player) if player else 0.0
        total   = (e.get("winnings") or 0) + exp
        scored.append((name, total))

    scored.sort(key=lambda x: -x[1])
    return {name: rank + 1 for rank, (name, _) in enumerate(scored)}


# ── ANSI helpers ─────────────────────────────────────────────────────────────
BOLD  = "\033[1m"
DIM   = "\033[2m"
GREEN = "\033[32m"
RED   = "\033[31m"
CYAN  = "\033[36m"
YELLOW= "\033[33m"
RESET = "\033[0m"

def bold(s: str)   -> str: return f"{BOLD}{s}{RESET}"
def dim(s: str)    -> str: return f"{DIM}{s}{RESET}"
def green(s: str)  -> str: return f"{GREEN}{s}{RESET}"
def red(s: str)    -> str: return f"{RED}{s}{RESET}"
def cyan(s: str)   -> str: return f"{CYAN}{s}{RESET}"
def yellow(s: str) -> str: return f"{YELLOW}{s}{RESET}"


# ── Projected finish label ────────────────────────────────────────────────────

def proj_finish_label(p: dict) -> str:
    if not p:
        return "—"
    win   = p.get("win",      0) or 0
    top5  = p.get("top_5",    0) or 0
    top10 = p.get("top_10",   0) or 0
    top20 = p.get("top_20",   0) or 0
    mkcut = p.get("make_cut", 0) or 0
    if win   > 0.20:  return "Win favorite"
    if win   > 0.06:  return "Contender"
    if top5  > 0.30:  return "Top 5"
    if top10 > 0.30:  return "Top 10"
    if top20 > 0.35:  return "Top 20"
    if top20 > 0.15:  return "Top 25"
    if mkcut > 0.70:  return "Makes cut"
    if mkcut > 0.45:  return "Cut risk"
    return "MC likely"


# ── Spinner fetch ─────────────────────────────────────────────────────────────

def spinner_fetch(fn):
    """Run fn() with a terminal spinner. Returns the result."""
    import itertools, threading
    result = [None]
    done   = [False]
    frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def spin():
        for f in itertools.cycle(frames):
            if done[0]:
                break
            print(f"\r  {cyan(f)}  Fetching live data…", end="", flush=True)
            time.sleep(0.08)
        print(f"\r  {green('✓')}  Live data loaded.              ")

    t = threading.Thread(target=spin, daemon=True)
    t.start()
    result[0] = fn()
    done[0] = True
    t.join()
    return result[0]


# ── Narrative generator ───────────────────────────────────────────────────────

def build_narrative(my_entry, entry_pick, live, standings, proj_rank,
                    n_total, current_round, label,
                    sg_event: dict | None = None,
                    tke_group: list | None = None) -> list[str]:
    import textwrap

    my_pick   = entry_pick.get(my_entry, "")
    my_player = live.get(my_pick)
    my_data   = next((e for e in standings if e["entry"] == my_entry), None)
    my_proj   = proj_rank.get(my_entry)
    my_pre    = my_data["rank"] if my_data else None
    my_delta  = (my_proj - my_pre) if my_proj and my_pre else 0

    paras = []
    ts = time.strftime("%I:%M %p")

    # ── Paragraph 1: TIGER WOODS YALL! ───────────────────────────────────────
    if my_player and my_pre and my_proj:
        score   = my_player["current_score"]
        pos     = my_player["current_pos"]
        thru    = my_player.get("thru", 0) or 0
        today   = my_player.get(f"R{current_round}", my_player.get("today", 0)) or 0
        win_pct = (my_player.get("win", 0) or 0) * 100
        mkcut   = (my_player.get("make_cut", 0) or 0) * 100
        first   = my_pick.split(",")[1].strip() if "," in my_pick else my_pick
        finished_r4 = (current_round == 4 and thru == 18)

        if finished_r4:
            if score <= -8:
                tone = "finished in stunning form"
            elif score <= -4:
                tone = "turned in a strong final round"
            elif score <= -1:
                tone = "finished in solid shape"
            elif score == 0:
                tone = "finished at even par — respectable"
            elif score <= 3:
                tone = "finished over par — a tough week"
            else:
                tone = "had a rough week"
        else:
            if score <= -8:
                tone = "is in full Sunday-charge mode"
            elif score <= -4:
                tone = "is making serious moves"
            elif score <= -1:
                tone = "is in solid shape"
            elif score == 0:
                tone = "is treading water at even par"
            elif score <= 3:
                tone = "is struggling but likely to survive the cut"
            else:
                tone = "is in serious trouble"

        today_s = fmt_score(today) if today else "—"
        pool_dir = f"up {abs(my_delta)}" if my_delta < 0 else (f"down {my_delta}" if my_delta > 0 else "steady")
        pool_note = f"#{my_pre} → #{my_proj} ({pool_dir})" if my_delta != 0 else f"holding at #{my_proj}"

        if finished_r4:
            p = (f"{my_entry}: {first} {tone}. Final: {fmt_score(score)} ({pos}), "
                 f"R{current_round} {today_s}. "
                 f"Win probability: {win_pct:.1f}%. "
                 f"Pool standing projected {pool_note} of {n_total}.")
        else:
            p = (f"{my_entry}: {first} {tone}. He's at {fmt_score(score)} ({pos}) "
                 f"through {thru} holes of R{current_round}, {today_s} today. "
                 f"Win probability: {win_pct:.1f}%. Cut survival: {mkcut:.0f}%. "
                 f"Pool standing projected {pool_note} of {n_total}.")
        paras.append(p)

        # ── SG diagnostic line ────────────────────────────────────────────────
        if sg_event:
            sg = sg_event.get(my_pick)
            if sg:
                ott  = fmt_sg(sg.get("sg_ott"))
                app  = fmt_sg(sg.get("sg_app"))
                arg  = fmt_sg(sg.get("sg_arg"))
                putt = fmt_sg(sg.get("sg_putt"))
                diag = sg_diagnosis(sg)
                paras.append(
                    f"SG splits (cumulative): OTT {ott}  APP {app}  "
                    f"ARG {arg}  PUTT {putt}  →  {diag}."
                )
    else:
        paras.append(f"{my_entry}: No live data for pick '{my_pick}'.")

    # ── Paragraph 1b: tournament completion context ───────────────────────────
    if current_round == 4:
        n_finished = sum(
            1 for p in live.values()
            if (p.get("thru") or 0) == 18
        )
        n_field = len(live)
        if n_finished == n_field:
            paras.append(f"Tournament complete — all {n_field} players have finished R4.")
        elif n_finished > 0:
            n_playing = n_field - n_finished
            paras.append(
                f"R4 in progress — {n_finished} of {n_field} players have finished, "
                f"{n_playing} still on the course."
            )

    # ── Paragraph 2: pool leaders ─────────────────────────────────────────────
    proj_sorted = sorted(standings, key=lambda e: proj_rank.get(e["entry"], 9999))
    leaders = proj_sorted[:3]
    leader_parts = []
    for e in leaders:
        name = e["entry"]
        pick = entry_pick.get(name, "—")
        p    = live.get(pick)
        score_s = fmt_score(p["current_score"]) if p else "—"
        pos_s   = p["current_pos"] if p else "—"
        last    = pick.split(",")[0] if "," in pick else pick
        done_flag = ""
        if p and current_round == 4 and (p.get("thru") or 0) == 18:
            done_flag = " ✓"
        leader_parts.append(f"{name} ({last}, {score_s} / {pos_s}{done_flag})")
    paras.append("Pool leaders — " + "  ·  ".join(
        f"#{i+1} {lp}" for i, lp in enumerate(leader_parts)
    ) + ".")

    # ── Paragraph 3: biggest movers ───────────────────────────────────────────
    movers = []
    for e in standings:
        name  = e["entry"]
        pre   = e["rank"]
        proj  = proj_rank.get(name, pre)
        delta = proj - pre
        pick  = entry_pick.get(name, "")
        player = live.get(pick)
        if player:
            movers.append((name, pre, proj, delta, pick))

    risers = sorted(movers, key=lambda x: x[3])[:3]   # biggest negative delta = moving up
    fallers= sorted(movers, key=lambda x: -x[3])[:3]  # biggest positive delta = moving down

    riser_parts = [f"{n} (#{pre}→#{proj}, {pick.split(',')[0]})" for n, pre, proj, d, pick in risers if d < 0]
    faller_parts= [f"{n} (#{pre}→#{proj}, {pick.split(',')[0]})" for n, pre, proj, d, pick in fallers if d > 0]

    if riser_parts or faller_parts:
        move_lines = []
        if riser_parts:
            move_lines.append("Rising: " + ", ".join(riser_parts))
        if faller_parts:
            move_lines.append("Falling: " + ", ".join(faller_parts))
        paras.append("Biggest movers — " + "  ·  ".join(move_lines) + ".")

    # ── Paragraph 4: rivals directly above my entry ───────────────────────────
    if my_proj:
        rivals_above = [
            e for e in standings
            if proj_rank.get(e["entry"], 9999) < my_proj
            and e["entry"] != my_entry
        ]
        rivals_above_sorted = sorted(rivals_above, key=lambda e: proj_rank.get(e["entry"], 9999))
        closest = rivals_above_sorted[-3:] if rivals_above_sorted else []
        if closest:
            parts = []
            for e in closest:
                pick = entry_pick.get(e["entry"], "")
                player = live.get(pick)
                score_s = fmt_score(player["current_score"]) if player else "—"
                mkcut_pct = (player.get("make_cut", 1) or 1) * 100 if player else 100
                danger = f", cut survival {mkcut_pct:.0f}%" if mkcut_pct < 60 else ""
                last = pick.split(",")[0] if "," in pick else pick
                parts.append(f"{e['entry']} ({last}, {score_s}{danger})")
            paras.append(
                f"Closest rivals ahead of {my_entry}: " + "  ·  ".join(parts) + "."
            )

    # ── Paragraph 5: cut danger / opportunity ────────────────────────────────
    cut_entries = [
        (e["entry"], proj_rank.get(e["entry"], 9999), entry_pick.get(e["entry"], ""),
         (live.get(entry_pick.get(e["entry"], "")) or {}).get("make_cut", 1) or 1)
        for e in standings
        if live.get(entry_pick.get(e["entry"], "")) and
           ((live.get(entry_pick.get(e["entry"], "")) or {}).get("make_cut", 1) or 1) < 0.50
    ]
    if cut_entries:
        ahead_danger = [(n, pr, pk, mc) for n, pr, pk, mc in cut_entries if pr < (my_proj or 9999)]
        if ahead_danger:
            names = ", ".join(f"{n} ({pk.split(',')[0]}, {mc*100:.0f}% cut)"
                              for n, pr, pk, mc in sorted(ahead_danger, key=lambda x: x[3])[:4])
            paras.append(
                f"Cut danger ahead of you — {len(ahead_danger)} entries projected above you "
                f"are at risk of zeroing out: {names}. "
                f"If they miss the cut, you move up."
            )

    # ── TKE section ───────────────────────────────────────────────────────────
    paras_tke = []
    if tke_group:
        tke_alias = {entry: a for entry, a in tke_group if a}
        tke_names_set = {entry for entry, _ in tke_group}
        standings_by_name = {e["entry"]: e for e in standings}

        tke_sorted = sorted(
            [e for e in standings if e["entry"] in tke_names_set],
            key=lambda e: proj_rank.get(e["entry"], 9999),
        )
        n_tke = len(tke_sorted)

        # Standings summary — top 5 TKEs
        parts = []
        for i, e in enumerate(tke_sorted[:5], 1):
            name  = e["entry"]
            alias = (tke_alias.get(name) or name)
            pick  = entry_pick.get(name, "")
            p     = live.get(pick)
            last  = pick.split(",")[0] if "," in pick else pick
            score_s = fmt_score(p["current_score"]) if p else "—"
            pos_s   = p["current_pos"] if p else "—"
            pool_r  = proj_rank.get(name, "?")
            done_flag = " ✓" if (p and current_round == 4 and (p.get("thru") or 0) == 18) else ""
            parts.append(f"#{pool_r} {alias} ({last}, {score_s}/{pos_s}{done_flag})")
        if parts:
            paras_tke.append("TKE pool standings — " + "  ·  ".join(
                f"{i}. {p}" for i, p in enumerate(parts, 1)
            ) + ".")

        # My entry's TKE rank
        my_tke_rank = next(
            (i for i, e in enumerate(tke_sorted, 1) if e["entry"] == my_entry), None
        )
        if my_tke_rank and my_proj:
            delta_tke = ""
            if my_tke_rank == 1:
                delta_tke = " — leading the group"
            elif my_tke_rank <= 3:
                delta_tke = f" — top 3 in the group"
            elif my_tke_rank > n_tke - 2:
                delta_tke = f" — near the bottom of the group"
            paras_tke.append(
                f"{my_entry} is #{my_tke_rank} of {n_tke} in the TKE group "
                f"(pool #{my_proj} of {n_total}){delta_tke}."
            )

        # TKE leaders detail (top 3 with more context)
        leaders_tke = tke_sorted[:3]
        leader_detail = []
        for e in leaders_tke:
            name  = e["entry"]
            alias = (tke_alias.get(name) or name)
            pick  = entry_pick.get(name, "")
            p     = live.get(pick)
            last  = pick.split(",")[0] if "," in pick else pick
            win_s = f"{(p.get('win') or 0)*100:.1f}% win" if p else "—"
            proj_label = proj_finish_label(p) if p else "—"
            leader_detail.append(f"{alias}: {last} ({proj_label}, {win_s})")
        if leader_detail:
            paras_tke.append("TKE top 3 — " + "  ·  ".join(leader_detail) + ".")

        # TKE cut danger
        tke_cut = [
            (e["entry"], proj_rank.get(e["entry"], 9999), entry_pick.get(e["entry"], ""),
             (live.get(entry_pick.get(e["entry"], "")) or {}).get("make_cut", 1) or 1)
            for e in tke_sorted
            if live.get(entry_pick.get(e["entry"], "")) and
               ((live.get(entry_pick.get(e["entry"], "")) or {}).get("make_cut", 1) or 1) < 0.50
        ]
        if tke_cut:
            names = ", ".join(
                f"{(tke_alias.get(nm) or nm)} ({pk.split(',')[0]}, {mc*100:.0f}% cut)"
                for nm, pr, pk, mc in sorted(tke_cut, key=lambda x: x[3])[:4]
            )
            paras_tke.append(f"TKE cut danger: {names}.")

    # ── Wrap and return ───────────────────────────────────────────────────────
    W_WRAP = 76
    lines = [f"  LIVE NARRATIVE  ·  {label}  R{current_round}  ·  updated {ts}"]
    lines.append("  " + "─" * W_WRAP)
    lines.append("")

    # Tournament section header
    lines.append(bold("  ── TOURNAMENT ──"))
    lines.append("")
    for para in paras:
        wrapped = textwrap.fill(para, width=W_WRAP, initial_indent="  ", subsequent_indent="  ")
        lines.append(wrapped)
        lines.append("")

    # TKE section
    if paras_tke:
        lines.append(bold("  ── TOP TKE ──"))
        lines.append("")
        for para in paras_tke:
            wrapped = textwrap.fill(para, width=W_WRAP, initial_indent="  ", subsequent_indent="  ")
            lines.append(wrapped)
            lines.append("")

    return lines


# ── SG watchlist panel ───────────────────────────────────────────────────────

def render_sg_panel(watchlist: list[str], sg_by_round: dict[str, dict],
                    current_round: int, W: int = 104) -> None:
    """Print per-round SG splits for each player on the watchlist."""
    rounds = [str(r) for r in range(1, current_round + 1)]
    components = [
        ("sg_ott",   "OTT  "),
        ("sg_app",   "APP  "),
        ("sg_arg",   "ARG  "),
        ("sg_putt",  "PUTT "),
        ("sg_total", "TOTAL"),
    ]

    print()
    print("━" * W)
    print(bold("  SG WATCHLIST  ·  strokes-gained splits by round"))
    print(dim("  OTT = off-the-tee · APP = approach · ARG = around green · PUTT = putting"))
    print()

    rnd_hdr = "".join(f"  {'R' + r:>7}" for r in rounds) + f"  {'EVENT':>7}"
    print(dim(f"  {'Player':<26}  {'':8}" + rnd_hdr))
    print(dim(f"  {'─'*26}  {'─'*8}" + ("  " + "─" * 7) * (len(rounds) + 1)))

    for player in watchlist:
        sg_ev = (sg_by_round.get("event") or {}).get(player)
        if not sg_ev:
            continue
        diag = sg_diagnosis(sg_ev)
        print()
        print(bold(f"  {player:<26}") + dim(f"  [{diag}]"))
        for key, label in components:
            vals = ""
            for r in rounds:
                v = (sg_by_round.get(r) or {}).get(player, {}).get(key)
                vals += f"  {fmt_sg(v):>7}"
            ev_v = sg_ev.get(key)
            vals += f"  {fmt_sg(ev_v):>7}"
            line = f"  {'':26}  {label}{vals}"
            if key == "sg_total":
                ev_val = ev_v or 0
                print(green(line) if ev_val > 0.3 else (red(line) if ev_val < -0.3 else dim(line)))
            elif key == "sg_putt":
                ev_val = ev_v or 0
                # Highlight cold putter (signal for regression vs. continuation)
                print(red(line) if ev_val < -0.8 else (green(line) if ev_val > 0.8 else line))
            else:
                print(line)

    print()
    print("━" * W)


# ── Scoreboard: top-20 golfers ║ top-20 pool (side-by-side) ─────────────────

def render_scoreboard(args, refresh_secs: int | None = None) -> None:
    if args.demo:
        info, live = demo_inplay()
        sg_by_round = demo_sg_splits()
    else:
        info, live = spinner_fetch(fetch_inplay)
        sg_by_round = {}
        try:
            rnd = info.get("current_round", 1)
            if isinstance(rnd, int) and rnd >= 1:
                sg_by_round = fetch_sg_splits(rnd)
        except Exception:
            pass  # SG data is best-effort; don't crash if endpoint unavailable

    tournament    = info.get("event_name", "Unknown Tournament")
    current_round = info.get("current_round", "?")
    last_update   = info.get("last_updated") or info.get("last_update", "?")

    entry_pick, resolved = load_picks(tournament)
    standings, standings_date = load_standings()
    proj_rank = project_standings(standings, entry_pick, live)
    sg_event = sg_by_round.get("event", {})

    label   = resolved if resolved != tournament else tournament
    n_total = len(standings)
    now_str = time.strftime("%A, %B %-d, %Y  %-I:%M %p")
    refresh_note = f"  ·  auto-refresh {refresh_secs}s" if refresh_secs else ""

    # ── Layout constants ──────────────────────────────────────────────────────
    # Left   panel: tournament leaderboard (L visible chars, no SG — use --sg)
    # Middle panel: pool top 20            (M visible chars)
    # Right  panel: TKE group              (R visible chars)
    L   = 50
    M   = 58
    R   = 49
    SEP = "  ║  "

    import re as _re
    _ansi = _re.compile(r'\033\[[0-9;]*m')

    def lpad(s: str, n: int) -> str:
        """Pad/truncate to exactly n *visible* chars (ANSI escape-safe)."""
        visible = _ansi.sub('', s)
        vlen = len(visible)
        if vlen <= n:
            return s + ' ' * (n - vlen)
        return visible[:n]

    W = L + len(SEP) + M + len(SEP) + R   # ≈ 165

    # ── Header ────────────────────────────────────────────────────────────────
    print("━" * W)
    print(bold(f"  🦫 CHIP LEADER 🏆  ·  {label}  Round {current_round}  ·  {now_str}{refresh_note}"))
    print(f"  {n_total} entries  ·  DG updated: {last_update}  ·  standings as of {standings_date}")
    print("━" * W)
    print()

    # ── Build left panel (tournament top 20, no SG columns) ───────────────────
    live_sorted = sorted(live.values(), key=lambda p: (p["current_score"], p["player_name"]))

    L_HDR = lpad(f"  {'Pos':<5}  {'Player':<15}  {'Score':>5}  {'Thru':>4}  {'Win%':>5}", L)
    L_SEP = lpad(f"  {'─'*5}  {'─'*15}  {'─'*5}  {'─'*4}  {'─'*5}", L)

    my_pick = entry_pick.get(args.my_entry)

    def player_row(p: dict, highlight_fn=None) -> str:
        pos_s   = p["current_pos"]
        name_s  = p["player_name"][:15]
        score_s = fmt_score(p["current_score"])
        thru_s  = "F" if p.get("thru") == 18 else str(p.get("thru", "-"))
        win_s   = fmt_pct(p.get("win"))
        plain   = lpad(f"  {pos_s:<5}  {name_s:<15}  {score_s:>5}  {thru_s:>4}  {win_s:>5}", L)
        return highlight_fn(plain) if highlight_fn else plain

    def pick_color(p: dict):
        today = p.get(f"R{current_round}", p.get("today", 0)) or 0
        if today < 0: return green
        if today > 0: return red
        return dim

    top20_names = {p["player_name"] for p in live_sorted[:20]}
    my_player   = live.get(my_pick) if my_pick else None

    left_lines = [dim(L_HDR), dim(L_SEP)]
    for p in live_sorted[:20]:
        is_pick = (p["player_name"] == my_pick)
        left_lines.append(player_row(p, pick_color(p) if is_pick else None))

    if my_player and my_pick not in top20_names:
        left_lines.append(lpad(f"  {'·' * (L - 2)}", L))
        left_lines.append(player_row(my_player, pick_color(my_player)))

    # ── Build middle panel (pool top 20) ──────────────────────────────────────
    proj_sorted = sorted(standings, key=lambda e: proj_rank.get(e["entry"], 9999))

    M_HDR = f"  {'#':>4}  {'Entry':<15}  {'Golfer':<13}  {'Score':>5}  {'Pos':<5}  {'Δ':>4}"
    M_SEP = f"  {'─'*4}  {'─'*15}  {'─'*13}  {'─'*5}  {'─'*5}  {'─'*4}"

    mid_lines: list[str] = [dim(M_HDR), dim(M_SEP)]
    my_in_mid = False
    for entry in proj_sorted[:20]:
        name   = entry["entry"]
        pre    = entry["rank"]
        proj   = proj_rank.get(name, pre)
        pick   = entry_pick.get(name)
        player = live.get(pick) if pick else None
        is_me  = (name == args.my_entry)
        if is_me:
            my_in_mid = True

        last  = (pick.split(",")[0] if pick and "," in pick else (pick or "—"))[:13]
        ename = name[:15]
        delta = fmt_delta(proj - pre)
        if player:
            score_s = fmt_score(player["current_score"])
            pos_s   = player["current_pos"][:5]
        else:
            score_s = pos_s = "—"

        plain = f"  {proj:>4}  {ename:<15}  {last:<13}  {score_s:>5}  {pos_s:<5}  {delta:>4}"
        mid_lines.append(bold(yellow(plain)) if is_me else plain)

    if not my_in_mid:
        my_standing = next((e for e in standings if e["entry"] == args.my_entry), None)
        if my_standing:
            _name  = my_standing["entry"]
            _pre   = my_standing["rank"]
            _proj  = proj_rank.get(_name, _pre)
            _pick  = entry_pick.get(_name)
            _player = live.get(_pick) if _pick else None
            _last  = (_pick.split(",")[0] if _pick and "," in _pick else (_pick or "—"))[:13]
            _ename = _name[:15]
            _delta = fmt_delta(_proj - _pre)
            _score_s, _pos_s = ("—", "—") if not _player else (
                fmt_score(_player["current_score"]), _player["current_pos"][:5])
            mid_lines.append(dim(f"  {'·' * 51}"))
            _plain = f"  {_proj:>4}  {_ename:<15}  {_last:<13}  {_score_s:>5}  {_pos_s:<5}  {_delta:>4}"
            mid_lines.append(bold(yellow(_plain)))

    # ── Build right panel (TKE group) ─────────────────────────────────────────
    alias_map = {entry: a for entry, a in TKE_GROUP if a}
    standings_by_name = {e["entry"]: e for e in standings}

    tke_rows_raw = []
    for entry_name, _ in TKE_GROUP:
        standing = standings_by_name.get(entry_name)
        if not standing:
            continue
        pre  = standing["rank"]
        proj = proj_rank.get(entry_name, pre)
        pick = entry_pick.get(entry_name)
        player = live.get(pick) if pick else None
        tke_rows_raw.append((entry_name, pre, proj, pick, player))
    tke_rows_raw.sort(key=lambda x: x[2])   # sort by projected pool rank

    T_HDR = f"  {'TKE':>3}  {'Name':<13}  {'Golfer':<12}  {'Score':>5}  {'Pool':<8}"
    T_SEP = f"  {'─'*3}  {'─'*13}  {'─'*12}  {'─'*5}  {'─'*8}"

    tke_lines: list[str] = [dim(T_HDR), dim(T_SEP)]
    for tke_rank, (entry_name, pre, proj, pick, player) in enumerate(tke_rows_raw, 1):
        is_me   = (entry_name == args.my_entry)
        alias_s = (alias_map.get(entry_name) or entry_name)[:13]
        last    = (pick.split(",")[0] if pick and "," in pick else (pick or "—"))[:12]
        delta_s = fmt_delta(proj - pre)
        pool_s  = f"#{proj}{delta_s}"[:8]
        if player:
            score_s = fmt_score(player["current_score"])
        else:
            score_s = "—"
        plain = f"  {tke_rank:>3}  {alias_s:<13}  {last:<12}  {score_s:>5}  {pool_s:<8}"
        tke_lines.append(bold(yellow(plain)) if is_me else plain)

    # ── Print three panels side by side ───────────────────────────────────────
    lh = lpad(bold("  TOURNAMENT TOP 20"), L)
    mh = bold(f"  {'POOL TOP 20':<{M - 2}}")
    th = bold("  TOP TKE")
    print(f"{lh}{SEP}{lpad(mh, M)}{SEP}{th}")
    print()

    max_rows = max(len(left_lines), len(mid_lines), len(tke_lines))
    left_lines += [""] * (max_rows - len(left_lines))
    mid_lines  += [""] * (max_rows - len(mid_lines))
    tke_lines  += [""] * (max_rows - len(tke_lines))

    for left, mid, tke in zip(left_lines, mid_lines, tke_lines):
        print(f"{lpad(left, L)}{SEP}{lpad(mid, M)}{SEP}{tke}")

    # ── Narrative ─────────────────────────────────────────────────────────────
    print()
    print("━" * W)
    narrative = build_narrative(
        args.my_entry, entry_pick, live, standings, proj_rank,
        n_total, current_round, label, sg_event=sg_event,
        tke_group=TKE_GROUP,
    )
    for line in narrative:
        print(line)
    print("━" * W)
    print()

    # ── SG Watchlist (--sg) ────────────────────────────────────────────────────
    if args.sg and sg_by_round and isinstance(current_round, int):
        my_pick   = entry_pick.get(args.my_entry)
        watchlist = [my_pick] if my_pick else []
        # Add top contenders by win% not already on the list
        top_by_win = sorted(live.values(), key=lambda p: -(p.get("win") or 0))
        for p in top_by_win:
            if p["player_name"] not in watchlist:
                watchlist.append(p["player_name"])
            if len(watchlist) >= 8:
                break
        render_sg_panel(watchlist, sg_by_round, current_round, W=W)


# ── Single render pass ────────────────────────────────────────────────────────

def render(args, refresh_secs: int | None = None) -> None:
    if args.demo:
        info, live = demo_inplay()
        sg_by_round = demo_sg_splits()
    else:
        info, live = spinner_fetch(fetch_inplay)
        sg_by_round = {}
        try:
            rnd = info.get("current_round", 1)
            if isinstance(rnd, int) and rnd >= 1:
                sg_by_round = fetch_sg_splits(rnd)
        except Exception:
            pass

    tournament    = info.get("event_name", "Unknown Tournament")
    current_round = info.get("current_round", "?")
    last_update   = info.get("last_updated") or info.get("last_update", "?")

    entry_pick, resolved = load_picks(tournament)
    standings, standings_date = load_standings()
    proj_rank = project_standings(standings, entry_pick, live)
    sg_event = sg_by_round.get("event", {})

    label   = resolved if resolved != tournament else tournament
    n_total = len(standings)

    # Sort all entries by projected rank for the live leaderboard
    proj_sorted = sorted(standings, key=lambda e: proj_rank.get(e["entry"], 9999))

    W = 104   # table width
    now_str  = time.strftime("%A, %B %-d, %Y  %-I:%M %p")
    refresh_note = f"  ·  auto-refresh {refresh_secs}s" if refresh_secs else ""

    # ── Header ───────────────────────────────────────────────────────────────
    print(f"{'━' * W}")
    print(bold(f"  🦫 CHIP LEADER 🏆  ·  {label}  Round {current_round}  ·  {now_str}{refresh_note}"))
    print(f"  {n_total} entries  ·  DG updated: {last_update}  ·  standings as of {standings_date}")
    print(f"{'━' * W}")
    print()

    # ── Column layout ─────────────────────────────────────────────────────────
    # #(4) Entry(24) Golfer(22) Score(7) Pos(6) Thru(5) Today(6) ProjFin(13) Win%(7) Δ(5)
    HDR = (f"  {'#':>4}  {'Entry':<24}  {'Golfer':<22}  "
           f"{'Score':>6}  {'Pos':<6}  {'Thru':>4}  {'Today':>5}  "
           f"{'Proj Finish':<13}  {'Win%':>5}  {'Δ':>5}")
    SEP = (f"  {'─'*4}  {'─'*24}  {'─'*22}  "
           f"{'─'*6}  {'─'*6}  {'─'*4}  {'─'*5}  "
           f"{'─'*13}  {'─'*5}  {'─'*5}")

    def row_str(rank: int, entry_name: str, pick: str | None,
                player: dict | None, pre_rank: int) -> str:
        delta = rank - pre_rank
        delta_s = fmt_delta(delta)
        if player:
            score   = player["current_score"]
            pos     = player["current_pos"]
            thru    = player.get("thru", 0)
            thru_s  = "F" if thru == 18 else str(thru)
            today   = player.get(f"R{current_round}", player.get("today")) or 0
            today_s = fmt_score(today)
            proj    = proj_finish_label(player)
            win_s   = fmt_pct(player.get("win"))
            score_s = fmt_score(score)
        else:
            score_s = today_s = pos = thru_s = proj = win_s = "—"

        golfer = (pick or "—")[:22]
        name   = entry_name[:24]

        return (f"  {rank:>4}  {name:<24}  {golfer:<22}  "
                f"{score_s:>6}  {pos:<6}  {thru_s:>4}  {today_s:>5}  "
                f"{proj:<13}  {win_s:>5}  {delta_s:>5}")

    # ── Page 1 (1–25) ────────────────────────────────────────────────────────
    print(bold(f"  TOP 25 — sorted by projected pool standing"))
    print()
    print(dim(HDR))
    print(dim(SEP))

    my_in_view = False
    page1 = proj_sorted[:25]
    for entry in page1:
        name   = entry["entry"]
        pick   = entry_pick.get(name)
        player = live.get(pick) if pick else None
        pre    = entry["rank"]
        proj   = proj_rank.get(name, pre)
        is_me  = (name == args.my_entry)
        if is_me:
            my_in_view = True

        line = row_str(proj, name, pick, player, pre)
        print(bold(yellow(line)) if is_me else line)

    # ── Page 2 (26–50) ───────────────────────────────────────────────────────
    page2 = proj_sorted[25:50]
    if page2:
        print()
        print(f"  {'─' * (W - 2)}")
        print(bold(f"  26–50"))
        print()
        print(dim(HDR))
        print(dim(SEP))
        for entry in page2:
            name   = entry["entry"]
            pick   = entry_pick.get(name)
            player = live.get(pick) if pick else None
            pre    = entry["rank"]
            proj   = proj_rank.get(name, pre)
            is_me  = (name == args.my_entry)
            if is_me:
                my_in_view = True

            line = row_str(proj, name, pick, player, pre)
            print(bold(yellow(line)) if is_me else line)

    # ── Always pin my entry — show below page 2 if outside top 50 ────────────
    if not my_in_view:
        my_standing = next((e for e in standings if e["entry"] == args.my_entry), None)
        if my_standing:
            _name   = my_standing["entry"]
            _pre    = my_standing["rank"]
            _proj   = proj_rank.get(_name, _pre)
            _pick   = entry_pick.get(_name)
            _player = live.get(_pick) if _pick else None
            print()
            print(f"  {'─' * (W - 2)}")
            print(bold(f"  MY ENTRY"))
            print()
            print(dim(HDR))
            print(dim(SEP))
            line = row_str(_proj, _name, _pick, _player, _pre)
            print(bold(yellow(line)))

    # ── Narrative ─────────────────────────────────────────────────────────────
    print()
    print(f"{'━' * W}")
    narrative = build_narrative(
        args.my_entry, entry_pick, live, standings, proj_rank,
        n_total, current_round, label, sg_event=sg_event,
        tke_group=TKE_GROUP,
    )
    for line in narrative:
        print(line)
    print(f"{'━' * W}")
    print()

    # ── SG Watchlist (--sg) ────────────────────────────────────────────────────
    if args.sg and sg_by_round and isinstance(current_round, int):
        my_pick   = entry_pick.get(args.my_entry)
        watchlist = [my_pick] if my_pick else []
        top_by_win = sorted(live.values(), key=lambda p: -(p.get("win") or 0))
        for p in top_by_win:
            if p["player_name"] not in watchlist:
                watchlist.append(p["player_name"])
            if len(watchlist) >= 8:
                break
        render_sg_panel(watchlist, sg_by_round, current_round, W=W)


# ── TKE leaderboard ──────────────────────────────────────────────────────────

def render_tke(args, refresh_secs: int | None = None) -> None:
    """Filtered leaderboard showing only TKE group entries."""
    if args.demo:
        info, live = demo_inplay()
        sg_by_round = demo_sg_splits()
    else:
        info, live = spinner_fetch(fetch_inplay)
        sg_by_round = {}

    tournament    = info.get("event_name", "Unknown Tournament")
    current_round = info.get("current_round", "?")
    last_update   = info.get("last_updated") or info.get("last_update", "?")

    entry_pick, resolved = load_picks(tournament)
    standings, standings_date = load_standings()
    proj_rank = project_standings(standings, entry_pick, live)

    label        = resolved if resolved != tournament else tournament
    n_total      = len(standings)
    now_str      = time.strftime("%A, %B %-d, %Y  %-I:%M %p")
    refresh_note = f"  ·  auto-refresh {refresh_secs}s" if refresh_secs else ""

    # Build alias lookup
    alias = {entry: a for entry, a in TKE_GROUP if a}

    # Standings lookup for winnings
    standings_by_name = {e["entry"]: e for e in standings}

    # Build TKE rows sorted by projected pool rank
    tke_rows = []
    missing   = []
    for entry_name, _ in TKE_GROUP:
        standing = standings_by_name.get(entry_name)
        if not standing:
            missing.append(entry_name)
            continue
        pre     = standing["rank"]
        proj    = proj_rank.get(entry_name, pre)
        current_win = standing.get("winnings") or 0
        pick    = entry_pick.get(entry_name)
        player  = live.get(pick) if pick else None
        exp_pay = expected_payout(player) if player else 0.0
        proj_win = current_win + exp_pay
        tke_rows.append({
            "entry":       entry_name,
            "alias":       alias.get(entry_name),
            "pre":         pre,
            "proj":        proj,
            "pick":        pick,
            "player":      player,
            "current_win": current_win,
            "proj_win":    proj_win,
        })

    tke_rows.sort(key=lambda r: r["proj"])

    W = 110
    print("━" * W)
    print(bold(f"  TKE LEADERBOARD  ·  {label}  Round {current_round}  ·  {now_str}{refresh_note}"))
    print(f"  {len(tke_rows)} entries  ·  {n_total} total in pool  ·  DG updated: {last_update}")
    print("━" * W)
    print()

    HDR = (f"  {'TKE':>3}  {'Entry':<20}  {'(Alias)':<11}  {'Golfer':<18}"
           f"  {'Score':>5}  {'Pos':<6}  {'Pool':>10}  {'Δ':>4}  {'Current':>9}  {'Proj':>9}")
    SEP = (f"  {'─'*3}  {'─'*20}  {'─'*11}  {'─'*18}"
           f"  {'─'*5}  {'─'*6}  {'─'*10}  {'─'*4}  {'─'*9}  {'─'*9}")
    print(dim(HDR))
    print(dim(SEP))

    for tke_rank, r in enumerate(tke_rows, 1):
        is_me  = (r["entry"] == args.my_entry)
        delta  = r["proj"] - r["pre"]
        delta_s = fmt_delta(delta)

        entry_s  = r["entry"][:20]
        alias_s  = f"({r['alias']})" if r["alias"] else ""
        pool_s   = f"#{r['pre']}→#{r['proj']}"

        if r["player"]:
            p       = r["player"]
            score_s = fmt_score(p["current_score"])
            pos_s   = p["current_pos"][:6]
            thru    = p.get("thru", 0)
            today   = p.get(f"R{current_round}", p.get("today", 0)) or 0
        else:
            score_s = pos_s = "—"
            today   = 0

        golfer_s = (r["pick"] or "—")
        # shorten "Last, First" → "Last, F."
        if golfer_s and "," in golfer_s:
            last, first = golfer_s.split(",", 1)
            golfer_s = f"{last.strip()}, {first.strip()[0]}."
        golfer_s = golfer_s[:18]

        cur_s  = fmt_money(r["current_win"])
        proj_s = fmt_money(r["proj_win"])

        line = (f"  {tke_rank:>3}  {entry_s:<20}  {alias_s:<11}  {golfer_s:<18}"
                f"  {score_s:>5}  {pos_s:<6}  {pool_s:>10}  {delta_s:>4}  {cur_s:>9}  {proj_s:>9}")

        if is_me:
            print(bold(yellow(line)))
        elif today < 0:
            print(green(line))
        elif today > 0:
            print(red(line))
        else:
            print(line)

    if missing:
        print()
        print(dim(f"  Not found in standings: {', '.join(missing)}"))

    print()
    print("━" * W)
    print()


# ── Web server ────────────────────────────────────────────────────────────────

_HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🦫 Chip Leader 🏆</title>
<link rel="icon" type="image/svg+xml" href="/icon.svg">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Chip Leader">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="theme-color" content="#0d1117">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #0d1117; color: #c9d1d9;
  font-family: 'SF Mono','Cascadia Code','Consolas',monospace;
  font-size: 13px; line-height: 1.5;
}
.header {
  background: #161b22; border-bottom: 1px solid #30363d;
  padding: 14px 24px; display: flex; align-items: center;
  justify-content: space-between; gap: 16px; flex-wrap: wrap;
}
.header-title {
  font-size: 17px; font-weight: 700; color: #fff; letter-spacing: 0.4px;
  display: flex; align-items: baseline; gap: 8px;
}
.brand-emoji { font-size: 18px; filter: drop-shadow(0 0 6px rgba(212,168,67,0.35)); }
.brand-long  { display: inline; }
.brand-short { display: none; }
.header-sep  { color: #484f58; font-weight: 400; }
.header-meta  { color: #8b949e; font-size: 11px; margin-top: 3px; }
.status-line {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  margin-top: 5px; font-size: 13px; color: #c9d1d9;
}
.status-emoji { font-size: 14px; line-height: 1; }
.status-emoji.pulse { animation: status-pulse 1.6s ease-in-out infinite; }
@keyframes status-pulse { 0%,100%{opacity:1;} 50%{opacity:0.45;} }
.status-tournament { font-weight: 600; color: #fff; }
.status-loc  { color: #8b949e; }
.status-loc::before { content: "·"; margin-right: 8px; color: #484f58; }
.status-time { color: #8b949e; font-variant-numeric: tabular-nums; }
.status-time::before { content: "·"; margin-right: 8px; color: #484f58; }
.header-right { display: flex; align-items: center; gap: 14px; }
.last-fetched { font-size: 11px; color: #8b949e; white-space: nowrap; }

/* ── Countdown ring ── */
.refresh-area { display: flex; align-items: center; gap: 10px; }
.ring-wrap {
  position: relative; width: 50px; height: 50px;
  display: flex; align-items: center; justify-content: center;
  transition: filter 0.3s;
}
.ring-wrap.low { filter: drop-shadow(0 0 6px rgba(248,81,73,0.65)); }
.countdown-svg { width: 50px; height: 50px; transform: rotate(-90deg); }
.ring-bg   { fill: none; stroke: #30363d; stroke-width: 3; }
.ring-fill {
  fill: none; stroke: #d4a843; stroke-width: 3; stroke-linecap: round;
  stroke-dasharray: 100 100; stroke-dashoffset: 0;
  transition: stroke-dashoffset 0.9s linear, stroke 0.5s;
}
.ring-fill.spin {
  animation: ring-spin 1.1s linear infinite;
  stroke-dasharray: 70 100; stroke-dashoffset: 0; stroke: #58a6ff;
  transition: none;
}
@keyframes ring-spin { to { stroke-dashoffset: -100; } }
.ring-label {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  transform: rotate(90deg);
  font-size: 11px; font-weight: 700; color: #d4a843;
  pointer-events: none;
  font-variant-numeric: tabular-nums;
}
.ring-label.low  { color: #f85149; animation: label-pulse 1s ease-in-out infinite; }
.ring-label.spin { color: #58a6ff; font-size: 11px; animation: label-pulse 0.9s ease-in-out infinite; }
@keyframes label-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.45; } }

/* ── Loading shimmer bar (top of page during fetch) ── */
.shimmer {
  position: fixed; top: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, transparent, #58a6ff, transparent);
  background-size: 50% 100%; background-repeat: no-repeat;
  background-position: -50% 0;
  opacity: 0; pointer-events: none; z-index: 100;
  transition: opacity 0.2s;
}
.shimmer.on { opacity: 1; animation: shimmer-slide 1.1s linear infinite; }
@keyframes shimmer-slide {
  0%   { background-position: -50% 0; }
  100% { background-position: 150% 0; }
}

.btn-update {
  background: #21262d; border: 1px solid #30363d;
  color: #c9d1d9; padding: 7px 16px; border-radius: 6px;
  cursor: pointer; font-family: inherit; font-size: 12px;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
  white-space: nowrap;
}
.btn-update:hover  { background: #30363d; border-color: #58a6ff; color: #58a6ff; }
.btn-update:active { background: #0d1117; }
.btn-update:disabled { opacity: 0.55; cursor: default; }

/* ── Tabs ── */
.tabs {
  background: #161b22; border-bottom: 1px solid #30363d;
  padding: 0 24px; display: flex;
}
.tab-btn {
  background: none; border: none; border-bottom: 2px solid transparent;
  color: #8b949e; padding: 10px 16px; cursor: pointer;
  font-family: inherit; font-size: 13px; font-weight: 500;
  transition: color 0.15s, border-color 0.15s;
}
.tab-btn:hover  { color: #c9d1d9; }
.tab-btn.active { color: #fff; border-bottom-color: #d4a843; }

/* ── Layout ── */
.content  { padding: 14px 20px; }
.tab-pane { display: none; }
.tab-pane.active { display: block; }

/* ── Status banners ── */
.banner {
  display: none; border-radius: 6px; padding: 9px 14px;
  font-size: 12px; margin-bottom: 12px; align-items: center; gap: 8px;
}
.banner.visible { display: flex; }
.banner-load { background: #161b22; border: 1px solid #30363d; color: #58a6ff; }
.banner-err  { background: #160707; border: 1px solid #f85149; color: #f85149; }
.banner-warn { background: #1c1606; border: 1px solid #d4a843; color: #d4a843; }
.dot {
  width: 7px; height: 7px; background: #58a6ff; border-radius: 50%;
  animation: pulse 0.9s ease-in-out infinite; flex-shrink: 0;
}
@keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.25; } }

/* ── Table ── */
.tbl-wrap { overflow-x: auto; border-radius: 6px; border: 1px solid #30363d; }
table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
thead th {
  background: #161b22; color: #8b949e; font-weight: 600;
  padding: 8px 11px; text-align: left; border-bottom: 1px solid #30363d;
  cursor: pointer; white-space: nowrap; user-select: none;
  position: sticky; top: 0; z-index: 1;
}
thead th:hover { color: #c9d1d9; }
thead th.sort-asc::after  { content: ' ↑'; color: #d4a843; }
thead th.sort-desc::after { content: ' ↓'; color: #d4a843; }
thead th.r, td.r { text-align: right; font-variant-numeric: tabular-nums; }
tbody tr { border-bottom: 1px solid #1c2128; }
tbody tr:last-child { border-bottom: none; }
tbody tr:hover td { background: #161b22; }
@keyframes row-flash {
  0%   { background: rgba(212,168,67,0.35); }
  100% { background: transparent; }
}
tbody tr.flash td { animation: row-flash 5s ease-out; }
tbody td { padding: 6px 11px; white-space: nowrap; }

/* Row/cell states */
tr.me td { color: #d4a843; font-weight: 700; }
tr.me:hover td { background: #1a1508 !important; }
tr.tke td { color: #ff6b6b; }
tr.me.tke td { color: #d4a843; }   /* "me" wins over tke */
.dragon { margin-left: 4px; }
.g { color: #3fb950; }
.rr { color: #f85149; }
.dim { color: #8b949e; }
.gold { color: #d4a843; font-weight: 600; }
.danger { color: #f85149; }

/* ── Narrative ── */
.narrative {
  background: #161b22; border: 1px solid #30363d;
  border-radius: 6px; padding: 16px 20px; margin-top: 4px;
}
.nar-section { color: #58a6ff; font-size: 11px; font-weight: 700;
  letter-spacing: 1px; text-transform: uppercase;
  margin: 14px 0 6px; }
.nar-section:first-child { margin-top: 0; }
.nar-p { font-size: 12.5px; line-height: 1.65; margin-bottom: 8px; color: #c9d1d9; }

/* ── Footer ── */
.footer { text-align: center; color: #484f58; font-size: 11px;
  padding: 14px; border-top: 1px solid #1c2128; margin-top: 20px; }

/* ── Tab label show/hide ── */
.tab-long  { display: inline; }
.tab-short { display: none; }
.tab-ico   { font-size: 14px; }

/* ── Mobile responsive (<=768px): hide secondary columns ── */
@media (max-width: 768px) {
  .header { padding: 10px 14px; }
  .header-title { font-size: 16px; gap: 6px; }
  .brand-long { display: none; }
  .brand-short { display: inline; }
  .header-sep { font-size: 12px; }
  .last-fetched { display: none; }
  .ring-wrap, .countdown-svg { width: 56px; height: 56px; }
  .ring-label { font-size: 12px; }
  .btn-update { padding: 9px 14px; font-size: 13px; }
  .content { padding: 10px 8px; }
  .tabs { padding: 0 6px; }
  .tab-btn { padding: 10px 9px; font-size: 12px; }
  .tab-long  { display: none; }
  .tab-short { display: inline; }
  table { font-size: 11.5px; }
  thead th, tbody td { padding: 5px 7px; }
  /* Pool tab: hide Thru, Today, Proj Finish, Cur #, Cuts */
  #tbl-pool th[data-col="5"], #tbl-pool td:nth-child(6),
  #tbl-pool th[data-col="6"], #tbl-pool td:nth-child(7),
  #tbl-pool th[data-col="7"], #tbl-pool td:nth-child(8),
  #tbl-pool th[data-col="9"], #tbl-pool td:nth-child(10),
  #tbl-pool th[data-col="13"], #tbl-pool td:nth-child(14) { display: none; }
  /* Tournament tab: hide Today, Top10, Make Cut */
  #tbl-tournament th[data-col="4"], #tbl-tournament td:nth-child(5),
  #tbl-tournament th[data-col="6"], #tbl-tournament td:nth-child(7),
  #tbl-tournament th[data-col="7"], #tbl-tournament td:nth-child(8) { display: none; }
  /* TKE tab: hide Thru/Today */
  #tbl-tke th[data-col="6"], #tbl-tke td:nth-child(7) { display: none; }
}
</style>
</head>
<body>

<div class="shimmer" id="shimmer"></div>

<div class="header">
  <div>
    <div class="header-title">
      <span class="brand-emoji">🦫</span>
      <span class="brand-long">Chip Leaderboard</span>
      <span class="brand-short">Chip Leader</span>
      <span class="brand-emoji">🏆</span>
      <span class="header-sep" id="hdr-context"></span>
    </div>
    <div class="status-line" id="status-line">
      <span class="status-emoji" id="status-emoji">🟡</span>
      <span class="status-tournament" id="status-tournament">—</span>
      <span class="status-loc" id="status-loc"></span>
      <span class="status-time" id="status-time"></span>
    </div>
    <div class="header-meta"  id="hdr-meta">Loading…</div>
  </div>
  <div class="header-right">
    <span class="last-fetched" id="last-fetched"></span>
    <div class="refresh-area">
      <div class="ring-wrap">
        <svg class="countdown-svg" viewBox="0 0 36 36">
          <circle class="ring-bg"   cx="18" cy="18" r="15.9155"/>
          <circle class="ring-fill" cx="18" cy="18" r="15.9155" id="ring-fill"/>
        </svg>
        <div class="ring-label" id="ring-label">120s</div>
      </div>
      <button class="btn-update" id="btn-update" onclick="manualRefresh()">Update Now</button>
    </div>
  </div>
</div>

<div class="tabs">
  <button class="tab-btn active" onclick="switchTab(this,'pool')"><span class="tab-ico">🏆</span><span class="tab-long"> Pool Standings</span><span class="tab-short"> Pool</span></button>
  <button class="tab-btn" onclick="switchTab(this,'tournament')"><span class="tab-ico">⛳</span><span class="tab-long"> Tournament Board</span><span class="tab-short"> Board</span></button>
  <button class="tab-btn" onclick="switchTab(this,'tke')"><span class="tab-ico">🐉</span><span class="tab-long"> Top TKEs</span><span class="tab-short"> TKEs</span></button>
  <button class="tab-btn" onclick="switchTab(this,'narrative')"><span class="tab-ico">📝</span><span class="tab-long"> Narrative</span><span class="tab-short"> Story</span></button>
</div>

<div class="content">
  <div class="banner banner-load" id="banner-load"><div class="dot"></div>Fetching live data from DataGolf…</div>
  <div class="banner banner-err"  id="banner-err"></div>
  <div class="banner banner-warn" id="banner-stale"></div>

  <div class="tab-pane active" id="tab-pool">
    <div class="tbl-wrap"><table id="tbl-pool">
      <thead><tr>
        <th class="r" data-col="0" onclick="sortBy(this,'tbl-pool')" title="Projected pool rank">Proj #</th>
        <th data-col="1" onclick="sortBy(this,'tbl-pool')">Entry</th>
        <th data-col="2" onclick="sortBy(this,'tbl-pool')">Golfer</th>
        <th class="r" data-col="3" onclick="sortBy(this,'tbl-pool')">Score</th>
        <th data-col="4" onclick="sortBy(this,'tbl-pool')">Pos</th>
        <th class="r" data-col="5" onclick="sortBy(this,'tbl-pool')">Thru</th>
        <th class="r" data-col="6" onclick="sortBy(this,'tbl-pool')">Today</th>
        <th data-col="7" onclick="sortBy(this,'tbl-pool')">Proj Finish</th>
        <th class="r" data-col="8" onclick="sortBy(this,'tbl-pool')">Win%</th>
        <th class="r" data-col="9" onclick="sortBy(this,'tbl-pool')" title="Current pool rank">Cur #</th>
        <th class="r" data-col="10" onclick="sortBy(this,'tbl-pool')" title="Current season winnings">Cur $</th>
        <th class="r" data-col="11" onclick="sortBy(this,'tbl-pool')" title="Projected season winnings (current + expected payout this event)">Proj $</th>
        <th class="r" data-col="12" onclick="sortBy(this,'tbl-pool')" title="Δ Proj $ − Cur $: expected money added by this event">Δ$</th>
        <th class="r" data-col="13" onclick="sortBy(this,'tbl-pool')" title="Cuts made / events played (pick reliability)">Cuts</th>
        <th class="r" data-col="14" onclick="sortBy(this,'tbl-pool')" title="Cur # − Proj #">Δ#</th>
      </tr></thead>
      <tbody id="tbody-pool"></tbody>
    </table></div>
  </div>

  <div class="tab-pane" id="tab-tournament">
    <div class="tbl-wrap"><table id="tbl-tournament">
      <thead><tr>
        <th data-col="0" onclick="sortBy(this,'tbl-tournament')">Pos</th>
        <th data-col="1" onclick="sortBy(this,'tbl-tournament')">Player</th>
        <th class="r" data-col="2" onclick="sortBy(this,'tbl-tournament')">Score</th>
        <th class="r" data-col="3" onclick="sortBy(this,'tbl-tournament')">Thru</th>
        <th class="r" data-col="4" onclick="sortBy(this,'tbl-tournament')">Today</th>
        <th class="r" data-col="5" onclick="sortBy(this,'tbl-tournament')">Win%</th>
        <th class="r" data-col="6" onclick="sortBy(this,'tbl-tournament')">Top 10%</th>
        <th class="r" data-col="7" onclick="sortBy(this,'tbl-tournament')">Make Cut%</th>
      </tr></thead>
      <tbody id="tbody-tournament"></tbody>
    </table></div>
  </div>

  <div class="tab-pane" id="tab-tke">
    <div class="tbl-wrap"><table id="tbl-tke">
      <thead><tr>
        <th class="r" data-col="0" onclick="sortBy(this,'tbl-tke')">TKE</th>
        <th data-col="1" onclick="sortBy(this,'tbl-tke')">Entry</th>
        <th data-col="2" onclick="sortBy(this,'tbl-tke')">Alias</th>
        <th data-col="3" onclick="sortBy(this,'tbl-tke')">Golfer</th>
        <th class="r" data-col="4" onclick="sortBy(this,'tbl-tke')">Score</th>
        <th data-col="5" onclick="sortBy(this,'tbl-tke')">Pos</th>
        <th class="r" data-col="6" onclick="sortBy(this,'tbl-tke')">Pool Rank</th>
        <th class="r" data-col="7" onclick="sortBy(this,'tbl-tke')">Δ Pool</th>
        <th class="r" data-col="8" onclick="sortBy(this,'tbl-tke')">Current $</th>
        <th class="r" data-col="9" onclick="sortBy(this,'tbl-tke')" title="Projected season winnings (current + expected payout this event)">Proj $</th>
        <th class="r" data-col="10" onclick="sortBy(this,'tbl-tke')" title="Δ Proj $ − Cur $: expected money added by this event">Δ$</th>
        <th class="r" data-col="11" onclick="sortBy(this,'tbl-tke')">Win%</th>
      </tr></thead>
      <tbody id="tbody-tke"></tbody>
    </table></div>
  </div>

  <div class="tab-pane" id="tab-narrative">
    <div class="narrative" id="narrative-content"></div>
  </div>
</div>

<div class="footer">🦫 Chip Leader 🏆 · Feit Club One-and-Done · ⛳ Powered by DataGolf</div>

<script>
const REFRESH = 120;
const REFRESH_OFFHOURS = 600;  // 10min poll when tournament is in overnight pause
let countdown = REFRESH, ticker = null, loading = false;
let playState = {};
const prevSnapshot = { pool: {}, tournament: {}, tke: {} };
function flashIfChanged(tr, key, signature, bucket) {
  const prev = prevSnapshot[bucket][key];
  if (prev !== undefined && prev !== signature) tr.classList.add('flash');
  prevSnapshot[bucket][key] = signature;
}
const sortState = {};

// ── Tabs ──────────────────────────────────────────────────────────────────────
function switchTab(btn, id) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-' + id).classList.add('active');
}

// ── Ring ──────────────────────────────────────────────────────────────────────
function setRing(secs) {
  const fill  = document.getElementById('ring-fill');
  const label = document.getElementById('ring-label');
  const wrap  = document.querySelector('.ring-wrap');
  const pct   = Math.max(0, secs / REFRESH);
  fill.classList.remove('spin');
  fill.style.strokeDashoffset = (1 - pct) * 100;
  fill.style.stroke = pct > 0.5 ? '#d4a843' : pct > 0.2 ? '#e3b341' : '#f85149';
  label.classList.remove('spin');
  label.textContent = secs + 's';
  const low = secs <= 10 && secs > 0;
  wrap.classList.toggle('low', low);
  label.classList.toggle('low', low);
}
function setRingLoading() {
  const fill  = document.getElementById('ring-fill');
  const label = document.getElementById('ring-label');
  const wrap  = document.querySelector('.ring-wrap');
  fill.classList.add('spin');
  fill.style.strokeDashoffset = '';
  label.classList.add('spin');
  label.classList.remove('low');
  wrap.classList.remove('low');
  label.textContent = '⛳';
  document.getElementById('shimmer').classList.add('on');
}
function clearShimmer() { document.getElementById('shimmer').classList.remove('on'); }
function setRingPaused() {
  const fill  = document.getElementById('ring-fill');
  const label = document.getElementById('ring-label');
  const wrap  = document.querySelector('.ring-wrap');
  fill.classList.remove('spin');
  fill.style.strokeDashoffset = 0;
  fill.style.stroke = '#484f58';
  label.classList.remove('spin','low');
  wrap.classList.remove('low');
  label.textContent = '⏸';
}
function startTicker() {
  clearInterval(ticker);
  if (document.hidden) { setRingPaused(); return; }
  // FR1: if tournament is outside its 7am-7pm event-local play window,
  // poll every 10 min instead of every 2 min and show ⏸ on the ring.
  const offhours = playState && playState.in_play_window === false;
  countdown = offhours ? REFRESH_OFFHOURS : REFRESH;
  if (offhours) { setRingPaused(); }
  else { setRing(countdown); }
  ticker = setInterval(() => {
    countdown--;
    if (!offhours) setRing(countdown);
    if (countdown <= 0) fetchData();
  }, 1000);
}

// ── Formatting ────────────────────────────────────────────────────────────────
const fmtScore = v => v === null || v === undefined ? '—' : v === 0 ? 'E' : (v > 0 ? '+' + v : '' + v);
const fmtPct   = v => v === null || v === undefined ? '—' : (v * 100).toFixed(1) + '%';
const fmtMoney = v => !v ? '—' : v >= 1e6 ? '$' + (v/1e6).toFixed(2) + 'M' : v >= 1e3 ? '$' + Math.round(v/1e3) + 'K' : '$' + v;
const fmtDeltaMoney = v => {
  if (!v || Math.abs(v) < 1) return '—';
  const sign = v > 0 ? '+' : '−';
  const a = Math.abs(v);
  const body = a >= 1e6 ? '$' + (a/1e6).toFixed(2) + 'M' : a >= 1e3 ? '$' + Math.round(a/1e3) + 'K' : '$' + Math.round(a);
  return sign + body;
};
const fmtThru  = v => v === null || v === undefined ? '—' : v === 18 ? 'F' : '' + v;
const fmtDelta = d => !d || d === 0 ? '—' : d < 0 ? '↑' + Math.abs(d) : '↓' + d;
const scoreCls = v => v === null || v === undefined ? 'dim' : v < 0 ? 'g' : v > 0 ? 'rr' : 'dim';
const deltaCls = d => !d || d === 0 ? 'dim' : d < 0 ? 'g' : 'rr';
function fmtGolfer(dg) {
  if (!dg) return '—';
  if (!dg.includes(',')) return dg;
  const [last, first] = dg.split(',', 2);
  return first.trim() + ' ' + last.trim();
}

function escapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function td(content, cls, sortVal, title) {
  const el = document.createElement('td');
  if (cls) el.className = cls;
  el.innerHTML = content;
  if (sortVal !== undefined) el.dataset.sort = sortVal;
  if (title) el.title = title;
  return el;
}

// ── Pool table ────────────────────────────────────────────────────────────────
function renderPool(entries) {
  const tbody = document.getElementById('tbody-pool');
  tbody.innerHTML = '';
  entries.forEach(e => {
    const tr = document.createElement('tr');
    if (e.is_me) tr.classList.add('me');
    if (e.is_tke) tr.classList.add('tke');
    flashIfChanged(tr, e.entry, e.rank + '|' + e.score + '|' + e.today, 'pool');
    const sv = e.score !== null && e.score !== undefined ? e.score : 999;
    const tv = e.today !== null && e.today !== undefined ? e.today : 999;
    const wv = -(e.win_pct || 0);
    const entryLabel = escapeHtml(e.entry) + (e.is_tke ? '<span class="dragon">🐉</span>' : '');
    tr.appendChild(td(e.rank,             'r',  e.rank));
    tr.appendChild(td(entryLabel,         '',   e.entry));
    tr.appendChild(td(fmtGolfer(e.golfer),'',   e.golfer,  e.golfer));
    tr.appendChild(td(fmtScore(e.score),  'r ' + scoreCls(e.score), sv));
    tr.appendChild(td(e.pos || '—',       ''));
    tr.appendChild(td(fmtThru(e.thru),    'r',  e.thru !== null ? e.thru : 99));
    tr.appendChild(td(fmtScore(e.today),  'r ' + scoreCls(e.today), tv));
    tr.appendChild(td(e.proj_finish || '—', ''));
    const wc = (e.win_pct || 0) > 0.08 ? 'r gold' : 'r dim';
    tr.appendChild(td(fmtPct(e.win_pct),  wc,  wv));
    tr.appendChild(td(e.pre_rank,         'r',  e.pre_rank));
    tr.appendChild(td(fmtMoney(e.winnings),       'r', -(e.winnings || 0)));
    tr.appendChild(td(fmtMoney(e.proj_winnings),  'r', -(e.proj_winnings || 0)));
    const dMoney = (e.proj_winnings || 0) - (e.winnings || 0);
    tr.appendChild(td(fmtDeltaMoney(dMoney), 'r ' + (dMoney > 0 ? 'g' : dMoney < 0 ? 'rr' : 'dim'), -dMoney));
    const cutsCls = e.cuts_ratio == null ? 'r dim' : e.cuts_ratio >= 0.875 ? 'r g' : e.cuts_ratio >= 0.625 ? 'r' : 'r rr';
    tr.appendChild(td(e.cuts_made || '—', cutsCls, -(e.cuts_ratio || 0)));
    tr.appendChild(td(fmtDelta(e.delta),  'r ' + deltaCls(e.delta), e.delta || 0));
    tbody.appendChild(tr);
  });
}

// ── Tournament table ──────────────────────────────────────────────────────────
function renderTournament(players, myPick) {
  const tbody = document.getElementById('tbody-tournament');
  tbody.innerHTML = '';
  players.forEach(p => {
    const tr = document.createElement('tr');
    if (p.player === myPick) tr.classList.add('me');
    flashIfChanged(tr, p.player, p.pos + '|' + p.score + '|' + p.today, 'tournament');
    const sv  = p.score !== null && p.score !== undefined ? p.score : 999;
    const tv  = p.today !== null && p.today !== undefined ? p.today : 999;
    tr.appendChild(td(p.pos || '—', ''));
    tr.appendChild(td(p.player,     ''));
    tr.appendChild(td(fmtScore(p.score), 'r ' + scoreCls(p.score), sv));
    tr.appendChild(td(fmtThru(p.thru),   'r', p.thru !== null ? p.thru : 99));
    tr.appendChild(td(fmtScore(p.today), 'r ' + scoreCls(p.today), tv));
    const wc = (p.win_pct || 0) > 0.08 ? 'r gold' : 'r';
    tr.appendChild(td(fmtPct(p.win_pct), wc,  -(p.win_pct || 0)));
    tr.appendChild(td(fmtPct(p.top10),   'r',  -(p.top10 || 0)));
    const mc = (p.make_cut || 1) < 0.5 ? 'r danger' : 'r';
    tr.appendChild(td(fmtPct(p.make_cut), mc,  -(p.make_cut || 0)));
    tbody.appendChild(tr);
  });
}

// ── TKE table ─────────────────────────────────────────────────────────────────
function renderTKE(rows) {
  const tbody = document.getElementById('tbody-tke');
  tbody.innerHTML = '';
  rows.forEach((r, i) => {
    const tr = document.createElement('tr');
    if (r.is_me) tr.classList.add('me');
    // No .tke class on this tab: TKEs render white; my-entry stays gold.
    flashIfChanged(tr, r.entry, r.proj + '|' + r.score, 'tke');
    const sv = r.score !== null && r.score !== undefined ? r.score : 999;
    const entryLabel = escapeHtml(r.entry) + '<span class="dragon">🐉</span>';
    tr.appendChild(td(i + 1,               'r',  i + 1));
    tr.appendChild(td(entryLabel,          ''));
    tr.appendChild(td(r.alias || '—',      ''));
    tr.appendChild(td(fmtGolfer(r.pick),   '',   r.pick, r.pick));
    tr.appendChild(td(fmtScore(r.score),   'r ' + scoreCls(r.score), sv));
    tr.appendChild(td(r.pos || '—',        ''));
    tr.appendChild(td('#' + r.proj,        'r',  r.proj));
    tr.appendChild(td(fmtDelta(r.delta),   'r ' + deltaCls(r.delta), r.delta || 0));
    tr.appendChild(td(fmtMoney(r.winnings),'r',  -(r.winnings || 0)));
    tr.appendChild(td(fmtMoney(r.proj_winnings), 'r', -(r.proj_winnings || 0)));
    const dM = (r.proj_winnings || 0) - (r.winnings || 0);
    tr.appendChild(td(fmtDeltaMoney(dM), 'r ' + (dM > 0 ? 'g' : dM < 0 ? 'rr' : 'dim'), -dM));
    const wc = (r.win_pct || 0) > 0.08 ? 'r gold' : 'r dim';
    tr.appendChild(td(fmtPct(r.win_pct),   wc,  -(r.win_pct || 0)));
    tbody.appendChild(tr);
  });
}

// ── Narrative ─────────────────────────────────────────────────────────────────
function renderNarrative(lines) {
  const el = document.getElementById('narrative-content');
  let html = '';
  for (const raw of lines) {
    const s = raw.trim();
    if (!s || /^[─━]+$/.test(s)) continue;
    if (s.includes('── TOURNAMENT') || s.includes('── TOP TKE') ||
        s.includes('──TOURNAMENT') || s.includes('──TOP TKE')) {
      const title = s.replace(/──/g,'').trim();
      html += `<div class="nar-section">${title}</div>`;
    } else if (s.startsWith('LIVE NARRATIVE') || s.startsWith('──')) {
      // skip leading title/separator lines
    } else if (s.length > 6) {
      html += `<p class="nar-p">${s}</p>`;
    }
  }
  el.innerHTML = html || '<p class="nar-p dim">No narrative available.</p>';
}

// ── Render all ────────────────────────────────────────────────────────────────
function renderAll(data) {
  const m = data.meta;
  document.getElementById('hdr-context').textContent =
    '·  ' + m.tournament + '  ·  R' + m.round;
  document.getElementById('hdr-meta').textContent =
    '👥 ' + m.n_total + ' entries  ·  🛰 DG ' + m.last_update +
    '  ·  📊 standings ' + m.standings_date;
  document.getElementById('last-fetched').textContent = '🕒 ' + m.fetched_at;

  // Status line: emoji · tournament · location · local time (PT offset)
  const p = m.play || {};
  playState = p;
  const emojiEl = document.getElementById('status-emoji');
  emojiEl.textContent = p.emoji || '🟡';
  emojiEl.classList.toggle('pulse', p.status === 'lightning' || p.status === 'active');
  emojiEl.title = p.label || '';
  document.getElementById('status-tournament').textContent = m.tournament + ' · R' + m.round;
  document.getElementById('status-loc').textContent = p.location || '';
  if (p.local_time) {
    document.getElementById('status-time').textContent =
      p.local_time + ' ' + (p.tz_abbr || '') + ' (' + (p.pt_offset || 'PT') + ')';
  } else {
    document.getElementById('status-time').textContent = '';
  }

  const stale = document.getElementById('banner-stale');
  if (m.standings_stale_days != null && m.standings_stale_days > 14) {
    stale.textContent = '⚠ Pool standings are ' + m.standings_stale_days + ' days old (' + m.standings_date + '). Parse the latest standings PDF to refresh winnings/positions.';
    stale.classList.add('visible');
  } else {
    stale.classList.remove('visible');
  }

  const myEntry = (data.pool_entries || []).find(e => e.is_me);
  const myPick  = myEntry ? myEntry.golfer : '';

  renderPool(data.pool_entries || []);
  renderTournament(data.tournament_top || [], myPick);
  renderTKE(data.tke_rows || []);
  renderNarrative(data.narrative_lines || []);
}

// ── Fetch ─────────────────────────────────────────────────────────────────────
function fetchData() {
  if (loading) return;
  loading = true;
  clearInterval(ticker);
  setRingLoading();
  const bl = document.getElementById('banner-load');
  const be = document.getElementById('banner-err');
  const btn = document.getElementById('btn-update');
  bl.classList.add('visible');
  be.classList.remove('visible');
  btn.disabled = true;
  btn.textContent = 'Updating…';

  fetch('/data')
    .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(data => {
      loading = false;
      bl.classList.remove('visible');
      clearShimmer();
      btn.disabled = false;
      btn.textContent = 'Update Now';
      if (data.error) throw new Error(data.error);
      renderAll(data);
      startTicker();
    })
    .catch(err => {
      loading = false;
      bl.classList.remove('visible');
      clearShimmer();
      btn.disabled = false;
      btn.textContent = 'Update Now';
      be.textContent = 'Error: ' + err.message;
      be.classList.add('visible');
      setRing(REFRESH);
      startTicker();
    });
}
function manualRefresh() { if (!loading) fetchData(); }

// ── Sort ──────────────────────────────────────────────────────────────────────
function sortBy(th, tableId) {
  const col   = parseInt(th.dataset.col);
  const state = sortState[tableId] || {};
  const asc   = state.col === col ? !state.asc : true;
  sortState[tableId] = { col, asc };

  const tbl = document.getElementById(tableId);
  tbl.querySelectorAll('thead th').forEach(h => h.classList.remove('sort-asc','sort-desc'));
  th.classList.add(asc ? 'sort-asc' : 'sort-desc');

  const tbody = tbl.querySelector('tbody');
  const rows  = Array.from(tbody.querySelectorAll('tr'));
  rows.sort((a, b) => {
    const ac = a.cells[col], bc = b.cells[col];
    const av = ac.dataset.sort !== undefined ? parseFloat(ac.dataset.sort) : ac.textContent.trim();
    const bv = bc.dataset.sort !== undefined ? parseFloat(bc.dataset.sort) : bc.textContent.trim();
    if (typeof av === 'number' && typeof bv === 'number') return asc ? av - bv : bv - av;
    return asc ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
  });
  rows.forEach(r => tbody.appendChild(r));
}

document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    clearInterval(ticker);
    if (!loading) setRingPaused();
  } else if (!loading) {
    fetchData();
  }
});
document.addEventListener('DOMContentLoaded', fetchData);
</script>
</body>
</html>"""


def _strip_ansi(s: str) -> str:
    import re
    return re.sub(r'\033\[[0-9;]*m', '', s)


def _today_with_fallback(player: dict, current_round: int):
    """Return player's today-score, falling back to current_score minus prior
    round totals when DG returns null mid-round."""
    today = player.get(f"R{current_round}", player.get("today"))
    if today is not None:
        return today
    total = player.get("current_score")
    if total is None or current_round <= 1:
        return None
    prior = 0
    for r in range(1, current_round):
        rv = player.get(f"R{r}")
        if rv is None:
            return None
        prior += rv
    return total - prior


def build_web_data(args) -> dict:
    """Fetch live data and build JSON payload for the web view."""
    if args.demo:
        info, live = demo_inplay()
        sg_by_round = demo_sg_splits()
    else:
        info, live = fetch_inplay()
        sg_by_round = {}
        try:
            rnd = info.get("current_round", 1)
            if isinstance(rnd, int) and rnd >= 1:
                sg_by_round = fetch_sg_splits(rnd)
        except Exception:
            pass

    tournament    = info.get("event_name", "Unknown Tournament")
    current_round = info.get("current_round", "?")
    last_update   = info.get("last_updated") or info.get("last_update", "?")

    entry_pick, resolved = load_picks(tournament)
    standings, standings_date = load_standings()
    proj_rank = project_standings(standings, entry_pick, live)

    label   = resolved if resolved != tournament else tournament
    n_total = len(standings)

    # Pool entries — all, sorted by projected rank
    proj_sorted = sorted(standings, key=lambda e: proj_rank.get(e["entry"], 9999))
    pool_entries = []
    for entry in proj_sorted:
        name   = entry["entry"]
        pre    = entry["rank"]
        proj   = proj_rank.get(name, pre)
        pick   = entry_pick.get(name)
        player = live.get(pick) if pick else None
        row: dict = {
            "rank": proj, "pre_rank": pre, "delta": proj - pre,
            "entry": name, "golfer": pick or "",
            "is_me": (name == args.my_entry),
            "is_tke": (name in TKE_NAMES),
            "winnings": entry.get("winnings") or 0,
            "proj_winnings": (entry.get("winnings") or 0) + (expected_payout(player) if player else 0.0),
            "cuts_made":  entry.get("cuts_made"),
            "cuts_ratio": entry.get("cuts_ratio"),
            "fedex":      entry.get("fedex"),
        }
        if player:
            today = _today_with_fallback(player, current_round)
            row.update({
                "score": player.get("current_score"),
                "pos":   player.get("current_pos", ""),
                "thru":  player.get("thru"),
                "today": today,
                "win_pct": player.get("win"),
                "top10":   player.get("top_10"),
                "make_cut": player.get("make_cut"),
                "proj_finish": proj_finish_label(player),
            })
        else:
            row.update({"score": None, "pos": "", "thru": None, "today": None,
                        "win_pct": None, "top10": None, "make_cut": None, "proj_finish": ""})
        pool_entries.append(row)

    # Tournament top 25
    live_sorted = sorted(live.values(),
                         key=lambda p: (p.get("current_score", 0), p.get("player_name", "")))
    tournament_top = []
    for p in live_sorted[:25]:
        today = _today_with_fallback(p, current_round)
        tournament_top.append({
            "pos":      p.get("current_pos", ""),
            "player":   p.get("player_name", ""),
            "score":    p.get("current_score"),
            "thru":     p.get("thru"),
            "today":    today,
            "win_pct":  p.get("win"),
            "top10":    p.get("top_10"),
            "make_cut": p.get("make_cut"),
        })

    # TKE rows
    alias_map = {e: a for e, a in TKE_GROUP if a}
    standings_by_name = {e["entry"]: e for e in standings}
    tke_rows = []
    for entry_name, _ in TKE_GROUP:
        standing = standings_by_name.get(entry_name)
        if not standing:
            continue
        pre  = standing["rank"]
        proj = proj_rank.get(entry_name, pre)
        pick = entry_pick.get(entry_name)
        player = live.get(pick) if pick else None
        row = {
            "entry": entry_name, "alias": alias_map.get(entry_name, ""),
            "pre_rank": pre, "proj": proj, "delta": proj - pre,
            "pick": pick or "", "is_me": (entry_name == args.my_entry),
            "winnings": standing.get("winnings") or 0,
            "proj_winnings": (standing.get("winnings") or 0) + (expected_payout(player) if player else 0.0),
        }
        if player:
            today = _today_with_fallback(player, current_round)
            row.update({
                "score": player.get("current_score"),
                "pos":   player.get("current_pos", ""),
                "thru":  player.get("thru"),
                "today": today,
                "win_pct": player.get("win"),
                "make_cut": player.get("make_cut"),
            })
        else:
            row.update({"score": None, "pos": "", "thru": None,
                        "today": None, "win_pct": None, "make_cut": None})
        tke_rows.append(row)
    tke_rows.sort(key=lambda r: r["proj"])

    # Narrative (ANSI stripped)
    sg_event = sg_by_round.get("event", {})
    narrative_raw = build_narrative(
        args.my_entry, entry_pick, live, standings, proj_rank,
        n_total, current_round, label, sg_event=sg_event, tke_group=TKE_GROUP,
    )
    narrative_lines = [_strip_ansi(ln) for ln in narrative_raw]

    # Convert DG's last_updated (Eastern, returned as "YYYY-MM-DD H:MM AM/PM"
    # or 24-hour UTC) to local time.
    last_update_local = str(last_update)
    try:
        from datetime import datetime
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            ZoneInfo = None
        s = str(last_update).replace(" UTC", "").strip()
        dt = None
        src_tz = None
        for fmt in ("%Y-%m-%d %I:%M %p", "%Y-%m-%d %I:%M:%S %p"):
            try:
                dt = datetime.strptime(s, fmt)
                src_tz = ZoneInfo("America/New_York") if ZoneInfo else None
                break
            except ValueError:
                continue
        if dt is None:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    dt = datetime.strptime(s, fmt)
                    src_tz = ZoneInfo("UTC") if ZoneInfo else None
                    break
                except ValueError:
                    continue
        if dt is not None and src_tz is not None:
            dt = dt.replace(tzinfo=src_tz)
            last_update_local = dt.astimezone().strftime("%-I:%M %p %Z")
    except Exception:
        pass

    # Stale-standings flag (>14 days old)
    stale_days = None
    try:
        from datetime import date
        sd = date.fromisoformat(str(standings_date))
        stale_days = (date.today() - sd).days
    except Exception:
        pass

    sched_row = None
    if not args.demo:
        try:
            sched_row = fetch_schedule().get(tournament)
        except Exception:
            sched_row = None
    play = compute_play_status(info, sched_row)

    return {
        "meta": {
            "tournament":    label,
            "round":         current_round,
            "last_update":   last_update_local,
            "standings_date": standings_date,
            "standings_stale_days": stale_days,
            "n_total":       n_total,
            "fetched_at":    time.strftime("%I:%M:%S %p"),
            "play":          play,
        },
        "pool_entries":    pool_entries,
        "tournament_top":  tournament_top,
        "tke_rows":        tke_rows,
        "narrative_lines": narrative_lines,
    }


def serve_web(args, port: int = 8765) -> None:
    """Start lightweight HTTP server for the web view."""
    import socket
    import threading
    import webbrowser
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import urlparse

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *a):
            pass  # suppress access logs

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/":
                body = _HTML_PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", len(body))
                self.end_headers()
                self.wfile.write(body)
            elif path in ("/icon.svg", "/apple-touch-icon.png", "/favicon.ico"):
                # Beaver emoji rendered as SVG. Used for browser favicon and
                # iOS home-screen icon; iOS 16+ accepts SVG for apple-touch-icon.
                svg = (
                    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 180">'
                    '<rect width="180" height="180" rx="36" fill="#0d1117"/>'
                    '<text x="50%" y="54%" text-anchor="middle" '
                    'dominant-baseline="middle" font-size="120" '
                    'font-family="Apple Color Emoji,Segoe UI Emoji,sans-serif">'
                    '\U0001F9AB</text></svg>'
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "image/svg+xml")
                self.send_header("Content-Length", len(svg))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                self.wfile.write(svg)
            elif path == "/data":
                try:
                    data = build_web_data(args)
                    body = json.dumps(data).encode()
                    import hashlib
                    etag_src = str(data.get("meta", {}).get("last_update", "")) + "|" + str(len(body))
                    etag = '"' + hashlib.md5(etag_src.encode()).hexdigest() + '"'
                    if self.headers.get("If-None-Match") == etag:
                        self.send_response(304)
                        self.send_header("ETag", etag)
                        self.send_header("Cache-Control", "no-cache")
                        self.end_headers()
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", len(body))
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("ETag", etag)
                    self.end_headers()
                    self.wfile.write(body)
                except Exception as exc:
                    err = json.dumps({"error": str(exc)}).encode()
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", len(err))
                    self.end_headers()
                    self.wfile.write(err)
            else:
                self.send_response(404)
                self.end_headers()

    for attempt in range(10):
        try:
            httpd = ThreadingHTTPServer(("0.0.0.0", port + attempt), Handler)
            port = port + attempt
            break
        except OSError:
            continue
    else:
        raise SystemExit(f"No free port found near {port}")
    try:
        host = socket.gethostname()
        if not host.endswith(".local"):
            host = f"{host}.local"
    except Exception:
        host = "localhost"
    url = f"http://{host}:{port}"
    print(f"\n  Web view:  {url}")
    print(f"  Auto-refresh: 120s   ·   Ctrl+C to stop\n")
    if sys.stdout.isatty() and not os.environ.get("CHIP_NO_OPEN"):
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
        httpd.shutdown()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Live pool tournament tracker")
    parser.add_argument("--my-entry", default=MY_ENTRY)
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--all", action="store_true", dest="show_all")
    parser.add_argument("--watch", nargs="?", const=60, type=int, metavar="SECS",
                        help="Auto-refresh every N seconds (default 60)")
    parser.add_argument("--demo", action="store_true",
                        help="Show a simulated mid-round snapshot (no API call)")
    parser.add_argument("--full", action="store_true",
                        help="Show full 50-entry pool table instead of scoreboard")
    parser.add_argument("--sg", action="store_true",
                        help="Show SG component watchlist panel (my pick + top contenders)")
    parser.add_argument("--tke", action="store_true",
                        help="Show TKE group leaderboard only")
    parser.add_argument("--serve", nargs="?", const=8765, type=int, metavar="PORT",
                        help="Start web server (default port 8765)")
    args = parser.parse_args()

    if args.serve is not None:
        serve_web(args, port=args.serve)
        return

    # Default view: scoreboard (top-20 golfers ║ top-20 pool)
    # --full: full 50-entry pool table
    # --tke: TKE group filtered view
    if args.tke:
        view_fn = render_tke
    elif args.full:
        view_fn = render
    else:
        view_fn = render_scoreboard

    if args.watch:
        interval = args.watch
        try:
            while True:
                os.system("clear")
                view_fn(args, refresh_secs=interval)
                print(f"  Refreshing in {interval}s — Ctrl+C to stop\n")
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n  Stopped.")
    else:
        view_fn(args)


if __name__ == "__main__":
    main()
