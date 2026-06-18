#!/usr/bin/env python3
"""
Generate all F1 data as static JSON files for GitHub Pages.
Run locally or in a GitHub Action — no server needed.
Output goes to ./data/
"""

import os
import json
from datetime import datetime, timezone
from collections import defaultdict

import fastf1
import pandas as pd


CACHE_DIR = os.path.join(os.environ.get('TEMP', '/tmp'), 'pitwall_cache')
os.makedirs(CACHE_DIR, exist_ok=True)
fastf1.Cache.enable_cache(CACHE_DIR)

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(OUT_DIR, exist_ok=True)

YEAR = datetime.now(timezone.utc).year


def _utc_now():
    return datetime.now(timezone.utc)


def _to_utc(dt):
    if hasattr(dt, 'tzinfo') and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def get_schedule(year):
    schedule = fastf1.get_event_schedule(year)
    return schedule[schedule['RoundNumber'] > 0].copy()


def get_round_info(year):
    schedule = get_schedule(year)
    now = _utc_now()
    total = len(schedule)
    current = None
    next_round = None
    for _, r in schedule.iterrows():
        race_date = _to_utc(r['EventDate'])
        if race_date <= now:
            current = int(r['RoundNumber'])
        elif next_round is None:
            next_round = int(r['RoundNumber'])
            break
    return {"current": current, "next": next_round, "total": total}


def load_session(year, round_num):
    session = fastf1.get_session(year, round_num, 'R')
    session.load(telemetry=False, laps=False, messages=False, weather=False)
    return session


def _session_to_results(session):
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


def generate_calendar(year):
    """Full season calendar."""
    schedule = get_schedule(year)
    races = []
    for _, race in schedule.iterrows():
        races.append({
            "round": int(race['RoundNumber']),
            "raceName": race['EventName'],
            "location": str(race.get('Location', '')),
            "country": str(race.get('Country', '')),
            "date": str(pd.to_datetime(race['EventDate']).date()),
        })
    return {"year": year, "races": races}


def generate_next_race(year):
    """Next race details."""
    schedule = get_schedule(year)
    ri = get_round_info(year)
    if ri['next'] is None:
        return None
    race = schedule[schedule['RoundNumber'] == ri['next']]
    if race.empty:
        return None
    race = race.iloc[0]
    return {
        "year": year,
        "round": int(race['RoundNumber']),
        "raceName": race['EventName'],
        "circuit": str(race.get('Location', '')),
        "country": str(race.get('Country', '')),
        "date": str(pd.to_datetime(race['EventDate']).date()),
        "totalRaces": ri['total'],
    }


def generate_standings(year):
    """Cumulative driver and constructor standings."""
    schedule = get_schedule(year)
    now = _utc_now()
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
            print(f"[WARN] Round {round_num} ({year}): {e}")
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
        "year": year,
        "cached_at": _utc_now().isoformat(),
        "drivers": driver_standings,
        "constructors": constructor_standings,
    }


def generate_last_race(year):
    """Last completed race results."""
    ri = get_round_info(year)
    if ri['current'] is None:
        return {"race": None, "results": []}
    try:
        session = load_session(year, ri['current'])
        return {
            "race": {
                "raceName": session.event['EventName'],
                "circuit": session.event.get('Location', ''),
                "round": ri['current'],
                "season": year,
            },
            "results": _session_to_results(session),
        }
    except Exception as e:
        print(f"[WARN] Last race: {e}")
        return {"race": None, "results": []}


def generate_race_result(year, round_num):
    """Results for a single round."""
    try:
        session = load_session(year, round_num)
        return {
            "race": {
                "raceName": session.event['EventName'],
                "round": round_num,
                "season": year,
            },
            "results": _session_to_results(session),
        }
    except Exception as e:
        print(f"[WARN] Race {round_num}: {e}")
        return None


def main():
    print(f"Generating F1 data for {YEAR}...")
    os.makedirs(OUT_DIR, exist_ok=True)

    # Calendar
    cal = generate_calendar(YEAR)
    with open(os.path.join(OUT_DIR, "calendar.json"), "w") as f:
        json.dump(cal, f)
    print(f"  calendar.json — {len(cal['races'])} races")

    # Next race
    nr = generate_next_race(YEAR)
    with open(os.path.join(OUT_DIR, "next-race.json"), "w") as f:
        json.dump(nr, f)
    print(f"  next-race.json — round {nr['round'] if nr else 'none'}")

    # Standings
    st = generate_standings(YEAR)
    with open(os.path.join(OUT_DIR, "standings.json"), "w") as f:
        json.dump(st, f)
    print(f"  standings.json — {len(st['drivers'])} drivers, {len(st['constructors'])} constructors")

    # Last race
    lr = generate_last_race(YEAR)
    with open(os.path.join(OUT_DIR, "last-race.json"), "w") as f:
        json.dump(lr, f)
    print(f"  last-race.json — round {lr['race']['round'] if lr['race'] else 'none'}")

    # Individual race results (for calendar winner column)
    schedule = get_schedule(YEAR)
    now = _utc_now()
    generated = 0
    for _, race in schedule.iterrows():
        race_date = _to_utc(race['EventDate'])
        if race_date >= now:
            break
        round_num = int(race['RoundNumber'])
        result = generate_race_result(YEAR, round_num)
        if result:
            with open(os.path.join(OUT_DIR, f"race-{round_num}.json"), "w") as f:
                json.dump(result, f)
            generated += 1
    print(f"  race-*.json — {generated} completed rounds")

    print(f"\nDone — {OUT_DIR}/")


if __name__ == "__main__":
    main()
