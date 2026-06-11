"""Regression: intermission must fire when the just-finished event is over.

Root cause this guards against: the in-play feed names the event with its sponsor
suffix ("the Memorial Tournament presented by Workday") while the schedule feed omits
it ("the Memorial Tournament"). An exact dict lookup on the in-play name missed the
schedule row, so the authoritative status="completed" never reached compute_play_status,
the board fell through to "off-hours", and the public leaderboard stayed stuck on the
finished event instead of showing the intermission dark-state card.

Run: DATAGOLF_API_KEY=x python3 -m pytest tests/ -q   (or: python3 tests/test_intermission_name_match.py)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATAGOLF_API_KEY", "test-key")  # module requires it at import

import track_tournament as t

# The schedule feed exactly as upstream returns it: un-suffixed key, completed status,
# plus a future event the day after "today".
_SCHEDULE = {
    "the Memorial Tournament": {
        "event_name": "the Memorial Tournament", "status": "completed",
        "start_date": "2026-06-04", "location": "Dublin, OH",
    },
    "RBC Canadian Open": {
        "event_name": "RBC Canadian Open", "status": "",
        # start_date is set per-test relative to "today" so the test never goes stale.
        "location": "Toronto, ON",
    },
}

# The in-play feed name — note the sponsor suffix the schedule lacks.
_INPLAY_NAME = "the Memorial Tournament presented by Workday"


def _seed_schedule(next_start):
    sched = {k: dict(v) for k, v in _SCHEDULE.items()}
    sched["RBC Canadian Open"]["start_date"] = next_start.isoformat()
    t._SCHED_CACHE.update(ts=9e18, by_name=sched)  # ts in far future => never refetches


def test_schedule_row_matches_across_sponsor_suffix():
    from datetime import date
    _seed_schedule(date.today())
    row = t.schedule_row_for(_INPLAY_NAME)
    assert row is not None, "schedule lookup must tolerate the sponsor-suffix mismatch"
    assert row["status"] == "completed"


def test_intermission_fires_for_finished_event_with_cut():
    from datetime import date, timedelta
    tomorrow = date.today() + timedelta(days=1)
    _seed_schedule(tomorrow)

    info = {"event_name": _INPLAY_NAME, "current_round": 4, "last_update": "2026-06-07 5:59 PM"}
    sched_row = t.schedule_row_for(_INPLAY_NAME)
    next_event = t.next_scheduled_event(after_name=_INPLAY_NAME)

    assert next_event is not None and next_event["event_name"] == "RBC Canadian Open"

    # tournament_complete stays False on purpose: a cut event leaves missed-cut
    # players at thru=0, so the all-thru-18 fallback can never carry the load.
    ps = t.compute_play_status(info, sched_row, tournament_complete=False,
                               next_event=next_event)
    assert ps["status"] == "intermission", f"expected intermission, got {ps['status']!r}"
    assert ps["dark_card"] is not None
    assert ps["dark_card"]["concluded"] == "The Memorial Tournament"
    assert ps["dark_card"]["next"] == "RBC Canadian Open"


if __name__ == "__main__":
    test_schedule_row_matches_across_sponsor_suffix()
    test_intermission_fires_for_finished_event_with_cut()
    print("ok: both regression tests passed")
