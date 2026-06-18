# F1 Dashboard - My Personal Pit Wall

I've been building this dashboard to keep track of everything F1 - race results, standings, calendar, and the next race - all in one place. It pulls data from the official F1 API through a local Python server and displays it in a clean, grid-based layout.

## What's On The Dashboard

The hero section shows the upcoming race with a live countdown, round badge, and circuit name. Below that, there are three columns:
- Driver standings showing top 10 with their team and points
- Constructor standings with all 10 teams
- Race points from the last race

The calendar section has all the races for the season with flag emojis, dates, and winner for completed rounds.


## Visit the page:

https://vineshf1.github.io/F1-Dashboard/


## Tech Stuff

Vanilla HTML, CSS, and JavaScript on the frontend. Python FastAPI with FastF1 on the backend talking directly to the official F1 API. No external API keys needed.
