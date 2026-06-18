#!/usr/bin/env python3
"""
Pit Wall API Server
Uses FastF1 to fetch data from the official Formula 1 API.
Replaces the deprecated Ergast API entirely.
Supports multi-season: append ?year=YYYY to any endpoint.
"""

import os
import time
import json
from datetime import datetime, timezone
from collections import defaultdict

import fastf1
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
CACHE_DIR = os.path.join(os.environ.get('TEMP', '/tmp'), 'pitwall_cache')
os.makedirs(CACHE_DIR, exist_ok=True)
fastf1.Cache.enable_cache(CACHE_DIR)

CURRENT_YEAR = datetime.now(timezone.utc).year
STATIC_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(STATIC_DIR, 'index.html')

# ---------------------------------------------------------------------------
# In-memory data cache (survives between requests) — separate per year
# ---------------------------------------------------------------------------
_data_cache = {}  # {year: {"standings": ..., "cached_at": ...}}


def _utc_now():
    return datetime.now(timezone.utc)


def _resolve_year(year: int | None) -> int:
    """Use the provided year or detect the current F1 season."""
    if year is not None:
        return year
    # Try current year first; fall back to previous if no schedule
    try:
        s = fastf1.get_event_schedule(CURRENT_YEAR)
        if s is not None and len(s) > 0:
            return CURRENT_YEAR
    except Exception:
        pass
    return CURRENT_YEAR - 1


def get_schedule(year=2026):
    """Return the race schedule with practice/testing rounds removed."""
    schedule = fastf1.get_event_schedule(year)
    return schedule[schedule['RoundNumber'] > 0].copy()


def get_round_info(year=2026):
    """Determine current (last finished), next, and total rounds."""
    schedule = get_schedule(year)
    now = _utc_now()
    total = len(schedule)
    current = None
    next_round = None

    def _to_utc(dt):
        if hasattr(dt, 'tzinfo') and dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    for _, r in schedule.iterrows():
        race_date = _to_utc(r['EventDate'])
        if race_date <= now:
            current = int(r['RoundNumber'])
        elif next_round is None:
            next_round = int(r['RoundNumber'])
            break

    return {"current": current, "next": next_round, "total": total}


def load_session(year, round_num):
    """Load a race session with only results data (no telemetry/laps)."""
    session = fastf1.get_session(year, round_num, 'R')
    session.load(telemetry=False, laps=False, messages=False, weather=False)
    return session


def _compute_standings(year=2026):
    """
    Compute cumulative driver and constructor standings by loading each
    completed race session and summing points.
    """
    schedule = get_schedule(year)
    now = _utc_now()

    def _to_utc(dt):
        if hasattr(dt, 'tzinfo') and dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    driver_points = defaultdict(float)
    driver_info = {}
    constructor_points = defaultdict(float)

    for _, race in schedule.iterrows():
        race_date = _to_utc(race['EventDate'])
        if race_date >= now:
            break

        round_num = int(race['RoundNumber'])
        try:
            session = load_session(year, round_num)
            if session.results is None:
                continue
            for _, r in session.results.iterrows():
                name = f"{r['FirstName']} {r['LastName']}"
                team = r['TeamName']
                pts = float(r['Points'])

                driver_points[name] += pts
                driver_info[name] = {
                    'firstName': r['FirstName'],
                    'lastName': r['LastName'],
                    'code': r['Abbreviation'],
                    'team': team,
                    'number': str(r['DriverNumber']),
                }
                constructor_points[team] += pts
        except Exception as e:
            print(f"[WARN] Could not load round {round_num} ({year}): {e}")
            continue

    sorted_drivers = sorted(driver_points.items(), key=lambda x: -x[1])
    driver_standings = [
        {"position": i + 1, **driver_info[name], "points": pts}
        for i, (name, pts) in enumerate(sorted_drivers)
    ]

    sorted_constructors = sorted(constructor_points.items(), key=lambda x: -x[1])
    constructor_standings = [
        {"position": i + 1, "name": team, "points": pts}
        for i, (team, pts) in enumerate(sorted_constructors)
    ]

    return {
        "drivers": driver_standings,
        "constructors": constructor_standings,
    }


def _session_to_results(session):
    """Convert a session's results DF to a JSON-friendly list."""
    results_list = []
    if session.results is not None:
        for _, r in session.results.iterrows():
            results_list.append({
                "position": int(r['Position']),
                "givenName": r['FirstName'],
                "familyName": r['LastName'],
                "code": r['Abbreviation'],
                "constructor": r['TeamName'],
                "points": float(r['Points']),
                "number": str(r['DriverNumber']),
            })
    return results_list


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Pit Wall API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/years")
def api_years():
    """
    List F1 seasons that fastf1 can access.
    Returns a reasonable range of modern seasons.
    """
    # Probe a handful of years to confirm data exists
    known = []
    for y in range(2020, _utc_now().year + 2):
        try:
            s = fastf1.get_event_schedule(y)
            if s is not None and len(s) > 0:
                known.append(y)
        except Exception:
            continue
    return {"years": [y for y in sorted(set(known))]}


@app.get("/api/calendar")
def api_calendar(year: int = Query(default=None)):
    """Full season calendar."""
    y = _resolve_year(year)
    schedule = get_schedule(y)
    races = []
    for _, race in schedule.iterrows():
        race_name = race['EventName']
        races.append({
            "round": int(race['RoundNumber']),
            "raceName": race_name,
            "location": str(race.get('Location', '')),
            "country": str(race.get('Country', '')),
            "date": str(pd.to_datetime(race['EventDate']).date()),
        })
    return {"year": y, "races": races}


@app.get("/api/next-race")
def api_next_race(year: int = Query(default=None)):
    """Next race details with round info."""
    y = _resolve_year(year)
    schedule = get_schedule(y)
    ri = get_round_info(y)

    if ri['next'] is None:
        raise HTTPException(404, "No upcoming races")

    race = schedule[schedule['RoundNumber'] == ri['next']]
    if race.empty:
        raise HTTPException(404, "Race not found in schedule")
    race = race.iloc[0]

    return {
        "year": y,
        "round": int(race['RoundNumber']),
        "raceName": race['EventName'],
        "circuit": str(race.get('Location', '')),
        "country": str(race.get('Country', '')),
        "date": str(pd.to_datetime(race['EventDate']).date()),
        "totalRaces": ri['total'],
    }


@app.get("/api/standings")
def api_standings(year: int = Query(default=None), refresh: bool = False):
    """
    Driver and Constructor championship standings.
    Computed from official F1 session data via FastF1.
    """
    global _data_cache
    y = _resolve_year(year)

    if y not in _data_cache or _data_cache[y]["standings"] is None or refresh:
        _data_cache[y] = {
            "standings": _compute_standings(y),
            "cached_at": _utc_now().isoformat(),
        }

    return {
        "year": y,
        "cached_at": _data_cache[y]["cached_at"],
        **_data_cache[y]["standings"],
    }


@app.get("/api/last-race")
def api_last_race(year: int = Query(default=None)):
    """Last race results with podium."""
    y = _resolve_year(year)
    ri = get_round_info(y)
    if ri['current'] is None:
        return {"race": None, "results": []}

    try:
        session = load_session(y, ri['current'])
        results_list = _session_to_results(session)
        return {
            "race": {
                "raceName": session.event['EventName'],
                "circuit": session.event.get('Location', ''),
                "round": ri['current'],
                "season": y,
            },
            "results": results_list,
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/race/{round_num}")
def api_race_result(round_num: int, year: int = Query(default=None)):
    """Results for a specific round. Used by calendar winner display."""
    y = _resolve_year(year)
    try:
        session = load_session(y, round_num)
        results_list = _session_to_results(session)
        return {
            "race": {
                "raceName": session.event['EventName'],
                "round": round_num,
                "season": y,
            },
            "results": results_list,
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/info")
def api_info(year: int = Query(default=None)):
    """Basic season info."""
    y = _resolve_year(year)
    ri = get_round_info(y)
    return {
        "season": y,
        "currentRound": ri['current'],
        "nextRound": ri['next'],
        "totalRaces": ri['total'],
    }


@app.get("/")
def api_index():
    """Serve the frontend."""
    if os.path.exists(INDEX_PATH):
        return FileResponse(INDEX_PATH)
    return {"error": "index.html not found", "path": INDEX_PATH}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8766))
    print(f"🏎️  Pit Wall API starting on http://localhost:{port}")
    print(f"   Multi-season: append ?year=YYYY to any /api/ endpoint")
    print(f"   Serving frontend from: {INDEX_PATH}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
