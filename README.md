# F1 Dashboard - My Personal Pit Wall

Personal F1 dashboard that pulls race results, standings, and calendar from the **official formula1.com website** (standings) and the **FastF1 API** (race results & calendar). Data updates automatically via GitHub Actions every 4 hours + Monday 12 AM IST.

## What's On The Dashboard

- **Hero** — Upcoming race with live countdown, round badge, circuit
- **Drivers' Championship** — Top 10 with team & points (scraped from formula1.com)
- **Constructors' Cup** — All 11 teams with points (scraped from formula1.com)
- **Race Results** — Last race's full finishing order
- **Calendar** — Full season with flag emojis, dates, winners for completed rounds

## Visit the page:

**https://vineshf1.github.io/F1-Dashboard/**

## Data Updates

| Trigger | When | What |
|---|---|---|
| ⏰ Every 4 hours | 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC | Full data refresh |
| 📅 Monday IST | Sun 18:30 UTC (= Mon 12 AM IST) | Guaranteed post-race update |
| ✋ Manual | `workflow_dispatch` in GitHub Actions | On-demand refresh |

- **Standings** scraped directly from `formula1.com/en/results/2026/drivers` and `/team`
- **Race results & calendar** loaded via FastF1 (official F1 API)
- **Cutoff logic:** Races are considered complete on **Monday 12 AM IST** (Sun 18:30 UTC)

## Local Development

```bash
# Start the API + static file server
python server.py

# Or use VS Code Live Server on index.html
# (API_BASE auto-detects Live Server vs FastAPI server)
```

Open `http://localhost:8766` (FastAPI) or `http://127.0.0.1:5500/index.html` (Live Server).

For initial data generation:
```bash
python generate_data.py
```

## Tech Stack

- **Frontend:** Vanilla HTML, CSS, JavaScript
- **Backend:** Python FastAPI + FastF1 (race data), BeautifulSoup (standings scraping)
- **Deployment:** GitHub Actions → GitHub Pages (static JSON files)
- **No API keys needed**
